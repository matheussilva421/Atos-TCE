"""Parity and behaviour tests for the backend legal foundation (M4 Task 3).

The oracle is the proven JavaScript pipeline: ``legal_parity_harness.mjs`` runs
``resolveLegalFoundation`` and its helpers over the same fixtures and the test
compares every field. A behavioural assertion that disagrees with the oracle is
a bug in the port, not a licence to change the rule.
"""

import json
import math
import shutil
import subprocess
import unittest
from pathlib import Path

from app.analysis import legal

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "legal-cases.json"
HARNESS = REPO_ROOT / "tests" / "legal_parity_harness.mjs"
NODE = shutil.which("node")

_ORACLE_CACHE: dict[str, object] = {}


def cases() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def case(name: str) -> dict:
    for entry in cases():
        if entry["name"] == name:
            return entry
    raise KeyError(name)


def oracle() -> list[dict]:
    """Run the proven JavaScript once per test session."""

    if "payload" not in _ORACLE_CACHE:
        result = subprocess.run(
            [NODE, str(HARNESS), str(FIXTURES)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
        if result.returncode != 0:
            raise AssertionError(f"the parity harness failed: {result.stderr[:400]}")
        _ORACLE_CACHE["payload"] = json.loads(result.stdout)
    return _ORACLE_CACHE["payload"]


def oracle_for(name: str) -> dict:
    for entry in oracle():
        if entry["name"] == name:
            return entry
    raise KeyError(name)


def python_result(fixture: dict) -> dict:
    context = fixture["context"]
    return {
        "name": fixture["name"],
        "normalize": legal.normalize_legal_text(context.get("operative_text", "")),
        "references": legal.parse_legal_references(context.get("operative_text", "")),
        "references_v2": legal.parse_legal_references_v2(context.get("operative_text", "")),
        "profile": legal.build_retirement_legal_profile(
            operative_text=context.get("operative_text", ""), cargo=context.get("cargo", "")
        ),
        "signatures": [
            legal.build_catalog_option_signature(option, index)
            for index, option in enumerate(fixture.get("options") or [])
        ],
        "decision": legal.resolve_legal_foundation(context, fixture.get("options") or []),
    }


def compare(test: unittest.TestCase, left: object, right: object, path: str = "") -> None:
    """Deep comparison where JavaScript ``undefined`` equals Python ``None``."""

    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            left_value = left.get(key)
            right_value = right.get(key)
            if left_value is None and right_value is None:
                continue
            test.assertIn(
                key,
                left,
                f"{path}.{key} is missing from the JavaScript result",
            )
            compare(test, left_value, right_value, f"{path}.{key}")
        return
    if isinstance(left, list) and isinstance(right, list):
        test.assertEqual(len(left), len(right), f"{path} length differs")
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            compare(test, left_item, right_item, f"{path}[{index}]")
        return
    if isinstance(left, float) or isinstance(right, float):
        test.assertTrue(
            isinstance(left, (int, float)) and isinstance(right, (int, float)),
            f"{path}: {left!r} vs {right!r}",
        )
        test.assertTrue(
            math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12),
            f"{path}: {left!r} != {right!r}",
        )
        return
    test.assertEqual(left, right, path)


class NormalizerParityTests(unittest.TestCase):
    def test_normalization_matches_the_proven_implementation(self):
        for fixture in cases():
            with self.subTest(fixture=fixture["name"]):
                expected = oracle_for(fixture["name"])["normalize"]
                actual = legal.normalize_legal_text(fixture["context"].get("operative_text", ""))
                self.assertEqual(actual, expected)

    def test_the_normalizer_is_pure_and_never_returns_display_text(self):
        self.assertEqual(legal.normalize_legal_text(""), "")
        self.assertEqual(legal.normalize_legal_text(None), "")
        self.assertNotIn("º", legal.normalize_legal_text("Art. 6º"))


class ReferenceParserTests(unittest.TestCase):
    def test_the_v1_parser_matches_the_proven_implementation(self):
        for fixture in cases():
            with self.subTest(fixture=fixture["name"]):
                expected = oracle_for(fixture["name"])["references"]
                actual = legal.parse_legal_references(fixture["context"].get("operative_text", ""))
                compare(self, expected, actual, f"references[{fixture['name']}]")

    def test_the_v2_parser_matches_the_proven_implementation(self):
        for fixture in cases():
            with self.subTest(fixture=fixture["name"]):
                expected = oracle_for(fixture["name"])["references_v2"]
                actual = legal.parse_legal_references_v2(
                    fixture["context"].get("operative_text", "")
                )
                compare(self, expected, actual, f"references_v2[{fixture['name']}]")

    def test_an_empty_source_yields_no_references(self):
        self.assertEqual(legal.parse_legal_references("   "), [])
        self.assertEqual(legal.parse_legal_references_v2(None), [])


class ProfileAndSignatureParityTests(unittest.TestCase):
    def test_the_retirement_profile_matches_the_proven_implementation(self):
        for fixture in cases():
            with self.subTest(fixture=fixture["name"]):
                expected = oracle_for(fixture["name"])["profile"]
                actual = legal.build_retirement_legal_profile(
                    operative_text=fixture["context"].get("operative_text", ""),
                    cargo=fixture["context"].get("cargo", ""),
                )
                compare(self, expected, actual, f"profile[{fixture['name']}]")

    def test_catalog_option_signatures_match_the_proven_implementation(self):
        for fixture in cases():
            with self.subTest(fixture=fixture["name"]):
                expected = oracle_for(fixture["name"])["signatures"]
                actual = [
                    legal.build_catalog_option_signature(option, index)
                    for index, option in enumerate(fixture.get("options") or [])
                ]
                compare(self, expected, actual, f"signatures[{fixture['name']}]")


@unittest.skipIf(NODE is None, "node is not available for the parity oracle")
class FoundationParityTests(unittest.TestCase):
    def test_every_fixture_decision_matches_the_proven_javascript(self):
        for fixture in cases():
            with self.subTest(fixture=fixture["name"]):
                expected = oracle_for(fixture["name"])["decision"]
                actual = legal.resolve_legal_foundation(
                    fixture["context"], fixture.get("options") or []
                )
                compare(self, expected, actual, f"decision[{fixture['name']}]")

    def test_the_full_python_result_matches_the_oracle_document(self):
        for fixture, expected in zip(cases(), oracle()):
            with self.subTest(fixture=fixture["name"]):
                compare(self, expected, python_result(fixture), f"result[{fixture['name']}]")


class FoundationBehaviourTests(unittest.TestCase):
    def decide(self, name: str) -> dict:
        fixture = case(name)
        return legal.resolve_legal_foundation(fixture["context"], fixture.get("options") or [])

    def test_an_exact_structural_ec41_pair_is_an_automatic_selection(self):
        decision = self.decide("ec41_without_p5")

        self.assertEqual(decision["status"], "selected")
        self.assertTrue(decision["automatic"])
        self.assertEqual(decision["decision_state"], "AUTO_SELECTED")
        self.assertEqual(decision["confidence"], 1)
        self.assertEqual(decision["margin"], 1)
        self.assertEqual(decision["rules_version"], "legal-foundation-v3")
        self.assertEqual(decision["option_value"], "A")
        self.assertEqual(len(decision["citations"]), 1)

    def test_the_public_rule_id_is_only_reported_for_mapped_classes(self):
        # The engine exposes rule_id only for the public rule families; the
        # EC41 pair is selected through EC41_TRANSITION_GENERAL, which is not
        # one of them, so rule_id stays empty even on an automatic decision.
        self.assertIsNone(self.decide("ec41_without_p5")["rule_id"])
        self.assertEqual(self.decide("ec47_art3")["rule_id"], "EC47_ART3")

    def test_a_reference_without_year_blocks_the_decision(self):
        decision = self.decide("incomplete_reference")

        self.assertEqual(decision["status"], "pending")
        self.assertEqual(decision["reasons"], ["reference-incomplete"])
        self.assertFalse(decision["automatic"])

    def test_contradictory_years_for_the_same_diploma_block_the_decision(self):
        self.assertEqual(self.decide("contradictory_reference")["reasons"], ["contradictory-reference"])

    def test_an_operative_text_without_references_blocks_the_decision(self):
        self.assertEqual(self.decide("no_references")["reasons"], ["no-legal-references"])

    def test_an_incomplete_context_blocks_the_decision(self):
        self.assertEqual(self.decide("context_incomplete")["reasons"], ["context-incomplete"])

    def test_a_federal_and_state_constitution_conflict_blocks_the_decision(self):
        decision = self.decide("constitution_family_conflict")

        self.assertEqual(decision["decision_state"], "DOCUMENT_CONFLICT")
        self.assertEqual(decision["status"], "pending")

    def test_a_catalog_option_without_structural_evidence_stays_in_review(self):
        decision = self.decide("unrecognised_catalog_option")

        self.assertEqual(decision["status"], "pending")
        self.assertEqual(decision["decision_state"], "REVIEW_REQUIRED")
        self.assertFalse(decision["automatic"])

    def test_a_military_profile_rejects_a_civil_catalog_option(self):
        decision = self.decide("military_scope")

        self.assertEqual(decision["status"], "pending")
        self.assertEqual(decision["reasons"][0], "no-compatible-candidate")

    def test_no_catalog_option_is_reported_as_a_missing_class(self):
        decision = self.decide("empty_options")

        self.assertIn("CATALOG_CLASS_MISSING", decision["reasons"])
        self.assertFalse(decision["automatic"])

    def test_the_operative_text_is_read_after_the_last_resolve_marker(self):
        self.assertEqual(self.decide("operative_text_after_resolve_marker")["rule_id"], "EC47_ART3")

    def test_the_shared_guard_refuses_a_decision_the_engine_would_not_write(self):
        selected = self.decide("ec41_without_p5")
        self.assertTrue(legal.is_automatic_legal_decision(selected))

        weak = dict(selected, confidence=0.8)
        self.assertFalse(legal.is_automatic_legal_decision(weak))

        conflicting = dict(selected, hard_conflict=True)
        self.assertFalse(legal.is_automatic_legal_decision(conflicting))

        wrong_version = dict(selected, rules_version="legal-foundation-v2")
        self.assertFalse(legal.is_automatic_legal_decision(wrong_version))

        no_confidence = {key: value for key, value in selected.items() if key != "confidence"}
        self.assertFalse(legal.is_automatic_legal_decision(no_confidence))

    def test_the_rules_version_is_pinned(self):
        self.assertEqual(legal.RULES_VERSION, "legal-foundation-v3")
        self.assertEqual(self.decide("ec47_art3")["rules_version"], legal.RULES_VERSION)


class PlanFixtureDivergenceTests(unittest.TestCase):
    """Record where the plan's illustrative fixture disagrees with the engine."""

    def test_the_plan_example_expects_a_rule_id_the_engine_does_not_publish(self):
        fixture = case("ec41_without_p5")
        expected = fixture["expected"]
        decision = legal.resolve_legal_foundation(fixture["context"], fixture["options"])

        # The plan's fixture asks for rule_id EC41_SEM_P5; the proven engine
        # reports no public rule_id for this input. Parity with the shipped rule
        # wins, and the divergence is asserted here so it cannot be forgotten.
        self.assertEqual(decision["status"], expected["status"])
        self.assertEqual(decision["automatic"], expected["automatic"])
        self.assertEqual(expected["rule_id"], "EC41_SEM_P5")
        self.assertIsNone(decision["rule_id"])


if __name__ == "__main__":
    unittest.main()
