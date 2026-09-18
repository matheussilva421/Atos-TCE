"""Writer for the frozen-queue contract the proven collector already validates.

The schema is not invented here: it is reproduced byte-for-byte from the
expectations of ``work/tce-extractor/portable/app/frozen_queue.py`` and
``work/tce-extractor/portable/TceFrozenQueue.psm1``, so the Mesa can command
the existing download engine without changing it.

Key details that are easy to get wrong and are therefore asserted by tests:

* ``canonical_json`` covers exactly ``schema_version``, ``observed_at``,
  ``spec``, ``queue`` and ``blocked``;
* ``dataset_sha256`` is the SHA-256 of that canonical JSON;
* ``analysis_id`` is ``analysis-`` plus the first 24 hex characters of it;
* ``lots`` are sequential from 1 and their flattened order equals ``queue``;
* the file is written atomically and never inside the process archive.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FROZEN_QUEUE_SCHEMA_VERSION = 3
ACQUISITION_SOURCE = "econtas"
DEFAULT_LOT_SIZE = 50
SOURCE_SCOPES: frozenset[str] = frozenset({"sector_finalistic", "my_processes"})
PROCESS_KEY_PATTERN = re.compile(r"^\s*(\d+)\s*/\s*(\d{4})\s*$")
CANONICAL_KEYS = ("schema_version", "observed_at", "spec", "queue", "blocked")


class FrozenQueueError(RuntimeError):
    """Raised when a frozen queue cannot be built as the collector expects."""


@dataclass(slots=True)
class FrozenQueueInfo:
    path: Path
    analysis_id: str
    dataset_sha256: str
    queue_size: int
    lot_count: int
    lot_size: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_process_key(value: object) -> str:
    """Normalize one process key exactly like the legacy filter does."""

    raw = value.get("process_key") or value.get("key") if isinstance(value, Mapping) else value
    match = PROCESS_KEY_PATTERN.match(str(raw or ""))
    if match is None:
        raise FrozenQueueError(f"invalid process key: {raw!r}")
    return f"{match.group(1)}/{match.group(2)}"


def build_frozen_queue(
    processes: Iterable[object],
    source_scope: str,
    marker: Mapping[str, Any] | None = None,
    *,
    lot_size: int = DEFAULT_LOT_SIZE,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Build the complete frozen-queue document for ``processes``."""

    if source_scope not in SOURCE_SCOPES:
        raise FrozenQueueError(f"unsupported source scope: {source_scope!r}")
    keys = list(dict.fromkeys(canonical_process_key(item) for item in processes))
    if not keys:
        raise FrozenQueueError("a frozen queue needs at least one process key")
    size = max(1, int(lot_size))

    queue = [{"process_key": key} for key in keys]
    lots: list[dict[str, Any]] = []
    for start in range(0, len(queue), size):
        number = len(lots) + 1
        lots.append(
            {
                "lot_number": number,
                "lot_id": f"lot-{number}",
                "items": queue[start : start + size],
            }
        )

    canonical_source: dict[str, Any] = {
        "schema_version": FROZEN_QUEUE_SCHEMA_VERSION,
        "observed_at": observed_at or utc_now(),
        "spec": {
            "source_scope": source_scope,
            "acquisition_source": ACQUISITION_SOURCE,
            "marker": dict(marker or {}),
        },
        "queue": queue,
        "blocked": [],
    }
    canonical_json = json.dumps(
        canonical_source, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    dataset_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    document: dict[str, Any] = {
        "schema_version": canonical_source["schema_version"],
        "observed_at": canonical_source["observed_at"],
        "analysis_id": f"analysis-{dataset_sha256[:24]}",
        "dataset_sha256": dataset_sha256,
        "canonical_json": canonical_json,
        "spec": canonical_source["spec"],
        "queue": queue,
        "blocked": canonical_source["blocked"],
        "lots": lots,
    }
    for key in CANONICAL_KEYS:
        if key not in document:
            raise FrozenQueueError(f"internal error: canonical key {key} missing")
    return document


def write_frozen_queue(
    processes: Sequence[object],
    source_scope: str,
    marker: Mapping[str, Any] | None,
    path: str | Path,
    lot_size: int = DEFAULT_LOT_SIZE,
    *,
    observed_at: str | None = None,
) -> FrozenQueueInfo:
    """Write the document atomically and report the identity the collector sees."""

    document = build_frozen_queue(
        processes, source_scope, marker, lot_size=lot_size, observed_at=observed_at
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:  # pragma: no cover - best effort cleanup
                pass
    return FrozenQueueInfo(
        path=target,
        analysis_id=str(document["analysis_id"]),
        dataset_sha256=str(document["dataset_sha256"]),
        queue_size=len(document["queue"]),
        lot_count=len(document["lots"]),
        lot_size=max(1, int(lot_size)),
    )


def read_frozen_queue(path: str | Path) -> dict[str, Any]:
    """Read a queue back, verifying the identity before trusting it."""

    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict):
        raise FrozenQueueError("a frozen queue must be a JSON object")
    canonical_json = document.get("canonical_json")
    if not isinstance(canonical_json, str) or not canonical_json:
        raise FrozenQueueError("canonical_json is missing from the frozen queue")
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    if digest != document.get("dataset_sha256"):
        raise FrozenQueueError("the frozen queue hash does not match its content")
    if document.get("analysis_id") != f"analysis-{digest[:24]}":
        raise FrozenQueueError("the frozen queue analysis_id does not match its hash")
    try:
        canonical = json.loads(canonical_json)
    except json.JSONDecodeError as error:
        raise FrozenQueueError(f"canonical_json is not valid JSON: {error.msg}") from error
    if canonical != {key: document.get(key) for key in CANONICAL_KEYS}:
        raise FrozenQueueError("the frozen queue content does not match its canonical_json")
    return document
