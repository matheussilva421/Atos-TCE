"""Two-phase local runner for the TCE/RN document manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Mapping, Sequence

from tce_extractor import (
    FIELD_LABELS,
    FIELD_ORDER,
    CheckpointStore,
    Extraction,
    FieldEvidence,
    classify_document,
    extract_fields,
    extract_pdf_pages,
    merge_extractions,
    _fold,
)


def process_input_signature(entry: Mapping[str, object]) -> str:
    """Return an order-independent signature for one process's document inputs."""
    payload = sorted(
        (str(document.get("event", "")), str(document.get("sha256", "")))
        for document in entry.get("documents", [])
        if isinstance(document, Mapping)
    )
    serialized = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _evidence_to_dict(evidence: FieldEvidence) -> dict:
    return {
        "key": evidence.key,
        "value": evidence.value,
        "status": evidence.status,
        "process": evidence.process,
        "event": evidence.event,
        "document": evidence.document,
        "page": evidence.page,
        "confidence": evidence.confidence,
        "raw_value": evidence.raw_value,
        "candidates": [_evidence_to_dict(item) for item in evidence.candidates],
    }


def _evidence_from_dict(payload: Mapping[str, object]) -> FieldEvidence:
    return FieldEvidence(
        key=str(payload.get("key", "")),
        value=payload.get("value") if isinstance(payload.get("value"), str) else None,
        status=str(payload.get("status", "missing")),
        process=payload.get("process") if isinstance(payload.get("process"), str) else None,
        event=payload.get("event") if isinstance(payload.get("event"), str) else None,
        document=payload.get("document") if isinstance(payload.get("document"), str) else None,
        page=payload.get("page") if isinstance(payload.get("page"), int) else None,
        confidence=str(payload.get("confidence", "high")),
        raw_value=payload.get("raw_value")
        if isinstance(payload.get("raw_value"), str)
        else None,
        candidates=tuple(
            _evidence_from_dict(item)
            for item in payload.get("candidates", [])
            if isinstance(item, Mapping)
        ),
    )


def _record_to_checkpoint(record: Mapping[str, object]) -> dict:
    blocks = []
    for block in record.get("blocks", []):
        fields = block.get("fields", {})
        blocks.append(
            {
                "interested": block.get("interested", "Não identificado"),
                "pending": list(block.get("pending", [])),
                "fields": {
                    key: _evidence_to_dict(value)
                    for key, value in fields.items()
                    if isinstance(value, FieldEvidence)
                },
            }
        )
    return {
        "process": record["process"],
        "status": record["status"],
        "pending": list(record.get("pending", [])),
        "blocks": blocks,
    }


def _record_from_checkpoint(payload: Mapping[str, object]) -> dict:
    blocks = []
    for block in payload.get("blocks", []):
        if not isinstance(block, Mapping):
            continue
        raw_fields = block.get("fields", {})
        blocks.append(
            {
                "interested": str(block.get("interested", "Não identificado")),
                "pending": [str(item) for item in block.get("pending", [])],
                "fields": {
                    key: _evidence_from_dict(value)
                    for key, value in raw_fields.items()
                    if isinstance(value, Mapping)
                },
            }
        )
    return {
        "process": str(payload.get("process", "")),
        "status": str(payload.get("status", "partial")),
        "pending": [str(item) for item in payload.get("pending", [])],
        "blocks": blocks,
    }


def _markdown_value(evidence: FieldEvidence) -> str:
    if evidence.status == "found" and evidence.value:
        return evidence.value
    if evidence.status == "conflict":
        return "CONFLITO — revisar fontes"
    if evidence.status == "ambiguous":
        return evidence.raw_value or "AMBÍGUO — revisar"
    return "—"


def _markdown_source(evidence: FieldEvidence) -> str:
    if evidence.status == "conflict":
        return "; ".join(item.citation or "fonte sem página" for item in evidence.candidates)
    return evidence.citation or "—"


def _display_status(status: object) -> str:
    return {"complete": "completo", "partial": "parcial"}.get(
        str(status), str(status)
    )


