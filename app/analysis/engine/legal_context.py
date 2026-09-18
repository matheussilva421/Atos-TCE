"""Build and publish the local legal-evidence context sidecar."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile


SCHEMA_VERSION = 1
LEGAL_CONTEXT_VERSION = "legal-context-v4"
EXTRACTION_VERSION = LEGAL_CONTEXT_VERSION
_RESOLUTION_CLASSIFICATION = "resolucao_administrativa"
_FAILED_PAGE_STATUSES = frozenset(
    {"failed", "error", "erro", "missing", "unavailable", "pendente_ocr"}
)
_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_NAME_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_NUMERIC_IDENTIFIER_RE = re.compile(
    r"\b(?:matricula|registro|inscricao|identificador|id)\b"
    r"\s*(?:n(?:o|º)?\s*)?[:#-]?\s*"
    r"(?P<value>\d(?:[\d\s./-]*\d)?)",
    re.IGNORECASE,
)


def _normalise_interested(value: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_marks.casefold()).strip()


def _normalised_tokens(value: object) -> tuple[str, ...]:
    return tuple(_NAME_TOKEN_RE.findall(_normalise_interested(value)))


def _contains_token_sequence(text: object, target: object) -> bool:
    target_tokens = _normalised_tokens(target)
    page_tokens = _normalised_tokens(text)
    if not target_tokens or len(target_tokens) > len(page_tokens):
        return False
    width = len(target_tokens)
    return any(
        page_tokens[index : index + width] == target_tokens
        for index in range(len(page_tokens) - width + 1)
    )


def _normalise_identifier(value: object) -> str:
    return "".join(_normalised_tokens(value))


def _contains_identifier(text: object, target: object) -> bool:
    normalized_target = _normalise_identifier(target)
    target_digits = "".join(re.findall(r"\d+", str(target)))
    if not target_digits or normalized_target != target_digits:
        return _contains_token_sequence(text, target)
    normalized_text = _normalise_interested(text)
    for match in _NUMERIC_IDENTIFIER_RE.finditer(normalized_text):
        value_digits = "".join(re.findall(r"\d+", match.group("value")))
        if value_digits == target_digits:
            return True
    return False


def _safe_document_id(value: object) -> str:
    text = str(value or "").strip()
    if not text or _URL_RE.search(text) or "\n" in text or "\r" in text:
        return ""
    components = text.replace("\\", "/").split("/")
    if ".." in components:
        return ""
    return components[-1].strip() if components[-1].strip() else ""


def _document_id(document: Mapping[str, object]) -> str:
    for key in ("document_id", "id", "card_id", "title", "relative_path", "pdf_path"):
        value = _safe_document_id(document.get(key))
        if value:
            return value
    return ""


def _first_text(mapping: Mapping[str, object], keys: Sequence[str]) -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _declared_page_count(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _process_entries(value: object) -> list[tuple[str, Mapping[str, object]]]:
    if isinstance(value, list):
        result = []
        for entry in value:
            if not isinstance(entry, Mapping):
                continue
            process_key = _first_text(entry, ("process", "key", "id"))
            result.append((process_key, entry))
        return result
    if isinstance(value, Mapping):
        return [
            (
                _first_text(entry, ("process", "key", "id")) or str(process_key),
                entry,
            )
            for process_key, entry in value.items()
            if isinstance(entry, Mapping)
        ]
    return []


def _documents(entry: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw_documents = entry.get("documents", [])
    return [item for item in raw_documents if isinstance(item, Mapping)] if isinstance(raw_documents, list) else []


def _manifest_sources(manifest: Mapping[str, object]) -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    for process_key, process_entry in _process_entries(manifest.get("processes")):
        for document in _documents(process_entry):
            classification = str(
                document.get(
                    "classification",
                    document.get("kind", document.get("document_type", "")),
                )
            ).casefold()
            if classification != _RESOLUTION_CLASSIFICATION or document.get("automatic_source") is False:
                continue
            raw_identifiers = [
                document.get(key)
                for key in (
                    "document_id",
                    "id",
                    "card_id",
                    "title",
                    "relative_path",
                    "pdf_path",
                    "geometry_cache_key",
                    "pdf_sha256",
                    "sha256",
                )
            ]
            identifiers = {str(value).strip() for value in raw_identifiers if value is not None and str(value).strip()}
            safe_identifiers = {_safe_document_id(value) for value in raw_identifiers}
            safe_identifiers.discard("")
            aliases = identifiers | safe_identifiers
            event_id = _first_text(document, ("event_id", "event"))
            if event_id:
                aliases.add(event_id)
            source_hash = _first_text(document, ("pdf_sha256", "sha256"))
            page_count = _declared_page_count(document.get("page_count"))
            sources.append(
                {
                    "process_key": process_key,
                    "document_id": _document_id(document),
                    "event_id": event_id,
                    "pdf_sha256": source_hash,
                    "page_count": page_count,
                    "page_count_valid": page_count is not None,
                    "geometry_status": _first_text(document, ("geometry_status",)),
                    "aliases": aliases,
                }
            )
    return sources


def _checkpoint_blocks(checkpoint: Mapping[str, object]) -> list[tuple[str, Mapping[str, object]]]:
    blocks: list[tuple[str, Mapping[str, object]]] = []
    for process_key, process_entry in _process_entries(checkpoint.get("processes")):
        result = process_entry.get("result", process_entry)
        if not isinstance(result, Mapping):
            continue
        raw_blocks = result.get("blocks", [])
        if not isinstance(raw_blocks, list):
            continue
        blocks.extend(
            (process_key, block)
            for block in raw_blocks
            if isinstance(block, Mapping)
        )
    return blocks


def _block_identifiers(block: Mapping[str, object]) -> frozenset[str]:
    values: list[object] = []
    for key in (
        "interested_identifier",
        "interested_id",
        "identifier",
        "matricula",
        "registration",
    ):
        if block.get(key) is not None:
            values.append(block[key])
    fields = block.get("fields")
    if isinstance(fields, Mapping):
        for key in ("matricula", "identifier"):
            field = fields.get(key)
            if isinstance(field, Mapping):
                for value_key in ("form_value", "source_value", "value", "raw_value"):
                    if field.get(value_key) is not None:
                        values.append(field[value_key])
    return frozenset(
        normalized
        for normalized in (_normalise_identifier(value) for value in values)
        if normalized
    )


def _block_references(block: Mapping[str, object]) -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            document = _first_text(value, ("document_id", "document"))
            event = _first_text(value, ("event_id", "event"))
            if document or event:
                references.append((document, event))
            for key, child in value.items():
                if key in {"candidates", "fields", "resolution", "citation"}:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(block)
    return references


def _source_matches_reference(source: Mapping[str, object], reference: tuple[str, str]) -> bool:
    document, event = reference
    aliases = source["aliases"]
    document_match = not document or document in aliases or _safe_document_id(document) in aliases
    event_match = not event or event == source["event_id"]
    return document_match and event_match


def _source_identity(source: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(source["document_id"]),
        str(source["event_id"]),
        str(source["pdf_sha256"]),
    )


def _payload_identity(payload: object) -> tuple[str, str, str]:
    if not isinstance(payload, Mapping):
        return "", "", ""
    return (
        _first_text(payload, ("document_id", "document", "id", "card_id")),
        _first_text(payload, ("event_id", "event")),
        _first_text(payload, ("pdf_sha256", "sha256")),
    )


def _payload_identity_matches(
    payload: object, source: Mapping[str, object]
) -> bool:
    document_id, event_id, pdf_sha256 = _payload_identity(payload)
    if document_id:
        aliases = source["aliases"]
        if document_id not in aliases and _safe_document_id(document_id) not in aliases:
            return False
    if event_id and event_id != source["event_id"]:
        return False
    if pdf_sha256 and pdf_sha256 != source["pdf_sha256"]:
        return False
    return True


def _lookup_page_payload(
    page_texts: Mapping[str, object],
    source: Mapping[str, object],
    candidate_sources: Sequence[Mapping[str, object]] | None = None,
) -> tuple[object | None, str]:
    containers: list[Mapping[str, object]] = [page_texts]
    for key in ("documents", "entries"):
        nested = page_texts.get(key)
        if isinstance(nested, Mapping):
            containers.append(nested)
    process_payload = page_texts.get(source["process_key"])
    if isinstance(process_payload, Mapping):
        containers.append(process_payload)
    candidates = list(candidate_sources or [source])
    ambiguous_alias = False
    for container in containers:
        for key, payload in container.items():
            key_text = str(key)
            if key_text not in source["aliases"]:
                continue
            alias_matches = [
                candidate for candidate in candidates if key_text in candidate["aliases"]
            ]
            payload_identity = _payload_identity(payload)
            if not _payload_identity_matches(payload, source):
                if len(alias_matches) > 1 and not all(payload_identity):
                    ambiguous_alias = True
                continue
            if all(payload_identity):
                return payload, "matched"
            if len(alias_matches) == 1 and _source_identity(alias_matches[0]) == _source_identity(source):
                return payload, "matched"
            ambiguous_alias = True
    return None, "ambiguous_alias" if ambiguous_alias else "missing"


def _page_items(payload: object) -> tuple[list[object], str, bool]:
    if isinstance(payload, Mapping):
        declared_hash = _first_text(payload, ("pdf_sha256", "sha256"))
        raw_pages = payload.get("pages", payload.get("page_texts"))
        if raw_pages is None and "text" in payload:
            raw_pages = [payload.get("text")]
        if raw_pages is None:
            numeric_keys = [key for key in payload if str(key).isdigit()]
            if numeric_keys:
                raw_pages = [payload[key] for key in sorted(numeric_keys, key=lambda key: int(str(key)))]
        if isinstance(raw_pages, Mapping):
            raw_pages = [raw_pages[key] for key in sorted(raw_pages, key=lambda key: int(str(key)) if str(key).isdigit() else str(key))]
        if not isinstance(raw_pages, Sequence) or isinstance(raw_pages, (str, bytes, bytearray)):
            return [], declared_hash, True
        failed_document = str(payload.get("status", "")).casefold() in _FAILED_PAGE_STATUSES
        return list(raw_pages), declared_hash, failed_document
    if isinstance(payload, str):
        return [payload], "", False
    if isinstance(payload, Sequence) and not isinstance(payload, (bytes, bytearray)):
        return list(payload), "", False
    return [], "", True


def _snapshot(
    page_texts: Mapping[str, object],
    source: Mapping[str, object],
    candidate_sources: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    payload, lookup_reason = _lookup_page_payload(
        page_texts, source, candidate_sources=candidate_sources
    )
    if payload is None:
        return {
            "state": "incomplete" if lookup_reason == "ambiguous_alias" else "missing",
            "reason": (
                "source_alias_ambiguous"
                if lookup_reason == "ambiguous_alias"
                else "source_evidence_missing"
            ),
            "pages": [],
            "page_count_observed": 0,
            "operative_text": "",
        }
    raw_pages, declared_hash, failed_document = _page_items(payload)
    source_hash = str(source["pdf_sha256"] or declared_hash)
    if (
        not source_hash
        or not str(source["document_id"])
        or not str(source["event_id"])
        or source.get("page_count_valid") is not True
        or (declared_hash and source_hash != declared_hash)
    ):
        return {
            "state": "incomplete",
            "reason": "source_identity_incomplete",
            "pages": [],
            "page_count_observed": 0,
            "operative_text": "",
        }

    expected_page_count = source.get("page_count")
    observed_page_count = len(raw_pages)
    page_count_mismatch = expected_page_count != observed_page_count
    if isinstance(expected_page_count, int) and expected_page_count > len(raw_pages):
        raw_pages.extend([None] * (expected_page_count - len(raw_pages)))
    pages: list[dict[str, object]] = []
    failed = failed_document
    for page_number, raw_page in enumerate(raw_pages, start=1):
        page_failed = False
        if isinstance(raw_page, Mapping):
            text_value = raw_page.get("text")
            page_status = str(raw_page.get("status", raw_page.get("extraction_status", ""))).casefold()
            page_failed = page_status in _FAILED_PAGE_STATUSES or text_value is None
            text = "" if text_value is None else str(text_value)
        else:
            page_failed = raw_page is None
            text = "" if raw_page is None else str(raw_page)
        if not text.strip():
            page_failed = True
        failed = failed or page_failed
        pages.append(
            {
                "text": text,
                "citation": {
                    "document_id": str(source["document_id"]),
                    "event_id": str(source["event_id"]),
                    "page": page_number,
                    "pdf_sha256": source_hash,
                },
            }
        )
    operative_text = _operative_text([str(page["text"]) for page in pages])
    return {
        "state": "incomplete" if failed or page_count_mismatch or not pages else "complete",
        "pages": pages,
        "page_count_observed": observed_page_count,
        "operative_text": operative_text,
    }


_OPERATIVE_MARKER_RE = re.compile(
    r"(?im)^\s*resolve\b\s*:?(?:[ \t]+.*)?$"
)


def _operative_text(pages: list[str]) -> str:
    full_text = "\n".join(pages)
    markers = list(_OPERATIVE_MARKER_RE.finditer(full_text))
    marker = markers[-1] if markers else None
    return full_text[marker.start() :].strip() if marker else ""


def _snapshot_matches_identity(
    snapshot: Mapping[str, object],
    interested_normalized: str,
    identifiers: frozenset[str],
) -> bool:
    if not interested_normalized or interested_normalized == _normalise_interested("Não identificado"):
        return False
    for page in snapshot.get("pages", []):
        if not isinstance(page, Mapping):
            continue
        citation = page.get("citation")
        page_number = citation.get("page") if isinstance(citation, Mapping) else None
        if (
            not isinstance(page_number, int)
            or isinstance(page_number, bool)
            or page_number <= 0
        ):
            continue
        text = page.get("text", "")
        if not _contains_token_sequence(text, interested_normalized):
            continue
        if identifiers and not any(
            _contains_identifier(text, identifier) for identifier in identifiers
        ):
            continue
        return True
    return False


def _identity_match_count(
    interested_normalized: str,
    identifiers: frozenset[str],
    snapshots: Sequence[Mapping[str, object]],
) -> int:
    return sum(
        _snapshot_matches_identity(snapshot, interested_normalized, identifiers)
        for snapshot in snapshots
    )


def _source_evidence(
    source: Mapping[str, object], snapshot: Mapping[str, object]
) -> dict[str, object]:
    return {
        "document_id": str(source["document_id"]),
        "event_id": str(source["event_id"]),
        "pdf_sha256": str(source["pdf_sha256"]),
        "page_count": source.get("page_count"),
        "page_count_observed": snapshot.get("page_count_observed", 0),
        "state": str(snapshot["state"]),
        "reason": str(snapshot.get("reason", "")),
        "geometry_status": str(source.get("geometry_status", "")),
    }


def _source_status_reasons(
    sources: Sequence[Mapping[str, object]],
    snapshots: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    reasons: list[dict[str, object]] = []
    for source, snapshot in zip(sources, snapshots):
        state = str(snapshot["state"])
        if state not in {"missing", "incomplete"}:
            continue
        snapshot_reason = str(snapshot.get("reason", ""))
        reasons.append(
            {
                "code": (
                    snapshot_reason
                    if snapshot_reason
                    in {"source_alias_ambiguous", "source_identity_incomplete"}
                    else (
                        "source_evidence_missing"
                        if state == "missing"
                        else "source_evidence_incomplete"
                    )
                ),
                "document_id": str(source["document_id"]),
                "event_id": str(source["event_id"]),
                "state": state,
            }
        )
    return reasons


def _select_sources(
    sources: list[dict[str, object]],
    process_key: str,
    block: Mapping[str, object],
    page_texts: Mapping[str, object],
) -> list[dict[str, object]]:
    process_sources = [source for source in sources if source["process_key"] == process_key]
    references = _block_references(block)
    if references:
        candidates = [
            source
            for source in process_sources
            if any(_source_matches_reference(source, reference) for reference in references)
        ]
    else:
        candidates = process_sources
    interested = _normalise_interested(
        block.get("interested", block.get("interested_normalized", ""))
    )
    identifiers = _block_identifiers(block)
    if len(candidates) > 1 and interested and interested != _normalise_interested("Não identificado"):
        matched = [
            source
            for source in candidates
            if _snapshot_matches_identity(
                _snapshot(
                    page_texts,
                    source,
                    candidate_sources=process_sources,
                ),
                interested,
                identifiers,
            )
        ]
        if matched:
            return matched
    return candidates


def _record(
    process_key: str,
    block: Mapping[str, object],
    sources: list[dict[str, object]],
    page_texts: Mapping[str, object],
    dataset_sha256: str,
    evidence_sources: Sequence[dict[str, object]] | None = None,
) -> dict[str, object]:
    interested_normalized = _normalise_interested(
        block.get("interested", block.get("interested_normalized", "Não identificado"))
    ) or _normalise_interested("Não identificado")
    identifiers = _block_identifiers(block)
    evidence_sources = list(evidence_sources) if evidence_sources is not None else sources
    candidate_sources = evidence_sources or sources
    snapshots = [
        _snapshot(page_texts, source, candidate_sources=candidate_sources)
        for source in sources
    ]
    evidence_snapshots = [
        _snapshot(page_texts, source, candidate_sources=candidate_sources)
        for source in evidence_sources
    ]
    status_reasons = _source_status_reasons(evidence_sources, evidence_snapshots)
    source_evidence = [
        _source_evidence(source, snapshot)
        for source, snapshot in zip(evidence_sources, evidence_snapshots)
    ]
    geometry_statuses = {
        str(source.get("geometry_status", ""))
        for source in evidence_sources
        if str(source.get("geometry_status", ""))
    }
    identity_match_count = _identity_match_count(
        interested_normalized,
        identifiers,
        snapshots,
    )
    pages = [page for snapshot in snapshots for page in snapshot["pages"]]
    operative_values = [
        str(snapshot["operative_text"])
        for snapshot in snapshots
        if str(snapshot["operative_text"])
    ]
    distinct_operative = {_normalise_interested(value) for value in operative_values}
    if not sources:
        status = "missing"
        pages = []
        operative_text = ""
        status_reasons.append({"code": "resolution_source_missing"})
    elif len(distinct_operative) > 1 or identity_match_count > 1:
        status = "conflict"
        operative_text = "\n\n".join(operative_values)
    else:
        operative_text = operative_values[0] if operative_values else ""
        status = "complete"
        if (
            not operative_text
            or any(snapshot["state"] != "complete" for snapshot in snapshots)
            or any(
                snapshot["state"] != "complete"
                for snapshot in evidence_snapshots
            )
            or not all(str(page["text"]).strip() for page in pages)
            or identity_match_count != 1
        ):
            status = "incomplete"
    record = {
        "schema_version": SCHEMA_VERSION,
        "process_key": process_key,
        "interested_normalized": interested_normalized,
        "dataset_sha256": dataset_sha256,
        "resolution_status": status,
        "pages": pages,
        "operative_text": operative_text,
        "extraction_version": EXTRACTION_VERSION,
        "source_evidence": source_evidence,
        "status_reasons": status_reasons,
    }
    if "unavailable" in geometry_statuses:
        record["geometry_status"] = "unavailable"
    elif "available" in geometry_statuses:
        record["geometry_status"] = "available"
    return record


def build_legal_contexts(
    manifest: dict,
    checkpoint: dict,
    page_texts: dict,
    dataset_sha256: str,
) -> dict:
    sources = _manifest_sources(manifest)
    records = []
    for process_key, block in _checkpoint_blocks(checkpoint):
        process_sources = [
            source for source in sources if source["process_key"] == process_key
        ]
        records.append(
            _record(
                process_key,
                block,
                _select_sources(sources, process_key, block, page_texts),
                page_texts,
                dataset_sha256,
                evidence_sources=process_sources,
            )
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_sha256": dataset_sha256,
        "records": records,
    }


def build_legal_context_record(
    manifest: Mapping[str, object],
    checkpoint: Mapping[str, object],
    page_texts: Mapping[str, object],
    dataset_sha256: str,
    process_key: str,
    interested_normalized: str,
) -> dict[str, object] | None:
    """Rebuild one identity's context from already persisted evidence only."""
    wanted = _normalise_interested(interested_normalized)
    if not wanted:
        return None
    block = next(
        (
            candidate
            for key, candidate in _checkpoint_blocks(checkpoint)
            if key == process_key
            and _normalise_interested(
                candidate.get("interested", candidate.get("interested_normalized", ""))
            )
            == wanted
        ),
        None,
    )
    if block is None:
        return None
    sources = _manifest_sources(manifest)
    process_sources = [source for source in sources if source["process_key"] == process_key]
    return _record(
        process_key,
        block,
        _select_sources(sources, process_key, block, page_texts),
        page_texts,
        dataset_sha256,
        evidence_sources=process_sources,
    )


