"""Traceable PDF word geometry and a portable visual-evidence sidecar."""

from __future__ import annotations

import hashlib
import math
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


MIN_OCR_CONFIDENCE = 50.0


def _fold(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def _token(value: object) -> str:
    return re.sub(r"^[^\w]+|[^\w./-]+$", "", _fold(value), flags=re.UNICODE)


def _normalise_rect(rect: Sequence[object], page_width: float, page_height: float) -> list[float] | None:
    if (
        len(rect) != 4
        or not math.isfinite(page_width)
        or not math.isfinite(page_height)
        or page_width <= 0
        or page_height <= 0
    ):
        return None
    try:
        x0, y0, x1, y1 = (float(value) for value in rect)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x0, y0, x1, y1)):
        return None
    if x1 < x0 or y1 < y0:
        return None
    if x0 < 0 or y0 < 0 or x1 > page_width or y1 > page_height:
        return None
    return [
        max(0.0, min(1.0, x0 / page_width)),
        max(0.0, min(1.0, y0 / page_height)),
        max(0.0, min(1.0, x1 / page_width)),
        max(0.0, min(1.0, y1 / page_height)),
    ]


def _display_rect(
    rect: Sequence[object], *, width: float, height: float, rotation: int
) -> list[float] | None:
    """Map a crop-box-relative PDF rect into the displayed page coordinates."""
    if len(rect) != 4 or width <= 0 or height <= 0:
        return None
    try:
        x0, y0, x1, y1 = (float(value) for value in rect)
    except (TypeError, ValueError):
        return None
    if x1 < x0 or y1 < y0:
        return None
    angle = int(rotation) % 360
    if angle == 0:
        return [x0, y0, x1, y1]
    if angle == 90:
        return [height - y1, x0, height - y0, x1]
    if angle == 180:
        return [width - x1, height - y1, width - x0, height - y0]
    if angle == 270:
        return [y0, width - x1, y1, width - x0]
    return [x0, y0, x1, y1]


def locate_evidence(
    words: Sequence[Mapping[str, object]],
    quote: str,
    *,
    page_width: float = 1.0,
    page_height: float = 1.0,
) -> list[list[float]]:
    """Return one bounding rectangle only when ``quote`` occurs once.

    Multiple equal matches are intentionally treated as unresolved instead of
    guessing which occurrence the field came from.
    """
    target = [_token(part) for part in re.findall(r"\S+", quote or "")]
    target = [part for part in target if part]
    if not target:
        return []
    matches: list[list[float]] = []
    normalised_words = [_token(item.get("text")) for item in words]
    for start in range(len(normalised_words) - len(target) + 1):
        if normalised_words[start : start + len(target)] != target:
            continue
        rects = [item.get("rect") for item in words[start : start + len(target)]]
        valid = []
        for rect in rects:
            if not isinstance(rect, Sequence) or isinstance(rect, (str, bytes)):
                valid = []
                break
            confidence = words[start + len(valid)].get("confidence")
            if confidence is not None:
                try:
                    confidence_value = float(confidence)
                except (TypeError, ValueError):
                    valid = []
                    break
                if (
                    not math.isfinite(confidence_value)
                    or confidence_value < MIN_OCR_CONFIDENCE
                ):
                    valid = []
                    break
            normalised = _normalise_rect(rect, page_width, page_height)
            if normalised is None:
                valid = []
                break
            valid.append(normalised)
        if not valid:
            continue
        matches.append([
            min(rect[0] for rect in valid),
            min(rect[1] for rect in valid),
            max(rect[2] for rect in valid),
            max(rect[3] for rect in valid),
        ])
    return matches if len(matches) == 1 else []


def parse_ocr_tsv(text: str, page_width: float, page_height: float) -> tuple[list[dict], str]:
    lines = text.splitlines()
    if not lines:
        return [], ""
    words: list[dict] = []
    for line in lines[1:]:
        columns = line.split("\t")
        if len(columns) < 12 or not columns[11].strip():
            continue
        try:
            left, top, width, height = (float(columns[index]) for index in (6, 7, 8, 9))
            confidence = float(columns[10])
        except ValueError:
            continue
        rect = [left, top, left + width, top + height]
        normalised = _normalise_rect(rect, page_width, page_height)
        if normalised is None:
            continue
        words.append({"text": columns[11], "rect": normalised, "confidence": confidence, "method": "ocr"})
    return words, " ".join(str(item["text"]) for item in words)


# Kept as a private compatibility alias for the local OCR adapter.
_parse_tsv = parse_ocr_tsv


