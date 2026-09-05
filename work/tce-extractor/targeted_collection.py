"""Persist only the two TCE/RN target documents, without OCR or field extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import Future, ThreadPoolExecutor
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Callable, Mapping
from urllib.request import Request, urlopen

from tce_extractor import classify_document


@dataclass(frozen=True)
class TargetIdentification:
    status: str
    kind: str | None = None
    native_text_chars: int = 0
    metadata_title: str = ""


def _event_number(value: object) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def _native_pdf_text(pdf_bytes: bytes) -> tuple[str, str]:
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("resposta não possui assinatura PDF")
    try:
        import pymupdf as fitz
    except ImportError:  # pragma: no cover - compatibility with older installs
        import fitz

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        metadata_title = str((document.metadata or {}).get("title") or "").strip()
        text = "\n".join(page.get_text("text") for page in document)
    finally:
        document.close()
    return text, metadata_title


def identify_target_document(
    *, event: object, title: str, pdf_bytes: bytes
) -> TargetIdentification:
    number = _event_number(event)
    if number is None or number <= 1:
        return TargetIdentification(status="skipped_event")

    native_text, metadata_title = _native_pdf_text(pdf_bytes)
    kind = classify_document(f"{title}\n{metadata_title}", native_text)
    if kind:
        return TargetIdentification(
            status="target",
            kind=kind,
            native_text_chars=len(native_text.strip()),
            metadata_title=metadata_title,
        )
    if not native_text.strip():
        return TargetIdentification(
            status="pending_no_native_text",
            metadata_title=metadata_title,
        )
    return TargetIdentification(
        status="unrelated",
        native_text_chars=len(native_text.strip()),
        metadata_title=metadata_title,
    )


def download_url(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "TCE-target-collector/1.0"})
    with urlopen(request, timeout=60) as response:
        return response.read()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        json.dump(payload, temporary, ensure_ascii=False, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(payload)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _target_path(
    output_dir: Path, process: str, event: int, kind: str, ordinal: int
) -> Path:
    process_key = process.replace("/", "-")
    suffix = "" if ordinal == 1 else f"--{ordinal}"
    return output_dir / process_key / f"evento-{event:04d}-{kind}{suffix}.pdf"


def _download_and_identify(
    document: Mapping[str, object], downloader: Callable[[str], bytes]
) -> tuple[bytes, TargetIdentification]:
    pdf_bytes = downloader(str(document.get("url", "")))
    identified = identify_target_document(
        event=document.get("event"),
        title=str(document.get("title", "")),
        pdf_bytes=pdf_bytes,
    )
    return pdf_bytes, identified


def collect_target_documents(
    manifest: Mapping[str, object],
    *,
    output_dir: Path,
    checkpoint_path: Path,
    target_manifest_path: Path,
    downloader: Callable[[str], bytes] = download_url,
) -> dict[str, int]:
    output_dir = Path(output_dir)
    checkpoint_path = Path(checkpoint_path)
    target_manifest_path = Path(target_manifest_path)
    process_results: list[dict[str, object]] = []
    target_processes: list[dict[str, object]] = []
    counts = {
        "processes": 0,
        "documents_probed": 0,
        "targets_saved": 0,
        "pending_no_native_text": 0,
        "unrelated": 0,
        "errors": 0,
    }
    started_at = datetime.now(timezone.utc).isoformat()

    for process_entry in manifest.get("processes", []):
        process = str(process_entry.get("process", ""))
        records: list[dict[str, object]] = []
        targets: list[dict[str, object]] = []
        ordinals: dict[tuple[int, str], int] = {}

        documents = list(process_entry.get("documents", []))
        futures: dict[int, Future[tuple[bytes, TargetIdentification]]] = {}
        worker_count = min(8, max(1, len(documents)))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for index, document in enumerate(documents):
                event = _event_number(document.get("event"))
                if event is not None and event > 1:
                    futures[index] = executor.submit(
                        _download_and_identify, document, downloader
                    )

            for index, document in enumerate(documents):
                event = _event_number(document.get("event"))
                safe_record = {
                    "event": str(document.get("event", "")),
                    "date": str(document.get("date", "")),
                    "title": str(document.get("title", "")),
                    "card_id": str(document.get("card_id", "")),
                }
                if event is None or event <= 1:
                    records.append({**safe_record, "status": "skipped_event"})
                    continue

                counts["documents_probed"] += 1
                try:
                    pdf_bytes, identified = futures[index].result()
                except Exception as error:
                    counts["errors"] += 1
                    records.append(
                        {**safe_record, "status": "error", "reason": str(error)}
                    )
                    continue

                record = {
                    **safe_record,
                    "status": identified.status,
                    "kind": identified.kind,
                    "native_text_chars": identified.native_text_chars,
                    "metadata_title": identified.metadata_title,
                }
                if identified.status == "target" and identified.kind:
                    key = (event, identified.kind)
                    ordinals[key] = ordinals.get(key, 0) + 1
                    destination = _target_path(
                        output_dir, process, event, identified.kind, ordinals[key]
                    )
                    _atomic_bytes(destination, pdf_bytes)
                    target = {
                        "event": str(event),
                        "date": safe_record["date"],
                        "title": safe_record["title"],
                        "card_id": safe_record["card_id"],
                        "kind": identified.kind,
                        "pdf_path": str(destination),
                    }
                    targets.append(target)
                    record["file"] = destination.name
                    counts["targets_saved"] += 1
                elif identified.status == "pending_no_native_text":
                    counts["pending_no_native_text"] += 1
                else:
                    counts["unrelated"] += 1
                records.append(record)

        status = "partial" if any(
            item["status"] in {"error", "pending_no_native_text"} for item in records
        ) else "complete"
        process_results.append(
            {"process": process, "status": status, "documents": records}
        )
        target_processes.append({"process": process, "documents": targets})
        counts["processes"] += 1
        _atomic_json(
            checkpoint_path,
            {
                "version": 1,
                "started_at": started_at,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "mode": "target-identification-native-text-no-ocr",
                "processes": process_results,
                "summary": counts,
            },
        )

    _atomic_json(
        target_manifest_path,
        {
            "version": 1,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "source": "target-identification-native-text-no-ocr",
            "processes": target_processes,
        },
    )
    return counts


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--target-manifest", type=Path, required=True)
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    summary = collect_target_documents(
        manifest,
        output_dir=args.output_dir,
        checkpoint_path=args.checkpoint,
        target_manifest_path=args.target_manifest,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
