import json
import tempfile
import unittest
from pathlib import Path

from process_collections import write_process_collections


class ProcessCollectionsTests(unittest.TestCase):
    def test_builds_named_views_in_each_source_order_and_preserves_overlap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            order = root / "ordem-portal.json"
            preview = root / "preview.json"
            output = root / "colecoes-processos.json"
            order.write_text(
                json.dumps({"schema_version": 1, "process_keys": ["2/2026", "1/2026"]}),
                encoding="utf-8",
            )
            preview.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "pending_processes": [
                            {"process_key": "1/2026", "interested": ["Ana", "Bia"]},
                            {"process_key": "3/2026", "interested": ["Caio"]},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = write_process_collections(order, preview, output)

            self.assertEqual("sector_finalistic", payload["default_collection"])
            self.assertEqual(
                ["2/2026", "1/2026"], payload["collections"][0]["process_keys"]
            )
            self.assertEqual(
                ["1/2026", "3/2026"], payload["collections"][1]["process_keys"]
            )
            self.assertEqual(
                {"1/2026": ["Ana", "Bia"], "3/2026": ["Caio"]},
                payload["collections"][1]["interested_by_process"],
            )
            self.assertEqual(payload, json.loads(output.read_text(encoding="utf-8")))

    def test_rejects_duplicate_keys_inside_a_view(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            order = root / "ordem-portal.json"
            preview = root / "preview.json"
            order.write_text(json.dumps({"process_keys": ["1/2026", "1/2026"]}))
            preview.write_text(json.dumps({"pending_processes": [{"process_key": "1/2026"}]}))

            with self.assertRaisesRegex(ValueError, "duplicad"):
                write_process_collections(order, preview, root / "out.json")


if __name__ == "__main__":
    unittest.main()
