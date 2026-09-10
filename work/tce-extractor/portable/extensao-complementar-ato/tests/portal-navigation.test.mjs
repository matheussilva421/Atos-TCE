import test from "node:test";
import assert from "node:assert/strict";

import {
  detectPortalScreen,
  executeNavigation,
  createMessageHandler,
  snapshotPortalScreen,
} from "../content/portal-navigation.js";

class FakeElement {
  constructor(tagName = "div", { id = "", text = "", attrs = {}, value = "" } = {}) {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this._text = text;
    this.attributes = { ...attrs };
    if (id) this.attributes.id = id;
    this.value = value;
    this.checked = false;
    this.disabled = false;
    this.hidden = false;
    this.children = [];
    this.parentElement = null;
    this.ownerDocument = null;
    this.clickCount = 0;
    this.onClick = null;
    this.dataset = Object.fromEntries(Object.entries(this.attributes)
      .filter(([key]) => key.startsWith("data-"))
      .map(([key, child]) => [key.slice(5).replace(/-([a-z])/gu, (_, letter) => letter.toUpperCase()), child]));
  }

  get textContent() {
    return [this._text, ...this.children.map((child) => child.textContent)].filter(Boolean).join(" ");
  }

  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }

  append(...children) {
    for (const child of children) {
      child.parentElement = this;
      child.ownerDocument = this.ownerDocument;
      this.children.push(child);
    }
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === "id") this.id = String(value);
  }

  getAttribute(name) {
    return Object.hasOwn(this.attributes, name) ? this.attributes[name] : null;
  }

  matches(selector) {
    const normalized = selector.trim();
    if (normalized.includes(",")) return normalized.split(",").some((part) => this.matches(part));
    const descendant = normalized.split(/\s+/u);
    if (descendant.length > 1) return this.matches(descendant.at(-1));
    const idMatch = normalized.match(/^#([\w-]+)$/u);
    if (idMatch) return this.id === idMatch[1];
    const classMatch = normalized.match(/^\.([\w-]+)$/u);
    if (classMatch) return getAttributeForTest(this, "class").split(/\s+/u).includes(classMatch[1]);
    const tagMatch = normalized.match(/^([a-z][\w-]*)?/iu);
    const tag = tagMatch?.[1];
    if (tag && this.tagName !== tag.toUpperCase()) return false;
    const attrMatches = [...normalized.matchAll(/\[([\w-]+)(?:=["']?([^\]"']+)["']?)?\]/gu)];
    return attrMatches.every(([, name, expected]) => (
      Object.hasOwn(this.attributes, name)
      && (expected === undefined || this.attributes[name] === expected)
    ));
  }

  querySelectorAll(selector) {
    const result = [];
    const walk = (node) => {
      for (const child of node.children) {
        if (child.matches(selector)) result.push(child);
        walk(child);
      }
    };
    walk(this);
    return result;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] ?? null;
  }

  closest(selector) {
    let current = this;
    while (current) {
      if (current.matches(selector)) return current;
      current = current.parentElement;
    }
    return null;
  }

  click() {
    this.clickCount += 1;
    this.onClick?.();
  }
}

function getAttributeForTest(element, name) {
  return Object.hasOwn(element.attributes, name) ? String(element.attributes[name]) : "";
}

class FakeDocument extends FakeElement {
  constructor({ screen, page = "", sector = "aposentadorias" } = {}) {
    super("document");
    this.defaultView = { location: { href: `https://portal.test/${screen}?page=${page}` } };
    this.documentElement = new FakeElement("html", { attrs: { "data-screen": screen, "data-sector": sector } });
    this.body = new FakeElement("body");
    this.append(this.documentElement);
    this.documentElement.append(this.body);
    this.screen = screen;
    this.page = page;
    this.ownerDocument = this;
    this.documentElement.ownerDocument = this;
    this.body.ownerDocument = this;
  }

  getElementById(id) {
    return this.querySelector(`#${id}`);
  }

