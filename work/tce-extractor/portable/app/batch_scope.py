"""Closed contracts for hybrid portal analysis and deterministic lots.

This module is deliberately independent from browser and network code.  It
normalizes sanitized observations, computes a preview, and freezes only items
whose Area Restrita evidence and local acquisition state are both sufficient.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import unicodedata
from typing import Any, Mapping, Sequence

try:  # package import in tests/service
    from .filter_new_batch import FilterError, canonical_process_key
except ImportError:  # direct script-compatible import used by existing portable tools
    from filter_new_batch import FilterError, canonical_process_key


SCHEMA_VERSION = 3
LEGACY_SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = frozenset({LEGACY_SCHEMA_VERSION, SCHEMA_VERSION})
SOURCE_SCOPES = frozenset({"sector_finalistic", "my_processes"})
ACQUISITION_SOURCES = frozenset({"econtas"})
ITEM_STATES = frozenset(
    {
        "discovered",
        "eligibility_confirmed",
        "acquisition_pending",
        "downloaded",
        "ocr_pending",
        "ocr_ready",
        "ready_for_preflight",
        "prepared",
        "awaiting_send_confirmation",
        "send_intent",
        "send_issued",
        "outcome_observed",
        "confirmed",
        "failed",
        "unconfirmed",
        "blocked",
    }
)
_LEGACY_SPEC_KEYS = frozenset(
    {
        "schema_version",
        "source_scope",
        "marker",
        "acquisition_source",
        "lot_size",
        "analysis_only",
        "auto_prepare",
        "auto_submit",
        "dataset_sha256",
        "area_snapshot_sha256",
    }
)
_SPEC_KEYS = _LEGACY_SPEC_KEYS | frozenset(
    {"input_list_id", "input_sha256", "input_unique_count"}
)
_MARKER_KEYS = frozenset({"label", "value"})
_ACTION_SIGNATURE_KEYS = frozenset({"kind", "alt", "title", "src"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INPUT_LIST_ID_RE = re.compile(r"^input-[0-9a-f]{24}$")
_AREA_CLASSIFICATIONS = frozenset(
    {
        "PRECISA_COMPLEMENTAR",
        "ATO_COMPLEMENTADO",
        "NAO_ENCONTRADO_AREA_RESTRITA",
        "AMBIGUO",
        "BLOQUEADO",
    }
)
_MATCHES = frozenset({"pending", "exact", "missing", "ambiguous", "conflict"})
_OCR_STATES = frozenset({"not_run", "pending", "ready", "inconclusive", "failed"})


def _error(message: str) -> ValueError:
    return ValueError(message)


def _text(value: object, name: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise _error(f"{name} deve ser texto não vazio com até {max_length} caracteres")
    return value.strip()


def _sha(value: object, name: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise _error(f"{name} deve ser SHA-256 hexadecimal")
    return value


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise _error("valor não é JSON canônico") from exc


def _normalize_action(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def _has_complement_action(value: str | None) -> bool:
    return "complementar ato" in _normalize_action(value)


def validate_batch_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a defensive, closed batch specification."""

    if not isinstance(spec, Mapping):
        raise _error("especificação de lote possui chaves inválidas ou ausentes")
    schema_version = spec.get("schema_version")
    expected_keys = _LEGACY_SPEC_KEYS if schema_version == LEGACY_SCHEMA_VERSION else _SPEC_KEYS
    if set(spec) != expected_keys:
        raise _error("especificação de lote possui chaves inválidas ou ausentes")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise _error("versão da especificação de lote incompatível")

    source_scope = spec["source_scope"]
    if source_scope not in SOURCE_SCOPES:
        raise _error("source_scope inválido")
    acquisition_source = spec["acquisition_source"]
    if acquisition_source not in ACQUISITION_SOURCES:
        raise _error("acquisition_source inválido")

    marker = spec["marker"]
    if not isinstance(marker, Mapping) or set(marker) != _MARKER_KEYS:
        raise _error("marker deve conter exatamente label e value")
    normalized_marker = {
        "label": _text(marker["label"], "marker.label"),
        "value": _text(marker["value"], "marker.value", max_length=256),
    }

    lot_size = spec["lot_size"]
    if isinstance(lot_size, bool) or not isinstance(lot_size, int) or not 1 <= lot_size <= 1000:
        raise _error("lot_size deve ser inteiro entre 1 e 1000")
    booleans = ("analysis_only", "auto_prepare", "auto_submit")
    for name in booleans:
        if type(spec[name]) is not bool:
            raise _error(f"{name} deve ser booleano")

    dataset_sha256 = _sha(spec["dataset_sha256"], "dataset_sha256", allow_none=True)
    area_snapshot_sha256 = _sha(spec["area_snapshot_sha256"], "area_snapshot_sha256")
    normalized = {
        "schema_version": schema_version,
        "source_scope": source_scope,
        "marker": normalized_marker,
        "acquisition_source": acquisition_source,
        "lot_size": lot_size,
        "analysis_only": spec["analysis_only"],
        "auto_prepare": spec["auto_prepare"],
        "auto_submit": spec["auto_submit"],
        "dataset_sha256": dataset_sha256,
        "area_snapshot_sha256": area_snapshot_sha256,
    }
    if schema_version == SCHEMA_VERSION:
        input_list_id = spec["input_list_id"]
        if not isinstance(input_list_id, str) or not _INPUT_LIST_ID_RE.fullmatch(input_list_id):
            raise _error("input_list_id inválido")
        input_unique_count = spec["input_unique_count"]
        if type(input_unique_count) is not int or not 1 <= input_unique_count <= 10000:
            raise _error("input_unique_count deve ser inteiro positivo")
        normalized.update(
            {
                "input_list_id": input_list_id,
                "input_sha256": _sha(spec["input_sha256"], "input_sha256"),
                "input_unique_count": input_unique_count,
            }
        )
    return normalized


