import tempfile
import unittest
from pathlib import Path

from app.automation_store import AutomationStore, InvalidTransition


IDENTITY = {
    "process_key": "103439/2023",
    "interested_normalized": "ana da silva",
    "portal_act_id": "act-1",
}
HASH = "a" * 64


class AutomationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = AutomationStore(Path(self.tempdir.name))
        run = self.store.create_run(
            {
                "tab_id": 7,
                "sector": "aposentadorias",
                "dataset_sha256": HASH,
                "rules_version": "legal-foundation-v1",
                "run_id": "run-recovery",
            },
            "run-create",
        )
        run = self.store.freeze_queue(run["run_id"], [IDENTITY], "queue-1", run["revision"])
        run = self.store.append_event(
            run["run_id"],
            {"event_id": "prepare-1", "expected_revision": run["revision"], "type": "item_prepared", "item_id": "act-1", "payload": {"reason": "ready"}},
        )
        run = self.store.append_event(
            run["run_id"],
            {"event_id": "fields-1", "expected_revision": run["revision"], "type": "fields_verified", "item_id": "act-1", "payload": {"field_results": {}, "rereads": []}},
        )
        self.run_id = run["run_id"]

    def tearDown(self):
        self.store.close()
        self.tempdir.cleanup()

    def _send_intent(self, revision, command_id="command-1", expires_at=115_000):
        return self.store.append_event(
            self.run_id,
            {
                "event_id": f"intent-{command_id}",
                "expected_revision": revision,
                "type": "send_intent",
                "item_id": "act-1",
                "payload": {
                    "identity": IDENTITY,
                    "command_id": command_id,
                    "expires_at": expires_at,
                    "expected_fields_hash": HASH,
                },
            },
        )

    def test_consume_command_is_single_use_and_advances_revision(self):
        run = self._send_intent(3)
        consumed = self.store.consume_command(self.run_id, "command-1", run["revision"], now_ms=100_000)
        self.assertTrue(consumed["dispatch_allowed"])
        self.assertEqual(consumed["revision"], 5)
        self.assertEqual(consumed["command_id"], "command-1")
        self.assertEqual(self.store.get_events(self.run_id)[-1]["type"], "command_consumed")
        with self.assertRaisesRegex(InvalidTransition, "COMMAND_ALREADY_CONSUMED"):
            self.store.consume_command(self.run_id, "command-1", consumed["revision"], now_ms=100_000)

    def test_expired_command_is_not_dispatchable(self):
        run = self._send_intent(3, expires_at=100_001)
        with self.assertRaisesRegex(InvalidTransition, "COMMAND_EXPIRED"):
            self.store.consume_command(self.run_id, "command-1", run["revision"], now_ms=100_002)

    def test_reopen_turns_send_intent_into_unconfirmed_and_blocks_consume(self):
        run = self._send_intent(3)
        self.store.close()
        reopened = AutomationStore(Path(self.tempdir.name))
        self.addCleanup(reopened.close)
        snapshot = reopened.snapshot(self.run_id)
        self.assertEqual(snapshot["state"], "paused")
        self.assertEqual(snapshot["items"][0]["state"], "unconfirmed")
        with self.assertRaisesRegex(InvalidTransition, "COMMAND_NOT_READY"):
            reopened.consume_command(self.run_id, "command-1", snapshot["revision"], now_ms=100_000)


if __name__ == "__main__":
    unittest.main()
