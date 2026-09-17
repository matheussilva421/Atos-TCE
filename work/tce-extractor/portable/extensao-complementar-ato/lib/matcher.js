import { extractLegalSignals, normalizeLegalText } from "./normalizer.js";
import { resolveLegalFoundation } from "./legal-foundation.js";

const WEIGHTS = Object.freeze({
  benefit: 100,
  proportion: 60,
  professor: 50,
  legalReference: 40,
  diploma: 25,
});

function asText(value) {
  return value === null || value === undefined ? "" : String(value);
}

function optionParts(option) {
  if (option !== null && typeof option === "object") {
    const value = option.value ?? option.label ?? "";
    const label = option.label ?? value;
    return {
      value,
      label,
      normalizedValue: normalizeLegalText(value),
      normalizedLabel: normalizeLegalText(label),
    };
  }

  return {
    value: option,
    label: option,
    normalizedValue: normalizeLegalText(option),
    normalizedLabel: normalizeLegalText(option),
  };
}

function firstSignalFromHint(hints, key, fallback) {
  const value = hints?.[key];
  if (value === undefined || value === null || value === "") {
    return fallback;
  }

  if (key === "professor") {
    return value === true || /^(?:true|sim|yes)$/iu.test(asText(value));
  }

  if (key === "incisos") {
    const values = Array.isArray(value) ? value : [value];
    return values
      .map((item) => extractLegalSignals(item).incisos)
      .flat()
      .filter((item, index, all) => all.indexOf(item) === index);
  }

  if (key === "diplomas") {
    const values = Array.isArray(value) ? value : [value];
    return values.map((item) => asText(item)).filter(Boolean);
  }

  const extracted = extractLegalSignals(value);
  if (key === "benefit") {
    return extracted.benefit ?? normalizeLegalText(value);
  }
  if (key === "modality") {
    return extracted.modality ?? normalizeLegalText(value);
  }
  if (key === "proportion") {
    return extracted.proportion ?? normalizeLegalText(value);
  }
  if (key === "article") {
    return extracted.article ?? asText(value);
  }
  if (key === "paragraph") {
    return extracted.paragraph ?? asText(value);
  }
  return fallback;
}

function sourceSignals(documentaryValue, hints) {
  const extracted = extractLegalSignals(documentaryValue);
  const safeHints = hints !== null && typeof hints === "object" ? hints : {};

  return {
    benefit: firstSignalFromHint(safeHints, "benefit", extracted.benefit),
    modality: firstSignalFromHint(safeHints, "modality", extracted.modality),
    proportion: firstSignalFromHint(safeHints, "proportion", extracted.proportion),
    professor: firstSignalFromHint(safeHints, "professor", extracted.professor),
    article: firstSignalFromHint(safeHints, "article", extracted.article),
    paragraph: firstSignalFromHint(safeHints, "paragraph", extracted.paragraph),
    incisos: firstSignalFromHint(safeHints, "incisos", extracted.incisos),
    diplomas: firstSignalFromHint(safeHints, "diplomas", extracted.diplomas),
  };
}

function candidateSignals(option) {
  return extractLegalSignals(option.label);
}

function allLegalSignalsMatch(source, candidate) {
  const requested = [];
  const matched = [];

  if (source.article !== null) {
    requested.push("article");
    if (candidate.article === source.article) {
      matched.push("article");
    }
  }
  if (source.paragraph !== null) {
    requested.push("paragraph");
    if (candidate.paragraph === source.paragraph) {
      matched.push("paragraph");
    }
  }
  if (source.incisos.length > 0) {
    requested.push("inciso");
    if (source.incisos.every((inciso) => candidate.incisos.includes(inciso))) {
      matched.push("inciso");
    }
  }

  return requested.length > 0 && matched.length === requested.length
    ? matched
    : [];
}

