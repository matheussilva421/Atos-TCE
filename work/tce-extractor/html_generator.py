"""Generate a standalone local workbench for Complementar Ato review."""

from __future__ import annotations

import argparse
from html import escape
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
from tempfile import NamedTemporaryFile
from typing import Mapping
from urllib.parse import quote
from uuid import UUID


FIELD_ORDER = (
    "modalidade",
    "fundamento_legal",
    "data_publicacao_doe",
    "cargo",
    "matricula",
    "data_nascimento",
    "genero",
)

FIELD_LABELS = {
    "modalidade": "Modalidade",
    "fundamento_legal": "Fundamento legal",
    "data_publicacao_doe": "Data de publicação no DOE",
    "cargo": "Cargo",
    "matricula": "Matrícula",
    "data_nascimento": "Data de nascimento",
    "genero": "Gênero",
}


def _document_sort_key(document: Mapping[str, object]) -> tuple[int, int, str]:
    priority = {
        "resolucao_administrativa": 0,
        "guia_financeira_taxacao": 1,
    }.get(str(document.get("classification", "")), 2)
    match = re.search(r"\d+", str(document.get("event", "")))
    event = int(match.group(0)) if match else 10**9
    return priority, event, str(document.get("title", "")).casefold()


def _citation(field: Mapping[str, object]) -> str | None:
    existing = field.get("citation")
    if isinstance(existing, str) and existing:
        return existing
    process = field.get("process")
    event = field.get("event")
    page = field.get("page")
    if process and event and page:
        return f"Processo {process} · Evento {event} · p. {page}"
    return None


def _safe_evidence(evidence: Mapping[str, object] | None) -> dict | None:
    if not isinstance(evidence, Mapping):
        return None
    document_id = evidence.get("document_id")
    page = evidence.get("page")
    if not isinstance(document_id, str) or not document_id or not isinstance(page, int) or page < 1:
        return None
    rects = []
    for rect in evidence.get("rects", []):
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            continue
        try:
            values = [float(value) for value in rect]
        except (TypeError, ValueError):
            continue
        if all(0 <= value <= 1 for value in values) and values[0] <= values[2] and values[1] <= values[3]:
            rects.append(values)
    return {
        "document_id": document_id,
        "page": page,
        "quote": evidence.get("quote") if isinstance(evidence.get("quote"), str) else None,
        "rects": rects,
        "method": str(evidence.get("method", "none")),
        "status": str(evidence.get("status", "missing")),
    }


def _safe_field(
    field: Mapping[str, object] | None,
    key: str,
    visual_evidence: Mapping[str, object] | None = None,
) -> dict:
    source = dict(field or {})
    candidates = [
        _safe_field(candidate, key)
        for candidate in source.get("candidates", [])
        if isinstance(candidate, Mapping)
    ]
    result = {
        "key": key,
        "value": source.get("value") if isinstance(source.get("value"), str) else None,
        "status": str(source.get("status", "missing")),
        "process": source.get("process") if isinstance(source.get("process"), str) else None,
        "event": source.get("event") if isinstance(source.get("event"), str) else None,
        "document": source.get("document") if isinstance(source.get("document"), str) else None,
        "page": source.get("page") if isinstance(source.get("page"), int) else None,
        "confidence": str(source.get("confidence", "high")),
        "raw_value": source.get("raw_value")
        if isinstance(source.get("raw_value"), str)
        else None,
        "citation": _citation(source),
        "candidates": candidates,
    }
    evidence = _safe_evidence(visual_evidence)
    if evidence is not None:
        result["evidence"] = evidence
    return result


def _safe_block(block: Mapping[str, object], visual_record: Mapping[str, object] | None = None) -> dict:
    raw_fields = block.get("fields", {})
    fields = {
        key: _safe_field(
            raw_fields.get(key),
            key,
            visual_record.get(key) if isinstance(visual_record, Mapping) else None,
        )
        for key in FIELD_ORDER
        if isinstance(raw_fields, Mapping)
    }
    return {
        "interested": str(block.get("interested", "Não identificado")),
        "pending": [str(item) for item in block.get("pending", [])],
        "fields": fields,
    }


def _safe_document(
    document: Mapping[str, object],
    analyzed: Mapping[str, object] | None,
    *,
    process_key: str = "",
    pdf_link_root: str | None = None,
    process_folder: str | None = None,
) -> dict:
    raw_path = Path(str(document.get("pdf_path", ""))).expanduser()
    if pdf_link_root is None:
        pdf_url = _relative_pdf_url(document.get("relative_path"))
    else:
        raw_path = raw_path.resolve()
        relative = Path(pdf_link_root) / str(process_folder or "") / raw_path.name
        pdf_url = _relative_pdf_url(relative.as_posix())
    page_count = int((analyzed or {}).get("pages", 0) or 0)
    classification = (analyzed or {}).get("classification") or document.get("classification") or document.get("kind")
    source_document_id = str(
        document.get("id")
        or document.get("document_id")
        or document.get("card_id")
        or document.get("title", "")
    )
    pdf_sha256 = str(document.get("sha256") or "")
    visual_document_id = hashlib.sha256(
        f"{process_key}|{document.get('event_id', document.get('event', ''))}|{source_document_id}|{pdf_sha256}".encode()
    ).hexdigest()
    return {
        "document_id": visual_document_id,
        "source_document_id": source_document_id,
        "sha256": pdf_sha256,
        "event": str(document.get("event", "")),
        "date": str(document.get("date", "")),
        "title": str(document.get("title", "")),
        "kind": str(document.get("kind", "")),
        "file": raw_path.name,
        "pages": page_count,
        "page_count": page_count,
        "classification": classification,
        "automatic_source": document.get("automatic_source") is True,
        "classification_conflict": document.get("classification_conflict") is True,
        "pending": classification in {"pendente_ocr", "erro_leitura"},
        "pdf_url": pdf_url,
    }


def _relative_pdf_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    normalized = value.replace("\\", "/")
    path = Path(normalized)
    if (
        "://" in normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or PureWindowsPath(normalized).is_absolute()
        or ".." in path.parts
    ):
        return ""
    return quote(path.as_posix(), safe="/._-()")


def _document_file(document: Mapping[str, object]) -> str:
    for key in ("relative_path", "pdf_path", "file"):
        value = document.get(key)
        if isinstance(value, str) and value:
            return Path(value.replace("\\", "/")).name
    return ""


def _safe_archive_document(
    event: Mapping[str, object],
    document: Mapping[str, object],
    target: Mapping[str, object] | None,
    analyzed: Mapping[str, object] | None,
    *,
    process_key: str = "",
) -> dict:
    source = target or {}
    classification = (
        source.get("classification")
        or source.get("kind")
        or document.get("classification")
        or "outro_documento"
    )
    page_count = int(
        document.get("page_count")
        or document.get("pages")
        or (analyzed or {}).get("pages")
        or source.get("page_count")
        or source.get("pages")
        or 0
    )
    status = str(document.get("status", ""))
    source_document_id = str(
        document.get("id")
        or document.get("document_id")
        or document.get("card_id")
        or source.get("id")
        or source.get("document_id")
        or source.get("card_id")
        or document.get("title")
        or source.get("title", "")
    )
    pdf_sha256 = str(document.get("sha256") or source.get("sha256") or "")
    visual_document_id = hashlib.sha256(
        f"{process_key}|{event.get('event_id', event.get('event', ''))}|{source_document_id}|{pdf_sha256}".encode()
    ).hexdigest()
    return {
        "document_id": visual_document_id,
        "source_document_id": source_document_id,
        "sha256": pdf_sha256,
        "event": str(event.get("event", source.get("event", ""))),
        "date": str(document.get("date") or event.get("date") or source.get("date", "")),
        "title": str(document.get("title") or source.get("title") or event.get("title", "")),
        "kind": str(classification),
        "file": _document_file(document) or _document_file(source),
        "pages": page_count,
        "page_count": page_count,
        "classification": str(classification),
        "automatic_source": (
            source.get("automatic_source") is True
            if target is not None
            else document.get("automatic_source") is True
        ),
        "classification_conflict": document.get("classification_conflict") is True,
        "pending": (
            classification in {"pendente_ocr", "erro_leitura"}
            or bool(status and status != "complete")
        ),
        "pdf_url": _relative_pdf_url(document.get("relative_path")),
    }


