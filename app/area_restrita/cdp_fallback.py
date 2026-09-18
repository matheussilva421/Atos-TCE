"""Read-only CDP compatibility fallback for the Área Restrita scan.

The extension installed in the operator's browser is the primary path. This
module exists for diagnosis and compatibility: it drives the *same* scanner
through Chrome DevTools Protocol against the already authenticated tab, and
persists the result through the same ``Store.create_area_scan`` path so both
origins produce one identical schema.

It never writes a field, never opens Complementar Ato, never selects an
interested person and never clicks a conclusion control. The only navigation it
may perform is list pagination.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..core.store import Store
from . import PORTAL_ROLES

CDP_SCRIPT_RELATIVE = Path("scripts") / "scan-area-cdp.ps1"
DEFAULT_TIMEOUT_SECONDS = 600
MAX_CDP_PAGES = 50


class CdpScanError(RuntimeError):
    """Raised when the compatibility scan cannot produce a usable snapshot."""


@dataclass(slots=True)
class CdpScanResult:
    ok: bool
    snapshot: dict[str, Any] | None = None
    error: str | None = None
    exit_code: int | None = None


def build_cdp_scan_command(
    repo_root: str | Path,
    *,
    max_pages: int | None = None,
    chrome_user_data: str | Path | None = None,
) -> list[str]:
    """Build the argument vector for the read-only compatibility script.

    The vector deliberately contains no credential, no cookie and no
    write/finalise switch: there is nothing to leak and nothing to submit.
    """

    command = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path(repo_root) / CDP_SCRIPT_RELATIVE),
    ]
    if max_pages is not None:
        command += ["-MaxPages", str(int(max_pages))]
    if chrome_user_data is not None:
        command += ["-ChromeUserData", str(chrome_user_data)]
    return command


def parse_cdp_output(stdout: str) -> dict[str, Any]:
    """Parse the single JSON object the compatibility script prints."""

    text = (stdout or "").strip()
    if not text:
        raise CdpScanError("the compatibility scan produced no output")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise CdpScanError("the compatibility scan produced no JSON object")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise CdpScanError(f"invalid JSON from the compatibility scan: {error.msg}") from error
    if not isinstance(payload, dict):
        raise CdpScanError("the compatibility scan must print a JSON object")
    # Windows PowerShell collapses a one-element array when it is piped; keep
    # accepting that shape instead of silently dropping a single row.
    if isinstance(payload.get("rows"), dict):
        payload["rows"] = [payload["rows"]]
    return payload


def run_cdp_scan(
    repo_root: str | Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_pages: int | None = None,
    chrome_user_data: str | Path | None = None,
) -> CdpScanResult:
    """Run the compatibility script once and return a validated snapshot."""

    root = Path(repo_root)
    script = root / CDP_SCRIPT_RELATIVE
    if not script.is_file():
        return CdpScanResult(ok=False, error=f"script not found: {CDP_SCRIPT_RELATIVE.as_posix()}")

    command = build_cdp_scan_command(root, max_pages=max_pages, chrome_user_data=chrome_user_data)
    execute = runner or subprocess.run
    try:
        completed = execute(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CdpScanResult(ok=False, error="the compatibility scan timed out")
    except OSError as error:
        return CdpScanResult(ok=False, error=f"cannot run the compatibility scan: {type(error).__name__}")

    if completed.returncode != 0:
        # The console output may quote portal content, so it is never echoed.
        return CdpScanResult(
            ok=False,
            error=f"the compatibility scan failed (exit code {completed.returncode})",
            exit_code=completed.returncode,
        )
    try:
        snapshot = parse_cdp_output(completed.stdout or "")
    except CdpScanError as error:
        return CdpScanResult(ok=False, error=str(error), exit_code=0)
    if str(snapshot.get("role") or "") not in PORTAL_ROLES:
        return CdpScanResult(
            ok=False,
            error="the compatibility scan did not report a known portal role",
            exit_code=0,
        )
    return CdpScanResult(ok=True, snapshot=snapshot, exit_code=0)


def persist_cdp_scan(store: Store, snapshot: dict[str, Any], origin: str = "cdp") -> int:
    """Persist a CDP snapshot through the same path the extension result uses."""

    if not isinstance(snapshot, dict):
        raise CdpScanError("the compatibility snapshot must be a JSON object")
    role = str(snapshot.get("role") or "")
    if role not in PORTAL_ROLES:
        raise CdpScanError(f"unknown portal role: {role or 'missing'}")
    rows = snapshot.get("rows")
    if not isinstance(rows, list):
        raise CdpScanError("the compatibility snapshot must carry a rows list")
    marker = snapshot.get("marker")
    marker = marker if isinstance(marker, dict) else {}
    return store.create_area_scan(
        source_scope=str(snapshot.get("source_scope") or "") or "unknown",
        marker_label=str(marker.get("label") or "") or None,
        marker_value=str(marker.get("value") or "") or None,
        rows=rows,
        origin=origin,
    )
