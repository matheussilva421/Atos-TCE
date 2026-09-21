"""Tests for trusted extension registration, Mesa sessions and the authenticated command API.

Covers automatic trusted extension registration, bearer tokens that survive
server restarts, a one-time Mesa bootstrap token and fail-closed same-origin
validation for every state-changing route.
"""

import json
import sqlite3
import threading
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from app.api.bridge import Bridge, TRUSTED_EXTENSION_ID, hash_token
from app.api.server import serve
from app.core.store import Store

EXTENSION_ORIGIN = f"chrome-extension://{TRUSTED_EXTENSION_ID}"


class BridgeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name) / "data"
        self.store = Store.open(self.data_root / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.servers: list = []
        self.bridge = Bridge(bootstrap_token="bootstrap-token")
        self.server = self.start_server(self.bridge)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def start_server(self, bridge):
        server = serve(self.store, self.data_root, port=0, bridge=bridge)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.servers.append(server)
        return server

    # ---------------------------------------------------------------- helpers

    def call(self, path, method="GET", headers=None, body=None, opener=None):
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self.base + path, data=payload, method=method)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        send = opener.open if opener is not None else urlopen
        try:
            with send(request, timeout=10) as response:
                raw = response.read()
                return response.status, dict(response.headers), raw
        except HTTPError as error:
            raw = error.read()
            headers_out = dict(error.headers)
            code = error.code
            error.close()
            return code, headers_out, raw

    def call_json(self, path, *args, **kwargs):
        status, headers, raw = self.call(path, *args, **kwargs)
        return status, headers, (json.loads(raw.decode("utf-8")) if raw else None)

    def extension_headers(self, token, client_id="extension-test"):
        return {
            "Authorization": f"Bearer {token}",
            "X-TCE-Client": client_id,
            "Origin": EXTENSION_ORIGIN,
        }

    def register(self, client_id="extension-test", origin=EXTENSION_ORIGIN):
        return self.call_json(
            "/api/v1/bridge/register",
            method="POST",
            headers={"Origin": origin},
            body={"client_id": client_id},
        )

    def registered_token(self, client_id="extension-test"):
        status, _headers, payload = self.register(client_id=client_id)
        self.assertEqual(status, 200, payload)
        return payload["token"]

    def mesa_opener(self):
        """Return an opener holding a valid Mesa session cookie."""

        jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(jar))
        status, _headers, payload = self.call_json(
            "/api/v1/session/bootstrap",
            method="POST",
            headers={"Origin": self.base},
            body={"token": self.bridge.bootstrap_token},
            opener=opener,
        )
        self.assertEqual(status, 200, payload)
        return opener

    def mesa_headers(self):
        return {"Origin": self.base}


