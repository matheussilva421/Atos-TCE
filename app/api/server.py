"""Loopback HTTP server that exposes the Mesa to its own web UI and to the
paired Chrome/Edge extension.

Three route families exist and never share credentials:

``public``
    read-only Mesa routes (health, processes, storage, documents) plus the
    one-time bootstrap exchange;
``mesa``
    state-changing routes; they require the HttpOnly Mesa session cookie and a
    same-origin request;
``extension``
    routes used by the paired adapter; they require the bearer token plus
    ``X-TCE-Client`` and only answer Chrome/Edge extension origins.

There is deliberately no generic file route: PDFs are reachable solely through
``/api/v1/documents/<id>/pdf``, and the path is always resolved from SQLite and
re-checked against the data root.
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from ..core.store import Store
from ..area_restrita import PORTAL_ROLES
from ..area_restrita import cdp_fallback
from ..analysis.service import AnalysisService
from ..analysis.evidence import evidence_for_field
from ..econtas.service import AcquisitionError, AcquisitionService
from . import views
from .bridge import SESSION_COOKIE, Bridge, hash_token, is_extension_origin

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18743
WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_BODY_BYTES = 8 * 1024 * 1024

#: Command types the Mesa may queue for the thin extension. There is never a
#: submit type: the final completion click stays with the operator.
ALLOWED_COMMAND_TYPES = frozenset({"STATUS", "SCAN_AREA", "OPEN_ACT", "READ_FORM", "FILL_FORM"})

@dataclass(frozen=True)
class Route:
    pattern: re.Pattern[str]
    handler: str
    kind: str


ROUTES: tuple[Route, ...] = (
    Route(re.compile(r"/api/v1/health"), "handle_health", "public"),
    Route(re.compile(r"/api/v1/storage"), "handle_storage", "public"),
    Route(re.compile(r"/api/v1/processes"), "handle_process_list", "public"),
    Route(re.compile(r"/api/v1/processes/(?P<process_id>\d+)"), "handle_process_detail", "public"),
    Route(
        re.compile(r"/api/v1/processes/(?P<process_id>\d+)/evidence/(?P<field_name>[\w\-]+)"),
        "handle_field_evidence",
        "public",
    ),
    Route(re.compile(r"/api/v1/documents/(?P<document_id>\d+)/pdf"), "handle_document_pdf", "public"),
    Route(re.compile(r"/api/v1/bridge/pairing"), "handle_bridge_pairing", "mesa"),
    Route(re.compile(r"/api/v1/area/latest"), "handle_area_latest", "public"),
    Route(re.compile(r"/api/v1/acquisition/plan"), "handle_acquisition_plan", "public"),
    Route(re.compile(r"/api/v1/jobs/(?P<job_id>\d+)"), "handle_job_status", "public"),
    Route(re.compile(r"/api/v1/bridge/status"), "handle_bridge_status", "extension"),
    Route(re.compile(r"/api/v1/extension/commands/next"), "handle_command_next", "extension"),
    Route(re.compile(r"/api/v1/extension/commands/(?P<command_id>\d+)"), "handle_command_status", "mesa"),
)

POST_ROUTES: tuple[Route, ...] = (
    Route(re.compile(r"/api/v1/session/bootstrap"), "post_session_bootstrap", "public"),
    Route(re.compile(r"/api/v1/bridge/pair"), "post_bridge_pair", "public"),
    Route(re.compile(r"/api/v1/bridge/pairing/renew"), "post_pairing_renew", "mesa"),
    Route(re.compile(r"/api/v1/extension/commands"), "post_extension_command", "mesa"),
    Route(re.compile(r"/api/v1/extension/commands/(?P<command_id>\d+)/result"), "post_command_result", "extension"),
    Route(re.compile(r"/api/v1/area/scans"), "post_area_scan", "mesa"),
    Route(re.compile(r"/api/v1/area/analyze"), "post_area_analyze", "mesa"),
    Route(re.compile(r"/api/v1/area/analyze-cdp"), "post_area_analyze_cdp", "mesa"),
    Route(re.compile(r"/api/v1/acquisition/jobs"), "post_acquisition_job", "mesa"),
)


def _is_loopback(host: str) -> bool:
    if host in {"localhost", ""}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class MesaServer(ThreadingHTTPServer):
    """Threaded HTTP server that carries the store, the data root and the bridge."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address,
        handler,
        *,
        store: Store,
        data_root: Path,
        bridge: Bridge,
        acquisition_factory=None,
        verbose: bool = False,
    ):
        super().__init__(address, handler)
        self.store = store
        self.data_root = Path(data_root)
        self.bridge = bridge
        self.verbose = verbose
        self._acquisition = None
        self._acquisition_factory = acquisition_factory
        self._analysis: AnalysisService | None = None

    @property
    def analysis(self) -> AnalysisService:
        """The analysis worker, created once per server process (M4)."""

        if self._analysis is None:
            self._analysis = AnalysisService(self.store, self.data_root)
        return self._analysis

    @property
    def acquisition(self) -> AcquisitionService:
        """The acquisition coordinator, created once per server process."""

        if self._acquisition is None:
            if self._acquisition_factory is not None:
                self._acquisition = self._acquisition_factory(self.store, self.data_root)
            else:
                self._acquisition = AcquisitionService(
                    self.store, self.data_root, analysis=self.analysis
                )
        return self._acquisition

    @property
    def origins(self) -> set[str]:
        """Origins that count as "the Mesa itself"."""

        _host, port = self.server_address[0], self.server_address[1]
        return {f"http://127.0.0.1:{port}", f"http://localhost:{port}", f"http://[::1]:{port}"}


