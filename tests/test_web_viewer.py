"""Runs the Mesa PDF viewer contract through Node (M4 Task 5).

The viewer is browser code, so its behaviour is asserted by the same kind of
``node --test`` suite the proven legacy viewer uses; this test wires that suite
into the root Python test run.
"""

import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@unittest.skipIf(NODE is None, "node is not available")
class MesaPdfViewerTests(unittest.TestCase):
    def test_the_viewer_contract_is_green(self):
        result = subprocess.run(
            [NODE, "--test", "app/web/tests/pdf-viewer.test.mjs"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )

        self.assertEqual(result.returncode, 0, result.stdout[-1500:] + result.stderr[-500:])
        self.assertIn("pass ", result.stdout)

    def test_the_vendor_bundle_is_present_and_pinned(self):
        vendor = REPO_ROOT / "app" / "web" / "vendor" / "pdfjs"
        manifest = vendor / "manifest.json"

        self.assertTrue((vendor / "pdf.mjs").is_file())
        self.assertTrue((vendor / "pdf.worker.mjs").is_file())
        self.assertTrue((vendor / "LICENSE").is_file())
        self.assertTrue(manifest.is_file())

    def test_the_viewer_never_builds_a_filesystem_url(self):
        source = (REPO_ROOT / "app" / "web" / "pdf-viewer.js").read_text(encoding="utf-8")

        self.assertIn("/api/v1/documents/", source)
        self.assertNotIn("file://", source)
        self.assertNotIn("data/archive", source)


if __name__ == "__main__":
    unittest.main()
