"""Tests for the read-only Área Restrita CDP compatibility fallback (M2 Task 6)."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.area_restrita.cdp_fallback import (
    CdpScanError,
    build_cdp_scan_command,
    parse_cdp_output,
    persist_cdp_scan,
    run_cdp_scan,
)
from app.core.store import Store

REPO_ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT = {
    "role": "list",
    "source_scope": "sector_finalistic",
    "marker": {"label": "PROFESSOR - IPERN - 2 RUBRICAS", "value": "6189"},
    "page": 1,
    "total_pages": 1,
    "rows": [
        {
            "process_key": "102390/2026",
            "interested": "Pessoa Exemplo",
            "interested_normalized": "pessoa exemplo",
            "portal_act_id": "123",
            "classification": "PRECISA_COMPLEMENTAR",
            "needs_complement": True,
            "action_observed": "Complementar Ato",
        },
        {
            "process_key": "102391/2026",
            "interested": "Outra Pessoa",
            "interested_normalized": "outra pessoa",
            "portal_act_id": None,
            "classification": "ATO_COMPLEMENTADO",
            "needs_complement": False,
            "action_observed": "Ato Complementado",
        },
    ],
}


class CdpCommandTests(unittest.TestCase):
    def test_command_invokes_the_read_only_script(self):
        command = build_cdp_scan_command(REPO_ROOT)
        joined = " ".join(command)

        self.assertIn("scan-area-cdp.ps1", joined)
        self.assertIn("powershell", command[0].casefold())
        self.assertIn("-NonInteractive", command)

    def test_command_carries_no_write_or_credential_argument(self):
        joined = " ".join(build_cdp_scan_command(REPO_ROOT)).casefold()

        for forbidden in (
            "submit",
            "submeter",
            "finalizar",
            "cookie",
            "password",
            "senha",
            "credential",
            "-credential",
            "auto_submit",
            "real_send_enabled",
            "complementarato",
            "open_act",
            "fill_form",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, joined)

    def test_the_script_itself_never_writes_or_submits(self):
        source = (REPO_ROOT / "scripts" / "scan-area-cdp.ps1").read_text(encoding="utf-8")

        self.assertIn("Runtime.evaluate", source)
        for forbidden in (
            "Submit",
            "Finalizar",
            "BtnComplementar",
            "AUTO_SUBMIT",
            "real_send_enabled",
            "autoSubmit",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        # Only pagination may be driven, and only through the shared scanner.
        self.assertIn("findNextPageControl", source)
        self.assertIn("area-snapshot.js", source)

    def test_script_suppresses_the_websocket_connect_result(self):
        source = (REPO_ROOT / "scripts" / "scan-area-cdp.ps1").read_text(encoding="utf-8")

        self.assertRegex(source, r"\[void\]\s*\$socket\.ConnectAsync\(")

    def test_script_refuses_to_emit_non_list_snapshots(self):
        source = (REPO_ROOT / "scripts" / "scan-area-cdp.ps1").read_text(encoding="utf-8")

        self.assertIn("if ([string]$snapshot.role -ne 'list')", source)
        self.assertIn("não está numa lista reconhecida", source)

    def test_script_uses_allowlisted_legacy_pagination_and_checks_progress(self):
        source = (REPO_ROOT / "scripts" / "scan-area-cdp.ps1").read_text(encoding="utf-8")

        self.assertIn("legacyPaginationPlan", source)
        self.assertIn("submitLegacyPagination", source)
        self.assertIn("a paginação não avançou", source)

    def test_marker_continuity_uses_stable_value_not_dynamic_count_label(self):
        source = (REPO_ROOT / "scripts" / "scan-area-cdp.ps1").read_text(encoding="utf-8")

        self.assertIn("function Get-MarkerSignature", source)
        self.assertIn("$Marker.value", source)
        self.assertIn("Get-MarkerSignature -Marker $pendingSnapshot.marker", source)

    def test_script_requires_exact_page_progress_and_complete_coverage(self):
        source = (REPO_ROOT / "scripts" / "scan-area-cdp.ps1").read_text(encoding="utf-8")

        self.assertIn("if ($lastPage -eq $ExpectedPage) { return $snapshot }", source)
        self.assertIn("if ($pagesVisited -ne [int]$last.total_pages)", source)

    def test_script_prefers_the_newest_page_even_when_the_last_page_is_shorter(self):
        source = (REPO_ROOT / "scripts" / "scan-area-cdp.ps1").read_text(encoding="utf-8")

        self.assertIn("right.page - left.page || right.rows.length - left.rows.length", source)

    @unittest.skipUnless(shutil.which("powershell.exe"), "requires Windows PowerShell")
    def test_script_resolves_default_repo_root_after_parameter_binding(self):
        script = REPO_ROOT / "scripts" / "scan-area-cdp.ps1"
        with TemporaryDirectory() as chrome_profile:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-ChromeUserData",
                    chrome_profile,
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                timeout=15,
            )

        output = (result.stdout + result.stderr).decode(errors="replace")
        self.assertNotIn("Split-Path", output)
        self.assertIn("DevToolsActivePort", output)

    @unittest.skipUnless(shutil.which("powershell.exe"), "requires Windows PowerShell")
    def test_script_can_resolve_websocket_from_an_explicit_cdp_port(self):
        script = REPO_ROOT / "scripts" / "scan-area-cdp.ps1"
        with TemporaryDirectory() as chrome_profile:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-ChromeUserData",
                    chrome_profile,
                    "-CdpPort",
                    "1",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                timeout=15,
            )

        output = (result.stdout + result.stderr).decode(errors="replace")
        self.assertNotIn("DevToolsActivePort", output)
        self.assertIn("127.0.0.1:1/json/version", output)


class CdpOutputTests(unittest.TestCase):
    def test_the_last_json_object_on_stdout_wins(self):
        stdout = 'aviso do PowerShell\n{"role": "list", "rows": []}\n'

        self.assertEqual(parse_cdp_output(stdout), {"role": "list", "rows": []})

    def test_stdout_without_json_is_an_error(self):
        with self.assertRaises(CdpScanError):
            parse_cdp_output("nada aqui")

    def test_a_non_object_payload_is_refused(self):
        with self.assertRaises(CdpScanError):
            parse_cdp_output("[1, 2, 3]")


class CdpRunnerTests(unittest.TestCase):
    def run_with(self, *, returncode=0, stdout="", stderr=""):
        def runner(command, **kwargs):
            runner.command = command
            runner.kwargs = kwargs
            return subprocess.CompletedProcess(command, returncode, stdout, stderr)

        return run_cdp_scan(REPO_ROOT, runner=runner)

    def test_a_successful_run_returns_the_snapshot(self):
        result = self.run_with(stdout=json.dumps(SNAPSHOT))

        self.assertTrue(result.ok)
        self.assertEqual(result.snapshot["rows"][0]["process_key"], "102390/2026")
        self.assertEqual(result.snapshot["role"], "list")

    def test_a_failed_run_reports_a_safe_error(self):
        result = self.run_with(returncode=1, stderr="senha super secreta")

        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertNotIn("super secreta", result.error)

    def test_a_missing_script_is_reported(self):
        result = run_cdp_scan(REPO_ROOT / "nao-existe", runner=lambda *a, **k: None)

        self.assertFalse(result.ok)
        self.assertIn("scan-area-cdp.ps1", result.error)

    def test_a_snapshot_without_the_portal_role_is_refused(self):
        result = self.run_with(stdout=json.dumps({"rows": []}))

        self.assertFalse(result.ok)
        self.assertIn("role", result.error)


class CdpPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Store.open(Path(self._tmp.name) / "atos-tce.db")
        self.addCleanup(self.store.close)

    def test_the_cdp_snapshot_uses_the_same_store_path(self):
        scan_id = persist_cdp_scan(self.store, SNAPSHOT)

        scan = self.store.get_area_scan(scan_id)
        self.assertEqual(scan["origin"], "cdp")
        self.assertEqual(scan["total"], 2)
        self.assertEqual(scan["pending"], 1)
        self.assertEqual(scan["completed"], 1)
        self.assertEqual(scan["marker_value"], "6189")
        self.assertEqual(scan["source_scope"], "sector_finalistic")

        processes = {row["process_key"]: row for row in self.store.list_processes()}
        self.assertEqual(processes["102390/2026"]["status"], "PENDENTE")
        self.assertEqual(processes["102390/2026"]["needs_complement"], 1)
        self.assertEqual(processes["102391/2026"]["status"], "CONCLUÍDO")

    def test_the_same_payload_produces_the_same_rows_as_the_extension(self):
        extension_scan = persist_cdp_scan(self.store, SNAPSHOT, origin="extension")
        cdp_scan = persist_cdp_scan(self.store, SNAPSHOT, origin="cdp")

        first = self.store.get_area_scan(extension_scan)["items"]
        second = self.store.get_area_scan(cdp_scan)["items"]
        self.assertEqual(
            [(item["process_key"], item["classification"]) for item in first],
            [(item["process_key"], item["classification"]) for item in second],
        )

    def test_a_malformed_snapshot_is_refused(self):
        with self.assertRaises(CdpScanError):
            persist_cdp_scan(self.store, {"rows": "nope"})

        with self.assertRaises(CdpScanError):
            persist_cdp_scan(self.store, {"role": "nada", "rows": []})

    def test_expected_keys_match_between_extension_and_cdp(self):
        def keys(payload):
            return sorted(row["process_key"] for row in payload["rows"])

        self.assertEqual(keys(SNAPSHOT), ["102390/2026", "102391/2026"])


if __name__ == "__main__":
    unittest.main()
