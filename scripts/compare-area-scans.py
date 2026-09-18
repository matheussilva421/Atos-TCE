#!/usr/bin/env python
r"""Read-only comparison between two Área Restrita scans (M2 real gate).

The supervised M2 gate compares the CDP fallback scan with the scan produced by
the thin extension on the same marker. This tool loads both sides — the CDP
payload from its JSON file and the Mesa side from either a JSON export or the
SQLite store — and reports the divergences: rows that only one side saw,
classification or act-id mismatches, and a different scope or marker. It never
connects to the portal, never writes to the store and never types credentials.

    powershell.exe -File scripts\scan-area-cdp.ps1 -Output data\logs\area-cdp.json
    python scripts/compare-area-scans.py --cdp-json data\logs\area-cdp.json --db data\atos-tce.db
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.area_restrita import AREA_CLASSIFICATIONS  # noqa: E402
from app.core.store import Store  # noqa: E402


class ComparisonError(RuntimeError):
    """Raised when one of the two scans cannot be read."""


def _row_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("process_key") or "").strip(),
        str(row.get("interested_normalized") or "").strip().lower(),
    )


def _marker_of(payload: Mapping[str, Any]) -> dict[str, str]:
    marker = payload.get("marker")
    if isinstance(marker, Mapping):
        return {
            "label": str(marker.get("label") or ""),
            "value": str(marker.get("value") or ""),
        }
    return {
        "label": str(payload.get("marker_label") or ""),
        "value": str(payload.get("marker_value") or ""),
    }


def normalize_scan(payload: Mapping[str, Any], *, rows_field: str) -> dict[str, Any]:
    """Reduce one scan payload to what the gate compares."""

    rows = payload.get(rows_field)
    if not isinstance(rows, list):
        raise ComparisonError(f"payload sem lista '{rows_field}'")
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = _row_key(row)
        if not key[0]:
            continue
        indexed[key] = {
            "process_key": key[0],
            "interested_normalized": key[1],
            "classification": str(row.get("classification") or ""),
            "portal_act_id": (
                str(row.get("portal_act_id")) if row.get("portal_act_id") is not None else None
            ),
        }
    return {
        "scope": str(payload.get("source_scope") or ""),
        "marker": _marker_of(payload),
        "origin": str(payload.get("origin") or ""),
        "rows": indexed,
    }


def _counts(rows: Mapping[tuple[str, str], Mapping[str, Any]]) -> dict[str, int]:
    counts = {name: 0 for name in AREA_CLASSIFICATIONS}
    counts["total"] = 0
    counts["outras_classificacoes"] = 0
    for row in rows.values():
        counts["total"] += 1
        classification = str(row.get("classification") or "")
        if classification in AREA_CLASSIFICATIONS:
            counts[classification] += 1
        else:
            counts["outras_classificacoes"] += 1
    return counts


def compare_scans(cdp_payload: Mapping[str, Any], mesa_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the CDP scan against the Mesa scan, row by row."""

    cdp = normalize_scan(cdp_payload, rows_field="rows")
    mesa = normalize_scan(mesa_payload, rows_field="items")

    only_in_cdp = [
        {"process_key": key[0], "interested_normalized": key[1]}
        for key in sorted(set(cdp["rows"]) - set(mesa["rows"]))
    ]
    only_in_mesa = [
        {"process_key": key[0], "interested_normalized": key[1]}
        for key in sorted(set(mesa["rows"]) - set(cdp["rows"]))
    ]

    classification_mismatches = []
    act_id_mismatches = []
    for key in sorted(set(cdp["rows"]) & set(mesa["rows"])):
        left = cdp["rows"][key]
        right = mesa["rows"][key]
        if left["classification"] != right["classification"]:
            classification_mismatches.append(
                {
                    "process_key": key[0],
                    "interested_normalized": key[1],
                    "cdp": left["classification"],
                    "mesa": right["classification"],
                }
            )
        if left["portal_act_id"] != right["portal_act_id"]:
            act_id_mismatches.append(
                {
                    "process_key": key[0],
                    "cdp": left["portal_act_id"],
                    "mesa": right["portal_act_id"],
                }
            )

    context_differences = []
    if cdp["scope"] != mesa["scope"]:
        context_differences.append("source_scope")
    if cdp["marker"] != mesa["marker"]:
        context_differences.append("marker")

    return {
        "origins": {"cdp": cdp["origin"], "mesa": mesa["origin"]},
        "scope": {"cdp": cdp["scope"], "mesa": mesa["scope"]},
        "marker": {"cdp": cdp["marker"], "mesa": mesa["marker"]},
        "counts": {"cdp": _counts(cdp["rows"]), "mesa": _counts(mesa["rows"])},
        "only_in_cdp": only_in_cdp,
        "only_in_mesa": only_in_mesa,
        "classification_mismatches": classification_mismatches,
        "act_id_mismatches": act_id_mismatches,
        "context_differences": context_differences,
        "equal": not (
            only_in_cdp
            or only_in_mesa
            or classification_mismatches
            or act_id_mismatches
            or context_differences
        ),
    }


def read_scan_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ComparisonError(f"arquivo de varredura ausente: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ComparisonError(f"varredura ilegível ({source}): {error}") from error
    if not isinstance(payload, dict):
        raise ComparisonError(f"varredura sem objeto JSON: {source}")
    return payload


def mesa_scan_from_database(database: str | Path, scan_id: int | None) -> dict[str, Any]:
    path = Path(database)
    if not path.is_file():
        # A read-only comparison must never create a database by accident.
        raise ComparisonError(f"banco da Mesa ausente: {path}")
    store = Store.open(path)
    try:
        scan = store.get_area_scan(scan_id) if scan_id is not None else store.latest_area_scan()
    finally:
        store.close()
    if scan is None:
        raise ComparisonError(
            f"nenhuma varredura da Mesa encontrada em {database}"
            + (f" com id {scan_id}" if scan_id is not None else "")
        )
    return scan


def compare_with_database(
    cdp_payload: Mapping[str, Any], database: str | Path, scan_id: int | None = None
) -> dict[str, Any]:
    """Compare the CDP scan against one persisted Mesa scan."""

    return compare_scans(cdp_payload, mesa_scan_from_database(database, scan_id))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--cdp-json", type=Path, required=True, help="payload emitted by scripts/scan-area-cdp.ps1")
    parser.add_argument("--mesa-json", type=Path, default=None, help="Mesa scan exported as JSON")
    parser.add_argument("--db", type=Path, default=None, help="Mesa database with area_scans")
    parser.add_argument("--scan-id", type=int, default=None, help="scan id (default: the latest one)")
    parser.add_argument("--json", type=Path, default=None, help="also write the report to this file")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - host stream dependent
                pass
    args = build_parser().parse_args(argv)
    if args.mesa_json is None and args.db is None:
        print(json.dumps({"error": "informe --mesa-json ou --db"}), file=sys.stderr)
        return 2
    try:
        cdp_payload = read_scan_json(args.cdp_json)
        if args.mesa_json is not None:
            report = compare_scans(cdp_payload, read_scan_json(args.mesa_json))
        else:
            report = compare_with_database(cdp_payload, args.db, args.scan_id)
    except ComparisonError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
