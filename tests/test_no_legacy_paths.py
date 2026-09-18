"""Dependency boundary: the root application must not point at the legacy tree.

M6 Task 1 promotes the engines the adapters still need, so no supported runtime
path may name the legacy portable tree. This is a blunt, fail-closed scan on
purpose: naming it under ``app/`` means a runtime dependency, and provenance is
described without the literal path.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP = REPO_ROOT / "app"
SCANNED_SUFFIXES = {".py", ".ps1", ".psm1", ".js"}
FORBIDDEN_MARKERS = ("work/tce-extractor", "work\\tce-extractor")


class NoLegacyPathTests(unittest.TestCase):
    def test_root_app_has_no_operational_legacy_path(self):
        offenders = []
        for path in sorted(APP.rglob("*")):
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            if any(marker in text for marker in FORBIDDEN_MARKERS):
                offenders.append(str(path.relative_to(REPO_ROOT)))

        self.assertEqual(offenders, [])

    def test_root_app_has_no_legacy_sys_path_bootstrap(self):
        offenders = []
        for path in sorted(APP.rglob("*.py")):
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            if "sys.path.insert" in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))

        self.assertEqual(offenders, [])

    def test_the_promoted_engines_ship_inside_app(self):
        expected = (
            "app/econtas/runtime/Coletar-Processos-TCE.ps1",
            "app/econtas/runtime/TcePortal.Driver.js",
            "app/analysis/engine/incremental_pipeline.py",
            "app/analysis/engine/tce_extractor.py",
            "app/analysis/engine/batch_runner.py",
        )
        for relative in expected:
            with self.subTest(relative=relative):
                self.assertTrue((REPO_ROOT / relative).is_file())

    def test_the_promoted_analysis_engine_carries_no_presentation_code(self):
        engine = APP / "analysis" / "engine"

        names = {path.name for path in engine.glob("*.py")}
        self.assertNotIn("extension_exporter.py", names)
        self.assertNotIn("html_generator.py", names)
        for path in engine.glob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            with self.subTest(module=path.name):
                self.assertNotIn("extension_exporter", text)
                self.assertNotIn("html_generator", text)


if __name__ == "__main__":
    unittest.main()
