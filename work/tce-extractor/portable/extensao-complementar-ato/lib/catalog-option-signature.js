import { normalizeLegalText } from "./normalizer.js";
import { parseLegalReferencesV2 } from "./legal-reference-parser-v2.js";

const ARTICLE_NUMBER_PATTERN = /\bart(?:igo|igos)?s?\.?\s*(\d+)\s*(?:º|ª|o)?/giu;
const ALINEA_PATTERN = /\balineas?\s+([a-z])\b/giu;
const MILITARY_PATTERN = /\bmilitar\b/u;
const PLACEHOLDER_PATTERN = /^selecion(?:e|ar)\b/u;

function asText(value) {
  return value === null || value === undefined ? "" : String(value);
}

function optionParts(option, index) {
  if (option !== null && typeof option === "object") {
    const value = option.value ?? option.label ?? "";
    const label = option.label ?? value;
    return { index, value, label };
  }
  return { index, value: option, label: option };
}

function referenceIdentity(reference) {
  return [
    reference.diploma_type ?? "",
    reference.diploma_number ?? "",
    reference.diploma_year ?? "",
    reference.article ?? "",
    reference.article_suffix ?? "",
  ].join(":");
}

function uniqueReferences(references) {
  const seen = new Set();
  return references.filter((reference) => {
    const key = referenceIdentity(reference);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function hasDiploma(references, type, number = null) {
  return references.some((reference) => (
    reference.diploma_type === type
    && (number === null || reference.diploma_number === number)
  ));
}

function hasArticle(references, type, number, article, suffix = null) {
  return references.some((reference) => (
    reference.diploma_type === type
    && reference.diploma_number === number
    && reference.article === article
    && (reference.article_suffix ?? null) === suffix
  ));
}

function articleNumbersFromLabel(normalizedLabel) {
  return [...normalizedLabel.matchAll(ARTICLE_NUMBER_PATTERN)].map((match) => match[1]);
}

function hasArticleNumber(numbers, expected) {
  return numbers.includes(expected);
}

function hasParagraph(references, number) {
  return references.some((reference) => (
    reference.paragraphs.some((paragraph) => paragraph.number === number)
  ));
}

function paragraphNumbersFromLabel(normalizedLabel) {
  return [...normalizedLabel.matchAll(/§{1,2}\s*(\d+)/gu)].map((match) => match[1]);
}

function hasInciso(reference, number) {
  return reference.incisos.includes(number)
    || reference.paragraphs.some((paragraph) => paragraph.incisos.includes(number));
}

function hasIncisoIn(references, number, article = null) {
  return references.some((reference) => (
    (article === null || reference.article === article) && hasInciso(reference, number)
  ));
}

function alineasFor(references, article = null) {
  const alineas = [];
  for (const reference of references) {
    if (article !== null && reference.article !== article) continue;
    for (const alinea of reference.alineas) if (!alineas.includes(alinea)) alineas.push(alinea);
    for (const paragraph of reference.paragraphs) {
      for (const alinea of paragraph.alineas) if (!alineas.includes(alinea)) alineas.push(alinea);
    }
  }
  return alineas;
}

function alineasFromLabel(normalizedLabel) {
  return [...normalizedLabel.matchAll(ALINEA_PATTERN)].map((match) => match[1]);
}

function cf40Paragraph5(references) {
  return references.some((reference) => (
    reference.diploma_type === "cf"
    && reference.article === "40"
    && reference.paragraphs.some((paragraph) => paragraph.number === "5")
  ));
}

function hasEc41Transition(references) {
  return hasArticle(references, "ec", "41", "6")
    && hasArticle(references, "ec", "41", "7");
}

function hasEc41Article6A(references) {
  return hasArticle(references, "ec", "41", "6", "a");
}

function hasLc51(references) {
  return references.some((reference) => (
    ["lc", "lce"].includes(reference.diploma_type) && reference.diploma_number === "51"
  ));
}

function hasCe29(references) {
  return references.some((reference) => reference.diploma_type === "ce" && reference.article === "29");
}

function deriveClassId(references, normalizedLabel, index) {
  const articleNumbers = articleNumbersFromLabel(normalizedLabel);
  const paragraphNumbers = paragraphNumbersFromLabel(normalizedLabel);
  const hasP5 = paragraphNumbers.includes("5") || hasParagraph(references, "5");
  if (MILITARY_PATTERN.test(normalizedLabel)) return "MILITARY_TRANSITION";
  if (hasEc41Article6A(references)) return "EC41_ART6A_EC70";
  if (hasEc41Transition(references)) return hasP5 ? "EC41_TRANSITION_TEACHER" : "EC41_TRANSITION_GENERAL";
  // A state-constitution article 40 must never be classified as a CF art. 40
  // class: the state diploma takes precedence over the generic article branch.
  if (references.some((reference) => reference.diploma_type === "ce" && reference.article === "40")) {
    return "CE40";
  }
  if (hasArticleNumber(articleNumbers, "40")) {
    const alineas = [...alineasFor(references, "40"), ...alineasFromLabel(normalizedLabel)];
    if (hasP5) return "CF40_III_A_P5";
    if (hasIncisoIn(references, "1", "40")) return "CF40_I";
    if (hasIncisoIn(references, "2", "40")) return "CF40_II";
    if (hasIncisoIn(references, "3", "40")) {
      return alineas.includes("b") && !alineas.includes("a") ? "CF40_III_B" : "CF40_III_A";
    }
    return `CATALOG_OPTION_${index}`;
  }
  if (hasLc51(references)) {
    return hasParagraph(references, "4")
      ? "CF40_P1_II_LC51"
      : (hasIncisoIn(references, "2") ? "LC51_ART1_II" : "LC51_ART1");
  }
  if (hasArticle(references, "ec", "20", "8")) return "EC20_ART8";
  if (hasArticle(references, "ec", "20", "9")) return "EC20_ART9";
  if (hasArticle(references, "ec", "20", "1")) return "EC20_ART1";
  if (hasArticle(references, "ec", "41", "2")) return "EC41_ART2";
  if (hasArticle(references, "ec", "47", "3")) return "EC47_ART3";
  if (hasArticle(references, "ec", "41", "1")) return "EC41_ART1";
  if (hasCe29(references)) {
    const alineas = [...alineasFor(references, "29"), ...alineasFromLabel(normalizedLabel)];
    if (hasIncisoIn(references, "1", "29")) return `CE29_I_${(alineas[0] ?? "a").toUpperCase()}`;
    if (hasIncisoIn(references, "3", "29")) return `CE29_III_${(alineas[0] ?? "a").toUpperCase()}`;
    return "CE29_OTHER";
  }
  return `CATALOG_OPTION_${index}`;
}

function deriveModality(classId, references) {
  if (classId.includes("ART6A") || classId === "CF40_I") return "invalidity_permanent_disability";
  if (classId === "CF40_P1_II_LC51" || classId === "LC51_ART1_II" || classId === "LC51_ART1") {
    return "invalidity_permanent_disability";
  }
  if (classId === "CF40_II") return "other";
  if (classId.includes("TRANSITION") || classId.includes("ART3") || classId.includes("ART2") || classId.includes("ART8")) {
    return "voluntary_contribution";
  }
  if (hasDiploma(references, "ec") || hasDiploma(references, "ece")) return "voluntary_contribution";
  if (classId.startsWith("CF40_III")) return "voluntary_contribution";
  return "unknown";
}

function deriveProportionality(classId, normalizedLabel) {
  if (/\bproventos?\s+proporciona/u.test(normalizedLabel)) return "proportional";
  if (/\bproventos?\s+integra/u.test(normalizedLabel)) return "integral";
  if (classId.includes("TRANSITION") || classId === "EC47_ART3") return "integral";
  return "unknown";
}

/**
 * Builds the jurisprudence signature of one raw portal catalog option. The
 * portal publishes only `{value, label}`; every legal signal below is derived
 * from the label structure, never from injected metadata such as `class_id`.
 */
export function buildCatalogOptionSignature(option, index = 0) {
  const parts = optionParts(option, index);
  const label = asText(parts.label);
  const value = asText(parts.value);
  const normalizedLabel = normalizeLegalText(label);
  const references = uniqueReferences(parseLegalReferencesV2(label));
  const placeholder = PLACEHOLDER_PATTERN.test(normalizedLabel.trim());
  const selectable = value.trim() !== "" && label.trim() !== "" && !placeholder;
  const classId = deriveClassId(references, normalizedLabel, index);
  return {
    index,
    value,
    label,
    selectable,
    class_id: classId,
    scope: MILITARY_PATTERN.test(normalizedLabel) ? "military" : "civil",
    modality: deriveModality(classId, references),
    proportionality: deriveProportionality(classId, normalizedLabel),
    calculation_basis: "unknown",
    parity: "unknown",
    teacher_rule: cf40Paragraph5(references),
    references,
  };
}
