"""Tests for the read-only Mesa API (M1 Task 4)."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from app.api.bridge import Bridge, hash_token
from app.api.server import serve
from app.archive.legacy_import import blob_path, sha256_file
from app.area_restrita import cdp_fallback
from app.core.models import DocumentRecord, FieldRecord, ProcessRecord
from app.core.store import SCHEMA_VERSION, Store

PDF = b"%PDF-1.4\napi fixture\n%%EOF\n"
REPO_ROOT = Path(__file__).resolve().parents[1]


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.data_root = self.tmp / "data"
        self.store = Store.open(self.data_root / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.seed()
        self.bridge = Bridge(code="618900", bootstrap_token="bootstrap-token")
        self.server = serve(self.store, self.data_root, port=0, bridge=self.bridge)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def seed(self):
        view = self.data_root / "archive" / "processos" / "102390-2026" / "Ato.pdf"
        view.parent.mkdir(parents=True, exist_ok=True)
        view.write_bytes(PDF)
        digest = sha256_file(view)
        self.blob = blob_path(self.data_root, digest)
        self.blob.parent.mkdir(parents=True, exist_ok=True)
        self.blob.write_bytes(PDF)
        self.digest = digest

        self.process_id = self.store.upsert_process(
            ProcessRecord(
                process_key="102390/2026",
                interested="Pessoa Exemplo",
                interested_normalized="pessoa exemplo",
                source_scope="sector_finalistic",
                marker="PROFESSOR - IPERN - 2 RUBRICAS",
                status="PRONTO",
            )
        )
        self.store.replace_documents(
            self.process_id,
            [
                DocumentRecord(
                    source_id="102390/2026|1|informacao-1",
                    title="Ato",
                    relative_path="archive/processos/102390-2026/Ato.pdf",
                    sha256=digest,
                    page_count=2,
                    event="1",
                    classification="ato",
                    storage_state="HOT",
                )
            ],
        )
        document_id = self.store.get_process(self.process_id)["documents"][0]["id"]
        self.document_id = document_id
        self.store.replace_fields(
            self.process_id,
            [
                FieldRecord(
                    field_name="cargo",
                    value="Professor",
                    status="found",
                    confidence=1.0,
                    document_id=document_id,
                    page=2,
                    evidence={"quote": "Professor"},
                )
            ],
        )
        self.store.add_workflow_event(self.process_id, "analysis_finished", {"status": "PRONTO"})

    def call(self, path, method="GET", headers=None, body=None, opener=None):
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(f"{self.base}{path}", data=payload, method=method)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        send = opener.open if opener is not None else urlopen
        try:
            with send(request, timeout=15) as response:
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

    def get(self, path):
        status, headers, raw = self.call(path)
        self.assertEqual(status, 200, f"GET {path} answered {status}")
        return _InMemoryResponse(raw, headers)

    def get_json(self, path):
        status, _headers, payload = self.call_json(path)
        self.assertEqual(status, 200, f"GET {path} answered {status}")
        return payload

    def mesa_headers(self):
        return {"Origin": self.base}

    def mesa_opener(self):
        """Return an opener holding a valid Mesa session cookie."""

        jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(jar))
        status, _headers, payload = self.call_json(
            "/api/v1/session/bootstrap",
            method="POST",
            headers=self.mesa_headers(),
            body={"token": self.bridge.bootstrap_value},
            opener=opener,
        )
        self.assertEqual(status, 200, payload)
        return opener

    def pair_extension(self, token="extension-token", client_id="extension-test"):
        self.store.pair_bridge_client(
            client_id, hash_token(token), origin="chrome-extension://abcdefghijklmnop"
        )
        return {
            "Authorization": f"Bearer {token}",
            "X-TCE-Client": client_id,
            "Origin": "chrome-extension://abcdefghijklmnop",
        }

    def status_of(self, path):
        """Return the HTTP status without leaking an unclosed error body."""

        return self.call(path)[0]


class _InMemoryResponse:
    """Context manager mimicking the urllib response used by the tests."""

    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers
        self.status = 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None


class HealthTests(ApiTestCase):
    def test_health_reports_api_and_schema_version(self):
        payload = self.get_json("/api/v1/health")

        self.assertEqual(payload["api_version"], 1)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
        self.assertEqual(payload["process_count"], 1)


class ProcessRouteTests(ApiTestCase):
    def test_process_list(self):
        payload = self.get_json("/api/v1/processes")

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["process_key"], "102390/2026")
        self.assertEqual(payload["items"][0]["document_count"], 1)

    def test_process_list_filters_by_status(self):
        self.assertEqual(self.get_json("/api/v1/processes?status=PRONTO")["total"], 1)
        self.assertEqual(self.get_json("/api/v1/processes?status=ERRO")["total"], 0)

    def test_process_detail_includes_documents_fields_and_history(self):
        payload = self.get_json(f"/api/v1/processes/{self.process_id}")

        self.assertEqual(payload["process_key"], "102390/2026")
        self.assertEqual(payload["documents"][0]["title"], "Ato")
        self.assertEqual(payload["fields"][0]["field_name"], "cargo")
        self.assertEqual(payload["fields"][0]["evidence"], {"quote": "Professor"})
        self.assertEqual(payload["events"][0]["event_type"], "analysis_finished")

    def test_unknown_process_is_404(self):
        self.assertEqual(self.status_of("/api/v1/processes/4242"), 404)


class StorageRouteTests(ApiTestCase):
    def test_storage_reports_canonical_archive(self):
        payload = self.get_json("/api/v1/storage")

        self.assertEqual(payload["database"]["processes"]["total"], 1)
        self.assertEqual(payload["archive"]["blob_count"], 1)
        self.assertEqual(payload["archive"]["blob_bytes"], len(PDF))
        self.assertEqual(payload["archive"]["process_view_files"], 1)
        # In this fixture the view is an independent copy, so nothing is saved.
        self.assertEqual(payload["archive"]["process_view_physical_bytes"], len(PDF))
        self.assertEqual(payload["archive"]["deduplicated_bytes"], 0)

    def test_hardlinked_view_is_reported_as_deduplicated(self):
        view = self.data_root / "archive" / "processos" / "102390-2026" / "Ato.pdf"
        view.unlink()
        os.link(self.blob, view)

        payload = self.get_json("/api/v1/storage")

        self.assertEqual(payload["archive"]["process_view_bytes"], len(PDF))
        self.assertEqual(payload["archive"]["process_view_physical_bytes"], 0)
        self.assertEqual(payload["archive"]["deduplicated_bytes"], len(PDF))


class PdfRouteTests(ApiTestCase):
    def test_document_pdf_is_served(self):
        with self.get(f"/api/v1/documents/{self.document_id}/pdf") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "application/pdf")
            self.assertEqual(response.read(), PDF)

    def test_pdf_falls_back_to_the_canonical_blob(self):
        (self.data_root / "archive" / "processos" / "102390-2026" / "Ato.pdf").unlink()

        with self.get(f"/api/v1/documents/{self.document_id}/pdf") as response:
            self.assertEqual(response.read(), PDF)

    def test_unknown_document_is_404(self):
        self.assertEqual(self.status_of("/api/v1/documents/9999/pdf"), 404)

    def test_missing_file_is_404(self):
        self.blob.unlink()
        (self.data_root / "archive" / "processos" / "102390-2026" / "Ato.pdf").unlink()

        self.assertEqual(self.status_of(f"/api/v1/documents/{self.document_id}/pdf"), 404)

    def test_query_parameters_cannot_select_a_file(self):
        with self.get(
            f"/api/v1/documents/{self.document_id}/pdf"
            "?path=..%2F..%2F..%2FWindows%2Fwin.ini&file=C%3A%5CWindows%5Cwin.ini"
        ) as response:
            self.assertEqual(response.read(), PDF)

    def test_no_generic_file_route_exists(self):
        for candidate in (
            "/api/v1/file?path=C%3A%5CWindows%5Cwin.ini",
            "/api/v1/documents?path=..%2Fsecret.pdf",
            "/api/v1/processes/1/pdf",
        ):
            with self.subTest(candidate=candidate):
                self.assertEqual(self.status_of(candidate), 404)

    def test_unknown_query_parameters_are_ignored(self):
        # /api/v1/storage answers 200 but must never let ?path= pick a file.
        payload = self.get_json("/api/v1/storage?path=..%2F..%2Fsecret&file=C%3A%5CWindows%5Cwin.ini")

        self.assertNotIn("secret", json.dumps(payload))
        self.assertNotIn("win.ini", json.dumps(payload))

    def test_escaped_relative_path_is_refused(self):
        secret = self.tmp / "secret.pdf"
        secret.write_bytes(b"%PDF-1.4 secret\n")
        self.store.replace_documents(
            self.process_id,
            [
                DocumentRecord(
                    source_id="escape",
                    title="Escape",
                    relative_path="../secret.pdf",
                    sha256="0" * 64,
                    page_count=1,
                )
            ],
        )
        document_id = self.store.get_process(self.process_id)["documents"][0]["id"]

        self.assertEqual(self.status_of(f"/api/v1/documents/{document_id}/pdf"), 404)


class StaticRouteTests(ApiTestCase):
    def test_unknown_static_path_is_404(self):
        self.assertEqual(self.status_of("/nao-existe.html"), 404)

    def test_static_path_traversal_is_refused(self):
        self.assertIn(self.status_of("/../../README.md"), (400, 404))


class MesaUiTests(ApiTestCase):
    """Static contract of the read-only Mesa shell (M1 Task 5)."""

    CONTRACT_ELEMENTS = (
        'id="health-status"',
        'id="summary"',
        'id="storage-summary"',
        'id="process-search"',
        'id="process-list"',
        'id="process-detail"',
    )

    def test_root_serves_the_mesa_shell(self):
        with self.get("/") as response:
            body = response.read().decode("utf-8")

        self.assertIn('id="process-list"', body)
        self.assertIn('id="storage-summary"', body)
        self.assertIn('src="/app.js"', body)
        self.assertIn('href="/app.css"', body)

    def test_shell_exposes_every_contract_element(self):
        with self.get("/") as response:
            body = response.read().decode("utf-8")

        for element in self.CONTRACT_ELEMENTS:
            with self.subTest(element=element):
                self.assertIn(element, body)

    def test_assets_are_served_with_correct_types(self):
        with self.get("/app.js") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("javascript", response.headers["Content-Type"])
            script = response.read().decode("utf-8")
        with self.get("/app.css") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/css", response.headers["Content-Type"])

        self.assertIn("/api/v1/health", script)
        self.assertIn("/api/v1/processes", script)
        self.assertIn("/api/v1/storage", script)

    def test_bootstrap_page_keeps_the_token_in_the_fragment(self):
        with self.get("/bootstrap") as response:
            self.assertEqual(response.status, 200)
            body = response.read().decode("utf-8")

        self.assertIn("/api/v1/session/bootstrap", body)
        self.assertIn("location.hash", body)
        self.assertIn("location.replace(\"/\")", body)

    def test_the_mesa_exposes_the_area_analysis_action(self):
        with self.get("/") as response:
            shell = response.read().decode("utf-8")

        self.assertIn('id="analyze-area"', shell)
        self.assertIn('id="analyze-area-cdp"', shell)
        self.assertIn("Analisar Área Restrita", shell)
        self.assertIn('id="analyze-status"', shell)
        self.assertIn('id="area-counters"', shell)
        self.assertIn('id="pairing-code"', shell)
        self.assertIn('id="renew-pairing"', shell)

        with self.get("/app.js") as response:
            script = response.read().decode("utf-8")
        for counter in ("total", "pending", "completed", "ambiguous"):
            with self.subTest(counter=counter):
                self.assertIn(f"{counter}:", script)

    def test_the_mesa_only_posts_the_documented_analyze_action(self):
        with self.get("/") as response:
            shell = response.read().decode("utf-8")
        with self.get("/app.js") as response:
            script = response.read().decode("utf-8")
        source = shell + script

        # M2 adds exactly one state-changing action: Analisar Área Restrita.
        self.assertIn("/api/v1/area/analyze", source)
        for forbidden in (
            "/api/v1/acquisition",
            "/api/v1/fill",
            "/api/v1/portal/manual-form",
            "autoSubmit",
            "real_send",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


SNAPSHOT = {
    "role": "list",
    "source_scope": "sector_finalistic",
    "marker": {"label": "PROFESSOR - IPERN - 2 RUBRICAS", "value": "6189"},
    "page": 1,
    "total_pages": 1,
    "rows": [
        {
            "process_key": "102391/2026",
            "interested": "Outra Pessoa",
            "interested_normalized": "outra pessoa",
            "portal_act_id": None,
            "classification": "ATO_COMPLEMENTADO",
            "needs_complement": False,
            "action_observed": "Ato Complementado",
        },
        {
            "process_key": "102392/2026",
            "interested": "Terceira Pessoa",
            "interested_normalized": "terceira pessoa",
            "portal_act_id": "987654",
            "classification": "PRECISA_COMPLEMENTAR",
            "needs_complement": True,
            "action_observed": "Complementar Ato",
        },
        {
            "process_key": "102390/2026",
            "interested": "Pessoa Exemplo",
            "interested_normalized": "pessoa exemplo",
            "portal_act_id": "123",
            "classification": "PRECISA_COMPLEMENTAR",
            "needs_complement": True,
            "action_observed": "Complementar Ato",
        },
    ],
    "skipped_rows": 0,
}


class AreaAnalyzeFlowTests(ApiTestCase):
    def start_analyze(self):
        opener = self.mesa_opener()
        status, _headers, created = self.call_json(
            "/api/v1/area/analyze", method="POST", headers=self.mesa_headers(), body={}, opener=opener
        )
        self.assertEqual(status, 201, created)
        return opener, created["command_id"]

    def test_analyze_flow_persists_the_scan_and_updates_processes(self):
        opener, command_id = self.start_analyze()

        status, _headers, command = self.call_json(
            f"/api/v1/extension/commands/{command_id}", headers=self.mesa_headers(), opener=opener
        )
        self.assertEqual(status, 200)
        self.assertEqual(command["state"], "QUEUED")
        self.assertEqual(command["type"], "SCAN_AREA")

        extension_headers = self.pair_extension()
        status, _headers, claimed = self.call_json(
            "/api/v1/extension/commands/next", headers=extension_headers
        )
        self.assertEqual(claimed["command"]["id"], command_id)

        status, _headers, posted = self.call_json(
            f"/api/v1/extension/commands/{command_id}/result",
            method="POST",
            headers=extension_headers,
            body={**SNAPSHOT, "command_id": command_id, "ok": True},
        )
        self.assertEqual(status, 200, posted)
        self.assertEqual(posted["scan_id"], 1)

        payload = self.get_json("/api/v1/area/latest")
        self.assertEqual(payload["scan"]["total"], 3)
        self.assertEqual(payload["scan"]["pending"], 2)
        self.assertEqual(payload["scan"]["completed"], 1)
        self.assertEqual(payload["scan"]["ambiguous"], 0)
        self.assertEqual(payload["scan"]["marker_value"], "6189")
        self.assertEqual(payload["scan"]["source_scope"], "sector_finalistic")

        processes = {row["process_key"]: row for row in self.get_json("/api/v1/processes")["items"]}
        self.assertEqual(processes["102391/2026"]["status"], "CONCLUÍDO")
        self.assertEqual(processes["102392/2026"]["status"], "PENDENTE")
        self.assertEqual(processes["102392/2026"]["needs_complement"], 1)
        self.assertEqual(processes["102392/2026"]["portal_act_id"], "987654")
        # The seeded process was already PRONTO: a portal scan never regresses it.
        self.assertEqual(processes["102390/2026"]["status"], "PRONTO")
        self.assertEqual(processes["102390/2026"]["needs_complement"], 1)

        status, _headers, command = self.call_json(
            f"/api/v1/extension/commands/{command_id}", headers=self.mesa_headers(), opener=opener
        )
        self.assertEqual(command["state"], "SUCCEEDED")

    def test_analyze_route_requires_a_mesa_session(self):
        status, _headers, payload = self.call_json(
            "/api/v1/area/analyze", method="POST", headers=self.mesa_headers(), body={}
        )

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "session_required")

    def test_a_result_without_a_portal_role_is_recorded_but_not_persisted(self):
        opener, command_id = self.start_analyze()
        extension_headers = self.pair_extension()
        self.call_json("/api/v1/extension/commands/next", headers=extension_headers)

        status, _headers, posted = self.call_json(
            f"/api/v1/extension/commands/{command_id}/result",
            method="POST",
            headers=extension_headers,
            body={"ok": True, "rows": [{"process_key": "102390/2026"}]},
        )

        self.assertEqual(status, 200, posted)
        self.assertIsNone(posted.get("scan_id"))
        self.assertIsNone(self.store.latest_area_scan())
        status, _headers, command = self.call_json(
            f"/api/v1/extension/commands/{command_id}", headers=self.mesa_headers(), opener=opener
        )
        self.assertEqual(command["state"], "SUCCEEDED")

    def test_a_failed_extension_report_is_stored_as_an_error(self):
        opener, command_id = self.start_analyze()
        extension_headers = self.pair_extension()
        self.call_json("/api/v1/extension/commands/next", headers=extension_headers)

        self.call_json(
            f"/api/v1/extension/commands/{command_id}/result",
            method="POST",
            headers=extension_headers,
            body={"ok": False, "error": "Nenhuma aba autenticada da Área Restrita está aberta."},
        )

        _status, _headers, command = self.call_json(
            f"/api/v1/extension/commands/{command_id}", headers=self.mesa_headers(), opener=opener
        )
        self.assertEqual(command["state"], "FAILED")
        self.assertIn("Área Restrita", command["error"])
        self.assertIsNone(self.store.latest_area_scan())

    def test_area_latest_is_empty_before_the_first_scan(self):
        payload = self.get_json("/api/v1/area/latest")

        self.assertIsNone(payload["scan"])
        self.assertEqual(payload["counters"]["total"], 0)

    def test_the_cdp_fallback_persists_the_same_scan_schema(self):
        opener = self.mesa_opener()
        snapshot = {**SNAPSHOT, "origin": "cdp"}
        result = cdp_fallback.CdpScanResult(ok=True, snapshot=snapshot, exit_code=0)

        with mock.patch.object(cdp_fallback, "run_cdp_scan", return_value=result):
            status, _headers, payload = self.call_json(
                "/api/v1/area/analyze-cdp",
                method="POST",
                headers=self.mesa_headers(),
                body={},
                opener=opener,
            )

        self.assertEqual(status, 201, payload)
        self.assertEqual(payload["origin"], "cdp")
        scan = self.store.get_area_scan(payload["scan_id"])
        self.assertEqual(scan["origin"], "cdp")
        self.assertEqual(scan["total"], 3)
        self.assertEqual(scan["pending"], 2)
        self.assertEqual(scan["completed"], 1)
        latest = self.get_json("/api/v1/area/latest")
        self.assertEqual(latest["counters"], scan_counters(scan))

    def test_the_cdp_fallback_reports_a_safe_failure(self):
        opener = self.mesa_opener()
        result = cdp_fallback.CdpScanResult(
            ok=False, error="the compatibility scan failed (exit code 1)", exit_code=1
        )

        with mock.patch.object(cdp_fallback, "run_cdp_scan", return_value=result):
            status, _headers, payload = self.call_json(
                "/api/v1/area/analyze-cdp",
                method="POST",
                headers=self.mesa_headers(),
                body={},
                opener=opener,
            )

        self.assertEqual(status, 502)
        self.assertEqual(payload["error"], "cdp_scan_failed")
        self.assertIsNone(self.store.latest_area_scan())

    def test_the_cdp_fallback_requires_a_mesa_session(self):
        status, _headers, payload = self.call_json(
            "/api/v1/area/analyze-cdp", method="POST", headers=self.mesa_headers(), body={}
        )

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "session_required")


def scan_counters(scan: dict) -> dict:
    return {
        field: int(scan.get(field) or 0)
        for field in ("total", "pending", "completed", "ambiguous", "blocked", "not_found")
    }


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class MesaLauncherTests(unittest.TestCase):
    def test_main_serves_health_then_stops_cleanly(self):
        with TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "data"
            port = free_port()
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "app.main",
                    "--data-root",
                    str(data_root),
                    "--port",
                    str(port),
                    "--no-browser",
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            try:
                deadline = time.monotonic() + 30
                payload = None
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=2) as response:
                            payload = json.loads(response.read().decode("utf-8"))
                        break
                    except OSError:
                        time.sleep(0.3)
                self.assertIsNotNone(payload, "the Mesa never answered /api/v1/health")
                self.assertEqual(payload["status"], "ok")
                self.assertTrue((data_root / "atos-tce.db").is_file())
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                    process.kill()
                    process.wait(timeout=15)
                process.stdout.close()
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
