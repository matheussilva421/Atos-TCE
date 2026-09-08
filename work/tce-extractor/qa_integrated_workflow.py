"""Fixture-only QA report for the portable workflow.

This command deliberately does not log in, open a browser, contact the portal,
or submit an act. Real portal QA remains a supervised human checkpoint.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping


def run_fixture_checks(project_root: Path) -> dict:
    root = Path(project_root)
    extension = root / "portable" / "extensao-complementar-ato"
    required = {
        "extension_signal": extension / "content" / "form-detector.js",
        "manual_search": extension / "sidepanel" / "panel.js",
        "bridge_client": extension / "lib" / "bridge-client.js",
        "visual_evidence": root / "portable" / "app" / "evidence_geometry.py",
        "local_service": root / "portable" / "app" / "local_service.py",
    }
    checks = {name: path.is_file() for name, path in required.items()}
    checks["no_portal_qa"] = True
    checks["no_submit_automation"] = "submit" not in (extension / "content" / "form-detector.js").read_text(encoding="utf-8").casefold()
    return {
        "status": "fixture-only",
        "portal_login": "not-run",
        "portal_submission": "not-run",
        "checks": checks,
        "passed": all(checks.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--fixture-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.fixture_only:
        print(json.dumps({"status": "human-checkpoint-required", "portal_qa": "not-run"}, ensure_ascii=False))
        return 2
    report = run_fixture_checks(args.project_root)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
