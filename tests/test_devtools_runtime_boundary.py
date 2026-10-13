"""Ensure supported product code never imports development-only browser tools."""

from pathlib import Path
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_ONLY_TOKENS = (
    "chrome-devtools-mcp",
    "playwright-cli",
    ".agents/skills/area-restrita",
    "devtools/area-restrita",
    "portal-reliability",
)
SOURCE_SUFFIXES = {".py", ".js", ".ps1", ".psm1", ".json"}


class RuntimeBoundaryTests(unittest.TestCase):
    def test_supported_runtime_does_not_depend_on_portal_lab(self):
        roots = [REPO_ROOT / "app", REPO_ROOT / "extension"]
        files = [path for root in roots for path in root.rglob("*")]
        files.append(REPO_ROOT / "START.cmd")
        offenders = []

        for path in files:
            if not path.is_file():
                continue
            if path.suffix.lower() not in SOURCE_SUFFIXES and path.name != "START.cmd":
                continue
            source = path.read_text(encoding="utf-8", errors="ignore").lower()
            if any(token in source for token in DEV_ONLY_TOKENS):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())

        self.assertEqual(offenders, [])

    def test_raw_capture_is_ignored_and_sanitized_lab_sources_are_trackable(self):
        def ignored(path):
            result = subprocess.run(
                ["git", "check-ignore", "--no-index", "-q", path],
                cwd=REPO_ROOT,
                check=False,
            )
            self.assertIn(result.returncode, (0, 1))
            return result.returncode == 0

        self.assertTrue(ignored("tmp/portal-lab/raw/capture.json"))
        self.assertTrue(ignored(".playwright-cli/state.json"))
        self.assertTrue(ignored(".agents/skills/playwright-cli/SKILL.md"))
        self.assertFalse(ignored("devtools/area-restrita/fixtures/list-page.json"))
        self.assertFalse(ignored(".agents/skills/area-restrita/SKILL.md"))
        self.assertFalse(ignored("scripts/portal-lab/capture-structure.js"))


    def test_reliability_reset_tooling_never_reaches_the_product_tree(self):
        roots = [REPO_ROOT / "app", REPO_ROOT / "extension"]
        offenders = []
        for root in roots:
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
                    continue
                source = path.read_text(encoding="utf-8", errors="ignore").lower()
                if any(
                    token in source
                    for token in ("scripts/portal-reliability", "devtools/area-restrita/controller")
                ):
                    offenders.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(offenders, [])

    def test_raw_reliability_captures_are_ignored_and_lab_sources_are_trackable(self):
        def ignored(path):
            result = subprocess.run(
                ["git", "check-ignore", "--no-index", "-q", path],
                cwd=REPO_ROOT,
                check=False,
            )
            self.assertIn(result.returncode, (0, 1))
            return result.returncode == 0

        self.assertTrue(ignored("tmp/portal-reliability/raw/events.jsonl"))
        self.assertTrue(ignored("tmp/portal-reliability/qualification.json"))
        self.assertFalse(ignored("scripts/portal-reliability/qualification.py"))
        self.assertFalse(ignored("scripts/portal-reliability/report.py"))
        self.assertFalse(ignored("devtools/area-restrita/controller/navigation.mjs"))



if __name__ == "__main__":
    unittest.main()
