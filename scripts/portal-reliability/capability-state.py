#!/usr/bin/env python
"""Controlled, non-promoting bootstrap for one capability's declared state.

The offline AR-1 contract being green is a build-time decision, so an operator
must be able to move manual_form_fill to EXPERIMENTAL on a clean data root
before the supervised qualification sequence can start.

This CLI deliberately has no path to QUALIFIED or PRODUCTION: those are earned
through the ledger, and only the recorder's promotion method can grant them.

Exit codes:
    0  the state was written
    2  the request itself is invalid
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.area_restrita.reliability import (  # noqa: E402 - after sys.path
    CAPABILITIES,
    ReliabilityError,
    ReliabilityRecorder,
)

UNKNOWN_BUILD = "unknown-build"
SAFE_BUILD = re.compile(r"^[A-Za-z0-9_.+\-]{1,128}$")


def resolve_build_id(repo_root: Path = REPO_ROOT) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN_BUILD
    sha = (result.stdout or "").strip()
    return sha if result.returncode == 0 and sha else UNKNOWN_BUILD


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--capability", required=True, choices=CAPABILITIES)
    parser.add_argument("--build", default=None)
    parser.add_argument("--reason", default=None)
    parser.add_argument(
        "--experimental",
        action="store_true",
        help="record EXPERIMENTAL (the offline contract is green)",
    )
    parser.add_argument(
        "--downgrade",
        action="store_true",
        help="return the capability to UNQUALIFIED",
    )
    args = parser.parse_args(argv)

    if bool(args.experimental) == bool(args.downgrade):
        print(
            json.dumps(
                {"ok": False, "error": "use exatamente um de --experimental ou --downgrade"},
                sort_keys=True,
            )
        )
        return 2

    build = args.build or resolve_build_id()
    if not SAFE_BUILD.fullmatch(build):
        print(json.dumps({"ok": False, "error": "build inválido"}, sort_keys=True))
        return 2

    try:
        recorder = ReliabilityRecorder(args.data_root, build)
        if args.experimental:
            reason = args.reason or f"contrato offline verde em {build} (nao qualifica)"
            recorder.mark_experimental(args.capability, reason=reason)
        else:
            reason = args.reason or f"rebaixado manualmente em {build}"
            recorder.downgrade(args.capability, reason=reason)
    except ReliabilityError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 2

    entry = recorder.capabilities()[args.capability]
    print(
        json.dumps(
            {"ok": True, "capability": args.capability, **entry},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

