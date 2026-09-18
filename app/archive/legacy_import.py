"""Safe import of the legacy ``acervo-tce`` tree into the canonical data root.

Nothing in this module mutates the source archive. The source is hashed, read
and indexed; the new data root receives one canonical blob per unique SHA-256
plus a legacy-shaped ``archive/processos`` view that is hardlinked to those
blobs whenever the volume supports it. When a hardlink is impossible the bytes
are copied and counted separately as fallback copies, so the migration report
never hides duplicated storage.

Two entry points share the same hashing and linking code:

``import_legacy_archive``
    one-shot migration rehearsal of an existing archive (dry-run by default).

``canonicalize_process_tree``
    repeated, incremental canonicalization of newly downloaded bytes and is
    the only entry point that touches files *inside* a data root.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.identity import normalize_interested
from ..core.models import DocumentRecord, ProcessRecord
from ..core.store import SCHEMA_VERSION, Store, utc_now

HASH_CHUNK_SIZE = 1024 * 1024
ARCHIVE_TREE = "archive"
PROCESS_TREE = "processos"
BLOB_TREE = "blobs"
LOGS_TREE = "logs"
INTEREST_INDEX_NAME = "dados-complementar-ato.json"
DOCUMENT_MANIFEST_NAME = "pdfs-alvo-manifest.json"
PROCESS_MANIFEST_NAME = "processo.json"

#: Directory names that must never be treated as process content.
SKIPPED_DIRECTORY_NAMES = frozenset({BLOB_TREE})

#: Interested-person placeholder used when the legacy index has no record.
UNKNOWN_INTERESTED = "Interessado não identificado"

#: Imported processes start at the beginning of the workflow; the Área Restrita
#: scan (M2) and the analysis pipeline (M4) are the owners of later states.
DEFAULT_PROCESS_STATUS = "PENDENTE"

#: Cap the number of individual messages kept in a report or receipt.
MAX_REPORT_MESSAGES = 50

EVENT_FOLDER_RE = re.compile(r"^evento-(\d+)-(\d+)$", re.IGNORECASE)
DOCUMENT_NAME_RE = re.compile(r"^documento-(\d+)-(.*)$", re.IGNORECASE)
FOLDER_KEY_RE = re.compile(r"^(\d+)-(\d{4})$")


class LegacyImportError(RuntimeError):
    """Raised when the legacy archive cannot be read safely."""


# --------------------------------------------------------------------- helpers


def sha256_file(path: Path, chunk_size: int = HASH_CHUNK_SIZE) -> str:
    """Hash one file in bounded chunks so multi-gigabyte PDFs stay safe."""

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def blob_relative_path(digest: str) -> str:
    """Return the canonical blob location for ``digest`` relative to a data root."""

    return f"{ARCHIVE_TREE}/{BLOB_TREE}/{digest[:2]}/{digest}.pdf"


def blob_path(data_root: Path, digest: str) -> Path:
    """Return the absolute canonical blob path for ``digest``."""

    return Path(data_root) / blob_relative_path(digest)


def view_relative_path(archive_relative: str) -> str:
    """Map an archive-relative path onto its data-root-relative process view."""

    return f"{ARCHIVE_TREE}/{archive_relative}"


def _is_link(path: Path) -> bool:
    """True for symlinks *and* Windows junctions/reparse points."""

    try:
        info = os.lstat(path)
    except OSError:
        return True
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _is_same_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _normalize_relative(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    return text.lstrip("/")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _iter_child_directories(parent: Path) -> list[Path]:
    """List real child directories, skipping links and blob storage."""

    directories: list[Path] = []
    for entry in sorted(parent.iterdir(), key=lambda item: item.name.casefold()):
        if entry.name.casefold() in SKIPPED_DIRECTORY_NAMES:
            continue
        if _is_link(entry) or not entry.is_dir():
            continue
        directories.append(entry)
    return directories


def _iter_pdfs(root: Path) -> list[Path]:
    """Recursively list PDFs under ``root`` without following any link."""

    found: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        directory_names[:] = [
            name
            for name in sorted(directory_names, key=str.casefold)
            if name.casefold() not in SKIPPED_DIRECTORY_NAMES
            and not _is_link(current_path / name)
        ]
        for name in sorted(file_names, key=str.casefold):
            if not name.casefold().endswith(".pdf"):
                continue
            candidate = current_path / name
            if not _is_link(candidate):
                found.append(candidate)
    return found


# ----------------------------------------------------------------- data shapes


@dataclass(slots=True)
class LegacyInterest:
    original: str
    normalized: str
    legacy_status: str | None = None


@dataclass(slots=True)
class LegacyDocument:
    """One PDF found in the source archive, already enriched with metadata."""

    source_path: Path
    archive_relative: str
    source_id: str
    title: str
    event: str | None
    page_count: int
    classification: str | None
    manifest_sha256: str | None
    size_bytes: int

    @property
    def view_relative(self) -> str:
        return view_relative_path(self.archive_relative)


@dataclass(slots=True)
class LegacyProcess:
    process_key: str
    folder: str
    interests: list[LegacyInterest]
    documents: list[LegacyDocument]


@dataclass(slots=True)
class LegacyScan:
    archive_root: Path
    processes: list[LegacyProcess]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImportReport:
    """Counters and diagnostics for one import or canonicalization run."""

    mode: str
    archive_root: str | None = None
    processes_seen: int = 0
    documents_seen: int = 0
    unique_pdfs: int = 0
    duplicate_pdfs: int = 0
    bytes_source: int = 0
    bytes_unique: int = 0
    copied_files: int = 0
    moved_files: int = 0
    hardlinked_files: int = 0
    fallback_copies: int = 0
    bytes_fallback_copies: int = 0
    reused_blobs: int = 0
    verified_blobs: int = 0
    processes_upserted: int = 0
    document_rows: int = 0
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    receipt_path: str | None = None
    unreferenced: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        if len(self.errors) < MAX_REPORT_MESSAGES:
            self.errors.append(message)
        elif len(self.errors) == MAX_REPORT_MESSAGES:
            self.errors.append("… further errors omitted from this report")

    def add_warning(self, message: str) -> None:
        if len(self.warnings) < MAX_REPORT_MESSAGES:
            self.warnings.append(message)
        elif len(self.warnings) == MAX_REPORT_MESSAGES:
            self.warnings.append("… further warnings omitted from this report")

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "mode": self.mode,
            "archive_root": self.archive_root,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "processes_seen": self.processes_seen,
            "documents_seen": self.documents_seen,
            "unique_pdfs": self.unique_pdfs,
            "duplicate_pdfs": self.duplicate_pdfs,
            "bytes_source": self.bytes_source,
            "bytes_unique": self.bytes_unique,
            "copied_files": self.copied_files,
            "moved_files": self.moved_files,
            "hardlinked_files": self.hardlinked_files,
            "fallback_copies": self.fallback_copies,
            "bytes_fallback_copies": self.bytes_fallback_copies,
            "reused_blobs": self.reused_blobs,
            "verified_blobs": self.verified_blobs,
            "processes_upserted": self.processes_upserted,
            "document_rows": self.document_rows,
            "unreferenced_count": len(self.unreferenced),
            "unreferenced": self.unreferenced[:MAX_REPORT_MESSAGES],
            "errors": self.errors,
            "warnings": self.warnings,
            "receipt_path": self.receipt_path,
        }
        return payload


# --------------------------------------------------------------------- scanning


def scan_legacy_archive(root: str | Path) -> LegacyScan:
    """Index the process tree of ``root`` without modifying anything."""

    archive_root = Path(root)
    if not archive_root.is_dir():
        raise LegacyImportError(f"legacy archive root does not exist: {archive_root}")
    process_root = archive_root / PROCESS_TREE
    if not process_root.is_dir():
        raise LegacyImportError(f"legacy process tree does not exist: {process_root}")

    warnings: list[str] = []
    interests = _read_interest_index(archive_root, warnings)
    document_manifest = _read_document_manifest(archive_root, warnings)

    processes: list[LegacyProcess] = []
    for folder in _iter_child_directories(process_root):
        process_key = _resolve_process_key(folder, warnings)
        folder_interests = interests.get(process_key, [])
        if not folder_interests and process_key in interests:
            folder_interests = interests[process_key]
        local_manifest = _read_process_manifest(folder, warnings)
        documents: list[LegacyDocument] = []
        used_ids: set[str] = set()
        for pdf in _iter_pdfs(folder):
            archive_relative = pdf.relative_to(archive_root).as_posix()
            metadata = _resolve_metadata(
                pdf, archive_relative, process_key, document_manifest, local_manifest
            )
            source_id = _unique_source_id(metadata["source_id"], used_ids)
            try:
                size_bytes = pdf.stat().st_size
            except OSError as exc:
                warnings.append(f"{archive_relative}: cannot stat the file: {exc}")
                continue
            documents.append(
                LegacyDocument(
                    source_path=pdf,
                    archive_relative=archive_relative,
                    source_id=source_id,
                    title=metadata["title"],
                    event=metadata["event"],
                    page_count=metadata["page_count"],
                    classification=metadata["classification"],
                    manifest_sha256=metadata["sha256"],
                    size_bytes=size_bytes,
                )
            )
        processes.append(
            LegacyProcess(
                process_key=process_key,
                folder=folder.name,
                interests=folder_interests,
                documents=documents,
            )
        )

    processes.sort(key=lambda item: (item.process_key, item.folder))
    return LegacyScan(archive_root=archive_root, processes=processes, warnings=warnings)


def _resolve_process_key(folder: Path, warnings: list[str]) -> str:
    manifest = folder / PROCESS_MANIFEST_NAME
    if manifest.is_file():
        try:
            payload = _read_json(manifest)
            key = str(payload.get("key") or "").strip()
            if key:
                return key
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            warnings.append(f"{folder.name}/{PROCESS_MANIFEST_NAME}: unreadable ({exc})")
    match = FOLDER_KEY_RE.match(folder.name)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    warnings.append(f"{folder.name}: cannot infer a canonical process key from the folder name")
    return folder.name


def _read_interest_index(archive_root: Path, warnings: list[str]) -> dict[str, list[LegacyInterest]]:
    path = archive_root / INTEREST_INDEX_NAME
    if not path.is_file():
        warnings.append(f"interest index not found: {INTEREST_INDEX_NAME}")
        return {}
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"unreadable interest index {INTEREST_INDEX_NAME}: {exc}")
        return {}
    index: dict[str, list[LegacyInterest]] = {}
    records = payload.get("records") if isinstance(payload, Mapping) else None
    for record in records or []:
        if not isinstance(record, Mapping):
            continue
        process = record.get("process") or {}
        process_key = str(process.get("key") or "").strip() if isinstance(process, Mapping) else ""
        interested = record.get("interested") or {}
        if not isinstance(interested, Mapping):
            continue
        original = str(interested.get("original") or "").strip()
        if not process_key or not original:
            continue
        legacy_normalized = str(interested.get("normalized") or "").strip()
        canonical = normalize_interested(original)
        if legacy_normalized and legacy_normalized != canonical:
            warnings.append(
                f"{process_key}/{original}: legacy normalized '{legacy_normalized}' "
                f"differs from the canonical '{canonical}'; using the canonical form"
            )
        index.setdefault(process_key, []).append(
            LegacyInterest(
                original=original,
                normalized=canonical,
                legacy_status=str(record.get("status") or "") or None,
            )
        )
    return index


def _read_document_manifest(archive_root: Path, warnings: list[str]) -> dict[str, dict[str, Any]]:
    path = archive_root / DOCUMENT_MANIFEST_NAME
    if not path.is_file():
        warnings.append(f"document manifest not found: {DOCUMENT_MANIFEST_NAME}")
        return {}
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"unreadable document manifest {DOCUMENT_MANIFEST_NAME}: {exc}")
        return {}
    index: dict[str, dict[str, Any]] = {}
    for entry in payload.get("processes") or []:
        if not isinstance(entry, Mapping):
            continue
        process_key = str(entry.get("process") or entry.get("key") or "").strip()
        for document in entry.get("documents") or []:
            if not isinstance(document, Mapping):
                continue
            relative = _normalize_relative(document.get("relative_path") or document.get("pdf_path"))
            if not relative:
                continue
            event = document.get("event")
            document_id = str(document.get("id") or "").strip()
            source_id = "|".join(
                part for part in (process_key, str(event).strip() if event is not None else "", document_id) if part
            )
            index[relative] = {
                "source_id": source_id or relative,
                "title": str(document.get("title") or "").strip(),
                "event": str(event).strip() if event is not None else None,
                "page_count": document.get("page_count"),
                "classification": document.get("classification") or document.get("kind"),
                "sha256": str(document.get("sha256") or "").strip() or None,
            }
    return index


def _read_process_manifest(folder: Path, warnings: list[str]) -> dict[str, dict[str, Any]]:
    path = folder / PROCESS_MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"{folder.name}/{PROCESS_MANIFEST_NAME}: unreadable ({exc})")
        return {}
    index: dict[str, dict[str, Any]] = {}
    for event in payload.get("events") or []:
        if not isinstance(event, Mapping):
            continue
        number = event.get("event")
        for document in event.get("documents") or []:
            if not isinstance(document, Mapping):
                continue
            relative = _normalize_relative(document.get("path"))
            if not relative:
                continue
            # ``processo.json`` document keys are already fully qualified ids.
            source_id = str(document.get("key") or document.get("id") or "").strip() or relative
            index[relative] = {
                "source_id": source_id,
                "title": str(document.get("title") or "").strip(),
                "event": str(number).strip() if number is not None else None,
                "page_count": None,
                "classification": None,
                "sha256": str(document.get("sha256") or "").strip() or None,
            }
    return index


def _resolve_metadata(
    pdf: Path,
    archive_relative: str,
    process_key: str,
    document_manifest: Mapping[str, Mapping[str, Any]],
    local_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Merge target manifest, per-process manifest and path-derived fallbacks."""

    derived = _derive_metadata(pdf)
    merged: dict[str, Any] = {
        "source_id": f"{process_key}|{archive_relative}",
        "title": derived["title"],
        "event": derived["event"],
        "page_count": 0,
        "classification": None,
        "sha256": None,
    }
    for layer in (local_manifest.get(archive_relative), document_manifest.get(archive_relative)):
        if not layer:
            continue
        for key, value in layer.items():
            if key == "page_count":
                if isinstance(value, int) and value >= 0:
                    merged["page_count"] = value
                continue
            if value in (None, ""):
                continue
            if key == "source_id":
                merged["source_id"] = str(value)
                continue
            merged[key] = value
    if merged["source_id"] == f"{process_key}|{archive_relative}":
        merged["source_id"] = f"{process_key}|{archive_relative}"
    return merged


