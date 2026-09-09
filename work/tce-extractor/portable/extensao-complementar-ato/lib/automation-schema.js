const AUTOMATION_SCHEMA_VERSION = 1;
const LEGAL_CONTEXT_SCHEMA_VERSION = 1;
const API_VERSION = 1;
const MAX_CONTEXT_BYTES = 2 * 1024 * 1024;
const MAX_QUEUE_ITEMS = 10000;
const SHA256_RE = /^[0-9a-f]{64}$/u;
const PROCESS_KEY_RE = /^\d+\/\d{4}$/u;
const EVENT_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$/u;
const ACTIONS = new Set(["pause", "resume", "stop"]);
const RUN_STATUSES = new Set(["discovering", "running", "paused", "stopped", "completed"]);
const ITEM_STATES = new Set(["queued", "prepared", "filled", "send_intent", "confirmed", "pending", "failed", "unconfirmed"]);
const EVENT_TYPES = new Set([
  "item_prepared",
  "fields_verified",
  "send_intent",
  "send_confirmed",
  "item_pending",
  "item_failed",
  "send_unconfirmed",
  "run_paused",
  "run_resumed",
  "run_stopped",
  "run_completed",
]);
const EVENT_PAYLOAD_KEYS = new Set([
  "identity",
  "itemId",
  "fields",
  "fieldResults",
  "before",
  "after",
  "method",
  "origin",
  "rereads",
  "reRead",
  "legalDecision",
  "decision",
  "citations",
  "timestamp",
  "error",
  "errors",
  "reason",
  "expectedFieldsHash",
]);

export class AutomationSchemaError extends TypeError {
  constructor(message, code = "INVALID_AUTOMATION_SCHEMA") {
    super(`invalid automation schema: ${message}`);
    this.name = "AutomationSchemaError";
    this.code = code;
  }
}

function invalid(message, code = "INVALID_AUTOMATION_SCHEMA") {
  throw new AutomationSchemaError(message, code);
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function clone(value) {
  return structuredClone(value);
}

function exactKeys(value, expected) {
  const keys = Object.keys(value);
  if (keys.length !== expected.length || expected.some((key) => !Object.hasOwn(value, key))) {
    invalid("unexpected keys", "UNEXPECTED_KEY");
  }
}

function exactKeysWithOptional(value, required, optional) {
  const allowed = new Set([...required, ...optional]);
  if (Object.keys(value).some((key) => !allowed.has(key))) invalid("unexpected keys", "UNEXPECTED_KEY");
  if (required.some((key) => !Object.hasOwn(value, key))) invalid("missing key", "MISSING_KEY");
}

function nonEmptyString(value, label, max = 256) {
  if (typeof value !== "string" || value.length === 0 || value.length > max) {
    invalid(`${label} must be a non-empty string`, "INVALID_VALUE");
  }
}

function normalizeInterested(value) {
  return value.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/gu, " ").trim();
}

function revision(value, label = "revision") {
  if (!Number.isSafeInteger(value) || value < 0) invalid(`${label} must be a non-negative integer`, "INVALID_REVISION");
}

function rejectPrivateKeys(value) {
  if (Array.isArray(value)) {
    value.forEach(rejectPrivateKeys);
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (/^(?:token|cookie|password|session|authorization|workflow_root|root|path|url)$/iu.test(key)) {
      invalid(`private key ${key} is not allowed`, "PRIVATE_KEY");
    }
    rejectPrivateKeys(child);
  }
}

export function validateAutomationIdentity(value) {
  if (!isRecord(value)) invalid("identity must be an object", "INVALID_IDENTITY");
  exactKeys(value, ["processKey", "interestedNormalized", "portalActId"]);
  if (typeof value.processKey !== "string" || !PROCESS_KEY_RE.test(value.processKey)) {
    invalid("processKey is not canonical", "INVALID_PROCESS_KEY");
  }
  nonEmptyString(value.interestedNormalized, "interestedNormalized");
  if (normalizeInterested(value.interestedNormalized) !== value.interestedNormalized) {
    invalid("interestedNormalized must be normalized", "INVALID_IDENTITY");
  }
  if (value.portalActId !== null) nonEmptyString(value.portalActId, "portalActId");
  rejectPrivateKeys(value);
  return value;
}

