"""RED tests for the Area Restrita reliability ledger (Reliability Reset Task 1)."""

import json
import subprocess
import sys
import threading
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
        run_id = self.recorder.start("manual_form_fill", "real-dev")
        self.recorder.transition(
            run_id,
            boundary="manual_fill",
            state_before="FORM",
            state_after="FORM_FILLED",
            result_code="SUCCEEDED",
            expected_identity={"processKey": "1/2", "interestedNormalized": "pessoa"},
        )
        self.recorder.mark_experimental("manual_form_fill", reason="offline contract green")
        root = self.data / "reliability"
        self.assertTrue((root / "events.jsonl").is_file())
        self.assertTrue((root / "capabilities.json").is_file())
        self.assertTrue((root / "identity.key").is_file())
        self.assertEqual(list(root.parent.glob("*.jsonl")), [])

    def test_a_pure_read_never_creates_local_state(self):
        fresh = Path(self._tmp.name) / "fresh"
        recorder = ReliabilityRecorder(fresh, BUILD)

        capabilities = recorder.capabilities()
        self.assertEqual(capabilities["manual_form_fill"]["state"], "UNQUALIFIED")
        self.assertEqual(recorder.evaluate("manual_form_fill", "real-dev")["streak"], 0)
        self.assertEqual(recorder.summary("manual_form_fill", "real-dev")["runs"], 0)

        self.assertFalse((fresh / "reliability").exists())

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

    def test_a_duplicate_terminal_after_a_malformed_one_is_refused(self):
        path = self.data / "reliability" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            {
                "type": "run_start",
                "run_id": "tampered-1",
                "capability": "manual_form_fill",
                "environment": "real-dev",
                "build_id": BUILD,
                "ts": 1.0,
            },
            {
                "type": "run_finished",
                "run_id": "tampered-1",
                "passed": "false",
                "result_code": "SUCCEEDED",
                "ts": 1.1,
            },
            {
                "type": "run_finished",
                "run_id": "tampered-1",
                "passed": True,
                "result_code": "SUCCEEDED",
                "ts": 1.2,
            },
        ]
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

        with self.assertRaises(ReliabilityError):
            self.recorder.evaluate("manual_form_fill", "real-dev")

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

    def test_finish_requires_a_real_boolean(self):
        run_id = self.recorder.start("manual_form_fill", "real-dev")

        with self.assertRaises(ReliabilityError):
            self.recorder.finish(run_id, passed="false", result_code="SUCCEEDED")

    def test_evaluate_refuses_a_threshold_below_the_spec_gate(self):
        with self.assertRaises(ReliabilityError):
            self.recorder.evaluate("manual_form_fill", "real-dev", 1)

    def test_a_concurrent_double_finish_records_one_terminal_event(self):
        run_id = self.recorder.start("manual_form_fill", "real-dev")
        outcomes = []

        def close():
            try:
                self.recorder.finish(run_id, passed=True, result_code="SUCCEEDED")
                outcomes.append("ok")
            except ReliabilityError:
                outcomes.append("refused")

        threads = [threading.Thread(target=close) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(outcomes), ["ok", "refused"])
        self.assertEqual(self.events_text().count('"type":"run_finished"'), 1)

    def test_a_non_boolean_terminal_record_is_never_counted_as_a_pass(self):
        path = self.data / "reliability" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            {
                "type": "run_start",
                "run_id": "tampered-0",
                "capability": "manual_form_fill",
                "environment": "real-dev",
                "build_id": BUILD,
                "ts": 1.0,
            },
            {
                "type": "run_finished",
                "run_id": "tampered-0",
                "passed": "false",
                "result_code": "SUCCEEDED",
                "ts": 1.1,
            },
        ]
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

        self.assertEqual(self.recorder.evaluate("manual_form_fill", "real-dev")["streak"], 0)


REPO_ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION_CLI = REPO_ROOT / "scripts" / "portal-reliability" / "qualification.py"
REPORT_CLI = REPO_ROOT / "scripts" / "portal-reliability" / "report.py"
CAPABILITY_STATE_CLI = REPO_ROOT / "scripts" / "portal-reliability" / "capability-state.py"


