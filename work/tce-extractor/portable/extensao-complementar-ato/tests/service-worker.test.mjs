import test from "node:test";
import assert from "node:assert/strict";

import { computeLogicalSha256, STORAGE_KEYS } from "../lib/schema.js";
import { MESSAGE_TYPES, createMessage } from "../lib/messages.js";
import { createServiceWorker } from "../background/service-worker.js";

const PORTAL_URL = "https://novaarearestrita.tce.rn.gov.br/ComplementarAto.asp";
const PROCESS_KEY = "103439/2023";

function field(value) {
  return {
    status: "found",
    confidence: "high",
    source_value: value,
    form_value: value,
    citation: {
      process: PROCESS_KEY,
      event: "9",
      page: 1,
      document: "Resolucao_103439.pdf",
    },
  };
}

function makeRecord(interested) {
  return {
    process: { key: PROCESS_KEY, number: "103439", year: "2023" },
    interested: {
      original: interested,
      normalized: interested.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase(),
    },
    status: "found",
    fields: {
      modalidade: field("Aposentadoria voluntária"),
      fundamento_legal: field("Art. 40"),
      data_publicacao_doe: field("07/02/2020"),
      cargo: field("PROFESSOR PN - IV"),
      matricula: field("103.870-2/1"),
      data_nascimento: field("30/04/1967"),
      genero: field("Feminino"),
    },
  };
}

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortKeys(value[key])]));
  }
  return value;
}

async function makeDataset() {
  const records = [makeRecord("João da Silva")];
  const dataset = {
    schema_version: 1,
    generated_at: "2026-09-04T12:00:00+00:00",
    batch: {
      id: "batch-valid",
      logical_sha256: "",
      process_count: 1,
      record_count: 1,
      process_keys: [PROCESS_KEY],
    },
    records,
  };
  const payload = {
    schema_version: dataset.schema_version,
    batch_id: dataset.batch.id,
    process_keys: dataset.batch.process_keys,
    records: dataset.records,
  };
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(JSON.stringify(sortKeys(payload))),
  );
  dataset.batch.logical_sha256 = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  return dataset;
}

function storageMock(initial = {}) {
  const state = structuredClone(initial);
  const calls = [];
  return {
    state,
    calls,
    async get(keys) {
      const result = {};
      for (const key of keys) {
        if (Object.hasOwn(state, key)) result[key] = structuredClone(state[key]);
      }
      return result;
    },
    async set(values) {
      calls.push(structuredClone(values));
      Object.assign(state, structuredClone(values));
    },
  };
}

function chromeMock(storage, sendMessage = async () => ({ ok: true }), session = storageMock()) {
  const removedListeners = [];
  return {
    storage: { local: storage, session },
    tabs: {
      onRemoved: { addListener(listener) { removedListeners.push(listener); } },
      async query() { return [{ id: 7 }]; },
      async sendMessage(...args) { return sendMessage(...args); },
    },
    runtime: {
      id: "test-extension",
      onMessage: { addListener() {} },
    },
    fireTabRemoved(tabId) {
      for (const listener of removedListeners) listener(tabId);
    },
  };
}

function extensionSender(tabId) {
  return {
    id: "test-extension",
    url: "chrome-extension://test-extension/panel.html",
    ...(tabId === undefined ? {} : { tab: { id: tabId } }),
  };
}

function sender(tabId = 7, frameId = 12, url = PORTAL_URL) {
  return { tab: { id: tabId, url }, frameId, url };
}

function snapshot(processKey = PROCESS_KEY, interested = "João da Silva") {
  const [number, year] = processKey.split("/");
  return {
    process: { number, year, key: processKey },
    interested: {
      original: interested,
      normalized: interested.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase(),
    },
    options: {},
    fields: {},
  };
}

test("imports a valid batch once and a fresh worker can query it from persisted storage", async () => {
  const dataset = await makeDataset();
  const storage = storageMock();
  const chromeApi = chromeMock(storage);
  const worker = createServiceWorker({ chromeApi, now: () => "2026-09-04T13:00:00.000Z" });

  const imported = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.IMPORT_DATASET, { dataset }, "import-1"),
    { url: "chrome-extension://test/panel.html" },
  );

  assert.equal(imported.ok, true);
  assert.equal(storage.calls.length, 1);
  assert.deepEqual(Object.keys(storage.calls[0]).sort(), [
    STORAGE_KEYS.DATASET,
    STORAGE_KEYS.DATASET_INDEX,
    STORAGE_KEYS.REVIEWED,
  ].sort());

  const freshWorker = createServiceWorker({ chromeApi });
  const match = await freshWorker.handleMessage(
    createMessage(
      MESSAGE_TYPES.GET_MATCH,
      {
        processKey: PROCESS_KEY,
        interestedNormalized: "JOAO DA SILVA",
        options: {
          modalidade: [{ value: "option-1", label: "Aposentadoria voluntária" }],
          fundamento_legal: [{ value: "option-2", label: "Artigo 40" }],
        },
      },
      "match-1",
    ),
    { url: "chrome-extension://test/panel.html" },
  );

  assert.equal(match.ok, true);
  assert.equal(match.payload.record.interested.original, "João da Silva");
  assert.equal(match.payload.matches.modalidade.kind, "exact");
});

test("can import and query with only the minimum storage.local dependency", async () => {
  const dataset = await makeDataset();
  const storage = storageMock();
  const worker = createServiceWorker({ chromeApi: { storage: { local: storage } } });

  const imported = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.IMPORT_DATASET, { dataset }, "import-minimal"),
    { url: "chrome-extension://test/panel.html" },
  );
  assert.equal(imported.ok, true);

  const match = await worker.handleMessage(
    createMessage(
      MESSAGE_TYPES.GET_MATCH,
      { processKey: PROCESS_KEY, interestedNormalized: "joao da silva", options: {} },
      "match-minimal",
    ),
    { url: "chrome-extension://test/panel.html" },
  );
  assert.equal(match.ok, true);
  assert.equal(match.payload.record.process.key, PROCESS_KEY);
});