class LegalContextUpsertError(ValueError):
    """Raised when the sidecar being updated is not compatible with the build."""


def upsert_legal_context_record(
    path: Path,
    record: Mapping[str, object],
    dataset_sha256: str,
) -> None:
    """Replace a single identity record without touching the other records."""
    target = Path(path)
    payload: object = None
    if target.is_file():
        try:
            payload = json.loads(target.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise LegalContextUpsertError("invalid sidecar") from error
    elif target.exists():
        raise LegalContextUpsertError("invalid sidecar")
    if payload is None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "dataset_sha256": dataset_sha256,
            "records": [],
        }
    if not isinstance(payload, Mapping) or payload.get("schema_version") != SCHEMA_VERSION:
        raise LegalContextUpsertError("unsupported sidecar schema")
    if payload.get("dataset_sha256") != dataset_sha256:
        raise LegalContextUpsertError("sidecar belongs to another dataset")
    records = payload.get("records")
    if not isinstance(records, list):
        raise LegalContextUpsertError("invalid sidecar records")
    if record.get("dataset_sha256") != dataset_sha256:
        raise LegalContextUpsertError("record belongs to another dataset")
    key = (record.get("process_key"), record.get("interested_normalized"))
    kept = [
        entry
        for entry in records
        if not (
            isinstance(entry, Mapping)
            and (entry.get("process_key"), entry.get("interested_normalized")) == key
        )
    ]
    kept.append(dict(record))
    write_legal_contexts(
        target,
        {
            "schema_version": SCHEMA_VERSION,
            "dataset_sha256": dataset_sha256,
            "records": kept,
        },
    )


