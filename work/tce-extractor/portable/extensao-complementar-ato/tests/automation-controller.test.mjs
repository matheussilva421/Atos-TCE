import test from "node:test";
import assert from "node:assert/strict";

import { createAutomationController } from "../background/automation-controller.js";
import { validateAutomationEvent } from "../lib/automation-schema.js";
import { resolveLegalFoundation } from "../lib/legal-foundation.js";
import { MESSAGE_TYPES } from "../lib/messages.js";

const HASH = "a".repeat(64);

function identity(processKey, interestedNormalized, portalActId = null) {
  return { processKey, interestedNormalized, portalActId };
}

function snapshot(role, generation, identities = [], actions = [], sector = "aposentadorias", marker = undefined) {
  return {
    role, generation, sector, identities, actions,
    ...(marker === undefined ? {} : { marker }),
  };
}

function runSpec() {
  return {
    tabId: 7,
    sector: "aposentadorias",
    datasetSha256: HASH,
    rulesVersion: "legal-foundation-v1",
  };
}

function markerSnapshot(role, generation, identities = [], actions = [], marker = "PROFESSOR - IPERN - 2 RUBRICAS") {
  return snapshot(role, generation, identities, actions, "aposentadorias", { label: marker, value: "marker-2" });
}

function bridgeMock() {
  const calls = [];
  const initial = {
    api_version: 1,
    run_id: "run-1",
    revision: 0,
    status: "discovering",
    items: [],
    last_confirmed_item_id: null,
  };
  return {
    calls,
    async createAutomationRun(spec, eventId) {
      calls.push(["start", spec, eventId]);
      return structuredClone(initial);
    },
    async getDataset() {
      calls.push(["dataset"]);
      return { api_version: 1, revision: 1, dataset: { batch: { logical_sha256: HASH } } };
    },
    async freezeAutomationQueue(runId, queue) {
      calls.push(["freeze", runId, structuredClone(queue)]);
      return {
        ...structuredClone(initial),
        revision: 1,
        status: "running",
        items: queue.identities.map((item, index) => ({
          item_id: item.processKey,
          ordinal: index + 1,
          identity: item,
          state: "queued",
        })),
      };
    },
    async getAutomationRun(runId) {
      calls.push(["status", runId]);
      return { ...structuredClone(initial), run_id: runId, status: "running" };
    },
    async controlAutomationRun(runId, body) {
      calls.push([body.action, runId, body]);
      return { ...structuredClone(initial), run_id: runId, revision: body.expectedRevision + 1, status: body.action === "pause" ? "paused" : body.action === "stop" ? "stopped" : "running" };
    },
  };
}

function chromeMock(snapshots) {
  const calls = [];
  let current = 0;
  const removedListeners = [];
  const updatedListeners = [];
  return {
    calls,
    storage: {
      session: {
        state: {},
        async get(keys) {
          return Object.fromEntries(keys.filter((key) => Object.hasOwn(this.state, key)).map((key) => [key, structuredClone(this.state[key])]));
        },
        async set(values) {
          Object.assign(this.state, structuredClone(values));
        },
      },
    },
    tabs: {
      async sendMessage(tabId, message, options) {
        calls.push([tabId, message, options]);
        if (message.type === "PORTAL_GET_SNAPSHOT") {
          return {
            ok: true,
            frameId: Number.isSafeInteger(options?.frameId) ? options.frameId : 0,
            payload: structuredClone(snapshots[Math.min(current, snapshots.length - 1)]),
          };
        }
        if (message.type === "PORTAL_NAVIGATE") {
          current += 1;
          return {
            ok: true,
            frameId: Number.isSafeInteger(options?.frameId) ? options.frameId : 0,
            navigationToken: message.requestId,
            payload: { snapshot: structuredClone(snapshots[Math.min(current, snapshots.length - 1)]) },
          };
        }
        return { ok: true, payload: {} };
      },
      onRemoved: { addListener(listener) { removedListeners.push(listener); } },
      onUpdated: { addListener(listener) { updatedListeners.push(listener); } },
    },
    fireTabRemoved(tabId) {
      for (const listener of removedListeners) listener(tabId);
    },
    fireTabUpdated(tabId, changeInfo) {
      for (const listener of updatedListeners) listener(tabId, changeInfo);
    },
  };
}

function activeChromeMock(page) {
  const chromeApi = chromeMock([page]);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") {
      return {
        ok: true,
        frameId: Number.isSafeInteger(options?.frameId) ? options.frameId : 0,
        navigationToken: message.requestId,
        payload: {},
      };
    }
    return originalSendMessage(tabId, message, options);
  };
  return chromeApi;
}

const PAGE_1 = snapshot("list", 1, [
  { processKey: "103401/2023", interestedOriginal: "Ana da Silva", interestedNormalized: "ana da silva", portalActId: "act-1" },
  { processKey: "103402/2023", interestedOriginal: "Bruno de Souza", interestedNormalized: "bruno de souza", portalActId: "act-2" },
], [{ action: "next_page", enabled: true }]);
const PAGE_2 = snapshot("list", 2, [
  { processKey: "103403/2023", interestedOriginal: "Carla de Lima", interestedNormalized: "carla de lima", portalActId: "act-3" },
  { processKey: "103404/2023", interestedOriginal: "Diego Alves", interestedNormalized: "diego alves", portalActId: "act-4" },
], [{ action: "next_page", enabled: true }]);
const PAGE_3 = snapshot("list", 3, [
  { processKey: "103405/2023", interestedOriginal: "Érica Santos", interestedNormalized: "erica santos", portalActId: "act-5" },
], []);

test("starts a run, discovers 2/2/1 pages, deduplicates rerenders, and freezes before process navigation", async () => {
  const bridge = bridgeMock();
  const chromeApi = chromeMock([PAGE_1, PAGE_2, PAGE_3]);
  const controller = createAutomationController({ chromeApi, bridge, clock: { now: () => 1000 } });

  const started = await controller.start({ spec: runSpec(), eventId: "start-1" });
  assert.equal(started.run_id, "run-1");
  const state = controller.status();
  assert.equal(state.totals.discovered, 5);
  assert.equal(state.totals.unique, 5);
  assert.equal(state.totals.pending, 0);
  assert.equal(state.queueFrozen, true);
  assert.equal(bridge.calls.findIndex(([name]) => name === "freeze") >= 0, true);
  assert.equal(chromeApi.calls.some(([, message]) => message.type === "PORTAL_NAVIGATE" && message.payload.action === "open_act"), false);

  await controller.handlePortalEvent({ tabId: 7, frameId: 0, type: "snapshot", snapshot: PAGE_2 });
  await controller.handlePortalEvent({ tabId: 7, frameId: 0, type: "snapshot", snapshot: PAGE_2 });
  assert.equal(controller.status().totals.unique, 5);
  assert.equal(chromeApi.storage.session.state["portal-frame-registrations:v1"][0].role, "list");
});

test("requires the live Area Restrita list to match the selected source scope", async () => {
  const bridge = bridgeMock();
  const page = { ...PAGE_1, source_scope: "sector_finalistic" };
  const controller = createAutomationController({ chromeApi: chromeMock([page]), bridge });
  const started = await controller.start({
    spec: { ...runSpec(), sourceScope: "my_processes", lotSize: 50, acquisitionSource: "econtas" },
    eventId: "start-source-mismatch",
  });
  assert.equal(started.status, "paused");
  assert.match(started.pausedReason, /origem selecionada.*lista aberta/iu);
  assert.equal(started.sourceScope, "my_processes");
  assert.equal(bridge.calls.some(([name]) => name === "freeze"), false);
});

test("analyzes every observed page into sanitized Area Restrita rows without freezing or opening an act", async () => {
  const bridge = bridgeMock();
  const page = {
    ...markerSnapshot("list", 1, [
      { ...identity("103401/2023", "ana da silva", "act-1"), needsComplement: true },
      { ...identity("103402/2023", "bruno de souza", "act-2"), needsComplement: false },
    ], []),
    source_scope: "sector_finalistic",
  };
  const controller = createAutomationController({ chromeApi: chromeMock([page]), bridge });
  const result = await controller.analyze({
    spec: { ...runSpec(), marker: "PROFESSOR - IPERN - 2 RUBRICAS", sourceScope: "sector_finalistic", lotSize: 50, acquisitionSource: "econtas" },
    eventId: "analysis-1",
  });
  assert.equal(result.source_scope, "sector_finalistic");
  assert.deepEqual(result.marker, { label: "PROFESSOR - IPERN - 2 RUBRICAS", value: "marker-2" });
  assert.equal(result.rows.length, 2);
  assert.equal(result.rows[0].area_restrita.needs_complement, true);
  assert.match(result.rows[0].area_restrita.action_observed, /Complementar Ato/u);
  assert.equal(result.rows[0].area_restrita.snapshot_hash.length, 64);
  assert.equal(bridge.calls.some(([name]) => name === "freeze"), false);
  assert.equal(controller.status().status, "stopped");
});

test("reads and locks the marker already selected in the Area Restrita without a typed marker or dataset", async () => {
  const bridge = bridgeMock();
  const actionSignature = {
    kind: "red_complement_icon",
    alt: "Complementar Ato",
    title: "Complementar Ato",
    src: "../../images/icone-complementar-ato-vermelho.png",
  };
  const firstPage = {
    ...markerSnapshot("list", 1, [
      { ...identity("103401/2023", "ana da silva", "act-1"), needsComplement: true, actionSignature },
    ], [{ action: "next_page", enabled: true }]),
    source_scope: "sector_finalistic",
  };
  const lastPage = {
    ...markerSnapshot("list", 2, [
      { ...identity("103402/2023", "bruno de souza", "act-2"), needsComplement: false, actionSignature: null },
    ], []),
    source_scope: "sector_finalistic",
  };
  const chromeApi = chromeMock([firstPage, lastPage]);
  const controller = createAutomationController({ chromeApi, bridge });

  const result = await controller.analyze({
    spec: {
      ...runSpec(),
      datasetSha256: null,
      analysisOnly: true,
      sourceScope: "sector_finalistic",
      lotSize: 50,
      acquisitionSource: "econtas",
    },
    eventId: "analysis-selected-marker",
  });

  assert.deepEqual(result.marker, { label: "PROFESSOR - IPERN - 2 RUBRICAS", value: "marker-2" });
  assert.equal(result.area_snapshot_sha256.length, 64);
  assert.deepEqual(result.rows[0].area_restrita.action_signature, actionSignature);
  assert.equal(chromeApi.calls.some(([, message]) => message.payload?.action === "filter_marker"), false);
});

