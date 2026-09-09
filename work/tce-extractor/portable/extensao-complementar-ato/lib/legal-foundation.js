import { normalizeLegalText } from "./normalizer.js";

const RAW_ARTICLE_PATTERN = /\bart(?:s|igo|igos)?\.?\s*(\d+)\s*(?:º|ª|o)?(?:\s*[-–]\s*([a-z]))?/giu;
const ARTICLE_PATTERN = /\bartigos?\s+(\d+)([a-z])?/giu;
const DIPLOMA_PATTERN = /\b(emenda constitucional estadual|emenda constitucional)\s+(?:numero\s+)?(\d+)(?:\s*(?:\/|de)\s*(\d{2,4}))?|\b(constituicao federal|constituicao estadual)\b/giu;
const COMBINED_PATTERN = /\bcombinado\s+com\b/giu;

function asText(value) {
  return value === null || value === undefined ? "" : String(value);
}

function normalizeYear(value) {
  if (!value) return null;
  return value.length === 2 ? `20${value}` : value;
}

function diplomaFromMatch(match) {
  const rawType = match[1] ?? match[4];
  const type = rawType === "emenda constitucional estadual"
    ? "ece"
    : rawType === "constituicao federal"
      ? "cf"
      : rawType === "constituicao estadual"
        ? "ce"
        : "ec";
  return {
    type,
    number: match[2] ?? null,
    year: normalizeYear(match[3]),
  };
}

function collectDiplomas(normalized) {
  return [...normalized.matchAll(DIPLOMA_PATTERN)].map((match) => ({
    start: match.index,
    end: match.index + match[0].length,
    value: diplomaFromMatch(match),
  }));
}

function collectArticles(normalized) {
  const matches = [...normalized.matchAll(ARTICLE_PATTERN)];
  const articles = [];
  matches.forEach((match, index) => {
    const article = {
      start: match.index,
      end: match.index + match[0].length,
      number: match[1],
      suffix: match[2] ?? null,
    };
    articles.push(article);
    if (!/^artigos\b/iu.test(match[0])) return;
    const tailEnd = matches[index + 1]?.index ?? normalized.length;
    const tail = normalized.slice(article.end, tailEnd);
    const extra = tail.match(/^\s*(?:,|e)\s*(\d+)([a-z])?/iu);
    if (extra) {
      const numberStart = article.end + extra.index + extra[0].indexOf(extra[1]);
      articles.push({
        start: numberStart,
        end: numberStart + extra[1].length + (extra[2]?.length ?? 0),
        number: extra[1],
        suffix: extra[2] ?? null,
      });
    }
  });
  return articles.sort((left, right) => left.start - right.start);
}

function clauseAt(normalized, position) {
  const boundaries = [0];
  for (const match of normalized.matchAll(COMBINED_PATTERN)) {
    boundaries.push(match.index + match[0].length);
  }
  boundaries.push(normalized.length);
  const start = boundaries.findLast((boundary) => boundary <= position) ?? 0;
  const end = boundaries.find((boundary) => boundary > position) ?? normalized.length;
  return { start, end };
}

function diplomaForArticle(diplomas, articles, index, normalized) {
  const article = articles[index];
  const previousEnd = articles[index - 1]?.end ?? 0;
  const nextStart = articles[index + 1]?.start ?? Number.POSITIVE_INFINITY;
  const after = diplomas.filter(
    (diploma) => diploma.start >= article.end && diploma.start < nextStart,
  );
  if (after.length > 0 && ["cf", "ce"].includes(after[0].value.type)) {
    const lead = normalized.slice(article.end, after[0].start);
    if (/\b(?:paragrafo|inciso)\b/iu.test(lead)) return after[0].value;
  }
  if (!Number.isFinite(nextStart)) {
    if (after.length > 0) return after[0].value;
  }
  const before = diplomas.filter(
    (diploma) => diploma.start >= previousEnd && diploma.start < article.start,
  );
  if (before.length > 0) return before.at(-1).value;
  const clause = clauseAt(normalized, article.start);
  const forward = diplomas.filter(
    (diploma) => diploma.start >= article.end && diploma.start < clause.end,
  );
  if (forward.length > 0) return forward[0].value;
  const prior = diplomas.filter((diploma) => diploma.start < article.start);
  return prior.at(-1)?.value ?? null;
}

