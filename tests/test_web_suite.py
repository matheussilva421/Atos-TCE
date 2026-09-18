"""Run the Mesa's browser-side tests from the root suite.

``app/web/tests/*.test.mjs`` guards the review screen (PDF viewer, evidence,
tab wiring). The legacy gate's web stage only covers the old web tree, so
without this the new suite would only run when somebody typed the command by
hand — which is how a broken tab wiring survived until a real browser check.
"""

import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_TESTS = REPO_ROOT / "app" / "web" / "tests"
NODE = shutil.which("node")


@unittest.skipIf(NODE is None, "node is not available for the web suite")
class WebSuiteTests(unittest.TestCase):
    def test_the_web_suite_passes(self):
        files = sorted(WEB_TESTS.glob("*.test.mjs"))
        self.assertTrue(files, f"no web tests found in {WEB_TESTS}")

        result = subprocess.run(
            [NODE, "--test", *[str(path) for path in files]],
            cwd=str(REPO_ROOT / "app" / "web"),
            capture_output=True,
            text=True,
            timeout=180,
        )

        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-500:])
        self.assertIn("fail 0", result.stdout)

    def test_the_tab_wiring_guard_is_part_of_the_suite(self):
        names = {path.name for path in WEB_TESTS.glob("*.test.mjs")}

        self.assertIn("ui-wiring.test.mjs", names)
        self.assertIn("pdf-viewer.test.mjs", names)


if __name__ == "__main__":
    unittest.main()
