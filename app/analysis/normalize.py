"""Normalize the proven incremental-analysis payload into Mesa records.

The legacy pipeline answers with ``{"process", "status", "blocks": [{
"interested", "pending", "fields": {name: {...}}}]}``. This module turns that
into frozen ``FieldRecord`` rows plus the field/document context the Mesa needs,
without touching SQLite or the filesystem, so the readiness rule is unit
testable on its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..core.models import FieldRecord
from . import MANDATORY_FIELDS, OPTIONAL_FIELDS

#: Deterministic numeric meaning for the legacy confidence vocabulary.
CONFIDENCE_VALUES: dict[str, float] = {
    "high": 1.0,
    "alta": 1.0,
    "medium": 0.6,
    "media": 0.6,
    "média": 0.6,
    "low": 0.3,
    "baixa": 0.3,
    "none": 0.0,
    "nenhuma": 0.0,
}

FOUND_STATUS = "found"


@dataclass(slots=True)
class NormalizedAnalysis:
    process_key: str
    process_status: str
    fields: list[FieldRecord] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    pending_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    legacy_status: str | None = None
    interested: list[str] = field(default_factory=list)


def normalize_analysis(
    process_key: str,
    payload: Mapping[str, Any] | None,
    *,
    documents: Sequence[Mapping[str, Any]] | None = None,
) -> NormalizedAnalysis:
    """Map one legacy result into Mesa field records and a readiness verdict."""

    data = payload if isinstance(payload, Mapping) else {}
    document_index = _index_documents(documents or [])
    warnings: list[str] = []
    fields: list[FieldRecord] = []
    interested: list[str] = []

    for block in data.get("blocks") or []:
        if not isinstance(block, Mapping):
            continue
        person = str(block.get("interested") or "").strip()
        if person and person not in interested:
            interested.append(person)
        for name, raw in (block.get("fields") or {}).items():
            fields.append(_field_record(str(name), raw, document_index, warnings))
        for name in block.get("pending") or []:
            warnings.append(f"campo pendente informado pelo pipeline: {name}")

    guaranteed = {
        record.field_name
        for record in fields
        if record.status == FOUND_STATUS and (record.value or "").strip()
    }
    pending_fields = [name for name in MANDATORY_FIELDS if name not in guaranteed]
    for name in OPTIONAL_FIELDS:
        if name not in guaranteed:
            warnings.append(f"campo opcional ausente: {name}")
    unknown = sorted(
        {record.field_name for record in fields} - set(MANDATORY_FIELDS) - set(OPTIONAL_FIELDS)
    )
    for name in unknown:
        warnings.append(f"campo desconhecido no resultado legado: {name}")

    return NormalizedAnalysis(
        process_key=str(process_key),
        process_status="PRONTO" if not pending_fields else "REVISAR",
        fields=fields,
        documents=[dict(document) for document in (documents or [])],
        pending_fields=pending_fields,
        warnings=warnings,
        legacy_status=str(data.get("status") or "") or None,
        interested=interested,
    )


def mandatory_ready(payload: Mapping[str, Any] | None) -> bool:
    """True when every mandatory field is present and marked as found."""

    return not normalize_analysis("", payload).pending_fields


def _field_record(
    name: str,
    raw: Any,
    document_index: Mapping[tuple[str, str], int],
    warnings: list[str],
) -> FieldRecord:
    data = raw if isinstance(raw, Mapping) else {}
    value = data.get("form_value")
    if value is None:
        value = data.get("value")
    if value is None:
        value = data.get("source_value")
    status = str(data.get("status") or "pending")
    page = data.get("page")
    citation = data.get("citation") if isinstance(data.get("citation"), Mapping) else None
    if page is None and citation is not None:
        page = citation.get("page")

    evidence: dict[str, Any] = {}
    if isinstance(data.get("evidence"), Mapping):
        evidence.update(dict(data["evidence"]))
    if citation is not None:
        evidence.setdefault("citation", dict(citation))
    for key in ("process", "event", "document", "method"):
        if data.get(key) is not None and key not in evidence:
            evidence[key] = data[key]

    document_id = _resolve_document_id(citation or data, document_index)
    cited = data.get("document") or (citation or {}).get("document")
    if document_id is None and cited:
        warnings.append(f"{name}: documento citado não está registrado no processo")

    return FieldRecord(
        field_name=name,
        value=str(value) if value is not None and str(value).strip() else None,
        status=status,
        confidence=_confidence(data.get("confidence")),
        document_id=document_id,
        page=int(page) if isinstance(page, int) and not isinstance(page, bool) else None,
        evidence=evidence or None,
    )


def _confidence(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return max(0.0, min(1.0, float(raw)))
    key = str(raw).strip().casefold()
    if key in CONFIDENCE_VALUES:
        return CONFIDENCE_VALUES[key]
    try:
        return max(0.0, min(1.0, float(key)))
    except ValueError:
        return None


def _index_documents(documents: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], int]:
    index: dict[tuple[str, str], int] = {}
    for document in documents:
        try:
            document_id = int(document["id"])
        except (KeyError, TypeError, ValueError):
            continue
        event = str(document.get("event") or "").strip()
        title = str(document.get("title") or "").strip().casefold()
        if title:
            index.setdefault((event, title), document_id)
            index.setdefault(("", title), document_id)
        index.setdefault((event, ""), document_id)
    return index


def _resolve_document_id(
    source: Mapping[str, Any], index: Mapping[tuple[str, str], int]
) -> int | None:
    if not index:
        return None
    event = source.get("event")
    event_key = str(event).strip() if event is not None else ""
    title_raw = source.get("document") or source.get("title")
    title = str(title_raw or "").strip().casefold()
    if title:
        exact = index.get((event_key, title))
        if exact is None:
            exact = index.get(("", title))
        if exact is not None:
            return exact
        for (entry_event, entry_title), document_id in index.items():
            if event_key and entry_event and entry_event != event_key:
                continue
            if entry_title and (entry_title.startswith(title) or title.startswith(entry_title)):
                return document_id
        # A named document that is not registered must stay unresolved: linking
        # it to another file of the same event would fabricate evidence.
        return None
    if event_key:
        return index.get((event_key, ""))
    return None
