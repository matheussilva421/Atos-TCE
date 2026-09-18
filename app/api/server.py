"""Loopback HTTP server that exposes the Mesa to its own web UI.

Only explicit routes exist. There is deliberately no generic file route: PDFs
are reachable solely through ``/api/v1/documents/<id>/pdf``, and the path is
always resolved from SQLite and re-checked against the data root.
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit

from ..core.store import Store
from . import views

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18743
WEB_ROOT = Path(__file__).resolve().parent.parent / "web"

Route = tuple[re.Pattern[str], str]

ROUTES: tuple[Route, ...] = (
    (re.compile(r"/api/v1/health"), "handle_health"),
    (re.compile(r"/api/v1/storage"), "handle_storage"),
    (re.compile(r"/api/v1/processes"), "handle_process_list"),
    (re.compile(r"/api/v1/processes/(?P<process_id>\d+)"), "handle_process_detail"),
    (re.compile(r"/api/v1/documents/(?P<document_id>\d+)/pdf"), "handle_document_pdf"),
)


def _is_loopback(host: str) -> bool:
    if host in {"localhost", ""}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class MesaServer(ThreadingHTTPServer):
    """Threaded HTTP server that carries the store and the data root."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, *, store: Store, data_root: Path, verbose: bool = False):
        super().__init__(address, handler)
        self.store = store
        self.data_root = Path(data_root)
        self.verbose = verbose


class MesaRequestHandler(BaseHTTPRequestHandler):
    server_version = "AtosTceMesa/0.1"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------- plumbing

    @property
    def mesa(self) -> MesaServer:
        return self.server  # type: ignore[return-value]

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        query = parse_qs(parts.query)
        try:
            self._dispatch(path, query)
        except Exception as error:  # keep the loopback server alive on any bug
            self._send_json(
                {"error": "internal_error", "detail": f"{type(error).__name__}: {error}"},
                status=500,
            )

    def _dispatch(self, path: str, query: dict[str, list[str]]) -> None:
        for pattern, method_name in ROUTES:
            match = pattern.fullmatch(path)
            if match is None:
                continue
            getattr(self, method_name)(query, **match.groupdict())
            return
        self._serve_static(path)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        if getattr(self.mesa, "verbose", False):
            super().log_message(format, *args)

    # --------------------------------------------------------------- routes

    def handle_health(self, query: dict[str, list[str]]) -> None:
        self._send_json(views.health_payload(self.mesa.store, self.mesa.data_root))

    def handle_storage(self, query: dict[str, list[str]]) -> None:
        self._send_json(views.storage_payload(self.mesa.store, self.mesa.data_root))

    def handle_process_list(self, query: dict[str, list[str]]) -> None:
        status = _first(query, "status")
        search = _first(query, "q")
        self._send_json(views.process_list_payload(self.mesa.store, status=status, query=search))

    def handle_process_detail(self, query: dict[str, list[str]], process_id: str) -> None:
        payload = views.process_detail_payload(self.mesa.store, int(process_id))
        if payload is None:
            self._send_json({"error": "process_not_found", "process_id": int(process_id)}, status=404)
            return
        self._send_json(payload)

    def handle_document_pdf(self, query: dict[str, list[str]], document_id: str) -> None:
        path = views.resolve_document_file(self.mesa.store, self.mesa.data_root, int(document_id))
        if path is None:
            self._send_json({"error": "document_not_found", "document_id": int(document_id)}, status=404)
            return
        try:
            payload = path.read_bytes()
        except OSError:
            self._send_json({"error": "document_unreadable"}, status=404)
            return
        self._send_bytes(payload, "application/pdf", filename=path.name)

    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        candidate = views.safe_join(WEB_ROOT, relative)
        if candidate is None or not candidate.is_file():
            self._send_json({"error": "not_found", "path": path}, status=404)
            return
        try:
            payload = candidate.read_bytes()
        except OSError:
            self._send_json({"error": "not_found", "path": path}, status=404)
            return
        self._send_bytes(payload, _content_type(candidate))

    # ------------------------------------------------------------ responses

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._send_length_and_body(body)

    def _send_bytes(self, body: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'inline; filename="{filename}"')
        self._send_length_and_body(body)

    def _send_length_and_body(self, body: bytes) -> None:
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _content_type(path: Path) -> str:
    if path.suffix.casefold() == ".js":
        return "text/javascript; charset=utf-8"
    if path.suffix.casefold() in {".html", ".css"}:
        return f"{mimetypes.guess_type(path.name)[0] or 'text/plain'}; charset=utf-8"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def serve(
    store: Store,
    data_root: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    verbose: bool = False,
) -> MesaServer:
    """Create (but do not start) the loopback Mesa server."""

    if not _is_loopback(host):
        raise ValueError(f"the Mesa only serves loopback clients, refusing to bind {host!r}")
    return MesaServer((host, port), MesaRequestHandler, store=store, data_root=data_root, verbose=verbose)