def _derive_metadata(pdf: Path) -> dict[str, Any]:
    match = DOCUMENT_NAME_RE.match(pdf.stem)
    title = match.group(2) if match else pdf.stem
    event = None
    parent_match = EVENT_FOLDER_RE.match(pdf.parent.name)
    if parent_match:
        event = str(int(parent_match.group(1)))
    return {"title": title or pdf.stem, "event": event}


def _unique_source_id(candidate: str, used: set[str]) -> str:
    base = candidate.strip() or "documento"
    if base not in used:
        used.add(base)
        return base
    suffix = 2
    while f"{base}#{suffix}" in used:
        suffix += 1
    unique = f"{base}#{suffix}"
    used.add(unique)
    return unique


# ------------------------------------------------------------------ materialize


def _ensure_blob(
    data_root: Path,
    digest: str,
    source_path: Path,
    report: ImportReport,
    verified: set[str],
) -> Path | None:
    """Materialize (or reuse) the canonical blob for ``digest``."""

    blob = blob_path(data_root, digest)
    if digest in verified:
        report.reused_blobs += 1
        return blob
    if blob.is_file():
        actual = sha256_file(blob)
        if actual != digest:
            report.add_error(
                f"blob {blob} contains {actual[:12]}… but its name promises {digest[:12]}…; "
                "refusing to reuse it"
            )
            return None
        verified.add(digest)
        report.verified_blobs += 1
        report.reused_blobs += 1
        return blob

    temporary = blob.with_name(blob.name + ".part")
    try:
        blob.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, temporary)
        actual = sha256_file(temporary)
        if actual != digest:
            report.add_error(
                f"{source_path}: the copied bytes hash to {actual[:12]}… instead of {digest[:12]}…"
            )
            return None
        os.replace(temporary, blob)
    except OSError as exc:
        report.add_error(f"cannot materialize blob {blob}: {exc}")
        return None
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:  # pragma: no cover - best effort cleanup
                pass
    verified.add(digest)
    report.copied_files += 1
    return blob


