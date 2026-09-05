"""Exercise distributed scripts with the actual Windows PowerShell 5.1 parser."""
import json
from pathlib import Path
import subprocess
import unittest


class PowerShellEncodingTests(unittest.TestCase):
    def test_native_windows_powershell_reads_menu_accents(self):
        menu = Path(__file__).parent / "portable" / "app" / "menu.ps1"
        script = (
            "[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false); "
            f". '{str(menu).replace(chr(39), chr(39)*2)}'; "
            "@(Get-TceMenuOptions | ForEach-Object label) | ConvertTo-Json -Compress"
        )
        result = subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-Command", script],
                                capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        labels = json.loads(result.stdout)
        self.assertEqual(labels[3], "Atualizar dados da extensão")
        self.assertEqual(labels[6], "Diagnóstico do runtime")


if __name__ == "__main__":
    unittest.main()
