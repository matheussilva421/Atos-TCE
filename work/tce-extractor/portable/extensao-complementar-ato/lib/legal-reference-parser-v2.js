const ROMAN_VALUES = Object.freeze({
  i: 1,
  v: 5,
  x: 10,
  l: 50,
  c: 100,
  d: 500,
  m: 1000,
});

const DIPLOMA_PATTERN = /\b(emenda\s+constitucional\s+estadual|emenda\s+constitucional|lei\s+complementar\s+estadual|lei\s+complementar(?:\s+nacional)?|constituicao\s+federal|constituicao\s+estadual|ece|ec|lce|lc|cf|ce|lei)\b/giu;
const ARTICLE_PATTERN = /\bart(?:igo|igos)?s?\.?\s*(\d+)\s*(?:º|ª|o)?\s*(?:[-–]\s*([a-z]))?/giu;
const PARAGRAPH_PATTERN = /§{1,2}\s*([\d]+|unico)(?:º|ª|o)?(?:\s*(?:e|,|a)\s*([\d]+|unico)(?:º|ª|o)?)*/giu;

function asText(value) {
  return value === null || value === undefined ? "" : String(value);
}

function normalizeSource(value) {
  return asText(value)
    .normalize("NFKD")
    .replace(/\p{M}+/gu, "")
    .toLowerCase()
    .replace(/[–—]/gu, "-")
    .replace(/\s+/gu, " ");
}

export function normalizeLegalYear(value) {
  const text = asText(value).trim();
  if (!/^\d{2,4}$/u.test(text)) return null;
  if (text.length === 4) return text;
  const year = Number(text);
  return String(year >= 50 ? 1900 + year : 2000 + year);
}

function romanToArabic(value) {
  const token = asText(value).toLowerCase();
  if (!/^[ivxlcdm]+$/u.test(token)) return null;

  let total = 0;
  for (let index = 0; index < token.length; index += 1) {
    const current = ROMAN_VALUES[token[index]];
    const next = ROMAN_VALUES[token[index + 1]] ?? 0;
    total += current < next ? -current : current;
  }
  return total > 0 ? String(total) : null;
}

function parseOrdinalList(value) {
  const tokens = asText(value).toLowerCase().match(/[ivxlcdm]+|\d+/gu) ?? [];
  const numbers = [];
  for (let index = 0; index < tokens.length; index += 1) {
    const current = /^\d+$/u.test(tokens[index])
      ? tokens[index]
      : romanToArabic(tokens[index]);
    if (current === null) continue;
    const connector = asText(value).toLowerCase();
    const next = tokens[index + 1];
    if (["a", "até", "ate"].some((word) => connector.includes(`${tokens[index]} ${word} ${next}`))) {
      const end = /^\d+$/u.test(next ?? "") ? next : romanToArabic(next);
      if (end !== null) {
        const first = Number(current);
        const last = Number(end);
        const step = first <= last ? 1 : -1;
        for (let item = first; item !== last + step; item += step) {
          if (!numbers.includes(String(item))) numbers.push(String(item));
        }
        index += 1;
        continue;
      }
    }
    if (!numbers.includes(current)) numbers.push(current);
  }
  return numbers;
}

function diplomaType(rawType) {
  const type = rawType.toLowerCase();
  if (type === "emenda constitucional estadual" || type === "ece") return "ece";
  if (type === "emenda constitucional" || type === "ec") return "ec";
  if (type === "constituicao federal" || type === "cf") return "cf";
  if (type === "constituicao estadual" || type === "ce") return "ce";
  if (type === "lei complementar estadual" || type === "lce") return "lce";
  if (type.startsWith("lei complementar") || type === "lc") return "lc";
  if (type === "lei") return "lei";
  return "unknown";
}

function collectDiplomas(normalized) {
  const diplomas = [];
  for (const match of normalized.matchAll(DIPLOMA_PATTERN)) {
    const rawType = match[1];
    const type = diplomaType(rawType);
    const tail = normalized.slice(match.index + match[0].length, match.index + match[0].length + 40);
    const numberMatch = tail.match(/^\s*(?:n(?:umero)?[ºo]?\s*)?([\d.]+)(?:\s*\/\s*(\d{2,4}))?/iu);
    diplomas.push({
      start: match.index,
      end: match.index + match[0].length,
      type,
      number: numberMatch?.[1] ?? null,
      year: normalizeLegalYear(numberMatch?.[2]),
    });
  }
  return diplomas;
}

function collectArticles(normalized) {
  const articles = [];
  for (const match of normalized.matchAll(ARTICLE_PATTERN)) {
    articles.push({
      start: match.index,
      end: match.index + match[0].length,
      number: match[1],
      suffix: match[2] ?? null,
    });
  }
  return articles;
}

function diplomaForArticle(article, articles, diplomas, normalized) {
  const nextArticle = articles.find((candidate) => candidate.start > article.start);
  const nextDiploma = diplomas.find((candidate) => candidate.start >= article.end);
  if (nextDiploma && (!nextArticle || nextDiploma.start < nextArticle.start)) {
    return nextDiploma;
  }

  if (nextArticle) {
    const sharedDiploma = diplomas.find((candidate) => candidate.start >= nextArticle.end);
    if (sharedDiploma) return sharedDiploma;
  }

  const previous = diplomas.filter((candidate) => candidate.start < article.start).at(-1);
  if (previous) return previous;

  const clauseStart = Math.max(
    normalized.lastIndexOf(";", article.start),
    normalized.lastIndexOf(".", article.start),
  );
  return diplomas.find((candidate) => candidate.start >= clauseStart && candidate.start < article.start) ?? null;
}

function blankParagraph(number) {
  return { number, incisos: [], alineas: [], items: [] };
}

