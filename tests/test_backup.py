"""Tests for the explicit full backup and its restore manifest (M6 Task 4)."""

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.models import DocumentRecord, ProcessRecord
from app.core.store import SCHEMA_VERSION, Store

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "backup.py"

PDF = b"%PDF-1.4\nbackup fixture\n%%EOF\n"
OTHER_PDF = b"%PDF-1.4\nsecond backup fixture\n%%EOF\n"

_MODULE = None
_RESTORE_MODULE = None


def backup_module():
    """Load the CLI script as a module so the backup can be driven in-process."""

    global _MODULE
    if _MODULE is None:
        spec = importlib.util.spec_from_file_location("backup_cli", SCRIPT_PATH)
        if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
            raise AssertionError(f"cannot load {SCRIPT_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
        _MODULE = module
    return _MODULE


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


class BackupTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.data = self.tmp / "data"
        self.out = self.tmp / "destino"
        self.out.mkdir(parents=True)
        self.store = Store.open(self.data / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.blobs = {}

    def store_blob(self, payload: bytes) -> str:
        value = digest(payload)
        write(self.data / "archive" / "blobs" / value[:2] / f"{value}.pdf", payload)
        self.blobs[value] = len(payload)
        return value

    def register_document(self, sha: str) -> None:
        process_id = self.store.upsert_process(
            ProcessRecord(
                process_key="100015/2026",
                interested="Pessoa Exemplo",
                interested_normalized="pessoa exemplo",
            )
        )
        self.store.replace_documents(
            process_id,
            [
                DocumentRecord(
                    source_id="doc-1",
                    event="1",
                    title="Ato.pdf",
                    relative_path="processos/100015-2026/Ato.pdf",
                    sha256=sha,
                    storage_state="HOT",
                )
            ],
        )

    def create_backup(self, destination: Path):
        return backup_module().create_backup(self.data, destination)

    def read_manifest(self, archive: Path) -> dict:
        with zipfile.ZipFile(archive) as handle:
            return json.loads(handle.read("manifest.json").decode("utf-8"))


class BackupContentTests(BackupTestCase):
    def test_backup_contains_database_blobs_and_manifest(self):
        first = self.store_blob(PDF)
        second = self.store_blob(OTHER_PDF)
        self.register_document(first)
        destination = self.out / "backup.zip"

        manifest = self.create_backup(destination)

        self.assertTrue(destination.is_file())
        self.assertEqual(manifest.file_count, 2)
        self.assertEqual(manifest.blob_bytes, len(PDF) + len(OTHER_PDF))
        self.assertEqual(manifest.total_bytes, manifest.blob_bytes + manifest.db_bytes)
        self.assertEqual(manifest.blob_sha256, tuple(sorted([first, second])))
        self.assertEqual(manifest.schema_version, SCHEMA_VERSION)

        with zipfile.ZipFile(destination) as handle:
            names = set(handle.namelist())
            self.assertIn("atos-tce.db", names)
            self.assertIn("manifest.json", names)
            for sha in (first, second):
                self.assertIn(f"archive/blobs/{sha[:2]}/{sha}.pdf", names)
            self.assertIsNone(handle.testzip())
            payload = self.read_manifest(destination)
            self.assertEqual(payload["db_sha256"], hashlib.sha256(handle.read("atos-tce.db")).hexdigest())
            self.assertEqual(payload["file_count"], 2)
            self.assertEqual(sorted(payload["blob_sha256"]), sorted([first, second]))

    def test_backup_database_holds_data_that_lives_in_the_write_ahead_log(self):
        sha = self.store_blob(PDF)
        self.register_document(sha)
        destination = self.out / "backup.zip"

        self.create_backup(destination)

        extracted = self.tmp / "restaurado.db"
        with zipfile.ZipFile(destination) as handle:
            extracted.write_bytes(handle.read("atos-tce.db"))
        connection = sqlite3.connect(str(extracted))
        try:
            count = connection.execute("SELECT COUNT(*) FROM processes").fetchone()[0]
            documents = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            version = connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()[0]
        finally:
            connection.close()

        # The store is still open, so the rows live in the -wal file: a plain
        # file copy of atos-tce.db would restore an empty database.
        self.assertEqual(count, 1)
        self.assertEqual(documents, 1)
        self.assertEqual(int(version), SCHEMA_VERSION)

    def test_backup_does_not_touch_the_source(self):
        sha = self.store_blob(PDF)
        blob = self.data / "archive" / "blobs" / sha[:2] / f"{sha}.pdf"
        before = (blob.stat().st_mtime_ns, blob.stat().st_size)

        self.create_backup(self.out / "backup.zip")

        after = (blob.stat().st_mtime_ns, blob.stat().st_size)
        self.assertEqual(before, after)

    def test_backup_leaves_no_temporary_file_behind(self):
        self.store_blob(PDF)
        destination = self.out / "backup.zip"

        self.create_backup(destination)

        leftovers = [path.name for path in self.out.iterdir() if path.name != "backup.zip"]
        self.assertEqual(leftovers, [])


class ExternalBlobBackupTests(BackupTestCase):
    """CR-18: the backup follows the database, not the local blob folder."""

    def archive_externally(self, sha: str, *, payload: bytes | None = None) -> Path:
        """Model an ARCHIVED document: local blob gone, external copy present."""

        content = PDF if payload is None else payload
        external = self.tmp / "externo" / sha[:2] / f"{sha}.pdf"
        write(external, content)
        (self.data / "archive" / "blobs" / sha[:2] / f"{sha}.pdf").unlink(missing_ok=True)
        self.store.upsert_archive_blob(
            sha,
            size_bytes=len(content),
            external_path=str(external),
            local_present=False,
            external_present=True,
        )
        return external

    def test_an_external_only_blob_is_included(self):
        sha = digest(PDF)
        self.register_document(sha)
        self.archive_externally(sha)
        destination = self.out / "backup.zip"

        manifest = self.create_backup(destination)

        self.assertEqual(manifest.file_count, 1)
        self.assertEqual(manifest.sources["external"], 1)
        self.assertEqual(manifest.sources["missing"], 0)
        with zipfile.ZipFile(destination) as handle:
            self.assertEqual(handle.read(f"archive/blobs/{sha[:2]}/{sha}.pdf"), PDF)

    def test_a_corrupted_external_copy_aborts_the_backup(self):
        sha = digest(PDF)
        self.register_document(sha)
        self.archive_externally(sha, payload=PDF[:-1] + b"X")
        destination = self.out / "backup.zip"

        with self.assertRaises(backup_module().BackupError):
            self.create_backup(destination)

        self.assertFalse(destination.exists())

    def test_a_referenced_blob_without_any_copy_aborts_the_backup(self):
        self.register_document(digest(PDF))
        destination = self.out / "backup.zip"

        with self.assertRaises(backup_module().BackupError):
            self.create_backup(destination)

        self.assertFalse(destination.exists())

    def test_a_blob_is_written_once_even_when_both_copies_exist(self):
        sha = self.store_blob(PDF)
        self.register_document(sha)
        self.store.upsert_archive_blob(
            sha,
            size_bytes=len(PDF),
            external_path=str(write(self.tmp / "externo" / "copia.pdf", PDF)),
            local_present=True,
            external_present=True,
        )

        manifest = self.create_backup(self.out / "backup.zip")

        self.assertEqual(manifest.file_count, 1)
        self.assertEqual(manifest.sources["local"], 1)
        self.assertEqual(manifest.sources["external"], 0)


class RestoreRoundTripTests(BackupTestCase):
    """CR-19: a backup is only a backup when it restores, verified."""

    def restore_module(self):
        global _RESTORE_MODULE
        if _RESTORE_MODULE is None:
            path = REPO_ROOT / "scripts" / "restore-backup.py"
            spec = importlib.util.spec_from_file_location("restore_backup_cli", path)
            if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
                raise AssertionError(f"cannot load {path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(spec.name, None)
                raise
            _RESTORE_MODULE = module
        return _RESTORE_MODULE

    def valid_backup(self) -> tuple[Path, str]:
        sha = self.store_blob(PDF)
        self.register_document(sha)
        destination = self.out / "backup.zip"
        self.create_backup(destination)
        return destination, sha

    def test_a_backup_restores_into_a_fresh_data_root(self):
        destination, sha = self.valid_backup()
        target = self.tmp / "restaurado"
        module = self.restore_module()

        plan = module.plan_restore(destination, target)
        self.assertTrue(plan.ok, plan.problems)
        self.assertFalse(plan.target_exists)

        result = module.apply_restore(destination, target)

        self.assertTrue(result["applied"])
        self.assertEqual(result["blobs_present"], 1)
        self.assertEqual(result["blobs_absent"], 0)
        self.assertEqual(
            (target / "archive" / "blobs" / sha[:2] / f"{sha}.pdf").read_bytes(), PDF
        )
        store = Store.open(target / "atos-tce.db")
        try:
            self.assertEqual(store.schema_version, SCHEMA_VERSION)
            self.assertEqual(len(store.list_processes()), 1)
        finally:
            store.close()

    def test_a_dry_run_writes_nothing(self):
        destination, _sha = self.valid_backup()
        target = self.tmp / "restaurado"

        plan = self.restore_module().plan_restore(destination, target)

        self.assertTrue(plan.ok, plan.problems)
        self.assertFalse(target.exists())

    def test_restore_refuses_a_non_empty_target_without_the_flag(self):
        destination, _sha = self.valid_backup()
        target = self.tmp / "restaurado"
        write(target / "algo.txt", b"conteudo")
        module = self.restore_module()

        with self.assertRaises(module.RestoreError):
            module.apply_restore(destination, target)

        result = module.apply_restore(destination, target, allow_non_empty=True)

        self.assertTrue(Path(result["previous_data_root"]).is_dir())
        self.assertEqual(
            (Path(result["previous_data_root"]) / "algo.txt").read_bytes(), b"conteudo"
        )

    def test_a_blob_member_that_does_not_match_its_name_is_refused(self):
        destination, _sha = self.valid_backup()
        broken = self.out / "corrompido.zip"
        with zipfile.ZipFile(destination) as source, zipfile.ZipFile(broken, "w") as target:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename.endswith(".pdf"):
                    payload = payload[:-1] + b"X"
                target.writestr(info, payload)

        with self.assertRaises(self.restore_module().RestoreError) as context:
            self.restore_module().plan_restore(broken, self.tmp / "destino")

        self.assertIn("não confere com o próprio sha", str(context.exception))

    def test_a_member_that_escapes_the_target_is_refused(self):
        archive = self.out / "mau.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("../escaped.txt", b"x")
            handle.writestr("manifest.json", json.dumps({"manifest_version": 1}))

        with self.assertRaises(self.restore_module().RestoreError) as context:
            self.restore_module().plan_restore(archive, self.tmp / "destino")

        self.assertIn("caminho inválido", str(context.exception))

    def test_a_backup_without_a_manifest_is_refused(self):
        archive = self.out / "sem-manifest.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("atos-tce.db", b"nao e sqlite")

        with self.assertRaises(self.restore_module().RestoreError) as context:
            self.restore_module().plan_restore(archive, self.tmp / "destino")

        self.assertIn("manifest.json", str(context.exception))

    def test_a_truncated_zip_is_refused(self):
        destination, _sha = self.valid_backup()
        truncated = self.out / "truncado.zip"
        truncated.write_bytes(destination.read_bytes()[:200])

        with self.assertRaises(self.restore_module().RestoreError):
            self.restore_module().plan_restore(truncated, self.tmp / "destino")


class BackupRefusalTests(BackupTestCase):
    def test_backup_refuses_a_destination_inside_the_archive_tree(self):
        self.store_blob(PDF)
        target = self.data / "archive" / "backup.zip"

        with self.assertRaises(backup_module().BackupError):
            self.create_backup(target)

        self.assertFalse(target.exists())

    def test_backup_requires_an_existing_database(self):
        empty = self.tmp / "sem-banco"
        empty.mkdir()

        with self.assertRaises(backup_module().BackupError):
            backup_module().create_backup(empty, self.out / "backup.zip")

        self.assertFalse((self.out / "backup.zip").exists())
        self.assertEqual(list(self.out.iterdir()), [])

    def test_backup_fails_closed_when_the_destination_is_a_directory(self):
        self.store_blob(PDF)
        destination = self.out / "backup.zip"
        destination.mkdir()

        with self.assertRaises(backup_module().BackupError):
            self.create_backup(destination)

        self.assertEqual([path.name for path in self.out.iterdir()], ["backup.zip"])


class BackupCliTests(BackupTestCase):
    def test_cli_requires_the_output_argument(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--data-root", str(self.data)],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--output", result.stderr)

    def test_cli_writes_the_backup_and_reports_the_manifest(self):
        sha = self.store_blob(PDF)
        self.register_document(sha)
        destination = self.out / "backup.zip"

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--data-root",
                str(self.data),
                "--output",
                str(destination),
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["file_count"], 1)
        self.assertEqual(manifest["blob_sha256"], [sha])
        self.assertTrue(destination.is_file())

    def test_cli_refuses_an_archive_destination_with_a_clear_error(self):
        self.store_blob(PDF)
        target = self.data / "archive" / "backup.zip"

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--data-root",
                str(self.data),
                "--output",
                str(target),
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("archive", result.stderr)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