def build_interface_payload(
    manifest_path: Path,
    checkpoint_path: Path,
    *,
    pdf_link_root: str | None = None,
    archive_index_path: Path | None = None,
    visual_evidence_path: Path | None = None,
) -> dict:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    checkpoint = json.loads(Path(checkpoint_path).read_text(encoding="utf-8"))
    checkpoint_processes = checkpoint.get("processes", {})
    archive_index = (
        json.loads(Path(archive_index_path).read_text(encoding="utf-8-sig"))
        if archive_index_path is not None
        else {}
    )
    archive_processes = {
        str(item.get("key") or item.get("process") or item.get("id") or ""): item
        for item in archive_index.get("processes", [])
        if isinstance(item, Mapping)
    }
    visual_evidence = {}
    if visual_evidence_path is not None and Path(visual_evidence_path).exists():
        loaded_visual_evidence = json.loads(Path(visual_evidence_path).read_text(encoding="utf-8-sig"))
        if isinstance(loaded_visual_evidence, Mapping) and loaded_visual_evidence.get("schema_version") == 1:
            visual_evidence = dict(loaded_visual_evidence)
    visual_records = visual_evidence.get("records", {}) if isinstance(visual_evidence, Mapping) else {}

    processes = []
    for entry in manifest.get("processes", []):
        process = str(entry.get("process", ""))
        saved = checkpoint_processes.get(process, {})
        result = saved.get("result", {}) if isinstance(saved, Mapping) else {}
        analyzed_by_event_file = {
            (str(item.get("event", "")), str(item.get("file", ""))): item
            for item in saved.get("documents", [])
            if isinstance(item, Mapping)
        }
        documents = []
        for document in entry.get("documents", []):
            if not isinstance(document, Mapping):
                continue
            file_name = Path(str(document.get("pdf_path", ""))).name
            analyzed = analyzed_by_event_file.get(
                (str(document.get("event", "")), file_name)
            )
            documents.append(
                _safe_document(
                    document,
                    analyzed,
                    process_key=process,
                    pdf_link_root=pdf_link_root,
                    process_folder=process.replace("/", "-"),
                )
            )

        all_documents = []
        archive_process = archive_processes.get(process, {})
        target_by_event_file = {
            (str(document.get("event", "")), _document_file(document)): document
            for document in entry.get("documents", [])
            if isinstance(document, Mapping)
        }
        for event in archive_process.get("events", []):
            if not isinstance(event, Mapping):
                continue
            event_id = str(event.get("event", ""))
            for document in event.get("documents", []):
                if not isinstance(document, Mapping):
                    continue
                file_name = _document_file(document)
                all_documents.append(
                    _safe_archive_document(
                        event,
                        document,
                        target_by_event_file.get((event_id, file_name)),
                        analyzed_by_event_file.get((event_id, file_name)),
                        process_key=process,
                    )
                )
        if not all_documents:
            all_documents = [dict(document) for document in documents]
        all_documents.sort(key=_document_sort_key)

        blocks = []
        for block in result.get("blocks", []):
            if not isinstance(block, Mapping):
                continue
            interested_normalized = re.sub(r"\s+", " ", str(block.get("interested", "")).casefold()).strip()
            record_id = hashlib.sha256(f"{process}|{interested_normalized}".encode()).hexdigest()
            blocks.append(_safe_block(block, visual_records.get(record_id)))
        processes.append(
            {
                "process": process,
                "status": str(saved.get("status", result.get("status", "pending"))),
                "pending": [str(item) for item in saved.get("pendencias", [])],
                "documents": documents,
                "all_documents": all_documents,
                "blocks": blocks,
            }
        )

    # Start on actionable records. Processes without either priority document
    # remain available, but appear after those that can populate the form.
    processes.sort(key=lambda item: not bool(item["documents"]))

    fields = [
        field
        for process in processes
        for block in process["blocks"]
        for field in block["fields"].values()
    ]
    priority_document_count = sum(len(process["documents"]) for process in processes)
    all_document_count = sum(len(process["all_documents"]) for process in processes)
    field_conflicts = sum(field["status"] == "conflict" for field in fields)
    field_pending = sum(field["status"] != "found" for field in fields)
    document_conflicts = sum(
        document["classification_conflict"]
        for process in processes
        for document in process["all_documents"]
    )
    document_pending = sum(
        document["pending"]
        for process in processes
        for document in process["all_documents"]
    )
    return {
        "generated_at": str(checkpoint.get("created_at", "")),
        "run_id": str(checkpoint.get("run_id", "")),
        "processes": processes,
        "review_assets": {
            "mode": "offline-pdfjs-with-iframe-fallback",
            "selection_module": "../app/web/review-app.js",
            "style": "../app/web/review.css",
            "pdfjs_manifest": "../app/web/vendor/pdfjs/manifest.json",
            "viewer_candidates": [
                {
                    "viewer_module": "../app/web/pdf-viewer.js",
                    "pdfjs_module": "../app/web/vendor/pdfjs/pdf.mjs",
                    "pdfjs_worker": "../app/web/vendor/pdfjs/pdf.worker.mjs",
                },
                {
                    "viewer_module": "web/pdf-viewer.js",
                    "pdfjs_module": "web/vendor/pdfjs/pdf.mjs",
                    "pdfjs_worker": "web/vendor/pdfjs/pdf.worker.mjs",
                },
            ],
        },
        "stats": {
            "processes": len(processes),
            "documents": priority_document_count,
            "priority_documents": priority_document_count,
            "all_documents": all_document_count,
            "blocks": sum(len(process["blocks"]) for process in processes),
            "found": sum(field["status"] == "found" for field in fields),
            "conflicts": field_conflicts + document_conflicts,
            "pending": field_pending + document_pending,
        },
    }


