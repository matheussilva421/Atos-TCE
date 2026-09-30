#!/usr/bin/env python
"""Aggregate, sanitized reliability report for one capability.

Only aggregate counts, result codes and timings leave the ledger. The ledger
itself holds no raw identity, and this reader never copies free text from it.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.area_restrita.reliability import (  # noqa: E402 - after sys.path
    CAPABILITIES,
    EVENTS_FILENAME,
    RELIABILITY_DIRNAME,
)


def read_runs(events_path: Path) -> list[dict]:
    """Group the append-only ledger into ordered runs."""

    if not events_path.is_file():
        return []
    runs: dict[str, dict] = {}
    order: list[str] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        event = json.loads(text)
        run_id = str(event.get("run_id") or "")
        kind = event.get("type")
        if kind == "run_start":
            if run_id and run_id not in runs:
                order.append(run_id)
            runs[run_id] = {
                "capability": str(event.get("capability") or ""),
                "environment": str(event.get("environment") or ""),
                "build_id": str(event.get("build_id") or ""),
                "started": float(event.get("ts") or 0.0),
                "finished": None,
                "passed": None,
                "result_code": None,
                "intervened": False,
                "codes": [],
            }
            continue
        run = runs.get(run_id)
        if run is None:
            continue
        if kind == "run_finished":
            run["passed"] = bool(event.get("passed"))
            run["result_code"] = str(event.get("result_code") or "UNKNOWN")
            run["finished"] = float(event.get("ts") or 0.0)
        elif kind == "intervention":
            run["intervened"] = True
        elif kind == "transition":
            run["codes"].append(str(event.get("result_code") or "UNKNOWN"))
    return [runs[run_id] for run_id in order]


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile: deterministic and easy to justify."""

    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(fraction * len(ordered))))
    return ordered[rank - 1]


def build_report(
    *, data_root: str, capability: str, build: str | None = None
) -> dict:
    events_path = Path(data_root) / RELIABILITY_DIRNAME / EVENTS_FILENAME
    runs = [run for run in read_runs(events_path) if run["capability"] == capability]
    if build is not None:
        runs = [run for run in runs if run["build_id"] == build]

    durations = [
        round((run["finished"] - run["started"]) * 1000)
        for run in runs
        if run["finished"] is not None and run["finished"] >= run["started"]
    ]
    outcome_codes: dict[str, int] = {}
    for run in runs:
        code = str(run["result_code"] or "UNFINISHED")
        outcome_codes[code] = outcome_codes.get(code, 0) + 1
    boundary_codes: dict[str, int] = {}
    for run in runs:
        for code in run["codes"]:
            boundary_codes[code] = boundary_codes.get(code, 0) + 1

    return {
        "capability": capability,
        "build": build,
        "attempts": len(runs),
        "passed": sum(1 for run in runs if run["passed"] is True),
        "failed": sum(1 for run in runs if run["passed"] is False),
        "interventions": sum(1 for run in runs if run["intervened"]),
        "median_ms": statistics.median(durations) if durations else None,
        "p95_ms": percentile(durations, 0.95),
        "outcome_codes": dict(sorted(outcome_codes.items())),
        "boundary_codes": dict(sorted(boundary_codes.items())),
    }


def render_markdown(report: dict) -> str:
    rows = [
        ("capability", report["capability"]),
        ("build", report["build"] or "(todos)"),
        ("tentativas", report["attempts"]),
        ("sucesso", report["passed"]),
        ("falhas", report["failed"]),
        ("intervenções", report["interventions"]),
        ("mediana_ms", report["median_ms"]),
        ("p95_ms", report["p95_ms"]),
    ]
    lines = ["| métrica | valor |", "|---|---:|"]
    for label, value in rows:
        lines.append(f"| {label} | {value} |")
    for title, codes in (("result_code", report["outcome_codes"]), ("boundary", report["boundary_codes"])):
        for code, count in codes.items():
            lines.append(f"| {title}:{code} | {count} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--capability", required=True, choices=CAPABILITIES)
    parser.add_argument("--build", default=None)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)

    report = build_report(
        data_root=args.data_root, capability=args.capability, build=args.build
    )
    if args.format == "markdown":
        print(render_markdown(report))
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

