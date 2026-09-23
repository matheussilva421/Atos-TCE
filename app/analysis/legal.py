"""Python owner of the legal foundation rules (``legal-foundation-v3``).

Behavioural port, not a redesign, of the proven extension chain: normalizer.js,
legal-reference-parser-v2.js, the parser and decision parts of
legal-foundation.js, catalog-option-signature.js, retirement-legal-profile.js
and portal-legal-crosswalk.js. The parity test runs both implementations over
the same fixtures and refuses any difference, so a rule that looks odd stays
odd until a fixture proves the change was intended.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping, Sequence

RULES_VERSION = "legal-foundation-v3"

ROMAN_VALUES: dict[str, int] = {
    "i": 1,
    "v": 5,
    "x": 10,
    "l": 50,
    "c": 100,
    "d": 500,
    "m": 1000,
}

ROMAN_DIGITS: tuple[tuple[int, str], ...] = (
    (1000, "m"),
    (900, "cm"),
    (500, "d"),
    (400, "cd"),
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
)

ROMAN_TOKEN = re.compile(r"^[ivxlcdm]+$")


def as_text(value: Any) -> str:
    """``String(value)`` with JavaScript's null/undefined collapse to empty."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def strip_marks(value: str) -> str:
    """Drop every Unicode mark character, matching JavaScript's escape for M."""

    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        char for char in decomposed if not unicodedata.category(char).startswith("M")
    )


_NON_LEGAL_SEPARATOR = re.compile(r"[^\w/]+", re.UNICODE)


def to_fixed(value: float, digits: int = 2) -> str:
    """``Number.prototype.toFixed`` for the positive scores used here."""

    quantum = Decimal(1).scaleb(-digits)
    return str(Decimal(repr(float(value))).quantize(quantum, rounding=ROUND_HALF_UP))


def js_round(value: float) -> int:
    """``Math.round``: half away from zero for negatives, half up for positives."""

    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


def js_number(value: Any) -> str:
    """``String(number)`` as JavaScript renders it (no trailing ``.0``)."""

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    number = float(value)
    return str(int(number)) if number.is_integer() else repr(number)


def roman_to_arabic(token: str) -> str | None:
    """Canonical Roman numeral to decimal string, else ``None``."""

    if not ROMAN_TOKEN.match(token):
        return None
    total = 0
    for index, char in enumerate(token):
        current = ROMAN_VALUES[char]
        following = ROMAN_VALUES.get(token[index + 1], 0) if index + 1 < len(token) else 0
        total += -current if current < following else current
    if total < 1 or total > 3999:
        return None
    remainder = total
    canonical = ""
    for value, digits in ROMAN_DIGITS:
        while remainder >= value:
            canonical += digits
            remainder -= value
    return str(total) if canonical == token else None


def _canonicalize_tokens(tokens: Sequence[str]) -> list[str]:
    canonical: list[str] = []
    for index, token in enumerate(tokens):
        previous = tokens[index - 1] if index >= 1 else None
        before_previous = tokens[index - 2] if index >= 2 else None
        roman = roman_to_arabic(token)
        if roman is not None and (
            len(token) > 1
            or previous in {"inciso", "incisos", "a"}
            or before_previous in {"inciso", "incisos"}
        ):
            canonical.append(roman)
            continue
        canonical.append(token)

    result: list[str] = []
    seen_incisos_by_article: dict[str, set[str]] = {}
    current_article = "without-article"
    index = 0
    while index < len(canonical):
        token = canonical[index]
        following = canonical[index + 1] if index + 1 < len(canonical) else ""
        if token == "artigo" and re.fullmatch(r"\d+", following or ""):
            current_article = following
        if token in {"inciso", "incisos"} and re.fullmatch(r"\d+", following or ""):
            seen = seen_incisos_by_article.setdefault(current_article, set())
            cursor = index + 1
            while cursor < len(canonical):
                number = canonical[cursor]
                if not re.fullmatch(r"\d+", number):
                    if number in {"e", "and"}:
                        cursor += 1
                        continue
                    break
                if number not in seen:
                    result.extend(["inciso", number])
                    seen.add(number)
                cursor += 1
            index = cursor
            continue
        result.append(token)
        index += 1
    return result


def normalize_legal_text(value: Any) -> str:
    """Comparison-only legal-text signature; never a display value."""

    text = strip_marks(as_text(value)).lower()
    text = re.sub(r"(\d+)\s*[ºª°o]\s*[-–]\s*([a-z])(?=\s|[^\w]|$)", r"\1 article suffix \2", text)
    text = re.sub("§", " paragrafo ", text)
    text = re.sub(r"\barts\s*\.\s*", " artigos ", text)
    text = re.sub(r"\bart\s*\.\s*", " artigo ", text)
    text = re.sub(r"\bart\b", " artigo ", text)
    text = re.sub(r"\bpar\s*\.\s*", " paragrafo ", text)
    text = re.sub(r"\binc\s*\.\s*", " inciso ", text)
    text = re.sub(r"\bn\s*(?:\.\s*)?[º°o]\s*", " numero ", text)
    text = re.sub(r"(\d+)\s*[ºª°o]\s*[-–]\s*([a-z])(?=\s|[^\w]|$)", r"\1\2", text)
    text = re.sub(r"(\d+)\s*[-–]\s*([a-z])(?=\s|[^\w]|$)", r"\1\2", text)
    text = re.sub(r"(\d+)\s*[ºª°o](?=\s|[^\w]|$)", r"\1", text)
    text = re.sub(r"(\d+)[oa](?=\s|[^\w]|$)", r"\1", text)
    text = re.sub(r"\baposentacao\b", " aposentadoria ", text)
    text = re.sub(r"\bece\b", " emenda constitucional estadual ", text)
    text = re.sub(r"\bec\b", " emenda constitucional ", text)
    text = re.sub(r"\bcf\b", " constituicao federal ", text)
    text = re.sub(r"\bce\b", " constituicao estadual ", text)
    text = re.sub(r"\bc\s*/\s*c\b", " combinado com ", text)
    text = re.sub(r"\blce?\b", " lei complementar ", text)
    text = re.sub(r"\bincisos\b", " incisos ", text)
    text = re.sub(r"\bparagrafos\b", " paragrafos ", text)
    text = _NON_LEGAL_SEPARATOR.sub(" ", text).strip()
    if not text:
        return ""
    joined = " ".join(_canonicalize_tokens(text.split()))
    return re.sub(r"\b(\d+)\s+article\s+suffix\s+([a-z])\b", r"\1\2", joined)


DIPLOMA_PATTERN = re.compile(
    r"\b(emenda\s+constitucional\s+estadual|emenda\s+constitucional|lei\s+complementar\s+estadual|"
    r"lei\s+complementar(?:\s+nacional)?|constituicao\s+federal|constituicao\s+estadual|ece|ec|lce|lc|cf|ce|lei)\b",
    re.IGNORECASE,
)
ARTICLE_PATTERN_V2 = re.compile(
    r"\bart(?:igo|igos)?s?\.?\s*(\d+)\s*(?:º|ª|o)?\s*(?:[-–]\s*([a-z]))?", re.IGNORECASE
)
PARAGRAPH_PATTERN = re.compile(
    r"§{1,2}\s*(\d+|unico)(?:º|ª|o)?(?:\s*(?:e|,|a)\s*(\d+|unico)(?:º|ª|o)?)*", re.IGNORECASE
)
INCISO_PATTERN = re.compile(
    r"\bincisos?\s+(.+?)(?=§|\balineas?\b|\bitens?\b|\bart(?:igo|igos)?\b|\b(?:da|de|do)\b|$)",
    re.IGNORECASE,
)
ALINEA_PATTERN = re.compile(
    r"\balineas?\s+(.+?)(?=§|\bincisos?\b|\bitens?\b|\bart(?:igo|igos)?\b|\b(?:da|de|do)\b|$)",
    re.IGNORECASE,
)
ITEM_PATTERN = re.compile(
    r"\bitens?\s+(.+?)(?=§|\bincisos?\b|\balineas?\b|\bart(?:igo|igos)?\b|\b(?:da|de|do)\b|$)",
    re.IGNORECASE,
)


def normalize_source(value: Any) -> str:
    """Normalizer used by the v2 parser (distinct from normalize_legal_text)."""

    text = strip_marks(as_text(value))
    text = text.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text)


def normalize_legal_year(value: Any) -> str | None:
    text = as_text(value).strip()
    if not re.fullmatch(r"\d{2,4}", text):
        return None
    if len(text) == 4:
        return text
    year = int(text)
    return str(1900 + year) if year >= 50 else str(2000 + year)


def _roman_value_simple(value: Any) -> str | None:
    token = as_text(value).lower()
    if not re.fullmatch(r"[ivxlcdm]+", token):
        return None
    total = 0
    for index, char in enumerate(token):
        current = ROMAN_VALUES[char]
        following = ROMAN_VALUES.get(token[index + 1], 0) if index + 1 < len(token) else 0
        total += -current if current < following else current
    return str(total) if total > 0 else None


def _parse_ordinal_list(value: Any) -> list[str]:
    text = as_text(value).lower()
    tokens = re.findall(r"[ivxlcdm]+|\d+", text)
    numbers: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        current = token if re.fullmatch(r"\d+", token) else _roman_value_simple(token)
        if current is None:
            index += 1
            continue
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        if following is not None and any(
            f"{token} {word} {following}" in text for word in ("a", "até", "ate")
        ):
            end = following if re.fullmatch(r"\d+", following) else _roman_value_simple(following)
            if end is not None:
                first, last = int(current), int(end)
                step = 1 if first <= last else -1
                for item in range(first, last + step, step):
                    if str(item) not in numbers:
                        numbers.append(str(item))
                index += 2
                continue
        if current not in numbers:
            numbers.append(current)
        index += 1
    return numbers


