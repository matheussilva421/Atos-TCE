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


class FillError(RuntimeError):
    """Raised when a fill request cannot be created or advanced."""


def identity_of(process: Mapping[str, Any]) -> dict[str, Any]:
    """The identity contract the extension must echo back."""

    return {
        "processKey": str(process.get("process_key") or ""),
        "interestedNormalized": str(process.get("interested_normalized") or ""),
        "portalActId": process.get("portal_act_id"),
    }


def _verified_fields(result: Mapping[str, Any]) -> dict[str, Any]:
    """A fill only counts when every changed field reread exactly as proposed."""

    field_results = result.get("field_results")
    if not isinstance(field_results, Mapping) or not field_results:
        return {"ok": False, "reason": "o portal não devolveu a releitura dos campos"}
    for name, entry in field_results.items():
        if not isinstance(entry, Mapping):
            return {"ok": False, "reason": f"resultado inválido para o campo {name}"}
        status = entry.get("status")
        if status in {"failed", "disabled", "not_found", "missing"}:
            return {"ok": False, "reason": f"o campo {name} não foi confirmado ({status})"}
        if status == "changed" and entry.get("after") != entry.get("proposed"):
            return {"ok": False, "reason": f"o campo {name} releu diferente do proposto"}
    return {"ok": True, "reason": None}


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
            self._fail(request, str(result.get("error") or "não foi possível abrir o ato"))
            return
        mismatch = self._identity_mismatch(process, result.get("identity"))
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
            self._fail(request, str(result.get("error") or "não foi possível ler o formulário"))
            return
        mismatch = self._identity_mismatch(process, result.get("identity"))
        if mismatch:
            self._block(request, mismatch)
            return
        self._store.update_fill_request(
            int(request["id"]), state="PREFLIGHT", error=None, form_snapshot=dict(result)
        )
        self._run_preflight(request, process, result)

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
            self._block(request, reason)
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
            },
        )

    def _handle_fill_result(
        self, request: Mapping[str, Any], result: Mapping[str, Any]
    ) -> None:
        """Only a fully reread result marks the act as filled."""

        process_id = int(request["process_id"])
        if result.get("ok") is not True:
            self._fail(request, str(result.get("error") or result.get("code") or "preenchimento recusado pelo portal"))
            return
        verification = _verified_fields(result)
        if not verification["ok"]:
            self._block(request, verification["reason"])
            return
        self._store.update_fill_request(
            int(request["id"]),
            state="PREENCHIDO",
            error=None,
            current_command_id=None,
            form_snapshot={"field_results": result.get("field_results") or {}},
        )
        self._store.set_process_status(
            process_id,
            "PREENCHIDO",
            event_type="form_filled",
            payload={
                "fill_request_id": int(request["id"]),
                "fields": sorted(
                    name
                    for name, entry in (result.get("field_results") or {}).items()
                    if isinstance(entry, Mapping) and entry.get("status") == "changed"
                ),
                "preserved": sorted(
                    name
                    for name, entry in (result.get("field_results") or {}).items()
                    if isinstance(entry, Mapping) and entry.get("status") == "preserved"
                ),
            },
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
        self._set_process_state(
            int(request["process_id"]), "BLOQUEADO", "fill_blocked", {"reason": reason}
        )

    def _fail(self, request: Mapping[str, Any], reason: str) -> None:
        self._store.update_fill_request(
            int(request["id"]), state="ERRO", error=reason, current_command_id=None
        )
        self._set_process_state(
            int(request["process_id"]), "ERRO", "fill_failed", {"reason": reason}
        )

    def _set_process_state(
        self, process_id: int, status: str, event_type: str, payload: Mapping[str, Any]
    ) -> None:
        self._store.set_process_status(
            process_id, status, event_type=event_type, payload=dict(payload)
        )