  setSurface(surface) {
    this.body.children = [];
    this.screen = surface.screen;
    this.page = surface.page ?? this.page;
    this.documentElement.attributes["data-screen"] = this.screen;
    this.documentElement.attributes["data-page"] = this.page;
    this.documentElement.dataset.screen = this.screen;
    this.documentElement.dataset.page = this.page;
    this.body.append(...surface.children);
    this.defaultView.location.href = `https://portal.test/${this.screen}?page=${this.page}`;
  }
}

function cell(text, attrs = {}) {
  return new FakeElement("td", { text, attrs });
}

function identity(processKey, interested, portalActId = null) {
  return {
    processKey,
    interestedOriginal: interested,
    interestedNormalized: interested.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase(),
    portalActId,
  };
}

function buildListDocument(page, rows, { hasNext = true } = {}) {
  const documentRef = new FakeDocument({ screen: "list", page });
  const table = new FakeElement("table", { id: "tbproc01" });
  const tbody = new FakeElement("tbody");
  table.append(tbody);
  for (const rowData of rows) {
    const row = new FakeElement("tr", { attrs: { "data-process-key": rowData.processKey } });
    const link = new FakeElement("a", { text: "Complementar Ato", attrs: { href: `/act/${rowData.processKey}` } });
    link.onClick = () => {
      documentRef.setSurface(buildInterestedSurface(documentRef, rowData));
    };
    row.append(cell(rowData.processKey), cell(rowData.interested), cell("Ação"));
    row.children[1].setAttribute("data-interested-name", rowData.interested);
    row.append(link);
    tbody.append(row);
  }
  const nav = new FakeElement("nav", { attrs: { "aria-label": "Paginação" } });
  const current = new FakeElement("a", { text: page, attrs: { "aria-current": "page" } });
  nav.append(current);
  if (hasNext) {
    const next = new FakeElement("a", { text: "Próxima", attrs: { "data-action": "next-page" } });
    next.onClick = () => documentRef.setSurface(buildListSurface(documentRef, Number(page) + 1));
    nav.append(next);
  }
  documentRef.body.append(table, nav);
  return documentRef;
}

function addMarkerFilter(documentRef, selectedLabel = "Todos os marcadores") {
  const form = new FakeElement("form", { id: "process-filter" });
  const label = new FakeElement("label", { text: "Marcador:" });
  const select = new FakeElement("select", { id: "marcador" });
  const all = new FakeElement("option", { text: "Todos os marcadores", value: "" });
  const target = new FakeElement("option", { text: "PROFESSOR - IPERN - 2 RUBRICAS", value: "marker-2" });
  all.selected = selectedLabel === all.textContent;
  target.selected = selectedLabel === target.textContent;
  select.value = target.selected ? target.value : all.value;
  select.append(all, target);
  const consult = new FakeElement("button", { text: "Consultar", attrs: { "data-action": "consultar" } });
  form.append(label, select, consult);
  documentRef.body.append(form);
  return { form, select, consult };
}

function buildListSurface(documentRef, page) {
  const pages = {
    1: [
      { processKey: "103401/2023", interested: "Ana da Silva" },
      { processKey: "103402/2023", interested: "Bruno de Souza" },
    ],
    2: [
      { processKey: "103403/2023", interested: "Carla de Lima" },
      { processKey: "103404/2023", interested: "Diego Alves" },
    ],
    3: [{ processKey: "103405/2023", interested: "Érica Santos" }],
  };
  const next = page < 3;
  const rebuilt = buildListDocument(page, pages[page], { hasNext: next });
  rebuilt.defaultView = documentRef.defaultView;
  const rebuiltRows = rebuilt.querySelectorAll("tr").filter((row) => row.querySelector("a"));
  rebuiltRows.forEach((row, index) => {
    row.querySelector("a").onClick = () => documentRef.setSurface(buildInterestedSurface(documentRef, pages[page][index]));
  });
  const rebuiltNext = rebuilt.querySelector('[data-action="next-page"]');
  if (rebuiltNext) rebuiltNext.onClick = () => documentRef.setSurface(buildListSurface(documentRef, Number(page) + 1));
  return { screen: "list", page, children: rebuilt.body.children };
}

