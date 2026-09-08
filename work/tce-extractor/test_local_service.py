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


def json_request(url, *, method="GET", payload=None, token=None, origin=None, host=None, range_header=None, cookie=None):
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
    if cookie is not None:
        headers["Cookie"] = cookie
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
            )
            self.assertEqual(status, 200)

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

    def test_dataset_prefers_the_current_incremental_publication(self):
        with running_server() as (root, server, base):
            publication = root / "publicacoes" / "7"
            publication.mkdir(parents=True)
            (root / "publicacao-atual.json").write_text(
                json.dumps({"schema_version": 1, "revision": 7}), encoding="utf-8"
            )
            dataset = {
                "schema_version": 1,
                "generated_at": "2026-09-08T12:00:00+00:00",
                "batch": {
                    "id": "publication-7",
                    "logical_sha256": "0" * 64,
                    "process_count": 0,
                    "record_count": 0,
                    "process_keys": [],
                },
                "records": [],
            }
            (publication / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://test-extension",
            )
            token = json.loads(pair_body)["token"]
            status, _headers, body = json_request(f"{base}/api/v1/dataset", token=token)
            payload = json.loads(body)
            self.assertEqual(status, 200)
            self.assertEqual(payload["revision"], 7)
            self.assertEqual(payload["dataset"]["batch"]["id"], "publication-7")

    def test_review_data_exposes_revision_and_supports_unchanged_poll(self):
        with running_server() as (root, server, base):
            publication = root / "publicacoes" / "7"
            publication.mkdir(parents=True)
            (root / "publicacao-atual.json").write_text(
                json.dumps({"schema_version": 1, "revision": 7}), encoding="utf-8"
            )
            review_data = {"live_revision": 7, "processes": [], "stats": {}}
            (publication / "review-data.json").write_text(json.dumps(review_data), encoding="utf-8")
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://test-extension",
            )
            token = json.loads(pair_body)["token"]
            status, _headers, body = json_request(f"{base}/api/v1/review-data?since=6", token=token)
            payload = json.loads(body)
            self.assertEqual(status, 200)
            self.assertFalse(payload["unchanged"])
            self.assertEqual(payload["revision"], 7)
            self.assertEqual(payload["data"]["live_revision"], 7)

            status, _headers, body = json_request(f"{base}/api/v1/review-data?since=7", token=token)
            payload = json.loads(body)
            self.assertEqual(status, 200)
            self.assertTrue(payload["unchanged"])
            self.assertNotIn("data", payload)

    def test_review_bootstrap_exchanges_fragment_code_for_authenticated_html_session(self):
        with running_server() as (root, server, base):
            publication = root / "publicacoes" / "1"
            publication.mkdir(parents=True)
            (root / "publicacao-atual.json").write_text(
                json.dumps({"schema_version": 1, "revision": 1}), encoding="utf-8"
            )
            (publication / "review-data.json").write_text(
                json.dumps({"live_revision": 1, "processes": [], "stats": {}}), encoding="utf-8"
            )

            status, _headers, body = json_request(f"{base}/review")
            self.assertEqual(status, 200)
            self.assertIn("review-bootstrap.js", body.decode("utf-8"))
            status, _headers, bootstrap = json_request(f"{base}/review-bootstrap.js")
            self.assertEqual(status, 200)
            self.assertIn("review-session", bootstrap.decode("utf-8"))

            status, headers, _body = json_request(
                f"{base}/api/v1/review-session",
                method="POST",
                payload={"code": server.review_bootstrap_code},
                origin=base,
            )
            self.assertEqual(status, 200)
            cookie = headers["Set-Cookie"].split(";", 1)[0]
            with self.assertRaises(HTTPError) as error:
                json_request(
                    f"{base}/api/v1/review-session",
                    method="POST",
                    payload={"code": server.review_bootstrap_code or "consumed"},
                    origin=base,
                )
            self.assertEqual(error.exception.code, 401)

            status, headers, body = json_request(f"{base}/review", cookie=cookie)
            self.assertEqual(status, 200)
            self.assertIn("api/v1/review-data", body.decode("utf-8"))
            self.assertNotIn("review-session", body.decode("utf-8"))
            self.assertIn("Content-Security-Policy", headers)

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
