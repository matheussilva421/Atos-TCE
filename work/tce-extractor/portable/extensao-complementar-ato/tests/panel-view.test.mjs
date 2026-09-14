import test from "node:test";
import assert from "node:assert/strict";

import { buildPanelViewModel, renderPanelView } from "../sidepanel/panel-view.js";

const IDENTITY = {
  processKey: "103439/2023",
  interestedNormalized: "ana da silva",
  interestedOriginal: "Ana da Silva",
};

function record() {
  return {
    process: { key: IDENTITY.processKey },
    interested: { original: IDENTITY.interestedOriginal, normalized: IDENTITY.interestedNormalized },
    fields: {
      modalidade: { source_value: "Especial", form_value: "Especial", status: "found", confidence: "high", citation: { page: 2 } },
      fundamento_legal: { source_value: "Art. 6º da EC 41/2003", form_value: "Art. 6º da EC 41/2003", status: "found", confidence: "high", citation: { page: 2 } },
      data_publicacao_doe: { source_value: "07/02/2020", form_value: "07/02/2020", status: "found", confidence: "high", citation: { page: 2 } },
      cargo: { source_value: "Professor", form_value: "Professor", status: "found", confidence: "high", citation: { page: 2 } },
      matricula: { source_value: "103", form_value: "103", status: "found", confidence: "high", citation: { page: 2 } },
      data_nascimento: { source_value: "30/04/1967", form_value: "30/04/1967", status: "found", confidence: "high", citation: { page: 2 } },
      genero: { source_value: "Feminino", form_value: "Feminino", status: "found", confidence: "high", citation: { page: 2 } },
    },
  };
}

function snapshot() {
  return {
    process: { key: IDENTITY.processKey },
    interested: { original: IDENTITY.interestedOriginal, normalized: IDENTITY.interestedNormalized },
    fields: Object.fromEntries(Object.keys(record().fields).map((field) => [field, { value: record().fields[field].form_value, disabled: false, readOnly: false }])),
    options: {},
  };
}

test("view model keeps similarity separate from portal confirmation", () => {
  const model = buildPanelViewModel({
    record: record(),
    snapshot: snapshot(),
    matches: { fundamento_legal: { kind: "probable", legalDecision: { status: "selected", method: "similarity", reasons: ["sem correspondência exata"] } } },
    run: { status: "running", marker: "PROFESSOR - IPERN - 2 RUBRICAS", items: [{ identity: IDENTITY, state: "filled" }] },
    connection: { connected: true, automationAvailable: true },
    selectedView: "execution",
    mode: "automatic",
  });

  assert.equal(model.legalDecision.method, "similarity");
  assert.equal(model.runSummary.confirmed, 0);
  assert.equal(model.run.marker, "PROFESSOR - IPERN - 2 RUBRICAS");
  assert.equal(model.actions.some((action) => action.id === "resend"), false);
  assert.match(model.banner.message, /lote complementa/u);
});

test("uncertain run exposes reconciliation guidance without resend", () => {
  const model = buildPanelViewModel({
    record: record(),
    snapshot: snapshot(),
    matches: {},
    run: { status: "paused", items: [{ identity: IDENTITY, state: "unconfirmed" }] },
    connection: { connected: true, automationAvailable: true },
    selectedView: "execution",
    mode: "automatic",
  });

  assert.equal(model.runSummary.unconfirmed, 1);
  assert.equal(model.actions.some((action) => action.id === "resend"), false);
  assert.match(model.banner.message, /confirmar|concilia/iu);
});

test("does not mark equivalent civil date representations as divergent", () => {
  const base = snapshot();
  const model = buildPanelViewModel({
    record: record(),
    snapshot: {
      ...base,
      fields: {
        ...base.fields,
        data_publicacao_doe: { ...base.fields.data_publicacao_doe, value: "2020-02-07" },
        data_nascimento: { ...base.fields.data_nascimento, value: "1967-04-30" },
      },
    },
  });

  assert.equal(model.fields.find((field) => field.id === "data_publicacao_doe").divergent, false);
  assert.equal(model.fields.find((field) => field.id === "data_nascimento").divergent, false);
});

