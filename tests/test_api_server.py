"""Tests for the read-only Mesa API (M1 Task 4)."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import urlopen

from app.api.server import serve
from app.archive.legacy_import import blob_path, sha256_file
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
        self.server = serve(self.store, self.data_root, port=0)
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

    def get(self, path):
        return urlopen(f"{self.base}{path}", timeout=10)

    def get_json(self, path):
        with self.get(path) as response:
            return json.loads(response.read().decode("utf-8"))

    def status_of(self, path):
        """Return the HTTP status without leaking an unclosed error body."""

        try:
            with self.get(path) as response:
                response.read()
                return response.status
        except HTTPError as error:
            code = error.code
            error.close()
            return code


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

    def test_mesa_is_read_only_in_m1(self):
        with self.get("/") as response:
            shell = response.read().decode("utf-8")
        with self.get("/app.js") as response:
            script = response.read().decode("utf-8")
        source = shell + script

        for forbidden in (
            "/api/v1/acquisition",
            "/api/v1/fill",
            "/api/v1/area/analyze",
            "method: 'POST'",
            'method: "POST"',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


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
