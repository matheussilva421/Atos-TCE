"""View models for the Mesa API.

These are pure read helpers: they translate SQLite rows and on-disk archive
facts into JSON-ready dictionaries. They contain no business rule and never
mutate state, so the read-only Mesa stays read-only by construction.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..archive.legacy_import import ARCHIVE_TREE, BLOB_TREE, PROCESS_TREE, blob_path
from ..core.identity import normalize_text
from ..core.store import Store

API_VERSION = 1


def health_payload(store: Store, data_root: Path) -> dict[str, Any]:
    """Report that the Mesa is answering and which schema it is reading."""

    summary = store.storage_summary()
    return {
        "status": "ok",
        "api_version": API_VERSION,
        "schema_version": summary["schema_version"],
        "data_root": str(Path(data_root)),
        "database": str(store.path),
        "process_count": summary["processes"]["total"],
    }


def process_list_payload(
    store: Store, status: str | None = None, query: str | None = None
) -> dict[str, Any]:
    """List processes with the per-process document count the Mesa displays."""

    items = store.list_processes(status=status)
    if query:
        needle = normalize_text(query)
        items = [
            item
            for item in items
            if needle in normalize_text(item["process_key"])
            or needle in normalize_text(item["interested"])
        ]
    counts = store.document_counts()
    for item in items:
        item["document_count"] = counts.get(int(item["id"]), 0)
    return {
        "api_version": API_VERSION,
        "total": len(items),
        "items": items,
        "filter": {"status": status, "query": query},
    }


def process_detail_payload(store: Store, process_id: int) -> dict[str, Any] | None:
    """Return one process with documents, fields and workflow history."""

    return store.get_process(process_id)


def storage_payload(store: Store, data_root: Path) -> dict[str, Any]:
    """Combine the SQLite summary with the physical state of the data root."""

    data_path = Path(data_root)
    blobs = _scan_tree(data_path / ARCHIVE_TREE / BLOB_TREE)
    views = _scan_tree(data_path / ARCHIVE_TREE / PROCESS_TREE)
    return {
        "api_version": API_VERSION,
        "database": store.storage_summary(),
        "archive": {
            "root": str(data_path / ARCHIVE_TREE),
            "blob_count": blobs["files"],
            "blob_bytes": blobs["bytes"],
            "process_view_files": views["files"],
            "process_view_bytes": views["bytes"],
            # How many bytes the hardlinked process view would cost without dedup.
            "deduplicated_bytes": max(0, views["bytes"] - blobs["bytes"]),
        },
    }


def resolve_document_file(store: Store, data_root: Path, document_id: int) -> Path | None:
    """Resolve a document id to a real file, preferring the process view.

    The path always comes from SQLite; a caller can never name a file. When the
    process view is gone (archived or cleaned) the canonical blob identified by
    the stored SHA-256 is used instead.
    """

    document = store.get_document(document_id)
    if document is None:
        return None
    data_path = Path(data_root)
    candidate = safe_join(data_path, str(document.get("relative_path") or ""))
    if candidate is not None and candidate.is_file():
        return candidate
    fallback = blob_path(data_path, str(document.get("sha256") or ""))
    if fallback.is_file():
        return fallback
    return None


def safe_join(root: Path, relative: str) -> Path | None:
    """Join ``relative`` under ``root``, refusing anything that escapes it."""

    if not relative:
        return None
    root_path = Path(root)
    try:
        candidate = (root_path / relative).resolve()
        candidate.relative_to(root_path.resolve())
    except (OSError, ValueError):
        return None
    return candidate


def _scan_tree(root: Path) -> dict[str, int]:
    """Count files and bytes below ``root`` without following links."""

    files = 0
    total = 0
    if not root.is_dir():
        return {"files": 0, "bytes": 0}
    for current, _directory_names, file_names in os.walk(root, followlinks=False):
        for name in file_names:
            try:
                info = os.stat(Path(current) / name)
            except OSError:
                continue
            files += 1
            total += info.st_size
    return {"files": files, "bytes": total}
