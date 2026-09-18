"""Fail-closed preflight for one act form.

The extension only reports what the DOM contains; the decision of what may be
written — and whether anything may be written at all — belongs to the backend.
Every mandatory field must pass before a single control is touched, because a
partially filled act is worse than an untouched one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..analysis import MANDATORY_FIELDS, OPTIONAL_FIELDS
from ..analysis.legal import RULES_VERSION, resolve_legal_foundation
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
    for option in options:
        if str(option.get("value") or "") == proposal:
            return proposal
    wanted = compare_text(proposal)
    for option in options:
        if compare_text(option.get("label")) == wanted:
            return str(option.get("value") or "")
    return None


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
    missing = [name for name in MANDATORY_FIELDS if name not in proposals]
    if missing:
        raise FillBlocked("FIELD_PROPOSAL_MISSING", missing)

    plan = FillPlan(identity=dict(identity), generation=generation)
    for name in ALLOWED_FIELDS:
        proposal = proposals.get(name)
        control = _control(snapshot, name)
        mandatory = name in MANDATORY_FIELDS
        if control is None:
            if mandatory:
                raise FillBlocked("CONTROL_NOT_FOUND", [name])
            plan.warnings.append(f"controle opcional ausente no formulário: {name}")
            continue
        if control.get("disabled") is True or control.get("readOnly") is True:
            if mandatory:
                raise FillBlocked("CONTROL_READONLY", [name])
            plan.warnings.append(f"controle opcional desabilitado: {name}")
            continue
        if proposal is None:
            plan.warnings.append(f"sem proposta para o campo opcional: {name}")
            continue
        current = str(control.get("value") or "").strip()
        if current:
            if compare_text(current) == compare_text(proposal):
                plan.preserved[name] = current
                continue
            raise FillBlocked("EXISTING_VALUE_DIVERGENCE", [name])
        resolved = _resolve_option_value(control, proposal)
        if resolved is None:
            raise FillBlocked("OPTION_NOT_AVAILABLE", [name])
        plan.fields[name] = resolved

    plan.legal_decision = _legal_decision(proposals, snapshot, legal_resolver, plan)
    if "fundamento_legal" in plan.fields and plan.legal_decision:
        chosen = plan.legal_decision.get("option_value")
        if plan.legal_decision.get("automatic") and chosen:
            plan.fields["fundamento_legal"] = str(chosen)
        elif not plan.legal_decision.get("automatic"):
            plan.warnings.append(
                "fundamento legal sem decisão automática; o texto localizado foi mantido para revisão"
            )
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
