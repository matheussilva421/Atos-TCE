"""Classify the local TCE archive and cache selective OCR results."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile
from typing import Any
import unicodedata

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent.parent
for candidate in (APP_ROOT, PROJECT_ROOT):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from archive_index import write_index
from batch_runner import run_manifest
from evidence_geometry import build_visual_evidence
from extension_exporter import export_extension_dataset
from html_generator import write_html
from legal_context import build_legal_contexts, write_legal_contexts
from tce_extractor import classify_document, extract_pdf_pages


CACHE_VERSION = 2
EXTRACTOR_VERSION = "analysis-pipeline-v3"
OCR_VERSION = "tesseract-por+eng-psm6-v2"
GEOMETRY_CACHE_VERSION = 1
TARGET_CLASSIFICATIONS = frozenset(
    {"resolucao_administrativa", "guia_financeira_taxacao"}
)

TextReader = Callable[[Path], Sequence[str] | str]
OcrReader = Callable[[Path], Sequence[str] | str | tuple[Sequence[str] | str, Sequence[Mapping[str, object]]]]


@dataclass(frozen=True)
class PipelineSummary:
    total_processes: int
    priority_documents: int
    completed: int
    partial: int
    index_path: Path
    manifest_path: Path
    checkpoint_path: Path
    markdown_path: Path
    html_path: Path
    extension_data_path: Path
    visual_evidence_path: Path | None = None
    legal_context_path: Path | None = None


def _write_json_atomic(path: Path, value: Mapping[str, object]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(value, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _normalise_interested(value: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_marks.casefold()).strip()


def write_visual_evidence(manifest_path: Path, checkpoint_path: Path, output_path: Path) -> Path:
    """Project checkpoint citations and manifest occurrences into a sidecar."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
    checkpoint = json.loads(Path(checkpoint_path).read_text(encoding="utf-8-sig"))
    documents: list[dict[str, object]] = []
    for process_entry in manifest.get("processes", []):
        if not isinstance(process_entry, Mapping):
            continue
        process_key = str(process_entry.get("process", process_entry.get("key", "")))
        for document in process_entry.get("documents", []):
            if not isinstance(document, Mapping):
                continue
            relative_path = document.get("relative_path")
            if not isinstance(relative_path, str) or not relative_path.strip():
                relative_path = Path(str(document.get("pdf_path", ""))).name
            documents.append(
                {
                    "process_key": process_key,
                    "event_id": str(document.get("event_id", document.get("event", ""))),
                    "document_id": str(document.get("id", document.get("document_id", document.get("title", "")))),
                    "pdf_sha256": str(document.get("sha256", "")),
                    "relative_path": relative_path,
                    "title": str(document.get("title", "")),
                    "page_count": int(document.get("page_count", 0) or 0),
                }
            )

    records: list[dict[str, object]] = []
    for process_key, state in checkpoint.get("processes", {}).items():
        if not isinstance(state, Mapping) or not isinstance(state.get("result"), Mapping):
            continue
        result = state["result"]
        for block in result.get("blocks", []):
            if not isinstance(block, Mapping):
                continue
            interested = str(block.get("interested", "Não identificado"))
            interested_normalized = _normalise_interested(interested)
            record_id = hashlib.sha256(f"{process_key}|{interested_normalized}".encode()).hexdigest()
            fields = block.get("fields", {})
            if isinstance(fields, Mapping):
                records.append(
                    {
                        "record_id": record_id,
                        "process_key": str(process_key),
                        "interested_normalized": interested_normalized,
                        "fields": {str(key): value for key, value in fields.items() if isinstance(value, Mapping)},
                    }
                )

    sidecar = build_visual_evidence(records, documents)
    _write_json_atomic(Path(output_path), sidecar)
    return Path(output_path)


