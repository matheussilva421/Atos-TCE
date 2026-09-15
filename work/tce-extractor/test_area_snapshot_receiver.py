from __future__ import annotations

from pathlib import Path
import json
import unittest

from portable.app.area_snapshot_receiver import _validate_snapshot


ROOT = Path(__file__).parent


def snapshot(source_scope: str) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "source_scope": source_scope,
            "marker": {"label": "PROFESSOR - IPERN", "value": "5159"},
            "rows": [{"process_key": "101/2024"}],
        }
    ).encode("utf-8")


class AreaSnapshotReceiverTests(unittest.TestCase):
    def test_accepts_both_authoritative_source_scopes(self):
        for source_scope in ("sector_finalistic", "my_processes"):
            with self.subTest(source_scope=source_scope):
                self.assertEqual(_validate_snapshot(snapshot(source_scope))["source_scope"], source_scope)

    def test_rejects_an_unknown_source_scope(self):
        with self.assertRaisesRegex(ValueError, "estrutura de fotografia inválida"):
            _validate_snapshot(snapshot("unknown_scope"))

    def test_transfer_page_validates_the_same_two_source_scopes(self):
        page = (ROOT / "portable" / "app" / "area_snapshot_transfer.html").read_text(encoding="utf-8")
        self.assertIn("sector_finalistic", page)
        self.assertIn("my_processes", page)
        self.assertIn("Set", page)


if __name__ == "__main__":
    unittest.main()
