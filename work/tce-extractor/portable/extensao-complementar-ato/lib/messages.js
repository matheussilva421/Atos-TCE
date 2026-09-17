import {
  ALLOWED_FIELDS,
  ALLOWED_ORIGIN,
  SCHEMA_VERSION,
  SchemaValidationError,
  validatePortalUrl,
} from "./schema.js";
import {
  validateAutomationEvent,
  validateAutomationIdentity,
  validateAutomationRunSpec,
  validateControlRequest,
  validateLegalContext,
} from "./automation-schema.js";

export const MESSAGE_TYPES = Object.freeze({
  FORM_READY: "FORM_READY",
  GET_FORM_SNAPSHOT: "GET_FORM_SNAPSHOT",
  IMPORT_DATASET: "IMPORT_DATASET",
  GET_MATCH: "GET_MATCH",
  APPLY_FIELDS: "APPLY_FIELDS",
  OVERRIDE_FIELD: "OVERRIDE_FIELD",
  SET_REVIEWED: "SET_REVIEWED",
  REQUEST_COMPLEMENTAR_ATO: "REQUEST_COMPLEMENTAR_ATO",
  AUTO_START: "AUTO_START",
  AUTO_ANALYZE: "AUTO_ANALYZE",
  AUTO_PAUSE: "AUTO_PAUSE",
  AUTO_RESUME: "AUTO_RESUME",
  AUTO_STOP: "AUTO_STOP",
  AUTO_STATUS: "AUTO_STATUS",
  AUTO_CONSUME_COMMAND: "AUTO_CONSUME_COMMAND",
  AUTO_SUBMIT_COMMAND: "AUTO_SUBMIT_COMMAND",
  AUTO_VERIFY_SUBMIT_STATE: "AUTO_VERIFY_SUBMIT_STATE",
  SUBMIT_FRAME_READY: "SUBMIT_FRAME_READY",
  PORTAL_GET_SNAPSHOT: "PORTAL_GET_SNAPSHOT",
  PORTAL_NAVIGATE: "PORTAL_NAVIGATE",
  PORTAL_EVENT: "PORTAL_EVENT",
});

const MESSAGE_TYPE_SET = new Set(Object.values(MESSAGE_TYPES));
const MESSAGE_KEYS = ["schemaVersion", "type", "requestId", "payload"];
const MATCH_KIND_SET = new Set(["exact", "probable", "tie"]);
const PORTAL_ACTION_SET = new Set(["first_page", "next_page", "open_act", "select_interested", "return_list", "filter_marker", "find_process"]);
const PORTAL_ROLE_SET = new Set(["list", "interested", "form", "buttons", "unknown"]);
const PORTAL_SOURCE_SCOPE_SET = new Set(["sector_finalistic", "my_processes"]);
const PORTAL_EVENT_SET = new Set(["snapshot", "navigation", "manual_navigation", "sector_changed", "frame_unavailable"]);
const PORTAL_IDENTITY_KEYS = ["processKey", "interestedOriginal", "interestedNormalized", "portalActId", "pending", "selected", "needsComplement", "classification", "actionObserved", "actionSignature"];
const AREA_CLASSIFICATION_SET = new Set(["PRECISA_COMPLEMENTAR", "ATO_COMPLEMENTADO", "NAO_ENCONTRADO_AREA_RESTRITA", "AMBIGUO", "BLOQUEADO"]);

function invalid(message) {
  throw new SchemaValidationError(`message ${message}`);
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value, expected, label) {
  const keys = Object.keys(value);
  if (keys.length !== expected.length || expected.some((key) => !keys.includes(key))) {
    invalid(`${label} has unexpected keys`);
  }
}

function exactKeysFrom(value, required, optional, label) {
  const allowed = new Set([...required, ...optional]);
  const keys = Object.keys(value);
  if (keys.some((key) => !allowed.has(key)) || required.some((key) => !Object.hasOwn(value, key))) {
    invalid(`${label} has unexpected keys`);
  }
}

function nonEmptyString(value, label) {
  if (typeof value !== "string" || value.length === 0 || value.length > 256) invalid(`${label} must be a non-empty string`);
}

