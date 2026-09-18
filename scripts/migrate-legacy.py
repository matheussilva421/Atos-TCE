#!/usr/bin/env python
"""Migrate the legacy ``acervo-tce`` archive into the canonical Mesa data root.

The default mode is a dry-run: it scans and hashes the source archive and
reports what an ``--apply`` run would do, without writing blobs or SQLite rows.
The source archive is never modified in either mode.

    python scripts/migrate-legacy.py --archive-root work\tce-extractor\acervo-tce --data-root data
    python scripts/migrate-legacy.py --archive-root work\tce-extractor\acervo-tce --data-root data --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.legacy_import import import_legacy_archive  # noqa: E402
from app.core.store import Store  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive-root", required=True, type=Path, help="legacy archive containing processos/")
    parser.add_argument("--data-root", required=True, type=Path, help="Mesa data root that receives archive/ and logs/")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="materialize canonical blobs, the process view and SQLite rows (default: dry-run)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # The report contains Portuguese names; a Windows console defaults to a
    # legacy code page and would otherwise raise UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - depends on the host stream
                pass
    args = build_parser().parse_args(argv)
    store = Store.open(args.data_root / "atos-tce.db") if args.apply else None
    try:
        report = import_legacy_archive(
            args.archive_root, args.data_root, store, apply=args.apply
        )
    finally:
        if store is not None:
            store.close()
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
