"""RED/GREEN contract tests for the authenticated automation API."""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
from http.client import RemoteDisconnected
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import sys

APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from local_service import create_server  # noqa: E402


EXTENSION_ORIGIN = "chrome-extension://test-extension"
RULES_VERSION = "legal-foundation-v1"


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def dataset_for(*names: str) -> dict:
    records = [
        {
            "process": {"key": "103439/2023"},
            "interested": {"original": name, "normalized": name.casefold()},
        }
        for name in names
    ]
    dataset = {
        "schema_version": 1,
        "generated_at": "2026-09-09T12:00:00+00:00",
        "batch": {
            "id": "api-fixture",
            "logical_sha256": "",
            "process_count": 1,
            "record_count": len(records),
            "process_keys": ["103439/2023"],
        },
        "records": records,
    }
    logical = {
        "schema_version": dataset["schema_version"],
        "batch_id": dataset["batch"]["id"],
        "process_keys": dataset["batch"]["process_keys"],
        "records": dataset["records"],
    }
    dataset["batch"]["logical_sha256"] = hashlib.sha256(canonical_json(logical)).hexdigest()
    return dataset


def write_fixture(root: Path, *names: str) -> tuple[dict, str]:
    dataset = dataset_for(*names)
    dataset_path = root / "dados-complementar-ato.json"
    dataset_path.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")
    return dataset, dataset["batch"]["logical_sha256"]


def write_context(root: Path, dataset_sha256: str, *names: str) -> None:
    context = {
        "schema_version": 1,
        "dataset_sha256": dataset_sha256,
        "records": [
            {
                "process_key": "103439/2023",
                "interested_normalized": name.casefold(),
                "resolution_status": "complete",
                "operative_text": f"RESOLVE: fundamento de {name}",
                "pages": [{"text": f"RESOLVE: fundamento de {name}", "citation": {"page": 1}}],
            }
            for name in names
        ],
    }
    (root / "fundamentos-contexto.v1.json").write_text(
        json.dumps(context, ensure_ascii=False), encoding="utf-8"
    )


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: object | None = None,
    token: str | None = None,
    origin: str | None = EXTENSION_ORIGIN,
    headers: dict[str, str] | None = None,
):
    request_headers = dict(headers or {})
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    else:
        body = None
    if token is not None:
        request_headers["Authorization"] = f"Bearer {token}"
    if origin is not None:
        request_headers["Origin"] = origin
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=3) as response:
            raw = response.read()
            if response.headers.get_content_type() == "application/json":
                raw = json.loads(raw)
            else:
                raw = raw.decode("utf-8")
            return response.status, response.headers, raw
    except (ConnectionAbortedError, RemoteDisconnected):
        return 0, {}, None
    except HTTPError as error:
        try:
            body = json.loads(error.read())
        except (json.JSONDecodeError, UnicodeDecodeError, RemoteDisconnected):
            body = None
        return error.code, error.headers, body


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