test("persists reviewed state by process and normalized interested", async () => {
  const dataset = await makeDataset();
  const storage = storageMock();
  const worker = createServiceWorker({ chromeApi: chromeMock(storage) });
  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.IMPORT_DATASET, { dataset }, "import-reviewed"),
    { url: "chrome-extension://test/panel.html" },
  );

  const reviewed = await worker.handleMessage(
    createMessage(
      MESSAGE_TYPES.SET_REVIEWED,
      { processKey: PROCESS_KEY, interestedNormalized: "joao da silva", reviewed: true },
      "review-1",
    ),
    { url: "chrome-extension://test/panel.html" },
  );
  assert.equal(reviewed.ok, true);
  assert.equal(storage.calls.length, 2);
  assert.deepEqual(Object.keys(storage.calls[1]), [STORAGE_KEYS.REVIEWED]);

  const match = await worker.handleMessage(
    createMessage(
      MESSAGE_TYPES.GET_MATCH,
      { processKey: PROCESS_KEY, interestedNormalized: "joao da silva", options: {} },
      "match-reviewed",
    ),
    { url: "chrome-extension://test/panel.html" },
  );
  assert.equal(match.payload.reviewed, true);
});

test("rejects an invalid import without calling storage or replacing the previous batch", async () => {
  const valid = await makeDataset();
  const storage = storageMock({ [STORAGE_KEYS.DATASET]: valid });
  const chromeApi = chromeMock(storage);
  const worker = createServiceWorker({ chromeApi });
  const invalid = structuredClone(valid);
  invalid.batch.logical_sha256 = "0".repeat(64);

  const response = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.IMPORT_DATASET, { dataset: invalid }, "import-bad"),
    { url: "chrome-extension://test/panel.html" },
  );

  assert.equal(response.ok, false);
  assert.equal(storage.calls.length, 0);
  assert.equal(storage.state[STORAGE_KEYS.DATASET].batch.id, "batch-valid");
});

test("automatic bridge imports preserve legacy review by process identity, while manual imports do not migrate it", async () => {
  const current = await makeDataset();
  const reviewedKey = `${PROCESS_KEY}\u0000joao da silva`;
  const storage = storageMock({
    [STORAGE_KEYS.REVIEWED]: { schemaVersion: 1, records: { [reviewedKey]: true } },
  });
  const worker = createServiceWorker({ chromeApi: chromeMock(storage) });

  const refreshed = await makeDataset();
  refreshed.batch.id = "batch-refresh";
  refreshed.batch.logical_sha256 = await computeLogicalSha256(refreshed);
  const preserved = await worker.handleMessage(
    createMessage(
      MESSAGE_TYPES.IMPORT_DATASET,
      { dataset: refreshed, preserveReviewed: true },
      "import-bridge",
    ),
    extensionSender(),
  );

  assert.equal(preserved.ok, true);
  const afterBridge = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.GET_MATCH, {
      processKey: PROCESS_KEY,
      interestedNormalized: "joao da silva",
      options: {},
    }, "match-after-bridge"),
    extensionSender(),
  );
  assert.equal(afterBridge.payload.reviewed, true);

  const manual = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.IMPORT_DATASET, { dataset: current }, "import-manual"),
    extensionSender(),
  );
  assert.equal(manual.ok, true);
  const afterManual = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.GET_MATCH, {
      processKey: PROCESS_KEY,
      interestedNormalized: "joao da silva",
      options: {},
    }, "match-after-manual"),
    extensionSender(),
  );
  assert.equal(afterManual.payload.reviewed, false);
});

test("registers only an allowed portal frame and routes only the requested current payload", async () => {
  const storage = storageMock();
  const sent = [];
  const chromeApi = chromeMock(storage, async (...args) => {
    sent.push(args);
    if (args[1].type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) {
      return { ok: true, payload: snapshot() };
    }
    return { ok: true, payload: { changed: ["cargo"] } };
  });
  const worker = createServiceWorker({ chromeApi, now: () => "2026-09-04T13:01:00.000Z" });

  const bad = await worker.handleMessage(
    {
      schemaVersion: 1,
      type: MESSAGE_TYPES.FORM_READY,
      requestId: "ready-bad",
      payload: { url: "https://evil.example/form" },
    },
    sender(7, 12, "https://evil.example/form"),
  );
  assert.equal(bad.ok, false);
  assert.equal(worker.getFrameRegistration(7), null);

  const ready = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-good"),
    sender(),
  );
  assert.equal(ready.ok, true);
  assert.deepEqual(worker.getFrameRegistration(7), {
    frameId: 12,
    url: PORTAL_URL,
    registeredAt: "2026-09-04T13:01:00.000Z",
  });

  const applied = await worker.handleMessage(
    createMessage(
      MESSAGE_TYPES.APPLY_FIELDS,
      { fields: { cargo: "PROFESSOR PN - IV" } },
      "apply-1",
    ),
    { url: "chrome-extension://test/panel.html", tab: { id: 7 } },
  );
  assert.equal(applied.ok, true);
  assert.equal(sent.length, 2);
  assert.equal(sent[0][0], 7);
  assert.equal(sent[0][1].type, MESSAGE_TYPES.GET_FORM_SNAPSHOT);
  assert.deepEqual(sent[0][2], { frameId: 12 });
  assert.equal(sent[1][0], 7);
  assert.equal(sent[1][1].type, MESSAGE_TYPES.APPLY_FIELDS);
  assert.deepEqual(sent[1][2], { frameId: 12 });
  assert.equal(Object.hasOwn(sent[1][1].payload, "dataset"), false);
  assert.deepEqual(sent[1][1].payload.fields, { cargo: "PROFESSOR PN - IV" });
});

test("forwards an explicit Complementar Ato signal to the current portal frame", async () => {
  const storage = storageMock();
  const sent = [];
  const chromeApi = chromeMock(storage, async (...args) => {
    sent.push(args);
    if (args[1].type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) return { ok: true, payload: snapshot() };
    return { ok: true, payload: { signaled: true } };
  });
  const worker = createServiceWorker({ chromeApi });
  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-signal"),
    sender(),
  );

  const response = await worker.handleMessage(
    createMessage(
      MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO,
      { processKey: PROCESS_KEY, interestedNormalized: "joao da silva" },
      "signal-1",
    ),
    extensionSender(),
  );
  assert.equal(response.ok, true);
  assert.equal(sent.at(-1)[1].type, MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO);
  assert.deepEqual(sent.at(-1)[1].payload, {
    processKey: PROCESS_KEY,
    interestedNormalized: "joao da silva",
  });
  assert.deepEqual(sent.at(-1)[2], { frameId: 12 });
});