def _read_mapping(path: Path) -> Mapping[str, object] | None:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _page_texts_from_caches(*paths: Path) -> dict[str, object]:
    """Reuse page text already persisted by the analysis pipeline."""
    page_texts: dict[str, object] = {}
    for path in paths:
        payload = _read_mapping(path)
        if payload is None:
            continue
        entries = payload.get("entries")
        if not isinstance(entries, Mapping):
            continue
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
                page_texts[str(key)] = entry
                page_texts[str(key).split(":", 1)[0]] = entry
    return page_texts


def rebuild_legal_context_from_root(
    root: Path,
    dataset_sha256: str,
    process_key: str,
    interested_normalized: str,
) -> dict[str, object] | None:
    """Rebuild one identity from local evidence; never triggers collection."""
    archive = Path(root)
    manifest = _read_mapping(archive / "pdfs-alvo-manifest.json")
    checkpoint = _read_mapping(archive / "checkpoint-extracao.json")
    if manifest is None or checkpoint is None:
        return None
    page_texts = _page_texts_from_caches(
        archive / "cache-ocr.json",
        archive / "cache-ocr-geometria.json",
    )
    return build_legal_context_record(
        manifest,
        checkpoint,
        page_texts,
        dataset_sha256,
        process_key,
        interested_normalized,
    )


def write_legal_contexts(path: Path, contexts: dict) -> None:
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
            temporary_path = Path(temporary.name)
            json.dump(contexts, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