HTML_TEMPLATE = r'''<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Complementar Ato · mesa de conferência</title>
  <style>
    :root {
      --ink: #142536;
      --ink-soft: #536475;
      --paper: #f6f0e4;
      --paper-deep: #e8dece;
      --line: #d5cabb;
      --teal: #1d7f78;
      --teal-dark: #105b59;
      --copper: #ce6844;
      --amber: #e6ad54;
      --danger: #a63c35;
      --shadow: 0 18px 55px rgba(12, 30, 48, .16);
      --viewer-size: 52%;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; min-height: 100%; overflow: hidden; }
    body {
      margin: 0;
      color: var(--ink);
      background: #d7e0df;
      font: 14px/1.45 "Segoe UI", Aptos, Arial, sans-serif;
    }
    button, input, select { font: inherit; }
    button, select { cursor: pointer; }
    button:focus-visible, input:focus-visible, select:focus-visible,
    a:focus-visible { outline: 3px solid var(--amber); outline-offset: 2px; }
    .app-shell { height: 100vh; min-height: 0; display: flex; flex-direction: column; }
    .topbar {
      display: grid; grid-template-columns: minmax(230px, 1fr) minmax(380px, 1.7fr) auto;
      gap: 22px; align-items: center; padding: 18px 26px 16px;
      color: #f4f7f3; background: var(--ink);
      border-bottom: 5px solid var(--copper);
    }
    .brand { display: flex; gap: 13px; align-items: center; }
    .brand-mark {
      width: 39px; height: 39px; display: grid; place-items: center;
      color: var(--ink); background: var(--amber); font: 700 19px Georgia, serif;
      transform: rotate(-4deg); box-shadow: 5px 5px 0 rgba(206,104,68,.55);
    }
    .eyebrow { color: #a9d0c6; font-size: 10px; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; }
    h1, h2, h3, p { margin: 0; }
    .brand h1 { margin-top: 2px; font: 700 25px/1.05 Georgia, "Times New Roman", serif; letter-spacing: -.02em; }
    .brand-note { margin-top: 4px; color: #b5c2ca; font-size: 11px; }
    .toolbar { display: grid; grid-template-columns: 1fr auto auto auto; gap: 8px; align-items: center; }
    .toolbar label { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
    .toolbar input, .toolbar select {
      min-width: 0; height: 39px; padding: 0 12px; color: var(--ink);
      background: #f2f5f3; border: 1px solid #ced9d5; border-radius: 3px;
    }
    .toolbar select { font-weight: 700; }
    .icon-button, .outline-button {
      height: 39px; padding: 0 12px; color: #eff5f1; background: transparent;
      border: 1px solid #6a8a8b; border-radius: 3px; font-weight: 700;
    }
    .icon-button:hover, .outline-button:hover { background: #294153; border-color: #b5d1c9; }
    .stats { display: flex; gap: 13px; justify-content: flex-end; }
    .stat { min-width: 69px; padding-left: 11px; border-left: 1px solid #476070; }
    .stat strong { display: block; color: #fff; font-size: 19px; line-height: 1; }
    .stat span { color: #adc0c4; font-size: 10px; text-transform: uppercase; letter-spacing: .08em; }
    .notice {
      display: flex; gap: 12px; justify-content: space-between; align-items: center;
      padding: 9px 26px; color: #38515a; background: #e8eee9; border-bottom: 1px solid #cad9d2;
      font-size: 12px;
    }
    .notice strong { color: var(--teal-dark); }
    .notice .run { color: var(--ink-soft); font-family: Consolas, monospace; font-size: 11px; }
    .workspace { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, var(--viewer-size)) 18px minmax(0, 1fr); gap: 0; }
    .viewer-panel { min-height: 0; display: flex; flex-direction: column; background: #233242; }
    .splitter { position: relative; z-index: 4; display: flex; align-items: center; justify-content: center; min-width: 0; background: #162737; cursor: col-resize; touch-action: none; user-select: none; }
    .splitter::before { content: ""; position: absolute; inset: 0 auto 0 50%; width: 2px; background: var(--amber); opacity: .7; transform: translateX(-50%); }
    #split-slider { position: absolute; width: 1px; height: 1px; padding: 0; opacity: 0; pointer-events: none; }
    .splitter-handle { position: relative; z-index: 1; width: 12px; height: 58px; display: grid; place-items: center; background: var(--amber); border: 2px solid var(--ink); border-radius: 8px; box-shadow: 0 3px 10px rgba(0,0,0,.28); transition: transform .15s ease, background .15s ease; pointer-events: none; }
    .splitter-handle::before { content: ""; width: 3px; height: 30px; background: repeating-linear-gradient(to bottom, var(--ink) 0 3px, transparent 3px 6px); opacity: .72; }
    .splitter:hover .splitter-handle, .splitter.dragging .splitter-handle { background: #f2c56f; transform: scaleX(1.08); }
    #split-slider:focus-visible + .splitter-handle { outline: 3px solid var(--amber); outline-offset: 3px; }
    .viewer-head, .inspector-head { padding: 15px 19px; }
    .viewer-head { display: flex; gap: 12px; align-items: end; background: #1d2d3d; border-bottom: 1px solid #385264; }
    .viewer-head label, .inspector-head label { display: block; margin-bottom: 5px; color: #9db7ba; font-size: 10px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
    .viewer-head select { width: 100%; min-width: 0; height: 37px; padding: 0 10px; color: #edf4ee; background: #2c4050; border: 1px solid #627b83; border-radius: 3px; }
    .viewer-head .open-pdf { flex: none; display: inline-grid; place-items: center; height: 37px; padding: 0 11px; color: #102d35; background: var(--amber); border-radius: 3px; font-weight: 800; text-decoration: none; white-space: nowrap; }
    .viewer-head .open-pdf.disabled { opacity: .45; pointer-events: none; }
    .document-badges { display: flex; gap: 5px; align-items: center; flex-wrap: wrap; }
    .document-badge { display: inline-flex; align-items: center; min-height: 22px; padding: 3px 6px; border: 1px solid transparent; border-radius: 2px; font-size: 9px; font-weight: 900; letter-spacing: .08em; white-space: nowrap; }
    .badge-resolution { color: #fff; background: var(--teal); border-color: #7dc0b5; }
    .badge-guide { color: var(--ink); background: var(--amber); border-color: #f1cd86; }
    .badge-other { color: #e0e8e7; background: #526270; border-color: #71828a; }
    .badge-conflict { color: #fff; background: var(--danger); border-color: #df8b81; }
    .badge-pending { color: var(--ink); background: #f3d9a6; border-color: var(--copper); }
    .pdf-wrap { position: relative; flex: 1; min-height: 320px; padding: 17px; background: #29313a; }
    #pdf-frame { width: 100%; height: 100%; min-height: 480px; display: block; background: #fff; border: 1px solid #526270; box-shadow: 0 15px 34px rgba(0,0,0,.2); }
    #pdf-canvas-stage { position: relative; width: 100%; height: 100%; min-height: 480px; overflow: auto; display: none; padding: 10px; background: #66717a; border: 1px solid #526270; box-shadow: 0 15px 34px rgba(0,0,0,.2); }
    #pdf-canvas { display: block; max-width: none; margin: 0 auto; background: #fff; }
    #pdf-overlay { position: absolute; inset: 10px; pointer-events: none; }
    .review-mode-note { color: #d6e0dd; font-size: 10px; }
    .pdf-empty { position: absolute; inset: 17px; display: grid; place-items: center; color: #d5dfdd; background: repeating-linear-gradient(135deg, #303d48 0, #303d48 9px, #2b3741 9px, #2b3741 18px); text-align: center; }
    .pdf-empty div { max-width: 320px; padding: 20px; border: 1px dashed #71828a; }
    .pdf-empty strong { display: block; margin-bottom: 6px; color: #fff; font: 700 20px Georgia, serif; }
    .viewer-foot { display: flex; justify-content: space-between; gap: 10px; padding: 9px 18px; color: #a9b8bb; background: #1d2d3d; font-size: 11px; }
    .inspector { min-height: 0; overflow: auto; background: var(--paper); box-shadow: var(--shadow); }
    .inspector-head { background: var(--paper); border-bottom: 1px solid var(--line); }
    .process-line { display: flex; justify-content: space-between; gap: 15px; align-items: start; }
    .process-code { font: 700 28px/1 Georgia, serif; letter-spacing: -.03em; }
    .process-sub { margin-top: 6px; color: var(--ink-soft); font-size: 12px; }
    .status { display: inline-flex; align-items: center; gap: 6px; padding: 5px 8px; border-radius: 2px; color: #fff; background: var(--copper); font-size: 10px; font-weight: 900; letter-spacing: .1em; text-transform: uppercase; }
    .status.complete { background: var(--teal); }
    .status.pending { color: var(--ink); background: var(--amber); }
    .process-actions { flex: none; display: grid; justify-items: end; gap: 7px; }
    .done-toggle { display: inline-flex; align-items: center; gap: 6px; color: var(--ink-soft); font-size: 11px; font-weight: 800; cursor: pointer; white-space: nowrap; }
    .done-toggle input { width: 17px; height: 17px; margin: 0; accent-color: var(--teal-dark); cursor: pointer; }
    .done-toggle:has(input:checked) { color: var(--teal-dark); }
    .block-row { display: grid; grid-template-columns: 1fr minmax(150px, .7fr); gap: 11px; margin-top: 17px; }
    .block-row select { width: 100%; height: 36px; padding: 0 9px; color: var(--ink); background: #fffdf8; border: 1px solid #c4b9a8; border-radius: 2px; }
    .section { padding: 18px 20px; border-bottom: 1px solid var(--line); }
    .section-kicker { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; color: var(--teal-dark); font-size: 11px; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }
    .section-kicker::before { content: ""; width: 19px; height: 3px; background: var(--copper); }
    .field-list { display: grid; gap: 8px; }
    .field-card { padding: 12px 13px; background: rgba(255,253,248,.72); border: 1px solid #d9cebf; border-left: 4px solid #a6b9b2; }
    .field-card.conflict { border-left-color: var(--danger); background: #fff6eb; }
    .field-card.missing { border-left-color: #b9b0a2; }
    .field-head { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
    .field-label { color: var(--ink-soft); font-size: 11px; font-weight: 900; letter-spacing: .09em; text-transform: uppercase; }
    .field-state { color: var(--teal-dark); font-size: 10px; font-weight: 900; text-transform: uppercase; }
    .field-state.conflict { color: var(--danger); }
    .field-value { margin: 5px 0 8px; color: var(--ink); font: 700 16px/1.3 Georgia, serif; overflow-wrap: anywhere; }
    .field-value.muted { color: #837b70; font: 14px/1.4 "Segoe UI", sans-serif; }
    .field-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .copy-button, .source-button { min-height: 27px; padding: 4px 8px; border-radius: 2px; font-size: 11px; font-weight: 800; }
    .copy-button { color: #fff; background: var(--teal-dark); border: 1px solid var(--teal-dark); }
    .copy-button:hover { background: var(--teal); }
    .source-button { color: var(--ink-soft); background: transparent; border: 1px solid #c4b9a8; }
    .source-button:hover { color: var(--teal-dark); border-color: var(--teal); }
    .source-note { color: #6f766f; font-size: 11px; }
    .candidate-list { display: grid; gap: 7px; margin-top: 9px; }
    .candidate { padding: 8px 9px; background: #fffaf3; border: 1px solid #e1c7ad; }
    .candidate-value { color: var(--danger); font-weight: 800; overflow-wrap: anywhere; }
    .pending-list { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
    .pending-list li { display: flex; gap: 9px; align-items: start; color: #604e43; font-size: 13px; }
    .pending-list li::before { content: "!"; flex: none; display: grid; place-items: center; width: 18px; height: 18px; color: #fff; background: var(--copper); border-radius: 50%; font-weight: 900; }
    .empty-message { color: var(--ink-soft); font-style: italic; }
    .toast { position: fixed; right: 22px; bottom: 20px; z-index: 5; transform: translateY(20px); opacity: 0; padding: 10px 13px; color: #fff; background: var(--ink); border-left: 4px solid var(--amber); box-shadow: var(--shadow); transition: .18s ease; pointer-events: none; }
    .toast.show { transform: translateY(0); opacity: 1; }
    @media (min-width: 680px) and (max-width: 1080px) {
      html, body { height: 100%; overflow: hidden; }
      .app-shell { height: 100vh; min-height: 0; }
      .topbar {
        grid-template-columns: minmax(190px, .72fr) minmax(280px, 1.5fr) auto;
        gap: 12px; padding: 10px 14px 9px; border-bottom-width: 3px;
      }
      .brand { gap: 9px; }
      .brand-mark { width: 30px; height: 30px; font-size: 15px; box-shadow: 3px 3px 0 rgba(206,104,68,.55); }
      .eyebrow { font-size: 8px; letter-spacing: .12em; }
      .brand h1 { font-size: 18px; }
      .brand-note { display: none; }
      .toolbar { grid-template-columns: minmax(120px, 1fr) minmax(155px, 1.15fr) 31px 31px; gap: 5px; }
      .toolbar input, .toolbar select { height: 31px; padding: 0 8px; font-size: 11px; }
      .icon-button, .outline-button { height: 31px; padding: 0 6px; font-size: 13px; }
      .stats { display: grid; grid-template-columns: repeat(3, minmax(45px, 1fr)); gap: 5px 7px; }
      .stat { min-width: 49px; padding-left: 6px; }
      .stat strong { font-size: 15px; }
      .stat span { font-size: 8px; letter-spacing: .04em; }
      .notice { min-height: 30px; padding: 6px 14px; gap: 8px; font-size: 10px; }
      .notice > span:first-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .notice .run { flex: none; font-size: 9px; }
      .workspace { --viewer-size: 42%; grid-template-columns: minmax(0, var(--viewer-size)) 18px minmax(0, 1fr); }
      .viewer-head, .inspector-head { padding: 9px 10px; }
      .viewer-head { gap: 7px; }
      .viewer-head label, .inspector-head label { margin-bottom: 3px; font-size: 8px; letter-spacing: .08em; }
      .viewer-head select { height: 31px; padding: 0 7px; font-size: 10px; }
      .viewer-head .open-pdf { height: 31px; padding: 0 7px; font-size: 10px; }
      .document-badges { gap: 3px; }
      .document-badge { min-height: 18px; padding: 2px 4px; font-size: 7px; }
      .pdf-wrap { min-height: 0; padding: 7px; }
      #pdf-frame, #pdf-canvas-stage { min-height: 0; box-shadow: 0 8px 20px rgba(0,0,0,.2); }
      .pdf-empty { inset: 7px; }
      .pdf-empty div { max-width: 220px; padding: 12px; }
      .pdf-empty strong { font-size: 16px; }
      .pdf-empty span { font-size: 11px; }
      .viewer-foot { padding: 6px 10px; font-size: 9px; }
      .viewer-foot span:first-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .inspector { overflow: auto; }
      .process-line { gap: 8px; }
      .process-code { font-size: 21px; }
      .process-sub { margin-top: 3px; font-size: 10px; }
      .status { gap: 4px; padding: 4px 6px; font-size: 8px; }
      .process-actions { gap: 4px; }
      .done-toggle { gap: 4px; font-size: 9px; }
      .done-toggle input { width: 15px; height: 15px; }
      .block-row { grid-template-columns: minmax(0, 1fr) 55px; gap: 7px; margin-top: 9px; }
      .block-row select { height: 30px; padding: 0 7px; font-size: 11px; }
      .section { padding: 10px 12px; }
      .section-kicker { gap: 7px; margin-bottom: 7px; font-size: 9px; letter-spacing: .08em; }
      .section-kicker::before { width: 14px; height: 2px; }
      .field-list { gap: 5px; }
      .field-card { padding: 7px 8px; border-left-width: 3px; }
      .field-head { gap: 6px; }
      .field-label { font-size: 9px; letter-spacing: .06em; }
      .field-state { font-size: 8px; }
      .field-value { margin: 3px 0 5px; font-size: 12px; line-height: 1.18; }
      .field-value.muted { font-size: 10px; line-height: 1.2; }
      .field-actions { gap: 4px; }
      .copy-button, .source-button { min-height: 22px; padding: 2px 5px; font-size: 9px; }
      .source-note { font-size: 9px; }
      .candidate-list { gap: 4px; margin-top: 5px; }
      .candidate { padding: 5px 6px; }
      .candidate-value { font-size: 10px; }
      .pending-list { gap: 4px; }
      .pending-list li { gap: 6px; font-size: 10px; line-height: 1.25; }
      .pending-list li::before { width: 15px; height: 15px; }
      .toast { right: 12px; bottom: 12px; padding: 8px 10px; font-size: 11px; }
    }
    @media (max-width: 679px) {
      html, body { min-height: 100%; overflow: auto; }
      .app-shell { height: auto; min-height: 100vh; }
      .topbar, .notice { padding-left: 15px; padding-right: 15px; }
      .toolbar { grid-template-columns: 1fr 1fr; }
      .toolbar input, .toolbar select { grid-column: 1 / -1; }
      .workspace { --viewer-size: auto; grid-template-columns: 1fr; }
      .viewer-panel { min-height: 620px; }
      .inspector { max-height: none; }
      .splitter { display: none; }
      .block-row { grid-template-columns: 1fr; }
      .process-code { font-size: 23px; }
      .section, .inspector-head { padding-left: 15px; padding-right: 15px; }
    }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition: none !important; } }
  </style>
</head>
<body data-review-mode="offline-pdfjs-with-iframe-fallback">
<div class="app-shell">
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark">§</div>
      <div>
        <div class="eyebrow">mesa local de conferência</div>
        <h1>Complementar Ato</h1>
        <div class="brand-note">PDF de prova · campos para colar · revisão humana</div>
      </div>
    </div>
    <div class="toolbar">
      <label for="search-process">Localizar processo ou interessado</label>
      <input id="search-process" type="search" placeholder="Filtrar por processo ou nome…" autocomplete="off">
      <label for="process-select">Processo</label>
      <select id="process-select" aria-label="Processo"></select>
      <button class="icon-button" id="prev-process" type="button" title="Processo anterior">←</button>
      <button class="icon-button" id="next-process" type="button" title="Próximo processo">→</button>
    </div>
    <div class="stats" aria-label="Resumo da extração">
      <div class="stat"><strong id="stat-processes">0</strong><span>processos</span></div>
      <div class="stat"><strong id="stat-done">0</strong><span>feitos</span></div>
      <div class="stat"><strong id="stat-documents">0</strong><span>prioritários</span></div>
      <div class="stat"><strong id="stat-all-documents">0</strong><span>documentos</span></div>
      <div class="stat"><strong id="stat-found">0</strong><span>encontrados</span></div>
      <div class="stat"><strong id="stat-conflicts">0</strong><span>conflitos</span></div>
      <div class="stat"><strong id="stat-pending">0</strong><span>pendências</span></div>
    </div>
  </header>
  <div class="notice">
    <span><strong>Somente leitura.</strong> Use “Copiar” para levar um valor ao formulário do TCE. Nada nesta página envia ou altera atos.</span>
    <span class="run" id="run-label"></span>
  </div>
  <main class="workspace">
    <section class="viewer-panel" aria-label="Documentos do processo">
      <div class="viewer-head">
        <div style="min-width:0;flex:1">
          <label for="document-select">Arquivos do processo · evento posterior ao 1</label>
          <select id="document-select" aria-label="Arquivo do processo"></select>
        </div>
        <div class="document-badges" id="document-badges" aria-live="polite"></div>
        <a id="open-pdf" class="open-pdf disabled" href="#" target="_blank" rel="noopener">Abrir PDF ↗</a>
      </div>
      <div class="pdf-wrap">
        <iframe id="pdf-frame" title="PDF do documento selecionado"></iframe>
        <div id="pdf-canvas-stage" aria-label="PDF renderizado pela mesa offline">
          <canvas id="pdf-canvas"></canvas>
          <div id="pdf-overlay" aria-hidden="true"></div>
        </div>
        <div class="pdf-empty" id="pdf-empty"><div><strong>Selecione um documento</strong><span>O PDF aparecerá nesta área. Se o navegador bloquear a visualização local, use “Abrir PDF”.</span></div></div>
      </div>
      <div class="viewer-foot"><span id="document-meta">Nenhum documento selecionado</span><span class="review-mode-note" id="review-mode-note">Modo integrado tentando carregar · fallback iframe disponível</span></div>
    </section>
    <div class="splitter" id="splitter" title="Arraste ou use as setas para ajustar a largura dos painéis">
      <input id="split-slider" type="range" min="30" max="68" value="42" step="1" aria-label="Ajustar largura dos painéis">
      <span class="splitter-handle" aria-hidden="true"></span>
    </div>
    <aside class="inspector" aria-label="Informações para complementar o ato">
      <div class="inspector-head">
        <div class="process-line">
          <div><div class="eyebrow" style="color:var(--teal-dark)">registro selecionado</div><h2 class="process-code" id="process-heading">—</h2><p class="process-sub" id="process-sub">—</p></div>
          <div class="process-actions">
            <span class="status pending" id="process-status">PENDENTE</span>
            <label class="done-toggle" for="process-done"><input id="process-done" type="checkbox"><span>Processo feito</span></label>
          </div>
        </div>
        <div class="block-row">
          <div><label for="block-select">Interessado</label><select id="block-select" aria-label="Interessado"></select></div>
          <div><label>Leitura</label><div class="process-sub" id="process-count">—</div></div>
        </div>
      </div>
      <section class="section">
        <div class="section-kicker">Campos para colar no formulário</div>
        <div class="field-list" id="field-list"></div>
      </section>
      <section class="section">
        <div class="section-kicker">Pendências de conferência</div>
        <ul class="pending-list" id="pending-list"></ul>
      </section>
    </aside>
  </main>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script type="application/json" id="app-data">__APP_DATA__</script>
<script>
(() => {
  let data = JSON.parse(document.getElementById('app-data').textContent);
  const reviewAssets = data.review_assets || {};
  const labels = {
    modalidade: 'Modalidade', fundamento_legal: 'Fundamento legal',
    data_publicacao_doe: 'Data de publicação no DOE', cargo: 'Cargo',
    matricula: 'Matrícula', data_nascimento: 'Data de nascimento', genero: 'Gênero'
  };
  const order = Object.keys(labels);
  const state = { processIndex: 0, blockIndex: 0, documentIndex: 0, query: '', evidence: null };
  let integratedViewer = null;
  let integratedPdfjs = null;
  let integratedLoad = null;
  let renderSequence = 0;
  let liveRevision = Number(data.live_revision || 0);
  const COMPLETED_STORAGE_KEY = data.archive_cycle_id
    ? `tce-completed-processes-v1:${data.archive_cycle_id}`
    : 'tce-completed-processes-v1';
  let completedProcesses = new Set();
  try {
    const savedCompleted = JSON.parse(localStorage.getItem(COMPLETED_STORAGE_KEY) || '[]');
    if (Array.isArray(savedCompleted)) completedProcesses = new Set(savedCompleted.map(String));
  } catch (_) {}
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const statusLabel = (status) => ({complete: 'completo', partial: 'parcial', pending: 'pendente'}[status] || status);
  const sourceText = (field) => field && field.citation ? field.citation : 'Fonte sem página';
  const currentProcess = () => data.processes[state.processIndex] || {process: '', status: 'pending', documents: [], all_documents: [], blocks: []};
  const currentBlock = () => currentProcess().blocks[state.blockIndex] || {interested: 'Não identificado', pending: [], fields: {}};
  const notify = (message) => { const toast = $('toast'); toast.textContent = message; toast.classList.add('show'); clearTimeout(notify.timer); notify.timer = setTimeout(() => toast.classList.remove('show'), 2200); };

  function applyLivePayload(next) {
    if (!next || !Array.isArray(next.processes)) return;
    const previousProcessKey = currentProcess().process;
    const previousInterested = currentBlock().interested;
    const previousDocuments = currentProcess().all_documents || currentProcess().documents || [];
    const previousDocumentId = previousDocuments[state.documentIndex]?.document_id || null;
    const previousProcess = JSON.stringify(currentProcess());
    data = next;
    const nextProcessIndex = data.processes.findIndex((process) => process.process === previousProcessKey);
    state.processIndex = nextProcessIndex >= 0 ? nextProcessIndex : Math.min(state.processIndex, Math.max(0, data.processes.length - 1));
    const nextBlocks = currentProcess().blocks || [];
    const nextBlockIndex = nextBlocks.findIndex((block) => block.interested === previousInterested);
    state.blockIndex = nextBlockIndex >= 0 ? nextBlockIndex : Math.min(state.blockIndex, Math.max(0, nextBlocks.length - 1));
    const nextDocuments = currentProcess().all_documents || currentProcess().documents || [];
    const nextDocumentIndex = nextDocuments.findIndex((document) => document.document_id === previousDocumentId);
    state.documentIndex = nextDocumentIndex >= 0 ? nextDocumentIndex : Math.min(state.documentIndex, Math.max(0, nextDocuments.length - 1));
    const currentProcessChanged = previousProcess !== JSON.stringify(currentProcess());
    renderStats();
    renderProcessOptions();
    if (currentProcessChanged) {
      state.evidence = state.evidence && nextDocuments[state.documentIndex]?.document_id === state.evidence.documentId
        ? state.evidence
        : null;
      const preserveViewer = Boolean(previousDocumentId && nextDocuments[state.documentIndex]?.document_id === previousDocumentId);
      renderIdentity(); renderFields(); renderPending(); renderDocuments(preserveViewer);
    }
  }

  async function pollLiveReview() {
    const localFileProtocol = 'file' + ':';
    if (window.location.protocol === localFileProtocol) return;
    if (window.location.protocol !== 'http:') return;
    try {
      const response = await fetch(`/api/v1/review-data?since=${encodeURIComponent(liveRevision)}`, {
        credentials: 'same-origin',
        cache: 'no-store',
      });
      if (response.ok) {
        const envelope = await response.json();
        if (!envelope.unchanged && envelope.data) {
          liveRevision = Number(envelope.revision || envelope.data.live_revision || liveRevision);
          applyLivePayload(envelope.data);
        }
      }
    } catch (_) {
      // The desk remains usable when the optional live service is unavailable.
    }
    const delay = document.visibilityState === 'hidden' ? 2000 : 500;
    window.setTimeout(pollLiveReview, delay);
  }

  function splitBounds() {
    const workspace = document.querySelector('.workspace');
    const width = workspace && workspace.clientWidth ? workspace.clientWidth : window.innerWidth;
    const divider = 18;
    const minViewer = width <= 1080 ? 290 : 340;
    const minInspector = width <= 1080 ? 360 : 430;
    const min = Math.max(30, Math.ceil((minViewer / width) * 100));
    const max = Math.min(68, Math.floor(((width - divider - minInspector) / width) * 100));
    return { min, max: Math.max(min + 1, max) };
  }

  function applySplit(value, persist) {
    const slider = $('split-slider');
    if (!slider) return;
    const bounds = splitBounds();
    const numeric = Number(value);
    const percent = Math.min(bounds.max, Math.max(bounds.min, Number.isFinite(numeric) ? numeric : 42));
    slider.min = String(bounds.min);
    slider.max = String(bounds.max);
    slider.value = String(percent);
    document.querySelector('.workspace').style.setProperty('--viewer-size', `${percent}%`);
    const splitter = $('splitter');
    splitter.setAttribute('aria-valuemin', String(bounds.min));
    splitter.setAttribute('aria-valuemax', String(bounds.max));
    splitter.setAttribute('aria-valuenow', String(percent));
    if (persist) {
      try { localStorage.setItem('tce-split-percent', String(percent)); } catch (_) {}
    }
  }

  function updateSplitBounds() { applySplit($('split-slider').value, false); }

  function applySplitFromPointer(clientX) {
    const workspace = document.querySelector('.workspace');
    const bounds = workspace.getBoundingClientRect();
    if (!bounds.width) return;
    const dividerOffset = 9;
    applySplit(((clientX - bounds.left - dividerOffset) / bounds.width) * 100, true);
  }

  function renderStats() {
    $('stat-processes').textContent = data.stats.processes;
    $('stat-done').textContent = completedProcesses.size;
    $('stat-documents').textContent = data.stats.priority_documents ?? data.stats.documents ?? 0;
    $('stat-all-documents').textContent = data.stats.all_documents ?? data.stats.documents ?? 0;
    $('stat-found').textContent = data.stats.found;
    $('stat-conflicts').textContent = data.stats.conflicts;
    $('stat-pending').textContent = data.stats.pending ?? 0;
    $('run-label').textContent = data.run_id ? `lote ${data.run_id}` : 'lote local';
  }

  function matchingIndexes() {
    const query = state.query.trim().toLocaleLowerCase('pt-BR');
    if (!query) return data.processes.map((_, index) => index);
    return data.processes.map((process, index) => {
      const names = process.blocks.map((block) => block.interested).join(' ');
      return `${process.process} ${names}`.toLocaleLowerCase('pt-BR').includes(query) ? index : -1;
    }).filter((index) => index >= 0);
  }

  function renderProcessOptions() {
    const select = $('process-select');
    const indexes = matchingIndexes();
    select.innerHTML = indexes.length ? indexes.map((index) => {
      const process = data.processes[index];
      const name = process.blocks[0] ? process.blocks[0].interested : 'sem interessado identificado';
      const doneMark = completedProcesses.has(process.process) ? '✓ ' : '';
      return `<option value="${index}">${doneMark}${esc(process.process)} · ${esc(name)}</option>`;
    }).join('') : '<option value="-1">Nenhum processo encontrado</option>';
    select.value = indexes.includes(state.processIndex) ? String(state.processIndex) : (indexes[0] ?? '-1');
    if (select.value !== '-1') state.processIndex = Number(select.value);
  }

  function renderIdentity() {
    const process = currentProcess();
    $('process-heading').textContent = process.process || '—';
    $('process-sub').textContent = `${process.documents.length} prioritário(s) · ${(process.all_documents || process.documents).length} arquivo(s) no processo`;
    const status = $('process-status');
    status.textContent = statusLabel(process.status).toUpperCase();
    status.className = `status ${process.status === 'complete' ? 'complete' : process.status === 'pending' ? 'pending' : ''}`;
    $('process-done').checked = completedProcesses.has(process.process);
    $('process-count').textContent = `${state.processIndex + 1} / ${data.processes.length}`;
    const blockSelect = $('block-select');
    blockSelect.innerHTML = process.blocks.length ? process.blocks.map((block, index) => `<option value="${index}">${esc(block.interested)}</option>`).join('') : '<option value="0">Não identificado</option>';
    state.blockIndex = Math.min(state.blockIndex, Math.max(0, process.blocks.length - 1));
    blockSelect.value = String(state.blockIndex);
  }

  function makeButton(text, className, handler, disabled = false) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = className; button.textContent = text; button.disabled = disabled; button.addEventListener('click', handler); return button;
  }

  async function copyValue(value, button) {
    let copied = false;
    try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(value); copied = true; } } catch (_) {}
    if (!copied) {
      const area = document.createElement('textarea'); area.value = value; area.style.position = 'fixed'; area.style.opacity = '0'; document.body.appendChild(area); area.focus(); area.select();
      try { copied = document.execCommand('copy'); } catch (_) {} area.remove();
    }
    if (copied) { const old = button.textContent; button.textContent = 'Copiado ✓'; setTimeout(() => button.textContent = old, 1300); notify('Valor copiado para colar no formulário.'); }
    else notify('A cópia foi bloqueada; selecione o valor manualmente.');
  }

  function sourceButton(field) {
    if (!field || !field.citation) return null;
    const evidence = field.evidence || {};
    return makeButton(`Ver ${field.citation}`, 'source-button', () => selectDocument(
      evidence.document_id || null,
      field.event,
      evidence.page || field.page,
      evidence.rects || [],
    ));
  }

  function candidateNode(candidate) {
    const row = document.createElement('div'); row.className = 'candidate';
    row.innerHTML = `<div class="candidate-value">${esc(candidate.value || candidate.raw_value || 'Valor ambíguo')}</div><div class="field-actions"></div>`;
    const actions = row.querySelector('.field-actions');
    if (candidate.value) actions.appendChild(makeButton('Copiar alternativa', 'copy-button', (event) => copyValue(candidate.value, event.currentTarget)));
    const source = sourceButton(candidate); if (source) actions.appendChild(source);
    return row;
  }

  function renderFields() {
    const block = currentBlock(); const list = $('field-list'); list.replaceChildren();
    order.forEach((key) => {
      const field = block.fields[key] || {status: 'missing', value: null, candidates: []};
      const card = document.createElement('article'); card.className = `field-card ${field.status}`;
      const status = field.status === 'found' ? 'encontrado' : field.status === 'conflict' ? 'conflito' : field.status === 'ambiguous' ? 'ambíguo' : 'pendente';
      const value = field.status === 'found' && field.value ? field.value : field.status === 'conflict' ? 'Revisar alternativas' : field.raw_value || 'Não localizado com segurança';
      card.innerHTML = `<div class="field-head"><span class="field-label">${labels[key]}</span><span class="field-state ${field.status}">${status}</span></div><div class="field-value ${field.status === 'found' ? '' : 'muted'}">${esc(value)}</div><div class="field-actions"></div>`;
      const actions = card.querySelector('.field-actions');
      if (field.status === 'found' && field.value) actions.appendChild(makeButton('Copiar valor', 'copy-button', (event) => copyValue(field.value, event.currentTarget)));
      const source = sourceButton(field); if (source) actions.appendChild(source); else if (field.status !== 'found') { const note = document.createElement('span'); note.className = 'source-note'; note.textContent = 'Sem evidência segura'; actions.appendChild(note); }
      if (field.status === 'conflict' && field.candidates && field.candidates.length) { const candidates = document.createElement('div'); candidates.className = 'candidate-list'; field.candidates.forEach((candidate) => candidates.appendChild(candidateNode(candidate))); card.appendChild(candidates); }
      list.appendChild(card);
    });
  }

  function renderPending() {
    const block = currentBlock(); const items = [...(block.pending || [])];
    order.forEach((key) => { const field = block.fields[key]; if (!field || field.status !== 'found') items.push(labels[key]); });
    const unique = [...new Set(items)]; const list = $('pending-list'); list.replaceChildren();
    if (!unique.length) { const empty = document.createElement('li'); empty.className = 'empty-message'; empty.textContent = 'Nenhuma pendência registrada.'; list.appendChild(empty); return; }
    unique.forEach((item) => { const li = document.createElement('li'); li.textContent = item; list.appendChild(li); });
  }

  async function ensureIntegratedViewer() {
    if (integratedViewer) return true;
    if (integratedLoad) return integratedLoad;
    integratedLoad = (async () => {
      const candidates = Array.isArray(reviewAssets.viewer_candidates)
        ? reviewAssets.viewer_candidates
        : [{ viewer_module: reviewAssets.viewer_module, pdfjs_module: reviewAssets.pdfjs_module, pdfjs_worker: reviewAssets.pdfjs_worker }];
      for (const candidate of candidates) {
        if (!candidate?.viewer_module || !candidate?.pdfjs_module) continue;
        try {
          const [viewerModule, pdfjsModule] = await Promise.all([
            import(`./${candidate.viewer_module}`),
            import(`./${candidate.pdfjs_module}`),
          ]);
          if (typeof viewerModule.renderPdfPage !== 'function' || typeof pdfjsModule.getDocument !== 'function') continue;
          integratedViewer = viewerModule;
          integratedPdfjs = pdfjsModule;
          reviewAssets.pdfjs_worker = candidate.pdfjs_worker;
          $('review-mode-note').textContent = 'Modo PDF.js local · fallback iframe disponível';
          return true;
        } catch (_) {
          // Try the next package-relative location before falling back to iframe.
        }
      }
      $('review-mode-note').textContent = 'Modo iframe nativo · PDF.js local indisponível';
      return false;
    })();
    return integratedLoad;
  }

  async function renderIntegrated(document, page, rects) {
    const sequence = ++renderSequence;
    if (!(await ensureIntegratedViewer()) || sequence !== renderSequence) return false;
    try {
      await integratedViewer.renderPdfPage({
        pdfjs: integratedPdfjs,
        pdfUrl: document.pdf_url,
        pageNumber: page,
        canvas: $('pdf-canvas'),
        overlay: $('pdf-overlay'),
        workerUrl: reviewAssets.pdfjs_worker,
        evidence: { rects },
      });
      if (sequence !== renderSequence) return false;
      $('pdf-frame').style.display = 'none';
      $('pdf-canvas-stage').style.display = 'block';
      return true;
    } catch (_) {
      $('pdf-frame').style.display = 'block';
      $('pdf-canvas-stage').style.display = 'none';
      $('review-mode-note').textContent = 'Modo iframe nativo · PDF.js local falhou';
      return false;
    }
  }

  function renderDocuments(preserveViewer = false) {
    const process = currentProcess(); const select = $('document-select');
    const documents = process.all_documents || process.documents;
    const prefixes = {resolucao_administrativa: 'RESOLUÇÃO', guia_financeira_taxacao: 'GUIA', outro_documento: 'OUTRO', pendente_ocr: 'PENDENTE', erro_leitura: 'PENDENTE'};
    select.innerHTML = documents.length ? documents.map((document, index) => `<option value="${index}">${esc(prefixes[document.classification] || 'OUTRO')} · Evento ${esc(document.event)} · ${esc(document.title || document.file)}</option>`).join('') : '<option value="-1">Nenhum arquivo disponível</option>';
    state.documentIndex = Math.min(state.documentIndex, Math.max(0, documents.length - 1)); select.value = String(documents.length ? state.documentIndex : -1);
    const document = documents[state.documentIndex]; const frame = $('pdf-frame'); const empty = $('pdf-empty'); const open = $('open-pdf'); const badges = $('document-badges');
    if (!document) { frame.removeAttribute('src'); frame.style.visibility = 'hidden'; frame.style.display = 'block'; $('pdf-canvas-stage').style.display = 'none'; empty.style.display = 'grid'; open.classList.add('disabled'); open.removeAttribute('href'); badges.replaceChildren(); $('document-meta').textContent = 'Nenhum arquivo disponível'; return; }
    const kindBadges = {
      resolucao_administrativa: '<span class="document-badge badge-resolution" data-kind="resolucao_administrativa">RESOLUÇÃO</span>',
      guia_financeira_taxacao: '<span class="document-badge badge-guide" data-kind="guia_financeira_taxacao">GUIA</span>',
      outro_documento: '<span class="document-badge badge-other" data-kind="outro_documento">OUTRO</span>',
      pendente_ocr: '<span class="document-badge badge-pending" data-kind="pendente_ocr">PENDENTE</span>',
      erro_leitura: '<span class="document-badge badge-pending" data-kind="erro_leitura">PENDENTE</span>'
    };
    badges.innerHTML = kindBadges[document.classification] || kindBadges.outro_documento;
    if (document.classification_conflict) badges.insertAdjacentHTML('beforeend', '<span class="document-badge badge-conflict">CONFLITO</span>');
    if (document.pending && !['pendente_ocr', 'erro_leitura'].includes(document.classification)) badges.insertAdjacentHTML('beforeend', '<span class="document-badge badge-pending">PENDENTE</span>');
    if (!document.pdf_url) { frame.removeAttribute('src'); frame.style.visibility = 'hidden'; frame.style.display = 'block'; $('pdf-canvas-stage').style.display = 'none'; empty.style.display = 'grid'; open.classList.add('disabled'); open.removeAttribute('href'); $('document-meta').textContent = `Evento ${document.event} · ${document.file || document.title} · arquivo indisponível`; return; }
    if (preserveViewer && frame.getAttribute('src')) {
      frame.style.visibility = 'visible'; open.href = document.pdf_url; open.classList.remove('disabled');
      $('document-meta').textContent = `Evento ${document.event} · ${document.file} · ${document.page_count || document.pages || '?'} página(s)`;
      return;
    }
    const evidence = state.evidence && state.evidence.documentId === document.document_id ? state.evidence : null;
    const page = evidence?.page || 1;
    frame.style.visibility = 'visible'; frame.style.display = 'block'; $('pdf-canvas-stage').style.display = 'none'; empty.style.display = 'none'; frame.src = `${document.pdf_url}#page=${page}&zoom=page-fit`; open.href = document.pdf_url; open.classList.remove('disabled'); $('document-meta').textContent = `Evento ${document.event} · ${document.file} · ${document.page_count || document.pages || '?'} página(s)`;
    void renderIntegrated(document, page, evidence?.rects || []);
  }

  function selectDocument(documentId, eventId, page, rects = []) { const process = currentProcess(); const documents = process.all_documents || process.documents; const index = documents.findIndex((document) => document.pdf_url && ((documentId && document.document_id === documentId) || (!documentId && String(document.event) === String(eventId)))); if (index < 0) { notify('PDF da evidência não está disponível neste lote.'); return; } state.documentIndex = index; state.evidence = { documentId: documents[index].document_id, page: page || 1, rects }; renderDocuments(); notify(`PDF posicionado no Evento ${eventId || documents[index].event}, página ${page || 1}.`); }

  function render() { renderProcessOptions(); renderIdentity(); renderFields(); renderPending(); renderDocuments(); }
  $('search-process').addEventListener('input', (event) => { state.query = event.target.value; renderProcessOptions(); render(); });
  $('process-select').addEventListener('change', (event) => { state.processIndex = Number(event.target.value); state.blockIndex = 0; state.documentIndex = 0; render(); });
  $('block-select').addEventListener('change', (event) => { state.blockIndex = Number(event.target.value); renderFields(); renderPending(); });
  $('document-select').addEventListener('change', (event) => { state.documentIndex = Number(event.target.value); state.evidence = null; renderDocuments(); });
  $('prev-process').addEventListener('click', () => { if (state.processIndex > 0) { state.processIndex--; state.blockIndex = 0; state.documentIndex = 0; render(); } });
  $('next-process').addEventListener('click', () => { if (state.processIndex < data.processes.length - 1) { state.processIndex++; state.blockIndex = 0; state.documentIndex = 0; render(); } });
  $('process-done').addEventListener('change', (event) => {
    const processId = currentProcess().process;
    if (!processId) return;
    if (event.target.checked) completedProcesses.add(processId); else completedProcesses.delete(processId);
    try { localStorage.setItem(COMPLETED_STORAGE_KEY, JSON.stringify([...completedProcesses])); } catch (_) {}
    renderStats();
    renderProcessOptions();
    $('process-done').checked = completedProcesses.has(processId);
    notify(event.target.checked ? 'Processo marcado como feito.' : 'Marcação de processo removida.');
  });
  let storedSplit = 42;
  try {
    const savedValue = localStorage.getItem('tce-split-percent');
    if (savedValue !== null) {
      const saved = Number(savedValue);
      if (Number.isFinite(saved)) storedSplit = saved;
    }
  } catch (_) {}
  const splitter = $('splitter');
  let splitDragging = false;
  splitter.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    splitDragging = true;
    splitter.classList.add('dragging');
    splitter.setPointerCapture(event.pointerId);
    $('split-slider').focus({preventScroll: true});
    applySplitFromPointer(event.clientX);
    event.preventDefault();
  });
  splitter.addEventListener('pointermove', (event) => {
    if (splitDragging) applySplitFromPointer(event.clientX);
  });
  const stopSplitDrag = (event) => {
    if (!splitDragging) return;
    splitDragging = false;
    splitter.classList.remove('dragging');
    if (splitter.hasPointerCapture(event.pointerId)) splitter.releasePointerCapture(event.pointerId);
  };
  splitter.addEventListener('pointerup', stopSplitDrag);
  splitter.addEventListener('pointercancel', stopSplitDrag);
  $('split-slider').addEventListener('input', (event) => applySplit(event.target.value, true));
  window.addEventListener('resize', updateSplitBounds);
  applySplit(storedSplit, false);
  renderStats(); render();
  void pollLiveReview();
})();
</script>
</body>
</html>
'''


