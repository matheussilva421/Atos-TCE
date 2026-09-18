"""Build a safe, local index of the portable TCE archive."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

_URI_RE = re.compile(r"(?i)\b[a-z][a-z0-9+.-]{1,31}://[^\s\"']+")
_PROCESS_KEY_PATTERN = re.compile(r"^\s*(\d+)\s*/\s*(\d{4})\s*$")
_SENSITIVE_WORD_RE = re.compile(
    r"(?i)\b(?:url|authorization|cookie|token|credential|credencial|session|password|senha)\b"
)
_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)\b(?:authorization|cookie|token|credential|credencial|session|password|senha)\b"
    r"\s*(?:(?:[:=]\s*)|(?:\s+))"
    r"(?:bearer|basic)?\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;|]+(?:\s+[^\s,;|]+)?)"
)
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)^(?:url|authorization|cookie|token|credential|credencial|session|password|senha)(?:[_-].*)?$"
)
_DOCUMENT_FIELDS = (
    "key",
    "id",
    "title",
    "extension",
    "remote_signature",
    "duplicate_of",
    "error",
)
_PROCESS_FIELDS = ("key", "id", "number", "year", "status", "synced_at")
_EVENT_FIELDS = ("event", "event_id", "date", "title", "active")


def _safe_text(value: Any) -> str:
    text = str(value)
    text = _URI_RE.sub("[ENDERECO REMOVIDO]", text)
    text = _SENSITIVE_VALUE_RE.sub("[DADO SENSIVEL REMOVIDO]", text)
    return _SENSITIVE_WORD_RE.sub("[DADO SENSIVEL REMOVIDO]", text)


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, dict):
        return {
            str(key): _safe_value(nested)
            for key, nested in value.items()
            if not _SENSITIVE_KEY_RE.fullmatch(str(key).strip())
        }
    if isinstance(value, list):
        return [_safe_value(nested) for nested in value]
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON de metadados deve ser um objeto: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _path_candidates(
    root: Path, process_dir: Path, event_dir: Path, raw_path: str
) -> list[Path]:
    normalized = raw_path.replace("\\", "/")
    parsed = Path(normalized)
    if parsed.is_absolute():
        return [parsed]
    return [
        root / parsed,
        process_dir / parsed,
        event_dir / parsed,
        event_dir / parsed.name,
    ]


def _resolve_document_path(
    root: Path, process_dir: Path, event_dir: Path, record: dict[str, Any]
) -> tuple[Path | None, str | None]:
    raw_path = record.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, None
    if _URI_RE.search(raw_path):
        return None, None

    for candidate in _path_candidates(root, process_dir, event_dir, raw_path):
        resolved = candidate.resolve()
        if not _inside(root, resolved):
            continue
        relative_path = resolved.relative_to(root).as_posix()
        if resolved.is_file():
            return resolved, relative_path

    fallback = (root / raw_path.replace("\\", "/")).resolve()
    if _inside(root, fallback):
        return None, fallback.relative_to(root).as_posix()
    return None, None


def _safe_relative_path(root: Path, value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip() or _URI_RE.search(value):
        return None
    normalized = value.replace("\\", "/")
    parsed = Path(normalized)
    if parsed.is_absolute() or PureWindowsPath(normalized).is_absolute():
        return None
    resolved = (root / parsed).resolve()
    if not _inside(root, resolved):
        return None
    return resolved.relative_to(root).as_posix()


def _safe_previous_versions(root: Path, value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    versions = []
    for item in value:
        if not isinstance(item, dict):
            continue
        if "path" in item and _safe_relative_path(root, item["path"]) is None:
            continue
        version = _safe_value(item)
        if "path" in item:
            version["path"] = _safe_relative_path(root, item["path"])
        if version:
            versions.append(version)
    return versions


def _safe_document(
    root: Path, process_dir: Path, event_dir: Path, record: Any
) -> dict[str, Any]:
    source = record if isinstance(record, dict) else {}
    document: dict[str, Any] = {
        field: _safe_value(source[field])
        for field in _DOCUMENT_FIELDS
        if field in source
    }
    if "previous_versions" in source:
        document["previous_versions"] = _safe_previous_versions(
            root, source["previous_versions"]
        )

    path, relative_path = _resolve_document_path(root, process_dir, event_dir, source)
    document["relative_path"] = relative_path
    document["sha256"] = _sha256(path) if path is not None else None
    if path is not None:
        document["status"] = "complete"
    else:
        source_status = source.get("status")
        document["status"] = (
            _safe_text(source_status)
            if isinstance(source_status, str)
            and source_status.lower() in {"error", "missing", "skipped", "unavailable"}
            else "missing"
        )
    return document


def _event_sort_key(event: dict[str, Any]) -> tuple[int, str]:
    try:
        number = int(event.get("event", 0))
    except (TypeError, ValueError):
        number = 0
    return number, str(event.get("event_id", ""))


def _event_identity(event: dict[str, Any]) -> tuple[str, str]:
    return str(event.get("event", "")), str(event.get("event_id", ""))


def _safe_event(
    root: Path, process_dir: Path, event_dir: Path, source: dict[str, Any]
) -> dict[str, Any]:
    event = {
        field: _safe_value(source[field])
        for field in _EVENT_FIELDS
        if field in source
    }
    event["documents"] = [
        _safe_document(root, process_dir, event_dir, document)
        for document in source.get("documents", [])
    ]
    return event


def _process_events(root: Path, process_dir: Path, process: dict[str, Any]) -> list[dict[str, Any]]:
    event_jsons = sorted(process_dir.glob("evento-*/evento.json"))
    events: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for event_json in event_jsons:
        resolved_event_json = event_json.resolve()
        if not _inside(root, resolved_event_json):
            continue
        event = _read_json(resolved_event_json)
        event_dir = resolved_event_json.parent
        safe_event = _safe_event(root, process_dir, event_dir, event)
        events.append(safe_event)
        seen.add(_event_identity(event))

    for event in process.get("events", []):
        if not isinstance(event, dict):
            continue
        identity = _event_identity(event)
        if identity in seen:
            continue
        events.append(_safe_event(root, process_dir, process_dir, event))
    return sorted(events, key=_event_sort_key)


def _safe_process(process_dir: Path, process: dict[str, Any], root: Path) -> dict[str, Any]:
    safe_process = {
        field: _safe_value(process[field])
        for field in _PROCESS_FIELDS
        if field in process
    }
    safe_process["events"] = _process_events(root, process_dir, process)
    return safe_process


def _canonical_process_key(record: Any, context: str) -> str:
    if not isinstance(record, dict):
        raise ValueError(f"{context}: registro de processo inválido")
    raw_key = record.get("key")
    if raw_key is None or not str(raw_key).strip():
        number = record.get("number", record.get("numero"))
        year = record.get("year", record.get("ano"))
        if number is None or year is None:
            raise ValueError(f"{context}: chave canônica numero/ano ausente")
        raw_key = f"{number}/{year}"
    match = _PROCESS_KEY_PATTERN.fullmatch(str(raw_key))
    if match is None:
        raise ValueError(f"{context}: chave canônica inválida: {raw_key}")
    return f"{match.group(1)}/{match.group(2)}"


def _portal_process_keys(root: Path) -> list[str] | None:
    order_path = root / "ordem-portal.json"
    if not order_path.is_file():
        return None
    order = _read_json(order_path)
    if (
        type(order.get("schema_version")) is not int
        or order.get("schema_version") != 1
        or not isinstance(order.get("captured_at"), str)
        or not order["captured_at"].strip()
        or not isinstance(order.get("process_keys"), list)
    ):
        raise ValueError(f"ordem do portal inválida: {order_path}")
    process_keys: list[str] = []
    seen: set[str] = set()
    for index, raw_key in enumerate(order["process_keys"]):
        try:
            key = _canonical_process_key(
                {"key": raw_key}, f"ordem do portal, item {index}"
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if key not in seen:
            seen.add(key)
            process_keys.append(key)
    return process_keys


def _process_index_key(process: dict[str, Any], context: str) -> str:
    try:
        return _canonical_process_key(process, context)
    except ValueError:
        raw_key = process.get("key")
        return str(raw_key) if raw_key is not None else ""


def scan_archive(root: Path) -> dict[str, Any]:
    """Read all process metadata without carrying URLs or credentials forward."""
    archive_root = Path(root)
    if not archive_root.is_dir():
        raise FileNotFoundError(f"Acervo não encontrado: {archive_root}")
    archive_root = archive_root.resolve()
    process_root = (archive_root / "processos").resolve()
    if not process_root.is_dir() or not _inside(archive_root, process_root):
        process_root = archive_root

    processes = []
    process_keys: list[str] = []
    keyed_processes: dict[str, dict[str, Any]] = {}
    for process_json in sorted(process_root.glob("*/processo.json")):
        resolved_process_json = process_json.resolve()
        if not _inside(archive_root, resolved_process_json):
            continue
        process = _read_json(resolved_process_json)
        safe_process = _safe_process(resolved_process_json.parent, process, archive_root)
        processes.append(safe_process)
        key = _process_index_key(process, str(resolved_process_json))
        if key and key not in keyed_processes:
            process_keys.append(key)
            keyed_processes[key] = safe_process

    persisted_order = _portal_process_keys(archive_root)
    if persisted_order is not None:
        process_keys = persisted_order + [
            key for key in process_keys if key not in persisted_order
        ]
        processes = [
            keyed_processes[key] for key in process_keys if key in keyed_processes
        ]
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "process_keys": process_keys,
        "processes": processes,
    }


def write_index(root: Path, output: Path) -> dict[str, Any]:
    """Write ``scan_archive`` output through a same-directory atomic replace."""
    archive_root = Path(root).resolve()
    destination = Path(output).resolve()
    if destination == archive_root or not _inside(archive_root, destination):
        raise ValueError("Índice deve ser gravado dentro da raiz do acervo")
    index = scan_archive(archive_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(index, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return index
