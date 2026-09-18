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

#: Fields of a scan the Mesa counters panel reads.
AREA_SUMMARY_FIELDS = (
    "id",
    "source_scope",
    "marker_label",
    "marker_value",
    "observed_at",
    "origin",
    "total",
    "pending",
    "completed",
    "ambiguous",
    "blocked",
    "not_found",
)

AREA_COUNTER_FIELDS = ("total", "pending", "completed", "ambiguous", "blocked", "not_found")


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
            # Bytes that a view file actually occupies: a hardlink shares the
            # blob inode and therefore adds nothing beyond the canonical copy.
            "process_view_physical_bytes": views["physical_bytes"],
            # What the process view would have cost as independent copies.
            "deduplicated_bytes": max(0, views["bytes"] - views["physical_bytes"]),
        },
    }


def area_summary_payload(store: Store) -> dict[str, Any]:
    """Report the latest Área Restrita scan and its counter block."""

    scan = store.latest_area_scan()
    counters = {field: 0 for field in AREA_COUNTER_FIELDS}
    summary = None
    if scan is not None:
        summary = {field: scan.get(field) for field in AREA_SUMMARY_FIELDS}
        for field in AREA_COUNTER_FIELDS:
            counters[field] = int(scan.get(field) or 0)
    return {"api_version": API_VERSION, "scan": summary, "counters": counters}


def acquisition_plan_payload(plan: Any) -> dict[str, Any]:
    """Report only what the operator needs: how many processes need bytes."""

    return {
        "api_version": API_VERSION,
        "total": int(plan.total),
        "lot_size": int(plan.lot_size),
        "lot_count": int(plan.lot_count),
    }


def archive_result_payload(result: Any) -> dict[str, Any]:
    """Report an archive/restore outcome as counts the operator can act on."""

    return {
        "ok": bool(result.ok),
        "documents": int(result.documents),
        "archived": len(result.archived),
        "restored": len(result.restored),
        "missing": len(result.missing),
        "errors": list(result.errors)[:20],
    }


def job_payload(store: Store, job_id: int, *, failure_limit: int = 20) -> dict[str, Any] | None:
    """Report a job as progress plus process-level failures, never as lot ids."""

    job = store.get_job(job_id)
    if job is None:
        return None
    failures: list[dict[str, Any]] = []
    for item in store.list_job_items(job_id):
        if item["state"] != "FAILED" or len(failures) >= failure_limit:
            continue
        process = store.get_process(int(item["process_id"]))
        failures.append(
            {
                "process_key": (process or {}).get("process_key"),
                "error": item["error"],
            }
        )
    return {
        "api_version": API_VERSION,
        "id": int(job["id"]),
        "job_type": job["job_type"],
        "status": job["status"],
        "total": int(job["total"]),
        "completed": int(job["completed"]),
        "failed": int(job["failed"]),
        "error": job["error"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "failures": failures,
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
    """Count files, logical bytes and really occupied bytes below ``root``.

    A file with more than one link shares its bytes with another path below the
    canonical blob store, so it is counted as logical size only. That is what
    makes ``deduplicated_bytes`` meaningful instead of always zero.
    """

    files = 0
    total = 0
    physical = 0
    if not root.is_dir():
        return {"files": 0, "bytes": 0, "physical_bytes": 0}
    for current, _directory_names, file_names in os.walk(root, followlinks=False):
        for name in file_names:
            try:
                info = os.stat(Path(current) / name)
            except OSError:
                continue
            files += 1
            total += info.st_size
            if info.st_nlink <= 1:
                physical += info.st_size
    return {"files": files, "bytes": total, "physical_bytes": physical}
