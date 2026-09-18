#!/usr/bin/env python
"""Read-only storage audit for the Mesa data root and the historical trees.

The tool never deletes anything. It reports how many bytes the repository holds
per category and, for every candidate deletion tree, whether the canonical
archive still preserves every unique PDF found there.

Preservation is proven by bytes, never by intent:

* a canonical blob is the file ``data/archive/blobs/AA/<sha256>.pdf`` whose name
  is its own SHA-256 (the importer writes and verifies those names);
* an ``archive_blobs`` row counts as preservation only when the file it points
  at still exists and its size matches the recorded size.

Archives are opened: every PDF member is hashed, so an old package ZIP holding a
PDF that never reached the canonical store is reported as unsafe. Archives the
tool cannot read (7z, rar, a corrupt ZIP, a ZIP holding another archive) block
deletion instead of being silently ignored.

    python scripts/storage-audit.py --repo-root . --data-root data --json data/logs/storage-audit.json
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import stat
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.legacy_import import (  # noqa: E402
    ARCHIVE_TREE,
    BLOB_TREE,
    _is_link as is_reparse_point,
    sha256_file,
)
from app.core.store import Store  # noqa: E402

HASH_CHUNK_SIZE = 1024 * 1024
DATABASE_NAME = "atos-tce.db"
BLOB_NAME_RE = re.compile(r"^([0-9a-f]{64})\.pdf$")

PDF_SUFFIX = ".pdf"
ZIP_SUFFIX = ".zip"
UNVERIFIABLE_ARCHIVE_SUFFIXES = (
    ".7z",
    ".bz2",
    ".cab",
    ".gz",
    ".iso",
    ".rar",
    ".tar",
    ".tgz",
    ".xz",
    ".zipx",
    ".zst",
)
ARCHIVE_SUFFIXES = (ZIP_SUFFIX,) + UNVERIFIABLE_ARCHIVE_SUFFIXES

CANONICAL_DATA = "canonical_data"
DIST = "dist"
OUTPUTS = "outputs"
VERSIONS = "versions"
STAGING = "staging"
TEMP = "temp"
LEGACY_ARCHIVE = "legacy_archive"
SOURCE = "source"
UNKNOWN = "unknown"

CATEGORIES = (
    CANONICAL_DATA,
    DIST,
    OUTPUTS,
    VERSIONS,
    STAGING,
    TEMP,
    LEGACY_ARCHIVE,
    SOURCE,
    UNKNOWN,
)

# Classification of any repository path. The most specific prefix wins, so
# ``work/tce-extractor/acervo-tce`` is a legacy archive while the rest of
# ``work`` remains source.
CLASSIFICATION_RULES = (
    ("data", CANONICAL_DATA),
    ("dist", DIST),
    ("Versions", VERSIONS),
    ("outputs", OUTPUTS),
    ("tmp", TEMP),
    ("work/tce-extractor/outputs", OUTPUTS),
    ("work/tce-extractor/acervo-tce", LEGACY_ARCHIVE),
    ("work", SOURCE),
    ("app", SOURCE),
    ("extension", SOURCE),
    ("packaging", SOURCE),
    ("scripts", SOURCE),
    ("tests", SOURCE),
    ("docs", SOURCE),
    (".superpowers", SOURCE),
    (".git", SOURCE),
)

# Trees that answer the destructive gate. ``dist`` is deliberately absent:
# keeping current plus previous build needs that decision (M6 task 6), so the
# audit only reports its size. ``data`` and the source trees are never
# candidates.
CANDIDATE_ROOTS = (
    ("Versions", VERSIONS),
    ("outputs", OUTPUTS),
    ("tmp", TEMP),
    ("work/outputs", OUTPUTS),
    ("work/tmp", TEMP),
    ("work/tce-extractor/Versions", VERSIONS),
    ("work/tce-extractor/outputs", OUTPUTS),
    ("work/tce-extractor/acervo-tce", LEGACY_ARCHIVE),
)
STAGING_PATTERNS = ("staging-*", ".package-staging-*")
STAGING_PARENTS = ("", "work", "work/tce-extractor")

REASON_ABSENT = "directory_absent"
REASON_UNIQUE = "unique_pdfs"
REASON_UNVERIFIABLE = "unverifiable_archive"
REASON_NESTED = "nested_archive"
REASON_LINKS = "skipped_links"


# ------------------------------------------------------------------ data model


@dataclass(frozen=True)
class CategoryTotal:
    """Bytes and file count held by one category of the repository."""

    category: str
    file_count: int
    bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "file_count": self.file_count, "bytes": self.bytes}


@dataclass(frozen=True)
class CanonicalStore:
    """What the canonical data root really preserves right now."""

    root: str
    blob_count: int
    blob_bytes: int
    malformed_entries: tuple[str, ...]
    external_count: int
    external_bytes: int
    database_checked: bool
    referenced_without_blob: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "blob_count": self.blob_count,
            "blob_bytes": self.blob_bytes,
            "malformed_entries": list(self.malformed_entries),
            "external_count": self.external_count,
            "external_bytes": self.external_bytes,
            "database_checked": self.database_checked,
            "referenced_without_blob": list(self.referenced_without_blob),
        }


@dataclass(frozen=True)
class CandidateReport:
    """One tree that a cleanup could delete, with the proof it is safe."""

    relative_path: str
    category: str
    exists: bool
    file_count: int
    bytes: int
    loose_pdf_count: int
    loose_pdf_bytes: int
    archive_count: int
    archive_bytes: int
    archive_pdf_count: int
    unique_pdf_count: int
    unique_pdf_bytes: int
    reclaimable_pdf_count: int
    reclaimable_pdf_bytes: int
    missing_from_canonical_sha256: tuple[str, ...]
    unverifiable_archives: tuple[str, ...]
    skipped_links: tuple[str, ...]
    safe_to_delete: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "category": self.category,
            "exists": self.exists,
            "file_count": self.file_count,
            "bytes": self.bytes,
            "loose_pdf_count": self.loose_pdf_count,
            "loose_pdf_bytes": self.loose_pdf_bytes,
            "archive_count": self.archive_count,
            "archive_bytes": self.archive_bytes,
            "archive_pdf_count": self.archive_pdf_count,
            "unique_pdf_count": self.unique_pdf_count,
            "unique_pdf_bytes": self.unique_pdf_bytes,
            "reclaimable_pdf_count": self.reclaimable_pdf_count,
            "reclaimable_pdf_bytes": self.reclaimable_pdf_bytes,
            "missing_from_canonical_sha256": list(self.missing_from_canonical_sha256),
            "unverifiable_archives": list(self.unverifiable_archives),
            "skipped_links": list(self.skipped_links),
            "safe_to_delete": self.safe_to_delete,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class StorageAudit:
    """The whole report: canonical state, category totals and candidates."""

    repo_root: str
    data_root: str
    canonical: CanonicalStore
    categories: tuple[CategoryTotal, ...]
    candidates: tuple[CandidateReport, ...]
    warnings: tuple[str, ...]
    duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": self.repo_root,
            "data_root": self.data_root,
            "canonical": self.canonical.to_dict(),
            "categories": [item.to_dict() for item in self.categories],
            "candidates": [item.to_dict() for item in self.candidates],
            "warnings": list(self.warnings),
            "duration_seconds": self.duration_seconds,
        }

    @property
    def unsafe_candidates(self) -> tuple[CandidateReport, ...]:
        return tuple(item for item in self.candidates if not item.safe_to_delete)


# ------------------------------------------------------------------- traversal


def _posix(path: Path) -> str:
    return path.as_posix()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:  # pragma: no cover - defensive, links are never followed
        return _posix(path)


def _walk(root: Path, *, warnings: list[str]) -> Iterator[dict[str, Any]]:
    """Yield every regular file and every reparse point below ``root``.

    Links are yielded but never followed, so a junction can neither escape the
    tree nor duplicate an accounting.
    """

    root = Path(root)
    if not root.is_dir():
        return
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as scan:
                entries = list(scan)
        except OSError as error:
            warnings.append(f"unreadable_directory:{_posix(current)}:{error.strerror or error}")
            continue
        for entry in entries:
            path = Path(entry.path)
            if is_reparse_point(path):
                yield {"path": path, "kind": "link", "size": 0}
                continue
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as error:
                warnings.append(f"unreadable_entry:{_posix(path)}:{error.strerror or error}")
                continue
            if stat.S_ISDIR(info.st_mode):
                stack.append(path)
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            yield {"path": path, "kind": "file", "size": int(info.st_size)}


def classify_relative(relative: str, *, is_directory: bool = False) -> str:
    """Return the category of one repository-relative path."""

    parts = PurePosixPath(relative.replace("\\", "/")).parts
    if not parts:
        return UNKNOWN
    for part in parts:
        if any(fnmatch.fnmatch(part.lower(), pattern) for pattern in STAGING_PATTERNS):
            return STAGING
    best: tuple[int, str] | None = None
    for prefix, category in CLASSIFICATION_RULES:
        prefix_parts = PurePosixPath(prefix).parts
        if parts[: len(prefix_parts)] == prefix_parts and (
            best is None or len(prefix_parts) > best[0]
        ):
            best = (len(prefix_parts), category)
    if best is not None:
        return best[1]
    if len(parts) == 1:
        return SOURCE if not is_directory else UNKNOWN
    # A deeper path without a rule inherits the category of its top-level
    # entry, which is a directory here.
    return classify_relative(parts[0], is_directory=True)


def candidate_roots(repo_root: Path, *, warnings: list[str]) -> list[tuple[str, str]]:
    """Return the trees a cleanup may target, most specific first."""

    repo_root = Path(repo_root)
    declared: list[tuple[str, str]] = [(relative, category) for relative, category in CANDIDATE_ROOTS]
    for parent in STAGING_PARENTS:
        base = repo_root / parent if parent else repo_root
        if not base.is_dir():
            continue
        try:
            with os.scandir(base) as scan:
                names = sorted(entry.name for entry in scan if entry.is_dir(follow_symlinks=False))
        except OSError as error:
            warnings.append(f"unreadable_directory:{_posix(base)}:{error.strerror or error}")
            continue
        for name in names:
            if any(fnmatch.fnmatch(name.lower(), pattern) for pattern in STAGING_PATTERNS):
                relative = f"{parent}/{name}" if parent else name
                declared.append((relative, STAGING))
    result: list[tuple[str, str]] = []
    for relative, category in declared:
        if any(other == relative for other, _ in result):
            continue
        if any(relative.startswith(other + "/") for other, _ in result):
            continue
        result.append((relative, category))
    return result


# -------------------------------------------------------------- canonical side


def _scan_canonical_blobs(
    data_root: Path, *, warnings: list[str]
) -> tuple[set[str], int, int, tuple[str, ...]]:
    """Return the SHAs physically preserved in the canonical blob tree."""

    blobs_root = Path(data_root) / ARCHIVE_TREE / BLOB_TREE
    shas: set[str] = set()
    blob_count = 0
    blob_bytes = 0
    malformed: list[str] = []
    for entry in _walk(blobs_root, warnings=warnings):
        if entry["kind"] != "file":
            continue
        blob_count += 1
        blob_bytes += entry["size"]
        match = BLOB_NAME_RE.match(entry["path"].name)
        if match is None:
            malformed.append(_relative(entry["path"], data_root))
            continue
        shas.add(match.group(1))
    return shas, blob_count, blob_bytes, tuple(sorted(malformed))


def _scan_external_copies(
    store: Store, canonical: set[str], *, warnings: list[str]
) -> tuple[set[str], int, int, set[str]]:
    """Return the SHAs preserved outside the data root, plus referenced ones."""

    preserved: set[str] = set()
    count = 0
    total = 0
    referenced: set[str] = set()
    for blob in store.list_archive_blobs():
        sha = str(blob.get("sha256") or "").strip().lower()
        if not sha:
            continue
        referenced.add(sha)
        if sha in canonical or not blob.get("external_present"):
            continue
        raw = str(blob.get("external_path") or "").strip()
        if not raw:
            warnings.append(f"external_path_missing:{sha}")
            continue
        path = Path(raw)
        if not path.is_file():
            warnings.append(f"external_file_absent:{sha}")
            continue
        try:
            size = int(path.stat().st_size)
        except OSError as error:
            warnings.append(f"external_file_unreadable:{sha}:{error.strerror or error}")
            continue
        recorded = int(blob.get("size_bytes") or 0)
        if recorded and size != recorded:
            warnings.append(f"external_size_mismatch:{sha}")
            continue
        preserved.add(sha)
        count += 1
        total += size
    for sha in store.list_document_shas():
        value = str(sha or "").strip().lower()
        if value:
            referenced.add(value)
    return preserved, count, total, referenced


# -------------------------------------------------------------- candidate side


def _hash_stream(handle: Any) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = handle.read(HASH_CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _scan_zip(
    path: Path, *, warnings: list[str]
) -> tuple[list[tuple[str, int]], bool, str | None]:
    """Hash every PDF member of one ZIP; report nested or unreadable archives."""

    members: list[tuple[str, int]] = []
    nested = False
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                lower = info.filename.lower()
                if lower.endswith(PDF_SUFFIX):
                    with archive.open(info) as handle:
                        members.append(_hash_stream(handle))
                elif lower.endswith(ARCHIVE_SUFFIXES):
                    nested = True
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError) as error:
        warnings.append(f"unreadable_archive:{_posix(path)}:{type(error).__name__}")
        return [], nested, type(error).__name__
    return members, nested, None


def _scan_candidate(
    repo_root: Path,
    relative: str,
    category: str,
    canonical: set[str],
    *,
    warnings: list[str],
    progress: Callable[[str], None] | None,
) -> CandidateReport:
    root = Path(repo_root) / PurePosixPath(relative)
    if not root.is_dir():
        return CandidateReport(
            relative_path=relative,
            category=category,
            exists=False,
            file_count=0,
            bytes=0,
            loose_pdf_count=0,
            loose_pdf_bytes=0,
            archive_count=0,
            archive_bytes=0,
            archive_pdf_count=0,
            unique_pdf_count=0,
            unique_pdf_bytes=0,
            reclaimable_pdf_count=0,
            reclaimable_pdf_bytes=0,
            missing_from_canonical_sha256=(),
            unverifiable_archives=(),
            skipped_links=(),
            safe_to_delete=False,
            reasons=(REASON_ABSENT,),
        )

    file_count = 0
    total_bytes = 0
    loose_pdf_count = 0
    loose_pdf_bytes = 0
    archive_count = 0
    archive_bytes = 0
    archive_pdf_count = 0
    pdf_sizes: dict[str, int] = {}
    unverifiable: list[str] = []
    skipped_links: list[str] = []
    nested_found = False

    for entry in _walk(root, warnings=warnings):
        entry_relative = _relative(entry["path"], repo_root)
        if entry["kind"] == "link":
            skipped_links.append(entry_relative)
            continue
        file_count += 1
        total_bytes += entry["size"]
        suffix = entry["path"].suffix.lower()
        if suffix == PDF_SUFFIX:
            loose_pdf_count += 1
            loose_pdf_bytes += entry["size"]
            if progress is not None:
                progress(entry_relative)
            digest = sha256_file(entry["path"], HASH_CHUNK_SIZE)
            pdf_sizes.setdefault(digest, entry["size"])
            continue
        if suffix == ZIP_SUFFIX:
            archive_count += 1
            archive_bytes += entry["size"]
            if progress is not None:
                progress(entry_relative)
            members, nested, failure = _scan_zip(entry["path"], warnings=warnings)
            if failure is not None:
                unverifiable.append(entry_relative)
            elif nested:
                unverifiable.append(entry_relative)
                nested_found = True
            for digest, size in members:
                archive_pdf_count += 1
                pdf_sizes.setdefault(digest, size)
            continue
        if suffix in UNVERIFIABLE_ARCHIVE_SUFFIXES:
            archive_count += 1
            archive_bytes += entry["size"]
            unverifiable.append(entry_relative)

    unique = sorted(digest for digest in pdf_sizes if digest not in canonical)
    unique_bytes = sum(pdf_sizes[digest] for digest in unique)
    reclaimable = sorted(digest for digest in pdf_sizes if digest in canonical)
    reclaimable_bytes = sum(pdf_sizes[digest] for digest in reclaimable)

    reasons: list[str] = []
    if unique:
        reasons.append(REASON_UNIQUE)
    if unverifiable:
        reasons.append(REASON_UNVERIFIABLE)
    if nested_found:
        reasons.append(REASON_NESTED)
    if skipped_links:
        reasons.append(REASON_LINKS)

    return CandidateReport(
        relative_path=relative,
        category=category,
        exists=True,
        file_count=file_count,
        bytes=total_bytes,
        loose_pdf_count=loose_pdf_count,
        loose_pdf_bytes=loose_pdf_bytes,
        archive_count=archive_count,
        archive_bytes=archive_bytes,
        archive_pdf_count=archive_pdf_count,
        unique_pdf_count=len(unique),
        unique_pdf_bytes=unique_bytes,
        reclaimable_pdf_count=len(reclaimable),
        reclaimable_pdf_bytes=reclaimable_bytes,
        missing_from_canonical_sha256=tuple(unique),
        unverifiable_archives=tuple(unverifiable),
        skipped_links=tuple(skipped_links),
        safe_to_delete=not reasons,
        reasons=tuple(reasons),
    )


# ---------------------------------------------------------------------- audit


def audit_storage(
    repo_root: str | Path,
    data_root: str | Path | None = None,
    *,
    store: Store | None = None,
    use_database: bool = True,
    progress: Callable[[str], None] | None = None,
) -> StorageAudit:
    """Report the storage state of ``repo_root`` without changing anything."""

    started = time.monotonic()
    repo_path = Path(repo_root).resolve()
    data_path = Path(data_root).resolve() if data_root is not None else repo_path / "data"
    warnings: list[str] = []

    canonical_shas, blob_count, blob_bytes, malformed = _scan_canonical_blobs(
        data_path, warnings=warnings
    )

    own_store = None
    database_checked = False
    external_shas: set[str] = set()
    external_count = 0
    external_bytes = 0
    referenced_without_blob: tuple[str, ...] = ()
    database_file = data_path / DATABASE_NAME
    if store is None and use_database and database_file.is_file():
        # The audit only opens a database that already exists, so it never
        # creates or migrates state while inspecting storage.
        store = Store.open(database_file)
        own_store = store
    if store is None and use_database:
        warnings.append(f"database_absent:{_posix(database_file)}")
    try:
        if store is not None:
            external_shas, external_count, external_bytes, referenced = _scan_external_copies(
                store, canonical_shas, warnings=warnings
            )
            referenced_without_blob = tuple(
                sorted(referenced - canonical_shas - external_shas)
            )
            database_checked = True
    finally:
        if own_store is not None:
            own_store.close()

    preserved = canonical_shas | external_shas

    totals: dict[str, dict[str, int]] = {
        category: {"file_count": 0, "bytes": 0} for category in CATEGORIES
    }
    for entry in _walk(repo_path, warnings=warnings):
        relative = _relative(entry["path"], repo_path)
        if entry["kind"] == "link":
            continue
        category = classify_relative(relative, is_directory=False)
        totals[category]["file_count"] += 1
        totals[category]["bytes"] += entry["size"]

    candidates = tuple(
        _scan_candidate(
            repo_path,
            relative,
            category,
            preserved,
            warnings=warnings,
            progress=progress,
        )
        for relative, category in candidate_roots(repo_path, warnings=warnings)
    )

    canonical = CanonicalStore(
        root=str(data_path),
        blob_count=blob_count,
        blob_bytes=blob_bytes,
        malformed_entries=malformed,
        external_count=external_count,
        external_bytes=external_bytes,
        database_checked=database_checked,
        referenced_without_blob=referenced_without_blob,
    )
    return StorageAudit(
        repo_root=str(repo_path),
        data_root=str(data_path),
        canonical=canonical,
        categories=tuple(
            CategoryTotal(category=category, **totals[category]) for category in CATEGORIES
        ),
        candidates=candidates,
        warnings=tuple(warnings),
        duration_seconds=round(time.monotonic() - started, 3),
    )


# ------------------------------------------------------------------------ CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="project root to audit")
    parser.add_argument(
        "--data-root", type=Path, default=None, help="Mesa data root (default: <repo-root>/data)"
    )
    parser.add_argument("--json", type=Path, default=None, help="also write the report to this file")
    parser.add_argument(
        "--progress", action="store_true", help="print one line per hashed file to stderr"
    )
    parser.add_argument(
        "--no-database", action="store_true", help="ignore atos-tce.db and audit the blob tree only"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - host stream dependent
                pass
    args = build_parser().parse_args(argv)
    data_root = args.data_root if args.data_root is not None else args.repo_root / "data"
    progress = _stderr_progress if args.progress else None
    try:
        audit = audit_storage(
            args.repo_root,
            data_root,
            use_database=not args.no_database,
            progress=progress,
        )
    except Exception as error:  # pragma: no cover - surfaced to the operator
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}), file=sys.stderr)
        return 1
    payload = json.dumps(audit.to_dict(), ensure_ascii=False, indent=2)
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


def _stderr_progress(relative: str) -> None:
    print(f"[audit] {relative}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