test("v3 analysis queries workbook keys absent from the marker and preserves input order", async () => {
  const pendingSignature = {
    kind: "red_complement_icon",
    alt: "Complementar Ato",
    title: "Complementar Ato",
    src: "red.png",
  };
  const markerPage = {
    ...markerSnapshot("list", 1, [
      { ...identity("101/2023", "ana da silva", "act-1"), needsComplement: true, actionSignature: pendingSignature },
    ], [{ action: "find_process", enabled: true }]),
    source_scope: "sector_finalistic",
  };
  const exactSearchResult = {
    ...markerSnapshot("list", 2, [], [{ action: "find_process", enabled: true }]),
    source_scope: "sector_finalistic",
  };
  const chromeApi = chromeMock([markerPage, exactSearchResult]);
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const result = await controller.analyze({
    spec: {
      ...runSpec(),
      datasetSha256: null,
      analysisOnly: true,
      sourceScope: "sector_finalistic",
      lotSize: 300,
      acquisitionSource: "econtas",
      inputListId: `input-${"b".repeat(24)}`,
      inputSha256: "c".repeat(64),
      inputUniqueCount: 2,
      inputKeys: ["101/2023", "202/2024"],
    },
    eventId: "analysis-input-list",
  });

  assert.deepEqual(result.rows.map((row) => row.process_key), ["101/2023", "202/2024"]);
  assert.equal(result.rows[0].area_restrita.classification, "PRECISA_COMPLEMENTAR");
  assert.equal(result.rows[1].area_restrita.classification, "NAO_ENCONTRADO_AREA_RESTRITA");
  const exactQuery = chromeApi.calls.find(([, message]) => (
    message.type === MESSAGE_TYPES.PORTAL_NAVIGATE && message.payload.action === "find_process"
  ));
  assert.equal(exactQuery[1].payload.process_key, "202/2024");
  assert.equal(controller.status().status, "stopped");
});

test("resets a marker analysis to the first page before collecting every page", async () => {
  const middle = {
    ...markerSnapshot("list", 6, [identity("106/2026", "middle", "act-6")], [
      { action: "first_page", enabled: true, direction: "first" },
      { action: "next_page", enabled: true, direction: "next" },
    ]),
    source_scope: "sector_finalistic",
  };
  const first = {
    ...markerSnapshot("list", 1, [identity("101/2026", "first", "act-1")], [
      { action: "next_page", enabled: true, direction: "next" },
    ]),
    source_scope: "sector_finalistic",
  };
  const last = {
    ...markerSnapshot("list", 2, [identity("102/2026", "last", "act-2")], []),
    source_scope: "sector_finalistic",
  };
  const chromeApi = chromeMock([middle, first, last]);
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const result = await controller.analyze({ spec: {
    ...runSpec(), datasetSha256: null, analysisOnly: true,
    sourceScope: "sector_finalistic", lotSize: 50, acquisitionSource: "econtas",
  }, eventId: "analysis-middle-page" });

  assert.deepEqual(result.rows.map((row) => row.process_key), ["101/2026", "102/2026"]);
  const navigations = chromeApi.calls
    .filter(([, message]) => message.type === "PORTAL_NAVIGATE")
    .map(([, message]) => message.payload.action);
  assert.deepEqual(navigations, ["first_page", "next_page"]);
});

test("allows analyze retry after a guard pauses without a persisted run", async () => {
  const bridge = bridgeMock();
  const goodPage = {
    ...markerSnapshot("list", 2, [
      { ...identity("103401/2023", "ana da silva", "act-1"), needsComplement: true },
    ], []),
    source_scope: "sector_finalistic",
  };
  const badPage = {
    ...snapshot("list", 1, [
      { ...identity("103401/2023", "ana da silva", "act-1"), needsComplement: true },
    ], []),
    source_scope: "sector_finalistic",
  };
  const chromeApi = chromeMock([goodPage]);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  let firstSnapshot = true;
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    const response = await originalSendMessage(tabId, message, options);
    if (message.type === "PORTAL_GET_SNAPSHOT" && firstSnapshot) {
      firstSnapshot = false;
      return { ...response, payload: structuredClone(badPage) };
    }
    return response;
  };
  const controller = createAutomationController({ chromeApi, bridge });
  const spec = {
    ...runSpec(),
    marker: "PROFESSOR - IPERN - 2 RUBRICAS",
    sourceScope: "sector_finalistic",
    lotSize: 50,
    acquisitionSource: "econtas",
  };

  const first = await controller.analyze({ spec, eventId: "analysis-guarded" });

  assert.equal(first.ok, false);
  assert.equal(controller.status().status, "paused");
  assert.equal(controller.status().runId, null);

  const retried = await controller.analyze({ spec, eventId: "analysis-retry" });

  assert.equal(retried.rows.length, 1);
  assert.deepEqual(retried.marker, { label: "PROFESSOR - IPERN - 2 RUBRICAS", value: "marker-2" });
  assert.equal(controller.status().status, "stopped");

  const pausedRunController = createAutomationController({
    chromeApi: chromeMock([snapshot("unknown", 1)]),
    bridge: bridgeMock(),
  });
  await pausedRunController.start({ spec: runSpec(), eventId: "start-paused" });
  await assert.rejects(
    () => pausedRunController.analyze({ spec: runSpec(), eventId: "analysis-blocked" }),
    (error) => error.code === "ACTIVE_RUN",
  );
});

test("applies the requested marker before discovering every page and freezes only the filtered queue", async () => {
  const target = { ...identity("103401/2023", "ana da silva", "act-1"), needsComplement: true };
  const filteredPage = markerSnapshot("list", 2, [target], [{ action: "next_page", enabled: true }]);
  const lastPage = markerSnapshot("list", 3, [
    { ...identity("103402/2023", "bruno de souza", "act-2"), needsComplement: true },
    { ...identity("103403/2023", "carla de lima", "act-3"), needsComplement: false },
  ], []);
  const bridge = bridgeMock();
  const chromeApi = chromeMock([
    snapshot("list", 1, [target], [{ action: "filter_marker", enabled: true }]),
    filteredPage,
    lastPage,
  ]);
  const controller = createAutomationController({ chromeApi, bridge });
  const result = await controller.start({
    spec: { ...runSpec(), marker: "PROFESSOR - IPERN - 2 RUBRICAS" },
    eventId: "start-marker",
  });
  assert.equal(result.marker, "PROFESSOR - IPERN - 2 RUBRICAS");
  assert.equal(result.totals.unique, 3);
  assert.equal(result.totals.pending, 1);
  assert.equal(bridge.calls.find(([name]) => name === "freeze")[2].identities.length, 2);
  const markerCall = chromeApi.calls.find(([, message]) => message.type === MESSAGE_TYPES.PORTAL_NAVIGATE && message.payload.action === "filter_marker");
  assert.equal(markerCall[1].payload.marker, "PROFESSOR - IPERN - 2 RUBRICAS");
});

test("pilot mode freezes only the explicitly selected identity", async () => {
  const target = identity("103401/2023", "ana da silva", "act-1");
  const bridge = bridgeMock();
  const controller = createAutomationController({ chromeApi: chromeMock([PAGE_1, PAGE_2, PAGE_3]), bridge });

  await controller.start({
    spec: { ...runSpec(), mode: "pilot", pilotIdentity: target },
    eventId: "start-pilot",
  });

  const status = controller.status();
  assert.equal(status.mode, "pilot");
  assert.deepEqual(status.totals, { discovered: 5, unique: 1, pending: 0 });
  assert.deepEqual(bridge.calls.find(([name]) => name === "freeze")[2].identities, [target]);
});

test("pilot with a confirmed marker stops discovery on the page containing its target", async () => {
  const target = identity("103401/2023", "ana da silva", "act-1");
  const targetRow = { ...target, needsComplement: true };
  const marker = "PROFESSOR - IPERN - 2 RUBRICAS";
  const pages = {
    1: { ...lifecycleList(1, [targetRow], { next: true }), marker: { label: marker, value: "marker-2" }, source_scope: "sector_finalistic" },
    2: { ...lifecycleList(2, [identity("103402/2023", "bruno de souza", "act-2")], { next: true }), marker: { label: marker, value: "marker-2" }, source_scope: "sector_finalistic" },
    3: { ...lifecycleList(3, [identity("103403/2023", "carla de lima", "act-3")], { first: true }), marker: { label: marker, value: "marker-2" }, source_scope: "sector_finalistic" },
  };
  const bridge = bridgeMock();
  const chromeApi = lifecycleChromeMock(pages);

  await createAutomationController({ chromeApi, bridge }).start({
    spec: {
      ...runSpec(),
      mode: "pilot",
      pilotIdentity: target,
      marker,
      sourceScope: "sector_finalistic",
      markerValue: "marker-2",
      acquisitionSource: "econtas",
    },
    eventId: "pilot-marker-fast-path",
  });

  const nextNavigations = chromeApi.calls.filter(([, message]) => (
    message.type === "PORTAL_NAVIGATE" && message.payload.action === "next_page"
  ));
  assert.equal(nextNavigations.length, 0);
  assert.equal(chromeApi.calls.filter(([, message]) => (
    message.type === "PORTAL_NAVIGATE" && message.payload.action === "open_act"
  )).length, 1);
  assert.deepEqual(bridge.calls.find(([name]) => name === "freeze")[2].identities, [target]);
});

test("keeps an unresolved identity in totals and pauses when pagination repeats", async () => {
  const unresolved = snapshot("list", 1, [
    { processKey: null, interestedOriginal: "", interestedNormalized: null, portalActId: null, pending: true },
  ], []);
  const unresolvedBridge = bridgeMock();
  const unresolvedController = createAutomationController({
    chromeApi: chromeMock([unresolved]),
    bridge: unresolvedBridge,
  });
  await unresolvedController.start({ spec: runSpec(), eventId: "start-pending" });
  assert.deepEqual(unresolvedController.status().totals, { discovered: 1, unique: 1, pending: 1 });
  assert.equal(unresolvedController.status().queueFrozen, true);
  assert.deepEqual(unresolvedBridge.calls.find(([name]) => name === "freeze")[2].identities, []);

  const repeatedBridge = bridgeMock();
  const repeatedController = createAutomationController({
    chromeApi: chromeMock([PAGE_1, PAGE_1]),
    bridge: repeatedBridge,
  });
  await repeatedController.start({ spec: runSpec(), eventId: "start-repeat" });
  assert.equal(repeatedController.status().status, "paused");
  assert.match(repeatedController.status().pausedReason, /repeated/iu);
  assert.equal(repeatedController.status().queueFrozen, false);
});

test("does not add identities observed after the queue has been frozen", async () => {
  const bridge = bridgeMock();
  const controller = createAutomationController({ chromeApi: chromeMock([PAGE_1, PAGE_2, PAGE_3]), bridge });
  await controller.start({ spec: runSpec(), eventId: "start-frozen" });

  await controller.handlePortalEvent({
    tabId: 7,
    frameId: 0,
    type: "snapshot",
    snapshot: snapshot("list", 4, [identity("103406/2023", "nova pessoa", "act-6")], []),
  });

  assert.equal(controller.status().queueFrozen, true);
  assert.deepEqual(controller.status().totals, { discovered: 5, unique: 5, pending: 0 });
});

function lifecycleList(page, identities, { next = false, first = false } = {}) {
  return snapshot(
    "list",
    page,
    identities,
    [
      ...identities.map((item) => ({ action: "open_act", enabled: true, identity: item })),
      ...((next || first) ? [{ action: "next_page", enabled: true, direction: first ? "first" : "next" }] : []),
    ],
  );
}

