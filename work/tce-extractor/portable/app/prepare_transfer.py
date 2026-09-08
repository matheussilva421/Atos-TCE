"""Prepare a consistent private portable snapshot without bridge credentials."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from package_complete_archive import build_complete_zip


def _active_bridge(package_root: Path) -> bool:
    metadata = package_root / "dados-locais" / "bridge" / "service.json"
    if not metadata.exists():
        return False
    try:
        value = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(value, Mapping) and isinstance(value.get("pid"), int)


def prepare_transfer(package_root: Path, destination: Path) -> dict:
    """Build a new private ZIP, leaving bridge state outside the archive.

    The current coordinator is single-writer and publication is atomic, so the
    preparation point is a read-only snapshot boundary. Callers must stop a
    running service explicitly before moving the package to another machine.
    """
    root = Path(package_root).resolve()
    output = Path(destination).resolve()
    if output.exists():
        raise FileExistsError(f"destino já existe: {output}")
    stats = build_complete_zip(root, output, distribution="private")
    return {
        **dict(stats),
        "path": str(output),
        "bridge_active_at_start": _active_bridge(root),
        "bridge_state_included": False,
        "progress_included": True,
    }
