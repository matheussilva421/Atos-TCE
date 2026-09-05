"""Build a flat portable ZIP with the application and optional TCE archive."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat as stat_module
import sys
import tempfile
import time
import uuid
import zipfile


def _load_sibling_audit():
    """Load the audit module shipped beside this script, without sys.path changes."""

    script_path = Path(__file__).resolve()
    sibling_path = script_path.with_name("package_audit.py")
    if not sibling_path.is_file():
        raise ImportError(
            "Não foi possível carregar package_audit.py irmão: "
            f"arquivo ausente ao lado de {script_path}"
        )

    spec = importlib.util.spec_from_file_location(
        "_tce_package_audit_sibling", sibling_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(
            "Não foi possível carregar package_audit.py irmão: "
            f"loader indisponível para {sibling_path}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(spec.name, None)
        raise ImportError(
            "Não foi possível carregar package_audit.py irmão "
            f"{sibling_path}: {error}"
        ) from error
    try:
        return module.audit_package
    except AttributeError as error:
        raise ImportError(
            "Não foi possível carregar package_audit.py irmão: "
            f"audit_package ausente em {sibling_path}"
        ) from error


def _load_audit_package():
    """Prefer project imports and fall back to the package's fixed sibling."""

    try:
        from package_audit import audit_package

        return audit_package
    except ModuleNotFoundError as error:
        if error.name != "package_audit":
            raise

    try:
        from portable.app.package_audit import audit_package

        return audit_package
    except ModuleNotFoundError as error:
        if error.name not in {"portable", "portable.app", "portable.app.package_audit"}:
            raise

    return _load_sibling_audit()


audit_package = _load_audit_package()


EXCLUDED_DIRECTORIES = frozenset(
    {
        "dados-locais",
        "backups-acervo",
        "downloads",
        "__pycache__",
        ".pytest_cache",
        ".git",
        "chrome",
        "chromium",
        "user data",
        "perfil-navegador",
        "guest profile",
        "system profile",
    }
)
EXCLUDED_SUFFIXES = frozenset({".part", ".tmp"})
EXTENSION_DIRECTORY = "extensao-complementar-ato"
EXTENSION_FILE_ALLOWLIST = frozenset(
    {
        "manifest.json",
        "package.json",
        "content/package.json",
        "content/form-detector.js",
        "background/service-worker.js",
        "lib/matcher.js",
        "lib/messages.js",
        "lib/normalizer.js",
        "lib/schema.js",
        "sidepanel/panel.css",
        "sidepanel/panel.html",
        "sidepanel/panel.js",
    }
)
EXTENSION_SOURCE_EXCLUDED_DIRECTORIES = frozenset({"tests"})
ARCHIVE_DATA_RELATIVE = Path("acervo-tce") / "dados-complementar-ato.json"
_REPARSE_POINT_FLAG = 0x400
_BROWSER_CREDENTIAL_FILE_NAMES = frozenset(
    {"cookies", "login data", "web data", "local state"}
)


def _replace_with_retry(source: Path, destination: Path, attempts: int = 8) -> None:
    for attempt in range(attempts):
        try:
            source.replace(destination)
            return
        except PermissionError:
            if attempt + 1 == attempts:
                source.unlink(missing_ok=True)
                raise
            time.sleep(min(0.05 * (2**attempt), 0.8))


def _is_reparse_point(path: Path) -> bool:
    info = path.lstat()
    attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    return stat_module.S_ISLNK(info.st_mode) or bool(attributes & _REPARSE_POINT_FLAG)


def _extension_relative(source_root: Path, path: Path) -> str | None:
    relative = path.relative_to(source_root).as_posix()
    prefix = EXTENSION_DIRECTORY + "/"
    if not relative.casefold().startswith(prefix):
        return None
    return relative[len(prefix) :]


def _is_under_archive(relative: str) -> bool:
    folded = relative.casefold()
    return folded == "acervo-tce" or folded.startswith("acervo-tce/")


def _has_nested_archive_component(relative: str) -> bool:
    parts = tuple(part.casefold() for part in relative.replace("\\", "/").split("/"))
    return "acervo-tce" in parts[1:]


def _is_allowed_source_file(source_root: Path, path: Path) -> bool:
    relative = path.relative_to(source_root).as_posix()
    folded = relative.casefold()
    name = path.name.casefold()

    if path.suffix.casefold() in EXCLUDED_SUFFIXES:
        return False
    if name in _BROWSER_CREDENTIAL_FILE_NAMES:
        return False
    if path.suffix.casefold() == ".pdf" and not _is_under_archive(relative):
        return False
    if "checkpoint" in folded and not _is_under_archive(relative):
        return False
    if name == "dados-complementar-ato.json" and not _is_under_archive(relative):
        return False

    extension_relative = _extension_relative(source_root, path)
    if extension_relative is not None:
        extension_parts = extension_relative.casefold().split("/")
        if extension_parts and extension_parts[0] in EXTENSION_SOURCE_EXCLUDED_DIRECTORIES:
            return False
        return True
    return True