class ExtensionRegistrationTests(BridgeTestCase):
    def test_trusted_extension_registers_without_a_code(self):
        status, _headers, payload = self.register()

        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["token"])
        self.assertEqual(payload["client_id"], "extension-test")

    def test_registration_token_authenticates_immediately(self):
        _status, _headers, registered = self.register()

        status, _headers, payload = self.call_json(
            "/api/v1/bridge/status",
            headers=self.extension_headers(registered["token"]),
        )

        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["paired"])

    def test_registration_rejects_an_untrusted_extension_origin(self):
        status, _headers, payload = self.register(
            origin="chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "extension_not_trusted")
        self.assertEqual(self.store.list_bridge_clients(), [])

    def test_registration_persists_only_the_token_hash(self):
        _status, _headers, payload = self.register()
        token = payload["token"]

        row = self.store.list_bridge_clients()[0]
        self.assertEqual(row["token_hash"], hash_token(token))
        self.assertNotIn(token.encode("utf-8"), (self.data_root / "atos-tce.db").read_bytes())

    def test_re_registration_rotates_a_rejected_credential(self):
        _status, _headers, first = self.register()
        _status, _headers, second = self.register()

        self.assertNotEqual(first["token"], second["token"])

        status, _headers, _payload = self.call_json(
            "/api/v1/bridge/status",
            headers=self.extension_headers(first["token"]),
        )
        self.assertEqual(status, 401)

        status, _headers, payload = self.call_json(
            "/api/v1/bridge/status",
            headers=self.extension_headers(second["token"]),
        )
        self.assertEqual(status, 200, payload)

    def test_manual_pairing_endpoints_are_retired(self):
        for path in (
            "/api/v1/bridge/pair",
            "/api/v1/bridge/pairing/renew",
            "/api/v1/bridge/pairing/reset",
        ):
            status, _headers, _payload = self.call_json(
                path,
                method="POST",
                headers={"Origin": self.base},
                body={},
            )
            self.assertEqual(status, 404, path)

        opener = self.mesa_opener()
        status, _headers, _payload = self.call_json(
            "/api/v1/bridge/pairing",
            headers=self.mesa_headers(),
            opener=opener,
        )
        self.assertEqual(status, 404)

    def test_unpaired_extension_is_rejected(self):
        status, _headers, payload = self.call_json(
            "/api/v1/extension/commands/next",
            headers={"X-TCE-Client": "extension-test", "Origin": EXTENSION_ORIGIN},
        )

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "unauthorized")

    def test_only_the_token_hash_is_persisted(self):
        token = self.registered_token()

        row = self.store.list_bridge_clients()[0]
        self.assertEqual(row["token_hash"], hash_token(token))
        self.assertNotIn(token, row["token_hash"])
        database = (self.data_root / "atos-tce.db").read_bytes()
        self.assertNotIn(token.encode("utf-8"), database)
        self.assertNotIn(b"618900", database)

    def test_a_token_is_only_valid_from_the_origin_it_was_paired_with(self):
        token = self.registered_token()

        status, _headers, payload = self.call_json(
            "/api/v1/extension/commands/next",
            headers={
                "Authorization": f"Bearer {token}",
                "X-TCE-Client": "extension-test",
                "Origin": "chrome-extension://outraextensaoqualquer",
            },
        )

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "unauthorized")

    def test_a_request_without_an_extension_origin_is_rejected(self):
        token = self.registered_token()

        status, _headers, _payload = self.call_json(
            "/api/v1/extension/commands/next",
            headers={"Authorization": f"Bearer {token}", "X-TCE-Client": "extension-test"},
        )

        self.assertEqual(status, 401)

    def test_token_survives_a_new_server_instance(self):
        token = self.registered_token()
        restarted = self.start_server(Bridge())
        self.base = f"http://127.0.0.1:{restarted.server_address[1]}"

        status, _headers, payload = self.call_json(
            "/api/v1/extension/commands/next", headers=self.extension_headers(token)
        )

        self.assertEqual(status, 200)
        self.assertIsNone(payload["command"])

    def test_invalid_token_is_rejected(self):
        self.registered_token()

        status, _headers, _payload = self.call_json(
            "/api/v1/extension/commands/next", headers=self.extension_headers("token-errado")
        )
        self.assertEqual(status, 401)

        status, _headers, _payload = self.call_json(
            "/api/v1/extension/commands/next",
            headers={"Authorization": "Bearer ", "X-TCE-Client": "extension-test"},
        )
        self.assertEqual(status, 401)

    def test_bridge_status_requires_a_token(self):
        self.assertEqual(self.call("/api/v1/bridge/status")[0], 401)

        token = self.registered_token()
        status, _headers, payload = self.call_json(
            "/api/v1/bridge/status", headers=self.extension_headers(token)
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["paired"])
        self.assertEqual(payload["client_id"], "extension-test")
        self.assertEqual(payload["origin"], EXTENSION_ORIGIN)

    def test_cors_preflight_allows_only_extension_origins(self):
        status, headers, _payload = self.call(
            "/api/v1/extension/commands/next", method="OPTIONS", headers={"Origin": EXTENSION_ORIGIN}
        )
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], EXTENSION_ORIGIN)
        self.assertIn("Authorization", headers["Access-Control-Allow-Headers"])

        status, _headers, _payload = self.call(
            "/api/v1/extension/commands/next", method="OPTIONS", headers={"Origin": "https://example.com"}
        )
        self.assertEqual(status, 403)

    def test_extension_responses_carry_cors_headers(self):
        token = self.registered_token()

        status, headers, _payload = self.call_json(
            "/api/v1/extension/commands/next", headers=self.extension_headers(token)
        )

        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], EXTENSION_ORIGIN)