function buildInterestedSurface(documentRef, rowData) {
  documentRef.documentElement.setAttribute("data-process-key", rowData.processKey);
  const table = new FakeElement("table", { id: "PessoasAssocicadas" });
  const row = new FakeElement("tr");
  const radio = new FakeElement("input", {
    attrs: { type: "radio", "data-interested-name": rowData.interested },
  });
  radio.onClick = () => { radio.checked = true; };
  row.append(radio, cell(rowData.interested));
  table.append(row);
  const back = new FakeElement("a", { text: "Voltar", attrs: { "data-action": "return-list" } });
  back.onClick = () => documentRef.setSurface(buildListSurface(documentRef, 1));
  return { screen: "interested", page: "", children: [table, back] };
}

function buildFormDocument() {
  const documentRef = new FakeDocument({ screen: "form" });
  const form = new FakeElement("form", { id: "complementarAtoForm" });
  form.append(
    new FakeElement("input", { id: "txtNumeroProcesso", value: "103401" }),
    new FakeElement("input", { id: "txtAnoProcesso", value: "2023" }),
  );
  documentRef.body.append(form);
  return documentRef;
}

function buildButtonsDocument() {
  const documentRef = new FakeDocument({ screen: "buttons" });
  documentRef.body.append(
    new FakeElement("button", { text: "Complementar Ato", attrs: { "data-action": "signal-only" } }),
    new FakeElement("button", { text: "Voltar", attrs: { "data-action": "return-list" } }),
  );
  return documentRef;
}

test("detects portal screens without requiring the seven form sentinels", () => {
  assert.equal(detectPortalScreen(buildListDocument("1", [])), "list");
  const interestedDocument = new FakeDocument({ screen: "interested" });
  interestedDocument.setSurface(buildInterestedSurface(interestedDocument, {
    processKey: "103401/2023",
    interested: "Ana da Silva",
  }));
  assert.equal(detectPortalScreen(interestedDocument), "interested");
  assert.equal(detectPortalScreen(buildFormDocument()), "form");
  assert.equal(detectPortalScreen(buildButtonsDocument()), "buttons");
  assert.equal(detectPortalScreen(new FakeDocument({ screen: "unknown" })), "unknown");
});

test("snapshots identities and observed actions without retaining nodes or URLs", () => {
  const documentRef = buildListDocument("1", [
    { processKey: "103401/2023", interested: "Ana da Silva" },
    { processKey: "103402/2023", interested: "Bruno de Souza" },
  ]);
  const snapshot = snapshotPortalScreen(documentRef);
  assert.equal(snapshot.role, "list");
  assert.equal(snapshot.generation, 1);
  assert.deepEqual(snapshot.identities.map(({ processKey, interestedNormalized }) => ({ processKey, interestedNormalized })), [
    { processKey: "103401/2023", interestedNormalized: "ana da silva" },
    { processKey: "103402/2023", interestedNormalized: "bruno de souza" },
  ]);
  assert.ok(snapshot.actions.some((action) => action.action === "next_page"));
  assert.ok(snapshot.actions.every((action) => !Object.hasOwn(action, "url") && !Object.hasOwn(action, "node")));
});

test("observes the selected marker and exposes a guarded marker-filter action", () => {
  const documentRef = buildListDocument("1", [{ processKey: "103401/2023", interested: "Ana da Silva" }]);
  const { select } = addMarkerFilter(documentRef, "PROFESSOR - IPERN - 2 RUBRICAS");
  const snapshot = snapshotPortalScreen(documentRef);
  assert.deepEqual(snapshot.marker, {
    label: "PROFESSOR - IPERN - 2 RUBRICAS",
    value: "marker-2",
  });
  assert.equal(snapshot.identities[0].needsComplement, true);
  assert.ok(snapshot.actions.some((action) => action.action === "filter_marker"));
  assert.equal(select.value, "marker-2");
});

