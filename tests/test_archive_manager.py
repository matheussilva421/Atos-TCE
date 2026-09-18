"""Tests for the hybrid archive manager (M6 Task 2)."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.archive.legacy_import import blob_path, sha256_file
from app.archive.manager import EXTERNAL_ROOT_KEY, ArchiveError, ArchiveManager
from app.core.models import DocumentRecord, ProcessRecord
from app.core.store import SCHEMA_VERSION, Store

PDF = b"%PDF-1.4\narchive fixture\n%%EOF\n"


class ArchiveTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.data_root = self.tmp / "data"
        self.external_root = self.tmp / "acervo-externo"
        self.store = Store.open(self.data_root / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.manager = ArchiveManager(self.store, self.data_root, external_root=self.external_root)

    def make_process(self, *, payload=None, name="102390/2026"):
        """One canonical blob plus a hardlinked process view, as M1 leaves it."""

        process_id = self.store.upsert_process(
            ProcessRecord(
                process_key=name,
                interested="Pessoa Exemplo",
                interested_normalized="pessoa exemplo",
                status="CONCLUÍDO",
            )
        )
        body = payload if payload is not None else PDF + name.encode()
        digest = sha256_from(body)
        blob = blob_path(self.data_root, digest)
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(body)
        view_rel = f"archive/processos/{name.replace('/', '-')}/Ato.pdf"
        view = self.data_root / view_rel
        view.parent.mkdir(parents=True, exist_ok=True)
        view.write_bytes(body)
        view.unlink()
        try:
            view.hardlink_to(blob)
        except OSError:  # pragma: no cover - filesystem without hardlinks
            view.write_bytes(body)
        self.store.replace_documents(
            process_id,
            [
                DocumentRecord(
                    source_id=f"{name}|1|Ato",
                    title="Ato.pdf",
                    relative_path=view_rel,
                    sha256=digest,
                    page_count=1,
                    event="1",
                    storage_state="HOT",
                )
            ],
        )
        return process_id, digest, blob, view


def sha256_from(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


class ArchiveProcessTests(ArchiveTestCase):
    def test_archiving_verifies_the_external_copy_then_frees_local_bytes(self):
        process_id, digest, blob, view = self.make_process()

        result = self.manager.archive_process(process_id)

        self.assertTrue(result.ok, result.errors)
        external = self.external_root / "blobs" / digest[:2] / f"{digest}.pdf"
        self.assertTrue(external.is_file())
        self.assertEqual(sha256_file(external), digest)
        self.assertFalse(view.exists(), "the process view link must be gone")
        self.assertFalse(blob.exists(), "the canonical blob is external-only now")
        documents = self.store.list_documents(process_id)
        self.assertEqual(documents[0]["storage_state"], "ARCHIVED")
        row = self.store.get_archive_blob(digest)
        self.assertEqual(row["external_present"], 1)
        self.assertEqual(row["local_present"], 0)
        self.assertTrue(row["verified_at"])

    def test_a_shared_blob_survives_while_another_document_is_hot(self):
        shared = PDF + b"shared"
        first, digest, _blob, _view = self.make_process(payload=shared, name="102390/2026")
        second = self.store.upsert_process(
            ProcessRecord(
                process_key="102391/2026",
                interested="Outra Pessoa",
                interested_normalized="outra pessoa",
                status="CONCLUÍDO",
            )
        )
        blob = blob_path(self.data_root, digest)
        self.store.replace_documents(
            second,
            [
                DocumentRecord(
                    source_id="102391/2026|1|Ato",
                    title="Ato.pdf",
                    relative_path="archive/processos/102391-2026/Ato.pdf",
                    sha256=digest,
                    page_count=1,
                )
            ],
        )

        result = self.manager.archive_process(first)

        self.assertTrue(result.ok, result.errors)
        self.assertTrue(blob.is_file(), "a HOT document still needs these bytes")
        self.assertEqual(self.store.get_archive_blob(digest)["local_present"], 1)
        self.assertEqual(self.store.list_documents(second)[0]["storage_state"], "HOT")

    def test_archiving_without_a_configured_root_is_refused(self):
        process_id, _digest, _blob, _view = self.make_process()
        manager = ArchiveManager(self.store, self.data_root)

        with self.assertRaises(ArchiveError):
            manager.archive_process(process_id)

    def test_a_failed_copy_leaves_the_local_copy_hot(self):
        process_id, digest, blob, view = self.make_process()
        # Point the external root at a path that cannot be created.
        self.manager = ArchiveManager(
            self.store, self.data_root, external_root=self.tmp / "arquivo.txt" / "blobs"
        )
        (self.tmp / "arquivo.txt").write_text("não é um diretório", encoding="utf-8")

        result = self.manager.archive_process(process_id)

        self.assertFalse(result.ok)
        self.assertTrue(result.errors)
        self.assertTrue(blob.is_file())
        self.assertTrue(view.exists())
        self.assertEqual(self.store.list_documents(process_id)[0]["storage_state"], "HOT")


class RestoreAndReconcileTests(ArchiveTestCase):
    def archive(self, process_id):
        result = self.manager.archive_process(process_id)
        self.assertTrue(result.ok, result.errors)

    def test_restore_brings_the_bytes_and_the_view_back(self):
        process_id, digest, blob, view = self.make_process()
        self.archive(process_id)

        result = self.manager.restore_process(process_id)

        self.assertTrue(result.ok, result.errors)
        self.assertTrue(blob.is_file())
        self.assertEqual(sha256_file(blob), digest)
        self.assertTrue(view.is_file())
        self.assertTrue(__import__("os").path.samefile(view, blob), "the view is a hardlink again")
        self.assertEqual(self.store.list_documents(process_id)[0]["storage_state"], "HOT")
        self.assertEqual(self.store.get_archive_blob(digest)["local_present"], 1)

    def test_restoring_without_any_copy_marks_the_document_missing(self):
        process_id, digest, blob, _view = self.make_process()
        self.archive(process_id)
        (self.external_root / "blobs" / digest[:2] / f"{digest}.pdf").unlink()

        result = self.manager.restore_process(process_id)

        self.assertFalse(result.ok)
        self.assertIn(digest, result.missing)
        self.assertEqual(self.store.list_documents(process_id)[0]["storage_state"], "MISSING")

    def test_reconcile_marks_missing_only_without_any_verified_location(self):
        hot_id, hot_digest, _blob, _view = self.make_process(name="102390/2026")
        archived_id, archived_digest, _blob, _view = self.make_process(name="102391/2026")
        self.archive(archived_id)

        summary = self.manager.reconcile_locations()

        self.assertEqual(summary["hot"], 1)
        self.assertEqual(summary["archived"], 1)
        self.assertEqual(summary["missing"], 0)
        self.assertEqual(self.store.list_documents(hot_id)[0]["storage_state"], "HOT")
        self.assertEqual(
            self.store.list_documents(archived_id)[0]["storage_state"], "ARCHIVED"
        )

        # Removing both copies is the only way a document becomes MISSING.
        external = self.external_root / "blobs" / archived_digest[:2] / f"{archived_digest}.pdf"
        external.unlink()
        summary = self.manager.reconcile_locations()

        self.assertEqual(self.store.list_documents(archived_id)[0]["storage_state"], "MISSING")
        self.assertEqual(summary["missing"], 1)

    def test_reconcile_returns_a_hot_document_to_hot(self):
        process_id, _digest, blob, _view = self.make_process()
        self.archive(process_id)
        # Simulate an out-of-band restore of the canonical blob.
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(PDF + b"102390/2026")

        self.manager.reconcile_locations()

        self.assertEqual(self.store.list_documents(process_id)[0]["storage_state"], "HOT")


class ArchiveSchemaTests(ArchiveTestCase):
    def test_the_store_reports_the_current_schema(self):
        self.assertEqual(self.store.schema_version, SCHEMA_VERSION)
        self.assertEqual(SCHEMA_VERSION, 6)

    def test_the_external_root_is_configured_through_metadata(self):
        manager = ArchiveManager(self.store, self.data_root)
        self.assertIsNone(manager.external_root)

        configured = manager.configure_external_root(self.external_root)

        self.assertEqual(configured, self.external_root.resolve())
        self.assertEqual(manager.external_root, self.external_root.resolve())
        self.assertEqual(
            self.store.get_metadata(EXTERNAL_ROOT_KEY), str(self.external_root.resolve())
        )

    def test_migration_registers_existing_documents_as_blobs(self):
        """The migration registers what a v4 database already had."""

        import sqlite3

        from app.core.store import SCHEMA_V1, SCHEMA_V2, SCHEMA_V3, SCHEMA_V4

        digest = sha256_from(PDF)
        database = self.tmp / "legado.db"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        for statement in (*SCHEMA_V1, *SCHEMA_V2, *SCHEMA_V3, *SCHEMA_V4):
            connection.execute(statement)
        connection.execute("INSERT INTO metadata (key, value) VALUES ('schema_version', '4')")
        connection.execute(
            "INSERT INTO processes (process_key, interested, interested_normalized, status, created_at, updated_at) "
            "VALUES ('102390/2026', 'Pessoa Exemplo', 'pessoa exemplo', 'HOT', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO documents (process_id, source_id, title, relative_path, sha256, page_count, storage_state) "
            "VALUES (1, 'doc-1', 'Ato.pdf', 'archive/processos/102390-2026/Ato.pdf', ?, 1, 'HOT')",
            (digest,),
        )
        connection.commit()
        connection.close()

        migrated = Store.open(database)
        try:
            self.assertEqual(migrated.schema_version, SCHEMA_VERSION)
            rows = migrated.list_archive_blobs()
        finally:
            migrated.close()

        self.assertEqual([row["sha256"] for row in rows], [digest])
        self.assertEqual(rows[0]["local_relative_path"], f"archive/blobs/{digest[:2]}/{digest}.pdf")
        # Presence is verified by the reconciler, never assumed by the migration.
        self.assertEqual(rows[0]["local_present"], 0)


if __name__ == "__main__":
    unittest.main()
