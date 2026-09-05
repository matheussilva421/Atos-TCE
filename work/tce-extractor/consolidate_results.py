"""Consolidate per-process collection checkpoints after download retries."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Mapping


def _atomic_text(path: Path, text: str) -> None:
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


def _atomic_json(path: Path, payload: object) -> None:
    _atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _document_key(document: Mapping[str, object]) -> str:
    card_id = str(document.get("card_id", ""))
    if card_id:
        return card_id
    return f"{document.get('event', '')}|{document.get('date', '')}"


def _load_documents(directory: Path) -> dict[str, dict[str, dict[str, object]]]:
    processes: dict[str, dict[str, dict[str, object]]] = {}
    if not directory.exists():
        return processes
    for checkpoint in sorted(directory.glob("*.checkpoint.json")):
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        for process_entry in payload.get("processes", []):
            process = str(process_entry.get("process", ""))
            documents = processes.setdefault(process, {})
            for document in process_entry.get("documents", []):
                safe_document = {
                    key: value for key, value in document.items() if key != "url"
                }
                documents[_document_key(safe_document)] = safe_document
    return processes


def consolidate_results(
    *,
    process_map_path: Path,
    primary_dir: Path,
    retry_dir: Path,
    pdf_root: Path,
    checkpoint_out: Path,
    manifest_out: Path,
    summary_out: Path,
) -> dict[str, int]:
    process_map = json.loads(Path(process_map_path).read_text(encoding="utf-8"))
    primary = _load_documents(Path(primary_dir))
    retries = _load_documents(Path(retry_dir))
    pdf_root = Path(pdf_root).resolve()

    for process, documents in retries.items():
        primary.setdefault(process, {}).update(documents)

    counts = {
        "processes": 0,
        "processes_with_eligible_documents": 0,
        "documents_probed": 0,
        "targets_saved": 0,
        "resolutions": 0,
        "financial_guides": 0,
        "pending_no_native_text": 0,
        "unrelated": 0,
        "errors": 0,
        "pdf_signature_failures": 0,
    }
    checkpoint_processes: list[dict[str, object]] = []
    manifest_processes: list[dict[str, object]] = []
    missing_types: list[tuple[str, list[str]]] = []
    no_eligible: list[str] = []
    expected_pdfs: set[Path] = set()

    for process_entry in process_map.get("processes", []):
        process = str(process_entry["process"])
        documents = list(primary.get(process, {}).values())
        documents.sort(key=lambda item: (int(str(item.get("event", "0"))), _document_key(item)))
        targets: list[dict[str, object]] = []
        found_kinds: set[str] = set()

        if documents:
            counts["processes_with_eligible_documents"] += 1
        else:
            no_eligible.append(process)

        for document in documents:
            status = str(document.get("status", ""))
            if status != "skipped_event":
                counts["documents_probed"] += 1
            if status == "target":
                kind = str(document.get("kind", ""))
                filename = str(document.get("file", ""))
                pdf_path = pdf_root / process.replace("/", "-") / filename
                expected_pdfs.add(pdf_path)
                signature_ok = pdf_path.is_file() and pdf_path.read_bytes()[:5] == b"%PDF-"
                if not signature_ok:
                    counts["pdf_signature_failures"] += 1
                counts["targets_saved"] += 1
                counts["resolutions" if kind == "resolucao_administrativa" else "financial_guides"] += 1
                found_kinds.add(kind)
                targets.append(
                    {
                        "event": str(document.get("event", "")),
                        "date": str(document.get("date", "")),
                        "title": str(document.get("title", "")),
                        "card_id": str(document.get("card_id", "")),
                        "kind": kind,
                        "pdf_path": str(pdf_path),
                        "pdf_signature_valid": signature_ok,
                    }
                )
            elif status == "pending_no_native_text":
                counts["pending_no_native_text"] += 1
            elif status == "unrelated":
                counts["unrelated"] += 1
            elif status == "error":
                counts["errors"] += 1

        required = {
            "resolucao_administrativa": "RESOLUÇÃO ADMINISTRATIVA",
            "guia_financeira_taxacao": "Guia Financeira/Taxação de Proventos",
        }
        absent = [label for kind, label in required.items() if kind not in found_kinds]
        if absent:
            missing_types.append((process, absent))

        status = "partial" if any(
            str(document.get("status", "")) in {"error", "pending_no_native_text"}
            for document in documents
        ) else "complete"
        checkpoint_processes.append(
            {
                "process": process,
                "id": process_entry.get("id"),
                "status": status,
                "documents": documents,
                "missing_target_types": absent,
            }
        )
        manifest_processes.append({"process": process, "documents": targets})
        counts["processes"] += 1

    physical_pdfs = set(pdf_root.rglob("*.pdf")) if pdf_root.exists() else set()
    counts["orphan_pdf_files"] = len(physical_pdfs - expected_pdfs)
    counts["missing_pdf_files"] = len(expected_pdfs - physical_pdfs)

    now = datetime.now(timezone.utc).isoformat()
    _atomic_json(
        checkpoint_out,
        {
            "version": 2,
            "updated_at": now,
            "mode": "target-identification-native-text-no-ocr",
            "processes": checkpoint_processes,
            "summary": counts,
        },
    )
    _atomic_json(
        manifest_out,
        {
            "version": 2,
            "collected_at": now,
            "source": "authenticated-browser-read-only-native-pdf-text-no-ocr",
            "pdf_root": str(pdf_root),
            "processes": manifest_processes,
            "summary": counts,
        },
    )

    lines = [
        "# Coleta seletiva de PDFs do TCE/RN",
        "",
        "Status: concluída em modo somente leitura, sem OCR e sem extração de campos.",
        "",
        f"- Processos enumerados: {counts['processes']}",
        f"- Processos com documentos elegíveis após o Evento 1: {counts['processes_with_eligible_documents']}",
        f"- PDFs candidatos verificados por texto nativo: {counts['documents_probed']}",
        f"- PDFs-alvo salvos: {counts['targets_saved']}",
        f"- Resoluções administrativas: {counts['resolutions']}",
        f"- Guias financeiras/taxações: {counts['financial_guides']}",
        f"- PDFs sem texto nativo pendentes de OCR: {counts['pending_no_native_text']}",
        f"- Erros após retries: {counts['errors']}",
        f"- Falhas de assinatura PDF: {counts['pdf_signature_failures']}",
        f"- Arquivos órfãos na pasta de alvos: {counts['orphan_pdf_files']}",
        "",
        "## Processos sem documento elegível após o Evento 1",
        "",
    ]
    lines.extend(f"- {process}" for process in no_eligible)
    lines.extend(["", "## Tipos-alvo não encontrados", ""])
    if missing_types:
        lines.extend(
            f"- {process}: {', '.join(types)}" for process, types in missing_types
        )
    else:
        lines.append("- Nenhum.")
    lines.extend(
        [
            "",
            "> O OCR e a extração das informações para Complementar Ato não foram executados.",
            "",
        ]
    )
    _atomic_text(summary_out, "\n".join(lines))
    return counts


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-map", type=Path, required=True)
    parser.add_argument("--primary-dir", type=Path, required=True)
    parser.add_argument("--retry-dir", type=Path, required=True)
    parser.add_argument("--pdf-root", type=Path, required=True)
    parser.add_argument("--checkpoint-out", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args(argv)
    counts = consolidate_results(
        process_map_path=args.process_map,
        primary_dir=args.primary_dir,
        retry_dir=args.retry_dir,
        pdf_root=args.pdf_root,
        checkpoint_out=args.checkpoint_out,
        manifest_out=args.manifest_out,
        summary_out=args.summary_out,
    )
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