test("selects the requested marker and clicks only the scoped Consultar control", async () => {
  const documentRef = buildListDocument("1", [{ processKey: "103401/2023", interested: "Ana da Silva" }]);
  const { select, consult } = addMarkerFilter(documentRef);
  consult.onClick = () => {
    select.value = "marker-2";
    select.querySelectorAll("option")[0].selected = false;
    select.querySelectorAll("option")[1].selected = true;
  };
  const before = snapshotPortalScreen(documentRef);
  const result = await executeNavigation(documentRef, {
    action: "filter_marker",
    marker: "PROFESSOR - IPERN - 2 RUBRICAS",
    expected_generation: before.generation,
    timeoutMs: 50,
  });
  assert.equal(result.ok, true);
  assert.equal(select.value, "marker-2");
  assert.equal(consult.clickCount, 1);
  assert.equal(result.snapshot.marker.label, "PROFESSOR - IPERN - 2 RUBRICAS");
});

test("keeps a row without a canonical identity as pending without exposing it as an action", () => {
  const documentRef = buildListDocument("1", [{ processKey: "", interested: "" }], { hasNext: false });
  const snapshot = snapshotPortalScreen(documentRef);

  assert.equal(snapshot.role, "list");
  assert.equal(snapshot.identities.length, 1);
  assert.deepEqual(snapshot.identities[0], {
    processKey: null,
    interestedOriginal: "",
    interestedNormalized: null,
    portalActId: null,
    pending: true,
  });
  assert.equal(snapshot.actions.some((action) => action.action === "open_act"), false);
});

test("opens the action link belonging to the requested process row", async () => {
  const documentRef = buildListDocument("1", [
    { processKey: "103401/2023", interested: "Ana da Silva" },
    { processKey: "103402/2023", interested: "Bruno de Souza" },
  ]);
  const targetRow = documentRef.querySelectorAll("tr").find((row) => row.textContent.includes("103402/2023"));
  const targetLink = targetRow.querySelector("a");
  const result = await executeNavigation(documentRef, {
    action: "open_act",
    identity: identity("103402/2023", "Bruno de Souza"),
    expected_generation: 1,
  });
  assert.equal(result.ok, true);
  assert.equal(detectPortalScreen(documentRef), "interested");
  assert.equal(targetLink.clickCount, 1);
});

test("chooses the semantic Complementar Ato icon when a process row has multiple actions", async () => {
  const documentRef = new FakeDocument({ screen: "list", page: "1" });
  const table = new FakeElement("table", { id: "tbproc01" });
  const tbody = new FakeElement("tbody");
  const row = new FakeElement("tr", { attrs: { "data-process-key": "103401/2023" } });
  row.append(cell("103401/2023"), cell("Ana da Silva"));
  row.children[1].setAttribute("data-interested-name", "Ana da Silva");
  const details = new FakeElement("a", { text: "Detalhes", attrs: { href: "/processo/103401" } });
  const complement = new FakeElement("a", { attrs: { href: "/SISTEMAS/PROCESSO/ComplementarAto.asp" } });
  complement.append(new FakeElement("img", { attrs: { alt: "Complementar Ato" } }));
  complement.onClick = () => documentRef.setSurface(buildInterestedSurface(documentRef, { processKey: "103401/2023", interested: "Ana da Silva" }));
  row.append(details, complement);
  tbody.append(row);
  table.append(tbody);
  documentRef.body.append(table);
  const result = await executeNavigation(documentRef, {
    action: "open_act",
    identity: identity("103401/2023", "Ana da Silva"),
    expected_generation: snapshotPortalScreen(documentRef).generation,
  });
  assert.equal(result.ok, true);
  assert.equal(details.clickCount, 0);
  assert.equal(complement.clickCount, 1);
});

