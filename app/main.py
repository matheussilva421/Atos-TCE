"""Entry point for the Mesa Local.

``python -m app.main --data-root data`` creates the data root, opens the SQLite
store, serves the loopback API and opens the Mesa in the default browser.
Ctrl+C stops the server cleanly.
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

from .api.bridge import Bridge
from .api.server import DEFAULT_HOST, DEFAULT_PORT, serve
from .core.store import Store


def bootstrap_handoff_message(url: str) -> str:
    """Explain the one-time bootstrap and the authenticated session handoff."""

    return (
        f"URL de sessão da Mesa (uso único): {url}\n"
        "Para outro Chrome, abra a Mesa primeiro e use 'Copiar sessão para outro Chrome'."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.main", description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"), help="folder with atos-tce.db and archive/")
    parser.add_argument("--host", default=DEFAULT_HOST, help="loopback address to bind")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="port to bind (0 chooses a free port)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the default browser")
    parser.add_argument("--verbose", action="store_true", help="log every HTTP request")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - host dependent
                pass

    data_root = Path(args.data_root)
    for folder in (data_root, data_root / "archive", data_root / "logs"):
        folder.mkdir(parents=True, exist_ok=True)

    store = Store.open(data_root / "atos-tce.db")
    # Nothing of a previous process is running any more: hand every in-progress
    # state back to something the operator can act on before the UI opens.
    recovered = store.recover_interrupted_runtime_state()
    bridge = Bridge()
    if any(recovered.values()):
        summary = ", ".join(f"{key}={value}" for key, value in recovered.items() if value)
        print(f"Estado recuperado do encerramento anterior: {summary}")
    try:
        server = serve(
            store, data_root, host=args.host, port=args.port, bridge=bridge, verbose=args.verbose
        )
    except (OSError, ValueError) as error:
        print(f"Não foi possível iniciar a Mesa: {error}", file=sys.stderr)
        store.close()
        return 2

    address = f"http://{args.host}:{server.server_address[1]}/"
    # The one-time bootstrap token stays in the URL fragment: it is never sent
    # to the server as part of a path, a query string or a Referer header.
    bootstrap_url = f"{address}bootstrap#token={bridge.bootstrap_value}"
    thread = threading.Thread(target=server.serve_forever, name="mesa-http", daemon=True)
    thread.start()
    print(f"Mesa Local em {address}")
    print(f"Banco de dados: {store.path}")
    print(bootstrap_handoff_message(bootstrap_url))
    print("Extensão confiável: registro automático ativo.")
    print("Pressione Ctrl+C para encerrar.")
    if not args.no_browser:
        webbrowser.open(bootstrap_url)

    try:
        while thread.is_alive():
            thread.join(timeout=1.0)
    except KeyboardInterrupt:
        print("\nEncerrando a Mesa…")
    finally:
        server.shutdown()
        server.server_close()
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
