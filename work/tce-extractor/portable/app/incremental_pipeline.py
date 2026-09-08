"""Bounded, atomic publication helpers for progressive local preparation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import copy
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
from typing import Mapping


APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent.parent
for candidate in (APP_ROOT, PROJECT_ROOT):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from analysis_pipeline import build_target_manifest, classify_archive
from archive_index import scan_archive
from batch_runner import run_manifest
from extension_exporter import build_extension_dataset
from html_generator import build_interface_payload


_PROCESS_KEY = re.compile(r"^\d+/\d{4}$")
_PUBLISH_LOCK = threading.RLock()


def _sidecar_path(root: Path, name: str) -> Path | None:
    for candidate in (root / name, root / "acervo-tce" / name):
        if candidate.is_file():
            return candidate
    return None


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON inválido: {path}")
    return value


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _current_pointer(root: Path) -> dict | None:
    pointer = root / "publicacao-atual.json"
    if not pointer.exists():
        return None
    value = _read_json(pointer)
    if value.get("schema_version") != 1 or not isinstance(value.get("revision"), int):
        raise ValueError("ponteiro de publicação inválido")
    return value


def current_results(archive_root: Path) -> dict[str, dict]:
    root = Path(archive_root)
    pointer = _current_pointer(root)
    if pointer is None:
        return {}
    snapshot = root / "publicacoes" / str(pointer["revision"]) / "resultados.json"
    payload = _read_json(snapshot)
    results = payload.get("results")
    if not isinstance(results, dict):
        raise ValueError("resultados de publicação inválidos")
    return copy.deepcopy(results)


def publish_results(
    archive_root: Path,
    process_results: Mapping[str, Mapping[str, object]],
    *,
    review_manifest: Mapping[str, object] | None = None,
    review_index: Mapping[str, object] | None = None,
) -> int:
    """Merge process results into a new revision and atomically repoint readers."""
    root = Path(archive_root).resolve()
    with _PUBLISH_LOCK:
        previous = current_results(root)
        pointer = _current_pointer(root)
        revision = int(pointer["revision"]) + 1 if pointer else 1
        merged = copy.deepcopy(previous)
        for process_key, result in process_results.items():
            if not _PROCESS_KEY.fullmatch(str(process_key)):
                raise ValueError(f"processo inválido: {process_key}")
            if not isinstance(result, Mapping):
                raise ValueError(f"resultado inválido: {process_key}")
            merged[str(process_key)] = copy.deepcopy(dict(result))

        publication_root = root / "publicacoes"
        publication_root.mkdir(parents=True, exist_ok=True)
        temporary_root = Path(tempfile.mkdtemp(prefix=f".revision-{revision}-", dir=publication_root))
        try:
            published_at = datetime.now(timezone.utc).isoformat()
            _atomic_json(
                temporary_root / "resultados.json",
                {
                    "schema_version": 1,
                    "revision": revision,
                    "published_at": published_at,
                    "results": merged,
                },
            )
            checkpoint = {
                "version": 1,
                "run_id": f"publication-{revision}",
                "created_at": published_at,
                "processes": {
                    process_key: {
                        "status": str(result.get("status", "partial")),
                        "result": dict(result),
                    }
                    for process_key, result in merged.items()
                },
            }
            _atomic_json(
                temporary_root / "dataset.json",
                build_extension_dataset(checkpoint, generated_at=published_at),
            )
            if review_manifest is not None:
                manifest_processes = {
                    str(item.get("process", "")): copy.deepcopy(dict(item))
                    for item in review_manifest.get("processes", [])
                    if isinstance(item, Mapping) and str(item.get("process", ""))
                }
                previous_manifest_path = None
                if pointer:
                    previous_manifest_path = publication_root / str(pointer["revision"]) / "manifest.json"
                if previous_manifest_path is not None and previous_manifest_path.is_file():
                    previous_manifest = _read_json(previous_manifest_path)
                    for item in previous_manifest.get("processes", []):
                        if isinstance(item, Mapping) and str(item.get("process", "")) not in manifest_processes:
                            manifest_processes[str(item["process"])] = copy.deepcopy(dict(item))
                merged_manifest = {
                    "version": 1,
                    "processes": list(manifest_processes.values()),
                }
                review_index_value = dict(review_index) if isinstance(review_index, Mapping) else scan_archive(root)
                manifest_path = temporary_root / "manifest.json"
                checkpoint_path = temporary_root / "checkpoint.json"
                archive_index_path = temporary_root / "archive-index.json"
                _atomic_json(manifest_path, merged_manifest)
                _atomic_json(checkpoint_path, checkpoint)
                _atomic_json(archive_index_path, review_index_value)
                review_payload = build_interface_payload(
                    manifest_path,
                    checkpoint_path,
                    archive_index_path=archive_index_path,
                    visual_evidence_path=_sidecar_path(root, "evidencias-visuais.json"),
                )
                review_payload["live_revision"] = revision
                _atomic_json(temporary_root / "review-data.json", review_payload)
            final_root = publication_root / str(revision)
            os.replace(temporary_root, final_root)
            temporary_root = None
            _atomic_json(root / "publicacao-atual.json", {"schema_version": 1, "revision": revision})
            revisions = sorted(
                (path for path in publication_root.iterdir() if path.is_dir() and path.name.isdigit()),
                key=lambda path: int(path.name),
            )
            for old_revision in revisions[:-2]:
                shutil.rmtree(old_revision)
            return revision
        finally:
            if temporary_root is not None and temporary_root.exists():
                shutil.rmtree(temporary_root)


def analyze_process(archive_root: Path, process_key: str, *, tesseract, tessdata) -> dict:
    """Classify and extract one locally synchronized process.

    The archive index is filtered before OCR, so progressive collection does
    not rerun OCR for unrelated processes. Shared caches are updated by the
    atomic classification helpers; extraction uses a private checkpoint and is
    published only after the process result is coherent.
    """
    if not _PROCESS_KEY.fullmatch(str(process_key)):
        raise ValueError("process_key inválido")

    root = Path(archive_root)
    index = scan_archive(root)
    selected = [
        item
        for item in index.get("processes", [])
        if isinstance(item, Mapping) and str(item.get("key", "")) == process_key
    ]
    if not selected:
        raise KeyError(process_key)

    publish_results(root, {process_key: {"process": process_key, "status": "preparando", "blocks": []}})
    selected_index = {
        "version": index.get("version", 1),
        "generated_at": index.get("generated_at"),
        "process_keys": [process_key],
        "processes": selected,
    }
    classified = classify_archive(
        selected_index,
        root / "cache-ocr.json",
        tesseract,
        tessdata,
        geometry_cache_path=root / "cache-ocr-geometria.json",
    )
    manifest = build_target_manifest(classified)
    with tempfile.TemporaryDirectory(prefix="tce-process-", dir=root) as temporary:
        scratch = Path(temporary)
        selected_manifest = scratch / "manifest.json"
        selected_manifest.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        checkpoint = scratch / "checkpoint.json"
        output = scratch / "resultado.md"
        run_manifest(
            selected_manifest,
            output,
            checkpoint,
            tesseract=str(tesseract),
            tessdata_dir=Path(tessdata),
            geometry_cache_path=root / "cache-ocr-geometria.json",
            resume=False,
        )
        saved = _read_json(checkpoint)
        process_result = saved.get("processes", {}).get(process_key, {}).get("result", {"status": "partial", "blocks": []})
    publish_results(root, {process_key: process_result}, review_manifest=manifest, review_index=index)
    return {"process": process_key, **dict(process_result)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Prepara um processo do acervo TCE de forma incremental.")
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--process-key", required=True)
    parser.add_argument("--tesseract", type=Path, required=True)
    parser.add_argument("--tessdata", type=Path, required=True)
    args = parser.parse_args(argv)
    result = analyze_process(
        args.archive_root,
        args.process_key,
        tesseract=args.tesseract,
        tessdata=args.tessdata,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
