"""Tests for the v4 legal policy and the unchanged parts of the historical v3 oracle.

The JavaScript oracle remains authoritative for parsing, normalization, profile
and catalog-signature parity. Final best-available selection is intentionally
owned by the Python v4 contract tests below.
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
    def test_the_parity_oracle_lives_inside_the_repository(self):
        """M6 Task 8 prep: the oracle must survive the legacy retirement."""

        source = HARNESS.read_text(encoding="utf-8")
        self.assertNotIn("tce-extractor", source)
        self.assertIn("oracles", source)
        oracle = REPO_ROOT / "tests" / "oracles" / "legal"
        direct = (
            "legal-foundation.js",
            "normalizer.js",
            "legal-reference-parser-v2.js",
            "retirement-legal-profile.js",
            "catalog-option-signature.js",
        )
        # Loaded transitively by the oracle modules above.
        transitive = (
            "portal-legal-crosswalk.js",
            "automation-preflight.js",
        )
        for name in direct + transitive:
            with self.subTest(name=name):
                self.assertTrue((oracle / name).is_file())
        for name in direct:
            with self.subTest(loaded=name):
                self.assertIn(name, source)
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
    def test_the_javascript_decisions_remain_the_historical_v3_oracle(self):
        for expected in oracle():
            with self.subTest(fixture=expected["name"]):
                self.assertEqual(expected["decision"]["rules_version"], "legal-foundation-v3")

    def test_unchanged_python_outputs_match_the_historical_v3_oracle(self):
        unchanged_outputs = ("normalize", "references", "references_v2", "profile", "signatures")
        for fixture, expected in zip(cases(), oracle()):
            with self.subTest(fixture=fixture["name"]):
                actual = python_result(fixture)
                for key in unchanged_outputs:
                    compare(self, expected[key], actual[key], f"{key}[{fixture['name']}]")


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
        self.assertEqual(decision["rules_version"], "legal-foundation-v4")
        self.assertEqual(decision["option_value"], "A")
        self.assertEqual(len(decision["citations"]), 1)

    def test_the_public_rule_id_is_only_reported_for_mapped_classes(self):
        # The engine exposes rule_id only for the public rule families; the
        # EC41 pair is selected through EC41_TRANSITION_GENERAL, which is not
        # one of them, so rule_id stays empty even on an automatic decision.
        self.assertIsNone(self.decide("ec41_without_p5")["rule_id"])
        self.assertEqual(self.decide("ec47_art3")["rule_id"], "EC47_ART3")

    def test_a_reference_without_year_is_a_warning_when_a_real_option_exists(self):
        decision = self.decide("incomplete_reference")

        self.assertEqual(decision["status"], "selected")
        self.assertTrue(decision["automatic"])
        self.assertEqual(decision["option_value"], "A")
        self.assertIn("reference-incomplete", decision["warnings"])

    def test_contradictory_references_are_a_warning_when_a_real_option_exists(self):
        decision = self.decide("contradictory_reference")

        self.assertEqual(decision["status"], "selected")
        self.assertIn("contradictory-reference", decision["warnings"])

    def test_operative_text_without_parseable_references_still_ranks_the_catalog(self):
        decision = self.decide("no_references")

        self.assertEqual(decision["status"], "selected")
        self.assertIn("no-legal-references", decision["warnings"])

    def test_incomplete_reference_status_does_not_veto_usable_documentary_text(self):
        decision = self.decide("context_incomplete")

        self.assertEqual(decision["status"], "selected")
        self.assertIn("context-incomplete", decision["warnings"])

    def test_a_federal_and_state_constitution_conflict_is_diagnostic(self):
        decision = self.decide("constitution_family_conflict")

        self.assertEqual(decision["decision_state"], "AUTO_SELECTED")
        self.assertEqual(decision["status"], "selected")
        self.assertIn("family-conflict", decision["warnings"])

    def test_a_catalog_option_without_structural_evidence_is_still_selected(self):
        decision = self.decide("unrecognised_catalog_option")

        self.assertEqual(decision["status"], "selected")
        self.assertTrue(decision["automatic"])
        self.assertTrue(decision["class_id"].startswith("CATALOG_OPTION_"))
        self.assertIn("unknown-catalog-class", decision["warnings"])

    def test_a_military_profile_hard_conflict_does_not_veto_a_real_option(self):
        decision = self.decide("military_scope")

        self.assertEqual(decision["status"], "selected")
        self.assertTrue(decision["hard_conflict"])
        self.assertIn("hard-conflict-best-available", decision["warnings"])

    def test_no_selectable_catalog_option_is_reported_without_inventing_a_value(self):
        decision = self.decide("empty_options")

        self.assertIsNone(decision["option_value"])
        self.assertIn("LEGAL_OPTIONS_EMPTY", decision["warnings"])
        self.assertFalse(decision["automatic"])

    def test_low_confidence_hard_conflict_still_selects_a_catalog_member(self):
        fixture = case("v4_all_hard_conflict")
        decision = self.decide("v4_all_hard_conflict")
        selectable_values = {
            option["value"] for option in legal.selectable_legal_options(fixture["options"])
        }

        self.assertEqual(decision["status"], "selected")
        self.assertTrue(decision["hard_conflict"])
        self.assertLess(decision["confidence"], 0.90)
        self.assertIn("hard-conflict-best-available", decision["warnings"])
        self.assertIn(decision["option_value"], selectable_values)

    def test_unknown_class_and_true_tie_choose_the_first_option_deterministically(self):
        decision = self.decide("v4_true_tie_unknown_catalog")
        repeated = self.decide("v4_true_tie_unknown_catalog")

        self.assertEqual(decision["status"], "selected")
        self.assertTrue(decision["class_id"].startswith("CATALOG_OPTION_"))
        self.assertEqual(decision["option_value"], "A")
        self.assertEqual(decision["option_value"], repeated["option_value"])
        self.assertEqual(decision["margin"], 0)
        self.assertTrue(decision["tie_break_used"])
        self.assertIn("equivalent-candidates", decision["warnings"])
        self.assertIn("tie-broken-by-option-index", decision["warnings"])

    def test_placeholder_is_ignored_when_a_real_option_is_available(self):
        fixture = case("v4_placeholder_plus_real_option")
        decision = self.decide("v4_placeholder_plus_real_option")
        selectable_values = {
            option["value"]
            for option in legal.selectable_legal_options(fixture["options"])
        }

        self.assertEqual(decision["option_value"], "EC41")
        self.assertIn(decision["option_value"], selectable_values)
        self.assertEqual(len(selectable_values), 1)

    def test_placeholder_only_catalog_does_not_produce_a_selection(self):
        decision = self.decide("v4_only_placeholder")

        self.assertEqual(decision["status"], "pending")
        self.assertIsNone(decision["option_value"])
        self.assertIn("LEGAL_OPTIONS_EMPTY", decision["warnings"])

    def test_missing_documentary_text_does_not_invent_a_legal_choice(self):
        decision = legal.resolve_legal_foundation(
            {"resolution_status": "complete", "operative_text": ""},
            [{"value": "A", "label": "Art. 6º da Emenda Constitucional 41/2003"}],
        )

        self.assertEqual(decision["status"], "pending")
        self.assertIsNone(decision["option_value"])
        self.assertIn("missing-source", decision["warnings"])

    def test_the_operative_text_is_read_after_the_last_resolve_marker(self):
        self.assertEqual(self.decide("operative_text_after_resolve_marker")["rule_id"], "EC47_ART3")

    def test_the_shared_guard_refuses_a_decision_the_engine_would_not_write(self):
        selected = self.decide("ec41_without_p5")
        self.assertTrue(legal.is_automatic_legal_decision(selected))

        weak = dict(selected, confidence=0.1, margin=0)
        self.assertTrue(legal.is_automatic_legal_decision(weak))

        conflicting = dict(selected, hard_conflict=True)
        self.assertTrue(legal.is_automatic_legal_decision(conflicting))

        wrong_version = dict(selected, rules_version="legal-foundation-v2")
        self.assertFalse(legal.is_automatic_legal_decision(wrong_version))

        no_method = dict(selected, method="none")
        self.assertFalse(legal.is_automatic_legal_decision(no_method))

        no_value = dict(selected, option_value="")
        self.assertFalse(legal.is_automatic_legal_decision(no_value))

        no_confidence = {key: value for key, value in selected.items() if key != "confidence"}
        no_confidence.pop("margin", None)
        self.assertTrue(legal.is_automatic_legal_decision(no_confidence))

    def test_the_rules_version_is_pinned(self):
        self.assertEqual(legal.RULES_VERSION, "legal-foundation-v4")
        self.assertEqual(self.decide("ec47_art3")["rules_version"], legal.RULES_VERSION)


class SelectableLegalCatalogTests(unittest.TestCase):
    def test_selectable_catalog_drops_placeholders_and_empty_options(self):
        options = [
            {"value": "", "label": "Selecione o Fundamento Legal"},
            {"value": "", "label": "EC 41/2003"},
            {"value": " ", "label": "EC 47/2005"},
            {"value": "CF40", "label": ""},
            {"value": "PLACEHOLDER", "label": "Selecionar uma opção"},
            {"value": " 47 ", "label": "Emenda Constitucional 47/2005"},
        ]

        self.assertEqual(
            legal.selectable_legal_options(options),
            [
                {
                    "value": " 47 ",
                    "label": "Emenda Constitucional 47/2005",
                    "index": 5,
                }
            ],
        )

    def test_selectable_catalog_never_substitutes_label_for_an_empty_value(self):
        options = [{"value": "", "label": "Emenda Constitucional 41/2003"}]

        self.assertEqual(legal.selectable_legal_options(options), [])

    def test_selectable_catalog_preserves_option_index_and_raw_value(self):
        options = [
            {"value": "", "label": "Selecione..."},
            {"value": " EC41 ", "label": "Emenda Constitucional 41/2003"},
        ]

        self.assertEqual(
            legal.selectable_legal_options(options),
            [
                {
                    "value": " EC41 ",
                    "label": "Emenda Constitucional 41/2003",
                    "index": 1,
                }
            ],
        )


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
