"""Hybrid archive: HOT, ARCHIVED and MISSING documents (M6 Task 2).

One canonical blob still owns each byte sequence. Archiving copies the blob to
an external root, verifies the copied hash, and only then removes the local
process-view link; the canonical blob itself is removed only when no HOT
document still needs it. A failure at any point leaves the local source and its
metadata untouched, because losing the last verified copy is the one outcome
this module must never produce.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.store import Store, utc_now
from .legacy_import import BLOB_TREE, blob_path, sha256_file

#: Metadata key holding the configured external archive root.
EXTERNAL_ROOT_KEY = "archive.external_root"

#: Metadata key holding the journal of an archiving commit that is in flight.
#: While it exists, the process is neither fully HOT nor fully ARCHIVED and the
#: recovery below is mandatory before any new archive/restore action.
JOURNAL_KEY = "archive.journal"


class ArchiveError(RuntimeError):
    """Raised when archiving cannot proceed without risking the last copy."""


@dataclass(slots=True)
class ArchiveResult:
    ok: bool
    documents: int = 0
    archived: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ArchiveManager:
    def __init__(self, store: Store, data_root: str | Path, *, external_root: str | Path | None = None) -> None:
        self._store = store
        self._data_root = Path(data_root)
        self._external_root = Path(external_root) if external_root is not None else None
        #: path/size/mtime -> "the bytes hash to the expected digest".
        self._verified_cache: dict[tuple[str, int, int], bool] = {}

    # ------------------------------------------------------------- configured

    @property
    def external_root(self) -> Path | None:
        if self._external_root is not None:
            return self._external_root
        configured = self._store.get_metadata(EXTERNAL_ROOT_KEY)
        return Path(configured) if configured else None

    def configure_external_root(self, path: str | Path) -> Path:
        resolved = Path(path).resolve()
        self._store.set_metadata(EXTERNAL_ROOT_KEY, str(resolved))
        self._external_root = resolved
        return resolved

    def local_blob(self, sha256: str) -> Path:
        return blob_path(self._data_root, sha256)

    def external_blob(self, sha256: str) -> Path | None:
        root = self.external_root
        if root is None:
            return None
        return root / BLOB_TREE / sha256[:2] / f"{sha256}.pdf"

    # ------------------------------------------------------------ primitives

    def verified(self, path: Path, digest: str) -> bool:
        """True only when the file really hashes to the expected digest.

        The answer is cached by (path, size, mtime), so a tree that did not
        change is not re-hashed on every reconciliation, while a file that did
        change is hashed again.
        """

        try:
            info = path.stat()
        except OSError:
            return False
        key = (str(path), int(info.st_size), int(info.st_mtime_ns))
        cached = self._verified_cache.get(key)
        if cached is not None:
            return cached
        try:
            actual = sha256_file(path)
        except OSError:  # pragma: no cover - defensive
            return False
        self._verified_cache[key] = actual == digest
        return self._verified_cache[key]

    @staticmethod
    def _discard_staging(staging: Path) -> None:
        """Remove a staging tree that was never published (best effort)."""

        if not staging.exists():
            return
        try:
            shutil.rmtree(staging)
        except OSError:  # pragma: no cover - best effort
            pass

    def _unlink_view(self, view: Path) -> None:
        """Remove one process view; the canonical blob is never touched here."""

        if view.is_file():
            view.unlink()

    @staticmethod
    def _copy_verified(source: Path, target: Path, digest: str) -> None:
        """Publish ``source`` at ``target`` only after its hash matches."""

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".part")
        try:
            shutil.copy2(source, temporary)
            actual = sha256_file(temporary)
            if actual != digest:
                raise ArchiveError(f"{target}: cópia com hash {actual[:12]}… diferente de {digest[:12]}…")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:  # pragma: no cover - best effort cleanup
                    pass

    def _ensure_view(self, view: Path, blob: Path, digest: str) -> None:
        """Recreate the process view as a verified hardlink, or a copy."""

        if view.is_file():
            try:
                if os.path.samefile(view, blob):
                    return
            except OSError:  # pragma: no cover - defensive
                pass
        view.parent.mkdir(parents=True, exist_ok=True)
        temporary = view.with_name(view.name + ".relink")
        try:
            os.link(blob, temporary)
            os.replace(temporary, view)
            return
        except OSError:
            if temporary.exists():  # pragma: no cover - best effort
                temporary.unlink(missing_ok=True)
        if sha256_file(blob) != digest:  # pragma: no cover - defensive
            raise ArchiveError(f"{blob}: blob não confere com o hash esperado")
        shutil.copy2(blob, view)

    # --------------------------------------------------------------- archive

    def archive_process(self, process_id: int) -> ArchiveResult:
        """Move one process's documents to the external root, verified.

        Two phases per process. Phase 1 copies and verifies every SHA into a
        staging area of the external root and changes no state at all; a single
        failure discards the staging copies and leaves every document HOT.
        Phase 2 publishes, unlinks the views and updates the metadata only
        after the whole process passed, so a process is never half archived.
        """

        external_root = self.external_root
        if external_root is None:
            raise ArchiveError("nenhum local externo de arquivo está configurado")
        if self._store.get_metadata(JOURNAL_KEY):
            raise ArchiveError(
                "há um arquivamento inacabado; rode recover_archive_journal antes de arquivar de novo"
            )
        documents = self._store.list_documents(process_id)
        result = ArchiveResult(ok=True, documents=len(documents))
        if not documents:
            return result

        # ---------------------------------------------------- phase 1: prepare
        staging = external_root / f".staging-{int(process_id)}"
        prepared: dict[str, Path] = {}
        for digest in sorted({str(document["sha256"]) for document in documents}):
            blob = self.local_blob(digest)
            if not blob.is_file():
                self._store.set_blob_presence(digest, local_present=False)
                result.errors.append(f"{digest[:12]}…: blob canônico ausente; nada foi arquivado")
                result.ok = False
                continue
            target = self.external_blob(digest)
            if target is not None and target.is_file() and self.verified(target, digest):
                prepared[digest] = target
                continue
            staged = staging / digest[:2] / f"{digest}.pdf"
            try:
                self._copy_verified(blob, staged, digest)
            except (OSError, ArchiveError) as error:
                result.errors.append(str(error))
                result.ok = False
                continue
            prepared[digest] = staged

        if not result.ok:
            # Nothing was published and nothing changed: every document is HOT.
            self._discard_staging(staging)
            return result

        # ----------------------------------------------------- phase 2: commit
        journal = {
            "process_id": int(process_id),
            "started_at": utc_now(),
            "blobs": [
                {
                    "sha256": digest,
                    "staged": str(staged),
                    "target": str(self.external_blob(digest)),
                }
                for digest, staged in sorted(prepared.items())
            ],
            "documents": [
                {
                    "id": int(document["id"]),
                    "sha256": str(document["sha256"]),
                    "view": str(document["relative_path"]),
                }
                for document in documents
                if str(document["sha256"]) in prepared
            ],
        }
        self._store.set_metadata(
            JOURNAL_KEY, json.dumps(journal, ensure_ascii=False, sort_keys=True)
        )
        try:
            self._commit_archive(journal, result)
        except Exception as error:  # any failure keeps the journal for recovery
            # The journal stays behind on purpose: recovery finishes or rolls
            # back the operation before any new archive/restore action.
            result.errors.append(f"{type(error).__name__}: {error}")
            result.ok = False
            result.archived = []
            return result
        self._store.set_metadata(JOURNAL_KEY, None)
        return result

    def _commit_archive(self, journal: Mapping[str, Any], result: ArchiveResult) -> None:
        """Publish, mark and free one journaled archiving; idempotent by design.

        Every step can be repeated: a target that already verifies is not
        copied again, a document already ARCHIVED is simply marked again, and a
        view that is already gone is not an error.
        """

        blobs = [entry for entry in journal.get("blobs") or [] if isinstance(entry, Mapping)]
        for entry in blobs:
            digest = str(entry.get("sha256") or "")
            target = Path(str(entry.get("target") or ""))
            staged = Path(str(entry.get("staged") or "")) if entry.get("staged") else None
            if not (target.is_file() and self.verified(target, digest)):
                if staged is None or not (staged.is_file() and self.verified(staged, digest)):
                    raise ArchiveError(
                        f"{digest[:12]}…: cópia externa ausente durante o commit do arquivamento"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, target)
            self._store.set_blob_presence(
                digest,
                size_bytes=target.stat().st_size,
                external_path=str(target),
                local_present=True,
                external_present=True,
                verified_at=utc_now(),
            )
        for entry in journal.get("documents") or []:
            if not isinstance(entry, Mapping):
                continue
            view = self._data_root / str(entry.get("view") or "")
            self._unlink_view(view)
            self._store.mark_document_storage_state(int(entry["id"]), "ARCHIVED")
            result.archived.append(str(entry.get("sha256") or ""))
        for entry in blobs:
            digest = str(entry.get("sha256") or "")
            if self._store.count_hot_documents(digest):
                continue
            local = self.local_blob(digest)
            if local.is_file():
                local.unlink()
            self._store.set_blob_presence(digest, local_present=False, external_present=True)
        staging = self.external_root / f".staging-{int(journal.get('process_id') or 0)}"
        self._discard_staging(staging)

    def _rollback_archive(self, journal: Mapping[str, Any]) -> None:
        """Leave every document of an unfinished archiving HOT again."""

        for entry in journal.get("blobs") or []:
            if not isinstance(entry, Mapping):
                continue
            staged = str(entry.get("staged") or "")
            if not staged:
                continue
            try:
                Path(staged).unlink(missing_ok=True)
            except OSError:  # pragma: no cover - best effort
                pass
        for entry in journal.get("documents") or []:
            if not isinstance(entry, Mapping):
                continue
            try:
                self._store.mark_document_storage_state(int(entry["id"]), "HOT")
            except (ValueError, TypeError):  # pragma: no cover - defensive
                pass
        self._discard_staging(
            self.external_root / f".staging-{int(journal.get('process_id') or 0)}"
        )

    def recover_archive_journal(self) -> dict[str, Any]:
        """Finish or roll back an archiving that stopped halfway.

        The journal is the only evidence that a commit started. Every external
        copy is verified: when all of them are there the operation completes
        (roll forward), otherwise nothing changes and every document goes back
        to HOT (roll back). Either way the process ends all ARCHIVED or all HOT,
        never in between, and the journal is cleared only at the end.
        """

        raw = self._store.get_metadata(JOURNAL_KEY)
        if not raw:
            return {"state": "clean", "completed": 0, "rolled_back": 0}
        try:
            journal = json.loads(raw)
        except ValueError:
            self._store.set_metadata(JOURNAL_KEY, None)
            return {"state": "unreadable", "completed": 0, "rolled_back": 0}
        if not isinstance(journal, Mapping):
            self._store.set_metadata(JOURNAL_KEY, None)
            return {"state": "unreadable", "completed": 0, "rolled_back": 0}

        ready = True
        for entry in journal.get("blobs") or []:
            if not isinstance(entry, Mapping):
                ready = False
                break
            digest = str(entry.get("sha256") or "")
            target = Path(str(entry.get("target") or ""))
            if target.is_file() and self.verified(target, digest):
                continue
            staged = Path(str(entry.get("staged") or "")) if entry.get("staged") else None
            if staged is None or not (staged.is_file() and self.verified(staged, digest)):
                ready = False
                break
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, target)
            except OSError:
                ready = False
                break

        if not ready:
            self._rollback_archive(journal)
            self._store.set_metadata(JOURNAL_KEY, None)
            return {"state": "rolled_back", "completed": 0, "rolled_back": 1}

        result = ArchiveResult(ok=True, documents=len(journal.get("documents") or []))
        self._commit_archive(journal, result)
        self._store.set_metadata(JOURNAL_KEY, None)
        return {"state": "completed", "completed": 1, "rolled_back": 0}

    # --------------------------------------------------------------- restore

    def restore_process(self, process_id: int) -> ArchiveResult:
        """Bring one process's archived documents back to HOT."""

        if self._store.get_metadata(JOURNAL_KEY):
            raise ArchiveError(
                "há um arquivamento inacabado; rode recover_archive_journal antes de restaurar"
            )
        documents = self._store.list_documents(process_id)
        result = ArchiveResult(ok=True, documents=len(documents))
        for document in documents:
            if str(document["storage_state"]) != "ARCHIVED":
                continue
            digest = str(document["sha256"])
            blob = self.local_blob(digest)
            # A local file that does not hash to its digest is not a copy.
            if not (blob.is_file() and self.verified(blob, digest)):
                external = self.external_blob(digest)
                if external is None or not (
                    external.is_file() and self.verified(external, digest)
                ):
                    self._store.mark_document_storage_state(int(document["id"]), "MISSING")
                    self._store.set_blob_presence(
                        digest, local_present=False, external_present=False
                    )
                    result.missing.append(digest)
                    result.ok = False
                    continue
                try:
                    self._copy_verified(external, blob, digest)
                except (OSError, ArchiveError) as error:
                    result.errors.append(str(error))
                    result.ok = False
                    continue
                self._store.set_blob_presence(
                    digest, size_bytes=blob.stat().st_size, local_present=True, external_present=True
                )
            view = self._data_root / str(document["relative_path"])
            try:
                self._ensure_view(view, blob, digest)
            except (OSError, ArchiveError) as error:
                result.errors.append(str(error))
                result.ok = False
                continue
            self._store.mark_document_storage_state(int(document["id"]), "HOT")
            result.restored.append(digest)
        return result

    # ----------------------------------------------------------- reconcile

    def reconcile_locations(self) -> dict[str, Any]:
        """Verify integrity per blob and mark documents accordingly.

        A file that exists but does not hash to its digest is not a copy: it is
        reported as corrupt and never counts as HOT or ARCHIVED. MISSING is
        only declared when neither an intact local nor an intact external copy
        exists, and every verified copy refreshes verified_at.
        """

        summary: dict[str, Any] = {
            "checked": 0,
            "hot": 0,
            "archived": 0,
            "missing": 0,
            "corrupt": 0,
            "documents_marked": 0,
        }
        external_root = self.external_root
        # Reconcile every SHA the documents reference, not only the ones the
        # migration registered: a document added later still needs its presence
        # verified.
        registered = {str(row["sha256"]): row for row in self._store.list_archive_blobs()}
        for digest in sorted(set(registered) | set(self._store.list_document_shas())):
            blob_row = registered.get(digest, {"sha256": digest})
            summary["checked"] += 1
            local_file = self.local_blob(digest)
            local_exists = local_file.is_file()
            local_present = local_exists and self.verified(local_file, digest)
            if local_exists and not local_present:
                summary["corrupt"] += 1
            external_present = False
            configured = blob_row.get("external_path")
            configured_path = Path(str(configured)) if configured else None
            if configured_path is not None and configured_path.is_file():
                external_present = self.verified(configured_path, digest)
                if not external_present:
                    summary["corrupt"] += 1
            elif external_root is not None:
                candidate = self.external_blob(digest)
                external_present = bool(
                    candidate and candidate.is_file() and self.verified(candidate, digest)
                )
            self._store.set_blob_presence(
                digest,
                local_present=local_present,
                external_present=external_present,
                external_path=str(configured) if configured else None,
                size_bytes=local_file.stat().st_size if local_present else None,
                verified_at=utc_now() if (local_present or external_present) else None,
            )
            key = "hot" if local_present else ("archived" if external_present else "missing")
            summary[key] += 1
            for document in self._store.documents_for_sha(digest):
                state = str(document["storage_state"])
                if local_present and state != "HOT":
                    self._store.mark_document_storage_state(int(document["id"]), "HOT")
                    summary["documents_marked"] += 1
                elif not local_present and external_present and state == "HOT":
                    self._store.mark_document_storage_state(int(document["id"]), "ARCHIVED")
                    summary["documents_marked"] += 1
                elif not local_present and not external_present and state != "MISSING":
                    self._store.mark_document_storage_state(int(document["id"]), "MISSING")
                    summary["documents_marked"] += 1
        return summary