_EXTERNAL_URL = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)


def _sanitize_for_offline(value):
    if isinstance(value, str):
        return _EXTERNAL_URL.sub("[endereço externo omitido]", value)
    if isinstance(value, list):
        return [_sanitize_for_offline(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_for_offline(item) for key, item in value.items()}
    return value


def render_html(payload: Mapping[str, object]) -> str:
    sanitized = _sanitize_for_offline(dict(payload))
    serialized = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    return HTML_TEMPLATE.replace("__APP_DATA__", serialized)


def write_html(
    manifest_path: Path,
    checkpoint_path: Path,
    output_path: Path,
    *,
    pdf_link_root: str | None = None,
    archive_index_path: Path | None = None,
    visual_evidence_path: Path | None = None,
) -> None:
    payload = build_interface_payload(
            manifest_path,
            checkpoint_path,
            pdf_link_root=pdf_link_root,
            archive_index_path=archive_index_path,
            visual_evidence_path=visual_evidence_path,
        )
    cycle_path = output_path.parent / "ciclo-acervo.json"
    if cycle_path.exists():
        cycle = json.loads(cycle_path.read_text(encoding="utf-8-sig"))
        if not isinstance(cycle, dict) or type(cycle.get("version")) is not int or cycle.get("version") != 1 or not isinstance(cycle.get("id"), str):
            raise ValueError("Marcador do ciclo do acervo inválido")
        payload["archive_cycle_id"] = UUID(cycle["id"]).hex
    html = render_html(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=output_path.parent, prefix=f".{output_path.name}.", suffix=".tmp", delete=False
    ) as temporary:
        temporary.write(html)
        temporary_path = Path(temporary.name)
    temporary_path.replace(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--pdf-link-root",
        help="Raiz relativa dos PDFs no HTML, para uso em pacote portátil.",
    )
    parser.add_argument(
        "--archive-index",
        type=Path,
        help="Índice local do acervo para listar todos os arquivos do processo.",
    )
    parser.add_argument(
        "--visual-evidence",
        type=Path,
        help="Sidecar de evidências geométricas para a mesa offline.",
    )
    args = parser.parse_args()
    write_html(
        args.manifest,
        args.checkpoint,
        args.output,
        pdf_link_root=args.pdf_link_root,
        archive_index_path=args.archive_index,
        visual_evidence_path=args.visual_evidence,
    )
    payload = build_interface_payload(
        args.manifest,
        args.checkpoint,
        pdf_link_root=args.pdf_link_root,
        archive_index_path=args.archive_index,
        visual_evidence_path=args.visual_evidence,
    )
    print(json.dumps(payload["stats"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