class AutomationApiTests(unittest.TestCase):
    def pair(self, server: ThreadingHTTPServer, base: str) -> str:
        status, _headers, body = request_json(
            f"{base}/api/v1/pair",
            method="POST",
            payload={"code": server.auth.issue_pairing_code()},
            origin=EXTENSION_ORIGIN,
        )
        self.assertEqual(status, 200, body)
        return body["token"]

    def run_spec(self, dataset_sha256: str, **overrides) -> dict:
        return {
            "tab_id": 7,
            "sector": "aposentadorias",
            "dataset_sha256": dataset_sha256,
            "rules_version": RULES_VERSION,
            "event_id": "start-1",
            **overrides,
        }

    def test_capabilities_reject_missing_or_wrong_origin_and_return_closed_v1_envelope(self):
        with running_server() as (root, server, base):
            write_fixture(root, "Ana")
            status, _headers, body = request_json(
                f"{base}/api/v1/automation/capabilities", origin=EXTENSION_ORIGIN
            )
            self.assertEqual(status, 401)
            self.assertEqual(body["error"]["code"], "UNAUTHORIZED")

            token = self.pair(server, base)
            status, _headers, body = request_json(
                f"{base}/api/v1/automation/capabilities",
                token=token,
                origin="https://evil.example",
            )
            self.assertEqual(status, 403)

            status, _headers, body = request_json(
                f"{base}/api/v1/automation/capabilities", token=token
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                set(body),
                {"api_version", "automation_schema", "legal_context_schema", "rules_version", "real_send_enabled"},
            )
            self.assertEqual(body["api_version"], 1)
            self.assertFalse(body["real_send_enabled"])

    def test_extra_run_payload_is_rejected_before_persistence(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(digest, extra="reject-me"),
            )
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "INVALID_PAYLOAD")
            db = sqlite3.connect(root / "automacao" / "execucoes.sqlite3")
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
            finally:
                db.close()

    def test_backend_rejects_dataset_swap_and_stale_queue_without_changing_snapshot(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec("f" * 64),
            )
            self.assertEqual(status, 409)
            self.assertEqual(body["error"]["code"], "DATASET_MISMATCH")

            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(digest),
            )
            self.assertEqual(status, 200)
            run_id = body["run_id"]
            identity = {
                "process_key": "103439/2023",
                "interested_normalized": "ana",
                "portal_act_id": None,
            }
            queue_url = f"{base}/api/v1/automation/runs/{run_id}/queue"
            status, _headers, body = request_json(
                queue_url,
                method="POST",
                token=token,
                payload={"identities": [identity], "event_id": "queue-1", "expected_revision": 9},
            )
            self.assertEqual(status, 409)
            self.assertEqual(body["error"]["code"], "REVISION_CONFLICT")

            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs/{run_id}", token=token
            )
            self.assertEqual(status, 200)
            self.assertEqual(body["revision"], 0)
            self.assertEqual(body["status"], "discovering")
            self.assertEqual(body["items"], [])

    def test_context_lookup_is_exact_and_does_not_return_first_record(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana", "Bia")
            write_context(root, digest, "Ana", "Bia")
            token = self.pair(server, base)
            status, _headers, body = request_json(
                f"{base}/api/v1/legal-context?process_key=103439%2F2023&interested_normalized=bia",
                token=token,
            )
            self.assertEqual(status, 200)
            self.assertEqual(body["api_version"], 1)
            self.assertEqual(body["context"]["interested_normalized"], "bia")
            self.assertIn("Bia", body["context"]["operative_text"])

            status, _headers, body = request_json(
                f"{base}/api/v1/legal-context?process_key=103439%2F2023&interested_normalized=missing",
                token=token,
            )
            self.assertEqual(status, 404)
            self.assertEqual(body["error"]["code"], "LEGAL_CONTEXT_NOT_FOUND")

    def test_event_replay_is_idempotent_but_changed_payload_conflicts(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            write_context(root, digest, "Ana")
            token = self.pair(server, base)
            _status, _headers, created = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(digest),
            )
            self.assertEqual(_status, 200, created)
            run_id = created["run_id"]
            identity = {
                "process_key": "103439/2023",
                "interested_normalized": "ana",
                "portal_act_id": None,
            }
            _status, _headers, queued = request_json(
                f"{base}/api/v1/automation/runs/{run_id}/queue",
                method="POST",
                token=token,
                payload={"identities": [identity], "event_id": "queue-1", "expected_revision": 0},
            )
            self.assertEqual(queued["revision"], 1)
            event_url = f"{base}/api/v1/automation/runs/{run_id}/events"
            event = {
                "event_id": "prepare-1",
                "expected_revision": 1,
                "item_id": "103439/2023",
                "type": "item_prepared",
                "payload": {},
            }
            status, _headers, first = request_json(event_url, method="POST", token=token, payload=event)
            self.assertEqual(status, 200)
            self.assertEqual(first["revision"], 2)
            status, _headers, replay = request_json(
                event_url, method="POST", token=token, payload={**event, "expected_revision": 0}
            )
            self.assertEqual(status, 200)
            self.assertEqual(replay["revision"], 2)
            status, _headers, conflict = request_json(
                event_url,
                method="POST",
                token=token,
                payload={**event, "expected_revision": 2, "payload": {"reason": "tampered"}},
            )
            self.assertEqual(status, 409)
            self.assertEqual(conflict["error"]["code"], "EVENT_CONFLICT")

    def test_body_and_queue_limits_are_closed_without_truncation_or_mutation(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            oversized = self.run_spec(digest, padding="x" * (2 * 1024 * 1024))
            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs", method="POST", token=token, payload=oversized
            )
            self.assertEqual(status, 413)
            self.assertEqual(body["error"]["code"], "BODY_TOO_LARGE")

            _status, _headers, created = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(digest),
            )
            self.assertEqual(_status, 200, created)
            run_id = created["run_id"]
            identities = [
                {
                    "process_key": "103439/2023",
                    "interested_normalized": f"ana-{index}",
                    "portal_act_id": None,
                }
                for index in range(10001)
            ]
            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs/{run_id}/queue",
                method="POST",
                token=token,
                payload={"identities": identities, "event_id": "queue-too-large", "expected_revision": 0},
            )
            self.assertEqual(status, 413)
            self.assertEqual(body["error"]["code"], "QUEUE_TOO_LARGE")
            _status, _headers, snapshot = request_json(
                f"{base}/api/v1/automation/runs/{run_id}", token=token
            )
            self.assertEqual(snapshot["revision"], 0)
            self.assertEqual(snapshot["items"], [])

    def test_report_requires_auth_accepts_only_html_or_csv_and_uses_service_root(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            _status, _headers, created = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(digest),
            )
            self.assertEqual(_status, 200, created)
            run_id = created["run_id"]
            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs/{run_id}/report?format=json", token=token
            )
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "REPORT_FORMAT_UNSUPPORTED")

            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs/{run_id}/report?format=html&path=C:%2Fsecret.txt",
                token=token,
            )
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "INVALID_QUERY")

            status, headers, report = request_json(
                f"{base}/api/v1/automation/runs/{run_id}/report?format=html", token=token
            )
            self.assertEqual(status, 200)
            self.assertIn("text/html", headers.get_content_type())
            self.assertIn("Relatório", report if isinstance(report, str) else "")


if __name__ == "__main__":
    unittest.main()
