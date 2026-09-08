"""Authenticated loopback HTTP bridge for the portable workflow."""

from __future__ import annotations

import hashlib
import json
import argparse
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from bridge_auth import BridgeAuth, BridgeAuthError
from workflow_state import RevisionConflict, WorkflowState


API_VERSION = 1
DEFAULT_PORT = 18743
FALLBACK_PORTS = tuple(range(18744, 18753))
MAX_BODY_BYTES = 1024 * 1024
PROCESS_KEY_RE = re.compile(r"^\d+/\d{4}$")


class _DocumentNotFound(Exception):
    pass


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _sidecar(root: Path, name: str) -> Path | None:
    for candidate in (root / name, root / "acervo-tce" / name):
        if candidate.is_file():
            return candidate
    return None


def _current_publication_dataset(root: Path) -> tuple[int, Path] | None:
    pointer_path = root / "publicacao-atual.json"
    if not pointer_path.is_file():
        return None
    try:
        pointer = _read_object(pointer_path)
        revision = pointer.get("revision")
        if type(revision) is not int or revision < 1:
            return None
        candidate = (root / "publicacoes" / str(revision) / "dataset.json").resolve()
        if not _inside(root, candidate) or not candidate.is_file():
            return None
        return revision, candidate
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"objeto JSON esperado: {path}")
    return value


def _safe_file(root: Path, relative_path: object) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path.strip():
        return None
    normalized = relative_path.replace("\\", "/")
    parsed = PurePosixPath(normalized)
    if parsed.is_absolute() or ".." in parsed.parts:
        return None
    candidate = (root / Path(*parsed.parts)).resolve()
    if not _inside(root, candidate) or not candidate.is_file():
        return None
    current = candidate
    while current != root:
        if current.is_symlink():
            return None
        current = current.parent
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_range(value: str | None, size: int) -> tuple[int, int] | None:
    if value is None:
        return None
    if not value.startswith("bytes=") or "," in value:
        raise ValueError("Range inválido")
    spec = value[6:]
    if "-" not in spec:
        raise ValueError("Range inválido")
    start_text, end_text = spec.split("-", 1)
    try:
        if not start_text:
            suffix = int(end_text)
            if suffix <= 0:
                raise ValueError
            start = max(0, size - suffix)
            end = size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
    except ValueError as exc:
        raise ValueError("Range inválido") from exc
    if start < 0 or start >= size or end < start:
        raise ValueError("Range fora do arquivo")
    return start, min(end, size - 1)


class _WorkflowHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, root: Path):
        self.workflow_root = root.resolve()
        workflow_state = WorkflowState(self.workflow_root)
        self.auth = BridgeAuth()
        self.selection: dict | None = None
        try:
            super().__init__(address, _WorkflowHandler)
        except Exception:
            workflow_state.close()
            raise
        self.workflow_state = workflow_state
        self.service_revision = self.workflow_state.snapshot()["revision"]