def _ocr_page(pdf_path: Path, page, tesseract: str, tessdata: str | None) -> tuple[list[dict], str]:
    with tempfile.TemporaryDirectory(prefix="tce-ocr-") as temporary:
        image_path = Path(temporary) / "page.png"
        page.get_pixmap(matrix=__import__("pymupdf").Matrix(2, 2), alpha=False).save(str(image_path))
        command = [str(tesseract), str(image_path), "stdout", "--psm", "6", "tsv"]
        if tessdata:
            command.extend(["--tessdata-dir", str(tessdata)])
        completed = subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode != 0:
            return [], ""
        return parse_ocr_tsv(completed.stdout, float(page.rect.width * 2), float(page.rect.height * 2))


def read_page_words(pdf, page_number: int, *, tesseract, tessdata) -> dict:
    """Read native words, falling back to one TSV OCR pass when needed."""
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - dependency is provided by runtime
        import fitz as pymupdf
    path = Path(pdf)
    document = pymupdf.open(str(path))
    try:
        page = document.load_page(page_number)
        width, height = float(page.rect.width), float(page.rect.height)
        crop_width, crop_height = float(page.cropbox.width), float(page.cropbox.height)
        rotation = int(page.rotation) % 360
        native = []
        for item in page.get_text("words"):
            if len(item) < 5 or not str(item[4]).strip():
                continue
            display_rect = _display_rect(
                item[:4],
                width=crop_width,
                height=crop_height,
                rotation=rotation,
            )
            rect = _normalise_rect(display_rect or [], width, height)
            if rect is not None:
                native.append({"text": str(item[4]), "rect": rect, "method": "native"})
        text = page.get_text("text")
        method = "native"
        words = native
        if not words and tesseract:
            words, text = _ocr_page(path, page, str(tesseract), str(tessdata) if tessdata else None)
            method = "ocr" if words else "none"
        return {
            "page": page_number,
            "width": width,
            "height": height,
            "rotation": rotation,
            "coordinates": "normalized",
            "text": text,
            "words": words,
            "method": method,
        }
    finally:
        document.close()


def _document_id(document: Mapping[str, object]) -> str:
    process_key = str(document.get("process_key", ""))
    event_id = str(document.get("event_id", document.get("event", "")))
    source_id = str(document.get("document_id", document.get("source_document_id", "")))
    pdf_sha256 = str(document.get("pdf_sha256", document.get("sha256", "")))
    return hashlib.sha256(f"{process_key}|{event_id}|{source_id}|{pdf_sha256}".encode()).hexdigest()


def _relative_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("relative_path ausente")
    normalised = value.replace("\\", "/")
    parsed = PurePosixPath(normalised)
    if parsed.is_absolute() or ".." in parsed.parts or ":" in parsed.parts[0]:
        raise ValueError("relative_path inseguro")
    return str(parsed)


def build_visual_evidence(records: Sequence[Mapping[str, object]], documents: Sequence[Mapping[str, object]]) -> dict:
    """Build the sidecar without absolute paths or ambiguous field guesses."""
    document_entries: dict[str, dict] = {}
    lookup: dict[tuple[str, str, str], str] = {}
    for source in documents:
        document_id = _document_id(source)
        entry = {
            "document_id": document_id,
            "process_key": str(source.get("process_key", "")),
            "event_id": str(source.get("event_id", source.get("event", ""))),
            "source_document_id": str(source.get("document_id", source.get("source_document_id", ""))),
            "sha256": str(source.get("pdf_sha256", source.get("sha256", ""))),
            "relative_path": _relative_path(source.get("relative_path", source.get("path"))),
            "page_count": int(source.get("page_count", 0) or 0),
        }
        document_entries[document_id] = entry
        for label in (str(source.get("title", "")), Path(entry["relative_path"]).name, entry["source_document_id"]):
            if label:
                lookup[(entry["process_key"], entry["event_id"], _fold(label))] = document_id

    record_entries: dict[str, dict] = {}
    for record in records:
        record_id = str(record.get("record_id", ""))
        fields = record.get("fields", {})
        if not record_id or not isinstance(fields, Mapping):
            continue
        visual_fields: dict[str, dict] = {}
        for key, field in fields.items():
            if not isinstance(field, Mapping):
                continue
            event = str(field.get("event", ""))
            source_label = _fold(field.get("document", ""))
            document_id = field.get("document_id")
            if not isinstance(document_id, str) or document_id not in document_entries:
                document_id = lookup.get((str(record.get("process_key", "")), event, source_label))
            visual_fields[str(key)] = {
                "document_id": document_id,
                "page": field.get("page"),
                "quote": field.get("quote", field.get("raw_value")),
                "rects": field.get("rects", []),
                "method": field.get("method", "native"),
                "status": field.get("status", "missing"),
            }
        record_entries[record_id] = visual_fields
    return {"schema_version": 1, "documents": document_entries, "records": record_entries}