function diplomaIdentity(value) {
  const normalized = normalizeLegalText(value);
  const match = normalized.match(
    /^(emenda constitucional estadual|emenda constitucional|lei complementar estadual|lei complementar|lei|decreto|resolucao|portaria)\s+(?:numero\s+)?(\d+)/u,
  );

  if (!match) {
    return null;
  }

  const family = match[1]
    .replace("emenda constitucional estadual", "emenda constitucional")
    .replace("lei complementar estadual", "lei complementar");
  return `${family}:${match[2]}`;
}

function hasDiplomaMatch(source, candidate) {
  const candidateIdentities = candidate.diplomas
    .map(diplomaIdentity)
    .filter(Boolean);

  return source.diplomas.some((diploma) => {
    const identity = diplomaIdentity(diploma);
    return identity !== null && candidateIdentities.includes(identity);
  });
}

function diceScore(left, right) {
  const leftTokens = new Set(normalizeLegalText(left).split(/\s+/u).filter(Boolean));
  const rightTokens = new Set(normalizeLegalText(right).split(/\s+/u).filter(Boolean));
  if (leftTokens.size === 0 || rightTokens.size === 0) {
    return 0;
  }

  let intersection = 0;
  for (const token of leftTokens) {
    if (rightTokens.has(token)) {
      intersection += 1;
    }
  }

  return Math.round((2 * intersection * 10) / (leftTokens.size + rightTokens.size));
}

function scoreOption(source, documentaryValue, option, field) {
  const candidate = candidateSignals(option);
  let score = 0;
  const reasons = [];

  const benefitMatches = source.benefit !== null && candidate.benefit === source.benefit;
  const modalityMatches = source.modality !== null && candidate.modality === source.modality;
  if (benefitMatches || modalityMatches) {
    score += WEIGHTS.benefit;
    reasons.push(`${benefitMatches ? "benefit" : "modality"}:${WEIGHTS.benefit}`);
  }

  // A shared benefit ("aposentadoria") must not erase its explicit subtype.
  // A long voluntary catalog label also contains the short "voluntaria"
  // signal, although extractLegalSignals returns its more specific tempo rule.
  if (field === "modalidade" && source.modality !== null
      && ` ${option.normalizedLabel} `.includes(` ${source.modality} `)) {
    score += WEIGHTS.benefit;
    reasons.push(`explicit-modality:${source.modality}:${WEIGHTS.benefit}`);
  }

  if (source.proportion !== null && candidate.proportion === source.proportion) {
    score += WEIGHTS.proportion;
    reasons.push(`proportion:${source.proportion}:${WEIGHTS.proportion}`);
  }

  if (source.professor === true && candidate.professor === true) {
    score += WEIGHTS.professor;
    reasons.push(`professor:${WEIGHTS.professor}`);
  }

  const legalMatches = allLegalSignalsMatch(source, candidate);
  if (legalMatches.length > 0) {
    score += WEIGHTS.legalReference;
    reasons.push(`${legalMatches.join("-")}:${WEIGHTS.legalReference}`);
  }

  if (hasDiplomaMatch(source, candidate)) {
    score += WEIGHTS.diploma;
    reasons.push(`diploma:${WEIGHTS.diploma}`);
  }

  const lexical = diceScore(documentaryValue, option.label);
  if (lexical > 0) {
    score += lexical;
    reasons.push(`lexical-dice:${lexical}`);
  }

  return { score, reasons };
}

function resultFor(option, index, kind, score, reasons) {
  return {
    kind,
    optionIndex: index,
    optionValue: option.value,
    optionLabel: option.label,
    score,
    reasons,
  };
}

/**
 * Fail-closed result for the legal foundation field. The specialized legal
 * pipeline owns this field: without a LegalContext there is no classification
 * and the generic matcher must never run, even for a perfect lexical match.
 */
function missingLegalContextMatch(reason = "LEGAL_CONTEXT_REQUIRED") {
  return {
    kind: "pending",
    optionIndex: -1,
    optionValue: null,
    optionLabel: null,
    score: 0,
    reasons: [reason],
    legalDecision: {
      status: "pending",
      decision_state: "CONTEXT_BLOCKED",
      automatic: false,
      option_value: null,
      option_label: null,
      method: "none",
      confidence: 0,
      margin: 0,
      hard_conflict: false,
      reason,
      reasons: [reason],
      warnings: [],
      ranking: [],
    },
  };
}