def _link_or_copy(source: Path, target: Path) -> str:
    """Create ``target`` as a hardlink to ``source``; copy only if forced."""

    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def _ensure_process_view(view: Path, blob: Path, digest: str, report: ImportReport) -> None:
    """Make ``view`` a verified hardlink to ``blob`` without losing bytes."""

    if view.exists() and _is_same_file(view, blob):
        report.hardlinked_files += 1
        return
    if view.exists():
        actual = sha256_file(view)
        if actual != digest:
            report.add_error(
                f"{view}: existing file hashes to {actual[:12]}… instead of {digest[:12]}…; left untouched"
            )
            return

    temporary = view.with_name(view.name + ".part")
    try:
        view.parent.mkdir(parents=True, exist_ok=True)
        outcome = _link_or_copy(blob, temporary)
        os.replace(temporary, view)
    except OSError as exc:
        report.add_error(f"{view}: cannot materialize the process view: {exc}")
        return
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:  # pragma: no cover - best effort cleanup
                pass

    if outcome == "hardlink":
        report.hardlinked_files += 1
    else:
        report.fallback_copies += 1
        try:
            report.bytes_fallback_copies += view.stat().st_size
        except OSError:  # pragma: no cover - the file exists right after os.replace
            pass


# ---------------------------------------------------------------------- import