class MesaSessionTests(BridgeTestCase):
    def test_bootstrap_token_is_single_use(self):
        opener = self.mesa_opener()

        status, _headers, payload = self.call_json(
            "/api/v1/session/bootstrap",
            method="POST",
            headers={"Origin": self.base},
            body={"token": "bootstrap-token"},
            opener=opener,
        )

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "bootstrap_rejected")

    def test_bootstrap_sets_an_httponly_same_site_cookie(self):
        status, headers, _payload = self.call_json(
            "/api/v1/session/bootstrap",
            method="POST",
            headers={"Origin": self.base},
            body={"token": "bootstrap-token"},
        )

        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("mesa_session=", cookie)

    def test_authenticated_mesa_can_issue_a_one_time_session_handoff_url(self):
        opener = self.mesa_opener()

        status, _headers, payload = self.call_json(
            "/api/v1/session/handoff",
            method="POST",
            headers=self.mesa_headers(),
            body={},
            opener=opener,
        )

        self.assertEqual(status, 200, payload)
        handoff_url = payload["url"]
        self.assertTrue(handoff_url.startswith(f"{self.base}/bootstrap#token="))
        token = handoff_url.split("#token=", 1)[1]

        other_profile = build_opener(HTTPCookieProcessor(CookieJar()))
        status, _headers, _payload = self.call_json(
            "/api/v1/session/bootstrap",
            method="POST",
            headers={"Origin": self.base},
            body={"token": token},
            opener=other_profile,
        )
        self.assertEqual(status, 200)

        status, _headers, _payload = self.call_json(
            "/api/v1/session/bootstrap",
            method="POST",
            headers={"Origin": self.base},
            body={"token": token},
        )
        self.assertEqual(status, 401)

    def test_state_changing_route_without_a_session_is_rejected(self):
        status, _headers, payload = self.call_json(
            "/api/v1/extension/commands",
            method="POST",
            headers=self.mesa_headers(),
            body={"type": "SCAN_AREA", "payload": {}},
        )

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "session_required")

    def test_state_changing_route_with_a_foreign_origin_is_rejected(self):
        opener = self.mesa_opener()

        status, _headers, payload = self.call_json(
            "/api/v1/extension/commands",
            method="POST",
            headers={"Origin": "https://evil.example.com", "Sec-Fetch-Site": "cross-site"},
            body={"type": "SCAN_AREA", "payload": {}},
            opener=opener,
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "origin_not_allowed")

    def test_area_scans_route_is_not_public(self):
        status, _headers, payload = self.call_json(
            "/api/v1/area/scans",
            method="POST",
            headers={"Origin": self.base},
            body={"source_scope": "sector_finalistic", "rows": []},
        )

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "session_required")

    def test_mesa_can_persist_a_scan_with_its_session(self):
        opener = self.mesa_opener()

        status, _headers, payload = self.call_json(
            "/api/v1/area/scans",
            method="POST",
            headers=self.mesa_headers(),
            body={
                "source_scope": "sector_finalistic",
                "marker_label": "PROFESSOR - IPERN - 2 RUBRICAS",
                "marker_value": "6189",
                "rows": [
                    {
                        "process_key": "102390/2026",
                        "interested": "Pessoa Exemplo",
                        "interested_normalized": "pessoa exemplo",
                        "classification": "PRECISA_COMPLEMENTAR",
                    }
                ],
            },
            opener=opener,
        )

        self.assertEqual(status, 201, payload)
        scan = self.store.get_area_scan(payload["scan_id"])
        self.assertEqual(scan["pending"], 1)


class ExtensionCommandApiTests(BridgeTestCase):
    def test_mesa_queues_a_command_and_the_extension_claims_it(self):
        opener = self.mesa_opener()
        status, _headers, created = self.call_json(
            "/api/v1/extension/commands",
            method="POST",
            headers=self.mesa_headers(),
            body={"type": "SCAN_AREA", "payload": {"scope": "sector_finalistic"}},
            opener=opener,
        )
        self.assertEqual(status, 201, created)
        self.assertGreater(created["command_id"], 0)
        self.assertEqual(created["state"], "QUEUED")

        token = self.registered_token()
        status, _headers, payload = self.call_json(
            "/api/v1/extension/commands/next", headers=self.extension_headers(token)
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["command"]["id"], created["command_id"])
        self.assertEqual(payload["command"]["type"], "SCAN_AREA")
        self.assertEqual(payload["command"]["payload"], {"scope": "sector_finalistic"})

        status, _headers, payload = self.call_json(
            "/api/v1/extension/commands/next", headers=self.extension_headers(token)
        )
        self.assertIsNone(payload["command"])

    def test_extension_reports_a_result_and_the_mesa_reads_it(self):
        opener = self.mesa_opener()
        _status, _headers, created = self.call_json(
            "/api/v1/extension/commands",
            method="POST",
            headers=self.mesa_headers(),
            body={"type": "SCAN_AREA", "payload": {}},
            opener=opener,
        )
        command_id = created["command_id"]
        token = self.registered_token()
        _status, _headers, claimed = self.call_json(
            "/api/v1/extension/commands/next", headers=self.extension_headers(token)
        )

        status, _headers, payload = self.call_json(
            f"/api/v1/extension/commands/{command_id}/result",
            method="POST",
            headers=self.extension_headers(token),
            body={
                "ok": True,
                "role": "list",
                "source_scope": "sector_finalistic",
                "rows": [{"process_key": "102390/2026"}],
                "claim_token": claimed["command"]["claim_token"],
            },
        )
        self.assertEqual(status, 200, payload)

        status, _headers, payload = self.call_json(
            f"/api/v1/extension/commands/{command_id}",
            headers=self.mesa_headers(),
            opener=opener,
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["state"], "SUCCEEDED")
        self.assertEqual(payload["result"]["rows"], [{"process_key": "102390/2026"}])
        self.assertNotIn("claim_token", payload["result"])

    def test_result_route_rejects_an_invalid_token(self):
        status, _headers, payload = self.call_json(
            "/api/v1/extension/commands/1/result",
            method="POST",
            headers=self.extension_headers("errado"),
            body={"ok": True},
        )

        self.assertEqual(status, 401)

    def test_command_status_route_requires_the_mesa_session(self):
        status, _headers, payload = self.call_json("/api/v1/extension/commands/1")

        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
