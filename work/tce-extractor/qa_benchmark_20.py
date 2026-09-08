"""Reproducer for the 20-process benchmark gate.

This tool never contacts the portal and never invents missing observations.
It scaffolds a run for an explicitly supplied, exact 20-process sample,
validates timestamp/click/OCR evidence collected by an operator, and compares
two completed runs without mutating production code or the portable archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import statistics
import sys
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
PROCESS_SAMPLE_SIZE = 20
_PROCESS_KEY = re.compile(r"^\s*(\d+)\s*/\s*(\d{4})\s*$")
_TIMESTAMP_FIELDS = (
    "started_at",
    "first_result_at",
    "preparation_started_at",
    "preparation_finished_at",
    "human_comparison_started_at",
    "human_comparison_finished_at",
)


class BenchmarkValidationError(ValueError):
    """Raised when a benchmark input cannot support a measured claim."""


@dataclass(frozen=True)
class LoadedRun:
    path: Path
    data: dict[str, Any]
    process_keys: tuple[str, ...]
    metrics: dict[str, dict[str, Any]]


class BenchmarkContractTests(unittest.TestCase):
    def test_process_sample_must_contain_exactly_twenty_unique_keys(self) -> None:
        with self.assertRaises(BenchmarkValidationError):
            validate_process_keys(["103439/2023"])

    def test_timestamp_metrics_are_derived_only_from_explicit_timestamps(self) -> None:
        metrics = derive_process_metrics(
            {
                "started_at": "2026-09-08T10:00:00-03:00",
                "first_result_at": "2026-09-08T10:00:12-03:00",
                "preparation_started_at": "2026-09-08T10:00:00-03:00",
                "preparation_finished_at": "2026-09-08T10:01:00-03:00",
                "human_comparison_started_at": "2026-09-08T10:01:00-03:00",
                "human_comparison_finished_at": "2026-09-08T10:01:20-03:00",
                "ocr_reused": False,
                "clicks_total": 3,
                "sync_samples_seconds": [0.5, 1.0],
            }
        )
        self.assertEqual(metrics["first_result_seconds"], 12.0)
        self.assertEqual(metrics["preparation_seconds"], 60.0)
        self.assertEqual(metrics["human_comparison_seconds"], 20.0)

    def test_percentile_is_not_reported_without_observations(self) -> None:
        with self.assertRaises(BenchmarkValidationError):
            summarize_values([])

    def test_completed_runs_must_use_the_same_ordered_sample(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_path = root / "baseline.json"
            candidate_path = root / "candidate.json"
            baseline_path.write_text(json.dumps(_test_run("baseline")), encoding="utf-8")
            candidate_payload = _test_run("portable-progressive")
            candidate_payload["processes"] = list(reversed(candidate_payload["processes"]))
            candidate_path.write_text(json.dumps(candidate_payload), encoding="utf-8")
            baseline = load_completed_run(baseline_path)
            candidate = load_completed_run(candidate_path)
            with self.assertRaises(BenchmarkValidationError):
                compare_runs(baseline, candidate)

    def test_scaffold_is_explicitly_not_measured(self) -> None:
        keys = [f"{103400 + index}/{2023}" for index in range(PROCESS_SAMPLE_SIZE)]
        payload = scaffold_run(keys, "baseline", "not-run", None)
        self.assertEqual(payload["status"], "template")
        self.assertEqual(payload["sample"]["count"], PROCESS_SAMPLE_SIZE)
        self.assertIsNone(payload["processes"][0]["observations"]["first_result_at"])


def canonical_process_key(value: object) -> str:
    """Return the repository's number/year spelling or reject the value."""

    if isinstance(value, Mapping):
        if "process_key" in value:
            value = value["process_key"]
        elif "process" in value:
            value = value["process"]
        elif "key" in value:
            value = value["key"]
        elif "number" in value and "year" in value:
            value = f"{value['number']}/{value['year']}"
    if not isinstance(value, str):
        raise BenchmarkValidationError(f"process key must be text, got {type(value).__name__}")
    match = _PROCESS_KEY.fullmatch(value)
    if match is None:
        raise BenchmarkValidationError(f"invalid process key: {value!r}")
    return f"{int(match.group(1))}/{match.group(2)}"


