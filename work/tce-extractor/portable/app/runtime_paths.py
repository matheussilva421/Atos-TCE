"""Resolve the executables and data files shipped with the portable package.

This module deliberately does not search PATH.  Callers must use the returned
absolute paths so a system Python or Tesseract cannot be selected by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


TRAINEDDATA_NAMES = ("por.traineddata", "eng.traineddata", "osd.traineddata")
REQUIRED_TESSERACT_DLL_NAMES = ("libtesseract-5.dll", "libleptonica-6.dll")


def _require_file(path: Path, component: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(
            f"Runtime portátil incompleto: {component} ausente: {path}"
        )
    return path


@dataclass(frozen=True)
class RuntimePaths:
    """Absolute paths to the fixed runtime components in a package root."""

    root: Path
    runtime: Path
    python_root: Path
    python: Path
    python_pth: Path
    site_packages: Path
    tesseract_root: Path
    tesseract: Path
    tessdata: Path
    traineddata: tuple[Path, ...]
    tesseract_dlls: tuple[Path, ...]

    @classmethod
    def from_package(cls, root: str | Path) -> "RuntimePaths":
        package_root = Path(root).expanduser().resolve()
        if not package_root.is_dir():
            raise FileNotFoundError(
                f"Raiz do pacote portátil ausente: {package_root}"
            )

        runtime_root = package_root / "runtime"
        python_root = runtime_root / "python"
        python = _require_file(
            python_root / "python.exe", "runtime/python/python.exe"
        )
        python_pth = _require_file(
            python_root / "python314._pth", "runtime/python/python314._pth"
        )

        tesseract_root = runtime_root / "tesseract"
        tesseract = _require_file(
            tesseract_root / "tesseract.exe", "runtime/tesseract/tesseract.exe"
        )
        tessdata = tesseract_root / "tessdata"
        traineddata = tuple(
            _require_file(tessdata / name, f"tessdata/{name}")
            for name in TRAINEDDATA_NAMES
        )
        tesseract_dlls = tuple(
            _require_file(tesseract_root / name, f"runtime/tesseract/{name}")
            for name in REQUIRED_TESSERACT_DLL_NAMES
        )

        return cls(
            root=package_root,
            runtime=runtime_root,
            python_root=python_root,
            python=python,
            python_pth=python_pth,
            site_packages=python_root / "Lib" / "site-packages",
            tesseract_root=tesseract_root,
            tesseract=tesseract,
            tessdata=tessdata,
            traineddata=traineddata,
            tesseract_dlls=tesseract_dlls,
        )

    @property
    def python_executable(self) -> Path:
        """Compatibility alias for callers that name the executable explicitly."""

        return self.python

    @property
    def all_files(self) -> tuple[Path, ...]:
        """Files checked by the resolver, all constrained below ``root``."""

        return (
            self.python,
            self.python_pth,
            self.tesseract,
            *self.tesseract_dlls,
            *self.traineddata,
        )
