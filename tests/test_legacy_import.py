"""Tests for the safe legacy archive import and SHA-256 deduplication (M1 Task 3)."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.archive.legacy_import import (
    canonicalize_process_tree,
    import_legacy_archive,
    scan_legacy_archive,
    sha256_file,
)
from app.core.identity import normalize_interested
from app.core.store import Store

PDF = b"%PDF-1.4\nfixture\n%%EOF\n"
OTHER_PDF = b"%PDF-1.4\nother fixture\n%%EOF\n"
REPO_ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def make_directory_link(target: Path, link: Path) -> bool:
    """Create a directory link, trying a symlink first and a junction second.

    Windows junctions need no administrator rights, so the importer's
    reparse-point guard is exercised on an ordinary developer machine too.
    """

    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and link.exists()


class LegacyFixtureTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "legacy"
        self.data = self.tmp / "data"
        self.store = None

    def tearDown(self):
        if self.store is not None:
            self.store.close()

    def open_store(self) -> Store:
        self.store = Store.open(self.data / "atos-tce.db")
        return self.store

    def add_interest_index(self, records):
        write_json(
            self.root / "dados-complementar-ato.json",
            {"schema_version": 1, "records": records},
        )


class LegacyDeduplicationTests(LegacyFixtureTestCase):
    def test_duplicate_pdf_is_materialized_once(self):
        a = write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)
        b = write(self.root / "processos" / "102391-2026" / "b.pdf", PDF)
        store = self.open_store()

        report = import_legacy_archive(self.root, self.data, store, apply=True)

        self.assertTrue(a.exists())
        self.assertTrue(b.exists())
        self.assertEqual(report.unique_pdfs, 1)
        self.assertEqual(report.duplicate_pdfs, 1)
        self.assertEqual(report.copied_files, 1)
        self.assertEqual(report.errors, [])

        digest = sha256_file(a)
        blob = self.data / "archive" / "blobs" / digest[:2] / f"{digest}.pdf"
        self.assertTrue(blob.is_file())
        self.assertEqual(len(list((self.data / "archive" / "blobs").rglob("*.pdf"))), 1)

    def test_process_view_is_hardlinked_to_the_canonical_blob(self):
        a = write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)

        report = import_legacy_archive(self.root, self.data, self.open_store(), apply=True)

        digest = sha256_file(a)
        blob = self.data / "archive" / "blobs" / digest[:2] / f"{digest}.pdf"
        view = self.data / "archive" / "processos" / "102390-2026" / "a.pdf"
        self.assertTrue(os.path.samefile(view, blob))
        self.assertEqual(report.hardlinked_files, 1)
        self.assertEqual(report.fallback_copies, 0)

    def test_source_archive_is_never_modified(self):
        a = write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)
        before = (sha256_file(a), a.stat().st_size, a.stat().st_mtime_ns)

        import_legacy_archive(self.root, self.data, self.open_store(), apply=True)

        after = (sha256_file(a), a.stat().st_size, a.stat().st_mtime_ns)
        self.assertEqual(before, after)

    def test_dry_run_materializes_nothing(self):
        write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)
        store = self.open_store()

        report = import_legacy_archive(self.root, self.data, store, apply=False)

        self.assertEqual(report.mode, "dry-run")
        self.assertEqual(report.unique_pdfs, 1)
        self.assertEqual(report.copied_files, 0)
        self.assertFalse((self.data / "archive").exists())
        self.assertEqual(store.list_processes(), [])


class LegacyMetadataTests(LegacyFixtureTestCase):
    def test_process_key_and_interested_come_from_index_metadata(self):
        write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)
        self.add_interest_index(
            [
                {
                    "process": {"key": "102390/2026", "number": "102390", "year": "2026"},
                    "interested": {
                        "original": "FERNANDO DE PAIVA FERREIRA",
                        "normalized": "fernando de paiva ferreira",
                    },
                    "status": "partial",
                }
            ]
        )
        store = self.open_store()

        import_legacy_archive(self.root, self.data, store, apply=True)

        processes = store.list_processes()
        self.assertEqual(len(processes), 1)
        self.assertEqual(processes[0]["process_key"], "102390/2026")
        self.assertEqual(processes[0]["interested"], "FERNANDO DE PAIVA FERREIRA")
        self.assertEqual(processes[0]["interested_normalized"], "fernando de paiva ferreira")
        self.assertEqual(processes[0]["status"], "PENDENTE")

        events = store.get_process(processes[0]["id"])["events"]
        self.assertEqual(events[0]["event_type"], "legacy_import")
        self.assertEqual(events[0]["payload"]["legacy_status"], "partial")

    def test_accented_interested_name_is_normalized_canonically(self):
        write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)
        self.add_interest_index(
            [
                {
                    "process": {"key": "102390/2026"},
                    "interested": {"original": "José  D'Ávila  Conceição", "normalized": "jose d'avila conceicao"},
                    "status": "partial",
                }
            ]
        )
        store = self.open_store()

        import_legacy_archive(self.root, self.data, store, apply=True)

        self.assertEqual(store.list_processes()[0]["interested_normalized"], "jose d'avila conceicao")

    def test_two_interested_records_share_the_same_documents(self):
        write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)
        self.add_interest_index(
            [
                {
                    "process": {"key": "102390/2026"},
                    "interested": {"original": "Pessoa Um", "normalized": "pessoa um"},
                    "status": "partial",
                },
                {
                    "process": {"key": "102390/2026"},
                    "interested": {"original": "Pessoa Dois", "normalized": "pessoa dois"},
                    "status": "partial",
                },
            ]
        )
        store = self.open_store()

        report = import_legacy_archive(self.root, self.data, store, apply=True)

        processes = store.list_processes()
        self.assertEqual(len(processes), 2)
        self.assertEqual(report.processes_upserted, 2)
        for process in processes:
            self.assertEqual(len(store.get_process(process["id"])["documents"]), 1)
        self.assertEqual(report.unique_pdfs, 1)
        self.assertEqual(report.copied_files, 1)

    def test_process_without_interest_record_stays_visible(self):
        write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)
        store = self.open_store()

        report = import_legacy_archive(self.root, self.data, store, apply=True)

        processes = store.list_processes()
        self.assertEqual(len(processes), 1)
        self.assertEqual(processes[0]["process_key"], "102390/2026")
        self.assertEqual(processes[0]["interested_normalized"], normalize_interested(processes[0]["interested"]))
        self.assertTrue(any("no interested record" in warning for warning in report.warnings))

    def test_document_metadata_comes_from_the_target_manifest(self):
        write(
            self.root / "processos" / "102390-2026" / "evento-0008-7439700" / "documento-001-Ato.pdf",
            PDF,
        )
        relative = "processos/102390-2026/evento-0008-7439700/documento-001-Ato.pdf"
        write_json(
            self.root / "pdfs-alvo-manifest.json",
            {
                "version": 1,
                "processes": [
                    {
                        "process": "102390/2026",
                        "documents": [
                            {
                                "event": "8",
                                "title": "Documento_Processo_Portal_Gestor",
                                "classification": "resolucao_administrativa",
                                "sha256": sha256_file(
                                    self.root
                                    / "processos"
                                    / "102390-2026"
                                    / "evento-0008-7439700"
                                    / "documento-001-Ato.pdf"
                                ),
                                "page_count": 4,
                                "relative_path": relative,
                                "pdf_path": relative,
                                "id": "informacao-3305567",
                            }
                        ],
                    }
                ],
            },
        )
        self.add_interest_index(
            [
                {
                    "process": {"key": "102390/2026"},
                    "interested": {"original": "Pessoa Um", "normalized": "pessoa um"},
                    "status": "partial",
                }
            ]
        )
        store = self.open_store()

        import_legacy_archive(self.root, self.data, store, apply=True)

        document = store.list_processes()[0]
        documents = store.get_process(document["id"])["documents"]
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["source_id"], "102390/2026|8|informacao-3305567")
        self.assertEqual(documents[0]["title"], "Documento_Processo_Portal_Gestor")
        self.assertEqual(documents[0]["event"], "8")
        self.assertEqual(documents[0]["classification"], "resolucao_administrativa")
        self.assertEqual(documents[0]["page_count"], 4)
        self.assertEqual(documents[0]["storage_state"], "HOT")
        self.assertEqual(
            documents[0]["relative_path"],
            "archive/processos/102390-2026/evento-0008-7439700/documento-001-Ato.pdf",
        )

    def test_manifest_hash_mismatch_warns_but_uses_the_real_file_hash(self):
        target = write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)
        write_json(
            self.root / "pdfs-alvo-manifest.json",
            {
                "version": 1,
                "processes": [
                    {
                        "process": "102390/2026",
                        "documents": [
                            {
                                "event": "1",
                                "title": "Ato",
                                "sha256": "b" * 64,
                                "page_count": 1,
                                "pdf_path": "processos/102390-2026/a.pdf",
                                "id": "informacao-1",
                            }
                        ],
                    }
                ],
            },
        )
        store = self.open_store()

        report = import_legacy_archive(self.root, self.data, store, apply=True)

        self.assertTrue(any("differs from the file hash" in warning for warning in report.warnings))
        documents = store.get_process(store.list_processes()[0]["id"])["documents"]
        self.assertEqual(documents[0]["sha256"], sha256_file(target))

    def test_event_folder_without_manifest_is_derived_from_the_path(self):
        write(
            self.root / "processos" / "102390-2026" / "evento-0003-7047391" / "documento-002-Parecer.pdf",
            PDF,
        )
        store = self.open_store()

        import_legacy_archive(self.root, self.data, store, apply=True)

        documents = store.get_process(store.list_processes()[0]["id"])["documents"]
        self.assertEqual(documents[0]["event"], "3")
        self.assertEqual(documents[0]["title"], "Parecer")

    def test_receipt_is_written_under_data_logs(self):
        write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)

        report = import_legacy_archive(self.root, self.data, self.open_store(), apply=True)

        receipt = Path(report.receipt_path)
        self.assertTrue(receipt.is_file())
        self.assertTrue(receipt.parent == self.data / "logs")
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(payload["mode"], "apply")
        self.assertEqual(payload["unique_pdfs"], 1)
        self.assertEqual(payload["schema_version"], 1)


class LegacySafetyTests(LegacyFixtureTestCase):
    def test_repeat_apply_is_idempotent(self):
        write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)
        store = self.open_store()

        first = import_legacy_archive(self.root, self.data, store, apply=True)
        second = import_legacy_archive(self.root, self.data, store, apply=True)

        self.assertEqual(first.unique_pdfs, second.unique_pdfs)
        self.assertEqual(second.copied_files, 0)
        self.assertEqual(second.verified_blobs, 1)
        self.assertEqual(len(store.list_processes()), 1)
        self.assertEqual(len(list((self.data / "archive" / "blobs").rglob("*.pdf"))), 1)

    def test_blobs_directory_is_never_scanned_as_a_source(self):
        write(self.root / "processos" / "102390-2026" / "blobs" / "ignored.pdf", PDF)
        write(self.root / "processos" / "102390-2026" / "kept.pdf", PDF)

        scan = scan_legacy_archive(self.root)

        names = [document.source_path.name for document in scan.processes[0].documents]
        self.assertEqual(names, ["kept.pdf"])

    def test_linked_directory_is_not_followed(self):
        outside = self.tmp / "outside"
        write(outside / "escape.pdf", PDF)
        write(self.root / "processos" / "102390-2026" / "kept.pdf", PDF)
        link = self.root / "processos" / "102390-2026" / "linked"
        if not make_directory_link(outside, link):  # pragma: no cover - host dependent
            self.skipTest("this host refuses to create a directory link")

        scan = scan_legacy_archive(self.root)

        names = [document.source_path.name for document in scan.processes[0].documents]
        self.assertEqual(names, ["kept.pdf"])

    def test_missing_process_tree_fails_loudly(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(Exception) as context:
            scan_legacy_archive(self.root)
        self.assertIn("process tree", str(context.exception))


class CanonicalizeProcessTreeTests(LegacyFixtureTestCase):
    def test_newly_downloaded_bytes_move_into_the_blob_store(self):
        process_view = self.data / "archive" / "processos" / "102390-2026" / "novo.pdf"
        write(process_view, PDF)
        store = self.open_store()
        digest = sha256_file(process_view)

        report = canonicalize_process_tree(self.data, store)

        blob = self.data / "archive" / "blobs" / digest[:2] / f"{digest}.pdf"
        self.assertTrue(blob.is_file())
        self.assertTrue(os.path.samefile(process_view, blob))
        self.assertEqual(report.moved_files, 1)
        self.assertEqual(report.hardlinked_files, 1)
        self.assertEqual(sha256_file(blob), digest)

    def test_second_identical_download_reuses_the_known_blob(self):
        first = self.data / "archive" / "processos" / "102390-2026" / "a.pdf"
        second = self.data / "archive" / "processos" / "102391-2026" / "b.pdf"
        write(first, PDF)
        write(second, PDF)

        report = canonicalize_process_tree(self.data, None)

        digest = sha256_file(first)
        blob = self.data / "archive" / "blobs" / digest[:2] / f"{digest}.pdf"
        self.assertEqual(report.moved_files, 1)
        self.assertEqual(report.reused_blobs, 1)
        self.assertTrue(os.path.samefile(first, blob))
        self.assertTrue(os.path.samefile(second, blob))
        self.assertEqual(len(list((self.data / "archive" / "blobs").rglob("*.pdf"))), 1)

    def test_never_touches_files_outside_the_process_tree(self):
        outside = self.data / "archive" / "fora-do-processos" / "x.pdf"
        write(outside, PDF)

        canonicalize_process_tree(self.data, None)

        self.assertTrue(outside.is_file())
        self.assertFalse((self.data / "archive" / "blobs").exists())

    def test_reports_process_view_paths_missing_from_sqlite(self):
        write(self.data / "archive" / "processos" / "102390-2026" / "a.pdf", PDF)

        report = canonicalize_process_tree(self.data, self.open_store())

        self.assertEqual(report.unreferenced, ["archive/processos/102390-2026/a.pdf"])


class MigrateLegacyCliTests(LegacyFixtureTestCase):
    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "migrate-legacy.py"), *arguments],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_cli_defaults_to_dry_run(self):
        write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)

        result = self.run_cli("--archive-root", str(self.root), "--data-root", str(self.data))

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["documents_seen"], 1)
        self.assertFalse((self.data / "archive").exists())

    def test_cli_apply_requires_the_flag(self):
        write(self.root / "processos" / "102390-2026" / "a.pdf", PDF)

        result = self.run_cli(
            "--archive-root", str(self.root), "--data-root", str(self.data), "--apply"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "apply")
        self.assertEqual(payload["copied_files"], 1)
        self.assertTrue((self.data / "archive" / "processos").is_dir())


if __name__ == "__main__":
    unittest.main()
