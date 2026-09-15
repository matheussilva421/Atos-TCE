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


if __name__ == "__main__":
    unittest.main()