function validateFields(fields) {
  if (!isRecord(fields)) invalid("payload.fields must be an object");
  for (const key of Object.keys(fields)) {
    if (!ALLOWED_FIELDS.includes(key)) invalid(`payload.fields contains unsupported field ${key}`);
    const value = fields[key];
    if (typeof value !== "string" && value !== null) invalid(`payload.fields.${key} must be a string or null`);
  }
}

function validateMatchKinds(matchKinds) {
  if (!isRecord(matchKinds)) invalid("payload.matchKinds must be an object");
  for (const [field, kind] of Object.entries(matchKinds)) {
    if (!ALLOWED_FIELDS.includes(field)) invalid(`payload.matchKinds contains unsupported field ${field}`);
    if (!MATCH_KIND_SET.has(kind)) {
      invalid(`payload.matchKinds.${field} must be exact, probable, or tie`);
    }
  }
}

function safeGeneratedMatchKind(value) {
  if (value === "pending") return "tie";
  if (!isRecord(value)) return value;

  const status = value.status ?? value.legalDecision?.status;
  if (value.kind === "pending" || status === "pending") return "tie";
  if (MATCH_KIND_SET.has(value.kind)) return value.kind;
  return value;
}

function normalizeGeneratedPayload(type, payload) {
  if (type !== MESSAGE_TYPES.APPLY_FIELDS || !isRecord(payload) || !isRecord(payload.matchKinds)) {
    return payload;
  }

  return {
    ...payload,
    matchKinds: Object.fromEntries(
      Object.entries(payload.matchKinds).map(([field, value]) => [field, safeGeneratedMatchKind(value)]),
    ),
  };
}

function validateOptions(options) {
  if (!isRecord(options)) invalid("payload.options must be an object");
  for (const [field, candidates] of Object.entries(options)) {
    if (!ALLOWED_FIELDS.includes(field)) invalid(`payload.options contains unsupported field ${field}`);
    if (!Array.isArray(candidates)) invalid(`payload.options.${field} must be an array`);
    candidates.forEach((candidate, index) => {
      if (typeof candidate === "string") return;
      if (!isRecord(candidate)) invalid(`payload.options.${field}[${index}] must be an object`);
      exactKeys(candidate, ["value", "label"], `payload.options.${field}[${index}]`);
      if (typeof candidate.value !== "string" || typeof candidate.label !== "string") {
        invalid(`payload.options.${field}[${index}] value and label must be strings`);
      }
    });
  }
}

function validateSubmitCommand(command, label = "AUTO_SUBMIT_COMMAND command") {
  if (!isRecord(command)) invalid(`${label} is invalid`);
  exactKeysFrom(
    command,
    ["command_id", "state", "issued_at", "expires_at", "frame_id", "generation", "identity", "expected_fields_hash"],
    ["button_id", "form_frame_id"],
    label,
  );
  nonEmptyString(command.command_id, `${label}.command_id`, 256);
  if (command.state !== "issued") invalid(`${label}.state is invalid`);
  for (const key of ["issued_at", "expires_at"]) {
    if (!Number.isSafeInteger(command[key]) || command[key] <= 0) invalid(`${label}.${key} is invalid`);
  }
  if (command.expires_at <= command.issued_at || command.expires_at - command.issued_at > 15_000) {
    invalid(`${label} lifetime is invalid`);
  }
  if (!Number.isSafeInteger(command.frame_id) || command.frame_id < 0) invalid(`${label}.frame_id is invalid`);
  if (Object.hasOwn(command, "form_frame_id")
    && (!Number.isSafeInteger(command.form_frame_id) || command.form_frame_id < 0)) {
    invalid(`${label}.form_frame_id is invalid`);
  }
  if (!Number.isSafeInteger(command.generation) || command.generation < 1) invalid(`${label}.generation is invalid`);
  if (typeof command.expected_fields_hash !== "string" || !/^[0-9a-f]{64}$/u.test(command.expected_fields_hash)) {
    invalid(`${label}.expected_fields_hash is invalid`);
  }
  try {
    validateAutomationIdentity(command.identity);
  } catch (error) {
    invalid(error instanceof Error ? error.message : `${label}.identity is invalid`);
  }
  if (Object.hasOwn(command, "button_id")) nonEmptyString(command.button_id, `${label}.button_id`, 256);
}

