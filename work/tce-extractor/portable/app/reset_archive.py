"""Safely start a new local TCE archive cycle.

The operation only accepts ``package_root/acervo-tce`` as its target.  An
existing archive is moved to a recoverable backup before a new archive is
atomically installed with a fresh cycle identifier.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import uuid


ARCHIVE_NAME = "acervo-tce"
BACKUP_NAME = "backups-acervo"
CYCLE_FILE_NAME = "ciclo-acervo.json"
REPARSE_POINT_ATTRIBUTE = 0x0400


class ResetArchiveError(RuntimeError):
    """A reset was rejected or could not be completed safely."""


def _absolute(path: str | os.PathLike[str]) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(
        os.path.normpath(str(right))
    )


def _is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(os.path, "isjunction", None)
        if is_junction is not None and is_junction(str(path)):
            return True
        attributes = int(getattr(os.lstat(path), "st_file_attributes", 0))
        return bool(attributes & REPARSE_POINT_ATTRIBUTE)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ResetArchiveError(f"não foi possível inspecionar o caminho: {path}") from exc


def _assert_package_root(package_root: Path) -> Path:
    if not package_root.exists() or not package_root.is_dir():
        raise ResetArchiveError(f"packageRoot inválido ou inexistente: {package_root}")
    if _is_reparse_point(package_root):
        raise ResetArchiveError(f"packageRoot não pode ser reparse point: {package_root}")
    try:
        resolved = package_root.resolve(strict=True)
    except OSError as exc:
        raise ResetArchiveError(f"não foi possível validar packageRoot: {package_root}") from exc
    if not _same_path(resolved, package_root):
        raise ResetArchiveError(f"packageRoot contém reparse point: {package_root}")
    return package_root


def _assert_no_reparse_points(root: Path) -> None:
    if _is_reparse_point(root):
        raise ResetArchiveError(f"alvo contém reparse point: {root}")

    def raise_walk_error(error: OSError) -> None:
        raise error

    try:
        for current, directories, files in os.walk(
            root, topdown=True, followlinks=False, onerror=raise_walk_error
        ):
            for name in (*directories, *files):
                candidate = Path(current) / name
                if _is_reparse_point(candidate):
                    raise ResetArchiveError(f"alvo contém reparse point: {candidate}")
    except OSError as exc:
        raise ResetArchiveError(f"não foi possível validar o conteúdo de: {root}") from exc


def _validate_archive_target(package_root: Path, archive_root: Path) -> Path:
    expected = package_root / ARCHIVE_NAME
    if not _same_path(archive_root, expected):
        raise ResetArchiveError(
            f"alvo recusado; somente o diretório exato {expected} pode ser zerado"
        )
    if _is_reparse_point(archive_root):
        raise ResetArchiveError(f"acervo-tce não pode ser reparse point: {archive_root}")
    if archive_root.exists():
        if not archive_root.is_dir():
            raise ResetArchiveError(f"acervo-tce existente não é um diretório: {archive_root}")
        _assert_no_reparse_points(archive_root)
    return archive_root


def _write_cycle_marker(directory: Path, cycle_id: str) -> None:
    marker = directory / CYCLE_FILE_NAME
    temporary = directory / f".{CYCLE_FILE_NAME}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump({"version": 1, "id": cycle_id}, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, marker)
    finally:
        if temporary.exists():
            temporary.unlink()


def _new_backup_root(package_root: Path, transaction_id: str) -> Path:
    backup_parent = package_root / BACKUP_NAME
    if _is_reparse_point(backup_parent):
        raise ResetArchiveError(f"pasta de backups inválida ou reparse point: {backup_parent}")
    if backup_parent.exists():
        if not backup_parent.is_dir():
            raise ResetArchiveError(f"pasta de backups inválida ou reparse point: {backup_parent}")
    else:
        backup_parent.mkdir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return backup_parent / f"{timestamp}-{transaction_id}"


def reset_archive(
    package_root: str | os.PathLike[str],
    *,
    archive_root: str | os.PathLike[str] | None = None,
) -> dict[str, str | None]:
    """Create a fresh archive cycle and preserve the old archive if present."""

    root = _assert_package_root(_absolute(package_root))
    target = _absolute(archive_root) if archive_root is not None else root / ARCHIVE_NAME
    target = _validate_archive_target(root, target)

    cycle_id = str(uuid.uuid4())
    transaction_id = uuid.uuid4().hex
    backup_root: Path | None = None
    backup_archive: Path | None = None
    staging_root: Path | None = None

    try:
        backup_root = _new_backup_root(root, transaction_id)
        backup_archive = backup_root / ARCHIVE_NAME
        backup_root.mkdir()
        staging_root = root / BACKUP_NAME / f".reset-staging-{transaction_id}"
        staging_root.mkdir()
        _write_cycle_marker(staging_root, cycle_id)

        if target.exists():
            os.replace(target, backup_archive)
        os.replace(staging_root, target)
        staging_root = None

        backup_summary = str(backup_root) if backup_archive.exists() else None
        if backup_summary is None:
            try:
                backup_root.rmdir()
            except OSError:
                pass

        return {
            "archive_root": str(target),
            "backup_root": backup_summary,
            "cycle_id": cycle_id,
        }
    except (OSError, ValueError) as exc:
        rollback_errors: list[OSError] = []
        try:
            if staging_root is not None and staging_root.exists():
                shutil.rmtree(staging_root)
        except OSError as cleanup_error:
            rollback_errors.append(cleanup_error)
        try:
            if backup_archive is not None and backup_archive.exists() and not target.exists():
                os.replace(backup_archive, target)
        except OSError as restore_error:
            rollback_errors.append(restore_error)
        try:
            if backup_root is not None and backup_root.exists():
                try:
                    backup_root.rmdir()
                except OSError:
                    pass
        except OSError as cleanup_backup_error:
            rollback_errors.append(cleanup_backup_error)
        message = f"reset não concluído; o acervo anterior permanece protegido: {target}"
        if backup_root is not None and backup_root.exists():
            message += f"; verifique o backup {backup_root}"
        if rollback_errors:
            details = "; ".join(str(error) for error in rollback_errors)
            message += f"; rollback manual necessário: {details}"
        raise ResetArchiveError(message) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inicia um novo ciclo do acervo TCE.")
    parser.add_argument("--package-root", required=True, type=Path)
    parser.add_argument(
        "--archive-root",
        type=Path,
        help="somente para validação; deve ser exatamente package-root/acervo-tce",
    )
    args = parser.parse_args(argv)
    try:
        summary = reset_archive(args.package_root, archive_root=args.archive_root)
    except ResetArchiveError as exc:
        print(f"reset recusado: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
