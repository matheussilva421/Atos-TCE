"""Dependency boundary: no supported runtime may point at the legacy tree.

M6 Task 1 promotes the engines the adapters still need, so no supported runtime
path may name the legacy portable tree. This is a blunt, fail-closed scan on
purpose: naming it under ``app/`` means a runtime dependency, and provenance is
described without the literal path. M6 Task 5 adds ``packaging/`` and
``START.cmd`` to the same boundary.

``scripts/`` is deliberately outside the scan: audit, cleanup and retirement
tools have to name the legacy tree, because retiring it is their job.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP = REPO_ROOT / "app"
RUNTIME_ROOTS = ("app", "extension", "packaging")
RUNTIME_FILES = ("START.cmd",)
SCANNED_SUFFIXES = {".py", ".ps1", ".psm1", ".js"}
FORBIDDEN_MARKERS = ("work/tce-extractor", "work\\tce-extractor")
# A composed path (``root / "work" / "tce-extractor" / ...``) hides from the
# literal markers above, so the runtime roots are also scanned for the segment
# itself. Nothing in app/, extension/, packaging/ or START.cmd has a legitimate
# reason to name the legacy extractor.
FORBIDDEN_SEGMENTS = ("tce-extractor",)


def runtime_files() -> list:
    """Every file of the supported runtime surface: app, extension, packaging, launcher."""

    found = []
    for root_name in RUNTIME_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            if "node_modules" in path.parts or "__pycache__" in path.parts:
                continue
            found.append(path)
    for name in RUNTIME_FILES:
        candidate = REPO_ROOT / name
        if candidate.is_file():
            found.append(candidate)
    return found


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

    def test_supported_runtime_has_no_legacy_path(self):
        offenders = []
        for path in runtime_files():
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            if any(marker in text for marker in FORBIDDEN_MARKERS):
                offenders.append(str(path.relative_to(REPO_ROOT)))

        self.assertEqual(offenders, [])

    def test_supported_runtime_never_names_the_legacy_segment(self):
        offenders = []
        for path in runtime_files():
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            if any(segment in text for segment in FORBIDDEN_SEGMENTS):
                offenders.append(str(path.relative_to(REPO_ROOT)))

        self.assertEqual(offenders, [])

    def test_start_cmd_is_the_single_normal_launcher(self):
        text = (REPO_ROOT / "START.cmd").read_text(encoding="utf-8-sig", errors="ignore")

        self.assertIn("app.main", text)
        self.assertIn("runtime\\python\\python.exe", text)
        self.assertNotIn("INICIAR", text)

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
