"""Create a non-destructive archive containing only processes absent from a baseline."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


CHECKPOINT_NAME = "checkpoint.json"
BASELINE_ENTRY = "acervo-tce/checkpoint.json"
PROCESS_KEY_PATTERN = re.compile(r"^\s*(\d+)\s*/\s*(\d{4})\s*$")


class FilterError(ValueError):
    """A user-correctable source, baseline, or output contract violation."""


def canonical_process_key(record: Any, context: str) -> str:
    if not isinstance(record, dict):
        raise FilterError(f"{context}: registro de processo inválido")

    raw_key = record.get("key")
    if raw_key is None or not str(raw_key).strip():
        number = record.get("number", record.get("numero"))
        year = record.get("year", record.get("ano"))
        if number is None or year is None:
            raise FilterError(f"{context}: chave canônica numero/ano ausente")
        raw_key = f"{number}/{year}"

    match = PROCESS_KEY_PATTERN.fullmatch(str(raw_key))
    if match is None:
        raise FilterError(f"{context}: chave canônica inválida: {raw_key}")
    return f"{match.group(1)}/{match.group(2)}"


def load_checkpoint_text(raw: bytes, context: str) -> dict[str, Any]:
    try:
        checkpoint = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FilterError(f"{context}: JSON inválido: {exc}") from exc
    if not isinstance(checkpoint, dict):
        raise FilterError(f"{context}: checkpoint deve ser um objeto JSON")
    for field in ("processes", "documents"):
        if not isinstance(checkpoint.get(field), list):
            raise FilterError(f"{context}: checkpoint deve conter a lista {field}")
    for index, process in enumerate(checkpoint["processes"]):
        if not isinstance(process, dict):
            raise FilterError(f"{context}: processo {index} inválido")
        canonical_process_key(process, f"{context}, processo {index}")
        if not isinstance(process.get("status"), str) or not process["status"].strip():
            raise FilterError(f"{context}, processo {index}: status ausente")
    for index, document in enumerate(checkpoint["documents"]):
        if not isinstance(document, dict):
            raise FilterError(f"{context}: documento {index} inválido")
    return checkpoint


def read_checkpoint_source(source: Path, label: str) -> dict[str, Any]:
    if not os.path.lexists(source):
        raise FilterError(f"{label} inexistente: {source}")
    if source.is_dir():
        checkpoint_path = source / CHECKPOINT_NAME
        if not checkpoint_path.is_file():
            raise FilterError(f"{label} inválido: diretório sem checkpoint.json: {source}")
        try:
            return load_checkpoint_text(checkpoint_path.read_bytes(), str(checkpoint_path))
        except OSError as exc:
            raise FilterError(f"{label} inválido em {checkpoint_path}: {exc}") from exc
    if source.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(source) as archive:
                entries = [
                    entry
                    for entry in archive.infolist()
                    if entry.filename.replace("\\", "/").lstrip("/").lower() == BASELINE_ENTRY
                ]
                if len(entries) != 1:
                    raise FilterError(f"{label} inválido: entrada {BASELINE_ENTRY} ausente ou ambígua")
                return load_checkpoint_text(archive.read(entries[0]), f"{label} em {source}")
        except FilterError:
            raise
        except (OSError, zipfile.BadZipFile, KeyError) as exc:
            raise FilterError(f"{label} inválido em {source} (ZIP): {exc}") from exc
    if source.name.lower() != CHECKPOINT_NAME:
        raise FilterError(f"{label} inválido: arquivo deve ser checkpoint.json ou ZIP privado: {source}")
    try:
        return load_checkpoint_text(source.read_bytes(), str(source))
    except OSError as exc:
        raise FilterError(f"{label} inválido em {source}: {exc}") from exc


def read_source_archive(source: Path) -> dict[str, Any]:
    if not source.is_dir():
        raise FilterError(f"source inválido: esperado um diretório de acervo: {source}")
    return read_checkpoint_source(source, "source")


def completed_keys(
    checkpoint: dict[str, Any], context: str, all_present_complete: bool = False
) -> set[str]:
    return {
        canonical_process_key(process, f"{context}, processo {index}")
        for index, process in enumerate(checkpoint["processes"])
        if all_present_complete or process.get("status", "").lower() == "complete"
    }


def source_process_records(checkpoint: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    records: list[tuple[dict[str, Any], str]] = []
    seen: set[str] = set()
    for index, process in enumerate(checkpoint["processes"]):
        key = canonical_process_key(process, f"source, processo {index}")
        if key in seen:
            raise FilterError(f"source: processo duplicado para a chave {key}")
        seen.add(key)
        records.append((process, key))
    return records


def source_process_directories(source: Path, records: list[tuple[dict[str, Any], str]]) -> dict[str, Path]:
    processes_root = source / "processos"
    if not processes_root.is_dir():
        raise FilterError(f"source inválido: diretório processos ausente: {processes_root}")
    expected = {key for _, key in records}
    directories: dict[str, Path] = {}
    for child in processes_root.iterdir():
        if not child.is_dir():
            continue
        process_json = child / "processo.json"
        if not process_json.is_file():
            raise FilterError(f"source inválido: processo sem processo.json: {child}")
        try:
            process_record = json.loads(process_json.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FilterError(f"source inválido em {process_json}: {exc}") from exc
        key = canonical_process_key(process_record, f"source, {process_json}")
        if key not in expected:
            raise FilterError(f"source inválido: pasta {child} não está no checkpoint")
        if key in directories:
            raise FilterError(f"source inválido: mais de uma pasta para a chave {key}")
        directories[key] = child
    missing = sorted(expected - directories.keys())
    if missing:
        raise FilterError(f"source inválido: processos sem pasta: {', '.join(missing)}")
    return directories


def document_owner_key(document: dict[str, Any], index: int) -> str:
    raw_key = document.get("key")
    if not isinstance(raw_key, str) or not raw_key.strip():
        raise FilterError(f"source, documento {index}: chave do processo ausente")
    owner = raw_key.split("|", 1)[0]
    return canonical_process_key({"key": owner}, f"source, documento {index}")


def validate_document_path(
    document: dict[str, Any],
    index: int,
    source: Path,
    owner_key: str,
    owner_directory: Path,
) -> None:
    raw_path = document.get("path")
    if raw_path is None or raw_path == "":
        if str(document.get("status", "")).lower() == "complete":
            raise FilterError(f"source, documento {index}: documento completo sem path")
        return
    if not isinstance(raw_path, str):
        raise FilterError(f"source, documento {index}: path inválido")
    normalized = raw_path.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if relative.is_absolute() or not relative.parts or relative.parts[0].lower() != "processos":
        raise FilterError(f"source, documento {index}: path deve permanecer sob processos/: {raw_path}")
    if any(part in ("", ".", "..") for part in relative.parts):
        raise FilterError(f"source, documento {index}: path relativo inválido: {raw_path}")

    source_root = source.resolve()
    source_path = (source_root / Path(*relative.parts)).resolve()
    processes_root = (source_root / "processos").resolve()
    owner_root = owner_directory.resolve()
    try:
        if os.path.commonpath((str(processes_root), str(source_path))) != str(processes_root):
            raise FilterError(f"source, documento {index}: path escapou de processos/: {raw_path}")
        if os.path.commonpath((str(owner_root), str(source_path))) != str(owner_root):
            raise FilterError(f"source, documento {index}: documento não pertence a {owner_key}: {raw_path}")
    except ValueError as exc:
        raise FilterError(f"source, documento {index}: path em volume diferente: {raw_path}") from exc
    if not source_path.is_file():
        raise FilterError(f"source, documento {index}: arquivo ausente: {raw_path}")


def filter_archive(
    source: Path,
    baseline: Path,
    output: Path,
    baseline_all_complete: bool = False,
) -> None:
    if os.path.lexists(output):
        raise FilterError(f"output já existe; recusando sobrescrever: {output}")
    source_checkpoint = read_source_archive(source)
    baseline_checkpoint = read_checkpoint_source(baseline, "baseline")
    baseline_keys = completed_keys(
        baseline_checkpoint,
        "baseline",
        all_present_complete=baseline_all_complete,
    )
    records = source_process_records(source_checkpoint)
    directories = source_process_directories(source, records)
    kept_records = [(record, key) for record, key in records if key not in baseline_keys]
    kept_keys = {key for _, key in kept_records}

    kept_documents: list[dict[str, Any]] = []
    source_document_keys: set[str] = set()
    for index, document in enumerate(source_checkpoint["documents"]):
        owner_key = document_owner_key(document, index)
        if owner_key not in {key for _, key in records}:
            raise FilterError(f"source, documento {index}: processo não está no checkpoint: {owner_key}")
        if owner_key not in kept_keys:
            continue
        validate_document_path(document, index, source, owner_key, directories[owner_key])
        document_key = str(document.get("key"))
        if document_key in source_document_keys:
            raise FilterError(f"source: documento duplicado: {document_key}")
        source_document_keys.add(document_key)
        kept_documents.append(document)

    filtered_checkpoint = dict(source_checkpoint)
    filtered_checkpoint["processes"] = [record for record, _ in kept_records]
    filtered_checkpoint["documents"] = kept_documents

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=str(output.parent)))
    committed = False
    try:
        for child in source.iterdir():
            if child.name in (CHECKPOINT_NAME, "processos"):
                continue
            target = staging / child.name
            if child.is_dir():
                shutil.copytree(child, target)
            else:
                shutil.copy2(child, target)

        staging_processes = staging / "processos"
        staging_processes.mkdir()
        for _, key in kept_records:
            shutil.copytree(directories[key], staging_processes / directories[key].name)
        (staging / CHECKPOINT_NAME).write_text(
            json.dumps(filtered_checkpoint, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, output)
        committed = True
    finally:
        if not committed and staging.exists():
            shutil.rmtree(staging)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--baseline-all-complete",
        action="store_true",
        help="trata todo processo presente na base como já concluído",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        filter_archive(
            args.source,
            args.baseline,
            args.output,
            baseline_all_complete=args.baseline_all_complete,
        )
    except FilterError as exc:
        print(f"filter_new_batch: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"filter_new_batch: falha de escrita atômica: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
