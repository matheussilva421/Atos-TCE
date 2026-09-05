const SCHEMA_VERSION = 1;

export { SCHEMA_VERSION };

export const ALLOWED_ORIGIN = "https://novaarearestrita.tce.rn.gov.br";

export const ALLOWED_FIELDS = Object.freeze([
  "modalidade",
  "fundamento_legal",
  "data_publicacao_doe",
  "cargo",
  "matricula",
  "data_nascimento",
  "genero",
]);

export const STORAGE_KEYS = Object.freeze({
  DATASET: "dataset:v1",
  DATASET_INDEX: "datasetIndex:v1",
  REVIEWED: "reviewed:v1",
});

const DATASET_KEYS = Object.freeze([
  "schema_version",
  "generated_at",
  "batch",
  "records",
]);
const BATCH_KEYS = Object.freeze([
  "id",
  "logical_sha256",
  "process_count",
  "record_count",
  "process_keys",
]);
const PROCESS_KEYS = Object.freeze(["key", "number", "year"]);
const INTERESTED_KEYS = Object.freeze(["original", "normalized"]);
const FIELD_KEYS = Object.freeze([
  "status",
  "confidence",
  "source_value",
  "form_value",
  "citation",
]);
const PRIVATE_KEYS = new Set([
  "cpf",
  "url",
  "cookie",
  "token",
  "session",
  "password",
  "absolute_path",
  "pdf_path",
]);
const PROCESS_RE = /^(\d+)\/(\d{4})$/u;
const SHA256_RE = /^[0-9a-f]{64}$/u;
const UNSAFE_VALUE_RE = /(?:[a-z][a-z0-9+.-]*:\/\/|\bwww\.|(?:^|[\s"'(])(?:[A-Za-z]:[\\/]|\\\\)|(?:^|[\\/])\.\.(?:[\\/]|$)|\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\bbearer\s+\S+|\b(?:cpf|token|cookie|session|password|senha)\s*[:=]\s*\S+|[\r\n])/iu;

export class SchemaValidationError extends TypeError {
  constructor(message) {
    super(`invalid extension schema: ${message}`);
    this.name = "SchemaValidationError";
  }
}

function invalid(message) {
  throw new SchemaValidationError(message);
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireRecord(value, label) {
  if (!isRecord(value)) invalid(`${label} must be an object`);
  return value;
}

function requireExactKeys(value, expected, label) {
  const keys = Object.keys(value);
  if (keys.length !== expected.length || expected.some((key) => !keys.includes(key))) {
    invalid(`${label} has unexpected keys or order`);
  }
}

function requireNonEmptyString(value, label) {
  if (typeof value !== "string" || value.length === 0) invalid(`${label} must be a non-empty string`);
}

function requireNonNegativeInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) invalid(`${label} must be a non-negative integer`);
}

function rejectPrivateKeys(value, path = "dataset") {
  if (Array.isArray(value)) {
    value.forEach((child, index) => rejectPrivateKeys(child, `${path}[${index}]`));
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (PRIVATE_KEYS.has(key.toLowerCase())) invalid(`private key at ${path}.${key}`);
    rejectPrivateKeys(child, `${path}.${key}`);
  }
}

function parseProcessKey(value, label) {
  if (typeof value !== "string") invalid(`${label} must be a string`);
  const match = PROCESS_RE.exec(value);
  if (!match) invalid(`${label} is not a canonical process key`);
  return { key: value, number: match[1], year: match[2] };
}

export function normalizeInterestedName(value) {
  if (typeof value !== "string") return "";
  return value
    .normalize("NFKD")
    .replace(/\p{M}+/gu, "")
    .toLowerCase()
    .replace(/\s+/gu, " ")
    .trim();
}

export function validatePortalUrl(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  try {
    const parsed = new URL(value);
    return parsed.origin === ALLOWED_ORIGIN
      && parsed.username === ""
      && parsed.password === "";
  } catch {
    return false;
  }
}

function validateDocument(value, label) {
  if (typeof value !== "string" || value.length === 0 || value.length > 255) {
    invalid(`${label} must be a safe document label`);
  }
  if (value.includes("/") || value.includes("\\") || value === "." || value === ".." || UNSAFE_VALUE_RE.test(value)) {
    invalid(`${label} is unsafe`);
  }
}

function validateCitation(value, label) {
  if (value === null) return;
  const citation = requireRecord(value, label);
  const allowed = ["process", "event", "page", "document"];
  if (Object.keys(citation).some((key) => !allowed.includes(key))) invalid(`${label} has unexpected keys`);
  requireNonEmptyString(citation.process, `${label}.process`);
  requireNonEmptyString(citation.event, `${label}.event`);
  if (!Number.isSafeInteger(citation.page) || citation.page <= 0) invalid(`${label}.page must be positive`);
  if (Object.hasOwn(citation, "document")) validateDocument(citation.document, `${label}.document`);
}

function validateField(value, label, processKey, allowCandidates = true) {
  const field = requireRecord(value, label);
  const expected = allowCandidates && Object.hasOwn(field, "candidates")
    ? [...FIELD_KEYS, "candidates"]
    : FIELD_KEYS;
  requireExactKeys(field, expected, label);
  requireNonEmptyString(field.status, `${label}.status`);
  requireNonEmptyString(field.confidence, `${label}.confidence`);
  for (const key of ["source_value", "form_value"]) {
    if (field[key] !== null && typeof field[key] !== "string") invalid(`${label}.${key} must be a string or null`);
    if (typeof field[key] === "string" && UNSAFE_VALUE_RE.test(field[key])) invalid(`${label}.${key} is unsafe`);
  }
  validateCitation(field.citation, `${label}.citation`);
  if (field.citation !== null && field.citation.process !== processKey) {
    invalid(`${label}.citation.process does not match the record`);
  }
  if (Object.hasOwn(field, "candidates")) {
    if (!Array.isArray(field.candidates)) invalid(`${label}.candidates must be an array`);
    field.candidates.forEach((candidate, index) => validateField(candidate, `${label}.candidates[${index}]`, processKey, false));
  }
}

function validateRecord(value, index, processKeys, seen) {
  const record = requireRecord(value, `record ${index}`);
  requireExactKeys(record, ["process", "interested", "status", "fields"], `record ${index}`);

  const process = requireRecord(record.process, `record ${index}.process`);
  requireExactKeys(process, PROCESS_KEYS, `record ${index}.process`);
  const parsedProcess = parseProcessKey(process.key, `record ${index}.process.key`);
  if (process.number !== parsedProcess.number || process.year !== parsedProcess.year) {
    invalid(`record ${index}.process components do not match`);
  }
  if (!processKeys.includes(parsedProcess.key)) invalid(`record ${index}.process is absent from process_keys`);

  const interested = requireRecord(record.interested, `record ${index}.interested`);
  requireExactKeys(interested, INTERESTED_KEYS, `record ${index}.interested`);
  requireNonEmptyString(interested.original, `record ${index}.interested.original`);
  requireNonEmptyString(interested.normalized, `record ${index}.interested.normalized`);
  if (normalizeInterestedName(interested.original) !== interested.normalized) {
    invalid(`record ${index}.interested normalization does not match`);
  }
  const identity = `${parsedProcess.key}\u0000${interested.normalized}`;
  if (seen.has(identity)) invalid(`duplicate process/interested record: ${parsedProcess.key}`);
  seen.add(identity);

  requireNonEmptyString(record.status, `record ${index}.status`);
  const fields = requireRecord(record.fields, `record ${index}.fields`);
  requireExactKeys(fields, ALLOWED_FIELDS, `record ${index}.fields`);
  ALLOWED_FIELDS.forEach((fieldName) => validateField(fields[fieldName], `record ${index}.fields.${fieldName}`, parsedProcess.key));
}

function logicalPayload(dataset) {
  return {
    schema_version: dataset.schema_version,
    batch_id: dataset.batch.id,
    process_keys: dataset.batch.process_keys,
    records: dataset.records,
  };
}

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (isRecord(value)) {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortKeys(value[key])]));
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(sortKeys(value));
}

