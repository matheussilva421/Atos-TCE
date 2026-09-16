import { normalizeLegalText } from "./normalizer.js";
import { parseLegalReferencesV2 } from "./legal-reference-parser-v2.js";
import { buildRetirementLegalProfile } from "./retirement-legal-profile.js";

const SCORE_WEIGHTS = Object.freeze({
  scope: 0.10,
  modality: 0.25,
  proportionality: 0.20,
  calculation_parity: 0.10,
  crosswalk: 0.20,
  discriminators: 0.10,
  lexical: 0.05,
});

const CROSSWALK_ECE20 = "ECE20_ART7_VOLUNTARY_TRANSITION";

function asText(value) {
  return value === null || value === undefined ? "" : String(value);
}

function optionParts(option, index) {
  const value = option?.value ?? option?.label ?? "";
  const label = option?.label ?? value;
  return {
    ...option,
    index,
    value,
    label,
    selectable: option?.selectable !== false && Boolean(value) && !/^selecion(?:e|ar)/iu.test(label.trim()),
  };
}

function inferClassId(option, references) {
  if (option.class_id || option.rule_id) return option.class_id ?? option.rule_id;
  const label = normalizeLegalText(option.label);
  if (label.includes("artigo 6") && label.includes("artigo 7") && label.includes("emenda constitucional 41") && label.includes("emenda constitucional 47")) {
    return label.includes("paragrafo 5") ? "EC41_TRANSITION_TEACHER" : "EC41_TRANSITION_GENERAL";
  }
  if (references.some((reference) => reference.diploma_type === "ec" && reference.diploma_number === "47" && reference.article === "3")) return "EC47_ART3";
  if (references.some((reference) => reference.diploma_type === "ec" && reference.diploma_number === "41" && reference.article === "6" && reference.article_suffix === "a")) return "EC41_ART6A_EC70";
  return `CATALOG_OPTION_${option.index}`;
}

function referencesHave(referenceList, predicate) {
  return referenceList.some(predicate);
}

function hasParagraph(reference, number) {
  return reference.paragraphs.some((paragraph) => paragraph.number === number);
}

function hasInciso(reference, number) {
  return reference.incisos.includes(number)
    || reference.paragraphs.some((paragraph) => paragraph.incisos.includes(number));
}

function candidateSignature(option) {
  const references = parseLegalReferencesV2(option.label);
  const classId = inferClassId(option, references);
  const label = normalizeLegalText(option.label);
  const scope = option.scope ?? (/\bmilitar\b/u.test(label) ? "military" : "civil");
  let modality = "unknown";
  if (classId.includes("ART6A") || referencesHave(references, (reference) => (
    reference.diploma_type === "ec" && reference.diploma_number === "41" && reference.article_suffix === "a"
  ))) {
    modality = "invalidity_permanent_disability";
  } else if (referencesHave(references, (reference) => (
    reference.diploma_type === "cf"
      && reference.article === "40"
      && hasParagraph(reference, "1")
      && hasInciso(reference, "1")
  ))) {
    modality = "invalidity_permanent_disability";
  } else if (referencesHave(references, (reference) => (
    reference.diploma_type === "cf"
      && reference.article === "40"
      && hasParagraph(reference, "1")
      && hasInciso(reference, "2")
  ))) {
    modality = "other";
  } else if (classId.includes("TRANSITION") || classId.includes("ART3") || classId.includes("ART2") || classId.includes("ART8") || referencesHave(references, (reference) => (
    ["ec", "ece"].includes(reference.diploma_type)
  ))) {
    modality = "voluntary_contribution";
  } else if (referencesHave(references, (reference) => (
    reference.diploma_type === "cf"
      && reference.article === "40"
      && hasParagraph(reference, "1")
      && hasInciso(reference, "3")
  ))) {
    modality = "voluntary_contribution";
  }

  let proportionality = "unknown";
  if (classId.includes("TRANSITION") || classId === "EC47_ART3") proportionality = "integral";
  if (/\bproventos?\s+proporciona/u.test(label)) proportionality = "proportional";
  if (/\bproventos?\s+integra/u.test(label)) proportionality = "integral";

  return {
    class_id: classId,
    scope,
    modality,
    proportionality,
    calculation_basis: "unknown",
    parity: "unknown",
    teacher_rule: classId.includes("TEACHER") || referencesHave(references, (reference) => (
      reference.diploma_type === "cf" && reference.article === "40" && hasParagraph(reference, "5")
    )),
    references,
  };
}

