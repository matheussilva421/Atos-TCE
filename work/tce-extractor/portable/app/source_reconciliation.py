"""Reconcile Area Restrita identities with local e-Contas acquisitions.

The adapter accepts sanitized records only.  It never authenticates, downloads
or decides portal eligibility; it only creates a deterministic enrichment that
the batch contract can consume.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from collections import defaultdict
from typing import Any, Mapping, Sequence

try:
    from .batch_scope import validate_batch_spec
    from .filter_new_batch import FilterError, canonical_process_key
except ImportError:  # direct script-compatible import used by existing tools
    from batch_scope import validate_batch_spec
    from filter_new_batch import FilterError, canonical_process_key


SCHEMA_VERSION = 1
_PRIVATE_KEYS = frozenset(
    {
        "cpf",
        "cookie",
        "token",
        "session",
        "password",
        "senha",
        "absolute_path",
        "pdf_path",
        "url",
    }
)
_MATCHES = ("exact", "missing", "ambiguous", "conflict")
_OCR_STATES = frozenset({"not_run", "pending", "ready", "inconclusive", "failed"})


def _text(value: object, name: str, *, allow_none: bool = False, max_length: int = 512) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{name} inválido")
    return value.strip()


def _safe_scalar(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and len(value) <= 2048 and "\r" not in value and "\n" not in value:
        return value
    return None


def _sanitize_document(value: object) -> object:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key in sorted(value):
            if not isinstance(key, str) or key.casefold() in _PRIVATE_KEYS:
                continue
            sanitized = _sanitize_document(value[key])
            if sanitized is not None:
                result[key] = sanitized
        return result
    if isinstance(value, list):
        return [_sanitize_document(item) for item in value]
    return _safe_scalar(value)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _process_key(value: object) -> str:
    try:
        return canonical_process_key({"key": value}, "process_key")
    except FilterError as exc:
        raise ValueError(str(exc)) from exc


def _candidate(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("registro e-Contas inválido")
    process_key = _process_key(raw.get("process_key"))
    interested_key = _text(raw.get("interested_key"), "interested_key", allow_none=True, max_length=256)
    documents = raw.get("documents", [])
    if not isinstance(documents, list):
        raise ValueError("econtas.documents deve ser lista")
    sanitized_documents = [_sanitize_document(document) for document in documents]
    sanitized_documents = [document for document in sanitized_documents if document is not None]
    ocr_status = raw.get("ocr_status", "not_run")
    if ocr_status not in _OCR_STATES:
        raise ValueError("econtas.ocr_status inválido")
    return {
        "process_key": process_key,
        "interested_key": interested_key,
        "documents": sanitized_documents,
        "ocr_status": ocr_status,
    }


def _area_row(raw: Mapping[str, Any], expected: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("registro Área Restrita inválido")
    process_key = _process_key(raw.get("process_key"))
    interested_key = _text(raw.get("interested_key"), "interested_key", allow_none=True, max_length=256)
    area = raw.get("area_restrita")
    if not isinstance(area, Mapping):
        raise ValueError("area_restrita ausente")
    if area.get("scope") != expected["source_scope"]:
        raise ValueError("escopo da Área Restrita divergente")
    if area.get("marker_label") != expected["marker"]["label"] or area.get("marker_value") != expected["marker"]["value"]:
        raise ValueError("marcador da Área Restrita divergente")
    if type(area.get("needs_complement")) is not bool:
        raise ValueError("needs_complement inválido")
    action = _text(area.get("action_observed"), "action_observed", allow_none=True, max_length=256)
    snapshot_hash = _text(area.get("snapshot_hash"), "area snapshot_hash", max_length=64)
    if snapshot_hash is None or len(snapshot_hash) != 64:
        raise ValueError("area snapshot_hash inválido")
    return {
        "process_key": process_key,
        "interested_key": interested_key,
        "area_restrita": {
            "scope": expected["source_scope"],
            "marker_label": expected["marker"]["label"],
            "marker_value": expected["marker"]["value"],
            "needs_complement": area["needs_complement"],
            "action_observed": action,
            "snapshot_hash": snapshot_hash,
        },
    }


def _econtas_payload(match: str, candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    if candidate is None:
        return {
            "match": match,
            "documents": [],
            "snapshot_hash": None,
            "ocr_status": "not_run",
        }
    raw = {
        "process_key": candidate["process_key"],
        "interested_key": candidate["interested_key"],
        "documents": candidate["documents"],
        "ocr_status": candidate["ocr_status"],
    }
    digest = hashlib.sha256(_canonical_json(raw).encode("utf-8")).hexdigest()
    return {
        "match": match,
        "documents": deepcopy(candidate["documents"]),
        "snapshot_hash": digest,
        "ocr_status": candidate["ocr_status"],
    }


def _match(area: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]) -> tuple[str, Mapping[str, Any] | None]:
    if not candidates:
        return "missing", None
    interested_key = area["interested_key"]
    if interested_key is None:
        return "ambiguous", None
    matches = [candidate for candidate in candidates if candidate["interested_key"] == interested_key]
    if len(candidates) == 1 and len(matches) == 1:
        return "exact", matches[0]
    if len(matches) > 1 or len(candidates) > 1:
        return "conflict", None
    return "conflict", None


def reconcile_snapshot(
    spec: Mapping[str, Any],
    area_rows: Sequence[Mapping[str, Any]],
    econtas_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a deterministic, sanitized enrichment snapshot."""

    expected = validate_batch_spec(spec)
    if not isinstance(area_rows, Sequence) or isinstance(area_rows, (str, bytes, bytearray)):
        raise ValueError("area_rows deve ser sequência")
    if not isinstance(econtas_rows, Sequence) or isinstance(econtas_rows, (str, bytes, bytearray)):
        raise ValueError("econtas_rows deve ser sequência")

    candidates_by_process: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in econtas_rows:
        candidate = _candidate(raw)
        candidates_by_process[candidate["process_key"]].append(candidate)
    for candidates in candidates_by_process.values():
        candidates.sort(key=lambda item: (item["interested_key"] or "", _canonical_json(item["documents"])))

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    counts = {match: 0 for match in _MATCHES}
    for raw in area_rows:
        area = _area_row(raw, expected)
        identity = (area["process_key"], area["interested_key"])
        if identity in seen:
            raise ValueError("registros Área Restrita duplicados")
        seen.add(identity)
        match, candidate = _match(area, candidates_by_process.get(area["process_key"], []))
        counts[match] += 1
        enriched = deepcopy(area)
        enriched["econtas"] = _econtas_payload(match, candidate)
        rows.append(enriched)

    snapshot_payload = {
        "schema_version": SCHEMA_VERSION,
        "spec": expected,
        "rows": rows,
    }
    snapshot_json = _canonical_json(snapshot_payload)
    return {
        **snapshot_payload,
        "counts": counts,
        "snapshot_hash": hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest(),
    }