def import_legacy_archive(
    root: str | Path,
    data_root: str | Path,
    store: Store | None = None,
    apply: bool = False,
) -> ImportReport:
    """Import the archive at ``root`` into ``data_root``.

    ``apply=False`` (the documented default) only reads and hashes: no blob,
    no process view and no SQLite row is written. ``store`` may be ``None`` in
    dry-run mode because nothing needs to be persisted.
    """

    scan = scan_legacy_archive(root)
    data_path = Path(data_root)
    report = ImportReport(
        mode="apply" if apply else "dry-run", archive_root=str(scan.archive_root)
    )
    for warning in scan.warnings:
        report.add_warning(warning)

    digests: dict[Path, str] = {}
    unique_sources: dict[str, Path] = {}
    for process in scan.processes:
        report.processes_seen += 1
        for document in process.documents:
            report.documents_seen += 1
            report.bytes_source += document.size_bytes
            try:
                digest = sha256_file(document.source_path)
            except OSError as exc:
                report.add_error(f"{document.archive_relative}: cannot hash the file: {exc}")
                continue
            digests[document.source_path] = digest
            if document.manifest_sha256 and document.manifest_sha256.casefold() != digest:
                report.add_warning(
                    f"{document.archive_relative}: manifest sha256 {document.manifest_sha256[:12]}… "
                    f"differs from the file hash {digest[:12]}…; the file hash wins"
                )
            if digest in unique_sources:
                report.duplicate_pdfs += 1
            else:
                unique_sources[digest] = document.source_path
                report.unique_pdfs += 1
                report.bytes_unique += document.size_bytes

    if apply:
        _materialize(scan, digests, data_path, store, report)

    report.finished_at = utc_now()
    _write_receipt(data_path, report)
    return report