function validatePortalIdentity(value, label = "portal identity") {
  if (!isRecord(value)) invalid(`${label} must be an object`);
  exactKeysFrom(value, [], PORTAL_IDENTITY_KEYS, label);
  if (Object.hasOwn(value, "processKey") && value.processKey !== null && (typeof value.processKey !== "string" || value.processKey.length === 0 || value.processKey.length > 256)) {
    invalid(`${label}.processKey must be a non-empty string or null`);
  }
  if (Object.hasOwn(value, "interestedOriginal") && (typeof value.interestedOriginal !== "string" || value.interestedOriginal.length > 256)) {
    invalid(`${label}.interestedOriginal must be a string`);
  }
  if (Object.hasOwn(value, "interestedNormalized") && value.interestedNormalized !== null && (typeof value.interestedNormalized !== "string" || value.interestedNormalized.length === 0 || value.interestedNormalized.length > 256)) {
    invalid(`${label}.interestedNormalized must be a non-empty string or null`);
  }
  if (Object.hasOwn(value, "portalActId") && value.portalActId !== null && (typeof value.portalActId !== "string" || value.portalActId.length > 256)) {
    invalid(`${label}.portalActId must be a string or null`);
  }
  if (Object.hasOwn(value, "pending") && typeof value.pending !== "boolean") invalid(`${label}.pending must be a boolean`);
  if (Object.hasOwn(value, "selected") && typeof value.selected !== "boolean") invalid(`${label}.selected must be a boolean`);
  if (Object.hasOwn(value, "needsComplement") && typeof value.needsComplement !== "boolean") invalid(`${label}.needsComplement must be a boolean`);
  if (Object.hasOwn(value, "classification") && (typeof value.classification !== "string" || !AREA_CLASSIFICATION_SET.has(value.classification))) {
    invalid(`${label}.classification is invalid`);
  }
  if (Object.hasOwn(value, "actionObserved") && value.actionObserved !== null
    && (typeof value.actionObserved !== "string" || value.actionObserved.length > 256)) {
    invalid(`${label}.actionObserved must be a string or null`);
  }
  if (Object.hasOwn(value, "actionSignature") && value.actionSignature !== null) {
    const signature = value.actionSignature;
    if (!isRecord(signature)
      || Object.keys(signature).some((key) => !["kind", "alt", "title", "src"].includes(key))
      || typeof signature.kind !== "string"
      || signature.kind !== "red_complement_icon"
      || typeof signature.alt !== "string"
      || typeof signature.title !== "string"
      || typeof signature.src !== "string") {
      invalid(`${label}.actionSignature is invalid`);
    }
  }
  const canonical = typeof value.processKey === "string"
    && value.processKey.length > 0
    && typeof value.interestedNormalized === "string"
    && value.interestedNormalized.length > 0;
  if (!canonical && value.pending !== true) invalid(`${label}.pending must be true when canonical identity is incomplete`);
  if (canonical && value.pending === true) invalid(`${label}.pending cannot be true for a canonical identity`);
}

function isCanonicalPortalIdentity(value) {
  return isRecord(value)
    && typeof value.processKey === "string"
    && value.processKey.length > 0
    && typeof value.interestedNormalized === "string"
    && value.interestedNormalized.length > 0
    && value.pending !== true;
}

