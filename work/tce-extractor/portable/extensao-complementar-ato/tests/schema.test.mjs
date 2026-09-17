import test from "node:test";
import assert from "node:assert/strict";

import {
  ALLOWED_ORIGIN,
  buildDatasetIndex,
  resolveIndexedRecord,
  validateDataset,
  validatePortalUrl,
} from "../lib/schema.js";
import {
  MESSAGE_TYPES,
  createMessage,
  validateMessage,
} from "../lib/messages.js";

const PROCESS_KEY = "103439/2023";
const DOCUMENT = "Resolucao_103439.pdf";

function field(value, processKey = PROCESS_KEY) {
  return {
    status: "found",
    confidence: "high",
    source_value: value,
    form_value: value,
    citation: {
      process: processKey,
      event: "9",
      page: 1,
      document: DOCUMENT,
    },
  };
}

function record(interested, processKey = PROCESS_KEY) {
  return {
    process: {
      key: processKey,
      number: processKey.split("/")[0],
      year: processKey.split("/")[1],
    },
    interested: {
      original: interested,
      normalized: interested.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase(),
    },
    status: "found",
    fields: {
      modalidade: field("Aposentadoria voluntária", processKey),
      fundamento_legal: field("Art. 40", processKey),
      data_publicacao_doe: field("07/02/2020", processKey),
      cargo: field("PROFESSOR PN - IV", processKey),
      matricula: field("103.870-2/1", processKey),
      data_nascimento: field("30/04/1967", processKey),
      genero: field("Feminino", processKey),
    },
  };
}

function sortKeys(value) {
  if (Array.isArray(value)) {
    return value.map(sortKeys);
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, sortKeys(value[key])]),
    );
  }
  return value;
}

async function logicalHash(dataset) {
  const payload = {
    schema_version: dataset.schema_version,
    batch_id: dataset.batch.id,
    process_keys: dataset.batch.process_keys,
    records: dataset.records,
  };
  const bytes = new TextEncoder().encode(JSON.stringify(sortKeys(payload)));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function validDataset() {
  const records = [
    record("João da Silva"),
    record("Maria de Souza"),
  ];
  const dataset = {
    schema_version: 1,
    generated_at: "2026-09-04T12:00:00+00:00",
    batch: {
      id: "20260904T120000Z",
      logical_sha256: "",
      process_count: 1,
      record_count: records.length,
      process_keys: [PROCESS_KEY],
    },
    records,
  };
  dataset.batch.logical_sha256 = await logicalHash(dataset);
  return dataset;
}

test("accepts a complete dataset and indexes records by process and normalized interested name", async () => {
  const dataset = await validDataset();

  await assert.doesNotReject(() => validateDataset(dataset));

  const index = buildDatasetIndex(dataset);
  assert.equal(index.schemaVersion, 1);
  assert.equal(index.batchId, "20260904T120000Z");
  assert.equal(
    resolveIndexedRecord(index, PROCESS_KEY, "  JOAO DA SILVA  "),
    dataset.records[0],
  );
  assert.equal(resolveIndexedRecord(index, PROCESS_KEY, "ausente"), null);
});

test("indexes a name that is also an object prototype property", async () => {
  const dataset = await validDataset();
  dataset.records[0].interested = {
    original: "__PROTO__",
    normalized: "__proto__",
  };
  dataset.records[1].interested = {
    original: "constructor",
    normalized: "constructor",
  };
  dataset.batch.logical_sha256 = await logicalHash(dataset);
  await assert.doesNotReject(() => validateDataset(dataset));

  const index = buildDatasetIndex(dataset);
  assert.equal(resolveIndexedRecord(index, PROCESS_KEY, "__proto__"), dataset.records[0]);
  assert.equal(resolveIndexedRecord(index, PROCESS_KEY, "constructor"), dataset.records[1]);
});

test("rejects a dataset with an unsupported schema version", async () => {
  const dataset = await validDataset();
  dataset.schema_version = 2;

  await assert.rejects(() => validateDataset(dataset), /unsupported schema version/iu);
});

test("rejects sensitive extra keys even when they are nested in a record", async () => {
  const dataset = await validDataset();
  dataset.records[0].cpf = "12345678901";

  await assert.rejects(() => validateDataset(dataset), /private key|unexpected key/iu);
});

test("rejects duplicate records for the same process and normalized interested", async () => {
  const dataset = await validDataset();
  dataset.records[1].interested = {
    original: "JOAO DA SILVA",
    normalized: "joao da silva",
  };

  await assert.rejects(() => validateDataset(dataset), /duplicate process\/interested/iu);
});

test("rejects a logical hash that does not describe the dataset", async () => {
  const dataset = await validDataset();
  dataset.batch.logical_sha256 = "0".repeat(64);

  await assert.rejects(() => validateDataset(dataset), /logical_sha256/iu);
});

test("accepts only the configured portal origin for frame registration", () => {
  assert.equal(ALLOWED_ORIGIN, "https://novaarearestrita.tce.rn.gov.br");
  assert.equal(validatePortalUrl(`${ALLOWED_ORIGIN}/ComplementarAto.asp`), true);
  assert.equal(validatePortalUrl("http://novaarearestrita.tce.rn.gov.br/ComplementarAto.asp"), false);
  assert.equal(validatePortalUrl("https://evil.example/ComplementarAto.asp"), false);
  assert.equal(validatePortalUrl("https://novaarearestrita.tce.rn.gov.br.evil.example/"), false);
});

test("requires version, known type, requestId, and validated payload on every message", () => {
  const message = createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "request-1");
  assert.deepEqual(validateMessage(message), message);
  assert.doesNotThrow(() => validateMessage({
    payload: {},
    requestId: "request-reordered",
    type: MESSAGE_TYPES.GET_FORM_SNAPSHOT,
    schemaVersion: 1,
  }));

  assert.throws(
    () => validateMessage({ ...message, schemaVersion: 2 }),
    /unsupported schema version/iu,
  );
  assert.throws(
    () => validateMessage({ ...message, requestId: "" }),
    /requestId/iu,
  );
  assert.throws(
    () => validateMessage({ ...message, type: "UNKNOWN" }),
    /message type/iu,
  );
  assert.throws(
    () => validateMessage({ ...message, payload: { cpf: "123" } }),
    /payload|unexpected/iu,
  );
});

