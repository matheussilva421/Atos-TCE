"""TDD contract tests for the durable automation event store."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import threading
import unittest


APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))


class AutomationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertIsNotNone(
            importlib.util.find_spec("automation_store"),
            "automation_store.py must exist before the production implementation",
        )
        from automation_store import (
            ActiveRunError,
            EventConflict,
            EventValidationError,
            LegacyEventReplayError,
            InvalidTransition,
            RevisionConflict,
        )

        self.ActiveRunError = ActiveRunError
        self.EventConflict = EventConflict
        self.EventValidationError = EventValidationError
        self.LegacyEventReplayError = LegacyEventReplayError
        self.InvalidTransition = InvalidTransition
        self.RevisionConflict = RevisionConflict

    def _store(self, root=None):
        from automation_store import AutomationStore

        return AutomationStore(self.root if root is None else root)

    def _create_running_run(self, store):
        created = store.create_run({"run_id": "run-1", "schema_version": 1})
        return store.freeze_queue(
            "run-1",
            [{"process_key": "103439/2023"}, {"process_key": "103490/2023"}],
            "event-queue",
            created["revision"],
        )

    def _confirm_single_act(self, store, run_id, prefix, fields_hash):
        identity = {"process_key": "103439/2023"}
        created = store.create_run({"run_id": run_id, "schema_version": 1})
        frozen = store.freeze_queue(run_id, [identity], f"{prefix}-queue", created["revision"])
        prepared = store.append_event(
            run_id,
            {
                "event_id": f"{prefix}-prepared",
                "type": "item_prepared",
                "expected_revision": frozen["revision"],
                "item_id": identity["process_key"],
            },
        )
        filled = store.append_event(
            run_id,
            {
                "event_id": f"{prefix}-filled",
                "type": "fields_verified",
                "expected_revision": prepared["revision"],
                "item_id": identity["process_key"],
            },
        )
        intent = store.append_event(
            run_id,
            {
                "event_id": f"{prefix}-intent",
                "type": "send_intent",
                "expected_revision": filled["revision"],
                "item_id": identity["process_key"],
                "payload": {
                    "identity": identity,
                    "expected_fields_hash": fields_hash,
                    "command_id": f"{prefix}-command",
                    "expires_at": 200_000,
                },
            },
        )
        confirmed = store.append_event(
            run_id,
            {
                "event_id": f"{prefix}-confirmed",
                "type": "send_confirmed",
                "expected_revision": intent["revision"],
                "item_id": identity["process_key"],
                "payload": {
                    "identity": identity,
                    "fields": {"fundamento_legal": "art. 1"},
                    "expected_fields_hash": fields_hash,
                    "citations": ["fixture:art-1"],
                },
            },
        )
        stopped = store.append_event(
            run_id,
            {
                "event_id": f"{prefix}-stopped",
                "type": "run_stopped",
                "expected_revision": confirmed["revision"],
            },
        )
        return identity, stopped

    def test_confirmation_blocks_resend_across_runs_and_changed_fields_need_review(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        identity, _ = self._confirm_single_act(store, "run-1", "first", "a" * 64)

        created = store.create_run({"run_id": "run-2", "schema_version": 1})
        frozen = store.freeze_queue("run-2", [identity], "second-queue", created["revision"])
        prepared = store.append_event(
            "run-2",
            {
                "event_id": "second-prepared",
                "type": "item_prepared",
                "expected_revision": frozen["revision"],
                "item_id": identity["process_key"],
            },
        )
        filled = store.append_event(
            "run-2",
            {
                "event_id": "second-filled",
                "type": "fields_verified",
                "expected_revision": prepared["revision"],
                "item_id": identity["process_key"],
            },
        )

        same = store.check_send_eligibility(identity, "a" * 64)
        self.assertFalse(same["eligible"])
        self.assertEqual(same["status"], "confirmed")
        self.assertEqual(same["reason"], "ACT_ALREADY_CONFIRMED")
        with self.assertRaisesRegex(self.InvalidTransition, "ACT_ALREADY_CONFIRMED"):
            store.append_event(
                "run-2",
                {
                    "event_id": "second-intent-same",
                    "type": "send_intent",
                    "expected_revision": filled["revision"],
                    "item_id": identity["process_key"],
                    "payload": {
                        "identity": identity,
                        "expected_fields_hash": "a" * 64,
                        "command_id": "second-command-same",
                        "expires_at": 200_000,
                    },
                },
            )

        changed = store.check_send_eligibility(identity, "b" * 64)
        self.assertFalse(changed["eligible"])
        self.assertEqual(changed["status"], "pending")
        self.assertEqual(changed["reason"], "ACT_REQUIRES_REVIEW")
        with self.assertRaisesRegex(self.InvalidTransition, "ACT_REQUIRES_REVIEW"):
            store.append_event(
                "run-2",
                {
                    "event_id": "second-intent-changed",
                    "type": "send_intent",
                    "expected_revision": filled["revision"],
                    "item_id": identity["process_key"],
                    "payload": {
                        "identity": identity,
                        "expected_fields_hash": "b" * 64,
                        "command_id": "second-command-changed",
                        "expires_at": 200_000,
                    },
                },
            )
        self.assertEqual(store.snapshot("run-2")["items"][0]["state"], "filled")

    def test_freeze_and_events_project_atomically(self) -> None:
        store = self._store()
        self.addCleanup(store.close)

        created = store.create_run({"run_id": "run-1", "schema_version": 1})
        self.assertEqual(created["state"], "discovering")
        self.assertEqual(created["revision"], 0)

        frozen = store.freeze_queue(
            "run-1",
            [{"process_key": "103439/2023"}],
            "event-queue",
            0,
        )
        self.assertEqual(frozen["state"], "running")
        self.assertEqual(frozen["revision"], 1)
        self.assertEqual(frozen["items"][0]["state"], "queued")

        prepared = store.append_event(
            "run-1",
            {
                "event_id": "event-prepared",
                "type": "item_prepared",
                "expected_revision": 1,
                "item_id": "103439/2023",
                "before": {"name": "old"},
                "after": {"name": "new"},
            },
        )
        self.assertEqual(prepared["revision"], 2)
        self.assertEqual(prepared["items"][0]["state"], "prepared")
        self.assertEqual(
            [event["type"] for event in store.get_events("run-1")],
            ["queue_frozen", "item_prepared"],
        )

    def test_stale_revision_rolls_back_without_advancing_memory(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        self._create_running_run(store)
        before = store.snapshot("run-1")

        with self.assertRaises(self.RevisionConflict):
            store.freeze_queue("run-1", [], "event-stale", 0)

        after = store.snapshot("run-1")
        self.assertEqual(after, before)
        self.assertEqual(store.get_events("run-1"), store.get_events("run-1", after=0))

    def test_repeated_event_is_idempotent_but_changed_payload_conflicts(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        self._create_running_run(store)
        event = {
            "event_id": "event-prepared",
            "type": "item_prepared",
            "expected_revision": 1,
            "item_id": "103439/2023",
            "before": {"name": "old"},
            "after": {"name": "new"},
        }

        first = store.append_event("run-1", event)
        second = store.append_event("run-1", {**event, "expected_revision": 0})
        self.assertEqual(second, first)
        self.assertEqual(store.snapshot("run-1")["revision"], 2)

        with self.assertRaises(self.EventConflict):
            store.append_event(
                "run-1",
                {**event, "expected_revision": 2, "after": {"name": "tampered"}},
            )
        self.assertEqual(store.snapshot("run-1")["revision"], 2)

    def test_run_creation_event_replays_original_snapshot_and_conflicts_on_changed_spec(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        spec = {"run_id": "run-1", "schema_version": 1}

        first = store.create_run(spec, "start-run")
        replay = store.create_run(spec, "start-run")
        self.assertEqual(replay, first)

        with self.assertRaises(self.EventConflict):
            store.create_run({**spec, "sector": "aposentadorias"}, "start-run")
        connection = sqlite3.connect(store.database_path)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 1)
        finally:
            connection.close()

    def test_event_id_is_global_between_run_creation_and_later_events(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        spec = {"run_id": "run-1", "schema_version": 1}

        created = store.create_run(spec, "shared-event-id")
        frozen = store.freeze_queue(
            "run-1",
            [{"process_key": "103439/2023"}],
            "queue-event",
            created["revision"],
        )
        before = store.snapshot("run-1")

        with self.assertRaises(self.EventConflict):
            store.append_event(
                "run-1",
                {
                    "event_id": "shared-event-id",
                    "type": "item_prepared",
                    "expected_revision": frozen["revision"],
                    "item_id": "103439/2023",
                    "reason": "prepared",
                },
            )

        self.assertEqual(store.snapshot("run-1"), before)
        self.assertEqual(
            [event["event_id"] for event in store.get_events("run-1")],
            ["queue-event"],
        )

    def test_event_id_from_an_event_blocks_later_run_creation(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        self._create_running_run(store)

        prepared = store.append_event(
            "run-1",
            {
                "event_id": "shared-event-id",
                "type": "item_prepared",
                "expected_revision": 1,
                "item_id": "103439/2023",
                "reason": "prepared",
            },
        )
        stopped = store.append_event(
            "run-1",
            {
                "event_id": "stop-event",
                "type": "run_stopped",
                "expected_revision": prepared["revision"],
            },
        )

        with self.assertRaises(self.EventConflict):
            store.create_run({"run_id": "run-2", "schema_version": 1}, "shared-event-id")

        self.assertEqual(store.snapshot("run-1"), stopped)
        self.assertEqual(store.snapshot("run-1")["revision"], 3)

    def test_existing_database_backfills_global_event_ids_without_breaking_replay(self) -> None:
        store = self._store()
        identity = {"process_key": "103439/2023"}
        store.create_run({"run_id": "run-1", "schema_version": 1})
        store.freeze_queue("run-1", [identity], "queue-event", 0)
        event = {
            "event_id": "legacy-event",
            "type": "item_prepared",
            "expected_revision": 1,
            "item_id": identity["process_key"],
            "reason": "prepared",
        }
        prepared = store.append_event("run-1", event)
        store.append_event(
            "run-1",
            {
                "event_id": "stop-event",
                "type": "run_stopped",
                "expected_revision": prepared["revision"],
            },
        )
        store.close()

        connection = sqlite3.connect(store.database_path)
        try:
            connection.execute("DROP TABLE event_id_registry")
            connection.execute("DROP TABLE run_creation_requests")
            connection.commit()
        finally:
            connection.close()

        reopened = self._store()
        self.addCleanup(reopened.close)
        replay = reopened.append_event("run-1", {**event, "expected_revision": 0})
        self.assertEqual(replay, prepared)
        with self.assertRaises(self.EventConflict):
            reopened.create_run({"run_id": "run-2", "schema_version": 1}, "legacy-event")

    def test_repeated_event_returns_original_result_after_later_events(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        self._create_running_run(store)
        event = {
            "event_id": "event-original-result",
            "type": "item_prepared",
            "expected_revision": 1,
            "item_id": "103439/2023",
        }

        first = store.append_event("run-1", event)
        store.append_event(
            "run-1",
            {
                "event_id": "event-later",
                "type": "fields_verified",
                "expected_revision": 2,
                "item_id": "103439/2023",
            },
        )

        replay = store.append_event(
            "run-1", {**event, "expected_revision": 0}
        )
        self.assertEqual(replay, first)

    def test_legacy_event_without_result_json_fails_closed_on_replay(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        self._create_running_run(store)
        event = {
            "event_id": "event-legacy-result",
            "type": "item_prepared",
            "expected_revision": 1,
            "item_id": "103439/2023",
        }
        original = store.append_event("run-1", event)

        connection = sqlite3.connect(store.database_path)
        connection.execute(
            "UPDATE events SET result_json = NULL WHERE event_id = ?",
            ("event-legacy-result",),
        )
        connection.commit()
        connection.close()

        store.append_event(
            "run-1",
            {
                "event_id": "event-after-legacy",
                "type": "fields_verified",
                "expected_revision": 2,
                "item_id": "103439/2023",
            },
        )

        with self.assertRaises(self.LegacyEventReplayError):
            store.append_event("run-1", {**event, "expected_revision": 0})
        self.assertEqual(original["revision"], 2)

    def test_semantically_different_json_payload_conflicts_without_python_coercion(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        self._create_running_run(store)
        event = {
            "event_id": "event-json-types",
            "type": "item_pending",
            "expected_revision": 1,
            "item_id": "103439/2023",
            "marker": 1,
        }

        store.append_event("run-1", event)
        with self.assertRaises(self.EventConflict):
            store.append_event(
                "run-1", {**event, "expected_revision": 2, "marker": True}
            )
        self.assertEqual(store.snapshot("run-1")["revision"], 2)

    def test_append_event_requires_explicit_revision_before_mutating(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        self._create_running_run(store)
        before = store.snapshot("run-1")

        with self.assertRaises(self.EventValidationError):
            store.append_event(
                "run-1",
                {
                    "event_id": "event-missing-revision",
                    "type": "item_prepared",
                    "item_id": "103439/2023",
                },
            )

        self.assertEqual(store.snapshot("run-1"), before)

    def test_invalid_transition_leaves_event_and_projection_unchanged(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        store.create_run({"run_id": "run-1"})

        with self.assertRaises(self.InvalidTransition):
            store.append_event(
                "run-1",
                {
                    "event_id": "event-confirmed",
                    "type": "send_confirmed",
                    "expected_revision": 0,
                    "item_id": "missing",
                },
            )

        snapshot = store.snapshot("run-1")
        self.assertEqual(snapshot["revision"], 0)
        self.assertEqual(store.get_events("run-1"), [])

    def test_reopen_pauses_run_and_marks_unconfirmed_send_intent(self) -> None:
        store = self._store()
        self._create_running_run(store)
        store.append_event(
            "run-1",
            {
                "event_id": "event-prepared",
                "type": "item_prepared",
                "expected_revision": 1,
                "item_id": "103439/2023",
            },
        )
        store.append_event(
            "run-1",
            {
                "event_id": "event-filled",
                "type": "fields_verified",
                "expected_revision": 2,
                "item_id": "103439/2023",
            },
        )
        store.append_event(
            "run-1",
            {
                "event_id": "event-intent",
                "type": "send_intent",
                "expected_revision": 3,
                "item_id": "103439/2023",
            },
        )
        store.close()

        reopened = self._store()
        self.addCleanup(reopened.close)
        snapshot = reopened.snapshot("run-1")
        self.assertEqual(snapshot["state"], "paused")
        self.assertEqual(snapshot["items"][0]["state"], "unconfirmed")
        self.assertEqual(
            [event["type"] for event in reopened.get_events("run-1")],
            [
                "queue_frozen",
                "item_prepared",
                "fields_verified",
                "send_intent",
                "run_paused",
                "send_unconfirmed",
            ],
        )

    def test_reopen_paused_run_marks_send_intent_unconfirmed(self) -> None:
        store = self._store()
        self._create_running_run(store)
        store.append_event(
            "run-1",
            {
                "event_id": "paused-prepared",
                "type": "item_prepared",
                "expected_revision": 1,
                "item_id": "103439/2023",
            },
        )
        store.append_event(
            "run-1",
            {
                "event_id": "paused-filled",
                "type": "fields_verified",
                "expected_revision": 2,
                "item_id": "103439/2023",
            },
        )
        store.append_event(
            "run-1",
            {
                "event_id": "paused-intent",
                "type": "send_intent",
                "expected_revision": 3,
                "item_id": "103439/2023",
            },
        )
        store.append_event(
            "run-1",
            {
                "event_id": "paused-before-close",
                "type": "run_paused",
                "expected_revision": 4,
            },
        )
        store.close()

        reopened = self._store()
        self.addCleanup(reopened.close)
        snapshot = reopened.snapshot("run-1")
        self.assertEqual(snapshot["state"], "paused")
        self.assertEqual(snapshot["items"][0]["state"], "unconfirmed")

    def test_reopen_discovering_run_can_resume_and_freeze_queue(self) -> None:
        store = self._store()
        store.create_run({"run_id": "discovering-run"})
        store.close()

        reopened = self._store()
        self.addCleanup(reopened.close)
        paused = reopened.snapshot("discovering-run")
        self.assertEqual(paused["state"], "paused")

        resumed = reopened.append_event(
            "discovering-run",
            {
                "event_id": "resume-discovering",
                "type": "run_resumed",
                "expected_revision": paused["revision"],
            },
        )
        self.assertEqual(resumed["state"], "discovering")

        with self.assertRaises(self.ActiveRunError):
            reopened.create_run({"run_id": "concurrent-run"})

        frozen = reopened.freeze_queue(
            "discovering-run",
            [{"process_key": "103439/2023"}],
            "queue-after-recovery",
            resumed["revision"],
        )
        self.assertEqual(frozen["state"], "running")
        with self.assertRaises(self.ActiveRunError):
            reopened.create_run({"run_id": "still-concurrent-run"})

    def test_reopen_running_run_still_resumes_as_running(self) -> None:
        store = self._store()
        self._create_running_run(store)
        store.close()

        reopened = self._store()
        self.addCleanup(reopened.close)
        paused = reopened.snapshot("run-1")
        self.assertEqual(paused["state"], "paused")

        resumed = reopened.append_event(
            "run-1",
            {
                "event_id": "resume-running",
                "type": "run_resumed",
                "expected_revision": paused["revision"],
            },
        )
        self.assertEqual(resumed["state"], "running")
        prepared = reopened.append_event(
            "run-1",
            {
                "event_id": "prepared-after-running-recovery",
                "type": "item_prepared",
                "expected_revision": resumed["revision"],
                "item_id": "103439/2023",
            },
        )
        self.assertEqual(prepared["items"][0]["state"], "prepared")

    def test_item_events_are_rejected_after_stopped_or_completed(self) -> None:
        stopped = self._store(self.root / "stopped")
        self.addCleanup(stopped.close)
        self._create_running_run(stopped)
        stopped.append_event(
            "run-1",
            {"event_id": "stop", "type": "run_stopped", "expected_revision": 1},
        )
        stopped_before = stopped.snapshot("run-1")
        with self.assertRaises(self.InvalidTransition):
            stopped.append_event(
                "run-1",
                {
                    "event_id": "after-stop",
                    "type": "item_prepared",
                    "expected_revision": 2,
                    "item_id": "103439/2023",
                },
            )
        self.assertEqual(stopped.snapshot("run-1"), stopped_before)

        completed = self._store(self.root / "completed")
        self.addCleanup(completed.close)
        completed.create_run({"run_id": "run-1"})
        completed.freeze_queue(
            "run-1", [{"process_key": "103439/2023"}], "queue", 0
        )
        completed.append_event(
            "run-1",
            {
                "event_id": "completed-prepared",
                "type": "item_prepared",
                "expected_revision": 1,
                "item_id": "103439/2023",
            },
        )
        completed.append_event(
            "run-1",
            {
                "event_id": "completed-filled",
                "type": "fields_verified",
                "expected_revision": 2,
                "item_id": "103439/2023",
            },
        )
        completed.append_event(
            "run-1",
            {
                "event_id": "completed-intent",
                "type": "send_intent",
                "expected_revision": 3,
                "item_id": "103439/2023",
            },
        )
        completed.append_event(
            "run-1",
            {
                "event_id": "completed-unconfirmed",
                "type": "send_unconfirmed",
                "expected_revision": 4,
                "item_id": "103439/2023",
            },
        )
        completed.append_event(
            "run-1",
            {"event_id": "complete", "type": "run_completed", "expected_revision": 5},
        )
        completed_before = completed.snapshot("run-1")
        with self.assertRaises(self.InvalidTransition):
            completed.append_event(
                "run-1",
                {
                    "event_id": "after-completed",
                    "type": "item_failed",
                    "expected_revision": 6,
                    "item_id": "103439/2023",
                },
            )
        self.assertEqual(completed.snapshot("run-1"), completed_before)

    def test_legacy_completed_progress_is_not_migrated_to_confirmed(self) -> None:
        (self.root / "progresso.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "revision": 1,
                    "processes": {
                        "103439/2023": {"completed": True, "updated_at": "legacy"}
                    },
                }
            ),
            encoding="utf-8",
        )
        store = self._store()
        self.addCleanup(store.close)
        store.create_run({"run_id": "run-1"})
        frozen = store.freeze_queue(
            "run-1", [{"process_key": "103439/2023"}], "event-queue", 0
        )
        self.assertEqual(frozen["items"][0]["state"], "queued")

    def test_only_one_active_run_is_allowed_across_concurrent_stores(self) -> None:
        first = self._store()
        second = self._store()
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        barrier = threading.Barrier(2)
        successes = []
        failures = []

        def create(store, run_id):
            try:
                barrier.wait(timeout=5)
                successes.append(store.create_run({"run_id": run_id})["run_id"])
            except self.ActiveRunError:
                failures.append(run_id)

        threads = [
            threading.Thread(target=create, args=(first, "run-a")),
            threading.Thread(target=create, args=(second, "run-b")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)

    def test_get_events_can_be_fenced_at_a_snapshot_revision(self) -> None:
        store = self._store()
        self.addCleanup(store.close)
        self._create_running_run(store)
        store.append_event(
            "run-1",
            {
                "event_id": "fenced-event",
                "type": "item_prepared",
                "expected_revision": 1,
                "item_id": "103439/2023",
            },
        )
        store.append_event(
            "run-1",
            {
                "event_id": "unfenced-event",
                "type": "fields_verified",
                "expected_revision": 2,
                "item_id": "103439/2023",
            },
        )

        events = store.get_events("run-1", through=2)

        self.assertEqual([event["event_id"] for event in events], [
            "event-queue",
            "fenced-event",
        ])


class OperationIndicatorsTests(unittest.TestCase):
    """Indicadores de desempenho da operacao (Fase 4)."""

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _store(self):
        from automation_store import AutomationStore

        return AutomationStore(self.root)

    def test_reports_empty_indicators_without_runs(self):
        store = self._store()
        try:
            indicators = store.operation_indicators()
        finally:
            store.close()

        self.assertEqual(indicators["schema_version"], 1)
        self.assertEqual(indicators["runs_total"], 0)
        self.assertEqual(indicators["confirmed_total"], 0)
        self.assertEqual(indicators["unconfirmed_total"], 0)
        self.assertEqual(indicators["failed_total"], 0)
        self.assertEqual(indicators["by_run_state"], {})

    def test_counts_confirmed_and_failed_items_from_the_workflow_root(self):
        store = self._store()
        try:
            created = store.create_run({"run_id": "run-ok", "schema_version": 1})
            frozen = store.freeze_queue(
                "run-ok",
                [
                    {"process_key": "103439/2023"},
                    {"process_key": "103490/2023"},
                ],
                "ind-queue",
                created["revision"],
            )
            prepared = store.append_event(
                "run-ok",
                {
                    "event_id": "ind-prepared",
                    "type": "item_prepared",
                    "expected_revision": frozen["revision"],
                    "item_id": "103439/2023",
                },
            )
            filled = store.append_event(
                "run-ok",
                {
                    "event_id": "ind-filled",
                    "type": "fields_verified",
                    "expected_revision": prepared["revision"],
                    "item_id": "103439/2023",
                },
            )
            sent = store.append_event(
                "run-ok",
                {
                    "event_id": "ind-sent",
                    "type": "send_intent",
                    "expected_revision": filled["revision"],
                    "item_id": "103439/2023",
                },
            )
            store.append_event(
                "run-ok",
                {
                    "event_id": "ind-confirmed",
                    "type": "send_confirmed",
                    "expected_revision": sent["revision"],
                    "item_id": "103439/2023",
                },
            )
            store.append_event(
                "run-ok",
                {
                    "event_id": "ind-failed",
                    "type": "item_failed",
                    "expected_revision": sent["revision"] + 1,
                    "item_id": "103490/2023",
                },
            )
            indicators = store.operation_indicators()
        finally:
            store.close()

        self.assertEqual(indicators["schema_version"], 1)
        self.assertEqual(indicators["runs_total"], 1)
        self.assertEqual(indicators["confirmed_total"], 1)
        self.assertEqual(indicators["failed_total"], 1)
        self.assertEqual(indicators["by_run_state"], {"running": 1})
        self.assertEqual(indicators["items_total"], 2)
        # Indicadores sao somente contagens: nenhum identificador de processo
        # ou interessado pode aparecer no resultado.
        rendered = json.dumps(indicators, ensure_ascii=False)
        self.assertNotIn("103439/2023", rendered)
        self.assertNotIn("103490/2023", rendered)
        self.assertTrue(all(
            not isinstance(value, str) or "/" not in value
            for value in indicators.values()
        ))


if __name__ == "__main__":

    unittest.main()
