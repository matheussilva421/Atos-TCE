#!/usr/bin/env python
"""Configure the external root the hybrid archive copies documents into.

The path is validated before anything is persisted: it must be absolute, must
not live inside the data root, the build output or the scratch areas, and it
must accept a real write. Only then is it recorded in the Mesa metadata.

    python scripts/configure-archive.py --data-root data --external-root D:/Atos-TCE-Archive
    python scripts/configure-archive.py --data-root data --show

The script never copies or removes a document: it only says where the archive
may go.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.manager import EXTERNAL_ROOT_KEY, ArchiveManager  # noqa: E402
from app.core.store import Store  # noqa: E402

PROBE_NAME = ".atos-tce-archive-probe"
FORBIDDEN_PARENTS = ("dist", "tmp", "outputs")


class ConfigureError(RuntimeError):
    """Raised when an external root cannot be used safely."""


def validate_external_root(
    candidate: str | Path, *, data_root: str | Path, repo_root: str | Path = REPO_ROOT
) -> Path:
    """Return the resolved external root, or explain why it cannot be used."""

    raw = Path(candidate)
    if not str(candidate).strip():
        raise ConfigureError("informe o caminho do arquivo externo")
    if not raw.is_absolute():
        raise ConfigureError("o caminho do arquivo externo precisa ser absoluto")
    resolved = raw.resolve()
    data = Path(data_root).resolve()
    if resolved == data or data in resolved.parents:
        raise ConfigureError("o arquivo externo não pode ficar dentro da raiz de dados")
    repo = Path(repo_root).resolve()
    for name in FORBIDDEN_PARENTS:
        forbidden = (repo / name).resolve()
        if resolved == forbidden or forbidden in resolved.parents:
            raise ConfigureError(f"o arquivo externo não pode ficar em {name}/")
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ConfigureError(f"não foi possível criar {resolved}: {error}") from error
    probe = resolved / PROBE_NAME
    try:
        probe.write_bytes(b"probe")
        probe.unlink()
    except OSError as error:
        raise ConfigureError(f"{resolved} não aceita escrita: {error}") from error
    return resolved


def configure(data_root: str | Path, external_root: str | Path) -> dict[str, Any]:
    """Validate the external root and persist it in the Mesa metadata."""

    store = Store.open(Path(data_root) / "atos-tce.db")
    try:
        resolved = validate_external_root(external_root, data_root=data_root)
        manager = ArchiveManager(store, data_root)
        manager.configure_external_root(resolved)
        return {
            "ok": True,
            "data_root": str(Path(data_root).resolve()),
            "external_root": str(resolved),
        }
    finally:
        store.close()


def show(data_root: str | Path) -> dict[str, Any]:
    """Report the configured external root without changing anything."""

    store = Store.open(Path(data_root) / "atos-tce.db")
    try:
        configured = store.get_metadata(EXTERNAL_ROOT_KEY)
        path = Path(configured) if configured else None
        usable = bool(path and path.is_dir())
        return {
            "ok": True,
            "data_root": str(Path(data_root).resolve()),
            "external_root": str(path) if path else None,
            "configured": path is not None,
            "usable": usable,
        }
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--data-root", type=Path, default=REPO_ROOT / "data", help="Mesa data root"
    )
    parser.add_argument(
        "--external-root", type=Path, default=None, help="absolute folder for archived documents"
    )
    parser.add_argument(
        "--show", action="store_true", help="only report the configured external root"
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
        if args.show or args.external_root is None:
            payload = show(args.data_root)
        else:
            payload = configure(args.data_root, args.external_root)
    except ConfigureError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