function collectMarkers(segment, marker, pattern) {
  return [...segment.matchAll(pattern)].map((match) => ({
    start: match.index,
    end: match.index + match[0].length,
    values: marker === "paragraph"
      ? parseOrdinalList(match[0])
      : parseOrdinalList(match[1] ?? match[0]),
  }));
}

function addUnique(target, values) {
  for (const value of values) {
    if (!target.includes(value)) target.push(value);
  }
}

function detailMarkers(segment) {
  const paragraphMarkers = collectMarkers(segment, "paragraph", PARAGRAPH_PATTERN);
  const incisoPattern = /\bincisos?\s+(.+?)(?=§|\balineas?\b|\bitens?\b|\bart(?:igo|igos)?\b|\b(?:da|de|do)\b|$)/giu;
  const alineaPattern = /\balineas?\s+(.+?)(?=§|\bincisos?\b|\bitens?\b|\bart(?:igo|igos)?\b|\b(?:da|de|do)\b|$)/giu;
  const itemPattern = /\bitens?\s+(.+?)(?=§|\bincisos?\b|\balineas?\b|\bart(?:igo|igos)?\b|\b(?:da|de|do)\b|$)/giu;
  const incisos = [...segment.matchAll(incisoPattern)].map((match) => ({
    start: match.index,
    end: match.index + match[0].length,
    values: parseOrdinalList(match[1]),
  }));
  const alineas = [...segment.matchAll(alineaPattern)].map((match) => ({
    start: match.index,
    end: match.index + match[0].length,
    values: (match[1].match(/[a-z]/giu) ?? []).map((value) => value.toLowerCase()),
  }));
  const items = [...segment.matchAll(itemPattern)].map((match) => ({
    start: match.index,
    end: match.index + match[0].length,
    values: parseOrdinalList(match[1]),
  }));

  const paragraphs = [];
  for (const marker of paragraphMarkers) {
    for (const number of marker.values) {
      paragraphs.push({ ...blankParagraph(number), start: marker.start, end: marker.end });
    }
  }
  paragraphs.sort((left, right) => left.start - right.start);

  const topLevelIncisos = [];
  const topLevelAlineas = [];
  const topLevelItems = [];
  for (const marker of incisos) {
    addUnique(topLevelIncisos, marker.values);
    const paragraph = paragraphs.findLast((candidate) => candidate.start <= marker.start);
    if (paragraph) addUnique(paragraph.incisos, marker.values);
  }
  for (const marker of alineas) {
    addUnique(topLevelAlineas, marker.values);
    const paragraph = paragraphs.findLast((candidate) => candidate.start <= marker.start);
    if (paragraph) addUnique(paragraph.alineas, marker.values);
  }
  for (const marker of items) {
    addUnique(topLevelItems, marker.values);
    const paragraph = paragraphs.findLast((candidate) => candidate.start <= marker.start);
    if (paragraph) addUnique(paragraph.items, marker.values);
  }

  return {
    paragraphs: paragraphs.map(({ start, end, ...paragraph }) => paragraph),
    incisos: topLevelIncisos,
    alineas: topLevelAlineas,
    items: topLevelItems,
  };
}

function articleSegment(article, nextArticle, normalized) {
  const end = nextArticle?.start ?? normalized.length;
  return normalized.slice(article.end, end);
}

function bridgeParagraphs(article, previousArticle, normalized) {
  if (!previousArticle) return [];
  const bridge = normalized.slice(previousArticle.end, article.start);
  if (!/\b(?:do|de)\s*$/iu.test(bridge.trim())) return [];
  const details = detailMarkers(bridge);
  const last = details.paragraphs.at(-1);
  if (!last) return [];
  const lastParagraph = { ...last };
  const paragraphStart = bridge.lastIndexOf("§", bridge.length);
  const beforeLast = paragraphStart >= 0 ? bridge.slice(0, paragraphStart) : bridge;
  const precedingInciso = [...beforeLast.matchAll(/\bincisos?\s+(.+?)(?=§|\balineas?\b|\bitens?\b|\bart(?:igo|igos)?\b|\b(?:da|de|do)\b|$)/giu)]
    .at(-1)?.[1];
  const lastInciso = parseOrdinalList(precedingInciso);
  if (lastInciso.length > 0) lastParagraph.incisos = [lastInciso.at(-1)];
  return [lastParagraph];
}

export function parseLegalReferencesV2(text) {
  const source = asText(text).trim();
  const normalized = normalizeSource(source);
  if (!normalized) return [];

  const articles = collectArticles(normalized);
  const diplomas = collectDiplomas(normalized);
  return articles.map((article, index) => {
    const previousArticle = articles[index - 1] ?? null;
    const nextArticle = articles[index + 1] ?? null;
    const localDetails = detailMarkers(articleSegment(article, nextArticle, normalized));
    const bridge = bridgeParagraphs(article, previousArticle, normalized);
    const paragraphs = [...localDetails.paragraphs, ...bridge];
    const incisos = [...localDetails.incisos];
    const alineas = [...localDetails.alineas];
    const items = [...localDetails.items];
    for (const paragraph of paragraphs) {
      addUnique(incisos, paragraph.incisos);
      addUnique(alineas, paragraph.alineas);
      addUnique(items, paragraph.items);
    }
    const diploma = diplomaForArticle(article, articles, diplomas, normalized);
    return {
      diploma_type: diploma?.type ?? "unknown",
      diploma_number: diploma?.number ?? null,
      diploma_year: diploma?.year ?? null,
      article: article.number,
      article_suffix: article.suffix,
      paragraphs,
      incisos,
      alineas,
      items,
      raw: source,
    };
  });
}