test("tracks multiple frames, skips a hidden last registration, and follows the visible frame after a switch", async () => {
  const storage = storageMock();
  const sent = [];
  const visibleFrames = new Map();
  const chromeApi = chromeMock(storage, async (...args) => {
    sent.push(args);
    const frameId = args[2]?.frameId;
    if (args[1].type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) {
      const currentSnapshot = visibleFrames.get(frameId);
      return currentSnapshot ? { ok: true, payload: currentSnapshot } : undefined;
    }
    return { ok: true, payload: { changed: ["cargo"] } };
  });
  const worker = createServiceWorker({ chromeApi });

  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-102256"),
    { ...sender(7, 12), id: "test-extension" },
  );
  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-103365"),
    sender(7, 13),
  );

  visibleFrames.set(12, snapshot("102256/2026"));
  const firstApply = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.APPLY_FIELDS, { fields: { cargo: "frame 102256" } }, "apply-102256"),
    extensionSender(),
  );
  assert.equal(firstApply.ok, true);
  assert.deepEqual(sent.slice(-1)[0][2], { frameId: 12 });
  assert.equal(sent.slice(-1)[0][1].type, MESSAGE_TYPES.APPLY_FIELDS);

  visibleFrames.clear();
  visibleFrames.set(13, snapshot("103365/2026"));
  const switched = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "snapshot-103365"),
    extensionSender(),
  );
  assert.equal(switched.ok, true);
  assert.equal(switched.payload.payload.process.key, "103365/2026");
  assert.deepEqual(sent.slice(-2).map((call) => call[2]), [{ frameId: 12 }, { frameId: 13 }]);
});

test("blocks a write when more than one registered frame reports a visible valid form", async () => {
  const storage = storageMock();
  const sent = [];
  const chromeApi = chromeMock(storage, async (...args) => {
    sent.push(args);
    if (args[1].type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) {
      return { ok: true, payload: snapshot(args[2]?.frameId === 12 ? "102256/2026" : "103365/2026") };
    }
    return { ok: true, payload: { changed: ["must-not-write"] } };
  });
  const worker = createServiceWorker({ chromeApi });

  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-visible-a"),
    { ...sender(7, 12), id: "test-extension" },
  );
  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-visible-b"),
    sender(7, 13),
  );

  const blocked = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.APPLY_FIELDS, { fields: { cargo: "ambiguous" } }, "apply-ambiguous"),
    extensionSender(),
  );

  assert.equal(blocked.ok, false);
  assert.equal(blocked.error.code, "AMBIGUOUS_FORM_FRAME");
  assert.deepEqual(sent.map((call) => call[1].type), [
    MESSAGE_TYPES.GET_FORM_SNAPSHOT,
    MESSAGE_TYPES.GET_FORM_SNAPSHOT,
  ]);
});

test("restores frame registrations from storage.session after a service worker suspension", async () => {
  const storage = storageMock();
  const session = storageMock();
  const sent = [];
  const chromeApi = chromeMock(storage, async (...args) => {
    sent.push(args);
    if (args[1].type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) {
      return { ok: true, payload: snapshot("103365/2026") };
    }
    return { ok: true, payload: { changed: ["cargo"] } };
  }, session);
  const firstWorker = createServiceWorker({ chromeApi });

  await firstWorker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-session"),
    sender(7, 13),
  );
  assert.deepEqual(session.state, { "frame-registrations:v1": [{ tabId: 7, frameId: 13 }] });

  const suspendedWorker = createServiceWorker({ chromeApi });
  const restored = await suspendedWorker.handleMessage(
    createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "snapshot-after-suspension"),
    extensionSender(),
  );

  assert.equal(restored.ok, true);
  assert.equal(restored.payload.payload.process.key, "103365/2026");
  assert.deepEqual(sent.at(-1)[2], { frameId: 13 });
  assert.deepEqual(suspendedWorker.getFrameRegistration(7), {
    frameId: 13,
  });
  assert.equal(Object.hasOwn(session.state["frame-registrations:v1"][0], "url"), false);
});

test("removes a tab frame registration from storage.session when the tab is removed", async () => {
  const storage = storageMock();
  const session = storageMock();
  const chromeApi = chromeMock(storage, async () => ({ ok: true }), session);
  const worker = createServiceWorker({ chromeApi });

  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-remove-session"),
    sender(7, 12),
  );
  chromeApi.fireTabRemoved(7);
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(worker.getFrameRegistration(7), null);
  assert.deepEqual(session.state, { "frame-registrations:v1": [] });
});

test("clears an unresponsive frame and clears a removed tab", async () => {
  const storage = storageMock();
  let shouldFail = true;
  const chromeApi = chromeMock(storage, async (tabId, message) => {
    if (message.type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) {
      return { ok: true, payload: snapshot() };
    }
    if (shouldFail) throw new Error("frame gone");
    return { ok: true };
  });
  const worker = createServiceWorker({ chromeApi });
  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-1"),
    sender(7, 12),
  );

  const failed = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.APPLY_FIELDS, { fields: { cargo: "frame gone" } }, "apply-1"),
    { url: "chrome-extension://test/panel.html", tab: { id: 7 } },
  );
  assert.equal(failed.ok, false);
  assert.equal(worker.getFrameRegistration(7), null);

  shouldFail = false;
  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-2"),
    sender(7, 12),
  );
  chromeApi.fireTabRemoved(7);
  assert.equal(worker.getFrameRegistration(7), null);
});