function lifecycleChromeMock(pages, { genericReturnList = false } = {}) {
  const calls = [];
  let currentPage = 1;
  let currentSurface = pages[1];
  return {
    calls,
    storage: { session: { async get() { return {}; }, async set() {} } },
    tabs: {
      async sendMessage(tabId, message, options) {
        calls.push([tabId, message, options]);
        if (message.type === "PORTAL_GET_SNAPSHOT") {
          return {
            ok: true,
            frameId: Number.isSafeInteger(options?.frameId) ? options.frameId : 0,
            payload: structuredClone(currentSurface),
          };
        }
        if (message.type !== "PORTAL_NAVIGATE") return { ok: true, payload: {} };
        const { action, identity: requested } = message.payload;
        if (action === "next_page") {
          currentPage = currentPage === 3 ? 1 : currentPage + 1;
          currentSurface = pages[currentPage];
        } else if (action === "open_act") {
          currentSurface = snapshot("interested", 10 + currentPage, [
            { ...requested, selected: false },
          ], [
            { action: "select_interested", enabled: true, identity: { ...requested, selected: false } },
            { action: "return_list", enabled: true, identity: requested },
          ]);
        } else if (action === "select_interested") {
          currentSurface = snapshot("interested", 20 + currentPage, [
            { ...requested, selected: true },
          ], genericReturnList
            ? [{ action: "return_list", enabled: true }]
            : [{ action: "return_list", enabled: true, identity: { ...requested, selected: true } }]);
        } else if (action === "return_list") {
          currentPage = 1;
          currentSurface = pages[1];
        }
        return {
          ok: true,
          frameId: Number.isSafeInteger(options?.frameId) ? options.frameId : 0,
          navigationToken: message.requestId,
          payload: { snapshot: structuredClone(currentSurface) },
        };
      },
      onRemoved: { addListener() {} },
    },
  };
}

function responseFrameChromeMock(page, frameId) {
  const chromeApi = activeChromeMock(page);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    const response = await originalSendMessage(tabId, message, options);
    if (message.type === "PORTAL_GET_SNAPSHOT") return { ...response, frameId };
    return response;
  };
  return chromeApi;
}

test("freezes then resets from the final discovery page and completes the full five-item cycle", async () => {
  const identities = [
    identity("103401/2023", "ana da silva", "act-1"),
    identity("103402/2023", "bruno de souza", "act-2"),
    identity("103403/2023", "carla de lima", "act-3"),
    identity("103404/2023", "diego alves", "act-4"),
    identity("103405/2023", "erica santos", "act-5"),
  ];
  const pages = {
    1: lifecycleList(1, identities.slice(0, 2), { next: true }),
    2: lifecycleList(2, identities.slice(2, 4), { next: true }),
    3: lifecycleList(3, identities.slice(4), { first: true }),
  };
  const bridge = bridgeMock();
  const chromeApi = lifecycleChromeMock(pages);
  const controller = createAutomationController({ chromeApi, bridge });

  const result = await controller.start({ spec: runSpec(), eventId: "start-cycle" });

  assert.equal(result.status, "completed");
  assert.equal(result.queueFrozen, true);
  assert.equal(result.currentIdentity, null);
  assert.equal(result.totals.unique, 5);
  assert.equal(chromeApi.calls.filter(([, message]) => message.type === "PORTAL_NAVIGATE" && message.payload.action === "open_act").length, 5);
});

test("integrated local qualification processes 25 acts across two pages and preserves three pending identities", async () => {
  const all = Array.from({ length: 22 }, (_, index) => identity(
    `${200000 + index}/2024`,
    `interessado ${index + 1}`,
    `act-${index + 1}`,
  ));
  const pending = [
    { processKey: "pending-1/2024", interestedOriginal: "", interestedNormalized: null, portalActId: null, pending: true },
    { processKey: "pending-2/2024", interestedOriginal: "", interestedNormalized: null, portalActId: null, pending: true },
    { processKey: "pending-3/2024", interestedOriginal: "", interestedNormalized: null, portalActId: null, pending: true },
  ];
  const firstValid = all.slice(0, 11);
  const secondValid = all.slice(11);
  const first = { ...lifecycleList(1, firstValid, { next: true }), identities: [...firstValid, pending[0], pending[1]] };
  const second = { ...lifecycleList(2, secondValid, { first: true }), identities: [...secondValid, pending[2]] };
  const bridge = bridgeMock();
  const chromeApi = lifecycleChromeMock({ 1: first, 2: second, 3: first });
  const result = await createAutomationController({ chromeApi, bridge }).start({
    spec: runSpec(),
    eventId: "qualification-25-acts",
  });

  assert.equal(result.status, "completed");
  assert.equal(result.totals.discovered, 25);
  assert.equal(result.totals.unique, 25);
  assert.equal(result.totals.pending, 3);
  assert.equal(bridge.calls.find(([name]) => name === "freeze")[2].identities.length, 22);
  assert.equal(chromeApi.calls.filter(([, message]) => message.type === "PORTAL_NAVIGATE" && message.payload.action === "open_act").length, 22);
});

test("completes and advances when the selected interested return control is generic", async () => {
  const requested = identity("103401/2023", "ana da silva", "act-1");
  const second = identity("103402/2023", "bruno de souza", "act-2");
  const pages = { 1: lifecycleList(1, [requested, second]) };
  const bridge = bridgeMock();
  const chromeApi = lifecycleChromeMock(pages, { genericReturnList: true });
  const result = await createAutomationController({ chromeApi, bridge }).start({
    spec: runSpec(),
    eventId: "start-generic-return",
  });

  assert.equal(result.status, "completed");
  assert.equal(result.currentIdentity, null);
  assert.equal(chromeApi.calls.filter(([, message]) => message.type === "PORTAL_NAVIGATE" && message.payload.action === "open_act").length, 2);
});

test("keeps unresolved identities in totals, pauses on manual/sector changes, and ignores another tab", async () => {
  const bridge = bridgeMock();
  const activePage = snapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
    { action: "open_act", enabled: true, identity: identity("103401/2023", "ana da silva", "act-1") },
  ]);
  const chromeApi = activeChromeMock(activePage);
  const controller = createAutomationController({ chromeApi, bridge, clock: { now: () => 1000 } });
  await controller.start({ spec: runSpec(), eventId: "start-2" });
  await controller.handlePortalEvent({
    tabId: 99,
    frameId: 0,
    type: "navigation",
    snapshot: snapshot("list", 9, [], [], "outra-secao"),
  });
  assert.equal(controller.status().status, "running");

  await controller.handlePortalEvent({ tabId: 7, frameId: 0, type: "manual_navigation", snapshot: PAGE_1 });
  assert.equal(controller.status().status, "paused");
  assert.match(controller.status().pausedReason, /manual/iu);
  const resumed = await controller.resume({ eventId: "resume-2" });
  assert.equal(resumed.status, "running");
  await controller.handlePortalEvent({ tabId: 7, frameId: 0, type: "sector_changed", snapshot: { ...PAGE_1, sector: "outra-secao" } });
  assert.equal(controller.status().status, "paused");
  assert.match(controller.status().pausedReason, /setor/iu);
});

test("does not pause for its own loading marker but pauses for an external loading", async () => {
  const activePage = snapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
    { action: "open_act", enabled: true, identity: identity("103401/2023", "ana da silva", "act-1") },
  ]);
  const chromeApi = activeChromeMock(activePage);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") {
      const frameId = options?.frameId ?? 0;
      chromeApi.fireTabUpdated(7, { status: "loading", frameId, navigationToken: message.requestId });
      const response = { ok: true, frameId, navigationToken: message.requestId, payload: {} };
      chromeApi.fireTabUpdated(7, { status: "complete", frameId, navigationToken: message.requestId });
      return response;
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const started = await controller.start({ spec: runSpec(), eventId: "start-loading" });
  assert.equal(started.status, "running");
  assert.notEqual(started.pausedReason, "manual navigation detected");

  chromeApi.fireTabUpdated(7, { status: "loading" });
  assert.equal(controller.status().status, "paused");
  assert.equal(controller.status().pausedReason, "manual navigation detected");
});

test("native tab loading without frame metadata keeps the pilot running through an act subframe load", async () => {
  const target = identity("103401/2023", "ana da silva", "act-1");
  const chromeApi = activeChromeMock(snapshot("list", 1, [target], [{ action: "open_act", enabled: true, identity: target }]));
  const navigationListeners = [];
  chromeApi.webNavigation = { onBeforeNavigate: { addListener(listener) { navigationListeners.push(listener); } } };
  const original = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") chromeApi.fireTabUpdated(tabId, { status: "loading" });
    return original(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });
  await controller.start({ spec: runSpec(), eventId: "native-load" });
  for (const listener of navigationListeners) listener({ tabId: 7, frameId: 88 });
  chromeApi.fireTabUpdated(7, { status: "loading" });
  assert.equal(controller.status().status, "running");
  assert.equal(controller.status().pausedReason, null);
});

test("native top-frame navigation still pauses the pilot while other tabs do not", async () => {
  const target = identity("103401/2023", "ana da silva", "act-1");
  const chromeApi = activeChromeMock(snapshot("list", 1, [target], [{ action: "open_act", enabled: true, identity: target }]));
  const navigationListeners = [];
  chromeApi.webNavigation = { onBeforeNavigate: { addListener(listener) { navigationListeners.push(listener); } } };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });
  await controller.start({ spec: runSpec(), eventId: "native-top-load" });
  for (const listener of navigationListeners) listener({ tabId: 8, frameId: 0 });
  assert.equal(controller.status().status, "running");
  for (const listener of navigationListeners) listener({ tabId: 7, frameId: 0 });
  assert.equal(controller.status().status, "paused");
  assert.equal(controller.status().pausedReason, "manual navigation detected");
});

test("pauses when a same-tab loading event has the wrong navigation token or frame", async () => {
  const activePage = snapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
    { action: "open_act", enabled: true, identity: identity("103401/2023", "ana da silva", "act-1") },
  ]);
  const chromeApi = activeChromeMock(activePage);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") {
      chromeApi.fireTabUpdated(7, { status: "loading", frameId: (options?.frameId ?? 0) + 1, navigationToken: "wrong-token" });
      return { ok: true, frameId: options?.frameId ?? 0, navigationToken: message.requestId, payload: {} };
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const started = await controller.start({ spec: runSpec(), eventId: "start-wrong-loading" });
  assert.equal(started.status, "paused");
  assert.equal(started.pausedReason, "navigation token/frame mismatch");
});

test("accepts a same-frame loading event when Chrome omits its navigation marker", async () => {
  const activePage = snapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
    { action: "open_act", enabled: true, identity: identity("103401/2023", "ana da silva", "act-1") },
  ]);
  const chromeApi = activeChromeMock(activePage);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") {
      chromeApi.fireTabUpdated(7, { status: "loading", frameId: options?.frameId ?? 0 });
      return { ok: true, frameId: options?.frameId ?? 0, navigationToken: message.requestId, payload: {} };
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const started = await controller.start({ spec: runSpec(), eventId: "start-missing-loading-marker" });
  assert.equal(started.status, "running");
  assert.notEqual(started.pausedReason, "navigation token/frame mismatch");
});

test("keeps running when the legacy portal reloads its own act subframe outside a navigation", async () => {
  const activePage = snapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
    { action: "open_act", enabled: true, identity: identity("103401/2023", "ana da silva", "act-1") },
  ]);
  const chromeApi = activeChromeMock(activePage);
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const started = await controller.start({ spec: runSpec(), eventId: "start-act-subframe-reload" });
  assert.equal(started.status, "running");

  // Live evidence (tmp/fase41/act-post-response.html): the act screen carries
  // `body onload="includeDataJs()"` next to the dvLoading fadeOut and reloads
  // its own nested screens whenever the portal advances a step, always after
  // the navigation promise has already settled. Chrome reports those loads with
  // a non-zero frameId; they are portal churn, not the operator taking over.
  chromeApi.fireTabUpdated(7, { status: "loading", frameId: 3 });
  assert.equal(controller.status().status, "running");
  assert.equal(controller.status().pausedReason, null);

  // A frameless load is still the top-level tab navigation the gate protects.
  chromeApi.fireTabUpdated(7, { status: "loading" });
  assert.equal(controller.status().status, "paused");
  assert.equal(controller.status().pausedReason, "manual navigation detected");
});

