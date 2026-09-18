"""Cross-language parity between the browser scanner and the Python backend.

The natural key of a logical process is ``(process_key, interested_normalized)``.
The extension computes it in JavaScript and the Mesa computes it in Python; if
the two drifts, the same act appears twice or is never matched. These tests run
the real JavaScript module through Node and compare it with
``app/core/identity.py``.
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from app.core.identity import is_normalized_interested, normalize_interested

REPO_ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")

NAMES = (
    "FERNANDO DE PAIVA FERREIRA",
    "  JOSÉ   D'ÁVILA Conceição ",
    "ANDRÉ LUÍS DA SILVA",
    "maria  das  dores",
    "Ângela MÜLLER",
    "Antônio de Sá",
    "Conceição  DOS  SANTOS",
)


@unittest.skipIf(NODE is None, "node is not available")
class InterestedNormalizationParityTests(unittest.TestCase):
    def run_node(self, source: str) -> str:
        result = subprocess.run(
            [NODE, "--input-type=module", "-e", source],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_browser_and_backend_normalize_identically(self):
        script = (
            "await import('./extension/lib/area-snapshot.js');"
            f"const names = {json.dumps(list(NAMES))};"
            "console.log(JSON.stringify(names.map((name) => globalThis.TCEAreaSnapshot.normalizeInterested(name))));"
        )

        from_browser = json.loads(self.run_node(script))
        from_backend = [normalize_interested(name) for name in NAMES]

        self.assertEqual(from_browser, from_backend)
        for value in from_browser:
            self.assertTrue(is_normalized_interested(value))

    def test_python_normalization_is_idempotent(self):
        for name in NAMES:
            with self.subTest(name=name):
                once = normalize_interested(name)
                self.assertEqual(normalize_interested(once), once)

    def test_the_scanner_module_exposes_the_expected_surface(self):
        script = (
            "await import('./extension/lib/area-snapshot.js');"
            "const api = globalThis.TCEAreaSnapshot;"
            "console.log(JSON.stringify({"
            "scan: typeof api.scan,"
            "normalizeInterested: typeof api.normalizeInterested,"
            "roles: api.PORTAL_ROLES,"
            "classifications: api.AREA_CLASSIFICATIONS,"
            "}));"
        )

        payload = json.loads(self.run_node(script))

        self.assertEqual(payload["scan"], "function")
        self.assertEqual(payload["normalizeInterested"], "function")
        self.assertIn("list", payload["roles"])
        self.assertEqual(
            set(payload["classifications"]),
            {
                "PRECISA_COMPLEMENTAR",
                "ATO_COMPLEMENTADO",
                "NAO_ENCONTRADO_AREA_RESTRITA",
                "AMBIGUO",
                "BLOQUEADO",
            },
        )


if __name__ == "__main__":
    unittest.main()