test("reads Interessado from its headed column when legacy action icons precede it", () => {
  const documentRef = new FakeDocument({ screen: "list", page: "1" });
  const table = new FakeElement("table", { id: "tbproc01" });
  const head = new FakeElement("thead");
  const headerRow = new FakeElement("tr");
  headerRow.append(...["", "", "", "Processo", "Ação", "Origem", "Relator", "Interessado", "Câmara"].map((value) => new FakeElement("th", { text: value })));
  head.append(headerRow);
  const body = new FakeElement("tbody");
  const row = new FakeElement("tr", { attrs: { "data-process-key": "103401/2023" } });
  row.append(...["", "★", "P", "103401/2023", "", "IPERN", "Relator", "Ana da Silva", "PLENO"].map((value) => cell(value)));
  const action = new FakeElement("a", { attrs: { href: "/SISTEMAS/PROCESSO/ComplementarAto.asp" } });
  action.append(new FakeElement("img", { attrs: { alt: "Complementar Ato" } }));
  row.append(action);
  body.append(row);
  table.append(head, body);
  documentRef.body.append(table);
  const snapshot = snapshotPortalScreen(documentRef);
  const process = snapshot.identities.find((candidate) => candidate.processKey === "103401/2023");
  assert.equal(process.interestedNormalized, "ana da silva");
  assert.equal(process.needsComplement, true);
});

test("reads Interessado from a legacy td header row used by the restricted portal", () => {
  const documentRef = new FakeDocument({ screen: "list", page: "1" });
  const table = new FakeElement("table", { id: "tbproc01" });
  const head = new FakeElement("thead");
  const headerRow = new FakeElement("tr");
  headerRow.append(...["", "", "", "Processo", "Ação", "Origem", "Relator", "Interessado", "Câmara"].map((value) => cell(value)));
  head.append(headerRow);
  const body = new FakeElement("tbody");
  const row = new FakeElement("tr", { attrs: { "data-process-key": "103401/2023" } });
  row.append(...["", "↻", "P", "103401/2023", "", "IPERN", "Relator", "Ana da Silva", "PLENO"].map((value) => cell(value)));
  const action = new FakeElement("a", { attrs: { href: "/SISTEMAS/PROCESSO/ComplementarAto.asp" } });
  action.append(new FakeElement("img", { attrs: { alt: "Complementar Ato" } }));
  row.append(action);
  body.append(row);
  table.append(head, body);
  documentRef.body.append(table);

  const process = snapshotPortalScreen(documentRef).identities.find((candidate) => candidate.processKey === "103401/2023");
  assert.equal(process.interestedNormalized, "ana da silva");
  assert.equal(process.needsComplement, true);
});

test("selects one interested person and supports return to the list", async () => {
  const documentRef = buildListDocument("1", [{ processKey: "103401/2023", interested: "Ana da Silva" }]);
  documentRef.querySelector("a").click();
  const afterSelect = await executeNavigation(documentRef, {
    action: "select_interested",
    identity: identity("103401/2023", "Ana da Silva"),
    expected_generation: snapshotPortalScreen(documentRef).generation,
  });
  assert.equal(afterSelect.ok, true);
  assert.equal(documentRef.querySelector('input[type="radio"]').checked, true);
  assert.deepEqual(afterSelect.snapshot.actions.find((action) => action.action === "return_list").identity, identity("103401/2023", "Ana da Silva"));
  const returned = await executeNavigation(documentRef, {
    action: "return_list",
    identity: identity("103401/2023", "Ana da Silva"),
    expected_generation: snapshotPortalScreen(documentRef).generation,
  });
  assert.equal(returned.ok, true);
  assert.equal(detectPortalScreen(documentRef), "list");
});

