"""Local acquisition contract for frozen analysis lots.

The service uses this module to construct a bounded PowerShell collector
process.  It never carries portal credentials and it never enables act send.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping


_ANALYSIS_FILE_RE = re.compile(r"^analysis-[0-9a-f]{24}\.json$")
_SOURCE_SCOPES = frozenset({"sector_finalistic", "my_processes"})


def validate_acquisition_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("requisição de aquisição inválida")
    selection = payload.get("selection")
    if selection == "all" and set(payload) == {"selection"}:
        return {"selection": "all", "lot_number": None}
    if selection != "lot" or set(payload) != {"selection", "lot_number"}:
        raise ValueError("requisição de aquisição deve selecionar all ou lot")
    lot_number = payload["lot_number"]
    if isinstance(lot_number, bool) or not isinstance(lot_number, int) or not 1 <= lot_number <= 1000:
        raise ValueError("lot_number deve ser inteiro entre 1 e 1000")
    return {"selection": "lot", "lot_number": lot_number}


def validate_source_scope(source_scope: str) -> str:
    if source_scope not in _SOURCE_SCOPES:
        raise ValueError("source_scope deve ser sector_finalistic ou my_processes")
    return source_scope


def _analysis_path(workflow_root: Path, value: Path) -> Path:
    root = Path(workflow_root).resolve() / "automacao" / "analises"
    path = Path(value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("analysis_path deve permanecer em automacao/analises") from exc
    if not _ANALYSIS_FILE_RE.fullmatch(path.name):
        raise ValueError("analysis_path não possui nome de análise válido")
    return path


def build_collector_command(
    *,
    package_root: Path,
    workflow_root: Path,
    analysis_path: Path,
    lot_number: int | None,
    source_scope: str,
    python_path: Path,
    tesseract_path: Path,
    tessdata_path: Path,
) -> list[str]:
    request = validate_acquisition_request(
        {"selection": "all"} if lot_number is None else {"selection": "lot", "lot_number": lot_number}
    )
    scope = validate_source_scope(source_scope)
    package = Path(package_root).resolve()
    archive = Path(workflow_root).resolve()
    frozen = _analysis_path(archive, Path(analysis_path))
    script = package / "Coletar-Processos-TCE.ps1"
    command = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Destino",
        str(archive),
        "-FilaCongelada",
        str(frozen),
        "-EscopoPortal",
        scope,
        "-ModoPreparacao",
        "progressivo",
        "-ManterNavegadorAberto",
        "-NaoInterativo",
        "-ServiceChild",
        "-Python",
        str(Path(python_path).resolve()),
        "-Tesseract",
        str(Path(tesseract_path).resolve()),
        "-Tessdata",
        str(Path(tessdata_path).resolve()),
    ]
    if request["selection"] == "lot":
        insert_at = command.index("-EscopoPortal")
        command[insert_at:insert_at] = ["-NumeroLote", str(request["lot_number"])]
    return command


__all__ = ["build_collector_command", "validate_acquisition_request", "validate_source_scope"]