class MesaRequestHandler(BaseHTTPRequestHandler):
    server_version = "AtosTceMesa/0.1"
    protocol_version = "HTTP/1.1"

    cors_origin: str | None = None
    _body: dict[str, Any] = {}

    # ------------------------------------------------------------- plumbing

    @property
    def mesa(self) -> MesaServer:
        return self.server  # type: ignore[return-value]

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._safe(self._dispatch_get)

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._safe(self._dispatch_post)

    def do_OPTIONS(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        origin = str(self.headers.get("Origin") or "").strip()
        if not is_extension_origin(origin):
            self._send_json({"error": "cors_not_allowed"}, status=403)
            return
        self.cors_origin = origin
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, X-TCE-Client, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self._apply_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _safe(self, action) -> None:
        try:
            action()
        except Exception as error:  # keep the loopback server alive on any bug
            self._send_json(
                {"error": "internal_error", "detail": f"{type(error).__name__}: {error}"},
                status=500,
            )

    def _dispatch_get(self) -> None:
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        query = parse_qs(parts.query)
        for route in ROUTES:
            match = route.pattern.fullmatch(path)
            if match is None:
                continue
            self._authorize(route.kind)
            getattr(self, route.handler)(query, **match.groupdict())
            return
        self._serve_static(path)

    def _dispatch_post(self) -> None:
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        for route in POST_ROUTES:
            match = route.pattern.fullmatch(path)
            if match is None:
                continue
            # The body is consumed *before* any authorization decision: replying
            # while the client is still writing would reset the TCP connection on
            # Windows instead of delivering the intended status code.
            try:
                self._body = self._parse_body()
            except ValueError as error:
                self._send_json({"error": "invalid_body", "detail": str(error)}, status=400)
                return
            self._authorize(route.kind)
            getattr(self, route.handler)(**match.groupdict())
            return
        self._discard_body()
        self._send_json({"error": "not_found", "path": path}, status=404)

    def _authorize(self, kind: str) -> None:
        """Let the handler run; each handler asks for what it needs."""

        if kind == "extension":
            origin = str(self.headers.get("Origin") or "").strip()
            if is_extension_origin(origin):
                self.cors_origin = origin

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        if getattr(self.mesa, "verbose", False):
            super().log_message(format, *args)

    # ------------------------------------------------------------------ auth

    def _extension_client(self) -> str | None:
        """Return the authenticated client id, or ``None``."""

        header = str(self.headers.get("Authorization") or "")
        if not header.casefold().startswith("bearer "):
            return None
        token = header[7:].strip()
        client_id = str(self.headers.get("X-TCE-Client") or "").strip()
        if not token or not client_id:
            return None
        if not self.mesa.store.verify_bridge_token(client_id, hash_token(token)):
            return None
        self.mesa.store.touch_bridge_client(client_id)
        return client_id

    def _require_extension(self) -> str | None:
        client_id = self._extension_client()
        if client_id is None:
            self._send_json({"error": "unauthorized"}, status=401)
        return client_id

    def _require_session(self) -> bool:
        session_id = self._cookie(SESSION_COOKIE)
        if not self.mesa.bridge.valid_session(session_id):
            self._send_json({"error": "session_required"}, status=401)
            return False
        if not self.mesa.bridge.is_same_origin(self.headers, self.mesa.origins):
            self._send_json({"error": "origin_not_allowed"}, status=403)
            return False
        return True

    def _cookie(self, name: str) -> str | None:
        raw = str(self.headers.get("Cookie") or "")
        for part in raw.split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return value or None
        return None

    def _parse_body(self) -> dict[str, Any]:
        """Read and parse the request body exactly once."""

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("invalid Content-Length")
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError("payload too large")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid JSON body: {error}") from error
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise ValueError("the body must be a JSON object")
        return payload

    def _discard_body(self) -> None:
        try:
            self._parse_body()
        except ValueError:
            pass

    def _read_json_body(self) -> dict[str, Any]:
        """Return the body parsed by :meth:`_dispatch_post`."""

        return self._body

    # --------------------------------------------------------------- routes

    def handle_health(self, query: dict[str, list[str]]) -> None:
        self._send_json(views.health_payload(self.mesa.store, self.mesa.data_root))

    def handle_storage(self, query: dict[str, list[str]]) -> None:
        self._send_json(views.storage_payload(self.mesa.store, self.mesa.data_root))

    def handle_process_list(self, query: dict[str, list[str]]) -> None:
        self._send_json(
            views.process_list_payload(
                self.mesa.store, status=_first(query, "status"), query=_first(query, "q")
            )
        )

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
            total = path.stat().st_size
            requested = _parse_range(str(self.headers.get("Range") or ""), total)
            if requested is None and str(self.headers.get("Range") or "").strip():
                self._send_range_not_satisfiable(total)
                return
            if requested is None:
                payload = path.read_bytes()
            else:
                start, end = requested
                with open(path, "rb") as handle:
                    handle.seek(start)
                    payload = handle.read(end - start + 1)
        except OSError:
            self._send_json({"error": "document_unreadable"}, status=404)
            return
        if requested is None:
            self._send_bytes(payload, "application/pdf", filename=path.name, accept_ranges=True)
            return
        start, end = requested
        self.send_response(206)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.send_header("Cache-Control", "no-store")
        self._send_length_and_body(payload)

    def handle_field_evidence(
        self, query: dict[str, list[str]], process_id: str, field_name: str
    ) -> None:
        payload = evidence_for_field(self.mesa.store, int(process_id), field_name)
        if payload is None:
            self._send_json(
                {"error": "evidence_not_found", "process_id": int(process_id), "field": field_name},
                status=404,
            )
            return
        self._send_json(payload)

    def _send_range_not_satisfiable(self, total: int) -> None:
        body = json.dumps({"error": "range_not_satisfiable", "size": total}).encode("utf-8")
        self.send_response(416)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Range", f"bytes */{total}")
        self.send_header("Cache-Control", "no-store")
        self._send_length_and_body(body)

    def handle_bridge_pairing(self, query: dict[str, list[str]]) -> None:
        if not self._require_session():
            return
        self._send_json(self._pairing_payload())

    def handle_area_latest(self, query: dict[str, list[str]]) -> None:
        self._send_json(views.area_summary_payload(self.mesa.store))

    def handle_acquisition_plan(self, query: dict[str, list[str]]) -> None:
        self._send_json(views.acquisition_plan_payload(self.mesa.acquisition.plan_pending()))

    def handle_job_status(self, query: dict[str, list[str]], job_id: str) -> None:
        payload = views.job_payload(self.mesa.store, int(job_id))
        if payload is None:
            self._send_json({"error": "job_not_found", "job_id": int(job_id)}, status=404)
            return
        self._send_json(payload)

    def post_acquisition_job(self) -> None:
        if not self._require_session():
            return
        service = self.mesa.acquisition
        try:
            job_id = service.start_async(service.plan_pending())
        except AcquisitionError as error:
            self._send_json({"error": "acquisition_refused", "detail": str(error)}, status=409)
            return
        job = self.mesa.store.get_job(job_id) or {}
        self._send_json(
            {"job_id": job_id, "status": job.get("status"), "total": job.get("total")}, status=201
        )

    def handle_bridge_status(self, query: dict[str, list[str]]) -> None:
        client_id = self._require_extension()
        if client_id is None:
            return
        client = next(
            (row for row in self.mesa.store.list_bridge_clients() if row["client_id"] == client_id),
            None,
        )
        self._send_json(
            {
                "paired": True,
                "client_id": client_id,
                "origin": (client or {}).get("origin"),
                "extension_id": (client or {}).get("extension_id"),
                "last_seen_at": (client or {}).get("last_seen_at"),
            }
        )

    def handle_command_next(self, query: dict[str, list[str]]) -> None:
        client_id = self._require_extension()
        if client_id is None:
            return
        self._send_json({"command": self.mesa.store.claim_extension_command(client_id)})

    def handle_command_status(self, query: dict[str, list[str]], command_id: str) -> None:
        if not self._require_session():
            return
        command = self.mesa.store.get_extension_command(int(command_id))
        if command is None:
            self._send_json({"error": "command_not_found", "command_id": int(command_id)}, status=404)
            return
        self._send_json(command)

    def post_session_bootstrap(self) -> None:
        payload = self._read_json_body()
        if not self.mesa.bridge.consume_bootstrap(str(payload.get("token") or "")):
            self._send_json({"error": "bootstrap_rejected"}, status=401)
            return
        session_id = self.mesa.bridge.open_session()
        self._send_json(
            {"ok": True},
            extra_headers=[
                ("Set-Cookie", f"{SESSION_COOKIE}={session_id}; Path=/; HttpOnly; SameSite=Strict")
            ],
        )

    def post_bridge_pair(self) -> None:
        origin = str(self.headers.get("Origin") or "").strip()
        if not is_extension_origin(origin):
            self._send_json({"error": "extension_origin_required"}, status=403)
            return
        self.cors_origin = origin
        payload = self._read_json_body()
        token = self.mesa.bridge.pair(
            self.mesa.store,
            str(payload.get("client_id") or ""),
            str(payload.get("code") or ""),
            origin,
            str(payload.get("extension_id") or "") or None,
        )
        if token is None:
            self._send_json({"error": "pairing_rejected"}, status=401)
            return
        self._send_json({"token": token, "token_type": "Bearer"})

    def post_pairing_renew(self) -> None:
        if not self._require_session():
            return
        self.mesa.bridge.renew_pairing_code()
        self._send_json(self._pairing_payload())

    def post_extension_command(self) -> None:
        if not self._require_session():
            return
        payload = self._read_json_body()
        command_type = str(payload.get("type") or "").strip().upper()
        if command_type not in ALLOWED_COMMAND_TYPES:
            self._send_json({"error": "unsupported_command", "type": command_type}, status=400)
            return
        command_payload = payload.get("payload") or {}
        if not isinstance(command_payload, dict):
            self._send_json({"error": "invalid_payload"}, status=400)
            return
        command_id = self.mesa.store.create_extension_command(command_type, command_payload)
        self._send_json(
            {"command_id": command_id, "type": command_type, "state": "QUEUED"}, status=201
        )

    def post_command_result(self, command_id: str) -> None:
        if self._require_extension() is None:
            return
        payload = self._read_json_body()
        command = self.mesa.store.get_extension_command(int(command_id))
        if command is None:
            self._send_json(
                {"error": "command_not_found", "command_id": int(command_id)}, status=404
            )
            return
        error = None if payload.get("ok") is not False else str(payload.get("error") or "") or "command failed"
        detail = self._persist_scan_result(command, payload) if error is None else None
        self.mesa.store.complete_extension_command(int(command_id), result=payload, error=error)
        self._send_json({"ok": True, **(detail or {})})

    def _persist_scan_result(self, command: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        """Turn an extension SCAN_AREA result into a persisted Mesa scan."""

        if command.get("type") != "SCAN_AREA":
            return None
        if str(payload.get("role") or "") not in PORTAL_ROLES:
            return None
        rows = payload.get("rows")
        if not isinstance(rows, list):
            return None
        marker = payload.get("marker")
        marker = marker if isinstance(marker, dict) else {}
        scan_id = self.mesa.store.create_area_scan(
            source_scope=str(payload.get("source_scope") or "") or "unknown",
            marker_label=str(marker.get("label") or "") or None,
            marker_value=str(marker.get("value") or "") or None,
            rows=rows,
            origin="extension",
        )
        return {"scan_id": scan_id}

    def post_area_analyze(self) -> None:
        """Queue the single read-only command the Mesa can start by itself."""

        if not self._require_session():
            return
        command_id = self.mesa.store.create_extension_command("SCAN_AREA", {"origin": "mesa"})
        self._send_json(
            {"command_id": command_id, "type": "SCAN_AREA", "state": "QUEUED"}, status=201
        )

    def post_area_analyze_cdp(self) -> None:
        """Run the read-only compatibility fallback and persist the same schema."""

        if not self._require_session():
            return
        result = cdp_fallback.run_cdp_scan(REPO_ROOT, max_pages=cdp_fallback.MAX_CDP_PAGES)
        if not result.ok or result.snapshot is None:
            self._send_json(
                {"error": "cdp_scan_failed", "detail": result.error or "unknown"}, status=502
            )
            return
        scan_id = cdp_fallback.persist_cdp_scan(self.mesa.store, result.snapshot)
        self._send_json(
            {
                "scan_id": scan_id,
                "origin": "cdp",
                "rows": len(result.snapshot.get("rows") or []),
            },
            status=201,
        )

    def post_area_scan(self) -> None:
        if not self._require_session():
            return
        payload = self._read_json_body()
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            self._send_json({"error": "invalid_rows"}, status=400)
            return
        scan_id = self.mesa.store.create_area_scan(
            source_scope=str(payload.get("source_scope") or ""),
            marker_label=str(payload.get("marker_label") or "") or None,
            marker_value=str(payload.get("marker_value") or "") or None,
            rows=rows,
            origin="mesa",
            raw_sha256=str(payload.get("raw_sha256") or "") or None,
        )
        self._send_json({"scan_id": scan_id}, status=201)

    def _pairing_payload(self) -> dict[str, Any]:
        clients = [
            {
                "client_id": row["client_id"],
                "origin": row["origin"],
                "extension_id": row["extension_id"],
                "last_seen_at": row["last_seen_at"],
            }
            for row in self.mesa.store.list_bridge_clients()
        ]
        active = self.mesa.bridge.pairing_is_active()
        return {
            "paired": bool(clients),
            "clients": clients,
            # The code is only meaningful (and only shown) while nothing is paired.
            "code": self.mesa.bridge.pairing_code if (active and not clients) else None,
            "active": active,
            "expires_in": self.mesa.bridge.pairing_expires_in if active else None,
        }

    # --------------------------------------------------------------- static

    def _serve_static(self, path: str) -> None:
        if path in {"/bootstrap", "/bootstrap/"}:
            relative = "bootstrap.html"
        else:
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

    def _apply_cors_headers(self) -> None:
        if not self.cors_origin:
            return
        self.send_header("Access-Control-Allow-Origin", self.cors_origin)
        self.send_header("Vary", "Origin")

    def _send_json(
        self,
        payload: dict[str, Any],
        status: int = 200,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._apply_cors_headers()
        for key, value in extra_headers or []:
            self.send_header(key, value)
        self._send_length_and_body(body)

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        filename: str | None = None,
        accept_ranges: bool = False,
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        if accept_ranges:
            self.send_header("Accept-Ranges", "bytes")
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


def _parse_range(header: str, total: int) -> tuple[int, int] | None:
    """Parse exactly one ``bytes=`` range, or ``None`` when unusable.

    Multiple ranges, malformed bounds and out-of-range starts are refused so the
    caller can answer 416 instead of streaming a partial file by accident.
    """

    text = header.strip()
    if not text:
        return None
    if not text.casefold().startswith("bytes="):
        return None
    spec = text[6:].strip()
    if "," in spec or not spec:
        return None
    start_text, _, end_text = spec.partition("-")
    start_text = start_text.strip()
    end_text = end_text.strip()
    if not start_text and not end_text:
        return None
    try:
        if not start_text:
            length = int(end_text)
            if length <= 0 or total <= 0:
                return None
            start = max(0, total - length)
            return start, total - 1
        start = int(start_text)
        end = int(end_text) if end_text else total - 1
    except ValueError:
        return None
    if total <= 0 or start < 0 or start > end or start >= total:
        return None
    return start, min(end, total - 1)


def _content_type(path: Path) -> str:
    if path.suffix.casefold() in {".js", ".mjs"}:
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
    bridge: Bridge | None = None,
    acquisition_factory=None,
    verbose: bool = False,
) -> MesaServer:
    """Create (but do not start) the loopback Mesa server."""

    if not _is_loopback(host):
        raise ValueError(f"the Mesa only serves loopback clients, refusing to bind {host!r}")
    return MesaServer(
        (host, port),
        MesaRequestHandler,
        store=store,
        data_root=data_root,
        bridge=bridge or Bridge(),
        acquisition_factory=acquisition_factory,
        verbose=verbose,
    )
