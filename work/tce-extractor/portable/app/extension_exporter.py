"""Project an extraction checkpoint into the minimal extension dataset.

This module only reads the already-produced checkpoint.  It deliberately has
no PDF, OCR, browser, or network dependency.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Mapping
import unicodedata


ALLOWED_FIELDS = (
    "modalidade",
    "fundamento_legal",
    "data_publicacao_doe",
    "cargo",
    "matricula",
    "data_nascimento",
    "genero",
)

_PROCESS_RE = re.compile(r"^(\d+)\s*/\s*(\d{4})$")
_PRIVATE_KEYS = frozenset(
    {
        "cpf",
        "url",
        "cookie",
        "token",
        "session",
        "password",
        "absolute_path",
        "pdf_path",
    }
)
_UNSAFE_VALUE_PATTERNS = (
    re.compile(r"\b[a-z][a-z0-9+.-]*://", re.IGNORECASE),
    re.compile(r"\bwww\.", re.IGNORECASE),
    re.compile(r"(?:^|[\s\"'(])(?:[A-Za-z]:[\\/]|\\\\)"),
    re.compile(r"(?:^|[\s\"'(])/(?:[^/\s]+/)+[^/\s]+"),
    re.compile(
        r"(?:^|[\s\"'(])(?:[^\\/\s]+[\\/])+\S+\."
        r"(?:pdf|json|txt|docx?|xlsx?|png|jpe?g)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)"),
    re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    re.compile(r"\bbearer\s+\S+", re.IGNORECASE),
    re.compile(
        r"\b(?:cpf|token|cookie|session|password|senha)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"[\r\n]"),
)
_CIVIL_DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_FIELD_OUTPUT_KEYS = (
    "status",
    "confidence",
    "source_value",
    "form_value",
    "citation",
)
_DATASET_KEYS = ("schema_version", "generated_at", "batch", "records")
_BATCH_KEYS = (
    "id",
    "logical_sha256",
    "process_count",
    "record_count",
    "process_keys",
)
_PROCESS_KEYS = ("key", "number", "year")
_INTERESTED_KEYS = ("original", "normalized")


def _invalid(message: str) -> ValueError:
    return ValueError(f"invalid extension dataset: {message}")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _parse_process(value: object) -> tuple[str, str, str]:
    if not isinstance(value, str):
        raise ValueError("process key must be a string")
    match = _PROCESS_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid process key: {value!r}")
    number, year = match.groups()
    return f"{number}/{year}", number, year


def _normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_marks.casefold()).strip()


def _is_unsafe_value(value: str) -> bool:
    return len(value) > 512 or any(pattern.search(value) for pattern in _UNSAFE_VALUE_PATTERNS)


def _is_valid_civil_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    match = _CIVIL_DATE_RE.fullmatch(value)
    if match is None:
        return False
    day, month, year = (int(part) for part in match.groups())
    try:
        datetime(year, month, day)
    except ValueError:
        return False
    return True


def _missing_field() -> dict[str, object]:
    return {
        "status": "missing",
        "confidence": "none",
        "source_value": None,
        "form_value": None,
        "citation": None,
    }


def _safe_document_label(value: object) -> str | None:
    document = _string(value)
    if (
        not document
        or len(document) > 1024
        or "\r" in document
        or "\n" in document
        or re.search(r"\b[a-z][a-z0-9+.-]*://", document, re.IGNORECASE)
    ):
        return None
    components = document.replace("\\", "/").split("/")
    if ".." in components:
        return None
    basename = components[-1]
    if not basename or basename in {".", ".."} or ":" in basename:
        return None
    if _is_unsafe_value(basename):
        return None
    return basename


def _citation(evidence: Mapping[str, object]) -> dict[str, object] | None:
    process = _string(evidence.get("process"))
    event = _string(evidence.get("event"))
    page = evidence.get("page")
    if not process or not event or isinstance(page, bool) or not isinstance(page, int) or page <= 0:
        return None

    citation: dict[str, object] = {
        "process": process,
        "event": event,
        "page": page,
    }
    document = _safe_document_label(evidence.get("document"))
    if document is not None:
        citation["document"] = document
    return citation


def _has_complete_document_citation(
    citation: Mapping[str, object] | None,
    process_key: str,
) -> bool:
    return bool(
        citation
        and citation.get("process") == process_key
        and isinstance(citation.get("event"), str)
        and citation.get("event")
        and isinstance(citation.get("page"), int)
        and not isinstance(citation.get("page"), bool)
        and citation.get("page", 0) > 0
        and isinstance(citation.get("document"), str)
        and citation.get("document")
    )


def _project_field(
    evidence: Mapping[str, object] | None,
    *,
    field_name: str,
    process_key: str,
    candidates: bool,
) -> dict[str, object]:
    if evidence is None:
        return _missing_field()

    status = _string(evidence.get("status")) or "missing"
    confidence = _string(evidence.get("confidence")) or "none"
    value = _string(evidence.get("value"))
    raw_value = _string(evidence.get("raw_value"))
    if any(
        candidate is not None and _is_unsafe_value(candidate)
        for candidate in (value, raw_value)
    ):
        return _missing_field()

    citation = _citation(evidence)
    if field_name == "genero" and not (
        status == "found"
        and confidence == "high"
        and value is not None
        and _has_complete_document_citation(citation, process_key)
    ):
        return _missing_field()
    if field_name == "data_publicacao_doe" and status == "found" and not _is_valid_civil_date(value):
        return _missing_field()

    source_value = raw_value if raw_value is not None else value
    if status in {"missing", "conflict"}:
        form_value = None
    else:
        form_value = value if value is not None else raw_value

    result = {
        "status": status,
        "confidence": confidence,
        "source_value": source_value,
        "form_value": form_value,
        "citation": citation,
    }
    if candidates:
        raw_candidates = evidence.get("candidates", [])
        if raw_candidates is None:
            raw_candidates = []
        if not isinstance(raw_candidates, list):
            raise ValueError("field candidates must be a list")
        if raw_candidates:
            result["candidates"] = [
                _project_field(
                    _mapping(candidate, "field candidate"),
                    field_name=field_name,
                    process_key=process_key,
                    candidates=False,
                )
                for candidate in raw_candidates
            ]
    return result


def _project_block(process_key: str, block: Mapping[str, object], process_status: str) -> dict[str, object]:
    interested_value = block.get("interested")
    interested = (
        interested_value
        if isinstance(interested_value, str) and interested_value
        else "Não identificado"
    )
    raw_fields = block.get("fields", {})
    fields = _mapping(raw_fields, "block fields")
    projected_fields: dict[str, object] = {}
    for field_name in ALLOWED_FIELDS:
        field = fields.get(field_name)
        projected_fields[field_name] = _project_field(
            field if isinstance(field, Mapping) else None,
            field_name=field_name,
            process_key=process_key,
            candidates=True,
        )

    return {
        "process": {
            "key": process_key,
            "number": process_key.split("/", 1)[0],
            "year": process_key.split("/", 1)[1],
        },
        "interested": {
            "original": interested,
            "normalized": _normalize_name(interested),
        },
        "status": process_status,
        "fields": projected_fields,
    }


def _batch_id(checkpoint: Mapping[str, object], generated_at: str) -> str:
    for key in ("batch_id", "run_id"):
        value = checkpoint.get(key)
        if isinstance(value, str) and value:
            return value

    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("generated_at must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _logical_payload(dataset: Mapping[str, object]) -> dict[str, object]:
    batch = _mapping(dataset["batch"], "batch")
    return {
        "schema_version": dataset["schema_version"],
        "batch_id": batch["id"],
        "process_keys": batch["process_keys"],
        "records": dataset["records"],
    }


def _logical_sha256(dataset: Mapping[str, object]) -> str:
    serialized = json.dumps(
        _logical_payload(dataset),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def build_extension_dataset(checkpoint: Mapping[str, object], *, generated_at: str) -> dict[str, object]:
    """Build a safe extension dataset from an already extracted checkpoint."""
    source = _mapping(checkpoint, "checkpoint")
    raw_processes = source.get("processes")
    processes = _mapping(raw_processes, "checkpoint processes")

    parsed_processes: list[tuple[str, str, str, Mapping[str, object]]] = []
    for raw_process, payload in processes.items():
        process_key, number, year = _parse_process(raw_process)
        parsed_processes.append((process_key, number, year, _mapping(payload, "process entry")))
    parsed_processes.sort(key=lambda item: (int(item[1]), int(item[2]), item[0]))

    records: list[dict[str, object]] = []
    for process_key, _number, _year, process_entry in parsed_processes:
        result = process_entry.get("result", {})
        result_mapping = _mapping(result, "process result")
        raw_blocks = result_mapping.get("blocks", [])
        if raw_blocks is None:
            raw_blocks = []
        if not isinstance(raw_blocks, list):
            raise ValueError(f"blocks for process {process_key} must be a list")
        process_status = _string(result_mapping.get("status")) or "partial"
        for raw_block in raw_blocks:
            records.append(
                _project_block(
                    process_key,
                    _mapping(raw_block, "process block"),
                    process_status,
                )
            )

    process_keys = [process_key for process_key, _number, _year, _entry in parsed_processes]
    batch: dict[str, object] = {
        "id": _batch_id(source, generated_at),
        "logical_sha256": "",
        "process_count": len(process_keys),
        "record_count": len(records),
        "process_keys": process_keys,
    }
    dataset: dict[str, object] = {
        "schema_version": 1,
        "generated_at": generated_at,
        "batch": batch,
        "records": records,
    }
    batch["logical_sha256"] = _logical_sha256(dataset)
    validate_extension_dataset(dataset)
    return dataset


def _assert_keys(value: Mapping[str, object], expected: tuple[str, ...], label: str) -> None:
    if set(value) != set(expected):
        raise _invalid(f"{label} has unexpected keys")


def _validate_citation(value: object, label: str) -> None:
    if value is None:
        return
    citation = _mapping(value, label)
    keys = set(citation)
    if keys - {"process", "event", "page", "document"} or not {"process", "event", "page"}.issubset(keys):
        raise _invalid(f"{label} has unexpected keys")
    if not isinstance(citation["process"], str) or not isinstance(citation["event"], str):
        raise _invalid(f"{label} process/event must be strings")
    page = citation["page"]
    if isinstance(page, bool) or not isinstance(page, int) or page <= 0:
        raise _invalid(f"{label} page must be a positive integer")
    if "document" in citation and not isinstance(citation["document"], str):
        raise _invalid(f"{label} document must be a string")
    if "document" in citation and _safe_document_label(citation["document"]) != citation["document"]:
        raise _invalid(f"{label} document is unsafe")


def _validate_field_policy(
    field: Mapping[str, object],
    label: str,
    field_name: str,
    process_key: str,
) -> None:
    for key in ("source_value", "form_value"):
        exported_value = field[key]
        if exported_value is not None and _is_unsafe_value(exported_value):
            raise _invalid(f"{label} contains an unsafe {key}")

    if field_name == "data_publicacao_doe" and field["status"] == "found":
        if not _is_valid_civil_date(field["form_value"]):
            raise _invalid(f"{label} form_value is not a valid DD/MM/YYYY date")

    if field_name == "genero":
        citation = field["citation"] if isinstance(field["citation"], Mapping) else None
        safe_found = (
            field["status"] == "found"
            and field["confidence"] == "high"
            and isinstance(field["source_value"], str)
            and isinstance(field["form_value"], str)
            and _has_complete_document_citation(citation, process_key)
        )
        safe_missing = (
            field["status"] == "missing"
            and field["confidence"] == "none"
            and field["source_value"] is None
            and field["form_value"] is None
            and field["citation"] is None
            and "candidates" not in field
        )
        if not safe_found and not safe_missing:
            raise _invalid(f"{label} lacks safe documentary evidence")


def _validate_field(
    value: object,
    label: str,
    field_name: str,
    process_key: str,
) -> None:
    field = _mapping(value, label)
    allowed = set(_FIELD_OUTPUT_KEYS) | {"candidates"}
    if set(field) - allowed or not set(_FIELD_OUTPUT_KEYS).issubset(field):
        raise _invalid(f"{label} has unexpected keys")
    if not isinstance(field["status"], str) or not isinstance(field["confidence"], str):
        raise _invalid(f"{label} status/confidence must be strings")
    for key in ("source_value", "form_value"):
        if field[key] is not None and not isinstance(field[key], str):
            raise _invalid(f"{label} {key} must be a string or null")
    _validate_citation(field["citation"], f"{label} citation")
    _validate_field_policy(field, label, field_name, process_key)
    if "candidates" in field:
        candidates = field["candidates"]
        if not isinstance(candidates, list):
            raise _invalid(f"{label} candidates must be a list")
        for index, candidate in enumerate(candidates):
            _validate_field_without_candidates(
                candidate,
                f"{label} candidate {index}",
                field_name,
                process_key,
            )


def _validate_field_without_candidates(
    value: object,
    label: str,
    field_name: str,
    process_key: str,
) -> None:
    field = _mapping(value, label)
    if set(field) != set(_FIELD_OUTPUT_KEYS):
        raise _invalid(f"{label} has unexpected keys")
    if not isinstance(field["status"], str) or not isinstance(field["confidence"], str):
        raise _invalid(f"{label} status/confidence must be strings")
    for key in ("source_value", "form_value"):
        if field[key] is not None and not isinstance(field[key], str):
            raise _invalid(f"{label} {key} must be a string or null")
    _validate_citation(field["citation"], f"{label} citation")
    _validate_field_policy(field, label, field_name, process_key)


def _reject_private_keys(value: object, path: str = "dataset") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key.casefold() in _PRIVATE_KEYS:
                raise _invalid(f"private key at {path}.{key}")
            _reject_private_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_private_keys(child, f"{path}[{index}]")


def validate_extension_dataset(dataset: Mapping[str, object]) -> None:
    """Validate the public schema and logical signature of an extension dataset."""
    value = _mapping(dataset, "dataset")
    _assert_keys(value, _DATASET_KEYS, "dataset")
    _reject_private_keys(value)
    if value["schema_version"] != 1:
        raise _invalid("unsupported schema version")
    if not isinstance(value["generated_at"], str) or not value["generated_at"]:
        raise _invalid("generated_at must be a non-empty string")

    batch = _mapping(value["batch"], "batch")
    _assert_keys(batch, _BATCH_KEYS, "batch")
    if not isinstance(batch["id"], str) or not batch["id"]:
        raise _invalid("batch id must be a non-empty string")
    logical_sha = batch["logical_sha256"]
    if not isinstance(logical_sha, str) or re.fullmatch(r"[0-9a-f]{64}", logical_sha) is None:
        raise _invalid("logical_sha256 must be 64 lowercase hexadecimal characters")
    for key in ("process_count", "record_count"):
        if isinstance(batch[key], bool) or not isinstance(batch[key], int) or batch[key] < 0:
            raise _invalid(f"batch {key} must be a non-negative integer")
    process_keys = batch["process_keys"]
    if not isinstance(process_keys, list):
        raise _invalid("batch process_keys must be a list")
    parsed_inventory: list[tuple[str, int, int]] = []
    for index, raw_process_key in enumerate(process_keys):
        process_key, number, year = _parse_process(raw_process_key)
        if raw_process_key != process_key:
            raise _invalid(f"batch process_keys[{index}] is not canonical")
        parsed_inventory.append((process_key, int(number), int(year)))
    if len({item[0] for item in parsed_inventory}) != len(parsed_inventory):
        raise _invalid("batch process_keys contains duplicates")
    if parsed_inventory != sorted(parsed_inventory, key=lambda item: (item[1], item[2], item[0])):
        raise _invalid("batch process_keys is not in canonical order")
    if batch["process_count"] != len(process_keys):
        raise _invalid("process_count does not match process_keys")

    records = value["records"]
    if not isinstance(records, list):
        raise _invalid("records must be a list")
    if batch["record_count"] != len(records):
        raise _invalid("record_count does not match records")

    seen: set[tuple[str, str]] = set()
    for index, raw_record in enumerate(records):
        record = _mapping(raw_record, f"record {index}")
        if set(record) != {"process", "interested", "status", "fields"}:
            raise _invalid(f"record {index} has unexpected keys")
        process = _mapping(record["process"], f"record {index} process")
        _assert_keys(process, _PROCESS_KEYS, f"record {index} process")
        process_key, number, year = _parse_process(process["key"])
        if process["key"] != process_key or process["number"] != number or process["year"] != year:
            raise _invalid(f"record {index} process components do not match")
        if process_key not in process_keys:
            raise _invalid(f"record {index} process is absent from process_keys")
        interested = _mapping(record["interested"], f"record {index} interested")
        _assert_keys(interested, _INTERESTED_KEYS, f"record {index} interested")
        if not isinstance(interested["original"], str) or not isinstance(interested["normalized"], str):
            raise _invalid(f"record {index} interested values must be strings")
        if _normalize_name(interested["original"]) != interested["normalized"]:
            raise _invalid(f"record {index} interested normalization does not match")
        identity = (process_key, interested["normalized"])
        if identity in seen:
            raise _invalid(f"duplicate process/interested record: {process_key}")
        seen.add(identity)
        if not isinstance(record["status"], str):
            raise _invalid(f"record {index} status must be a string")
        fields = _mapping(record["fields"], f"record {index} fields")
        if tuple(fields) != ALLOWED_FIELDS:
            raise _invalid(f"record {index} fields are not in fixed order")
        for field_name in ALLOWED_FIELDS:
            _validate_field(
                fields[field_name],
                f"record {index} field {field_name}",
                field_name,
                process_key,
            )

    if logical_sha != _logical_sha256(value):
        raise _invalid("logical_sha256 does not match dataset content")


def _write_atomic(path: Path, dataset: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def export_extension_dataset(
    checkpoint_path: Path,
    output_path: Path,
    *,
    generated_at: str | None = None,
) -> dict[str, object]:
    """Read a checkpoint, project it, and replace the output atomically."""
    checkpoint = json.loads(Path(checkpoint_path).read_text(encoding="utf-8"))
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    dataset = build_extension_dataset(checkpoint, generated_at=timestamp)
    _write_atomic(Path(output_path), dataset)
    return dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--generated-at")
    parser.add_argument(
        "--validate",
        type=Path,
        metavar="DATASET",
        help="validate an existing extension dataset without exporting it",
    )
    args = parser.parse_args(argv)

    if args.validate is not None:
        if args.checkpoint is not None or args.output is not None or args.generated_at:
            parser.error("--validate cannot be combined with export arguments")
        dataset = json.loads(args.validate.read_text(encoding="utf-8-sig"))
        validate_extension_dataset(dataset)
        print("dataset-ok")
        return 0

    if args.checkpoint is None or args.output is None:
        parser.error("--checkpoint and --output are required for export")
    dataset = export_extension_dataset(
        args.checkpoint,
        args.output,
        generated_at=args.generated_at,
    )
    batch = dataset["batch"]
    print(
        json.dumps(
            {
                "process_count": batch["process_count"],
                "record_count": batch["record_count"],
                "logical_sha256": batch["logical_sha256"],
                "path": str(args.output),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