test("routes an extension-page request through the active registered portal tab", async () => {
  const storage = storageMock();
  const sent = [];
  const queries = [];
  const chromeApi = chromeMock(storage, async (...args) => {
    sent.push(args);
    return { ok: true, payload: snapshot() };
  });
  chromeApi.tabs.query = async (query) => {
    queries.push(query);
    return [{ id: 7 }];
  };
  const worker = createServiceWorker({ chromeApi });

  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-active"),
    sender(7, 12),
  );
  const response = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "snapshot-from-panel"),
    extensionSender(),
  );

  assert.equal(response.ok, true);
  assert.equal(sent.length, 1);
  assert.equal(sent[0][0], 7);
  assert.deepEqual(sent[0][2], { frameId: 12 });
  assert.deepEqual(queries, [{ active: true, currentWindow: true }]);
});

test("does not route a panel request to a non-active registered tab", async () => {
  const storage = storageMock();
  const sent = [];
  const chromeApi = chromeMock(storage, async (...args) => {
    sent.push(args);
    return { ok: true };
  });
  chromeApi.tabs.query = async () => [{ id: 99 }];
  const worker = createServiceWorker({ chromeApi });

  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-background"),
    sender(7, 12),
  );
  const response = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "snapshot-stale-panel"),
    extensionSender(),
  );

  assert.equal(response.ok, false);
  assert.equal(response.error.code, "TAB_REQUIRED");
  assert.deepEqual(sent, []);
});

test("ignores a stale extension sender tab when the active tab has no registered frame", async () => {
  const storage = storageMock();
  const sent = [];
  const chromeApi = chromeMock(storage, async (...args) => {
    sent.push(args);
    return { ok: true };
  });
  chromeApi.tabs.query = async () => [{ id: 99 }];
  const worker = createServiceWorker({ chromeApi });

  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-stale"),
    sender(7, 12),
  );
  const response = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "snapshot-stale-sender"),
    extensionSender(7),
  );

  assert.equal(response.ok, false);
  assert.equal(response.error.code, "FRAME_NOT_REGISTERED");
  assert.deepEqual(sent, []);
});

test("fails closed when an extension request cannot resolve the active tab", async () => {
  const storage = storageMock();
  const sent = [];
  const chromeApi = chromeMock(storage, async (...args) => {
    sent.push(args);
    return { ok: true };
  });
  delete chromeApi.tabs.query;
  const worker = createServiceWorker({ chromeApi });

  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "ready-no-query"),
    sender(7, 12),
  );
  const response = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "snapshot-no-query"),
    extensionSender(7),
  );

  assert.equal(response.ok, false);
  assert.equal(response.error.code, "FRAME_NOT_REGISTERED");
  assert.deepEqual(sent, []);
});

test("rejects messages without requestId before dispatch", async () => {
  const worker = createServiceWorker({ chromeApi: chromeMock(storageMock()) });
  const response = await worker.handleMessage({
    schemaVersion: 1,
    type: MESSAGE_TYPES.GET_FORM_SNAPSHOT,
    payload: {},
  }, { url: "chrome-extension://test/panel.html" });

  assert.equal(response.ok, false);
  assert.match(response.error.code, /INVALID_MESSAGE/u);
});

test("automation control messages are restricted to extension pages and use the injected bridge", async () => {
  const storage = storageMock();
  const calls = [];
  const bridge = {
    async createAutomationRun(spec, eventId) {
      calls.push(["start", spec, eventId]);
      return { api_version: 1, run_id: "run-1", revision: 0, status: "discovering", items: [], last_confirmed_item_id: null };
    },
    async controlAutomationRun(runId, body) {
      calls.push(["control", runId, body]);
      return { api_version: 1, run_id: runId, revision: body.expectedRevision + 1, status: body.action === "pause" ? "paused" : "stopped", items: [], last_confirmed_item_id: null };
    },
    async getAutomationRun(runId) {
      calls.push(["status", runId]);
      return { api_version: 1, run_id: runId, revision: 0, status: "discovering", items: [], last_confirmed_item_id: null };
    },
  };
  const worker = createServiceWorker({ chromeApi: chromeMock(storage), bridge });
  const spec = {
    tabId: 7,
    sector: "aposentadorias",
    datasetSha256: "a".repeat(64),
    rulesVersion: "legal-foundation-v1",
  };

  const denied = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_START, { spec, eventId: "start-denied" }, "auto-denied"),
    sender(),
  );
  assert.equal(denied.ok, false);
  assert.equal(denied.error.code, "UNAUTHORIZED");

  const started = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_START, { spec, eventId: "start-1" }, "auto-start"),
    extensionSender(),
  );
  assert.equal(started.ok, true);
  assert.equal(started.payload.run_id, "run-1");

  const paused = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_PAUSE, { runId: "run-1", eventId: "pause-1", expectedRevision: 0 }, "auto-pause"),
    extensionSender(),
  );
  assert.equal(paused.ok, true);
  const status = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_STATUS, { runId: "run-1" }, "auto-status"),
    extensionSender(),
  );
  assert.equal(status.ok, true);
  assert.deepEqual(calls.map((call) => call[0]), ["start", "control", "status"]);
});

test("automation watchdog refreshes an active run and clears after an explicit stop", async () => {
  const storage = storageMock();
  const alarms = { created: [], cleared: [], listeners: [] };
  const chromeApi = chromeMock(storage);
  chromeApi.alarms = {
    onAlarm: { addListener(listener) { alarms.listeners.push(listener); } },
    create(name, info) { alarms.created.push({ name, info }); },
    clear(name) { alarms.cleared.push(name); },
  };
  const calls = [];
  const controller = {
    async start(spec, eventId) {
      calls.push(["start", spec, eventId]);
      return { run_id: "run-watchdog", revision: 0, status: "running" };
    },
    async status(options) {
      calls.push(["status", options]);
      return { run_id: "run-watchdog", revision: 1, status: "running" };
    },
    async stop(payload) {
      calls.push(["stop", payload]);
      return { run_id: "run-watchdog", revision: 2, status: "stopped" };
    },
  };
  const worker = createServiceWorker({ chromeApi, bridge: {}, automationController: controller });
  const spec = {
    tabId: 7,
    sector: "aposentadorias",
    datasetSha256: "a".repeat(64),
    rulesVersion: "legal-foundation-v1",
  };

  const started = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_START, { spec, eventId: "watchdog-start" }, "watchdog-start"),
    extensionSender(),
  );
  assert.equal(started.ok, true);
  assert.deepEqual(alarms.created, [{ name: "automation-watchdog-v1", info: { periodInMinutes: 1 } }]);
  assert.equal(alarms.listeners.length, 1);

  alarms.listeners[0]({ name: "automation-watchdog-v1" });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(calls[1], ["status", { refresh: true, runId: "run-watchdog" }]);

  const stopped = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_STOP, { runId: "run-watchdog", eventId: "watchdog-stop", expectedRevision: 0 }, "watchdog-stop"),
    extensionSender(),
  );
  assert.equal(stopped.ok, true);
  assert.deepEqual(alarms.cleared, ["automation-watchdog-v1"]);
});

