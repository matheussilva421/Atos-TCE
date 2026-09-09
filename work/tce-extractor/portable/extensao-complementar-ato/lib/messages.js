import {
  ALLOWED_FIELDS,
  ALLOWED_ORIGIN,
  SCHEMA_VERSION,
  SchemaValidationError,
  validatePortalUrl,
} from "./schema.js";
import {
  validateAutomationEvent,
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
  AUTO_PAUSE: "AUTO_PAUSE",
  AUTO_RESUME: "AUTO_RESUME",
  AUTO_STOP: "AUTO_STOP",
  AUTO_STATUS: "AUTO_STATUS",
  PORTAL_GET_SNAPSHOT: "PORTAL_GET_SNAPSHOT",
  PORTAL_NAVIGATE: "PORTAL_NAVIGATE",
  PORTAL_EVENT: "PORTAL_EVENT",
});

const MESSAGE_TYPE_SET = new Set(Object.values(MESSAGE_TYPES));
const MESSAGE_KEYS = ["schemaVersion", "type", "requestId", "payload"];
const MATCH_KIND_SET = new Set(["exact", "probable", "tie"]);
const PORTAL_ACTION_SET = new Set(["next_page", "open_act", "select_interested", "return_list"]);
const PORTAL_ROLE_SET = new Set(["list", "interested", "form", "buttons", "unknown"]);
const PORTAL_EVENT_SET = new Set(["snapshot", "navigation", "manual_navigation", "sector_changed", "frame_unavailable"]);

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

function validatePortalIdentity(value, label = "portal identity") {
  if (!isRecord(value)) invalid(`${label} must be an object`);
  if (typeof value.processKey !== "string" || value.processKey.length === 0 || value.processKey.length > 256) {
    invalid(`${label}.processKey must be a non-empty string`);
  }
  if (typeof value.interestedNormalized !== "string" || value.interestedNormalized.length === 0 || value.interestedNormalized.length > 256) {
    invalid(`${label}.interestedNormalized must be a non-empty string`);
  }
  if (Object.hasOwn(value, "portalActId") && value.portalActId !== null && typeof value.portalActId !== "string") {
    invalid(`${label}.portalActId must be a string or null`);
  }
}

function validatePortalSnapshot(value) {
  if (!isRecord(value)) invalid("PORTAL snapshot must be an object");
  exactKeys(value, ["role", "generation", "sector", "identities", "actions"], "PORTAL snapshot");
  if (!PORTAL_ROLE_SET.has(value.role)) invalid("PORTAL snapshot role is invalid");
  if (!Number.isSafeInteger(value.generation) || value.generation < 1) invalid("PORTAL snapshot generation is invalid");
  if (value.sector !== null && typeof value.sector !== "string") invalid("PORTAL snapshot sector is invalid");
  if (!Array.isArray(value.identities) || !Array.isArray(value.actions)) invalid("PORTAL snapshot collections are invalid");
  value.identities.forEach((identity, index) => validatePortalIdentity(identity, `PORTAL snapshot identity ${index}`));
  value.actions.forEach((action, index) => {
    if (!isRecord(action)) invalid(`PORTAL snapshot action ${index} is invalid`);
    if (typeof action.action !== "string" || !PORTAL_ACTION_SET.has(action.action)) invalid(`PORTAL snapshot action ${index} is unsupported`);
    if (typeof action.enabled !== "boolean") invalid(`PORTAL snapshot action ${index}.enabled is invalid`);
    if (Object.hasOwn(action, "identity")) validatePortalIdentity(action.identity, `PORTAL snapshot action ${index}.identity`);
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
        ["context", "datasetSha256", "rulesVersion", "contextRevision"],
        "GET_MATCH payload",
      );
      nonEmptyString(payload.processKey, "GET_MATCH processKey");
      nonEmptyString(payload.interestedNormalized, "GET_MATCH interestedNormalized");
      validateOptions(payload.options);
      if (Object.hasOwn(payload, "datasetSha256") && (typeof payload.datasetSha256 !== "string" || !/^[0-9a-f]{64}$/u.test(payload.datasetSha256))) {
        invalid("GET_MATCH datasetSha256 is invalid");
      }
      if (Object.hasOwn(payload, "rulesVersion")) nonEmptyString(payload.rulesVersion, "GET_MATCH rulesVersion");
      if (Object.hasOwn(payload, "contextRevision") && (!Number.isSafeInteger(payload.contextRevision) || payload.contextRevision < 0)) {
        invalid("GET_MATCH contextRevision is invalid");
      }
      if (Object.hasOwn(payload, "context") && payload.context !== null) {
        try {
          validateLegalContext(payload.context, {
            processKey: payload.processKey,
            interestedNormalized: payload.interestedNormalized,
            datasetSha256: payload.datasetSha256,
          });
        } catch (error) {
          if (error instanceof SchemaValidationError) throw error;
          invalid(error instanceof Error ? error.message : "GET_MATCH context is invalid");
        }
      }
      break;
    case MESSAGE_TYPES.APPLY_FIELDS:
      exactKeys(
        payload,
        Object.hasOwn(payload, "matchKinds") ? ["fields", "matchKinds"] : ["fields"],
        "APPLY_FIELDS payload",
      );
      validateFields(payload.fields);
      if (Object.hasOwn(payload, "matchKinds")) validateMatchKinds(payload.matchKinds);
      break;
    case MESSAGE_TYPES.OVERRIDE_FIELD:
      exactKeys(payload, ["field", "proposedValue"], "OVERRIDE_FIELD payload");
      if (!ALLOWED_FIELDS.includes(payload.field)) invalid("OVERRIDE_FIELD field is unsupported");
      if (typeof payload.proposedValue !== "string") invalid("OVERRIDE_FIELD proposedValue must be a string");
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
    case MESSAGE_TYPES.PORTAL_GET_SNAPSHOT:
      exactKeys(payload, [], "PORTAL_GET_SNAPSHOT payload");
      break;
    case MESSAGE_TYPES.PORTAL_NAVIGATE:
      exactKeysFrom(payload, ["action", "expected_generation"], ["identity", "timeoutMs"], "PORTAL_NAVIGATE payload");
      if (typeof payload.action !== "string" || !PORTAL_ACTION_SET.has(payload.action)) invalid("PORTAL_NAVIGATE action is unsupported");
      if (!Number.isSafeInteger(payload.expected_generation) || payload.expected_generation < 1) invalid("PORTAL_NAVIGATE expected_generation is invalid");
      if (Object.hasOwn(payload, "identity") && payload.identity !== null) validatePortalIdentity(payload.identity, "PORTAL_NAVIGATE identity");
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
