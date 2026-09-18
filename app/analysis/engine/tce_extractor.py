"""Local, conservative extraction helpers for TCE/RN Complementar Ato data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
import subprocess
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
import unicodedata
from typing import Iterable, Mapping, Sequence

from .evidence_geometry import locate_evidence, parse_ocr_tsv, read_native_page_words


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


def _replace_with_retry(source: Path, destination: Path, attempts: int = 8) -> None:
    """Replace a file atomically, tolerating short Windows/OneDrive locks."""
    for attempt in range(attempts):
        try:
            source.replace(destination)
            return
        except PermissionError:
            if attempt + 1 == attempts:
                source.unlink(missing_ok=True)
                raise
            time.sleep(min(0.05 * (2**attempt), 0.8))


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t:;-–—")


def _normalize_cargo(value: str) -> str:
    cargo = _clean(value)
    cargo = re.sub(r",\s*(?=PN\b)", " ", cargo, flags=re.IGNORECASE)
    cargo = re.sub(
        r"\bPN\s*[-–—�·]?\s*[\"“”']?"
        r"(VIII|VII|III|VI|IV|IX|II|V|X|I)[\"“”']?\b",
        lambda match: f"PN - {match.group(1).upper()}",
        cargo,
        flags=re.IGNORECASE,
    )
    return cargo


def _cargo_with_class_from_resolution(page_text: str) -> tuple[str, str] | None:
    anchor = re.search(r"\bno\s+cargo\s+de\b", page_text, re.IGNORECASE)
    if not anchor:
        return None
    class_marker = re.search(
        r"[,.]\s*classe\b", page_text[anchor.end() : anchor.end() + 360], re.IGNORECASE
    )
    if not class_marker:
        return None
    class_start = anchor.end() + class_marker.start()
    class_end = anchor.end() + class_marker.end()
    professional = re.compile(
        r"\b(?:PROF[A-ZÀ-Ý�]*|ANALISTA|AUXILIAR|T[ÉE]CNIC[OA]|"
        r"ESPECIALISTA|AGENTE|ASSISTENTE|M[ÉE]DIC[OA]|ENFERMEIR[OA])\b",
        re.IGNORECASE,
    )

    before_class = page_text[anchor.end() : class_start]
    starts = list(professional.finditer(before_class))
    if starts:
        cargo_raw = before_class[starts[-1].start() :]
    else:
        after_class = page_text[class_end : class_end + 360]
        start = professional.search(after_class)
        if not start:
            return None
        cargo_raw = after_class[start.start() :].splitlines()[0]

    cargo = _normalize_cargo(cargo_raw.strip(" \t\r\n,."))
    if not cargo:
        return None
    class_window = page_text[class_end : class_end + 360]
    direct = re.match(r"\s*[\"“”']?\s*([A-Z])\b", class_window, re.IGNORECASE)
    quoted = re.search(r"[\"“”']\s*([A-Z])\b", class_window, re.IGNORECASE)
    standalone = re.search(r"(?m)^\s*([A-J])\s*$", class_window, re.IGNORECASE)
    class_name = direct or quoted or standalone
    if not class_name:
        return None
    return cargo, class_name.group(1).upper()


def _cargo_scope(page_text: str, interested: str | None, kind: str | None) -> str:
    if kind != "resolucao_administrativa":
        return page_text
    anchors = list(re.finditer(r"\bno\s+cargo\s+de\b", page_text, re.IGNORECASE))
    if interested:
        name_pattern = r"\s+".join(re.escape(token) for token in interested.split())
        name = re.search(name_pattern, page_text, re.IGNORECASE)
        if name:
            return page_text[name.start() : name.start() + 900]
        if len(anchors) > 1:
            return ""
    elif len(anchors) > 1:
        return ""
    return page_text


def classify_document(title: str, text: str) -> str | None:
    folded_title = _fold(title)
    folded_text = _fold(text)
    resolution_pattern = r"resolu(?:cao|\W{1,3}o)\s+administrativa"

    title_is_resolution = re.search(resolution_pattern, folded_title) is not None
    text_starts_as_resolution = re.match(
        rf"\s*{resolution_pattern}", folded_text[:500]
    ) is not None
    text_is_resolution = (
        re.search(resolution_pattern, folded_text[:1500]) is not None
        and re.search(r"\bresolve\b", folded_text) is not None
    )
    if title_is_resolution or text_starts_as_resolution or text_is_resolution:
        return "resolucao_administrativa"

    title_is_guide = "guia financeira" in folded_title and (
        "taxacao" in folded_title
        or "proventos" in folded_title
        or "taxacao" in folded_text[:1500]
        or "proventos" in folded_text[:1500]
    )
    text_starts_as_guide = re.match(
        r"\s*guia financeira\W+(?:taxacao|proventos)", folded_text[:500]
    ) is not None
    text_has_calculation_guide = (
        "guia financeira" in folded_text[:1500]
        and (
            "planilha de calculo do provento" in folded_text[:1500]
            or "composicao da ultima remuneracao" in folded_text[:2500]
        )
    )
    text_has_long_guide = (
        "guia financeira" in folded_text[:1500]
        and ("taxacao" in folded_text[:1500] or "proventos" in folded_text[:1500])
        and (
            "remuneracao do servidor no cargo efetivo" in folded_text
            or "lista de remuneracoes" in folded_text
        )
    )
    text_is_guide = (
        "guia financeira" in folded_text[:1500]
        and ("taxacao" in folded_text[:1500] or "proventos" in folded_text[:1500])
        and "composicao da remuneracao" in folded_text[:2500]
    )
    if (
        title_is_guide
        or text_starts_as_guide
        or text_is_guide
        or text_has_calculation_guide
        or text_has_long_guide
    ):
        return "guia_financeira_taxacao"
    return None


def normalize_date(value: str) -> str | None:
    text = _clean(value)
    match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", text)
    if match:
        day, month, year = (int(part) for part in match.groups())
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{day:02d}/{month:02d}/{year:04d}"
        return None

    months = {
        "janeiro": 1,
        "fevereiro": 2,
        "marco": 3,
        "maro": 3,
        "abril": 4,
        "maio": 5,
        "junho": 6,
        "julho": 7,
        "agosto": 8,
        "setembro": 9,
        "outubro": 10,
        "novembro": 11,
        "dezembro": 12,
    }
    month_pattern = "|".join(months)
    folded_text = _fold(text).replace("�", "")
    match = re.search(
        rf"\b(\d{{1,2}})\s*,?\s+de\s+({month_pattern})\s+de\s+(\d{{4}})\b",
        folded_text,
    )
    if match:
        day, month_name, year = match.groups()
        return f"{int(day):02d}/{months[month_name]:02d}/{int(year):04d}"
    return None


@dataclass(frozen=True)
class FieldEvidence:
    key: str
    value: str | None
    status: str
    process: str | None = None
    event: str | None = None
    document: str | None = None
    page: int | None = None
    confidence: str = "high"
    raw_value: str | None = None
    candidates: tuple["FieldEvidence", ...] = ()
    quote: str | None = None
    rects: tuple[tuple[float, float, float, float], ...] = ()
    method: str | None = None

    @property
    def citation(self) -> str | None:
        if not self.process or not self.event or not self.page:
            return None
        return f"Processo {self.process} · Evento {self.event} · p. {self.page}"


@dataclass(frozen=True)
class Extraction:
    process: str
    event: str
    document: str
    fields: Mapping[str, FieldEvidence]
    interested: str | None = None
    kind: str | None = None
    is_republication: bool = False


def _empty_field(key: str) -> FieldEvidence:
    return FieldEvidence(key=key, value=None, status="missing")


def _attach_geometry(evidence: FieldEvidence, page_words: Mapping[str, object] | None) -> FieldEvidence:
    if page_words is None:
        return evidence
    words = page_words.get("words", [])
    if not isinstance(words, Sequence) or isinstance(words, (str, bytes)):
        return evidence
    quote = evidence.raw_value or evidence.value
    if not quote:
        return evidence
    coordinates = str(page_words.get("coordinates", "raw"))
    page_width = 1.0 if coordinates == "normalized" else float(page_words.get("width", 1) or 1)
    page_height = 1.0 if coordinates == "normalized" else float(page_words.get("height", 1) or 1)
    rects = locate_evidence(words, quote, page_width=page_width, page_height=page_height)
    return FieldEvidence(
        **{
            **evidence.__dict__,
            "quote": quote,
            "rects": tuple(tuple(rect) for rect in rects),
            "method": str(page_words.get("method", "native")),
        }
    )


def _normalize_matricula(value: str) -> str:
    """Collapse PDF layout whitespace inside a registration number."""
    return re.sub(r"\s+", "", _clean(value)).rstrip(".")


def _field_from_line(
    key: str,
    line: str,
    process: str,
    event: str,
    document: str,
    page: int,
) -> FieldEvidence | None:
    folded = _fold(line)
    label_patterns = {
        "modalidade": r"modalidade\s*(?:de\s*aposentadoria)?\s*[:=-]\s*(.+)$",
        "fundamento_legal": r"fundamento\s+legal\s*[:=-]\s*(.+)$",
        "data_publicacao_doe": (
            r"(?:data\s+de\s+)?publica[cç][aã]o\s+no\s+di[aá]rio\s+oficial\s+do\s+estado\s*[:=-]\s*(.+)$"
        ),
        "cargo": r"cargo\s*[:=-]\s*(.+)$",
        "matricula": r"matr[ií]cula\s*(?:n[ºo°.]*)?\s*[:=-]?\s*(.+)$",
        "data_nascimento": r"data\s+de\s+nascimento\s*[:=-]\s*(.+)$",
        "genero": r"g[eê]nero\s*[:=-]\s*(.+)$",
    }
    match = re.search(label_patterns[key], folded if key == "data_publicacao_doe" else line, re.IGNORECASE)
    if not match:
        return None

    raw_value = _clean(match.group(1))
    if key == "matricula":
        token = re.match(
            r"[A-Za-z0-9.]+(?:\s*[-/]\s*[A-Za-z0-9.]+)*",
            raw_value,
        )
        raw_value = _normalize_matricula(token.group(0)) if token else ""
    if not raw_value:
        return FieldEvidence(
            key=key,
            value=None,
            status="missing",
            process=process,
            event=event,
            document=document,
            page=page,
        )

    value = normalize_date(raw_value) if key in {"data_publicacao_doe", "data_nascimento"} else raw_value
    status = "found" if value else "ambiguous"
    return FieldEvidence(
        key=key,
        value=value,
        status=status,
        process=process,
        event=event,
        document=document,
        page=page,
        confidence="high" if status == "found" else "low",
        raw_value=raw_value,
    )


def _narrative_evidence(
    key: str,
    page_text: str,
    process: str,
    event: str,
    document: str,
    page: int,
) -> FieldEvidence | None:
    if key == "fundamento_legal":
        match = re.search(
            r"\b((?:nos\s+termos|com\s+fundamento)\s+(?:do|da|de)\s+.+?)"
            r"(?=,\s*com\s+efeitos\b|,\s*com\s+a\(s\)\s+seguinte|\.\s*$)",
            page_text,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            raw_value = _clean(match.group(1))
            if raw_value:
                return FieldEvidence(
                    key=key,
                    value=raw_value,
                    status="found",
                    process=process,
                    event=event,
                    document=document,
                    page=page,
                    confidence="high",
                    raw_value=raw_value,
                )
        return None

    if key == "data_publicacao_doe":
        heading = re.search(
            r"\bresolu(?:cao|\W{1,3}o)\s+administrativa.{0,180}?\bde\s+"
            r"(\d{1,2}\s+de\s+(?:janeiro|fevereiro|mar(?:co|\W{1,3}o)|abril|maio|junho|"
            r"julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+\d{4})\b",
            _fold(page_text[:2000]),
            re.IGNORECASE | re.DOTALL,
        )
        if heading:
            raw_value = _clean(heading.group(1))
            value = normalize_date(raw_value)
            if value:
                return FieldEvidence(
                    key=key,
                    value=value,
                    status="found",
                    process=process,
                    event=event,
                    document=document,
                    page=page,
                    confidence="high",
                    raw_value=raw_value,
                )

        return None

    if key == "cargo":
        complete = _cargo_with_class_from_resolution(page_text)
        if complete:
            cargo, class_name = complete
        else:
            without_class = re.search(
                r"\bno\s+cargo\s+de\s+(.{2,120}?)(?=,\s*matr[ií]cula\b)",
                page_text,
                re.IGNORECASE | re.DOTALL,
            )
            if not without_class:
                return None
            cargo = _normalize_cargo(without_class.group(1))
            class_name = ""
        if (
            not cargo
            or cargo.lstrip().startswith((",", ".", '"', "'"))
            or re.search(r"\bclasse\b", cargo, re.IGNORECASE)
        ):
            return None
        raw_value = f'{cargo}, Classe "{class_name}"' if class_name else cargo
        return FieldEvidence(
            key=key,
            value=raw_value,
            status="found",
            process=process,
            event=event,
            document=document,
            page=page,
            confidence="high",
            raw_value=raw_value,
        )

    patterns = {
        "modalidade": r"\b(?:concede|conceder)\s+(aposentadoria\b[^,.\n]+)",
        "matricula": (
            r"\bmatr[ií]cula\s*(?:n[ºo°.]*)?\s*[:=-]?\s*"
            r"([A-Za-z0-9.]+(?:\s*[-/]\s*[A-Za-z0-9.]+)*)"
        ),
    }
    pattern = patterns.get(key)
    if not pattern:
        return None
    match = re.search(pattern, page_text, re.IGNORECASE)
    if not match:
        return None
    raw_value = (
        _normalize_matricula(match.group(1))
        if key == "matricula"
        else _clean(match.group(1))
    )
    if not raw_value:
        return None
    return FieldEvidence(
        key=key,
        value=raw_value,
        status="found",
        process=process,
        event=event,
        document=document,
        page=page,
        confidence="high",
        raw_value=raw_value,
    )


def _guide_evidence(
    key: str,
    page_text: str,
    process: str,
    event: str,
    document: str,
    page: int,
) -> FieldEvidence | None:
    """Read values whose PDF text order follows the guide's visual columns."""

    folded = _fold(page_text)
    has_guide_heading = "guia financeira" in folded and (
        "taxacao" in folded
        or "proventos" in folded
        or "planilha de calculo do provento" in folded
        or "composicao da ultima remuneracao" in folded
    )
    if not has_guide_heading:
        return None

    if key == "data_nascimento":
        label = re.search(r"data\s+de\s+nascimento\s*:", page_text, re.IGNORECASE)
        if not label:
            return None
        candidate = re.search(
            r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b", page_text[label.end() :]
        )
        if not candidate:
            return None
        raw_value = candidate.group(0)
        value = normalize_date(raw_value)
        if not value:
            return None
        return FieldEvidence(
            key=key,
            value=value,
            status="found",
            process=process,
            event=event,
            document=document,
            page=page,
            confidence="high",
            raw_value=raw_value,
        )

    if key == "cargo":
        lines = page_text.splitlines()
        for index, line in enumerate(lines):
            if not re.search(r"\bcargo\s+efetivo\b", _fold(line), re.IGNORECASE):
                continue
            for candidate in lines[index + 1 :]:
                raw_value = _clean(candidate)
                if not raw_value:
                    continue
                if _fold(raw_value) in {"valor", "composicao", "fundamentacao"}:
                    break
                return FieldEvidence(
                    key=key,
                    value=raw_value,
                    status="found",
                    process=process,
                    event=event,
                    document=document,
                    page=page,
                    confidence="high",
                    raw_value=raw_value,
                )
        return None

    return None