def _diploma_type(raw_type: str) -> str:
    kind = raw_type.lower()
    if kind in {"emenda constitucional estadual", "ece"}:
        return "ece"
    if kind in {"emenda constitucional", "ec"}:
        return "ec"
    if kind in {"constituicao federal", "cf"}:
        return "cf"
    if kind in {"constituicao estadual", "ce"}:
        return "ce"
    if kind in {"lei complementar estadual", "lce"}:
        return "lce"
    if kind.startswith("lei complementar") or kind == "lc":
        return "lc"
    if kind == "lei":
        return "lei"
    return "unknown"


def _collect_diplomas_v2(normalized: str) -> list[dict[str, Any]]:
    diplomas: list[dict[str, Any]] = []
    for match in DIPLOMA_PATTERN.finditer(normalized):
        tail = normalized[match.end() : match.end() + 40]
        number_match = re.match(
            r"\s*(?:n(?:umero)?[ºo]?\s*)?(\d[\d.]*)(?:\s*/\s*(\d{2,4}))?", tail, re.IGNORECASE
        )
        diplomas.append(
            {
                "start": match.start(),
                "end": match.end(),
                "type": _diploma_type(match.group(1)),
                "number": number_match.group(1) if number_match else None,
                "year": normalize_legal_year(number_match.group(2)) if number_match else None,
            }
        )
    return diplomas


def _collect_articles_v2(normalized: str) -> list[dict[str, Any]]:
    return [
        {
            "start": match.start(),
            "end": match.end(),
            "number": match.group(1),
            "suffix": match.group(2),
        }
        for match in ARTICLE_PATTERN_V2.finditer(normalized)
    ]


def _diploma_for_article_v2(
    article: Mapping[str, Any],
    articles: Sequence[Mapping[str, Any]],
    diplomas: Sequence[Mapping[str, Any]],
    normalized: str,
) -> Mapping[str, Any] | None:
    next_article = next((item for item in articles if item["start"] > article["start"]), None)
    next_diploma = next((item for item in diplomas if item["start"] >= article["end"]), None)
    if next_diploma is not None and (
        next_article is None or next_diploma["start"] < next_article["start"]
    ):
        return next_diploma
    if next_article is not None:
        shared = next((item for item in diplomas if item["start"] >= next_article["end"]), None)
        if shared is not None:
            return shared
    previous = [item for item in diplomas if item["start"] < article["start"]]
    if previous:
        return previous[-1]
    clause_start = max(
        normalized.rfind(";", 0, article["start"] + 1),
        normalized.rfind(".", 0, article["start"] + 1),
    )
    return next(
        (
            item
            for item in diplomas
            if item["start"] >= clause_start and item["start"] < article["start"]
        ),
        None,
    )


