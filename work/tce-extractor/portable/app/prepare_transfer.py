"""Prepare a consistent private portable snapshot without bridge credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping
import uuid

from package_complete_archive import build_complete_zip


class TransferBusyError(RuntimeError):
    """The package is still being used by a local runtime or collector."""


_BRIDGE_ROOT_NAME = "dados-locais/bridge"
_OPERATION_LOCK_NAME = ".operation.lock"
_RUNTIME_MARKERS = ("service.json", "collector.json")


def _runtime_marker(package_root: Path, name: str) -> Path:
    return package_root / _BRIDGE_ROOT_NAME / name


def _active_runtime(package_root: Path) -> str | None:
    """Return the active marker name, rejecting malformed markers safely."""

    for name in _RUNTIME_MARKERS:
        metadata = _runtime_marker(package_root, name)
        if not metadata.exists():
            continue
        try:
            value = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TransferBusyError(
                f"marcador de execução inválido; transferência recusada: {metadata}"
            ) from exc
        if (
            not isinstance(value, Mapping)
            or type(value.get("pid")) is not int
            or value["pid"] <= 0
        ):
            raise TransferBusyError(
                f"marcador de execução inválido; transferência recusada: {metadata}"
            )
        if not _pid_is_alive(value["pid"]):
            try:
                metadata.unlink()
            except OSError as exc:
                raise TransferBusyError(
                    f"marcador de execução obsoleto não pôde ser removido: {metadata}"
                ) from exc
            continue
        return name
    return None


def _active_bridge(package_root: Path) -> bool:
    return _active_runtime(package_root) == "service.json"


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_owner_pid(lock_path: Path) -> int | None:
    try:
        value = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if isinstance(value, Mapping) and type(value.get("pid")) is int and value["pid"] > 0:
        return value["pid"]
    return None


def _acquire_operation_lock(package_root: Path) -> tuple[Path, str]:
    bridge_root = package_root / _BRIDGE_ROOT_NAME
    bridge_root.mkdir(parents=True, exist_ok=True)
    lock_path = bridge_root / _OPERATION_LOCK_NAME
    token = uuid.uuid4().hex
    descriptor = None
    for _ in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as exc:
            owner_pid = _lock_owner_pid(lock_path)
            if owner_pid is None or _pid_is_alive(owner_pid):
                raise TransferBusyError(
                    "outra operação portátil está fechando ou transferindo o pacote"
                ) from exc
            try:
                lock_path.unlink()
            except OSError as unlink_error:
                raise TransferBusyError(
                    "lock obsoleto não pôde ser recuperado; transferência recusada"
                ) from unlink_error
    if descriptor is None:
        raise TransferBusyError("não foi possível reservar a transferência")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                {
                    "schema_version": 1,
                    "kind": "transfer",
                    "pid": os.getpid(),
                    "token": token,
                },
                stream,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            lock_path.unlink()
        except OSError:
            pass
        raise
    return lock_path, token


def _release_operation_lock(lock_path: Path, token: str) -> None:
    try:
        value = json.loads(lock_path.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping) or value.get("token") != token:
            return
        lock_path.unlink()
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return


def prepare_transfer(package_root: Path, destination: Path) -> dict:
    """Build a quiescent private ZIP, leaving bridge state outside it.

    A process-wide operation lock prevents a new collector or transfer from
    starting during the snapshot. Existing service or collector markers cause
    an explicit refusal, so no ZIP is produced while those writers are active.
    """
    root = Path(package_root).resolve()
    output = Path(destination).resolve()
    if output.exists():
        raise FileExistsError(f"destino já existe: {output}")
    lock_path, lock_token = _acquire_operation_lock(root)
    try:
        active = _active_runtime(root)
        if active is not None:
            raise TransferBusyError(
                f"transferência recusada: execução ativa ({active}); pare-a e tente novamente"
            )
        stats = build_complete_zip(root, output, distribution="private")
        return {
            **dict(stats),
            "path": str(output),
            "bridge_active_at_start": False,
            "collector_active_at_start": False,
            "bridge_state_included": False,
            "progress_included": True,
        }
    finally:
        _release_operation_lock(lock_path, lock_token)