test("binds an explicitly identified non-zero frame from the initial snapshot response", async () => {
  const activePage = snapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
    { action: "open_act", enabled: true, identity: identity("103401/2023", "ana da silva", "act-1") },
  ]);
  const chromeApi = responseFrameChromeMock(activePage, 3);
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const started = await controller.start({ spec: runSpec(), eventId: "start-response-frame" });
  assert.equal(started.frame.frameId, 3);
  assert.equal(chromeApi.calls.find(([, message]) => message.type === "PORTAL_GET_SNAPSHOT")[2], undefined);
});

test("fails closed when a broadcast snapshot does not identify its responding frame", async () => {
  const activePage = snapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
    { action: "open_act", enabled: true, identity: identity("103401/2023", "ana da silva", "act-1") },
  ]);
  const chromeApi = activeChromeMock(activePage);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_GET_SNAPSHOT" && options === undefined) {
      return { ok: true, payload: structuredClone(activePage) };
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const started = await controller.start({ spec: runSpec(), eventId: "start-ambiguous-frame" });
  assert.equal(started.status, "paused");
  assert.equal(started.pausedReason, "portal frame unavailable");
  assert.equal(started.frame, null);
});

test("recovers the scoped list frame after reload when an unknown frame precedes it", async () => {
  const unknownPage = snapshot("unknown", 1);
  const sectorPage = { ...PAGE_1, actions: [], marker: { label: "PROFESSOR - IPERN - 2 RUBRICAS", value: "marker-2" }, source_scope: "sector_finalistic" };
  const myProcessesPage = { ...PAGE_1, actions: [], source_scope: "my_processes" };
  const chromeApi = chromeMock([unknownPage]);
  chromeApi.webNavigation = {
    async getAllFrames(details) {
      assert.deepEqual(details, { tabId: 7 });
      return [{ frameId: 0 }, { frameId: 6 }, { frameId: 4 }];
    },
  };
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_GET_SNAPSHOT" && Number.isSafeInteger(options?.frameId)) {
      const frameId = options.frameId;
      return {
        ok: true,
        frameId,
        payload: structuredClone(frameId === 4 ? sectorPage : frameId === 6 ? myProcessesPage : unknownPage),
      };
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const result = await controller.analyze({
    spec: { ...runSpec(), sourceScope: "sector_finalistic" },
    eventId: "analysis-recover-scoped-frame",
  });

  assert.equal(result.source_scope, "sector_finalistic");
  assert.equal(result.totals.unique, 2);
  assert.equal(result.frame_id, 4);
  assert.deepEqual(controller.status().frame, {
    frameId: 4,
    role: "list",
    generation: 1,
    sector: "aposentadorias",
    source_scope: "sector_finalistic",
  });
});

test("recovers a paginated list from a new frame after the navigation frame disappears", async () => {
  const pageOne = {
    ...markerSnapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
      { action: "next_page", enabled: true, direction: "next" },
    ]),
    source_scope: "sector_finalistic",
  };
  const pageTwo = {
    ...markerSnapshot("list", 1, [identity("103402/2023", "bruno de souza", "act-2")], []),
    source_scope: "sector_finalistic",
  };
  const chromeApi = chromeMock([pageOne]);
  chromeApi.webNavigation = {
    async getAllFrames() {
      return [{ frameId: 4 }, { frameId: 6 }];
    },
  };
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") {
      return null;
    }
    if (message.type === "PORTAL_GET_SNAPSHOT" && options?.frameId === 4) {
      return { ok: true, frameId: 4, payload: structuredClone(pageOne) };
    }
    if (message.type === "PORTAL_GET_SNAPSHOT" && options?.frameId === 6) {
      return { ok: true, frameId: 6, payload: structuredClone(pageTwo) };
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const result = await controller.analyze({
    spec: {
      ...runSpec(),
      marker: "PROFESSOR - IPERN - 2 RUBRICAS",
      sourceScope: "sector_finalistic",
      lotSize: 50,
      acquisitionSource: "econtas",
    },
    eventId: "analysis-frame-rollover",
  });

  assert.equal(result.source_scope, "sector_finalistic");
  assert.equal(result.rows.length, 2);
  assert.equal(result.frame_id, 6);
});

test("recovers the paginated list when the portal reports a navigation timeout after loading", async () => {
  const pageOne = {
    ...markerSnapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
      { action: "next_page", enabled: true, direction: "next" },
    ]),
    source_scope: "sector_finalistic",
  };
  const pageTwo = {
    ...markerSnapshot("list", 2, [identity("103402/2023", "bruno de souza", "act-2")], []),
    source_scope: "sector_finalistic",
  };
  const chromeApi = chromeMock([pageOne]);
  chromeApi.webNavigation = {
    async getAllFrames() {
      return [{ frameId: 4 }, { frameId: 6 }];
    },
  };
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") {
      return { ok: false, error: { code: "NAVIGATION_TIMEOUT", message: "portal did not confirm navigation" } };
    }
    if (message.type === "PORTAL_GET_SNAPSHOT" && options?.frameId === 4) {
      return { ok: true, frameId: 4, payload: structuredClone(pageOne) };
    }
    if (message.type === "PORTAL_GET_SNAPSHOT" && options?.frameId === 6) {
      return { ok: true, frameId: 6, payload: structuredClone(pageTwo) };
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const result = await controller.analyze({
    spec: {
      ...runSpec(),
      marker: "PROFESSOR - IPERN - 2 RUBRICAS",
      sourceScope: "sector_finalistic",
      lotSize: 50,
      acquisitionSource: "econtas",
    },
    eventId: "analysis-timeout-after-load",
  });

  assert.equal(result.source_scope, "sector_finalistic");
  assert.equal(result.rows.length, 2);
  assert.equal(result.frame_id, 6);
});

test("waits for the progressed list when legacy pagination returns without a snapshot", async () => {
  const pageOne = {
    ...markerSnapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
      { action: "next_page", enabled: true, direction: "next" },
    ]),
    source_scope: "sector_finalistic",
  };
  const pageTwo = {
    ...markerSnapshot("list", 2, [identity("103402/2023", "bruno de souza", "act-2")], []),
    source_scope: "sector_finalistic",
  };
  const chromeApi = chromeMock([pageOne]);
  chromeApi.webNavigation = {
    async getAllFrames() {
      return [{ frameId: 4 }, { frameId: 6 }];
    },
  };
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") {
      return {
        ok: true,
        frameId: Number.isSafeInteger(options?.frameId) ? options.frameId : 0,
        navigationToken: message.requestId,
        payload: {},
      };
    }
    if (message.type === "PORTAL_GET_SNAPSHOT" && options?.frameId === 4) {
      return { ok: true, frameId: 4, payload: structuredClone(pageOne) };
    }
    if (message.type === "PORTAL_GET_SNAPSHOT" && options?.frameId === 6) {
      return { ok: true, frameId: 6, payload: structuredClone(pageTwo) };
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const result = await controller.analyze({
    spec: {
      ...runSpec(),
      marker: "PROFESSOR - IPERN - 2 RUBRICAS",
      sourceScope: "sector_finalistic",
      lotSize: 50,
      acquisitionSource: "econtas",
    },
    eventId: "analysis-wait-for-list",
  });

  assert.equal(result.source_scope, "sector_finalistic");
  assert.equal(result.rows.length, 2);
  assert.equal(result.frame_id, 6);
});

test("ignores a transient unknown snapshot from the expected legacy pagination frame", async () => {
  const pageOne = {
    ...markerSnapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
      { action: "next_page", enabled: true, direction: "next" },
    ]),
    source_scope: "sector_finalistic",
  };
  const pageTwo = {
    ...markerSnapshot("list", 2, [identity("103402/2023", "bruno de souza", "act-2")], []),
    source_scope: "sector_finalistic",
  };
  const chromeApi = chromeMock([pageOne, pageTwo]);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  let controller;
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") {
      await controller.handlePortalEvent({
        tabId,
        frameId: options?.frameId ?? 0,
        type: "snapshot",
        snapshot: snapshot("unknown", 3),
      });
      return {
        ok: true,
        frameId: options?.frameId ?? 0,
        navigationToken: message.requestId,
        payload: { snapshot: structuredClone(pageTwo) },
      };
    }
    return originalSendMessage(tabId, message, options);
  };
  controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const result = await controller.analyze({
    spec: {
      ...runSpec(),
      marker: "PROFESSOR - IPERN - 2 RUBRICAS",
      sourceScope: "sector_finalistic",
      lotSize: 50,
      acquisitionSource: "econtas",
    },
    eventId: "analysis-transient-unknown-pagination",
  });

  assert.equal(result.source_scope, "sector_finalistic");
  assert.equal(result.rows.length, 2);
  assert.equal(controller.status().status, "stopped");
});

test("accepts a progressed list event from a replacement legacy pagination frame", async () => {
  const pageOne = {
    ...markerSnapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
      { action: "next_page", enabled: true, direction: "next" },
    ]),
    source_scope: "sector_finalistic",
  };
  const pageTwo = {
    ...markerSnapshot("list", 2, [identity("103402/2023", "bruno de souza", "act-2")], []),
    source_scope: "sector_finalistic",
  };
  const chromeApi = chromeMock([pageOne]);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  let controller;
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") {
      await controller.handlePortalEvent({
        tabId,
        frameId: 6,
        type: "snapshot",
        snapshot: pageTwo,
      });
      return {
        ok: true,
        frameId: options?.frameId ?? 0,
        navigationToken: message.requestId,
        payload: {},
      };
    }
    return originalSendMessage(tabId, message, options);
  };
  controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const result = await controller.analyze({
    spec: {
      ...runSpec(),
      marker: "PROFESSOR - IPERN - 2 RUBRICAS",
      sourceScope: "sector_finalistic",
      lotSize: 50,
      acquisitionSource: "econtas",
    },
    eventId: "analysis-progress-event-pagination",
  });

  assert.equal(result.source_scope, "sector_finalistic");
  assert.equal(result.rows.length, 2);
  assert.equal(result.frame_id, 6);
  assert.equal(controller.status().status, "stopped");
});