test("keeps an invalid date divergent when its text is repeated", () => {
  const invalid = "31.02.2020";
  const current = snapshot();
  const source = record();
  source.fields.data_publicacao_doe = {
    ...source.fields.data_publicacao_doe,
    source_value: invalid,
    form_value: invalid,
  };
  current.fields.data_publicacao_doe = {
    ...current.fields.data_publicacao_doe,
    value: invalid,
  };
  const model = buildPanelViewModel({ record: source, snapshot: current });

  assert.equal(model.fields.find((field) => field.id === "data_publicacao_doe").divergent, true);
});

test("renderPanelView uses accessible tabs, text nodes, and field cards", () => {
  const root = {
    ownerDocument: {
      createElement(tagName) {
        return {
          tagName,
          children: [],
          attributes: {},
          listeners: {},
          textContent: "",
          setAttribute(name, value) { this.attributes[name] = String(value); },
          append(...children) { this.children.push(...children); },
          addEventListener(type, listener) { this.listeners[type] = listener; },
          dispatchEvent(event) { this.listeners[event.type]?.(event); },
          focus() { this.focused = true; },
        };
      },
    },
    replaceChildren(...children) { this.children = children; },
    append(...children) { this.children = [...(this.children ?? []), ...children]; },
  };
  const model = buildPanelViewModel({ record: record(), snapshot: snapshot(), matches: {}, selectedView: "details" });
  renderPanelView(root, model, {});
  const text = JSON.stringify(root);
  assert.match(text, /Fundamentação/u);
  assert.match(text, /Professor/u);
  assert.doesNotMatch(text, /innerHTML/u);
});

test("renderPanelView renders execution and history into their separate tab roots", () => {
  const root = {
    ownerDocument: {
      createElement(tagName) {
        return {
          tagName,
          children: [],
          attributes: {},
          listeners: {},
          textContent: "",
          setAttribute(name, value) { this.attributes[name] = String(value); },
          append(...children) { this.children.push(...children); },
          addEventListener(type, listener) { this.listeners[type] = listener; },
          dispatchEvent(event) { this.listeners[event.type]?.(event); },
          focus() { this.focused = true; },
        };
      },
    },
    replaceChildren(...children) { this.children = children; },
    append(...children) { this.children = [...(this.children ?? []), ...children]; },
  };
  const execution = { ...root, children: [] };
  const history = { ...root, children: [] };
  renderPanelView({ details: root, execution, history }, buildPanelViewModel({ record: record(), snapshot: snapshot() }), {});
  assert.match(JSON.stringify(root), /Fundamentação/u);
  assert.match(JSON.stringify(execution), /Execução/u);
  assert.match(JSON.stringify(history), /Histórico/u);
});

test("history renders persisted chronology separately from report download", () => {
  const root = {
    ownerDocument: {
      createElement(tagName) {
        return {
          tagName,
          children: [],
          attributes: {},
          listeners: {},
          textContent: "",
          setAttribute(name, value) { this.attributes[name] = String(value); },
          append(...children) { this.children.push(...children); },
          addEventListener(type, listener) { this.listeners[type] = listener; },
          focus() {},
        };
      },
    },
    replaceChildren(...children) { this.children = children; },
    append(...children) { this.children = [...(this.children ?? []), ...children]; },
  };
  const model = buildPanelViewModel({
    selectedView: "history",
    historyNextCursor: "opaque-cursor",
    history: [{
      run_id: "run-1",
      created_at: "2026-09-09T12:00:00Z",
      state: "paused",
      totals: { confirmed: 1 },
      events: [{ type: "queue_frozen", created_at: "2026-09-09T12:01:00Z" }],
    }],
  });
  const details = { ...root, children: [] };
  const execution = { ...root, children: [] };
  const history = { ...root, children: [] };
  renderPanelView({ details, execution, history }, model, { openDetails() {}, openReport() {} });
  const text = JSON.stringify(history);
  assert.match(text, /Abrir detalhes/u);
  assert.match(text, /queue_frozen/u);
  assert.match(text, /HTML/u);
  assert.match(text, /Carregar mais/u);
});
