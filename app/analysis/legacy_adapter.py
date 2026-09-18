"""Adapter around the promoted incremental analysis pipeline.

M4 keeps the proven engine behind a seam: the Mesa asks this adapter to analyse
one process, and the engine that actually runs is the copy promoted into
``app/analysis/engine`` (M6 Task 1). No path here reaches into the legacy tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


class AnalysisError(RuntimeError):
    """Raised when the analysis engine cannot produce a usable result."""


@dataclass(slots=True)
class TesseractPaths:
    executable: Path
    tessdata: Path


def tesseract_candidates(data_root: str | Path, repo_root: str | Path | None = None) -> tuple[Path, ...]:
    """Folders that may hold the fixed Tesseract shipped with the runtime.

    Only supported locations are probed: the runtime folder inside the data root
    and the one that ships next to ``START.cmd``. A development checkout that
    needs OCR places the verified runtime in one of them.
    """

    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    return (
        Path(data_root) / "runtime" / "tesseract",
        root / "runtime" / "tesseract",
    )


def resolve_tesseract(data_root: str | Path, repo_root: str | Path | None = None) -> TesseractPaths:
    """Locate the Tesseract the portable runtime pins."""

    for candidate in tesseract_candidates(data_root, repo_root):
        executable = candidate / "tesseract.exe"
        tessdata = candidate / "tessdata"
        if executable.is_file() and tessdata.is_dir():
            return TesseractPaths(executable=executable, tessdata=tessdata)
    raise AnalysisError(
        "Tesseract do runtime portátil não encontrado em "
        + ", ".join(str(candidate) for candidate in tesseract_candidates(data_root, repo_root))
        + "; o OCR continua obrigatório como fallback"
    )


class LegacyAnalysisAdapter:
    """Run the proven per-process analysis without exposing its internals."""

    def __init__(
        self,
        data_root: str | Path,
        *,
        repo_root: str | Path | None = None,
        tesseract: TesseractPaths | None = None,
    ) -> None:
        self._data_root = Path(data_root)
        self._repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self._tesseract = tesseract

    @property
    def archive_root(self) -> Path:
        return self._data_root / "archive"

    def _paths(self) -> TesseractPaths:
        if self._tesseract is None:
            self._tesseract = resolve_tesseract(self._data_root, self._repo_root)
        return self._tesseract

    def analyze(self, process_key: str) -> dict[str, Any]:
        """Return the raw legacy result for one process."""

        module = _engine()
        paths = self._paths()
        try:
            result = module.analyze_process(
                self.archive_root,
                process_key,
                tesseract=paths.executable,
                tessdata=paths.tessdata,
            )
        except Exception as error:  # the engine raises many concrete types
            raise AnalysisError(f"a análise incremental falhou: {type(error).__name__}") from error
        if not isinstance(result, dict):
            raise AnalysisError("a análise incremental devolveu um resultado inesperado")
        return result

def _engine():
    """Import the promoted engine lazily, through the normal package path."""

    from .engine import incremental_pipeline

    return incremental_pipeline