function parseNumberList(value) {
  const numbers = [];
  const tokens = value.match(/\d+|a|e|and/gu) ?? [];
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (!/^\d+$/u.test(token)) continue;
    const next = tokens[index + 1];
    const end = tokens[index + 2];
    if (next === "a" && /^\d+$/u.test(end)) {
      const first = Number(token);
      const last = Number(end);
      const step = first <= last ? 1 : -1;
      for (let number = first; number !== last + step; number += step) {
        if (!numbers.includes(String(number))) numbers.push(String(number));
      }
      index += 2;
      continue;
    }
    if (!numbers.includes(token)) numbers.push(token);
  }
  return numbers;
}

function parseArticleDetails(segment) {
  const paragraphMatch = segment.match(/\bparagrafo\s+(\d+|unico)\b/iu);
  const incisoMatch = segment.match(
    /\bincisos?\s+(.+?)(?=\b(?:paragrafo|artigo|emenda|constituicao|combinado)\b|$)/iu,
  );
  return {
    paragraph: paragraphMatch?.[1]?.toLowerCase() ?? null,
    incisos: incisoMatch ? parseNumberList(incisoMatch[1]) : [],
    qualifiers: /\bambos\b/iu.test(segment) ? ["ambos"] : [],
  };
}

function rawReferenceText(source, rawArticle, nextRawArticle) {
  return source
    .slice(rawArticle.index, nextRawArticle?.index ?? source.length)
    .replace(/\s+e\s*$/iu, "")
    .trim();
}

export function parseLegalReferences(text) {
  const source = asText(text);
  const normalized = normalizeLegalText(source);
  if (!normalized) return [];

  const diplomas = collectDiplomas(normalized);
  const articles = collectArticles(normalized);
  const rawArticles = [...source.matchAll(RAW_ARTICLE_PATTERN)];

  return articles.map((article, index) => {
    const clause = clauseAt(normalized, article.start);
    const detailEnd = articles[index + 1]?.start ?? clause.end;
    const detail = parseArticleDetails(normalized.slice(article.end, detailEnd));
    if (/\bambos\b/iu.test(normalized.slice(clause.start, clause.end))) {
      detail.qualifiers = ["ambos"];
    }
    const diploma = diplomaForArticle(diplomas, articles, index, normalized);
    const rawArticle = rawArticles[index];
    const nextRawArticle = rawArticles[index + 1];
    return {
      raw: rawArticle ? rawReferenceText(source, rawArticle, nextRawArticle) : normalized.slice(article.start, detailEnd),
      diploma,
      article: article.number,
      suffix: article.suffix,
      paragraph: detail.paragraph,
      incisos: detail.incisos,
      qualifiers: detail.qualifiers,
      complete: Boolean(diploma && (diploma.type === "cf" || diploma.type === "ce" || diploma.year)),
    };
  });
}

export const LEGAL_FOUNDATION_RULES_VERSION = "legal-foundation-v1";

const RULE_IDS = new Set(["EC41_SEM_P5", "EC41_COM_P5", "EC47_ART3"]);

function optionParts(option, index) {
  if (option !== null && typeof option === "object") {
    const value = option.value ?? option.label ?? "";
    const label = option.label ?? value;
    return { ...option, index, value, label };
  }
  return { index, value: option, label: option };
}

function hasDiploma(reference, type, number, year) {
  return reference.diploma?.type === type
    && reference.diploma.number === number
    && reference.diploma.year === year;
}

function hasReference(references, predicate) {
  return references.some(predicate);
}

function isArticle(reference, number, suffix = null) {
  return reference.article === number && (reference.suffix ?? null) === suffix;
}

function hasArticle(references, type, number, year, article, suffix = null, predicate = () => true) {
  return hasReference(references, (reference) => (
    hasDiploma(reference, type, number, year)
    && isArticle(reference, article, suffix)
    && predicate(reference)
  ));
}

function hasParagraph(reference, paragraph) {
  return reference.paragraph === paragraph;
}

