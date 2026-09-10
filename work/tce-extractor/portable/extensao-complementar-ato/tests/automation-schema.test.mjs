import test from "node:test";
import assert from "node:assert/strict";

import {
  AutomationSchemaError,
  validateAutomationCapabilities,
  validateAutomationEvent,
  validateAutomationIdentity,
  validateAutomationQueue,
  validateAutomationRunSpec,
  validateAutomationSnapshot,
  validateControlRequest,
  validateLegalContext,
} from "../lib/automation-schema.js";
import { MESSAGE_TYPES, createMessage } from "../lib/messages.js";

const HASH = "a".repeat(64);
const AUTOMATION_FIELDS = [
  "modalidade",
  "fundamento_legal",
  "data_publicacao_doe",
  "cargo",
  "matricula",
  "data_nascimento",
  "genero",
];

function runSpec(overrides = {}) {
  return {
    tabId: 7,
    sector: "aposentadorias",
    datasetSha256: HASH,
    rulesVersion: "legal-foundation-v1",
    ...overrides,
  };
}

function identity(overrides = {}) {
  return {
    processKey: "103439/2023",
    interestedNormalized: "ana da silva",
    portalActId: null,
    ...overrides,
  };
}

function fieldEvidence() {
  return Object.fromEntries(AUTOMATION_FIELDS.map((field) => [field, {
    status: "present",
    valueHash: HASH,
    optionsHash: HASH,
    disabled: false,
    readOnly: false,
    redacted: true,
  }]));
}

function fieldResults() {
  return Object.fromEntries(AUTOMATION_FIELDS.map((field) => [field, {
    status: "verified",
    expectedHash: HASH,
    actualHash: HASH,
    redacted: true,
  }]));
}

function itemPreparedPayload() {
  return {
    reason: "ready",
    identity: identity(),
    frame: { generation: 3, frameId: 12 },
    dataset_sha256: HASH,
    context_hash: HASH,
    legalDecision: {
      status: "selected",
      method: "rule",
      rule_id: "EC41_COM_P5",
      option_value: "f-professor",
      rules_version: "legal-foundation-v1",
    },
    matchKinds: Object.fromEntries(AUTOMATION_FIELDS.map((field) => [field, "exact"])),
    before: fieldEvidence(),
    after: fieldEvidence(),
  };
}

test("validates the closed automation RunSpec and rejects a swapped hash or extra key", () => {
  assert.deepEqual(validateAutomationRunSpec(runSpec()), runSpec());
  assert.throws(
    () => validateAutomationRunSpec(runSpec({ datasetSha256: "b".repeat(63) })),
    (error) => error instanceof AutomationSchemaError && error.code === "INVALID_DATASET_HASH",
  );
  assert.throws(
    () => validateAutomationRunSpec(runSpec({ workflowRoot: "C:\\secret" })),
    (error) => error instanceof AutomationSchemaError && error.code === "UNEXPECTED_KEY",
  );
});

test("accepts an optional exact marker criterion and rejects unsafe marker values", () => {
  const withMarker = runSpec({ marker: "PROFESSOR - IPERN - 2 RUBRICAS" });
  assert.deepEqual(validateAutomationRunSpec(withMarker), withMarker);
  assert.throws(
    () => validateAutomationRunSpec(runSpec({ marker: "" })),
    (error) => error instanceof AutomationSchemaError && error.code === "INVALID_VALUE",
  );
  assert.throws(
    () => validateAutomationRunSpec(runSpec({ marker: { label: "PROFESSOR" } })),
    (error) => error instanceof AutomationSchemaError && error.code === "INVALID_VALUE",
  );
});

test("accepts explicit automatic submission only as a boolean opt-in", () => {
  const autoSubmit = runSpec({ autoSubmit: true });
  assert.deepEqual(validateAutomationRunSpec(autoSubmit), autoSubmit);
  assert.throws(
    () => validateAutomationRunSpec(runSpec({ autoSubmit: "yes" })),
    (error) => error instanceof AutomationSchemaError && error.code === "INVALID_VALUE",
  );
});

test("validates the explicit one-act pilot mode and optional pilot capabilities", () => {
  const pilot = runSpec({ mode: "pilot", pilotIdentity: identity() });
  assert.deepEqual(validateAutomationRunSpec(pilot), pilot);
  const capabilities = validateAutomationCapabilities({
    api_version: 1,
    automation_schema: 1,
    legal_context_schema: 1,
    rules_version: "legal-foundation-v1",
    real_send_enabled: false,
    pilot_enabled: true,
    pilot_consumes_remaining: true,
  });
  assert.equal(capabilities.pilot_enabled, true);
  assert.equal(capabilities.pilot_consumes_remaining, true);
});

