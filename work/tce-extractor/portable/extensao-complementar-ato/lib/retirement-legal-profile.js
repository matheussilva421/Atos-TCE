import { normalizeLegalText } from "./normalizer.js";
import { parseLegalReferencesV2 } from "./legal-reference-parser-v2.js";

function asText(value) {
  return value === null || value === undefined ? "" : String(value);
}

function sourceText({ operativeText, documentaryValue }) {
  if (asText(operativeText).trim()) return asText(operativeText);
  if (typeof documentaryValue === "string") return documentaryValue;
  if (documentaryValue && typeof documentaryValue === "object") {
    return asText(documentaryValue.operative_text ?? documentaryValue.value);
  }
  return "";
}

function detectScope(text) {
  if (/\b(?:militar|military|policia militar|reforma)\b/u.test(text)) return "military";
  if (/\b(?:servidor|professor|docente|magisterio|aposentadoria|invalidez|incapacidade)\b/u.test(text)) return "civil";
  return "unknown";
}

function detectModality(text) {
  if (/\b(?:aposentadoria\s+por\s+)?(?:invalidez|incapacidade\s+permanente)\b/u.test(text)) {
    return "invalidity_permanent_disability";
  }
  if (/\baposentadoria\b[\s\S]{0,100}\bvoluntaria\b[\s\S]{0,100}\btempo\s+de\s+contribuicao\b/u.test(text)) {
    return "voluntary_contribution";
  }
  if (/\baposentadoria\b[\s\S]{0,100}\bvoluntaria\b/u.test(text)) return "voluntary_contribution";
  if (/\b(?:aposentadoria|invalidez|incapacidade)\b/u.test(text)) return "other";
  return "unknown";
}

function detectProportionality(text) {
  if (/\bproventos?\s+integra(?:l|is)\b/u.test(text)) return "integral";
  if (/\bproventos?\s+proporciona(?:l|is)\b/u.test(text)) return "proportional";
  return "unknown";
}

function detectCalculationBasis(text) {
  if (/\b(?:pela|por|calculad[oa]s?\s+pel[ao])\s+media\b|\bmedia\s+(?:aritmetica|contributiva)\b/u.test(text)) {
    return "average";
  }
  if (/\b(?:integralidade|remuneracao\s+(?:do\s+cargo|do\s+servidor)|ultima\s+remuneracao)\b/u.test(text)) {
    return "remuneration";
  }
  return "unknown";
}

function detectParity(text) {
  if (/\bsem\s+paridade\b/u.test(text)) return "no";
  if (/\bparidade\b/u.test(text)) return "yes";
  return "unknown";
}

function detectTransitionRule(text, references) {
  if (/\bsem\s+regra\s+de\s+transicao\b/u.test(text)) return false;
  if (/\bregra\s+de\s+transicao\b/u.test(text)) return true;
  return references.some((reference) => (
    ["ec", "ece"].includes(reference.diploma_type)
      && ["20", "41", "47"].includes(reference.diploma_number)
  )) ? true : "unknown";
}

function isTeacherReference(reference) {
  return reference.diploma_type === "cf"
    && reference.article === "40"
    && reference.paragraphs.some((paragraph) => paragraph.number === "5");
}

function detectExplicitTeacherRule(text, references) {
  if (references.some(isTeacherReference)) return true;
  return /\b(?:regra|aposentadoria)\b[\s\S]{0,50}\b(?:professor|docente|magisterio)\b/u.test(text)
    && /\b(?:artigo|art\.)\b/u.test(text);
}

function evidenceFor(text, profile) {
  const evidence = [];
  if (profile.modality !== "unknown") evidence.push(`modality:${profile.modality}`);
  if (profile.proportionality !== "unknown") evidence.push(`proventos:${profile.proportionality}`);
  if (profile.calculation_basis !== "unknown") evidence.push(`base:${profile.calculation_basis}`);
  if (profile.parity !== "unknown") evidence.push(`parity:${profile.parity}`);
  if (profile.professor_context) evidence.push("context:professor");
  if (profile.professor_rule_explicit) evidence.push("rule:teacher-explicit");
  if (profile.transition_rule !== "unknown") evidence.push(`transition:${profile.transition_rule}`);
  if (/\b(?:proventos?\s+integra|proventos?\s+proporcional)/u.test(text)) evidence.push("operative:proventos");
  return evidence;
}

/**
 * Builds the stable functional profile used by the portal crosswalk. The
 * profile describes signals present in the document; it does not validate the
 * legality of the retirement or infer missing personal requirements.
 */
export function buildRetirementLegalProfile({ operativeText = "", cargo = "", documentaryValue = null } = {}) {
  const source = sourceText({ operativeText, documentaryValue });
  const normalized = normalizeLegalText(`${source} ${asText(cargo)}`);
  const references = parseLegalReferencesV2(source);
  const profile = {
    scope: detectScope(normalized),
    modality: detectModality(normalized),
    proportionality: detectProportionality(normalized),
    calculation_basis: detectCalculationBasis(normalized),
    parity: detectParity(normalized),
    professor_context: /\b(?:professor(?:a|es|as)?|docente|magisterio)\b/u.test(normalized),
    professor_rule_explicit: detectExplicitTeacherRule(normalized, references),
    transition_rule: detectTransitionRule(normalized, references),
    references,
    evidence: [],
  };
  profile.evidence = evidenceFor(normalized, profile);
  return profile;
}
