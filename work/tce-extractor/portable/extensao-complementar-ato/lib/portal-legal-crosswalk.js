import { buildCatalogOptionSignature } from "./catalog-option-signature.js";
import { normalizeLegalText } from "./normalizer.js";
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

function referencesHave(referenceList, predicate) {
  return referenceList.some(predicate);
}

function legalDiploma(reference) {
  return ["ec", "ece", "cf", "ce"].includes(reference.diploma_type)
    && reference.diploma_number !== null
    && reference.diploma_number !== undefined;
}

function matchingDiplomaFamilies(sourceReferences, candidateReferences) {
  const candidateDiplomas = candidateReferences.filter(legalDiploma);
  return sourceReferences.filter((reference) => (
    legalDiploma(reference)
    && candidateDiplomas.some((candidate) => (
      candidate.diploma_type === reference.diploma_type
      && candidate.diploma_number === reference.diploma_number
      && (candidate.diploma_year === null || reference.diploma_year === null
        || candidate.diploma_year === reference.diploma_year)
    ))
  ));
}

/**
 * EC and ECE amendments are distinct instruments. A state amendment is only
 * carried by a catalog option when the option declares the same instrument or
 * an explicit crosswalk translates it to the historical taxonomy.
 */
function missingDiplomaFamily(sourceReferences, candidateReferences, recognizedCrosswalk) {
  if (recognizedCrosswalk) return null;
  const candidateDiplomas = candidateReferences.filter(legalDiploma);
  const carries = (source) => candidateDiplomas.some((candidate) => (
    candidate.diploma_type === source.diploma_type
    && candidate.diploma_number === source.diploma_number
    && (candidate.diploma_year === null || source.diploma_year === null
      || candidate.diploma_year === source.diploma_year)
  ));
  for (const reference of sourceReferences) {
    if (!legalDiploma(reference)) continue;
    if (carries(reference)) continue;
    // A documented federal amendment shared with the option keeps the act
    // traceable even when the state amendment only preserves previous rules.
    const sharesFederal = reference.diploma_type === "ece"
      && sourceReferences.some((source) => source.diploma_type === "ec" && carries(source));
    if (reference.diploma_type === "ece" && !sharesFederal) {
      return "hard-reject:diploma-family-missing";
    }
  }
  return null;
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
  if (isEce20Case(profile) && ["EC41_TRANSITION_GENERAL", "EC41_TRANSITION_TEACHER"].includes(candidate.class_id)) {
    return CROSSWALK_ECE20;
  }
  const hasEc41Transition = ["EC41_SEM_P5", "EC41_COM_P5"].includes(candidate.class_id)
    && (!profile.professor_rule_explicit || candidate.teacher_rule)
    && profile.references.some((reference) => (
      reference.diploma_type === "ec"
        && reference.diploma_number === "41"
        && ["6", "7"].includes(reference.article)
        && !reference.article_suffix
    ));
  if (hasEc41Transition) return "EC41_TRANSITION_STRUCTURAL_RULE";
  if (["EC41_ART6A", "EC41_ART6A_EC70"].includes(candidate.class_id) && profile.references.some((reference) => (
    reference.diploma_type === "ec" && reference.diploma_number === "41" && reference.article_suffix === "a"
  ))) return "EC41_ART6A_STRUCTURAL_RULE";
  return null;
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
  const candidate = buildCatalogOptionSignature(option, option.index ?? 0);
  const reasons = [];
  const warnings = [];
  const hardReasons = [];
  const crosswalk = crosswalkFor(profile, candidate);

  if (!candidate.scope || candidate.scope !== profile.scope) hardReasons.push("hard-reject:scope-mismatch");
  const sourceHasCe = profile.references.some((reference) => reference.diploma_type === "ce");
  const candidateHasCf = candidate.references.some((reference) => reference.diploma_type === "cf");
  const sourceHasCf = profile.references.some((reference) => reference.diploma_type === "cf");
  const candidateHasCe = candidate.references.some((reference) => reference.diploma_type === "ce");
  if ((sourceHasCe && candidateHasCf) || (sourceHasCf && candidateHasCe)) {
    hardReasons.push("family-mismatch", "hard-reject:constitution-mismatch");
  }
  const sourceHasEc41Article6 = profile.references.some((reference) => (
    reference.diploma_type === "ec" && reference.diploma_number === "41" && reference.article === "6" && !reference.article_suffix
  ));
  const candidateHasEc41Article6A = candidate.class_id === "EC41_ART6A"
    || candidate.references.some((reference) => (
      reference.diploma_type === "ec" && reference.diploma_number === "41" && reference.article === "6" && reference.article_suffix === "a"
    ));
  if (sourceHasEc41Article6 && candidateHasEc41Article6A) hardReasons.push("hard-reject:article-suffix-mismatch");
  const discriminatorMismatch = hasDiscriminatorMismatch(profile.references, candidate.references);
  if (discriminatorMismatch) hardReasons.push(discriminatorMismatch);
  const missingFamily = missingDiplomaFamily(profile.references, candidate.references, crosswalk !== null);
  if (missingFamily) hardReasons.push(missingFamily);
  if (profile.modality !== "unknown" && candidate.modality !== "unknown" && profile.modality !== candidate.modality) {
    hardReasons.push("hard-reject:modality-mismatch");
  }
  // Professor cargo is context, not proof of the teacher rule: a candidate
  // that requires CF art. 40, § 5º is only compatible when the operative text
  // itself carries the teacher rule.
  if (profile.professor_context && candidate.teacher_rule && !profile.professor_rule_explicit) {
    hardReasons.push("hard-reject:teacher-rule-not-operative");
  }
  if (!option.selectable) hardReasons.push("hard-reject:option-not-selectable");

  const exactText = normalizeLegalText(sourceText) === normalizeLegalText(option.label);
  const legacyTeacherMismatch = profile.professor_rule_explicit && !candidate.teacher_rule;
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
      : (legacyTeacherMismatch ? 0 : 1),
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
    method: exactText
      ? "exact"
      : crosswalk === CROSSWALK_ECE20
        ? "similarity"
        : crosswalk || structuralMatch(profile.references, candidate.references)
          ? "rule"
          : "none",
    score_components: components,
  };
}