def _iter_package_files(source_root: Path, destination: Path):
    """Yield safe, deterministic package files without following reparse points."""

    source_root = Path(source_root)
    destination = Path(destination).resolve()
    stack = [source_root]
    while stack:
        current = stack.pop()
        with os.scandir(current) as iterator:
            entries = sorted(
                list(iterator),
                key=lambda entry: entry.name.casefold(),
                reverse=True,
            )
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(source_root).as_posix()
            if _has_nested_archive_component(relative):
                raise ValueError(
                    f"auditoria de inventário: acervo-tce só pode existir na raiz do pacote: {relative}"
                )
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                raise
            attributes = int(getattr(info, "st_file_attributes", 0) or 0)
            if stat_module.S_ISLNK(info.st_mode) or bool(attributes & _REPARSE_POINT_FLAG):
                raise ValueError(f"Reparse point não permitido: {relative}")
            if stat_module.S_ISDIR(info.st_mode):
                if entry.name.casefold() not in EXCLUDED_DIRECTORIES:
                    stack.append(path)
                continue
            if not stat_module.S_ISREG(info.st_mode):
                raise ValueError(f"Item não regular não permitido: {relative}")
            if path.resolve() == destination or not _is_allowed_source_file(source_root, path):
                continue
            yield path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_extension_data_records(path: Path) -> int:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"JSON da extensão inválido: {path}: {error}") from error
    if not isinstance(document, dict) or not isinstance(document.get("records"), list):
        raise ValueError("JSON da extensão deve conter records como lista")
    return len(document["records"])


def _require_public_sources(source_root: Path) -> None:
    required = (
        Path("app") / "extension_exporter.py",
        Path("app") / "package_complete_archive.py",
    )
    for relative in required:
        path = source_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"Fonte obrigatória ausente: {path}")
    extension = source_root / EXTENSION_DIRECTORY
    if not extension.is_dir():
        raise FileNotFoundError(f"Extensão obrigatória ausente: {extension}")
    for relative in EXTENSION_FILE_ALLOWLIST:
        path = extension / relative
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo da extensão ausente: {path}")


def _require_green_audit(source_root: Path, distribution: str) -> None:
    report = audit_package(source_root, distribution=distribution)
    if report.ok:
        return
    summary = "; ".join(
        f"{finding.code}:{finding.path}" for finding in report.findings[:8]
    )
    raise ValueError(f"auditoria {distribution} reprovada; ZIP não criado: {summary}")


def _stage_filtered_inventory(
    source_root: Path, staging_root: Path, destination: Path
) -> list[Path]:
    relative_paths = sorted(
        (
            path.relative_to(source_root)
            for path in _iter_package_files(source_root, destination)
        ),
        key=lambda path: path.as_posix().casefold(),
    )
    for relative in relative_paths:
        staged = staging_root / relative
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, staged)
    return relative_paths


def build_complete_zip(
    source_root: Path,
    destination: Path,
    *,
    force: bool = False,
    distribution: str = "private",
) -> dict[str, object]:
    """Build a flat ZIP and return file, archive, and extension counts."""

    source_root = Path(source_root).resolve()
    destination = Path(destination).resolve()
    if distribution not in {"public", "private"}:
        raise ValueError("distribution deve ser public ou private")
    if not source_root.is_dir():
        raise FileNotFoundError(f"Pasta portátil não existe: {source_root}")
    if destination.exists() and not force:
        raise FileExistsError(f"ZIP já existe: {destination}")
    if distribution == "private":
        archive_root = source_root / "acervo-tce"
        if not archive_root.is_dir():
            raise FileNotFoundError(f"Acervo local não existe: {archive_root}")
        data_path = source_root / ARCHIVE_DATA_RELATIVE
        if not data_path.is_file():
            raise FileNotFoundError(f"Dados da extensão ausentes: {data_path}")
    else:
        _require_public_sources(source_root)
        if (source_root / "acervo-tce").exists():
            raise ValueError("pacote público não pode receber acervo-tce")
    with tempfile.TemporaryDirectory(prefix="tce-package-staging-") as staging_text:
        staging_root = Path(staging_text)
        relative_paths = _stage_filtered_inventory(
            source_root, staging_root, destination
        )
        _require_green_audit(staging_root, distribution)
        extension_data_records = (
            _read_extension_data_records(staging_root / ARCHIVE_DATA_RELATIVE)
            if distribution == "private"
            else 0
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        counts = {
            "files": 0,
            "processes": 0,
            "events": 0,
            "pdfs": 0,
            "extension_files": 0,
            "extension_data_records": extension_data_records,
        }
        try:
            with zipfile.ZipFile(
                temporary,
                mode="x",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=1,
                allowZip64=True,
            ) as archive:
                for relative_path in relative_paths:
                    path = staging_root / relative_path
                    relative = relative_path.as_posix()
                    archive.write(path, relative)
                    counts["files"] += 1
                    if _extension_relative(staging_root, path) is not None:
                        counts["extension_files"] += 1
                    if path.name.casefold() == "processo.json":
                        counts["processes"] += 1
                    elif path.name.casefold() == "evento.json":
                        counts["events"] += 1
                    if path.suffix.casefold() == ".pdf":
                        counts["pdfs"] += 1
            _replace_with_retry(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    return {
        **counts,
        "zip": str(destination),
        "bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--distribution", choices=("public", "private"), default="private")
    args = parser.parse_args(argv)
    stats = build_complete_zip(
        args.source,
        args.output,
        force=args.force,
        distribution=args.distribution,
    )
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