function isEce20Case(profile) {
  return profile.modality === "voluntary_contribution"
    && referencesHave(profile.references, (reference) => (
      reference.diploma_type === "ece"
        && reference.diploma_number === "20"
        && reference.diploma_year === "2020"
        && reference.article === "7"
    ));
}

function crosswalkFor(profile, candidate) {
  if (!isEce20Case(profile)) return null;
  if (!["EC41_TRANSITION_GENERAL", "EC41_TRANSITION_TEACHER"].includes(candidate.class_id)) return null;
  return CROSSWALK_ECE20;
}

function sameDiploma(left, right) {
  return left.diploma_type === right.diploma_type
    && left.diploma_number === right.diploma_number
    && left.diploma_year === right.diploma_year;
}

function sameArticle(left, right) {
  return sameDiploma(left, right)
    && left.article === right.article
    && left.article_suffix === right.article_suffix;
}

function hasDiscriminatorMismatch(sourceReferences, candidateReferences) {
  for (const source of sourceReferences) {
    if (source.alineas.length === 0 && source.incisos.length === 0) continue;
    for (const candidate of candidateReferences) {
      if (!sameArticle(source, candidate)) continue;
      if (source.alineas.length > 0 && candidate.alineas.length > 0
          && !source.alineas.some((value) => candidate.alineas.includes(value))) {
        return "hard-reject:alinea-mismatch";
      }
      if (source.incisos.length > 0 && candidate.incisos.length > 0
          && !source.incisos.some((value) => candidate.incisos.includes(value))) {
        return "hard-reject:inciso-mismatch";
      }
    }
  }
  return null;
}

function structuralMatch(sourceReferences, candidateReferences) {
  return sourceReferences.some((source) => candidateReferences.some((candidate) => (
    sameArticle(source, candidate)
      && (source.paragraphs.length === 0 || candidate.paragraphs.length === 0
        || source.paragraphs.some((left) => candidate.paragraphs.some((right) => left.number === right.number)))
  )));
}

function diceSimilarity(left, right) {
  const leftTokens = new Set(normalizeLegalText(left).split(/\s+/u).filter(Boolean));
  const rightTokens = new Set(normalizeLegalText(right).split(/\s+/u).filter(Boolean));
  if (leftTokens.size === 0 || rightTokens.size === 0) return 0;
  let intersection = 0;
  for (const token of leftTokens) if (rightTokens.has(token)) intersection += 1;
  return (2 * intersection) / (leftTokens.size + rightTokens.size);
}

function scoreReason(name, value, weight) {
  return `${name}:${value}:${(value * weight).toFixed(2)}`;
}

