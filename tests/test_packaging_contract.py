"""Contract tests for the archive-free portable package (M6 Task 5)."""

import json
import hashlib
import base64
import os
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from app.api.bridge import TRUSTED_EXTENSION_ID

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPO_ROOT / "packaging" / "verify-package.ps1"
BUILDER = REPO_ROOT / "packaging" / "build-portable.ps1"
DIST_ZIP = REPO_ROOT / "dist" / "Atos-TCE-portable.zip"
SOURCE_MANIFEST = REPO_ROOT / "extension" / "manifest.json"
IDENTITY_ALPHABET = "abcdefghijklmnop"


def chromium_extension_id(public_key_der: bytes) -> str:
    digest = hashlib.sha256(public_key_der).digest()[:16]
    return "".join(IDENTITY_ALPHABET[b >> 4] + IDENTITY_ALPHABET[b & 0x0F] for b in digest)


def trusted_manifest() -> dict:
    return json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))


def assert_trusted_extension_manifest(test_case: unittest.TestCase, manifest: dict) -> None:
    test_case.assertEqual(
        chromium_extension_id(base64.b64decode(manifest["key"])), TRUSTED_EXTENSION_ID
    )


def canonical_path(value) -> str:
    r"""A Windows-safe comparison form for a path that may use short names.

    A GitHub runner reports %TEMP% as C:\Users\RUNNER~1\... while Python
    resolves the same folder as C:\Users\runneradmin\...: the strings differ
    for one single file.
    """

    return os.path.normcase(os.path.realpath(str(value)))


# The plan's allowlist for the standard portable ZIP.
FORBIDDEN_PREFIXES = (
    "data/",
    "acervo-tce/",
    "dados-locais/",
    "profile/",
    "outputs/",
    "Versions/",
    "work/",
    "logs/",
)

BASE_FILES = {
    "app/main.py": b"print('mesa')\n",
    "app/core/store.py": b"# store\n",
    "app/web/index.html": b"<!doctype html>\n",
    "extension/manifest.json": json.dumps(
        {"manifest_version": 3, "name": "Complementar Ato", "version": "1.0.0"}
    ).encode("utf-8"),
    "START.cmd": b"@echo off\r\npython -m app.main %*\r\n",
    "README.md": b"# Atos TCE\n",
    "licenses/README.md": b"# Licencas\n",
}

REQUIRED_ENTRIES = (
    "app/main.py",
    "extension/manifest.json",
    "START.cmd",
    "README.md",
)


def powershell(script: Path, *arguments, cwd: Path | None = None) -> subprocess.CompletedProcess:
    command = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ] + [str(argument) for argument in arguments]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
        env=powershell_env(),
    )


def powershell_env() -> dict:
    """Point Windows PowerShell 5.1 at its own modules.

    A host that exports a PowerShell 7 module path (as the Codex runtime shell
    does) makes 5.1 load the pwsh copy of Microsoft.PowerShell.Utility, which
    hides cmdlets such as Get-FileHash. The contract tests therefore run the
    packaged scripts with the module path of a plain Windows installation.
    """

    environment = dict(os.environ)
    program_files = environment.get("ProgramFiles", r"C:\Program Files")
    system_root = environment.get("SystemRoot", r"C:\Windows")
    environment["PSModulePath"] = os.pathsep.join(
        (
            os.path.join(program_files, "WindowsPowerShell", "Modules"),
            os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "Modules"),
        )
    )
    return environment


