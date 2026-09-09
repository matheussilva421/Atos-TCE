import test from "node:test";
import assert from "node:assert/strict";

import { createAutomationController } from "../background/automation-controller.js";

const HASH = "a".repeat(64);

function identity(processKey, interestedNormalized, portalActId = null) {
  return { processKey, interestedNormalized, portalActId };
}

function snapshot(role, generation, identities = [], actions = [], sector = "aposentadorias") {
  return { role, generation, sector, identities, actions };
}

function runSpec() {
  return {
    tabId: 7,
    sector: "aposentadorias",
    datasetSha256: HASH,
    rulesVersion: "legal-foundation-v1",
  };
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
          return { ok: true, payload: structuredClone(snapshots[Math.min(current, snapshots.length - 1)]) };
        }
        if (message.type === "PORTAL_NAVIGATE") {
          current += 1;
          return { ok: true, payload: { snapshot: structuredClone(snapshots[Math.min(current, snapshots.length - 1)]) } };
        }
        return { ok: true, payload: {} };
      },
      onRemoved: { addListener() {} },
    },
  };
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

test("keeps an unresolved identity in totals and pauses when pagination repeats", async () => {
  const unresolved = snapshot("list", 1, [
    { processKey: "103406/2023", interestedOriginal: "", interestedNormalized: "", portalActId: null },
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

test("keeps unresolved identities in totals, pauses on manual/sector changes, and ignores another tab", async () => {
  const bridge = bridgeMock();
  const chromeApi = chromeMock([PAGE_1, PAGE_3]);
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
