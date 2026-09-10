"""Reconcile the first real batch's process and interested-party records."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import unicodedata
from typing import Any, Mapping


REQUIRED_FIELDS = (
    "modalidade",
    "fundamento_legal",
    "data_publicacao_doe",
    "cargo",
    "matricula",
    "data_nascimento",
)
OPTIONAL_FIELDS = ("genero",)
DEFAULT_SOURCE = (
    Path(__file__).resolve().parent
    / "outputs"
    / "live-real-fase11h-sector-lot50"
    / "publicacoes"
    / "120"
    / "resultados.json"
)


def _normalise_identity(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.casefold().split())


def _field_is_present(evidence: object) -> bool:
    if not isinstance(evidence, Mapping) or evidence.get("status") != "found":
        return False
    value = evidence.get("value")
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _validate_payload(payload: object) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("root JSON must be an object")
    results = payload.get("results")
    if not isinstance(results, Mapping):
        raise ValueError("root.results must be an object keyed by process")
    for process_key, result in results.items():
        if not isinstance(process_key, str) or not process_key:
            raise ValueError("each results key must be a non-empty process string")
        if not isinstance(result, Mapping):
            raise ValueError(f"result for {process_key!r} must be an object")
        blocks = result.get("blocks")
        if not isinstance(blocks, list):
            raise ValueError(f"result for {process_key!r} must contain a blocks list")
        for index, block in enumerate(blocks, 1):
            if not isinstance(block, Mapping):
                raise ValueError(f"block {process_key!r}#{index} must be an object")
            identity = block.get("interested")
            if not isinstance(identity, str) or not identity.strip():
                raise ValueError(f"block {process_key!r}#{index} lacks an interested identity")
            if not isinstance(block.get("fields"), Mapping):
                raise ValueError(f"block {process_key!r}#{index} must contain a fields object")
    return payload


def reconcile_payload(payload: object) -> dict[str, object]:
    """Return a deterministic, privacy-preserving reconciliation summary."""

    payload = _validate_payload(payload)
    results = payload["results"]
    ordered_results = sorted(results.items(), key=lambda item: item[0])
    records: list[dict[str, object]] = []
    process_record_counts: dict[str, int] = {}
    identity_values: list[str] = []
    identity_counts: dict[str, int] = {}
    combination_counts: Counter[tuple[str, ...]] = Counter()

    for process_key, result in ordered_results:
        blocks = result["blocks"]
        process_record_counts[process_key] = len(blocks)
        identity_counts[process_key] = len(blocks)
        for record_index, block in enumerate(blocks, 1):
            identity_values.append(_normalise_identity(block["interested"]))
            fields = block["fields"]
            missing_required = [
                field for field in REQUIRED_FIELDS if not _field_is_present(fields.get(field))
            ]
            missing_optional = [
                field for field in OPTIONAL_FIELDS if not _field_is_present(fields.get(field))
            ]
            ready = not missing_required
            combination = tuple(missing_required)
            combination_counts[combination] += 1
            records.append(
                {
                    "process_key": process_key,
                    "record_index": record_index,
                    "missing_required_fields": missing_required,
                    "missing_optional_fields": missing_optional,
                    "ready_for_preflight": ready,
                }
            )

    process_key_count = len(ordered_results)
    record_count = len(records)
    process_length_counts = Counter(process_record_counts.values())
    matrix = [
        {
            "ready_for_preflight": not blocked_fields,
            "blocked_fields": list(blocked_fields),
            "record_count": count,
        }
        for blocked_fields, count in sorted(combination_counts.items())
    ]

    return {
        "source_structure": {
            "root_type": "object",
            "root_keys": sorted(str(key) for key in payload),
            "results_container_type": "object",
            "result_entry_keys": sorted(
                {
                    str(key) for _, result in ordered_results for key in result
                }
            ),
            "block_entry_keys": sorted(
                {
                    str(key)
                    for _, result in ordered_results
                    for block in result["blocks"]
                    for key in block
                }
            ),
            "field_keys": sorted(
                {
                    str(key)
                    for _, result in ordered_results
                    for block in result["blocks"]
                    for key in block["fields"]
                }
            ),
        },
        "structure": {
            "process_key_count": process_key_count,
            "record_count": record_count,
            "records_per_process": process_record_counts,
            "processes_by_record_count": {
                str(record_total): process_length_counts[record_total]
                for record_total in sorted(process_length_counts)
            },
        },
        "counts": {
            "process_key_count": process_key_count,
            "interested_identity_count": record_count,
            "distinct_interested_identity_count": len(set(identity_values)),
            "records_per_process": process_record_counts,
            "identity_count_per_process": identity_counts,
        },
        "records": records,
        "preflight_matrix": matrix,
        "reconciliation": {
            "process_keys": process_key_count,
            "interested_records": record_count,
            "extra_records_over_processes": record_count - process_key_count,
            "processes_with_one_record": process_length_counts[1],
            "processes_with_two_records": process_length_counts[2],
        },
    }


def reconcile_file(source: Path) -> dict[str, object]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    return reconcile_payload(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args(argv)
    try:
        summary = reconcile_file(args.source)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
