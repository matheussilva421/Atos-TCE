import test from "node:test";
import assert from "node:assert/strict";

import { createAutomationController } from "../background/automation-controller.js";
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

test("pauses when a same-tab loading event omits its navigation marker", async () => {
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
  assert.equal(started.status, "paused");
  assert.equal(started.pausedReason, "navigation token/frame mismatch");
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
    operative_text: "RESOLVE: Art. 40, § 5º.",
    pages: [],
    context_revision: 12,
    rules_version: "legal-foundation-v1",
  };
}

function preparationLegalDecision() {
  return {
    status: "selected",
    method: "rule",
    rule_id: "EC41_COM_P5",
    option_value: PREP_VALUES.fundamento_legal,
    option_label: "Regra do professor",
    rules_version: "legal-foundation-v1",
  };
}

function preparationFormSnapshot(fields = {}) {
  return {
    process: { number: "103439", year: "2023", key: PREP_IDENTITY.processKey },
    interested: { original: "Ana da Silva", normalized: PREP_IDENTITY.interestedNormalized },
    options: {
      modalidade: [{ value: PREP_VALUES.modalidade, label: "Especial" }],
      fundamento_legal: [{ value: PREP_VALUES.fundamento_legal, label: "Regra do professor" }],
      genero: [{ value: PREP_VALUES.genero, label: "Feminino" }],
    },
    fields: Object.fromEntries(PREP_FIELDS.map((field) => [field, {
      value: fields[field] ?? "",
      disabled: false,
      readOnly: false,
    }])),
  };
}

function preparationPortalSnapshots() {
  return {
    list: snapshot("list", 1, [PREP_IDENTITY], [{ action: "open_act", enabled: true, identity: PREP_IDENTITY }]),
    interested: snapshot("interested", 2, [{ ...PREP_IDENTITY, selected: false }], [{ action: "select_interested", enabled: true, identity: PREP_IDENTITY }]),
    form: snapshot("form", 3, [], [{ action: "return_list", enabled: true, identity: PREP_IDENTITY }]),
    returned: snapshot("list", 4, [PREP_IDENTITY], []),
  };
}

function preparationChromeMock({ initialFields = {}, afterApplyFields = null, submitResponse = null } = {}) {
  const calls = [];
  const removedListeners = [];
  const updatedListeners = [];
  const pages = preparationPortalSnapshots();
  let current = pages.list;
  let formFields = { ...initialFields };
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

function preparationResolverCalls(calls) {
  return async (resolvedIdentity, formSnapshot, portalSnapshot) => {
    calls.push({ resolvedIdentity, formSnapshot, portalSnapshot });
    return {
      record: preparationRecord(),
      context: preparationContext(),
      legalDecision: preparationLegalDecision(),
      matchKinds: Object.fromEntries(PREP_FIELDS.map((field) => [field, "exact"])),
    };
  };
}

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
