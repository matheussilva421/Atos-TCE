import json
import subprocess
import sys
import unittest
from pathlib import Path

from qa_integrated_workflow import run_fixture_checks


class IntegratedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent

    def test_fixture_report_is_explicitly_non_portal_and_has_safety_components(self):
        report = run_fixture_checks(self.root)
        self.assertEqual(report["status"], "fixture-only")
        self.assertEqual(report["portal_login"], "not-run")
        self.assertEqual(report["portal_submission"], "not-run")
        self.assertTrue(report["passed"])

    def test_cli_requires_explicit_fixture_mode(self):
        script = self.root / "qa_integrated_workflow.py"
        completed = subprocess.run(
            [sys.executable, str(script), "--project-root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["status"], "human-checkpoint-required")


if __name__ == "__main__":
    unittest.main()
