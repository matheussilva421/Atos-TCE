"""Opt-in smoke for the actual INICIAR.cmd entry point in an extracted package."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
import unittest


SMOKE_ROOT = os.environ.get("TCE_PORTABLE_SMOKE_ROOT")
PACKAGE_ROOT = Path(SMOKE_ROOT).resolve() if SMOKE_ROOT else None


@unittest.skipUnless(
    PACKAGE_ROOT is not None and PACKAGE_ROOT.is_dir(),
    "defina TCE_PORTABLE_SMOKE_ROOT para o smoke do INICIAR.cmd",
)
class PortableLauncherSmokeTests(unittest.TestCase):
    def test_iniciar_cmd_launches_the_local_service_before_showing_menu(self) -> None:
        assert PACKAGE_ROOT is not None
        launcher = PACKAGE_ROOT / "INICIAR.cmd"
        metadata_path = PACKAGE_ROOT / "dados-locais" / "bridge" / "service.json"
        metadata_path.unlink(missing_ok=True)
        command = [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            "call",
            str(launcher),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=PACKAGE_ROOT,
                input="7\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
            output = f"{completed.stdout}\n{completed.stderr}"
            self.assertEqual(completed.returncode, 0, output)
            self.assertIn("Serviço local disponível", output)
            self.assertIn("Código temporário para a extensão", output)

            deadline = time.monotonic() + 5
            metadata = None
            while time.monotonic() < deadline:
                if metadata_path.is_file():
                    try:
                        candidate = json.loads(metadata_path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        candidate = None
                    if isinstance(candidate, dict) and candidate.get("pairing_code"):
                        metadata = candidate
                        break
                time.sleep(0.05)
            self.assertIsNotNone(metadata)
            assert metadata is not None
            self.assertRegex(metadata["pairing_code"], r"^\d{8}$")
            self.assertGreater(metadata["port"], 0)
        finally:
            subprocess.run(
                [
                    os.environ.get("COMSPEC", "cmd.exe"),
                    "/d",
                    "/c",
                    "call",
                    str(launcher),
                    "parar",
                ],
                cwd=PACKAGE_ROOT,
                input="",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )

    def test_iniciar_bat_ponte_starts_and_verifies_loopback_bridge(self) -> None:
        assert PACKAGE_ROOT is not None
        launcher = PACKAGE_ROOT / "INICIAR.bat"
        metadata_path = PACKAGE_ROOT / "dados-locais" / "bridge" / "service.json"
        metadata_path.unlink(missing_ok=True)
        command = [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            "call",
            str(launcher),
            "ponte",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=PACKAGE_ROOT,
                input="\r\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
            output = f"{completed.stdout}\n{completed.stderr}"
            self.assertEqual(completed.returncode, 0, output)
            self.assertIn("Ponte local conectada", output)
            self.assertNotIn("1. Coletar processos selecionados", output)
        finally:
            subprocess.run(
                [
                    os.environ.get("COMSPEC", "cmd.exe"),
                    "/d",
                    "/c",
                    "call",
                    str(launcher),
                    "parar",
                ],
                cwd=PACKAGE_ROOT,
                input="",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )


if __name__ == "__main__":
    unittest.main()
