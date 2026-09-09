const COMBINING_MARKS = /\p{M}+/gu;
const NON_LEGAL_SEPARATOR = /[^\p{L}\p{N}/]+/gu;
const ROMAN_TOKEN = /^[ivxlcdm]+$/u;

const ROMAN_VALUES = Object.freeze({
  i: 1,
  v: 5,
  x: 10,
  l: 50,
  c: 100,
  d: 500,
  m: 1000,
});

const ROMAN_DIGITS = Object.freeze([
  [1000, "m"],
  [900, "cm"],
  [500, "d"],
  [400, "cd"],
  [100, "c"],
  [90, "xc"],
  [50, "l"],
  [40, "xl"],
  [10, "x"],
  [9, "ix"],
  [5, "v"],
  [4, "iv"],
  [1, "i"],
]);

const BENEFITS = Object.freeze([
  ["aposentadoria", "aposentadoria"],
  ["pensao", "pensao"],
  ["reforma", "reforma"],
  ["abono", "abono"],
  ["auxilio", "auxilio"],
]);

const PROPORTIONS = Object.freeze([
  ["integral", "integral"],
  ["integrais", "integral"],
  ["integralidade", "integral"],
  ["proporcional", "proporcional"],
  ["proporcionais", "proporcional"],
  ["proporcionalidade", "proporcional"],
  ["especial", "especial"],
  ["especiais", "especial"],
  ["especialidade", "especial"],
]);

function asText(value) {
  return value === null || value === undefined ? "" : String(value);
}

function romanToArabic(token) {
  if (!ROMAN_TOKEN.test(token)) {
    return null;
  }

  let total = 0;
  for (let index = 0; index < token.length; index += 1) {
    const current = ROMAN_VALUES[token[index]];
    const next = ROMAN_VALUES[token[index + 1]] ?? 0;
    total += current < next ? -current : current;
  }

  if (total < 1 || total > 3999) {
    return null;
  }

  let remainder = total;
  let canonical = "";
  for (const [value, digits] of ROMAN_DIGITS) {
    while (remainder >= value) {
      canonical += digits;
      remainder -= value;
    }
  }

  return canonical === token ? String(total) : null;
}

function canonicalizeTokens(tokens) {
  const canonical = tokens.map((token, index) => {
    const previous = tokens[index - 1];
    const roman = romanToArabic(token);

    if (roman !== null && (
      token.length > 1
      || previous === "inciso"
      || previous === "incisos"
      || previous === "a"
      || tokens[index - 2] === "inciso"
      || tokens[index - 2] === "incisos"
    )) {
      return roman;
    }
    return token;
  });

  const result = [];
  const seenIncisosByArticle = new Map();
  let currentArticle = "without-article";

  for (let index = 0; index < canonical.length;) {
    const token = canonical[index];
    if (token === "artigo" && /^\d+$/u.test(canonical[index + 1] ?? "")) {
      currentArticle = canonical[index + 1];
    }
    if ((token === "inciso" || token === "incisos") && /^\d+$/u.test(canonical[index + 1] ?? "")) {
      const seenIncisos = seenIncisosByArticle.get(currentArticle) ?? new Set();
      seenIncisosByArticle.set(currentArticle, seenIncisos);
      let cursor = index + 1;
      while (cursor < canonical.length) {
        const number = canonical[cursor];
        if (!/^\d+$/u.test(number)) {
          if (number === "e" || number === "and") {
            cursor += 1;
            continue;
          }
          break;
        }

        const key = number;
        if (!seenIncisos.has(key)) {
          result.push("inciso", number);
          seenIncisos.add(key);
        }
        cursor += 1;
      }
      index = cursor;
      continue;
    }

    result.push(token);
    index += 1;
  }

  return result;
}

/**
 * Returns a comparison-only legal-text signature. The caller must retain the
 * original value for display and persistence; this function is deliberately
 * pure and never returns a display value.
 */