def _cached_page_texts(
    *paths: Path,
    classified: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Read already persisted page text without invoking an OCR reader."""
    page_texts: dict[str, object] = {}
    for path in paths:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, TypeError, ValueError):
            continue
        if not isinstance(payload, Mapping) or not isinstance(payload.get("entries"), Mapping):
            continue
        entries = payload["entries"]
        for key, value in entries.items():
            if isinstance(value, Mapping) and isinstance(value.get("pages"), list):
                entry: dict[str, object] = {
                    "pages": list(value["pages"]),
                    "pdf_sha256": str(value.get("sha256", "")),
                }
                page_texts[str(key)] = entry
                if value.get("sha256"):
                    page_texts[str(value["sha256"])] = entry
                continue
            if isinstance(value, list):
                entry = {"pages": list(value)}
                key_text = str(key)
                page_texts[key_text] = entry
                page_texts[key_text.split(":", 1)[0]] = entry
    if isinstance(classified, Mapping):
        process_entries = classified.get("processes")
        if isinstance(process_entries, list):
            for process in process_entries:
                if not isinstance(process, Mapping):
                    continue
                for event in process.get("events", []):
                    if not isinstance(event, Mapping):
                        continue
                    for document in event.get("documents", []):
                        if not isinstance(document, Mapping):
                            continue
                        pages = document.get("page_texts")
                        if not isinstance(pages, list):
                            continue
                        entry = {
                            "pages": list(pages),
                            "pdf_sha256": str(document.get("sha256", "")),
                        }
                        for key in (
                            "id",
                            "document_id",
                            "card_id",
                            "title",
                            "relative_path",
                            "pdf_path",
                            "geometry_cache_key",
                            "sha256",
                        ):
                            value = document.get(key)
                            if value is not None and str(value).strip():
                                page_texts[str(value)] = entry
    return page_texts


def _exported_dataset_sha256(dataset: object, output_path: Path) -> str:
    if isinstance(dataset, Mapping):
        batch = dataset.get("batch")
        if isinstance(batch, Mapping) and isinstance(batch.get("logical_sha256"), str):
            return str(batch["logical_sha256"])
    try:
        persisted = json.loads(Path(output_path).read_text(encoding="utf-8-sig"))
    except (OSError, TypeError, ValueError):
        return ""
    if isinstance(persisted, Mapping) and isinstance(persisted.get("batch"), Mapping):
        value = persisted["batch"].get("logical_sha256")
        return value if isinstance(value, str) else ""
    return ""


def _event_number(value: object) -> int | None:
    text = str(value or "")
    digits = ""
    for character in text:
        if character.isdigit():
            digits += character
        elif digits:
            break
    return int(digits) if digits else None


def _pages(value: Sequence[str] | str) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("leitor deve devolver texto ou uma sequência de páginas")
    return ["" if page is None else str(page) for page in value]


_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_CLEARLY_NON_TARGET_RE = re.compile(
    r"\b(?:tramitacao|oficio|encaminhamento|despacho|parecer)\b", re.IGNORECASE
)


def _is_useful_native_page(page: str) -> bool:
    normalized = " ".join(page.split())
    words = _WORD_RE.findall(normalized)
    return len(words) >= 2 and sum(len(word) for word in words) >= 8


def _has_useful_text(pages: Sequence[str]) -> bool:
    return any(_is_useful_native_page(page) for page in pages)


def _fold_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def _non_target_label_source(document: Mapping[str, object]) -> str | None:
    labels = (
        ("title", document.get("title")),
        ("metadata", document.get("metadata_title")),
        ("name", document.get("name") or document.get("filename") or document.get("file")),
    )
    for source, value in labels:
        if isinstance(value, str) and _CLEARLY_NON_TARGET_RE.search(_fold_label(value)):
            return source
    return None


def _document_path(document: Mapping[str, object]) -> Path | None:
    for key in ("absolute_path", "pdf_path", "relative_path"):
        value = document.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value)
    return None


def _native_pdf_pages(path: Path) -> list[str]:
    try:
        import pymupdf as fitz
    except ImportError:  # pragma: no cover - compatibility with older installs
        try:
            import fitz
        except ImportError as error:  # pragma: no cover - environment guard
            raise RuntimeError("PyMuPDF (fitz) não está disponível") from error

    document = fitz.open(path)
    try:
        return [page.get_text("text").strip() for page in document]
    finally:
        document.close()


def _validate_ocr_runtime(
    tesseract: str | Path | None, tessdata: str | Path | None
) -> tuple[Path, Path]:
    if not isinstance(tesseract, (str, Path)) or not str(tesseract).strip():
        raise ValueError("caminho explícito do Tesseract é obrigatório")
    executable = Path(tesseract).expanduser().resolve()
    if not executable.is_file():
        raise ValueError("caminho explícito do Tesseract não é um arquivo válido")
    if tessdata is None:
        raise ValueError("caminho explícito de tessdata não é um diretório válido")
    tessdata_path = Path(tessdata).expanduser().resolve()
    if not tessdata_path.is_dir():
        raise ValueError("caminho explícito de tessdata não é um diretório válido")
    missing = [
        language
        for language in ("por", "eng")
        if not (tessdata_path / f"{language}.traineddata").is_file()
    ]
    if missing:
        raise ValueError(f"tessdata sem idiomas obrigatórios: {', '.join(missing)}")
    return executable, tessdata_path


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _component_identity(tesseract: str | Path | None, tessdata: Path | None) -> str:
    def file_identity(value: str | Path | None) -> dict[str, object]:
        if value is None:
            return {"present": False}
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            return {"present": False, "name": str(value)}
        return {"present": True, "sha256": _hash_file(path), "size": path.stat().st_size}

    if tessdata is None:
        tessdata_identity: object = {"present": False}
    else:
        data_path = Path(tessdata).expanduser().resolve()
        if not data_path.is_dir():
            tessdata_identity = {"present": False, "name": str(tessdata)}
        else:
            files = []
            for item in sorted(data_path.rglob("*"), key=lambda item: item.relative_to(data_path).as_posix()):
                if item.is_file():
                    files.append(
                        {
                            "path": item.relative_to(data_path).as_posix(),
                            "sha256": _hash_file(item),
                            "size": item.stat().st_size,
                        }
                    )
            tessdata_identity = {"present": True, "files": files}

    payload = {
        "ocr_version": OCR_VERSION,
        "tesseract": file_identity(tesseract),
        "tessdata": tessdata_identity,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _ocr_cache_key(sha256: str, runtime_identity: str) -> str:
    return f"{sha256}:{runtime_identity}"


def _geometry_cache_key(sha256: str, runtime_identity: str) -> str:
    return f"{sha256}:geometry-{GEOMETRY_CACHE_VERSION}:{runtime_identity}"


def _ocr_pdf_pages(
    path: Path,
    tesseract: str | Path | None,
    tessdata: str | Path | None,
    *,
    return_geometry: bool = False,
) -> list[str] | tuple[list[str], list[dict]]:
    executable, tessdata_path = _validate_ocr_runtime(tesseract, tessdata)
    if return_geometry:
        return extract_pdf_pages(
            path,
            tesseract=str(executable),
            tessdata_dir=tessdata_path,
            return_geometry=True,
        )
    try:
        import pymupdf as fitz
    except ImportError:  # pragma: no cover - compatibility with older installs
        try:
            import fitz
        except ImportError as error:  # pragma: no cover - environment guard
            raise RuntimeError("PyMuPDF (fitz) não está disponível") from error

    document = fitz.open(path)
    pages: list[str] = []
    try:
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            command = [str(executable), "stdin", "stdout", "-l", "por+eng", "--psm", "6"]
            command.extend(["--tessdata-dir", str(tessdata_path)])
            result = subprocess.run(
                command,
                input=pixmap.tobytes("png"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError("Tesseract não conseguiu processar uma página")
            pages.append(result.stdout.decode("utf-8", errors="replace").strip())
    finally:
        document.close()
    return pages


def _cache_pages(cache: Mapping[str, object], sha256: str) -> tuple[bool, list[str]]:
    if not sha256:
        return False, []
    entry = cache.get(sha256)
    if isinstance(entry, Mapping):
        entry = entry.get("pages")
    if isinstance(entry, list):
        return True, ["" if page is None else str(page) for page in entry]
    if isinstance(entry, tuple):
        return True, ["" if page is None else str(page) for page in entry]
    return False, []


def _store_cache_pages(cache: MutableMapping[str, object], sha256: str, pages: Sequence[str]) -> None:
    if sha256:
        cache[sha256] = list(pages)


def _read_cache(path: Path, runtime_identity: str) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(payload, Mapping):
        return {}
    if (
        payload.get("version") != CACHE_VERSION
        or payload.get("extractor_version") != EXTRACTOR_VERSION
        or payload.get("ocr_version") != OCR_VERSION
        or payload.get("runtime_identity") != runtime_identity
    ):
        return {}
    entries = payload.get("entries")
    if not isinstance(entries, Mapping):
        return {}
    return {
        str(sha256): value
        for sha256, value in entries.items()
        if isinstance(value, (list, tuple, Mapping))
    }


def _write_cache(path: Path, entries: Mapping[str, object], runtime_identity: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "ocr_version": OCR_VERSION,
        "runtime_identity": runtime_identity,
        "cache_key_format": "sha256:runtime_identity",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "entries": dict(entries),
    }
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _read_geometry_cache(path: Path, runtime_identity: str) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(payload, Mapping):
        return {}
    if (
        payload.get("geometry_version") != GEOMETRY_CACHE_VERSION
        or payload.get("extractor_version") != EXTRACTOR_VERSION
        or payload.get("ocr_version") != OCR_VERSION
        or payload.get("runtime_identity") != runtime_identity
    ):
        return {}
    entries = payload.get("entries")
    if not isinstance(entries, Mapping):
        return {}
    return {
        str(key): value
        for key, value in entries.items()
        if isinstance(value, Mapping)
    }


def _write_geometry_cache(
    path: Path, entries: Mapping[str, object], runtime_identity: str
) -> None:
    _write_json_atomic(
        Path(path),
        {
            "geometry_version": GEOMETRY_CACHE_VERSION,
            "extractor_version": EXTRACTOR_VERSION,
            "ocr_version": OCR_VERSION,
            "runtime_identity": runtime_identity,
            "cache_key_format": "sha256:geometry_version:runtime_identity",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": dict(entries),
        },
    )


def _cache_geometry(
    cache: Mapping[str, object], key: str, sha256: str
) -> tuple[bool, list[str], list[dict]]:
    if not key or not sha256:
        return False, [], []
    entry = cache.get(key)
    if not isinstance(entry, Mapping) or str(entry.get("sha256", "")) != sha256:
        return False, [], []
    pages = entry.get("pages")
    geometry = entry.get("geometry")
    if not isinstance(pages, list) or not isinstance(geometry, list):
        return False, [], []
    if len(pages) != len(geometry) or not all(isinstance(item, Mapping) for item in geometry):
        return False, [], []
    return True, ["" if page is None else str(page) for page in pages], [dict(item) for item in geometry]


def _store_geometry(
    cache: MutableMapping[str, object],
    key: str,
    sha256: str,
    pages: Sequence[str],
    geometry: Sequence[Mapping[str, object]],
) -> None:
    if key and sha256 and len(pages) == len(geometry):
        cache[key] = {
            "geometry_version": GEOMETRY_CACHE_VERSION,
            "sha256": sha256,
            "pages": list(pages),
            "geometry": [dict(item) for item in geometry],
        }


def classify_document_record(
    document: Mapping[str, object],
    *,
    event: object,
    text_reader: TextReader,
    ocr_reader: OcrReader,
    cache: MutableMapping[str, object],
    runtime_identity: str = "",
    geometry_cache: MutableMapping[str, object] | None = None,
    geometry_capable: bool = False,
) -> dict[str, object]:
    """Classify one document, with Event 0/1 excluded before reading it."""
    result = dict(document)
    result["event"] = event
    result["page_count"] = 0
    event_number = _event_number(event)
    if event_number is None or event_number <= 1:
        return {**result, "classification": "outro_documento", "automatic_source": False}

    path = _document_path(document)
    if path is None or str(document.get("status", "complete")) not in {
        "complete",
        "ok",
    }:
        return {
            **result,
            "classification": "erro_leitura",
            "automatic_source": False,
        }

    try:
        pages = _pages(text_reader(path))
    except Exception as error:
        return {
            **result,
            "classification": "erro_leitura",
            "automatic_source": False,
            "read_error": type(error).__name__,
        }
    result["page_count"] = len(pages)
    result["page_texts"] = list(pages)
    physical_page_count = len(pages)

    label_priority = any(
        classify_document(str(document.get(key, "")), "") in TARGET_CLASSIFICATIONS
        for key in ("title", "metadata_title", "name", "filename", "file")
    )
    non_target_source = None if label_priority else _non_target_label_source(document)
    if non_target_source is not None:
        return {
            **result,
            "classification": "outro_documento",
            "automatic_source": False,
            "text_source": "native",
            "classification_signals": [
                {
                    "source": non_target_source,
                    "classification": None,
                    "excluded": True,
                    "reason": "clearly_non_target",
                }
            ],
            "classification_alternatives": [],
            "classification_conflict": False,
        }

    text_source = "native"
    if not _has_useful_text(pages):
        sha256 = str(document.get("sha256") or "")
        cache_key = _ocr_cache_key(sha256, runtime_identity) if runtime_identity else sha256
        geometry_key = _geometry_cache_key(sha256, runtime_identity) if runtime_identity else ""
        found, cached_pages = _cache_pages(cache, cache_key)
        geometry_found, geometry_pages, _ = _cache_geometry(
            geometry_cache or {}, geometry_key, sha256
        )
        if geometry_found:
            pages = geometry_pages
            text_source = "ocr_geometry_cache"
            result["geometry_cache_key"] = geometry_key
        elif found and not geometry_capable:
            pages = cached_pages
            text_source = "ocr_cache"
        else:
            try:
                ocr_result = ocr_reader(path)
                geometry: list[Mapping[str, object]] = []
                if (
                    isinstance(ocr_result, tuple)
                    and len(ocr_result) == 2
                    and isinstance(ocr_result[1], Sequence)
                    and all(isinstance(item, Mapping) for item in ocr_result[1])
                ):
                    pages = _pages(ocr_result[0])
                    geometry = [dict(item) for item in ocr_result[1]]
                else:
                    pages = _pages(ocr_result)  # type: ignore[arg-type]
            except Exception as error:
                if found:
                    pages = cached_pages
                    text_source = "ocr_cache"
                else:
                    return {
                        **result,
                        "classification": "pendente_ocr",
                        "automatic_source": False,
                        "ocr_error": type(error).__name__,
                    }
            else:
                _store_cache_pages(cache, cache_key, pages)
                if geometry and geometry_cache is not None and geometry_key:
                    _store_geometry(geometry_cache, geometry_key, sha256, pages, geometry)
                    result["geometry_cache_key"] = geometry_key
                    text_source = "ocr_geometry"
                else:
                    text_source = "ocr"
        result["page_count"] = max(physical_page_count, len(pages))
        result["page_texts"] = list(pages)
        if not _has_useful_text(pages):
            return {
                **result,
                "classification": "pendente_ocr",
                "automatic_source": False,
                "text_source": text_source,
            }

    title = str(document.get("title", ""))
    metadata_title = str(document.get("metadata_title", ""))
    full_text = "\n".join(pages)
    signals = [
        {"source": "title", "classification": classify_document(title, "")},
        {
            "source": "metadata",
            "classification": classify_document(metadata_title, ""),
        },
        {"source": "content", "classification": classify_document("", full_text)},
    ]
    alternatives = sorted(
        {
            str(signal["classification"])
            for signal in signals
            if signal["classification"] in TARGET_CLASSIFICATIONS
        }
    )
    conflict = len(alternatives) > 1
    kind = alternatives[0] if len(alternatives) == 1 and not conflict else None
    return {
        **result,
        "classification": kind or "outro_documento",
        "automatic_source": bool(kind) and not conflict,
        "text_source": text_source,
        "classification_signals": signals,
        "classification_alternatives": alternatives,
        "classification_conflict": conflict,
    }


def _resolved_document(document: Mapping[str, object], cache_path: Path) -> dict[str, object]:
    result = dict(document)
    if isinstance(result.get("absolute_path"), str) and result["absolute_path"]:
        return result
    relative = result.get("relative_path")
    if not isinstance(relative, str) or not relative:
        return result
    relative_path = Path(relative)
    if relative_path.is_absolute():
        result["absolute_path"] = str(relative_path)
        return result
    bases = [Path(cache_path).parent, *Path(cache_path).parent.parents]
    for base in bases:
        candidate = (base / relative_path).resolve()
        if candidate.is_file():
            result["absolute_path"] = str(candidate)
            return result
    result["absolute_path"] = str((Path(cache_path).parent / relative_path).resolve())
    return result


def _classify_flat_documents(
    index: Mapping[str, object],
    cache_path: Path,
    text_reader: TextReader,
    ocr_reader: OcrReader,
    cache: MutableMapping[str, object],
    runtime_identity: str,
    geometry_cache: MutableMapping[str, object],
    geometry_capable: bool,
) -> dict[str, object]:
    result = dict(index)
    classified = []
    for document in index.get("documents", []):
        if not isinstance(document, Mapping):
            continue
        resolved = _resolved_document(document, cache_path)
        classified.append(
            classify_document_record(
                resolved,
                event=resolved.get("event", ""),
                text_reader=text_reader,
                ocr_reader=ocr_reader,
                cache=cache,
                runtime_identity=runtime_identity,
                geometry_cache=geometry_cache,
                geometry_capable=geometry_capable,
            )
        )
    result["documents"] = classified
    return result


def _classify_nested_documents(
    index: Mapping[str, object],
    cache_path: Path,
    text_reader: TextReader,
    ocr_reader: OcrReader,
    cache: MutableMapping[str, object],
    runtime_identity: str,
    geometry_cache: MutableMapping[str, object],
    geometry_capable: bool,
) -> dict[str, object]:
    result = dict(index)
    processes = []
    for process in index.get("processes", []):
        if not isinstance(process, Mapping):
            continue
        process_result = dict(process)
        events = []
        for event in process.get("events", []):
            if not isinstance(event, Mapping):
                continue
            event_result = dict(event)
            documents = []
            for document in event.get("documents", []):
                if not isinstance(document, Mapping):
                    continue
                resolved = _resolved_document(document, cache_path)
                documents.append(
                    classify_document_record(
                        resolved,
                        event=event.get("event", ""),
                        text_reader=text_reader,
                        ocr_reader=ocr_reader,
                        cache=cache,
                        runtime_identity=runtime_identity,
                        geometry_cache=geometry_cache,
                        geometry_capable=geometry_capable,
                    )
                )
            event_result["documents"] = documents
            events.append(event_result)
        process_result["events"] = events
        processes.append(process_result)
    result["processes"] = processes
    return result


def classify_archive(
    index: Mapping[str, object],
    cache_path: Path,
    tesseract: str | Path | None = None,
    tessdata: str | Path | None = None,
    *,
    text_reader: TextReader | None = None,
    ocr_reader: OcrReader | None = None,
    geometry_cache_path: Path | None = None,
) -> dict[str, object]:
    """Classify every indexed document while retaining the complete archive."""
    cache_path = Path(cache_path)
    if ocr_reader is None:
        resolved_tesseract, resolved_tessdata = _validate_ocr_runtime(tesseract, tessdata)
        runtime_identity = _component_identity(resolved_tesseract, resolved_tessdata)
    elif tesseract is not None or tessdata is not None:
        runtime_identity = _component_identity(tesseract, tessdata)
    else:
        runtime_identity = "injected-ocr-reader-v1"
    cache = _read_cache(cache_path, runtime_identity)
    geometry_path = geometry_cache_path or cache_path.with_name(
        f"{cache_path.stem}-geometria{cache_path.suffix}"
    )
    geometry_cache = _read_geometry_cache(geometry_path, runtime_identity)
    native_reader = text_reader or _native_pdf_pages
    selected_ocr_reader = ocr_reader or (
        lambda path: _ocr_pdf_pages(
            path,
            tesseract=resolved_tesseract,
            tessdata=resolved_tessdata,
            return_geometry=True,
        )
    )
    geometry_capable = ocr_reader is None
    if isinstance(index.get("documents"), list):
        result = _classify_flat_documents(
            index,
            cache_path,
            native_reader,
            selected_ocr_reader,
            cache,
            runtime_identity,
            geometry_cache,
            geometry_capable,
        )
    else:
        result = _classify_nested_documents(
            index,
            cache_path,
            native_reader,
            selected_ocr_reader,
            cache,
            runtime_identity,
            geometry_cache,
            geometry_capable,
        )
    _write_cache(cache_path, cache, runtime_identity)
    _write_geometry_cache(geometry_path, geometry_cache, runtime_identity)
    result["classification_version"] = EXTRACTOR_VERSION
    result["ocr_version"] = OCR_VERSION
    result["ocr_runtime_identity"] = runtime_identity
    return result


def _process_name(process: Mapping[str, object]) -> str:
    for key in ("key", "process", "id"):
        value = process.get(key)
        if value is not None and str(value):
            return str(value)
    return ""


def _manifest_page_count(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    return None


def _target_document(document: Mapping[str, object], event: object) -> dict[str, object]:
    classification = str(document.get("classification", ""))
    target = {
        "event": str(event),
        "date": str(document.get("date", "")),
        "title": str(document.get("title", "")),
        "kind": classification,
        "classification": classification,
        "automatic_source": True,
        "sha256": document.get("sha256"),
        "page_count": _manifest_page_count(document.get("page_count")),
        "relative_path": document.get("relative_path"),
        "pdf_path": str(
            document.get("absolute_path")
            or document.get("pdf_path")
            or document.get("relative_path")
            or ""
        ),
    }
    for key in ("card_id", "id", "extension", "metadata_title", "geometry_cache_key"):
        if key in document:
            target[key] = document[key]
    return target


def build_target_manifest(classified: Mapping[str, object]) -> dict[str, object]:
    """Build the extraction manifest without discarding non-target classifications."""
    processes: list[dict[str, object]] = []
    if isinstance(classified.get("processes"), list):
        for process in classified["processes"]:
            if not isinstance(process, Mapping):
                continue
            process_name = _process_name(process)
            documents: list[dict[str, object]] = []
            for event in process.get("events", []):
                if not isinstance(event, Mapping):
                    continue
                event_number = _event_number(event.get("event"))
                if event_number is None or event_number <= 1:
                    continue
                for document in event.get("documents", []):
                    if not isinstance(document, Mapping):
                        continue
                    if (
                        document.get("automatic_source") is True
                        and document.get("classification") in TARGET_CLASSIFICATIONS
                    ):
                        documents.append(
                            _target_document(document, event.get("event", ""))
                        )
            processes.append({"process": process_name, "documents": documents})
    else:
        documents = []
        for document in classified.get("documents", []):
            if not isinstance(document, Mapping):
                continue
            event = document.get("event", "")
            event_number = _event_number(event)
            if (
                event_number is not None
                and event_number > 1
                and document.get("automatic_source") is True
                and document.get("classification") in TARGET_CLASSIFICATIONS
            ):
                documents.append(_target_document(document, event))
        processes.append(
            {"process": str(classified.get("process", "")), "documents": documents}
        )

    return {
        "version": 1,
        "source": "local-classification",
        "classification_version": str(
            classified.get("classification_version", EXTRACTOR_VERSION)
        ),
        "ocr_version": str(classified.get("ocr_version", OCR_VERSION)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "processes": processes,
    }


def run_local_pipeline(
    archive_root: Path,
    *,
    tesseract: str | Path,
    tessdata: str | Path,
    run_id: str | None = None,
    resume: bool = True,
) -> PipelineSummary:
    """Compose local indexing, classification, extraction, and HTML generation."""
    root = Path(archive_root)
    index_path = root / "indice-local.json"
    classified_index_path = root / "indice-classificado.json"
    cache_path = root / "cache-ocr.json"
    geometry_cache_path = root / "cache-ocr-geometria.json"
    manifest_path = root / "pdfs-alvo-manifest.json"
    checkpoint_path = root / "checkpoint-extracao.json"
    markdown_path = root / "doc.md"
    html_path = root / "complementar-ato.html"
    extension_data_path = root / "dados-complementar-ato.json"
    visual_evidence_path = root / "evidencias-visuais.json"
    legal_context_path = root / "fundamentos-contexto.v1.json"

    index = write_index(root, index_path)
    classified = classify_archive(
        index,
        cache_path,
        tesseract,
        tessdata,
        geometry_cache_path=geometry_cache_path,
    )
    _write_json_atomic(classified_index_path, classified)
    manifest = build_target_manifest(classified)
    _write_json_atomic(manifest_path, manifest)
    extraction = run_manifest(
        manifest_path,
        markdown_path,
        checkpoint_path,
        run_id=run_id,
        resume=resume,
        tesseract=str(tesseract),
        tessdata_dir=Path(tessdata),
        geometry_cache_path=geometry_cache_path,
    )
    write_visual_evidence(manifest_path, checkpoint_path, visual_evidence_path)
    write_html(
        manifest_path,
        checkpoint_path,
        html_path,
        pdf_link_root=None,
        archive_index_path=classified_index_path,
        visual_evidence_path=visual_evidence_path,
    )
    dataset = export_extension_dataset(checkpoint_path, extension_data_path)
    write_legal_contexts(
        legal_context_path,
        build_legal_contexts(
            manifest=json.loads(manifest_path.read_text(encoding="utf-8-sig")),
            checkpoint=json.loads(checkpoint_path.read_text(encoding="utf-8-sig")),
            page_texts=_cached_page_texts(
                cache_path,
                geometry_cache_path,
                classified=classified,
            ),
            dataset_sha256=_exported_dataset_sha256(dataset, extension_data_path),
        ),
    )
    priority_documents = sum(
        len(process.get("documents", []))
        for process in manifest.get("processes", [])
        if isinstance(process, Mapping)
    )
    return PipelineSummary(
        total_processes=int(extraction.get("total", 0)),
        priority_documents=priority_documents,
        completed=int(extraction.get("completed", 0)),
        partial=int(extraction.get("partial", 0)),
        index_path=index_path,
        manifest_path=manifest_path,
        checkpoint_path=checkpoint_path,
        markdown_path=markdown_path,
        html_path=html_path,
        extension_data_path=extension_data_path,
        visual_evidence_path=visual_evidence_path,
        legal_context_path=legal_context_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analisa o acervo TCE somente em arquivos locais.")
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--tesseract", type=Path, required=True)
    parser.add_argument("--tessdata", type=Path, required=True)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args(argv)
    summary = run_local_pipeline(
        args.archive_root,
        tesseract=args.tesseract,
        tessdata=args.tessdata,
        resume=not args.no_resume,
    )
    print(json.dumps({
        "total_processes": summary.total_processes,
        "priority_documents": summary.priority_documents,
        "completed": summary.completed,
        "partial": summary.partial,
        "html": str(summary.html_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