function validatePortalSnapshot(value) {
  if (!isRecord(value)) invalid("PORTAL snapshot must be an object");
  exactKeysFrom(value, ["role", "generation", "sector", "identities", "actions"], ["marker", "source_scope"], "PORTAL snapshot");
  if (!PORTAL_ROLE_SET.has(value.role)) invalid("PORTAL snapshot role is invalid");
  if (!Number.isSafeInteger(value.generation) || value.generation < 1) invalid("PORTAL snapshot generation is invalid");
  if (value.sector !== null && typeof value.sector !== "string") invalid("PORTAL snapshot sector is invalid");
  if (Object.hasOwn(value, "source_scope")
    && value.source_scope !== null
    && !PORTAL_SOURCE_SCOPE_SET.has(value.source_scope)) invalid("PORTAL snapshot source_scope is invalid");
  if (!Array.isArray(value.identities) || !Array.isArray(value.actions)) invalid("PORTAL snapshot collections are invalid");
  value.identities.forEach((identity, index) => validatePortalIdentity(identity, `PORTAL snapshot identity ${index}`));
  if (Object.hasOwn(value, "marker")) {
    if (value.marker !== null) {
      if (!isRecord(value.marker)) invalid("PORTAL snapshot marker is invalid");
      exactKeys(value.marker, ["label", "value"], "PORTAL snapshot marker");
      nonEmptyString(value.marker.label, "PORTAL snapshot marker.label");
      if (value.marker.value !== null && (typeof value.marker.value !== "string" || value.marker.value.length > 256)) {
        invalid("PORTAL snapshot marker.value is invalid");
      }
    }
  }
  value.actions.forEach((action, index) => {
    if (!isRecord(action)) invalid(`PORTAL snapshot action ${index} is invalid`);
    exactKeysFrom(action, ["action", "enabled"], ["identity", "direction"], `PORTAL snapshot action ${index}`);
    if (typeof action.action !== "string" || !PORTAL_ACTION_SET.has(action.action)) invalid(`PORTAL snapshot action ${index} is unsupported`);
    if (typeof action.enabled !== "boolean") invalid(`PORTAL snapshot action ${index}.enabled is invalid`);
    if (Object.hasOwn(action, "direction") && (action.action !== "next_page" || !["next", "first"].includes(action.direction))) {
      invalid(`PORTAL snapshot action ${index}.direction is invalid`);
    }
    if (Object.hasOwn(action, "identity")) validatePortalIdentity(action.identity, `PORTAL snapshot action ${index}.identity`);
    if (["open_act", "select_interested"].includes(action.action) && !isCanonicalPortalIdentity(action.identity)) {
      invalid(`PORTAL snapshot action ${index}.identity must be canonical`);
    }
  });
}

