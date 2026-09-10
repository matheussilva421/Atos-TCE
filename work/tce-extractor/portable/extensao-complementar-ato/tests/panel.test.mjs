import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { createServiceWorker } from "../background/service-worker.js";
import { MESSAGE_TYPES, createMessage } from "../lib/messages.js";
import { ALLOWED_ORIGIN, STORAGE_KEYS, computeLogicalSha256 } from "../lib/schema.js";
import { createPanelApp, PANEL_FIELD_ORDER, PANEL_STATES } from "../sidepanel/panel.js";

const ROOT = resolve(import.meta.dirname, "..");
const PERMANENT_WARNING = "Modo manual: preenche para revisão; não envia o ato.";
const PORTAL_URL = `${ALLOWED_ORIGIN}/ComplementarAto`;

class FakeEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.bubbles = init.bubbles === true;
    this.target = null;
  }
}

class FakeClassList {
  #classes = new Set();

  add(...classes) { classes.forEach((name) => this.#classes.add(name)); }
  remove(...classes) { classes.forEach((name) => this.#classes.delete(name)); }
  contains(name) { return this.#classes.has(name); }
}

class FakeElement {
  constructor(tagName, attributes = {}) {
    this.tagName = tagName.toUpperCase();
    this.attributes = new Map(Object.entries(attributes));
    this.children = [];
    this.parentElement = null;
    this.classList = new FakeClassList();
    this.eventListeners = new Map();
    this._textContent = "";
    this.value = "";
    this.disabled = false;
    this.checked = false;
    this.hidden = false;
    this.files = [];
  }

  get id() { return this.getAttribute("id") ?? ""; }
  get type() { return this.getAttribute("type") ?? ""; }
  get options() { return this.children.filter((child) => child.tagName === "OPTION"); }
  get textContent() {
    return this._textContent + this.children.map((child) => child.textContent).join("");
  }
  set textContent(value) { this._textContent = String(value ?? ""); }

  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  append(...children) {
    for (let child of children) {
      if (typeof child === "string") {
        const text = new FakeElement("span");
        text.textContent = child;
        child = text;
      }
      child.parentElement = this;
      this.children.push(child);
    }
  }
  appendChild(child) { this.append(child); return child; }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  addEventListener(type, listener) {
    const listeners = this.eventListeners.get(type) ?? [];
    listeners.push(listener);
    this.eventListeners.set(type, listeners);
  }
  dispatchEvent(event) {
    event.target = this;
    for (const listener of this.eventListeners.get(event.type) ?? []) listener(event);
    return true;
  }

  matches(selector) {
    if (selector === "*") return true;
    if (selector === "button") return this.tagName === "BUTTON";
    if (selector === "tr") return this.tagName === "TR";
    if (selector === "tbody") return this.tagName === "TBODY";
    if (selector === "input") return this.tagName === "INPUT";
    if (selector === "input[type=\"file\"]") return this.tagName === "INPUT" && this.type === "file";
    if (selector === "input[type=\"checkbox\"]") return this.tagName === "INPUT" && this.type === "checkbox";
    if (selector.startsWith("#")) return this.id === selector.slice(1);
    const role = /^\[data-role=["']([^"']+)["']\]$/u.exec(selector);
    if (role) return this.getAttribute("data-role") === role[1];
    const field = /^\[data-field=["']([^"']+)["']\]$/u.exec(selector);
    if (field) return this.getAttribute("data-field") === field[1];
    if (selector === "[data-field]") return this.getAttribute("data-field") !== null;
    const kind = /^\[data-kind=["']([^"']+)["']\]$/u.exec(selector);
    if (kind) return this.getAttribute("data-kind") === kind[1];
    return this.tagName === selector.toUpperCase();
  }

  querySelectorAll(selector) {
    const result = [];
    const visit = (node) => {
      for (const child of node.children) {
        if (child.matches(selector)) result.push(child);
        visit(child);
      }
    };
    visit(this);
    return result;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
}

class FakeDocument extends FakeElement {
  constructor() {
    super("document");
    this.defaultView = { Event: FakeEvent };
    this.body = new FakeElement("body");
    this.append(this.body);
  }
  createElement(tagName) {
    const element = new FakeElement(tagName);
    element.ownerDocument = this;
    return element;
  }
  getElementById(id) { return this.querySelector(`#${id}`); }
}

function addElement(documentRef, tagName, id, attributes = {}) {
  const element = documentRef.createElement(tagName);
  element.setAttribute("id", id);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  documentRef.body.append(element);
  return element;
}

function buildPanelDocument() {
  const documentRef = new FakeDocument();
  addElement(documentRef, "p", "dataset-status");
  addElement(documentRef, "p", "screen-status");
  addElement(documentRef, "p", "identity-status");
  addElement(documentRef, "p", "panel-message");
  addElement(documentRef, "p", "result-summary");
  addElement(documentRef, "p", "last-imported");
  addElement(documentRef, "p", "permanent-warning");
  addElement(documentRef, "button", "import-button");
  addElement(documentRef, "input", "dataset-file", { type: "file" });
  addElement(documentRef, "button", "refresh-button");
  addElement(documentRef, "input", "bridge-base-url", { type: "url" });
  addElement(documentRef, "input", "bridge-pairing-code", { type: "text" });
  addElement(documentRef, "button", "bridge-connect-button");
  addElement(documentRef, "p", "bridge-status");
  addElement(documentRef, "button", "fill-button");
  addElement(documentRef, "button", "complement-button");
  addElement(documentRef, "input", "automation-auto-submit", { type: "checkbox" });
  addElement(documentRef, "input", "automation-marker", { type: "text" });
  addElement(documentRef, "input", "search-process", { type: "search" });
  addElement(documentRef, "input", "search-interested", { type: "search" });
  addElement(documentRef, "div", "search-results");
  addElement(documentRef, "p", "search-selection");
  addElement(documentRef, "section", "review-section");
  const reviewed = addElement(documentRef, "input", "reviewed-checkbox", { type: "checkbox" });
  reviewed.checked = false;
  addElement(documentRef, "div", "preview-body");
  return documentRef;
}

function citation(processKey = "103439/2023") {
  return { process: processKey, event: "9", page: 1, document: "Resolucao_103439.pdf" };
}

function makeField(value, processKey = "103439/2023") {
  return {
    status: value === null ? "missing" : "found",
    confidence: value === null ? "none" : "high",
    source_value: value,
    form_value: value,
    citation: value === null ? null : citation(processKey),
  };
}

async function makeDataset({ processKey = "103439/2023", interested = "Maria de Souza", sourceOverrides = {} } = {}) {
  const [number, year] = processKey.split("/");
  const fields = Object.fromEntries(PANEL_FIELD_ORDER.map((field) => [
    field,
    makeField(sourceOverrides[field] ?? {
      modalidade: "Aposentadoria voluntária por tempo de contribuição",
      fundamento_legal: "Art. 40, § 1º",
      data_publicacao_doe: "07/02/2020",
      cargo: "PROFESSOR PN - IV",
      matricula: "103.870-2/1",
      data_nascimento: "30/04/1967",
      genero: "Feminino",
    }[field], processKey),
  ]));
  const dataset = {
    schema_version: 1,
    generated_at: "2026-09-04T12:00:00+00:00",
    batch: {
      id: `batch-${number}`,
      logical_sha256: "",
      process_count: 1,
      record_count: 1,
      process_keys: [processKey],
    },
    records: [{
      process: { key: processKey, number, year },
      interested: {
        original: interested,
        normalized: interested.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/gu, " ").trim(),
      },
      status: "found",
      fields,
    }],
  };
  dataset.batch.logical_sha256 = await computeLogicalSha256(dataset);
  return dataset;
}

function snapshot({ processKey = "103439/2023", interested = { original: "Maria de Souza", normalized: "maria de souza" }, options = {}, fields = {}, bridgeContext = null } = {}) {
  const [number, year] = processKey.split("/");
  const allFields = Object.fromEntries(PANEL_FIELD_ORDER.map((field) => [field, {
    value: fields[field] ?? "",
    disabled: false,
    readOnly: false,
  }]));
  return {
    process: { number, year, key: processKey },
    interested,
    options,
    fields: allFields,
    ...(bridgeContext ? { bridgeContext } : {}),
  };
}

function currentOptions() {
  return {
    modalidade: [
      { value: "", label: "Selecione" },
      { value: "m-vol", label: "Aposentadoria voluntária por tempo de contribuição" },
      { value: "m-special", label: "Aposentadoria especial" },
    ],
    fundamento_legal: [
      { value: "", label: "Selecione" },
      { value: "f-general", label: "Artigo 40, parágrafo 1" },
      { value: "f-prof", label: "Artigo 40, parágrafo 5, professor" },
    ],
  };
}

function makeStorageArea(initialState = {}) {
  const state = structuredClone(initialState);
  return {
    state,
    async get(keys) {
      const result = {};
      for (const key of keys) if (Object.hasOwn(state, key)) result[key] = structuredClone(state[key]);
      return result;
    },
    async set(values) {
      for (const [key, value] of Object.entries(values)) state[key] = structuredClone(value);
    },
  };
}

function makeRuntime({
  dataset = null,
  storageArea = null,
  snapshots = [],
  matches = [],
  applyResponse = null,
  applyResponses = [],
  overrideResponses = [],
} = {}) {
  const calls = [];
  const localStorage = storageArea ?? makeStorageArea(dataset ? { [STORAGE_KEYS.DATASET]: dataset } : {});
  let snapshotIndex = 0;
  let matchIndex = 0;
  let applyIndex = 0;
  let overrideIndex = 0;
  const runtime = {
    calls,
    storageState: localStorage.state,
    async sendMessage(message) {
      calls.push(message);
      switch (message.type) {
        case MESSAGE_TYPES.GET_FORM_SNAPSHOT: {
          const current = snapshots[Math.min(snapshotIndex++, snapshots.length - 1)] ?? null;
          return current === null
            ? { ok: false, error: { code: "FORM_NOT_FOUND", message: "form missing" } }
            : { ok: true, payload: current };
        }
        case MESSAGE_TYPES.GET_MATCH: {
          const current = matches[Math.min(matchIndex++, matches.length - 1)] ?? { record: null, matches: {} };
          if (typeof current?.ok === "boolean") return current;
          return { ok: true, payload: current };
        }
        case MESSAGE_TYPES.IMPORT_DATASET:
          await localStorage.set({ [STORAGE_KEYS.DATASET]: message.payload.dataset });
          return { ok: true, payload: { batchId: message.payload.dataset.batch.id } };
        case MESSAGE_TYPES.APPLY_FIELDS: {
          const queued = applyResponses[Math.min(applyIndex++, applyResponses.length - 1)];
          if (queued) return queued;
          if (applyResponse) return applyResponse;
          const changed = [];
          const preserved = [];
          for (const field of Object.keys(message.payload.fields)) {
            if (field === "cargo" && snapshots[0]?.fields?.cargo?.value) preserved.push(field);
            else changed.push(field);
          }
          return { ok: true, payload: { changed, preserved, missing: [], disabled: [], errors: [] } };
        }
        case MESSAGE_TYPES.OVERRIDE_FIELD: {
          const queued = overrideResponses[Math.min(overrideIndex++, overrideResponses.length - 1)];
          if (queued) return queued;
          return { ok: true, payload: { changed: [message.payload.field], preserved: [], missing: [], disabled: [], errors: [] } };
        }
        case MESSAGE_TYPES.SET_REVIEWED:
          return { ok: true, payload: { reviewed: message.payload.reviewed } };
        case MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO:
          return { ok: true, payload: { signaled: true } };
        default:
          throw new Error(`unexpected message ${message.type}`);
      }
    },
    storage: {
      local: localStorage,
    },
  };
  return {
    calls: runtime.calls,
    storageState: runtime.storageState,
    runtime: { sendMessage: runtime.sendMessage },
    storage: runtime.storage,
  };
}

async function makeWorkerBackedChrome({ snapshots = [] } = {}) {
  const storageArea = makeStorageArea();
  const forwardedToContent = [];
  const panelCalls = [];
  let snapshotIndex = 0;
  const workerChrome = {
    runtime: {
      id: "test-extension",
      onMessage: { addListener() {} },
    },
    storage: { local: storageArea },
    tabs: {
      onRemoved: { addListener() {} },
      async query() { return [{ id: 7 }]; },
      async sendMessage(tabId, message, target) {
        forwardedToContent.push({ tabId, message: structuredClone(message), target: structuredClone(target) });
        if (message.type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) {
          const current = snapshots[Math.min(snapshotIndex++, snapshots.length - 1)] ?? null;
          return current === null
            ? { ok: false, error: { code: "FORM_NOT_FOUND", message: "form missing" } }
            : { ok: true, payload: structuredClone(current) };
        }
        if (message.type === MESSAGE_TYPES.APPLY_FIELDS) {
          return {
            ok: true,
            payload: {
              changed: Object.keys(message.payload.fields),
              preserved: [],
              missing: [],
              disabled: [],
              errors: [],
            },
          };
        }
        throw new Error(`unexpected content message ${message.type}`);
      },
    },
  };
  const worker = createServiceWorker({ chromeApi: workerChrome });
  const ready = await worker.handleMessage(
    createMessage(MESSAGE_TYPES.FORM_READY, { url: PORTAL_URL }, "panel-integration-ready"),
    { tab: { id: 7 }, frameId: 12, url: PORTAL_URL },
  );
  assert.equal(ready.ok, true);
  const panelChrome = {
    storage: { local: storageArea },
    runtime: {
      async sendMessage(message) {
        panelCalls.push(structuredClone(message));
        return worker.handleMessage(message, {
          id: "test-extension",
          url: "chrome-extension://test-extension/sidepanel/panel.html",
          tab: { id: 7 },
        });
      },
    },
  };
  return { forwardedToContent, panelCalls, panelChrome, storageArea };
}

function fieldMatch({ optionValue, optionLabel, kind = "exact", score = 100 } = {}) {
  return { kind, optionIndex: 1, optionValue, optionLabel, score, reasons: [] };
}

function fullMatches({ modalidade = fieldMatch({ optionValue: "m-vol", optionLabel: "Aposentadoria voluntária por tempo de contribuição" }), fundamento_legal = fieldMatch({ optionValue: "f-general", optionLabel: "Artigo 40, parágrafo 1" }) } = {}) {
  return { modalidade, fundamento_legal };
}

async function startApp({
  dataset = null,
  storageArea = null,
  snapshots = [],
  matches = [],
  applyResponse = null,
  applyResponses = [],
  overrideResponses = [],
  confirmFn = () => true,
  chromeApi = null,
  bridgeClientFactory = undefined,
  pairingFactory = undefined,
  setTimeoutFn = undefined,
  clearTimeoutFn = undefined,
} = {}) {
  const documentRef = buildPanelDocument();
  const resolvedChromeApi = chromeApi ?? makeRuntime({
    dataset,
    storageArea,
    snapshots,
    matches,
    applyResponse,
    applyResponses,
    overrideResponses,
  });
  const app = createPanelApp({ documentRef, chromeApi: resolvedChromeApi, confirmFn, bridgeClientFactory, pairingFactory, setTimeoutFn, clearTimeoutFn });
  await app.init();
  return { app, documentRef, chromeApi: resolvedChromeApi };
}

test("renders no-dataset state and permanent warning with inaccessible actions", async () => {
  const { documentRef } = await startApp({ snapshots: [null] });
  assert.equal(documentRef.getElementById("dataset-status").textContent, "Nenhum lote importado.");
  assert.equal(documentRef.getElementById("permanent-warning").textContent, PERMANENT_WARNING);
  assert.equal(documentRef.getElementById("fill-button").disabled, true);
  assert.equal(documentRef.getElementById("complement-button").disabled, true);
});

test("search filters imported records by process or interested name without changing portal identity", async () => {
  const dataset = await makeDataset();
  const { documentRef, app } = await startApp({ dataset, snapshots: [null] });
  const processSearch = documentRef.getElementById("search-process");
  const interestedSearch = documentRef.getElementById("search-interested");
  processSearch.value = "103439";
  processSearch.dispatchEvent(new FakeEvent("input"));
  assert.equal(documentRef.getElementById("search-results").children.length, 1);
  assert.match(documentRef.getElementById("search-results").textContent, /103439\/2023/u);

  processSearch.value = "";
  interestedSearch.value = "maria";
  interestedSearch.dispatchEvent(new FakeEvent("input"));
  assert.equal(documentRef.getElementById("search-results").children.length, 1);
  assert.match(documentRef.getElementById("search-results").textContent, /Maria de Souza/u);

  documentRef.getElementById("search-results").children[0].dispatchEvent(new FakeEvent("click"));
  assert.match(documentRef.getElementById("search-selection").textContent, /103439\/2023 · Maria de Souza/u);
  assert.equal(app.getState().previewIdentity, null);
});

test("explicit Complementar Ato button sends only a typed signal for the current identity", async () => {
  const dataset = await makeDataset();
  const { documentRef, chromeApi } = await startApp({
    dataset,
    snapshots: [snapshot()],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
  });
  const button = documentRef.getElementById("complement-button");
  assert.equal(button.disabled, false);
  button.dispatchEvent(new FakeEvent("click"));
  await new Promise((resolve) => setImmediate(resolve));
  const signal = chromeApi.calls.find((message) => message.type === MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO);
  assert.deepEqual(signal?.payload, {
    processKey: "103439/2023",
    interestedNormalized: "maria de souza",
  });
  assert.equal(chromeApi.calls.some((message) => message.type === MESSAGE_TYPES.APPLY_FIELDS), false);
});

test("optionally pairs with the local mesa and publishes the current selection without filling", async () => {
  const dataset = await makeDataset();
  const bridgeCalls = [];
  const { documentRef, app } = await startApp({
    dataset,
    snapshots: [snapshot({ bridgeContext: { tab_id: 7, frame_id: 12 } })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
    pairingFactory: async ({ baseUrl, code }) => {
      assert.equal(baseUrl, "http://127.0.0.1:18743");
      assert.equal(code, "12345678");
      return "ephemeral-token";
    },
    bridgeClientFactory: () => ({
      async publishSelection(selection) { bridgeCalls.push(selection); return { accepted: true, revision: 3 }; },
      async getState() { return { revision: 3 }; },
      async setCompleted() { return { revision: 4 }; },
    }),
  });
  documentRef.getElementById("bridge-base-url").value = "http://127.0.0.1:18743";
  const pairingCode = documentRef.getElementById("bridge-pairing-code");
  pairingCode.value = "12345678";
  pairingCode.dispatchEvent(new FakeEvent("input"));
  assert.equal(documentRef.getElementById("bridge-connect-button").disabled, false);
  documentRef.getElementById("bridge-connect-button").dispatchEvent(new FakeEvent("click"));
  await new Promise((resolve) => setImmediate(resolve));
  await app.refresh();
  assert.equal(app.getState().bridgeClient !== null, true);
  assert.equal(bridgeCalls.length, 1);
  assert.deepEqual(bridgeCalls[0], {
    process_key: "103439/2023",
    interested_normalized: "maria de souza",
    tab_id: 7,
    frame_id: 12,
    sequence: 1,
  });
  assert.equal(documentRef.getElementById("fill-button").disabled, false);
});

test("automation view requires a compatible bridge, starts explicitly, and keeps manual fill blocked while active", async () => {
  const dataset = await makeDataset();
  const calls = [];
  const run = {
    api_version: 1,
    run_id: "run-panel-1",
    revision: 0,
    status: "discovering",
    spec: { sector: "aposentadorias" },
    items: [],
    last_confirmed_item_id: null,
  };
  const client = {
    async publishSelection(value) { calls.push(["selection", value]); return { accepted: true, revision: 1 }; },
    async getState() { return { revision: 1 }; },
    async setCompleted() { return { revision: 2 }; },
    async getDataset() { return { api_version: 1, revision: 1, dataset }; },
    async getAutomationCapabilities() { calls.push(["capabilities"]); return { api_version: 1, automation_schema: 1, legal_context_schema: 1, rules_version: "legal-foundation-v1", real_send_enabled: false }; },
    async listAutomationRuns() { calls.push(["history"]); return { api_version: 1, runs: [{ run_id: "run-panel-1", state: "paused", revision: 0, created_at: "2026-09-09T12:00:00Z", updated_at: "2026-09-09T12:00:00Z", totals: {} }], next_cursor: null }; },
    async getAutomationEvents(runId) { calls.push(["events", runId]); return { api_version: 1, events: [{ type: "queue_frozen", created_at: "2026-09-09T12:01:00Z" }], next_after: null, has_more: false }; },
    async createAutomationRun(spec, eventId) { calls.push(["start", spec, eventId]); return { ...run, spec, status: "discovering" }; },
    async controlAutomationRun(runId, body) { calls.push([body.action, runId, body]); return { ...run, run_id: runId, revision: body.expectedRevision + 1, status: body.action === "pause" ? "paused" : body.action === "stop" ? "stopped" : "running" }; },
  };
  const chromeApi = makeRuntime({
    dataset,
    snapshots: [snapshot({ bridgeContext: { tab_id: 7, frame_id: 12, sector: "aposentadorias" } })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
  });
  const workerCalls = [];
  const sendMessage = chromeApi.runtime.sendMessage;
  chromeApi.runtime.sendMessage = async (message) => {
    workerCalls.push(message);
    if (message.type === MESSAGE_TYPES.AUTO_START) {
      return { ok: true, payload: { ...run, spec: message.payload.spec, status: "discovering" } };
    }
    if (message.type === MESSAGE_TYPES.AUTO_PAUSE) {
      return { ok: true, payload: { ...run, revision: 1, status: "paused" } };
    }
    return sendMessage(message);
  };
  const { app, documentRef } = await startApp({
    chromeApi,
    dataset,
    snapshots: [snapshot({ bridgeContext: { tab_id: 7, frame_id: 12, sector: "aposentadorias" } })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
    pairingFactory: async () => "token",
    bridgeClientFactory: () => client,
  });
  documentRef.getElementById("bridge-pairing-code").value = "12345678";
  documentRef.getElementById("bridge-connect-button").dispatchEvent(new FakeEvent("click"));
  for (let index = 0; index < 5; index += 1) await new Promise((resolve) => setImmediate(resolve));
  assert.ok(app.getState().automationCapabilities, documentRef.getElementById("bridge-status").textContent);
  assert.equal(app.getState().automationCapabilities.real_send_enabled, false);
  documentRef.getElementById("automation-marker").value = "PROFESSOR - IPERN - 2 RUBRICAS";
  assert.equal(await app.startAutomation(), true);
  assert.equal(workerCalls.find((message) => message.type === MESSAGE_TYPES.AUTO_START).payload.spec.marker, "PROFESSOR - IPERN - 2 RUBRICAS");
  assert.equal(app.getState().selectedView, "execution");
  assert.equal(documentRef.getElementById("fill-button").disabled, true);
  assert.equal(await app.controlAutomation("pause"), true);
  assert.match(documentRef.getElementById("permanent-warning").textContent, /pausada|Nenhum novo envio/iu);
  assert.equal(await app.openAutomationHistory("run-panel-1"), true);
  assert.equal(app.getState().selectedView, "history");
  assert.deepEqual(calls.filter(([name]) => ["capabilities", "history", "pause"].includes(name)).map(([name]) => name), ["capabilities", "history"]);
  assert.equal(workerCalls.some((message) => message.type === MESSAGE_TYPES.AUTO_START), true);
  assert.equal(workerCalls.some((message) => message.type === MESSAGE_TYPES.AUTO_PAUSE), true);
  assert.equal(calls.some(([name]) => name === "pause"), false);
  assert.equal(calls.some(([name, runId]) => name === "events" && runId === "run-panel-1"), true);
});

test("automatic submission requires capability and an action-time confirmation", async () => {
  const dataset = await makeDataset();
  const run = {
    api_version: 1,
    run_id: "run-auto-panel-1",
    revision: 0,
    status: "discovering",
    items: [],
    last_confirmed_item_id: null,
  };
  const client = {
    async getDataset() { return { api_version: 1, revision: 1, dataset }; },
    async publishSelection() { return { accepted: true, revision: 1 }; },
    async getState() { return { revision: 1 }; },
    async getAutomationCapabilities() {
      return {
        api_version: 1,
        automation_schema: 1,
        legal_context_schema: 1,
        rules_version: "legal-foundation-v1",
        real_send_enabled: true,
        pilot_enabled: false,
        pilot_consumes_remaining: false,
      };
    },
    async listAutomationRuns() { return { runs: [], next_cursor: null }; },
  };
  const runtime = makeRuntime({
    dataset,
    snapshots: [snapshot({ bridgeContext: { tab_id: 7, frame_id: 12, sector: "aposentadorias" } })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
  });
  const workerCalls = [];
  const originalSendMessage = runtime.runtime.sendMessage;
  runtime.runtime.sendMessage = async (message) => {
    workerCalls.push(message);
    if (message.type === MESSAGE_TYPES.AUTO_START) {
      return { ok: true, payload: { ...run, spec: message.payload.spec } };
    }
    return originalSendMessage(message);
  };
  let confirmation = "";
  const { app, documentRef } = await startApp({
    chromeApi: runtime,
    dataset,
    snapshots: [snapshot({ bridgeContext: { tab_id: 7, frame_id: 12, sector: "aposentadorias" } })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
    pairingFactory: async () => "token",
    bridgeClientFactory: () => client,
    confirmFn(message) { confirmation = message; return true; },
  });
  documentRef.getElementById("bridge-pairing-code").value = "12345678";
  documentRef.getElementById("bridge-connect-button").dispatchEvent(new FakeEvent("click"));
  for (let index = 0; index < 5; index += 1) await new Promise((resolve) => setImmediate(resolve));
  documentRef.getElementById("automation-marker").value = "PROFESSOR - IPERN - 2 RUBRICAS";
  documentRef.getElementById("automation-auto-submit").checked = true;

  assert.equal(await app.startAutomation(), true);
  assert.match(confirmation, /envio automático|ações externas|Complementar Ato/iu);
  const started = workerCalls.find((message) => message.type === MESSAGE_TYPES.AUTO_START);
  assert.equal(started.payload.spec.autoSubmit, true);
  assert.equal(started.payload.spec.marker, "PROFESSOR - IPERN - 2 RUBRICAS");
});

test("pilot action is explicit, targets the current identity, and preserves the one-act mode", async () => {
  const dataset = await makeDataset();
  const calls = [];
  const run = {
    api_version: 1,
    run_id: "run-pilot-1",
    revision: 0,
    status: "discovering",
    spec: { sector: "aposentadorias" },
    items: [],
    last_confirmed_item_id: null,
  };
  const client = {
    async getDataset() { return { api_version: 1, revision: 1, dataset }; },
    async publishSelection() { return { accepted: true, revision: 1 }; },
    async getState() { return { revision: 1 }; },
    async getAutomationCapabilities() {
      return {
        api_version: 1,
        automation_schema: 1,
        legal_context_schema: 1,
        rules_version: "legal-foundation-v1",
        real_send_enabled: false,
        pilot_enabled: true,
        pilot_consumes_remaining: true,
      };
    },
    async listAutomationRuns() { return { runs: [], next_cursor: null }; },
    async createAutomationRun(spec, eventId) { calls.push(["start", spec, eventId]); return { ...run, spec, status: "discovering" }; },
  };
  const chromeApi = makeRuntime({
    dataset,
    snapshots: [snapshot({ bridgeContext: { tab_id: 7, frame_id: 12, sector: "aposentadorias" } })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
  });
  const workerCalls = [];
  const sendMessage = chromeApi.runtime.sendMessage;
  chromeApi.runtime.sendMessage = async (message) => {
    workerCalls.push(message);
    if (message.type === MESSAGE_TYPES.AUTO_START) {
      return { ok: true, payload: { ...run, spec: message.payload.spec, status: "discovering" } };
    }
    return sendMessage(message);
  };
  const { app, documentRef } = await startApp({
    chromeApi,
    dataset,
    snapshots: [snapshot({ bridgeContext: { tab_id: 7, frame_id: 12, sector: "aposentadorias" } })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
    pairingFactory: async () => "token",
    bridgeClientFactory: () => client,
  });
  documentRef.getElementById("bridge-pairing-code").value = "12345678";
  documentRef.getElementById("bridge-connect-button").dispatchEvent(new FakeEvent("click"));
  for (let index = 0; index < 5; index += 1) await new Promise((resolve) => setImmediate(resolve));
  assert.equal(await app.startAutomation("pilot"), true);
  const started = workerCalls.find((message) => message.type === MESSAGE_TYPES.AUTO_START);
  assert.equal(started.payload.spec.mode, "pilot");
  assert.deepEqual(started.payload.spec.pilotIdentity, {
    processKey: "103439/2023",
    interestedNormalized: "maria de souza",
    portalActId: null,
  });
  assert.match(documentRef.getElementById("permanent-warning").textContent, /lote|piloto/iu);
});

test("pilot action delegates run creation to the worker controller", async () => {
  const dataset = await makeDataset();
  const runtime = makeRuntime({
    dataset,
    snapshots: [snapshot({ bridgeContext: { tab_id: 7, frame_id: 12, sector: "aposentadorias" } })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
  });
  const workerCalls = [];
  const sendMessage = runtime.runtime.sendMessage;
  runtime.runtime.sendMessage = async (message) => {
    workerCalls.push(message);
    if (message.type === MESSAGE_TYPES.AUTO_START) {
      return {
        ok: true,
        payload: {
          api_version: 1,
          run_id: "run-pilot-worker",
          revision: 0,
          status: "discovering",
          spec: message.payload.spec,
          items: [],
          last_confirmed_item_id: null,
        },
      };
    }
    return sendMessage(message);
  };
  const bridgeCalls = [];
  const client = {
    async getDataset() { return { api_version: 1, revision: 1, dataset }; },
    async publishSelection() { return { accepted: true, revision: 1 }; },
    async getState() { return { revision: 1 }; },
    async getAutomationCapabilities() {
      return {
        api_version: 1,
        automation_schema: 1,
        legal_context_schema: 1,
        rules_version: "legal-foundation-v1",
        real_send_enabled: false,
        pilot_enabled: true,
        pilot_consumes_remaining: true,
      };
    },
    async listAutomationRuns() { return { runs: [], next_cursor: null }; },
    async createAutomationRun(spec, eventId) { bridgeCalls.push([spec, eventId]); throw new Error("panel must use worker"); },
  };
  const { app, documentRef } = await startApp({
    chromeApi: runtime,
    dataset,
    snapshots: [snapshot({ bridgeContext: { tab_id: 7, frame_id: 12, sector: "aposentadorias" } })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
    pairingFactory: async () => "token",
    bridgeClientFactory: () => client,
  });
  documentRef.getElementById("bridge-pairing-code").value = "12345678";
  documentRef.getElementById("bridge-connect-button").dispatchEvent(new FakeEvent("click"));
  assert.equal(await app.startAutomation("pilot"), true);
  const start = workerCalls.find((message) => message.type === MESSAGE_TYPES.AUTO_START);
  assert.ok(start);
  assert.equal(start.payload.spec.mode, "pilot");
  assert.equal(start.payload.spec.pilotIdentity.interestedNormalized, "maria de souza");
  assert.deepEqual(bridgeCalls, []);
});

test("automation status polls every two seconds without requiring a panel action", async () => {
  const dataset = await makeDataset();
  const calls = [];
  const timers = [];
  const client = {
    async getDataset() { return { api_version: 1, revision: 1, dataset }; },
    async publishSelection() { return { accepted: true, revision: 1 }; },
    async getState() { return { revision: 1 }; },
    async getAutomationCapabilities() { calls.push("capabilities"); return { api_version: 1, automation_schema: 1, legal_context_schema: 1, rules_version: "legal-foundation-v1", real_send_enabled: false }; },
    async listAutomationRuns() { calls.push("history"); return { api_version: 1, runs: [], next_cursor: null }; },
  };
  const setTimeoutFn = (callback, delay) => {
    const timer = { callback, delay, unref() {} };
    timers.push(timer);
    return timer;
  };
  const clearTimeoutFn = (timer) => { timer.cleared = true; };
  const { app, documentRef } = await startApp({
    dataset,
    snapshots: [snapshot({ bridgeContext: { tab_id: 7, frame_id: 12 } })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
    pairingFactory: async () => "token",
    bridgeClientFactory: () => client,
    setTimeoutFn,
    clearTimeoutFn,
  });
  documentRef.getElementById("bridge-pairing-code").value = "12345678";
  documentRef.getElementById("bridge-connect-button").dispatchEvent(new FakeEvent("click"));
  for (let index = 0; index < 5; index += 1) await new Promise((resolve) => setImmediate(resolve));
  const automationTimer = timers.find((timer) => timer.delay === 2000);
  assert.ok(automationTimer, "automation polling timer should be scheduled");
  await automationTimer.callback();
  assert.equal(calls.filter((call) => call === "capabilities").length, 2);
  assert.ok(timers.filter((timer) => timer.delay === 2000).length >= 2);
  app.stopBridgePolling();
  assert.ok(timers.some((timer) => timer.delay === 2000 && timer.cleared === true));
});

test("rapid refreshes publish only the newest tab identity with increasing sequences", async () => {
  const first = await makeDataset({ processKey: "103439/2023", interested: "Maria de Souza" });
  const second = await makeDataset({ processKey: "103440/2023", interested: "Ana de Souza" });
  const dataset = structuredClone(first);
  dataset.batch = {
    ...dataset.batch,
    id: "batch-two-processes",
    process_count: 2,
    record_count: 2,
    process_keys: [first.batch.process_keys[0], second.batch.process_keys[0]],
  };
  dataset.records = [first.records[0], second.records[0]];
  dataset.batch.logical_sha256 = await computeLogicalSha256(dataset);

  let snapshotCall = 0;
  let rejectStale;
  let releaseCurrent;
  const staleSnapshot = new Promise((_resolveSnapshot, rejectSnapshot) => { rejectStale = rejectSnapshot; });
  const currentSnapshot = new Promise((resolveSnapshot) => { releaseCurrent = resolveSnapshot; });
  const selections = [];
  const storage = makeStorageArea({
    [STORAGE_KEYS.DATASET]: dataset,
    [STORAGE_KEYS.BRIDGE_BASE_URL]: "http://127.0.0.1:18743",
    [STORAGE_KEYS.BRIDGE_TOKEN]: "session-token",
  });
  const chromeApi = {
    storage: { local: storage, session: storage },
    runtime: {
      async sendMessage(message) {
        if (message.type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) {
          if (snapshotCall++ === 0) {
            return { ok: true, payload: snapshot({ bridgeContext: { tab_id: 7, frame_id: 12 } }) };
          }
          return snapshotCall === 2
            ? staleSnapshot.then((payload) => ({ ok: true, payload }))
            : currentSnapshot.then((payload) => ({ ok: true, payload }));
        }
        if (message.type === MESSAGE_TYPES.GET_MATCH) {
          const record = dataset.records.find((candidate) => candidate.process.key === message.payload.processKey);
          return { ok: true, payload: { record, matches: fullMatches(), reviewed: false } };
        }
        throw new Error(`unexpected message ${message.type}`);
      },
    },
  };
  const app = createPanelApp({
    documentRef: buildPanelDocument(),
    chromeApi,
    bridgeClientFactory: () => ({
      async publishSelection(selection) { selections.push(selection); return { accepted: true, revision: selections.length }; },
      async getState() { return { revision: selections.length }; },
    }),
  });
  await app.init();

  const staleRefresh = app.refresh();
  const currentRefresh = app.refresh();
  releaseCurrent(snapshot({
    processKey: "103440/2023",
    interested: { original: "Ana de Souza", normalized: "ana de souza" },
    bridgeContext: { tab_id: 7, frame_id: 12 },
    options: currentOptions(),
  }));
  assert.equal(await currentRefresh, true);
  rejectStale(new Error("stale snapshot failed"));
  assert.equal(await staleRefresh, false);

  assert.equal(app.getState().previewIdentity.processKey, "103440/2023");
  assert.deepEqual(selections.map(({ process_key, sequence }) => ({ process_key, sequence })), [
    { process_key: "103439/2023", sequence: 1 },
    { process_key: "103440/2023", sequence: 2 },
  ]);
});

test("bridge dataset refresh updates the current panel without applying fields", async () => {
  const initial = await makeDataset();
  const updated = await makeDataset({ interested: "Maria Atualizada" });
  let currentDataset = initial;
  let currentRevision = 1;
  const bridge = {
    async getDataset() { return { revision: currentRevision, dataset: currentDataset }; },
    async getState() { return { revision: 0 }; },
    async publishSelection() { return { accepted: true }; },
  };
  const { app, documentRef, chromeApi } = await startApp({
    dataset: initial,
    snapshots: [null],
    bridgeClientFactory: () => bridge,
    pairingFactory: async () => "token",
  });
  documentRef.getElementById("bridge-base-url").value = "http://127.0.0.1:18743";
  documentRef.getElementById("bridge-pairing-code").value = "12345678";
  documentRef.getElementById("bridge-connect-button").dispatchEvent(new FakeEvent("click"));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(app.getState().dataset.batch.id, initial.batch.id);
  currentDataset = updated;
  currentRevision = 2;
  await app.syncBridgeDataset();
  assert.equal(app.getState().dataset.records[0].interested.original, "Maria Atualizada");
  assert.match(documentRef.getElementById("bridge-status").textContent, /^Mesa local conectada\./u);
  const incrementalImport = chromeApi.calls.find((message) => message.type === MESSAGE_TYPES.IMPORT_DATASET);
  assert.equal(incrementalImport.payload.preserveReviewed, true);
  assert.equal(chromeApi.calls.some((message) => message.type === MESSAGE_TYPES.APPLY_FIELDS), false);
  assert.equal(documentRef.getElementById("fill-button").disabled, true);
});

test("imports one file, reuses it after switching process, and restores it in a second panel instance", async () => {
  const dataset = await makeDataset();
  const sharedStorage = makeStorageArea();
  const snapshots = [snapshot({}), snapshot({ processKey: "103440/2023" })];
  const { app, documentRef, chromeApi } = await startApp({ storageArea: sharedStorage, snapshots, matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }] });
  const file = { async text() { return JSON.stringify(dataset); } };
  const fileInput = documentRef.getElementById("dataset-file");
  fileInput.files = [file];
  await app.importSelectedFile();

  assert.equal(chromeApi.calls.filter((message) => message.type === MESSAGE_TYPES.IMPORT_DATASET).length, 1);
  assert.equal(documentRef.getElementById("dataset-status").textContent, "Lote importado: 1 processo, 1 interessado.");

  await app.refresh();
  assert.equal(chromeApi.calls.filter((message) => message.type === MESSAGE_TYPES.IMPORT_DATASET).length, 1);
  assert.equal(documentRef.getElementById("screen-status").textContent, "Processo 103440/2023 não está no lote.");

  const second = await startApp({
    storageArea: sharedStorage,
    snapshots: [snapshot({ options: currentOptions() })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
  });
  assert.equal(second.documentRef.getElementById("dataset-status").textContent, "Lote importado: 1 processo, 1 interessado.");
  assert.equal(second.documentRef.getElementById("screen-status").textContent, "Prévia pronta.");
  assert.equal(second.chromeApi.calls.some((message) => message.type === MESSAGE_TYPES.IMPORT_DATASET), false);
  assert.equal(second.app.getState().dataset.batch.id, dataset.batch.id);
});

test("rejects an invalid batch without replacing the previously persisted batch", async () => {
  const previous = await makeDataset();
  const { app, documentRef, chromeApi } = await startApp({ dataset: previous, snapshots: [snapshot()] });
  const invalid = structuredClone(previous);
  invalid.batch.logical_sha256 = "0".repeat(64);
  documentRef.getElementById("dataset-file").files = [{ async text() { return JSON.stringify(invalid); } }];

  await app.importSelectedFile();

  assert.equal(chromeApi.calls.filter((message) => message.type === MESSAGE_TYPES.IMPORT_DATASET).length, 0);
  assert.equal(chromeApi.storageState[STORAGE_KEYS.DATASET].batch.id, previous.batch.id);
  assert.match(documentRef.getElementById("panel-message").textContent, /inválido|rejeitado/iu);
});

test("shows incompatible screen when the current form snapshot cannot be obtained", async () => {
  const dataset = await makeDataset();
  const { documentRef } = await startApp({ dataset, snapshots: [null] });
  assert.equal(documentRef.getElementById("screen-status").textContent, "Tela incompatível: formulário Complementar Ato não detectado.");
});

test("shows process missing, interested not selected, and interested not found as blocking states", async (t) => {
  const dataset = await makeDataset();
  await t.test("process missing", async () => {
    const { documentRef } = await startApp({ dataset, snapshots: [snapshot({ processKey: "999999/2024" })] });
    assert.equal(documentRef.getElementById("screen-status").textContent, "Processo 999999/2024 não está no lote.");
  });
  await t.test("interested not selected", async () => {
    const { documentRef } = await startApp({ dataset, snapshots: [snapshot({ interested: null })] });
    assert.equal(documentRef.getElementById("identity-status").textContent, "Interessado não selecionado.");
    assert.equal(documentRef.getElementById("fill-button").disabled, true);
  });
  await t.test("interested not found", async () => {
    const { documentRef } = await startApp({ dataset, snapshots: [snapshot({ interested: { original: "Pessoa Ausente", normalized: "pessoa ausente" } })] });
    assert.match(documentRef.getElementById("identity-status").textContent, /Interessado não encontrado no lote\. Disponíveis: Maria de Souza\./u);
  });
});

test("renders a preview from current portal options with exact green and approximate yellow labels", async () => {
  const dataset = await makeDataset({ sourceOverrides: { fundamento_legal: "Fundamento sem opção literal" } });
  const { documentRef, chromeApi } = await startApp({
    dataset,
    snapshots: [snapshot({ options: currentOptions() })],
    matches: [{
      record: dataset.records[0],
      matches: fullMatches({ fundamento_legal: fieldMatch({ optionValue: "f-general", optionLabel: "Artigo 40, parágrafo 1", kind: "probable", score: 8 }) }),
      reviewed: false,
    }],
  });

  assert.equal(documentRef.getElementById("screen-status").textContent, "Prévia pronta.");
  assert.equal(documentRef.getElementById("fill-button").disabled, false);
  const matchRequest = chromeApi.calls.find((message) => message.type === MESSAGE_TYPES.GET_MATCH);
  assert.deepEqual(matchRequest.payload.options, currentOptions());
  const rows = documentRef.getElementById("preview-body").querySelectorAll("[data-field]");
  assert.equal(rows.length, 7);
  const exactControl = documentRef.getElementById("preview-body").querySelector('[data-kind="exact"]');
  const approximateControl = documentRef.getElementById("preview-body").querySelector('[data-kind="probable"]');
  assert.ok(exactControl);
  assert.ok(approximateControl);
  assert.match(approximateControl.textContent, /aproximado/iu);
  assert.equal(documentRef.getElementById("permanent-warning").textContent, PERMANENT_WARNING);
});

test("renders untrusted JSON values only as text, never as markup", async () => {
  const malicious = "<img src=x onerror=alert(1)>";
  const dataset = await makeDataset({ sourceOverrides: { cargo: malicious } });
  const { documentRef } = await startApp({
    dataset,
    snapshots: [snapshot({ options: currentOptions() })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
  });
  const body = documentRef.getElementById("preview-body");
  assert.equal(body.querySelector("img"), null);
  assert.ok(body.textContent.includes(malicious));
  assert.doesNotMatch(readFileSync(resolve(ROOT, "sidepanel/panel.js"), "utf8"), /innerHTML\s*=/u);
});

test("requests a fresh snapshot before filling and blocks when identity changed", async () => {
  const dataset = await makeDataset();
  const { app, documentRef, chromeApi } = await startApp({
    dataset,
    snapshots: [snapshot({ options: currentOptions() }), snapshot({ processKey: "103440/2023", options: currentOptions() })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
  });

  await app.fillAvailableFields();

  assert.equal(chromeApi.calls.some((message) => message.type === MESSAGE_TYPES.APPLY_FIELDS), false);
  assert.match(documentRef.getElementById("panel-message").textContent, /mudou|atualize/iu);
});

test("clears a completed result when process, interested, or screen becomes blocking", async (t) => {
  const dataset = await makeDataset();
  const cases = [
    {
      name: "different process",
      blockedSnapshot: snapshot({ processKey: "103440/2023", options: currentOptions() }),
      expectedState: PANEL_STATES.PROCESS_NOT_FOUND,
    },
    {
      name: "interested deselected",
      blockedSnapshot: snapshot({ interested: null, options: currentOptions() }),
      expectedState: PANEL_STATES.INTERESTED_NOT_SELECTED,
    },
    {
      name: "different interested",
      blockedSnapshot: snapshot({ interested: { original: "Pessoa Ausente", normalized: "pessoa ausente" }, options: currentOptions() }),
      expectedState: PANEL_STATES.INTERESTED_NOT_FOUND,
    },
    {
      name: "incompatible screen",
      blockedSnapshot: null,
      expectedState: PANEL_STATES.INCOMPATIBLE_SCREEN,
    },
  ];

  for (const scenario of cases) {
    await t.test(scenario.name, async () => {
      const current = snapshot({ options: currentOptions() });
      const { app, documentRef } = await startApp({
        dataset,
        snapshots: [current, current, scenario.blockedSnapshot],
        matches: [
          { record: dataset.records[0], matches: fullMatches(), reviewed: false },
          { record: dataset.records[0], matches: fullMatches(), reviewed: false },
        ],
      });

      assert.equal(await app.fillAvailableFields(), true);
      assert.match(documentRef.getElementById("result-summary").textContent, /Alterados: 7/u);
      await app.refresh();

      assert.equal(app.getState().kind, scenario.expectedState);
      assert.equal(app.getState().result, null);
      assert.equal(documentRef.getElementById("result-summary").textContent, "");
      assert.equal(documentRef.getElementById("fill-button").disabled, true);
    });
  }
});

test("blocks and invalidates every stale preview after an operation failure", async (t) => {
  const dataset = await makeDataset();
  const current = snapshot({ options: currentOptions() });
  const divergence = snapshot({ options: currentOptions(), fields: { cargo: "Cargo já existente" } });
  const match = { record: dataset.records[0], matches: fullMatches(), reviewed: false };
  const successfulApply = {
    ok: true,
    payload: {
      changed: [...PANEL_FIELD_ORDER],
      preserved: [],
      missing: [],
      disabled: [],
      errors: [],
    },
  };

  async function establishPreviousResult(started) {
    assert.equal(await started.app.fillAvailableFields(), true);
    assert.match(started.documentRef.getElementById("result-summary").textContent, /Alterados: 7/u);
    assert.equal(await started.app.setReviewed(true), true);
    assert.equal(started.app.getState().reviewed, true);
  }

  function assertSafelyBlocked(started, errorPattern) {
    const state = started.app.getState();
    assert.equal(state.kind, "operation-blocked");
    assert.equal(state.snapshot, null);
    assert.equal(state.record, null);
    assert.deepEqual(state.rows, []);
    assert.equal(state.result, null);
    assert.equal(state.reviewed, false);
    assert.equal(state.previewIdentity, null);
    assert.equal(started.documentRef.getElementById("result-summary").textContent, "");
    assert.equal(started.documentRef.getElementById("preview-body").querySelectorAll("[data-field]").length, 0);
    assert.equal(started.documentRef.getElementById("preview-body").querySelector('[data-role="override"]'), null);
    assert.equal(started.documentRef.getElementById("fill-button").disabled, true);
    assert.equal(started.documentRef.getElementById("reviewed-checkbox").disabled, true);
    assert.equal(started.documentRef.getElementById("reviewed-checkbox").checked, false);
    assert.equal(started.documentRef.getElementById("review-section").hidden, true);
    assert.equal(started.documentRef.getElementById("permanent-warning").textContent, PERMANENT_WARNING);
    assert.equal(started.documentRef.getElementById("screen-status").getAttribute("data-state"), "blocked");
    assert.equal(started.documentRef.getElementById("panel-message").getAttribute("data-state"), "error");
    assert.match(started.documentRef.getElementById("panel-message").textContent, errorPattern);
  }

  async function assertNoActionAfterBlock(started) {
    const callCount = started.chromeApi.calls.length;
    assert.equal(await started.app.fillAvailableFields(), false);
    assert.equal(await started.app.overrideField("cargo"), false);
    assert.equal(await started.app.setReviewed(true), false);
    assert.equal(started.chromeApi.calls.length, callCount);
  }

  await t.test("fresh snapshot failure", async () => {
    const started = await startApp({
      dataset,
      snapshots: [current, current, null],
      matches: [match, match],
      applyResponses: [successfulApply],
    });
    await establishPreviousResult(started);
    const matchCount = started.chromeApi.calls.filter(({ type }) => type === MESSAGE_TYPES.GET_MATCH).length;
    const applyCount = started.chromeApi.calls.filter(({ type }) => type === MESSAGE_TYPES.APPLY_FIELDS).length;

    assert.equal(await started.app.fillAvailableFields(), false);

    assertSafelyBlocked(started, /form missing/iu);
    assert.equal(started.chromeApi.calls.filter(({ type }) => type === MESSAGE_TYPES.GET_MATCH).length, matchCount);
    assert.equal(started.chromeApi.calls.filter(({ type }) => type === MESSAGE_TYPES.APPLY_FIELDS).length, applyCount);
    await assertNoActionAfterBlock(started);
  });

  await t.test("GET_MATCH failure", async () => {
    const started = await startApp({
      dataset,
      snapshots: [current, current, current],
      matches: [match, match, { ok: false, error: { code: "MATCH_FAILED", message: "match failed" } }],
      applyResponses: [successfulApply],
    });
    await establishPreviousResult(started);
    const applyCount = started.chromeApi.calls.filter(({ type }) => type === MESSAGE_TYPES.APPLY_FIELDS).length;

    assert.equal(await started.app.fillAvailableFields(), false);

    assertSafelyBlocked(started, /match failed/iu);
    assert.equal(started.chromeApi.calls.filter(({ type }) => type === MESSAGE_TYPES.APPLY_FIELDS).length, applyCount);
    await assertNoActionAfterBlock(started);
  });

  await t.test("APPLY_FIELDS failure", async () => {
    const started = await startApp({
      dataset,
      snapshots: [current, current, current],
      matches: [match, match, match],
      applyResponses: [
        successfulApply,
        { ok: false, error: { code: "APPLY_FAILED", message: "apply failed" } },
      ],
    });
    await establishPreviousResult(started);
    const overrideCount = started.chromeApi.calls.filter(({ type }) => type === MESSAGE_TYPES.OVERRIDE_FIELD).length;

    assert.equal(await started.app.fillAvailableFields(), false);

    assertSafelyBlocked(started, /apply failed/iu);
    assert.equal(started.chromeApi.calls.filter(({ type }) => type === MESSAGE_TYPES.OVERRIDE_FIELD).length, overrideCount);
    await assertNoActionAfterBlock(started);
  });

  await t.test("OVERRIDE_FIELD failure", async () => {
    const started = await startApp({
      dataset,
      snapshots: [divergence, divergence, divergence],
      matches: [match, match],
      applyResponses: [successfulApply],
      overrideResponses: [
        { ok: false, error: { code: "OVERRIDE_FAILED", message: "override failed" } },
      ],
    });
    await establishPreviousResult(started);
    assert.ok(started.documentRef.getElementById("preview-body").querySelector('[data-role="override"]'));

    assert.equal(await started.app.overrideField("cargo"), false);

    assertSafelyBlocked(started, /override failed/iu);
    assert.equal(started.chromeApi.calls.filter(({ type }) => type === MESSAGE_TYPES.OVERRIDE_FIELD).length, 1);
    await assertNoActionAfterBlock(started);
  });
});

test("integrates panel, worker, and matcher and recalculates changed options before apply", async () => {
  const dataset = await makeDataset();
  const initialOptions = {
    modalidade: currentOptions().modalidade,
    fundamento_legal: [
      { value: "f-current", label: "Artigo 40, parágrafo 1, regra geral" },
      { value: "f-other", label: "Artigo 41, parágrafo 2" },
    ],
  };
  const changedOptions = {
    modalidade: [
      { value: "m-current-a", label: "Aposentadoria voluntária por tempo de contribuição regra A" },
      { value: "m-current-b", label: "Aposentadoria voluntária por tempo de contribuição regra B" },
    ],
    fundamento_legal: initialOptions.fundamento_legal,
  };
  const integration = await makeWorkerBackedChrome({
    snapshots: [
      snapshot({ options: initialOptions }),
      snapshot({ options: changedOptions }),
    ],
  });
  const { app, documentRef } = await startApp({ chromeApi: integration.panelChrome });
  documentRef.getElementById("dataset-file").files = [{ async text() { return JSON.stringify(dataset); } }];

  assert.equal(await app.importSelectedFile(), true);
  assert.ok(documentRef.getElementById("preview-body").querySelector('[data-kind="exact"]'));
  assert.ok(documentRef.getElementById("preview-body").querySelector('[data-kind="probable"]'));
  assert.equal(await app.fillAvailableFields(), true);

  const matchCalls = integration.panelCalls.filter((message) => message.type === MESSAGE_TYPES.GET_MATCH);
  assert.equal(matchCalls.length, 2);
  assert.deepEqual(matchCalls[0].payload.options, initialOptions);
  assert.deepEqual(matchCalls[1].payload.options, changedOptions);
  assert.ok(documentRef.getElementById("preview-body").querySelector('[data-kind="tie"]'));
  const apply = integration.forwardedToContent.find(({ message }) => message.type === MESSAGE_TYPES.APPLY_FIELDS);
  assert.ok(apply);
  const formSnapshots = integration.forwardedToContent.filter(({ message }) => message.type === MESSAGE_TYPES.GET_FORM_SNAPSHOT);
  assert.equal(apply.message.requestId, formSnapshots.at(-1).message.requestId);
  assert.equal(apply.message.payload.fields.modalidade, "m-current-a");
  assert.equal(apply.message.payload.matchKinds.modalidade, "tie");
  assert.equal(apply.message.payload.fields.fundamento_legal, "f-current");
  assert.equal(apply.message.payload.matchKinds.fundamento_legal, "probable");
  assert.equal(integration.forwardedToContent.every(({ message }) => !Object.hasOwn(message.payload, "dataset")), true);
});

test("sends only the seven current fields and validated matchKinds after a fresh pre-fill snapshot", async () => {
  const dataset = await makeDataset();
  const { app, documentRef, chromeApi } = await startApp({
    dataset,
    snapshots: [snapshot({ options: currentOptions() }), snapshot({ options: currentOptions() })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }, { record: dataset.records[0], matches: fullMatches(), reviewed: false }],
  });

  await app.fillAvailableFields();

  const apply = chromeApi.calls.find((message) => message.type === MESSAGE_TYPES.APPLY_FIELDS);
  assert.ok(apply);
  assert.deepEqual(Object.keys(apply.payload), ["fields", "matchKinds"]);
  assert.deepEqual(Object.keys(apply.payload.fields), PANEL_FIELD_ORDER);
  assert.deepEqual(Object.keys(apply.payload.matchKinds), PANEL_FIELD_ORDER);
  assert.equal(Object.hasOwn(apply.payload, "dataset"), false);
  assert.match(documentRef.getElementById("result-summary").textContent, /alterados: 7/iu);
});

test("surfaces a forwarded content-script failure instead of reporting a false completed fill", async () => {
  const dataset = await makeDataset();
  const { app, documentRef } = await startApp({
    dataset,
    snapshots: [snapshot({ options: currentOptions() }), snapshot({ options: currentOptions() })],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }],
    applyResponse: {
      ok: true,
      payload: {
        ok: false,
        payload: { changed: [], preserved: [], missing: [], disabled: [], errors: ["identity changed"] },
        error: { code: "APPLY_BLOCKED", message: "identity changed" },
      },
    },
  });

  await app.fillAvailableFields();

  assert.match(documentRef.getElementById("panel-message").textContent, /identity changed/iu);
  assert.doesNotMatch(documentRef.getElementById("panel-message").textContent, /concluído/iu);
});

test("preserves divergences and exposes one specific override requiring confirmation", async () => {
  const dataset = await makeDataset();
  const initial = snapshot({ options: currentOptions(), fields: { cargo: "Cargo já existente" } });
  const fresh = snapshot({ options: currentOptions(), fields: { cargo: "Cargo já existente" } });
  let confirmation = "";
  const { app, documentRef, chromeApi } = await startApp({
    dataset,
    snapshots: [initial, fresh, fresh],
    matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }, { record: dataset.records[0], matches: fullMatches(), reviewed: false }],
    confirmFn(message) { confirmation = message; return true; },
  });

  assert.equal(documentRef.getElementById("preview-body").querySelector('[data-role="override"]') !== null, true);
  assert.match(documentRef.getElementById("preview-body").textContent, /atual: Cargo já existente/iu);
  await app.fillAvailableFields();
  const apply = chromeApi.calls.find((message) => message.type === MESSAGE_TYPES.APPLY_FIELDS);
  assert.equal(Object.hasOwn(apply.payload.fields, "cargo"), true);
  assert.match(documentRef.getElementById("result-summary").textContent, /preservados: 1/iu);

  const override = documentRef.getElementById("preview-body").querySelector('[data-role="override"]');
  assert.ok(override);
  await app.overrideField("cargo");
  const overrideMessage = chromeApi.calls.find((message) => message.type === MESSAGE_TYPES.OVERRIDE_FIELD);
  assert.match(confirmation, /Cargo já existente/iu);
  assert.match(confirmation, /PROFESSOR PN - IV/iu);
  assert.ok(overrideMessage);
  assert.deepEqual(overrideMessage.payload, { field: "cargo", proposedValue: "PROFESSOR PN - IV" });
});

test("does not send an override when the field-specific confirmation is declined", async () => {
  const dataset = await makeDataset();
  const current = snapshot({ options: currentOptions(), fields: { cargo: "Cargo já existente" } });
  const { app, documentRef, chromeApi } = await startApp({ dataset, snapshots: [current], matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }], confirmFn: () => false });
  const override = documentRef.getElementById("preview-body").querySelector('[data-role="override"]');
  await override.dispatchEvent(new FakeEvent("click"));
  assert.equal(chromeApi.calls.some((message) => message.type === MESSAGE_TYPES.OVERRIDE_FIELD), false);
});

test("persists reviewed per process and interested and restores it on panel initialization", async () => {
  const dataset = await makeDataset();
  const current = snapshot({ options: currentOptions() });
  const first = await startApp({ dataset, snapshots: [current], matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }] });
  const checkbox = first.documentRef.getElementById("reviewed-checkbox");
  checkbox.checked = true;
  await first.app.setReviewed(true);
  const reviewedMessage = first.chromeApi.calls.find((message) => message.type === MESSAGE_TYPES.SET_REVIEWED);
  assert.deepEqual(reviewedMessage.payload, { processKey: "103439/2023", interestedNormalized: "maria de souza", reviewed: true });

  const second = await startApp({ dataset, snapshots: [current], matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: true }] });
  assert.equal(second.documentRef.getElementById("reviewed-checkbox").checked, true);
});

test("keeps the permanent warning in every main blocking, preview, divergence, and completed state", async () => {
  const dataset = await makeDataset();
  const transientStorage = makeStorageArea();
  const transientCalls = [];
  let releaseSnapshot;
  const pendingSnapshot = new Promise((resolveSnapshot) => { releaseSnapshot = resolveSnapshot; });
  const transient = await startApp({
    chromeApi: {
      storage: { local: transientStorage },
      runtime: {
        async sendMessage(message) {
          transientCalls.push(message);
          if (message.type === MESSAGE_TYPES.IMPORT_DATASET) {
            await transientStorage.set({ [STORAGE_KEYS.DATASET]: message.payload.dataset });
            return { ok: true, payload: { batchId: message.payload.dataset.batch.id } };
          }
          if (message.type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) return pendingSnapshot;
          throw new Error(`unexpected transient message ${message.type}`);
        },
      },
    },
  });
  transient.documentRef.getElementById("dataset-file").files = [{ async text() { return JSON.stringify(dataset); } }];
  const importPromise = transient.app.importSelectedFile();
  while (!transientCalls.some((message) => message.type === MESSAGE_TYPES.GET_FORM_SNAPSHOT)) {
    await new Promise((resolveTurn) => setImmediate(resolveTurn));
  }
  assert.equal(transient.app.getState().kind, PANEL_STATES.DATASET_IMPORTED);
  assert.equal(transient.documentRef.getElementById("permanent-warning").textContent, PERMANENT_WARNING);
  releaseSnapshot({ ok: false, error: { code: "FORM_NOT_FOUND", message: "form missing" } });
  await importPromise;

  const scenarios = [
    await startApp(),
    await startApp({ dataset, snapshots: [null] }),
    await startApp({ dataset, snapshots: [snapshot({ processKey: "999999/2024" })] }),
    await startApp({ dataset, snapshots: [snapshot({ interested: null })] }),
    await startApp({ dataset, snapshots: [snapshot({ interested: { original: "Pessoa Ausente", normalized: "pessoa ausente" } })] }),
    await startApp({ dataset, snapshots: [snapshot({ options: currentOptions() })], matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }] }),
    await startApp({ dataset, snapshots: [snapshot({ options: currentOptions(), fields: { cargo: "Cargo divergente" } })], matches: [{ record: dataset.records[0], matches: fullMatches(), reviewed: false }] }),
  ];
  const completed = await startApp({
    dataset,
    snapshots: [snapshot({ options: currentOptions() }), snapshot({ options: currentOptions() })],
    matches: [
      { record: dataset.records[0], matches: fullMatches(), reviewed: false },
      { record: dataset.records[0], matches: fullMatches(), reviewed: false },
    ],
  });
  await completed.app.fillAvailableFields();
  scenarios.push(completed);

  assert.deepEqual(scenarios.map(({ app }) => app.getState().kind), [
    PANEL_STATES.NO_DATASET,
    PANEL_STATES.INCOMPATIBLE_SCREEN,
    PANEL_STATES.PROCESS_NOT_FOUND,
    PANEL_STATES.INTERESTED_NOT_SELECTED,
    PANEL_STATES.INTERESTED_NOT_FOUND,
    PANEL_STATES.PREVIEW_READY,
    PANEL_STATES.EXISTING_DIVERGENCE,
    PANEL_STATES.FILLED_FOR_REVIEW,
  ]);
  for (const { documentRef } of scenarios) {
    assert.equal(documentRef.getElementById("permanent-warning").textContent, PERMANENT_WARNING);
  }
});

test("has structurally associated labels, keyboard focus styles, and disabled initial actions", () => {
  const html = readFileSync(resolve(ROOT, "sidepanel/panel.html"), "utf8");
  const css = readFileSync(resolve(ROOT, "sidepanel/panel.css"), "utf8");
  const js = readFileSync(resolve(ROOT, "sidepanel/panel.js"), "utf8");
  const inputTags = [...html.matchAll(/<input\b[^>]*>/giu)].map(([tag]) => tag);
  const inputIds = new Set(inputTags.map((tag) => /\bid="([^"]+)"/iu.exec(tag)?.[1]).filter(Boolean));
  const labelTargets = [...html.matchAll(/<label\b[^>]*\bfor="([^"]+)"[^>]*>/giu)].map((match) => match[1]);
  const buttonLabels = [...html.matchAll(/<button\b[^>]*>([^<]+)<\/button>/giu)].map((match) => match[1].trim());

  assert.deepEqual(labelTargets, ["bridge-base-url", "bridge-pairing-code", "search-process", "search-interested", "automation-marker", "reviewed-checkbox"]);
  assert.equal(labelTargets.every((target) => inputIds.has(target)), true);
  assert.match(inputTags.find((tag) => /\bid="dataset-file"/iu.test(tag)), /\baria-label="[^"]+"/iu);
  assert.equal(buttonLabels.length, 5);
  assert.equal(buttonLabels.every(Boolean), true);
  assert.match(inputTags.find((tag) => /\bid="reviewed-checkbox"/iu.test(tag)), /\bdisabled\b/iu);
  assert.match(html, /<button\b[^>]*\bid="fill-button"[^>]*\bdisabled\b/iu);
  assert.match(css, /button:focus-visible\s*,\s*input:focus-visible\s*\{/u);
  assert.match(css, /button:disabled\s*\{/u);
  assert.match(html, /Modo manual: o preenchimento permanece para revisão/u);
  assert.match(html, /aria-live="polite"/u);
  assert.doesNotMatch(`${html}\n${css}\n${js}`, /localStorage|fetch\s*\(|eval\s*\(|clipboard|chrome\.tabs/u);
});
