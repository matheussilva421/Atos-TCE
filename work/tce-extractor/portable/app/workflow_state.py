"""Persistent, portable progress and portal-order state for an archive."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
import uuid
from typing import Any

from filter_new_batch import FilterError, canonical_process_key


SCHEMA_VERSION = 1
PROGRESS_FILE_NAME = "progresso.json"
ORDER_FILE_NAME = "ordem-portal.json"
LOCK_FILE_NAME = ".workflow-state.lock"


class WorkflowStateError(RuntimeError):
    """The state cannot be opened or is not safe to use."""


class RevisionConflict(WorkflowStateError):
    """The caller tried to write using a stale progress revision."""

    def __init__(self, expected_revision: int, actual_revision: int) -> None:
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        super().__init__(
            "revisão de progresso conflitante: "
            f"esperada {expected_revision}, atual {actual_revision}"
        )


def _canonical_key(value: object) -> str:
    try:
        return canonical_process_key({"key": value}, "process_key")
    except FilterError as exc:
        raise ValueError(str(exc)) from exc


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON de estado inválido: {path}") from exc


def _validate_progress(value: Any, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema de progresso inválido: {path}")
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError(f"revisão de progresso inválida: {path}")
    source_processes = value.get("processes")
    if not isinstance(source_processes, dict):
        raise ValueError(f"processos de progresso inválidos: {path}")

    processes: dict[str, dict[str, Any]] = {}
    for raw_key, entry in source_processes.items():
        key = _canonical_key(raw_key)
        if key in processes:
            raise ValueError(f"chave de processo duplicada no progresso: {key}")
        if not isinstance(entry, dict) or type(entry.get("completed")) is not bool:
            raise ValueError(f"marca de conclusão inválida para {key}: {path}")
        updated_at = entry.get("updated_at")
        if not isinstance(updated_at, str) or not updated_at.strip():
            raise ValueError(f"data de atualização inválida para {key}: {path}")
        processes[key] = {
            "completed": entry["completed"],
            "updated_at": updated_at,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": revision,
        "processes": processes,
    }


def _validate_order(value: Any, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema de ordem do portal inválido: {path}")
    captured_at = value.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at.strip():
        raise ValueError(f"data da ordem do portal inválida: {path}")
    source_keys = value.get("process_keys")
    if not isinstance(source_keys, list):
        raise ValueError(f"ordem do portal inválida: {path}")

    process_keys: list[str] = []
    seen: set[str] = set()
    for raw_key in source_keys:
        key = _canonical_key(raw_key)
        if key not in seen:
            seen.add(key)
            process_keys.append(key)
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_at": captured_at,
        "process_keys": process_keys,
    }


def _empty_progress() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "revision": 0, "processes": {}}


def _empty_order() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "process_keys": [],
    }


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class WorkflowState:
    """Own the two state files for one active portable archive."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise WorkflowStateError(f"raiz de estado inválida: {self.root}")
        self.root = self.root.resolve()
        self._lock_path = self.root / LOCK_FILE_NAME
        self._lock_token = uuid.uuid4().hex
        self._write_lock = threading.RLock()
        self._closed = False
        try:
            self._acquire_instance_lock()
            progress, order = self._load_state()
            if not (self.root / PROGRESS_FILE_NAME).exists():
                _atomic_write_json(self.root / PROGRESS_FILE_NAME, progress)
            if not (self.root / ORDER_FILE_NAME).exists():
                _atomic_write_json(self.root / ORDER_FILE_NAME, order)
        except Exception:
            self.close()
            raise

    def _acquire_instance_lock(self) -> None:
        for _ in range(2):
            try:
                descriptor = os.open(
                    self._lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError as exc:
                try:
                    owner = self._lock_path.read_text(encoding="ascii").split(":", 1)
                    owner_pid = int(owner[0])
                except (OSError, ValueError, IndexError):
                    raise WorkflowStateError(
                        f"estado já está em uso: {self.root}"
                    ) from exc
                if _pid_is_alive(owner_pid):
                    raise WorkflowStateError(f"estado já está em uso: {self.root}") from exc
                try:
                    self._lock_path.unlink()
                except OSError as unlink_error:
                    raise WorkflowStateError(
                        f"não foi possível recuperar lock obsoleto: {self.root}"
                    ) from unlink_error
                continue
            with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
                stream.write(f"{os.getpid()}:{self._lock_token}\n")
                stream.flush()
                os.fsync(stream.fileno())
            return
        raise WorkflowStateError(f"estado já está em uso: {self.root}")

    def _load_state(self) -> tuple[dict[str, Any], dict[str, Any]]:
        progress_path = self.root / PROGRESS_FILE_NAME
        order_path = self.root / ORDER_FILE_NAME
        progress = (
            _validate_progress(_read_json(progress_path), progress_path)
            if progress_path.exists()
            else _empty_progress()
        )
        order = (
            _validate_order(_read_json(order_path), order_path)
            if order_path.exists()
            else _empty_order()
        )
        return progress, order

    def _ensure_open(self) -> None:
        if self._closed:
            raise WorkflowStateError("estado já foi fechado")

    def _read_progress(self) -> dict[str, Any]:
        path = self.root / PROGRESS_FILE_NAME
        return _validate_progress(_read_json(path), path)

    def _read_order(self) -> dict[str, Any]:
        path = self.root / ORDER_FILE_NAME
        return _validate_order(_read_json(path), path)

    @staticmethod
    def _snapshot(progress: dict[str, Any], order: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "schema_version": SCHEMA_VERSION,
                "revision": progress["revision"],
                "processes": progress["processes"],
                "process_keys": order["process_keys"],
            }
        )

    def snapshot(self) -> dict[str, Any]:
        with self._write_lock:
            self._ensure_open()
            progress, order = self._load_state()
            return self._snapshot(progress, order)

    def set_completed(
        self, process_key: str, completed: bool, expected_revision: int
    ) -> dict[str, Any]:
        with self._write_lock:
            self._ensure_open()
            key = _canonical_key(process_key)
            if type(completed) is not bool:
                raise TypeError("completed deve ser booleano")
            if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
                raise TypeError("expected_revision deve ser inteiro")

            progress = self._read_progress()
            actual_revision = progress["revision"]
            if expected_revision != actual_revision:
                raise RevisionConflict(expected_revision, actual_revision)
            previous = progress["processes"].get(key)
            if previous is not None and previous["completed"] is completed:
                return self._snapshot(progress, self._read_order())

            updated = copy.deepcopy(progress)
            updated["revision"] = actual_revision + 1
            updated["processes"][key] = {
                "completed": completed,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _atomic_write_json(self.root / PROGRESS_FILE_NAME, updated)
            return self._snapshot(updated, self._read_order())

    def set_portal_order(self, keys: list[str]) -> dict[str, Any]:
        with self._write_lock:
            self._ensure_open()
            if not isinstance(keys, list):
                raise TypeError("keys deve ser uma lista")
            canonical_keys: list[str] = []
            seen: set[str] = set()
            for raw_key in keys:
                key = _canonical_key(raw_key)
                if key not in seen:
                    seen.add(key)
                    canonical_keys.append(key)

            current_order = self._read_order()
            if current_order["process_keys"] == canonical_keys:
                return self._snapshot(self._read_progress(), current_order)

            updated_order = {
                "schema_version": SCHEMA_VERSION,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "process_keys": canonical_keys,
            }
            _atomic_write_json(self.root / ORDER_FILE_NAME, updated_order)
            return self._snapshot(self._read_progress(), updated_order)

    def close(self) -> None:
        with self._write_lock:
            if self._closed:
                return
            self._closed = True
            try:
                content = self._lock_path.read_text(encoding="ascii")
                if content.strip() == f"{os.getpid()}:{self._lock_token}":
                    self._lock_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass

    def __enter__(self) -> "WorkflowState":
        self._ensure_open()
        return self

    def __exit__(self, _exc_type: object, _exc_value: object, _traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