def _add_unique(target: list[str], values: Iterable[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _detail_markers(segment: str) -> dict[str, Any]:
    paragraph_markers = [
        {"start": match.start(), "end": match.end(), "values": _parse_ordinal_list(match.group(0))}
        for match in PARAGRAPH_PATTERN.finditer(segment)
    ]
    inciso_markers = [
        {"start": match.start(), "end": match.end(), "values": _parse_ordinal_list(match.group(1))}
        for match in INCISO_PATTERN.finditer(segment)
    ]
    alinea_markers = [
        {
            "start": match.start(),
            "end": match.end(),
            "values": [char.lower() for char in re.findall(r"[a-z]", match.group(1), re.IGNORECASE)],
        }
        for match in ALINEA_PATTERN.finditer(segment)
    ]
    item_markers = [
        {"start": match.start(), "end": match.end(), "values": _parse_ordinal_list(match.group(1))}
        for match in ITEM_PATTERN.finditer(segment)
    ]

    paragraphs: list[dict[str, Any]] = []
    for marker in paragraph_markers:
        for number in marker["values"]:
            paragraphs.append(
                {
                    "number": number,
                    "incisos": [],
                    "alineas": [],
                    "items": [],
                    "start": marker["start"],
                    "end": marker["end"],
                }
            )
    paragraphs.sort(key=lambda item: item["start"])

    top_incisos: list[str] = []
    top_alineas: list[str] = []
    top_items: list[str] = []
    for marker, bucket in (
        (inciso_markers, "incisos"),
        (alinea_markers, "alineas"),
        (item_markers, "items"),
    ):
        for entry in marker:
            if bucket == "incisos":
                _add_unique(top_incisos, entry["values"])
            elif bucket == "alineas":
                _add_unique(top_alineas, entry["values"])
            else:
                _add_unique(top_items, entry["values"])
            paragraph = next(
                (item for item in reversed(paragraphs) if item["start"] <= entry["start"]), None
            )
            if paragraph is not None:
                _add_unique(paragraph[bucket], entry["values"])

    return {
        "paragraphs": [
            {
                "number": item["number"],
                "incisos": item["incisos"],
                "alineas": item["alineas"],
                "items": item["items"],
            }
            for item in paragraphs
        ],
        "incisos": top_incisos,
        "alineas": top_alineas,
        "items": top_items,
    }


def _bridge_paragraphs(
    article: Mapping[str, Any], previous_article: Mapping[str, Any] | None, normalized: str
) -> list[dict[str, Any]]:
    if previous_article is None:
        return []
    bridge = normalized[previous_article["end"] : article["start"]]
    if not re.search(r"\b(?:do|de)\s*$", bridge.strip(), re.IGNORECASE):
        return []
    details = _detail_markers(bridge)
    if not details["paragraphs"]:
        return []
    last = dict(details["paragraphs"][-1])
    paragraph_start = bridge.rfind("§")
    before_last = bridge[:paragraph_start] if paragraph_start >= 0 else bridge
    preceding = [match.group(1) for match in INCISO_PATTERN.finditer(before_last)]
    last_inciso = _parse_ordinal_list(preceding[-1] if preceding else None)
    if last_inciso:
        last["incisos"] = [last_inciso[-1]]
    return [last]


def parse_legal_references_v2(text: Any) -> list[dict[str, Any]]:
    """Port of ``parseLegalReferencesV2`` from legal-reference-parser-v2.js."""

    source = as_text(text).strip()
    normalized = normalize_source(source)
    if not normalized:
        return []
    articles = _collect_articles_v2(normalized)
    diplomas = _collect_diplomas_v2(normalized)
    references: list[dict[str, Any]] = []
    for index, article in enumerate(articles):
        previous_article = articles[index - 1] if index >= 1 else None
        next_article = articles[index + 1] if index + 1 < len(articles) else None
        segment_end = next_article["start"] if next_article is not None else len(normalized)
        local = _detail_markers(normalized[article["end"] : segment_end])
        paragraphs = list(local["paragraphs"]) + _bridge_paragraphs(
            article, previous_article, normalized
        )
        incisos = list(local["incisos"])
        alineas = list(local["alineas"])
        items = list(local["items"])
        for paragraph in paragraphs:
            _add_unique(incisos, paragraph["incisos"])
            _add_unique(alineas, paragraph["alineas"])
            _add_unique(items, paragraph["items"])
        diploma = _diploma_for_article_v2(article, articles, diplomas, normalized)
        references.append(
            {
                "diploma_type": (diploma or {}).get("type", "unknown"),
                "diploma_number": (diploma or {}).get("number"),
                "diploma_year": (diploma or {}).get("year"),
                "article": article["number"],
                "article_suffix": article["suffix"],
                "paragraphs": paragraphs,
                "incisos": incisos,
                "alineas": alineas,
                "items": items,
                "raw": source,
            }
        )
    return references


RAW_ARTICLE_PATTERN = re.compile(
    r"\bart(?:s|igo|igos)?\.?\s*(\d+)\s*(?:º|ª|o)?(?:\s*[-–]\s*([a-z]))?", re.IGNORECASE
)
ARTICLE_PATTERN_V1 = re.compile(r"\bartigos?\s+(\d+)([a-z])?", re.IGNORECASE)
COMBINED_PATTERN = re.compile(r"\bcombinado\s+com\b", re.IGNORECASE)
DIPLOMA_PATTERN_V1 = re.compile(
    r"\b(emenda constitucional estadual|emenda constitucional)\s+(?:numero\s+)?(\d+)"
    r"(?:\s*(?:/|de)\s*(\d{2,4}))?|\b(constituicao federal|constituicao estadual)\b",
    re.IGNORECASE,
)
ARTICLE_DETAIL_PATTERN = re.compile(r"\bparagrafo\s+(\d+|unico)\b", re.IGNORECASE)
INCISO_DETAIL_PATTERN = re.compile(
    r"\bincisos?\s+(.+?)(?=\b(?:paragrafo|artigo|emenda|constituicao|combinado)\b|$)",
    re.IGNORECASE,
)
AMBOS_PATTERN = re.compile(r"\bambos\b", re.IGNORECASE)


def _normalize_year_v1(value: str | None) -> str | None:
    if not value:
        return None
    return f"20{value}" if len(value) == 2 else value


def _diploma_from_match(match: re.Match[str]) -> dict[str, Any]:
    raw_type = match.group(1) or match.group(4)
    if raw_type == "emenda constitucional estadual":
        diploma_type = "ece"
    elif raw_type == "constituicao federal":
        diploma_type = "cf"
    elif raw_type == "constituicao estadual":
        diploma_type = "ce"
    else:
        diploma_type = "ec"
    return {
        "type": diploma_type,
        "number": match.group(2),
        "year": _normalize_year_v1(match.group(3)),
    }


def _collect_diplomas_v1(normalized: str) -> list[dict[str, Any]]:
    return [
        {"start": match.start(), "end": match.end(), "value": _diploma_from_match(match)}
        for match in DIPLOMA_PATTERN_V1.finditer(normalized)
    ]


def _collect_articles_v1(normalized: str) -> list[dict[str, Any]]:
    matches = list(ARTICLE_PATTERN_V1.finditer(normalized))
    articles: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        article = {
            "start": match.start(),
            "end": match.end(),
            "number": match.group(1),
            "suffix": match.group(2),
        }
        articles.append(article)
        if not re.match(r"artigos\b", match.group(0), re.IGNORECASE):
            continue
        tail_end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        tail = normalized[article["end"] : tail_end]
        extra = re.match(r"^\s*(?:,|e)\s*(\d+)([a-z])?", tail, re.IGNORECASE)
        if extra is not None:
            number_start = article["end"] + extra.start() + extra.group(0).index(extra.group(1))
            articles.append(
                {
                    "start": number_start,
                    "end": number_start + len(extra.group(1)) + len(extra.group(2) or ""),
                    "number": extra.group(1),
                    "suffix": extra.group(2),
                }
            )
    articles.sort(key=lambda item: item["start"])
    return articles


def _clause_at(normalized: str, position: int) -> dict[str, int]:
    boundaries = [0]
    for match in COMBINED_PATTERN.finditer(normalized):
        boundaries.append(match.end())
    boundaries.append(len(normalized))
    candidates = [boundary for boundary in boundaries if boundary <= position]
    start = candidates[-1] if candidates else 0
    end = next((boundary for boundary in boundaries if boundary > position), len(normalized))
    return {"start": start, "end": end}


def _diploma_for_article_v1(
    diplomas: Sequence[Mapping[str, Any]],
    articles: Sequence[Mapping[str, Any]],
    index: int,
    normalized: str,
) -> Mapping[str, Any] | None:
    article = articles[index]
    previous_end = articles[index - 1]["end"] if index >= 1 else 0
    next_start = articles[index + 1]["start"] if index + 1 < len(articles) else math.inf
    after = [
        diploma
        for diploma in diplomas
        if diploma["start"] >= article["end"] and diploma["start"] < next_start
    ]
    if after:
        lead = normalized[article["end"] : after[0]["start"]]
        has_postfixed = re.search(r"\b(?:da|do|de)\s*$", lead.strip(), re.IGNORECASE)
        has_constitution = after[0]["value"]["type"] in {"cf", "ce"} and re.search(
            r"\b(?:paragrafo|inciso)\b", lead, re.IGNORECASE
        )
        if has_postfixed or has_constitution:
            return after[0]["value"]
    if not math.isfinite(next_start) and after:
        return after[0]["value"]
    before = [
        diploma
        for diploma in diplomas
        if diploma["start"] >= previous_end and diploma["start"] < article["start"]
    ]
    if before:
        return before[-1]["value"]
    clause = _clause_at(normalized, article["start"])
    forward = [
        diploma
        for diploma in diplomas
        if diploma["start"] >= article["end"] and diploma["start"] < clause["end"]
    ]
    if forward:
        return forward[0]["value"]
    prior = [diploma for diploma in diplomas if diploma["start"] < article["start"]]
    return prior[-1]["value"] if prior else None


def _parse_number_list(value: Any) -> list[str]:
    tokens = re.findall(r"\d+|a|e|and", as_text(value))
    numbers: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not re.fullmatch(r"\d+", token):
            index += 1
            continue
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        after = tokens[index + 2] if index + 2 < len(tokens) else None
        if following == "a" and after is not None and re.fullmatch(r"\d+", after):
            first, last = int(token), int(after)
            step = 1 if first <= last else -1
            for number in range(first, last + step, step):
                if str(number) not in numbers:
                    numbers.append(str(number))
            index += 3
            continue
        if token not in numbers:
            numbers.append(token)
        index += 1
    return numbers


def _parse_article_details(segment: str) -> dict[str, Any]:
    paragraph_match = ARTICLE_DETAIL_PATTERN.search(segment)
    inciso_match = INCISO_DETAIL_PATTERN.search(segment)
    return {
        "paragraph": paragraph_match.group(1).lower() if paragraph_match else None,
        "incisos": _parse_number_list(inciso_match.group(1)) if inciso_match else [],
        "qualifiers": ["ambos"] if AMBOS_PATTERN.search(segment) else [],
    }


def _raw_reference_text(
    source: str, raw_article: re.Match[str], next_raw: re.Match[str] | None
) -> str:
    end = next_raw.start() if next_raw is not None else len(source)
    sliced = source[raw_article.start() : end]
    return re.sub(r"\s+e\s*$", "", sliced, flags=re.IGNORECASE).strip()


def parse_legal_references(text: Any) -> list[dict[str, Any]]:
    """Port of the v1 parser embedded in legal-foundation.js."""

    source = as_text(text)
    normalized = normalize_legal_text(source)
    if not normalized:
        return []
    diplomas = _collect_diplomas_v1(normalized)
    articles = _collect_articles_v1(normalized)
    raw_articles = list(RAW_ARTICLE_PATTERN.finditer(source))
    references: list[dict[str, Any]] = []
    for index, article in enumerate(articles):
        clause = _clause_at(normalized, article["start"])
        detail_end = (
            articles[index + 1]["start"] if index + 1 < len(articles) else clause["end"]
        )
        detail = _parse_article_details(normalized[article["end"] : detail_end])
        if AMBOS_PATTERN.search(normalized[clause["start"] : clause["end"]]):
            detail["qualifiers"] = ["ambos"]
        diploma = _diploma_for_article_v1(diplomas, articles, index, normalized)
        raw_article = raw_articles[index] if index < len(raw_articles) else None
        next_raw = raw_articles[index + 1] if index + 1 < len(raw_articles) else None
        if raw_article is not None:
            raw = _raw_reference_text(source, raw_article, next_raw)
        else:
            raw = normalized[article["start"] : detail_end]
        references.append(
            {
                "raw": raw,
                "diploma": diploma,
                "article": article["number"],
                "suffix": article["suffix"],
                "paragraph": detail["paragraph"],
                "incisos": detail["incisos"],
                "qualifiers": detail["qualifiers"],
                "complete": bool(
                    diploma and (diploma["type"] in {"cf", "ce"} or diploma.get("year"))
                ),
            }
        )
    return references


MILITARY_PATTERN = re.compile(r"\bmilitar\b", re.IGNORECASE)
PLACEHOLDER_PATTERN = re.compile(r"^selecion(?:e|ar)\b", re.IGNORECASE)
ALINEA_LETTER_PATTERN = re.compile(r"\balineas?\s+([a-z])\b", re.IGNORECASE)
ARTICLE_NUMBER_PATTERN = re.compile(r"\bart(?:igo|igos)?s?\.?\s*(\d+)\s*(?:º|ª|o)?", re.IGNORECASE)
PARAGRAPH_NUMBER_PATTERN = re.compile(r"§{1,2}\s*(\d+)")


def selectable_legal_options(options: Any) -> list[dict[str, Any]]:
    """Return only real DOM-backed legal choices with their original values."""
    option_list = options if isinstance(options, list) else []
    selected: list[dict[str, Any]] = []
    for index, raw in enumerate(option_list):
        if not isinstance(raw, Mapping):
            continue
        raw_value = raw.get("value")
        value = "" if raw_value is None else str(raw_value)
        raw_label = raw.get("label")
        label = "" if raw_label is None else str(raw_label).strip()
        if not value.strip() or not label:
            continue
        if raw.get("disabled") is True or raw.get("selectable") is False:
            continue
        if PLACEHOLDER_PATTERN.search(normalize_legal_text(label)):
            continue
        selected.append({**dict(raw), "value": value, "label": label, "index": index})
    return selected


def _option_parts(option: Any, index: int) -> dict[str, Any]:
    if option is not None and isinstance(option, Mapping):
        value = option.get("value") or option.get("label") or ""
        label = option.get("label") or value
        return dict(option, index=index, value=value, label=label)
    return {"index": index, "value": option, "label": option}


def _reference_identity(reference: Mapping[str, Any]) -> str:
    return ":".join(
        as_text(reference.get(key))
        for key in ("diploma_type", "diploma_number", "diploma_year", "article", "article_suffix")
    )


def _unique_references(references: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    seen: set[str] = set()
    unique: list[Mapping[str, Any]] = []
    for reference in references:
        key = _reference_identity(reference)
        if key in seen:
            continue
        seen.add(key)
        unique.append(reference)
    return unique


def _has_diploma(references: Sequence[Mapping[str, Any]], kind: str, number: str | None = None) -> bool:
    return any(
        reference.get("diploma_type") == kind
        and (number is None or reference.get("diploma_number") == number)
        for reference in references
    )


def _has_article(
    references: Sequence[Mapping[str, Any]],
    kind: str,
    number: str | None,
    article: str,
    suffix: str | None = None,
) -> bool:
    return any(
        reference.get("diploma_type") == kind
        and reference.get("diploma_number") == number
        and reference.get("article") == article
        and (reference.get("article_suffix") or None) == suffix
        for reference in references
    )


def _has_paragraph(references: Sequence[Mapping[str, Any]], number: str) -> bool:
    return any(
        any(paragraph.get("number") == number for paragraph in reference.get("paragraphs") or [])
        for reference in references
    )


def _has_inciso(reference: Mapping[str, Any], number: str) -> bool:
    return number in (reference.get("incisos") or []) or any(
        number in (paragraph.get("incisos") or [])
        for paragraph in reference.get("paragraphs") or []
    )


def _has_inciso_in(
    references: Sequence[Mapping[str, Any]], number: str, article: str | None = None
) -> bool:
    return any(
        (article is None or reference.get("article") == article) and _has_inciso(reference, number)
        for reference in references
    )


def _alineas_for(references: Sequence[Mapping[str, Any]], article: str | None = None) -> list[str]:
    alineas: list[str] = []
    for reference in references:
        if article is not None and reference.get("article") != article:
            continue
        for alinea in reference.get("alineas") or []:
            if alinea not in alineas:
                alineas.append(alinea)
        for paragraph in reference.get("paragraphs") or []:
            for alinea in paragraph.get("alineas") or []:
                if alinea not in alineas:
                    alineas.append(alinea)
    return alineas


def _cf40_paragraph5(references: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        reference.get("diploma_type") == "cf"
        and reference.get("article") == "40"
        and any(paragraph.get("number") == "5" for paragraph in reference.get("paragraphs") or [])
        for reference in references
    )


def _article_numbers_from_label(normalized_label: str) -> list[str]:
    return [match.group(1) for match in ARTICLE_NUMBER_PATTERN.finditer(normalized_label)]


def _paragraph_numbers_from_label(normalized_label: str) -> list[str]:
    return [match.group(1) for match in PARAGRAPH_NUMBER_PATTERN.finditer(normalized_label)]


def _alineas_from_label(normalized_label: str) -> list[str]:
    return [match.group(1) for match in ALINEA_LETTER_PATTERN.finditer(normalized_label)]


def _has_ec41_transition(references: Sequence[Mapping[str, Any]]) -> bool:
    return _has_article(references, "ec", "41", "6") and _has_article(references, "ec", "41", "7")


def _has_ec41_article6a(references: Sequence[Mapping[str, Any]]) -> bool:
    return _has_article(references, "ec", "41", "6", "a")


def _has_lc51(references: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        reference.get("diploma_type") in {"lc", "lce"}
        and reference.get("diploma_number") == "51"
        for reference in references
    )


def _has_ce29(references: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        reference.get("diploma_type") == "ce" and reference.get("article") == "29"
        for reference in references
    )


def _derive_class_id(
    references: Sequence[Mapping[str, Any]], normalized_label: str, index: int
) -> str:
    article_numbers = _article_numbers_from_label(normalized_label)
    paragraph_numbers = _paragraph_numbers_from_label(normalized_label)
    has_p5 = "5" in paragraph_numbers or _has_paragraph(references, "5")
    if MILITARY_PATTERN.search(normalized_label):
        return "MILITARY_TRANSITION"
    if _has_ec41_article6a(references):
        return "EC41_ART6A_EC70"
    if _has_ec41_transition(references):
        return "EC41_TRANSITION_TEACHER" if has_p5 else "EC41_TRANSITION_GENERAL"
    # A state-constitution article 40 must never be classified as a CF art. 40
    # class: the state diploma takes precedence over the generic branch.
    if any(
        reference.get("diploma_type") == "ce" and reference.get("article") == "40"
        for reference in references
    ):
        return "CE40"
    if "40" in article_numbers:
        alineas = _alineas_for(references, "40") + _alineas_from_label(normalized_label)
        if has_p5:
            return "CF40_III_A_P5"
        if _has_inciso_in(references, "1", "40"):
            return "CF40_I"
        if _has_inciso_in(references, "2", "40"):
            return "CF40_II"
        if _has_inciso_in(references, "3", "40"):
            return "CF40_III_B" if "b" in alineas and "a" not in alineas else "CF40_III_A"
        return f"CATALOG_OPTION_{index}"
    if _has_lc51(references):
        if _has_paragraph(references, "4"):
            return "CF40_P1_II_LC51"
        return "LC51_ART1_II" if _has_inciso_in(references, "2") else "LC51_ART1"
    if _has_article(references, "ec", "20", "8"):
        return "EC20_ART8"
    if _has_article(references, "ec", "20", "9"):
        return "EC20_ART9"
    if _has_article(references, "ec", "20", "1"):
        return "EC20_ART1"
    if _has_article(references, "ec", "41", "2"):
        return "EC41_ART2"
    if _has_article(references, "ec", "47", "3"):
        return "EC47_ART3"
    if _has_article(references, "ec", "41", "1"):
        return "EC41_ART1"
    if _has_ce29(references):
        alineas = _alineas_for(references, "29") + _alineas_from_label(normalized_label)
        first = (alineas[0] if alineas else "a").upper()
        if _has_inciso_in(references, "1", "29"):
            return f"CE29_I_{first}"
        if _has_inciso_in(references, "3", "29"):
            return f"CE29_III_{first}"
        return "CE29_OTHER"
    return f"CATALOG_OPTION_{index}"


def _derive_modality(class_id: str, references: Sequence[Mapping[str, Any]]) -> str:
    if "ART6A" in class_id or class_id == "CF40_I":
        return "invalidity_permanent_disability"
    if class_id in {"CF40_P1_II_LC51", "LC51_ART1_II", "LC51_ART1"}:
        return "invalidity_permanent_disability"
    if class_id == "CF40_II":
        return "other"
    if any(token in class_id for token in ("TRANSITION", "ART3", "ART2", "ART8")):
        return "voluntary_contribution"
    if _has_diploma(references, "ec") or _has_diploma(references, "ece"):
        return "voluntary_contribution"
    if class_id.startswith("CF40_III"):
        return "voluntary_contribution"
    return "unknown"


def _derive_proportionality(class_id: str, normalized_label: str) -> str:
    if re.search(r"\bproventos?\s+proporciona", normalized_label):
        return "proportional"
    if re.search(r"\bproventos?\s+integra", normalized_label):
        return "integral"
    if "TRANSITION" in class_id or class_id == "EC47_ART3":
        return "integral"
    return "unknown"


def build_catalog_option_signature(option: Any, index: int = 0) -> dict[str, Any]:
    """Jurisprudence signature of one raw portal catalog option."""

    parts = _option_parts(option, index)
    label = as_text(parts.get("label"))
    value = as_text(parts.get("value"))
    normalized_label = normalize_legal_text(label)
    references = _unique_references(parse_legal_references_v2(label))
    placeholder = bool(PLACEHOLDER_PATTERN.match(normalized_label.strip()))
    selectable = value.strip() != "" and label.strip() != "" and not placeholder
    class_id = _derive_class_id(references, normalized_label, index)
    return {
        "index": index,
        "value": value,
        "label": label,
        "selectable": selectable,
        "class_id": class_id,
        "scope": "military" if MILITARY_PATTERN.search(normalized_label) else "civil",
        "modality": _derive_modality(class_id, references),
        "proportionality": _derive_proportionality(class_id, normalized_label),
        "calculation_basis": "unknown",
        "parity": "unknown",
        "teacher_rule": _cf40_paragraph5(references),
        "references": references,
    }


_MILITARY_SCOPE = re.compile(r"\b(?:militar|military|policia militar|reforma)\b")
_CIVIL_SCOPE = re.compile(
    r"\b(?:servidor|professor|docente|magisterio|aposentadoria|invalidez|incapacidade)\b"
)
_INVALIDITY_MODALITY = re.compile(
    r"\b(?:aposentadoria\s+por\s+)?(?:invalidez|incapacidade\s+permanente)\b"
)
_VOLUNTARY_WITH_CONTRIBUTION = re.compile(
    r"\baposentadoria\b[\s\S]{0,100}\bvoluntaria\b[\s\S]{0,100}\btempo\s+de\s+contribuicao\b"
)
_VOLUNTARY = re.compile(r"\baposentadoria\b[\s\S]{0,100}\bvoluntaria\b")
_OTHER_MODALITY = re.compile(r"\b(?:aposentadoria|invalidez|incapacidade)\b")
_INTEGRAL_PROVENTOS = re.compile(r"\bproventos?\s+integra(?:l|is)\b")
_PROPORTIONAL_PROVENTOS = re.compile(r"\bproventos?\s+proporciona(?:l|is)\b")
_AVERAGE_BASIS = re.compile(
    r"\b(?:pela|por|calculad[oa]s?\s+pel[ao])\s+media\b|\bmedia\s+(?:aritmetica|contributiva)\b"
)
_REMUNERATION_BASIS = re.compile(
    r"\b(?:integralidade|remuneracao\s+(?:do\s+cargo|do\s+servidor)|ultima\s+remuneracao)\b"
)
_NO_PARITY = re.compile(r"\bsem\s+paridade\b")
_PARITY = re.compile(r"\bparidade\b")
_NO_TRANSITION_RULE = re.compile(r"\bsem\s+regra\s+de\s+transicao\b")
_TRANSITION_RULE = re.compile(r"\bregra\s+de\s+transicao\b")
_TEACHER_CONTEXT = re.compile(r"\b(?:professor(?:a|es|as)?|docente|magisterio)\b")
_EXPLICIT_TEACHER_RULE = re.compile(
    r"\b(?:regra|aposentadoria)\b[\s\S]{0,50}\b(?:professor|docente|magisterio)\b"
)
_ARTICLE_WORD = re.compile(r"\b(?:artigo|art\.)\b")
_PROVENTOS_OPERATIVE = re.compile(r"\b(?:proventos?\s+integra|proventos?\s+proporcional)")


def _profile_source_text(operative_text: Any, documentary_value: Any) -> str:
    if as_text(operative_text).strip():
        return as_text(operative_text)
    if isinstance(documentary_value, str):
        return documentary_value
    if isinstance(documentary_value, Mapping):
        primary = documentary_value.get("operative_text")
        if primary is None:
            primary = documentary_value.get("value")
        return as_text(primary)
    return ""


def _detect_scope(text: str) -> str:
    if _MILITARY_SCOPE.search(text):
        return "military"
    if _CIVIL_SCOPE.search(text):
        return "civil"
    return "unknown"


def _detect_modality(text: str) -> str:
    if _INVALIDITY_MODALITY.search(text):
        return "invalidity_permanent_disability"
    if _VOLUNTARY_WITH_CONTRIBUTION.search(text):
        return "voluntary_contribution"
    if _VOLUNTARY.search(text):
        return "voluntary_contribution"
    if _OTHER_MODALITY.search(text):
        return "other"
    return "unknown"


def _detect_proportionality(text: str) -> str:
    if _INTEGRAL_PROVENTOS.search(text):
        return "integral"
    if _PROPORTIONAL_PROVENTOS.search(text):
        return "proportional"
    return "unknown"


def _detect_calculation_basis(text: str) -> str:
    if _AVERAGE_BASIS.search(text):
        return "average"
    if _REMUNERATION_BASIS.search(text):
        return "remuneration"
    return "unknown"


def _detect_parity(text: str) -> str:
    if _NO_PARITY.search(text):
        return "no"
    if _PARITY.search(text):
        return "yes"
    return "unknown"


def _is_teacher_reference(reference: Mapping[str, Any]) -> bool:
    return (
        reference.get("diploma_type") == "cf"
        and reference.get("article") == "40"
        and any(
            paragraph.get("number") == "5" for paragraph in reference.get("paragraphs") or []
        )
    )


def _detect_explicit_teacher_rule(text: str, references: Sequence[Mapping[str, Any]]) -> bool:
    if any(_is_teacher_reference(reference) for reference in references):
        return True
    return bool(_EXPLICIT_TEACHER_RULE.search(text)) and bool(_ARTICLE_WORD.search(text))


def _detect_transition_rule(text: str, references: Sequence[Mapping[str, Any]]) -> bool | str:
    if _NO_TRANSITION_RULE.search(text):
        return False
    if _TRANSITION_RULE.search(text):
        return True
    has_transition = any(
        reference.get("diploma_type") in {"ec", "ece"}
        and reference.get("diploma_number") in {"20", "41", "47"}
        for reference in references
    )
    return True if has_transition else "unknown"


def _profile_evidence(text: str, profile: Mapping[str, Any]) -> list[str]:
    evidence: list[str] = []
    if profile["modality"] != "unknown":
        evidence.append(f"modality:{profile['modality']}")
    if profile["proportionality"] != "unknown":
        evidence.append(f"proventos:{profile['proportionality']}")
    if profile["calculation_basis"] != "unknown":
        evidence.append(f"base:{profile['calculation_basis']}")
    if profile["parity"] != "unknown":
        evidence.append(f"parity:{profile['parity']}")
    if profile["professor_context"]:
        evidence.append("context:professor")
    if profile["professor_rule_explicit"]:
        evidence.append("rule:teacher-explicit")
    if profile["transition_rule"] != "unknown":
        evidence.append(f"transition:{as_text(profile['transition_rule'])}")
    if _PROVENTOS_OPERATIVE.search(text):
        evidence.append("operative:proventos")
    return evidence


def build_retirement_legal_profile(
    operative_text: Any = "", cargo: Any = "", documentary_value: Any = None
) -> dict[str, Any]:
    """Stable functional profile of the retirement document under review."""

    source = _profile_source_text(operative_text, documentary_value)
    normalized = normalize_legal_text(f"{source} {as_text(cargo)}")
    references = parse_legal_references_v2(source)
    detected_scope = _detect_scope(normalized)
    profile: dict[str, Any] = {
        "scope": "civil" if detected_scope == "unknown" and references else detected_scope,
        "modality": _detect_modality(normalized),
        "proportionality": _detect_proportionality(normalized),
        "calculation_basis": _detect_calculation_basis(normalized),
        "parity": _detect_parity(normalized),
        "professor_context": bool(_TEACHER_CONTEXT.search(normalized)),
        "professor_rule_explicit": _detect_explicit_teacher_rule(normalized, references),
        "transition_rule": _detect_transition_rule(normalized, references),
        "references": references,
        "evidence": [],
    }
    profile["evidence"] = _profile_evidence(normalized, profile)
    return profile


SCORE_WEIGHTS: dict[str, float] = {
    "scope": 0.10,
    "modality": 0.25,
    "proportionality": 0.20,
    "calculation_parity": 0.10,
    "crosswalk": 0.20,
    "discriminators": 0.10,
    "lexical": 0.05,
}

CROSSWALK_ECE20 = "ECE20_ART7_VOLUNTARY_TRANSITION"
PUBLIC_RULE_IDS: frozenset[str] = frozenset({"EC41_SEM_P5", "EC41_COM_P5", "EC47_ART3"})
LEGAL_DIPLOMA_TYPES: frozenset[str] = frozenset({"ec", "ece", "cf", "ce"})


def _references_have(references: Sequence[Mapping[str, Any]], predicate) -> bool:
    return any(predicate(reference) for reference in references)


def _legal_diploma(reference: Mapping[str, Any]) -> bool:
    return (
        reference.get("diploma_type") in LEGAL_DIPLOMA_TYPES
        and reference.get("diploma_number") is not None
    )


def _missing_diploma_family(
    source_references: Sequence[Mapping[str, Any]],
    candidate_references: Sequence[Mapping[str, Any]],
    recognized_crosswalk: bool,
) -> str | None:
    """EC and ECE amendments are distinct instruments; fail closed otherwise."""

    if recognized_crosswalk:
        return None
    candidate_diplomas = [item for item in candidate_references if _legal_diploma(item)]

    def carries(source: Mapping[str, Any]) -> bool:
        return any(
            candidate.get("diploma_type") == source.get("diploma_type")
            and candidate.get("diploma_number") == source.get("diploma_number")
            and (
                candidate.get("diploma_year") is None
                or source.get("diploma_year") is None
                or candidate.get("diploma_year") == source.get("diploma_year")
            )
            for candidate in candidate_diplomas
        )

    for reference in source_references:
        if not _legal_diploma(reference):
            continue
        if carries(reference):
            continue
        shares_federal = reference.get("diploma_type") == "ece" and any(
            source.get("diploma_type") == "ec" and carries(source)
            for source in source_references
        )
        if reference.get("diploma_type") == "ece" and not shares_federal:
            return "hard-reject:diploma-family-missing"
    return None


def _is_ece20_case(profile: Mapping[str, Any]) -> bool:
    return profile["modality"] == "voluntary_contribution" and any(
        reference.get("diploma_type") == "ece"
        and reference.get("diploma_number") == "20"
        and reference.get("diploma_year") == "2020"
        and reference.get("article") == "7"
        for reference in profile["references"]
    )


def _crosswalk_for(profile: Mapping[str, Any], candidate: Mapping[str, Any]) -> str | None:
    class_id = candidate.get("class_id")
    if _is_ece20_case(profile) and class_id in {
        "EC41_TRANSITION_GENERAL",
        "EC41_TRANSITION_TEACHER",
    }:
        return CROSSWALK_ECE20
    has_ec41_transition = (
        class_id
        in {
            "EC41_SEM_P5",
            "EC41_COM_P5",
            "EC41_TRANSITION_GENERAL",
            "EC41_TRANSITION_TEACHER",
        }
        and (not profile["professor_rule_explicit"] or candidate.get("teacher_rule"))
        and any(
            reference.get("diploma_type") == "ec"
            and reference.get("diploma_number") == "41"
            and reference.get("article") in {"6", "7"}
            and not reference.get("article_suffix")
            for reference in profile["references"]
        )
    )
    if has_ec41_transition:
        return "EC41_TRANSITION_STRUCTURAL_RULE"
    if class_id in {"EC41_ART6A", "EC41_ART6A_EC70"} and any(
        reference.get("diploma_type") == "ec"
        and reference.get("diploma_number") == "41"
        and reference.get("article_suffix") == "a"
        for reference in profile["references"]
    ):
        return "EC41_ART6A_STRUCTURAL_RULE"
    return None


def _same_diploma(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        left.get("diploma_type") == right.get("diploma_type")
        and left.get("diploma_number") == right.get("diploma_number")
        and left.get("diploma_year") == right.get("diploma_year")
    )


def _same_article(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        _same_diploma(left, right)
        and left.get("article") == right.get("article")
        and left.get("article_suffix") == right.get("article_suffix")
    )


def _has_discriminator_mismatch(
    source_references: Sequence[Mapping[str, Any]],
    candidate_references: Sequence[Mapping[str, Any]],
) -> str | None:
    for source in source_references:
        if not (source.get("alineas") or source.get("incisos")):
            continue
        for candidate in candidate_references:
            if not _same_article(source, candidate):
                continue
            source_alineas = source.get("alineas") or []
            candidate_alineas = candidate.get("alineas") or []
            if source_alineas and candidate_alineas and not any(
                value in candidate_alineas for value in source_alineas
            ):
                return "hard-reject:alinea-mismatch"
            source_incisos = source.get("incisos") or []
            candidate_incisos = candidate.get("incisos") or []
            if source_incisos and candidate_incisos and not any(
                value in candidate_incisos for value in source_incisos
            ):
                return "hard-reject:inciso-mismatch"
    return None


def _structural_match(
    source_references: Sequence[Mapping[str, Any]],
    candidate_references: Sequence[Mapping[str, Any]],
) -> bool:
    for source in source_references:
        for candidate in candidate_references:
            if not _same_article(source, candidate):
                continue
            source_paragraphs = source.get("paragraphs") or []
            candidate_paragraphs = candidate.get("paragraphs") or []
            if not source_paragraphs or not candidate_paragraphs:
                return True
            if any(
                left.get("number") == right.get("number")
                for left in source_paragraphs
                for right in candidate_paragraphs
            ):
                return True
    return False


def _dice_similarity(left: Any, right: Any) -> float:
    left_tokens = {token for token in normalize_legal_text(left).split() if token}
    right_tokens = {token for token in normalize_legal_text(right).split() if token}
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = sum(1 for token in left_tokens if token in right_tokens)
    return (2 * intersection) / (len(left_tokens) + len(right_tokens))


def _score_reason(name: str, value: float, weight: float) -> str:
    return f"{name}:{js_number(value)}:{to_fixed(value * weight)}"


def _rank_one(
    profile: Mapping[str, Any], source_text: str, option: Mapping[str, Any]
) -> dict[str, Any]:
    candidate = build_catalog_option_signature(option, option.get("index") or 0)
    reasons: list[str] = []
    warnings: list[str] = []
    hard_reasons: list[str] = []
    crosswalk = _crosswalk_for(profile, candidate)

    if not candidate["scope"] or candidate["scope"] != profile["scope"]:
        hard_reasons.append("hard-reject:scope-mismatch")
    source_has_ce = any(
        reference.get("diploma_type") == "ce" for reference in profile["references"]
    )
    candidate_has_cf = any(
        reference.get("diploma_type") == "cf" for reference in candidate["references"]
    )
    source_has_cf = any(
        reference.get("diploma_type") == "cf" for reference in profile["references"]
    )
    candidate_has_ce = any(
        reference.get("diploma_type") == "ce" for reference in candidate["references"]
    )
    if (source_has_ce and candidate_has_cf) or (source_has_cf and candidate_has_ce):
        hard_reasons.extend(["family-mismatch", "hard-reject:constitution-mismatch"])
    source_has_ec41_art6 = any(
        reference.get("diploma_type") == "ec"
        and reference.get("diploma_number") == "41"
        and reference.get("article") == "6"
        and not reference.get("article_suffix")
        for reference in profile["references"]
    )
    candidate_has_ec41_art6a = candidate["class_id"] == "EC41_ART6A" or any(
        reference.get("diploma_type") == "ec"
        and reference.get("diploma_number") == "41"
        and reference.get("article") == "6"
        and reference.get("article_suffix") == "a"
        for reference in candidate["references"]
    )
    if source_has_ec41_art6 and candidate_has_ec41_art6a:
        hard_reasons.append("hard-reject:article-suffix-mismatch")
    discriminator = _has_discriminator_mismatch(profile["references"], candidate["references"])
    if discriminator:
        hard_reasons.append(discriminator)
    missing_family = _missing_diploma_family(
        profile["references"], candidate["references"], crosswalk is not None
    )
    if missing_family:
        hard_reasons.append(missing_family)
    if (
        profile["modality"] != "unknown"
        and candidate["modality"] != "unknown"
        and profile["modality"] != candidate["modality"]
    ):
        hard_reasons.append("hard-reject:modality-mismatch")
    # Professor cargo is context, not proof of the teacher rule.
    if profile["professor_context"] and candidate["teacher_rule"] and not profile["professor_rule_explicit"]:
        hard_reasons.append("hard-reject:teacher-rule-not-operative")
    if not candidate["selectable"]:
        hard_reasons.append("hard-reject:option-not-selectable")

    exact_text = normalize_legal_text(source_text) == normalize_legal_text(candidate["label"])
    legacy_teacher_mismatch = bool(profile["professor_rule_explicit"]) and not candidate["teacher_rule"]
    structural = _structural_match(profile["references"], candidate["references"])
    components = {
        "scope": 1 if profile["scope"] == candidate["scope"] else 0,
        "modality": 1
        if profile["modality"] == "unknown" or candidate["modality"] == "unknown"
        else (1 if profile["modality"] == candidate["modality"] else 0),
        "proportionality": 1
        if profile["proportionality"] == "unknown" or candidate["proportionality"] == "unknown"
        else (1 if profile["proportionality"] == candidate["proportionality"] else 0),
        "calculation_parity": 1
        if (
            (profile["calculation_basis"] == "unknown" or candidate["calculation_basis"] == "unknown")
            and (profile["parity"] == "unknown" or candidate["parity"] == "unknown")
        )
        else 0,
        "crosswalk": (0.75 if (candidate["teacher_rule"] and not profile["professor_rule_explicit"]) else 1)
        if crosswalk
        else (1 if structural else 0),
        "discriminators": (
            1 if profile["professor_rule_explicit"] else 0
        )
        if candidate["teacher_rule"]
        else (0 if legacy_teacher_mismatch else 1),
        "lexical": _dice_similarity(source_text, candidate["label"]),
    }

    reasons.append(_score_reason(f"scope:{profile['scope']}", components["scope"], SCORE_WEIGHTS["scope"]))
    reasons.append(
        _score_reason(f"modality:{profile['modality']}", components["modality"], SCORE_WEIGHTS["modality"])
    )
    reasons.append(
        _score_reason(
            f"proportionality:{profile['proportionality']}",
            components["proportionality"],
            SCORE_WEIGHTS["proportionality"],
        )
    )
    reasons.append(
        _score_reason(
            "calculation-parity", components["calculation_parity"], SCORE_WEIGHTS["calculation_parity"]
        )
    )
    if crosswalk:
        reasons.append(f"crosswalk:{crosswalk}")
    reasons.append(
        _score_reason("discriminators", components["discriminators"], SCORE_WEIGHTS["discriminators"])
    )
    reasons.append(_score_reason("lexical", components["lexical"], SCORE_WEIGHTS["lexical"]))
    if profile["professor_context"] and candidate["teacher_rule"] and not profile["professor_rule_explicit"]:
        warnings.append(
            "Professor identificado pelo cargo, mas a regra docente não foi encontrada "
            "expressamente na fundamentação. Revisão recomendada."
        )

    score = (
        0.0
        if hard_reasons
        else sum(components[key] * weight for key, weight in SCORE_WEIGHTS.items())
    )
    return {
        "class_id": candidate["class_id"],
        "scope": candidate["scope"],
        "option_value": option.get("value"),
        "option_label": option.get("label"),
        "option_index": option.get("index"),
        "score": score,
        "confidence": score,
        "hard_conflict": bool(hard_reasons),
        "rejected": bool(hard_reasons),
        "reasons": [*hard_reasons, *reasons],
        "warnings": warnings,
        "method": "exact"
        if exact_text
        else ("similarity" if crosswalk == CROSSWALK_ECE20 else ("rule" if (crosswalk or structural) else "none")),
        "score_components": components,
        "candidate_references": candidate["references"],
    }


def _empty_decision(
    profile: Mapping[str, Any],
    reason: str,
    warnings: Sequence[str] | None = None,
    decision_state: str = "NO_COMPATIBLE_CANDIDATE",
) -> dict[str, Any]:
    return {
        "status": "pending",
        "decision_state": decision_state,
        "automatic": False,
        "scope": profile["scope"],
        "option_value": None,
        "option_label": None,
        "class_id": None,
        "method": "none",
        "confidence": 0,
        "margin": 0,
        "reason": reason,
        "reasons": [reason],
        "warnings": list(warnings or []),
        "ranking": [],
        "profile": profile,
        "score_components": {"lexical_weight": SCORE_WEIGHTS["lexical"]},
    }


def classify_portal_legal_foundation(
    operative_text: Any = "",
    cargo: Any = "",
    options: Any = None,
    hints: Any = None,
) -> dict[str, Any]:
    """Rank the portal catalog against the documentary legal profile."""

    hint_map = hints if isinstance(hints, Mapping) else {}
    profile = build_retirement_legal_profile(
        operative_text=operative_text,
        cargo=cargo,
        documentary_value=hint_map.get("documentaryValue"),
    )
    if not as_text(operative_text).strip():
        return _empty_decision(profile, "missing-source")
    option_list = options if isinstance(options, list) else []
    normalized_options = [
        build_catalog_option_signature(option, index) for index, option in enumerate(option_list)
    ]
    if not normalized_options:
        return _empty_decision(profile, "CATALOG_CLASS_MISSING")

    references = profile["references"]
    reference_types = {reference.get("diploma_type") for reference in references}
    ec41_reference = any(
        reference.get("diploma_type") == "ec"
        and reference.get("diploma_number") == "41"
        and reference.get("article") in {"6", "7"}
        for reference in references
    )
    ec47_article3 = any(
        reference.get("diploma_type") == "ec"
        and reference.get("diploma_number") == "47"
        and reference.get("article") == "3"
        for reference in references
    )
    # Coexisting EC and ECE diplomas are not a conflict by themselves: ECE/RN
    # 20/2020 may preserve previous rules. Only contradictory roles conflict.
    if ({"cf"} <= reference_types and "ce" in reference_types) or (
        ec41_reference and ec47_article3
    ):
        return _empty_decision(profile, "family-conflict", [], "DOCUMENT_CONFLICT")

    ranking = sorted(
        [
            _rank_one(profile, operative_text, option)
            for option in normalized_options
            if option["selectable"]
        ],
        key=lambda candidate: (-candidate["score"], candidate["option_index"]),
    )
    viable = [candidate for candidate in ranking if not candidate["rejected"]]
    if not viable:
        decision = _empty_decision(profile, "no-compatible-candidate")
        decision["ranking"] = ranking
        return decision

    best = viable[0]
    second = viable[1] if len(viable) > 1 else None
    margin = best["confidence"] - second["confidence"] if second is not None else best["confidence"]
    reasons = list(best["reasons"])
    warnings = list(best["warnings"])
    tied = second is not None and best["confidence"] == second["confidence"]
    if tied:
        tied_count = sum(1 for candidate in viable if candidate["confidence"] == best["confidence"])
        reasons.extend(["equivalent-candidates", f"tie:{tied_count}"])
    if best["confidence"] >= 0.90 and margin >= 0.12 and not best["hard_conflict"]:
        status = "selected"
    elif best["confidence"] >= 0.75 and not best["hard_conflict"]:
        status = "review"
    else:
        status = "pending"
    # An option the structural classifier could not recognise never becomes an
    # automatic selection: it stays in review even when the numeric score passes.
    has_structural_evidence = (
        best["class_id"] == "EC20_ART8"
        or _structural_match(profile["references"], best.get("candidate_references") or [])
        or any(str(reason).startswith("crosswalk:") for reason in (best.get("reasons") or []))
    )
    if (
        status == "selected"
        and str(best["class_id"]).startswith("CATALOG_OPTION_")
        and not has_structural_evidence
    ):
        status = "review"
        warnings.append("Classe jurídica do catálogo não reconhecida; confirmação manual necessária.")
    if tied:
        decision_state = "TRUE_TIE"
    elif status == "selected":
        decision_state = "AUTO_SELECTED"
    elif status == "review":
        decision_state = "REVIEW_REQUIRED"
    else:
        decision_state = "NO_COMPATIBLE_CANDIDATE"
    if status != "selected":
        warnings.append(
            "Decisão não atende os limites de confiança/margem para preenchimento automático."
        )
    components = dict(best["score_components"])
    components["lexical_weight"] = SCORE_WEIGHTS["lexical"]
    return {
        "status": status,
        "decision_state": decision_state,
        "automatic": status == "selected",
        "scope": profile["scope"],
        "option_value": best["option_value"],
        "option_label": best["option_label"],
        "class_id": best["class_id"],
        "method": best["method"] if status == "selected" else "none",
        "confidence": best["confidence"],
        "margin": margin,
        "hard_conflict": best["hard_conflict"] is True,
        "reason": None if status == "selected" else "manual-review-required",
        "reasons": reasons,
        "warnings": warnings,
        "ranking": ranking,
        "profile": profile,
        "score_components": components,
    }


RULE_IDS: frozenset[str] = frozenset({"EC41_SEM_P5", "EC41_COM_P5", "EC47_ART3"})
_SELECT_PLACEHOLDER = re.compile(
    r"^selecione\s+(?:uma\s+)?fundamenta[cç][aã]o$", re.IGNORECASE
)


def _has_diploma_v1(
    reference: Mapping[str, Any], kind: str, number: str | None, year: str | None
) -> bool:
    diploma = reference.get("diploma") or {}
    return (
        diploma.get("type") == kind
        and diploma.get("number") == number
        and diploma.get("year") == year
    )


def _is_article_v1(reference: Mapping[str, Any], number: str, suffix: str | None = None) -> bool:
    return reference.get("article") == number and (reference.get("suffix") or None) == suffix


def _has_article_v1(
    references: Sequence[Mapping[str, Any]],
    kind: str,
    number: str | None,
    year: str | None,
    article: str,
    suffix: str | None = None,
    predicate=None,
) -> bool:
    for reference in references:
        if not _has_diploma_v1(reference, kind, number, year):
            continue
        if not _is_article_v1(reference, article, suffix):
            continue
        if predicate is not None and not predicate(reference):
            continue
        return True
    return False


def _has_paragraph_v1(reference: Mapping[str, Any], paragraph: str) -> bool:
    return reference.get("paragraph") == paragraph


def _has_incisos_v1(reference: Mapping[str, Any], incisos: Sequence[str]) -> bool:
    return all(inciso in (reference.get("incisos") or []) for inciso in incisos)


def _source_families(references: Sequence[Mapping[str, Any]]) -> list[str]:
    families: list[str] = []
    has_ec41_base = _has_article_v1(references, "ec", "41", "2003", "6") and _has_article_v1(
        references, "ec", "41", "2003", "7"
    )
    has_ec41_part = any(
        _has_diploma_v1(reference, "ec", "41", "2003")
        and reference.get("article") in {"6", "7"}
        and (reference.get("suffix") or None) is None
        for reference in references
    )
    has_cf_p5 = _has_article_v1(
        references, "cf", None, None, "40", None, lambda reference: _has_paragraph_v1(reference, "5")
    )
    if _has_article_v1(references, "ec", "41", "2003", "6", "a"):
        families.append("EC41_ART6A")
    if has_ec41_base or has_ec41_part:
        families.append("EC41_COM_P5" if has_cf_p5 else "EC41_SEM_P5")
    if _has_article_v1(references, "ec", "47", "2005", "3", None):
        families.append("EC47_ART3")
    if _has_article_v1(
        references,
        "cf",
        None,
        None,
        "40",
        None,
        lambda reference: _has_paragraph_v1(reference, "1") and _has_incisos_v1(reference, ["2"]),
    ):
        families.append("CF40_P1_II")
    if has_cf_p5 and not has_ec41_part:
        families.append("CF40_P5")
    return list(dict.fromkeys(families))


def _family_for_option(option: Mapping[str, Any], references: Sequence[Mapping[str, Any]]) -> str:
    declared = as_text(option.get("rule_id"))
    if declared in {"EC41_ART6A", "CF40_P1_II"}:
        return declared
    if declared in RULE_IDS:
        return declared
    families = _source_families(references)
    return families[0] if families else "OTHER"


def _candidate_rule_id(option: Mapping[str, Any], candidate_family: str) -> str | None:
    declared = as_text(option.get("rule_id"))
    if declared in RULE_IDS:
        return declared
    return candidate_family if candidate_family in RULE_IDS else None


def _diploma_key(diploma: Mapping[str, Any] | None) -> str | None:
    if not diploma:
        return None
    return f"{diploma.get('type')}:{as_text(diploma.get('number'))}:{as_text(diploma.get('year'))}"


def _diploma_family_key(reference: Mapping[str, Any]) -> str | None:
    kind = (reference.get("diploma") or {}).get("type")
    if kind not in {"ec", "ece", "cf", "ce"}:
        return None
    return _diploma_key(reference.get("diploma"))


def _diploma_family_keys(references: Sequence[Mapping[str, Any]]) -> set[str]:
    return {
        key for key in (_diploma_family_key(reference) for reference in references) if key
    }


def _legacy_diploma_family_conflict(references: Sequence[Mapping[str, Any]]) -> bool:
    types = {(reference.get("diploma") or {}).get("type") for reference in references}
    return ({"ec"} <= types and "ece" in types) or ({"cf"} <= types and "ce" in types)


def _article_key(reference: Mapping[str, Any]) -> str:
    return (
        f"{_diploma_key(reference.get('diploma'))}:{as_text(reference.get('article'))}"
        f":{as_text(reference.get('suffix'))}"
    )


def _reference_key(reference: Mapping[str, Any]) -> str:
    incisos = ",".join(sorted(reference.get("incisos") or []))
    qualifiers = ",".join(sorted(reference.get("qualifiers") or []))
    return "|".join(
        [_article_key(reference), as_text(reference.get("paragraph")), incisos, qualifiers]
    )


def _set_intersection(left: Sequence[str], right: Sequence[str]) -> list[str]:
    right_set = set(right)
    return [value for value in dict.fromkeys(left) if value in right_set]


def _dice_score(left: Any, right: Any) -> int:
    left_tokens = {token for token in normalize_legal_text(left).split() if token}
    right_tokens = {token for token in normalize_legal_text(right).split() if token}
    if not left_tokens or not right_tokens:
        return 0
    intersection = sum(1 for token in left_tokens if token in right_tokens)
    return js_round((2 * intersection * 10) / (len(left_tokens) + len(right_tokens)))


def _has_contradiction(references: Sequence[Mapping[str, Any]]) -> bool:
    years_by_device: dict[str, set[str]] = {}
    for reference in references:
        diploma = reference.get("diploma") or {}
        key = f"{as_text(diploma.get('type'))}:{as_text(diploma.get('number'))}"
        year = diploma.get("year")
        if not key or not year:
            continue
        years_by_device.setdefault(key, set()).add(str(year))
    return any(len(years) > 1 for years in years_by_device.values())


def _citations_for(context: Any) -> list[dict[str, Any]]:
    pages = context.get("pages") if isinstance(context, Mapping) else None
    pages = pages if isinstance(pages, list) else []
    seen: set[str] = set()
    citations: list[dict[str, Any]] = []
    for page in pages:
        citation = page.get("citation") if isinstance(page, Mapping) else None
        if not isinstance(citation, Mapping):
            continue
        key = json.dumps(citation, sort_keys=True, ensure_ascii=False, default=str)
        if key in seen:
            continue
        seen.add(key)
        citations.append(dict(citation))
    return citations


def _selectable_options(options: Any) -> list[dict[str, Any]]:
    source = options if isinstance(options, list) else []
    selected: list[dict[str, Any]] = []
    # JavaScript's ``.map(optionParts)`` passes the index as the second argument,
    # so ``option.index`` is populated for every selectable option.
    for index, option in enumerate(source):
        parts = _option_parts(option, index)
        if parts.get("selectable") is False:
            continue
        if not as_text(parts.get("value")).strip() or not as_text(parts.get("label")).strip():
            continue
        if _SELECT_PLACEHOLDER.match(as_text(parts.get("label")).strip()):
            continue
        selected.append(parts)
    return selected


def _zero_ranking(options: Any, reason: str) -> list[dict[str, Any]]:
    return [
        {
            "option_index": option.get("index"),
            "option_value": option.get("value"),
            "option_label": option.get("label"),
            "rule_id": option.get("rule_id") if option.get("rule_id") in RULE_IDS else None,
            "score": 0,
            "method": "none",
            "reasons": [reason],
        }
        for option in _selectable_options(options)
    ]


def _base_decision(
    context: Any,
    reasons: Sequence[str] | None = None,
    ranking: Sequence[Mapping[str, Any]] | None = None,
    score: float = 0,
    decision_state: str = "NO_COMPATIBLE_CANDIDATE",
) -> dict[str, Any]:
    reason_list = list(reasons or [])
    return {
        "status": "pending",
        "decision_state": decision_state,
        "automatic": False,
        "method": "none",
        "rule_id": None,
        "option_value": None,
        "option_label": None,
        "class_id": None,
        "confidence": 0,
        "margin": 0,
        "reason": reason_list[0] if reason_list else None,
        "score": score,
        "reasons": reason_list,
        "warnings": [],
        "ranking": [dict(entry) for entry in (ranking or [])],
        "citations": _citations_for(context),
        "rules_version": RULES_VERSION,
    }


def _operative_text_from_context(context: Any) -> str:
    text = as_text(context.get("operative_text")) if isinstance(context, Mapping) else ""
    markers = [match.start() for match in re.finditer(r"\bresolve\s*:", text, re.IGNORECASE)]
    return text[markers[-1] :].strip() if markers else text


def _score_candidate(
    source_references: Sequence[Mapping[str, Any]],
    option: Mapping[str, Any],
    operative_text: str,
    source_family: str,
) -> dict[str, Any]:
    candidate_references = parse_legal_references(option.get("label"))
    candidate_family = _family_for_option(option, candidate_references)
    exact_text = normalize_legal_text(operative_text) == normalize_legal_text(option.get("label"))
    source_families = _diploma_family_keys(source_references)
    candidate_families = _diploma_family_keys(candidate_references)
    shared_diploma_family = any(family in candidate_families for family in source_families)
    if source_family == "OTHER":
        family_matches = (
            candidate_family == "OTHER"
            and len(source_families) > 0
            and len(candidate_families) > 0
            and shared_diploma_family
        )
    else:
        family_matches = (
            candidate_family == source_family
            and (
                len(candidate_families) == 0
                or len(source_families) == 0
                or shared_diploma_family
            )
            and not _legacy_diploma_family_conflict(
                [*source_references, *candidate_references]
            )
        )
    if not family_matches:
        return {
            "candidate_references": candidate_references,
            "candidate_family": candidate_family,
            "score": 0,
            "reasons": ["family-mismatch"],
            "method": "none",
        }

    source_keys = {_reference_key(reference) for reference in source_references}
    candidate_keys = {_reference_key(reference) for reference in candidate_references}
    structurally_equivalent = len(source_keys) == len(candidate_keys) and all(
        key in candidate_keys for key in source_keys
    )
    complete_references = sum(1 for key in candidate_keys if key in source_keys)
    source_diplomas = [
        key for key in (_diploma_key(reference.get("diploma")) for reference in source_references) if key
    ]
    candidate_diplomas = [
        key
        for key in (_diploma_key(reference.get("diploma")) for reference in candidate_references)
        if key
    ]
    diploma_matches = len(_set_intersection(source_diplomas, candidate_diplomas))
    source_articles = [_article_key(reference) for reference in source_references]
    candidate_articles = [_article_key(reference) for reference in candidate_references]
    article_matches = len(_set_intersection(source_articles, candidate_articles))
    qualifiers: set[str] = set()
    for candidate in candidate_references:
        source = next(
            (
                reference
                for reference in source_references
                if _article_key(reference) == _article_key(candidate)
            ),
            None,
        )
        if source is None:
            continue
        paragraph = candidate.get("paragraph")
        if paragraph and paragraph == source.get("paragraph"):
            qualifiers.add(f"paragraph:{paragraph}")
        for value in _set_intersection(
            candidate.get("incisos") or [], source.get("incisos") or []
        ):
            qualifiers.add(f"inciso:{value}")
        for value in _set_intersection(
            candidate.get("qualifiers") or [], source.get("qualifiers") or []
        ):
            qualifiers.add(f"qualifier:{value}")
    qualifier_matches = len(qualifiers)
    lexical = _dice_score(operative_text, option.get("label"))
    score = (
        complete_references * 40
        + diploma_matches * 25
        + article_matches * 10
        + qualifier_matches * 5
        + lexical
    )
    reasons: list[str] = []
    if complete_references > 0:
        reasons.append(f"references:{complete_references * 40}")
    if diploma_matches > 0:
        reasons.append(f"diplomas:{diploma_matches * 25}")
    if article_matches > 0:
        reasons.append(f"articles:{article_matches * 10}")
    if qualifier_matches > 0:
        reasons.append(f"qualifiers:{qualifier_matches * 5}")
    if lexical > 0:
        reasons.append(f"dice:{lexical}")
    same_family = source_family == candidate_family and source_family != "OTHER"
    if exact_text:
        method = "exact"
    elif structurally_equivalent:
        method = "rule" if same_family else "exact"
    elif same_family:
        method = "rule"
    else:
        method = "similarity" if score > 0 else "none"
    return {
        "candidate_references": candidate_references,
        "candidate_family": candidate_family,
        "score": score,
        "reasons": reasons if reasons else ["no-positive-signal"],
        "method": method,
    }


def is_automatic_legal_decision(decision: Any) -> bool:
    """Shared guard: only a complete, unambiguous, high-confidence decision passes."""

    if not isinstance(decision, Mapping):
        return False
    confidence = decision.get("confidence")
    margin = decision.get("margin")
    numbers = (int, float)
    return (
        decision.get("status") == "selected"
        and decision.get("decision_state") == "AUTO_SELECTED"
        and decision.get("rules_version") == RULES_VERSION
        and decision.get("method") != "none"
        and decision.get("hard_conflict") is not True
        and isinstance(confidence, numbers)
        and not isinstance(confidence, bool)
        and math.isfinite(confidence)
        and confidence >= 0.90
        and isinstance(margin, numbers)
        and not isinstance(margin, bool)
        and math.isfinite(margin)
        and margin >= 0.12
    )


def _adapt_crosswalk_decision(
    context: Any, operative_text: str, classification: Mapping[str, Any]
) -> dict[str, Any]:
    references = parse_legal_references(operative_text)
    selected = classification.get("status") == "selected"
    ranking = []
    crosswalk_ranking = classification.get("ranking") or []
    for index, candidate in enumerate(crosswalk_ranking):
        class_id = candidate.get("class_id")
        ranking.append(
            {
                "option_index": candidate.get("option_index"),
                "option_value": candidate.get("option_value"),
                "option_label": candidate.get("option_label"),
                "class_id": class_id,
                "confidence": candidate.get("confidence"),
                "rule_id": class_id if class_id in RULE_IDS else None,
                "score": js_round(float(candidate.get("score") or 0) * 100),
                "margin": classification.get("margin"),
                "hard_conflict": candidate.get("hard_conflict") is True,
                "rejected": candidate.get("rejected") is True,
                "method": candidate.get("method") if (selected and index == 0) else "none",
                "reasons": candidate.get("reasons"),
                "warnings": candidate.get("warnings"),
            }
        )
    classification_reasons = classification.get("reasons") or []
    classification_warnings = classification.get("warnings") or []
    decision: dict[str, Any] = {
        "status": "selected" if selected else "pending",
        "automatic": bool(selected and classification.get("automatic") is True),
        "decision_state": classification.get("decision_state")
        or (
            "AUTO_SELECTED"
            if selected
            else (
                "REVIEW_REQUIRED"
                if classification.get("status") == "review"
                else "NO_COMPATIBLE_CANDIDATE"
            )
        ),
        "method": classification.get("method") if selected else "none",
        "rule_id": classification.get("class_id")
        if (selected and classification.get("class_id") in RULE_IDS)
        else None,
        "option_value": classification.get("option_value") if selected else None,
        "option_label": classification.get("option_label") if selected else None,
        "class_id": classification.get("class_id"),
        "score": js_round(float(classification.get("confidence") or 0) * 100),
        "confidence": classification.get("confidence"),
        "margin": classification.get("margin"),
        "reason": classification.get("reason"),
        "hard_conflict": classification.get("hard_conflict") is True,
        "reasons": [*classification_reasons, *classification_warnings],
        "warnings": list(classification_warnings),
        "ranking": ranking,
        "citations": _citations_for(context),
        "rules_version": RULES_VERSION,
        "references": references,
        "documentary_foundation": {
            "operative_text": operative_text,
            "references": (classification.get("profile") or {}).get("references"),
            "profile": classification.get("profile"),
        },
        "portal_classification": {
            "option_value": classification.get("option_value"),
            "option_label": classification.get("option_label"),
            "class_id": classification.get("class_id"),
            "method": classification.get("method"),
            "confidence": classification.get("confidence"),
            "margin": classification.get("margin"),
            "reasons": list(classification_reasons),
            "warnings": list(classification_warnings),
        },
    }
    if not selected:
        decision["reasons"].append(classification.get("reason") or "manual-review-required")
    # Defense in depth: never publish an automatic selection the shared guard
    # would refuse to write.
    if decision["automatic"] and not is_automatic_legal_decision(decision):
        decision["status"] = "pending"
        decision["automatic"] = False
        decision["option_value"] = None
        decision["option_label"] = None
        decision["method"] = "none"
        decision["decision_state"] = "REVIEW_REQUIRED"
        decision["reason"] = "manual-review-required"
        decision["reasons"].append("manual-review-required")
    return decision


def resolve_legal_foundation(
    context: Mapping[str, Any] | None = None, options: Any = None
) -> dict[str, Any]:
    """Python owner of the legal foundation decision for one act."""

    operative_text = _operative_text_from_context(context)
    if (
        not isinstance(context, Mapping)
        or context.get("resolution_status") != "complete"
        or not operative_text.strip()
    ):
        return _base_decision(
            context, ["context-incomplete"], _zero_ranking(options, "context-incomplete")
        )
    references = parse_legal_references(operative_text)
    if not references:
        return _base_decision(
            context, ["no-legal-references"], _zero_ranking(options, "no-legal-references")
        )
    if any(not reference.get("complete") for reference in references):
        return _base_decision(
            context, ["reference-incomplete"], _zero_ranking(options, "reference-incomplete")
        )
    if _has_contradiction(references):
        return _base_decision(
            context, ["contradictory-reference"], _zero_ranking(options, "contradictory-reference")
        )
    cargo = context.get("cargo")
    if cargo is None:
        fields = context.get("fields")
        cargo_field = fields.get("cargo") if isinstance(fields, Mapping) else None
        cargo = cargo_field.get("form_value") if isinstance(cargo_field, Mapping) else None
    if cargo is None:
        cargo = ""
    classification = classify_portal_legal_foundation(
        operative_text=operative_text,
        cargo=cargo,
        options=options,
        hints=context.get("hints") or {},
    )
    return _adapt_crosswalk_decision(context, operative_text, classification)
