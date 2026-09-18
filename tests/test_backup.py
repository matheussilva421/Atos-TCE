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