export function validateAutomationRunSpec(value) {
  if (!isRecord(value)) invalid("RunSpec must be an object", "INVALID_RUN_SPEC");
  exactKeys(value, ["tabId", "sector", "datasetSha256", "rulesVersion"]);
  if (!Number.isSafeInteger(value.tabId) || value.tabId < 0) invalid("tabId is invalid", "INVALID_TAB_ID");
  nonEmptyString(value.sector, "sector");
  if (typeof value.datasetSha256 !== "string" || !SHA256_RE.test(value.datasetSha256)) {
    invalid("datasetSha256 is invalid", "INVALID_DATASET_HASH");
  }
  nonEmptyString(value.rulesVersion, "rulesVersion");
  rejectPrivateKeys(value);
  return value;
}

export function validateAutomationQueue(value) {
  if (!isRecord(value)) invalid("queue must be an object", "INVALID_QUEUE");
  exactKeys(value, ["identities", "eventId", "expectedRevision"]);
  if (!Array.isArray(value.identities)) invalid("identities must be an array", "INVALID_QUEUE");
  if (value.identities.length > MAX_QUEUE_ITEMS) invalid("queue exceeds 10000 identities", "QUEUE_TOO_LARGE");
  value.identities.forEach(validateAutomationIdentity);
  nonEmptyString(value.eventId, "eventId", 256);
  if (!EVENT_ID_RE.test(value.eventId)) invalid("eventId is invalid", "INVALID_EVENT_ID");
  revision(value.expectedRevision, "expectedRevision");
  return value;
}

function validateEventPayload(payload) {
  if (!isRecord(payload)) invalid("event payload must be an object", "INVALID_EVENT_PAYLOAD");
  if (Object.keys(payload).some((key) => !EVENT_PAYLOAD_KEYS.has(key))) invalid("unexpected event payload key", "UNEXPECTED_KEY");
  rejectPrivateKeys(payload);
}

export function validateAutomationEvent(value) {
  if (!isRecord(value)) invalid("event must be an object", "INVALID_EVENT");
  exactKeys(value, ["eventId", "expectedRevision", "itemId", "type", "payload"]);
  nonEmptyString(value.eventId, "eventId", 256);
  if (!EVENT_ID_RE.test(value.eventId)) invalid("eventId is invalid", "INVALID_EVENT_ID");
  revision(value.expectedRevision, "expectedRevision");
  if (value.itemId !== null) nonEmptyString(value.itemId, "itemId", 256);
  if (typeof value.type !== "string" || !EVENT_TYPES.has(value.type)) invalid("event type is unsupported", "INVALID_EVENT_TYPE");
  validateEventPayload(value.payload);
  return value;
}

export function validateControlRequest(value) {
  if (!isRecord(value)) invalid("control request must be an object", "INVALID_CONTROL");
  exactKeys(value, ["action", "eventId", "expectedRevision"]);
  if (typeof value.action !== "string" || !ACTIONS.has(value.action)) invalid("action is unsupported", "INVALID_ACTION");
  nonEmptyString(value.eventId, "eventId", 256);
  if (!EVENT_ID_RE.test(value.eventId)) invalid("eventId is invalid", "INVALID_EVENT_ID");
  revision(value.expectedRevision, "expectedRevision");
  return value;
}

function contextByteLength(value) {
  return new TextEncoder().encode(JSON.stringify(value)).byteLength;
}