test("validates exact identities and the ten-thousand item queue limit", () => {
  assert.deepEqual(validateAutomationIdentity(identity()), identity());
  assert.throws(
    () => validateAutomationIdentity(identity({ interestedNormalized: "Ana da Silva" })),
    (error) => error instanceof AutomationSchemaError && error.code === "INVALID_IDENTITY",
  );
  assert.throws(
    () => validateAutomationIdentity(identity({ processKey: "103439" })),
    (error) => error instanceof AutomationSchemaError && error.code === "INVALID_PROCESS_KEY",
  );
  assert.throws(
    () => validateAutomationQueue({
      identities: Array.from({ length: 10001 }, (_, index) => identity({
        interestedNormalized: `person-${index}`,
      })),
      eventId: "queue-1",
      expectedRevision: 0,
    }),
    (error) => error instanceof AutomationSchemaError && error.code === "QUEUE_TOO_LARGE",
  );
});

test("validates discriminated events and closed control requests", () => {
  const validPayloads = {
    send_confirmed: {
      identity: { processKey: "103439/2023", interestedNormalized: "ana da silva", portalActId: null },
      origin: "portal",
      timestamp: "2026-09-09T12:00:00Z",
      fields: { cargo: "servidora" },
      citations: [{ source: "portal", reference: "act-1" }],
      reconciliation: { mode: "read_after_recovery", identityMatch: true, persisted: true },
    },
    send_intent: { expectedFieldsHash: HASH, commandId: "command-1", expiresAt: 1600000000000 },
    item_prepared: itemPreparedPayload(),
    fields_verified: { fieldResults: fieldResults(), rereads: [] },
    item_pending: { reason: "requires review" },
    item_failed: { error: "portal unavailable" },
    send_unconfirmed: { reason: "confirmation missing", rereads: [] },
    run_paused: {},
    run_resumed: {},
    run_stopped: {},
    run_completed: {},
  };
  for (const [index, [type, payload]] of Object.entries(validPayloads).entries()) {
    const event = {
      eventId: `event-${type}`,
      expectedRevision: index,
      itemId: type.startsWith("run_") ? null : "103439/2023",
      type,
      payload,
    };
    assert.deepEqual(validateAutomationEvent(event), event);
    if (!type.startsWith("run_")) {
      assert.throws(
        () => validateAutomationEvent({ ...event, payload: {} }),
        (error) => error instanceof AutomationSchemaError && error.code === "MISSING_KEY",
      );
    }
    assert.throws(
      () => validateAutomationEvent({ ...event, payload: { ...payload, arbitrary: true } }),
      (error) => error instanceof AutomationSchemaError && error.code === "UNEXPECTED_KEY",
    );
    if (type.startsWith("run_")) {
      assert.throws(
        () => validateAutomationEvent({ ...event, itemId: "103439/2023" }),
        (error) => error instanceof AutomationSchemaError && error.code === "INVALID_EVENT",
      );
    }
  }
  assert.deepEqual(
    validateControlRequest({ action: "pause", eventId: "pause-1", expectedRevision: 2 }),
    { action: "pause", eventId: "pause-1", expectedRevision: 2 },
  );
  assert.throws(
    () => validateControlRequest({ action: "send", eventId: "send-1", expectedRevision: 2 }),
    (error) => error instanceof AutomationSchemaError && error.code === "INVALID_ACTION",
  );
});

test("requires complete redacted preparation evidence and rejects raw field values", () => {
  const event = {
    eventId: "prepared-evidence-1",
    expectedRevision: 1,
    itemId: "103439/2023",
    type: "item_prepared",
    payload: itemPreparedPayload(),
  };

  assert.deepEqual(validateAutomationEvent(event), event);
  assert.throws(
    () => validateAutomationEvent({
      ...event,
      payload: { ...itemPreparedPayload(), before: { cargo: "raw personal value" } },
    }),
    (error) => error instanceof AutomationSchemaError && error.code === "INVALID_VALUE",
  );
  assert.throws(
    () => validateAutomationEvent({
      ...event,
      payload: { ...itemPreparedPayload(), context_hash: "not-a-hash" },
    }),
    (error) => error instanceof AutomationSchemaError && error.code === "INVALID_VALUE",
  );
});

test("requires hashed field results for fields_verified evidence", () => {
  const event = {
    eventId: "verified-evidence-1",
    expectedRevision: 1,
    itemId: "103439/2023",
    type: "fields_verified",
    payload: { fieldResults: fieldResults(), rereads: [] },
  };

  assert.deepEqual(validateAutomationEvent(event), event);
  assert.throws(
    () => validateAutomationEvent({
      ...event,
      payload: {
        fieldResults: { cargo: { expected: "raw", actual: "raw" } },
        rereads: [],
      },
    }),
    (error) => error instanceof AutomationSchemaError && error.code === "INVALID_VALUE",
  );
});

