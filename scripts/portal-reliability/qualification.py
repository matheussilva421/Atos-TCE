#!/usr/bin/env python
"""Read-only evaluator for one Area Restrita qualification sequence.

The CLI never promotes and never edits the ledger: it reads the sanitized
reliability events and answers one question — does the latest consecutive
sequence satisfy the requested gate on the requested build?

Exit codes:
    0  the latest consecutive sequence satisfies the gate on that build
    1  it does not (short, broken by a failure or intervention, other build)
    2  the request itself is invalid
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.area_restrita.reliability import (  # noqa: E402 - after sys.path
    CAPABILITIES,
    MIN_QUALIFICATION_RUNS,
    PRODUCTION_ENVIRONMENT,
    QUALIFICATION_ENVIRONMENT,
    ReliabilityError,
    ReliabilityRecorder,
)

UNKNOWN_BUILD = "unknown-build"


def resolve_build_id(repo_root: Path = REPO_ROOT) -> str:
    """The checkout SHA, so the reader and the writer agree by default."""

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


def evaluate_request(
    *, data_root: str, capability: str, environment: str, required: int, build: str
) -> dict:
    """Return the sanitized evaluation payload for one request."""

    recorder = ReliabilityRecorder(data_root, build)
    result = recorder.evaluate(capability, environment, required)
    observed = result.get("build_id")
    same_build = observed == build
    return {
        "ok": bool(result["qualified"]) and same_build,
        "capability": capability,
        "environment": environment,
        "required": int(required),
        "streak": int(result["streak"]),
        "build": build,
        "observed_streak_build": observed,
        "same_build": same_build,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--capability", required=True, choices=CAPABILITIES)
    # Only the two real environments can ever gate a capability: an offline
    # sequence never proves a real qualification.
    parser.add_argument(
        "--environment",
        required=True,
        choices=(QUALIFICATION_ENVIRONMENT, PRODUCTION_ENVIRONMENT),
    )
    parser.add_argument("--required", type=int, default=MIN_QUALIFICATION_RUNS)
    parser.add_argument("--build", default=None)
    args = parser.parse_args(argv)

    if args.required < MIN_QUALIFICATION_RUNS:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"required precisa ser >= {MIN_QUALIFICATION_RUNS}",
                },
                sort_keys=True,
            )
        )
        return 2

    build = args.build or resolve_build_id()
    try:
        payload = evaluate_request(
            data_root=args.data_root,
            capability=args.capability,
            environment=args.environment,
            required=args.required,
            build=build,
        )
    except ReliabilityError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 2

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

