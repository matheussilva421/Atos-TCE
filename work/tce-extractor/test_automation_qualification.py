from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).parent / "portable" / "app"))

from qualification import (
    QUALIFICATION_SCHEMA_VERSION,
    expected_qualification_versions,
    inspect_qualification,
)


class AutomationQualificationTests(unittest.TestCase):
    def valid_payload(self) -> dict:
        return {
            "schema_version": QUALIFICATION_SCHEMA_VERSION,
            "status": "qualified",
            "versions": expected_qualification_versions("1.1.0"),
            "fixture_hashes": ["a" * 64],
            "real_event_id": "real-event-2026-09-09",
        }

    def write_payload(self, root: Path, payload: dict) -> Path:
        path = root / "automacao" / "qualificacao.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_accepts_a_versioned_qualification_only_when_all_proofs_match(self):
        with TemporaryDirectory() as temporary:
            path = self.write_payload(Path(temporary), self.valid_payload())
            result = inspect_qualification(path, expected_qualification_versions("1.1.0"))
            self.assertEqual(result.valid, True)
            self.assertEqual(result.reason, "qualified")

    def test_rejects_stale_versions_and_missing_real_event(self):
        with TemporaryDirectory() as temporary:
            payload = self.valid_payload()
            payload["versions"]["extension"] = "1.0.0"
            payload["real_event_id"] = ""
            path = self.write_payload(Path(temporary), payload)
            result = inspect_qualification(path, expected_qualification_versions("1.1.0"))
            self.assertEqual(result.valid, False)
            self.assertEqual(result.reason, "version_mismatch")

    def test_missing_or_unqualified_file_fails_closed(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = inspect_qualification(
                root / "automacao" / "qualificacao.json",
                expected_qualification_versions("1.1.0"),
            )
            self.assertEqual(result.valid, False)
            self.assertEqual(result.reason, "missing")

            payload = self.valid_payload()
            payload["status"] = "pending"
            path = self.write_payload(root, payload)
            result = inspect_qualification(path, expected_qualification_versions("1.1.0"))
            self.assertEqual(result.valid, False)
            self.assertEqual(result.reason, "status_not_qualified")


if __name__ == "__main__":
    unittest.main()