test("echoes the navigation request token in the command response", async () => {
  const documentRef = buildListDocument("1", [{ processKey: "103401/2023", interested: "Ana da Silva" }]);
  const handler = createMessageHandler(documentRef);
  const response = await handler({
    type: "PORTAL_NAVIGATE",
    requestId: "navigation-token-3",
    payload: {
      action: "open_act",
      identity: identity("103401/2023", "Ana da Silva"),
      expected_generation: snapshotPortalScreen(documentRef).generation,
    },
  });

  assert.equal(response.ok, true);
  assert.equal(response.navigationToken, "navigation-token-3");
});

test("advances through three synthetic pages, invalidates generation on rerender, and never repeats an unverified click", async () => {
  const documentRef = buildListDocument("1", [
    { processKey: "103401/2023", interested: "Ana da Silva" },
    { processKey: "103402/2023", interested: "Bruno de Souza" },
  ]);
  const first = snapshotPortalScreen(documentRef);
  const second = await executeNavigation(documentRef, {
    action: "next_page",
    expected_generation: first.generation,
  });
  assert.equal(second.ok, true);
  assert.equal(second.snapshot.identities.length, 2);
  const third = await executeNavigation(documentRef, {
    action: "next_page",
    expected_generation: second.snapshot.generation,
  });
  assert.equal(third.ok, true);
  assert.equal(third.snapshot.identities.length, 1);
  assert.equal(third.snapshot.identities[0].processKey, "103405/2023");

  const stale = await executeNavigation(documentRef, {
    action: "next_page",
    expected_generation: first.generation,
  });
  assert.equal(stale.ok, false);
  assert.equal(stale.error.code, "STALE_GENERATION");

  const noProgressDocument = buildListDocument("1", [
    { processKey: "103401/2023", interested: "Ana da Silva" },
  ], { hasNext: true });
  const next = noProgressDocument.querySelector('[data-action="next-page"]');
  next.onClick = () => {};
  const noProgress = await executeNavigation(noProgressDocument, {
    action: "next_page",
    expected_generation: snapshotPortalScreen(noProgressDocument).generation,
    timeoutMs: 1,
  });
  assert.equal(noProgress.ok, false);
  assert.equal(noProgress.error.code, "NAVIGATION_TIMEOUT");
  assert.equal(next.clickCount, 1);
});

test("waits for a later mutation before using its single navigation reread", async () => {
  const documentRef = buildListDocument("1", [
    { processKey: "103401/2023", interested: "Ana da Silva" },
    { processKey: "103402/2023", interested: "Bruno de Souza" },
  ]);
  let notifyMutation = null;
  documentRef.defaultView.MutationObserver = class {
    constructor(callback) {
      notifyMutation = callback;
    }

    observe() {}

    disconnect() {}
  };
  const next = documentRef.querySelector('[data-action="next-page"]');
  next.onClick = () => setTimeout(() => {
    documentRef.setSurface(buildListSurface(documentRef, 2));
    notifyMutation?.();
  }, 0);

  const result = await executeNavigation(documentRef, {
    action: "next_page",
    expected_generation: snapshotPortalScreen(documentRef).generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, true);
  assert.equal(result.rereads, 1);
  assert.equal(next.clickCount, 1);
});

test("rejects a global Complementar Ato action and unsupported navigation", async () => {
  const documentRef = buildButtonsDocument();
  const rejected = await executeNavigation(documentRef, {
    action: "open_act",
    identity: identity("103401/2023", "Ana da Silva"),
    expected_generation: snapshotPortalScreen(documentRef).generation,
  });
  assert.equal(rejected.ok, false);
  assert.equal(rejected.error.code, "ROW_ACTION_NOT_FOUND");
  assert.equal(documentRef.querySelectorAll("button")[0].clickCount, 0);

  const unsupported = await executeNavigation(documentRef, {
    action: "submit",
    expected_generation: snapshotPortalScreen(documentRef).generation,
  });
  assert.equal(unsupported.ok, false);
  assert.equal(unsupported.error.code, "UNSUPPORTED_ACTION");
});
