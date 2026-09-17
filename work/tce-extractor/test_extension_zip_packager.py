"""The extension-only ZIP must be reproducible from the checked-in source."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACKAGER = ROOT / "empacotar-extensao-complementar-ato.ps1"
EXPECTED = {
    "extensao-complementar-ato/manifest.json",
    "extensao-complementar-ato/background/service-worker.js",
    "extensao-complementar-ato/background/automation-controller.js",
    "extensao-complementar-ato/background/legal-context-resolver.js",
    "extensao-complementar-ato/content/form-detector.js",
    "extensao-complementar-ato/content/portal-navigation.js",
    "extensao-complementar-ato/content/portal-submit.js",
    "extensao-complementar-ato/lib/automation-preflight.js",
    "extensao-complementar-ato/lib/automation-schema.js",
    "extensao-complementar-ato/lib/bridge-client.js",
    "extensao-complementar-ato/lib/catalog-option-signature.js",
    "extensao-complementar-ato/lib/legal-foundation.js",
    "extensao-complementar-ato/lib/legal-reference-parser-v2.js",
    "extensao-complementar-ato/lib/retirement-legal-profile.js",
    "extensao-complementar-ato/lib/portal-legal-crosswalk.js",
    "extensao-complementar-ato/lib/matcher.js",
    "extensao-complementar-ato/lib/messages.js",
    "extensao-complementar-ato/lib/normalizer.js",
    "extensao-complementar-ato/lib/schema.js",
    "extensao-complementar-ato/sidepanel/panel.css",
    "extensao-complementar-ato/sidepanel/panel.html",
    "extensao-complementar-ato/sidepanel/panel.js",
    "extensao-complementar-ato/sidepanel/panel-tokens.css",
    "extensao-complementar-ato/sidepanel/panel-view.js",
}


class ExtensionZipPackagerTests(unittest.TestCase):
    def test_packaged_extension_has_a_complete_import_closure(self):
        """Every relative import inside the ZIP must resolve inside the ZIP."""
        import re

        with tempfile.TemporaryDirectory(prefix="tce-extension-closure-") as temp_dir:
            output = Path(temp_dir) / "extension-only.zip"
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(PACKAGER),
                    "-OutputPath",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)

            with zipfile.ZipFile(output) as archive:
                names = {name for name in archive.namelist() if name.endswith(".js")}
                self.assertIn("extensao-complementar-ato/background/service-worker.js", names)
                for name in sorted(names):
                    source = archive.read(name).decode("utf-8")
                    for target in re.findall(r"from\s+\"([^\"]+)\"", source):
                        if not target.startswith("."):
                            continue
                        resolved = (Path(name).parent / target).as_posix()
                        parts = []
                        for part in resolved.split("/"):
                            if part == ".":
                                continue
                            if part == "..":
                                parts.pop()
                                continue
                            parts.append(part)
                        self.assertIn(
                            "/".join(parts),
                            names,
                            f"{name} imports {target}, absent from the packaged ZIP",
                        )

    def test_builds_only_the_extension_with_an_explicit_allowlist(self):
        self.assertTrue(PACKAGER.is_file())
        with tempfile.TemporaryDirectory(prefix="tce-extension-package-") as temp_dir:
            output = Path(temp_dir) / "extension-only.zip"
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(PACKAGER),
                    "-OutputPath",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertTrue(output.is_file())
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), EXPECTED)
                self.assertNotIn("extensao-complementar-ato/package.json", archive.namelist())
                self.assertNotIn("docs/", "\n".join(archive.namelist()))


if __name__ == "__main__":
    unittest.main()