class QualificationCliTests(unittest.TestCase):
    """The qualification CLI is a reader of the ledger, never a promoter."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"

    def seed(self, *, passes, failures=0, build="a" * 40, intervene=False):
        recorder = ReliabilityRecorder(self.data, build)
        total = passes + failures
        for index in range(total):
            run_id = f"{build[:6]}-{index}"
            recorder.start("manual_form_fill", "real-dev", run_id=run_id)
            recorder.transition(
                run_id,
                boundary="reread_completed",
                state_before="FORM",
                state_after="FORM_FILLED",
                result_code="REREAD_OK",
                elapsed_ms=100,
            )
            if intervene and index == total - 1:
                recorder.intervention(run_id, "technical-recovery")
            passed = index < passes
            recorder.finish(
                run_id,
                passed=passed,
                result_code="SUCCEEDED" if passed else "FORM_NOT_AVAILABLE",
            )

    def qualify(self, *, build="a" * 40, required=20, environment="real-dev"):
        return subprocess.run(
            [
                sys.executable,
                str(QUALIFICATION_CLI),
                "--data-root",
                str(self.data),
                "--capability",
                "manual_form_fill",
                "--environment",
                environment,
                "--required",
                str(required),
                "--build",
                build,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_nineteen_passes_are_not_qualified(self):
        self.seed(passes=19)

        result = self.qualify()

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(json.loads(result.stdout)["ok"])

    def test_twenty_consecutive_same_build_is_qualified(self):
        self.seed(passes=20)

        result = self.qualify()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["streak"], 20)
        self.assertTrue(payload["same_build"])

    def test_a_failure_inside_the_sequence_breaks_it(self):
        self.seed(passes=19, failures=1)

        self.assertNotEqual(self.qualify().returncode, 0)

    def test_twenty_split_across_builds_is_not_qualified(self):
        self.seed(passes=10, build="a" * 40)
        self.seed(passes=10, build="b" * 40)

        self.assertNotEqual(self.qualify(build="b" * 40).returncode, 0)
        self.assertNotEqual(self.qualify(build="a" * 40).returncode, 0)

    def test_an_intervention_breaks_the_sequence(self):
        self.seed(passes=20, intervene=True)

        self.assertNotEqual(self.qualify().returncode, 0)

    def test_the_cli_refuses_a_threshold_below_the_spec_gate(self):
        self.seed(passes=20)

        result = self.qualify(required=1)

        self.assertEqual(result.returncode, 2)


    def test_the_cli_does_not_mutate_capability_state(self):
        recorder = ReliabilityRecorder(self.data, "a" * 40)
        recorder.downgrade("open_act", reason="fixture")
        self.seed(passes=20)

        self.assertEqual(self.qualify().returncode, 0)

        after = json.loads((self.data / "reliability" / "capabilities.json").read_text(encoding="utf-8"))
        self.assertEqual(after["capabilities"]["open_act"]["state"], "UNQUALIFIED")
        self.assertNotIn("manual_form_fill", after["capabilities"])

    def test_the_cli_refuses_a_non_real_environment(self):
        self.seed(passes=20)

        result = self.qualify(environment="offline")

        self.assertEqual(result.returncode, 2)

    def test_the_cli_refuses_an_unsafe_build(self):
        self.seed(passes=20)

        result = self.qualify(build="102390/2026")

        self.assertEqual(result.returncode, 2)


class CapabilityStateCliTests(unittest.TestCase):
    """The bootstrap CLI can only declare EXPERIMENTAL or downgrade."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"

    def run_cli(self, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(CAPABILITY_STATE_CLI),
                "--data-root",
                str(self.data),
                "--capability",
                "manual_form_fill",
                "--build",
                "a" * 40,
                *extra,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_marking_experimental_records_the_state_without_qualifying(self):
        result = self.run_cli("--experimental")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "EXPERIMENTAL")
        self.assertEqual(payload["real_dev_streak"], 0)
        self.assertEqual(payload["portable_streak"], 0)
        self.assertIn("a" * 40, payload["reason"])

    def test_the_bootstrap_requires_exactly_one_action(self):
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(self.run_cli("--experimental", "--downgrade").returncode, 2)

    def test_downgrade_returns_the_capability_to_unqualified(self):
        self.assertEqual(self.run_cli("--experimental").returncode, 0)

        result = self.run_cli("--downgrade")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["state"], "UNQUALIFIED")

    def test_the_bootstrap_never_offers_a_promotion(self):
        source = CAPABILITY_STATE_CLI.read_text(encoding="utf-8")

        # The docstring states the prohibition; the code must not import the
        # state enum or reach the promotion method.
        for forbidden in ("CapabilityState", ".promote("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        for method in ("mark_experimental", "downgrade"):
            with self.subTest(method=method):
                self.assertIn(method, source)


class ReportCliTests(unittest.TestCase):
    """The report is aggregate-only and never copies ledger text."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"

    def report(self, *, capability="open_act", build=None, fmt="json"):
        command = [
            sys.executable,
            str(REPORT_CLI),
            "--data-root",
            str(self.data),
            "--capability",
            capability,
            "--format",
            fmt,
        ]
        if build is not None:
            command += ["--build", build]
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def write_synthetic(self, durations_ms, *, capability="open_act"):
        path = self.data / "reliability" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        base = 1_700_000_000.0
        lines = []
        for index, duration in enumerate(durations_ms):
            run_id = f"synth-{index}"
            started = base + index * 10.0
            lines.append(
                json.dumps(
                    {
                        "type": "run_start",
                        "run_id": run_id,
                        "capability": capability,
                        "environment": "real-dev",
                        "build_id": "d" * 40,
                        "ts": started,
                    }
                )
            )
            lines.append(
                json.dumps(
                    {
                        "type": "transition",
                        "run_id": run_id,
                        "boundary": "fill_command_completed",
                        "state_before": "FORM",
                        "state_after": "FORM_FILLED",
                        "result_code": "SUCCEEDED",
                        "ts": started + 0.01,
                    }
                )
            )
            lines.append(
                json.dumps(
                    {
                        "type": "run_finished",
                        "run_id": run_id,
                        "passed": True,
                        "result_code": "SUCCEEDED",
                        "ts": started + duration / 1000.0,
                    }
                )
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_report_computes_median_and_p95_deterministically(self):
        self.write_synthetic([(index + 1) * 100 for index in range(20)])

        result = self.report()

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["attempts"], 20)
        self.assertEqual(payload["passed"], 20)
        self.assertEqual(payload["median_ms"], 1050.0)
        self.assertEqual(payload["p95_ms"], 1900)
        self.assertEqual(payload["outcome_codes"], {"SUCCEEDED": 20})

    def test_report_markdown_contains_only_aggregates(self):
        self.write_synthetic([100, 200])

        result = self.report(fmt="markdown")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| mediana_ms | 150.0 |", result.stdout)
        self.assertIn("| result_code:SUCCEEDED | 2 |", result.stdout)

    def test_report_never_copies_identity_text(self):
        recorder = ReliabilityRecorder(self.data, "e" * 40)
        for index in range(3):
            run_id = f"priv-{index}"
            recorder.start("open_act", "real-dev", run_id=run_id)
            recorder.transition(
                run_id,
                boundary="open_act_completed",
                state_before="LIST",
                state_after="FORM",
                result_code="SUCCEEDED",
                expected_identity={
                    "processKey": "102390/2026",
                    "interestedNormalized": "pessoa exemplo",
                },
                observed_identity={
                    "processKey": "102390/2026",
                    "interestedNormalized": "pessoa exemplo",
                },
            )
            recorder.finish(run_id, passed=True, result_code="SUCCEEDED")

        result = self.report(fmt="markdown")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("102390", result.stdout)
        self.assertNotIn("pessoa exemplo", result.stdout)
        self.assertIn("| tentativas | 3 |", result.stdout)

    def test_report_collapses_unknown_codes_instead_of_echoing_them(self):
        path = self.data / "reliability" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(
                {
                    "type": "run_start",
                    "run_id": "x-0",
                    "capability": "open_act",
                    "environment": "real-dev",
                    "build_id": "f" * 40,
                    "ts": 1.0,
                }
            ),
            json.dumps(
                {
                    "type": "transition",
                    "run_id": "x-0",
                    "boundary": "b",
                    "result_code": "PESSOAEXEMPLO",
                    "ts": 1.1,
                }
            ),
            json.dumps(
                {
                    "type": "run_finished",
                    "run_id": "x-0",
                    "passed": False,
                    "result_code": "1023902026",
                    "ts": 1.2,
                }
            ),
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = self.report()

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["outcome_codes"], {"OTHER": 1})
        self.assertEqual(payload["boundary_codes"], {"OTHER": 1})
        markdown = self.report(fmt="markdown")
        self.assertNotIn("PESSOAEXEMPLO", markdown.stdout)
        self.assertNotIn("1023902026", markdown.stdout)
        self.assertIn("result_code:OTHER", markdown.stdout)

    def test_report_refuses_an_unsafe_build_filter(self):
        result = self.report(build="102390/2026")

        self.assertEqual(result.returncode, 2)





if __name__ == "__main__":  # pragma: no cover
    unittest.main()

