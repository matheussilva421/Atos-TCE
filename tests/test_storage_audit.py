"""Storage audit tests for canonical bytes and the historical trees (M6 Task 3)."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.models import DocumentRecord, ProcessRecord
from app.core.store import Store

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "storage-audit.py"

PDF = b"%PDF-1.4\ncanonical fixture\n%%EOF\n"
OTHER_PDF = b"%PDF-1.4\nunique fixture\n%%EOF\n"
THIRD_PDF = b"%PDF-1.4\nthird fixture\n%%EOF\n"

_MODULE = None


def audit_module():
    """Load the hyphenated CLI script so the audit can be driven in-process."""

    global _MODULE
    if _MODULE is None:
        spec = importlib.util.spec_from_file_location("storage_audit_cli", SCRIPT_PATH)
        if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
            raise AssertionError(f"cannot load {SCRIPT_PATH}")
        module = importlib.util.module_from_spec(spec)
        # dataclasses resolve ``__module__`` through ``sys.modules``, so the
        # module has to be registered before it is executed.
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


def make_directory_link(target: Path, link: Path) -> bool:
    """Create a directory link, trying a symlink first and a junction second."""

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


class StorageAuditTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = self.tmp / "repo"
        self.data = self.repo / "data"
        (self.repo / "app").mkdir(parents=True)
        (self.data / "archive" / "blobs").mkdir(parents=True)

    def store_blob(self, payload: bytes) -> str:
        value = digest(payload)
        write(self.data / "archive" / "blobs" / value[:2] / f"{value}.pdf", payload)
        return value

    def run_audit(self, **kwargs):
        return audit_module().audit_storage(self.repo, self.data, **kwargs)

    def candidate(self, audit, relative: str):
        wanted = relative.replace("\\", "/")
        for item in audit.candidates:
            if item.relative_path == wanted:
                return item
        self.fail(
            f"candidate {wanted!r} missing from {[item.relative_path for item in audit.candidates]}"
        )

    def category(self, audit, name: str):
        for item in audit.categories:
            if item.category == name:
                return item
        self.fail(f"category {name!r} missing from the report")


class CandidateSafetyTests(StorageAuditTestCase):
    def test_duplicate_pdf_is_reclaimable_and_unique_pdf_blocks_deletion(self):
        self.store_blob(PDF)
        write(self.repo / "Versions" / "old" / "a.pdf", PDF)
        write(self.repo / "Versions" / "old" / "sub" / "b.pdf", OTHER_PDF)

        versions = self.candidate(self.run_audit(), "Versions")

        self.assertTrue(versions.exists)
        self.assertEqual(versions.category, "versions")
        self.assertEqual(versions.loose_pdf_count, 2)
        self.assertEqual(versions.reclaimable_pdf_count, 1)
        self.assertEqual(versions.reclaimable_pdf_bytes, len(PDF))
        self.assertEqual(versions.unique_pdf_count, 1)
        self.assertEqual(versions.missing_from_canonical_sha256, (digest(OTHER_PDF),))
        self.assertIn("unique_pdfs", versions.reasons)
        self.assertFalse(versions.safe_to_delete)

    def test_tree_with_only_canonical_copies_is_safe_to_delete(self):
        self.store_blob(PDF)
        write(self.repo / "Versions" / "old" / "a.pdf", PDF)
        write(self.repo / "Versions" / "old" / "b.pdf", PDF)

        versions = self.candidate(self.run_audit(), "Versions")

        self.assertEqual(versions.unique_pdf_count, 0)
        self.assertEqual(versions.missing_from_canonical_sha256, ())
        self.assertEqual(versions.reasons, ())
        self.assertTrue(versions.safe_to_delete)

    def test_repeated_unique_pdf_is_counted_once(self):
        write(self.repo / "outputs" / "pkg" / "b.pdf", OTHER_PDF)
        write(self.repo / "outputs" / "pkg" / "copia" / "b-again.pdf", OTHER_PDF)

        outputs = self.candidate(self.run_audit(), "outputs")

        self.assertEqual(outputs.loose_pdf_count, 2)
        self.assertEqual(outputs.unique_pdf_count, 1)
        self.assertEqual(outputs.unique_pdf_bytes, len(OTHER_PDF))

    def test_absent_candidate_is_reported_as_absent(self):
        versions = self.candidate(self.run_audit(), "Versions")

        self.assertFalse(versions.exists)
        self.assertEqual(versions.file_count, 0)
        self.assertEqual(versions.bytes, 0)
        self.assertFalse(versions.safe_to_delete)
        self.assertIn("directory_absent", versions.reasons)

    def test_protected_trees_are_never_candidates(self):
        self.store_blob(PDF)
        write(self.data / "archive" / "processos" / "100015-2026" / "a.pdf", PDF)
        write(self.repo / "app" / "web" / "asset.pdf", OTHER_PDF)
        write(self.repo / "docs" / "nota.pdf", THIRD_PDF)

        audit = self.run_audit()
        paths = {item.relative_path for item in audit.candidates}

        for protected in ("data", "data/archive", "app", "app/web", "docs"):
            self.assertNotIn(protected, paths)
        self.assertGreaterEqual(self.category(audit, "canonical_data").bytes, 2 * len(PDF))
        self.assertGreaterEqual(
            self.category(audit, "source").bytes, len(OTHER_PDF) + len(THIRD_PDF)
        )

    def test_staging_directories_are_candidates(self):
        self.store_blob(PDF)
        write(self.repo / "staging-2026-09-18" / "a.pdf", PDF)
        write(self.repo / "work" / ".package-staging-r3" / "b.pdf", OTHER_PDF)

        audit = self.run_audit()
        root_staging = self.candidate(audit, "staging-2026-09-18")
        work_staging = self.candidate(audit, "work/.package-staging-r3")

        self.assertEqual(root_staging.category, "staging")
        self.assertTrue(root_staging.safe_to_delete)
        self.assertEqual(work_staging.category, "staging")
        self.assertFalse(work_staging.safe_to_delete)


class CategoryAccountingTests(StorageAuditTestCase):
    def test_categories_classify_the_repository_trees(self):
        self.store_blob(PDF)
        write(self.repo / "Versions" / "ref" / "a.pdf", PDF)
        write(self.repo / "outputs" / "pkg" / "old.pdf", PDF)
        write(self.repo / "tmp" / "scratch.bin", b"x" * 10)
        write(self.repo / "work" / "tce-extractor" / "acervo-tce" / "origem" / "a.pdf", PDF)
        write(self.repo / "work" / "tce-extractor" / "portable" / "app" / "menu.ps1", b"# menu")
        write(self.repo / "work" / "tce-extractor" / "outputs" / "old.zip", b"PK")
        write(self.repo / "dados-locais" / "perfil" / "Cache" / "x.bin", b"y" * 5)

        audit = self.run_audit()

        self.assertEqual(self.category(audit, "canonical_data").file_count, 1)
        self.assertEqual(self.category(audit, "versions").file_count, 1)
        self.assertEqual(self.category(audit, "outputs").file_count, 2)
        self.assertEqual(self.category(audit, "temp").file_count, 1)
        self.assertEqual(self.category(audit, "legacy_archive").file_count, 1)
        self.assertEqual(self.category(audit, "source").file_count, 1)
        self.assertEqual(self.category(audit, "unknown").file_count, 1)
        self.assertEqual(self.category(audit, "dist").file_count, 0)

    def test_category_bytes_are_relative_and_add_up_to_the_scanned_total(self):
        self.store_blob(PDF)
        write(self.repo / "outputs" / "pkg" / "old.pdf", OTHER_PDF)
        write(self.repo / "Versions" / "ref" / "old.pdf", THIRD_PDF)

        audit = self.run_audit()
        total = sum(item.bytes for item in audit.categories)

        self.assertEqual(total, len(PDF) + len(OTHER_PDF) + len(THIRD_PDF))
        for item in audit.categories:
            self.assertNotIn(":", item.category)
        for item in audit.candidates:
            self.assertNotIn(":\\", item.relative_path)


class ArchiveVerificationTests(StorageAuditTestCase):
    def make_zip(self, path: Path, members: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)
        return path

    def test_zip_members_are_verified_against_canonical(self):
        self.store_blob(PDF)
        self.make_zip(self.repo / "outputs" / "pkg" / "lote.zip", {"a.pdf": PDF, "b.pdf": OTHER_PDF})

        outputs = self.candidate(self.run_audit(), "outputs")

        self.assertEqual(outputs.archive_count, 1)
        self.assertEqual(outputs.archive_pdf_count, 2)
        self.assertEqual(outputs.loose_pdf_count, 0)
        self.assertEqual(outputs.reclaimable_pdf_count, 1)
        self.assertEqual(outputs.unique_pdf_count, 1)
        self.assertEqual(outputs.missing_from_canonical_sha256, (digest(OTHER_PDF),))
        self.assertFalse(outputs.safe_to_delete)

    def test_zip_with_only_canonical_members_is_safe(self):
        self.store_blob(PDF)
        self.store_blob(OTHER_PDF)
        self.make_zip(self.repo / "outputs" / "pkg" / "lote.zip", {"a.pdf": PDF, "b.pdf": OTHER_PDF})

        outputs = self.candidate(self.run_audit(), "outputs")

        self.assertEqual(outputs.unique_pdf_count, 0)
        self.assertEqual(outputs.reasons, ())
        self.assertTrue(outputs.safe_to_delete)

    def test_zip_with_nested_archive_blocks_deletion(self):
        self.store_blob(PDF)
        self.make_zip(
            self.repo / "outputs" / "pkg" / "lote.zip",
            {"a.pdf": PDF, "interno.zip": b"PK\x03\x04nested"},
        )

        outputs = self.candidate(self.run_audit(), "outputs")

        self.assertEqual(outputs.unverifiable_archives, ("outputs/pkg/lote.zip",))
        self.assertIn("nested_archive", outputs.reasons)
        self.assertFalse(outputs.safe_to_delete)

    def test_unverifiable_and_corrupt_archives_block_deletion(self):
        write(self.repo / "outputs" / "pkg" / "base.7z", b"7z\xbc\xaf\x27\x1c")
        write(self.repo / "outputs" / "pkg" / "broken.zip", b"not a zip at all")

        outputs = self.candidate(self.run_audit(), "outputs")

        self.assertEqual(
            outputs.unverifiable_archives, ("outputs/pkg/base.7z", "outputs/pkg/broken.zip")
        )
        self.assertIn("unverifiable_archive", outputs.reasons)
        self.assertFalse(outputs.safe_to_delete)


class DatabaseEvidenceTests(StorageAuditTestCase):
    def register_document(self, sha: str) -> None:
        store = Store.open(self.data / "atos-tce.db")
        try:
            process_id = store.upsert_process(
                ProcessRecord(
                    process_key="100015/2026",
                    interested="Pessoa Exemplo",
                    interested_normalized="pessoa exemplo",
                )
            )
            store.replace_documents(
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
        finally:
            store.close()

    def test_database_row_does_not_prove_preservation(self):
        self.register_document(digest(OTHER_PDF))
        write(self.repo / "Versions" / "old" / "b.pdf", OTHER_PDF)

        audit = self.run_audit()
        versions = self.candidate(audit, "Versions")

        self.assertTrue(audit.canonical.database_checked)
        self.assertEqual(audit.canonical.referenced_without_blob, (digest(OTHER_PDF),))
        self.assertEqual(versions.unique_pdf_count, 1)
        self.assertFalse(versions.safe_to_delete)

    def test_external_copy_counts_as_preservation(self):
        external = self.tmp / "externo" / "b.pdf"
        write(external, OTHER_PDF)
        store = Store.open(self.data / "atos-tce.db")
        try:
            store.upsert_archive_blob(
                digest(OTHER_PDF),
                size_bytes=len(OTHER_PDF),
                external_path=str(external),
                external_present=True,
            )
        finally:
            store.close()
        write(self.repo / "Versions" / "old" / "b.pdf", OTHER_PDF)

        audit = self.run_audit()
        versions = self.candidate(audit, "Versions")

        self.assertEqual(audit.canonical.external_count, 1)
        self.assertEqual(versions.unique_pdf_count, 0)
        self.assertTrue(versions.safe_to_delete)

    def test_external_copy_with_wrong_size_does_not_preserve(self):
        external = self.tmp / "externo" / "b.pdf"
        write(external, b"truncated")
        store = Store.open(self.data / "atos-tce.db")
        try:
            store.upsert_archive_blob(
                digest(OTHER_PDF),
                size_bytes=len(OTHER_PDF),
                external_path=str(external),
                external_present=True,
            )
        finally:
            store.close()
        write(self.repo / "Versions" / "old" / "b.pdf", OTHER_PDF)

        audit = self.run_audit()
        versions = self.candidate(audit, "Versions")

        self.assertEqual(audit.canonical.external_count, 0)
        self.assertFalse(versions.safe_to_delete)

    def test_audit_without_database_reports_it(self):
        audit = self.run_audit()
        self.assertFalse(audit.canonical.database_checked)
        self.assertEqual(audit.canonical.referenced_without_blob, ())


class LinkSafetyTests(StorageAuditTestCase):
    def test_reparse_point_blocks_deletion_and_is_reported(self):
        self.store_blob(PDF)
        write(self.repo / "Versions" / "old" / "a.pdf", PDF)
        link = self.repo / "Versions" / "old" / "fora"
        if not make_directory_link(self.repo / "data", link):
            self.skipTest("cannot create a directory link on this host")

        versions = self.candidate(self.run_audit(), "Versions")

        self.assertEqual(versions.skipped_links, ("Versions/old/fora",))
        self.assertIn("skipped_links", versions.reasons)
        # The junction points at the canonical blob; following it would have
        # counted the blob as a second PDF inside the candidate tree.
        self.assertEqual(versions.loose_pdf_count, 1)
        self.assertEqual(versions.reclaimable_pdf_count, 1)
        self.assertEqual(versions.missing_from_canonical_sha256, ())
        self.assertFalse(versions.safe_to_delete)


class CliTests(unittest.TestCase):
    def test_cli_writes_json_report(self):
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            data = repo / "data"
            (data / "archive" / "blobs").mkdir(parents=True)
            write(repo / "Versions" / "old" / "a.pdf", PDF)
            report_path = data / "logs" / "storage-audit.json"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--repo-root",
                    str(repo),
                    "--data-root",
                    str(data),
                    "--json",
                    str(report_path),
                ],
                capture_output=True,
                text=True,
                cwd=str(repo),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["candidates"][0]["relative_path"], "Versions")
            self.assertFalse(report["candidates"][0]["safe_to_delete"])
            self.assertEqual(report["candidates"][0]["missing_from_canonical_sha256"], [digest(PDF)])
            self.assertIn("canonical", report)
            self.assertEqual(json.loads(result.stdout)["repo_root"], str(repo))

    def test_cli_defaults_to_the_repository_root(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--data-root", result.stdout)


if __name__ == "__main__":
    unittest.main()