def _materialize(
    scan: LegacyScan,
    digests: Mapping[Path, str],
    data_root: Path,
    store: Store | None,
    report: ImportReport,
) -> None:
    if store is None:
        raise LegacyImportError("apply mode needs an open Store to persist processes")

    verified: set[str] = set()
    for process in scan.processes:
        documents: list[DocumentRecord] = []
        for document in process.documents:
            digest = digests.get(document.source_path)
            if digest is None:
                continue
            view = data_root / document.view_relative
            if _is_same_file(document.source_path, view):
                # The archive root already *is* the process view; nothing to do.
                report.hardlinked_files += 1
            else:
                blob = _ensure_blob(data_root, digest, document.source_path, report, verified)
                if blob is None:
                    continue
                _ensure_process_view(view, blob, digest, report)
            documents.append(
                DocumentRecord(
                    source_id=document.source_id,
                    title=document.title,
                    relative_path=document.view_relative,
                    sha256=digest,
                    page_count=document.page_count,
                    event=document.event,
                    classification=document.classification,
                    storage_state="HOT",
                )
            )

        candidates = process.interests
        if not candidates:
            report.add_warning(
                f"{process.process_key}: no interested record found; imported as "
                f"'{UNKNOWN_INTERESTED}'"
            )
            candidates = [
                LegacyInterest(
                    original=UNKNOWN_INTERESTED,
                    normalized=normalize_interested(UNKNOWN_INTERESTED),
                )
            ]
        for interest in candidates:
            process_id = store.upsert_process(
                ProcessRecord(
                    process_key=process.process_key,
                    interested=interest.original,
                    interested_normalized=interest.normalized,
                    source_scope=None,
                    marker=None,
                    status=DEFAULT_PROCESS_STATUS,
                )
            )
            report.processes_upserted += 1
            store.replace_documents(process_id, documents)
            report.document_rows += len(documents)
            store.add_workflow_event(
                process_id,
                "legacy_import",
                {
                    "source": "acervo-tce",
                    "folder": process.folder,
                    "legacy_status": interest.legacy_status,
                    "document_count": len(documents),
                    "mode": report.mode,
                },
            )


