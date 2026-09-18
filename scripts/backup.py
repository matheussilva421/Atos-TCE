#!/usr/bin/env python
"""Explicit full backup of the Mesa data root, with a restore manifest.

A backup is an operator action, never a release artefact: the command always
needs ``--output`` and nothing schedules it. The ZIP holds the SQLite snapshot,
every canonical blob and ``manifest.json`` with the SHA-256 of each file.

The database is snapshotted through the SQLite backup API, so rows that still
live in the write-ahead log (the store runs in WAL mode) are restored too; a
plain file copy would silently lose them.

    python scripts/backup.py --data-root data --output D:\backups\atos-tce-2026-09-18.zip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.legacy_import import ARCHIVE_TREE, BLOB_TREE  # noqa: E402

HASH_CHUNK_SIZE = 1024 * 1024
DATABASE_NAME = "atos-tce.db"
MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
BLOB_STEM_RE = re.compile(r"^[0-9a-f]{64}$")


class BackupError(RuntimeError):
    """Raised when a backup cannot be produced or verified."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class BackupEntry:
    """One canonical blob inside the backup."""

    sha256: str
    path: str
    bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {"sha256": self.sha256, "path": self.path, "bytes": self.bytes}


@dataclass(frozen=True)
class BackupManifest:
    """What the backup contains, written inside the ZIP for restoration."""

    manifest_version: int
    schema_version: int
    created_at: str
    database_path: str
    db_sha256: str
    db_bytes: int
    file_count: int
    blob_bytes: int
    total_bytes: int
    blob_sha256: tuple[str, ...]
    blobs: tuple[BackupEntry, ...]
    name_mismatches: tuple[str, ...]
    #: How many blobs came from the local tree, from the external archive and
    #: how many had no intact copy at all (always zero: a missing copy aborts).
    sources: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "database_path": self.database_path,
            "db_sha256": self.db_sha256,
            "db_bytes": self.db_bytes,
            "file_count": self.file_count,
            "blob_bytes": self.blob_bytes,
            "total_bytes": self.total_bytes,
            "blob_sha256": list(self.blob_sha256),
            "blobs": [entry.to_dict() for entry in self.blobs],
            "name_mismatches": list(self.name_mismatches),
            "sources": dict(self.sources),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BackupManifest":
        """Rebuild a manifest from the JSON stored inside a backup."""

        return cls(
            manifest_version=int(payload["manifest_version"]),
            schema_version=int(payload["schema_version"]),
            created_at=str(payload["created_at"]),
            database_path=str(payload["database_path"]),
            db_sha256=str(payload["db_sha256"]),
            db_bytes=int(payload["db_bytes"]),
            file_count=int(payload["file_count"]),
            blob_bytes=int(payload["blob_bytes"]),
            total_bytes=int(payload["total_bytes"]),
            blob_sha256=tuple(str(value) for value in payload["blob_sha256"]),
            blobs=tuple(
                BackupEntry(
                    sha256=str(entry["sha256"]),
                    path=str(entry["path"]),
                    bytes=int(entry["bytes"]),
                )
                for entry in payload["blobs"]
            ),
            name_mismatches=tuple(str(value) for value in payload.get("name_mismatches", ())),
            sources={
                str(key): int(value) for key, value in (payload.get("sources") or {}).items()
            },
        )


def _snapshot_database(database: Path, target: Path) -> None:
    """Write a consistent copy of ``database``, including the WAL contents."""

    source = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        destination = sqlite3.connect(str(target))
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()


