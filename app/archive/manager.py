"""Hybrid archive: HOT, ARCHIVED and MISSING documents (M6 Task 2).

One canonical blob still owns each byte sequence. Archiving copies the blob to
an external root, verifies the copied hash, and only then removes the local
process-view link; the canonical blob itself is removed only when no HOT
document still needs it. A failure at any point leaves the local source and its
metadata untouched, because losing the last verified copy is the one outcome
this module must never produce.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.store import Store, utc_now
from .legacy_import import BLOB_TREE, blob_path, sha256_file

#: Metadata key holding the configured external archive root.
EXTERNAL_ROOT_KEY = "archive.external_root"


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
        """Move one process's documents to the external root, verified."""

        external_root = self.external_root
        if external_root is None:
            raise ArchiveError("nenhum local externo de arquivo está configurado")
        documents = self._store.list_documents(process_id)
        result = ArchiveResult(ok=True, documents=len(documents))
        if not documents:
            return result

        archived_shas: list[str] = []
        for digest in sorted({str(document["sha256"]) for document in documents}):
            blob = self.local_blob(digest)
            if not blob.is_file():
                self._store.set_blob_presence(digest, local_present=False)
                result.errors.append(f"{digest[:12]}…: blob canônico ausente; nada foi arquivado")
                result.ok = False
                continue
            target = self.external_blob(digest)
            try:
                self._copy_verified(blob, target, digest)
            except (OSError, ArchiveError) as error:
                result.errors.append(str(error))
                result.ok = False
                continue
            self._store.set_blob_presence(
                digest,
                size_bytes=blob.stat().st_size,
                external_path=str(target),
                local_present=True,
                external_present=True,
                verified_at=utc_now(),
            )
            archived_shas.append(digest)

        for document in documents:
            if str(document["sha256"]) not in archived_shas:
                continue
            view = self._data_root / str(document["relative_path"])
            if view.is_file():
                view.unlink()
            self._store.mark_document_storage_state(int(document["id"]), "ARCHIVED")
            result.archived.append(str(document["sha256"]))

        for digest in archived_shas:
            if self._store.count_hot_documents(digest):
                continue
            blob = self.local_blob(digest)
            if blob.is_file():
                blob.unlink()
            self._store.set_blob_presence(digest, local_present=False, external_present=True)
        return result

    # --------------------------------------------------------------- restore

    def restore_process(self, process_id: int) -> ArchiveResult:
        """Bring one process's archived documents back to HOT."""

        documents = self._store.list_documents(process_id)
        result = ArchiveResult(ok=True, documents=len(documents))
        for document in documents:
            if str(document["storage_state"]) != "ARCHIVED":
                continue
            digest = str(document["sha256"])
            blob = self.local_blob(digest)
            if not blob.is_file():
                external = self.external_blob(digest)
                if external is None or not external.is_file():
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
        """Verify presence per blob and mark documents accordingly.

        Presence is a filesystem fact; ``verified_at`` is only refreshed by the
        archive/restore paths, which hash the bytes they move. MISSING is only
        declared when neither a local nor an external copy exists.
        """

        summary: dict[str, Any] = {
            "checked": 0,
            "hot": 0,
            "archived": 0,
            "missing": 0,
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
            local_present = local_file.is_file()
            external_present = False
            configured = blob_row.get("external_path")
            if configured and Path(str(configured)).is_file():
                external_present = True
            elif external_root is not None:
                candidate = self.external_blob(digest)
                external_present = bool(candidate and candidate.is_file())
            self._store.set_blob_presence(
                digest,
                local_present=local_present,
                external_present=external_present,
                external_path=str(configured) if configured else None,
                size_bytes=local_file.stat().st_size if local_present else None,
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