# --------------------------------------------------------------- canonicalize


def canonicalize_process_tree(data_root: str | Path, store: Store | None = None) -> ImportReport:
    """Move verified bytes into the blob store and relink the process view.

    Only ``<data_root>/archive/processos`` is scanned and only files below it
    are touched. ``store`` is optional and used solely to report which process
    view paths have no document row yet, so the caller can register them.
    """

    data_path = Path(data_root)
    report = ImportReport(
        mode="canonicalize", archive_root=str(data_path / ARCHIVE_TREE)
    )
    process_root = data_path / ARCHIVE_TREE / PROCESS_TREE
    if not process_root.is_dir():
        report.finished_at = utc_now()
        return report

    registered: set[str] | None = None
    if store is not None:
        registered = {row["relative_path"] for row in store.list_all_documents()}

    verified: set[str] = set()
    seen: set[str] = set()
    for pdf in _iter_pdfs(process_root):
        relative = pdf.relative_to(data_path).as_posix()
        try:
            digest = sha256_file(pdf)
            size_bytes = pdf.stat().st_size
        except OSError as exc:
            report.add_error(f"{relative}: cannot hash the file: {exc}")
            continue

        report.documents_seen += 1
        report.bytes_source += size_bytes
        if digest in seen:
            report.duplicate_pdfs += 1
        else:
            seen.add(digest)
            report.unique_pdfs += 1
            report.bytes_unique += size_bytes
        if registered is not None and relative not in registered:
            report.unreferenced.append(relative)

        blob = blob_path(data_path, digest)
        if digest in verified and blob.is_file():
            report.reused_blobs += 1
            _relink_view(pdf, blob, report)
            continue
        if blob.is_file():
            if _is_same_file(pdf, blob):
                verified.add(digest)
                report.hardlinked_files += 1
                continue
            actual = sha256_file(blob)
            if actual != digest:
                report.add_error(
                    f"blob {blob} contains {actual[:12]}… but its name promises {digest[:12]}…; "
                    "refusing to relink"
                )
                continue
            verified.add(digest)
            report.verified_blobs += 1
            report.reused_blobs += 1
            _relink_view(pdf, blob, report)
            continue

        try:
            blob.parent.mkdir(parents=True, exist_ok=True)
            os.replace(pdf, blob)
        except OSError as exc:
            report.add_error(f"{relative}: cannot move the bytes into the blob store: {exc}")
            continue
        verified.add(digest)
        report.moved_files += 1
        try:
            outcome = _link_or_copy(blob, pdf)
        except OSError as exc:
            report.add_error(f"{relative}: cannot recreate the process view: {exc}")
            continue
        if outcome == "hardlink":
            report.hardlinked_files += 1
        else:
            report.fallback_copies += 1
            report.bytes_fallback_copies += size_bytes

    report.finished_at = utc_now()
    return report


def _relink_view(view: Path, blob: Path, report: ImportReport) -> None:
    """Replace a copied process-view file with a hardlink, never losing bytes."""

    if _is_same_file(view, blob):
        report.hardlinked_files += 1
        return
    temporary = view.with_name(view.name + ".relink")
    try:
        outcome = _link_or_copy(blob, temporary)
        os.replace(temporary, view)
    except OSError as exc:
        report.add_error(f"{view}: cannot relink to the canonical blob: {exc}")
        return
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:  # pragma: no cover - best effort cleanup
                pass
    if outcome == "hardlink":
        report.hardlinked_files += 1
    else:
        report.fallback_copies += 1
        try:
            report.bytes_fallback_copies += view.stat().st_size
        except OSError:  # pragma: no cover
            pass


# --------------------------------------------------------------------- receipt


def _write_receipt(data_root: Path, report: ImportReport) -> Path:
    logs = Path(data_root) / LOGS_TREE
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = logs / f"legacy-import-{stamp}.json"
    payload = report.to_dict()
    payload["receipt_path"] = str(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report.receipt_path = str(path)
    return path