def render_batch_markdown(records: Sequence[Mapping[str, object]], run_id: str) -> str:
    lines = [
        "# Extração para Complementar Ato",
        "",
        f"Execução: `{run_id}`",
        "",
        "> Somente leitura. Os valores abaixo não foram enviados nem preenchidos no TCE.",
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"## Processo {record['process']}",
                "",
                f"Status: {_display_status(record.get('status', 'partial'))}",
                "",
            ]
        )
        for block in record.get("blocks", []):
            interested = block.get("interested", "Não identificado")
            fields = block.get("fields", {})
            lines.extend(
                [
                    f"### Interessado: {interested}",
                    "",
                    "| Campo | Valor para o formulário | Fonte |",
                    "|---|---|---|",
                ]
            )
            for key in FIELD_ORDER:
                evidence = fields.get(key, FieldEvidence(key, None, "missing"))
                lines.append(
                    f"| {FIELD_LABELS[key]} | {_markdown_value(evidence)} | {_markdown_source(evidence)} |"
                )
            pending = list(block.get("pending", []))
            pending.extend(
                FIELD_LABELS[key]
                for key in FIELD_ORDER
                if fields.get(key, FieldEvidence(key, None, "missing")).status != "found"
            )
            lines.extend(["", "### Pendências", ""])
            if pending:
                for item in dict.fromkeys(pending):
                    lines.append(f"- {item}.")
            else:
                lines.append("- Nenhuma.")
            lines.append("")
        if not record.get("blocks"):
            lines.extend(["### Pendências", "", "- Nenhuma extração disponível.", ""])
    return "\n".join(lines).rstrip() + "\n"


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(text)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _safe_document_entry(document: Mapping[str, object], kind: str | None, pages: int) -> dict:
    return {
        "event": str(document.get("event", "")),
        "date": str(document.get("date", "")),
        "title": str(document.get("title", "")),
        "file": Path(str(document.get("pdf_path", ""))).name,
        "classification": kind,
        "pages": pages,
    }


def _build_process_record(
    process: str,
    extractions: Sequence[Extraction],
    pending: Sequence[str],
) -> dict:
    grouped: dict[str, list[Extraction]] = {}
    names: dict[str, str] = {}
    for extraction in extractions:
        name = extraction.interested or "Não identificado"
        key = _fold(name) or "__nao_identificado__"
        grouped.setdefault(key, []).append(extraction)
        names.setdefault(key, name)

    if not grouped:
        grouped["__nao_identificado__"] = []
        names["__nao_identificado__"] = "Não identificado"

    effective_groups: dict[str, list[Extraction]] = {}
    for key, items in grouped.items():
        republications = [
            extraction
            for extraction in items
            if extraction.kind == "resolucao_administrativa"
            and extraction.is_republication
        ]
        effective_groups[key] = (
            [
                extraction
                for extraction in items
                if extraction.kind != "resolucao_administrativa"
                or extraction.is_republication
            ]
            if republications
            else items
        )

    effective_extractions = [
        extraction
        for items in effective_groups.values()
        for extraction in items
    ]
    resolution_fields = merge_extractions(
        extraction
        for extraction in effective_extractions
        if extraction.kind == "resolucao_administrativa"
    )
    resolution_dates = resolution_fields["data_publicacao_doe"]
    resolution_cargo = resolution_fields["cargo"]
    resolution_matricula = resolution_fields["matricula"]

    blocks = []
    for key, items in effective_groups.items():
        fields = merge_extractions(items)
        group_resolution_cargo = merge_extractions(
            extraction
            for extraction in items
            if extraction.kind == "resolucao_administrativa"
        )["cargo"]
        group_resolution_matricula = merge_extractions(
            extraction
            for extraction in items
            if extraction.kind == "resolucao_administrativa"
        )["matricula"]
        if group_resolution_cargo.status != "missing":
            fields["cargo"] = group_resolution_cargo
        elif resolution_cargo.status != "missing":
            fields["cargo"] = resolution_cargo
        if group_resolution_matricula.status != "missing":
            fields["matricula"] = group_resolution_matricula
        elif resolution_matricula.status != "missing":
            fields["matricula"] = resolution_matricula
        if fields["data_publicacao_doe"].status == "missing" and resolution_dates.status != "missing":
            fields["data_publicacao_doe"] = resolution_dates
        block_pending = list(pending)
        if names[key] == "Não identificado":
            block_pending.append("Interessado não identificado com segurança")
        blocks.append(
            {
                "interested": names[key],
                "fields": fields,
                "pending": block_pending,
            }
        )
    status = "complete"
    for block in blocks:
        if block["pending"] or any(
            block["fields"].get(key, FieldEvidence(key, None, "missing")).status != "found"
            for key in FIELD_ORDER
        ):
            status = "partial"
            break
    return {"process": process, "status": status, "pending": list(pending), "blocks": blocks}


