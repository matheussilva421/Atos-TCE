#!/usr/bin/env python
"""Receipt-driven cleanup of the duplicated storage the audit proved redundant.

Fail-closed by design:

* the tool only ever touches the candidate trees listed in an audit receipt and
  refuses anything outside the repository, the canonical ``data/`` root, the
  ``dist/`` builds and the source trees;
* a tree is deletable only when the receipt says ``safe_to_delete`` and the
  canonical blob store exists;
* the tree is re-measured immediately before deletion: a different file count or
  byte total invalidates the receipt and a new audit is required;
* reparse points are refused, so a junction can never make the deletion escape
  the candidate;
* the retired legacy archive needs both ``--allow-legacy-archive`` and the M1
  migration receipt;
* the default is a dry-run, and every applied removal is written to
  ``data/logs/storage-cleanup-<UTC>.json``.

    python scripts/cleanup-storage.py --audit data/logs/storage-audit.json
    python scripts/cleanup-storage.py --audit data/logs/storage-audit.json --apply
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

RECEIPT_VERSION = 1
DATABASE_NAME = "atos-tce.db"
BLOB_TREE_PARTS = ("archive", "blobs")
LEGACY_ARCHIVE = "work/tce-extractor/acervo-tce"
PROTECTED_TOP_LEVEL = (
    ".git",
    "app",
    "data",
    "dist",
    "docs",
    "extension",
    "packaging",
    "scripts",
    "tests",
)


class CleanupError(RuntimeError):
    """Raised when the cleanup cannot run safely."""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class CleanupEntry:
    """One candidate tree and the decision taken for it."""

    relative_path: str
    category: str
    bytes: int
    file_count: int
    decision: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "category": self.category,
            "bytes": self.bytes,
            "file_count": self.file_count,
            "decision": self.decision,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class CleanupPlan:
    """What the cleanup would remove, or what it removed."""

    repo_root: str
    data_root: str
    audit: str
    entries: tuple[CleanupEntry, ...]
    delete: tuple[str, ...]
    refuse: tuple[str, ...]
    delete_bytes: int
    refused_bytes: int
    applied: bool
    receipt: str | None
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": self.repo_root,
            "data_root": self.data_root,
            "audit": self.audit,
            "entries": [entry.to_dict() for entry in self.entries],
            "delete": list(self.delete),
            "refuse": list(self.refuse),
            "delete_bytes": self.delete_bytes,
            "refused_bytes": self.refused_bytes,
            "applied": self.applied,
            "receipt": self.receipt,
            "notes": list(self.notes),
        }


def _read_audit(audit_path: Path) -> dict[str, Any]:
    if not audit_path.is_file():
        raise CleanupError(f"recibo de auditoria ausente: {audit_path}")
    try:
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CleanupError(f"recibo de auditoria ilegível ({audit_path}): {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise CleanupError(f"recibo de auditoria sem lista de candidatos: {audit_path}")
    return payload


def _tree_totals(root: Path) -> tuple[int, int, tuple[str, ...]]:
    """Return (file count, bytes, reparse points) for one tree."""

    files = 0
    total = 0
    links: list[str] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as scan:
                entries = list(scan)
        except OSError as error:
            raise CleanupError(f"árvore ilegível ({current}): {error}") from error
        for entry in entries:
            path = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise CleanupError(f"entrada ilegível ({path}): {error}") from error
            attributes = getattr(info, "st_file_attributes", 0)
            if entry.is_symlink() or (attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
                links.append(path.as_posix())
                continue
            if stat.S_ISDIR(info.st_mode):
                stack.append(path)
                continue
            if stat.S_ISREG(info.st_mode):
                files += 1
                total += int(info.st_size)
    return files, total, tuple(links)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _decide(
    candidate: dict[str, Any],
    *,
    repo_root: Path,
    data_root: Path,
    canonical_ready: bool,
    allow_legacy_archive: bool,
    migration_receipt: str | None,
    receipt_problems: tuple[str, ...] = (),
) -> CleanupEntry:
    relative = str(candidate.get("relative_path") or "")
    category = str(candidate.get("category") or "")
    recorded_bytes = int(candidate.get("bytes") or 0)
    recorded_files = int(candidate.get("file_count") or 0)
    reasons: list[str] = []

    pure = PurePosixPath(relative.replace("\\", "/"))
    if not relative or pure.is_absolute() or ".." in pure.parts:
        resolved = None
    else:
        resolved = (repo_root / pure).resolve()

    if resolved is None or not _inside(resolved, repo_root) or resolved == repo_root:
        return CleanupEntry(
            relative_path=relative,
            category=category,
            bytes=recorded_bytes,
            file_count=recorded_files,
            decision="refuse",
            reasons=("outside_repository",),
        )

    if not (candidate.get("exists") and resolved.is_dir()):
        reasons.append("absent")
    if pure.parts and pure.parts[0].lower() in PROTECTED_TOP_LEVEL:
        reasons.append("protected_path")
    if not canonical_ready:
        reasons.append("canonical_data_missing")
    if not candidate.get("safe_to_delete"):
        reasons.append("audit_not_safe")
    if relative == LEGACY_ARCHIVE:
        if not allow_legacy_archive:
            reasons.append("legacy_archive_requires_flag")
        elif migration_receipt is None:
            reasons.extend(receipt_problems or ("migration_receipt_missing",))

    if not reasons:
        files, total, links = _tree_totals(resolved)
        if links:
            reasons.append("reparse_point")
        elif files != recorded_files or total != recorded_bytes:
            reasons.append("changed_since_audit")

    return CleanupEntry(
        relative_path=relative,
        category=category,
        bytes=recorded_bytes,
        file_count=recorded_files,
        decision="refuse" if reasons else "delete",
        reasons=tuple(reasons),
    )


def _receipt_problem(payload: Any) -> tuple[str, ...]:
    """Return why one migration receipt cannot authorise a removal."""

    problems: list[str] = []
    if not isinstance(payload, dict):
        return ("migration_receipt_missing",)
    if str(payload.get("mode") or "").strip().lower() != "apply":
        problems.append("migration_receipt_not_apply")
    if payload.get("errors"):
        problems.append("migration_receipt_has_errors")
    return tuple(problems)


def _find_migration_receipt(
    data_root: Path, explicit: str | None
) -> tuple[str | None, tuple[str, ...]]:
    """Find an *applied* M1 migration receipt; a dry-run never authorises removal."""

    if explicit:
        candidates = [Path(explicit)]
    else:
        logs = data_root / "logs"
        candidates = sorted(logs.glob("legacy-import-*.json"), reverse=True) if logs.is_dir() else []
    last_problem: tuple[str, ...] = ("migration_receipt_missing",)
    for candidate in candidates:
        if not candidate.is_file():
            last_problem = ("migration_receipt_missing",)
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            last_problem = ("migration_receipt_unreadable",)
            continue
        problems = _receipt_problem(payload)
        if not problems:
            return str(candidate.resolve()), ()
        last_problem = problems
    return None, last_problem


def plan_cleanup(
    audit_path: str | Path,
    *,
    allow_legacy_archive: bool = False,
    migration_receipt: str | None = None,
) -> CleanupPlan:
    """Decide what an audit receipt allows deleting, without deleting anything."""

    audit_file = Path(audit_path).resolve()
    payload = _read_audit(audit_file)
    repo_root = Path(str(payload.get("repo_root") or REPO_ROOT)).resolve()
    data_root = Path(str(payload.get("data_root") or (repo_root / "data"))).resolve()
    if not repo_root.is_dir():
        raise CleanupError(f"raiz do projeto do recibo não existe: {repo_root}")

    canonical = payload.get("canonical") or {}
    blobs_root = data_root.joinpath(*BLOB_TREE_PARTS)
    canonical_ready = bool(blobs_root.is_dir()) and int(canonical.get("blob_count") or 0) > 0

    receipt, receipt_problems = _find_migration_receipt(data_root, migration_receipt)
    entries = tuple(
        _decide(
            candidate,
            repo_root=repo_root,
            data_root=data_root,
            canonical_ready=canonical_ready,
            allow_legacy_archive=allow_legacy_archive,
            migration_receipt=receipt,
            receipt_problems=receipt_problems,
        )
        for candidate in payload["candidates"]
        if isinstance(candidate, dict)
    )
    approved = tuple(entry for entry in entries if entry.decision == "delete")
    refused = tuple(entry for entry in entries if entry.decision != "delete")
    notes: list[str] = []
    if not canonical_ready:
        notes.append(f"acervo canônico ausente ou vazio em {blobs_root}; nenhuma remoção é permitida")
    if receipt:
        notes.append(f"recibo de migração de M1: {receipt}")

    return CleanupPlan(
        repo_root=str(repo_root),
        data_root=str(data_root),
        audit=str(audit_file),
        entries=entries,
        delete=tuple(entry.relative_path for entry in approved),
        refuse=tuple(entry.relative_path for entry in refused),
        delete_bytes=sum(entry.bytes for entry in approved),
        refused_bytes=sum(entry.bytes for entry in refused),
        applied=False,
        receipt=None,
        notes=tuple(notes),
    )


def _remove_tree(path: Path) -> None:
    def on_error(function: Any, target: Any, error: Any) -> None:
        # Windows marks some archived files read-only; retry once without it.
        try:
            os.chmod(target, stat.S_IWRITE)
            function(target)
        except OSError:
            raise error

    shutil.rmtree(path, onexc=on_error)


def apply_cleanup(
    audit_path: str | Path,
    *,
    allow_legacy_archive: bool = False,
    migration_receipt: str | None = None,
    receipt_path: str | Path | None = None,
) -> CleanupPlan:
    """Delete exactly the candidates the receipt approved and log a receipt."""

    plan = plan_cleanup(
        audit_path,
        allow_legacy_archive=allow_legacy_archive,
        migration_receipt=migration_receipt,
    )
    repo_root = Path(plan.repo_root)
    data_root = Path(plan.data_root)
    audit_payload = _read_audit(Path(plan.audit))
    removed: list[dict[str, Any]] = []

    for entry in plan.entries:
        if entry.decision != "delete":
            continue
        target = (repo_root / PurePosixPath(entry.relative_path)).resolve()
        if not _inside(target, repo_root) or target == repo_root:
            raise CleanupError(f"alvo fora do repositório durante a remoção: {target}")
        files, total, links = _tree_totals(target)
        if links:
            raise CleanupError(f"reparse point apareceu em {target} depois do plano; novo recibo necessário")
        if files != entry.file_count or total != entry.bytes:
            raise CleanupError(
                f"{entry.relative_path} mudou depois do plano "
                f"({files} arquivos/{total} bytes contra {entry.file_count}/{entry.bytes}); rode a auditoria de novo"
            )
        _remove_tree(target)
        removed.append(
            {
                "relative_path": entry.relative_path,
                "category": entry.category,
                "bytes": entry.bytes,
                "file_count": entry.file_count,
            }
        )

    destination = Path(receipt_path) if receipt_path else data_root / "logs" / f"storage-cleanup-{utc_stamp()}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "receipt_version": RECEIPT_VERSION,
        "created_at": utc_now(),
        "audit": plan.audit,
        "repo_root": plan.repo_root,
        "data_root": plan.data_root,
        "canonical": audit_payload.get("canonical") or {},
        "removed": removed,
        "removed_bytes": sum(item["bytes"] for item in removed),
        "refused": [
            {"relative_path": entry.relative_path, "reasons": list(entry.reasons)}
            for entry in plan.entries
            if entry.decision != "delete"
        ],
        "refused_bytes": plan.refused_bytes,
    }
    destination.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return CleanupPlan(
        repo_root=plan.repo_root,
        data_root=plan.data_root,
        audit=plan.audit,
        entries=plan.entries,
        delete=plan.delete,
        refuse=plan.refuse,
        delete_bytes=plan.delete_bytes,
        refused_bytes=plan.refused_bytes,
        applied=True,
        receipt=str(destination.resolve()),
        notes=plan.notes,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--audit", type=Path, required=True, help="storage-audit.json receipt to honour")
    parser.add_argument("--apply", action="store_true", help="really delete (default: dry-run)")
    parser.add_argument(
        "--allow-legacy-archive",
        action="store_true",
        help="allow retiring work/tce-extractor/acervo-tce when the M1 receipt exists",
    )
    parser.add_argument("--migration-receipt", default=None, help="explicit M1 migration receipt path")
    parser.add_argument("--json", type=Path, default=None, help="also write the plan to this file")
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
            plan = apply_cleanup(
                args.audit,
                allow_legacy_archive=args.allow_legacy_archive,
                migration_receipt=args.migration_receipt,
            )
        else:
            plan = plan_cleanup(
                args.audit,
                allow_legacy_archive=args.allow_legacy_archive,
                migration_receipt=args.migration_receipt,
            )
    except CleanupError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    payload = json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
