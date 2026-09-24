"""Launch the local Mesa and keep its one-time bootstrap inside QA Chrome."""

from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import socket
import sys
from urllib.error import URLError
from urllib.parse import quote, urlsplit
from urllib.request import ProxyHandler, Request, build_opener


DEFAULT_CDP_URL = "http://127.0.0.1:9222"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REQUEST_TIMEOUT_SECONDS = 3
_LOCAL_OPENER = build_opener(ProxyHandler({}))


def _loopback_http_origin(value: str) -> str | None:
    try:
        parsed = urlsplit(str(value or ""))
        host = (parsed.hostname or "").casefold()
        port = parsed.port
        if (
            parsed.scheme != "http"
            or not host
            or port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            return None
        is_loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
        if not is_loopback:
            return None
        authority_host = f"[{host}]" if ":" in host else host
        return f"http://{authority_host}:{port}"
    except (ValueError, TypeError):
        return None


def _read_json(url: str, *, method: str = "GET") -> dict | None:
    request = Request(url, method=method)
    try:
        with _LOCAL_OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                return None
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def validate_cdp_endpoint(cdp_url: str) -> bool:
    origin = _loopback_http_origin(cdp_url)
    if origin is None:
        return False
    payload = _read_json(f"{origin}/json/version")
    if payload is None:
        return False
    try:
        websocket = urlsplit(str(payload.get("webSocketDebuggerUrl") or ""))
        host = (websocket.hostname or "").casefold()
        port = websocket.port
        return (
            websocket.scheme == "ws"
            and host in {"localhost", "127.0.0.1", "::1"}
            and port == urlsplit(origin).port
        )
    except ValueError:
        return False


def can_bind_mesa_port(host: str, port: int) -> bool:
    """Refuse non-loopback binds and an already occupied Mesa port."""

    if host != "127.0.0.1" or not isinstance(port, int) or not 0 <= port <= 65535:
        return False
    if port == 0:
        return True

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            probe.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _is_official_bootstrap_url(value: str) -> bool:
    try:
        parsed = urlsplit(str(value or ""))
        fragment_key, separator, token = parsed.fragment.partition("=")
        return (
            parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and parsed.port is not None
            and parsed.path == "/bootstrap"
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and fragment_key == "token"
            and separator == "="
            and bool(token)
            and all(
                character.isascii() and (character.isalnum() or character in "_-")
                for character in token
            )
        )
    except ValueError:
        return False


def open_bootstrap_in_chrome(cdp_url: str, bootstrap_url: str) -> bool:
    """Open only the local one-time Mesa bootstrap in the loopback CDP browser."""

    origin = _loopback_http_origin(cdp_url)
    if origin is None or not _is_official_bootstrap_url(bootstrap_url):
        return False
    if not validate_cdp_endpoint(origin):
        return False
    target_url = f"{origin}/json/new?{quote(bootstrap_url, safe='')}"
    target = _read_json(target_url, method="PUT")
    return bool(target and target.get("type") == "page" and target.get("id"))


def safe_bootstrap_handoff_message(_bootstrap_url: str) -> str:
    return "Sessão da Mesa encaminhada ao Chrome QA pelo CDP local; o código de uso único não será exibido."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Mesa with its one-time bootstrap opened in the dedicated QA Chrome."
    )
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    parser.add_argument("app_args", nargs=argparse.REMAINDER, help="arguments forwarded to app.main")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app_args = list(args.app_args)
    if app_args and app_args[0] == "--":
        app_args.pop(0)

    if not validate_cdp_endpoint(args.cdp_url):
        print("Chrome QA não está disponível em um endpoint CDP de loopback válido.", file=sys.stderr)
        return 2

    repository = str(REPOSITORY_ROOT)
    if repository not in sys.path:
        sys.path.insert(0, repository)
    from app import main as mesa_main

    app_config = mesa_main.build_parser().parse_args(app_args)
    if not can_bind_mesa_port(app_config.host, app_config.port):
        print(
            "A Mesa requer 127.0.0.1 e uma porta livre; encerre a instância anterior antes de continuar.",
            file=sys.stderr,
        )
        return 2

    server_holder: dict[str, object] = {}
    handoff_failed = False
    original_serve = mesa_main.serve

    def tracked_serve(*serve_args, **serve_kwargs):
        server = original_serve(*serve_args, **serve_kwargs)
        server_holder["server"] = server
        return server

    def open_in_qa_chrome(bootstrap_url: str) -> bool:
        nonlocal handoff_failed
        if open_bootstrap_in_chrome(args.cdp_url, bootstrap_url):
            return True
        handoff_failed = True
        server = server_holder.get("server")
        if server is not None:
            server.shutdown()
        return False

    mesa_main.serve = tracked_serve
    mesa_main.webbrowser.open = open_in_qa_chrome
    mesa_main.bootstrap_handoff_message = safe_bootstrap_handoff_message
    result = mesa_main.main(app_args)
    if handoff_failed:
        print("O encaminhamento ao Chrome QA falhou; o serviço foi encerrado sem exibir o código de uso único.", file=sys.stderr)
        return 2
    return result


if __name__ == "__main__":
    raise SystemExit(main())
