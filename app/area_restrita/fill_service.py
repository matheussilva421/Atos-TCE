"""Backend-owned act filling workflow (M5).

The Mesa creates a fill *request*; the extension only receives specific
commands (``OPEN_ACT``, ``READ_FORM``, ``FILL_FORM``) and reports results. The
state machine below is the only place that decides what happens next, and it
refuses to advance on a stale, foreign or unexpected command result.

There is no ``SUBMIT`` step by design: the final completion click stays with
the operator.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..analysis import MANDATORY_FIELDS
from ..core.identity import normalize_interested
from ..core.store import Store
from .preflight import FillBlocked, build_fill_plan

FILL_STATES: tuple[str, ...] = (
    "OPENING",
    "READING",
    "PREFLIGHT",
    "FILLING",
    "PREENCHIDO",
    "BLOQUEADO",
    "ERRO",
)

TERMINAL_FILL_STATES: frozenset[str] = frozenset({"PREENCHIDO", "BLOQUEADO", "ERRO"})

#: Which command type each state is waiting for.
EXPECTED_COMMAND: dict[str, str] = {
    "OPENING": "OPEN_ACT",
    "READING": "READ_FORM",
    "FILLING": "FILL_FORM",
}

#: Navigation outcomes OPEN_ACT may report. OPEN_ACT only proves that the
#: navigation happened: the authoritative identity of the act arrives with
#: READ_FORM, so an outcome without identity still moves the request to
#: READING. Anything outside this vocabulary blocks instead of advancing.
OPEN_ACT_ACTIONS: frozenset[str] = frozenset({"open_act", "select_interested", "already_open"})
OPEN_ACT_SCREENS: frozenset[str] = frozenset({"list", "interested", "form", "buttons"})

#: Refusals the extension reports when the page itself was ambiguous. They are
#: not portal failures: the workflow stops for a human instead of looking like
#: a transient error the operator could retry blindly.
EXTENSION_BLOCK_CODES: frozenset[str] = frozenset(
    {
        "FORM_AMBIGUOUS",
        "IDENTITY_AMBIGUOUS",
        "IDENTITY_MISMATCH",
        "IDENTITY_MISMATCH_AFTER_WRITE",
    }
)


class FillError(RuntimeError):
    """Raised when a fill request cannot be created or advanced."""


def identity_of(process: Mapping[str, Any]) -> dict[str, Any]:
    """The identity contract the extension must echo back."""

    return {
        "processKey": str(process.get("process_key") or ""),
        "interestedNormalized": str(process.get("interested_normalized") or ""),
        "portalActId": process.get("portal_act_id"),
    }


def summarize_field_results(
    field_results: Mapping[str, Any] | None, mandatory_fields: tuple[str, ...]
) -> dict[str, Any]:
    """Summarize a field pass without turning local failures into request errors."""

    results = field_results if isinstance(field_results, Mapping) else {}
    changed: list[str] = []
    preserved: list[str] = []
    unresolved: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    mandatory = set(mandatory_fields)

    for raw_name, raw_entry in results.items():
        name = str(raw_name)
        seen.add(name)
        if not isinstance(raw_entry, Mapping):
            entry: Mapping[str, Any] = {}
            status = "failed"
            warning = "invalid_field_result"
        else:
            entry = raw_entry
            status = str(entry.get("status") or "failed")
            warning = entry.get("warning") or entry.get("error")

        if status == "changed":
            changed.append(name)
            satisfied = entry.get("proposed") is not None and entry.get("after") == entry.get("proposed")
            if not satisfied:
                warning = warning or "readback_mismatch"
        elif status == "preserved":
            preserved.append(name)
            satisfied = (
                not warning
                and entry.get("proposed") is not None
                and entry.get("after") == entry.get("proposed")
            )
        else:
            satisfied = False

        if warning:
            warnings.append({"field": name, "code": str(warning), "status": status})
        if not satisfied:
            unresolved.append(
                {
                    "field": name,
                    "status": status,
                    "code": str(warning or status),
                    **({"error": str(entry["error"])} if entry.get("error") else {}),
                }
            )

    for name in sorted(mandatory - seen):
        missing = {"field": name, "status": "missing_proposal", "code": "missing_field_result"}
        unresolved.append(missing)
        warnings.append({"field": name, "code": "missing_field_result", "status": "missing_proposal"})

    unresolved.sort(key=lambda item: (item["field"], item["status"]))
    warnings.sort(key=lambda item: (item["field"], item["code"]))
    mandatory_satisfied = not any(item["field"] in mandatory for item in unresolved)
    return {
        "changed": changed,
        "preserved": preserved,
        "unresolved": unresolved,
        "warnings": warnings,
        "mandatory_satisfied": mandatory_satisfied,
    }


class FillService:
    def __init__(self, store: Store, *, preflight: Any | None = None) -> None:
        self._store = store
        self._preflight = preflight or build_fill_plan

    # ------------------------------------------------------------- entry points

    def request_fill(self, process_id: int) -> int:
        """Start the automatic ``Preencher ato`` flow for one PRONTO process."""

        process = self._store.get_process(process_id)
        if process is None:
            raise FillError(f"unknown process: {process_id}")
        if str(process.get("status")) != "PRONTO":
            raise FillError("somente um processo PRONTO pode ser preenchido")
        request_id = self._store.create_fill_request(
            int(process_id), state="OPENING", mode="automatic"
        )
        command_id = self._store.queue_fill_command(
            "OPEN_ACT", {"identity": identity_of(process)}, request_id
        )
        self._store.update_fill_request(
            request_id, state="OPENING", current_command_id=command_id
        )
        self._store.add_workflow_event(
            int(process_id), "fill_requested", {"fill_request_id": request_id, "mode": "automatic"}
        )
        return request_id

    def request_manual_fill(self, form_snapshot: Mapping[str, Any] | None) -> int:
        """Create a request from a form the operator opened by hand.

        The snapshot must identify exactly one PRONTO process; zero or several
        matches block, because filling the wrong act is worse than not filling.
        """

        snapshot = form_snapshot if isinstance(form_snapshot, Mapping) else {}
        identity = snapshot.get("identity")
        if not isinstance(identity, Mapping):
            raise FillError("o formulário aberto não trouxe identidade")
        process_key = str(identity.get("processKey") or identity.get("process_key") or "").strip()
        interested = normalize_interested(
            identity.get("interestedNormalized") or identity.get("interested_normalized") or ""
        )
        if not process_key or not interested:
            raise FillError("identidade incompleta no formulário aberto")
        matches = [
            process
            for process in self._store.list_processes(status="PRONTO")
            if str(process["process_key"]) == process_key
            and str(process["interested_normalized"]) == interested
        ]
        if not matches:
            raise FillError("nenhum processo PRONTO corresponde ao formulário aberto")
        if len(matches) > 1:
            raise FillError("mais de um processo PRONTO corresponde ao formulário aberto")
        process_id = int(matches[0]["id"])
        request_id = self._store.create_fill_request(
            process_id, state="PREFLIGHT", mode="manual", form_snapshot=dict(snapshot)
        )
        self._store.add_workflow_event(
            process_id, "fill_requested", {"fill_request_id": request_id, "mode": "manual"}
        )
        # The operator already opened the act, so the manual path skips
        # OPEN_ACT/READ_FORM and goes straight to the same backend preflight the
        # automatic path uses: identical snapshot, identical plan, one filler.
        process = self._store.get_process(process_id)
        if process is None:
            raise FillError("processo desapareceu durante o preenchimento manual")
        self._run_preflight({"id": request_id, "process_id": process_id}, process, snapshot)
        return request_id

    # ------------------------------------------------------------ state machine

    def handle_command_result(self, command_id: int, result: Mapping[str, Any] | None) -> None:
        """Advance the request that owns ``command_id``, if it still does."""

        command = self._store.get_extension_command(int(command_id))
        if command is None:
            raise FillError(f"unknown command: {command_id}")
        request_id = command.get("fill_request_id")
        if not request_id:
            return
        request = self._store.get_fill_request(int(request_id))
        if request is None:
            raise FillError(f"unknown fill request: {request_id}")
        if request["state"] in TERMINAL_FILL_STATES:
            return
        current = request.get("current_command_id")
        if current is None or int(current) != int(command_id):
            # Only the command the request is actually waiting for may move it;
            # anything else is a stale, foreign or already applied result.
            return
        if EXPECTED_COMMAND.get(str(request["state"])) != str(command.get("type")):
            # A stale or foreign result must never move the workflow.
            return
        payload = result if isinstance(result, Mapping) else {}
        handler = {
            "OPENING": self._handle_open_result,
            "READING": self._handle_read_result,
            "FILLING": self._handle_fill_result,
        }.get(str(request["state"]))
        if handler is None:
            return
        handler(request, payload)

    def _handle_open_result(self, request: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        process = self._store.get_process(int(request["process_id"]))
        if process is None:
            self._block(request, "processo desapareceu durante o preenchimento")
            return
        if result.get("ok") is not True:
            self._refuse(request, result, "não foi possível abrir o ato")
            return
        action = str(result.get("action") or "").strip().lower()
        screen = str(result.get("screen") or "").strip().lower()
        if action not in OPEN_ACT_ACTIONS or screen not in OPEN_ACT_SCREENS:
            self._block(
                request,
                "resultado de navegação desconhecido: "
                f"action={action or 'ausente'}, screen={screen or 'ausente'}",
            )
            return
        # Identity is optional at this stage: it is a defensive echo, never a
        # requirement. When the extension does report one, it must agree.
        identity = result.get("identity")
        if isinstance(identity, Mapping) and identity:
            mismatch = self._identity_mismatch(process, identity)
            if mismatch:
                self._block(request, mismatch)
                return
        command_id = self._store.queue_fill_command(
            "READ_FORM", {"identity": identity_of(process)}, int(request["id"])
        )
        self._store.update_fill_request(
            int(request["id"]), state="READING", current_command_id=command_id, error=None
        )

    def _handle_read_result(self, request: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        process = self._store.get_process(int(request["process_id"]))
        if process is None:
            self._block(request, "processo desapareceu durante o preenchimento")
            return
        if result.get("ok") is not True:
            self._refuse(request, result, "não foi possível ler o formulário")
            return
        mismatch = self._identity_mismatch(process, result.get("identity"))
        if mismatch:
            self._block(request, mismatch)
            return
        previous_snapshot = request.get("form_snapshot")
        stale_retries = (
            int(previous_snapshot.get("stale_generation_retries") or 0)
            if isinstance(previous_snapshot, Mapping)
            else 0
        )
        snapshot = dict(result)
        snapshot["stale_generation_retries"] = stale_retries
        self._store.update_fill_request(
            int(request["id"]), state="PREFLIGHT", error=None, form_snapshot=snapshot
        )
        self._run_preflight(request, process, snapshot)

    def _run_preflight(
        self, request: Mapping[str, Any], process: Mapping[str, Any], snapshot: Mapping[str, Any]
    ) -> None:
        """Decide the exact fields to write, or block without touching a control."""

        try:
            plan = self._preflight(process, snapshot)
        except FillBlocked as blocked:
            reason = blocked.code
            if blocked.details:
                reason = f"{blocked.code}: {', '.join(blocked.details)}"
            if blocked.code in {"IDENTITY_MISSING", "IDENTITY_MISMATCH", "PROCESS_MISSING"}:
                self._block(request, reason)
            else:
                self._fail(request, reason)
            return
        except Exception as error:  # a broken plan must never reach the portal
            self._fail(request, f"preflight falhou: {type(error).__name__}")
            return
        command_id = self._store.queue_fill_command(
            "FILL_FORM",
            {
                "identity": plan.identity,
                "generation": plan.generation,
                "fields": plan.fields,
                "preserved": plan.preserved,
            },
            int(request["id"]),
        )
        self._store.update_fill_request(
            int(request["id"]),
            state="FILLING",
            current_command_id=command_id,
            error=None,
            form_snapshot={
                "plan": plan.fields,
                "preserved": plan.preserved,
                "warnings": plan.warnings,
                "legal_decision": plan.legal_decision,
                "modality_decision": plan.modality_decision,
                "stale_generation_retries": int(
                    (request.get("form_snapshot") or {}).get("stale_generation_retries", 0)
                    if isinstance(request.get("form_snapshot"), Mapping)
                    else 0
                ),
            },
        )

    def _handle_fill_result(
        self, request: Mapping[str, Any], result: Mapping[str, Any]
    ) -> None:
        """Record the field pass and promote only a fully satisfied process."""

        process_id = int(request["process_id"])
        if result.get("ok") is not True:
            if str(result.get("code") or "").strip().upper() == "STALE_GENERATION":
                self._retry_stale_generation(request)
                return
            self._refuse(request, result, "preenchimento recusado pelo portal")
            return
        raw_results = result.get("field_results")
        if not isinstance(raw_results, Mapping):
            self._fail(request, "o portal não devolveu os resultados dos campos")
            return
        process = self._store.get_process(process_id)
        if process is None:
            self._block(request, "processo desapareceu durante o preenchimento")
            return
        mismatch = self._identity_mismatch(process, result.get("identity"))
        if mismatch:
            self._block(request, mismatch)
            return
        generation_after = result.get("generation_after")
        if (
            not isinstance(generation_after, int)
            or isinstance(generation_after, bool)
            or generation_after < 1
        ):
            self._fail(request, "resultado de preenchimento sem generation_after válida")
            return

        snapshot = request.get("form_snapshot")
        snapshot = dict(snapshot) if isinstance(snapshot, Mapping) else {}
        field_results = {
            str(name): dict(entry) if isinstance(entry, Mapping) else entry
            for name, entry in raw_results.items()
        }
        proposals = {
            str(entry.get("field_name")): str(entry.get("value")).strip()
            for entry in process.get("fields") or []
            if isinstance(entry, Mapping)
            and entry.get("status") == "found"
            and entry.get("value") is not None
            and str(entry.get("value")).strip()
        }
        preserved_values = snapshot.get("preserved")
        preserved_values = preserved_values if isinstance(preserved_values, Mapping) else {}
        preflight_warnings = snapshot.get("warnings")
        preflight_warnings = preflight_warnings if isinstance(preflight_warnings, list) else []
        legal_decision = snapshot.get("legal_decision")
        legal_value = (
            str(legal_decision.get("option_value"))
            if isinstance(legal_decision, Mapping) and legal_decision.get("option_value") is not None
            else None
        )

        for name in MANDATORY_FIELDS:
            if name in field_results:
                continue
            if name in preserved_values:
                current = str(preserved_values[name])
                divergent = any(
                    "valor divergente existente preservado" in str(warning)
                    and str(warning).endswith(f": {name}")
                    for warning in preflight_warnings
                )
                proposed = legal_value if name == "fundamento_legal" and legal_value is not None else proposals.get(name)
                field_results[name] = {
                    "status": "preserved",
                    "before": current,
                    "after": current,
                    "proposed": proposed if proposed is not None else current,
                    **({"warning": "existing_value_divergence"} if divergent else {}),
                }
                continue

            field_warnings = [
                str(item)
                for item in preflight_warnings
                if str(item).endswith(f": {name}") or str(item).startswith(f"{name}:")
            ]
            if any("controle ausente" in warning for warning in field_warnings):
                status = "not_found"
                code = "control_not_found"
            elif any(
                "desabilitado" in warning or "somente leitura" in warning
                for warning in field_warnings
            ):
                status = "disabled"
                code = "control_disabled"
            elif any("sem proposta" in warning for warning in field_warnings):
                status = "missing_proposal"
                code = "missing_proposal"
            elif any(
                "opção indisponível" in warning
                or "sem decisão automática" in warning
                or "LEGAL_OPTIONS_EMPTY" in warning
                for warning in field_warnings
            ):
                status = "option_unavailable"
                code = "option_unavailable"
            else:
                status = "failed"
                code = "field_result_missing"
            field_results[name] = {
                "status": status,
                "proposed": proposals.get(name),
                "warning": code,
            }

        summary = summarize_field_results(field_results, MANDATORY_FIELDS)
        extension_warnings = result.get("warnings")
        if isinstance(extension_warnings, list):
            operation_warnings = [*preflight_warnings, *extension_warnings]
        else:
            operation_warnings = list(preflight_warnings)
        snapshot.update(
            {
                "field_results": field_results,
                "summary": summary,
                "operation_warnings": operation_warnings,
            }
        )
        self._store.update_fill_request(
            int(request["id"]),
            state="PREENCHIDO",
            error=None,
            current_command_id=None,
            form_snapshot=snapshot,
        )
        payload = {"fill_request_id": int(request["id"]), **summary}
        if summary["mandatory_satisfied"]:
            self._store.set_process_status(
                process_id, "PREENCHIDO", event_type="form_filled", payload=payload
            )
        else:
            self._store.add_workflow_event(process_id, "form_filled_partial", payload)

    def _retry_stale_generation(self, request: Mapping[str, Any]) -> None:
        snapshot = request.get("form_snapshot")
        snapshot = dict(snapshot) if isinstance(snapshot, Mapping) else {}
        retries = int(snapshot.get("stale_generation_retries") or 0)
        if retries >= 1:
            self._fail(request, "generation do formulário mudou novamente após a releitura")
            return
        process = self._store.get_process(int(request["process_id"]))
        if process is None:
            self._block(request, "processo desapareceu durante o preenchimento")
            return
        command_id = self._store.queue_fill_command(
            "READ_FORM", {"identity": identity_of(process)}, int(request["id"])
        )
        snapshot["stale_generation_retries"] = 1
        self._store.update_fill_request(
            int(request["id"]),
            state="READING",
            current_command_id=command_id,
            error=None,
            form_snapshot=snapshot,
        )
        self._store.add_workflow_event(
            int(request["process_id"]),
            "fill_generation_stale_retry",
            {"fill_request_id": int(request["id"]), "retry": 1},
        )

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _identity_mismatch(
        process: Mapping[str, Any], identity: Mapping[str, Any] | None
    ) -> str | None:
        if not isinstance(identity, Mapping):
            return "a extensão não informou a identidade do ato aberto"
        process_key = str(identity.get("processKey") or identity.get("process_key") or "").strip()
        interested = normalize_interested(
            identity.get("interestedNormalized") or identity.get("interested_normalized") or ""
        )
        if process_key != str(process.get("process_key")) or interested != str(
            process.get("interested_normalized")
        ):
            return "identidade divergente entre o ato aberto e o processo selecionado"
        return None

    def _block(self, request: Mapping[str, Any], reason: str) -> None:
        self._store.update_fill_request(
            int(request["id"]), state="BLOQUEADO", error=reason, current_command_id=None
        )
        self._store.add_workflow_event(
            int(request["process_id"]),
            "fill_blocked",
            {"fill_request_id": int(request["id"]), "reason": reason},
        )

    def _refuse(
        self, request: Mapping[str, Any], result: Mapping[str, Any], fallback: str
    ) -> None:
        """A refusal from the extension is a block when the page was ambiguous."""

        code = str(result.get("code") or "").strip().upper()
        reason = str(result.get("error") or code or fallback)
        if code in EXTENSION_BLOCK_CODES:
            self._block(request, reason)
            return
        self._fail(request, reason)

    def _fail(self, request: Mapping[str, Any], reason: str) -> None:
        self._store.update_fill_request(
            int(request["id"]), state="ERRO", error=reason, current_command_id=None
        )
        self._store.add_workflow_event(
            int(request["process_id"]),
            "fill_failed",
            {"fill_request_id": int(request["id"]), "reason": reason},
        )