class _WorkflowHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format, *_args):
        # Request headers/body can contain pairing material; never log them.
        return

    @property
    def server_state(self) -> _WorkflowHTTPServer:
        return self.server  # type: ignore[return-value]

    def _send(self, status: int, payload: object = None, *, headers: dict[str, str] | None = None, body: bytes | None = None) -> None:
        response = body if body is not None else _json_bytes(payload if payload is not None else {})
        self.send_response(status)
        self.send_header("Content-Length", str(len(response)))
        if body is None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(response)

    def _error(self, status: int, code: str, message: str) -> None:
        self._send(status, {"error": {"code": code, "message": message}})

    def _valid_host(self) -> bool:
        return self.headers.get("Host", "") == f"127.0.0.1:{self.server.server_port}"

    def _valid_origin_header(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or self.server_state.auth.is_extension_origin(origin)

    def _authorized(self) -> bool:
        if not self._valid_host() or not self._valid_origin_header():
            return False
        value = self.headers.get("Authorization", "")
        if not value.startswith("Bearer "):
            return False
        return self.server_state.auth.validate(value[7:].strip(), self.headers.get("Origin"))

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length inválido") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("corpo excede o limite")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("objeto JSON esperado")
        return value

    def _require_auth(self) -> bool:
        if not self._authorized():
            self._error(403 if self.headers.get("Origin") and not self.server_state.auth.is_extension_origin(self.headers.get("Origin")) else 401, "UNAUTHORIZED", "autenticação local necessária")
            return False
        return True

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/api/v1/health":
            if not self._valid_host() or not self._valid_origin_header():
                self._error(403, "FORBIDDEN_ORIGIN", "Host ou Origin não permitido")
                return
            self._send(200, {"api_version": API_VERSION, "service": "tce-portable"})
            return
        if not self._require_auth():
            return
        if parsed.path == "/api/v1/state":
            params = parse_qs(parsed.query)
            try:
                since = int(params.get("since", ["-1"])[0])
            except ValueError:
                self._error(400, "INVALID_JSON", "since inválido")
                return
            snapshot = self.server_state.workflow_state.snapshot()
            self._send(200, {
                "api_version": API_VERSION,
                "revision": snapshot["revision"],
                "order": snapshot["process_keys"],
                "processes": snapshot["processes"],
                "selection": self.server_state.selection,
                "unchanged": since == snapshot["revision"],
            })
            return
        if parsed.path == "/api/v1/dataset":
            self._send_dataset()
            return
        if parsed.path.startswith("/api/v1/evidence/"):
            self._send_evidence(unquote(parsed.path.removeprefix("/api/v1/evidence/")))
            return
        if parsed.path.startswith("/api/v1/pdf/"):
            self._send_pdf(unquote(parsed.path.removeprefix("/api/v1/pdf/")))
            return
        self._error(404, "NOT_FOUND", "rota não encontrada")

    def _send_dataset(self):
        publication = _current_publication_dataset(self.server_state.workflow_root)
        path = publication[1] if publication is not None else _sidecar(self.server_state.workflow_root, "dados-complementar-ato.json")
        if path is None:
            self._error(404, "DATASET_NOT_FOUND", "dataset não encontrado")
            return
        try:
            dataset = _read_object(path)
        except (OSError, ValueError, json.JSONDecodeError):
            self._error(500, "DATASET_INVALID", "dataset inválido")
            return
        revision = publication[0] if publication is not None else self.server_state.service_revision
        self._send(200, {"api_version": API_VERSION, "revision": revision, "dataset": dataset})

    def _send_evidence(self, record_id: str):
        if not record_id or "/" in record_id or "\\" in record_id:
            self._error(404, "EVIDENCE_NOT_FOUND", "evidência não encontrada")
            return
        path = _sidecar(self.server_state.workflow_root, "evidencias-visuais.json")
        if path is None:
            self._error(404, "EVIDENCE_NOT_FOUND", "evidência não encontrada")
            return
        try:
            data = _read_object(path)
            record = data.get("records", {}).get(record_id)
        except (OSError, ValueError, json.JSONDecodeError):
            record = None
        if record is None:
            self._error(404, "EVIDENCE_NOT_FOUND", "evidência não encontrada")
            return
        self._send(200, {"api_version": API_VERSION, "record_id": record_id, "record": record, "documents": data.get("documents", {})})

    def _send_pdf(self, document_id: str):
        if not document_id or "/" in document_id or "\\" in document_id:
            self._error(404, "DOCUMENT_NOT_FOUND", "documento não encontrado")
            return
        path = _sidecar(self.server_state.workflow_root, "evidencias-visuais.json")
        if path is None:
            self._error(404, "DOCUMENT_NOT_FOUND", "documento não encontrado")
            return
        try:
            data = _read_object(path)
            entry = data.get("documents", {}).get(document_id)
            file_path = _safe_file(self.server_state.workflow_root, entry.get("relative_path") if isinstance(entry, dict) else None)
            if file_path is None or (isinstance(entry, dict) and entry.get("sha256") and entry["sha256"] != _sha256(file_path)):
                raise _DocumentNotFound
            payload = file_path.read_bytes()
        except _DocumentNotFound:
            self._error(404, "DOCUMENT_NOT_FOUND", "documento não encontrado")
            return
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            self._error(404, "DOCUMENT_NOT_FOUND", "documento não encontrado")
            return
        try:
            selected = _parse_range(self.headers.get("Range"), len(payload))
        except ValueError:
            self._send(416, {"error": {"code": "RANGE_INVALID", "message": "Range inválido"}}, headers={"Content-Range": f"bytes */{len(payload)}"})
            return
        if selected is None:
            self._send(200, body=payload, headers={"Content-Type": "application/pdf", "Accept-Ranges": "bytes"})
            return
        start, end = selected
        self._send(206, body=payload[start:end + 1], headers={
            "Content-Type": "application/pdf",
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{len(payload)}",
        })

    def do_POST(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/api/v1/pair":
            if not self._valid_host():
                self._error(403, "FORBIDDEN_HOST", "Host não permitido")
                return
            origin = self.headers.get("Origin")
            if not self.server_state.auth.is_extension_origin(origin):
                self._error(403, "FORBIDDEN_ORIGIN", "Origin de extensão necessária")
                return
            try:
                payload = self._read_json()
                if set(payload) != {"code"} or not isinstance(payload["code"], str):
                    raise ValueError
                token = self.server_state.auth.redeem(payload["code"], origin)
            except (ValueError, UnicodeDecodeError):
                self._error(400, "INVALID_JSON", "JSON inválido")
                return
            except BridgeAuthError:
                self._error(401, "PAIRING_REJECTED", "pareamento rejeitado")
                return
            self._send(200, {"api_version": API_VERSION, "token": token})
            return
        if not self._require_auth():
            return
        if parsed.path == "/api/v1/selection":
            try:
                payload = self._read_json()
                if set(payload) != {"process_key", "interested_normalized", "tab_id", "frame_id", "sequence"}:
                    raise ValueError
                if not isinstance(payload["process_key"], str) or not isinstance(payload["interested_normalized"], str) or not all(isinstance(payload[key], int) for key in ("tab_id", "frame_id", "sequence")):
                    raise ValueError
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                self._error(400, "INVALID_JSON", "seleção inválida")
                return
            previous = self.server_state.selection
            if previous is not None and payload["sequence"] <= previous["sequence"]:
                self._send(200, {"accepted": False, "sequence": previous["sequence"]})
                return
            self.server_state.selection = payload
            self.server_state.service_revision += 1
            self._send(200, {"accepted": True, "revision": self.server_state.service_revision})
            return
        self._error(404, "NOT_FOUND", "rota não encontrada")

    def do_PUT(self):
        parsed = urlsplit(self.path)
        if not self._require_auth():
            return
        if not parsed.path.startswith("/api/v1/progress/"):
            self._error(404, "NOT_FOUND", "rota não encontrada")
            return
        process_key = unquote(parsed.path.removeprefix("/api/v1/progress/"))
        try:
            payload = self._read_json()
            if set(payload) != {"completed", "expected_revision"} or type(payload["completed"]) is not bool or type(payload["expected_revision"]) is not int:
                raise ValueError
            result = self.server_state.workflow_state.set_completed(process_key, payload["completed"], payload["expected_revision"])
        except RevisionConflict as exc:
            self._error(409, "REVISION_CONFLICT", str(exc))
            return
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
            self._error(400, "INVALID_JSON", "progresso inválido")
            return
        self._send(200, {"api_version": API_VERSION, "revision": result["revision"], "state": result})


def create_server(root: Path, host: str = "127.0.0.1", port: int = DEFAULT_PORT):
    if host != "127.0.0.1":
        raise ValueError("o serviço deve usar 127.0.0.1")
    if not isinstance(port, int) or port < 0 or port > 65535:
        raise ValueError("porta inválida")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidates = (port,) if port == 0 else (port, *FALLBACK_PORTS)
    last_error = None
    for candidate in candidates:
        try:
            server = _WorkflowHTTPServer((host, candidate), root)
            return server
        except OSError as exc:
            last_error = exc
        except Exception:
            raise
    raise OSError(f"não foi possível abrir porta loopback: {last_error}")


def _write_runtime_metadata(path: Path, server: _WorkflowHTTPServer) -> dict[str, object]:
    pairing_code = server.auth.issue_pairing_code()
    metadata = {
        "schema_version": 1,
        "pid": os.getpid(),
        "port": server.server_port,
        "executable": str(Path(os.environ.get("PYTHONEXECUTABLE", os.sys.executable)).resolve()),
        "started_at": time.time(),
        "pairing_code": pairing_code,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(metadata, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="serviço local autenticado do pacote portátil")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bridge-root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    server = create_server(args.root, host=args.host, port=args.port)
    metadata_path = args.bridge_root / "service.json"
    _write_runtime_metadata(metadata_path, server)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        server.workflow_state.close()
        try:
            metadata_path.unlink()
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