export async function computeLogicalSha256(dataset) {
  const cryptoApi = globalThis.crypto;
  if (!cryptoApi?.subtle || typeof TextEncoder === "undefined") {
    throw new Error("Web Crypto SHA-256 is unavailable");
  }
  const digest = await cryptoApi.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(canonicalJson(logicalPayload(dataset))),
  );
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function validateDataset(dataset) {
  const value = requireRecord(dataset, "dataset");
  rejectPrivateKeys(value);
  requireExactKeys(value, DATASET_KEYS, "dataset");
  if (value.schema_version !== SCHEMA_VERSION) invalid("unsupported schema version");
  requireNonEmptyString(value.generated_at, "generated_at");

  const batch = requireRecord(value.batch, "batch");
  requireExactKeys(batch, BATCH_KEYS, "batch");
  requireNonEmptyString(batch.id, "batch.id");
  if (typeof batch.logical_sha256 !== "string" || !SHA256_RE.test(batch.logical_sha256)) {
    invalid("logical_sha256 must be 64 lowercase hexadecimal characters");
  }
  requireNonNegativeInteger(batch.process_count, "batch.process_count");
  requireNonNegativeInteger(batch.record_count, "batch.record_count");
  if (!Array.isArray(batch.process_keys)) invalid("batch.process_keys must be an array");

  const parsedProcessKeys = batch.process_keys.map((key, index) => parseProcessKey(key, `batch.process_keys[${index}]`));
  if (new Set(batch.process_keys).size !== batch.process_keys.length) invalid("batch.process_keys contains duplicates");
  const canonicalOrder = [...parsedProcessKeys].sort((left, right) => (
    Number(left.number) - Number(right.number)
    || Number(left.year) - Number(right.year)
    || left.key.localeCompare(right.key)
  ));
  if (canonicalOrder.some((item, index) => item.key !== parsedProcessKeys[index].key)) {
    invalid("batch.process_keys is not in canonical order");
  }
  if (batch.process_count !== batch.process_keys.length) invalid("process_count does not match process_keys");

  if (!Array.isArray(value.records)) invalid("records must be an array");
  if (batch.record_count !== value.records.length) invalid("record_count does not match records");
  const seen = new Set();
  value.records.forEach((record, index) => validateRecord(record, index, batch.process_keys, seen));

  const expectedHash = await computeLogicalSha256(value);
  if (batch.logical_sha256 !== expectedHash) invalid("logical_sha256 does not match dataset content");
  return value;
}

export function buildDatasetIndex(dataset) {
  const byProcess = Object.create(null);
  for (const processKey of dataset.batch.process_keys) byProcess[processKey] = Object.create(null);
  for (const record of dataset.records) {
    const processKey = record.process.key;
    byProcess[processKey][record.interested.normalized] = record;
  }
  return {
    schemaVersion: SCHEMA_VERSION,
    batchId: dataset.batch.id,
    processKeys: [...dataset.batch.process_keys],
    byProcess,
  };
}

export function resolveIndexedRecord(index, processKey, interested) {
  if (!isRecord(index) || typeof processKey !== "string") return null;
  const processRecords = index.byProcess?.[processKey];
  if (!isRecord(processRecords)) return null;
  const normalized = normalizeInterestedName(interested);
  return normalized && Object.hasOwn(processRecords, normalized) ? processRecords[normalized] : null;
}