test("refreshes a stale list generation before the next legacy pagination action", async () => {
  const pageOne = {
    ...markerSnapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
      { action: "next_page", enabled: true, direction: "next" },
    ]),
    source_scope: "sector_finalistic",
  };
  const stalePageTwo = {
    ...markerSnapshot("list", 1, [identity("103402/2023", "bruno de souza", "act-2")], [
      { action: "next_page", enabled: true, direction: "next" },
    ]),
    source_scope: "sector_finalistic",
  };
  const freshPageTwo = {
    ...markerSnapshot("list", 2, [identity("103402/2023", "bruno de souza", "act-2")], []),
    source_scope: "sector_finalistic",
  };
  const chromeApi = chromeMock([pageOne]);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  let snapshotReads = 0;
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_GET_SNAPSHOT") {
      snapshotReads += 1;
      return {
        ok: true,
        frameId: options?.frameId ?? 0,
        payload: structuredClone(snapshotReads >= 2 ? freshPageTwo : pageOne),
      };
    }
    if (message.type === "PORTAL_NAVIGATE") {
      if (message.payload.action === "next_page" && snapshotReads <= 2) {
        return {
          ok: true,
          frameId: options?.frameId ?? 0,
          navigationToken: message.requestId,
          payload: { snapshot: structuredClone(stalePageTwo) },
        };
      }
      return { ok: false, error: { code: "STALE_GENERATION", message: "stale page" } };
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const result = await controller.analyze({
    spec: {
      ...runSpec(),
      marker: "PROFESSOR - IPERN - 2 RUBRICAS",
      sourceScope: "sector_finalistic",
      lotSize: 50,
      acquisitionSource: "econtas",
    },
    eventId: "analysis-refresh-stale-pagination",
  });

  assert.equal(result.source_scope, "sector_finalistic");
  assert.equal(result.rows.length, 2);
  assert.equal(controller.status().status, "stopped");
});

test("accepts Chrome loading for the expected frame without a synthetic navigation token", async () => {
  const activePage = snapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
    { action: "open_act", enabled: true, identity: identity("103401/2023", "ana da silva", "act-1") },
  ]);
  const chromeApi = activeChromeMock(activePage);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") {
      chromeApi.fireTabUpdated(7, { status: "loading", frameId: options?.frameId ?? 0 });
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const started = await controller.start({ spec: runSpec(), eventId: "start-standard-loading" });

  assert.equal(started.status, "running");
  assert.notEqual(started.pausedReason, "navigation token/frame mismatch");
});

test("binds the discovered frame and pauses fail-closed on frame send errors", async () => {
  const activePage = snapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
    { action: "open_act", enabled: true, identity: identity("103401/2023", "ana da silva", "act-1") },
  ]);
  const chromeApi = activeChromeMock(activePage);
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });
  await controller.handlePortalEvent({ tabId: 7, frameId: 3, type: "snapshot", snapshot: activePage });
  const started = await controller.start({ spec: runSpec(), eventId: "start-frame" });
  assert.equal(started.frame.frameId, 3);
  assert.equal(chromeApi.calls.find(([, message]) => message.type === "PORTAL_GET_SNAPSHOT")[2].frameId, 3);

  const errorChromeApi = activeChromeMock(activePage);
  const originalErrorSendMessage = errorChromeApi.tabs.sendMessage.bind(errorChromeApi.tabs);
  errorChromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_NAVIGATE") {
      const error = new Error("frame disappeared");
      error.code = "NO_FRAME";
      throw error;
    }
    return originalErrorSendMessage(tabId, message, options);
  };
  const errorController = createAutomationController({ chromeApi: errorChromeApi, bridge: bridgeMock() });
  const failed = await errorController.start({ spec: runSpec(), eventId: "start-frame-error" });
  assert.equal(failed.status, "paused");
  assert.equal(failed.pausedReason, "portal frame unavailable");
});

test("prefers a registered list frame when the portal exposes multiple frames", async () => {
  const chromeApi = chromeMock([PAGE_1]);
  chromeApi.storage.session.state["portal-frame-registrations:v1"] = [
    { tabId: 7, frameId: 3, role: "buttons", generation: 2 },
    { tabId: 7, frameId: 4, role: "list", generation: 2 },
  ];
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  await controller.start({ spec: runSpec(), eventId: "start-registered-list-frame" });

  const firstSnapshotCall = chromeApi.calls.find(([, message]) => message.type === "PORTAL_GET_SNAPSHOT");
  assert.equal(firstSnapshotCall[2].frameId, 4);
  assert.equal(controller.status().frame.frameId, 4);
});

test("selects the registered list frame from the requested Area Restrita source scope", async () => {
  const sectorPage = { ...PAGE_1, identities: [], actions: [], source_scope: "sector_finalistic" };
  const myProcessesPage = { ...PAGE_1, identities: [], actions: [], source_scope: "my_processes" };
  const chromeApi = chromeMock([sectorPage]);
  chromeApi.storage.session.state["portal-frame-registrations:v1"] = [
    { tabId: 7, frameId: 4, role: "list", source_scope: "sector_finalistic", observedAt: 200 },
    { tabId: 7, frameId: 6, role: "list", source_scope: "my_processes", observedAt: 100 },
  ];
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (message.type === "PORTAL_GET_SNAPSHOT") {
      const frameId = options?.frameId;
      const payload = frameId === 6 ? myProcessesPage : sectorPage;
      chromeApi.calls.push([tabId, message, options]);
      return { ok: true, frameId, payload: structuredClone(payload) };
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const started = await controller.start({
    spec: { ...runSpec(), sourceScope: "my_processes" },
    eventId: "start-source-scoped-frame",
  });

  const firstSnapshotCall = chromeApi.calls.find(([, message]) => message.type === "PORTAL_GET_SNAPSHOT");
  assert.equal(firstSnapshotCall[2].frameId, 6);
  assert.equal(started.sourceScope, "my_processes");
  assert.notEqual(started.status, "paused");
  assert.equal(started.pausedReason ?? null, null);
});

test("probes an unknown registered frame before declaring the scoped list unavailable", async () => {
  const sectorPage = { ...PAGE_1, identities: [], actions: [], source_scope: "sector_finalistic" };
  const chromeApi = chromeMock([sectorPage]);
  chromeApi.storage.session.state["portal-frame-registrations:v1"] = [
    { tabId: 7, frameId: 4, role: "unknown", source_scope: "sector_finalistic", observedAt: 200 },
    { tabId: 7, frameId: 5, role: "form", source_scope: null, observedAt: 100 },
  ];
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const started = await controller.start({
    spec: { ...runSpec(), sourceScope: "sector_finalistic" },
    eventId: "start-unknown-scoped-frame",
  });

  const firstSnapshotCall = chromeApi.calls.find(([, message]) => message.type === "PORTAL_GET_SNAPSHOT");
  assert.equal(firstSnapshotCall[2].frameId, 4);
  assert.notEqual(started.status, "paused");
  assert.equal(started.pausedReason ?? null, null);
  assert.equal(controller.status().frame.frameId, 4);
});

test("does not restore a sole registered frame from the wrong Area Restrita source", async () => {
  const sectorPage = { ...PAGE_1, identities: [], actions: [], source_scope: "sector_finalistic" };
  const chromeApi = chromeMock([sectorPage]);
  chromeApi.storage.session.state["portal-frame-registrations:v1"] = [
    { tabId: 7, frameId: 4, role: "list", source_scope: "sector_finalistic", observedAt: 200 },
  ];
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  const started = await controller.start({
    spec: { ...runSpec(), sourceScope: "my_processes" },
    eventId: "start-wrong-restored-frame",
  });

  const firstSnapshotCall = chromeApi.calls.find(([, message]) => message.type === "PORTAL_GET_SNAPSHOT");
  assert.equal(firstSnapshotCall[2]?.frameId ?? null, null);
  assert.equal(started.status, "paused");
  assert.match(started.pausedReason, /origem selecionada/iu);
});

test("allows the selected source scope to continue into an unscoped interested frame", async () => {
  const target = identity("103401/2023", "ana da silva", "act-1");
  const activePage = {
    ...snapshot("list", 1, [target], [
      { action: "open_act", enabled: true, identity: target },
    ]),
    source_scope: "sector_finalistic",
  };
  const interestedPage = {
    ...snapshot("interested", 2, [target], [
      { action: "select_interested", enabled: true, identity: target },
    ]),
    source_scope: null,
  };
  const chromeApi = activeChromeMock(activePage);
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  await controller.start({
    spec: { ...runSpec(), sourceScope: "sector_finalistic" },
    eventId: "start-interested-unscoped",
  });
  const result = await controller.handlePortalEvent({
    tabId: 7,
    frameId: 5,
    type: "snapshot",
    snapshot: interestedPage,
  });

  assert.notEqual(result.status, "paused");
  assert.equal(result.sourceScope, "sector_finalistic");
});

test("trusts the explicitly targeted frame when Chrome omits a response frame echo", async () => {
  const chromeApi = chromeMock([PAGE_1]);
  chromeApi.storage.session.state["portal-frame-registrations:v1"] = [
    { tabId: 7, frameId: 4, role: "list", generation: 2 },
  ];
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    const response = await originalSendMessage(tabId, message, options);
    if (message.type !== "PORTAL_GET_SNAPSHOT") return response;
    const { frameId: _frameId, ...withoutFrameEcho } = response;
    return withoutFrameEcho;
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });

  await controller.start({ spec: runSpec(), eventId: "start-registered-list-no-echo" });

  const snapshotCalls = chromeApi.calls.filter(([, message]) => message.type === "PORTAL_GET_SNAPSHOT");
  assert.equal(snapshotCalls.length, 1);
  assert.equal(snapshotCalls[0][2].frameId, 4);
  assert.equal(controller.status().frame.frameId, 4);
});

test("persists a pause when the initial portal snapshot is not a process list", async () => {
  const bridge = bridgeMock();
  const chromeApi = chromeMock([snapshot("unknown", 1)]);
  const controller = createAutomationController({ chromeApi, bridge });

  const result = await controller.start({ spec: runSpec(), eventId: "start-non-list" });

  assert.equal(result.status, "paused");
  assert.equal(result.pausedReason, "manual navigation required: process list not visible");
  assert.equal(bridge.calls.some(([name]) => name === "pause"), true);
});

test("pauses and persists when an active run receives an unrecognized portal screen", async () => {
  const bridge = bridgeMock();
  const target = identity("103401/2023", "ana da silva", "act-1");
  const activePage = snapshot("list", 1, [target], [
    { action: "open_act", enabled: true, identity: target },
  ]);
  const chromeApi = activeChromeMock(activePage);
  const controller = createAutomationController({ chromeApi, bridge });

  const started = await controller.start({ spec: runSpec(), eventId: "start-expired-screen" });
  assert.equal(started.status, "running");

  const result = await controller.handlePortalEvent({
    tabId: 7,
    frameId: 0,
    type: "snapshot",
    snapshot: snapshot("unknown", 2),
  });

  assert.equal(result.status, "paused");
  assert.equal(result.pausedReason, "portal screen not recognized; manual intervention required");
  assert.equal(bridge.calls.some(([name, runId, body]) => name === "pause"
    && runId === "run-1"
    && body?.action === "pause"), true);
});

test("pauses and persists an unrecognized portal screen while discovering", async () => {
  const bridge = bridgeMock();
  const target = identity("103401/2023", "ana da silva", "act-1");
  const activePage = snapshot("list", 1, [target], [
    { action: "open_act", enabled: true, identity: target },
  ]);
  const chromeApi = activeChromeMock(activePage);
  const originalSendMessage = chromeApi.tabs.sendMessage.bind(chromeApi.tabs);
  let releaseInitialSnapshot;
  const initialSnapshotGate = new Promise((resolve) => {
    releaseInitialSnapshot = resolve;
  });
  let initialSnapshotEnteredResolve;
  const initialSnapshotEntered = new Promise((resolve) => {
    initialSnapshotEnteredResolve = resolve;
  });
  let blockInitialSnapshot = true;
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    if (blockInitialSnapshot && message.type === "PORTAL_GET_SNAPSHOT") {
      blockInitialSnapshot = false;
      initialSnapshotEnteredResolve();
      await initialSnapshotGate;
    }
    return originalSendMessage(tabId, message, options);
  };
  const controller = createAutomationController({ chromeApi, bridge });

  const starting = controller.start({ spec: runSpec(), eventId: "start-discovering-unknown-screen" });
  await initialSnapshotEntered;
  assert.equal(controller.status().status, "discovering");

  const result = await controller.handlePortalEvent({
    tabId: 7,
    frameId: 0,
    type: "snapshot",
    snapshot: snapshot("unknown", 2),
  });

  assert.equal(result.status, "paused");
  assert.equal(result.pausedReason, "portal screen not recognized; manual intervention required");
  assert.equal(bridge.calls.some(([name, runId, body]) => name === "pause"
    && runId === "run-1"
    && body?.action === "pause"), true);

  releaseInitialSnapshot();
  const finished = await starting;
  assert.equal(finished.status, "paused");
  assert.equal(finished.pausedReason, "portal screen not recognized; manual intervention required");
});