def _find_interested(text: str) -> str | None:
    labeled = re.search(r"\b(?:interessad[oa]|beneficiári[ao]|nome)\s*[:=-]\s*([^\n]+)", text, re.IGNORECASE)
    if labeled:
        return _clean(labeled.group(1))
    narrative_pattern = (
        r"\ba\s+([A-ZÀ-Ý�][A-ZÀ-Ý� .'\-\r\n]{3,}?),\s+"
        r"no\s+cargo\s+de\b"
    )
    for narrative in re.finditer(narrative_pattern, text):
        candidate = _clean(narrative.group(1))
        if len(re.findall(r"[A-ZÀ-Ý�]{2,}", candidate)) >= 2:
            return candidate
    guide_pattern = (
        r"^\s*[\d./-]{3,}\s+-\s+([A-ZÀ-Ý�][A-ZÀ-Ý� .'-]{3,})\s*$"
    )
    for guide in re.finditer(guide_pattern, text, re.MULTILINE):
        candidate = _clean(guide.group(1))
        if len(re.findall(r"[A-ZÀ-Ý�]{2,}", candidate)) >= 2:
            return candidate
    return None


def extract_interested(extraction: Extraction) -> str | None:
    return extraction.interested


def extract_fields(
    pages: Sequence[str], process: str, event: str, document: str, kind: str | None = None,
    page_words: Sequence[Mapping[str, object]] | None = None,
) -> Extraction:
    fields = {key: _empty_field(key) for key in FIELD_ORDER}
    full_text = "\n".join(pages)
    interested = _find_interested(full_text)
    for page_number, page_text in enumerate(pages, start=1):
        for line in page_text.splitlines():
            for key in FIELD_ORDER:
                # Matrículas can be split around '-' and '/' by PDF column layout.
                # Extract them from the complete page so a truncated line value does
                # not block the canonical number found immediately below it.
                if key in {"matricula", "data_publicacao_doe"}:
                    continue
                if fields[key].status != "missing":
                    continue
                found = _field_from_line(key, line, process, event, document, page_number)
                if found:
                    fields[key] = _attach_geometry(found, page_words[page_number - 1] if page_words and page_number <= len(page_words) else None)
        for key in ("modalidade", "cargo", "matricula"):
            if fields[key].status == "missing":
                narrative_text = (
                    _cargo_scope(page_text, interested, kind) if key == "cargo" else page_text
                )
                if not narrative_text:
                    continue
                found = _narrative_evidence(
                    key, narrative_text, process, event, document, page_number
                )
                if found:
                    fields[key] = _attach_geometry(found, page_words[page_number - 1] if page_words and page_number <= len(page_words) else None)
        for key in ("data_nascimento", "cargo"):
            if fields[key].status == "missing":
                found = _guide_evidence(
                    key, page_text, process, event, document, page_number
                )
                if found:
                    fields[key] = _attach_geometry(found, page_words[page_number - 1] if page_words and page_number <= len(page_words) else None)
        for key in ("fundamento_legal", "data_publicacao_doe"):
            if fields[key].status == "missing":
                found = _narrative_evidence(
                    key, page_text, process, event, document, page_number
                )
                if found:
                    fields[key] = _attach_geometry(found, page_words[page_number - 1] if page_words and page_number <= len(page_words) else None)
    return Extraction(
        process=process,
        event=event,
        document=document,
        fields=fields,
        interested=interested,
        kind=kind,
        is_republication=bool(
            re.search(r"\brepublicad[ao]\s+por\s+incorre", _fold(full_text))
        ),
    )


