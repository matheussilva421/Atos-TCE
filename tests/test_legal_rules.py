"""Parser/profile parity and v4 behavior tests for legal foundation.

The JavaScript decision output is retained as a historical v3 oracle. Final
selection policy is now owned by the Python v4 contract tests below.
"""

import json
import math
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

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
            if fixture["name"] in {"v4_placeholder_plus_real", "v4_only_placeholder"}:
                continue
            with self.subTest(fixture=fixture["name"]):
                expected = oracle_for(fixture["name"])["signatures"]
                actual = [
                    legal.build_catalog_option_signature(option, index)
                    for index, option in enumerate(fixture.get("options") or [])
                ]
                compare(self, expected, actual, f"signatures[{fixture['name']}]")


@unittest.skipIf(NODE is None, "node is not available for the parity oracle")
class FoundationParityTests(unittest.TestCase):
    def test_v3_final_decisions_remain_available_as_historical_oracle_records(self):
        for fixture in cases():
            with self.subTest(fixture=fixture["name"]):
                decision = oracle_for(fixture["name"])["decision"]
                self.assertIsInstance(decision, dict)
                self.assertEqual(decision.get("rules_version"), "legal-foundation-v3")

    def test_unchanged_python_primitives_match_the_v3_oracle_document(self):
        for fixture, expected in zip(cases(), oracle()):
            with self.subTest(fixture=fixture["name"]):
                historical = {key: value for key, value in expected.items() if key != "decision"}
                current = {
                    key: value
                    for key, value in python_result(fixture).items()
                    if key != "decision"
                }
                if fixture["name"] in {"v4_placeholder_plus_real", "v4_only_placeholder"}:
                    # These two v4 fixtures intentionally test raw empty DOM values;
                    # the historical JS signature adapter substitutes the label.
                    historical.pop("signatures", None)
                    current.pop("signatures", None)
                compare(self, historical, current, f"result[{fixture['name']}]")


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
        self.assertIsNone(self.decide("ec41_without_p5")["rule_id"])
        self.assertEqual(self.decide("ec47_art3")["rule_id"], "EC47_ART3")

    def test_incomplete_reference_is_a_warning_and_still_selects(self):
        decision = self.decide("incomplete_reference")
        self.assertEqual(decision["status"], "selected")
        self.assertIn("reference-incomplete", decision["warnings"])

    def test_contradictory_reference_is_a_warning_and_still_selects(self):
        decision = self.decide("contradictory_reference")
        self.assertEqual(decision["status"], "selected")
        self.assertIn("contradictory-reference", decision["warnings"])

    def test_text_without_parseable_references_is_a_warning_and_still_selects(self):
        decision = self.decide("no_references")
        self.assertEqual(decision["status"], "selected")
        self.assertIn("no-legal-references", decision["warnings"])

    def test_incomplete_context_with_documentary_text_is_a_warning(self):
        decision = self.decide("context_incomplete")
        self.assertEqual(decision["status"], "selected")
        self.assertIn("context-incomplete", decision["warnings"])

    def test_a_document_conflict_remains_diagnostic(self):
        decision = self.decide("constitution_family_conflict")
        self.assertEqual(decision["status"], "selected")
        self.assertIn("family-conflict", decision["warnings"])

    def test_an_unrecognised_catalog_class_is_selected_with_a_warning(self):
        decision = self.decide("unrecognised_catalog_option")
        self.assertEqual(decision["status"], "selected")
        self.assertTrue(str(decision["class_id"]).startswith("CATALOG_OPTION_"))
        self.assertIn("unknown-catalog-class", decision["warnings"])

    def test_a_hard_scope_conflict_is_selected_with_a_warning(self):
        decision = self.decide("military_scope")
        self.assertEqual(decision["status"], "selected")
        self.assertIn("hard-conflict", decision["warnings"])

    def test_empty_catalog_reports_no_selectable_options(self):
        decision = self.decide("empty_options")
        self.assertIsNone(decision["option_value"])
        self.assertIn("LEGAL_OPTIONS_EMPTY", decision["warnings"])

    def test_the_operative_text_is_read_after_the_last_resolve_marker(self):
        self.assertEqual(self.decide("operative_text_after_resolve_marker")["rule_id"], "EC47_ART3")

    def test_the_shared_guard_checks_integrity_not_confidence_or_conflict(self):
        selected = self.decide("ec41_without_p5")
        self.assertTrue(legal.is_automatic_legal_decision(selected))
        self.assertTrue(legal.is_automatic_legal_decision(dict(selected, confidence=0.8)))
        self.assertTrue(legal.is_automatic_legal_decision(dict(selected, hard_conflict=True)))
        self.assertTrue(
            legal.is_automatic_legal_decision(
                {key: value for key, value in selected.items() if key != "confidence"}
            )
        )
        self.assertFalse(legal.is_automatic_legal_decision(dict(selected, rules_version="legal-foundation-v2")))
        self.assertFalse(legal.is_automatic_legal_decision(dict(selected, method="none")))
        self.assertFalse(legal.is_automatic_legal_decision(dict(selected, option_value="")))

    def test_the_rules_version_is_pinned(self):
        self.assertEqual(legal.RULES_VERSION, "legal-foundation-v4")
        self.assertEqual(self.decide("ec47_art3")["rules_version"], legal.RULES_VERSION)