test("does not replace a bound frame when another frame reports a snapshot", async () => {
  const activePage = snapshot("list", 1, [identity("103401/2023", "ana da silva", "act-1")], [
    { action: "open_act", enabled: true, identity: identity("103401/2023", "ana da silva", "act-1") },
  ]);
  const chromeApi = activeChromeMock(activePage);
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });
  await controller.start({ spec: runSpec(), eventId: "start-frame-bound" });
  await controller.handlePortalEvent({ tabId: 7, frameId: 9, type: "snapshot", snapshot: { ...activePage, generation: 2 } });
  assert.equal(controller.status().frame.frameId, 0);
  assert.equal(controller.status().status, "running");
});

test("accepts the restricted portal's newly created interested/form frame after opening an act", async () => {
  const target = identity("103401/2023", "ana da silva", "act-1");
  const chromeApi = activeChromeMock(snapshot("list", 1, [target], [
    { action: "open_act", enabled: true, identity: target },
  ]));
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });
  await controller.start({ spec: runSpec(), eventId: "start-new-form-frame" });

  await controller.handlePortalEvent({
    tabId: 7,
    frameId: 5,
    type: "snapshot",
    snapshot: snapshot("interested", 2, [{ ...target, selected: false }], [
      { action: "select_interested", enabled: true, identity: { ...target, selected: false } },
    ]),
  });

  assert.equal(controller.status().frame.frameId, 5);
  assert.equal(controller.status().frame.role, "interested");
});

test("replays a newly created interested frame that arrives during open-act navigation", async () => {
  const target = identity("103401/2023", "ana da silva", "act-1");
  const interested = snapshot("interested", 2, [{ ...target, selected: false }], [
    { action: "select_interested", enabled: true, identity: { ...target, selected: false } },
  ]);
  const calls = [];
  let releaseOpen;
  let openEnteredResolve;
  const openEntered = new Promise((resolve) => { openEnteredResolve = resolve; });
  const openGate = new Promise((resolve) => { releaseOpen = resolve; });
  const chromeApi = {
    calls,
    storage: { session: { async get() { return {}; }, async set() {} } },
    tabs: {
      async sendMessage(tabId, message, options) {
        calls.push([tabId, message, options]);
        const frameId = Number.isSafeInteger(options?.frameId) ? options.frameId : 0;
        if (message.type === "PORTAL_GET_SNAPSHOT") {
          return { ok: true, frameId, payload: snapshot("list", 1, [target], [
            { action: "open_act", enabled: true, identity: target },
          ]) };
        }
        if (message.type === "PORTAL_NAVIGATE") {
          if (message.payload.action === "open_act") {
            openEnteredResolve();
            await openGate;
          }
          return { ok: true, frameId, navigationToken: message.requestId, payload: {} };
        }
        return { ok: true, payload: {} };
      },
      onRemoved: { addListener() {} },
      onUpdated: { addListener() {} },
    },
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });
  const starting = controller.start({ ...runSpec(), lotSize: 1 }, "start-interested-race");
  await openEntered;

  const received = controller.handlePortalEvent({
    tabId: 7,
    frameId: 5,
    type: "snapshot",
    snapshot: interested,
  });
  const staleList = controller.handlePortalEvent({
    tabId: 7,
    frameId: 0,
    type: "snapshot",
    snapshot: snapshot("list", 1, [target], [
      { action: "open_act", enabled: true, identity: target },
    ]),
  });
  releaseOpen();
  await starting;
  await received;
  await staleList;

  assert.equal(controller.status().status, "running");
  assert.equal(controller.status().currentIdentity.processKey, target.processKey);
  assert.equal(controller.status().frame.frameId, 5);
  assert.equal(controller.status().frame.role, "interested");
  assert.equal(calls.some(([, message]) => message.type === "PORTAL_NAVIGATE"
    && message.payload.action === "select_interested"), true);
});

test("rehydrated pilot recovers its sole queued identity from an interested snapshot", async () => {
  const target = identity("103401/2023", "ana da silva", null);
  const calls = [];
  const chromeApi = {
    calls,
    storage: { session: { async get() { return {}; }, async set() {} } },
    tabs: {
      async sendMessage(tabId, message, options) {
        calls.push([tabId, message, options]);
        return { ok: true, payload: {} };
      },
      onRemoved: { addListener() {} },
      onUpdated: { addListener() {} },
    },
  };
  const controller = createAutomationController({ chromeApi, bridge: bridgeMock() });
  await controller.rehydrate({
    api_version: 1,
    run_id: "run-rehydrated-interested",
    revision: 3,
    status: "running",
    items: [{
      item_id: target.processKey,
      ordinal: 1,
      identity: target,
      state: "queued",
    }],
    last_confirmed_item_id: null,
  }, {
    ...runSpec(),
    mode: "pilot",
    pilotIdentity: target,
    sourceScope: "sector_finalistic",
  });

  await controller.handlePortalEvent({
    tabId: 7,
    frameId: 5,
    type: "snapshot",
    snapshot: {
      ...snapshot("interested", 2, [{ ...target, selected: false }], [
        { action: "select_interested", enabled: true, identity: { ...target, selected: false } },
      ]),
      source_scope: null,
    },
  });

  assert.deepEqual(controller.status().currentIdentity, target);
  assert.equal(calls.some(([, message]) => message.type === "PORTAL_NAVIGATE"
    && message.payload.action === "select_interested"), true);
});

test("controller owns navigation loop and exposes pause/resume/stop/status without panel participation", async () => {
  const bridge = bridgeMock();
  const chromeApi = chromeMock([PAGE_1, PAGE_2, PAGE_3]);
  const controller = createAutomationController({ chromeApi, bridge, ranker: () => ({ kind: "exact" }) });
  await controller.start({ spec: runSpec(), eventId: "start-3" });
  const paused = await controller.pause({ eventId: "pause-3" });
  assert.equal(paused.status, "paused");
  const resumed = await controller.resume({ eventId: "resume-3" });
  assert.equal(resumed.status, "running");
  const status = await controller.status({ refresh: true });
  assert.equal(status.runId, "run-1");
  const stopped = await controller.stop({ eventId: "stop-3" });
  assert.equal(stopped.status, "stopped");
  assert.deepEqual(bridge.calls.map(([name]) => name).filter((name) => ["pause", "resume", "stop"].includes(name)), ["pause", "resume", "stop"]);
});

const PREP_IDENTITY = identity("103439/2023", "ana da silva", "act-prep");
const PREP_VALUES = {
  modalidade: "m-special",
  fundamento_legal: "f-professor",
  data_publicacao_doe: "07/02/2020",
  cargo: "Professor",
  matricula: "103.870-2/1",
  data_nascimento: "30/04/1967",
  genero: "Feminino",
};
const PREP_FIELDS = Object.keys(PREP_VALUES);

function preparationRecord() {
  return {
    dataset_sha256: HASH,
    process: { key: PREP_IDENTITY.processKey, number: "103439", year: "2023" },
    interested: { original: "Ana da Silva", normalized: PREP_IDENTITY.interestedNormalized },
    status: "ready",
    fields: Object.fromEntries(PREP_FIELDS.map((field) => [field, {
      status: "found",
      confidence: "high",
      source_value: PREP_VALUES[field],
      form_value: PREP_VALUES[field],
      citation: null,
    }])),
  };
}

function preparationContext() {
  return {
    schema_version: 1,
    dataset_sha256: HASH,
    process_key: PREP_IDENTITY.processKey,
    interested_normalized: PREP_IDENTITY.interestedNormalized,
    resolution_status: "complete",
    operative_text: "RESOLVE: Art. 3º, incisos I a III e parágrafo único, da EC nº 47/2005.",
    pages: [],
    context_revision: 12,
    rules_version: "legal-foundation-v1",
  };
}

function preparationLegalDecision() {
  return resolveLegalFoundation({
    context: preparationContext(),
    options: preparationFormSnapshot().options.fundamento_legal,
  });
}

function preparationFormSnapshot(fields = {}) {
  return {
    process: { number: "103439", year: "2023", key: PREP_IDENTITY.processKey },
    interested: { original: "Ana da Silva", normalized: PREP_IDENTITY.interestedNormalized },
    options: {
      modalidade: [{ value: PREP_VALUES.modalidade, label: "Especial" }],
      fundamento_legal: [{
        value: PREP_VALUES.fundamento_legal,
        label: "Civil - Artigo 3º, incisos I a III e parágrafo único, da Emenda Constitucional nº 47/2005",
      }],
      genero: [{ value: PREP_VALUES.genero, label: "Feminino" }],
    },
    fields: Object.fromEntries(PREP_FIELDS.map((field) => [field, {
      value: fields[field] ?? "",
      disabled: false,
      readOnly: false,
    }])),
  };
}

function preparationPortalSnapshots(sourceScope = null) {
  const scoped = (entry) => ({ ...entry, source_scope: sourceScope });
  return {
    list: scoped(snapshot("list", 1, [PREP_IDENTITY], [{ action: "open_act", enabled: true, identity: PREP_IDENTITY }])),
    interested: scoped(snapshot("interested", 2, [{ ...PREP_IDENTITY, selected: false }], [{ action: "select_interested", enabled: true, identity: PREP_IDENTITY }])),
    form: scoped(snapshot("form", 3, [], [{ action: "return_list", enabled: true, identity: PREP_IDENTITY }])),
    returned: scoped(snapshot("list", 4, [PREP_IDENTITY], [])),
  };
}

