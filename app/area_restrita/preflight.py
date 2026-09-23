"""Best-effort preflight for a securely identified act form."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..analysis import MANDATORY_FIELDS, OPTIONAL_FIELDS
from ..analysis.legal import (
    RULES_VERSION,
    is_automatic_legal_decision,
    resolve_legal_foundation,
    selectable_legal_options,
)
from ..core.identity import normalize_interested

ALLOWED_FIELDS: tuple[str, ...] = MANDATORY_FIELDS + OPTIONAL_FIELDS


class FillBlocked(RuntimeError):
    """A preflight failure that must stop the fill with a machine code."""

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
        return proposal
    selectable = selectable_legal_options(options)
    for option in selectable:
        if str(option.get("value") or "") == proposal:
            return str(option.get("value") or "")
    wanted = compare_text(proposal)
    for option in selectable:
        if compare_text(option.get("label")) == wanted:
            return str(option.get("value") or "")
    return None


def _is_placeholder_current(control: Mapping[str, Any], current: str) -> bool:
    if not current:
        return True
    for option in _control_options(control):
        if str(option.get("value") or "") != current:
            continue
        label = compare_text(option.get("label"))
        return label.startswith(("selecione", "selecionar", "select "))
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
    process_key = str(process.get("process_key") or "")
    interested = str(process.get("interested_normalized") or "")

    identity = snapshot.get("identity")
    if not isinstance(identity, Mapping):
        raise FillBlocked("IDENTITY_MISSING")
    snapshot_key = str(identity.get("processKey") or identity.get("process_key") or "").strip()
    snapshot_interested = normalize_interested(
        identity.get("interestedNormalized") or identity.get("interested_normalized") or ""
    )
    if snapshot_key != process_key or snapshot_interested != interested:
        raise FillBlocked("IDENTITY_MISMATCH")

    generation = snapshot.get("generation")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise FillBlocked("GENERATION_MISSING")

    proposals = _proposals(process)
    plan = FillPlan(identity=dict(identity), generation=generation)
    for name in ALLOWED_FIELDS:
        proposal = proposals.get(name)
        control = _control(snapshot, name)
        if control is None:
            plan.warnings.append(f"CONTROL_NOT_FOUND: {name}")
            continue
        if control.get("readable") is False:
            plan.warnings.append(f"FIELD_READ_FAILED: {name}")
            continue
        if control.get("disabled") is True or control.get("readOnly") is True:
            code = "CONTROL_DISABLED" if control.get("disabled") is True else "CONTROL_READONLY"
            plan.warnings.append(f"{code}: {name}")
            continue
        if proposal is None:
            plan.warnings.append(f"FIELD_PROPOSAL_MISSING: {name}")
            continue
        current = str(control.get("value") or "").strip()
        if name == "fundamento_legal":
            continue
        if current and not _is_placeholder_current(control, current):
            if compare_text(current) == compare_text(proposal):
                plan.preserved[name] = current
                continue
            plan.preserved[name] = current
            plan.warnings.append(f"EXISTING_VALUE_DIVERGENCE: {name}")
            continue
        resolved = _resolve_option_value(control, proposal)
        if resolved is None:
            plan.warnings.append(f"OPTION_NOT_AVAILABLE: {name}")
            continue
        plan.fields[name] = resolved

    legal_proposal = proposals.get("fundamento_legal")
    legal_control = _control(snapshot, "fundamento_legal")
    if (
        legal_proposal
        and legal_control is not None
        and legal_control.get("readable") is not False
        and legal_control.get("disabled") is not True
        and legal_control.get("readOnly") is not True
    ):
        plan.legal_decision = _legal_decision(proposals, snapshot, legal_resolver, plan)
        decision_warnings = plan.legal_decision.get("warnings") if plan.legal_decision else []
        if isinstance(decision_warnings, list):
            plan.warnings.extend(
                f"fundamento_legal: {warning}"
                for warning in decision_warnings
                if isinstance(warning, str) and warning
            )
        current = str(legal_control.get("value") or "").strip()
        chosen = plan.legal_decision.get("option_value") if plan.legal_decision else None
        selectable = selectable_legal_options(_control_options(legal_control))
        selectable_values = {str(option.get("value") or "") for option in selectable}
        if current and not _is_placeholder_current(legal_control, current):
            plan.preserved["fundamento_legal"] = current
            if chosen and str(chosen) != current:
                plan.warnings.append("EXISTING_VALUE_DIVERGENCE: fundamento_legal")
        elif plan.legal_decision and is_automatic_legal_decision(plan.legal_decision) and chosen:
            if str(chosen) in selectable_values:
                plan.fields["fundamento_legal"] = str(chosen)
            else:
                plan.warnings.append("OPTION_NOT_AVAILABLE: fundamento_legal")
        else:
            plan.warnings.append("LEGAL_DECISION_UNAVAILABLE: fundamento_legal")
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
    options = [dict(option) for option in _control_options(control)]
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