test("portal content events are routed to the automation controller with tab and frame identity", async () => {
  const events = [];
  const controller = {
    async handlePortalEvent(event) {
      events.push(event);
      return { status: "running", frame: { frameId: event.frameId } };
    },
  };
  const worker = createServiceWorker({
    chromeApi: chromeMock(storageMock()),
    automationController: controller,
  });
  const portalSnapshot = {
    role: "list",
    generation: 4,
    sector: "aposentadorias",
    identities: [],
    actions: [],
  };

  const response = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.PORTAL_EVENT, {
      event: { type: "snapshot", snapshot: portalSnapshot },
    }, "portal-event-1"),
    { ...sender(7, 12), id: "test-extension" },
  );

  assert.equal(response.ok, true);
  assert.deepEqual(events, [{
    type: "snapshot",
    snapshot: portalSnapshot,
    tabId: 7,
    frameId: 12,
  }]);
});

test("portal content events accept the extension content script but reject extension pages, IDs, and origins", async () => {
  const events = [];
  const controller = {
    async handlePortalEvent(event) {
      events.push(event);
      return { status: "running" };
    },
  };
  const worker = createServiceWorker({
    chromeApi: chromeMock(storageMock()),
    automationController: controller,
  });
  const message = createMessage(MESSAGE_TYPES.PORTAL_EVENT, {
    event: { type: "manual_navigation" },
  }, "portal-event-denied");

  const contentResponse = await worker.handleMessage(message, { ...sender(), id: "test-extension" });
  assert.equal(contentResponse.ok, true);
  assert.equal(events.length, 1);

  const extensionResponse = await worker.handleMessage(message, extensionSender(7));
  assert.equal(extensionResponse.ok, false);
  assert.equal(extensionResponse.error.code, "UNAUTHORIZED");

  const divergentIdResponse = await worker.handleMessage(message, { ...sender(), id: "other-extension" });
  assert.equal(divergentIdResponse.ok, false);
  assert.equal(divergentIdResponse.error.code, "INVALID_ORIGIN");

  const unrelatedResponse = await worker.handleMessage(message, { ...sender(7, 12, "https://example.test/other"), id: "test-extension" });
  assert.equal(unrelatedResponse.ok, false);
  assert.equal(unrelatedResponse.error.code, "INVALID_ORIGIN");
});

test("portal events preserve unresolved row identities as pending without backend queue identity", () => {
  const pendingSnapshot = {
    role: "list",
    generation: 1,
    sector: "aposentadorias",
    identities: [{
      processKey: null,
      interestedOriginal: "",
      interestedNormalized: null,
      portalActId: null,
      pending: true,
    }],
    actions: [],
  };
  const message = createMessage(MESSAGE_TYPES.PORTAL_EVENT, {
    event: { type: "snapshot", snapshot: pendingSnapshot },
  }, "portal-pending");

  assert.deepEqual(message.payload.event.snapshot.identities, pendingSnapshot.identities);
});

test("routes button-frame registration and sibling-form verification only from the authenticated portal frame", async () => {
  const calls = [];
  const controller = {
    async handleSubmitFrameReady(input) {
      calls.push(["ready", input]);
      return { registered: true };
    },
    async verifySubmitState(input) {
      calls.push(["verify", input]);
      return { ok: true, visible: true, paused: false, frame_id: 12 };
    },
  };
  const worker = createServiceWorker({
    chromeApi: chromeMock(storageMock()),
    automationController: controller,
  });
  const portalSender = { ...sender(7, 14), id: "test-extension" };
  const command = {
    command_id: "command-1",
    state: "issued",
    issued_at: 2_000,
    expires_at: 17_000,
    frame_id: 14,
    form_frame_id: 12,
    generation: 3,
    identity: {
      processKey: PROCESS_KEY,
      interestedNormalized: "joao da silva",
      portalActId: null,
    },
    expected_fields_hash: "a".repeat(64),
  };

  const ready = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.SUBMIT_FRAME_READY, {
      url: PORTAL_URL,
      button_id: "btnComplementarAto",
    }, "submit-frame-ready"),
    portalSender,
  );
  assert.equal(ready.ok, true);
  assert.deepEqual(calls[0], ["ready", { tabId: 7, frameId: 14, buttonId: "btnComplementarAto" }]);

  const verify = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_VERIFY_SUBMIT_STATE, {
      runId: "run-1",
      expectedRevision: 4,
      command,
      phase: "before_click",
    }, "submit-state-verify"),
    portalSender,
  );
  assert.equal(verify.ok, true);
  assert.equal(calls[1][0], "verify");
  assert.equal(calls[1][1].tabId, 7);
  assert.equal(calls[1][1].frameId, 14);
  assert.equal(calls[1][1].command.form_frame_id, 12);

  const denied = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.SUBMIT_FRAME_READY, { url: PORTAL_URL }, "submit-frame-denied"),
    { ...portalSender, id: "other-extension" },
  );
  assert.equal(denied.ok, false);
  assert.equal(denied.error.code, "UNAUTHORIZED");
});

test("automation control rejects a content script even when its sender id is the extension", async () => {
  const bridge = {
    async createAutomationRun() {
      throw new Error("must not be called");
    },
  };
  const worker = createServiceWorker({ chromeApi: chromeMock(storageMock()), bridge });
  const response = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_START, {
      spec: {
        tabId: 7,
        sector: "aposentadorias",
        datasetSha256: "a".repeat(64),
        rulesVersion: "legal-foundation-v1",
      },
      eventId: "start-content-script",
    }, "auto-content-script"),
    { ...sender(), id: "test-extension" },
  );
  assert.equal(response.ok, false);
  assert.equal(response.error.code, "UNAUTHORIZED");
});