function preparationChromeMock({ initialFields = {}, afterApplyFields = null, afterApplyPortal = null, submitResponse = null, sourceScope = null, startAt = "list", staleGenerationOnce = [], staleGenerationAlways = false } = {}) {
  const calls = [];
  const removedListeners = [];
  const updatedListeners = [];
  const pages = preparationPortalSnapshots(sourceScope);
  let current = pages[startAt];
  let formFields = { ...initialFields };
  const staleReported = new Set();
  return {
    calls,
    storage: { session: { async get() { return {}; }, async set() {} } },
    tabs: {
      async sendMessage(tabId, message, options) {
        calls.push([tabId, message, options]);
        const frameId = Number.isSafeInteger(options?.frameId) ? options.frameId : 0;
        if (message.type === MESSAGE_TYPES.PORTAL_GET_SNAPSHOT) {
          return { ok: true, frameId, payload: structuredClone(current) };
        }
        if (message.type === MESSAGE_TYPES.PORTAL_NAVIGATE) {
          const staleOnce = staleGenerationOnce.includes(message.payload.action) && !staleReported.has(message.payload.action);
          if (staleGenerationAlways || staleOnce) {
            // The restricted act screen repaints itself right after boot (body
            // onload plus the jQuery fadeOut animation), so the navigation gate
            // rejects anything sent with the generation observed before that
            // repaint and reports the generation the frame is actually on.
            if (staleOnce) staleReported.add(message.payload.action);
            return {
              ok: false,
              error: { code: "STALE_GENERATION", message: "portal screen generation changed before navigation" },
              generation: current.generation + 1,
            };
          }
          if (message.payload.action === "open_act") current = pages.interested;
          if (message.payload.action === "select_interested") current = pages.form;
          if (message.payload.action === "return_list") current = pages.returned;
          return {
            ok: true,
            frameId,
            navigationToken: message.requestId,
            payload: { snapshot: structuredClone(current) },
          };
        }
        if (message.type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) {
          return { ok: true, frameId, payload: preparationFormSnapshot(formFields) };
        }
        if (message.type === MESSAGE_TYPES.APPLY_FIELDS) {
          formFields = afterApplyFields ? { ...afterApplyFields } : { ...formFields, ...message.payload.fields };
          // The restricted portal mutates the act screen on its own after the
          // first observation (body onload plus a jQuery fadeOut animation),
          // so the post-apply snapshot must be configurable per test.
          if (afterApplyPortal) current = { ...current, ...afterApplyPortal };
          return {
            ok: true,
            frameId,
            payload: {
              changed: Object.keys(message.payload.fields),
              preserved: [],
              missing: [],
              disabled: [],
              errors: [],
            },
          };
        }
        if (message.type === MESSAGE_TYPES.AUTO_SUBMIT_COMMAND) {
          return submitResponse ?? { ok: true, payload: { status: "confirmed", evidence: { signal: "fixture-accepted" } } };
        }
        return { ok: true, frameId, payload: {} };
      },
      onRemoved: { addListener(listener) { removedListeners.push(listener); } },
      onUpdated: { addListener(listener) { updatedListeners.push(listener); } },
    },
    fireTabRemoved(tabId) { removedListeners.forEach((listener) => listener(tabId)); },
    fireTabUpdated(tabId, changeInfo) { updatedListeners.forEach((listener) => listener(tabId, changeInfo)); },
  };
}

function preparationBridge({ failEventType = null } = {}) {
  const bridge = bridgeMock();
  let revision = 1;
  bridge.appendAutomationEvent = async (runId, event) => {
    validateAutomationEvent(event);
    bridge.calls.push(["event", runId, structuredClone(event)]);
    if (event.type === failEventType) throw new Error("event persistence unavailable");
    revision += 1;
    return {
      api_version: 1,
      run_id: runId,
      revision,
      status: "running",
      items: [],
      last_confirmed_item_id: null,
    };
  };
  return bridge;
}

function preparationResolverCalls(calls, overrides = {}) {
  return async (resolvedIdentity, formSnapshot, portalSnapshot) => {
    calls.push({ resolvedIdentity, formSnapshot, portalSnapshot });
    return {
      record: preparationRecord(),
      context: preparationContext(),
      legalDecision: preparationLegalDecision(),
      matchKinds: Object.fromEntries(PREP_FIELDS.map((field) => [field, "exact"])),
      ...overrides,
    };
  };
}

test("no-send pilot persists a review pause and leaves the verified form open", async () => {
  const chromeApi = preparationChromeMock();
  const bridge = preparationBridge();
  const controller = createAutomationController({ chromeApi, bridge, resolveAutomaticAct: preparationResolverCalls([]) });
  const spec = { ...runSpec(), mode: "pilot", pilotIdentity: PREP_IDENTITY, autoSubmit: false };
  const result = await controller.start({ spec, eventId: "review-pilot" });
  assert.equal(result.status, "paused");
  assert.equal(result.pausedReason, "pilot prepared; review the fields before continuing");
  assert.deepEqual(persistedEventTypes(bridge), ["item_prepared", "fields_verified"]);
  assert.equal(bridge.calls.filter(([name]) => name === "pause").length, 1);
  assert.equal(chromeApi.calls.some(([, message]) => message.payload?.action === "return_list"), false);
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO), false);
  const writes = chromeApi.calls.filter(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS);
  assert.equal(writes.length, 1);
  await controller.handlePortalEvent({ tabId: 7, frameId: 0, type: "screen_changed", snapshot: preparationPortalSnapshots().form });
  assert.equal(chromeApi.calls.filter(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS).length, 1);
});

test("prepares and verifies the discovered form through typed APPLY_FIELDS without sending", async () => {
  const resolverCalls = [];
  const bridge = preparationBridge();
  const chromeApi = preparationChromeMock();
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls(resolverCalls),
  });

  const result = await controller.start({ spec: runSpec(), eventId: "start-preparation" });

  const applyCalls = chromeApi.calls.filter(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS);
  assert.equal(result.status, "completed");
  assert.equal(resolverCalls.length, 1);
  assert.deepEqual(resolverCalls[0].resolvedIdentity, PREP_IDENTITY);
  assert.equal(resolverCalls[0].formSnapshot.identity.processKey, PREP_IDENTITY.processKey);
  assert.equal(resolverCalls[0].formSnapshot.frameId, 0);
  assert.equal(resolverCalls[0].formSnapshot.generation, 3);
  assert.equal(applyCalls.length, 1);
  assert.deepEqual(Object.keys(applyCalls[0][1].payload.fields), PREP_FIELDS);
  assert.deepEqual(applyCalls[0][1].payload.matchKinds, Object.fromEntries(PREP_FIELDS.map((field) => [field, "exact"])));
  assert.deepEqual(bridge.calls.filter(([name]) => name === "event").map(([, , event]) => event.type), [
    "item_prepared",
    "fields_verified",
  ]);
  const preparedEvent = bridge.calls.find(([name, , event]) => name === "event" && event.type === "item_prepared")[2];
  assert.equal(preparedEvent.itemId, PREP_IDENTITY.portalActId);
  assert.deepEqual(preparedEvent.payload.identity, PREP_IDENTITY);
  assert.deepEqual(preparedEvent.payload.frame, { generation: 3, frameId: 0 });
  assert.equal(preparedEvent.payload.dataset_sha256, HASH);
  assert.match(preparedEvent.payload.context_hash, /^[0-9a-f]{64}$/u);
  assert.deepEqual(preparedEvent.payload.matchKinds, Object.fromEntries(PREP_FIELDS.map((field) => [field, "exact"])));
  assert.equal(Object.keys(preparedEvent.payload.before).length, PREP_FIELDS.length);
  assert.equal(Object.keys(preparedEvent.payload.after).length, PREP_FIELDS.length);
  assert.equal(JSON.stringify(preparedEvent.payload).includes(PREP_VALUES.cargo), false);
  const verifiedEvent = bridge.calls.find(([name, , event]) => name === "event" && event.type === "fields_verified")[2];
  assert.equal(Object.hasOwn(verifiedEvent.payload.fieldResults.cargo, "expected"), false);
  assert.equal(Object.hasOwn(verifiedEvent.payload.fieldResults.cargo, "actual"), false);
  assert.match(verifiedEvent.payload.fieldResults.cargo.expectedHash, /^[0-9a-f]{64}$/u);
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO), false);
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.OVERRIDE_FIELD), false);
});

test("retries the act navigation once when the portal reports a newer screen generation", async () => {
  const bridge = preparationBridge();
  const chromeApi = preparationChromeMock({ staleGenerationOnce: ["select_interested"] });
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
  });

  const result = await controller.start({ spec: runSpec(), eventId: "start-stale-act-generation" });

  const selects = chromeApi.calls.filter(([, message]) => message.type === MESSAGE_TYPES.PORTAL_NAVIGATE
    && message.payload.action === "select_interested");
  assert.equal(result.status, "completed");
  assert.equal(result.pausedReason ?? null, null);
  assert.equal(selects.length, 2);
  assert.equal(selects[0][1].payload.expected_generation, 2);
  // The retry keeps the action and the canonical identity and only carries the
  // generation the navigation gate reported, so every identity and value gate
  // still runs against the current screen.
  assert.equal(selects[1][1].payload.expected_generation, 3);
  assert.deepEqual(selects[1][1].payload.identity, PREP_IDENTITY);
  assert.deepEqual(bridge.calls.filter(([name]) => name === "event").map(([, , event]) => event.type), [
    "item_prepared",
    "fields_verified",
  ]);
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO), false);
});

test("pauses instead of retrying forever when the portal keeps reporting newer generations", async () => {
  const bridge = preparationBridge();
  const chromeApi = preparationChromeMock({ staleGenerationAlways: true });
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
  });

  const result = await controller.start({ spec: runSpec(), eventId: "start-stale-act-loop" });

  const navigations = chromeApi.calls.filter(([, message]) => message.type === MESSAGE_TYPES.PORTAL_NAVIGATE);
  assert.equal(result.status, "paused");
  assert.equal(navigations.length, 2);
  assert.equal(result.pausedReason, "portal screen changed under the run; manual intervention required");
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS), false);
});

async function rehydratedActPilot({ sourceScope = "sector_finalistic", startAt = "form" } = {}) {
  const resolverCalls = [];
  const bridge = preparationBridge();
  const chromeApi = preparationChromeMock({ sourceScope, startAt });
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls(resolverCalls),
  });
  await controller.rehydrate({
    api_version: 1,
    run_id: "run-rehydrated-act",
    revision: 4,
    status: "running",
    items: [{
      item_id: PREP_IDENTITY.processKey,
      ordinal: 1,
      identity: PREP_IDENTITY,
      state: "queued",
    }],
    last_confirmed_item_id: null,
  }, {
    ...runSpec(),
    mode: "pilot",
    pilotIdentity: PREP_IDENTITY,
    sourceScope,
  });
  return { controller, chromeApi, bridge, resolverCalls };
}

function persistedEventTypes(bridge) {
  return bridge.calls.filter(([name]) => name === "event").map(([, , event]) => event.type);
}

test("rehydrated running pilot resumes its queued identity from the act form snapshot and prepares it without sending", async () => {
  const sourceScope = "sector_finalistic";
  const { controller, chromeApi, bridge, resolverCalls } = await rehydratedActPilot();

  await controller.handlePortalEvent({
    tabId: 7,
    frameId: 21,
    type: "snapshot",
    snapshot: preparationPortalSnapshots(sourceScope).form,
  });

  const applyCalls = chromeApi.calls.filter(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS);
  assert.equal(resolverCalls.length, 1);
  assert.deepEqual(resolverCalls[0].resolvedIdentity, PREP_IDENTITY);
  assert.equal(resolverCalls[0].formSnapshot.identity.processKey, PREP_IDENTITY.processKey);
  assert.equal(resolverCalls[0].formSnapshot.frameId, 21);
  assert.equal(applyCalls.length, 1);
  assert.deepEqual(Object.keys(applyCalls[0][1].payload.fields), PREP_FIELDS);
  assert.deepEqual(persistedEventTypes(bridge), ["item_prepared", "fields_verified"]);
  assert.equal(controller.status().status, "paused");
  assert.equal(controller.status().pausedReason, "pilot prepared; review the fields before continuing");
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO), false);
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.AUTO_SUBMIT_COMMAND), false);
});

