import {
  ALLOWED_FIELDS,
  ALLOWED_ORIGIN,
  SCHEMA_VERSION,
  SchemaValidationError,
  validatePortalUrl,
} from "./schema.js";

export const MESSAGE_TYPES = Object.freeze({
  FORM_READY: "FORM_READY",
  GET_FORM_SNAPSHOT: "GET_FORM_SNAPSHOT",
  IMPORT_DATASET: "IMPORT_DATASET",
  GET_MATCH: "GET_MATCH",
  APPLY_FIELDS: "APPLY_FIELDS",
  OVERRIDE_FIELD: "OVERRIDE_FIELD",
  SET_REVIEWED: "SET_REVIEWED",
  REQUEST_COMPLEMENTAR_ATO: "REQUEST_COMPLEMENTAR_ATO",
});

const MESSAGE_TYPE_SET = new Set(Object.values(MESSAGE_TYPES));
const MESSAGE_KEYS = ["schemaVersion", "type", "requestId", "payload"];
const MATCH_KIND_SET = new Set(["exact", "probable", "tie"]);

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
      exactKeys(payload, ["dataset"], "IMPORT_DATASET payload");
      if (!isRecord(payload.dataset)) invalid("IMPORT_DATASET dataset must be an object");
      break;
    case MESSAGE_TYPES.GET_MATCH:
      exactKeys(payload, ["processKey", "interestedNormalized", "options"], "GET_MATCH payload");
      nonEmptyString(payload.processKey, "GET_MATCH processKey");
      nonEmptyString(payload.interestedNormalized, "GET_MATCH interestedNormalized");
      validateOptions(payload.options);
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
    payload,
  };
  return validateMessage(message);
}
