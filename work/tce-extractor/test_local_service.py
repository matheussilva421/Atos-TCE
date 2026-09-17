import contextlib
import base64
from contextlib import redirect_stderr
from http.client import RemoteDisconnected
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import socket
import time
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from openpyxl import Workbook

APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

import local_service  # noqa: E402
from local_service import create_server  # noqa: E402


def json_request(url, *, method="GET", payload=None, token=None, origin=None, host=None, range_header=None, cookie=None, csrf=None, omit_origin=False):
    headers = {}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if not omit_origin:
        effective_origin = origin
        if effective_origin is None and token is not None:
            effective_origin = "chrome-extension://test-extension"
        if effective_origin is not None:
            headers["Origin"] = effective_origin
    if host is not None:
        headers["Host"] = host
    if range_header is not None:
        headers["Range"] = range_header
    if cookie is not None:
        headers["Cookie"] = cookie
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
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
    def test_extension_cors_preflight_and_pair_response_are_supported(self):
        with running_server() as (_root, server, base):
            origin = "chrome-extension://test-extension"
            preflight = Request(
                f"{base}/api/v1/pair",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization, content-type",
                },
                method="OPTIONS",
            )
            with urlopen(preflight, timeout=3) as response:
                self.assertEqual(response.status, 204)
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)
                self.assertIn("POST", response.headers["Access-Control-Allow-Methods"])
                allowed_headers = response.headers["Access-Control-Allow-Headers"].lower()
                self.assertIn("authorization", allowed_headers)
                self.assertIn("content-type", allowed_headers)

            status, headers, body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": server.auth.issue_pairing_code()},
                origin=origin,
            )
            self.assertEqual(status, 200)
            self.assertEqual(headers["Access-Control-Allow-Origin"], origin)
            self.assertTrue(json.loads(body)["token"])

    def test_authenticated_process_list_import_active_query_and_report(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "professor-ipern.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Planilha2"
            sheet.append(["numero_processo", "ano_processo"])
            sheet.append([101, 2023])
            sheet.append([101, 2023])
            workbook.save(source)
            with running_server() as (root, server, base):
                code = server.auth.issue_pairing_code()
                _status, _headers, pair_body = json_request(
                    f"{base}/api/v1/pair",
                    method="POST",
                    payload={"code": code},
                    origin="chrome-extension://test-extension",
                )
                token = json.loads(pair_body)["token"]
                imported_status, _headers, imported_body = json_request(
                    f"{base}/api/v1/process-lists/import",
                    method="POST",
                    payload={
                        "filename": source.name,
                        "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
                    },
                    token=token,
                )
                manifest = json.loads(imported_body)
                self.assertEqual(imported_status, 200)
                self.assertEqual(manifest["unique_count"], 1)
                self.assertEqual(manifest["duplicate_count"], 1)
                _status, _headers, active_body = json_request(
                    f"{base}/api/v1/process-lists/active", token=token
                )
                active = json.loads(active_body)
                self.assertEqual(active["input_list_id"], manifest["input_list_id"])
                report_status, _headers, report_body = json_request(
                    f"{base}/api/v1/process-lists/{manifest['input_list_id']}/report",
                    method="POST",
                    payload={
                        "classifications": {
                            "101/2023": {
                                "marker_present": True,
                                "marker_observed": "PROFESSOR - IPERN",
                                "area_status": "PRECISA_COMPLEMENTAR",
                                "action_signature": None,
                                "lot_number": 1,
                                "econtas_status": "not_started",
                                "documents_downloaded": 0,
                                "error": None,
                            }
                        }
                    },
                    token=token,
                )
                report = json.loads(report_body)
                self.assertEqual(report_status, 200)
                self.assertEqual(report["summary"]["linhas"], 2)
                self.assertTrue((root / report["relative_path"]).is_file())

    def test_authenticated_analysis_v3_preserves_input_provenance(self):
        with running_server() as (_root, server, base):
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://test-extension",
            )
            token = json.loads(pair_body)["token"]
            payload = {
                "spec": {
                    "schema_version": 3,
                    "source_scope": "sector_finalistic",
                    "marker": {"label": "Marcador", "value": "m-1"},
                    "acquisition_source": "econtas",
                    "lot_size": 300,
                    "analysis_only": True,
                    "auto_prepare": False,
                    "auto_submit": False,
                    "dataset_sha256": None,
                    "area_snapshot_sha256": "b" * 64,
                    "input_list_id": "input-" + "a" * 24,
                    "input_sha256": "c" * 64,
                    "input_unique_count": 1,
                },
                "observed_at": "2026-09-14T12:00:00+00:00",
                "rows": [],
            }
            status, _headers, body = json_request(
                f"{base}/api/v1/analysis/preview",
                method="POST",
                payload=payload,
                token=token,
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["schema_version"], 3)
    def test_run_payload_preserves_hybrid_scope_and_frozen_lot_contract(self):
        payload = {
            "tab_id": 7,
            "sector": "aposentadorias",
            "dataset_sha256": "a" * 64,
            "rules_version": "legal-foundation-v3",
            "event_id": "start-hybrid-1",
            "marker": "Marcador",
            "marker_value": "marker-1",
            "source_scope": "my_processes",
            "acquisition_source": "econtas",
            "lot_size": 100,
            "analysis_id": "analysis-" + "a" * 24,
            "preview_hash": "a" * 64,
            "auto_submit": False,
        }

        normalized, event_id = local_service._validate_run_payload(payload)

        self.assertEqual(event_id, "start-hybrid-1")
        self.assertEqual(normalized["source_scope"], "my_processes")
        self.assertEqual(normalized["acquisition_source"], "econtas")
        self.assertEqual(normalized["lot_size"], 100)
        self.assertEqual(normalized["analysis_id"], "analysis-" + "a" * 24)
        self.assertEqual(normalized["preview_hash"], "a" * 64)

    def test_authenticated_analysis_preview_can_be_read_and_split_into_lots(self):
        with running_server() as (_root, server, base):
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://test-extension",
            )
            token = json.loads(pair_body)["token"]
            payload = {
                "spec": {
                    "schema_version": 2,
                    "source_scope": "sector_finalistic",
                    "marker": {"label": "Marcador", "value": "m-1"},
                    "acquisition_source": "econtas",
                    "lot_size": 50,
                    "analysis_only": True,
                    "auto_prepare": True,
                    "auto_submit": False,
                    "dataset_sha256": None,
                    "area_snapshot_sha256": "b" * 64,
                },
                "observed_at": "2026-09-10T12:00:00+00:00",
                "rows": [{
                    "process_key": "100/2026",
                    "interested_key": "person-1",
                    "area_restrita": {
                        "scope": "sector_finalistic",
                        "marker_label": "Marcador",
                        "marker_value": "m-1",
                        "needs_complement": True,
                        "action_observed": "Complementar Ato",
                        "action_signature": {"kind": "red_complement_icon", "alt": "Complementar Ato", "title": "Complementar Ato", "src": "icone-vermelho.png"},
                        "snapshot_hash": "a" * 64,
                    },
                    "econtas": {
                        "match": "exact",
                        "documents": [{
                            "document_id": "doc-1",
                            "relative_path": "documentos/doc-1.pdf",
                            "sha256": "d" * 64,
                        }],
                        "snapshot_hash": "a" * 64,
                        "ocr_status": "ready",
                    },
                }],
            }
            status, _headers, body = json_request(
                f"{base}/api/v1/analysis/preview",
                method="POST",
                payload=payload,
                token=token,
                origin="chrome-extension://test-extension",
            )
            preview = json.loads(body)
            self.assertEqual(status, 200)
            self.assertEqual(preview["preview"]["eligible"], 1)
            self.assertNotIn("canonical_json", preview)

            analysis_id = preview["analysis_id"]
            status, _headers, body = json_request(
                f"{base}/api/v1/analysis/{analysis_id}",
                token=token,
                origin="chrome-extension://test-extension",
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["dataset_sha256"], preview["dataset_sha256"])

            status, _headers, body = json_request(
                f"{base}/api/v1/analysis/{analysis_id}/lots",
                method="POST",
                payload={},
                token=token,
                origin="chrome-extension://test-extension",
            )
            self.assertEqual(status, 200)
            self.assertEqual(len(json.loads(body)["lots"]), 1)

    def test_authenticated_analysis_lot_rejects_zero_download_auth_failure_even_with_exit_zero(self):
        with running_server() as (root, server, base):
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://test-extension",
            )
            token = json.loads(pair_body)["token"]
            payload = {
                "spec": {
                    "schema_version": 2,
                    "source_scope": "sector_finalistic",
                    "marker": {"label": "Marcador", "value": "m-1"},
                    "acquisition_source": "econtas",
                    "lot_size": 50,
                    "analysis_only": True,
                    "auto_prepare": True,
                    "auto_submit": False,
                    "dataset_sha256": None,
                    "area_snapshot_sha256": "b" * 64,
                },
                "observed_at": "2026-09-10T12:00:00+00:00",
                "rows": [{
                    "process_key": "100/2026",
                    "interested_key": "person-1",
                    "area_restrita": {
                        "scope": "sector_finalistic",
                        "marker_label": "Marcador",
                        "marker_value": "m-1",
                        "needs_complement": True,
                        "action_observed": "Complementar Ato",
                        "action_signature": {"kind": "red_complement_icon", "alt": "Complementar Ato", "title": "Complementar Ato", "src": "icone-vermelho.png"},
                        "snapshot_hash": "a" * 64,
                    },
                    "econtas": {
                        "match": "missing",
                        "documents": [],
                        "snapshot_hash": None,
                        "ocr_status": "not_run",
                    },
                }],
            }
            _status, _headers, body = json_request(
                f"{base}/api/v1/analysis/preview",
                method="POST",
                payload=payload,
                token=token,
                origin="chrome-extension://test-extension",
            )
            analysis = json.loads(body)
            analysis_id = analysis["analysis_id"]
            json_request(
                f"{base}/api/v1/analysis/{analysis_id}/lots",
                method="POST",
                payload={},
                token=token,
                origin="chrome-extension://test-extension",
            )

            process = MagicMock()
            process.pid = 4321
            process.poll.return_value = None
            with patch.object(local_service.subprocess, "Popen", return_value=process) as popen:
                status, _headers, body = json_request(
                    f"{base}/api/v1/analysis/{analysis_id}/acquire",
                    method="POST",
                    payload={"selection": "lot", "lot_number": 1},
                    token=token,
                    origin="chrome-extension://test-extension",
                )

            started = json.loads(body)
            self.assertEqual(status, 202)
            self.assertEqual(started["status"], "started")
            self.assertEqual(started["lot_number"], 1)
            command = popen.call_args.args[0]
            self.assertIn("-FilaCongelada", command)
            self.assertIn("-NumeroLote", command)
            self.assertIn("1", command)
            self.assertIn("-NaoInterativo", command)
            self.assertIn("-ServiceChild", command)
            self.assertNotIn("-enable-real-send", " ".join(command).lower())

            status, _headers, body = json_request(
                f"{base}/api/v1/analysis/{analysis_id}/acquire/{started['job_id']}",
                token=token,
                origin="chrome-extension://test-extension",
            )
            self.assertEqual(status, 200)
            running = json.loads(body)
            self.assertEqual(running["status"], "running")
            self.assertEqual(running["lot"]["status"], "running")
            self.assertEqual(running["items"][0]["status"], "running")
            self.assertNotIn(str(root), json.dumps(running))
            log_path = root / "automacao" / "coletas" / f"{started['job_id']}.log"
            log_path.write_text(
                "Sessão expirada ou não autorizada. Faça login novamente antes de retomar a coleta.\n"
                "Concluído (progressivo). Baixados: 0; reutilizados: 0; deduplicados: 0; processos com falha: 1.\n",
                encoding="utf-8",
            )
            process.poll.return_value = 0
            status, _headers, body = json_request(
                f"{base}/api/v1/analysis/{analysis_id}/acquire/{started['job_id']}",
                token=token,
                origin="chrome-extension://test-extension",
            )
            self.assertEqual(status, 200)
            zero_download_auth_failure = json.loads(body)
            self.assertEqual(zero_download_auth_failure["status"], "failed")
            self.assertEqual(zero_download_auth_failure["lot"]["status"], "failed")
            self.assertEqual(zero_download_auth_failure["items"][0]["status"], "failed")
            self.assertNotEqual(zero_download_auth_failure["status"], "completed")
            process.poll.return_value = 23
            status, _headers, body = json_request(
                f"{base}/api/v1/analysis/{analysis_id}/acquire/{started['job_id']}",
                token=token,
                origin="chrome-extension://test-extension",
            )
            self.assertEqual(status, 200)
            failed = json.loads(body)
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["lot"]["status"], "failed")
            self.assertEqual(failed["items"][0]["status"], "failed")
            self.assertNotEqual(failed["lot"]["status"], "completed")

    def test_portable_service_metadata_pairs_and_reaches_capabilities(self):
        """Exercise the package startup boundary, not only an in-process server."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "acervo-tce"
            bridge = root / "dados-locais" / "bridge"
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    str(APP_ROOT / "local_service.py"),
                    "--root",
                    str(archive),
                    "--bridge-root",
                    str(bridge),
                    "--port",
                    "0",
                ],
                cwd=APP_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            metadata_path = bridge / "service.json"
            metadata = None
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        self.fail("serviço portátil encerrou antes de publicar service.json")
                    if metadata_path.is_file():
                        try:
                            candidate = json.loads(metadata_path.read_text(encoding="utf-8"))
                        except json.JSONDecodeError:
                            candidate = None
                        if isinstance(candidate, dict) and candidate.get("pairing_code"):
                            metadata = candidate
                            break
                    time.sleep(0.05)

                self.assertIsNotNone(metadata)
                assert metadata is not None
                self.assertEqual(metadata["schema_version"], 1)
                self.assertEqual(metadata["pid"], process.pid)
                self.assertGreater(metadata["port"], 0)
                self.assertRegex(metadata["pairing_code"], r"^\d{8}$")

                base = f"http://127.0.0.1:{metadata['port']}"
                status, _headers, pair_body = json_request(
                    f"{base}/api/v1/pair",
                    method="POST",
                    payload={"code": metadata["pairing_code"]},
                    origin="chrome-extension://test-extension",
                )
                self.assertEqual(status, 200)
                token = json.loads(pair_body)["token"]
                self.assertNotEqual(token, metadata["pairing_code"])

                status, _headers, capabilities_body = json_request(
                    f"{base}/api/v1/automation/capabilities",
                    token=token,
                    origin="chrome-extension://test-extension",
                )
                self.assertEqual(status, 200)
                capabilities = json.loads(capabilities_body)
                self.assertEqual(capabilities["api_version"], 1)
                self.assertFalse(capabilities["real_send_enabled"])
                self.assertNotIn(token, json.dumps(capabilities))

                with self.assertRaises(HTTPError) as error:
                    json_request(
                        f"{base}/api/v1/pair",
                        method="POST",
                        payload={"code": metadata["pairing_code"]},
                        origin="chrome-extension://test-extension",
                    )
                self.assertEqual(error.exception.code, 401)
                error.exception.close()
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)

    def test_private_state_requires_auth(self):
        with running_server() as (_root, _server, base):
            with self.assertRaises(HTTPError) as error:
                urlopen(f"{base}/api/v1/state", timeout=3)
            self.assertEqual(error.exception.code, 401)

    def test_browser_omitted_origin_is_allowed_for_authenticated_reads_only(self):
        with running_server() as (_root, server, base):
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://test-extension",
            )
            token = json.loads(pair_body)["token"]

            status, _headers, capabilities_body = json_request(
                f"{base}/api/v1/automation/capabilities",
                token=token,
                omit_origin=True,
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(capabilities_body)["api_version"], 1)

            with self.assertRaises(HTTPError) as error:
                json_request(
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
                    omit_origin=True,
                )
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
                origin="chrome-extension://test-extension",
            )
            self.assertEqual(status, 200)

            status, _headers, body = json_request(
                f"{base}/api/v1/progress/103439%2F2023",
                method="PUT",
                payload={"completed": True, "expected_revision": 0},
                token=token,
                origin="chrome-extension://test-extension",
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["revision"], 1)

            with self.assertRaises(HTTPError) as error:
                json_request(
                    f"{base}/api/v1/progress/103439%2F2023",
                    method="PUT",
                    payload={"completed": False, "expected_revision": 0},
                    token=token,
                    origin="chrome-extension://test-extension",
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

            status, headers, session_body = json_request(
                f"{base}/api/v1/review-session",
                method="POST",
                payload={"code": server.review_bootstrap_code},
                origin=base,
            )
            self.assertEqual(status, 200)
            cookie = headers["Set-Cookie"].split(";", 1)[0]
            csrf = json.loads(session_body)["csrf_token"]
            self.assertTrue(csrf)
            self.assertIn("tce_csrf=", "\n".join(headers.get_all("Set-Cookie", [])))
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
            self.assertIn('href="/app/web/review.css"', body.decode("utf-8"))
            self.assertIn('src="/app/web/review-app.js"', body.decode("utf-8"))
            self.assertIn("Content-Security-Policy", headers)

            status, _headers, body = json_request(f"{base}/api/v1/state?since=-1", cookie=cookie)
            self.assertEqual(status, 200)
            self.assertIn("selection", json.loads(body))

            status, _headers, body = json_request(
                f"{base}/api/v1/progress/103439%2F2023",
                method="PUT",
                cookie=cookie,
                payload={"completed": True, "expected_revision": 0},
                origin=base,
                csrf=csrf,
            )
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["state"]["processes"]["103439/2023"]["completed"])

    def test_bearer_requests_without_origin_are_rejected(self):
        with running_server() as (_root, server, base):
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://test-extension",
            )
            token = json.loads(pair_body)["token"]
            with self.assertRaises(HTTPError) as error:
                json_request(f"{base}/api/v1/state", token=token, omit_origin=True)
            self.assertEqual(error.exception.code, 401)

    def test_invalid_extension_bearer_is_401_and_valid_bearer_can_resume(self):
        with running_server() as (root, server, base):
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://test-extension",
            )
            token = json.loads(pair_body)["token"]
            payload = {"completed": True, "expected_revision": 0}

            with self.assertRaises(HTTPError) as error:
                json_request(
                    f"{base}/api/v1/progress/103439%2F2023",
                    method="PUT",
                    cookie=None,
                    payload=payload,
                    token="invalid-token",
                    origin="chrome-extension://test-extension",
                )
            self.assertEqual(error.exception.code, 401)
            error.exception.close()

            status, _headers, body = json_request(
                f"{base}/api/v1/progress/103439%2F2023",
                method="PUT",
                payload=payload,
                token=token,
                origin="chrome-extension://test-extension",
            )
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["state"]["processes"]["103439/2023"]["completed"])
            self.assertTrue((root / "progresso.json").is_file())

    def test_review_mutation_requires_local_origin_and_csrf_token(self):
        with running_server() as (_root, server, base):
            status, headers, body = json_request(f"{base}/api/v1/review-session", method="POST", payload={"code": server.review_bootstrap_code}, origin=base)
            self.assertEqual(status, 200)
            cookie = headers["Set-Cookie"].split(";", 1)[0]
            csrf = json.loads(body)["csrf_token"]

            with self.assertRaises(HTTPError) as error:
                json_request(
                    f"{base}/api/v1/progress/103439%2F2023",
                    method="PUT",
                    cookie=cookie,
                    payload={"completed": True, "expected_revision": 0},
                    origin=base,
                )
            self.assertEqual(error.exception.code, 403)

            with self.assertRaises(HTTPError) as error:
                json_request(
                    f"{base}/api/v1/progress/103439%2F2023",
                    method="PUT",
                    cookie=cookie,
                    payload={"completed": True, "expected_revision": 0},
                    csrf=csrf,
                    omit_origin=True,
                )
            self.assertEqual(error.exception.code, 403)

            with self.assertRaises(HTTPError) as error:
                json_request(
                    f"{base}/api/v1/progress/103439%2F2023",
                    method="PUT",
                    cookie=cookie,
                    payload={"completed": True, "expected_revision": 0},
                    origin="http://127.0.0.1:1",
                    csrf=csrf,
                )
            self.assertEqual(error.exception.code, 403)

    def test_selection_rejects_invalid_coordinates_and_non_positive_sequence(self):
        with running_server() as (_root, server, base):
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair", method="POST", payload={"code": code}, origin="chrome-extension://test-extension"
            )
            token = json.loads(pair_body)["token"]
            selection = {
                "process_key": "103439/2023",
                "interested_normalized": "pessoa teste",
                "tab_id": 1,
                "frame_id": 0,
                "sequence": 1,
            }
            for key, value in (("tab_id", -1), ("frame_id", -1), ("sequence", 0)):
                invalid = {**selection, key: value}
                with self.assertRaises(HTTPError) as error:
                    json_request(f"{base}/api/v1/selection", method="POST", payload=invalid, token=token)
                self.assertEqual(error.exception.code, 400)

    def test_selection_discards_an_old_sequence_explicitly(self):
        with running_server() as (_root, server, base):
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair", method="POST", payload={"code": code}, origin="chrome-extension://test-extension"
            )
            token = json.loads(pair_body)["token"]
            selection = {
                "process_key": "103439/2023",
                "interested_normalized": "pessoa teste",
                "tab_id": 1,
                "frame_id": 0,
                "sequence": 2,
            }
            status, _headers, body = json_request(f"{base}/api/v1/selection", method="POST", payload=selection, token=token)
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["accepted"])
            status, _headers, body = json_request(
                f"{base}/api/v1/selection", method="POST", payload={**selection, "sequence": 1}, token=token
            )
            self.assertEqual(status, 200)
            self.assertFalse(json.loads(body)["accepted"])
            self.assertEqual(json.loads(body)["discarded_sequence"], 1)

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

            with self.assertRaises(HTTPError) as error:
                json_request(f"{base}/api/v1/pdf/doc-1", token=token, range_header="bytes=0-1,3-4")
            self.assertEqual(error.exception.code, 416)

    def test_corrupt_publication_pointer_does_not_fallback_to_legacy_dataset(self):
        with running_server() as (root, server, base):
            (root / "publicacao-atual.json").write_text("{broken", encoding="utf-8")
            (root / "dados-complementar-ato.json").write_text(
                json.dumps({"schema_version": 1, "records": []}), encoding="utf-8"
            )
            code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": code},
                origin="chrome-extension://test-extension",
            )
            token = json.loads(pair_body)["token"]

            with self.assertRaises(HTTPError) as error:
                json_request(f"{base}/api/v1/dataset", token=token)
            self.assertEqual(error.exception.code, 500)
            error.exception.close()

    def test_pdf_rejects_internal_reparse_path(self):
        with running_server() as (root, server, base):
            real = root / "real.pdf"
            alias = root / "alias.pdf"
            real.write_bytes(b"payload")
            try:
                os.symlink(real, alias)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"ambiente sem criação de symlink: {exc}")
            (root / "evidencias-visuais.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "documents": {"doc-1": {"relative_path": "alias.pdf"}},
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

            with self.assertRaises(HTTPError) as error:
                json_request(f"{base}/api/v1/pdf/doc-1", token=token)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()

    def test_server_close_releases_state_lock_for_restart(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = create_server(root, port=0)
            port = first.server_port
            first.server_close()

            second = create_server(root, port=port)
            second.server_close()

    def test_occupied_port_uses_loopback_fallback(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            requested_port = occupied.getsockname()[1]
            with TemporaryDirectory() as temporary:
                server = create_server(Path(temporary), port=requested_port)
                try:
                    self.assertNotEqual(server.server_port, requested_port)
                    self.assertEqual(server.server_address[0], "127.0.0.1")
                finally:
                    server.server_close()

    def test_health_rejects_null_origin_and_forged_host(self):
        with running_server() as (_root, server, base):
            with self.assertRaises(HTTPError) as error:
                json_request(f"{base}/api/v1/health", origin="null")
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

            with self.assertRaises(HTTPError) as error:
                json_request(
                    f"{base}/api/v1/health",
                    host=f"127.0.0.1:{server.server_port + 1}",
                )
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

    def test_service_failure_reports_manual_fallback_without_leaving_lock(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            bridge_root = root / "dados-locais" / "bridge"
            with patch.object(local_service, "create_server", side_effect=OSError("porta ocupada")):
                with redirect_stderr(io.StringIO()) as error_output:
                    result = local_service.main(
                        [
                            "--root",
                            str(root / "acervo-tce"),
                            "--bridge-root",
                            str(bridge_root),
                            "--port",
                            "0",
                        ]
                    )

            self.assertEqual(result, 2)
            self.assertIn("modo manual", error_output.getvalue().lower())
            self.assertFalse((bridge_root / ".operation.lock").exists())


if __name__ == "__main__":
    unittest.main()