export function validateLegalContext(value, expected = {}) {
  if (!isRecord(value)) invalid("legal context must be an object", "INVALID_CONTEXT");
  exactKeysWithOptional(
    value,
    ["schema_version", "dataset_sha256", "process_key", "interested_normalized", "resolution_status", "operative_text", "pages"],
    ["extraction_version", "source_evidence", "status_reasons", "geometry_status"],
  );
  if (value.schema_version !== LEGAL_CONTEXT_SCHEMA_VERSION) invalid("unsupported context schema", "INVALID_CONTEXT_SCHEMA");
  if (typeof value.dataset_sha256 !== "string" || !SHA256_RE.test(value.dataset_sha256)) invalid("context dataset hash is invalid", "INVALID_DATASET_HASH");
  if (expected.datasetSha256 !== undefined && value.dataset_sha256 !== expected.datasetSha256) invalid("context dataset hash differs", "CONTEXT_DATASET_MISMATCH");
  if (typeof value.process_key !== "string" || !PROCESS_KEY_RE.test(value.process_key)) invalid("context process is invalid", "INVALID_PROCESS_KEY");
  if (expected.processKey !== undefined && value.process_key !== expected.processKey) invalid("context process differs", "CONTEXT_IDENTITY_MISMATCH");
  nonEmptyString(value.interested_normalized, "context interested_normalized");
  if (expected.interestedNormalized !== undefined && value.interested_normalized !== expected.interestedNormalized) invalid("context interested differs", "CONTEXT_IDENTITY_MISMATCH");
  if (!["complete", "missing", "incomplete", "conflict", "pending"].includes(value.resolution_status)) invalid("context resolution status is invalid", "INVALID_CONTEXT_STATUS");
  if (typeof value.operative_text !== "string") invalid("context operative_text must be a string", "INVALID_CONTEXT");
  if (!Array.isArray(value.pages)) invalid("context pages must be an array", "INVALID_CONTEXT");
  rejectPrivateKeys(value);
  if (contextByteLength(value) > MAX_CONTEXT_BYTES) {
    const pending = clone(value);
    pending.resolution_status = "pending";
    pending.status_reasons = [
      ...(Array.isArray(pending.status_reasons) ? pending.status_reasons : []),
      { code: "context_too_large" },
    ];
    return pending;
  }
  return value;
}

export function validateAutomationCapabilities(value) {
  if (!isRecord(value)) invalid("capabilities must be an object", "INVALID_CAPABILITIES");
  exactKeys(value, ["api_version", "automation_schema", "legal_context_schema", "rules_version", "real_send_enabled"]);
  if (value.api_version !== API_VERSION || value.automation_schema !== AUTOMATION_SCHEMA_VERSION || value.legal_context_schema !== LEGAL_CONTEXT_SCHEMA_VERSION) {
    invalid("capabilities version is incompatible", "INCOMPATIBLE_VERSION");
  }
  nonEmptyString(value.rules_version, "rules_version");
  if (typeof value.real_send_enabled !== "boolean") invalid("real_send_enabled must be boolean", "INVALID_CAPABILITIES");
  return value;
}

export function validateAutomationSnapshot(value) {
  if (!isRecord(value)) invalid("snapshot must be an object", "INVALID_SNAPSHOT");
  exactKeysWithOptional(value, ["api_version", "run_id", "revision", "status", "items", "last_confirmed_item_id"], ["reports", "spec"]);
  if (value.api_version !== API_VERSION) invalid("snapshot api_version is incompatible", "INCOMPATIBLE_VERSION");
  nonEmptyString(value.run_id, "run_id", 128);
  revision(value.revision);
  if (!RUN_STATUSES.has(value.status)) invalid("snapshot status is invalid", "INVALID_SNAPSHOT");
  if (!Array.isArray(value.items)) invalid("snapshot items must be an array", "INVALID_SNAPSHOT");
  value.items.forEach((item) => {
    if (!isRecord(item)) invalid("snapshot item must be an object", "INVALID_SNAPSHOT");
    exactKeys(item, ["item_id", "ordinal", "identity", "state"]);
    nonEmptyString(item.item_id, "item_id");
    if (!Number.isSafeInteger(item.ordinal) || item.ordinal < 1) invalid("snapshot ordinal is invalid", "INVALID_SNAPSHOT");
    validateAutomationIdentity(item.identity);
    if (!ITEM_STATES.has(item.state)) invalid("snapshot item state is invalid", "INVALID_SNAPSHOT");
  });
  if (value.last_confirmed_item_id !== null) nonEmptyString(value.last_confirmed_item_id, "last_confirmed_item_id");
  return value;
}

export {
  API_VERSION,
  AUTOMATION_SCHEMA_VERSION,
  LEGAL_CONTEXT_SCHEMA_VERSION,
  MAX_CONTEXT_BYTES,
  MAX_QUEUE_ITEMS,
};
