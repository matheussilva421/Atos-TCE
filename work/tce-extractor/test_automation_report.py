"""TDD contract tests for durable automation reports."""

from __future__ import annotations

import csv
import importlib.util
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))


class AutomationReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertIsNotNone(
            importlib.util.find_spec("automation_report"),
            "automation_report.py must exist before the production implementation",
        )
        self.assertIsNotNone(importlib.util.find_spec("automation_store"))

    def _store_with_report_data(self):
        from automation_store import AutomationStore

        store = AutomationStore(self.root)
        store.create_run({"run_id": "run-report", "schema_version": 1})
        store.freeze_queue(
            "run-report",
            [{"process_key": "103439/2023"}],
            "queue-report",
            0,
        )
        store.append_event(
            "run-report",
            {
                "event_id": "prepare-report",
                "type": "item_prepared",
                "item_id": "103439/2023",
                "before": {"fundamento": "=old"},
                "after": {"fundamento": "+new"},
                "rereads": [{"source": "document-7", "page": 4}],
                "legal_decision": {"status": "selected", "rule_id": "EC41_SEM_P5"},
                "citations": [{"document_id": "document-7", "page": 4}],
                "timestamp": "2026-09-08T20:00:00+00:00",
                "error": None,
            },
        )
        store.append_event(
            "run-report",
            {
                "event_id": "filled-report",
                "type": "fields_verified",
                "item_id": "103439/2023",
                "fields": {
                    "fundamento": {
                        "before": "old",
                        "after": "new",
                        "method": "exact",
                        "source": "document-7",
                    }
                },
            },
        )
        return store

    def test_render_writes_atomic_html_and_csv_without_mutating_store(self) -> None:
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)
        before = store.snapshot("run-report")

        result = render_run_reports(store, "run-report", self.root)
        html_path = self.root / "relatorios" / "complementacao" / "run-report" / "relatorio.html"
        csv_path = self.root / "relatorios" / "complementacao" / "run-report" / "relatorio.csv"

        self.assertEqual(result["run_id"], "run-report")
        self.assertTrue(html_path.is_file())
        self.assertTrue(csv_path.is_file())
        self.assertEqual(store.snapshot("run-report"), before)
        self.assertEqual(result, render_run_reports(store, "run-report", self.root))

    def test_html_escapes_payload_and_report_contains_recovery_fields(self) -> None:
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)
        store.append_event(
            "run-report",
            {
                "event_id": "unsafe-report",
                "type": "item_failed",
                "item_id": "103439/2023",
                "error": "<script>alert('x')</script>",
                "url": "https://session.example.invalid/?token=secret",
                "path": r"C:\private\secret.pdf",
                "cpf": "123.456.789-00",
                "before": {"html": "<b>before</b>"},
                "after": {"html": "<i>after</i>"},
            },
        )
        result = render_run_reports(store, "run-report", self.root)
        html = Path(result["html_path"]).read_text(encoding="utf-8")

        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Último confirmado", html)
        self.assertIn("Item interrompido", html)
        self.assertNotIn("session.example.invalid", html)
        self.assertNotIn("123.456.789-00", html)
        self.assertNotIn("C:\\private\\secret.pdf", html)

    def test_csv_has_field_rows_and_neutralizes_formula_prefixes(self) -> None:
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)
        result = render_run_reports(store, "run-report", self.root)
        rows = list(csv.DictReader(StringIO(Path(result["csv_path"]).read_text(encoding="utf-8"))))

        fundamento_rows = [row for row in rows if row["field"] == "fundamento"]
        self.assertTrue(fundamento_rows)
        self.assertEqual(fundamento_rows[-1]["method"], "exact")
        self.assertEqual(fundamento_rows[-1]["source"], "document-7")
        self.assertTrue(fundamento_rows[0]["before"].startswith("'"))
        self.assertTrue(fundamento_rows[0]["after"].startswith("'"))
        content = Path(result["csv_path"]).read_text(encoding="utf-8")
        self.assertNotIn("session.example.invalid", content)

    def test_failed_replace_preserves_previous_reports_and_removes_temporaries(self) -> None:
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)
        render_run_reports(store, "run-report", self.root)
        directory = self.root / "relatorios" / "complementacao" / "run-report"
        old_html = (directory / "relatorio.html").read_bytes()
        old_csv = (directory / "relatorio.csv").read_bytes()

        with patch("automation_report.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                render_run_reports(store, "run-report", self.root)

        self.assertEqual((directory / "relatorio.html").read_bytes(), old_html)
        self.assertEqual((directory / "relatorio.csv").read_bytes(), old_csv)
        self.assertEqual(list(directory.glob(".relatorio.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
