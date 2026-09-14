"""Tests for the bounded QA matrix executor and public report."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from qa_matrix_runner import (
    CommandCase,
    build_report,
    default_cases,
    execute_case,
    render_markdown,
    write_report,
)


ROOT = Path(__file__).resolve().parent


class QaMatrixRunnerTests(unittest.TestCase):
    def test_default_cases_are_windows_executable_and_use_project_root(self):
        cases = {case.matrix_id: case for case in default_cases(ROOT, ROOT)}
        self.assertTrue(cases["web.collections"].command[0].lower().endswith("npm.cmd"))
        self.assertIn("offline.menu-suite", cases)
        review = cases["offline.review-launcher"]
        self.assertIn(str(ROOT), review.command)
        self.assertNotIn(str(ROOT / "portable"), review.command)

    def test_success_report_contains_every_matrix_function_and_no_command_output(self):
        matrix = [
            {
                "id": "fixture.pass",
                "function": "Fixture passa",
                "layer": "extension",
                "preconditions": "fixture",
                "risk": "low",
                "procedure": "run",
                "expected": "ok",
                "evidence": "exit code",
                "automation": "fixture",
            },
            {
                "id": "portal.blocked",
                "function": "Portal bloqueado",
                "layer": "portal",
                "preconditions": "login",
                "risk": "high",
                "procedure": "manual",
                "expected": "observe",
                "evidence": "trace",
                "automation": "manual",
            },
        ]
        case = CommandCase(
            matrix_id="fixture.pass",
            command=(sys.executable, "-c", "print('token=never-publish')"),
            cwd=ROOT,
            timeout_seconds=5,
            pass_status="PASS_FIXTURE",
        )
        result = execute_case(case)
        report = build_report(
            matrix=matrix,
            results={"fixture.pass": result},
            metadata={"run_id": "qa-test", "commit": "local"},
        )
        self.assertEqual(report["summary"], {"PASS_FIXTURE": 1, "BLOCKED": 1})
        self.assertEqual(len(report["functions"]), 2)
        self.assertNotIn("token=never-publish", json.dumps(report))
        markdown = render_markdown(report)
        self.assertIn("fixture.pass", markdown)
        self.assertIn("BLOCKED", markdown)

    def test_timeout_is_blocked_and_output_is_only_hashed(self):
        case = CommandCase(
            matrix_id="fixture.timeout",
            command=(sys.executable, "-c", "import time; print('secret'); time.sleep(1)"),
            cwd=ROOT,
            timeout_seconds=0.05,
            pass_status="PASS_FIXTURE",
        )
        result = execute_case(case)
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(result.timed_out)
        self.assertEqual(len(result.output_sha256), 64)
        self.assertNotIn("secret", repr(result))

    def test_write_report_creates_json_and_markdown(self):
        report = {
            "schema": "qa-matrix-v1",
            "summary": {"PASS_FIXTURE": 1},
            "functions": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            paths = write_report(Path(temporary), report)
            self.assertTrue(paths["json"].is_file())
            self.assertTrue(paths["markdown"].is_file())
            self.assertEqual(json.loads(paths["json"].read_text(encoding="utf-8")), report)


if __name__ == "__main__":
    unittest.main()
