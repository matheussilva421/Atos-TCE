"""The M3 real gate: prove that only the requested keys were downloaded."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.models import ProcessRecord
from app.core.store import Store
from app.econtas.legacy_queue import write_frozen_queue

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify-acquisition.py"

_MODULE = None


def module():
    """Load the CLI script as a module so the check can be driven in-process."""

    global _MODULE
    if _MODULE is None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("verify_acquisition_cli", SCRIPT_PATH)
        if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
            raise AssertionError(f"cannot load {SCRIPT_PATH}")
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = loaded
        try:
            spec.loader.exec_module(loaded)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
        _MODULE = loaded
    return _MODULE


class AcquisitionCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name) / "data"
        self.store = Store.open(self.data_root / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.keys = ("100015/2026", "100023/2026", "100031/2026")
        self.process_ids = {}
        for key in self.keys:
            process_id = self.store.upsert_process(
                ProcessRecord(
                    process_key=key,
                    interested=f"Pessoa {key}",
                    interested_normalized=f"pessoa {key}",
                )
            )
            self.store.set_process_acquisition_state(process_id, "NOT_DOWNLOADED")
            self.process_ids[key] = process_id
        self.queue_path = self.data_root / "queues" / "acquisition-1.json"
        write_frozen_queue(
            [{"process_key": key} for key in self.keys],
            "sector_finalistic",
            {"label": "PROFESSOR - IPERN - 2 RUBRICAS", "value": "6189"},
            self.queue_path,
            50,
        )
        self.job_id = self.store.create_job("acquisition", total=len(self.keys))
        for key in self.keys:
            self.store.add_job_item(self.job_id, self.process_ids[key], "QUEUED")
        self.store.mark_job_item(self.job_id, self.process_ids[self.keys[0]], "DOWNLOADED")
        self.store.mark_job_item(self.job_id, self.process_ids[self.keys[1]], "DOWNLOADED")
        self.store.mark_job_item(
            self.job_id, self.process_ids[self.keys[2]], "FAILED", "HTTP 400 em /api/informacao/1/pdf"
        )
        self.store.set_job_status(self.job_id, "COMPLETED", started=True, finished=True)

    def verify(self, **kwargs):
        return module().verify_job(
            self.data_root / "atos-tce.db", self.job_id, queue_path=self.queue_path, **kwargs
        )


class VerdictTests(AcquisitionCase):
    def test_a_matching_queue_and_job_pass(self):
        report = self.verify()

        self.assertTrue(report["ok"], report["violations"])
        self.assertEqual(report["violations"], [])
        self.assertEqual(sorted(report["requested"]), sorted(self.keys))
        self.assertEqual(sorted(report["attempted"]), sorted(self.keys))
        self.assertEqual(report["counts"]["downloaded"], 2)
        self.assertEqual(report["counts"]["failed"], 1)

    def test_a_key_attempted_without_being_requested_is_a_violation(self):
        extra = self.store.upsert_process(
            ProcessRecord(
                process_key="100099/2026",
                interested="Pessoa Extra",
                interested_normalized="pessoa extra",
            )
        )
        self.store.add_job_item(self.job_id, extra, "QUEUED")
        self.store.mark_job_item(self.job_id, extra, "DOWNLOADED")

        report = self.verify()

        self.assertFalse(report["ok"])
        self.assertIn("100099/2026", report["attempted"])
        self.assertTrue(any("sem pedido" in violation for violation in report["violations"]), report)

    def test_a_requested_key_without_an_item_is_a_violation(self):
        # A second job that attempted only two of the three requested keys.
        second_job = self.store.create_job("acquisition", total=2)
        for key in self.keys[:2]:
            self.store.add_job_item(second_job, self.process_ids[key], "QUEUED")
            self.store.mark_job_item(second_job, self.process_ids[key], "DOWNLOADED")
        self.store.set_job_status(second_job, "COMPLETED", started=True, finished=True)

        report = module().verify_job(
            self.data_root / "atos-tce.db", second_job, queue_path=self.queue_path
        )

        self.assertFalse(report["ok"])
        self.assertIn(self.keys[2], report["requested"])
        self.assertTrue(any("sem item no job" in violation for violation in report["violations"]), report)

    def test_an_item_still_running_after_the_job_finished_is_a_violation(self):
        self.store.mark_job_item(self.job_id, self.process_ids[self.keys[2]], "DOWNLOADING")

        report = self.verify()

        self.assertFalse(report["ok"])
        self.assertTrue(any("DOWNLOADING" in violation for violation in report["violations"]), report)

    def test_counters_that_disagree_with_the_items_are_a_violation(self):
        with self.store._transaction() as connection:
            connection.execute("UPDATE jobs SET completed = 9 WHERE id = ?", (self.job_id,))

        report = self.verify()

        self.assertFalse(report["ok"])
        self.assertTrue(any("completed" in violation for violation in report["violations"]), report)

    def test_a_process_updated_outside_the_request_is_a_warning(self):
        outsider = self.store.upsert_process(
            ProcessRecord(
                process_key="100777/2026",
                interested="Pessoa Fora",
                interested_normalized="pessoa fora",
            )
        )
        self.store.set_process_acquisition_state(outsider, "DOWNLOADED")

        report = self.verify()

        self.assertTrue(report["ok"], report["violations"])
        self.assertIn("100777/2026", [item["process_key"] for item in report["warnings"]])

    def test_a_missing_job_is_an_error(self):
        with self.assertRaises(module().AcquisitionCheckError):
            module().verify_job(self.data_root / "atos-tce.db", 4242, queue_path=self.queue_path)

    def test_a_missing_queue_is_an_error(self):
        with self.assertRaises(module().AcquisitionCheckError):
            module().verify_job(
                self.data_root / "atos-tce.db", self.job_id, queue_path=self.data_root / "nao-existe.json"
            )


class CliTests(AcquisitionCase):
    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *[str(argument) for argument in arguments]],
            capture_output=True,
            text=True,
        )

    def test_cli_reports_ok_with_exit_zero(self):
        result = self.run_cli(
            "--db", self.data_root / "atos-tce.db", "--job", self.job_id, "--queue", self.queue_path
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_cli_uses_the_default_queue_path_of_the_data_root(self):
        result = self.run_cli("--db", self.data_root / "atos-tce.db", "--job", self.job_id)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["queue"]["path"].endswith("acquisition-1.json"))

    def test_cli_reports_a_violation_with_exit_one(self):
        self.store.mark_job_item(self.job_id, self.process_ids[self.keys[0]], "DOWNLOADING")

        result = self.run_cli(
            "--db", self.data_root / "atos-tce.db", "--job", self.job_id, "--queue", self.queue_path
        )

        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
