#!/usr/bin/env python
"""Keep exactly two portable builds in ``dist/``.

The rotation publishes the *verified* build as ``Atos-TCE-portable.zip``, moves
the build it replaces to ``Atos-TCE-portable.previous.zip`` and removes every
other ZIP, so an upgrade never accumulates archives. Other files in ``dist/``
are reported and left alone.

It never runs on its own: the default is a dry-run, and ``--apply`` refuses to
work without ``--verified-hash`` (the SHA-256 that ``packaging/verify-package.ps1``
and ``packaging/build-portable.ps1`` report), so only a package that already
passed the gate can become the current build.

    python scripts/rotate-builds.py --dist dist
    python scripts/rotate-builds.py --dist dist --apply --verified-hash <sha256>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

CURRENT_NAME = "Atos-TCE-portable.zip"
PREVIOUS_NAME = "Atos-TCE-portable.previous.zip"
HASH_CHUNK_SIZE = 1024 * 1024


class RotationError(RuntimeError):
    """Raised when the rotation cannot run safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class BuildRotationPlan:
    """What the rotation would do, or did."""

    dist_root: str
    keep: tuple[str, ...]
    remove: tuple[str, ...]
    ignored: tuple[str, ...]
    remove_bytes: int
    current: str | None
    previous: str | None
    applied: bool
    verified_sha256: str | None
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dist_root": self.dist_root,
            "keep": list(self.keep),
            "remove": list(self.remove),
            "ignored": list(self.ignored),
            "remove_bytes": self.remove_bytes,
            "current": self.current,
            "previous": self.previous,
            "applied": self.applied,
            "verified_sha256": self.verified_sha256,
            "notes": list(self.notes),
        }


def _list_builds(dist_root: Path) -> tuple[list[Path], list[str]]:
    builds: list[Path] = []
    ignored: list[str] = []
    for entry in sorted(dist_root.iterdir(), key=lambda path: path.name):
        if entry.is_file() and entry.suffix.lower() == ".zip":
            builds.append(entry)
        elif entry.is_file():
            ignored.append(entry.name)
        else:
            ignored.append(entry.name + "/")
    return builds, ignored


def _newest(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    return max(paths, key=lambda path: (path.stat().st_mtime, path.name))


def rotate_builds(
    dist_root: str | Path,
    *,
    verified_sha256: str | None = None,
    apply: bool = False,
) -> BuildRotationPlan:
    """Report (and with ``apply=True`` execute) the retention of ``dist_root``."""

    root = Path(dist_root)
    if not root.is_dir():
        raise RotationError(f"dist root inexistente: {root}")
    builds, ignored = _list_builds(root)
    canonical_current = root / CURRENT_NAME
    canonical_previous = root / PREVIOUS_NAME
    notes: list[str] = []

    if apply and not verified_sha256:
        raise RotationError(
            "rotação recusada: informe --verified-hash do pacote que passou em "
            "packaging/verify-package.ps1"
        )

    current: Path | None = None
    if verified_sha256:
        wanted = verified_sha256.strip().lower()
        matches = [path for path in builds if sha256_file(path) == wanted]
        if not matches:
            raise RotationError(
                f"nenhum build em {root} tem o SHA-256 verificado {wanted}"
            )
        if len(matches) > 1:
            canonical_matches = [path for path in matches if path.name == CURRENT_NAME]
            if len(canonical_matches) != 1:
                raise RotationError(
                    "hash verificado corresponde a mais de um build; remova a duplicata antes de rotacionar"
                )
            current = canonical_matches[0]
        else:
            current = matches[0]
        if current.name != CURRENT_NAME:
            notes.append(f"build verificado {current.name} promovido a {CURRENT_NAME}")
    elif canonical_current.is_file():
        current = canonical_current
    else:
        current = _newest([path for path in builds])
        if current is not None:
            notes.append(f"sem {CURRENT_NAME}; o build mais recente ({current.name}) seria promovido")

    previous: Path | None
    if canonical_current.is_file() and current is not None and canonical_current != current:
        # The build being replaced becomes the previous one.
        previous = canonical_current
        notes.append(f"{CURRENT_NAME} atual passa a ser {PREVIOUS_NAME}")
    elif canonical_previous.is_file() and canonical_previous != current:
        previous = canonical_previous
    else:
        previous = _newest([path for path in builds if path != current])
        if previous is not None and previous.name not in (CURRENT_NAME, PREVIOUS_NAME):
            notes.append(f"build anterior mais recente ({previous.name}) passa a ser {PREVIOUS_NAME}")

    kept_paths = [path for path in (current, previous) if path is not None]
    remove = [path for path in builds if path not in kept_paths]
    keep = sorted({CURRENT_NAME if path == current else PREVIOUS_NAME for path in kept_paths})
    plan = BuildRotationPlan(
        dist_root=str(root.resolve()),
        keep=tuple(keep),
        remove=tuple(path.name for path in remove),
        ignored=tuple(ignored),
        remove_bytes=sum(path.stat().st_size for path in remove),
        current=current.name if current is not None else None,
        previous=previous.name if previous is not None else None,
        applied=False,
        verified_sha256=verified_sha256.lower() if verified_sha256 else None,
        notes=tuple(notes),
    )
    if not apply:
        return plan

    for path in remove:
        path.unlink()
    if previous is not None and previous.name != PREVIOUS_NAME:
        os.replace(previous, canonical_previous)
    if current is not None and current.name != CURRENT_NAME:
        os.replace(current, canonical_current)
    if current is not None and previous is not None and current == previous:  # pragma: no cover - guarded above
        raise RotationError("build atual e anterior não podem ser o mesmo arquivo")
    return BuildRotationPlan(
        dist_root=plan.dist_root,
        keep=plan.keep,
        remove=plan.remove,
        ignored=plan.ignored,
        remove_bytes=plan.remove_bytes,
        current=plan.current,
        previous=plan.previous,
        applied=True,
        verified_sha256=plan.verified_sha256,
        notes=plan.notes,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dist", type=Path, default=REPO_ROOT / "dist", help="dist folder holding the builds")
    parser.add_argument("--apply", action="store_true", help="really rotate (default: dry-run)")
    parser.add_argument(
        "--verified-hash",
        default=None,
        help="SHA-256 of the build that passed packaging/verify-package.ps1",
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
    try:
        plan = rotate_builds(args.dist, verified_sha256=args.verified_hash, apply=args.apply)
    except RotationError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
