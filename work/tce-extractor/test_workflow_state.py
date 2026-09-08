"""TDD tests for the portable workflow state contract."""

from pathlib import Path
import json
import sys
import threading
from tempfile import TemporaryDirectory
import unittest


APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from unittest.mock import patch

import workflow_state
from archive_index import scan_archive
from workflow_state import RevisionConflict, WorkflowState, WorkflowStateError


class WorkflowStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_completion_survives_order_refresh(self):
        state = WorkflowState(self.root)
        self.addCleanup(state.close)
        state.set_completed("103439/2023", True, 0)
        state.set_portal_order(["103490/2023", "103439/2023"])
        state.close()

        reopened = WorkflowState(self.root)
        self.addCleanup(reopened.close)
        result = reopened.snapshot()

        self.assertTrue(result["processes"]["103439/2023"]["completed"])
        self.assertEqual(result["process_keys"][0], "103490/2023")

    def test_fresh_state_writes_v1_files(self):
        state = WorkflowState(self.root)
        self.addCleanup(state.close)

        self.assertEqual(
            state.snapshot(),
            {
                "schema_version": 1,
                "revision": 0,
                "processes": {},
                "process_keys": [],
            },
        )
        self.assertEqual(
            (self.root / "progresso.json").read_text(encoding="utf-8"),
            '{"schema_version": 1, "revision": 0, "processes": {}}\n',
        )
        order = __import__("json").loads(
            (self.root / "ordem-portal.json").read_text(encoding="utf-8")
        )
        self.assertEqual(order["schema_version"], 1)
        self.assertEqual(order["process_keys"], [])
        self.assertIsInstance(order["captured_at"], str)

    def test_process_keys_are_canonicalized_and_order_is_deduplicated(self):
        state = WorkflowState(self.root)
        self.addCleanup(state.close)

        result = state.set_completed(" 00103439 / 2023 ", True, 0)
        self.assertIn("00103439/2023", result["processes"])
        result = state.set_portal_order(
            ["103490 / 2023", "103439/2023", "103490/2023"]
        )

        self.assertEqual(result["process_keys"], ["103490/2023", "103439/2023"])

    def test_revision_conflict_does_not_write_partial_state(self):
        state = WorkflowState(self.root)
        self.addCleanup(state.close)
        state.set_completed("103439/2023", True, 0)

        with self.assertRaises(RevisionConflict):
            state.set_completed("103439/2023", False, 0)

        self.assertEqual(state.snapshot()["revision"], 1)
        self.assertTrue(state.snapshot()["processes"]["103439/2023"]["completed"])

    def test_reopen_preserves_progress_and_order(self):
        state = WorkflowState(self.root)
        state.set_completed("103439/2023", True, 0)
        state.set_portal_order(["103439/2023"])
        state.close()

        reopened = WorkflowState(self.root)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.snapshot()["revision"], 1)
        self.assertEqual(reopened.snapshot()["process_keys"], ["103439/2023"])

    def test_corrupt_json_is_rejected_instead_of_becoming_empty(self):
        (self.root / "progresso.json").write_text("{broken", encoding="utf-8")

        with self.assertRaises(ValueError):
            WorkflowState(self.root)

    def test_failed_replace_keeps_previous_valid_progress(self):
        state = WorkflowState(self.root)
        self.addCleanup(state.close)
        state.set_completed("103439/2023", True, 0)
        previous = (self.root / "progresso.json").read_bytes()

        with patch.object(workflow_state.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                state.set_completed("103439/2023", False, 1)

        self.assertEqual((self.root / "progresso.json").read_bytes(), previous)
        self.assertTrue(state.snapshot()["processes"]["103439/2023"]["completed"])
        self.assertEqual(list(self.root.glob(".progresso.json.*.tmp")), [])

    def test_idempotent_completion_does_not_advance_revision(self):
        state = WorkflowState(self.root)
        self.addCleanup(state.close)

        first = state.set_completed("103439/2023", True, 0)
        second = state.set_completed("103439/2023", True, 1)

        self.assertEqual(first, second)
        self.assertEqual(second["revision"], 1)

    def test_order_refresh_does_not_change_completion_revision(self):
        state = WorkflowState(self.root)
        self.addCleanup(state.close)
        state.set_completed("103439/2023", True, 0)

        result = state.set_portal_order(["103490/2023", "103439/2023"])

        self.assertEqual(result["revision"], 1)
        self.assertTrue(result["processes"]["103439/2023"]["completed"])

    def test_snapshot_is_defensive(self):
        state = WorkflowState(self.root)
        self.addCleanup(state.close)
        state.set_completed("103439/2023", True, 0)
        snapshot = state.snapshot()
        snapshot["processes"]["103439/2023"]["completed"] = False
        snapshot["process_keys"].append("999/2024")

        fresh = state.snapshot()
        self.assertTrue(fresh["processes"]["103439/2023"]["completed"])
        self.assertNotIn("999/2024", fresh["process_keys"])

    def test_second_instance_is_rejected_until_first_is_closed(self):
        state = WorkflowState(self.root)
        self.addCleanup(state.close)

        with self.assertRaises(WorkflowStateError):
            WorkflowState(self.root)

        state.close()
        reopened = WorkflowState(self.root)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.snapshot()["revision"], 0)

    def test_concurrent_writers_are_serialized(self):
        state = WorkflowState(self.root)
        self.addCleanup(state.close)
        first_replace_started = threading.Event()
        release_first_replace = threading.Event()
        real_replace = workflow_state.os.replace
        replace_count = 0
        replace_count_lock = threading.Lock()

        def delayed_replace(source, destination):
            nonlocal replace_count
            if Path(destination) == self.root / "progresso.json":
                with replace_count_lock:
                    replace_count += 1
                    current_replace = replace_count
                if current_replace == 1:
                    first_replace_started.set()
                    release_first_replace.wait(timeout=5)
            return real_replace(source, destination)

        results = []

        def write(completed):
            try:
                results.append(("ok", state.set_completed("103439/2023", completed, 0)))
            except RevisionConflict:
                results.append(("conflict", None))

        with patch.object(workflow_state.os, "replace", side_effect=delayed_replace):
            first = threading.Thread(target=write, args=(True,))
            second = threading.Thread(target=write, args=(False,))
            first.start()
            self.assertTrue(first_replace_started.wait(timeout=5))
            second.start()
            release_first_replace.set()
            first.join(timeout=5)
            second.join(timeout=5)

        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(sorted(result[0] for result in results), ["conflict", "ok"])
        self.assertEqual(state.snapshot()["revision"], 1)

    def test_legacy_reviewed_checkpoint_is_not_migrated(self):
        (self.root / "checkpoint.json").write_text(
            '{"processes": [{"key": "103439/2023", "status": "reviewed:v1"}]}',
            encoding="utf-8",
        )

        state = WorkflowState(self.root)
        self.addCleanup(state.close)

        self.assertEqual(state.snapshot()["processes"], {})

    def test_archive_index_uses_deduplicated_persisted_portal_order(self):
        process_root = self.root / "processos"
        for key in ("103439-2023", "103490-2023"):
            process_dir = process_root / key
            process_dir.mkdir(parents=True)
            number, year = key.split("-")
            (process_dir / "processo.json").write_text(
                json.dumps({"key": f"{number}/{year}", "events": []}),
                encoding="utf-8",
            )
        (self.root / "ordem-portal.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "captured_at": "2026-09-08T00:00:00+00:00",
                    "process_keys": [
                        "103490/2023",
                        "103439 / 2023",
                        "103490/2023",
                        "999/2024",
                    ],
                }
            ),
            encoding="utf-8",
        )

        index = scan_archive(self.root)

        self.assertEqual(
            index["process_keys"],
            ["103490/2023", "103439/2023", "999/2024"],
        )
        self.assertEqual(
            [process["key"] for process in index["processes"]],
            ["103490/2023", "103439/2023"],
        )


if __name__ == "__main__":
    unittest.main()
