import contextlib
from http.client import RemoteDisconnected
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from local_service import create_server  # noqa: E402


def json_request(url, *, method="GET", payload=None, token=None, origin=None, host=None, range_header=None):
    headers = {}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if origin is not None:
        headers["Origin"] = origin
    if host is not None:
        headers["Host"] = host
    if range_header is not None:
        headers["Range"] = range_header
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    with urlopen(Request(url, data=body, headers=headers, method=method), timeout=3) as response:
        return response.status, response.headers, response.read()


@contextlib.contextmanager
def running_server():
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        server = create_server(root, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            yield root, server, base
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            server.workflow_state.close()


class LocalServiceTests(unittest.TestCase):
    def test_private_state_requires_auth(self):
        with running_server() as (_root, _server, base):
            with self.assertRaises(HTTPError) as error:
                urlopen(f"{base}/api/v1/state", timeout=3)
            self.assertEqual(error.exception.code, 401)

    def test_health_is_public_and_does_not_expose_private_state(self):
        with running_server() as (_root, _server, base):
            status, _headers, body = json_request(f"{base}/api/v1/health")
            self.assertEqual(status, 200)
            payload = json.loads(body)
            self.assertEqual(payload["api_version"], 1)
            self.assertNotIn("processes", json.dumps(payload))

    def test_pairing_then_state_and_progress_conflict(self):
        with running_server() as (root, server, base):
            code = server.auth.issue_pairing_code()
            status, _headers, body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://test-extension",
            )
            self.assertEqual(status, 200)
            token = json.loads(body)["token"]

            status, _headers, body = json_request(
                f"{base}/api/v1/state?since=0", token=token
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["revision"], 0)

            status, _headers, body = json_request(
                f"{base}/api/v1/progress/103439%2F2023",
                method="PUT",
                payload={"completed": True, "expected_revision": 0},
                token=token,
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["revision"], 1)

            with self.assertRaises(HTTPError) as error:
                json_request(
                    f"{base}/api/v1/progress/103439%2F2023",
                    method="PUT",
                    payload={"completed": False, "expected_revision": 0},
                    token=token,
                )
            self.assertEqual(error.exception.code, 409)
            self.assertTrue((root / "progresso.json").is_file())

    def test_pdf_is_served_only_by_document_id_and_supports_range(self):
        with running_server() as (root, server, base):
            pdf = root / "sample.pdf"
            pdf.write_bytes(b"0123456789")
            (root / "evidencias-visuais.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "documents": {"doc-1": {"relative_path": "sample.pdf", "sha256": ""}},
                    "records": {},
                }),
                encoding="utf-8",
            )
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://test-extension",
            )
            token = json.loads(pair_body)["token"]

            status, headers, body = json_request(
                f"{base}/api/v1/pdf/doc-1", token=token, range_header="bytes=2-5"
            )
            self.assertEqual(status, 206)
            self.assertEqual(body, b"2345")
            self.assertEqual(headers["Content-Range"], "bytes 2-5/10")

            with self.assertRaises(HTTPError) as error:
                json_request(f"{base}/api/v1/pdf/../../sample.pdf", token=token)
            self.assertEqual(error.exception.code, 404)

            with self.assertRaises(HTTPError) as error:
                json_request(f"{base}/api/v1/pdf/unknown", token=token)
            self.assertEqual(error.exception.code, 404)

            with self.assertRaises(HTTPError) as error:
                json_request(f"{base}/api/v1/pdf/doc-1", token=token, range_header="bytes=99-100")
            self.assertEqual(error.exception.code, 416)


if __name__ == "__main__":
    unittest.main()