def validate_process_keys(values: Sequence[object]) -> tuple[str, ...]:
    """Validate an explicit ordered sample of exactly twenty unique processes."""

    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise BenchmarkValidationError("process sample must be an ordered JSON list")
    keys = tuple(canonical_process_key(value) for value in values)
    if len(keys) != PROCESS_SAMPLE_SIZE:
        raise BenchmarkValidationError(
            f"expected exactly {PROCESS_SAMPLE_SIZE} processes, received {len(keys)}"
        )
    if len(set(keys)) != len(keys):
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        raise BenchmarkValidationError("duplicate process keys: " + ", ".join(duplicates))
    return keys


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as error:
        raise BenchmarkValidationError(f"input file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise BenchmarkValidationError(f"invalid JSON in {path}: {error}") from error


def load_process_list(path: Path) -> tuple[str, ...]:
    """Load only an explicit process list; never select the first twenty implicitly."""

    payload = _read_json(path)
    values: Any = payload
    if isinstance(payload, Mapping):
        for field in ("process_keys", "processes", "order"):
            if field in payload:
                values = payload[field]
                break
        else:
            raise BenchmarkValidationError(
                f"{path} must contain process_keys, processes, or order"
            )
    if not isinstance(values, list):
        raise BenchmarkValidationError(f"{path} does not contain a JSON list")
    return validate_process_keys(values)


def _parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkValidationError(f"{field} is required and must be an ISO timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise BenchmarkValidationError(f"{field} is not a valid ISO timestamp: {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BenchmarkValidationError(f"{field} must include a timezone offset")
    return parsed


def _seconds_between(later: datetime, earlier: datetime, field: str) -> float:
    seconds = (later - earlier).total_seconds()
    if seconds < 0:
        raise BenchmarkValidationError(f"{field} is earlier than its start timestamp")
    return round(seconds, 6)


def _observations(entry: Mapping[str, Any]) -> dict[str, Any]:
    observations: dict[str, Any] = {}
    for container_name in ("observations", "metrics"):
        container = entry.get(container_name)
        if container is not None:
            if not isinstance(container, Mapping):
                raise BenchmarkValidationError(f"{container_name} must be an object")
            observations.update(container)
    observations.update({key: entry[key] for key in _TIMESTAMP_FIELDS if key in entry})
    for key in ("ocr_reused", "clicks_total", "sync_samples_seconds"):
        if key in entry:
            observations[key] = entry[key]
    if "clicks" in entry and "clicks_total" not in observations:
        clicks = entry["clicks"]
        if isinstance(clicks, Mapping):
            observations["clicks_total"] = clicks.get("total")
        else:
            observations["clicks_total"] = clicks
    return observations


def derive_process_metrics(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Derive durations only from explicit operator-captured timestamps."""

    timestamps = {
        field: _parse_timestamp(observation.get(field), field)
        for field in _TIMESTAMP_FIELDS
    }
    if timestamps["first_result_at"] < timestamps["started_at"]:
        raise BenchmarkValidationError("first_result_at is earlier than started_at")
    first_result_seconds = _seconds_between(
        timestamps["first_result_at"], timestamps["started_at"], "first_result_at"
    )
    preparation_seconds = _seconds_between(
        timestamps["preparation_finished_at"],
        timestamps["preparation_started_at"],
        "preparation_finished_at",
    )
    human_comparison_seconds = _seconds_between(
        timestamps["human_comparison_finished_at"],
        timestamps["human_comparison_started_at"],
        "human_comparison_finished_at",
    )
    total_until_preparation_seconds = _seconds_between(
        timestamps["preparation_finished_at"], timestamps["started_at"], "preparation_finished_at"
    )

    ocr_reused = observation.get("ocr_reused")
    if type(ocr_reused) is not bool:
        raise BenchmarkValidationError("ocr_reused must be an explicit boolean")

    clicks_total = observation.get("clicks_total")
    if isinstance(clicks_total, bool) or not isinstance(clicks_total, int) or clicks_total < 0:
        raise BenchmarkValidationError("clicks_total must be an explicit non-negative integer")

    sync_values = observation.get("sync_samples_seconds")
    if not isinstance(sync_values, list) or not sync_values:
        raise BenchmarkValidationError(
            "sync_samples_seconds must contain at least one measured sample"
        )
    sync_samples: list[float] = []
    for index, value in enumerate(sync_values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BenchmarkValidationError(f"sync sample {index} must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0:
            raise BenchmarkValidationError(f"sync sample {index} must be finite and non-negative")
        sync_samples.append(round(numeric, 6))

    return {
        "first_result_seconds": first_result_seconds,
        "preparation_seconds": preparation_seconds,
        "human_comparison_seconds": human_comparison_seconds,
        "total_until_preparation_seconds": total_until_preparation_seconds,
        "ocr_reused": ocr_reused,
        "clicks_total": clicks_total,
        "sync_samples_seconds": sync_samples,
    }


def _process_key_from_entry(entry: Mapping[str, Any]) -> str:
    for field in ("process_key", "process", "key"):
        if field in entry:
            return canonical_process_key(entry[field])
    raise BenchmarkValidationError("each process entry needs process_key")


def _require_environment(data: Mapping[str, Any]) -> None:
    environment = data.get("environment")
    if not isinstance(environment, Mapping):
        raise BenchmarkValidationError("environment is required")
    network = environment.get("network")
    if not isinstance(network, str) or not network.strip():
        raise BenchmarkValidationError(
            "environment.network must record the observed network or an explicit block"
        )
    hardware = environment.get("hardware")
    if not isinstance(hardware, Mapping) or not hardware:
        raise BenchmarkValidationError("environment.hardware must record observed hardware")


def load_completed_run(path: Path) -> LoadedRun:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise BenchmarkValidationError(f"{path} must contain a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise BenchmarkValidationError(f"{path} has unsupported schema_version")
    if payload.get("kind") != "tce-benchmark-20":
        raise BenchmarkValidationError(f"{path} is not a tce-benchmark-20 run")
    if payload.get("status") != "complete":
        raise BenchmarkValidationError(
            f"{path} is not complete; status must be 'complete' after real observations are recorded"
        )
    mode = payload.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        raise BenchmarkValidationError(f"{path} has no benchmark mode")
    _require_environment(payload)
    entries = payload.get("processes")
    if not isinstance(entries, list):
        raise BenchmarkValidationError(f"{path}.processes must be a list")
    keys = validate_process_keys([_process_key_from_entry(entry) for entry in entries if isinstance(entry, Mapping)])
    if len(entries) != len(keys):
        raise BenchmarkValidationError(f"{path}.processes contains a non-object entry")
    metrics: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise BenchmarkValidationError(f"{path}.processes contains a non-object entry")
        key = _process_key_from_entry(entry)
        if key in metrics:
            raise BenchmarkValidationError(f"duplicate process entry: {key}")
        metrics[key] = derive_process_metrics(_observations(entry))
    return LoadedRun(path=path, data=payload, process_keys=keys, metrics=metrics)


def summarize_values(values: Sequence[float | int]) -> dict[str, float | int]:
    if not values:
        raise BenchmarkValidationError("cannot summarize an empty set of measured values")
    numeric = [float(value) for value in values]
    if any(not math.isfinite(value) for value in numeric):
        raise BenchmarkValidationError("cannot summarize non-finite values")
    if len(numeric) == 1:
        p95 = numeric[0]
    else:
        p95 = statistics.quantiles(numeric, n=100, method="inclusive")[94]
    return {
        "count": len(numeric),
        "min": round(min(numeric), 6),
        "median": round(statistics.median(numeric), 6),
        "p95": round(p95, 6),
        "max": round(max(numeric), 6),
    }


def _order_hash(keys: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def _metric_values(run: LoadedRun, field: str) -> list[float | int]:
    return [run.metrics[key][field] for key in run.process_keys]


def _delta(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, float | None]:
    difference = round(float(candidate["median"]) - float(baseline["median"]), 6)
    baseline_median = float(baseline["median"])
    percentage = None if baseline_median == 0 else round(difference / baseline_median * 100, 6)
    return {"candidate_minus_baseline_median": difference, "percent_of_baseline_median": percentage}


def compare_runs(
    baseline: LoadedRun | Mapping[str, Any],
    candidate: LoadedRun | Mapping[str, Any],
    *,
    include_process_keys: bool = False,
) -> dict[str, Any]:
    """Compare two already-complete runs over the exact same ordered sample."""

    if not isinstance(baseline, LoadedRun) or not isinstance(candidate, LoadedRun):
        raise BenchmarkValidationError("compare_runs requires loaded completed runs")
    if baseline.process_keys != candidate.process_keys:
        raise BenchmarkValidationError(
            "baseline and candidate must use the same 20 processes in the same order"
        )

    metric_fields = (
        "first_result_seconds",
        "preparation_seconds",
        "total_until_preparation_seconds",
        "human_comparison_seconds",
        "clicks_total",
    )
    metrics: dict[str, Any] = {}
    for field in metric_fields:
        baseline_summary = summarize_values(_metric_values(baseline, field))
        candidate_summary = summarize_values(_metric_values(candidate, field))
        metrics[field] = {
            "baseline": baseline_summary,
            "candidate": candidate_summary,
            "delta": _delta(candidate_summary, baseline_summary),
        }

    baseline_sync = [
        value
        for key in baseline.process_keys
        for value in baseline.metrics[key]["sync_samples_seconds"]
    ]
    candidate_sync = [
        value
        for key in candidate.process_keys
        for value in candidate.metrics[key]["sync_samples_seconds"]
    ]
    baseline_sync_summary = summarize_values(baseline_sync)
    candidate_sync_summary = summarize_values(candidate_sync)
    metrics["sync_seconds"] = {
        "baseline": baseline_sync_summary,
        "candidate": candidate_sync_summary,
        "delta": _delta(candidate_sync_summary, baseline_sync_summary),
    }

    baseline_ocr = sum(bool(baseline.metrics[key]["ocr_reused"]) for key in baseline.process_keys)
    candidate_ocr = sum(bool(candidate.metrics[key]["ocr_reused"]) for key in candidate.process_keys)
    metrics["ocr_reused"] = {
        "baseline_count": baseline_ocr,
        "candidate_count": candidate_ocr,
        "sample_size": PROCESS_SAMPLE_SIZE,
    }
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "tce-benchmark-20-summary",
        "status": "measured",
        "sample": {
            "count": PROCESS_SAMPLE_SIZE,
            "ordered_process_sha256": _order_hash(baseline.process_keys),
        },
        "runs": {
            "baseline": {"path": str(baseline.path), "mode": baseline.data["mode"]},
            "candidate": {"path": str(candidate.path), "mode": candidate.data["mode"]},
        },
        "metrics": metrics,
        "measurement_boundary": {
            "durations": "derived from recorded timezone-aware timestamps",
            "clicks": "accepted only from explicit per-process counts",
            "ocr_reuse": "accepted only from explicit per-process booleans",
            "missing_data": "rejected; no baseline, OCR result, or time is fabricated",
        },
    }
    if include_process_keys:
        result["sample"]["process_keys"] = list(baseline.process_keys)
    return result


def _memory_bytes() -> int | None:
    if os.name != "nt":
        return None
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_physical)
    except (AttributeError, OSError, TypeError):
        return None
    return None


def collect_environment(network: str) -> dict[str, Any]:
    """Record local facts and require the operator to label the observed network."""

    if not network.strip():
        raise BenchmarkValidationError("--network must describe the observed network or block")
    return {
        "hardware": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor() or None,
            "logical_cpu_count": os.cpu_count(),
            "memory_bytes": _memory_bytes(),
        },
        "network": network.strip(),
        "python": platform.python_version(),
    }


def scaffold_run(process_keys: Sequence[str], mode: str, network: str, note: str | None) -> dict[str, Any]:
    keys = validate_process_keys(process_keys)
    if not mode.strip():
        raise BenchmarkValidationError("--mode must not be empty")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "tce-benchmark-20",
        "status": "template",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode.strip(),
        "source": "manual portal measurement; operator must record real observations",
        "environment": collect_environment(network),
        "sample": {
            "count": PROCESS_SAMPLE_SIZE,
            "ordered_process_sha256": _order_hash(keys),
            "process_list_is_explicit": True,
        },
        "processes": [
            {
                "process_key": key,
                "observations": {
                    "started_at": None,
                    "first_result_at": None,
                    "preparation_started_at": None,
                    "preparation_finished_at": None,
                    "human_comparison_started_at": None,
                    "human_comparison_finished_at": None,
                    "ocr_reused": None,
                    "clicks_total": None,
                    "sync_samples_seconds": [],
                },
            }
            for key in keys
        ],
        "operator_note": note,
        "instructions": {
            "complete_only_with": [
                "real portal events for these exact 20 processes",
                "timezone-aware timestamps captured at the declared boundaries",
                "explicit human comparison start/end and click counts",
                "explicit OCR reuse boolean; do not infer it from cache presence",
                "one or more measured synchronization samples per process",
            ],
            "before_validation": "change status to complete only after all observations are filled",
        },
    }


def _write_json(path: Path, payload: Mapping[str, Any], force: bool) -> None:
    if path.exists() and not force:
        raise BenchmarkValidationError(f"refusing to overwrite existing file: {path}; use --force")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _test_observation(offset: int = 0) -> dict[str, Any]:
    start = f"2026-09-08T10:{offset:02d}:00+00:00"
    first = f"2026-09-08T10:{offset:02d}:12+00:00"
    prep_end = f"2026-09-08T10:{offset + 1:02d}:00+00:00"
    human_end = f"2026-09-08T10:{offset + 1:02d}:20+00:00"
    return {
        "started_at": start,
        "first_result_at": first,
        "preparation_started_at": start,
        "preparation_finished_at": prep_end,
        "human_comparison_started_at": prep_end,
        "human_comparison_finished_at": human_end,
        "ocr_reused": False,
        "clicks_total": 3,
        "sync_samples_seconds": [0.5, 1.0],
    }


def _test_run(mode: str) -> dict[str, Any]:
    keys = tuple(f"{103400 + index}/{2023}" for index in range(PROCESS_SAMPLE_SIZE))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "tce-benchmark-20",
        "status": "complete",
        "mode": mode,
        "environment": {"network": "unit-test", "hardware": {"logical_cpu_count": 1}},
        "processes": [
            {"process_key": key, "observations": _test_observation(index)}
            for index, key in enumerate(keys)
        ],
    }


def _run_self_tests() -> int:
    result = unittest.main(module=__name__, argv=[__file__], exit=False)
    return 0 if result.result.wasSuccessful() else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run deterministic contract tests")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="write a non-measured run template")
    init_parser.add_argument("--process-list", type=Path, required=True)
    init_parser.add_argument("--mode", required=True)
    init_parser.add_argument("--network", required=True)
    init_parser.add_argument("--output", type=Path, required=True)
    init_parser.add_argument("--note")
    init_parser.add_argument("--force", action="store_true")

    validate_parser = subparsers.add_parser("validate", help="validate a completed measured run")
    validate_parser.add_argument("--run", type=Path, required=True)

    summary_parser = subparsers.add_parser("summarize", help="compare two complete runs")
    summary_parser.add_argument("--baseline", type=Path, required=True)
    summary_parser.add_argument("--candidate", type=Path, required=True)
    summary_parser.add_argument("--output", type=Path)
    summary_parser.add_argument("--include-process-keys", action="store_true")
    summary_parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _run_self_tests()
    try:
        if args.command == "init":
            keys = load_process_list(args.process_list)
            _write_json(args.output, scaffold_run(keys, args.mode, args.network, args.note), args.force)
            print(
                json.dumps(
                    {
                        "status": "template",
                        "output": str(args.output),
                        "process_count": len(keys),
                        "measured": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "validate":
            run = load_completed_run(args.run)
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "mode": run.data["mode"],
                        "process_count": len(run.process_keys),
                        "ordered_process_sha256": _order_hash(run.process_keys),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "summarize":
            baseline = load_completed_run(args.baseline)
            candidate = load_completed_run(args.candidate)
            summary = compare_runs(
                baseline,
                candidate,
                include_process_keys=args.include_process_keys,
            )
            if args.output is None:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            else:
                _write_json(args.output, summary, args.force)
                print(json.dumps({"status": "written", "output": str(args.output)}))
            return 0
        parser.print_help()
        return 2
    except (BenchmarkValidationError, OSError) as error:
        print(f"benchmark blocked: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