function sourceFamilies(references) {
  const families = [];
  const hasEc41Base = hasArticle(references, "ec", "41", "2003", "6")
    && hasArticle(references, "ec", "41", "2003", "7");
  const hasEc41Part = hasReference(references, (reference) => (
    hasDiploma(reference, "ec", "41", "2003")
    && ["6", "7"].includes(reference.article)
    && (reference.suffix ?? null) === null
  ));
  const hasCfP5 = hasArticle(
    references,
    "cf",
    null,
    null,
    "40",
    null,
    (reference) => hasParagraph(reference, "5"),
  );

  if (hasArticle(references, "ec", "41", "2003", "6", "a")) {
    families.push("EC41_ART6A");
  }
  if (hasEc41Base || hasEc41Part) families.push(hasCfP5 ? "EC41_COM_P5" : "EC41_SEM_P5");
  if (hasArticle(
    references,
    "ec",
    "47",
    "2005",
    "3",
    null,
  )) {
    families.push("EC47_ART3");
  }
  if (hasArticle(
    references,
    "cf",
    null,
    null,
    "40",
    null,
    (reference) => hasParagraph(reference, "1") && hasIncisos(reference, ["2"]),
  )) {
    families.push("CF40_P1_II");
  }
  if (hasCfP5 && !hasEc41Base) {
    families.push("CF40_P5");
  }
  return [...new Set(families)];
}

function familyForOption(option, references) {
  const declared = String(option.rule_id ?? "");
  if (declared === "EC41_ART6A" || declared === "CF40_P1_II") return declared;
  if (RULE_IDS.has(declared)) return declared;
  return sourceFamilies(references)[0] ?? "OTHER";
}

function diplomaFamilyKey(reference) {
  const type = reference.diploma?.type;
  if (!new Set(["ec", "ece", "cf", "ce"]).has(type)) return null;
  return diplomaKey(reference.diploma);
}

function diplomaFamilyKeys(references) {
  return new Set(references.map(diplomaFamilyKey).filter(Boolean));
}

function hasIncompatibleDiplomaFamilies(references) {
  const types = new Set(references.map((reference) => reference.diploma?.type));
  return (types.has("ec") && types.has("ece"))
    || (types.has("cf") && types.has("ce"));
}

function diplomaKey(diploma) {
  if (!diploma) return null;
  return `${diploma.type}:${diploma.number ?? ""}:${diploma.year ?? ""}`;
}

function articleKey(reference) {
  const key = `${diplomaKey(reference.diploma)}:${reference.article ?? ""}:${reference.suffix ?? ""}`;
  return key;
}

function referenceKey(reference) {
  return [
    articleKey(reference),
    reference.paragraph ?? "",
    [...reference.incisos].sort().join(","),
    [...reference.qualifiers].sort().join(","),
  ].join("|");
}

function setIntersection(left, right) {
  const rightSet = new Set(right);
  return [...new Set(left)].filter((value) => rightSet.has(value));
}

