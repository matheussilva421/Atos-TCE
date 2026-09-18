"""Evidence lookup: the source that supports one proposed field.

Evidence is never invented. When a field has no registered document, or the
registration is gone, the lookup returns ``None`` so the Mesa shows "no source"
instead of pointing at an arbitrary file.
"""

from __future__ import annotations

from typing import Any

from ..core.store import Store


def evidence_for_field(store: Store, process_id: int, field_name: str) -> dict[str, Any] | None:
    """Return the evidence of one field, resolved through SQLite only."""

    field = next(
        (
            item
            for item in store.list_fields(process_id)
            if item["field_name"] == str(field_name)
        ),
        None,
    )
    if field is None:
        return None
    document_id = field.get("document_id")
    if document_id is None:
        return None
    document = store.get_document(int(document_id))
    if document is None:
        return None
    evidence = field.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    return {
        "process_id": int(process_id),
        "field_name": str(field_name),
        "value": field.get("value"),
        "status": field.get("status"),
        "confidence": field.get("confidence"),
        "document_id": int(document_id),
        "document_title": document.get("title"),
        "document_storage_state": document.get("storage_state"),
        "page": field.get("page"),
        "quote": evidence.get("quote"),
        "rects": evidence.get("rects") or [],
        "method": evidence.get("method"),
        "evidence_status": evidence.get("status"),
    }