function emptyDecision(profile, reason, warnings = [], decisionState = "NO_COMPATIBLE_CANDIDATE") {
  return {
    status: "pending",
    decision_state: decisionState,
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
  const normalizedOptions = Array.isArray(options)
    ? options.map((option, index) => buildCatalogOptionSignature(option, index))
    : [];
  if (normalizedOptions.length === 0) return emptyDecision(profile, "CATALOG_CLASS_MISSING");

  const referenceTypes = new Set(profile.references.map((reference) => reference.diploma_type));
  const ec41Reference = profile.references.some((reference) => (
    reference.diploma_type === "ec" && reference.diploma_number === "41" && ["6", "7"].includes(reference.article)
  ));
  const ec47Article3 = profile.references.some((reference) => (
    reference.diploma_type === "ec" && reference.diploma_number === "47" && reference.article === "3"
  ));
  // Coexisting EC and ECE diplomas are not a conflict by themselves: ECE/RN
  // 20/2020 may preserve previous rules. Only contradictory roles conflict.
  if ((referenceTypes.has("cf") && referenceTypes.has("ce"))
      || (ec41Reference && ec47Article3)) {
    return emptyDecision(profile, "family-conflict", [], "DOCUMENT_CONFLICT");
  }

  const ranking = normalizedOptions
    .filter((option) => option.selectable)
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
  const tied = second !== null && best.confidence === second.confidence;
  if (tied) {
    reasons.push("equivalent-candidates", `tie:${viable.filter((candidate) => candidate.confidence === best.confidence).length}`);
  }
  // The operational status stays compatible with the earlier contract, while
  // decision_state makes the legal situation explicit for the UI and guards.
  let status;
  if (best.confidence >= 0.90 && margin >= 0.12 && !best.hard_conflict) status = "selected";
  else if (best.confidence >= 0.75 && !best.hard_conflict) status = "review";
  else status = "pending";
  let decisionState;
  if (tied) decisionState = "TRUE_TIE";
  else if (status === "selected") decisionState = "AUTO_SELECTED";
  else if (status === "review") decisionState = "REVIEW_REQUIRED";
  else decisionState = "NO_COMPATIBLE_CANDIDATE";

  if (status !== "selected") warnings.push("Decisão não atende os limites de confiança/margem para preenchimento automático.");
  return {
    status,
    decision_state: decisionState,
    automatic: status === "selected",
    scope: profile.scope,
    option_value: best.option_value,
    option_label: best.option_label,
    class_id: best.class_id,
    method: status === "selected" ? best.method : "none",
    confidence: best.confidence,
    margin,
    hard_conflict: best.hard_conflict === true,
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
