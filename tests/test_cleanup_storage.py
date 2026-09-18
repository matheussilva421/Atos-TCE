"""Safety tests for the receipt-driven storage cleanup (M6 Task 7)."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "cleanup-storage.py"
PDF = b"%PDF-1.4\ncleanup fixture\n%%EOF\n"

_MODULE = None


def cleanup_module():
    """Load the CLI script so the cleanup can be driven in-process."""

    global _MODULE
    if _MODULE is None:
        spec = importlib.util.spec_from_file_location("cleanup_storage_cli", SCRIPT_PATH)
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


def write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def tree_stats(root: Path) -> tuple:
    files = 0
    total = 0
    for current, _directories, names in os.walk(root):
        for name in names:
            info = os.stat(Path(current) / name)
            files += 1
            total += info.st_size
    return files, total


def make_directory_link(target: Path, link: Path) -> bool:
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


class CleanupTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = self.tmp / "repo"
        self.data = self.repo / "data"
        (self.repo / "app").mkdir(parents=True)
        write(self.repo / "README.md", b"# Atos TCE\n")
        write(self.repo / "app" / "main.py", b"print('mesa')\n")
        write(self.data / "archive" / "blobs" / "aa" / ("a" * 64 + ".pdf"), PDF)
        self.audit_path = self.data / "logs" / "storage-audit.json"

    # -- fixtures ---------------------------------------------------------
    def candidate_payload(
        self,
        relative: str,
        *,
        safe: bool,
        category: str = "versions",
        missing: tuple = (),
        reasons: tuple = (),
        bytes_override: int | None = None,
        file_count_override: int | None = None,
    ) -> dict:
        root = self.repo / relative
        files, total = tree_stats(root) if root.exists() else (0, 0)
        return {
            "relative_path": relative,
            "category": category,
            "exists": root.exists(),
            "file_count": file_count_override if file_count_override is not None else files,
            "bytes": bytes_override if bytes_override is not None else total,
            "loose_pdf_count": 0,
            "loose_pdf_bytes": 0,
            "archive_count": 0,
            "archive_bytes": 0,
            "archive_pdf_count": 0,
            "unique_pdf_count": len(missing),
            "unique_pdf_bytes": 0,
            "reclaimable_pdf_count": 0,
            "reclaimable_pdf_bytes": 0,
            "missing_from_canonical_sha256": list(missing),
            "unverifiable_archives": [],
            "skipped_links": [],
            "safe_to_delete": safe,
            "reasons": list(reasons),
        }

    def write_audit(self, candidates: list, *, blob_count: int = 1, blob_bytes: int = len(PDF)) -> Path:
        payload = {
            "repo_root": str(self.repo.resolve()),
            "data_root": str(self.data.resolve()),
            "canonical": {
                "root": str(self.data.resolve()),
                "blob_count": blob_count,
                "blob_bytes": blob_bytes,
                "malformed_entries": [],
                "external_count": 0,
                "external_bytes": 0,
                "database_checked": True,
                "referenced_without_blob": [],
            },
            "categories": [],
            "candidates": candidates,
            "warnings": [],
            "duration_seconds": 0.0,
        }
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.audit_path

    def plan(self, **kwargs):
        return cleanup_module().plan_cleanup(self.audit_path, **kwargs)


class RefusalTests(CleanupTestCase):
    def test_unsafe_candidate_with_one_missing_sha_is_refused(self):
        write(self.repo / "outputs" / "pkg" / "a.pdf", PDF)
        self.write_audit(
            [
                self.candidate_payload(
                    "outputs",
                    safe=False,
                    category="outputs",
                    missing=("b" * 64,),
                    reasons=("unique_pdfs",),
                )
            ]
        )

        plan = self.plan()

        self.assertEqual(plan.delete, ())
        self.assertEqual(plan.entries[0].decision, "refuse")
        self.assertIn("audit_not_safe", plan.entries[0].reasons)
        self.assertGreater(plan.refused_bytes, 0)

    def test_protected_data_tree_is_refused_even_when_the_audit_says_safe(self):
        self.write_audit(
            [
                self.candidate_payload("data/archive", safe=True, category="canonical_data"),
                self.candidate_payload("dist", safe=True, category="dist"),
            ]
        )

        plan = self.plan()

        self.assertEqual(plan.delete, ())
        for entry in plan.entries:
            self.assertEqual(entry.decision, "refuse")
            self.assertIn("protected_path", entry.reasons)

    def test_current_and_previous_dist_builds_are_refused(self):
        write(self.repo / "dist" / "Atos-TCE-portable.zip", b"PK\x03\x04build")
        write(self.repo / "dist" / "Atos-TCE-portable.previous.zip", b"PK\x03\x04build")
        self.write_audit([self.candidate_payload("dist", safe=True, category="dist")])

        plan = self.plan()

        self.assertEqual(plan.delete, ())
        self.assertIn("protected_path", plan.entries[0].reasons)

    def test_paths_outside_the_repository_are_refused(self):
        outside = self.tmp / "fora"
        write(outside / "a.pdf", PDF)
        self.write_audit(
            [
                {
                    **self.candidate_payload("data", safe=True, category="outputs"),
                    "relative_path": "../fora",
                    "exists": True,
                }
            ]
        )

        plan = self.plan()

        self.assertEqual(plan.delete, ())
        self.assertIn("outside_repository", plan.entries[0].reasons)
        self.assertTrue((outside / "a.pdf").exists())

    def test_reparse_point_inside_a_candidate_is_refused(self):
        write(self.repo / "outputs" / "pkg" / "a.pdf", PDF)
        link = self.repo / "outputs" / "pkg" / "atalho"
        if not make_directory_link(self.data, link):
            self.skipTest("cannot create a directory link on this host")
        self.write_audit([self.candidate_payload("outputs", safe=True, category="outputs")])

        plan = self.plan()

        self.assertEqual(plan.delete, ())
        self.assertIn("reparse_point", plan.entries[0].reasons)

    def test_candidate_changed_after_the_audit_is_refused(self):
        write(self.repo / "outputs" / "pkg" / "a.pdf", PDF)
        self.write_audit(
            [
                self.candidate_payload(
                    "outputs", safe=True, category="outputs", bytes_override=1, file_count_override=1
                )
            ]
        )

        plan = self.plan()

        self.assertEqual(plan.delete, ())
        self.assertIn("changed_since_audit", plan.entries[0].reasons)

    def test_legacy_archive_is_refused_without_the_migration_receipt(self):
        write(self.repo / "work" / "tce-extractor" / "acervo-tce" / "origem" / "a.pdf", PDF)
        self.write_audit(
            [self.candidate_payload("work/tce-extractor/acervo-tce", safe=True, category="legacy_archive")]
        )

        plan = self.plan(allow_legacy_archive=True)

        self.assertEqual(plan.delete, ())
        self.assertIn("migration_receipt_missing", plan.entries[0].reasons)

    def write_migration_receipt(self, name: str, payload: dict) -> Path:
        path = self.data / "logs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_legacy_gate_accepts_an_apply_receipt_and_ignores_a_newer_dry_run(self):
        write(self.repo / "work" / "tce-extractor" / "acervo-tce" / "origem" / "a.pdf", PDF)
        self.write_migration_receipt(
            "legacy-import-20260918T123734Z.json",
            {"mode": "apply", "processes_seen": 724, "documents_seen": 14179, "errors": []},
        )
        self.write_migration_receipt(
            "legacy-import-20260918T181835Z.json",
            {"mode": "dry-run", "processes_seen": 166, "documents_seen": 3273, "errors": []},
        )
        self.write_audit(
            [self.candidate_payload("work/tce-extractor/acervo-tce", safe=True, category="legacy_archive")]
        )

        plan = self.plan(allow_legacy_archive=True)

        self.assertEqual(plan.delete, ("work/tce-extractor/acervo-tce",))

    def test_legacy_gate_refuses_when_only_a_dry_run_receipt_exists(self):
        write(self.repo / "work" / "tce-extractor" / "acervo-tce" / "origem" / "a.pdf", PDF)
        self.write_migration_receipt(
            "legacy-import-20260918T181835Z.json",
            {"mode": "dry-run", "processes_seen": 166, "documents_seen": 3273, "errors": []},
        )
        self.write_audit(
            [self.candidate_payload("work/tce-extractor/acervo-tce", safe=True, category="legacy_archive")]
        )

        plan = self.plan(allow_legacy_archive=True)

        self.assertEqual(plan.delete, ())
        self.assertIn("migration_receipt_not_apply", plan.entries[0].reasons)

    def test_legacy_gate_refuses_an_apply_receipt_with_errors(self):
        write(self.repo / "work" / "tce-extractor" / "acervo-tce" / "origem" / "a.pdf", PDF)
        self.write_migration_receipt(
            "legacy-import-20260918T123734Z.json",
            {"mode": "apply", "processes_seen": 724, "documents_seen": 14179, "errors": ["falha"]},
        )
        self.write_audit(
            [self.candidate_payload("work/tce-extractor/acervo-tce", safe=True, category="legacy_archive")]
        )

        plan = self.plan(allow_legacy_archive=True)

        self.assertEqual(plan.delete, ())
        self.assertIn("migration_receipt_has_errors", plan.entries[0].reasons)


class ApplyTests(CleanupTestCase):
    def test_safe_old_extraction_is_listed_in_dry_run_and_removed_on_apply(self):
        write(self.repo / "Versions" / "ref" / "a.pdf", PDF)
        write(self.repo / "Versions" / "ref" / "manifest.json", b"{}")
        self.write_audit([self.candidate_payload("Versions", safe=True)])

        dry = self.plan()
        self.assertEqual(dry.delete, ("Versions",))
        self.assertFalse(dry.applied)
        self.assertTrue((self.repo / "Versions").exists())
        self.assertGreater(dry.delete_bytes, 0)

        applied = cleanup_module().apply_cleanup(self.audit_path)

        self.assertTrue(applied.applied)
        self.assertFalse((self.repo / "Versions").exists())
        receipt = json.loads(Path(applied.receipt).read_text(encoding="utf-8"))
        self.assertEqual([item["relative_path"] for item in receipt["removed"]], ["Versions"])
        self.assertEqual(receipt["removed_bytes"], dry.delete_bytes)
        self.assertEqual(receipt["audit"], str(self.audit_path.resolve()))
        self.assertTrue(receipt["receipt_version"])

    def test_apply_removes_only_the_safe_candidates(self):
        write(self.repo / "Versions" / "ref" / "a.pdf", PDF)
        write(self.repo / "outputs" / "pkg" / "unico.pdf", PDF)
        write(self.repo / "work" / "tce-extractor" / "outputs" / "antigo.zip", b"PK")
        self.write_audit(
            [
                self.candidate_payload("Versions", safe=True),
                self.candidate_payload(
                    "outputs", safe=False, category="outputs", missing=("c" * 64,), reasons=("unique_pdfs",)
                ),
                self.candidate_payload("work/tce-extractor/outputs", safe=True, category="outputs"),
            ]
        )

        applied = cleanup_module().apply_cleanup(self.audit_path)

        self.assertEqual(sorted(applied.delete), ["Versions", "work/tce-extractor/outputs"])
        self.assertFalse((self.repo / "Versions").exists())
        self.assertFalse((self.repo / "work" / "tce-extractor" / "outputs").exists())
        self.assertTrue((self.repo / "outputs" / "pkg" / "unico.pdf").exists())
        self.assertTrue((self.repo / "data" / "archive" / "blobs").exists())

    def test_apply_writes_a_receipt_with_the_canonical_summary(self):
        write(self.repo / "Versions" / "ref" / "a.pdf", PDF)
        self.write_audit([self.candidate_payload("Versions", safe=True)], blob_count=7, blob_bytes=123)

        applied = cleanup_module().apply_cleanup(self.audit_path)

        receipt = json.loads(Path(applied.receipt).read_text(encoding="utf-8"))
        self.assertEqual(receipt["canonical"]["blob_count"], 7)
        self.assertEqual(receipt["canonical"]["blob_bytes"], 123)
        self.assertTrue(Path(applied.receipt).name.startswith("storage-cleanup-"))


class CleanupCliTests(CleanupTestCase):
    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *[str(argument) for argument in arguments]],
            capture_output=True,
            text=True,
        )

    def test_cli_requires_the_audit_receipt(self):
        result = self.run_cli()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--audit", result.stderr)

    def test_cli_defaults_to_dry_run(self):
        write(self.repo / "Versions" / "ref" / "a.pdf", PDF)
        self.write_audit([self.candidate_payload("Versions", safe=True)])

        result = self.run_cli("--audit", self.audit_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["applied"])
        self.assertEqual(report["delete"], ["Versions"])
        self.assertTrue((self.repo / "Versions").exists())

    def test_cli_apply_removes_and_reports_the_receipt(self):
        write(self.repo / "Versions" / "ref" / "a.pdf", PDF)
        self.write_audit([self.candidate_payload("Versions", safe=True)])

        result = self.run_cli("--audit", self.audit_path, "--apply")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["applied"])
        self.assertFalse((self.repo / "Versions").exists())
        self.assertTrue(Path(report["receipt"]).is_file())


if __name__ == "__main__":
    unittest.main()