function validatePayload(type, payload) {
  if (!isRecord(payload)) invalid(`${type} payload must be an object`);
  switch (type) {
    case MESSAGE_TYPES.FORM_READY:
      exactKeys(payload, ["url"], "FORM_READY payload");
      if (!validatePortalUrl(payload.url)) invalid(`FORM_READY origin must be ${ALLOWED_ORIGIN}`);
      break;
    case MESSAGE_TYPES.GET_FORM_SNAPSHOT:
      exactKeys(payload, [], "GET_FORM_SNAPSHOT payload");
      break;
    case MESSAGE_TYPES.IMPORT_DATASET:
      exactKeys(
        payload,
        Object.hasOwn(payload, "preserveReviewed") ? ["dataset", "preserveReviewed"] : ["dataset"],
        "IMPORT_DATASET payload",
      );
      if (!isRecord(payload.dataset)) invalid("IMPORT_DATASET dataset must be an object");
      if (Object.hasOwn(payload, "preserveReviewed") && typeof payload.preserveReviewed !== "boolean") {
        invalid("IMPORT_DATASET preserveReviewed must be a boolean");
      }
      break;
    case MESSAGE_TYPES.GET_MATCH:
      exactKeysFrom(
        payload,
        ["processKey", "interestedNormalized", "options"],
        ["datasetSha256"],
        "GET_MATCH payload",
      );
      nonEmptyString(payload.processKey, "GET_MATCH processKey");
      nonEmptyString(payload.interestedNormalized, "GET_MATCH interestedNormalized");
      validateOptions(payload.options);
      if (Object.hasOwn(payload, "datasetSha256") && (typeof payload.datasetSha256 !== "string" || !/^[0-9a-f]{64}$/u.test(payload.datasetSha256))) {
        invalid("GET_MATCH datasetSha256 is invalid");
      }
      break;
    case MESSAGE_TYPES.APPLY_FIELDS:
      exactKeys(
        payload,
        ["fields",
          ...(Object.hasOwn(payload, "matchKinds") ? ["matchKinds"] : []),
          ...(Object.hasOwn(payload, "legalDecision") ? ["legalDecision"] : [])],
        "APPLY_FIELDS payload",
      );
      validateFields(payload.fields);
      if (Object.hasOwn(payload, "matchKinds")) validateMatchKinds(payload.matchKinds);
      if (Object.hasOwn(payload, "legalDecision") && !isRecord(payload.legalDecision)) {
        invalid("APPLY_FIELDS legalDecision must be an object");
      }
      break;
    case MESSAGE_TYPES.OVERRIDE_FIELD:
      exactKeysFrom(
        payload,
        ["field", "proposedValue"],
        ["matchKinds", "legalDecision"],
        "OVERRIDE_FIELD payload",
      );
      if (!ALLOWED_FIELDS.includes(payload.field)) invalid("OVERRIDE_FIELD field is unsupported");
      if (typeof payload.proposedValue !== "string") invalid("OVERRIDE_FIELD proposedValue must be a string");
      if (Object.hasOwn(payload, "matchKinds")) validateMatchKinds(payload.matchKinds);
      if (Object.hasOwn(payload, "legalDecision") && !isRecord(payload.legalDecision)) {
        invalid("OVERRIDE_FIELD legalDecision must be an object");
      }
      break;
    case MESSAGE_TYPES.SET_REVIEWED:
      exactKeys(payload, ["processKey", "interestedNormalized", "reviewed"], "SET_REVIEWED payload");
      nonEmptyString(payload.processKey, "SET_REVIEWED processKey");
      nonEmptyString(payload.interestedNormalized, "SET_REVIEWED interestedNormalized");
      if (typeof payload.reviewed !== "boolean") invalid("SET_REVIEWED reviewed must be boolean");
      break;
    case MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO:
      exactKeys(payload, ["processKey", "interestedNormalized"], "REQUEST_COMPLEMENTAR_ATO payload");
      nonEmptyString(payload.processKey, "REQUEST_COMPLEMENTAR_ATO processKey");
      nonEmptyString(payload.interestedNormalized, "REQUEST_COMPLEMENTAR_ATO interestedNormalized");
      break;
    case MESSAGE_TYPES.AUTO_START:
      exactKeys(payload, ["spec", "eventId"], "AUTO_START payload");
      try {
        validateAutomationRunSpec(payload.spec);
      } catch (error) {
        invalid(error instanceof Error ? error.message : "AUTO_START spec is invalid");
      }
      nonEmptyString(payload.eventId, "AUTO_START eventId");
      break;
    case MESSAGE_TYPES.AUTO_ANALYZE: {
      exactKeys(payload, ["spec", "eventId"], "AUTO_ANALYZE payload");
      const spec = payload.spec;
      if (!isRecord(spec)) invalid("AUTO_ANALYZE spec must be an object");
      exactKeysFrom(
        spec,
        ["sector", "datasetSha256", "rulesVersion", "sourceScope", "lotSize", "acquisitionSource"],
        ["tabId", "marker", "analysisOnly", "inputListId", "inputSha256", "inputUniqueCount", "inputKeys"],
        "AUTO_ANALYZE spec",
      );
      nonEmptyString(spec.sector, "AUTO_ANALYZE sector");
      if (spec.datasetSha256 !== null && (typeof spec.datasetSha256 !== "string" || !/^[0-9a-f]{64}$/u.test(spec.datasetSha256))) invalid("AUTO_ANALYZE datasetSha256 is invalid");
      if (spec.datasetSha256 === null && spec.analysisOnly !== true) invalid("AUTO_ANALYZE datasetSha256 is invalid");
      nonEmptyString(spec.rulesVersion, "AUTO_ANALYZE rulesVersion");
      if (Object.hasOwn(spec, "marker")) nonEmptyString(spec.marker, "AUTO_ANALYZE marker");
      if (Object.hasOwn(spec, "analysisOnly") && typeof spec.analysisOnly !== "boolean") invalid("AUTO_ANALYZE analysisOnly is invalid");
      if (!new Set(["sector_finalistic", "my_processes"]).has(spec.sourceScope)) invalid("AUTO_ANALYZE sourceScope is invalid");
      if (!Number.isSafeInteger(spec.lotSize) || spec.lotSize < 1 || spec.lotSize > 1000) invalid("AUTO_ANALYZE lotSize is invalid");
      if (spec.acquisitionSource !== "econtas") invalid("AUTO_ANALYZE acquisitionSource is invalid");
      if (Object.hasOwn(spec, "tabId") && (!Number.isSafeInteger(spec.tabId) || spec.tabId < 0)) invalid("AUTO_ANALYZE tabId is invalid");
      if (Object.hasOwn(spec, "inputListId") && (typeof spec.inputListId !== "string" || !/^input-[0-9a-f]{24}$/u.test(spec.inputListId))) invalid("AUTO_ANALYZE inputListId is invalid");
      if (Object.hasOwn(spec, "inputSha256") && (typeof spec.inputSha256 !== "string" || !/^[0-9a-f]{64}$/u.test(spec.inputSha256))) invalid("AUTO_ANALYZE inputSha256 is invalid");
      if (Object.hasOwn(spec, "inputUniqueCount") && (!Number.isSafeInteger(spec.inputUniqueCount) || spec.inputUniqueCount < 1 || spec.inputUniqueCount > 10000)) invalid("AUTO_ANALYZE inputUniqueCount is invalid");
      if (Object.hasOwn(spec, "inputKeys")) {
        if (!Array.isArray(spec.inputKeys) || spec.inputKeys.length > 10000 || spec.inputKeys.some((key) => typeof key !== "string" || !/^\d+\/\d{4}$/u.test(key))) invalid("AUTO_ANALYZE inputKeys is invalid");
      }
      nonEmptyString(payload.eventId, "AUTO_ANALYZE eventId");
      break;
    }
    case MESSAGE_TYPES.AUTO_PAUSE:
    case MESSAGE_TYPES.AUTO_RESUME:
    case MESSAGE_TYPES.AUTO_STOP:
      exactKeys(payload, ["runId", "eventId", "expectedRevision"], `${type} payload`);
      nonEmptyString(payload.runId, `${type} runId`, 128);
      try {
        validateControlRequest({
          action: type.slice("AUTO_".length).toLowerCase(),
          eventId: payload.eventId,
          expectedRevision: payload.expectedRevision,
        });
      } catch (error) {
        invalid(error instanceof Error ? error.message : `${type} payload is invalid`);
      }
      break;
    case MESSAGE_TYPES.AUTO_STATUS:
      exactKeys(payload, ["runId"], "AUTO_STATUS payload");
      nonEmptyString(payload.runId, "AUTO_STATUS runId", 128);
      break;
    case MESSAGE_TYPES.AUTO_CONSUME_COMMAND:
      exactKeys(payload, ["runId", "commandId", "expectedRevision", "generation", "identity"], "AUTO_CONSUME_COMMAND payload");
      nonEmptyString(payload.runId, "AUTO_CONSUME_COMMAND runId", 128);
      nonEmptyString(payload.commandId, "AUTO_CONSUME_COMMAND commandId", 256);
      if (!Number.isSafeInteger(payload.expectedRevision) || payload.expectedRevision < 0) invalid("AUTO_CONSUME_COMMAND expectedRevision is invalid");
      if (!Number.isSafeInteger(payload.generation) || payload.generation < 1) invalid("AUTO_CONSUME_COMMAND generation is invalid");
      try {
        validateAutomationIdentity(payload.identity);
      } catch (error) {
        invalid(error instanceof Error ? error.message : "AUTO_CONSUME_COMMAND identity is invalid");
      }
      break;
    case MESSAGE_TYPES.AUTO_SUBMIT_COMMAND: {
      exactKeys(payload, ["runId", "expectedRevision", "command"], "AUTO_SUBMIT_COMMAND payload");
      nonEmptyString(payload.runId, "AUTO_SUBMIT_COMMAND runId", 128);
      if (!Number.isSafeInteger(payload.expectedRevision) || payload.expectedRevision < 0) invalid("AUTO_SUBMIT_COMMAND expectedRevision is invalid");
      validateSubmitCommand(payload.command);
      break;
    }
    case MESSAGE_TYPES.AUTO_VERIFY_SUBMIT_STATE: {
      exactKeys(payload, ["runId", "expectedRevision", "command", "phase"], "AUTO_VERIFY_SUBMIT_STATE payload");
      nonEmptyString(payload.runId, "AUTO_VERIFY_SUBMIT_STATE runId", 128);
      if (!Number.isSafeInteger(payload.expectedRevision) || payload.expectedRevision < 0) invalid("AUTO_VERIFY_SUBMIT_STATE expectedRevision is invalid");
      if (!["before_consume", "before_click"].includes(payload.phase)) invalid("AUTO_VERIFY_SUBMIT_STATE phase is invalid");
      validateSubmitCommand(payload.command, "AUTO_VERIFY_SUBMIT_STATE command");
      break;
    }
    case MESSAGE_TYPES.SUBMIT_FRAME_READY:
      exactKeysFrom(payload, ["url"], ["button_id"], "SUBMIT_FRAME_READY payload");
      if (!validatePortalUrl(payload.url)) invalid(`SUBMIT_FRAME_READY origin must be ${ALLOWED_ORIGIN}`);
      if (Object.hasOwn(payload, "button_id")) nonEmptyString(payload.button_id, "SUBMIT_FRAME_READY button_id", 256);
      break;
    case MESSAGE_TYPES.PORTAL_GET_SNAPSHOT:
      exactKeys(payload, [], "PORTAL_GET_SNAPSHOT payload");
      break;
    case MESSAGE_TYPES.PORTAL_NAVIGATE:
      exactKeysFrom(payload, ["action", "expected_generation"], ["identity", "timeoutMs", "marker", "process_key"], "PORTAL_NAVIGATE payload");
      if (typeof payload.action !== "string" || !PORTAL_ACTION_SET.has(payload.action)) invalid("PORTAL_NAVIGATE action is unsupported");
      if (!Number.isSafeInteger(payload.expected_generation) || payload.expected_generation < 1) invalid("PORTAL_NAVIGATE expected_generation is invalid");
      if (Object.hasOwn(payload, "identity") && payload.identity !== null) validatePortalIdentity(payload.identity, "PORTAL_NAVIGATE identity");
      if (["open_act", "select_interested"].includes(payload.action) && !isCanonicalPortalIdentity(payload.identity)) {
        invalid("PORTAL_NAVIGATE identity must be canonical");
      }
      if (payload.action === "filter_marker") {
        nonEmptyString(payload.marker, "PORTAL_NAVIGATE marker");
        if (!payload.marker.trim()) invalid("PORTAL_NAVIGATE marker must not be blank");
      } else if (Object.hasOwn(payload, "marker")) {
        invalid("PORTAL_NAVIGATE marker is only valid for filter_marker");
      }
      if (Object.hasOwn(payload, "process_key")) {
        if (typeof payload.process_key !== "string" || !/^\d+\/\d{4}$/u.test(payload.process_key)) {
          invalid("PORTAL_NAVIGATE process_key is invalid");
        }
        if (payload.action !== "find_process") {
          invalid("PORTAL_NAVIGATE process_key is only valid for find_process");
        }
      }
      if (Object.hasOwn(payload, "timeoutMs") && (!Number.isSafeInteger(payload.timeoutMs) || payload.timeoutMs <= 0 || payload.timeoutMs > 30000)) invalid("PORTAL_NAVIGATE timeoutMs is invalid");
      break;
    case MESSAGE_TYPES.PORTAL_EVENT:
      exactKeys(payload, ["event"], "PORTAL_EVENT payload");
      if (!isRecord(payload.event)) invalid("PORTAL_EVENT event must be an object");
      exactKeysFrom(payload.event, ["type"], ["snapshot"], "PORTAL_EVENT event");
      if (typeof payload.event.type !== "string" || !PORTAL_EVENT_SET.has(payload.event.type)) invalid("PORTAL_EVENT type is unsupported");
      if (Object.hasOwn(payload.event, "snapshot") && payload.event.snapshot !== null) validatePortalSnapshot(payload.event.snapshot);
      break;
    default:
      invalid(`type ${type} is unsupported`);
  }
}

export function validateMessage(message) {
  if (!isRecord(message)) invalid("must be an object");
  exactKeys(message, MESSAGE_KEYS, "message");
  if (message.schemaVersion !== SCHEMA_VERSION) invalid("unsupported schema version");
  if (typeof message.type !== "string" || !MESSAGE_TYPE_SET.has(message.type)) invalid("type is unsupported");
  nonEmptyString(message.requestId, "requestId");
  validatePayload(message.type, message.payload);
  return message;
}

export function createMessage(type, payload, requestId) {
  const message = {
    schemaVersion: SCHEMA_VERSION,
    type,
    requestId,
    payload: normalizeGeneratedPayload(type, payload),
  };
  return validateMessage(message);
}
