"""Prepare a consistent private portable snapshot without bridge credentials."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Mapping
import uuid

from package_complete_archive import build_complete_zip


class TransferBusyError(RuntimeError):
    """The package is still being used by a local runtime or collector."""


_BRIDGE_ROOT_NAME = "dados-locais/bridge"
_OPERATION_LOCK_NAME = ".operation.lock"
_TRANSFER_REQUEST_NAME = "transfer-request.json"
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


def _transfer_request_path(package_root: Path) -> Path:
    return package_root / _BRIDGE_ROOT_NAME / _TRANSFER_REQUEST_NAME


def transfer_requested(package_root: Path) -> bool:
    """Return whether a transfer is pausing new portable writers."""

    path = _transfer_request_path(Path(package_root).resolve())
    if not path.is_file():
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransferBusyError(f"solicitação de transferência inválida: {path}") from exc
    if not isinstance(value, Mapping) or type(value.get("pid")) is not int or value["pid"] <= 0:
        raise TransferBusyError(f"solicitação de transferência inválida: {path}")
    if _pid_is_alive(value["pid"]):
        return True
    try:
        path.unlink()
    except OSError as exc:
        raise TransferBusyError(f"solicitação obsoleta não pôde ser removida: {path}") from exc
    return False


def _request_transfer(package_root: Path) -> tuple[Path, str]:
    bridge_root = package_root / _BRIDGE_ROOT_NAME
    bridge_root.mkdir(parents=True, exist_ok=True)
    path = bridge_root / _TRANSFER_REQUEST_NAME
    token = uuid.uuid4().hex
    metadata = {
        "schema_version": 1,
        "kind": "transfer-request",
        "pid": os.getpid(),
        "token": token,
        "state": "requested",
        "requested_at": time.time(),
    }
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        if transfer_requested(package_root):
            raise TransferBusyError("outra transferência já está pausando o pacote") from exc
        try:
            path.unlink()
        except OSError as unlink_error:
            raise TransferBusyError("solicitação obsoleta não pôde ser recuperada") from unlink_error
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            json.dump(metadata, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return path, token


def _update_transfer_request(path: Path, token: str, state: str, deadline: float) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping) or value.get("token") != token:
            return
        payload = dict(value)
        payload.update({"state": state, "deadline": deadline, "updated_at": time.time()})
        temporary_path: Path | None = None
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return


def _release_transfer_request(path: Path, token: str) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, Mapping) and value.get("token") == token:
            path.unlink()
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return


def _quiesce_runtime(package_root: Path, request_path: Path, request_token: str, timeout_seconds: float) -> set[str]:
    if timeout_seconds < 0:
        raise ValueError("timeout_seconds deve ser não-negativo")
    deadline = time.monotonic() + timeout_seconds
    _update_transfer_request(request_path, request_token, "draining", time.time() + timeout_seconds)
    initial_active: set[str] = set()
    while True:
        active = _active_runtime(package_root)
        if active is None:
            return initial_active
        initial_active.add(active)
        if time.monotonic() >= deadline:
            raise TransferBusyError(
                "trabalho pendente: execução ativa não drenou dentro do timeout de "
                f"{timeout_seconds:g} segundos ({active})"
            )
        time.sleep(min(0.1, max(0.01, deadline - time.monotonic())))


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


def _assert_distinct_destination(package_root: Path, destination: Path) -> None:
    try:
        destination.relative_to(package_root)
    except ValueError:
        return
    raise ValueError(
        "destino da transferência deve ser distinto e ficar fora da pasta portátil"
    )


def prepare_transfer(package_root: Path, destination: Path, *, timeout_seconds: float = 60.0) -> dict:
    """Build a quiescent private ZIP, leaving bridge state outside it.

    A transfer request first pauses new writers and lets an existing collector
    or service drain. Only after the runtime markers disappear is the
    operation lock acquired and the coherent ZIP built.
    """
    root = Path(package_root).resolve()
    output = Path(destination).resolve()
    if output.exists():
        raise FileExistsError(f"destino já existe: {output}")
    _assert_distinct_destination(root, output)
    request_path, request_token = _request_transfer(root)
    lock_path: Path | None = None
    lock_token: str | None = None
    try:
        initial_active = _quiesce_runtime(root, request_path, request_token, timeout_seconds)
        lock_path, lock_token = _acquire_operation_lock(root)
        if _active_runtime(root) is not None:
            raise TransferBusyError("trabalho pendente: novo escritor iniciou durante a transferência")
        progress_path = root / "acervo-tce" / "progresso.json"
        if not progress_path.is_file():
            raise ValueError(
                "snapshot de transferência exige acervo-tce/progresso.json coerente"
            )
        stats = build_complete_zip(root, output, distribution="private")
        return {
            **dict(stats),
            "path": str(output),
            "bridge_active_at_start": "service.json" in initial_active,
            "collector_active_at_start": "collector.json" in initial_active,
            "bridge_state_included": False,
            "progress_included": True,
            "quiesced": True,
            "drain_timeout_seconds": timeout_seconds,
        }
    finally:
        if lock_path is not None and lock_token is not None:
            _release_operation_lock(lock_path, lock_token)
        _release_transfer_request(request_path, request_token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--distribution", choices=("private",), default="private")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        result = prepare_transfer(args.source, args.output)
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
