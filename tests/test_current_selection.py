"""Tests for the transient current-selection tracker (Portal Atual)."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.area_restrita.current_selection import (
    PORTAL_SELECTION_TTL_SECONDS,
    PortalSelectionError,
    PortalSelectionTracker,
)
from app.core.models import ProcessRecord
from app.core.store import Store

IDENTITY = {"processKey": "102390/2026", "interestedNormalized": "pessoa exemplo"}


class FakeClock:
    """A monotonic clock the test can move by hand."""

    def __init__(self, start=0.0):
        self.now = float(start)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += float(seconds)


class PortalSelectionTrackerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        self.store = Store.open(self.data / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.clock = FakeClock()
        self.tracker = PortalSelectionTracker(self.store, clock=self.clock)

    def make_process(self, *, status="REVISAR", process_key="102390/2026"):
        return self.store.upsert_process(
            ProcessRecord(
                process_key=process_key,
                interested="Pessoa Exemplo",
                interested_normalized="pessoa exemplo",
                status=status,
            )
        )

    def snapshot(self, **overrides):
        payload = {
            "identity": dict(IDENTITY),
            "generation": 3,
            "screen": "form",
            "fields": {
                "cargo": {"value": "", "disabled": False, "readOnly": False, "options": []}
            },
        }
        payload.update(overrides)
        return payload


class PortalSelectionResolutionTests(PortalSelectionTrackerTestCase):
    def test_an_exact_identity_resolves_to_one_process(self):
        process_id = self.make_process()

        state = self.tracker.observe(self.snapshot())

        self.assertEqual(state["state"], "MATCHED")
        self.assertEqual(state["process_id"], process_id)
        self.assertEqual(state["process_key"], "102390/2026")
        self.assertEqual(state["generation"], 3)
        self.assertEqual(state["screen"], "form")
        self.assertTrue(state["observed_at"])

    def test_the_observed_screen_defaults_to_the_act_form(self):
        self.make_process()

        without_screen = self.snapshot()
        without_screen.pop("screen")

        state = self.tracker.observe(without_screen)

        self.assertEqual(state["state"], "MATCHED")
        self.assertEqual(state["screen"], "form")

    def test_an_unknown_process_is_not_found_without_a_process_id(self):
        self.make_process(process_key="999999/2026")

        state = self.tracker.observe(self.snapshot())

        self.assertEqual(state["state"], "NOT_FOUND")
        self.assertNotIn("process_id", state)
        self.assertEqual(self.tracker.public_state()["state"], "NOT_FOUND")

    def test_an_ambiguous_identity_is_reported_without_choosing_a_process(self):
        process_id = self.make_process()
        self.store._connection.execute(
            "UPDATE processes SET portal_act_id = ? WHERE id = ?", ("act-1", process_id)
        )

        state = self.tracker.observe(
            self.snapshot(identity={**IDENTITY, "portalActId": "act-2"})
        )

        self.assertEqual(state["state"], "AMBIGUOUS")
        self.assertNotIn("process_id", state)
        # Ambiguity is never repaired by picking the closest looking match.
        self.assertEqual(len(self.store.list_processes()), 1)

    def test_an_observation_never_changes_the_process_status(self):
        process_id = self.make_process(status="REVISAR")
        before = self.store.get_process(process_id)

        for _ in range(3):
            self.tracker.observe(self.snapshot())

        self.assertEqual(self.store.get_process(process_id), before)


class PortalSelectionValidationTests(PortalSelectionTrackerTestCase):
    def assertInvalid(self, observation):
        with self.assertRaises(PortalSelectionError) as raised:
            self.tracker.observe(observation)
        self.assertEqual(raised.exception.code, "INVALID")

    def test_a_non_mapping_observation_is_invalid(self):
        for payload in (None, "form", 3, [], ()):
            with self.subTest(payload=payload):
                self.assertInvalid(payload)

    def test_a_snapshot_without_identity_is_invalid(self):
        self.assertInvalid({"generation": 3, "fields": {}})
        self.assertInvalid({"identity": None, "generation": 3})

    def test_an_incomplete_identity_is_invalid(self):
        for identity in (
            {},
            {"processKey": "102390/2026"},
            {"interestedNormalized": "pessoa exemplo"},
            {"processKey": "  ", "interestedNormalized": "pessoa exemplo"},
        ):
            with self.subTest(identity=identity):
                self.assertInvalid(self.snapshot(identity=identity))

    def test_a_missing_boolean_or_zero_generation_is_invalid(self):
        for generation in (None, True, False, 0, -1, "3", 3.0):
            with self.subTest(generation=generation):
                self.assertInvalid(self.snapshot(generation=generation))

    def test_a_malformed_screen_is_invalid(self):
        for screen in ("", "A B", "form/../x", "x" * 40, 7):
            with self.subTest(screen=screen):
                self.assertInvalid(self.snapshot(screen=screen))

    def test_the_public_state_never_carries_the_private_snapshot(self):
        self.make_process()
        self.tracker.observe(self.snapshot())

        state = self.tracker.public_state()

        self.assertEqual(
            set(state),
            {"state", "process_id", "process_key", "generation", "screen", "observed_at"},
        )
        self.assertNotIn("form", state)
        self.assertNotIn("fields", state)
        serialized = json.dumps(state)
        for forbidden in (
            "interestedNormalized",
            "cargo",
            "cookie",
            "token",
            "authorization",
        ):
            self.assertNotIn(forbidden, serialized)


class PortalSelectionTtlTests(PortalSelectionTrackerTestCase):
    def test_the_ttl_is_ten_seconds(self):
        self.assertEqual(PORTAL_SELECTION_TTL_SECONDS, 10.0)

    def test_a_recent_selection_still_serves_its_private_snapshot(self):
        self.make_process()
        self.tracker.observe(self.snapshot())
        self.clock.advance(PORTAL_SELECTION_TTL_SECONDS - 0.001)

        snapshot = self.tracker.require_fill_snapshot()

        self.assertEqual(snapshot["identity"]["processKey"], "102390/2026")
        self.assertEqual(snapshot["generation"], 3)
        self.assertEqual(self.tracker.public_state()["state"], "MATCHED")

    def test_the_served_snapshot_is_a_copy(self):
        self.make_process()
        self.tracker.observe(self.snapshot())

        first = self.tracker.require_fill_snapshot()
        first["fields"]["cargo"]["value"] = "mutado"
        first["identity"]["processKey"] = "mutado/2026"

        second = self.tracker.require_fill_snapshot()
        self.assertEqual(second["identity"]["processKey"], "102390/2026")
        self.assertEqual(second["fields"]["cargo"]["value"], "")

    def test_the_observation_expires_and_drops_its_snapshot(self):
        self.make_process()
        self.tracker.observe(self.snapshot())

        self.clock.advance(PORTAL_SELECTION_TTL_SECONDS)

        self.assertEqual(self.tracker.public_state()["state"], "NO_ACTIVE_FORM")
        with self.assertRaises(PortalSelectionError) as raised:
            self.tracker.require_fill_snapshot()
        self.assertEqual(raised.exception.code, "FORM_NOT_AVAILABLE")

    def test_a_renewed_observation_keeps_the_selection_alive(self):
        self.make_process()
        self.tracker.observe(self.snapshot())
        self.clock.advance(PORTAL_SELECTION_TTL_SECONDS - 1)

        self.tracker.observe(self.snapshot())
        self.clock.advance(PORTAL_SELECTION_TTL_SECONDS - 1)

        self.assertEqual(self.tracker.public_state()["state"], "MATCHED")
        self.assertEqual(self.tracker.require_fill_snapshot()["generation"], 3)


class PortalSelectionClearTests(PortalSelectionTrackerTestCase):
    def test_an_unobserved_tracker_reports_no_active_form(self):
        self.assertEqual(self.tracker.public_state(), {"state": "NO_ACTIVE_FORM"})
        with self.assertRaises(PortalSelectionError) as raised:
            self.tracker.require_fill_snapshot()
        self.assertEqual(raised.exception.code, "FORM_NOT_AVAILABLE")

    def test_clearing_without_a_form_reports_no_active_form(self):
        self.make_process()
        self.tracker.observe(self.snapshot())

        state = self.tracker.clear("FORM_NOT_AVAILABLE")

        self.assertEqual(state["state"], "NO_ACTIVE_FORM")
        self.assertNotIn("process_id", state)
        with self.assertRaises(PortalSelectionError) as raised:
            self.tracker.require_fill_snapshot()
        self.assertEqual(raised.exception.code, "FORM_NOT_AVAILABLE")

    def test_clearing_an_ambiguous_form_reports_ambiguity(self):
        self.make_process()
        self.tracker.observe(self.snapshot())

        state = self.tracker.clear("FORM_AMBIGUOUS")

        self.assertEqual(state["state"], "AMBIGUOUS")
        self.assertNotIn("process_id", state)
        with self.assertRaises(PortalSelectionError) as raised:
            self.tracker.require_fill_snapshot()
        self.assertEqual(raised.exception.code, "FORM_AMBIGUOUS")

    def test_an_inactive_portal_tab_reports_no_active_form(self):
        self.make_process()
        self.tracker.observe(self.snapshot())

        state = self.tracker.clear("PORTAL_TAB_NOT_ACTIVE")

        self.assertEqual(state["state"], "NO_ACTIVE_FORM")
        self.assertEqual(state["code"], "PORTAL_TAB_NOT_ACTIVE")

    def test_the_default_clear_code_is_form_not_available(self):
        self.assertEqual(self.tracker.clear()["state"], "NO_ACTIVE_FORM")

    def test_a_cleared_state_expires_like_an_observation(self):
        self.make_process()
        self.tracker.clear("FORM_AMBIGUOUS")

        self.clock.advance(PORTAL_SELECTION_TTL_SECONDS)

        self.assertEqual(self.tracker.public_state()["state"], "NO_ACTIVE_FORM")
        self.assertNotIn("code", self.tracker.public_state())