test("requires non-empty proof fields for send_confirmed", () => {
  const event = {
    eventId: "confirmed-1",
    expectedRevision: 1,
    itemId: "103439/2023",
    type: "send_confirmed",
    payload: {
      identity: { processKey: "103439/2023", interestedNormalized: "ana da silva", portalActId: null },
      origin: "portal",
      timestamp: "2026-09-09T12:00:00Z",
      fields: {},
      citations: [],
    },
  };
  assert.throws(
    () => validateAutomationEvent(event),
    (error) => error instanceof AutomationSchemaError && error.code === "INVALID_VALUE",
  );
});

test("accepts only matching legal context and keeps oversized context pending without truncation", () => {
  const context = {
    schema_version: 1,
    dataset_sha256: HASH,
    process_key: "103439/2023",
    interested_normalized: "ana da silva",
    resolution_status: "complete",
    operative_text: "RESOLVE: Art. 6º da EC 41/2003.",
    pages: [],
  };
  assert.deepEqual(
    validateLegalContext(context, {
      processKey: "103439/2023",
      interestedNormalized: "ana da silva",
      datasetSha256: HASH,
    }),
    context,
  );
  assert.equal(validateLegalContext({ ...context, resolution_status: "missing" }).resolution_status, "missing");
  assert.throws(
    () => validateLegalContext(context, {
      processKey: "103439/2023",
      interestedNormalized: "outra pessoa",
      datasetSha256: HASH,
    }),
    (error) => error instanceof AutomationSchemaError && error.code === "CONTEXT_IDENTITY_MISMATCH",
  );
  const oversized = { ...context, operative_text: "x".repeat(2 * 1024 * 1024) };
  assert.equal(validateLegalContext(oversized, {
    processKey: "103439/2023",
    interestedNormalized: "ana da silva",
    datasetSha256: HASH,
  }).resolution_status, "pending");
});

test("validates v1 capabilities and run snapshots without changing legacy fields", () => {
  assert.deepEqual(
    validateAutomationCapabilities({
      api_version: 1,
      automation_schema: 1,
      legal_context_schema: 1,
      rules_version: "legal-foundation-v1",
      real_send_enabled: false,
    }).real_send_enabled,
    false,
  );
  const snapshot = {
    api_version: 1,
    run_id: "run-1",
    revision: 1,
    status: "running",
    items: [{
      item_id: "103439/2023",
      ordinal: 1,
      identity: identity(),
      state: "queued",
    }],
    last_confirmed_item_id: null,
  };
  assert.equal(validateAutomationSnapshot(snapshot).run_id, "run-1");
});

test("automation messages are typed and reject payload extras", () => {
  assert.deepEqual(
    Object.values(MESSAGE_TYPES).filter((type) => type.startsWith("AUTO_")),
    [
      "AUTO_START",
      "AUTO_PAUSE",
      "AUTO_RESUME",
      "AUTO_STOP",
      "AUTO_STATUS",
      "AUTO_CONSUME_COMMAND",
      "AUTO_SUBMIT_COMMAND",
    ],
  );
  assert.throws(
    () => createMessage(MESSAGE_TYPES.AUTO_STATUS, { runId: "run-1", extra: true }, "status-1"),
    /unexpected keys/i,
  );
  assert.doesNotThrow(() => createMessage(MESSAGE_TYPES.PORTAL_NAVIGATE, {
    action: "filter_marker",
    marker: "PROFESSOR - IPERN - 2 RUBRICAS",
    expected_generation: 3,
  }, "marker-1"));
  assert.throws(
    () => createMessage(MESSAGE_TYPES.PORTAL_NAVIGATE, {
      action: "open_act",
      marker: "PROFESSOR",
      expected_generation: 3,
      identity: identity(),
    }, "marker-2"),
    /only valid for filter_marker/i,
  );
  assert.doesNotThrow(() => createMessage(MESSAGE_TYPES.AUTO_SUBMIT_COMMAND, {
    runId: "run-1",
    expectedRevision: 4,
    command: {
      command_id: "command-1",
      state: "issued",
      issued_at: 2_000,
      expires_at: 17_000,
      frame_id: 12,
      generation: 3,
      identity: identity(),
      expected_fields_hash: HASH,
    },
  }, "submit-1"));
  assert.throws(
    () => createMessage(MESSAGE_TYPES.AUTO_SUBMIT_COMMAND, {
      runId: "run-1",
      expectedRevision: 4,
      command: {
        command_id: "command-1",
        state: "issued",
        issued_at: 2_000,
        expires_at: 20_000,
        frame_id: 12,
        generation: 3,
        identity: identity(),
        expected_fields_hash: HASH,
      },
    }, "submit-2"),
    /lifetime/i,
  );
});
