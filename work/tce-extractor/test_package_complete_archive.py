import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
import shutil
from pathlib import Path

from package_complete_archive import EXTENSION_FILE_ALLOWLIST, build_complete_zip


class CompleteArchivePackageTests(unittest.TestCase):
    def _make_auditable_package(self, source: Path, *, private: bool) -> None:
        app = source / "app"
        app.mkdir(parents=True)
        (app / "extension_exporter.py").write_text("pass", encoding="utf-8")
        (app / "package_complete_archive.py").write_text("pass", encoding="utf-8")

        project_root = Path(__file__).parent
        extension_source = project_root / "portable" / "extensao-complementar-ato"
        for relative in EXTENSION_FILE_ALLOWLIST:
            target = source / "extensao-complementar-ato" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(extension_source / relative, target)

        runtime_file = source / "runtime" / "python.exe"
        runtime_file.parent.mkdir(parents=True)
        runtime_file.write_bytes(b"python-fixture")
        license_file = source / "licenses" / "README.md"
        license_file.parent.mkdir(parents=True)
        license_file.write_text("Licenças fixture", encoding="utf-8")
        entries = []
        for relative, path in (
            ("runtime/python.exe", runtime_file),
            ("licenses/README.md", license_file),
        ):
            entries.append({
                "path": relative,
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        (source / "runtime-manifest.json").write_text(
            json.dumps({"schema_version": 1, "build": {"included_files": entries}}),
            encoding="utf-8",
        )
        if private:
            archive = source / "acervo-tce"
            archive.mkdir()
            (archive / "dados-complementar-ato.json").write_text(
                '{"records":[]}', encoding="utf-8"
            )

    def test_reset_backup_is_not_included_in_the_next_private_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "kit"
            self._make_auditable_package(source, private=True)
            previous = source / "backups-acervo" / "previous" / "acervo-tce" / "old-records.json"
            previous.parent.mkdir(parents=True)
            previous.write_text('{"previous_person":"fixture"}', encoding="utf-8")
            destination = root / "new.zip"
            build_complete_zip(source, destination, distribution="private")
            with zipfile.ZipFile(destination) as package:
                names = package.namelist()
            self.assertFalse(any(name.startswith("backups-acervo/") for name in names))
            self.assertIn("acervo-tce/dados-complementar-ato.json", names)
            self.assertTrue(previous.exists())

    def test_refuses_private_zip_when_content_audit_is_not_green(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "private"
            destination = root / "private.zip"
            self._make_auditable_package(source, private=True)
            (source / "notes.txt").write_text(
                'Authorization: "Bearer fixture-secret"', encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "auditoria"):
                build_complete_zip(source, destination, distribution="private")

            self.assertFalse(destination.exists())

    def test_private_zip_audits_filtered_inventory_and_omits_extension_tests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "private"
            destination = root / "private.zip"
            self._make_auditable_package(source, private=True)
            project_tests = (
                Path(__file__).parent
                / "portable"
                / "extensao-complementar-ato"
                / "tests"
            )
            shutil.copytree(
                project_tests, source / "extensao-complementar-ato" / "tests"
            )

            stats = build_complete_zip(source, destination, distribution="private")

            self.assertEqual(stats["extension_files"], len(EXTENSION_FILE_ALLOWLIST))
            with zipfile.ZipFile(destination) as package:
                names = set(package.namelist())
            self.assertFalse(
                any(
                    name.startswith("extensao-complementar-ato/tests/")
                    for name in names
                )
            )

    def test_private_builder_rejects_unlisted_extension_extra(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "private"
            destination = root / "private.zip"
            self._make_auditable_package(source, private=True)
            (source / "extensao-complementar-ato" / "extra.js").write_text(
                "console.log('fixture extra');", encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "extension_file_unlisted"):
                build_complete_zip(source, destination, distribution="private")

            self.assertFalse(destination.exists())

    def test_refuses_public_zip_with_nested_private_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "public"
            destination = root / "public.zip"
            self._make_auditable_package(source, private=False)
            private_file = source / "state" / "acervo-tce" / "records.json"
            private_file.parent.mkdir(parents=True)
            private_file.write_text('{"fixture":true}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "auditoria"):
                build_complete_zip(source, destination, distribution="public")

            self.assertFalse(destination.exists())

    def test_builder_rejects_acervo_component_outside_archive_root(self):
        for relative in (
            "app/acervo-tce/records.json",
            "extensao-complementar-ato/acervo-tce/records.json",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                source = root / "private"
                destination = root / "private.zip"
                self._make_auditable_package(source, private=True)
                target = source / relative
                target.parent.mkdir(parents=True)
                target.write_text('{"fixture":true}', encoding="utf-8")

                with self.assertRaisesRegex(ValueError, "acervo-tce"):
                    build_complete_zip(source, destination, distribution="private")

                self.assertFalse(destination.exists())

    def test_public_distribution_requires_extension_and_never_adds_private_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "public"
            destination = root / "public.zip"
            self._make_auditable_package(source, private=False)

            stats = build_complete_zip(source, destination, distribution="public")

            self.assertEqual(stats["extension_files"], len(EXTENSION_FILE_ALLOWLIST))
            self.assertEqual(stats["extension_data_records"], 0)
            with zipfile.ZipFile(destination) as package:
                names = set(package.namelist())
            self.assertNotIn("acervo-tce/dados-complementar-ato.json", names)

    def test_packages_application_and_archive_without_browser_profile_or_temporary_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "tce-processos-completo-portatil"
            destination = root / "pacote.zip"
            self._make_auditable_package(source, private=True)
            (source / "acervo-tce" / "processos" / "fixture-process" / "evento-fixture").mkdir(
                parents=True
            )
            (source / "INICIAR.cmd").write_text("menu", encoding="utf-8")
            (source / "app" / "main.py").write_text("pass", encoding="utf-8")
            (source / "acervo-tce" / "complementar-ato.html").write_text(
                "<html></html>", encoding="utf-8"
            )
            process_dir = source / "acervo-tce" / "processos" / "fixture-process"
            (process_dir / "processo.json").write_text("{}", encoding="utf-8")
            event_dir = process_dir / "evento-fixture"
            (event_dir / "evento.json").write_text("{}", encoding="utf-8")
            (event_dir / "ato.pdf").write_bytes(b"%PDF-test")

            stats = build_complete_zip(source, destination)

            self.assertEqual(stats["processes"], 1)
            self.assertEqual(stats["events"], 1)
            self.assertEqual(stats["pdfs"], 1)
            with zipfile.ZipFile(destination) as archive:
                names = set(archive.namelist())
            self.assertIn("INICIAR.cmd", names)
            self.assertIn("acervo-tce/complementar-ato.html", names)
            self.assertIn("acervo-tce/processos/fixture-process/evento-fixture/ato.pdf", names)
            self.assertFalse(
                any(name.startswith("tce-processos-completo-portatil/") for name in names)
            )

    def test_does_not_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "portable"
            (source / "acervo-tce").mkdir(parents=True)
            destination = root / "pacote.zip"
            destination.write_bytes(b"existing")

            with self.assertRaises(FileExistsError):
                build_complete_zip(source, destination)

    def test_private_zip_requires_dataset_and_reports_extension_integrity_counts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "portable"
            destination = root / "pacote.zip"
            self._make_auditable_package(source, private=True)
            archive = source / "acervo-tce"
            (archive / "dados-complementar-ato.json").write_text(
                '{"records":[{"id":"fixture-alpha"},{"id":"fixture-beta"}]}', encoding="utf-8"
            )

            stats = build_complete_zip(source, destination)

            self.assertEqual(stats["extension_files"], len(EXTENSION_FILE_ALLOWLIST))
            self.assertEqual(stats["extension_data_records"], 2)
            with zipfile.ZipFile(destination) as package:
                names = set(package.namelist())
            self.assertIn("extensao-complementar-ato/manifest.json", names)
            self.assertIn("acervo-tce/dados-complementar-ato.json", names)

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "portable"
            (source / "acervo-tce").mkdir(parents=True)
            with self.assertRaises(FileNotFoundError):
                build_complete_zip(source, Path(temp_dir) / "missing-data.zip")

    def test_private_zip_allows_archive_pdfs_and_checkpoints(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "portable"
            destination = root / "pacote.zip"
            self._make_auditable_package(source, private=True)
            archive = source / "acervo-tce" / "processos" / "fixture"
            archive.mkdir(parents=True)
            (archive / "checkpoint.json").write_text("{}", encoding="utf-8")
            (archive / "documento.pdf").write_bytes(b"pdf")

            build_complete_zip(source, destination)

            with zipfile.ZipFile(destination) as package:
                names = set(package.namelist())
            self.assertIn("acervo-tce/processos/fixture/checkpoint.json", names)
            self.assertIn("acervo-tce/processos/fixture/documento.pdf", names)

    def test_isolated_cli_loads_sibling_audit_without_project_on_sys_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = root / "app"
            app.mkdir()
            project_root = Path(__file__).parent
            shutil.copyfile(
                project_root / "package_complete_archive.py",
                app / "package_complete_archive.py",
            )
            shutil.copyfile(
                project_root / "portable" / "app" / "package_audit.py",
                app / "package_audit.py",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(app / "package_complete_archive.py"),
                    "--help",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--distribution", result.stdout)

    def test_isolated_cli_reports_missing_sibling_audit_without_using_arbitrary_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = root / "app"
            app.mkdir()
            project_root = Path(__file__).parent
            shutil.copyfile(
                project_root / "package_complete_archive.py",
                app / "package_complete_archive.py",
            )
            (root / "package_audit.py").write_text(
                "raise RuntimeError('arbitrary audit module loaded')\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(app / "package_complete_archive.py"),
                    "--help",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("package_audit.py", result.stderr)
            self.assertIn("arquivo ausente", result.stderr)
            self.assertNotIn("arbitrary audit module loaded", result.stderr)


if __name__ == "__main__":
    unittest.main()