test("accepts my_processes as a read-only Area Restrita analysis scope", () => {
  const message = createMessage(
    MESSAGE_TYPES.AUTO_ANALYZE,
    {
      spec: {
        sector: "aposentadorias",
        datasetSha256: null,
        rulesVersion: "legal-foundation-v3",
        sourceScope: "my_processes",
        lotSize: 50,
        acquisitionSource: "econtas",
        analysisOnly: true,
      },
      eventId: "analysis-my-processes",
    },
    "request-analysis-my-processes",
  );

  assert.deepEqual(validateMessage(message), message);
});

test("validates an explicit Complementar Ato signal with current identity", () => {
  const message = createMessage(
    MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO,
    { processKey: "103439/2023", interestedNormalized: "maria de souza" },
    "signal-1",
  );
  assert.equal(message.type, MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO);
  assert.throws(
    () => createMessage(MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO, { processKey: "103439/2023" }, "signal-2"),
    /unexpected keys|interestedNormalized/u,
  );
});

test("validates optional APPLY_FIELDS matchKinds without accepting external fields or class names", () => {
  const message = createMessage(
    MESSAGE_TYPES.APPLY_FIELDS,
    {
      fields: {
        modalidade: "m-special",
        fundamento_legal: "f-professor",
      },
      matchKinds: {
        modalidade: "exact",
        fundamento_legal: "tie",
      },
    },
    "apply-with-match-kinds",
  );
  assert.deepEqual(validateMessage(message), message);

  for (const [matchKinds, pattern] of [
    [{ txtModalidade: "exact" }, /unsupported field/iu],
    [{ financeiro: "probable" }, /unsupported field/iu],
    [{ modalidade: "green" }, /exact|probable|tie/iu],
    [{ modalidade: null }, /exact|probable|tie/iu],
  ]) {
    assert.throws(
      () => createMessage(
        MESSAGE_TYPES.APPLY_FIELDS,
        { fields: { modalidade: "m-special" }, matchKinds },
        "apply-invalid-match-kind",
      ),
      pattern,
    );
  }

  assert.throws(
    () => createMessage(
      MESSAGE_TYPES.APPLY_FIELDS,
      { fields: { txtCargo: "Campo externo" }, matchKinds: {} },
      "apply-invalid-field",
    ),
    /unsupported field/iu,
  );
});

test("falls back pending matcher kind or legal status to a safe v1 tie", () => {
  for (const pendingMatch of [
    "pending",
    { kind: "pending" },
    { status: "pending" },
    { kind: "pending", legalDecision: { status: "pending" } },
  ]) {
    const message = createMessage(
      MESSAGE_TYPES.APPLY_FIELDS,
      {
        fields: { fundamento_legal: "f-pending" },
        matchKinds: { fundamento_legal: pendingMatch },
      },
      "apply-pending-fallback",
    );

    assert.equal(message.payload.matchKinds.fundamento_legal, "tie");
    assert.deepEqual(validateMessage(message), message);
  }
});