test("rehydrated pilot stays parked when the act form snapshot carries a diverging identity", async () => {
  const sourceScope = "sector_finalistic";
  const { controller, chromeApi, bridge, resolverCalls } = await rehydratedActPilot();

  await controller.handlePortalEvent({
    tabId: 7,
    frameId: 21,
    type: "snapshot",
    snapshot: {
      ...snapshot("form", 3, [], [{
        action: "return_list",
        enabled: true,
        identity: identity("103440/2023", "bruno de souza", "act-other"),
      }]),
      source_scope: sourceScope,
    },
  });

  assert.equal(controller.status().status, "running");
  assert.equal(controller.status().currentIdentity, null);
  assert.equal(resolverCalls.length, 0);
  assert.deepEqual(persistedEventTypes(bridge), []);
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS), false);
});

test("rehydrated pilot does not invent an identity from a generic return_list act snapshot", async () => {
  const sourceScope = "sector_finalistic";
  const { controller, chromeApi, bridge, resolverCalls } = await rehydratedActPilot();

  await controller.handlePortalEvent({
    tabId: 7,
    frameId: 21,
    type: "snapshot",
    snapshot: {
      ...snapshot("form", 3, [], [{ action: "return_list", enabled: true }]),
      source_scope: sourceScope,
    },
  });

  assert.equal(controller.status().status, "running");
  assert.equal(controller.status().currentIdentity, null);
  assert.equal(resolverCalls.length, 0);
  assert.deepEqual(persistedEventTypes(bridge), []);
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS), false);
});

test("fails closed when the integrated resolver cannot persist automation events", async () => {
  const bridge = bridgeMock();
  const chromeApi = preparationChromeMock();
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
  });

  const result = await controller.start({ spec: runSpec(), eventId: "start-no-event-append" });

  assert.equal(result.status, "paused");
  assert.match(result.pausedReason, /event persistence/u);
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS), false);
});

test("blocks a tied modalidade match before issuing APPLY_FIELDS", async () => {
  const bridge = preparationBridge();
  const chromeApi = preparationChromeMock();
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([], {
      matchedValues: {
        modalidade: PREP_VALUES.modalidade,
        fundamento_legal: PREP_VALUES.fundamento_legal,
      },
      matchKinds: {
        ...Object.fromEntries(PREP_FIELDS.map((field) => [field, "exact"])),
        modalidade: "tie",
      },
    }),
  });

  await controller.start({ spec: runSpec(), eventId: "start-modalidade-tie" });

  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS), false);
  const pendingEvent = bridge.calls.find(([name, , event]) => name === "event" && event.type === "item_pending");
  assert.ok(pendingEvent);
  assert.equal(pendingEvent[2].payload.reason, "SELECT_MATCH_TIE");
});

test("rejects a post-apply catalog or field-state change across all seven fields", async () => {
  const bridge = preparationBridge();
  const chromeApi = preparationChromeMock();
  const originalSendMessage = chromeApi.tabs.sendMessage;
  let formReads = 0;
  chromeApi.tabs.sendMessage = async (tabId, message, options) => {
    const response = await originalSendMessage(tabId, message, options);
    if (message.type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) {
      formReads += 1;
      if (formReads === 2) {
        response.payload.options.modalidade = [
          ...response.payload.options.modalidade,
          { value: "m-new", label: "New catalog option" },
        ];
        response.payload.fields.genero.disabled = true;
      }
    }
    return response;
  };
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
  });

  await controller.start({ spec: runSpec(), eventId: "start-catalog-drift" });

  assert.deepEqual(bridge.calls.filter(([name]) => name === "event").map(([, , event]) => event.type), [
    "item_prepared",
    "item_failed",
  ]);
  assert.match(bridge.calls.at(-1)[2].payload.error, /catalog|state|option|field/u);
});

test("verifies the prepared act when the portal mutates its own act screen between the snapshot and the reread", async () => {
  const bridge = preparationBridge();
  const chromeApi = preparationChromeMock({ afterApplyPortal: { generation: 9 } });
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
  });

  const result = await controller.start({ spec: runSpec(), eventId: "start-portal-self-mutation" });

  assert.deepEqual(persistedEventTypes(bridge), ["item_prepared", "fields_verified"]);
  assert.equal(result.status, "completed");
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO), false);
  const verifiedEvent = bridge.calls.find(([name, , event]) => name === "event" && event.type === "fields_verified")[2];
  assert.equal(verifiedEvent.payload.rereads[0].generation, 9);
});

test("fails the prepared act when the portal leaves the act screen during preparation", async () => {
  const bridge = preparationBridge();
  const chromeApi = preparationChromeMock({ afterApplyPortal: { role: "list", generation: 12 } });
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
  });

  await controller.start({ spec: runSpec(), eventId: "start-surface-drift" });

  assert.equal(chromeApi.calls.filter(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS).length, 1);
  assert.deepEqual(persistedEventTypes(bridge), ["item_prepared", "item_failed"]);
  assert.equal(bridge.calls.at(-1)[2].payload.error, "portal surface changed during preparation");
  assert.equal(bridge.calls.at(-1)[2].payload.reason, "fields verification failed");
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO), false);
});

test("does not partially write when the preflight snapshot contains a divergent field", async () => {
  const bridge = preparationBridge();
  const chromeApi = preparationChromeMock({ initialFields: { cargo: "Analista" } });
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
  });

  await controller.start({ spec: runSpec(), eventId: "start-divergence" });

  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS), false);
  assert.deepEqual(bridge.calls.filter(([name]) => name === "event").map(([, , event]) => event.type), ["item_pending"]);
  assert.match(bridge.calls.find(([name]) => name === "event")[2].payload.reason, /EXISTING_VALUE_CONFLICT/u);
});

test("fails the item when the post-apply reread does not match every proposed value", async () => {
  const bridge = preparationBridge();
  const chromeApi = preparationChromeMock({ afterApplyFields: { ...PREP_VALUES, cargo: "Unexpected" } });
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
  });

  await controller.start({ spec: runSpec(), eventId: "start-reread-mismatch" });

  assert.equal(chromeApi.calls.filter(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS).length, 1);
  assert.deepEqual(bridge.calls.filter(([name]) => name === "event").map(([, , event]) => event.type), [
    "item_prepared",
    "item_failed",
  ]);
  assert.match(bridge.calls.at(-1)[2].payload.error, /reread|mismatch/u);
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO), false);
});

test("fails closed before any field write when item_prepared persistence fails", async () => {
  const bridge = preparationBridge({ failEventType: "item_prepared" });
  const chromeApi = preparationChromeMock();
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
  });

  const result = await controller.start({ spec: runSpec(), eventId: "start-event-failure" });

  assert.equal(result.status, "paused");
  assert.equal(chromeApi.calls.some(([, message]) => message.type === MESSAGE_TYPES.APPLY_FIELDS), false);
  assert.equal(bridge.calls.filter(([name]) => name === "event").length, 1);
});

test("auto-submit is explicit, issues one command after verification, and persists the confirmed outcome", async () => {
  const bridge = preparationBridge();
  bridge.getAutomationCapabilities = async () => ({
    api_version: 1,
    automation_schema: 1,
    legal_context_schema: 1,
    rules_version: "legal-foundation-v1",
    real_send_enabled: true,
    pilot_enabled: false,
    pilot_consumes_remaining: false,
  });
  const chromeApi = preparationChromeMock({
    submitResponse: {
      ok: true,
      payload: {
        status: "confirmed",
        evidence: { signal: "fixture-accepted", read: "post-read" },
      },
    },
  });
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
    clock: { now: () => 2_000 },
  });

  const result = await controller.start({ spec: { ...runSpec(), autoSubmit: true }, eventId: "start-auto-submit" });

  assert.equal(result.status, "completed");
  assert.deepEqual(bridge.calls.filter(([name]) => name === "event").map(([, , event]) => event.type), [
    "item_prepared",
    "fields_verified",
    "send_intent",
    "send_confirmed",
  ]);
  const commandCall = chromeApi.calls.find(([, message]) => message.type === MESSAGE_TYPES.AUTO_SUBMIT_COMMAND);
  assert.ok(commandCall);
  assert.equal(commandCall[1].payload.runId, "run-1");
  assert.equal(commandCall[1].payload.command.identity.processKey, PREP_IDENTITY.processKey);
  assert.match(commandCall[1].payload.command.expected_fields_hash, /^[0-9a-f]{64}$/u);
  assert.equal(commandCall[1].payload.command.expires_at - commandCall[1].payload.command.issued_at, 15_000);
  const confirmed = bridge.calls.find(([name, , event]) => name === "event" && event.type === "send_confirmed")[2];
  assert.equal(confirmed.payload.origin, "portal");
  assert.equal(confirmed.payload.evidence, undefined);
  assert.equal(confirmed.payload.citations.length > 0, true);
});

test("auto-submit targets a separately registered buttons frame and keeps the form frame in the command", async () => {
  const bridge = preparationBridge();
  bridge.getAutomationCapabilities = async () => ({
    api_version: 1,
    automation_schema: 1,
    legal_context_schema: 1,
    rules_version: "legal-foundation-v1",
    real_send_enabled: true,
    pilot_enabled: false,
    pilot_consumes_remaining: false,
  });
  const chromeApi = preparationChromeMock({
    submitResponse: {
      ok: true,
      payload: { status: "confirmed", evidence: { signal: "fixture-accepted" } },
    },
  });
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
    clock: { now: () => 2_000 },
  });

  await controller.handleSubmitFrameReady({ tabId: 7, frameId: 4, buttonId: null });
  const result = await controller.start({ spec: { ...runSpec(), autoSubmit: true }, eventId: "start-cross-frame-submit" });

  assert.equal(result.status, "completed");
  const commandCall = chromeApi.calls.find(([, message]) => message.type === MESSAGE_TYPES.AUTO_SUBMIT_COMMAND);
  assert.ok(commandCall);
  assert.equal(commandCall[2].frameId, 4);
  assert.equal(commandCall[1].payload.command.frame_id, 4);
  assert.equal(commandCall[1].payload.command.form_frame_id, 0);
});

test("auto-submit pauses and records an unconfirmed outcome without issuing another command", async () => {
  const bridge = preparationBridge();
  bridge.getAutomationCapabilities = async () => ({
    api_version: 1,
    automation_schema: 1,
    legal_context_schema: 1,
    rules_version: "legal-foundation-v1",
    real_send_enabled: true,
  });
  const chromeApi = preparationChromeMock({
    submitResponse: { ok: true, payload: { status: "unconfirmed", evidence: { reason: "timeout" } } },
  });
  const controller = createAutomationController({
    chromeApi,
    bridge,
    resolveAutomaticAct: preparationResolverCalls([]),
    clock: { now: () => 2_000 },
  });

  const result = await controller.start({ spec: { ...runSpec(), autoSubmit: true }, eventId: "start-auto-timeout" });

  assert.equal(result.status, "paused");
  assert.match(result.pausedReason, /confirm|incerto|resultado/iu);
  assert.equal(bridge.calls.some(([name]) => name === "pause"), true);
  assert.deepEqual(bridge.calls.filter(([name]) => name === "event").map(([, , event]) => event.type), [
    "item_prepared",
    "fields_verified",
    "send_intent",
    "send_unconfirmed",
  ]);
  assert.equal(chromeApi.calls.filter(([, message]) => message.type === MESSAGE_TYPES.AUTO_SUBMIT_COMMAND).length, 1);
});
