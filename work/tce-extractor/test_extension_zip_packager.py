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
    "extensao-complementar-ato/content/form-detector.js",
    "extensao-complementar-ato/lib/bridge-client.js",
    "extensao-complementar-ato/lib/matcher.js",
    "extensao-complementar-ato/lib/messages.js",
    "extensao-complementar-ato/lib/normalizer.js",
    "extensao-complementar-ato/lib/schema.js",
    "extensao-complementar-ato/sidepanel/panel.css",
    "extensao-complementar-ato/sidepanel/panel.html",
    "extensao-complementar-ato/sidepanel/panel.js",
}


class ExtensionZipPackagerTests(unittest.TestCase):
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