function rankOne(profile, sourceText, option) {
  const candidate = candidateSignature(option);
  const reasons = [];
  const warnings = [];
  const hardReasons = [];
  const crosswalk = crosswalkFor(profile, candidate);

  if (!candidate.scope || candidate.scope !== profile.scope) hardReasons.push("hard-reject:scope-mismatch");
  const discriminatorMismatch = hasDiscriminatorMismatch(profile.references, candidate.references);
  if (discriminatorMismatch) hardReasons.push(discriminatorMismatch);
  if (profile.modality !== "unknown" && candidate.modality !== "unknown" && profile.modality !== candidate.modality) {
    hardReasons.push("hard-reject:modality-mismatch");
  }
  if (!option.selectable) hardReasons.push("hard-reject:option-not-selectable");

  const components = {
    scope: profile.scope === candidate.scope ? 1 : 0,
    modality: profile.modality === "unknown" || candidate.modality === "unknown"
      ? 1
      : profile.modality === candidate.modality ? 1 : 0,
    proportionality: profile.proportionality === "unknown" || candidate.proportionality === "unknown"
      ? 1
      : profile.proportionality === candidate.proportionality ? 1 : 0,
    calculation_parity: (profile.calculation_basis === "unknown" || candidate.calculation_basis === "unknown")
      && (profile.parity === "unknown" || candidate.parity === "unknown")
      ? 1
      : 0,
    crosswalk: crosswalk
      ? (candidate.teacher_rule && !profile.professor_rule_explicit ? 0.75 : 1)
      : structuralMatch(profile.references, candidate.references) ? 1 : 0,
    discriminators: candidate.teacher_rule
      ? (profile.professor_rule_explicit ? 1 : 0)
      : 1,
    lexical: diceSimilarity(sourceText, option.label),
  };

  reasons.push(scoreReason(`scope:${profile.scope}`, components.scope, SCORE_WEIGHTS.scope));
  reasons.push(scoreReason(`modality:${profile.modality}`, components.modality, SCORE_WEIGHTS.modality));
  reasons.push(scoreReason(`proportionality:${profile.proportionality}`, components.proportionality, SCORE_WEIGHTS.proportionality));
  reasons.push(scoreReason("calculation-parity", components.calculation_parity, SCORE_WEIGHTS.calculation_parity));
  if (crosswalk) reasons.push(`crosswalk:${crosswalk}`);
  reasons.push(scoreReason("discriminators", components.discriminators, SCORE_WEIGHTS.discriminators));
  reasons.push(scoreReason("lexical", components.lexical, SCORE_WEIGHTS.lexical));
  if (profile.professor_context && candidate.teacher_rule && !profile.professor_rule_explicit) {
    warnings.push("Professor identificado pelo cargo, mas a regra docente não foi encontrada expressamente na fundamentação. Revisão recomendada.");
  }

  const score = hardReasons.length > 0
    ? 0
    : Object.entries(SCORE_WEIGHTS).reduce((total, [key, weight]) => total + components[key] * weight, 0);
  return {
    class_id: candidate.class_id,
    scope: candidate.scope,
    option_value: option.value,
    option_label: option.label,
    option_index: option.index,
    score,
    confidence: score,
    hard_conflict: hardReasons.length > 0,
    rejected: hardReasons.length > 0,
    reasons: [...hardReasons, ...reasons],
    warnings,
    method: crosswalk ? "similarity" : structuralMatch(profile.references, candidate.references) ? "rule" : "none",
    score_components: components,
  };
}

function emptyDecision(profile, reason, warnings = []) {
  return {
    status: "pending",
    automatic: false,
    scope: profile.scope,
    option_value: null,
    option_label: null,
    class_id: null,
    method: "none",
    confidence: 0,
    margin: 0,
    reason,
    reasons: [reason],
    warnings,
    ranking: [],
    profile,
    score_components: { lexical_weight: SCORE_WEIGHTS.lexical },
  };
}

export function classifyPortalLegalFoundation({ operativeText = "", cargo = "", options = [], hints = {} } = {}) {
  const profile = buildRetirementLegalProfile({ operativeText, cargo, documentaryValue: hints.documentaryValue });
  if (!asText(operativeText).trim()) return emptyDecision(profile, "missing-source");
  const normalizedOptions = Array.isArray(options) ? options.map(optionParts) : [];
  if (normalizedOptions.length === 0) return emptyDecision(profile, "CATALOG_CLASS_MISSING");

  const ranking = normalizedOptions
    .map((option) => rankOne(profile, operativeText, option))
    .sort((left, right) => right.score - left.score || left.option_index - right.option_index);
  const viable = ranking.filter((candidate) => !candidate.rejected);
  if (viable.length === 0) return {
    ...emptyDecision(profile, "no-compatible-candidate"),
    ranking,
  };

  const best = viable[0];
  const second = viable[1] ?? null;
  const margin = second ? best.confidence - second.confidence : best.confidence;
  const reasons = [...best.reasons];
  const warnings = [...best.warnings];
  let status = "pending";
  if (best.confidence >= 0.90 && margin >= 0.12 && !best.hard_conflict) status = "selected";
  else if (best.confidence >= 0.75 && !best.hard_conflict) status = "review";
  else status = "pending";

  if (status !== "selected") warnings.push("Decisão não atende os limites de confiança/margem para preenchimento automático.");
  return {
    status,
    automatic: status === "selected",
    scope: profile.scope,
    option_value: best.option_value,
    option_label: best.option_label,
    class_id: best.class_id,
    method: status === "selected" ? best.method : "none",
    confidence: best.confidence,
    margin,
    reason: status === "selected" ? null : "manual-review-required",
    reasons,
    warnings,
    ranking,
    profile,
    score_components: {
      ...best.score_components,
      lexical_weight: SCORE_WEIGHTS.lexical,
    },
  };
}

export { SCORE_WEIGHTS };
