"""Materialize a complete v3 Area Restrita snapshot from sanitized evidence.

This adapter is intentionally browser-free.  It is used when a live, sanitized
Area Restrita photograph was captured outside the local service and must be
joined back to the authoritative XLSX manifest before acquisition resumes.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

try:
    from .analysis_preview import AnalysisPreviewStore, create_preview
    from .batch_scope import split_lots
except ImportError:  # direct script-compatible import in the portable package
    from analysis_preview import AnalysisPreviewStore, create_preview
    from batch_scope import split_lots


AREA_CLASSIFICATIONS = frozenset(
    {
        "PRECISA_COMPLEMENTAR",
        "ATO_COMPLEMENTADO",
        "NAO_ENCONTRADO_AREA_RESTRITA",
        "AMBIGUO",
        "BLOQUEADO",
    }
)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} deve ser texto não vazio")
    return value.strip()


def _marker(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"label", "value"}:
        raise ValueError("marker deve conter exatamente label e value")
    return {"label": _require_text(value["label"], "marker.label"), "value": _require_text(value["value"], "marker.value")}


def materialize_analysis(
    input_manifest: Mapping[str, Any],
    area_snapshot: Mapping[str, Any],
    *,
    lot_size: int = 300,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Join input order with sanitized Area Restrita evidence and freeze lots."""

    if type(lot_size) is not int or not 1 <= lot_size <= 300:
        raise ValueError("lot_size deve ser inteiro entre 1 e 300")
    if not isinstance(input_manifest, Mapping) or not isinstance(input_manifest.get("rows"), list):
        raise ValueError("manifesto da lista inválido")
    if not isinstance(area_snapshot, Mapping) or not isinstance(area_snapshot.get("rows"), list):
        raise ValueError("fotografia da Área Restrita inválida")
    marker = _marker(area_snapshot.get("marker"))
    source_scope = _require_text(area_snapshot.get("source_scope"), "source_scope")
    if source_scope != "sector_finalistic":
        raise ValueError("source_scope da fotografia deve ser sector_finalistic")

    area_by_key: dict[str, Mapping[str, Any]] = {}
    for raw in area_snapshot["rows"]:
        if not isinstance(raw, Mapping):
            raise ValueError("linha da fotografia inválida")
        key = _require_text(raw.get("process_key"), "area.process_key")
        if key in area_by_key:
            raise ValueError(f"processo duplicado na fotografia: {key}")
        classification = raw.get("area_classification")
        if classification not in AREA_CLASSIFICATIONS:
            raise ValueError(f"classificação inválida na fotografia: {key}")
        area_by_key[key] = raw

    unique_rows: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for raw in input_manifest["rows"]:
        if not isinstance(raw, Mapping):
            raise ValueError("linha do manifesto inválida")
        key = _require_text(raw.get("process_key"), "input.process_key")
        source_row = raw.get("source_row")
        if type(source_row) is not int or source_row < 1:
            raise ValueError(f"source_row inválida: {key}")
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(raw)

    observations: list[dict[str, Any]] = []
    for raw_input in unique_rows:
        key = str(raw_input["process_key"])
        observed = area_by_key.get(key)
        if observed is None:
            classification = "NAO_ENCONTRADO_AREA_RESTRITA"
            interested_key = None
            action = None
            signature = None
            area_page = None
        else:
            classification = str(observed["area_classification"])
            interested_key = observed.get("interested_key")
            if interested_key is not None:
                interested_key = _require_text(interested_key, f"interested_key {key}")
            action = observed.get("action_observed")
            if action is not None:
                action = _require_text(action, f"action_observed {key}")
            signature = observed.get("action_signature")
            if signature is not None:
                if not isinstance(signature, Mapping) or set(signature) != {"kind", "alt", "title", "src"}:
                    raise ValueError(f"assinatura inválida na fotografia: {key}")
                signature = {name: str(signature.get(name, "")) for name in ("kind", "alt", "title", "src")}
            area_page = observed.get("area_page")

        area_evidence = {
            "process_key": key,
            "interested_key": interested_key,
            "area_classification": classification,
            "action_observed": action,
            "action_signature": signature,
            "area_page": area_page,
        }
        observations.append(
            {
                "process_key": key,
                "interested_key": interested_key,
                "area_restrita": {
                    "scope": source_scope,
                    "marker_label": marker["label"],
                    "marker_value": marker["value"],
                    "classification": classification,
                    "needs_complement": classification == "PRECISA_COMPLEMENTAR",
                    "action_observed": action,
                    "action_signature": signature,
                    "snapshot_hash": _sha256(area_evidence),
                },
                "econtas": {
                    "match": "exact",
                    "documents": [],
                    "snapshot_hash": None,
                    "ocr_status": "not_run",
                },
                "input_row": int(raw_input["source_row"]),
                "state": "discovered",
            }
        )

    if not observations:
        raise ValueError("manifesto sem processos únicos")
    input_list_id = _require_text(input_manifest.get("input_list_id"), "input_list_id")
    input_sha256 = _require_text(input_manifest.get("input_sha256"), "input_sha256")
    input_unique_count = input_manifest.get("unique_count")
    if type(input_unique_count) is not int or input_unique_count != len(observations):
        raise ValueError("unique_count do manifesto não confere com as linhas únicas")
    spec = {
        "schema_version": 3,
        "source_scope": source_scope,
        "marker": marker,
        "acquisition_source": "econtas",
        "lot_size": lot_size,
        "analysis_only": True,
        "auto_prepare": False,
        "auto_submit": False,
        "dataset_sha256": None,
        "area_snapshot_sha256": _sha256({"source_scope": source_scope, "marker": marker, "rows": area_snapshot["rows"]}),
        "input_list_id": input_list_id,
        "input_sha256": input_sha256,
        "input_unique_count": input_unique_count,
    }
    snapshot = create_preview(
        Path("."),
        spec,
        observations,
        observed_at or datetime.now(timezone.utc).isoformat(),
    )
    snapshot["rows"] = observations
    snapshot["area_snapshot"] = {
        "source_scope": source_scope,
        "marker": marker,
        "row_count": len(area_snapshot["rows"]),
        "sha256": spec["area_snapshot_sha256"],
    }
    snapshot["lots"] = split_lots(snapshot["queue"], lot_size)
    return snapshot


def _read_json(path: str) -> dict[str, Any]:
    if path == "-":
        value = json.load(sys.stdin)
    else:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON deve ser objeto: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-list", required=True)
    parser.add_argument("--area-snapshot", required=True, help="JSON ou - para ler a fotografia pelo stdin")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--lot-size", type=int, default=300)
    parser.add_argument("--observed-at")
    args = parser.parse_args()
    snapshot = materialize_analysis(
        _read_json(args.input_list),
        _read_json(args.area_snapshot),
        lot_size=args.lot_size,
        observed_at=args.observed_at,
    )
    saved = AnalysisPreviewStore(args.output_root).save(snapshot)
    print(json.dumps({
        "analysis_id": saved["analysis_id"],
        "rows": len(saved["rows"]),
        "queue": len(saved["queue"]),
        "blocked": len(saved["blocked"]),
        "lots": [{"lot_number": lot["lot_number"], "items": len(lot["items"])} for lot in saved["lots"]],
        "area_snapshot_sha256": saved["spec"]["area_snapshot_sha256"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