function scoreCandidate(sourceReferences, option, operativeText, sourceFamily) {
  const candidateReferences = parseLegalReferences(option.label);
  const candidateFamily = familyForOption(option, candidateReferences);
  const exactText = normalizeLegalText(operativeText) === normalizeLegalText(option.label);
  const sourceDiplomaFamilies = diplomaFamilyKeys(sourceReferences);
  const candidateDiplomaFamilies = diplomaFamilyKeys(candidateReferences);
  const sharedDiplomaFamily = [...sourceDiplomaFamilies]
    .some((family) => candidateDiplomaFamilies.has(family));
  const familyMatches = sourceFamily === "OTHER"
    ? candidateFamily === "OTHER"
      && sourceDiplomaFamilies.size > 0
      && candidateDiplomaFamilies.size > 0
      && sharedDiplomaFamily
    : candidateFamily === sourceFamily
      && (candidateDiplomaFamilies.size === 0
        || sourceDiplomaFamilies.size === 0
        || sharedDiplomaFamily)
      && !hasIncompatibleDiplomaFamilies([...sourceReferences, ...candidateReferences]);
  if (!familyMatches) {
    return {
      candidateReferences,
      candidateFamily,
      score: 0,
      reasons: ["family-mismatch"],
      method: "none",
    };
  }

  const sourceKeys = new Set(sourceReferences.map(referenceKey));
  const candidateKeys = new Set(candidateReferences.map(referenceKey));
  const structurallyEquivalent = sourceKeys.size === candidateKeys.size
    && [...sourceKeys].every((key) => candidateKeys.has(key));
  const completeReferences = [...candidateKeys].filter((key) => sourceKeys.has(key)).length;
  const sourceDiplomas = sourceReferences.map((reference) => diplomaKey(reference.diploma)).filter(Boolean);
  const candidateDiplomas = candidateReferences.map((reference) => diplomaKey(reference.diploma)).filter(Boolean);
  const diplomaMatches = setIntersection(sourceDiplomas, candidateDiplomas).length;
  const sourceArticles = sourceReferences.map(articleKey);
  const candidateArticles = candidateReferences.map(articleKey);
  const articleMatches = setIntersection(sourceArticles, candidateArticles).length;
  const qualifierMatches = [...new Set(candidateReferences.flatMap((candidate) => {
    const source = sourceReferences.find((reference) => articleKey(reference) === articleKey(candidate));
    if (!source) return [];
    return [
      ...(candidate.paragraph && candidate.paragraph === source.paragraph ? [`paragraph:${candidate.paragraph}`] : []),
      ...setIntersection(candidate.incisos, source.incisos).map((value) => `inciso:${value}`),
      ...setIntersection(candidate.qualifiers, source.qualifiers).map((value) => `qualifier:${value}`),
    ];
  }))].length;
  const lexical = diceScore(operativeText, option.label);
  const score = completeReferences * 40 + diplomaMatches * 25 + articleMatches * 10 + qualifierMatches * 5 + lexical;
  const reasons = [];
  if (completeReferences > 0) reasons.push(`references:${completeReferences * 40}`);
  if (diplomaMatches > 0) reasons.push(`diplomas:${diplomaMatches * 25}`);
  if (articleMatches > 0) reasons.push(`articles:${articleMatches * 10}`);
  if (qualifierMatches > 0) reasons.push(`qualifiers:${qualifierMatches * 5}`);
  if (lexical > 0) reasons.push(`dice:${lexical}`);
  return {
    candidateReferences,
    candidateFamily,
    score,
    reasons: reasons.length > 0 ? reasons : ["no-positive-signal"],
    method: exactText
      ? "exact"
      : structurallyEquivalent
        ? "equivalence"
        : sourceFamily === candidateFamily && sourceFamily !== "OTHER"
          ? "rule"
          : score > 0
            ? "similarity"
            : "none",
  };
}

function diceScore(left, right) {
  const leftTokens = new Set(normalizeLegalText(left).split(/\s+/u).filter(Boolean));
  const rightTokens = new Set(normalizeLegalText(right).split(/\s+/u).filter(Boolean));
  if (leftTokens.size === 0 || rightTokens.size === 0) return 0;
  let intersection = 0;
  for (const token of leftTokens) if (rightTokens.has(token)) intersection += 1;
  return Math.round((2 * intersection * 10) / (leftTokens.size + rightTokens.size));
}

function hasContradiction(references) {
  const yearsByDevice = new Map();
  for (const reference of references) {
    const key = `${reference.diploma?.type ?? ""}:${reference.diploma?.number ?? ""}`;
    const year = reference.diploma?.year;
    if (!key || !year) continue;
    const years = yearsByDevice.get(key) ?? new Set();
    years.add(year);
    yearsByDevice.set(key, years);
  }
  return [...yearsByDevice.values()].some((years) => years.size > 1);
}

