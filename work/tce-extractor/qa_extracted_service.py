"""Exercise the authenticated service imported from an extracted package."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import socket
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _load_service(app_root: Path):
    sys.path.insert(0, str(app_root))
    try:
        spec = importlib.util.spec_from_file_location("qa_extracted_local_service", app_root / "local_service.py")
        if spec is None or spec.loader is None:
            raise ImportError("local_service.py não carregou")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def _request(url: str, *, method: str = "GET", payload: dict | None = None, token: str | None = None, origin: str | None = None, cookie: str | None = None, csrf: str | None = None):
    headers: dict[str, str] = {}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-CSRF-Token"] = csrf
    request = Request(
        url,
        method=method,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, response.headers, json.loads(response.read())
    except HTTPError as error:
        error.close()
        raise


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    args = parser.parse_args()
    package_root = args.package_root.resolve()
    module = _load_service(package_root / "app")
    with TemporaryDirectory(prefix="tce-extracted-service-") as temporary:
        root = Path(temporary)
        server = module.create_server(root, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            code = server.auth.issue_pairing_code()
            _status, _headers, paired = _request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://qa",
            )
            token = paired["token"]
            try:
                _request(
                    f"{base}/api/v1/progress/103439%2F2023",
                    method="PUT",
                    payload={"completed": True, "expected_revision": 0},
                    token="invalid",
                    origin="chrome-extension://qa",
                )
            except HTTPError as error:
                invalid_bearer = error.code
            else:
                raise AssertionError("Bearer inválido foi aceito")
            _status, _headers, accepted = _request(
                f"{base}/api/v1/selection",
                method="POST",
                payload={
                    "process_key": "103439/2023",
                    "interested_normalized": "pessoa teste",
                    "tab_id": 1,
                    "frame_id": 0,
                    "sequence": 2,
                },
                token=token,
                origin="chrome-extension://qa",
            )
            _status, _headers, stale = _request(
                f"{base}/api/v1/selection",
                method="POST",
                payload={
                    "process_key": "103439/2023",
                    "interested_normalized": "pessoa teste",
                    "tab_id": 1,
                    "frame_id": 0,
                    "sequence": 1,
                },
                token=token,
                origin="chrome-extension://qa",
            )
            review_code = server.review_bootstrap_code
            _status, review_headers, review = _request(
                f"{base}/api/v1/review-session",
                method="POST",
                payload={"code": review_code},
                origin=base,
            )
            cookies = review_headers.get_all("Set-Cookie")
            review_cookie = next(cookie.split(";", 1)[0] for cookie in cookies if cookie.startswith("tce_review="))
            try:
                _request(
                    f"{base}/api/v1/progress/103439%2F2023",
                    method="PUT",
                    payload={"completed": True, "expected_revision": 0},
                    cookie=review_cookie,
                    origin=base,
                )
            except HTTPError as error:
                missing_csrf = error.code
            else:
                raise AssertionError("mutação da mesa sem CSRF foi aceita")
            _status, _headers, completed = _request(
                f"{base}/api/v1/progress/103439%2F2023",
                method="PUT",
                payload={"completed": True, "expected_revision": 0},
                cookie=review_cookie,
                csrf=review["csrf_token"],
                origin=base,
            )
            package_marker = root / "package"
            transfer_dir = package_marker / "dados-locais" / "bridge"
            transfer_dir.mkdir(parents=True)
            transfer_path = transfer_dir / "transfer-request.json"
            transfer_path.write_text(
                json.dumps({"kind": "transfer-request", "state": "requested", "pid": os.getpid()}),
                encoding="utf-8",
            )
            transfer_blocked = module.transfer_requested(package_marker)
            transfer_path.unlink()
            if not transfer_blocked:
                raise AssertionError("transfer-request.json não bloqueou o serviço extraído")

            occupied = socket.socket()
            occupied.bind(("127.0.0.1", 18743))
            occupied.listen(1)
            fallback_server = module.create_server(root / "fallback", port=18743)
            fallback_port = fallback_server.server_port
            fallback_server.server_close()
            fallback_server.workflow_state.close()
            occupied.close()
            if fallback_port == 18743:
                raise AssertionError("create_server não escolheu porta de fallback")
            print(json.dumps({
                "package_root": str(package_root),
                "invalid_bearer_status": invalid_bearer,
                "selection_accepted": accepted["accepted"],
                "stale_selection_discarded": stale["discarded_sequence"],
                "missing_csrf_status": missing_csrf,
                "review_completed": completed["state"]["processes"]["103439/2023"]["completed"],
                "transfer_request_blocks": transfer_blocked,
                "fallback_port": fallback_port,
            }, ensure_ascii=False))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            server.workflow_state.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