async function assertAutomationRejectedForSender(senderValue) {
  const calls = [];
  const bridge = {
    async createAutomationRun() {
      calls.push("start");
      return {};
    },
    async controlAutomationRun() {
      calls.push("control");
      return {};
    },
    async getAutomationRun() {
      calls.push("status");
      return {};
    },
  };
  const worker = createServiceWorker({ chromeApi: chromeMock(storageMock()), bridge });
  const messages = [
    [MESSAGE_TYPES.AUTO_START, {
      spec: {
        tabId: 7,
        sector: "aposentadorias",
        datasetSha256: "a".repeat(64),
        rulesVersion: "legal-foundation-v1",
      },
      eventId: "identity-check-start",
    }],
    [MESSAGE_TYPES.AUTO_PAUSE, { runId: "run-1", eventId: "identity-check-pause", expectedRevision: 0 }],
    [MESSAGE_TYPES.AUTO_RESUME, { runId: "run-1", eventId: "identity-check-resume", expectedRevision: 0 }],
    [MESSAGE_TYPES.AUTO_STOP, { runId: "run-1", eventId: "identity-check-stop", expectedRevision: 0 }],
    [MESSAGE_TYPES.AUTO_STATUS, { runId: "run-1" }],
  ];

  for (const [index, [type, payload]] of messages.entries()) {
    const response = await worker.handleMessage(
      createMessage(type, payload, `identity-check-${index}`),
      senderValue,
    );
    assert.equal(response.ok, false, `${type} should be rejected`);
    assert.equal(response.error.code, "UNAUTHORIZED", `${type} should be unauthorized`);
  }
  assert.deepEqual(calls, []);
}

test("automation control rejects another extension id in the sender URL", async () => {
  await assertAutomationRejectedForSender({
    id: "test-extension",
    url: "chrome-extension://other-extension/panel.html",
  });
});

test("automation control rejects a sender id that differs from the installed extension", async () => {
  await assertAutomationRejectedForSender({
    id: "other-extension",
    url: "chrome-extension://test-extension/panel.html",
  });
});

test("automation messages preserve manual fallback when the old service has no bridge", async () => {
  const worker = createServiceWorker({ chromeApi: chromeMock(storageMock()) });
  const response = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_START, {
      spec: {
        tabId: 7,
        sector: "aposentadorias",
        datasetSha256: "a".repeat(64),
        rulesVersion: "legal-foundation-v1",
      },
      eventId: "start-old-service",
    }, "auto-old-service"),
    extensionSender(),
  );
  assert.equal(response.ok, false);
  assert.equal(response.error.code, "AUTOMATION_UNAVAILABLE");
});

test("failed AUTO_START clears the active run and watchdog state", async () => {
  const storage = storageMock();
  const alarms = { created: [], cleared: [], listeners: [] };
  const chromeApi = chromeMock(storage);
  chromeApi.alarms = {
    onAlarm: { addListener(listener) { alarms.listeners.push(listener); } },
    create(name, info) { alarms.created.push({ name, info }); },
    clear(name) { alarms.cleared.push(name); },
  };
  let starts = 0;
  const controller = {
    async start() {
      starts += 1;
      if (starts === 2) throw new Error("start failed");
      return { run_id: "run-cleanup", revision: 0, status: "running" };
    },
  };
  const worker = createServiceWorker({
    chromeApi,
    bridge: { createAutomationRun() {}, controlAutomationRun() {} },
    automationController: controller,
  });
  const spec = {
    tabId: 7,
    sector: "aposentadorias",
    datasetSha256: "a".repeat(64),
    rulesVersion: "legal-foundation-v1",
  };

  const started = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_START, { spec, eventId: "cleanup-start" }, "cleanup-start"),
    extensionSender(),
  );
  assert.equal(started.ok, true);
  const failed = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_START, { spec, eventId: "cleanup-retry" }, "cleanup-retry"),
    extensionSender(),
  );
  assert.equal(failed.ok, false);
  assert.equal(failed.error.code, "AUTOMATION_ERROR");
  assert.equal(alarms.created.length, 1);
  assert.deepEqual(alarms.cleared, ["automation-watchdog-v1"]);
});

test("AUTO_START resolves the authenticated worker bridge without exposing its token", async () => {
  const storage = storageMock();
  const token = "opaque-worker-token";
  const session = storageMock({
    [STORAGE_KEYS.BRIDGE_BASE_URL]: "http://127.0.0.1:18743",
    [STORAGE_KEYS.BRIDGE_TOKEN]: token,
  });
  const bridgeCalls = [];
  let factoryOptions = null;
  const bridge = {
    async createAutomationRun(spec, eventId) {
      bridgeCalls.push(["start", spec, eventId]);
      return { api_version: 1, run_id: "run-authenticated", revision: 0, status: "discovering", items: [], last_confirmed_item_id: null };
    },
    async getDataset() {
      bridgeCalls.push(["dataset"]);
      return { api_version: 1, revision: 1, dataset: { batch: { logical_sha256: "a".repeat(64) } } };
    },
    async freezeAutomationQueue(runId, queue) {
      bridgeCalls.push(["freeze", runId, queue]);
      return { api_version: 1, run_id: runId, revision: 1, status: "running", items: [], last_confirmed_item_id: null };
    },
    async controlAutomationRun(runId, body) {
      bridgeCalls.push(["control", runId, body]);
      return { api_version: 1, run_id: runId, revision: 1, status: "paused", items: [], last_confirmed_item_id: null };
    },
  };
  const sent = [];
  const chromeApi = chromeMock(
    storage,
    async (_tabId, message, options) => {
      sent.push({ message, options });
      return {
        ok: true,
        frameId: options?.frameId ?? 12,
        payload: {
          role: "list",
          generation: 1,
          sector: "aposentadorias",
          identities: [],
          actions: [],
        },
      };
    },
    session,
  );
  const worker = createServiceWorker({
    chromeApi,
    bridgeClientFactory(options) {
      factoryOptions = options;
      return bridge;
    },
  });

  const response = await worker.handleMessage(createMessage(MESSAGE_TYPES.AUTO_START, {
    spec: {
      tabId: 7,
      sector: "aposentadorias",
      datasetSha256: "a".repeat(64),
      rulesVersion: "legal-foundation-v1",
    },
    eventId: "auto-authenticated",
  }, "auto-authenticated"), extensionSender());

  assert.equal(response.ok, true);
  assert.equal(response.payload.runId, "run-authenticated");
  assert.deepEqual(factoryOptions, {
    baseUrl: "http://127.0.0.1:18743",
    token,
  });
  assert.equal(JSON.stringify(response).includes(token), false);
  assert.equal(JSON.stringify(sent).includes(token), false);
  assert.deepEqual(bridgeCalls.map(([name]) => name), ["start", "dataset", "freeze"]);
});

