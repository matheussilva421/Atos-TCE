from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
import zipfile

from app.area_restrita.diagnostics import DiagnosticRecorder


class DiagnosticRecorderStartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name)

    def test_new_recorder_starts_on_and_restart_starts_a_new_on_session(self) -> None:
        first_recorder = DiagnosticRecorder(
            self.data_root,
            build_id="build-test",
            extension_version="1.2.3",
        )

        settings_path = self.data_root / "diagnostics" / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        first_status = first_recorder.status()

        self.assertIs(settings["diagnostic_enabled"], True)
        self.assertIs(first_status["active"], True)
        first_recorder.pause()

        second_recorder = DiagnosticRecorder(
            self.data_root,
            build_id="build-test",
            extension_version="1.2.3",
        )
        second_status = second_recorder.status()
        restarted_settings = json.loads(settings_path.read_text(encoding="utf-8"))

        self.assertIs(restarted_settings["diagnostic_enabled"], True)
        self.assertIs(second_status["active"], True)
        self.assertNotEqual(first_status["session_id"], second_status["session_id"])


class DiagnosticRecorderEventTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name)
        self.timestamp = datetime(2026, 10, 6, 12, 30, tzinfo=timezone.utc)
        self.recorder = DiagnosticRecorder(
            self.data_root,
            build_id="build-test",
            extension_version="1.2.3",
            utcnow=lambda: self.timestamp,
        )

    def read_events(self) -> list[dict[str, object]]:
        path = next((self.data_root / "diagnostics" / "sessions").glob("*.jsonl"))
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_record_stamps_session_timestamp_component_step_and_duration(self) -> None:
        self.assertTrue(
            self.recorder.record(
                {
                    "component": "extension",
                    "step": "form_detected",
                    "elapsed_ms": 84,
                    "result": "ok",
                }
            )
        )

        event = self.read_events()[0]
        self.assertEqual(event["timestamp"], "2026-10-06T12:30:00+00:00")
        self.assertEqual(event["session_id"], self.recorder.status()["session_id"])
        self.assertEqual(event["component"], "extension")
        self.assertEqual(event["step"], "form_detected")
        self.assertEqual(event["elapsed_ms"], 84)

    def test_record_marks_exactly_two_seconds_slow(self) -> None:
        self.recorder.record({"component": "extension", "step": "fast", "elapsed_ms": 1999})
        self.recorder.record({"component": "extension", "step": "slow", "elapsed_ms": 2000})

        fast, slow = self.read_events()
        self.assertNotIn("severity", fast)
        self.assertEqual(slow["severity"], "SLOW")

    def test_record_preserves_result_code_and_redacts_full_error_text(self) -> None:
        self.recorder.record(
            {
                "component": "mesa",
                "step": "command_result",
                "code": "FORM_NOT_AVAILABLE",
                "error": "Authorization: Bearer usable-secret-token; command timed out",
            }
        )

        event = self.read_events()[0]
        self.assertEqual(event["code"], "FORM_NOT_AVAILABLE")
        self.assertIn("command timed out", event["error"])
        self.assertNotIn("usable-secret-token", json.dumps(event))

    def test_record_redacts_secret_keys_and_text_and_strips_url_query(self) -> None:
        self.recorder.record(
            {
                "component": "extension",
                "step": "portal_detected",
                "url": "https://user:pass@example.test/form?token=url-secret#fragment-secret",
                "password": "password-secret",
                "cookie": "cookie-secret",
                "extra": "not-allowlisted",
                "fields": {"headers": {"Authorization": "Bearer nested-secret"}},
                "error": "token=text-secret; Cookie: session=cookie-one; auth=cookie-two; diagnostic detail",
            }
        )

        serialized = json.dumps(self.read_events()[0])
        self.assertIn("https://example.test/form", serialized)
        for secret in (
            "url-secret",
            "fragment-secret",
            "password-secret",
            "cookie-secret",
            "text-secret",
            "nested-secret",
            "cookie-one",
            "cookie-two",
        ):
            self.assertNotIn(secret, serialized)
        self.assertNotIn("not-allowlisted", serialized)

    def test_record_rejects_an_oversized_event_line(self) -> None:
        event = {"component": "extension", "step": "fields", "fields": {f"field-{index}": "x" * 4096 for index in range(100)}}

        self.assertFalse(self.recorder.record(event))
        self.assertEqual(self.read_events(), [])


class DiagnosticRecorderLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name)
        self.recorder = DiagnosticRecorder(
            self.data_root,
            build_id="build-test",
            extension_version="1.2.3",
        )

    def session_files(self) -> list[Path]:
        return list((self.data_root / "diagnostics" / "sessions").glob("*.jsonl"))

    def test_pause_blocks_events_and_resume_records_again(self) -> None:
        self.assertTrue(self.recorder.record({"component": "mesa", "step": "before_pause"}))
        self.assertIs(self.recorder.pause()["active"], False)
        self.assertFalse(self.recorder.record({"component": "mesa", "step": "paused"}))
        self.assertIs(self.recorder.resume()["active"], True)
        self.assertTrue(self.recorder.record({"component": "mesa", "step": "after_resume"}))

        events = [
            json.loads(line)
            for path in self.session_files()
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual([event["step"] for event in events], ["before_pause", "after_resume"])

    def test_clear_removes_prior_sessions_and_starts_a_fresh_session(self) -> None:
        self.recorder.record({"component": "mesa", "step": "before_clear"})
        previous_session = self.recorder.status()["session_id"]
        self.recorder.pause()

        cleared = self.recorder.clear()

        self.assertNotEqual(previous_session, cleared["session_id"])
        self.assertIs(cleared["active"], False)
        self.assertEqual(cleared["event_count"], 0)
        self.assertEqual(len(self.session_files()), 1)
        self.assertEqual(self.session_files()[0].read_text(encoding="utf-8"), "")
        settings = json.loads((self.data_root / "diagnostics" / "settings.json").read_text(encoding="utf-8"))
        self.assertIs(settings["diagnostic_enabled"], True)

    def test_retention_keeps_five_sessions_and_trims_active_timeline(self) -> None:
        recorders = [self.recorder]
        for _ in range(5):
            time.sleep(0.002)
            recorders.append(
                DiagnosticRecorder(
                    self.data_root,
                    build_id="build-test",
                    extension_version="1.2.3",
                )
            )
        current = recorders[-1]
        self.assertEqual(len(self.session_files()), 5)
        self.assertTrue((self.data_root / "diagnostics" / "sessions" / f"{current.status()['session_id']}.jsonl").exists())

        session_path = next(
            path
            for path in self.session_files()
            if path.stem == current.status()["session_id"]
        )
        line = b'{"step":"old","padding":"' + (b"x" * 1000) + b'"}\n'
        session_path.write_bytes(line * 8200)
        self.assertGreater(session_path.stat().st_size, 8 * 1024 * 1024)
        self.assertTrue(current.record({"component": "mesa", "step": "survives_trim"}))

        self.assertLessEqual(session_path.stat().st_size, 6 * 1024 * 1024)
        surviving_events = [json.loads(row) for row in session_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(surviving_events[-1]["step"], "survives_trim")
        self.assertLess(len(surviving_events), 8200)

    def test_export_contains_six_files_and_summary_identifies_failures_and_slow_steps(self) -> None:
        for event in (
            {"component": "extension", "step": "form_detected", "elapsed_ms": 4800, "form_state": "visible"},
            {"component": "mesa", "step": "preflight", "code": "FORM_NOT_AVAILABLE", "result": "refused"},
            {"component": "mesa", "step": "preflight", "code": "STALE_FORM", "result": "refused"},
            {
                "component": "extension",
                "step": "result",
                "command_type": "FILL_FORM",
                "code": "FILL_FORM_OK",
                "result": "ok",
                "fields": {
                    "ato": {"before": "old", "proposed": "new", "after": "new"},
                    "senha": "senha-secret",
                },
            },
            {
                "component": "mesa",
                "step": "command_timeout",
                "code": "COMMAND_TIMEOUT",
                "result": "timeout",
                "error": "Authorization: Bearer export-secret-token; polling expired",
            },
        ):
            self.recorder.record(event)

        filename, archive_bytes = self.recorder.export_zip(
            capabilities={"manual_fill": "qualified", "diagnostic": True}
        )

        self.assertRegex(filename, r"^diagnostico-atos-tce-\d{8}-\d{6}\.zip$")
        archive_path = Path(self._tmp.name) / filename
        archive_path.write_bytes(archive_bytes)
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"resumo.txt", "timeline.jsonl", "ambiente.json", "mesa.log", "extensao.log", "ultima-sessao.json"},
            )
            summary = archive.read("resumo.txt").decode("utf-8")
            timeline = archive.read("timeline.jsonl").decode("utf-8")
            environment = json.loads(archive.read("ambiente.json"))
            last_session = json.loads(archive.read("ultima-sessao.json"))
            full_export = b"".join(archive.read(name) for name in archive.namelist()).decode("utf-8")

        self.assertIn("FORM_NOT_AVAILABLE", summary)
        self.assertIn("STALE_FORM", summary)
        self.assertIn("COMMAND_TIMEOUT", summary)
        self.assertIn("SLOW", summary)
        self.assertIn("build-test", summary)
        self.assertIn("1.2.3", summary)
        self.assertIn('"manual_fill": "qualified"', json.dumps(environment))
        self.assertIn("runtime", environment)
        self.assertIn('"before":"old"', timeline)
        self.assertIn('"proposed":"new"', timeline)
        self.assertIn('"after":"new"', timeline)
        self.assertNotIn("export-secret-token", full_export)
        self.assertNotIn("senha-secret", full_export)
        self.assertEqual(last_session["events"][-1]["code"], "COMMAND_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
