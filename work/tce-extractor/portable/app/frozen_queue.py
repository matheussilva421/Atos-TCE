"""Validate and reconcile immutable analysis queues before e-Contas acquisition.

This module has no browser or network dependency.  It is the boundary between
the Area Restrita analysis snapshot and the e-Contas downloader: only the
frozen process keys may cross it, in their persisted order.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

try:
    from .filter_new_batch import FilterError, canonical_process_key
except ImportError:  # direct script-compatible import
    from filter_new_batch import FilterError, canonical_process_key


_ANALYSIS_ID_RE = re.compile(r"^analysis-[0-9a-f]{24}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SCOPES = frozenset({"sector_finalistic", "my_processes"})


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} ausente ou inválido")
    return value.strip()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"fila congelada inválida: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError("fila congelada deve ser um objeto JSON")
    return value


def _validate_identity(value: Mapping[str, Any]) -> None:
    analysis_id = value.get("analysis_id")
    dataset_sha256 = value.get("dataset_sha256")
    canonical_json = value.get("canonical_json")
    if not isinstance(analysis_id, str) or not _ANALYSIS_ID_RE.fullmatch(analysis_id):
        raise ValueError("analysis_id da fila congelada inválido")
    if not isinstance(dataset_sha256, str) or not _SHA256_RE.fullmatch(dataset_sha256):
        raise ValueError("dataset_sha256 da fila congelada inválido")
    if not isinstance(canonical_json, str) or not canonical_json:
        raise ValueError("canonical_json ausente na fila congelada")
    actual = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    if actual != dataset_sha256 or f"analysis-{actual[:24]}" != analysis_id:
        raise ValueError("hash ou identidade da fila congelada não confere")
    try:
        canonical = json.loads(canonical_json)
    except json.JSONDecodeError as exc:
        raise ValueError("canonical_json da fila congelada inválido") from exc
    expected = {key: value.get(key) for key in ("schema_version", "observed_at", "spec", "queue", "blocked")}
    if canonical != expected:
        raise ValueError("conteúdo da fila congelada não confere com o hash")


def _validate_queue_items(items: object, name: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError(f"{name} deve ser uma lista")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValueError(f"{name}[{index}] inválido")
        try:
            key = canonical_process_key({"key": item.get("process_key")}, f"{name}[{index}]")
        except FilterError as exc:
            raise ValueError(str(exc)) from exc
        if key in seen:
            raise ValueError(f"chave de processo duplicada na {name}: {key}")
        seen.add(key)
        normalized = deepcopy(dict(item))
        normalized["process_key"] = key
        result.append(normalized)
    return result


def _validate_lots(value: object, queue: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("lots da fila congelada deve ser uma lista")
    lots: list[dict[str, Any]] = []
    seen: set[str] = set()
    flattened: list[str] = []
    for index, lot in enumerate(value):
        if not isinstance(lot, Mapping):
            raise ValueError(f"lots[{index}] inválido")
        number = lot.get("lot_number")
        if isinstance(number, bool) or not isinstance(number, int) or number != index + 1:
            raise ValueError("lot_number deve ser sequencial e começar em 1")
        if lot.get("lot_id") != f"lot-{number}":
            raise ValueError(f"lots[{index}] possui lot_id inválido")
        items = _validate_queue_items(lot.get("items"), f"lots[{index}].items")
        for item in items:
            key = item["process_key"]
            if key in seen:
                raise ValueError(f"processo repetido entre lotes: {key}")
            seen.add(key)
            flattened.append(key)
        lots.append({"lot_number": number, "lot_id": f"lot-{number}", "items": items})
    queue_keys = [item["process_key"] for item in queue]
    if flattened != queue_keys:
        raise ValueError("lots não preservam a ordem da fila congelada")
    return lots


def load_frozen_queue(path: Path, *, lot_number: int | None = None) -> dict[str, Any]:
    """Load one full queue or one explicitly requested lot.

    A lot number is one-based.  A queue containing persisted lots may still be
    consumed as a whole when no number is supplied; callers that want bounded
    acquisition should pass the number explicitly.
    """

    value = _load_json(Path(path))
    if value.get("schema_version") not in (1, 2, 3):
        raise ValueError("schema_version da fila congelada incompatível")
    _validate_identity(value)
    spec = value.get("spec")
    if not isinstance(spec, Mapping):
        raise ValueError("spec ausente na fila congelada")
    if spec.get("source_scope") not in _SOURCE_SCOPES:
        raise ValueError("source_scope da fila congelada inválido")
    if spec.get("acquisition_source") != "econtas":
        raise ValueError("acquisition_source da fila congelada deve ser econtas")
    queue = _validate_queue_items(value.get("queue"), "queue")
    if not isinstance(value.get("blocked"), list):
        raise ValueError("blocked da fila congelada deve ser uma lista")

    lots_value = value.get("lots")
    lots = _validate_lots(lots_value, queue) if lots_value is not None else []
    if lot_number is not None:
        if isinstance(lot_number, bool) or not isinstance(lot_number, int) or lot_number < 1:
            raise ValueError("lot_number deve ser inteiro positivo")
        if not lots:
            raise ValueError("lot_number solicitado, mas a análise ainda não possui lots")
        matches = [lot for lot in lots if lot["lot_number"] == lot_number]
        if not matches:
            raise ValueError(f"lot_number inexistente: {lot_number}")
        items = matches[0]["items"]
    else:
        items = queue

    return {
        "analysis_id": value["analysis_id"],
        "dataset_sha256": value["dataset_sha256"],
        "source_scope": spec["source_scope"],
        "marker": deepcopy(spec.get("marker")),
        "lot_number": lot_number,
        "items": deepcopy(items),
        "queue_size": len(queue),
    }


def reconcile_frozen_queue(
    items: Sequence[Mapping[str, Any]], processes: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Match a frozen queue against the current e-Contas list, fail-closed."""

    normalized_items = _validate_queue_items(list(items), "items")
    by_key: dict[str, dict[str, Any]] = {}
    for index, process in enumerate(processes):
        if not isinstance(process, Mapping):
            raise ValueError(f"processes[{index}] inválido")
        try:
            key = canonical_process_key(process, f"processes[{index}]")
        except FilterError as exc:
            raise ValueError(str(exc)) from exc
        if key in by_key:
            raise ValueError(f"processo duplicado na lista e-Contas: {key}")
        normalized = dict(process)
        normalized["key"] = key
        by_key[key] = normalized

    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    for item in normalized_items:
        key = item["process_key"]
        process = by_key.get(key)
        if process is None:
            missing.append(key)
        else:
            selected.append(process)
    return {"selected": selected, "missing": missing}


__all__ = ["load_frozen_queue", "reconcile_frozen_queue"]