def _value_key(value: str | None) -> str:
    return _fold(_clean(value or ""))


def merge_extractions(extractions: Iterable[Extraction]) -> dict[str, FieldEvidence]:
    by_field: dict[str, list[FieldEvidence]] = {key: [] for key in FIELD_ORDER}
    for extraction in extractions:
        for key in FIELD_ORDER:
            evidence = extraction.fields.get(key)
            if evidence and evidence.status in {"found", "ambiguous"} and evidence.value is not None:
                by_field[key].append(evidence)

    merged: dict[str, FieldEvidence] = {}
    for key, candidates in by_field.items():
        if not candidates:
            merged[key] = _empty_field(key)
            continue
        distinct: list[FieldEvidence] = []
        seen: set[str] = set()
        for candidate in candidates:
            value_key = _value_key(candidate.value)
            if value_key not in seen:
                distinct.append(candidate)
                seen.add(value_key)
        if len(distinct) == 1:
            merged[key] = distinct[0]
            continue
        first = distinct[0]
        merged[key] = FieldEvidence(
            key=key,
            value=None,
            status="conflict",
            process=first.process,
            event=first.event,
            document=first.document,
            page=first.page,
            confidence="low",
            candidates=tuple(distinct),
        )
    return merged


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
        return "; ".join(
            f"{candidate.citation or 'fonte sem página'}"
            for candidate in evidence.candidates
        )
    return evidence.citation or "—"