test("contextual getMatch caches by identity, dataset, rules and revision", async () => {
  const dataset = await makeDataset();
  const calls = [];
  const ranker = (input) => {
    calls.push(input.context);
    return { kind: "pending", optionIndex: null, optionValue: null, optionLabel: null, score: 0, reasons: [] };
  };
  const storage = storageMock();
  const worker = createServiceWorker({ chromeApi: chromeMock(storage), ranker });
  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.IMPORT_DATASET, { dataset }, "import-context"),
    extensionSender(),
  );
  const context = {
    schema_version: 1,
    dataset_sha256: dataset.batch.logical_sha256,
    process_key: PROCESS_KEY,
    interested_normalized: "joao da silva",
    resolution_status: "complete",
    operative_text: "RESOLVE: Art. 6º da EC 41/2003.",
    pages: [],
    context_revision: 1,
    rules_version: "legal-foundation-v1",
  };
  const payload = {
    processKey: PROCESS_KEY,
    interestedNormalized: "joao da silva",
    options: { fundamento_legal: [{ value: "ec41", label: "Art. 6 da EC 41/2003" }] },
    context,
    datasetSha256: dataset.batch.logical_sha256,
    rulesVersion: "legal-foundation-v1",
    contextRevision: 1,
  };
  const first = await worker.handleMessage(createMessage(MESSAGE_TYPES.GET_MATCH, payload, "match-context-1"), extensionSender());
  const second = await worker.handleMessage(createMessage(MESSAGE_TYPES.GET_MATCH, payload, "match-context-2"), extensionSender());
  const third = await worker.handleMessage(createMessage(MESSAGE_TYPES.GET_MATCH, {
    ...payload,
    context: { ...context, context_revision: 2 },
    contextRevision: 2,
  }, "match-context-3"), extensionSender());
  assert.equal(first.ok, true);
  assert.equal(second.ok, true);
  assert.equal(third.ok, true);
  assert.equal(calls.length, 3);
  assert.equal(calls[0].operative_text, context.operative_text);
  assert.equal(calls[2].operative_text, context.operative_text);
});

test("contextual getMatch rejects backend context hash or revision mismatches", async () => {
  const dataset = await makeDataset();
  const worker = createServiceWorker({ chromeApi: chromeMock(storageMock()) });
  await worker.handleMessage(
    createMessage(MESSAGE_TYPES.IMPORT_DATASET, { dataset }, "import-context-bindings"),
    extensionSender(),
  );

  const baseContext = {
    schema_version: 1,
    dataset_sha256: dataset.batch.logical_sha256,
    process_key: PROCESS_KEY,
    interested_normalized: "joao da silva",
    resolution_status: "complete",
    operative_text: "RESOLVE: Art. 6º",
    pages: [],
    context_revision: 7,
    rules_version: "legal-foundation-v1",
  };
  const options = { fundamento_legal: [{ value: "art-6", label: "Art. 6º" }] };

  const hashMismatch = await worker.handleMessage(
    createMessage(
      MESSAGE_TYPES.GET_MATCH,
      {
        processKey: PROCESS_KEY,
        interestedNormalized: "joao da silva",
        options,
        context: { ...baseContext, dataset_sha256: "b".repeat(64) },
        datasetSha256: "b".repeat(64),
        rulesVersion: "legal-foundation-v1",
        contextRevision: 7,
      },
      "match-context-hash-mismatch",
    ),
    extensionSender(),
  );
  assert.equal(hashMismatch.ok, false);
  assert.equal(hashMismatch.error.code, "CONTEXT_DATASET_MISMATCH");

  const revisionMismatch = await worker.handleMessage(
    createMessage(
      MESSAGE_TYPES.GET_MATCH,
      {
        processKey: PROCESS_KEY,
        interestedNormalized: "joao da silva",
        options,
        context: baseContext,
        datasetSha256: dataset.batch.logical_sha256,
        rulesVersion: "legal-foundation-v1",
        contextRevision: 8,
      },
      "match-context-revision-mismatch",
    ),
    extensionSender(),
  );
  assert.equal(revisionMismatch.ok, false);
  assert.equal(revisionMismatch.error.code, "CONTEXT_REVISION_MISMATCH");
});

