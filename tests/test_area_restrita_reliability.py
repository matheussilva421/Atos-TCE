"""RED tests for the Area Restrita reliability ledger (Reliability Reset Task 1)."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.area_restrita.reliability import (
    CAPABILITIES,
    ENVIRONMENTS,
    MIN_QUALIFICATION_RUNS,
    CapabilityState,
    ReliabilityError,
    ReliabilityRecorder,
    canonical_identity,
    ensure_sanitized,
)

BUILD = "a" * 40


class ReliabilityRecorderTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        self.recorder = ReliabilityRecorder(self.data, BUILD)

    def record(
        self,
        capability="manual_form_fill",
        environment="real-dev",
        *,
        passed=True,
        result_code="SUCCEEDED",
        recorder=None,
        intervene=False,
    ):
        recorder = recorder or self.recorder
        run_id = recorder.start(capability, environment)
        recorder.transition(
            run_id,
            boundary="fill_command_completed",
            state_before="FORM",
            state_after="FORM_FILLED",
            result_code=result_code,
            elapsed_ms=1200,
            expected_identity={"processKey": "102390/2026", "interestedNormalized": "pessoa exemplo"},
            observed_identity={"processKey": "102390/2026", "interestedNormalized": "pessoa exemplo"},
            generation_before=7,
            generation_after=7,
        )
        if intervene:
            recorder.intervention(run_id, "technical-recovery")
        recorder.finish(run_id, passed=passed, result_code=result_code)
        return run_id

    def events_text(self):
        return (self.data / "reliability" / "events.jsonl").read_text(encoding="utf-8")

    # -------------------------------------------------- default state / storage

    def test_capabilities_default_to_unqualified(self):
        capabilities = self.recorder.capabilities()
        self.assertEqual(sorted(capabilities), sorted(CAPABILITIES))
        for name, entry in capabilities.items():
            self.assertEqual(entry["state"], CapabilityState.UNQUALIFIED.value, name)
            self.assertEqual(entry["real_dev_streak"], 0, name)
            self.assertEqual(entry["portable_streak"], 0, name)

    def test_reliability_files_live_under_data_root(self):
        self.recorder.start("manual_form_fill", "real-dev")
        self.recorder.mark_experimental("manual_form_fill", reason="offline contract green")
        root = self.data / "reliability"
        self.assertTrue((root / "events.jsonl").is_file())
        self.assertTrue((root / "capabilities.json").is_file())
        self.assertTrue((root / "identity.key").is_file())
        self.assertEqual(list(root.parent.glob("*.jsonl")), [])

    # ---------------------------------------------------------------- privacy

    def test_identity_is_persisted_only_as_local_hmac(self):
        self.record()
        text = self.events_text()
        self.assertNotIn("102390/2026", text)
        self.assertNotIn("pessoa exemplo", text)
        event = [json.loads(line) for line in text.splitlines() if line.strip()]
        transition = next(item for item in event if item["type"] == "transition")
        for key in ("expected_identity_hash", "observed_identity_hash"):
            value = transition[key]
            self.assertIsInstance(value, str)
            self.assertEqual(len(value), 64)
            int(value, 16)

    def test_event_rejects_forbidden_private_keys(self):
        for key in (
            "processKey",
            "process_key",
            "interested",
            "interestedNormalized",
            "cpf",
            "matricula",
            "cookie",
            "token",
            "authorization",
        ):
            with self.subTest(key=key):
                with self.assertRaises(ReliabilityError):
                    ensure_sanitized({"boundary": "fill", key: "valor sensível"})
        # Nested keys are refused too.
        with self.assertRaises(ReliabilityError):
            ensure_sanitized({"outer": {"inner": [{"cpf": "000"}]}})

    def test_event_never_serializes_process_or_interested_text(self):
        self.record()
        text = self.events_text()
        self.assertNotIn("102390", text)
        self.assertNotIn("pessoa", text)
        self.assertEqual(canonical_identity({"cpf": "x", "processKey": "1/2"}), {"processKey": "1/2"})

    # ------------------------------------------------------------- sequences

    def test_twenty_consecutive_same_build_passes_qualification(self):
        for _ in range(20):
            self.record()
        evaluation = self.recorder.evaluate("manual_form_fill", "real-dev", 20)
        self.assertTrue(evaluation["qualified"])
        self.assertEqual(evaluation["streak"], 20)

    def test_failure_resets_the_counted_sequence(self):
        for _ in range(19):
            self.record()
        self.assertFalse(self.recorder.evaluate("manual_form_fill", "real-dev")["qualified"])
        self.record(passed=False, result_code="FORM_NOT_AVAILABLE")
        self.assertEqual(self.recorder.evaluate("manual_form_fill", "real-dev")["streak"], 0)
        for _ in range(19):
            self.record()
        self.assertFalse(self.recorder.evaluate("manual_form_fill", "real-dev")["qualified"])
        self.record()
        self.assertTrue(self.recorder.evaluate("manual_form_fill", "real-dev")["qualified"])

    def test_build_change_breaks_the_sequence(self):
        for _ in range(10):
            self.record()
        other = ReliabilityRecorder(self.data, "b" * 40)
        for _ in range(10):
            self.record(recorder=other)
        evaluation = self.recorder.evaluate("manual_form_fill", "real-dev", 20)
        self.assertFalse(evaluation["qualified"])
        self.assertEqual(evaluation["streak"], 10)

    def test_intervention_breaks_the_sequence(self):
        for _ in range(19):
            self.record()
        self.record(intervene=True)
        evaluation = self.recorder.evaluate("manual_form_fill", "real-dev", 20)
        self.assertFalse(evaluation["qualified"])
        self.assertEqual(evaluation["streak"], 0)

    def test_offline_environment_never_qualifies_real_capability(self):
        for _ in range(25):
            self.record(environment="offline")
        self.assertTrue(self.recorder.evaluate("manual_form_fill", "offline", 20)["qualified"])
        self.assertFalse(self.recorder.evaluate("manual_form_fill", "real-dev", 20)["qualified"])
        with self.assertRaises(ReliabilityError):
            self.recorder.promote(
                "manual_form_fill",
                CapabilityState.QUALIFIED,
                environment="offline",
                required=20,
                reason="offline nunca qualifica",
            )

    def test_production_requires_portable_normal_chrome_environment(self):
        for _ in range(20):
            self.record()
        self.recorder.promote(
            "manual_form_fill",
            CapabilityState.QUALIFIED,
            environment="real-dev",
            required=20,
            reason="real-dev 20/20",
        )
        with self.assertRaises(ReliabilityError):
            self.recorder.promote(
                "manual_form_fill",
                CapabilityState.PRODUCTION,
                environment="real-dev",
                required=20,
                reason="ambiente errado",
            )
        for _ in range(20):
            self.record(environment="portable-normal-chrome")
        self.recorder.promote(
            "manual_form_fill",
            CapabilityState.PRODUCTION,
            environment="portable-normal-chrome",
            required=20,
            reason="portable 20/20",
        )
        self.assertEqual(
            self.recorder.capabilities()["manual_form_fill"]["state"],
            CapabilityState.PRODUCTION.value,
        )

    # -------------------------------------------------------------- promotion

    def test_cannot_promote_to_qualified_without_valid_real_dev_20_of_20(self):
        with self.assertRaises(ReliabilityError):
            self.recorder.promote(
                "manual_form_fill",
                CapabilityState.QUALIFIED,
                environment="real-dev",
                required=20,
                reason="sem sequência",
            )
        for _ in range(19):
            self.record()
        with self.assertRaises(ReliabilityError):
            self.recorder.promote(
                "manual_form_fill",
                CapabilityState.QUALIFIED,
                environment="real-dev",
                required=20,
                reason="19/20",
            )
        self.record()
        self.recorder.promote(
            "manual_form_fill",
            CapabilityState.QUALIFIED,
            environment="real-dev",
            required=20,
            reason="20/20",
        )
        self.assertEqual(
            self.recorder.capabilities()["manual_form_fill"]["state"],
            CapabilityState.QUALIFIED.value,
        )

    def test_cannot_promote_to_production_without_valid_portable_20_of_20(self):
        for _ in range(20):
            self.record()
        self.recorder.promote(
            "manual_form_fill",
            CapabilityState.QUALIFIED,
            environment="real-dev",
            required=20,
            reason="real-dev 20/20",
        )
        with self.assertRaises(ReliabilityError):
            self.recorder.promote(
                "manual_form_fill",
                CapabilityState.PRODUCTION,
                environment="portable-normal-chrome",
                required=20,
                reason="sem amostra portátil",
            )
        self.assertEqual(
            self.recorder.capabilities()["manual_form_fill"]["state"],
            CapabilityState.QUALIFIED.value,
        )

    def test_reproducible_regression_can_downgrade_to_unqualified(self):
        for _ in range(20):
            self.record()
        self.recorder.promote(
            "manual_form_fill",
            CapabilityState.QUALIFIED,
            environment="real-dev",
            required=20,
            reason="real-dev 20/20",
        )
        self.recorder.downgrade("manual_form_fill", reason="regressão reproduzível em uso real")
        self.assertEqual(
            self.recorder.capabilities()["manual_form_fill"]["state"],
            CapabilityState.UNQUALIFIED.value,
        )

    def test_promote_refuses_unearned_targets_and_unknown_names(self):
        with self.assertRaises(ReliabilityError):
            self.recorder.promote(
                "manual_form_fill",
                CapabilityState.EXPERIMENTAL,
                environment="real-dev",
                required=20,
                reason="não é promoção",
            )
        with self.assertRaises(ReliabilityError):
            self.recorder.start("nao_existe", "real-dev")
        with self.assertRaises(ReliabilityError):
            self.recorder.start("manual_form_fill", "producao")
        self.assertEqual(set(ENVIRONMENTS), {"offline", "real-dev", "portable-normal-chrome"})


    def test_promote_refuses_a_threshold_below_the_spec_gate(self):
        for _ in range(20):
            self.record()
        for required in (1, 19):
            with self.subTest(required=required):
                with self.assertRaises(ReliabilityError):
                    self.recorder.promote(
                        "manual_form_fill",
                        CapabilityState.QUALIFIED,
                        environment="real-dev",
                        required=required,
                        reason="gate rebaixado",
                    )
        self.recorder.promote(
            "manual_form_fill",
            CapabilityState.QUALIFIED,
            environment="real-dev",
            required=MIN_QUALIFICATION_RUNS,
            reason="20/20 real-dev",
        )
        self.assertEqual(
            self.recorder.capabilities()["manual_form_fill"]["state"],
            CapabilityState.QUALIFIED.value,
        )

    def test_a_second_terminal_event_for_the_same_run_is_refused(self):
        run_id = self.recorder.start("manual_form_fill", "real-dev")
        self.recorder.finish(run_id, passed=False, result_code="FORM_NOT_AVAILABLE")

        with self.assertRaises(ReliabilityError):
            self.recorder.finish(run_id, passed=True, result_code="SUCCEEDED")

        self.assertEqual(self.recorder.evaluate("manual_form_fill", "real-dev")["streak"], 0)

    def test_free_form_codes_and_identifiers_are_refused(self):
        run_id = self.recorder.start("manual_form_fill", "real-dev")

        with self.assertRaises(ReliabilityError):
            self.recorder.transition(
                run_id,
                boundary="manual_fill",
                state_before="FORM",
                state_after="FORM_FILLED",
                result_code="Pessoa Exemplo, CPF 123",
            )
        with self.assertRaises(ReliabilityError):
            self.recorder.intervention(run_id, "recovery manual")
        with self.assertRaises(ReliabilityError):
            self.recorder.start("manual_form_fill", "real-dev", browser_session_id="cookie=abc")

        # A plain machine code is still accepted.
        self.recorder.transition(
            run_id,
            boundary="manual_fill",
            state_before="FORM",
            state_after="FORM_FILLED",
            result_code="FORM_NOT_AVAILABLE",
        )
        self.assertEqual(len([line for line in self.events_text().splitlines() if line.strip()]), 2)



if __name__ == "__main__":  # pragma: no cover
    unittest.main()

