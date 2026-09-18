"""Adapter around the proven e-Contas collector.

M3 does not replace the download engine: it drives it. The Mesa decides which
process keys are eligible, writes the frozen queue, and this module invokes the
existing PowerShell collector with exactly those keys.

Two safety rules live here:

* nothing that identifies a person, a URL or a credential is echoed back — the
  progress callback only ever receives redacted lines;
* an authentication failure is reported as ``auth_required`` so the caller can
  pause the job instead of hammering the portal.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

COLLECTOR_SCRIPT = Path("work") / "tce-extractor" / "portable" / "Coletar-Processos-TCE.ps1"
DEFAULT_TIMEOUT_SECONDS = 3600
DEFAULT_MAX_DOWNLOADS = 2
OUTPUT_TAIL_LIMIT = 25

SUMMARY_PATTERN = re.compile(
    r"Conclu[ií]do \((?P<mode>[^)]+)\)\.\s*"
    r"Baixados:\s*(?P<downloaded>\d+);\s*"
    r"reutilizados:\s*(?P<reused>\d+);\s*"
    r"deduplicados:\s*(?P<deduplicated>\d+);\s*"
    r"processos com falha:\s*(?P<failed>\d+)\.",
    re.IGNORECASE,
)

AUTH_MARKERS = (
    "faça login",
    "faca login",
    "login novamente",
    "sessão expirada",
    "sessao expirada",
    "não autorizada",
    "nao autorizada",
    "sem token",
    "unauthorized",
    "not authenticated",
)

URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
BEARER_PATTERN = re.compile(r"\bbearer\s+\S+", re.IGNORECASE)
SECRET_PATTERN = re.compile(
    r"\b(token|senha|password|authorization|credencial|chave)\b\s*[:=]\s*\S+", re.IGNORECASE
)
LONG_SECRET_PATTERN = re.compile(r"[A-Za-z0-9_\-\.]{40,}")


@dataclass(slots=True)
class CollectorRequest:
    queue_path: Path
    lot_number: int
    destination: Path
    source_scope: str = "sector_finalistic"
    keep_browser_open: bool = True
    #: M4: the Mesa runs the analysis itself, so the collector must not prepare.
    preparation_mode: str = "nenhum"
    max_downloads: int = DEFAULT_MAX_DOWNLOADS


@dataclass(slots=True)
class CollectorResult:
    exit_code: int
    downloaded: int = 0
    reused: int = 0
    deduplicated: int = 0
    failed: int = 0
    auth_required: bool = False
    summary_found: bool = False
    error: str | None = None
    output_tail: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.summary_found and not self.auth_required


def build_collector_command(request: CollectorRequest, repo_root: str | Path) -> list[str]:
    """Build the argument vector for the proven collector.

    ``-Selecao`` is never passed (the Mesa owns selection through the frozen
    queue) and ``-ServiceChild`` is never passed (the new Mesa is not the legacy
    service parent and must not claim its lock).
    """

    command = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path(repo_root) / COLLECTOR_SCRIPT),
        "-Destino",
        str(Path(request.destination)),
        "-FilaCongelada",
        str(Path(request.queue_path)),
        "-NumeroLote",
        str(int(request.lot_number)),
        "-EscopoPortal",
        str(request.source_scope),
        "-ModoPreparacao",
        str(request.preparation_mode),
        "-MaxDownloads",
        str(int(request.max_downloads)),
        "-NaoInterativo",
    ]
    if request.keep_browser_open:
        command.append("-ManterNavegadorAberto")
    return command


def parse_summary_line(line: str) -> dict[str, object] | None:
    """Parse the collector's final summary line, if present."""

    match = SUMMARY_PATTERN.search(str(line or ""))
    if match is None:
        return None
    return {
        "mode": match.group("mode").strip(),
        "downloaded": int(match.group("downloaded")),
        "reused": int(match.group("reused")),
        "deduplicated": int(match.group("deduplicated")),
        "failed": int(match.group("failed")),
    }


def is_auth_required(line: str) -> bool:
    """True when the console line describes a login/session problem."""

    folded = str(line or "").casefold()
    return any(marker in folded for marker in AUTH_MARKERS)


def redact(line: str) -> str:
    """Remove URLs and anything token-shaped before anything is logged."""

    text = URL_PATTERN.sub("<url>", str(line or ""))
    text = BEARER_PATTERN.sub("Bearer <redigido>", text)
    text = SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=<redigido>", text)
    return LONG_SECRET_PATTERN.sub("<redigido>", text)


def run_collector(
    request: CollectorRequest,
    on_line: Callable[[str], None] | None = None,
    repo_root: str | Path | None = None,
    *,
    runner: Callable[..., object] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> CollectorResult:
    """Run one lot and report only what the Mesa needs to know."""

    root = Path(repo_root) if repo_root is not None else Path.cwd()
    command = build_collector_command(request, root)
    execute = runner or subprocess.Popen
    try:
        process = execute(
            command,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        return CollectorResult(
            exit_code=-1,
            error=f"cannot start the legacy collector: {type(error).__name__}",
        )

    result = CollectorResult(exit_code=0)
    for raw_line in _iter_lines(process):
        line = str(raw_line).rstrip("\r\n")
        if not line.strip():
            continue
        summary = parse_summary_line(line)
        if summary is not None:
            result.summary_found = True
            result.downloaded = int(summary["downloaded"])
            result.reused = int(summary["reused"])
            result.deduplicated = int(summary["deduplicated"])
            result.failed = int(summary["failed"])
        elif is_auth_required(line):
            result.auth_required = True
        safe = redact(line)
        result.output_tail.append(safe)
        if len(result.output_tail) > OUTPUT_TAIL_LIMIT:
            result.output_tail.pop(0)
        if on_line is not None:
            on_line(safe)

    exit_code = _wait(process, timeout)
    result.exit_code = exit_code
    if exit_code != 0 and not result.summary_found and result.error is None:
        result.error = f"the legacy collector exited with code {exit_code}"
    return result


def _iter_lines(process: object) -> Iterable[str]:
    stream = getattr(process, "stdout", None)
    if stream is None:
        return ()
    try:
        return iter(stream)
    except TypeError:  # pragma: no cover - defensive for odd doubles
        return ()


def _wait(process: object, timeout: int) -> int:
    wait = getattr(process, "wait", None)
    if wait is None:  # pragma: no cover - defensive for odd doubles
        return 0
    try:
        return int(wait(timeout=timeout))
    except TypeError:  # pragma: no cover - doubles without the keyword
        return int(wait())
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:  # pragma: no cover - best effort
            pass
        return -1
