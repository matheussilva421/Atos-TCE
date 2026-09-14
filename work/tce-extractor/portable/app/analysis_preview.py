"""Durable storage for read-only analysis snapshots and deterministic lots."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

try:
    from .batch_scope import build_preview, freeze_queue, split_lots
except ImportError:  # direct script-compatible import used by existing tools
    from batch_scope import build_preview, freeze_queue, split_lots


SCHEMA_VERSION = 3
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2, 3})
_ANALYSIS_ID_RE = re.compile(r"^analysis-[0-9a-f]{24}$")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _analysis_path(root: Path, analysis_id: str) -> Path:
    if not isinstance(analysis_id, str) or not _ANALYSIS_ID_RE.fullmatch(analysis_id):
        raise ValueError("analysis_id inválido")
    return Path(root) / "automacao" / "analises" / f"{analysis_id}.json"


def create_preview(
    root: Path,
    spec: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    observed_at: str,
) -> dict[str, Any]:
    """Build an analysis payload without writing it or contacting a portal."""

    del root  # the root belongs to the persistence layer, not the pure builder
    preview = build_preview(spec, rows)
    frozen = freeze_queue(spec, rows, observed_at=observed_at)
    return {
        **frozen,
        "schema_version": frozen["schema_version"],
        "preview": preview,
    }


class AnalysisPreviewStore:
    """Atomically persist private analysis snapshots below one workflow root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.directory = self.root / "automacao" / "analises"
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_payload(value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping) or value.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError("snapshot de análise inválido")
        analysis_id = value.get("analysis_id")
        if not isinstance(analysis_id, str) or not _ANALYSIS_ID_RE.fullmatch(analysis_id):
            raise ValueError("analysis_id inválido")
        canonical_json = value.get("canonical_json")
        dataset_sha256 = value.get("dataset_sha256")
        if not isinstance(canonical_json, str) or not isinstance(dataset_sha256, str):
            raise ValueError("hash do snapshot ausente")
        actual_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        if actual_hash != dataset_sha256 or f"analysis-{actual_hash[:24]}" != analysis_id:
            raise ValueError("snapshot de análise adulterado")
        if not isinstance(value.get("queue"), list) or not isinstance(value.get("blocked"), list):
            raise ValueError("fila congelada inválida")
        if value.get("preview") is not None and not isinstance(value.get("preview"), Mapping):
            raise ValueError("prévia ausente")
        return deepcopy(dict(value))

    @staticmethod
    def _write_atomic(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def save(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._validate_payload(snapshot)
        path = _analysis_path(self.root, payload["analysis_id"])
        if path.exists():
            existing = self.load(payload["analysis_id"])
            if _canonical_json(existing) != _canonical_json(payload):
                raise ValueError("analysis_id já existe com conteúdo diferente")
            return existing
        self._write_atomic(path, payload)
        return deepcopy(payload)

    def load(self, analysis_id: str) -> dict[str, Any]:
        path = _analysis_path(self.root, analysis_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("snapshot de análise não encontrado ou inválido") from exc
        return self._validate_payload(value)

    def create_lots(self, analysis_id: str) -> dict[str, Any]:
        snapshot = self.load(analysis_id)
        existing_lots = snapshot.get("lots")
        if existing_lots is not None:
            if not isinstance(existing_lots, list):
                raise ValueError("lotes persistidos inválidos")
            return snapshot
        spec = snapshot.get("spec")
        if not isinstance(spec, Mapping) or not isinstance(spec.get("lot_size"), int):
            raise ValueError("tamanho de lote ausente")
        snapshot["lots"] = split_lots(snapshot["queue"], spec["lot_size"])
        self._write_atomic(_analysis_path(self.root, analysis_id), snapshot)
        return deepcopy(snapshot)
