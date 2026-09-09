"""TDD contract tests for durable automation reports."""

from __future__ import annotations

import csv
import importlib.util
from io import StringIO
import json
from pathlib import Path
import shutil
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

    def _store_with_report_data(self, root=None, identities=None):
        from automation_store import AutomationStore

        store = AutomationStore(self.root if root is None else root)
        store.create_run({"run_id": "run-report", "schema_version": 1})
        store.freeze_queue(
            "run-report",
            identities or [{"process_key": "103439/2023"}],
            "queue-report",
            0,
        )
        store.append_event(
            "run-report",
            {
                "event_id": "prepare-report",
                "type": "item_prepared",
                "expected_revision": 1,
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
                "expected_revision": 2,
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
                "expected_revision": 3,
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

    def test_html_and_csv_redact_sensitive_text_in_error_and_source(self) -> None:
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)
        store.append_event(
            "run-report",
            {
                "event_id": "sensitive-text-report",
                "type": "item_failed",
                "expected_revision": 3,
                "item_id": "103439/2023",
                "error": (
                    "token=TOKEN-SECRET cookie=COOKIE-SECRET "
                    "cpf=987.654.321-00 "
                    "url=https://session.example.invalid/?sid=SESSION-SECRET "
                    r"path=C:\\private\\secret.pdf"
                ),
                "source": r"C:\\private\\source.pdf",
            },
        )
        result = render_run_reports(store, "run-report", self.root)
        contents = [
            Path(result["html_path"]).read_text(encoding="utf-8"),
            Path(result["csv_path"]).read_text(encoding="utf-8"),
        ]

        for content in contents:
            for secret in (
                "TOKEN-SECRET",
                "COOKIE-SECRET",
                "987.654.321-00",
                "session.example.invalid",
                "SESSION-SECRET",
                r"C:\\private\\secret.pdf",
                r"C:\\private\\source.pdf",
            ):
                self.assertNotIn(secret, content)

    def test_reports_allowlist_nested_payload_and_safe_citations(self) -> None:
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)
        store.append_event(
            "run-report",
            {
                "event_id": "nested-sensitive-report",
                "type": "item_failed",
                "expected_revision": 3,
                "item_id": "103439/2023",
                "error": (
                    "refresh_token=REFRESH-SECRET; "
                    "Cookie: a=ONE; sessionid=SESSION-SECRET; "
                    "csrftoken=CSRF-SECRET; cpf=12345678900; "
                    "www.session.example.invalid/private"
                ),
                "source": (
                    r"relative\private\source.pdf and C:\absolute\source.pdf"
                ),
                "fields": {
                    "observacao": {
                        "before": {
                            "nested": (
                                "refresh_token=NESTED-SECRET "
                                "https://session.example.invalid/?sid=URL-SECRET"
                            ),
                            "numeric_cpf": 98765432100,
                            "relative_path": "./nested/private.pdf",
                        },
                        "after": "visible legal text",
                    }
                },
                "citations": [
                    {
                        "document_id": "document-7",
                        "page_id": "page-4",
                        "page": 4,
                        "label": "Acórdão <seguro>",
                        "url": "https://session.example.invalid/citation",
                        "path": r"C:\private\citation.pdf",
                        "document": "LEGACY-DOCUMENT-SECRET",
                    }
                ],
                "unknown_field": "MUST-NOT-BE-EMITTED",
            },
        )

        result = render_run_reports(store, "run-report", self.root)
        contents = [
            Path(result["html_path"]).read_text(encoding="utf-8"),
            Path(result["csv_path"]).read_text(encoding="utf-8"),
        ]

        for content in contents:
            for secret in (
                "REFRESH-SECRET",
                "SESSION-SECRET",
                "CSRF-SECRET",
                "12345678900",
                "98765432100",
                "www.session.example.invalid",
                "URL-SECRET",
                r"relative\private\source.pdf",
                r"C:\absolute\source.pdf",
                "MUST-NOT-BE-EMITTED",
                "LEGACY-DOCUMENT-SECRET",
                "citation.pdf",
            ):
                self.assertNotIn(secret, content)
            self.assertIn("document-7", content)
            self.assertIn("page-4", content)
            self.assertIn("Acórdão", content)

    def test_snapshot_recovery_sections_use_the_same_safe_projection(self) -> None:
        from automation_report import render_run_reports

        confirmed_root = self.root / "confirmed"
        confirmed = self._store_with_report_data(confirmed_root)
        self.addCleanup(confirmed.close)
        confirmed.append_event(
            "run-report",
            {
                "event_id": "confirmed-report",
                "type": "send_intent",
                "expected_revision": 3,
                "item_id": "103439/2023",
            },
        )
        confirmed.append_event(
            "run-report",
            {
                "event_id": "confirmed-result",
                "type": "send_confirmed",
                "expected_revision": 4,
                "item_id": "103439/2023",
                "metadata": {
                    "authToken": "AUTH-TOKEN-LEAK",
                    "apiKey": "API-KEY-LEAK",
                    "cpfValue": 1234567890,
                    "artifact": r"C:\private\confirmed.pdf",
                    "freeText": "CONFIRMED-FREE-PAYLOAD",
                },
            },
        )
        confirmed_result = render_run_reports(confirmed, "run-report", confirmed_root)
        confirmed_html = Path(confirmed_result["html_path"]).read_text(encoding="utf-8")

        interrupted_root = self.root / "interrupted"
        interrupted = self._store_with_report_data(
            interrupted_root,
            [
                {
                    "process_key": "103439/2023",
                    "metadata": {
                        "authToken": "INTERRUPTED-AUTH-TOKEN-LEAK",
                        "apiKey": "INTERRUPTED-API-KEY-LEAK",
                        "cpfValue": 1234567890,
                        "artifact": r"C:\private\interrupted.pdf",
                        "freeText": "INTERRUPTED-FREE-PAYLOAD",
                    },
                }
            ],
        )
        self.addCleanup(interrupted.close)
        interrupted.append_event(
            "run-report",
            {
                "event_id": "interrupted-intent",
                "type": "send_intent",
                "expected_revision": 3,
                "item_id": "103439/2023",
            },
        )
        interrupted_result = render_run_reports(
            interrupted, "run-report", interrupted_root
        )
        interrupted_html = Path(interrupted_result["html_path"]).read_text(
            encoding="utf-8"
        )

        for content in (confirmed_html, interrupted_html):
            for secret in (
                "AUTH-TOKEN-LEAK",
                "API-KEY-LEAK",
                "1234567890",
                r"C:\private\confirmed.pdf",
                "CONFIRMED-FREE-PAYLOAD",
                "INTERRUPTED-AUTH-TOKEN-LEAK",
                "INTERRUPTED-API-KEY-LEAK",
                "INTERRUPTED-FREE-PAYLOAD",
                r"C:\private\interrupted.pdf",
            ):
                self.assertNotIn(secret, content)

    def test_allowed_act_identities_remain_visible_but_real_paths_are_redacted(self) -> None:
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)
        store.append_event(
            "run-report",
            {
                "event_id": "identity-context-report",
                "type": "item_pending",
                "expected_revision": 3,
                "item_id": "103439/2023",
                "process_key": "103439/2023",
                "identity": {"process_key": "103439/2023"},
                "act_id": "ato-42",
                "source": r"C:\private\source.pdf",
            },
        )

        result = render_run_reports(store, "run-report", self.root)
        contents = [
            Path(result["html_path"]).read_text(encoding="utf-8"),
            Path(result["csv_path"]).read_text(encoding="utf-8"),
        ]

        for content in contents:
            self.assertIn("103439/2023", content)
            self.assertNotIn(r"C:\private\source.pdf", content)
        self.assertIn("ato-42", contents[0])

    def test_citations_without_document_or_page_id_are_discarded(self) -> None:
        from automation_report import render_run_reports

        cases = (
            ("page-only", [{"page": 8}]),
            ("label-only", [{"label": "INVALID-LABEL-ONLY"}]),
            ("string", ["INVALID-CITATION-STRING"]),
            ("arbitrary-object", [{"document": "INVALID-LEGACY-DOCUMENT"}]),
        )
        for suffix, citations in cases:
            with self.subTest(suffix=suffix):
                root = self.root / f"citation-context-{suffix}"
                store = self._store_with_report_data(root)
                self.addCleanup(store.close)
                store.append_event(
                    "run-report",
                    {
                        "event_id": f"invalid-citation-context-{suffix}",
                        "type": "item_failed",
                        "expected_revision": 3,
                        "item_id": "103439/2023",
                        "citations": citations,
                    },
                )

                result = render_run_reports(store, "run-report", root)
                contents = [
                    Path(result["html_path"]).read_text(encoding="utf-8"),
                    Path(result["csv_path"]).read_text(encoding="utf-8"),
                ]
                for content in contents:
                    self.assertNotIn("p.8", content)
                    self.assertNotIn("INVALID-LABEL-ONLY", content)
                    self.assertNotIn("INVALID-CITATION-STRING", content)
                    self.assertNotIn("INVALID-LEGACY-DOCUMENT", content)

    def test_malformed_citations_are_discarded_without_generic_payload_fallback(self) -> None:
        from automation_report import render_run_reports

        cases = (
            ("dict", {"unknown": "CITATION-DICT-LEAK"}),
            ("string", "CITATION-STRING-LEAK"),
            (
                "list",
                [
                    {
                        "document_id": "document-8",
                        "page_id": "page-8",
                        "page": 8,
                        "label": "Ato seguro",
                    },
                    {"unknown": "CITATION-LIST-LEAK"},
                    "CITATION-LIST-STRING-LEAK",
                ],
            ),
        )
        for suffix, citations in cases:
            with self.subTest(suffix=suffix):
                root = self.root / f"citation-{suffix}"
                store = self._store_with_report_data(root)
                self.addCleanup(store.close)
                store.append_event(
                    "run-report",
                    {
                        "event_id": f"invalid-citation-{suffix}",
                        "type": "item_failed",
                        "expected_revision": 3,
                        "item_id": "103439/2023",
                        "citations": citations,
                    },
                )
                result = render_run_reports(store, "run-report", root)
                contents = [
                    Path(result["html_path"]).read_text(encoding="utf-8"),
                    Path(result["csv_path"]).read_text(encoding="utf-8"),
                ]
                for content in contents:
                    self.assertNotIn("CITATION-DICT-LEAK", content)
                    self.assertNotIn("CITATION-STRING-LEAK", content)
                    self.assertNotIn("CITATION-LIST-LEAK", content)
                    self.assertNotIn("CITATION-LIST-STRING-LEAK", content)
                if suffix == "list":
                    self.assertIn("document-8", contents[0])
                    self.assertIn("page-8", contents[0])

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

    def test_failure_after_first_replace_preserves_published_generation(self) -> None:
        import automation_report
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)
        first = render_run_reports(store, "run-report", self.root)
        directory = self.root / "relatorios" / "complementacao" / "run-report"
        old_html = Path(first["html_path"]).read_bytes()
        old_csv = Path(first["csv_path"]).read_bytes()
        manifest_path = Path(first["manifest_path"])
        old_manifest = manifest_path.read_bytes()

        real_replace = automation_report.os.replace

        def fail_after_html(source, destination):
            if (
                Path(destination).parent == directory
                and Path(destination).name == "relatorio.csv"
            ):
                raise OSError("csv replace failed")
            return real_replace(source, destination)

        with patch.object(automation_report.os, "replace", side_effect=fail_after_html):
            with self.assertRaises(OSError):
                render_run_reports(store, "run-report", self.root)

        self.assertEqual(Path(first["html_path"]).read_bytes(), old_html)
        self.assertEqual(Path(first["csv_path"]).read_bytes(), old_csv)
        self.assertEqual(manifest_path.read_bytes(), old_manifest)
        self.assertEqual(list(directory.glob(".relatorio.*.tmp")), [])

    def test_tampered_existing_generation_fails_closed(self) -> None:
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)
        first = render_run_reports(store, "run-report", self.root)
        directory = self.root / "relatorios" / "complementacao" / "run-report"
        generation_html = (
            directory / ".generations" / first["generation"] / "relatorio.html"
        )
        old_html = Path(first["html_path"]).read_bytes()
        old_csv = Path(first["csv_path"]).read_bytes()
        manifest_path = Path(first["manifest_path"])
        old_manifest = manifest_path.read_bytes()
        generation_html.write_text("CORRUPTED-GENERATION", encoding="utf-8")

        with self.assertRaises(OSError):
            render_run_reports(store, "run-report", self.root)

        self.assertEqual(Path(first["html_path"]).read_bytes(), old_html)
        self.assertEqual(Path(first["csv_path"]).read_bytes(), old_csv)
        self.assertEqual(manifest_path.read_bytes(), old_manifest)
        self.assertEqual(generation_html.read_text(encoding="utf-8"), "CORRUPTED-GENERATION")
        self.assertEqual(list(directory.glob(".relatorio.*.tmp")), [])

    def test_divergent_manifest_hash_fails_closed(self) -> None:
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)
        first = render_run_reports(store, "run-report", self.root)
        directory = self.root / "relatorios" / "complementacao" / "run-report"
        html_path = Path(first["html_path"])
        csv_path = Path(first["csv_path"])
        manifest_path = Path(first["manifest_path"])
        old_html = html_path.read_bytes()
        old_csv = csv_path.read_bytes()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["html_sha256"] = "0" * 64
        divergent_manifest = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        manifest_path.write_text(divergent_manifest, encoding="utf-8")

        with self.assertRaises(OSError):
            render_run_reports(store, "run-report", self.root)

        self.assertEqual(html_path.read_bytes(), old_html)
        self.assertEqual(csv_path.read_bytes(), old_csv)
        self.assertEqual(manifest_path.read_text(encoding="utf-8"), divergent_manifest)
        self.assertEqual(list(directory.glob(".relatorio.*.tmp")), [])

    def test_divergent_generation_id_fails_closed_with_intact_files(self) -> None:
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)
        first = render_run_reports(store, "run-report", self.root)
        directory = self.root / "relatorios" / "complementacao" / "run-report"
        manifest_path = Path(first["manifest_path"])
        original_generation = directory / ".generations" / first["generation"]
        fake_generation_id = "f" * 64
        fake_generation = directory / ".generations" / fake_generation_id
        fake_generation.mkdir()
        shutil.copy2(
            original_generation / "relatorio.html", fake_generation / "relatorio.html"
        )
        shutil.copy2(
            original_generation / "relatorio.csv", fake_generation / "relatorio.csv"
        )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["generation"] = fake_generation_id
        manifest["html_path"] = f".generations/{fake_generation_id}/relatorio.html"
        manifest["csv_path"] = f".generations/{fake_generation_id}/relatorio.csv"
        divergent_manifest = json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, indent=2
        ) + "\n"
        manifest_path.write_text(divergent_manifest, encoding="utf-8")

        with self.assertRaises(OSError):
            render_run_reports(store, "run-report", self.root)

        self.assertEqual(manifest_path.read_text(encoding="utf-8"), divergent_manifest)
        self.assertEqual(
            Path(first["html_path"]).read_bytes(),
            (original_generation / "relatorio.html").read_bytes(),
        )
        self.assertEqual(
            Path(first["csv_path"]).read_bytes(),
            (original_generation / "relatorio.csv").read_bytes(),
        )

    def test_report_uses_snapshot_revision_as_event_upper_bound(self) -> None:
        from automation_report import render_run_reports

        store = self._store_with_report_data()
        self.addCleanup(store.close)

        class SnapshotAdvancingStore:
            def __init__(self, wrapped):
                self.wrapped = wrapped

            def snapshot(self, run_id):
                snapshot = self.wrapped.snapshot(run_id)
                self.wrapped.append_event(
                    run_id,
                    {
                        "event_id": "late-report-event",
                        "type": "item_failed",
                        "expected_revision": snapshot["revision"],
                        "item_id": "103439/2023",
                    },
                )
                return snapshot

            def get_events(self, run_id, after=0, through=None):
                return self.wrapped.get_events(run_id, after=after, through=through)

        result = render_run_reports(SnapshotAdvancingStore(store), "run-report", self.root)

        self.assertEqual(result["revision"], 3)
        self.assertEqual(result["event_count"], 3)
        html = Path(result["html_path"]).read_text(encoding="utf-8")
        self.assertNotIn("late-report-event", html)


if __name__ == "__main__":
    unittest.main()