test("wires the authenticated automatic resolver to the loaded dataset and contextual ranker without sending", async () => {
  const dataset = await makeDataset();
  const legalContext = {
    schema_version: 1,
    dataset_sha256: dataset.batch.logical_sha256,
    process_key: PROCESS_KEY,
    interested_normalized: "joao da silva",
    resolution_status: "complete",
    operative_text: "RESOLVE: Art. 40, § 5º.",
    pages: [],
    context_revision: 12,
    rules_version: "legal-foundation-v1",
  };
  const surfaces = {
    list: {
      role: "list",
      generation: 1,
      sector: "aposentadorias",
      identities: [{ processKey: PROCESS_KEY, interestedNormalized: "joao da silva", portalActId: "act-1" }],
      actions: [{ action: "open_act", enabled: true, identity: { processKey: PROCESS_KEY, interestedNormalized: "joao da silva", portalActId: "act-1" } }],
    },
    interested: {
      role: "interested",
      generation: 2,
      sector: "aposentadorias",
      identities: [{ processKey: PROCESS_KEY, interestedNormalized: "joao da silva", portalActId: "act-1", selected: false }],
      actions: [{ action: "select_interested", enabled: true, identity: { processKey: PROCESS_KEY, interestedNormalized: "joao da silva", portalActId: "act-1" } }],
    },
    form: {
      role: "form",
      generation: 3,
      sector: "aposentadorias",
      identities: [],
      actions: [{ action: "return_list", enabled: true, identity: { processKey: PROCESS_KEY, interestedNormalized: "joao da silva", portalActId: "act-1" } }],
    },
    returned: {
      role: "list",
      generation: 4,
      sector: "aposentadorias",
      identities: [{ processKey: PROCESS_KEY, interestedNormalized: "joao da silva", portalActId: "act-1" }],
      actions: [],
    },
  };
  const values = {
    modalidade: "Aposentadoria voluntária",
    fundamento_legal: "Art. 40",
    data_publicacao_doe: "07/02/2020",
    cargo: "PROFESSOR PN - IV",
    matricula: "103.870-2/1",
    data_nascimento: "30/04/1967",
    genero: "Feminino",
  };
  const formValues = Object.fromEntries(Object.keys(values).map((field) => [field, ""]));
  let currentSurface = surfaces.list;
  const bridgeCalls = [];
  const rankCalls = [];
  const storage = storageMock();
  const ranker = (input) => {
    rankCalls.push(input);
    if (input.field === "fundamento_legal") {
      return {
        kind: "exact",
        optionIndex: 0,
        optionValue: input.options[0]?.value ?? values.fundamento_legal,
        optionLabel: input.options[0]?.label ?? "Art. 40",
        score: 100,
        reasons: ["contextual-rule"],
        legalDecision: {
          status: "selected",
          method: "rule",
          rule_id: "EC41_COM_P5",
          option_value: input.options[0]?.value ?? values.fundamento_legal,
          option_label: input.options[0]?.label ?? "Art. 40",
          rules_version: "legal-foundation-v1",
        },
      };
    }
    return {
      kind: "exact",
      optionIndex: 0,
      optionValue: values[input.field],
      optionLabel: values[input.field],
      score: 100,
      reasons: ["fixture"],
    };
  };
  const bridge = {
    async createAutomationRun(spec, eventId) {
      bridgeCalls.push(["start", spec, eventId]);
      return { api_version: 1, run_id: "run-fase6", revision: 0, status: "discovering", items: [], last_confirmed_item_id: null };
    },
    async getDataset() {
      bridgeCalls.push(["dataset"]);
      return { api_version: 1, revision: 1, dataset };
    },
    async getLegalContext(identity) {
      bridgeCalls.push(["context", identity]);
      return { api_version: 1, context: legalContext };
    },
    async freezeAutomationQueue(runId, body) {
      bridgeCalls.push(["freeze", runId, body]);
      return { api_version: 1, run_id: runId, revision: 1, status: "running", items: [], last_confirmed_item_id: null };
    },
    async appendAutomationEvent(runId, event) {
      bridgeCalls.push(["event", runId, event]);
      return { api_version: 1, run_id: runId, revision: 2, status: "running", items: [], last_confirmed_item_id: null };
    },
    async getAutomationRun(runId) {
      return { api_version: 1, run_id: runId, revision: 2, status: "running", items: [], last_confirmed_item_id: null };
    },
    async controlAutomationRun() {
      return { api_version: 1, run_id: "run-fase6", revision: 3, status: "stopped", items: [], last_confirmed_item_id: null };
    },
  };
  const chromeApi = chromeMock(storage, async (tabId, message, options) => {
    const frameId = options?.frameId ?? 12;
    if (message.type === MESSAGE_TYPES.PORTAL_GET_SNAPSHOT) {
      return { ok: true, frameId, payload: structuredClone(currentSurface) };
    }
    if (message.type === MESSAGE_TYPES.PORTAL_NAVIGATE) {
      if (message.payload.action === "open_act") currentSurface = surfaces.interested;
      if (message.payload.action === "select_interested") currentSurface = surfaces.form;
      if (message.payload.action === "return_list") currentSurface = surfaces.returned;
      return { ok: true, frameId, navigationToken: message.requestId, payload: { snapshot: structuredClone(currentSurface) } };
    }
    if (message.type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) {
      return {
        ok: true,
        frameId,
        payload: {
          process: { number: "103439", year: "2023", key: PROCESS_KEY },
          interested: { original: "João da Silva", normalized: "joao da silva" },
          options: {
            modalidade: [{ value: values.modalidade, label: values.modalidade }],
            fundamento_legal: [{ value: values.fundamento_legal, label: values.fundamento_legal }],
            genero: [{ value: values.genero, label: values.genero }],
          },
          fields: Object.fromEntries(Object.keys(values).map((field) => [field, {
            value: formValues[field], disabled: false, readOnly: false,
          }])),
        },
      };
    }
    if (message.type === MESSAGE_TYPES.APPLY_FIELDS) {
      Object.assign(formValues, message.payload.fields);
      return { ok: true, frameId, payload: { changed: Object.keys(message.payload.fields), preserved: [], missing: [], disabled: [], errors: [] } };
    }
    return { ok: true, frameId, payload: {} };
  });
  const worker = createServiceWorker({ chromeApi, bridge, ranker });
  await worker.handleMessage(createMessage(MESSAGE_TYPES.IMPORT_DATASET, { dataset }, "import-fase6"), extensionSender());
  const spec = {
    tabId: 7,
    sector: "aposentadorias",
    datasetSha256: dataset.batch.logical_sha256,
    rulesVersion: "legal-foundation-v1",
  };

  const denied = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_START, { spec, eventId: "fase6-denied" }, "fase6-denied"),
    sender(),
  );
  assert.equal(denied.ok, false);
  assert.equal(denied.error.code, "UNAUTHORIZED");

  const started = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.AUTO_START, { spec, eventId: "fase6-start" }, "fase6-start"),
    extensionSender(),
  );
  assert.equal(started.ok, true);
  assert.equal(bridgeCalls.some(([name]) => name === "context"), true);
  assert.equal(rankCalls.some((input) => input.field === "fundamento_legal" && input.context === legalContext), true);
  assert.equal(formValues.fundamento_legal, values.fundamento_legal);
  assert.equal(bridgeCalls.some(([name, , event]) => name === "event" && event.type === "fields_verified"), true);
});
