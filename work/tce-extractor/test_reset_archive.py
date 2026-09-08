"""Focused safety tests for the portable archive reset transaction."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).parent / "portable" / "app" / "reset_archive.py"
SPEC = spec_from_file_location("portable_reset_archive", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
reset_archive = module_from_spec(SPEC)
SPEC.loader.exec_module(reset_archive)


class ResetArchiveSafetyTests(unittest.TestCase):
    def test_rollback_restores_old_archive_when_staging_cleanup_is_denied(self):
        with TemporaryDirectory() as temporary:
            package_root = Path(temporary)
            archive_root = package_root / "acervo-tce"
            archive_root.mkdir()
            old_file = archive_root / "processos" / "103365-2024" / "processo.json"
            old_file.parent.mkdir(parents=True)
            old_file.write_text("conteudo antigo", encoding="utf-8")

            real_replace = reset_archive.os.replace
            replace_calls = []

            def fail_install(source, destination):
                replace_calls.append((Path(source), Path(destination)))
                if Path(destination) == archive_root and Path(source).name.startswith(".reset-staging-"):
                    raise OSError("falha injetada ao instalar acervo novo")
                return real_replace(source, destination)

            with patch.object(reset_archive.os, "replace", side_effect=fail_install), patch.object(
                reset_archive.shutil,
                "rmtree",
                side_effect=PermissionError("staging bloqueado"),
            ):
                with self.assertRaises(reset_archive.ResetArchiveError):
                    reset_archive.reset_archive(package_root)

            self.assertEqual(old_file.read_text(encoding="utf-8"), "conteudo antigo")
            self.assertGreaterEqual(len(replace_calls), 4)
            self.assertEqual(replace_calls[-1][1], archive_root)
            self.assertEqual(replace_calls[-1][0], replace_calls[1][1])

    def test_broken_archive_symlink_is_rejected_before_exists_check(self):
        with TemporaryDirectory() as temporary:
            package_root = Path(temporary)
            package_root.mkdir(exist_ok=True)
            archive_root = package_root / "acervo-tce"
            missing_target = package_root / "target-that-does-not-exist"
            try:
                os.symlink(str(missing_target), str(archive_root), target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"ambiente sem criação de symlink: {exc}")

            with self.assertRaises(reset_archive.ResetArchiveError):
                reset_archive.reset_archive(package_root)
            self.assertTrue(archive_root.is_symlink())
            self.assertFalse((package_root / "backups-acervo").exists())

    def test_nonexistent_reparse_target_is_rejected_before_exists_check(self):
        with TemporaryDirectory() as temporary:
            package_root = Path(temporary)
            archive_root = package_root / "acervo-tce"

            def probe(path):
                return Path(path) == archive_root

            with patch.object(reset_archive, "_is_reparse_point", side_effect=probe):
                with self.assertRaises(reset_archive.ResetArchiveError):
                    reset_archive.reset_archive(package_root)
            self.assertFalse(archive_root.exists())
            self.assertFalse((package_root / "backups-acervo").exists())

    def test_archive_walk_permission_error_fails_closed(self):
        with TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "acervo-tce"
            archive_root.mkdir()

            def inaccessible_walk(_root, **kwargs):
                self.assertIsNotNone(kwargs.get("onerror"))
                kwargs["onerror"](PermissionError("subarvore inacessível"))
                return iter(())

            with patch.object(reset_archive.os, "walk", side_effect=inaccessible_walk):
                with self.assertRaises(reset_archive.ResetArchiveError):
                    reset_archive._assert_no_reparse_points(archive_root)

    def test_reset_preserves_valid_workflow_progress_in_new_cycle(self):
        with TemporaryDirectory() as temporary:
            package_root = Path(temporary)
            archive_root = package_root / "acervo-tce"
            archive_root.mkdir()
            progress = {
                "schema_version": 1,
                "revision": 4,
                "processes": {
                    "103439/2023": {
                        "completed": True,
                        "updated_at": "2026-09-08T00:00:00+00:00",
                    }
                },
            }
            (archive_root / "progresso.json").write_text(
                __import__("json").dumps(progress), encoding="utf-8"
            )

            summary = reset_archive.reset_archive(package_root)

            active = __import__("json").loads(
                (archive_root / "progresso.json").read_text(encoding="utf-8")
            )
            backup = __import__("json").loads(
                (
                    Path(summary["backup_root"])
                    / "acervo-tce"
                    / "progresso.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(active, progress)
            self.assertEqual(backup, progress)

    def test_reset_does_not_promote_legacy_reviewed_checkpoint(self):
        with TemporaryDirectory() as temporary:
            package_root = Path(temporary)
            archive_root = package_root / "acervo-tce"
            archive_root.mkdir()
            (archive_root / "checkpoint.json").write_text(
                '{"processes": [{"key": "103439/2023", "status": "reviewed:v1"}]}',
                encoding="utf-8",
            )

            reset_archive.reset_archive(package_root)

            active = __import__("json").loads(
                (archive_root / "progresso.json").read_text(encoding="utf-8")
            )
            self.assertEqual(active["schema_version"], 1)
            self.assertEqual(active["revision"], 0)
            self.assertEqual(active["processes"], {})

    def test_reset_rejects_corrupt_workflow_progress_before_moving_archive(self):
        with TemporaryDirectory() as temporary:
            package_root = Path(temporary)
            archive_root = package_root / "acervo-tce"
            archive_root.mkdir()
            old_file = archive_root / "progresso.json"
            old_file.write_text("{broken", encoding="utf-8")

            with self.assertRaises(reset_archive.ResetArchiveError):
                reset_archive.reset_archive(package_root)

            self.assertEqual(old_file.read_text(encoding="utf-8"), "{broken")
            self.assertFalse((package_root / "backups-acervo").exists())


if __name__ == "__main__":
    unittest.main()
