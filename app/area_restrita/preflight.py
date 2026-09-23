"""Identity-safe, best-effort preflight for one act form.

The extension only reports what the DOM contains; the backend confirms the
target identity and plans each field independently. Content problems produce
warnings for that field, while an unsafe or stale target blocks the request.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..analysis import MANDATORY_FIELDS, OPTIONAL_FIELDS
from ..analysis.legal import (
    PLACEHOLDER_PATTERN,
    RULES_VERSION,
    is_automatic_legal_decision,
    normalize_legal_text,
    resolve_legal_foundation,
    selectable_legal_options,
)
from ..core.identity import normalize_interested

ALLOWED_FIELDS: tuple[str, ...] = MANDATORY_FIELDS + OPTIONAL_FIELDS
SELECT_FIELDS = frozenset({"modalidade", "fundamento_legal"})


class FillBlocked(RuntimeError):
    """An unsafe process/form target or invalid request that must stop filling."""

    def __init__(self, code: str, details: Sequence[str] | None = None) -> None:
        self.code = code
        self.details = list(details or [])
        super().__init__(code if not self.details else f"{code}: {', '.join(self.details)}")


@dataclass(slots=True)
class FillPlan:
    identity: dict[str, Any]
    generation: int
    fields: dict[str, str] = field(default_factory=dict)
    preserved: dict[str, str] = field(default_factory=dict)
    legal_decision: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


def compare_text(value: Any) -> str:
    """Comparison form for a field value: accent and case insensitive."""

    return normalize_interested(value)


def _proposals(process: Mapping[str, Any]) -> dict[str, str]:
    proposals: dict[str, str] = {}
    for entry in process.get("fields") or []:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("field_name") or "")
        value = entry.get("value")
        if name in ALLOWED_FIELDS and entry.get("status") == "found" and value:
            text = str(value).strip()
            if text:
                proposals[name] = text
    return proposals


def _control(snapshot: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    controls = snapshot.get("fields")
    if not isinstance(controls, Mapping):
        return None
    control = controls.get(name)
    return control if isinstance(control, Mapping) else None


def _control_options(control: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    options = control.get("options")
    if not isinstance(options, list):
        return []
    return [option for option in options if isinstance(option, Mapping)]


def _resolve_option_value(control: Mapping[str, Any], proposal: str) -> str | None:
    """Map a proposal onto one of the current options, by value then by label."""

    options = _control_options(control)
    if not options:
        return None
    selectable: list[tuple[str, str]] = []
    for option in options:
        raw_value = "" if option.get("value") is None else str(option.get("value"))
        raw_label = "" if option.get("label") is None else str(option.get("label"))
        if not raw_value.strip() or not raw_label.strip():
            continue
        if PLACEHOLDER_PATTERN.match(normalize_legal_text(raw_label).strip()):
            continue
        selectable.append((raw_value, raw_label))
    for value, _ in selectable:
        if value == proposal:
            return value
    wanted = compare_text(proposal)
    for value, label in selectable:
        if compare_text(label) == wanted:
            return value
    return None


def _is_selected_placeholder(control: Mapping[str, Any], current: str) -> bool:
    """Treat an explicitly selected select placeholder as an empty control."""

    if not current:
        return True
    for option in _control_options(control):
        value = "" if option.get("value") is None else str(option.get("value"))
        if value != current:
            continue
        label = "" if option.get("label") is None else str(option.get("label"))
        return bool(PLACEHOLDER_PATTERN.match(normalize_legal_text(label).strip()))
    return False


def build_fill_plan(
    process: Mapping[str, Any],
    form_snapshot: Mapping[str, Any] | None,
    *,
    legal_resolver=resolve_legal_foundation,
) -> FillPlan:
    """Decide the exact fields the extension may write, or block."""

    if not isinstance(process, Mapping):
        raise FillBlocked("PROCESS_MISSING")
    snapshot = form_snapshot if isinstance(form_snapshot, Mapping) else {}
    process_key = str(process.get("process_key") or "").strip()
    interested = normalize_interested(process.get("interested_normalized") or "")
    if not process_key or not interested:
        raise FillBlocked("IDENTITY_MISSING")

    identity = snapshot.get("identity")
    if not isinstance(identity, Mapping):
        raise FillBlocked("IDENTITY_MISSING")
    snapshot_key = str(identity.get("processKey") or identity.get("process_key") or "").strip()
    snapshot_interested = normalize_interested(
        identity.get("interestedNormalized") or identity.get("interested_normalized") or ""
    )
    if not snapshot_key or not snapshot_interested:
        raise FillBlocked("IDENTITY_MISSING")
    if snapshot_key != process_key or snapshot_interested != interested:
        raise FillBlocked("IDENTITY_MISMATCH")

    generation = snapshot.get("generation")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise FillBlocked("GENERATION_MISSING")

    plan = FillPlan(identity=dict(identity), generation=generation)
    proposals = _proposals(process)
    legal_proposal = proposals.get("fundamento_legal")
    if legal_proposal:
        plan.legal_decision = _legal_decision(proposals, snapshot, legal_resolver, plan)
        legal_control = _control(snapshot, "fundamento_legal")
        legal_options = selectable_legal_options(
            _control_options(legal_control) if legal_control is not None else []
        )
        if not legal_options and not any(
            "LEGAL_OPTIONS_EMPTY" in str(warning) for warning in plan.warnings
        ):
            plan.warnings.append("fundamento_legal: LEGAL_OPTIONS_EMPTY - sem opção selecionável")
        if plan.legal_decision:
            diagnostics = plan.legal_decision.get("warnings") or []
            if not isinstance(diagnostics, (list, tuple)):
                diagnostics = [diagnostics]
            for warning in diagnostics:
                if isinstance(warning, str) and warning.strip():
                    plan.warnings.append(f"fundamento_legal: {warning}")

    legal_value: str | None = None
    legal_decision = plan.legal_decision
    if legal_proposal and legal_decision:
        chosen = legal_decision.get("option_value")
        selectable_values = {
            option["value"]
            for option in selectable_legal_options(
                _control_options(_control(snapshot, "fundamento_legal") or {})
            )
        }
        if chosen is not None and str(chosen) not in selectable_values:
            plan.warnings.append("fundamento_legal: valor resolvido não pertence ao catálogo atual")
        elif is_automatic_legal_decision(legal_decision):
            legal_value = str(chosen)
        else:
            plan.warnings.append("fundamento_legal: sem decisão automática; campo mantido para revisão")

    for name in ALLOWED_FIELDS:
        proposal = proposals.get(name)
        control = _control(snapshot, name)
        if control is None:
            plan.warnings.append(f"controle ausente no formulário: {name}")
            continue
        if control.get("disabled") is True or control.get("readOnly") is True:
            plan.warnings.append(f"controle desabilitado ou somente leitura: {name}")
            continue
        if proposal is None:
            plan.warnings.append(f"sem proposta para o campo: {name}")
            continue

        raw_current = "" if control.get("value") is None else str(control.get("value"))
        current = raw_current.strip()
        if name in SELECT_FIELDS and _is_selected_placeholder(control, current):
            current = ""
        if current:
            expected = legal_value if name == "fundamento_legal" else proposal
            if expected is not None and compare_text(current) == compare_text(expected):
                plan.preserved[name] = raw_current
                continue
            plan.preserved[name] = raw_current
            plan.warnings.append(f"valor divergente existente preservado: {name}")
            continue

        if name == "fundamento_legal":
            if legal_value is not None:
                plan.fields[name] = legal_value
            continue
        if name in SELECT_FIELDS:
            resolved = _resolve_option_value(control, proposal)
            if resolved is None:
                plan.warnings.append(f"opção indisponível no catálogo atual: {name}")
                continue
            plan.fields[name] = resolved
            continue
        plan.fields[name] = proposal
    return plan


def _legal_decision(
    proposals: Mapping[str, str],
    snapshot: Mapping[str, Any],
    legal_resolver,
    plan: FillPlan,
) -> dict[str, Any] | None:
    proposal = proposals.get("fundamento_legal")
    if not proposal:
        return None
    control = _control(snapshot, "fundamento_legal") or {}
    options = [
        {"value": str(option.get("value") or ""), "label": str(option.get("label") or "")}
        for option in _control_options(control)
    ]
    context = {
        "resolution_status": "complete",
        "operative_text": proposal,
        "cargo": proposals.get("cargo") or "",
    }
    try:
        decision = legal_resolver(context, options)
    except Exception as error:  # the engine must never break the fill silently
        plan.warnings.append(f"motor jurídico indisponível: {type(error).__name__}")
        return None
    if not isinstance(decision, Mapping):
        return None
    result = dict(decision)
    result.setdefault("rules_version", RULES_VERSION)
    return result
