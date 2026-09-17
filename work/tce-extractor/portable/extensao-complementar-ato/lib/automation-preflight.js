const AUTOMATION_FIELDS = Object.freeze([
  "modalidade",
  "fundamento_legal",
  "data_publicacao_doe",
  "cargo",
  "matricula",
  "data_nascimento",
  "genero",
]);
const REQUIRED_AUTOMATION_FIELDS = Object.freeze(AUTOMATION_FIELDS.filter((field) => field !== "genero"));
const SELECT_FIELDS = new Set(["modalidade", "fundamento_legal"]);

const DATE_FIELDS = new Set(["data_publicacao_doe", "data_nascimento"]);
const PROCESS_KEY_RE = /^\d+\/\d{4}$/u;
const SHA256_RE = /^[0-9a-f]{64}$/u;
const PRIVATE_KEY_RE = /^(?:cpf|url|cookie|token|session|password|senha|authorization|dom|node|element)$/iu;
const UNSAFE_VALUE_RE = /(?:\b[a-z][a-z0-9+.-]*:\/\/|\bbearer\s+\S+|\b(?:cpf|token|cookie|session|password|senha)\s*[:=]\s*\S+|(?:^|[\s"'(])(?:[A-Za-z]:[\\/]|\\\\)|\r|\n)/iu;

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function addReason(reasons, reason) {
  if (!reasons.includes(reason)) reasons.push(reason);
}

function normalizeInterested(value) {
  return typeof value === "string"
    ? value.normalize("NFKD").replace(/\p{M}+/gu, "").toLowerCase().replace(/\s+/gu, " ").trim()
    : "";
}

function normalizeText(value) {
  return typeof value === "string"
    ? value.normalize("NFKC").replace(/\s+/gu, " ").trim().toLocaleLowerCase("pt-BR")
    : null;
}

function safeString(value) {
  return typeof value === "string"
    && value.length <= 512
    && !UNSAFE_VALUE_RE.test(value);
}

function canonicalIdentity(candidate) {
  if (!isRecord(candidate)) return null;
  const processKey = candidate.processKey ?? candidate.process_key;
  const interestedNormalized = candidate.interestedNormalized ?? candidate.interested_normalized;
  if (typeof processKey !== "string" || !PROCESS_KEY_RE.test(processKey)) return null;
  if (typeof interestedNormalized !== "string" || !interestedNormalized) return null;
  if (normalizeInterested(interestedNormalized) !== interestedNormalized) return null;
  return { processKey, interestedNormalized };
}

function identityFromRecord(record) {
  if (!isRecord(record)) return null;
  return canonicalIdentity({
    processKey: record.process?.key,
    interestedNormalized: record.interested?.normalized,
  });
}

function identityFromSnapshot(snapshot) {
  if (!isRecord(snapshot)) return null;
  if (isRecord(snapshot.identity)) return canonicalIdentity(snapshot.identity);
  if (isRecord(snapshot.selectedIdentity)) return canonicalIdentity(snapshot.selectedIdentity);
  return canonicalIdentity({
    processKey: snapshot.process?.key,
    interestedNormalized: snapshot.interested?.normalized,
  });
}

function sameIdentity(left, right) {
  return Boolean(left && right)
    && left.processKey === right.processKey
    && left.interestedNormalized === right.interestedNormalized;
}

function readFrame(snapshot) {
  const frame = isRecord(snapshot?.frame) ? snapshot.frame : {};
  const generation = snapshot?.generation
    ?? snapshot?.frame_generation
    ?? frame.generation;
  const frameId = snapshot?.frameId
    ?? snapshot?.frame_id
    ?? frame.frameId
    ?? frame.frame_id;
  const currentGeneration = snapshot?.currentGeneration
    ?? snapshot?.current_generation
    ?? snapshot?.expected_generation
    ?? frame.currentGeneration
    ?? frame.current_generation
    ?? generation;
  const currentFrameId = snapshot?.currentFrameId
    ?? snapshot?.current_frame_id
    ?? snapshot?.expected_frame_id
    ?? frame.currentFrameId
    ?? frame.current_frame_id
    ?? frameId;
  return { generation, frameId, currentGeneration, currentFrameId };
}

function expectedHashes(record, snapshot) {
  return [
    record?.dataset_sha256,
    record?.datasetSha256,
    record?.batch?.logical_sha256,
    snapshot?.dataset_sha256,
    snapshot?.datasetSha256,
  ].filter((value) => value !== undefined && value !== null && value !== "");
}

function parseCivilDate(value) {
  if (typeof value !== "string") return null;
  const displayMatch = /^(\d{2})[./-](\d{2})[./-](\d{4})$/u.exec(value);
  const isoMatch = /^(\d{4})[./-](\d{2})[./-](\d{2})$/u.exec(value);
  const match = displayMatch
    ? { day: displayMatch[1], month: displayMatch[2], year: displayMatch[3] }
    : isoMatch
      ? { day: isoMatch[3], month: isoMatch[2], year: isoMatch[1] }
      : null;
  if (!match) return null;
  const day = Number(match.day);
  const month = Number(match.month);
  const year = Number(match.year);
  if (year < 1 || month < 1 || month > 12 || day < 1) return null;
  const daysInMonth = [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
  if (day > daysInMonth) return null;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function isLeapYear(year) {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

function sameValue(field, current, proposed, options) {
  if (typeof current !== "string" || typeof proposed !== "string") return false;
  if (DATE_FIELDS.has(field)) {
    const currentDate = parseCivilDate(current);
    const proposedDate = parseCivilDate(proposed);
    return currentDate !== null && proposedDate !== null && currentDate === proposedDate;
  }
  if (Array.isArray(options)) return current === proposed;
  return normalizeText(current) === normalizeText(proposed);
}

function optionValueExists(options, proposed) {
  return Array.isArray(options) && options.some((option) => {
    const value = isRecord(option) ? option.value : option;
    return typeof value === "string" && value === proposed;
  });
}

function isSafeSelectTie(field, snapshotFields, options, matchedValues) {
  const currentState = isRecord(snapshotFields) && isRecord(snapshotFields[field])
    ? snapshotFields[field]
    : null;
  const current = currentState?.value;
  if (!safeString(current) || !current.trim()) return false;
  if (!isRecord(matchedValues) || !Object.hasOwn(matchedValues, field)) return false;
  const matchedValue = matchedValues[field];
  return safeString(matchedValue)
    && Boolean(matchedValue.trim())
    && current === matchedValue
    && optionValueExists(options[field], matchedValue);
}

function fieldProposal(field, recordField, legalDecision, matchedValues) {
  if (SELECT_FIELDS.has(field) && isRecord(matchedValues) && Object.hasOwn(matchedValues, field)) {
    const matchedValue = matchedValues[field];
    return typeof matchedValue === "string" && matchedValue.trim() ? matchedValue : null;
  }
  if (!isRecord(recordField) || typeof recordField.form_value !== "string" || !recordField.form_value.trim()) {
    return null;
  }
  if (field === "fundamento_legal") return legalDecision.option_value;
  const value = recordField.form_value;
  return typeof value === "string" && value.trim() ? value : null;
}

function baseEvidence(identity, context, frame, legalDecision) {
  const evidence = {};
  if (identity) evidence.identity = { ...identity };
  if (Number.isSafeInteger(frame.generation) && Number.isSafeInteger(frame.frameId)) {
    evidence.frame = { generation: frame.generation, frameId: frame.frameId };
  }
  if (isRecord(context)) {
    const safeContext = {
      schema_version: context.schema_version,
      dataset_sha256: context.dataset_sha256,
      process_key: context.process_key,
      interested_normalized: context.interested_normalized,
      resolution_status: context.resolution_status,
    };
    for (const key of ["context_revision", "rules_version"]) {
      if (Number.isSafeInteger(context[key]) || safeString(context[key])) safeContext[key] = context[key];
    }
    evidence.context = safeContext;
  }
  if (isRecord(legalDecision)) {
    const safeDecision = {};
    for (const key of ["status", "method", "rule_id", "option_value", "rules_version"]) {
      if (safeString(legalDecision[key])) safeDecision[key] = legalDecision[key];
    }
    for (const key of ["confidence", "margin"]) {
      if (typeof legalDecision[key] === "number" && Number.isFinite(legalDecision[key])) {
        safeDecision[key] = legalDecision[key];
      }
    }
    if (typeof legalDecision.hard_conflict === "boolean") {
      safeDecision.hard_conflict = legalDecision.hard_conflict;
    }
    evidence.legalDecision = safeDecision;
  }
  return evidence;
}

function result(eligible, fields, preserved, reasons, evidence) {
  return { eligible, fields, preserved, reasons, evidence };
}

export function isAutomaticLegalDecision(decision) {
  return decision?.status === "selected"
    && decision.decision_state === "AUTO_SELECTED"
    && decision.rules_version === "legal-foundation-v3"
    && decision.method !== "none"
    && decision.hard_conflict !== true
    && typeof decision.confidence === "number"
    && Number.isFinite(decision.confidence)
    && decision.confidence >= 0.90
    && typeof decision.margin === "number"
    && Number.isFinite(decision.margin)
    && decision.margin >= 0.12;
}

export function prepareAutomaticAct({ record, context, snapshot, legalDecision, matchedValues, matchKinds } = {}) {
  const reasons = [];
  const identity = identityFromRecord(record);
  const snapshotIdentity = identityFromSnapshot(snapshot);
  const frame = readFrame(snapshot);
  const evidence = baseEvidence(identity, context, frame, legalDecision);
  const recordFields = record?.fields;
  const snapshotFields = snapshot?.fields;
  const options = isRecord(snapshot?.options) ? snapshot.options : {};

  if (!identity) addReason(reasons, "RECORD_IDENTITY_INVALID");
  if (!snapshotIdentity || !sameIdentity(identity, snapshotIdentity)) addReason(reasons, "IDENTITY_MISMATCH");
  if (snapshot?.role !== undefined && snapshot.role !== "form") addReason(reasons, "SNAPSHOT_ROLE_MISMATCH");

  if (!Number.isSafeInteger(frame.generation) || frame.generation < 1) {
    addReason(reasons, "SNAPSHOT_GENERATION_MISSING");
  } else if (frame.currentGeneration !== frame.generation) {
    addReason(reasons, "STALE_GENERATION");
  }
  if (!Number.isSafeInteger(frame.frameId) || frame.frameId < 0) {
    addReason(reasons, "SNAPSHOT_FRAME_MISSING");
  } else if (frame.currentFrameId !== frame.frameId) {
    addReason(reasons, "STALE_FRAME");
  }

  if (!isRecord(context)) {
    addReason(reasons, "CONTEXT_MISSING");
  } else {
    if (context.schema_version !== 1
      || context.resolution_status !== "complete"
      || typeof context.operative_text !== "string"
      || !Array.isArray(context.pages)) {
      addReason(reasons, "CONTEXT_INCOMPLETE");
    }
    if (!identity
      || context.process_key !== identity.processKey
      || context.interested_normalized !== identity.interestedNormalized) {
      addReason(reasons, "CONTEXT_IDENTITY_MISMATCH");
    }
    const hashes = expectedHashes(record, snapshot);
    if (typeof context.dataset_sha256 !== "string" || !SHA256_RE.test(context.dataset_sha256)) {
      addReason(reasons, "CONTEXT_HASH_MISMATCH");
    } else if (hashes.length === 0 || hashes.some((hash) => hash !== context.dataset_sha256)) {
      addReason(reasons, hashes.length === 0 ? "CONTEXT_HASH_MISSING" : "CONTEXT_HASH_MISMATCH");
    }
    if (Number.isSafeInteger(snapshot?.context_revision)
      && Number.isSafeInteger(context.context_revision)
      && snapshot.context_revision !== context.context_revision) {
      addReason(reasons, "CONTEXT_REVISION_MISMATCH");
    }
  }

  if (!isRecord(legalDecision)
    || legalDecision.status !== "selected"
    || legalDecision.method === "none") {
    addReason(reasons, "LEGAL_DECISION_NOT_SELECTED");
  } else if (!isAutomaticLegalDecision(legalDecision)) {
    addReason(reasons, "LEGAL_DECISION_REVIEW_REQUIRED");
  }
  if (!safeString(legalDecision?.option_value) || !legalDecision.option_value.trim()) {
    addReason(reasons, "LEGAL_DECISION_VALUE_MISSING");
  }
  if (context?.rules_version && legalDecision?.rules_version
    && context.rules_version !== legalDecision.rules_version) {
    addReason(reasons, "LEGAL_RULES_VERSION_MISMATCH");
  }
  if ([...SELECT_FIELDS].some((field) => matchKinds?.[field] === "tie"
    && !isSafeSelectTie(field, snapshotFields, options, matchedValues))) {
    addReason(reasons, "SELECT_MATCH_TIE");
  }

  if (!isRecord(recordFields) || !isRecord(snapshotFields)) {
    addReason(reasons, "FIELDS_SNAPSHOT_INCOMPLETE");
  } else {
    if (Object.keys(recordFields).some((field) => !AUTOMATION_FIELDS.includes(field))
      || Object.keys(snapshotFields).some((field) => !AUTOMATION_FIELDS.includes(field))) {
      addReason(reasons, "FIELD_ALLOWLIST_VIOLATION");
    }
    for (const field of AUTOMATION_FIELDS) {
      if (!Object.hasOwn(recordFields, field) || !Object.hasOwn(snapshotFields, field)) {
        addReason(reasons, "FIELDS_SNAPSHOT_INCOMPLETE");
      }
    }
  }

  if (!Array.isArray(options.fundamento_legal)) addReason(reasons, "OPTION_CATALOG_MISSING");
  if (Object.values(options).some((value) => !Array.isArray(value))) addReason(reasons, "OPTION_CATALOG_INVALID");

  if (reasons.length > 0) return result(false, {}, {}, reasons, evidence);

  const fields = {};
  const preserved = {};
  const fieldEvidence = {};
  let hasDivergence = false;
  let unsafeInput = false;

  for (const field of AUTOMATION_FIELDS) {
    const source = recordFields[field];
    const currentState = snapshotFields[field];
    if (!isRecord(source) || !isRecord(currentState) || typeof currentState.value !== "string") {
      addReason(reasons, "FIELDS_SNAPSHOT_INCOMPLETE");
      continue;
    }
    const current = currentState.value;
    const proposed = fieldProposal(field, source, legalDecision, matchedValues);
    if (!safeString(current) || (proposed !== null && !safeString(proposed))) {
      addReason(reasons, "PRIVATE_DATA_REJECTED");
      unsafeInput = true;
      continue;
    }
    if (typeof source.source_value === "string" && !safeString(source.source_value)) {
      addReason(reasons, "PRIVATE_DATA_REJECTED");
      unsafeInput = true;
      continue;
    }

    if (DATE_FIELDS.has(field)) {
      if (proposed !== null && parseCivilDate(proposed) === null) addReason(reasons, "INVALID_CIVIL_DATE");
      if (current !== "" && parseCivilDate(current) === null) addReason(reasons, "CURRENT_CIVIL_DATE_INVALID");
    }
    const selectOptions = options[field];
    if (proposed !== null && Array.isArray(selectOptions) && !optionValueExists(selectOptions, proposed)) {
      addReason(reasons, "OPTION_VALUE_NOT_PRESENT");
    }
    if (proposed === null) {
      preserved[field] = current;
      if (REQUIRED_AUTOMATION_FIELDS.includes(field)) addReason(reasons, "FIELD_PROPOSAL_MISSING");
      fieldEvidence[field] = { current, proposed: null, action: "preserve" };
      continue;
    }
    if (current !== "" && sameValue(field, current, proposed, selectOptions)) {
      preserved[field] = current;
      fieldEvidence[field] = { current, proposed, action: "preserve" };
      continue;
    }
    if (current !== "") {
      hasDivergence = true;
      preserved[field] = current;
      fieldEvidence[field] = { current, proposed, action: "preserve", divergent: true };
      addReason(reasons, "EXISTING_VALUE_CONFLICT");
      continue;
    }
    if (currentState.disabled === true) {
      preserved[field] = current;
      addReason(reasons, "FIELD_DISABLED");
      fieldEvidence[field] = { current, proposed, action: "preserve", disabled: true };
      continue;
    }
    if (currentState.readOnly === true) {
      preserved[field] = current;
      addReason(reasons, "FIELD_READ_ONLY");
      fieldEvidence[field] = { current, proposed, action: "preserve", readOnly: true };
      continue;
    }
    fields[field] = proposed;
    fieldEvidence[field] = { current, proposed, action: "prepare" };
  }

  evidence.fields = fieldEvidence;
  if (hasDivergence || unsafeInput) return result(false, {}, unsafeInput ? {} : preserved, reasons, evidence);
  if (reasons.length > 0) return result(false, {}, preserved, reasons, evidence);
  return result(true, fields, preserved, [], evidence);
}

export { AUTOMATION_FIELDS, sameValue };