def run_manifest(
    manifest_path: Path,
    output_path: Path,
    checkpoint_path: Path,
    *,
    run_id: str | None = None,
    resume: bool = True,
    tesseract: str = "tesseract",
    tessdata_dir: Path | None = None,
) -> dict[str, int]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    identifier = run_id or str(manifest.get("run_id") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    process_entries = manifest.get("processes", [])
    process_ids = [str(entry["process"]) for entry in process_entries]
    store = CheckpointStore(Path(checkpoint_path))
    existing = store._read()
    if not resume or existing.get("run_id") != identifier:
        store.initialize(process_ids, identifier)
        existing = store._read()
    else:
        for process in process_ids:
            if process not in existing.get("processes", {}):
                store.update_process(process, {"status": "pending"})
        existing = store._read()

    records: dict[str, dict] = {}
    completed = partial = 0
    for entry in process_entries:
        process = str(entry["process"])
        input_signature = process_input_signature(entry)
        prior = existing.get("processes", {}).get(process, {})
        if (
            resume
            and prior.get("status") in {"complete", "partial"}
            and prior.get("input_signature") == input_signature
            and isinstance(prior.get("result"), Mapping)
        ):
            record = _record_from_checkpoint(prior["result"])
            records[process] = record
            if record["status"] == "complete":
                completed += 1
            else:
                partial += 1
            continue

        extractions: list[Extraction] = []
        analyzed: list[dict] = []
        pending: list[str] = []
        documents = entry.get("documents", [])
        priority_seen = False
        for document in documents:
            pdf_path = Path(str(document.get("pdf_path", "")))
            if not pdf_path.exists():
                pending.append(f"PDF ausente para o Evento {document.get('event', '?')}")
                analyzed.append(_safe_document_entry(document, None, 0))
                continue
            pages = extract_pdf_pages(pdf_path, tesseract=tesseract, tessdata_dir=tessdata_dir)
            text = "\n".join(pages)
            kind = classify_document(str(document.get("title", "")), text)
            analyzed.append(_safe_document_entry(document, kind, len(pages)))
            if not kind:
                continue
            priority_seen = True
            extraction = extract_fields(
                pages,
                process=process,
                event=str(document.get("event", "")),
                document=str(document.get("title", "")),
                kind=kind,
            )
            extractions.append(extraction)

        if not priority_seen:
            pending.append("Documento prioritário não encontrado: RESOLUÇÃO ADMINISTRATIVA ou Guia Financeira/Taxação de Proventos")
        record = _build_process_record(process, extractions, pending)
        records[process] = record
        safe_record = _record_to_checkpoint(record)
        store.update_process(
            process,
            {
                "status": record["status"],
                "input_signature": input_signature,
                "event": analyzed[-1]["event"] if analyzed else None,
                "documents": analyzed,
                "pendencias": sorted(
                    set(record.get("pending", []))
                    | {
                        FIELD_LABELS[key]
                        for block in record["blocks"]
                        for key in FIELD_ORDER
                        if block["fields"].get(key, FieldEvidence(key, None, "missing")).status != "found"
                    }
                ),
                "result": safe_record,
            },
        )
        if record["status"] == "complete":
            completed += 1
        else:
            partial += 1
        ordered = [records[item] for item in process_ids if item in records]
        _write_atomic(Path(output_path), render_batch_markdown(ordered, identifier))

    ordered = [records[item] for item in process_ids if item in records]
    _write_atomic(Path(output_path), render_batch_markdown(ordered, identifier))
    return {"total": len(process_ids), "completed": completed, "partial": partial}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--tesseract", default="tesseract")
    parser.add_argument("--tessdata-dir", type=Path)
    args = parser.parse_args()
    summary = run_manifest(
        args.manifest,
        args.output,
        args.checkpoint,
        run_id=args.run_id,
        resume=not args.no_resume,
        tesseract=args.tesseract,
        tessdata_dir=args.tessdata_dir,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
