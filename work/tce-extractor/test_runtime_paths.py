import json
import os
import subprocess
import sys
import tempfile
import uuid
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parent
APP_ROOT = REPO_ROOT / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from runtime_paths import RuntimePaths


def make_runtime(root: Path) -> Path:
    python = root / "runtime" / "python"
    tesseract = root / "runtime" / "tesseract"
    tessdata = tesseract / "tessdata"
    python.mkdir(parents=True)
    tessdata.mkdir(parents=True)
    (python / "python.exe").write_bytes(b"python")
    (python / "python314._pth").write_text(
        "python314.zip\n.\nLib\\site-packages\n",
        encoding="utf-8",
    )
    (tesseract / "tesseract.exe").write_bytes(b"tesseract")
    (tesseract / "libtesseract-5.dll").write_bytes(b"tesseract-dll")
    (tesseract / "libleptonica-6.dll").write_bytes(b"leptonica-dll")
    for language in ("por", "eng", "osd"):
        (tessdata / f"{language}.traineddata").write_bytes(language.encode())
    return root


class RuntimePathsTests(unittest.TestCase):
    def test_runtime_paths_require_components_and_languages(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = RuntimePaths.from_package(make_runtime(Path(temporary)))

        self.assertEqual(paths.python.name, "python.exe")
        self.assertEqual(paths.tesseract.name, "tesseract.exe")
        self.assertEqual(
            {path.name for path in paths.traineddata},
            {"por.traineddata", "eng.traineddata", "osd.traineddata"},
        )
        self.assertEqual(
            {path.name for path in paths.tesseract_dlls},
            {"libtesseract-5.dll", "libleptonica-6.dll"},
        )

    def test_runtime_paths_fail_with_specific_missing_language(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = make_runtime(Path(temporary))
            (root / "runtime" / "tesseract" / "tessdata" / "por.traineddata").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "por\\.traineddata"):
                RuntimePaths.from_package(root)

    def test_runtime_paths_fail_with_specific_missing_tesseract_dll(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = make_runtime(Path(temporary))
            (root / "runtime" / "tesseract" / "libtesseract-5.dll").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "libtesseract-5\\.dll"):
                RuntimePaths.from_package(root)

    def test_runtime_paths_are_package_local_even_when_path_is_restricted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = make_runtime(Path(temporary)).resolve()
            old_path = os.environ.get("PATH")
            try:
                os.environ["PATH"] = os.pathsep.join(
                    [os.environ.get("SystemRoot", "C:\\Windows") + "\\System32", os.environ.get("SystemRoot", "C:\\Windows")]
                )
                paths = RuntimePaths.from_package(root)
            finally:
                if old_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = old_path

        self.assertEqual(paths.root, root)
        self.assertTrue(paths.python.is_absolute())
        self.assertTrue(paths.tesseract.is_absolute())
        self.assertTrue(all(path.is_absolute() for path in paths.traineddata))
        self.assertTrue(all(path.is_relative_to(root) for path in paths.all_files))

    def test_runtime_manifest_declares_fixed_components_and_hashes(self):
        manifest_path = REPO_ROOT / "portable" / "runtime-manifest.json"
        self.assertTrue(manifest_path.exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["python"]["version"], "3.14.4")
        self.assertEqual(manifest["pymupdf"]["version"], "1.28.2")
        self.assertEqual(manifest["tesseract"]["version"], "5.4.0.20240606")
        for component in ("python", "pymupdf", "tesseract"):
            self.assertRegex(manifest[component]["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(manifest[component]["source"])
            self.assertTrue(manifest[component]["license"])

    def test_builder_is_build_time_only_and_uses_staging(self):
        builder_path = REPO_ROOT / "build-portable-runtime.ps1"
        self.assertTrue(builder_path.exists())
        builder = builder_path.read_text(encoding="utf-8-sig")

        self.assertIn("3.14.4", builder)
        self.assertIn("1.28.2", builder)
        self.assertIn("5.4.0.20240606", builder)
        self.assertIn("SHA256", builder)
        self.assertIn("staging", builder)
        self.assertIn(
            "$StagingRoot = Join-Path $ProjectRoot 'staging-verified'", builder
        )
        self.assertIn("$pythonRoot = Join-Path $StagingRoot 'runtime\\python'", builder)
        self.assertIn("$tesseractRoot = Join-Path $StagingRoot 'runtime\\tesseract'", builder)
        self.assertIn("--no-deps", builder)
        self.assertIn("python314._pth", builder)
        self.assertIn("por.traineddata", builder)
        self.assertIn("eng.traineddata", builder)
        self.assertIn("osd.traineddata", builder)
        self.assertIn("licenses", builder)
        self.assertNotRegex(builder, r"(?i)Start-Process.*tesseract.*setup")
        self.assertIn("function Convert-TesseractOutputToLines", builder)
        self.assertIn("2>&1", builder)
        self.assertIn("-split '\\r?\\n'", builder)
        self.assertIn("-notcontains $language", builder)

    def test_builder_keeps_embedded_python_isolated_and_extracts_wheel_directly(self):
        builder = (REPO_ROOT / "build-portable-runtime.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(
            "$StagingRoot = Join-Path $ProjectRoot 'staging-verified'", builder
        )
        self.assertIn("Lib/site-packages", builder)
        self.assertNotIn("$pthLines += 'import site'", builder)
        self.assertNotIn("#import site') { 'import site'", builder)
        self.assertNotRegex(
            builder, r"(?im)^\s*&?\s*\$?[^\r\n]*pip\s+install[^\r\n]*--target"
        )
        self.assertRegex(builder, r"(?i)zipfile")

    def test_builder_gate_uses_isolated_python_and_package_local_pymupdf(self):
        builder = (REPO_ROOT / "build-portable-runtime.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertRegex(builder, r"(?m)&\s+\$pythonExe\s+-B\s+-s\s+-c")
        self.assertIn("pymupdf.__file__", builder)
        self.assertIn("staging-verified", builder)
        self.assertRegex(builder, r"(?m)\^?1\.28\.2")

    def test_builder_rejects_unreserved_staging_without_deleting_sentinel(self):
        builder_path = REPO_ROOT / "build-portable-runtime.ps1"
        sentinel = REPO_ROOT / "portable" / f".task5-sentinel-{uuid.uuid4().hex}"
        sentinel.write_text("must survive", encoding="utf-8")
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(builder_path),
                    "-StagingRoot",
                    "portable",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            output = f"{result.stdout}\n{result.stderr}"
            self.assertNotEqual(result.returncode, 0, output)
            self.assertRegex(output, r"(?i)reserv|staging")
            self.assertTrue(sentinel.exists(), output)
        finally:
            sentinel.unlink(missing_ok=True)

    def test_builder_uses_transactional_reserved_build_and_backup_paths(self):
        builder = (REPO_ROOT / "build-portable-runtime.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertRegex(builder, r"stagingRoot.*\.build-")
        self.assertIn("Publish-Staging", builder)
        self.assertIn("Move-Item -LiteralPath $StagingRoot", builder)
        self.assertIn("backup", builder.lower())
        self.assertIn("rollback", builder.lower())
        self.assertNotIn("Remove-Item -LiteralPath $StagingRoot", builder)
        self.assertIn("Assert-BuilderRemovalTarget", builder)

    def test_builder_manifest_scans_transaction_build_root(self):
        builder = (REPO_ROOT / "build-portable-runtime.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(
            "Get-ChildItem -LiteralPath (Join-Path $BuildRoot 'runtime')",
            builder,
        )
        self.assertNotIn(
            "Get-ChildItem -LiteralPath (Join-Path $StagingRoot 'runtime')",
            builder,
        )

    def test_builder_materializes_tesseract_from_verified_nsis_with_temporary_sevenzip(self):
        builder = (REPO_ROOT / "build-portable-runtime.ps1").read_text(
            encoding="utf-8-sig"
        )
        manifest = json.loads(
            (REPO_ROOT / "portable" / "runtime-manifest.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertIn("7zr.exe", builder)
        self.assertIn("7z2602-extra.7z", builder)
        self.assertRegex(builder, r"(?i)nsis")
        self.assertRegex(builder, r"(?i)\b7z\.exe\b")
        self.assertIn("-o", builder)
        self.assertIn("installer", builder.lower())
        self.assertNotIn("$sourceTesseract", builder)
        self.assertNotIn("$TesseractSource", builder)
        self.assertNotIn("Copy-Item -LiteralPath $TesseractSource", builder)
        self.assertIn("Remove-BuilderPath", builder)
        self.assertIn("sevenzip", manifest)
        self.assertEqual(manifest["sevenzip"]["version"], "26.02")
        self.assertEqual(
            manifest["sevenzip"]["sha256"],
            "081df9e9311dfd9c9e0e98c1c80180b99bb51e4cb24156b5f3057fe3c259d70a",
        )
        self.assertEqual(
            manifest["sevenzip"]["standalone_sha256"],
            "56b8cc9f4971cef253644fafe54063ed7fdca551d4dee0f8c6baa81b855acd72",
        )

    def test_pymupdf_provenance_uses_pypi_page_and_artifact_identity(self):
        manifest = json.loads(
            (REPO_ROOT / "portable" / "runtime-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        pymupdf = manifest["pymupdf"]

        self.assertEqual(pymupdf["source"], "https://pypi.org/project/PyMuPDF/1.28.2/")
        self.assertEqual(
            pymupdf["artifact"], "pymupdf-1.28.2-cp310-abi3-win_amd64.whl"
        )
        self.assertRegex(pymupdf["sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("files.pythonhosted.org", json.dumps(pymupdf))

    def test_license_readme_describes_temporary_path_restriction(self):
        readme = (REPO_ROOT / "portable" / "licenses" / "README.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("temporariamente", readme.lower())
        self.assertNotIn("nunca altera `PATH`", readme)


if __name__ == "__main__":
    unittest.main()