export function normalizeLegalText(value) {
  let text = asText(value)
    .normalize("NFKD")
    .replace(COMBINING_MARKS, "")
    .toLowerCase();

  text = text.replace(
    /(\d+)\s*[ºª°o]\s*[-–]\s*([a-z])(?=\s|[^\p{L}\p{N}]|$)/gu,
    "$1 article suffix $2",
  );

  text = text
    .replace(/§/gu, " paragrafo ")
    .replace(/\barts\s*\.\s*/gu, " artigos ")
    .replace(/\bart\s*\.\s*/gu, " artigo ")
    .replace(/\bart\b/gu, " artigo ")
    .replace(/\bpar\s*\.\s*/gu, " paragrafo ")
    .replace(/\binc\s*\.\s*/gu, " inciso ")
    .replace(/\bn\s*(?:\.\s*)?[º°o]\s*/gu, " numero ")
    .replace(/(\d+)\s*[ºª°o]\s*[-–]\s*([a-z])(?=\s|[^\p{L}\p{N}]|$)/gu, "$1$2")
    .replace(/(\d+)\s*[-–]\s*([a-z])(?=\s|[^\p{L}\p{N}]|$)/gu, "$1$2")
    .replace(/(\d+)\s*[ºª°o](?=\s|[^\p{L}\p{N}]|$)/gu, "$1")
    .replace(/(\d+)[oa](?=\s|[^\p{L}\p{N}]|$)/gu, "$1")
    .replace(/\baposentacao\b/gu, " aposentadoria ")
    .replace(/\bece\b/gu, " emenda constitucional estadual ")
    .replace(/\bec\b/gu, " emenda constitucional ")
    .replace(/\bcf\b/gu, " constituicao federal ")
    .replace(/\bce\b/gu, " constituicao estadual ")
    .replace(/\bc\s*\/\s*c\b/gu, " combinado com ")
    .replace(/\blce?\b/gu, " lei complementar ")
    .replace(/\bincisos\b/gu, " incisos ")
    .replace(/\bparagrafos\b/gu, " paragrafos ");

  text = text.replace(NON_LEGAL_SEPARATOR, " ").trim();
  if (!text) {
    return "";
  }

  return canonicalizeTokens(text.split(/\s+/u))
    .join(" ")
    .replace(/\b(\d+)\s+article\s+suffix\s+([a-z])\b/gu, "$1$2");
}

function firstMatchingValue(text, patterns) {
  for (const [pattern, value] of patterns) {
    if (new RegExp(`\\b${pattern}\\b`, "u").test(text)) {
      return value;
    }
  }
  return null;
}

function firstNumberAfter(tokens, marker) {
  const index = tokens.indexOf(marker);
  if (index === -1) {
    return null;
  }

  for (let cursor = index + 1; cursor < tokens.length; cursor += 1) {
    if (/^\d+$/u.test(tokens[cursor])) {
      return tokens[cursor];
    }
    if (!["de", "do", "da", "e", "and"].includes(tokens[cursor])) {
      break;
    }
  }
  return null;
}

function extractIncisos(tokens) {
  const incisos = [];
  for (let index = 0; index < tokens.length - 1; index += 1) {
    if (tokens[index] !== "inciso" || !/^\d+$/u.test(tokens[index + 1])) {
      continue;
    }
    if (!incisos.includes(tokens[index + 1])) {
      incisos.push(tokens[index + 1]);
    }
  }
  return incisos;
}

function canonicalDiplomaType(type) {
  if (type === "emenda constitucional estadual") {
    return "ece";
  }
  if (type === "emenda constitucional") {
    return "ec";
  }
  if (type === "lei complementar estadual" || type === "lei complementar") {
    return "lei complementar";
  }
  return type;
}

function extractDiplomas(normalizedText) {
  const diplomaPattern = /\b(emenda constitucional estadual|emenda constitucional|lei complementar estadual|lei complementar|lei|decreto|resolucao|portaria)\s+(?:numero\s+)?(\d+(?:\/\d{2,4})?)/gu;
  const diplomas = [];
  for (const match of normalizedText.matchAll(diplomaPattern)) {
    const type = canonicalDiplomaType(match[1]);
    const value = `${type} ${match[2]}`;
    if (!diplomas.includes(value)) {
      diplomas.push(value);
    }
  }
  return diplomas;
}

/**
 * Extracts stable, small legal signals for the matcher. It intentionally
 * omits the source text and citation so callers cannot mistake a signal for
 * the documentary value shown to the user.
 */
export function extractLegalSignals(value) {
  const normalized = normalizeLegalText(value);
  const tokens = normalized ? normalized.split(/\s+/u) : [];

  return {
    benefit: firstMatchingValue(normalized, BENEFITS),
    modality: firstMatchingValue(normalized, [
      ["tempo\\s+de\\s+contribuicao", "tempo de contribuicao"],
      ["incapacidade\\s+permanente", "incapacidade permanente"],
      ["invalidez", "invalidez"],
      ["por\\s+idade", "idade"],
      ["compulsoria", "compulsoria"],
      ["voluntaria", "voluntaria"],
    ]),
    proportion: firstMatchingValue(normalized, PROPORTIONS),
    professor: /\b(?:professor(?:a|es|as)?|magisterio|docente)\b/u.test(normalized),
    article: firstNumberAfter(tokens, "artigo"),
    paragraph: firstNumberAfter(tokens, "paragrafo"),
    incisos: extractIncisos(tokens),
    diplomas: extractDiplomas(normalized),
  };
}