def _snapshot_schema_version(snapshot: Path) -> int:
    connection = sqlite3.connect(f"file:{snapshot.as_posix()}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
    finally:
        connection.close()
    return int(row[0]) if row is not None else 0


def _snapshot_blobs(snapshot: Path) -> dict[str, dict[str, Any]]:
    """Every SHA the snapshot references, with where its copy may live.

    The backup is driven by the database, not by the local blob folder: after a
    document is archived, the only intact copy can be the external one, and a
    backup that ignored it would restore a database pointing at nothing.
    """

    connection = sqlite3.connect(f"file:{snapshot.as_posix()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT sha256, size_bytes, external_path FROM archive_blobs"
        ).fetchall()
        referenced = {
            str(row[0]).strip().lower()
            for row in connection.execute("SELECT DISTINCT sha256 FROM documents")
            if row and row[0]
        }
    finally:
        connection.close()
    blobs = {
        str(row[0]).strip().lower(): {
            "size_bytes": int(row[1] or 0),
            "external_path": str(row[2] or "").strip(),
        }
        for row in rows
        if row and row[0]
    }
    for sha in blobs:
        referenced.add(sha)
    return {sha: blobs.get(sha, {"size_bytes": 0, "external_path": ""}) for sha in sorted(referenced)}


def _canonical_arcname(sha: str) -> str:
    """The one path a blob always has inside a backup, wherever it came from."""

    return f"{ARCHIVE_TREE}/{BLOB_TREE}/{sha[:2]}/{sha}.pdf"


def _local_blob_files(data_root: Path) -> list[Path]:
    """Every regular file under the canonical blob tree, links never followed."""

    blobs_root = data_root / ARCHIVE_TREE / BLOB_TREE
    if not blobs_root.is_dir():
        return []
    found: list[Path] = []
    for current, directory_names, file_names in os.walk(blobs_root, followlinks=False):
        directory_names[:] = [
            name for name in sorted(directory_names) if not Path(current, name).is_symlink()
        ]
        for name in sorted(file_names):
            path = Path(current, name)
            if path.is_symlink():
                continue
            found.append(path)
    return found


def _backup_blob_set(snapshot: Path, data_root: Path) -> dict[str, dict[str, Any]]:
    """The referenced SHAs plus every local blob, so no local byte is dropped."""

    blobs = _snapshot_blobs(snapshot)
    for path in _local_blob_files(data_root):
        sha = path.stem.strip().lower()
        if not BLOB_STEM_RE.match(sha):
            raise BackupError(f"nome de blob inesperado no acervo: {path.name}")
        blobs.setdefault(sha, {"size_bytes": path.stat().st_size, "external_path": ""})
    return blobs


def _intact_source(
    data_root: Path, sha: str, external_path: Any
) -> tuple[Path, str] | None:
    """The local copy when it is intact, otherwise the verified external one."""

    local = data_root / ARCHIVE_TREE / BLOB_TREE / sha[:2] / f"{sha}.pdf"
    if local.is_file() and _hash_file(local) == sha:
        return local, "local"
    raw = str(external_path or "").strip()
    if not raw:
        return None
    external = Path(raw)
    if external.is_file() and _hash_file(external) == sha:
        return external, "external"
    return None


def _stream_into_archive(archive: zipfile.ZipFile, path: Path, arcname: str, info: zipfile.ZipInfo):
    """Copy one file into the archive, returning its SHA-256 and byte count."""

    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as source, archive.open(info, "w") as target:
        while True:
            chunk = source.read(HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            target.write(chunk)
    return digest.hexdigest(), size


def _verify_backup(archive_path: Path, expected: BackupManifest) -> None:
    """Fail closed unless the written ZIP matches its own manifest."""

    try:
        with zipfile.ZipFile(archive_path) as archive:
            broken = archive.testzip()
            if broken is not None:
                raise BackupError(f"backup member failed its CRC check: {broken}")
            stored = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            if stored != expected.to_dict():
                raise BackupError("backup manifest does not match the written archive")
            names = set(archive.namelist())
            for entry in expected.blobs:
                if entry.path not in names:
                    raise BackupError(f"backup is missing blob {entry.sha256}")
            if expected.database_path not in names:
                raise BackupError("backup is missing the database snapshot")
    except zipfile.BadZipFile as error:
        raise BackupError(f"backup is not a readable ZIP: {error}") from error


def create_backup(data_root: str | Path, destination: str | Path) -> BackupManifest:
    """Write an explicit full backup of ``data_root`` to ``destination``."""

    data_path = Path(data_root).resolve()
    target = Path(destination).resolve()
    database = data_path / DATABASE_NAME
    if not database.is_file():
        raise BackupError(f"no database at {database}; nothing to back up")
    archive_root = (data_path / ARCHIVE_TREE).resolve()
    if target == archive_root or archive_root in target.parents:
        raise BackupError(
            f"refusing to write a backup inside {archive_root}; "
            "choose an output path outside data/archive"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_zip = target.with_name(target.name + ".tmp")
    if temporary_zip.exists():
        raise BackupError(f"temporary path already exists: {temporary_zip}")

    try:
        with tempfile.TemporaryDirectory(dir=str(target.parent), prefix=".backup-") as work:
            snapshot = Path(work) / DATABASE_NAME
            _snapshot_database(database, snapshot)
            schema_version = _snapshot_schema_version(snapshot)
            db_sha256 = _hash_file(snapshot)
            db_bytes = snapshot.stat().st_size

            entries: list[BackupEntry] = []
            mismatches: list[str] = []
            local_sources = 0
            external_sources = 0
            missing: list[str] = []
            with zipfile.ZipFile(temporary_zip, "w", allowZip64=True) as archive:
                archive.write(snapshot, DATABASE_NAME, compress_type=zipfile.ZIP_DEFLATED)
                for digest, blob in _backup_blob_set(snapshot, data_path).items():
                    source = _intact_source(data_path, digest, blob.get("external_path"))
                    if source is None:
                        missing.append(digest)
                        continue
                    if source[1] == "local":
                        local_sources += 1
                    else:
                        external_sources += 1
                    path = source[0]
                    arcname = _canonical_arcname(digest)
                    info = zipfile.ZipInfo(arcname)
                    info.compress_type = zipfile.ZIP_STORED
                    info.external_attr = 0o644 << 16
                    written, size = _stream_into_archive(archive, path, arcname, info)
                    entries.append(BackupEntry(sha256=written, path=arcname, bytes=size))
                    if written != digest:
                        mismatches.append(arcname)
                if missing or mismatches:
                    raise BackupError(
                        "backup abortado: "
                        f"{len(missing)} blob(s) sem cópia íntegra e {len(mismatches)} divergência(s)"
                    )
                entries.sort(key=lambda entry: entry.sha256)
                manifest = BackupManifest(
                    manifest_version=MANIFEST_VERSION,
                    schema_version=schema_version,
                    created_at=utc_now(),
                    database_path=DATABASE_NAME,
                    db_sha256=db_sha256,
                    db_bytes=db_bytes,
                    file_count=len(entries),
                    blob_bytes=sum(entry.bytes for entry in entries),
                    total_bytes=sum(entry.bytes for entry in entries) + db_bytes,
                    blob_sha256=tuple(entry.sha256 for entry in entries),
                    blobs=tuple(entries),
                    name_mismatches=tuple(sorted(mismatches)),
                    sources={
                        "local": local_sources,
                        "external": external_sources,
                        "missing": 0,
                    },
                )
                archive.writestr(
                    MANIFEST_NAME,
                    json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n",
                    compress_type=zipfile.ZIP_DEFLATED,
                )
            _verify_backup(temporary_zip, manifest)
        os.replace(temporary_zip, target)
    except BackupError:
        temporary_zip.unlink(missing_ok=True)
        raise
    except OSError as error:
        temporary_zip.unlink(missing_ok=True)
        raise BackupError(f"backup failed: {error.strerror or error}") from error
    except Exception as error:  # pragma: no cover - defensive cleanup
        temporary_zip.unlink(missing_ok=True)
        raise BackupError(f"backup failed: {type(error).__name__}: {error}") from error
    return manifest


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--data-root", type=Path, default=REPO_ROOT / "data", help="Mesa data root to back up"
    )
    parser.add_argument("--output", type=Path, required=True, help="destination .zip file")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - host stream dependent
                pass
    args = build_parser().parse_args(argv)
    try:
        manifest = create_backup(args.data_root, args.output)
    except BackupError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    payload = dict(manifest.to_dict())
    payload["destination"] = str(Path(args.output).resolve())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
