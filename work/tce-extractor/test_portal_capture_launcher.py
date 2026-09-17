from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import json


LAUNCHER = Path(__file__).with_name("portable") / "INICIAR-CAPTURA-AREA-RESTRITA.cmd"


class PortalCaptureLauncherTests(unittest.TestCase):
    def test_runner_invocation_is_single_line_and_keeps_required_arguments(self):
        text = LAUNCHER.read_text(encoding="utf-8")

        invocation = (
            'python "%PACKAGE_ROOT%\\real_portal_session.py" '
            '--package-root "%PACKAGE_ROOT%" '
            '--output "%OBSERVATION%" '
            '--record-root "%RECORD_ROOT%" '
            '--stay-open'
        )

        self.assertIn(invocation, text)
        self.assertNotIn('real_portal_session.py" ^', text)

    @unittest.skipUnless(os.name == "nt", "teste usa cmd.exe")
    def test_cmd_passes_all_runner_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copy2(LAUNCHER, root / LAUNCHER.name)
            (root / "INICIAR.cmd").write_text(
                "@echo off\nexit /b 0\n", encoding="utf-8"
            )
            (root / "argv-probe.py").write_text(
                "import json, sys\n"
                "print(json.dumps(sys.argv[1:], ensure_ascii=False))\n",
                encoding="utf-8",
            )
            (root / "python.cmd").write_text(
                "@echo off\n"
                "\"%TCE_TEST_PYTHON%\" \"%~dp0argv-probe.py\" %* > \"%~dp0python-args.json\"\n"
                "exit /b %ERRORLEVEL%\n",
                encoding="utf-8",
            )

            environment = os.environ.copy()
            environment["PATH"] = str(root) + os.pathsep + environment["PATH"]
            environment["TCE_TEST_PYTHON"] = os.sys.executable
            completed = subprocess.run(
                [
                    os.environ.get("COMSPEC", "cmd.exe"),
                    "/d",
                    "/c",
                    "call",
                    str(root / LAUNCHER.name),
                ],
                cwd=root,
                input="\r\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                timeout=10,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            arguments = json.loads(
                (root / "python-args.json").read_text(encoding="utf-8")
            )
            self.assertIn("--package-root", arguments)
            self.assertIn("--output", arguments)
            self.assertIn("--record-root", arguments)
            self.assertIn("--stay-open", arguments)


if __name__ == "__main__":
    unittest.main()
