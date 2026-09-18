"""Materialise the analysis engine's execution view from the canonical store.

The promoted engine (M6 Task 1) reads ``archive/processos/<folder>/processo.json``
plus the event folders, and it recomputes each document's SHA-256 while
resolving ``root / path``. The M1 import writes only the documents, so the
adapter renders that manifest from the canonical rows before the engine runs:
SQLite keeps owning the state and this module is the single place that renders
it in the shape the engine expects.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

EVENT_FOLDER_RE = re.compile(r"^evento-(\d+)-(\d+)$")
ENGINE_MANIFEST_NAME = "processo.json"


def process_folder(process_key: str) -> str:
    """Return the archive folder name of one canonical process."""

    return str(process_key).strip().replace("/", "-")


def manifest_path(data_root: str | Path, process_key: str) -> Path:
    """Return where the engine expects the process manifest."""

    return (
        Path(data_root)
        / "archive"
        / "processos"
        / process_folder(process_key)
        / ENGINE_MANIFEST_NAME
    )


def _event_identity(relative_path: str, event: object) -> tuple[int, str]:
    for part in reversed(Path(relative_path).parts):
        match = EVENT_FOLDER_RE.match(part)
        if match:
            return int(match.group(1)), match.group(2)
    try:
        return int(str(event)), ""
    except (TypeError, ValueError):
        return 0, ""


def _document_id(source_id: str) -> str:
    parts = str(source_id).split("|")
    return parts[-1] if len(parts) >= 3 else str(source_id)


def archive_relative(relative_path: str) -> str:
    """Render a document path the way the engine resolves it.

    The ``documents`` table stores paths relative to the *data root*
    (``archive/processos/...``) while the engine resolves every document
    against the *archive root*; the prefix has to go.
    """

    normalized = str(relative_path).replace("\\", "/").lstrip("/")
    prefix = "archive/"
    if normalized.lower().startswith(prefix):
        return normalized[len(prefix) :]
    return normalized


def process_manifest(
    process: Mapping[str, Any], documents: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Render the engine's per-process manifest from canonical rows."""

    process_key = str(process.get("process_key") or "").strip()
    if not process_key:
        raise ValueError("process_key is required")
    number, _, year = process_key.partition("/")

    events: dict[tuple[int, str], dict[str, Any]] = {}
    for document in documents:
        relative = archive_relative(str(document.get("relative_path") or ""))
        if not relative:
            continue
        event_number, event_id = _event_identity(relative, document.get("event"))
        event = events.setdefault(
            (event_number, event_id),
            {
                "event": event_number,
                "event_id": event_id,
                "date": "",
                "title": "",
                "active": True,
                "documents": [],
            },
        )
        title = str(document.get("title") or "")
        if not event["title"]:
            event["title"] = title
        source_id = str(document.get("source_id") or "")
        event["documents"].append(
            {
                "key": source_id,
                "id": _document_id(source_id),
                "title": title,
                "extension": Path(relative).suffix or ".pdf",
                "sha256": str(document.get("sha256") or ""),
                "path": relative,
                "status": "complete",
            }
        )

    return {
        "key": process_key,
        "number": number,
        "year": int(year) if str(year).isdigit() else year,
        "status": "complete",
        # The canonical row's own timestamp keeps the rendering stable, so an
        # unchanged process never rewrites its manifest.
        "synced_at": str(process.get("updated_at") or ""),
        "events": [events[key] for key in sorted(events)],
    }


def ensure_process_manifest(
    data_root: str | Path,
    process: Mapping[str, Any],
    documents: Sequence[Mapping[str, Any]],
) -> Path | None:
    """Write the manifest when the canonical rows say something new."""

    process_key = str(process.get("process_key") or "").strip()
    if not process_key:
        raise ValueError("process_key is required")
    target = manifest_path(data_root, process_key)
    payload = json.dumps(process_manifest(process, documents), ensure_ascii=False, indent=2) + "\n"
    if target.is_file() and target.read_text(encoding="utf-8") == payload:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(target)
    return target
