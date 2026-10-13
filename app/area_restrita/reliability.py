"""Area Restrita reliability ledger and qualification evaluator (Reliability Reset, Phase 1).

Offline tests never promote a capability: only a real consecutive sequence in a
local ledger can move a capability from EXPERIMENTAL to QUALIFIED, and only a
portable normal-Chrome sequence can move it to PRODUCTION. Raw portal identity
is never persisted: it is reduced to a local HMAC-SHA256 before it reaches the
event log, and every event is validated against a private-key denylist first.

Storage lives under the local data root, never in the repository::

    <data-root>/reliability/events.jsonl
    <data-root>/reliability/capabilities.json
    <data-root>/reliability/identity.key

Phase 1 deliberately keeps this file SQLite-free and schema-free.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

#: Every capability the Reliability Reset tracks. All start UNQUALIFIED.
CAPABILITIES: tuple[str, ...] = (
    "manual_form_fill",
    "open_act",
    "select_interested",
    "return_to_list",
    "pagination",
    "next_process",
    "area_restrita_end_to_end",
)

#: The only environments a run may be recorded under.
ENVIRONMENTS: tuple[str, ...] = ("offline", "real-dev", "portable-normal-chrome")

#: QUALIFIED is earned on a real development sequence; PRODUCTION on a portable
#: normal-Chrome sequence. Nothing else may promote a capability.
QUALIFICATION_ENVIRONMENT = "real-dev"
PRODUCTION_ENVIRONMENT = "portable-normal-chrome"

#: The spec's gate. ``promote`` can never be asked for a lower one.
MIN_QUALIFICATION_RUNS = 20

# A manual AR-1 pass is countable only when the ledger independently records
# the successful path that FillService emits. Keep the expected state/result
# pairs here so the evaluator does not trust the writer or ``passed=true``.
MANUAL_FORM_FILL_EVIDENCE: tuple[tuple[str, str, str | None, str], ...] = (
    ("current_form_detected", "FORM_DETECTED", None, "FORM"),
    ("manual_fill_requested", "REQUEST_CREATED", "FORM", "PREFLIGHT"),
    ("preflight_completed", "PLAN_READY", "PREFLIGHT", "FILLING"),
    ("fill_command_completed", "SUCCEEDED", "FILLING", "PREENCHIDO"),
    ("reread_completed", "BEST_EFFORT_OK", "FORM_FILLED", "FORM_FILLED"),
)

#: Persisted codes are short machine tokens, never free text: a private value
#: smuggled into ``result_code``/``boundary``/``kind`` is refused, not stored.
CODE_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")
MAX_REASON_LENGTH = 512

#: One lock per local ledger, so a check-then-append is atomic inside the
#: threaded Mesa: a run can never gain a second terminal event.
_LOCKS_GUARD = threading.Lock()
_ROOT_LOCKS: dict[str, threading.RLock] = {}


def _lock_for(root: Path) -> threading.RLock:
    key = os.path.abspath(str(root))
    with _LOCKS_GUARD:
        lock = _ROOT_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _ROOT_LOCKS[key] = lock
        return lock

RELIABILITY_DIRNAME = "reliability"
EVENTS_FILENAME = "events.jsonl"
CAPABILITIES_FILENAME = "capabilities.json"
IDENTITY_KEY_FILENAME = "identity.key"

#: Keys that must never reach a persisted event, at any depth. Matched
#: case-insensitively against the exact key name.
FORBIDDEN_EVENT_KEYS: frozenset[str] = frozenset(
    {
        "process",
        "processkey",
        "process_key",
        "interested",
        "interestednormalized",
        "interested_normalized",
        "interestedname",
        "interested_name",
        "cpf",
        "matricula",
        "cookies",
        "cookie",
        "token",
        "tokens",
        "authorization",
        "auth",
        "password",
        "passwd",
        "secret",
        "sessionid",
        "session_id",
        "har",
        "html",
        "body",
    }
)

#: The identity fields a run may bind to. Everything else is dropped before the
#: value is hashed, so an unexpected private field can never be persisted.
_IDENTITY_FIELDS: tuple[tuple[str, str], ...] = (
    ("processKey", "process_key"),
    ("interestedNormalized", "interested_normalized"),
    ("portalActId", "portal_act_id"),
)


class ReliabilityError(RuntimeError):
    """Raised when a record would be unsafe or a promotion is not earned."""


class CapabilityState(StrEnum):
    UNQUALIFIED = "UNQUALIFIED"
    EXPERIMENTAL = "EXPERIMENTAL"
    QUALIFIED = "QUALIFIED"
    PRODUCTION = "PRODUCTION"


# --------------------------------------------------------------------- helpers


def canonical_identity(identity: Mapping[str, Any] | None) -> dict[str, str]:
    """Reduce an identity mapping to the fields the ledger is allowed to bind to."""

    if not isinstance(identity, Mapping):
        return {}
    canonical: dict[str, str] = {}
    for camel, snake in _IDENTITY_FIELDS:
        value = identity.get(camel)
        if value is None:
            value = identity.get(snake)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        canonical[camel] = text
    return canonical


def ensure_sanitized(event: Mapping[str, Any], *, path: str = "event") -> None:
    """Refuse an event that carries a private key anywhere in its tree."""

    stack: list[tuple[str, Any]] = [(path, event)]
    while stack:
        label, node = stack.pop()
        if isinstance(node, Mapping):
            for key, value in node.items():
                name = str(key)
                if name.strip().lower() in FORBIDDEN_EVENT_KEYS:
                    raise ReliabilityError(
                        f"campo privado não pode ser persistido: {label}.{name}"
                    )
                stack.append((f"{label}.{name}", value))
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                stack.append((f"{label}[{index}]", value))


def _require_member(value: str, allowed: Sequence[str], label: str) -> str:
    text = str(value)
    if text not in allowed:
        raise ReliabilityError(f"{label} desconhecido: {text!r} (esperado: {', '.join(allowed)})")
    return text


def _require_code(value: Any, label: str) -> str:
    """Refuse anything that is not a short machine code."""

    text = str(value).strip()
    if not CODE_PATTERN.fullmatch(text):
        raise ReliabilityError(
            f"{label} inválido: use um código curto [A-Za-z0-9_-]: {text[:40]!r}"
        )
    return text


def _require_run_id(value: Any, label: str = "run_id") -> str:
    text = str(value).strip()
    if not RUN_ID_PATTERN.fullmatch(text):
        raise ReliabilityError(f"{label} inválido: {text[:40]!r}")
    return text


# ------------------------------------------------------------------- recorder


class ReliabilityRecorder:
    """Append-only, sanitized reliability ledger for one local data root and build."""

    def __init__(self, data_root: str | os.PathLike[str], build_id: str) -> None:
        self._root = Path(data_root) / RELIABILITY_DIRNAME
        self._events_path = self._root / EVENTS_FILENAME
        self._capabilities_path = self._root / CAPABILITIES_FILENAME
        self._key_path = self._root / IDENTITY_KEY_FILENAME
        self._build_id = str(build_id)
        # Nothing touches the filesystem until a run or a state change is
        # recorded: reading the ledger must never create local state.
        self._key: bytes | None = None

    # ------------------------------------------------------------------ paths

    @property
    def root(self) -> Path:
        return self._root

    @property
    def build_id(self) -> str:
        return self._build_id

    def _ensure_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def _key_bytes(self) -> bytes:
        """The local HMAC key, created on the first write only."""

        if self._key is not None:
            return self._key
        with _lock_for(self._root):
            if self._key is not None:
                return self._key
            self._ensure_root()
            if self._key_path.exists():
                self._key = bytes.fromhex(
                    self._key_path.read_text(encoding="utf-8").strip()
                )
            else:
                key = secrets.token_bytes(32)
                self._key_path.write_text(key.hex(), encoding="utf-8")
                self._key = key
            return self._key

    # ------------------------------------------------------------- recording

    def start(
        self,
        capability: str,
        environment: str,
        browser_session_id: str | None = None,
        run_id: str | None = None,
    ) -> str:
        capability = _require_member(capability, CAPABILITIES, "capability")
        environment = _require_member(environment, ENVIRONMENTS, "environment")
        run_id = uuid.uuid4().hex if run_id is None else _require_run_id(run_id)
        if browser_session_id is not None:
            browser_session_id = _require_run_id(browser_session_id, "browser_session_id")
        self._append(
            {
                "type": "run_start",
                "run_id": run_id,
                "capability": capability,
                "environment": environment,
                "build_id": self._build_id,
                "browser_session_id": browser_session_id,
            }
        )
        return run_id

    def transition(
        self,
        run_id: str,
        *,
        boundary: str,
        state_before: str | None,
        state_after: str | None,
        result_code: str,
        elapsed_ms: int | None = None,
        expected_identity: Mapping[str, Any] | None = None,
        observed_identity: Mapping[str, Any] | None = None,
        generation_before: int | None = None,
        generation_after: int | None = None,
    ) -> None:
        self._append(
            {
                "type": "transition",
                "run_id": _require_run_id(run_id),
                "boundary": _require_code(boundary, "boundary"),
                "state_before": None if state_before is None else _require_code(state_before, "state_before"),
                "state_after": None if state_after is None else _require_code(state_after, "state_after"),
                "result_code": _require_code(result_code, "result_code"),
                "elapsed_ms": elapsed_ms,
                "expected_identity_hash": self._hash_identity(expected_identity),
                "observed_identity_hash": self._hash_identity(observed_identity),
                "generation_before": generation_before,
                "generation_after": generation_after,
            }
        )

    def intervention(self, run_id: str, kind: str) -> None:
        self._append(
            {"type": "intervention", "run_id": _require_run_id(run_id), "kind": _require_code(kind, "kind")}
        )

    def finish(self, run_id: str, *, passed: bool, result_code: str) -> None:
        run_id = _require_run_id(run_id)
        if not isinstance(passed, bool):
            # "false" is not False: a coerced string would silently record a pass.
            raise ReliabilityError("passed precisa ser um booleano real")
        with _lock_for(self._root):
            if self._has_finished(run_id):
                raise ReliabilityError(
                    f"execução {run_id} já tem resultado terminal; um novo finish foi recusado"
                )
            self._append(
                {
                    "type": "run_finished",
                    "run_id": run_id,
                    "passed": passed,
                    "result_code": _require_code(result_code, "result_code"),
                }
            )

    # ------------------------------------------------------------- state API

    def capabilities(self) -> dict[str, dict[str, Any]]:
        """Current state and streaks for every tracked capability."""

        stored = self._read_capabilities()
        result: dict[str, dict[str, Any]] = {}
        for capability in CAPABILITIES:
            entry = stored.get(capability, {})
            result[capability] = {
                "state": str(entry.get("state") or CapabilityState.UNQUALIFIED.value),
                "reason": str(entry.get("reason") or ""),
                "real_dev_streak": self.evaluate(
                    capability, QUALIFICATION_ENVIRONMENT
                )["streak"],
                "portable_streak": self.evaluate(
                    capability, PRODUCTION_ENVIRONMENT
                )["streak"],
            }
        return result

    def mark_experimental(self, capability: str, *, reason: str) -> None:
        """Record a capability as EXPERIMENTAL. Never a promotion."""

        capability = _require_member(capability, CAPABILITIES, "capability")
        self._write_state(capability, CapabilityState.EXPERIMENTAL, reason)

    def bootstrap_experimental_if_unset(
        self, capability: str, *, reason: str
    ) -> bool:
        """Initialize a packaged capability once without overriding local state."""

        capability = _require_member(capability, CAPABILITIES, "capability")
        with _lock_for(self._root):
            if capability in self._read_capabilities():
                return False
            self._write_state(capability, CapabilityState.EXPERIMENTAL, reason)
            return True

    def downgrade(self, capability: str, *, reason: str) -> None:
        """Return a capability to UNQUALIFIED after a reproducible regression."""

        capability = _require_member(capability, CAPABILITIES, "capability")
        self._write_state(capability, CapabilityState.UNQUALIFIED, reason)

    def promote(
        self,
        capability: str,
        target: CapabilityState,
        *,
        environment: str,
        required: int = 20,
        reason: str,
    ) -> None:
        """Promote only when the ledger proves the gate for the target state."""

        capability = _require_member(capability, CAPABILITIES, "capability")
        target = CapabilityState(target)
        try:
            required = int(required)
        except (TypeError, ValueError) as error:
            raise ReliabilityError("required precisa ser um inteiro") from error
        if required < MIN_QUALIFICATION_RUNS:
            # The spec's gate is not negotiable: a caller cannot lower it.
            raise ReliabilityError(
                f"promoção exige o gate de {MIN_QUALIFICATION_RUNS}/20; "
                f"required={required} foi recusado"
            )
        if target is CapabilityState.QUALIFIED:
            if str(environment) != QUALIFICATION_ENVIRONMENT:
                raise ReliabilityError(
                    "QUALIFIED só é permitido a partir do ambiente "
                    f"{QUALIFICATION_ENVIRONMENT!r}, não {str(environment)!r}"
                )
            evaluation = self.evaluate(capability, QUALIFICATION_ENVIRONMENT, required)
            if not evaluation["qualified"]:
                raise ReliabilityError(
                    f"QUALIFIED recusado: {evaluation['streak']}/{required} "
                    f"execuções reais consecutivas válidas ({evaluation['reason']})"
                )
        elif target is CapabilityState.PRODUCTION:
            if str(environment) != PRODUCTION_ENVIRONMENT:
                raise ReliabilityError(
                    "PRODUCTION só é permitido a partir do ambiente "
                    f"{PRODUCTION_ENVIRONMENT!r}, não {str(environment)!r}"
                )
            if self._state_of(capability) is not CapabilityState.QUALIFIED:
                raise ReliabilityError(
                    "PRODUCTION exige que a capability já esteja QUALIFIED"
                )
            evaluation = self.evaluate(capability, PRODUCTION_ENVIRONMENT, required)
            if not evaluation["qualified"]:
                raise ReliabilityError(
                    f"PRODUCTION recusado: {evaluation['streak']}/{required} "
                    f"execuções portáteis consecutivas válidas ({evaluation['reason']})"
                )
        else:
            raise ReliabilityError(
                f"estado alvo inválido para promote: {target.value!r}; "
                "use mark_experimental ou downgrade"
            )
        self._write_state(capability, target, reason)

    # ---------------------------------------------------------- evaluation

    def summary(self, capability: str, environment: str) -> dict[str, Any]:
        capability = _require_member(capability, CAPABILITIES, "capability")
        environment = _require_member(environment, ENVIRONMENTS, "environment")
        runs = [run for run in self._runs() if run["capability"] == capability and run["environment"] == environment]
        passed = [run for run in runs if run["passed"] is True]
        failed = [run for run in runs if run["passed"] is False]
        codes: dict[str, int] = {}
        for run in runs:
            code = str(run.get("result_code") or "UNKNOWN")
            codes[code] = codes.get(code, 0) + 1
        streak, build_id = self._streak(capability, environment)
        return {
            "capability": capability,
            "environment": environment,
            "runs": len(runs),
            "passed": len(passed),
            "failed": len(failed),
            "streak": streak,
            "build_id": build_id,
            "result_codes": codes,
        }

    def evaluate(
        self, capability: str, environment: str, required: int = 20
    ) -> dict[str, Any]:
        capability = _require_member(capability, CAPABILITIES, "capability")
        environment = _require_member(environment, ENVIRONMENTS, "environment")
        if int(required) < MIN_QUALIFICATION_RUNS:
            # A read must never be able to answer "qualified" below the spec gate.
            raise ReliabilityError(
                f"required precisa ser >= {MIN_QUALIFICATION_RUNS} (recebido: {required})"
            )
        streak, build_id = self._streak(capability, environment)
        qualified = streak >= int(required)
        return {
            "capability": capability,
            "environment": environment,
            "required": int(required),
            "streak": streak,
            "qualified": qualified,
            "build_id": build_id,
            "reason": (
                "sequência consecutiva válida comprovada"
                if qualified
                else "sequência consecutiva válida insuficiente ou interrompida"
            ),
        }

    # ------------------------------------------------------------- internals

    def _streak(self, capability: str, environment: str) -> tuple[int, str | None]:
        """Count the trailing run of clean passes on one build and environment."""

        streak = 0
        build_id: str | None = None
        for run in reversed(self._runs()):
            if run["capability"] != capability or run["environment"] != environment:
                continue
            if run["passed"] is not True or run["intervened"]:
                break
            if build_id is None:
                build_id = run["build_id"]
            elif run["build_id"] != build_id:
                break
            streak += 1
        return streak, build_id

    def _hash_identity(self, identity: Mapping[str, Any] | None) -> str | None:
        canonical = canonical_identity(identity)
        if not canonical:
            return None
        payload = json.dumps(
            canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        return hmac.new(self._key_bytes(), payload, hashlib.sha256).hexdigest()

    def _has_finished(self, run_id: str) -> bool:
        """True when the ledger already holds a terminal result for this run."""

        return any(
            event.get("type") == "run_finished" and str(event.get("run_id") or "") == run_id
            for event in self._read_events()
        )

    def has_finished(self, run_id: str) -> bool:
        """Public, read-only form of :meth:`_has_finished`.

        A worker that restarts mid-run must be able to tell that the terminal
        event is already durable instead of appending a second one.
        """

        try:
            return self._has_finished(_require_run_id(run_id))
        except ReliabilityError:
            return False

    def _append(self, event: Mapping[str, Any]) -> None:
        record = dict(event)
        record.setdefault("ts", time.time())
        ensure_sanitized(record)
        try:
            line = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as error:  # pragma: no cover - defensive
            raise ReliabilityError(f"evento não serializável: {error}") from error
        self._ensure_root()
        with self._events_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _read_events(self) -> list[dict[str, Any]]:
        if not self._events_path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self._events_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as error:
                    raise ReliabilityError(f"evento corrompido no ledger: {error}") from error
                if isinstance(parsed, dict):
                    events.append(parsed)
        return events

    def _runs(self) -> list[dict[str, Any]]:
        runs: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for event in self._read_events():
            kind = event.get("type")
            run_id = str(event.get("run_id") or "")
            if kind == "run_start":
                if not run_id:
                    continue
                if run_id in runs:
                    runs[run_id]["evidence_invalid"] = True
                    continue
                order.append(run_id)
                runs[run_id] = {
                    "run_id": run_id,
                    "capability": str(event.get("capability") or ""),
                    "environment": str(event.get("environment") or ""),
                    "build_id": str(event.get("build_id") or ""),
                    "browser_session_id": event.get("browser_session_id"),
                    "passed": None,
                    # Distinct from "passed is None": a malformed terminal still
                    # closes the run, so a later duplicate can never turn it
                    # into a counted pass.
                    "terminal_seen": False,
                    "intervened": False,
                    "result_code": None,
                    "transitions": [],
                    "evidence_invalid": False,
                }
                continue
            run = runs.get(run_id)
            if run is None:
                continue
            if kind == "intervention":
                run["intervened"] = True
                if run["terminal_seen"]:
                    run["evidence_invalid"] = True
            elif kind == "transition":
                if run["terminal_seen"]:
                    run["evidence_invalid"] = True
                elif run["capability"] == "manual_form_fill":
                    run["transitions"].append(event)
            elif kind == "run_finished":
                if run["terminal_seen"]:
                    raise ReliabilityError(
                        f"ledger com resultado terminal duplicado para a execução {run_id}"
                    )
                run["terminal_seen"] = True
                raw_passed = event.get("passed")
                # Anything that is not a real boolean is unproven, never a pass.
                run["passed"] = raw_passed if isinstance(raw_passed, bool) else None
                run["result_code"] = event.get("result_code")
        for run_id in order:
            run = runs[run_id]
            if run["capability"] != "manual_form_fill":
                continue
            if run["evidence_invalid"] or not self._valid_manual_form_evidence(
                run["transitions"]
            ):
                # A terminal pass without a structurally valid evidence chain
                # is a failed qualification attempt, regardless of what the
                # component that wrote ``run_finished`` claimed.
                if run["passed"] is True:
                    run["passed"] = False
        # A still-open run is unproven, never a pass.
        return [runs[run_id] for run_id in order]

    @staticmethod
    def _valid_manual_form_evidence(transitions: Sequence[Mapping[str, Any]]) -> bool:
        """Check the complete AR-1 evidence chain from the persisted events."""

        if len(transitions) != len(MANUAL_FORM_FILL_EVIDENCE):
            return False
        identity_hash: str | None = None
        for event, (boundary, result_code, state_before, state_after) in zip(
            transitions, MANUAL_FORM_FILL_EVIDENCE, strict=True
        ):
            if (
                event.get("boundary") != boundary
                or event.get("result_code") != result_code
                or event.get("state_before") != state_before
                or event.get("state_after") != state_after
            ):
                return False
            expected_hash = event.get("expected_identity_hash")
            observed_hash = event.get("observed_identity_hash")
            if (
                not isinstance(expected_hash, str)
                or not isinstance(observed_hash, str)
                or not expected_hash
                or expected_hash != observed_hash
            ):
                return False
            if identity_hash is None:
                identity_hash = expected_hash
            elif expected_hash != identity_hash:
                return False

        preflight, fill, reread = transitions[2:]
        generation_fields = (
            preflight.get("generation_after"),
            fill.get("generation_before"),
            fill.get("generation_after"),
            reread.get("generation_after"),
        )
        if any(value is not None for value in generation_fields):
            if any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in generation_fields
            ):
                return False
            preflight_generation, fill_before, fill_after, reread_generation = generation_fields
            if (
                preflight_generation != fill_before
                or fill_after < fill_before
                or reread_generation != fill_after
            ):
                return False
        return True

    def _read_capabilities(self) -> dict[str, dict[str, Any]]:
        if not self._capabilities_path.exists():
            return {}
        try:
            payload = json.loads(self._capabilities_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ReliabilityError(f"capabilities.json corrompido: {error}") from error
        capabilities = payload.get("capabilities") if isinstance(payload, Mapping) else None
        return dict(capabilities) if isinstance(capabilities, Mapping) else {}

    def _state_of(self, capability: str) -> CapabilityState:
        entry = self._read_capabilities().get(capability) or {}
        try:
            return CapabilityState(str(entry.get("state") or CapabilityState.UNQUALIFIED.value))
        except ValueError:
            return CapabilityState.UNQUALIFIED

    def _write_state(
        self, capability: str, state: CapabilityState, reason: str
    ) -> None:
        reason_text = str(reason)
        if len(reason_text) > MAX_REASON_LENGTH:
            raise ReliabilityError(f"reason excede {MAX_REASON_LENGTH} caracteres")
        with _lock_for(self._root):
            self._ensure_root()
            stored = self._read_capabilities()
            stored[capability] = {
                "state": state.value,
                "reason": reason_text,
                "build_id": self._build_id,
                "updated_at": time.time(),
            }
            payload = {
                "build_id": self._build_id,
                "updated_at": time.time(),
                "capabilities": stored,
            }
            ensure_sanitized({"capabilities": stored}, path="capabilities")
            temporary = self._capabilities_path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self._capabilities_path)