class V4BestAvailableTests(unittest.TestCase):
    SELECTABLE_CASES = (
        "ec47_art3",
        "incomplete_reference",
        "contradictory_reference",
        "no_references",
        "context_incomplete",
        "unrecognised_catalog_option",
        "military_scope",
        "v4_low_confidence",
        "v4_low_margin",
        "v4_true_tie",
        "v4_all_hard_conflicts",
        "v4_placeholder_plus_real",
    )

    def test_disabled_best_match_does_not_hide_an_enabled_catalog_option(self):
        decision = legal.resolve_legal_foundation(
            {
                "resolution_status": "complete",
                "operative_text": "RESOLVE: Art. 6º da Emenda Constitucional 41/2003",
            },
            [
                {
                    "value": "EC41",
                    "label": "Art. 6º da Emenda Constitucional 41/2003",
                    "disabled": True,
                },
                {
                    "value": "EC47",
                    "label": "Emenda Constitucional 47/2005",
                    "disabled": False,
                },
            ],
        )

        self.assertEqual(decision["status"], "selected")
        self.assertEqual(decision["option_value"], "EC47")

    def test_documentary_text_and_real_options_always_select_one_catalog_value(self):
        for name in self.SELECTABLE_CASES:
            with self.subTest(fixture=name):
                fixture = case(name)
                decision = legal.resolve_legal_foundation(
                    fixture["context"], fixture.get("options") or []
                )
                values = {
                    option["value"]
                    for option in legal.selectable_legal_options(fixture.get("options") or [])
                }

                self.assertEqual(decision["status"], "selected")
                self.assertTrue(decision["automatic"])
                self.assertTrue(decision["option_value"])
                self.assertIn(decision["option_value"], values)
                self.assertEqual(decision["rules_version"], "legal-foundation-v4")

    def test_only_placeholder_options_remain_empty_with_a_warning(self):
        fixture = case("v4_only_placeholder")
        decision = legal.resolve_legal_foundation(fixture["context"], fixture["options"])

        self.assertIsNone(decision.get("option_value"))
        self.assertIn("LEGAL_OPTIONS_EMPTY", decision.get("warnings", []) + decision.get("reasons", []))

    def test_low_confidence_low_margin_and_conflicts_are_diagnostics(self):
        for name, expected_warning in (
            ("v4_low_confidence", "low-confidence"),
            ("v4_low_margin", "low-margin"),
            ("v4_all_hard_conflicts", "hard-conflict"),
        ):
            with self.subTest(fixture=name):
                fixture = case(name)
                decision = legal.resolve_legal_foundation(fixture["context"], fixture["options"])
                self.assertEqual(decision["status"], "selected")
                if name == "v4_all_hard_conflicts":
                    self.assertTrue(decision["hard_conflict"])
                self.assertIn(expected_warning, decision["warnings"])

    def test_true_tie_selects_the_lowest_catalog_index_and_reports_it(self):
        fixture = case("v4_true_tie")
        decision = legal.resolve_legal_foundation(fixture["context"], fixture["options"])

        self.assertEqual(decision["option_value"], "first")
        self.assertTrue(decision.get("tie_break_used"))
        self.assertIn("equivalent-candidates", decision["warnings"])
        self.assertIn("tie-broken-by-option-index", decision["warnings"])

    def test_equal_scores_use_semantic_components_before_catalog_index(self):
        fixture = case("ec41_without_p5")
        ranked = {
            "early": {
                "class_id": "EC41_ART6",
                "scope": "personal",
                "option_value": "early",
                "option_label": "Early catalog option",
                "option_index": 0,
                "score": 0.8,
                "confidence": 0.8,
                "hard_conflict": False,
                "rejected": False,
                "reasons": [],
                "warnings": [],
                "method": "rule",
                "score_components": {
                    "structural": 0,
                    "crosswalk": 0,
                    "discriminators": 1,
                    "lexical": 1,
                },
                "candidate_references": [],
            },
            "semantic": {
                "class_id": "EC41_ART6",
                "scope": "personal",
                "option_value": "semantic",
                "option_label": "Later catalog option",
                "option_index": 1,
                "score": 0.8,
                "confidence": 0.8,
                "hard_conflict": False,
                "rejected": False,
                "reasons": [],
                "warnings": [],
                "method": "rule",
                "score_components": {
                    "structural": 1,
                    "crosswalk": 1,
                    "discriminators": 1,
                    "lexical": 0.5,
                },
                "candidate_references": [],
            },
        }

        with patch.object(legal, "_rank_one", side_effect=lambda _profile, _text, option: ranked[option["value"]]):
            decision = legal.classify_portal_legal_foundation(
                fixture["context"]["operative_text"],
                fixture["context"]["cargo"],
                [
                    {"value": "early", "label": "Early catalog option"},
                    {"value": "semantic", "label": "Later catalog option"},
                ],
            )

        self.assertEqual(decision["option_value"], "semantic")
        self.assertFalse(decision["tie_break_used"])
        self.assertNotIn("equivalent-candidates", decision["warnings"])


class SelectableLegalOptionsTests(unittest.TestCase):
    def test_selectable_catalog_drops_placeholder_and_empty_values(self):
        options = [
            {"value": "", "label": "Selecione o Fundamento Legal"},
            {"value": "41", "label": "EC 41/2003"},
        ]

        self.assertEqual(
            legal.selectable_legal_options(options),
            [{"value": "41", "label": "EC 41/2003", "index": 1}],
        )

    def test_selectable_catalog_never_replaces_empty_value_with_label(self):
        self.assertEqual(
            legal.selectable_legal_options([{"value": "", "label": "EC 41/2003"}]),
            [],
        )

    def test_selectable_catalog_preserves_the_dom_value_verbatim(self):
        self.assertEqual(
            legal.selectable_legal_options([{"value": " 41 ", "label": "EC 41/2003"}]),
            [{"value": " 41 ", "label": "EC 41/2003", "index": 0}],
        )

    def test_selectable_catalog_drops_disabled_options(self):
        options = [
            {"value": "41", "label": "EC 41/2003", "disabled": True},
            {"value": "47", "label": "EC 47/2005", "selectable": False},
        ]

        self.assertEqual(legal.selectable_legal_options(options), [])


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
