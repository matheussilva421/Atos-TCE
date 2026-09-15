from __future__ import annotations

import unittest

from portable.app.materialize_area_analysis import materialize_analysis


class MaterializeAreaAnalysisTests(unittest.TestCase):
    def test_rebuilds_full_v3_queue_in_input_order_and_keeps_duplicates_in_provenance(self):
        input_manifest = {
            "input_list_id": "input-" + "a" * 24,
            "input_sha256": "b" * 64,
            "unique_count": 2,
            "rows": [
                {"source_row": 2, "process_key": "101/2024", "duplicate_of_row": None},
                {"source_row": 3, "process_key": "202/2024", "duplicate_of_row": None},
                {"source_row": 4, "process_key": "101/2024", "duplicate_of_row": 2},
            ],
        }
        area_snapshot = {
            "source_scope": "sector_finalistic",
            "marker": {"label": "PROFESSOR - IPERN", "value": "5159"},
            "rows": [
                {
                    "process_key": "101/2024",
                    "interested_key": "MARIA",
                    "area_classification": "PRECISA_COMPLEMENTAR",
                    "action_observed": "Complementar Ato",
                    "action_signature": {"kind": "red_complement_icon", "alt": "Complementar Ato", "title": "Complementar Ato", "src": "../../images/atov.png"},
                    "area_page": 1,
                },
                {
                    "process_key": "202/2024",
                    "interested_key": "JOAO",
                    "area_classification": "ATO_COMPLEMENTADO",
                    "action_observed": "Ato Complementado",
                    "action_signature": None,
                    "area_page": 1,
                },
            ],
        }

        result = materialize_analysis(input_manifest, area_snapshot, lot_size=1, observed_at="2026-09-14T00:00:00Z")

        self.assertEqual(result["schema_version"], 3)
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual([item["process_key"] for item in result["queue"]], ["101/2024"])
        self.assertEqual(result["lots"][0]["items"][0]["input_row"], 2)
        self.assertEqual(result["rows"][0]["input_row"], 2)
        self.assertEqual(result["preview"]["needs_complement"], 1)

    def test_keeps_distinct_interested_identities_for_one_process_and_blocks_absent_processes(self):
        input_manifest = {
            "input_list_id": "input-" + "c" * 24,
            "input_sha256": "d" * 64,
            "unique_count": 2,
            "rows": [
                {"source_row": 2, "process_key": "101/2024", "duplicate_of_row": None},
                {"source_row": 3, "process_key": "202/2024", "duplicate_of_row": None},
            ],
        }
        pending = {
            "area_classification": "PRECISA_COMPLEMENTAR",
            "action_observed": "Complementar Ato",
            "action_signature": {
                "kind": "red_complement_icon",
                "alt": "Complementar Ato",
                "title": "Complementar Ato",
                "src": "red.png",
            },
            "area_page": 1,
        }
        area_snapshot = {
            "source_scope": "my_processes",
            "marker": {"label": "PROFESSOR - IPERN", "value": "5159"},
            "rows": [
                {"process_key": "101/2024", "interested_key": "MARIA", **pending},
                {"process_key": "101/2024", "interested_key": "JOAO", **pending},
            ],
        }

        result = materialize_analysis(input_manifest, area_snapshot, lot_size=1, observed_at="2026-09-14T00:00:00Z")

        self.assertEqual(result["spec"]["source_scope"], "my_processes")
        self.assertEqual([(row["process_key"], row["interested_key"]) for row in result["rows"]], [
            ("101/2024", "MARIA"),
            ("101/2024", "JOAO"),
            ("202/2024", None),
        ])
        self.assertEqual(len(result["queue"]), 2)
        self.assertEqual(len(result["blocked"]), 1)
        self.assertIsNone(result["blocked"][0]["interested_key"])
        self.assertEqual(result["blocked"][0]["state"], "blocked")

    def test_rejects_duplicate_same_process_and_interested_identity(self):
        input_manifest = {
            "input_list_id": "input-" + "e" * 24,
            "input_sha256": "f" * 64,
            "unique_count": 1,
            "rows": [{"source_row": 2, "process_key": "101/2024", "duplicate_of_row": None}],
        }
        row = {
            "process_key": "101/2024",
            "interested_key": "MARIA",
            "area_classification": "ATO_COMPLEMENTADO",
            "action_observed": "Ato Complementado",
            "action_signature": None,
            "area_page": 1,
        }
        with self.assertRaisesRegex(ValueError, "duplicad"):
            materialize_analysis(
                input_manifest,
                {
                    "source_scope": "sector_finalistic",
                    "marker": {"label": "M", "value": "1"},
                    "rows": [row, dict(row)],
                },
            )


if __name__ == "__main__":
    unittest.main()