def runtime_entries(payload: bytes) -> dict:
    """Entries that satisfy the runtime contract: one declared file plus its licence."""

    licence = BASE_FILES["licenses/README.md"]
    declared = (
        ("runtime/python/python.exe", "python", payload),
        ("licenses/README.md", "licenses", licence),
    )
    entries = {name: data for name, _component, data in declared}
    entries["runtime-manifest.json"] = json.dumps(
        {
            "python": {"version": "3.14.4"},
            "build": {
                "included_files": [
                    {
                        "path": name,
                        "component": component,
                        "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                    for name, component, data in declared
                ]
            },
        }
    ).encode("utf-8")
    return entries


def make_package(path: Path, entries: dict | None = None, base: dict | None = None) -> Path:
    payload = dict(BASE_FILES if base is None else base)
    payload.update(entries or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in payload.items():
            archive.writestr(name, data)
    return path


class VerifierContractTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def verify(self, archive: Path, *extra):
        return powershell(VERIFIER, "-ZipPath", archive, *extra)

    def test_accepts_a_clean_minimal_package(self):
        archive = make_package(self.tmp / "clean.zip")

        result = self.verify(archive, "-AllowMissingRuntime", "-SkipSmoke")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(canonical_path(report["zip"]), canonical_path(archive.resolve()))
        self.assertFalse(report["runtime_included"])
        self.assertEqual(report["zip_sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_requires_the_runtime_by_default(self):
        archive = make_package(self.tmp / "clean.zip")

        result = self.verify(archive, "-SkipSmoke")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime", (result.stderr + result.stdout).lower())

    def test_rejects_private_archive_data(self):
        archive = make_package(
            self.tmp / "privado.zip",
            {
                "data/atos-tce.db": b"SQLite format 3\x00",
                "acervo-tce/processos/102390-2026/documento.pdf": b"%PDF-1.4\n",
            },
        )

        result = self.verify(archive, "-AllowMissingRuntime", "-SkipSmoke")

        self.assertNotEqual(result.returncode, 0)
        output = result.stderr + result.stdout
        self.assertTrue("data/" in output or "acervo-tce" in output, output)

    def test_rejects_pdf_and_browser_profile_artifacts(self):
        cases = (
            {"docs/relatorio.pdf": b"%PDF-1.4\n"},
            {"dados-locais/perfil/Default/Cookies": b"sqlite"},
            {"profile/Default/Login Data": b"sqlite"},
            {"outputs/Atos-TCE-completo.zip": b"PK\x03\x04"},
            {"app/__pycache__/main.cpython-314.pyc": b"\x00\x01"},
        )
        for index, entries in enumerate(cases):
            with self.subTest(entries=entries):
                archive = make_package(self.tmp / f"forbidden-{index}.zip", entries)
                result = self.verify(archive, "-AllowMissingRuntime", "-SkipSmoke")
                self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_required_entries(self):
        base = dict(BASE_FILES)
        base.pop("START.cmd")
        archive = make_package(self.tmp / "incompleto.zip", base=base)

        result = self.verify(archive, "-AllowMissingRuntime", "-SkipSmoke")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("START.cmd", result.stderr + result.stdout)

    def test_verifies_every_runtime_file_against_the_runtime_manifest(self):
        payload = b"runtime payload"

        good = make_package(self.tmp / "runtime-ok.zip", runtime_entries(payload))
        result = self.verify(good, "-SkipSmoke")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["runtime_included"])

        corrupted = runtime_entries(payload)
        corrupted["runtime/python/python.exe"] = b"runtime payloaX"
        bad = make_package(self.tmp / "runtime-ruim.zip", corrupted)
        result = self.verify(bad, "-SkipSmoke")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("python.exe", result.stderr + result.stdout)

    def test_rejects_a_runtime_file_that_is_not_declared(self):
        payload = b"runtime payload"
        entries = runtime_entries(payload)
        entries["runtime/python/surpresa.exe"] = b"nao declarado"
        archive = make_package(self.tmp / "runtime-extra.zip", entries)

        result = self.verify(archive, "-SkipSmoke")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("surpresa.exe", result.stderr + result.stdout)


class BuilderContractTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def build(self, *arguments):
        return powershell(BUILDER, "-SkipRuntime", *arguments)

    def test_builds_an_allowlisted_package_without_the_runtime(self):
        destination = self.tmp / "contract.zip"

        result = self.build("-OutputPath", destination, "-StagingRoot", "staging-package-contract")

        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(destination) as handle:
            names = [name.replace("\\", "/") for name in handle.namelist()]
        self.assertTrue(any(name.startswith("app/") for name in names))
        self.assertTrue(any(name.startswith("extension/") for name in names))
        self.assertIn("START.cmd", names)
        self.assertIn("README.md", names)
        self.assertFalse(any(name.lower().endswith(".pdf") for name in names))
        self.assertFalse(any("__pycache__" in name for name in names))
        for prefix in FORBIDDEN_PREFIXES:
            self.assertFalse(any(name.startswith(prefix) for name in names), prefix)
        self.assertFalse((REPO_ROOT / "staging-package-contract").exists())

        # A runtime-free ZIP is a contract fixture, never a release artefact.
        verification = powershell(VERIFIER, "-ZipPath", destination, "-SkipSmoke")
        self.assertNotEqual(verification.returncode, 0)

    def test_built_package_preserves_the_trusted_extension_identity(self):
        destination = self.tmp / "identity.zip"

        result = self.build("-OutputPath", destination, "-StagingRoot", "staging-package-identity")

        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(destination) as handle:
            packaged = json.loads(handle.read("extension/manifest.json").decode("utf-8"))
        source = trusted_manifest()
        self.assertEqual(packaged["key"], source["key"])
        assert_trusted_extension_manifest(self, packaged)

    def test_refuses_an_output_path_inside_the_data_root(self):
        result = self.build("-OutputPath", REPO_ROOT / "data" / "pacote.zip")

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((REPO_ROOT / "data" / "pacote.zip").exists())

    def test_refuses_to_overwrite_without_force(self):
        destination = self.tmp / "existing.zip"
        destination.write_bytes(b"ocupado")

        result = self.build("-OutputPath", destination)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(destination.read_bytes(), b"ocupado")

        forced = self.build("-OutputPath", destination, "-Force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertGreater(destination.stat().st_size, len(b"ocupado"))


class RealPackageContractTests(unittest.TestCase):
    def test_real_portable_zip_respects_the_allowlist(self):
        if not DIST_ZIP.is_file():
            self.skipTest(f"{DIST_ZIP} nao existe neste checkout (rode packaging/build-portable.ps1)")

        with zipfile.ZipFile(DIST_ZIP) as handle:
            names = [name.replace("\\", "/") for name in handle.namelist()]
            self.assertTrue(any(name.startswith("app/") for name in names))
            self.assertTrue(any(name.startswith("extension/") for name in names))
            self.assertTrue(any(name.startswith("runtime/") for name in names))
            self.assertFalse(any(name.lower().endswith(".pdf") for name in names))
            for prefix in FORBIDDEN_PREFIXES:
                self.assertFalse(any(name.startswith(prefix) for name in names), prefix)
            packaged = json.loads(handle.read("extension/manifest.json").decode("utf-8"))
        self.assertEqual(packaged["key"], trusted_manifest()["key"])
        assert_trusted_extension_manifest(self, packaged)

        result = powershell(VERIFIER, "-ZipPath", DIST_ZIP, "-SkipSmoke")

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
