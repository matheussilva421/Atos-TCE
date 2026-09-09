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
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import sys

APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from local_service import create_server  # noqa: E402
from qualification import expected_qualification_versions  # noqa: E402


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
                "dataset_sha256": dataset_sha256,
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


def write_qualification(root: Path) -> None:
    path = root / "automacao" / "qualificacao.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "qualified",
                "versions": expected_qualification_versions("1.1.0"),
                "fixture_hashes": ["a" * 64],
                "real_event_id": "real-event-2026-09-09",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
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
def running_server(*, automation_pilot: bool = False):
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        server = create_server(root, port=0, automation_pilot=automation_pilot)
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

    def test_send_confirmed_renders_report_before_returning_to_caller(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            status, _headers, created = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(digest, event_id="report-before-next-start"),
            )
            self.assertEqual(status, 200, created)
            run_id = created["run_id"]
            identity = {
                "process_key": "103439/2023",
                "interested_normalized": "ana",
                "portal_act_id": None,
            }
            status, _headers, queued = request_json(
                f"{base}/api/v1/automation/runs/{run_id}/queue",
                method="POST",
                token=token,
                payload={"identities": [identity], "event_id": "report-before-next-queue", "expected_revision": 0},
            )
            self.assertEqual(status, 200, queued)
            event_url = f"{base}/api/v1/automation/runs/{run_id}/events"
            revision = queued["revision"]
            for event_id, event_type, payload in (
                ("report-before-next-prepared", "item_prepared", {"reason": "ready"}),
                ("report-before-next-filled", "fields_verified", {"field_results": {}, "rereads": []}),
                (
                    "report-before-next-intent",
                    "send_intent",
                    {"expected_fields_hash": "a" * 64, "command_id": "report-before-next-command", "expires_at": 4102444800000},
                ),
            ):
                status, _headers, result = request_json(
                    event_url,
                    method="POST",
                    token=token,
                    payload={
                        "event_id": event_id,
                        "expected_revision": revision,
                        "item_id": "103439/2023",
                        "type": event_type,
                        "payload": payload,
                    },
                )
                self.assertEqual(status, 200, result)
                revision = result["revision"]

            with patch("local_service.render_run_reports") as render_reports:
                status, _headers, confirmed = request_json(
                    event_url,
                    method="POST",
                    token=token,
                    payload={
                        "event_id": "report-before-next-confirmed",
                        "expected_revision": revision,
                        "item_id": "103439/2023",
                        "type": "send_confirmed",
                        "payload": {
                            "identity": identity,
                            "fields": {"fundamento_legal": "art. 1"},
                            "origin": "portal",
                            "timestamp": "2026-09-09T12:00:00+00:00",
                            "citations": ["fixture:art-1"],
                        },
                    },
                )
            self.assertEqual(status, 200, confirmed)
            render_reports.assert_called_once()
            self.assertEqual(render_reports.call_args.args[1], run_id)

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
                {
                    "api_version",
                    "automation_schema",
                    "legal_context_schema",
                    "rules_version",
                    "real_send_enabled",
                    "pilot_enabled",
                    "pilot_consumes_remaining",
                },
            )
            self.assertEqual(body["api_version"], 1)
            self.assertFalse(body["real_send_enabled"])
            self.assertFalse(body["pilot_enabled"])
            self.assertFalse(body["pilot_consumes_remaining"])

    def test_qualified_batch_requires_explicit_activation_and_matching_versions(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture(root, "Ana")
            write_qualification(root)

            server = create_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                token = self.pair(server, base)
                status, _headers, capabilities = request_json(
                    f"{base}/api/v1/automation/capabilities", token=token
                )
                self.assertEqual(status, 200, capabilities)
                self.assertFalse(capabilities["real_send_enabled"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_explicitly_qualified_batch_can_consume_one_prepared_command(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _dataset, digest = write_fixture(root, "Ana")
            write_qualification(root)
            server = create_server(root, port=0, enable_real_send=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                token = self.pair(server, base)
                status, _headers, created = request_json(
                    f"{base}/api/v1/automation/runs",
                    method="POST",
                    token=token,
                    payload=self.run_spec(digest, event_id="qualified-batch-start"),
                )
                self.assertEqual(status, 200, created)
                run_id = created["run_id"]
                identity = {
                    "process_key": "103439/2023",
                    "interested_normalized": "ana",
                    "portal_act_id": None,
                }
                status, _headers, queued = request_json(
                    f"{base}/api/v1/automation/runs/{run_id}/queue",
                    method="POST",
                    token=token,
                    payload={
                        "identities": [identity],
                        "event_id": "qualified-batch-queue",
                        "expected_revision": 0,
                    },
                )
                self.assertEqual(status, 200, queued)
                revision = queued["revision"]
                events_url = f"{base}/api/v1/automation/runs/{run_id}/events"
                for event_id, event_type, payload in (
                    ("qualified-batch-prepared", "item_prepared", {"reason": "ready"}),
                    ("qualified-batch-verified", "fields_verified", {"field_results": {}, "rereads": []}),
                    (
                        "qualified-batch-intent",
                        "send_intent",
                        {
                            "expected_fields_hash": "a" * 64,
                            "command_id": "qualified-batch-command",
                            "expires_at": 4102444800000,
                        },
                    ),
                ):
                    status, _headers, result = request_json(
                        events_url,
                        method="POST",
                        token=token,
                        payload={
                            "event_id": event_id,
                            "expected_revision": revision,
                            "item_id": "103439/2023",
                            "type": event_type,
                            "payload": payload,
                        },
                    )
                    self.assertEqual(status, 200, result)
                    revision = result["revision"]

                status, _headers, consumed = request_json(
                    f"{base}/api/v1/automation/runs/{run_id}/commands/qualified-batch-command/consume",
                    method="POST",
                    token=token,
                    payload={"expected_revision": revision},
                )
                self.assertEqual(status, 200, consumed)
                self.assertTrue(consumed["dispatch_allowed"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

            server = create_server(root, port=0, enable_real_send=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                token = self.pair(server, base)
                status, _headers, capabilities = request_json(
                    f"{base}/api/v1/automation/capabilities", token=token
                )
                self.assertEqual(status, 200, capabilities)
                self.assertTrue(capabilities["real_send_enabled"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_pilot_run_requires_explicit_service_flag(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(
                    digest,
                    mode="pilot",
                    pilot_identity={"process_key": "103439/2023", "interested_normalized": "ana", "portal_act_id": None},
                    event_id="pilot-without-flag",
                ),
            )
            self.assertEqual(status, 409, body)
            self.assertEqual(body["error"]["code"], "PILOT_DISABLED")

        with running_server(automation_pilot=True) as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            status, _headers, capabilities = request_json(
                f"{base}/api/v1/automation/capabilities", token=token
            )
            self.assertEqual(status, 200, capabilities)
            self.assertTrue(capabilities["pilot_enabled"])
            self.assertTrue(capabilities["pilot_consumes_remaining"])
            status, _headers, created = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(
                    digest,
                    mode="pilot",
                    pilot_identity={"process_key": "103439/2023", "interested_normalized": "ana", "portal_act_id": None},
                    event_id="pilot-with-flag",
                ),
            )
            self.assertEqual(status, 200, created)

    def test_pilot_allows_one_command_and_does_not_reset_after_service_restart(self):
        def seed_intent(base, token, run_id, prefix):
            identity = {
                "process_key": "103439/2023",
                "interested_normalized": "ana",
                "portal_act_id": None,
            }
            status, _headers, queued = request_json(
                f"{base}/api/v1/automation/runs/{run_id}/queue",
                method="POST",
                token=token,
                payload={"identities": [identity], "event_id": f"{prefix}-queue", "expected_revision": 0},
            )
            self.assertEqual(status, 200, queued)
            revision = queued["revision"]
            event_url = f"{base}/api/v1/automation/runs/{run_id}/events"
            for event_id, event_type, payload in (
                (f"{prefix}-prepared", "item_prepared", {"reason": "prepared"}),
                (f"{prefix}-verified", "fields_verified", {"field_results": {}, "rereads": []}),
                (
                    f"{prefix}-intent",
                    "send_intent",
                    {"expected_fields_hash": "a" * 64, "command_id": f"{prefix}-command", "expires_at": 4102444800000},
                ),
            ):
                status, _headers, result = request_json(
                    event_url,
                    method="POST",
                    token=token,
                    payload={
                        "event_id": event_id,
                        "expected_revision": revision,
                        "item_id": "103439/2023",
                        "type": event_type,
                        "payload": payload,
                    },
                )
                self.assertEqual(status, 200, result)
                revision = result["revision"]
            return revision, f"{base}/api/v1/automation/runs/{run_id}/commands/{prefix}-command/consume"

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture(root, "Ana")
            server = create_server(root, port=0, automation_pilot=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                token = self.pair(server, base)
                _dataset, digest = write_fixture(root, "Ana")
                status, _headers, created = request_json(
                    f"{base}/api/v1/automation/runs",
                    method="POST",
                    token=token,
                    payload=self.run_spec(
                        digest,
                        mode="pilot",
                        pilot_identity={"process_key": "103439/2023", "interested_normalized": "ana", "portal_act_id": None},
                        event_id="pilot-first-start",
                    ),
                )
                self.assertEqual(status, 200, created)
                revision, consume_url = seed_intent(base, token, created["run_id"], "pilot-first")
                status, _headers, consumed = request_json(
                    consume_url,
                    method="POST",
                    token=token,
                    payload={"expected_revision": revision},
                )
                self.assertEqual(status, 200, consumed)
                self.assertTrue(consumed["dispatch_allowed"])
                status, _headers, stopped = request_json(
                    f"{base}/api/v1/automation/runs/{created['run_id']}/control",
                    method="POST",
                    token=token,
                    payload={"action": "stop", "event_id": "pilot-first-stop", "expected_revision": consumed["revision"]},
                )
                self.assertEqual(status, 200, stopped)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

            server = create_server(root, port=0, automation_pilot=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                token = self.pair(server, base)
                _dataset, digest = write_fixture(root, "Ana")
                status, _headers, created = request_json(
                    f"{base}/api/v1/automation/runs",
                    method="POST",
                    token=token,
                    payload=self.run_spec(
                        digest,
                        mode="pilot",
                        pilot_identity={"process_key": "103439/2023", "interested_normalized": "ana", "portal_act_id": None},
                        event_id="pilot-second-start",
                    ),
                )
                self.assertEqual(status, 200, created)
                revision, consume_url = seed_intent(base, token, created["run_id"], "pilot-second")
                status, _headers, body = request_json(
                    consume_url,
                    method="POST",
                    token=token,
                    payload={"expected_revision": revision},
                )
                self.assertEqual(status, 409, body)
                self.assertEqual(body["error"]["code"], "PILOT_EXHAUSTED")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

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

    def test_run_mode_must_be_a_supported_scalar(self):
        with running_server(automation_pilot=True) as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(digest, mode=[]),
            )
            self.assertEqual(status, 400, body)
            self.assertEqual(body["error"]["code"], "INVALID_MODE")

    def test_run_creation_retries_are_idempotent_and_conflicting_payloads_rejected(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            run_url = f"{base}/api/v1/automation/runs"

            status, _headers, first = request_json(
                run_url,
                method="POST",
                token=token,
                payload=self.run_spec(digest),
            )
            self.assertEqual(status, 200, first)

            status, _headers, replay = request_json(
                run_url,
                method="POST",
                token=token,
                payload=self.run_spec(digest),
            )
            self.assertEqual(status, 200, replay)
            self.assertEqual(replay, first)

            status, _headers, conflict = request_json(
                run_url,
                method="POST",
                token=token,
                payload=self.run_spec(digest, sector="outro-setor"),
            )
            self.assertEqual(status, 409)
            self.assertEqual(conflict["error"]["code"], "EVENT_CONFLICT")

            db = sqlite3.connect(root / "automacao" / "execucoes.sqlite3")
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 1)
            finally:
                db.close()

    def test_run_creation_replay_precedes_current_dataset_validation(self):
        with running_server() as (root, server, base):
            _dataset, original_digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            run_url = f"{base}/api/v1/automation/runs"
            original_payload = self.run_spec(original_digest)

            status, _headers, first = request_json(
                run_url, method="POST", token=token, payload=original_payload
            )
            self.assertEqual(status, 200, first)

            _dataset, replacement_digest = write_fixture(root, "Bia")
            self.assertNotEqual(replacement_digest, original_digest)

            status, _headers, replay = request_json(
                run_url, method="POST", token=token, payload=original_payload
            )
            self.assertEqual(status, 200, replay)
            self.assertEqual(replay, first)

            status, _headers, conflict = request_json(
                run_url,
                method="POST",
                token=token,
                payload=self.run_spec(original_digest, sector="outro-setor"),
            )
            self.assertEqual(status, 409, conflict)
            self.assertEqual(conflict["error"]["code"], "EVENT_CONFLICT")

            status, _headers, unknown = request_json(
                run_url,
                method="POST",
                token=token,
                payload=self.run_spec(original_digest, event_id="start-after-dataset-swap"),
            )
            self.assertEqual(status, 409, unknown)
            self.assertEqual(unknown["error"]["code"], "DATASET_MISMATCH")

    def test_queue_replay_precedes_current_dataset_validation_and_unknown_event_is_rejected(self):
        with running_server() as (root, server, base):
            _dataset, original_digest = write_fixture(root, "Ana")
            write_context(root, original_digest, "Ana")
            token = self.pair(server, base)
            _status, _headers, created = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(original_digest),
            )
            self.assertEqual(_status, 200, created)
            run_id = created["run_id"]
            identity = {
                "process_key": "103439/2023",
                "interested_normalized": "ana",
                "portal_act_id": None,
            }
            queue_url = f"{base}/api/v1/automation/runs/{run_id}/queue"
            original_payload = {
                "identities": [identity],
                "event_id": "queue-replay-1",
                "expected_revision": 0,
            }
            status, _headers, first = request_json(
                queue_url, method="POST", token=token, payload=original_payload
            )
            self.assertEqual(status, 200, first)

            _dataset, replacement_digest = write_fixture(root, "Bia")
            self.assertNotEqual(replacement_digest, original_digest)

            status, _headers, replay = request_json(
                queue_url, method="POST", token=token, payload=original_payload
            )
            self.assertEqual(status, 200, replay)
            self.assertEqual(replay, first)

            changed_identity = {**identity, "interested_normalized": "bia"}
            status, _headers, conflict = request_json(
                queue_url,
                method="POST",
                token=token,
                payload={**original_payload, "identities": [changed_identity]},
            )
            self.assertEqual(status, 409, conflict)
            self.assertEqual(conflict["error"]["code"], "EVENT_CONFLICT")

            status, _headers, unknown = request_json(
                queue_url,
                method="POST",
                token=token,
                payload={
                    "identities": [changed_identity],
                    "event_id": "queue-never-persisted",
                    "expected_revision": 1,
                },
            )
            self.assertEqual(status, 409, unknown)
            self.assertEqual(unknown["error"]["code"], "DATASET_MISMATCH")

    def test_event_payloads_are_discriminated_and_controls_are_closed(self):
        cases = [
            ("item_prepared", [], {"reason": "prepared", "unexpected": True}),
            (
                "fields_verified",
                [("item_prepared", {"reason": "prepared"})],
                {"field_results": {}, "rereads": [], "unexpected": True},
            ),
            (
                "send_intent",
                [
                    ("item_prepared", {"reason": "prepared"}),
                    ("fields_verified", {"field_results": {}, "rereads": []}),
                ],
                {"expected_fields_hash": "a" * 64, "unexpected": True},
            ),
            (
                "send_confirmed",
                [
                    ("item_prepared", {"reason": "prepared"}),
                    ("fields_verified", {"field_results": {}, "rereads": []}),
                    ("send_intent", {"expected_fields_hash": "a" * 64}),
                ],
                {
                    "identity": {"process_key": "103439/2023"},
                    "origin": "portal",
                    "timestamp": "2026-09-09T12:00:00Z",
                    "fields": {"cargo": "servidora"},
                    "citations": [{"reference": "act-1"}],
                    "unexpected": True,
                },
            ),
            ("item_pending", [], {"reason": "review", "unexpected": True}),
            ("item_failed", [], {"error": "failed", "unexpected": True}),
            (
                "send_unconfirmed",
                [
                    ("item_prepared", {"reason": "prepared"}),
                    ("fields_verified", {"field_results": {}, "rereads": []}),
                    ("send_intent", {"expected_fields_hash": "a" * 64}),
                ],
                {"reason": "uncertain", "rereads": [], "unexpected": True},
            ),
        ]
        for event_type, seeds, invalid_payload in cases:
            with self.subTest(event_type=event_type):
                with running_server() as (root, server, base):
                    _dataset, digest = write_fixture(root, "Ana")
                    write_context(root, digest, "Ana")
                    token = self.pair(server, base)
                    _status, _headers, created = request_json(
                        f"{base}/api/v1/automation/runs",
                        method="POST",
                        token=token,
                        payload=self.run_spec(digest, event_id=f"start-{event_type}"),
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
                        payload={
                            "identities": [identity],
                            "event_id": f"queue-{event_type}",
                            "expected_revision": 0,
                        },
                    )
                    self.assertEqual(_status, 200, queued)
                    revision = queued["revision"]
                    event_url = f"{base}/api/v1/automation/runs/{run_id}/events"
                    for index, (seed_type, seed_payload) in enumerate(seeds):
                        if seed_type == "send_intent":
                            seed_payload = {
                                **seed_payload,
                                "command_id": f"command-seed-{event_type}",
                                "expires_at": 4102444800,
                            }
                        _status, _headers, seeded = request_json(
                            event_url,
                            method="POST",
                            token=token,
                            payload={
                                "event_id": f"seed-{event_type}-{index}",
                                "expected_revision": revision,
                                "item_id": "103439/2023",
                                "type": seed_type,
                                "payload": seed_payload,
                            },
                        )
                        self.assertEqual(_status, 200, seeded)
                        revision = seeded["revision"]
                    status, _headers, body = request_json(
                        event_url,
                        method="POST",
                        token=token,
                        payload={
                            "event_id": f"invalid-{event_type}",
                            "expected_revision": revision,
                            "item_id": "103439/2023",
                            "type": event_type,
                            "payload": invalid_payload,
                        },
                    )
                    self.assertEqual(status, 400, body)
                    self.assertEqual(body["error"]["code"], "INVALID_EVENT", body)

    def test_control_event_payloads_reject_nonempty_payloads(self):
        for event_type, seeds in (
            ("run_paused", []),
            ("run_resumed", [("run_paused", None)]),
            ("run_stopped", []),
            ("run_completed", []),
        ):
            with self.subTest(event_type=event_type):
                with running_server() as (root, server, base):
                    _dataset, digest = write_fixture(root, "Ana")
                    token = self.pair(server, base)
                    _status, _headers, created = request_json(
                        f"{base}/api/v1/automation/runs",
                        method="POST",
                        token=token,
                        payload=self.run_spec(digest, event_id=f"start-{event_type}"),
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
                        payload={
                            "identities": [] if event_type == "run_completed" else [identity],
                            "event_id": f"queue-{event_type}",
                            "expected_revision": 0,
                        },
                    )
                    self.assertEqual(_status, 200, queued)
                    revision = queued["revision"]
                    event_url = f"{base}/api/v1/automation/runs/{run_id}/events"
                    for index, (seed_type, seed_payload) in enumerate(seeds):
                        _status, _headers, seeded = request_json(
                            event_url,
                            method="POST",
                            token=token,
                            payload={
                                "event_id": f"seed-{event_type}-{index}",
                                "expected_revision": revision,
                                "item_id": None,
                                "type": seed_type,
                                "payload": seed_payload or {},
                            },
                        )
                        self.assertEqual(_status, 200, seeded)
                        revision = seeded["revision"]
                    status, _headers, body = request_json(
                        event_url,
                        method="POST",
                        token=token,
                        payload={
                            "event_id": f"invalid-{event_type}",
                            "expected_revision": revision,
                            "item_id": None,
                            "type": event_type,
                            "payload": {"reason": "must-reject"},
                        },
                    )
                    self.assertEqual(status, 400, body)
                    self.assertEqual(body["error"]["code"], "INVALID_EVENT", body)

                    status, _headers, body = request_json(
                        event_url,
                        method="POST",
                        token=token,
                        payload={
                            "event_id": f"invalid-item-{event_type}",
                            "expected_revision": revision,
                            "item_id": "103439/2023",
                            "type": event_type,
                            "payload": {},
                        },
                    )
                    self.assertEqual(status, 400, body)
                    self.assertEqual(body["error"]["code"], "INVALID_EVENT", body)

    def test_send_confirmed_requires_nonempty_proof_fields(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            _status, _headers, created = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(digest, event_id="start-confirmed-proof"),
            )
            self.assertEqual(_status, 200, created)
            run_id = created["run_id"]
            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs/{run_id}/events",
                method="POST",
                token=token,
                payload={
                    "event_id": "confirmed-proof-1",
                    "expected_revision": 0,
                    "item_id": "103439/2023",
                    "type": "send_confirmed",
                    "payload": {
                        "identity": {
                            "process_key": "103439/2023",
                            "interested_normalized": "ana",
                            "portal_act_id": None,
                        },
                        "origin": "portal",
                        "timestamp": "2026-09-09T12:00:00Z",
                        "fields": {},
                        "citations": [],
                    },
                },
            )
            self.assertEqual(status, 400, body)
            self.assertEqual(body["error"]["code"], "INVALID_EVENT", body)

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
            self.assertEqual(body["error"]["code"], "IDENTITY_NOT_IN_DATASET")

    def test_context_lookup_canonicalizes_and_requires_dataset_identity_and_record_hash(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            write_context(root, digest, "Ana", "Bia")
            token = self.pair(server, base)

            status, _headers, body = request_json(
                f"{base}/api/v1/legal-context?process_key=103439%20%2F%202023&interested_normalized=Ana%20",
                token=token,
            )
            self.assertEqual(status, 200, body)
            self.assertEqual(body["context"]["process_key"], "103439/2023")
            self.assertEqual(body["context"]["interested_normalized"], "ana")

            status, _headers, body = request_json(
                f"{base}/api/v1/legal-context?process_key=103439%2F2023&interested_normalized=bia",
                token=token,
            )
            self.assertEqual(status, 404)
            self.assertEqual(body["error"]["code"], "IDENTITY_NOT_IN_DATASET")

            context_path = root / "fundamentos-contexto.v1.json"
            context = json.loads(context_path.read_text(encoding="utf-8"))
            context["records"][0].pop("dataset_sha256")
            context_path.write_text(json.dumps(context), encoding="utf-8")
            status, _headers, body = request_json(
                f"{base}/api/v1/legal-context?process_key=103439%2F2023&interested_normalized=ana",
                token=token,
            )
            self.assertEqual(status, 500)
            self.assertEqual(body["error"]["code"], "LEGAL_CONTEXT_INVALID")

            context["records"][0]["dataset_sha256"] = "f" * 64
            context_path.write_text(json.dumps(context), encoding="utf-8")
            status, _headers, body = request_json(
                f"{base}/api/v1/legal-context?process_key=103439%2F2023&interested_normalized=ana",
                token=token,
            )
            self.assertEqual(status, 409)
            self.assertEqual(body["error"]["code"], "CONTEXT_DATASET_MISMATCH")

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
                "payload": {"reason": "prepared"},
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

    def test_common_run_cannot_consume_a_send_command_when_real_send_is_disabled(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            status, _headers, created = request_json(
                f"{base}/api/v1/automation/runs",
                method="POST",
                token=token,
                payload=self.run_spec(digest, event_id="start-send-gate"),
            )
            self.assertEqual(status, 200, created)
            run_id = created["run_id"]
            identity = {
                "process_key": "103439/2023",
                "interested_normalized": "ana",
                "portal_act_id": None,
            }
            event_url = f"{base}/api/v1/automation/runs/{run_id}/events"
            status, _headers, queued = request_json(
                f"{base}/api/v1/automation/runs/{run_id}/queue",
                method="POST",
                token=token,
                payload={"identities": [identity], "event_id": "queue-send-gate", "expected_revision": 0},
            )
            self.assertEqual(status, 200, queued)
            revision = queued["revision"]
            seeds = [
                ("prepared-send-gate", "item_prepared", {"reason": "prepared"}),
                ("verified-send-gate", "fields_verified", {"field_results": {}, "rereads": []}),
                (
                    "intent-send-gate",
                    "send_intent",
                    {"expected_fields_hash": "a" * 64, "command_id": "command-send-gate", "expires_at": 4102444800000},
                ),
            ]
            for event_id, event_type, payload in seeds:
                status, _headers, result = request_json(
                    event_url,
                    method="POST",
                    token=token,
                    payload={
                        "event_id": event_id,
                        "expected_revision": revision,
                        "item_id": "103439/2023",
                        "type": event_type,
                        "payload": payload,
                    },
                )
                self.assertEqual(status, 200, result)
                revision = result["revision"]

            status, _headers, body = request_json(
                f"{base}/api/v1/automation/runs/{run_id}/commands/command-send-gate/consume",
                method="POST",
                token=token,
                payload={"expected_revision": revision},
            )
            self.assertEqual(status, 409, body)
            self.assertEqual(body["error"]["code"], "REAL_SEND_DISABLED")

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

    def test_history_requires_auth_paginates_runs_and_events_without_run_payloads(self):
        with running_server() as (root, server, base):
            _dataset, digest = write_fixture(root, "Ana")
            token = self.pair(server, base)
            history_url = f"{base}/api/v1/automation/runs"

            unauthorized_status, _headers, unauthorized = request_json(history_url)
            self.assertEqual(unauthorized_status, 401)
            self.assertEqual(unauthorized["error"]["code"], "UNAUTHORIZED")

            created_ids = []
            for index in range(2):
                status, _headers, created = request_json(
                    history_url,
                    method="POST",
                    token=token,
                    payload=self.run_spec(digest, event_id=f"history-start-{index}"),
                )
                self.assertEqual(status, 200, created)
                created_ids.append(created["run_id"])
                if index == 0:
                    status, _headers, stopped = request_json(
                        f"{history_url}/{created['run_id']}/control",
                        method="POST",
                        token=token,
                        payload={"action": "stop", "event_id": "history-stop", "expected_revision": 0},
                    )
                    self.assertEqual(status, 200, stopped)

            status, _headers, first_page = request_json(
                f"{history_url}?limit=1", token=token
            )
            self.assertEqual(status, 200, first_page)
            self.assertEqual(first_page["api_version"], 1)
            self.assertEqual(len(first_page["runs"]), 1)
            self.assertIsNotNone(first_page["next_cursor"])
            self.assertIn("spec", first_page["runs"][0])
            self.assertNotIn("items", first_page["runs"][0])
            self.assertNotIn("token", json.dumps(first_page, ensure_ascii=False).lower())

            status, _headers, second_page = request_json(
                f"{history_url}?limit=1&before={first_page['next_cursor']}", token=token
            )
            self.assertEqual(status, 200, second_page)
            self.assertEqual(len(second_page["runs"]), 1)
            self.assertNotEqual(first_page["runs"][0]["run_id"], second_page["runs"][0]["run_id"])
            self.assertEqual(set(created_ids), {first_page["runs"][0]["run_id"], second_page["runs"][0]["run_id"]})

            run_id = first_page["runs"][0]["run_id"]
            status, _headers, queued = request_json(
                f"{history_url}/{run_id}/queue",
                method="POST",
                token=token,
                payload={
                    "identities": [{
                        "process_key": "103439/2023",
                        "interested_normalized": "ana",
                        "portal_act_id": None,
                    }],
                    "event_id": "history-queue",
                    "expected_revision": 0,
                },
            )
            self.assertEqual(status, 200, queued)
            status, _headers, paused = request_json(
                f"{history_url}/{run_id}/control",
                method="POST",
                token=token,
                payload={"action": "pause", "event_id": "history-pause", "expected_revision": 1},
            )
            self.assertEqual(status, 200, paused)

            events_url = f"{history_url}/{run_id}/events"
            unauthorized_status, _headers, unauthorized = request_json(events_url)
            self.assertEqual(unauthorized_status, 401)
            self.assertEqual(unauthorized["error"]["code"], "UNAUTHORIZED")

            status, _headers, event_page = request_json(
                f"{events_url}?after=0&limit=1", token=token
            )
            self.assertEqual(status, 200, event_page)
            self.assertEqual(len(event_page["events"]), 1)
            self.assertTrue(event_page["has_more"])
            self.assertIsNotNone(event_page["next_after"])

            status, _headers, tail = request_json(
                f"{events_url}?after={event_page['next_after']}&limit=100", token=token
            )
            self.assertEqual(status, 200, tail)
            self.assertEqual(len(tail["events"]), 1)
            self.assertFalse(tail["has_more"])


if __name__ == "__main__":
    unittest.main()
