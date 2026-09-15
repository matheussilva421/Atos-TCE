"""Loopback-only receiver for a sanitized Area Restrita snapshot."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
import tempfile


MAX_BODY_BYTES = 2 * 1024 * 1024
SOURCE_SCOPES = frozenset(("sector_finalistic", "my_processes"))


def _validate_snapshot(body: bytes) -> dict:
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("fotografia excede 2 MiB")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("fotografia não é JSON UTF-8 válido") from error
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("source_scope") not in SOURCE_SCOPES
        or not isinstance(value.get("marker"), dict)
        or not isinstance(value["marker"].get("label"), str)
        or not value["marker"]["label"].strip()
        or not isinstance(value.get("rows"), list)
        or not value["rows"]
    ):
        raise ValueError("estrutura de fotografia inválida")
    return value


def _write_atomic(destination: Path, body: bytes) -> None:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".area-snapshot-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


class _Handler(BaseHTTPRequestHandler):
    server: "_Server"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path not in {"/", "/app/area_snapshot_transfer.html"}:
            self._send_json(404, {"error": "rota não encontrada"})
            return
        try:
            body = self.server.transfer_page.read_bytes()
        except OSError:
            self._send_json(500, {"error": "página local indisponível"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/snapshot":
            self._send_json(404, {"error": "rota não encontrada"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if length < 0 or length > MAX_BODY_BYTES:
                raise ValueError("tamanho inválido")
            snapshot_body = self.rfile.read(length)
            value = _validate_snapshot(snapshot_body)
            _write_atomic(self.server.destination, snapshot_body)
        except (ValueError, OSError) as error:
            self._send_json(400, {"error": str(error)})
            return
        self._send_json(200, {"saved": True, "rows": len(value["rows"])})


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], destination: Path):
        super().__init__(address, _Handler)
        self.destination = destination
        self.transfer_page = Path(__file__).with_name("area_snapshot_transfer.html")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18799)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("porta inválida")
    server = _Server(("127.0.0.1", args.port), args.output)
    print(f"Receiver loopback em http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
