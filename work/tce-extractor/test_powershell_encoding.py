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

    def test_core_reuses_an_existing_tce_devtools_port_before_opening_browser(self):
        module = Path(__file__).parent / "portable" / "TcePortable.Core.psm1"
        escaped = str(module).replace("'", "''")
        script = (
            f"Import-Module '{escaped}' -Force; "
            "$probe = { param([int]$Port) if ($Port -eq 9223) { @([pscustomobject]@{ type = 'page'; url = 'https://novaarearestrita.tce.rn.gov.br/telaPrincipalMenu.asp' }) } else { @() } }; "
            "$port = Get-TceExistingPortalDevToolsPort -Ports @(9222, 9223) -TargetProbe $probe; "
            "[string]$port"
        )
        result = subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-Command", script],
                                capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "9223")

    def test_collector_keeps_the_two_econtas_scopes_distinct(self):
        collector = Path(__file__).parent / "portable" / "Coletar-Processos-TCE.ps1"
        text = collector.read_text(encoding="utf-8")
        self.assertIn("[ValidateSet('sector_finalistic','my_processes')][string]$EscopoPortal", text)
        self.assertIn("/dashboard/processos-no-setor/no-setor?", text)
        self.assertIn("/dashboard/meus/meus-processos?", text)

    def test_collector_downloads_restricted_pdfs_inside_the_authenticated_browser(self):
        collector = Path(__file__).parent / "portable" / "Coletar-Processos-TCE.ps1"
        text = collector.read_text(encoding="utf-8")
        self.assertIn("Connect-TceCdpTarget", text)
        self.assertIn("novaarearestrita.tce.rn.gov.br", text)
        self.assertIn("Invoke-TceBrowserDownload", text)
        self.assertIn("arrayBuffer()", text)
        self.assertIn("FromBase64String", text)

    def test_browser_downloader_uses_windows_powershell_file_length_check(self):
        collector = Path(__file__).parent / "portable" / "Coletar-Processos-TCE.ps1"
        text = collector.read_text(encoding="utf-8")
        self.assertNotIn("[IO.File]::GetLength", text)
        self.assertIn("(Get-Item -LiteralPath $Destination).Length", text)


if __name__ == "__main__":
    unittest.main()