const LEGAL_CONTEXT_SHA256_RE = /^[a-f0-9]{64}$/u;

/**
 * The specialized pipeline only runs for a complete, versioned LegalContext.
 * Any other object stays fail-closed instead of being classified.
 */
function isCompleteLegalContext(context) {
  return context !== null
    && typeof context === "object"
    && !Array.isArray(context)
    && context.schema_version === 1
    && typeof context.dataset_sha256 === "string"
    && LEGAL_CONTEXT_SHA256_RE.test(context.dataset_sha256)
    && typeof context.process_key === "string"
    && context.process_key !== ""
    && typeof context.interested_normalized === "string"
    && context.interested_normalized !== ""
    && context.resolution_status === "complete"
    && typeof context.operative_text === "string"
    && context.operative_text.trim() !== ""
    && Array.isArray(context.pages)
    && context.pages.length > 0
    && context.extraction_version === "legal-context-v4"
    && Number.isSafeInteger(context.context_revision)
    && context.context_revision >= 0
    && context.rules_version === "legal-foundation-v3";
}

/**
 * Ranks the current portal catalog against one documentary value. The source
 * and option labels are returned untouched; normalized signatures exist only
 * inside this comparison.
 */
export function rankPortalOptions({ field, documentaryValue, hints = {}, options = [], context = null }) {
  if (field === "fundamento_legal") {
    if (!isCompleteLegalContext(context)) return missingLegalContextMatch();
    const legalDecision = resolveLegalFoundation({ context, options });
    const optionIndex = legalDecision.option_value === null
      ? null
      : options.findIndex((option) => optionParts(option).value === legalDecision.option_value);
    return {
      kind: legalDecision.status === "selected"
        ? (legalDecision.method === "exact" ? "exact" : "probable")
        : "pending",
      optionIndex: optionIndex >= 0 ? optionIndex : null,
      optionValue: legalDecision.option_value,
      optionLabel: legalDecision.option_label,
      score: legalDecision.score,
      reasons: legalDecision.reasons,
      legalDecision,
    };
  }

  if (!asText(documentaryValue).trim()) {
    return {
      kind: "missing-source",
      optionIndex: null,
      optionValue: null,
      optionLabel: null,
      score: 0,
      reasons: ["missing-source"],
    };
  }

  const portalOptions = Array.isArray(options) ? options.map(optionParts) : [];
  if (portalOptions.length === 0) {
    return {
      kind: "probable",
      optionIndex: null,
      optionValue: null,
      optionLabel: null,
      score: 0,
      reasons: ["no-options"],
    };
  }

  const sourceSignature = normalizeLegalText(documentaryValue);
  const exactIndex = portalOptions.findIndex((option) => (
    sourceSignature !== "" && (
      option.normalizedLabel === sourceSignature || option.normalizedValue === sourceSignature
    )
  ));
  if (exactIndex >= 0) {
    return resultFor(
      portalOptions[exactIndex],
      exactIndex,
      "exact",
      WEIGHTS.benefit,
      ["normalized-equivalence"],
    );
  }

  const source = sourceSignals(documentaryValue, hints);
  const ranked = portalOptions.map((option, index) => ({
    option,
    index,
    ...scoreOption(source, documentaryValue, option, field),
  }));
  ranked.sort((left, right) => right.score - left.score || left.index - right.index);

  const best = ranked[0];
  if (best.score === 0) {
    return resultFor(best.option, best.index, "probable", 0, ["no-positive-signal"]);
  }

  const tied = ranked.filter((candidate) => candidate.score === best.score);
  if (tied.length > 1) {
    return resultFor(best.option, best.index, "tie", best.score, [
      ...best.reasons,
      `tie:${tied.length}`,
    ]);
  }

  return resultFor(best.option, best.index, "probable", best.score, best.reasons);
}