def render_markdown(records: Sequence[Mapping[str, object]], run_id: str) -> str:
    lines = [
        "# Extração para Complementar Ato",
        "",
        f"Execução: `{run_id}`",
        "",
        "> Somente leitura. Os valores abaixo não foram enviados nem preenchidos no TCE.",
        "",
    ]
    for record in records:
        process = str(record["process"])
        status = str(record.get("status", "partial"))
        interested = str(record.get("interested", "Não identificado"))
        fields = record.get("fields", {})
        lines.extend(
            [
                f"## Processo {process}",
                "",
                f"Status: {status}",
                "",
                f"### Interessado: {interested}",
                "",
                "| Campo | Valor para o formulário | Fonte |",
                "|---|---|---|",
            ]
        )
        for key in FIELD_ORDER:
            evidence = fields.get(key, _empty_field(key))
            lines.append(
                f"| {FIELD_LABELS[key]} | {_markdown_value(evidence)} | {_markdown_source(evidence)} |"
            )
        pending = [
            FIELD_LABELS[key]
            for key in FIELD_ORDER
            if fields.get(key, _empty_field(key)).status != "found"
        ]
        lines.extend(["", "### Pendências", ""])
        if pending:
            lines.extend(f"- Campo sem evidência segura: {field_name}." for field_name in pending)
        else:
            lines.append("- Nenhuma.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


class CheckpointStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def initialize(self, processes: Sequence[str], run_id: str) -> None:
        payload = {
            "version": 1,
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "processes": {
                process: {
                    "status": "pending",
                    "event": None,
                    "documents": [],
                    "pendencias": [],
                }
                for process in processes
            },
        }
        self._write(payload)

    def update_process(self, process: str, update: Mapping[str, object]) -> None:
        payload = self._read()
        processes = payload.setdefault("processes", {})
        current = dict(processes.get(process, {}))
        current.update(update)
        processes[process] = current
        self._write(payload)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "processes": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, payload: Mapping[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        _replace_with_retry(temporary_path, self.path)


def extract_pdf_pages(
    pdf_path: Path,
    tesseract: str = "tesseract",
    tessdata_dir: Path | None = None,
    *,
    return_geometry: bool = False,
) -> list[str] | tuple[list[str], list[dict]]:
    """Extract text, optionally retaining geometry from the same OCR pass.

    The default return value remains the historical ``list[str]``. When
    ``return_geometry`` is true, scanned pages are sent to Tesseract once as
    TSV; the returned text and word boxes come from that same response.
    """
    try:
        import fitz
    except ImportError as error:  # pragma: no cover - environment guard
        raise RuntimeError("PyMuPDF (fitz) não está disponível") from error

    document = fitz.open(pdf_path)
    pages: list[str] = []
    geometry: list[dict] = []
    for page_number, page in enumerate(document):
        native = page.get_text("text").strip()
        if native:
            pages.append(native)
            native_geometry = read_native_page_words(page)
            geometry.append({
                **native_geometry,
                "page": page_number,
                "text": native,
                "method": "native",
            })
            continue

        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        command = [tesseract, "stdin", "stdout", "-l", "por+eng", "--psm", "6"]
        if tessdata_dir:
            command.extend(["--tessdata-dir", str(tessdata_dir)])
        command.extend(["-c", "tessedit_create_tsv=1"])
        result = subprocess.run(
            command,
            input=pixmap.tobytes("png"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            pages.append("")
            geometry.append({
                "page": page_number,
                "width": float(page.rect.width),
                "height": float(page.rect.height),
                "rotation": int(page.rotation),
                "coordinates": "normalized",
                "text": "",
                "words": [],
                "method": "none",
            })
        else:
            raw_tsv = result.stdout
            if isinstance(raw_tsv, bytes):
                raw_tsv = raw_tsv.decode("utf-8", errors="replace")
            words, text = parse_ocr_tsv(
                str(raw_tsv),
                float(pixmap.width),
                float(pixmap.height),
            )
            pages.append(text.strip())
            geometry.append({
                "page": page_number,
                "width": float(page.rect.width),
                "height": float(page.rect.height),
                "rotation": int(page.rotation),
                "coordinates": "normalized",
                "text": text.strip(),
                "words": words,
                "method": "ocr" if words else "none",
            })
    document.close()
    return (pages, geometry) if return_geometry else pages
