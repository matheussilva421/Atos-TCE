import test from "node:test";
import assert from "node:assert/strict";

import {
  detectPortalScreen,
  executeNavigation,
  createMessageHandler,
  installPortalNavigation,
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
    const hasMatch = normalized.match(/^(.+):has\((.+)\)$/u);
    if (hasMatch) return this.matches(hasMatch[1]) && Boolean(this.querySelector(hasMatch[2]));
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

function buildRestrictedListWithFormIdentityInputs() {
  const documentRef = new FakeDocument({ screen: "list" });
  const form = new FakeElement("form", { id: "process-filter" });
  form.append(
    new FakeElement("input", { id: "txtNumeroProcesso", value: "100271" }),
    new FakeElement("input", { id: "txtAnoProcesso", value: "2026" }),
  );
  const table = new FakeElement("table", { id: "tbproc01" });
  const row = new FakeElement("tr", { attrs: { "data-process-key": "100271/2026" } });
  row.append(cell("100271/2026"), cell("JOSAFA INACIO DE LIMA"));
  table.append(row);
  const filterTable = new FakeElement("table");
  const filterRow = new FakeElement("tr");
  filterRow.append(new FakeElement("input", { attrs: { type: "radio", id: "txtDividaAtiva" } }));
  filterTable.append(filterRow);
  documentRef.body.append(form, table, filterTable);
  return documentRef;
}

function buildRestrictedInitialActDocument({ selected = false, withTopClose = false } = {}) {
  const documentRef = buildFormDocument();
  const form = documentRef.getElementById("complementarAtoForm");
  const interestedTable = new FakeElement("table", { id: "PessoasAssocicadas" });
  const row = new FakeElement("tr");
  const radio = new FakeElement("input", {
    attrs: { type: "radio", name: "escolha" },
  });
  radio.checked = selected;
  row.append(radio, cell("Núzia Maria Barbosa"), cell("CPF-SANITIZADO-01"), cell("Interessado"));
  interestedTable.append(row);
  form.append(interestedTable);
  documentRef.documentElement.setAttribute("data-process-key", "101675/2026");
  let close = null;
  if (withTopClose) {
    const topDocument = new FakeDocument({ screen: "shell" });
    const tab = new FakeElement("li");
    close = new FakeElement("a", { attrs: { class: "tabs-close" } });
    close.onClick = () => { topDocument.body.children = []; };
    tab.append(
      new FakeElement("a", { text: "Complementar Ato", attrs: { class: "tabs-inner" } }),
      close,
    );
    topDocument.body.append(tab);
    const listDocument = buildListDocument("1", [{ processKey: "103401/2023", interested: "Ana da Silva" }], { hasNext: false });
    topDocument.defaultView.frames = [{ document: listDocument }];
    documentRef.defaultView.top = { document: topDocument, frames: topDocument.defaultView.frames };
  }
  return { documentRef, radio, close };
}

function buildButtonsDocument() {
  const documentRef = new FakeDocument({ screen: "buttons" });
  documentRef.body.append(
    new FakeElement("button", { text: "Complementar Ato", attrs: { "data-action": "signal-only" } }),
    new FakeElement("button", { text: "Voltar", attrs: { "data-action": "return-list" } }),
  );
  return documentRef;
}

// The browser's window.frames is array-like and exposes no Symbol.iterator;
// regression fixtures must exercise that exact shape instead of a real array.
function arrayLikeFrames(...windows) {
  const frames = { length: windows.length };
  windows.forEach((windowRef, index) => {
    frames[index] = windowRef;
  });
  return frames;
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

test("does not misclassify the restricted process list as a form when it reuses process inputs", () => {
  assert.equal(detectPortalScreen(buildRestrictedListWithFormIdentityInputs()), "list");
});

test("recognizes the restricted addtabs action as Complementar Ato without an href", () => {
  const documentRef = new FakeDocument({ screen: "list" });
  const table = new FakeElement("table", { id: "tbproc01" });
  const row = new FakeElement("tr", { attrs: { "data-process-key": "100271/2026" } });
  row.append(cell("100271/2026"), cell("JOSAFA INACIO DE LIMA"));
  row.append(new FakeElement("a"), new FakeElement("a"));
  row.append(new FakeElement("a", {
    attrs: { onclick: "addtabsinformacao('Complementar Ato', 'ComplementarAto.asp')" },
  }));
  table.append(row);
  documentRef.body.append(table);

  const snapshot = snapshotPortalScreen(documentRef);

  assert.equal(snapshot.actions.some((action) => action.action === "open_act"), true);
});

test("detects the restricted portal's initial Complementar Ato screen as interested selection", () => {
  const { documentRef } = buildRestrictedInitialActDocument();
  const snapshot = snapshotPortalScreen(documentRef);

  assert.equal(snapshot.role, "interested");
  assert.deepEqual(snapshot.identities[0], {
    processKey: "101675/2026",
    interestedOriginal: "Núzia Maria Barbosa",
    interestedNormalized: "nuzia maria barbosa",
    portalActId: null,
    pending: false,
    selected: false,
  });
  assert.ok(snapshot.actions.some((action) => action.action === "select_interested"));
});

test("accepts a legacy interested selection that transitions directly to the form", async () => {
  const { documentRef, radio } = buildRestrictedInitialActDocument();
  let mutationCallback = null;
  let observeCount = 0;
  let disconnectCount = 0;
  documentRef.defaultView.MutationObserver = class {
    constructor(callback) {
      mutationCallback = callback;
    }

    observe(target, options) {
      observeCount += 1;
      assert.equal(target, documentRef.body);
      assert.deepEqual(options, { childList: true, subtree: true, attributes: true });
    }

    disconnect() {
      disconnectCount += 1;
    }
  };
  radio.onClick = () => {
    radio.checked = true;
    mutationCallback?.();
  };
  const before = snapshotPortalScreen(documentRef);

  const result = await executeNavigation(documentRef, {
    action: "select_interested",
    identity: identity("101675/2026", "Núzia Maria Barbosa"),
    expected_generation: before.generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, true);
  assert.equal(result.snapshot.role, "form");
  assert.equal(radio.checked, true);
  assert.equal(observeCount, 1);
  assert.equal(disconnectCount, 1);
});

test("does not treat an already selected form as progress for select_interested", async () => {
  const { documentRef, radio } = buildRestrictedInitialActDocument({ selected: true });
  const before = snapshotPortalScreen(documentRef);

  const result = await executeNavigation(documentRef, {
    action: "select_interested",
    identity: identity("101675/2026", "Núzia Maria Barbosa"),
    expected_generation: before.generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, false);
  assert.equal(result.error.code, "NAVIGATION_TIMEOUT");
  assert.equal(radio.clickCount, 1);
});

test("rejects a selected interested identity that differs from the requested identity", async () => {
  const { documentRef, radio } = buildRestrictedInitialActDocument();
  documentRef.querySelector("td").textContent = "Bruno de Souza";
  const interestedTable = documentRef.querySelector("#PessoasAssocicadas");
  const requestedRow = new FakeElement("tr");
  const requestedRadio = new FakeElement("input", {
    attrs: { type: "radio", "data-interested-name": "Ana da Silva" },
  });
  requestedRow.append(requestedRadio, cell("Ana da Silva"), cell("CPF-SANITIZADO-02"), cell("Interessado"));
  interestedTable.append(requestedRow);
  requestedRadio.onClick = () => { radio.checked = true; };
  const before = snapshotPortalScreen(documentRef);

  const result = await executeNavigation(documentRef, {
    action: "select_interested",
    identity: identity("101675/2026", "Ana da Silva"),
    expected_generation: before.generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, false);
  assert.equal(result.error.code, "NAVIGATION_TIMEOUT");
  assert.equal(radio.checked, true);
  assert.equal(requestedRadio.clickCount, 1);
});

test("exposes the restricted portal tab close as the automatic return action after selection", () => {
  const { documentRef } = buildRestrictedInitialActDocument({ selected: true, withTopClose: true });
  const snapshot = snapshotPortalScreen(documentRef);

  assert.equal(snapshot.role, "form");
  assert.ok(snapshot.actions.some((action) => action.action === "return_list" && action.enabled === true));
});

test("returns from the restricted portal form by closing its tab and snapshots the live list", async () => {
  const { documentRef, close } = buildRestrictedInitialActDocument({ selected: true, withTopClose: true });
  const before = snapshotPortalScreen(documentRef);
  const result = await executeNavigation(documentRef, {
    action: "return_list",
    expected_generation: before.generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, true);
  assert.equal(result.snapshot.role, "list");
  assert.equal(close.clickCount, 1);
});

test("closes the restricted tab when the top frames collection is array-like without an iterator", async () => {
  const { documentRef, close } = buildRestrictedInitialActDocument({ selected: true, withTopClose: true });
  const top = documentRef.defaultView.top;
  top.frames = arrayLikeFrames(...top.frames);
  const before = snapshotPortalScreen(documentRef);
  const result = await executeNavigation(documentRef, {
    action: "return_list",
    expected_generation: before.generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, true);
  assert.equal(result.snapshot.role, "list");
  assert.equal(close.clickCount, 1);
});

test("returns to the list through a local Voltar control when the document is its own top window", async () => {
  const documentRef = new FakeDocument({ screen: "interested" });
  documentRef.defaultView.top = { document: documentRef, frames: arrayLikeFrames() };
  documentRef.setSurface(buildInterestedSurface(documentRef, { processKey: "103401/2023", interested: "Ana da Silva" }));

  const before = snapshotPortalScreen(documentRef);
  const result = await executeNavigation(documentRef, {
    action: "return_list",
    expected_generation: before.generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, true);
  assert.equal(result.snapshot.role, "list");
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

test("identifies the selected Area Restrita process source from its legacy route", () => {
  const sector = buildListDocument(1, [{ processKey: "103401/2023", interested: "Ana da Silva" }], { hasNext: false });
  sector.defaultView.location.href = "https://novaarearestrita.tce.rn.gov.br/SISTEMAS/PROCESSO/ProcessonoSetor.asp";
  assert.equal(snapshotPortalScreen(sector).source_scope, "sector_finalistic");

  const mine = buildListDocument(1, [{ processKey: "103401/2023", interested: "Ana da Silva" }], { hasNext: false });
  mine.defaultView.location.href = "https://novaarearestrita.tce.rn.gov.br/SISTEMAS/PROCESSO/MeusProcessos.asp";
  assert.equal(snapshotPortalScreen(mine).source_scope, "my_processes");
});

test("does not classify a hidden Area Restrita process frame as the active list", () => {
  const hidden = buildListDocument(1, [{ processKey: "103401/2023", interested: "Ana da Silva" }], { hasNext: false });
  hidden.defaultView.frameElement = { hidden: true };
  assert.equal(detectPortalScreen(hidden), "unknown");
  assert.equal(snapshotPortalScreen(hidden).role, "unknown");
});

test("registers an initially zero-sized list frame and emits one typed snapshot when it becomes visible", async () => {
  const documentRef = buildListDocument(1, [{ processKey: "103401/2023", interested: "Ana da Silva" }], { hasNext: false });
  documentRef.defaultView.location.href = "https://novaarearestrita.tce.rn.gov.br/SISTEMAS/PROCESSO/ProcessonoSetor.asp";
  let rect = { width: 0, height: 0 };
  const frameElement = { getBoundingClientRect: () => rect };
  documentRef.defaultView.frameElement = frameElement;
  const observers = [];
  const events = [];
  documentRef.defaultView.ResizeObserver = class {
    constructor(callback) {
      this.callback = callback;
      this.disconnected = false;
      observers.push(this);
    }

    observe(target) {
      assert.equal(target, frameElement);
    }

    disconnect() {
      this.disconnected = true;
    }

    notify() {
      this.callback([{ target: frameElement }]);
    }
  };
  const chromeApi = {
    runtime: {
      onMessage: { addListener() {} },
      sendMessage(message) {
        events.push(message);
      },
    },
  };

  installPortalNavigation({ documentRef, chromeApi });

  assert.equal(events.length, 1);
  assert.equal(events[0].type, "PORTAL_EVENT");
  assert.equal(events[0].payload.event.snapshot.role, "unknown");
  assert.equal(observers.length, 1);

  rect = { width: 640, height: 480 };
  observers[0].notify();
  await Promise.resolve();

  assert.equal(events.length, 2);
  assert.equal(events[1].type, "PORTAL_EVENT");
  assert.equal(events[1].payload.event.type, "snapshot");
  assert.equal(events[1].payload.event.snapshot.role, "list");
  assert.equal(events[1].payload.event.snapshot.source_scope, "sector_finalistic");
  assert.equal(observers[0].disconnected, true);

  observers[0].notify();
  await Promise.resolve();
  assert.equal(events.length, 2);
});

test("bounds the lifetime of observers when an unknown frame never becomes recognizable", () => {
  const documentRef = new FakeDocument({ screen: "unknown" });
  documentRef.defaultView.location.href = "https://novaarearestrita.tce.rn.gov.br/blank.asp";
  const frameElement = { getBoundingClientRect: () => ({ width: 0, height: 0 }) };
  documentRef.defaultView.frameElement = frameElement;
  const observers = [];
  const timers = [];
  documentRef.defaultView.setTimeout = (callback, delay) => {
    timers.push({ callback, delay, cleared: false });
    return timers.length;
  };
  documentRef.defaultView.clearTimeout = (id) => {
    if (timers[id - 1]) timers[id - 1].cleared = true;
  };
  documentRef.defaultView.ResizeObserver = class {
    constructor() {
      this.disconnected = false;
      observers.push(this);
    }

    observe(target) {
      assert.equal(target, frameElement);
    }

    disconnect() {
      this.disconnected = true;
    }
  };
  documentRef.defaultView.MutationObserver = class {
    constructor() {
      this.disconnected = false;
      observers.push(this);
    }

    observe() {}

    disconnect() {
      this.disconnected = true;
    }
  };
  const events = [];
  const chromeApi = {
    runtime: {
      onMessage: { addListener() {} },
      sendMessage(message) {
        events.push(message);
      },
    },
  };

  installPortalNavigation({ documentRef, chromeApi });

  assert.equal(events.length, 1);
  assert.equal(timers.length, 1);
  assert.ok(timers[0].delay > 0);
  timers[0].callback();

  assert.ok(observers.every((observer) => observer.disconnected));
  assert.equal(timers[0].cleared, false);
  assert.equal(events.length, 1);
});

test("uses the mutation observer for a top-level unknown frame and cleans it after recognition", async () => {
  const documentRef = new FakeDocument({ screen: "unknown" });
  documentRef.defaultView.location.href = "https://novaarearestrita.tce.rn.gov.br/SISTEMAS/Processo/ProcessonoSetor.asp";
  documentRef.defaultView.frameElement = null;
  const observers = [];
  documentRef.defaultView.MutationObserver = class {
    constructor(callback) {
      this.callback = callback;
      this.disconnected = false;
      observers.push(this);
    }

    observe(target, options) {
      assert.equal(target, documentRef.body);
      assert.deepEqual(options, { childList: true, subtree: true, attributes: true });
    }

    disconnect() {
      this.disconnected = true;
    }

    notify() {
      this.callback([]);
    }
  };
  const events = [];
  const chromeApi = {
    runtime: {
      onMessage: { addListener() {} },
      sendMessage(message) {
        events.push(message);
      },
    },
  };

  installPortalNavigation({ documentRef, chromeApi });

  const table = new FakeElement("table", { id: "tbproc01" });
  documentRef.body.append(table);
  observers[0].notify();
  await Promise.resolve();

  assert.equal(events.length, 2);
  assert.equal(events[1].payload.event.snapshot.role, "list");
  assert.equal(events[1].payload.event.snapshot.source_scope, "sector_finalistic");
  assert.equal(observers.length, 1);
  assert.equal(observers[0].disconnected, true);
});

test("cleans a created resize observer when observer installation fails", () => {
  const documentRef = new FakeDocument({ screen: "unknown" });
  const frameElement = { getBoundingClientRect: () => ({ width: 0, height: 0 }) };
  documentRef.defaultView.frameElement = frameElement;
  let resizeObserver = null;
  documentRef.defaultView.ResizeObserver = class {
    constructor() {
      resizeObserver = this;
    }

    observe() {
      throw new Error("observer unavailable");
    }

    disconnect() {
      this.disconnected = true;
    }
  };
  const events = [];
  const chromeApi = {
    runtime: {
      onMessage: { addListener() {} },
      sendMessage(message) {
        events.push(message);
      },
    },
  };

  installPortalNavigation({ documentRef, chromeApi });

  assert.equal(events.length, 1);
  assert.equal(resizeObserver.disconnected, true);
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

test("finds the Area Restrita Consultar control in the sibling botoesNOVO frame", async () => {
  const documentRef = buildListDocument("1", [{ processKey: "103401/2023", interested: "Ana da Silva" }]);
  const form = new FakeElement("form");
  const select = new FakeElement("select", { id: "cmbMarcadorFiltro" });
  const all = new FakeElement("option", { text: "Todos os marcadores", value: "" });
  const target = new FakeElement("option", { text: "PROFESSOR - IPERN - 2 RUBRICAS", value: "marker-2" });
  all.selected = true;
  select.value = "";
  select.append(all, target);
  form.append(select);
  documentRef.body.append(form);

  const topDocument = new FakeDocument({ screen: "shell" });
  const buttonFrame = new FakeDocument({ screen: "buttons" });
  buttonFrame.defaultView.location.href = "https://portal.test/botoesNOVO.asp?pagina=ProcessonoSetor";
  const consult = new FakeElement("input", { value: "Consultar", attrs: { type: "button", onclick: "parametros('1695','C','','');" } });
  buttonFrame.body.append(consult);
  documentRef.defaultView.top = { document: topDocument, frames: [{ document: documentRef }, { document: buttonFrame }] };

  consult.onClick = () => {
    target.selected = true;
    all.selected = false;
    select.value = "marker-2";
  };
  const before = snapshotPortalScreen(documentRef);
  const result = await executeNavigation(documentRef, {
    action: "filter_marker",
    marker: "PROFESSOR - IPERN - 2 RUBRICAS",
    expected_generation: before.generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, true);
  assert.equal(consult.clickCount, 1);
  assert.equal(result.snapshot.marker.value, "marker-2");
});

test("finds the sibling Consultar control when the top frames collection is array-like", async () => {
  const documentRef = buildListDocument("1", [{ processKey: "103401/2023", interested: "Ana da Silva" }]);
  const form = new FakeElement("form");
  const select = new FakeElement("select", { id: "cmbMarcadorFiltro" });
  const all = new FakeElement("option", { text: "Todos os marcadores", value: "" });
  const target = new FakeElement("option", { text: "PROFESSOR - IPERN - 2 RUBRICAS", value: "marker-2" });
  all.selected = true;
  select.value = "";
  select.append(all, target);
  form.append(select);
  documentRef.body.append(form);

  const topDocument = new FakeDocument({ screen: "shell" });
  const buttonFrame = new FakeDocument({ screen: "buttons" });
  buttonFrame.defaultView.location.href = "https://portal.test/botoesNOVO.asp?pagina=ProcessonoSetor";
  const consult = new FakeElement("input", { value: "Consultar", attrs: { type: "button", onclick: "parametros('1695','C','','');" } });
  buttonFrame.body.append(consult);
  documentRef.defaultView.top = { document: topDocument, frames: arrayLikeFrames({ document: documentRef }, { document: buttonFrame }) };

  consult.onClick = () => {
    target.selected = true;
    all.selected = false;
    select.value = "marker-2";
  };
  const before = snapshotPortalScreen(documentRef);
  const result = await executeNavigation(documentRef, {
    action: "filter_marker",
    marker: "PROFESSOR - IPERN - 2 RUBRICAS",
    expected_generation: before.generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, true);
  assert.equal(consult.clickCount, 1);
  assert.equal(result.snapshot.marker.value, "marker-2");
});

test("recognizes the legacy Area Restrita pagination link with NumeroPagina.value", () => {
  const documentRef = buildListDocument("3", [{ processKey: "103401/2023", interested: "Ana da Silva" }], { hasNext: false });
  const currentPage = new FakeElement("input", { id: "NumeroPagina", value: "3", attrs: { type: "hidden" } });
  const next = new FakeElement("a", {
    text: "Pr�xima >",
    attrs: { href: "javascript: form1.NumeroPagina.value=4; document.form1.Paginacao.value='S'; form1.submit();" },
  });
  documentRef.body.append(currentPage, next);

  const before = snapshotPortalScreen(documentRef);
  assert.ok(before.actions.some((action) => action.action === "next_page" && action.direction === "next"));
});

test("uses the named legacy pagination form and extracts every allowlisted value", async () => {
  const documentRef = buildListDocument("1", [
    { processKey: "103401/2023", interested: "Ana da Silva" },
  ], { hasNext: false });
  const distractor = new FakeElement("form", { attrs: { name: "otherForm" } });
  distractor.append(new FakeElement("input", {
    value: "1",
    attrs: { name: "NumeroPagina", type: "hidden" },
  }));
  let distractorSubmitCount = 0;
  distractor.submit = () => { distractorSubmitCount += 1; };
  const form = new FakeElement("form", { id: "form1", attrs: { name: "form1" } });
  const currentPage = new FakeElement("input", {
    id: "NumeroPagina",
    value: "1",
    attrs: { name: "NumeroPagina", type: "hidden" },
  });
  const pagination = new FakeElement("input", {
    value: "",
    attrs: { name: "Paginacao", type: "hidden" },
  });
  const group = new FakeElement("input", {
    value: "",
    attrs: { name: "GrupoProcesso", type: "hidden" },
  });
  form.append(currentPage, pagination, group);
  let submitCount = 0;
  form.submit = () => {
    submitCount += 1;
    documentRef.setSurface(buildListSurface(documentRef, 2));
  };
  const next = new FakeElement("a", {
    text: "Pr�xima >",
    attrs: {
      href: "javascript: form1.NumeroPagina.value=2; document.form1.Paginacao.value='S'; document.form1.GrupoProcesso.value='NS'; form1.submit();",
    },
  });
  next.onClick = () => {};
  documentRef.body.append(distractor, form, next);

  const before = snapshotPortalScreen(documentRef);
  const result = await executeNavigation(documentRef, {
    action: "next_page",
    expected_generation: before.generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, true);
  assert.equal(result.snapshot, null);
  assert.equal(result.waitingForFrame, true);
  assert.equal(submitCount, 1);
  assert.equal(distractorSubmitCount, 0);
  assert.equal(currentPage.value, "2");
  assert.equal(pagination.value, "S");
  assert.equal(group.value, "NS");
  assert.equal(next.clickCount, 0);
});

test("rejects an unallowlisted legacy pagination command without clicking its javascript link", async () => {
  const documentRef = buildListDocument("1", [
    { processKey: "103401/2023", interested: "Ana da Silva" },
  ], { hasNext: false });
  const form = new FakeElement("form", { id: "form1", attrs: { name: "form1" } });
  form.append(
    new FakeElement("input", { value: "1", attrs: { name: "NumeroPagina", type: "hidden" } }),
    new FakeElement("input", { value: "", attrs: { name: "Paginacao", type: "hidden" } }),
    new FakeElement("input", { value: "", attrs: { name: "GrupoProcesso", type: "hidden" } }),
  );
  let submitCount = 0;
  form.submit = () => { submitCount += 1; };
  const next = new FakeElement("a", {
    text: "Pr�xima >",
    attrs: {
      href: "javascript: form1.NumeroPagina.value=2; document.form1.Paginacao.value='N'; document.form1.GrupoProcesso.value='OTHER'; form1.submit();",
    },
  });
  next.onClick = () => {};
  documentRef.body.append(form, next);

  const result = await executeNavigation(documentRef, {
    action: "next_page",
    expected_generation: snapshotPortalScreen(documentRef).generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, false);
  assert.equal(result.error.code, "ACTION_NOT_ALLOWED");
  assert.equal(submitCount, 0);
  assert.equal(next.clickCount, 0);
});

test("submits the safe legacy pagination form when the javascript link click is inert", async () => {
  const documentRef = buildListDocument("1", [
    { processKey: "103401/2023", interested: "Ana da Silva" },
  ], { hasNext: false });
  const form = new FakeElement("form", { id: "form1", attrs: { name: "form1" } });
  const currentPage = new FakeElement("input", {
    id: "NumeroPagina",
    value: "1",
    attrs: { name: "NumeroPagina", type: "hidden" },
  });
  const pagination = new FakeElement("input", {
    value: "",
    attrs: { name: "Paginacao", type: "hidden" },
  });
  const group = new FakeElement("input", {
    value: "",
    attrs: { name: "GrupoProcesso", type: "hidden" },
  });
  form.append(currentPage, pagination, group);
  let submitCount = 0;
  form.submit = () => {
    submitCount += 1;
    documentRef.setSurface(buildListSurface(documentRef, 2));
  };
  const next = new FakeElement("a", {
    text: "Pr�xima >",
    attrs: {
      href: "javascript: form1.NumeroPagina.value=2; document.form1.Paginacao.value='S'; document.form1.GrupoProcesso.value='NS'; form1.submit();",
    },
  });
  next.onClick = () => {};
  documentRef.body.append(form, next);

  const before = snapshotPortalScreen(documentRef);
  const result = await executeNavigation(documentRef, {
    action: "next_page",
    expected_generation: before.generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, true);
  assert.equal(result.snapshot, null);
  assert.equal(result.waitingForFrame, true);
  assert.equal(submitCount, 1);
  assert.equal(currentPage.value, "2");
  assert.equal(pagination.value, "S");
  assert.equal(group.value, "NS");
  assert.equal(next.clickCount, 0);
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

test("does not wait on the list frame when Area Restrita opens Complementar Ato in a sibling frame", async () => {
  const documentRef = new FakeDocument({ screen: "list", page: "1" });
  const table = new FakeElement("table", { id: "tbproc01" });
  const tbody = new FakeElement("tbody");
  const row = new FakeElement("tr", { attrs: { "data-process-key": "101675/2026" } });
  row.append(cell("101675/2026"), cell("Núzia Maria Barbosa"));
  const action = new FakeElement("a", {
    attrs: {
      href: "/SISTEMAS/PROCESSO/ComplementarAto.asp",
      onclick: "window.parent.parent.addtabsinformacao('Complementar Ato', '../SISTEMAS/PROCESSO/ComplementarAto.asp');",
    },
  });
  action.append(new FakeElement("img", { attrs: { alt: "Complementar Ato" } }));
  row.append(action);
  tbody.append(row);
  table.append(tbody);
  documentRef.body.append(table);

  const before = snapshotPortalScreen(documentRef);
  const result = await executeNavigation(documentRef, {
    action: "open_act",
    identity: identity("101675/2026", "Núzia Maria Barbosa"),
    expected_generation: before.generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, true);
  assert.equal(result.snapshot, null);
  assert.equal(action.clickCount, 1);
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

test("keeps waiting after an intermediate list mutation before the paginated result", async () => {
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
    documentRef.setSurface(buildListSurface(documentRef, 1));
    notifyMutation?.();
    setTimeout(() => {
      documentRef.setSurface(buildListSurface(documentRef, 2));
      notifyMutation?.();
    }, 0);
  }, 0);

  const result = await executeNavigation(documentRef, {
    action: "next_page",
    expected_generation: snapshotPortalScreen(documentRef).generation,
    timeoutMs: 50,
  });

  assert.equal(result.ok, true);
  assert.equal(result.snapshot.identities[0].processKey, "103403/2023");
  assert.equal(result.rereads, 2);
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