function citationsFor(context) {
  const pages = Array.isArray(context?.pages) ? context.pages : [];
  const seen = new Set();
  return pages
    .map((page) => page?.citation)
    .filter((citation) => citation && typeof citation === "object")
    .filter((citation) => {
      const key = JSON.stringify(citation);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function selectableOptions(options) {
  return (Array.isArray(options) ? options : [])
    .map(optionParts)
    .filter((option) => option.selectable !== false && asText(option.value).trim() && asText(option.label).trim())
    .filter((option) => !/^selecione\s+(?:uma\s+)?fundamenta[cç][aã]o$/iu.test(asText(option.label).trim()));
}

function zeroRanking(options, reason) {
  return selectableOptions(options).map((option) => ({
    option_index: option.index,
    option_value: option.value,
    option_label: option.label,
    rule_id: RULE_IDS.has(option.rule_id) ? option.rule_id : null,
    score: 0,
    method: "none",
    reasons: [reason],
  }));
}

function baseDecision(context, reasons = [], ranking = [], score = 0) {
  return {
    status: "pending",
    method: "none",
    rule_id: null,
    option_value: null,
    option_label: null,
    score,
    reasons,
    ranking,
    citations: citationsFor(context),
    rules_version: LEGAL_FOUNDATION_RULES_VERSION,
  };
}

function operativeTextFromContext(context) {
  const text = asText(context?.operative_text);
  const markers = [...text.matchAll(/\bresolve\s*:/giu)];
  return markers.length > 0 ? text.slice(markers.at(-1).index).trim() : text;
}

export function resolveLegalFoundation({ context, options = [] } = {}) {
  const operativeText = operativeTextFromContext(context);
  if (!context || context.resolution_status !== "complete" || !operativeText.trim()) {
    return baseDecision(context, ["context-incomplete"], zeroRanking(options, "context-incomplete"));
  }

  const references = parseLegalReferences(operativeText);
  if (references.length === 0) {
    return baseDecision(context, ["no-legal-references"], zeroRanking(options, "no-legal-references"));
  }
  if (references.some((reference) => !reference.complete)) {
    return baseDecision(context, ["reference-incomplete"], zeroRanking(options, "reference-incomplete"), 0);
  }
  if (hasContradiction(references)) {
    return baseDecision(context, ["contradictory-reference"], zeroRanking(options, "contradictory-reference"), 0);
  }
  if (hasIncompatibleDiplomaFamilies(references)) {
    return baseDecision(context, ["family-conflict"], zeroRanking(options, "family-conflict"), 0);
  }

  const families = sourceFamilies(references);
  const hasEc41Reference = references.some((reference) => (
    hasDiploma(reference, "ec", "41", "2003")
    && ["6", "7"].includes(reference.article)
  ));
  const hasEc47Article3 = references.some((reference) => (
    hasDiploma(reference, "ec", "47", "2005") && reference.article === "3"
  ));
  if (hasEc41Reference && hasEc47Article3) {
    return baseDecision(context, ["family-conflict"], zeroRanking(options, "family-conflict"), 0);
  }
  if (families.length > 1 || families[0] === "EC41_PARTIAL" || families[0] === "CF40_P5") {
    const reason = families.length > 1 ? "family-conflict" : "unsupported-family";
    return baseDecision(context, [reason], zeroRanking(options, reason), 0);
  }
  const sourceFamily = families[0] ?? "OTHER";
  const candidates = selectableOptions(options)
    .map((option) => {
      const scored = scoreCandidate(references, option, operativeText, sourceFamily);
      return {
        option_index: option.index,
        option_value: option.value,
        option_label: option.label,
        rule_id: RULE_IDS.has(option.rule_id) ? option.rule_id : null,
        score: scored.score,
        method: scored.method,
        reasons: scored.reasons,
      };
    })
    .sort((left, right) => right.score - left.score || left.option_index - right.option_index);

  if (candidates.length === 0) return baseDecision(context, ["no-selectable-options"], []);
  const best = candidates[0];
  if (best.score <= 0) return baseDecision(context, ["no-positive-signal"], candidates, 0);
  const tied = candidates.filter((candidate) => candidate.score === best.score);
  if (tied.length > 1) return baseDecision(context, ["equivalent-candidates", `tie:${tied.length}`], candidates, best.score);
  return {
    ...best,
    status: "resolved",
    method: best.method,
    rule_id: best.rule_id,
    option_value: best.option_value,
    option_label: best.option_label,
    ranking: candidates,
    citations: citationsFor(context),
    rules_version: LEGAL_FOUNDATION_RULES_VERSION,
    references,
  };
}
