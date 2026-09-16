"""Local integrated qualification gates for a multi-item persisted run.

The fixture represents a two-page discovery result after the browser controller
has frozen its 25-item queue. It never contacts the portal.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.automation_store import AutomationStore


HASH = "a" * 64


def identities(count: int = 25) -> list[dict[str, str | None]]:
    return [
        {
            "process_key": f"{200000 + index}/2024",
            "interested_normalized": f"interessado {index + 1}",
            "portal_act_id": f"act-{index + 1}",
        }
        for index in range(count)
    ]


class AutomationIntegrationTests(unittest.TestCase):
    def test_25_item_queue_persists_pending_positions_across_store_restart(self):
        with tempfile.TemporaryDirectory(prefix="tce-automation-integration-") as directory:
            root = Path(directory)
            store = AutomationStore(root)
            run = store.create_run(
                {
                    "tab_id": 7,
                    "sector": "aposentadorias",
                    "dataset_sha256": HASH,
                    "rules_version": "legal-foundation-v2",
                    "run_id": "run-qualification-25",
                },
                "qualification-start",
            )
            run = store.freeze_queue(run["run_id"], identities(), "qualification-queue", run["revision"])
            for index in range(3):
                run = store.append_event(
                    run["run_id"],
                    {
                        "event_id": f"qualification-pending-{index + 1}",
                        "expected_revision": run["revision"],
                        "type": "item_pending",
                        "item_id": f"act-{index + 1}",
                        "payload": {"reason": "dados documentais insuficientes"},
                    },
                )
            timeout_identity = identities()[10]
            run = store.append_event(
                run["run_id"],
                {
                    "event_id": "qualification-timeout-prepared",
                    "expected_revision": run["revision"],
                    "type": "item_prepared",
                    "item_id": timeout_identity["portal_act_id"],
                    "payload": {"reason": "ready"},
                },
            )
            run = store.append_event(
                run["run_id"],
                {
                    "event_id": "qualification-timeout-fields",
                    "expected_revision": run["revision"],
                    "type": "fields_verified",
                    "item_id": timeout_identity["portal_act_id"],
                    "payload": {"field_results": {}, "rereads": []},
                },
            )
            run = store.append_event(
                run["run_id"],
                {
                    "event_id": "qualification-timeout-intent",
                    "expected_revision": run["revision"],
                    "type": "send_intent",
                    "item_id": timeout_identity["portal_act_id"],
                    "payload": {
                        "identity": timeout_identity,
                        "command_id": "qualification-timeout-command",
                        "expires_at": 200_000,
                        "expected_fields_hash": HASH,
                    },
                },
            )
            run = store.append_event(
                run["run_id"],
                {
                    "event_id": "qualification-timeout-unconfirmed",
                    "expected_revision": run["revision"],
                    "type": "send_unconfirmed",
                    "item_id": timeout_identity["portal_act_id"],
                    "payload": {"identity": timeout_identity, "reason": "timeout"},
                },
            )
            self.assertEqual(run["revision"], 8)
            store.close()

            reopened = AutomationStore(root)
            try:
                snapshot = reopened.snapshot("run-qualification-25")
                self.assertEqual(snapshot["state"], "paused")
                timeout_item = next(item for item in snapshot["items"] if item["ordinal"] == 11)
                self.assertEqual(timeout_item["state"], "unconfirmed")
                self.assertEqual(len(snapshot["items"]), 25)
                self.assertEqual(sum(item["state"] == "pending" for item in snapshot["items"]), 3)
                self.assertEqual(sum(item["state"] == "unconfirmed" for item in snapshot["items"]), 1)
                resumed = reopened.append_event(
                    "run-qualification-25",
                    {
                        "event_id": "qualification-resumed-after-recovery",
                        "expected_revision": snapshot["revision"],
                        "type": "run_resumed",
                        "payload": {"reason": "operator_reviewed_recovery"},
                    },
                )
                self.assertEqual(resumed["state"], "running")
                history = reopened.list_runs(limit=20)
                self.assertEqual(history["runs"][0]["totals"]["total"], 25)
                self.assertEqual(history["runs"][0]["totals"]["pending"], 3)
                self.assertEqual(history["runs"][0]["totals"]["unconfirmed"], 1)
                events = reopened.get_events("run-qualification-25", after=0)
                self.assertEqual(
                    sum(event["type"] == "item_pending" for event in events),
                    3,
                )
                self.assertEqual(
                    sum(event["type"] == "send_unconfirmed" for event in events),
                    1,
                )
                self.assertEqual([event["type"] for event in events][-2:], ["run_paused", "run_resumed"])
                self.assertNotIn("payload_json", events[-1])
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
