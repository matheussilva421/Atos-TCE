#!/usr/bin/env python
"""Verifiable restore of a Mesa backup produced by scripts/backup.py.

The default is a dry-run that validates everything without writing anything:
the manifest version, every ZIP CRC, the database SHA-256 and the SHA-256 of
every blob member. Only --apply extracts, and even then nothing is published
until the extracted database has been opened read-only and every extracted
blob has been hashed again.

    python scripts/restore-backup.py --backup D:/backups/atos-tce.zip --data-root data
    python scripts/restore-backup.py --backup D:/backups/atos-tce.zip --data-root data --apply

Nothing here ever deletes: an existing data root is moved aside with a
timestamped name, never removed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.legacy_import import ARCHIVE_TREE, BLOB_TREE  # noqa: E402
from app.core.store import SCHEMA_VERSION, Store, StoreError  # noqa: E402

HASH_CHUNK_SIZE = 1024 * 1024
DATABASE_NAME = "atos-tce.db"
MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1


class RestoreError(RuntimeError):
    """Raised when a backup cannot be restored without risking the archive."""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _safe_member(name: str) -> str:
    """Return the member name as a relative POSIX path, or refuse it."""

    candidate = str(name or "").replace(chr(92), "/")
    pure = PurePosixPath(candidate)
    if not candidate or pure.is_absolute() or ".." in pure.parts:
        raise RestoreError(f"caminho inválido dentro do backup: {name!r}")
    if ":" in pure.parts[0]:
        raise RestoreError(f"caminho absoluto dentro do backup: {name!r}")
    return pure.as_posix()


@dataclass
class RestorePlan:
    """What a restore would do, with every check already applied."""

    backup: str
    data_root: str
    manifest: dict[str, Any]
    blob_count: int
    blob_bytes: int
    database_bytes: int
    schema_version: int
    target_exists: bool
    target_non_empty: bool
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup": self.backup,
            "data_root": self.data_root,
            "blob_count": self.blob_count,
            "blob_bytes": self.blob_bytes,
            "database_bytes": self.database_bytes,
            "schema_version": self.schema_version,
            "target_exists": self.target_exists,
            "target_non_empty": self.target_non_empty,
            "ok": self.ok,
            "problems": list(self.problems),
        }


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, Any]:
    try:
        raw = archive.read(MANIFEST_NAME)
    except KeyError as error:
        raise RestoreError("o backup não tem manifest.json") from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RestoreError(f"manifest.json ilegível: {error}") from error
    if not isinstance(payload, dict):
        raise RestoreError("manifest.json não é um objeto JSON")
    version = int(payload.get("manifest_version") or 0)
    if version != MANIFEST_VERSION:
        raise RestoreError(f"manifest_version {version} não é suportada")
    return payload


def _database_schema_version(payload: bytes) -> int:
    """Read the schema version of a database held in memory, read-only."""

    with tempfile.TemporaryDirectory() as work:
        candidate = Path(work) / DATABASE_NAME
        candidate.write_bytes(payload)
        connection = sqlite3.connect(f"file:{candidate.as_posix()}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
        except sqlite3.DatabaseError as error:
            raise RestoreError(f"o banco do backup não é um SQLite legível: {error}") from error
        finally:
            connection.close()
    return int(row[0]) if row is not None else 0


def plan_restore(backup: str | Path, data_root: str | Path) -> RestorePlan:
    """Validate a backup end to end without writing anything."""

    backup_path = Path(backup).resolve()
    target = Path(data_root).resolve()
    if not backup_path.is_file():
        raise RestoreError(f"backup ausente: {backup_path}")
    try:
        archive = zipfile.ZipFile(backup_path)
    except (zipfile.BadZipFile, OSError) as error:
        raise RestoreError(f"backup ilegível: {error}") from error
    with archive:
        broken = archive.testzip()
        if broken is not None:
            raise RestoreError(f"membro do backup falhou no CRC: {broken}")
        manifest = _read_manifest(archive)
        names = {_safe_member(info.filename) for info in archive.infolist() if not info.is_dir()}

        database_path = _safe_member(str(manifest.get("database_path") or DATABASE_NAME))
        if database_path not in names:
            raise RestoreError("o backup não contém o banco de dados")
        database_bytes = archive.read(database_path)
        db_sha256 = hashlib.sha256(database_bytes).hexdigest()
        if db_sha256 != str(manifest.get("db_sha256") or ""):
            raise RestoreError("o banco do backup não confere com o manifest")
        if len(database_bytes) != int(manifest.get("db_bytes") or -1):
            raise RestoreError("o tamanho do banco do backup não confere com o manifest")

        blobs = manifest.get("blobs")
        if not isinstance(blobs, list):
            raise RestoreError("manifest sem lista de blobs")
        expected = {database_path, MANIFEST_NAME}
        blob_bytes = 0
        for entry in blobs:
            if not isinstance(entry, dict):
                raise RestoreError("entrada de blob inválida no manifest")
            sha = str(entry.get("sha256") or "").strip().lower()
            arcname = _safe_member(str(entry.get("path") or ""))
            expected.add(arcname)
            if arcname not in names:
                raise RestoreError(f"o backup não contém o blob {sha[:12]}…")
            if PurePosixPath(arcname).stem != sha:
                raise RestoreError(f"o caminho do blob não corresponde ao sha {sha[:12]}…")
            with archive.open(arcname) as handle:
                digest, size = _hash_stream(handle)
            if digest != sha:
                raise RestoreError(f"o blob {sha[:12]}… não confere com o próprio sha")
            if size != int(entry.get("bytes") or -1):
                raise RestoreError(f"o blob {sha[:12]}… tem tamanho diferente do manifest")
            blob_bytes += size
        unexpected = sorted(names - expected)
        if unexpected:
            raise RestoreError(f"o backup tem membros fora do manifest: {unexpected[:3]}")

        schema_version = _database_schema_version(database_bytes)

    problems: list[str] = []
    if schema_version != int(manifest.get("schema_version") or -1):
        problems.append("schema_version do banco difere do manifest")
    if schema_version != SCHEMA_VERSION:
        problems.append(
            f"schema_version {schema_version} não é a suportada ({SCHEMA_VERSION}); "
            "restaure com a versão do programa que gerou o backup"
        )
    non_empty = target.is_dir() and any(target.iterdir())
    return RestorePlan(
        backup=str(backup_path),
        data_root=str(target),
        manifest=manifest,
        blob_count=len(blobs),
        blob_bytes=blob_bytes,
        database_bytes=len(database_bytes),
        schema_version=schema_version,
        target_exists=target.exists(),
        target_non_empty=non_empty,
        problems=problems,
    )


def _extract(archive: zipfile.ZipFile, staging: Path, names: set[str]) -> None:
    """Extract exactly the validated members, never trusting the ZIP layout."""

    staging.mkdir(parents=True, exist_ok=False)
    for name in sorted(names):
        destination = staging.joinpath(*PurePosixPath(name).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(name) as source, open(destination, "wb") as target:
            while True:
                chunk = source.read(HASH_CHUNK_SIZE)
                if not chunk:
                    break
                target.write(chunk)


def _reconcile_blobs(data_root: Path) -> dict[str, int]:
    """Re-derive blob presence from the restored filesystem."""

    store = Store.open(data_root / DATABASE_NAME)
    try:
        blobs_root = data_root / ARCHIVE_TREE / BLOB_TREE
        present = 0
        absent = 0
        registered = {str(row["sha256"]) for row in store.list_archive_blobs()}
        for sha in sorted(registered | set(store.list_document_shas())):
            path = blobs_root / sha[:2] / f"{sha}.pdf"
            exists = path.is_file()
            store.set_blob_presence(
                sha,
                local_present=exists,
                size_bytes=path.stat().st_size if exists else None,
            )
            present += 1 if exists else 0
            absent += 0 if exists else 1
        return {"blobs_present": present, "blobs_absent": absent}
    finally:
        store.close()


def apply_restore(
    backup: str | Path,
    data_root: str | Path,
    *,
    allow_non_empty: bool = False,
) -> dict[str, Any]:
    """Restore a validated backup, publishing the data root atomically."""

    plan = plan_restore(backup, data_root)
    if not plan.ok:
        raise RestoreError("; ".join(plan.problems))
    if plan.target_non_empty and not allow_non_empty:
        raise RestoreError(
            f"{plan.data_root} não está vazio; use --allow-non-empty para substituí-lo"
        )

    target = Path(plan.data_root)
    staging = target.with_name(f".{target.name}.restoring-{utc_stamp()}")
    if staging.exists():
        raise RestoreError(f"diretório de preparação já existe: {staging}")
    previous: Path | None = None
    with zipfile.ZipFile(Path(plan.backup)) as archive:
        names = {_safe_member(info.filename) for info in archive.infolist() if not info.is_dir()}
        _extract(archive, staging, names)
        restored_db = staging / DATABASE_NAME
        if _hash_file(restored_db) != str(plan.manifest.get("db_sha256") or ""):
            raise RestoreError("o banco extraído não confere com o manifest")
        try:
            probe = Store.open_read_only(restored_db)
        except StoreError as error:
            raise RestoreError(f"o banco extraído não abre: {error}") from error
        probe.close()
        for entry in plan.manifest.get("blobs") or []:
            path = staging.joinpath(*PurePosixPath(_safe_member(str(entry["path"]))).parts)
            if _hash_file(path) != str(entry["sha256"]):
                raise RestoreError(f"o blob extraído {str(entry['sha256'])[:12]}… não confere")
        if target.exists():
            previous = target.with_name(f"{target.name}.before-restore-{utc_stamp()}")
            os.replace(target, previous)
        os.replace(staging, target)
    summary = {
        "backup": plan.backup,
        "data_root": str(target),
        "blob_count": plan.blob_count,
        "blob_bytes": plan.blob_bytes,
        "database_bytes": plan.database_bytes,
        "schema_version": plan.schema_version,
        "previous_data_root": str(previous) if previous is not None else None,
        "applied": True,
    }
    summary.update(_reconcile_blobs(target))
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--backup", type=Path, required=True, help="backup .zip to restore")
    parser.add_argument(
        "--data-root", type=Path, default=REPO_ROOT / "data", help="data root to restore into"
    )
    parser.add_argument("--apply", action="store_true", help="really restore (default: dry-run)")
    parser.add_argument(
        "--allow-non-empty",
        action="store_true",
        help="move an existing data root aside and publish the restored one",
    )
    parser.add_argument("--json", type=Path, default=None, help="also write the report to this file")
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
        if args.apply:
            payload = apply_restore(
                args.backup, args.data_root, allow_non_empty=args.allow_non_empty
            )
        else:
            plan = plan_restore(args.backup, args.data_root)
            payload = plan.to_dict()
            payload["applied"] = False
    except RestoreError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + chr(10), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