def _normalize_observation(raw: Mapping[str, Any], expected: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise _error("observação deve ser um objeto")
    try:
        process_key = canonical_process_key({"key": raw.get("process_key")}, "process_key")
    except FilterError as exc:
        raise _error(str(exc)) from exc

    interested_key = raw.get("interested_key")
    if interested_key is not None:
        interested_key = _text(interested_key, "interested_key", max_length=256)

    area = raw.get("area_restrita")
    if not isinstance(area, Mapping):
        raise _error("area_restrita ausente")
    area_scope = area.get("scope")
    if area_scope not in SOURCE_SCOPES:
        raise _error("area_restrita.scope inválido")
    marker_label = _text(area.get("marker_label"), "area_restrita.marker_label")
    marker_value = _text(area.get("marker_value"), "area_restrita.marker_value", max_length=256)
    if marker_label != expected["marker"]["label"] or marker_value != expected["marker"]["value"]:
        raise _error("observação não pertence ao marcador solicitado")
    if area_scope != expected["source_scope"]:
        raise _error("observação não pertence à origem solicitada")
    if type(area.get("needs_complement")) is not bool:
        raise _error("area_restrita.needs_complement deve ser booleano")
    classification = area.get("classification")
    if expected["schema_version"] == SCHEMA_VERSION:
        if classification not in _AREA_CLASSIFICATIONS:
            raise _error("area_restrita.classification inválida")
        if area["needs_complement"] != (classification == "PRECISA_COMPLEMENTAR"):
            raise _error("area_restrita.classification não confere com needs_complement")
    else:
        classification = "PRECISA_COMPLEMENTAR" if area["needs_complement"] else "ATO_COMPLEMENTADO"
    action = area.get("action_observed")
    if action is not None:
        action = _text(action, "area_restrita.action_observed", max_length=256)
    action_signature = area.get("action_signature")
    if action_signature is not None:
        if not isinstance(action_signature, Mapping) or set(action_signature) != _ACTION_SIGNATURE_KEYS:
            raise _error("area_restrita.action_signature possui chaves inválidas")
        action_signature = {
            "kind": _text(action_signature.get("kind"), "area_restrita.action_signature.kind", max_length=64),
            "alt": str(action_signature.get("alt", ""))[:256],
            "title": str(action_signature.get("title", ""))[:256],
            "src": _text(action_signature.get("src"), "area_restrita.action_signature.src", max_length=512),
        }
        if action_signature["kind"] != "red_complement_icon":
            raise _error("area_restrita.action_signature.kind inválido")
    if area.get("needs_complement") is True and action_signature is None:
        raise _error("pendência exige assinatura do ícone vermelho Complementar Ato")
    snapshot_hash = _sha(area.get("snapshot_hash"), "area_restrita.snapshot_hash")

    econtas = raw.get("econtas")
    if not isinstance(econtas, Mapping):
        raise _error("econtas ausente")
    match = econtas.get("match")
    if match not in _MATCHES:
        raise _error("econtas.match inválido")
    documents = econtas.get("documents")
    if not isinstance(documents, list):
        raise _error("econtas.documents deve ser lista")
    if any(not isinstance(document, (str, Mapping)) for document in documents):
        raise _error("econtas.documents possui item inválido")
    econtas_hash = _sha(econtas.get("snapshot_hash"), "econtas.snapshot_hash", allow_none=True)
    ocr_status = econtas.get("ocr_status", "not_run")
    if ocr_status not in _OCR_STATES:
        raise _error("econtas.ocr_status inválido")

    normalized = {
        "process_key": process_key,
        "interested_key": interested_key,
        "area_restrita": {
            "scope": area_scope,
            "marker_label": marker_label,
            "marker_value": marker_value,
            "classification": classification,
            "needs_complement": area["needs_complement"],
            "action_observed": action,
            "action_signature": action_signature,
            "snapshot_hash": snapshot_hash,
        },
        "econtas": {
            "match": match,
            "documents": deepcopy(documents),
            "snapshot_hash": econtas_hash,
            "ocr_status": ocr_status,
        },
        "state": "discovered",
    }
    for field in ("input_row", "duplicate_of_row"):
        if field in raw:
            value = raw[field]
            if type(value) is not int or value < 1:
                raise _error(f"{field} deve ser inteiro positivo")
            normalized[field] = value
    return normalized


def _blocked_reason(item: Mapping[str, Any]) -> str | None:
    area = item["area_restrita"]
    econtas = item["econtas"]
    classification = area["classification"]
    if classification != "PRECISA_COMPLEMENTAR":
        return None if classification == "ATO_COMPLEMENTADO" else classification.casefold()
    if not area["needs_complement"]:
        return None
    if not _has_complement_action(area["action_observed"]):
        return "without_action"
    if item["interested_key"] is None:
        return "identity_ambiguous"
    if econtas["match"] != "exact" or not econtas["documents"]:
        return "document_unavailable"
    if econtas["ocr_status"] != "ready":
        return "ocr_inconclusive" if econtas["ocr_status"] == "inconclusive" else "ocr_not_ready"
    return None


def _acquisition_block_reason(item: Mapping[str, Any]) -> str | None:
    """Return only Area Restrita blockers for the acquisition queue.

    Missing e-Contas documents and OCR are deliberately not blockers here:
    acquiring the frozen lot is the step that is meant to resolve them.
    """

    area = item["area_restrita"]
    classification = area["classification"]
    if classification != "PRECISA_COMPLEMENTAR":
        return "already_complemented" if classification == "ATO_COMPLEMENTADO" else classification.casefold()
    if not area["needs_complement"]:
        return "already_complemented"
    if not _has_complement_action(area["action_observed"]):
        return "without_action"
    if item["interested_key"] is None:
        return "identity_ambiguous"
    return None


def _normalize_rows(spec: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validated = validate_batch_spec(spec)
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise _error("rows deve ser uma sequência")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for raw in rows:
        item = _normalize_observation(raw, validated)
        identity = (item["process_key"], item["interested_key"])
        if identity in seen:
            raise _error("observações duplicadas na fotografia")
        seen.add(identity)
        normalized.append(item)
    return normalized


def build_preview(spec: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return aggregate metrics without changing portal or local state."""

    validated = validate_batch_spec(spec)
    items = _normalize_rows(validated, rows)
    statuses = [item["area_restrita"]["classification"] for item in items]
    needs = [item for item in items if item["area_restrita"]["classification"] == "PRECISA_COMPLEMENTAR"]
    available = [
        item
        for item in items
        if item["econtas"]["match"] == "exact" and bool(item["econtas"]["documents"])
    ]
    ocr_ready = [
        item
        for item in items
        if item["econtas"]["match"] == "exact"
        and bool(item["econtas"]["documents"])
        and item["econtas"]["ocr_status"] == "ready"
    ]
    eligible = [item for item in needs if _blocked_reason(item) is None]
    acquisition_eligible = [item for item in needs if _acquisition_block_reason(item) is None]
    blocked = [item for item in items if _acquisition_block_reason(item) is not None]
    blocked_count = sum(status == "BLOQUEADO" for status in statuses) if validated["schema_version"] == SCHEMA_VERSION else len(blocked)
    return {
        "schema_version": validated["schema_version"],
        "source_scope": validated["source_scope"],
        "marker": deepcopy(validated["marker"]),
        "lot_size": validated["lot_size"],
        "total_seen": len(items),
        "needs_complement": len(needs),
        "already_complemented": sum(status == "ATO_COMPLEMENTADO" for status in statuses),
        "absent": sum(status == "NAO_ENCONTRADO_AREA_RESTRITA" for status in statuses),
        "ambiguous": sum(status == "AMBIGUO" for status in statuses),
        "without_action": sum(
            _blocked_reason(item) == "without_action" for item in needs
        ),
        "identity_ambiguous": sum(item["interested_key"] is None for item in needs),
        "download_available": len(available),
        "download_missing": len(items) - len(available),
        "ocr_ready": len(ocr_ready),
        "ocr_inconclusive": sum(
            item["econtas"]["ocr_status"] == "inconclusive" for item in items
        ),
        "acquisition_eligible": len(acquisition_eligible),
        "eligible": len(eligible),
        "blocked": blocked_count,
        "area_blocked": len(blocked),
        "lot_count": (len(acquisition_eligible) + validated["lot_size"] - 1) // validated["lot_size"],
    }


def freeze_queue(
    spec: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    observed_at: str,
) -> dict[str, Any]:
    """Freeze an immutable, ordered queue from one validated portal snapshot."""

    validated = validate_batch_spec(spec)
    observed_at = _text(observed_at, "observed_at", max_length=128)
    items = _normalize_rows(validated, rows)
    queue: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for item in items:
        acquisition_reason = _acquisition_block_reason(item)
        if acquisition_reason is None:
            item["state"] = "discovered" if _blocked_reason(item) is None else "acquisition_pending"
            item["ordinal"] = len(queue) + 1
            queue.append(item)
        elif acquisition_reason != "already_complemented":
            item["state"] = "blocked"
            item["block_reason"] = acquisition_reason
            blocked.append(item)

    payload = {
        "schema_version": validated["schema_version"],
        "observed_at": observed_at,
        "spec": validated,
        "queue": queue,
        "blocked": blocked,
    }
    canonical_json = _canonical_json(payload)
    dataset_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return {
        **payload,
        "analysis_id": f"analysis-{dataset_sha256[:24]}",
        "dataset_sha256": dataset_sha256,
        "canonical_json": canonical_json,
    }


def split_lots(queue: Sequence[Mapping[str, Any]], lot_size: int) -> list[dict[str, Any]]:
    """Split an already frozen queue without changing its order."""

    if isinstance(lot_size, bool) or not isinstance(lot_size, int) or not 1 <= lot_size <= 1000:
        raise _error("lot_size deve ser inteiro entre 1 e 1000")
    if not isinstance(queue, Sequence) or isinstance(queue, (str, bytes, bytearray)):
        raise _error("queue deve ser uma sequência")
    lots: list[dict[str, Any]] = []
    for start in range(0, len(queue), lot_size):
        number = len(lots) + 1
        items = [deepcopy(item) for item in queue[start : start + lot_size]]
        lots.append(
            {
                "lot_number": number,
                "lot_id": f"lot-{number}",
                "items": items,
            }
        )
    return lots
