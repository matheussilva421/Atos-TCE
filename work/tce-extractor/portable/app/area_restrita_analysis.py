"""Fail-closed classification and guard helpers for Area Restrita snapshots."""

from __future__ import annotations

from copy import deepcopy
import re
import unicodedata
from typing import Any, Mapping, Sequence


AREA_CLASSIFICATIONS = frozenset(
    {
        "PRECISA_COMPLEMENTAR",
        "ATO_COMPLEMENTADO",
        "NAO_ENCONTRADO_AREA_RESTRITA",
        "AMBIGUO",
        "BLOQUEADO",
    }
)
_SEMANTIC_RE = re.compile(r"^complementar ato$", re.IGNORECASE)


def _normalize(value: object) -> str:
    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    return " ".join("".join(char for char in decomposed if not unicodedata.combining(char)).casefold().split())


def _is_red_complement(control: Mapping[str, Any]) -> bool:
    if control.get("kind") != "red_complement_icon":
        return False
    semantic_values = {_normalize(control.get("alt")), _normalize(control.get("title"))}
    return any(_SEMANTIC_RE.fullmatch(value) for value in semantic_values)


def _is_completed(control: Mapping[str, Any]) -> bool:
    values = {_normalize(control.get("alt")), _normalize(control.get("title"))}
    return "ato complementado" in values


def _safe_signature(control: Mapping[str, Any]) -> dict[str, str]:
    return {
        "kind": "red_complement_icon",
        "alt": str(control.get("alt", ""))[:256],
        "title": str(control.get("title", ""))[:256],
        "src": str(control.get("src", ""))[:512],
    }


def classify_area_evidence(evidence: Mapping[str, Any], *, expected_marker: Mapping[str, str]) -> dict[str, Any]:
    """Classify one sanitized row; never infer eligibility from loose text."""

    if not isinstance(evidence, Mapping) or not isinstance(expected_marker, Mapping):
        return {"classification": "BLOQUEADO", "reason": "evidence_invalid"}
    marker = evidence.get("marker")
    if marker != dict(expected_marker):
        return {"classification": "BLOQUEADO", "reason": "marker_identity_diverged"}
    if evidence.get("present") is not True:
        return {"classification": "NAO_ENCONTRADO_AREA_RESTRITA", "action_signature": None}
    controls = evidence.get("controls", [])
    if not isinstance(controls, Sequence) or isinstance(controls, (str, bytes, bytearray)):
        return {"classification": "BLOQUEADO", "reason": "controls_invalid"}
    sanitized = [control for control in controls if isinstance(control, Mapping)]
    pending = [control for control in sanitized if _is_red_complement(control)]
    completed = [control for control in sanitized if _is_completed(control)]
    if len(pending) > 1:
        return {"classification": "AMBIGUO", "reason": "multiple_complement_controls"}
    if pending:
        return {
            "classification": "PRECISA_COMPLEMENTAR",
            "action_signature": _safe_signature(pending[0]),
        }
    if completed:
        return {"classification": "ATO_COMPLEMENTADO", "action_signature": None}
    return {"classification": "AMBIGUO", "reason": "no_recognized_action"}


class AreaScanGuard:
    """Detect global inconsistencies while a paginated marker scan is running."""

    def __init__(self, *, marker: Mapping[str, str], origin: str) -> None:
        self.marker = deepcopy(dict(marker))
        self.origin = origin
        self._pages: set[int] = set()
        self._snapshots: dict[int, str] = {}
        self._snapshot_hashes: set[str] = set()

    def check(self, *, marker: Mapping[str, str], origin: str, session_valid: bool, identity_ok: bool = True) -> None:
        if not session_valid:
            raise RuntimeError("sessão expirada durante a análise")
        if origin != self.origin:
            raise RuntimeError("origem da Área Restrita divergente")
        if dict(marker) != self.marker:
            raise RuntimeError("marcador mudou durante a análise")
        if not identity_ok:
            raise RuntimeError("identidade da linha divergente")

    def accept_page(self, page_number: int, snapshot_hash: str) -> None:
        if page_number in self._pages or snapshot_hash in self._snapshot_hashes:
            raise RuntimeError("página repetida durante a análise")
        self._pages.add(page_number)
        self._snapshots[page_number] = snapshot_hash
        self._snapshot_hashes.add(snapshot_hash)


def split_eligible_lots(queue: Sequence[Mapping[str, Any]], lot_size: int = 300) -> list[dict[str, Any]]:
    if type(lot_size) is not int or not 1 <= lot_size <= 300:
        raise ValueError("lot_size deve ser inteiro entre 1 e 300")
    if not isinstance(queue, Sequence) or isinstance(queue, (str, bytes, bytearray)):
        raise ValueError("fila deve ser uma sequência")
    return [
        {
            "lot_number": index // lot_size + 1,
            "lot_id": f"lot-{index // lot_size + 1}",
            "items": [deepcopy(item) for item in queue[index : index + lot_size]],
        }
        for index in range(0, len(queue), lot_size)
    ]
