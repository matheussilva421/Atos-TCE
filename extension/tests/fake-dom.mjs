/**
 * Minimal DOM used by the extension tests.
 *
 * Ported from the fixtures of the proven legacy suite
 * (work/tce-extractor/portable/extensao-complementar-ato/tests/portal-navigation.test.mjs)
 * so the new scanner is exercised against exactly the structures the real
 * Área Restrita renders, without needing a browser.
 */

export class FakeElement {
  constructor(tagName = "div", { id = "", text = "", attrs = {}, value = "" } = {}) {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this._text = text;
    this.attributes = { ...attrs };
    if (id) this.attributes.id = id;
    // ``value`` lives behind an accessor so the native-setter walk used by the
    // filler finds a real setter, exactly like a browser input does.
    this._value = String(value ?? "");
    this.writeCount = 0;
    this.events = [];
    this.checked = false;
    this.disabled = false;
    this.hidden = false;
    this.selected = false;
    this.children = [];
    this.parentElement = null;
    this.ownerDocument = null;
    this.labels = [];
    this.clickCount = 0;
    this.onClick = null;
    this.dataset = Object.fromEntries(
      Object.entries(this.attributes)
        .filter(([key]) => key.startsWith("data-"))
        .map(([key, child]) => [
          key.slice(5).replace(/-([a-z])/gu, (_, letter) => letter.toUpperCase()),
          child,
        ])
    );
  }

  get textContent() {
    return [this._text, ...this.children.map((child) => child.textContent)]
      .filter(Boolean)
      .join(" ");
  }

  get value() {
    return this._value;
  }

  set value(next) {
    this._value = String(next ?? "");
    this.writeCount += 1;
  }

  dispatchEvent(event) {
    this.events.push(event?.type ?? "");
    return true;
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
    if (classMatch)
      return attributeOf(this, "class")
        .split(/\s+/u)
        .includes(classMatch[1]);
    const tagMatch = normalized.match(/^([a-z][\w-]*)?/iu);
    const tag = tagMatch?.[1];
    if (tag && this.tagName !== tag.toUpperCase()) return false;
    const attrMatches = [...normalized.matchAll(/\[([\w-]+)(?:=["']?([^\]"']+)["']?)?\]/gu)];
    return attrMatches.every(
      ([, name, expected]) =>
        Object.hasOwn(this.attributes, name) &&
        (expected === undefined || this.attributes[name] === expected)
    );
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

export function attributeOf(element, name) {
  return Object.hasOwn(element.attributes, name) ? String(element.attributes[name]) : "";
}

export class FakeDocument extends FakeElement {
  constructor({ screen = "list", page = "", sector = "aposentadorias", href = null } = {}) {
    super("document");
    this.defaultView = { location: { href: href ?? `https://portal.test/${screen}?page=${page}` } };
    this.documentElement = new FakeElement("html", {
      attrs: { "data-screen": screen, "data-sector": sector },
    });
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

export function cell(text, attrs = {}) {
  return new FakeElement("td", { text, attrs });
}

export function redComplementIcon() {
  return new FakeElement("img", {
    attrs: {
      alt: "Complementar Ato",
      title: "Complementar Ato",
      src: "../../images/icone-complementar-ato-vermelho.png",
    },
  });
}

export function greenComplementIcon() {
  return new FakeElement("img", {
    attrs: {
      alt: "Ato Complementado",
      title: "Ato Complementado",
      src: "../../images/icone-complementar-ato-verde.png",
    },
  });
}

/** One `tbproc01` list row with the standard three cells plus an action link. */
export function listRow({ processKey, interested, icon = redComplementIcon(), actId = null, interestedInCell = true }) {
  const attrs = { "data-process-key": processKey };
  if (actId) attrs["data-portal-act-id"] = actId;
  const row = new FakeElement("tr", { attrs });
  const link = new FakeElement("a", { attrs: { href: `/act/${processKey}` } });
  link.append(icon);
  row.append(cell(processKey), cell(interested), cell("Ação"));
  if (interestedInCell) row.children[1].setAttribute("data-interested-name", interested);
  row.append(link);
  return row;
}

/** Build a list screen with optional marker filter and numeric pagination. */
export function buildListDocument({
  page = "1",
  rows = [],
  hasNext = true,
  markerLabel = null,
  paginationLabels = null,
  sourceScope = null,
} = {}) {
  const documentRef = new FakeDocument({ screen: "list", page: String(page) });
  if (sourceScope) documentRef.documentElement.setAttribute("data-source-scope", sourceScope);
  const table = new FakeElement("table", { id: "tbproc01" });
  const tbody = new FakeElement("tbody");
  for (const rowData of rows) tbody.append(listRow(rowData));
  table.append(tbody);
  documentRef.body.append(table);

  if (markerLabel !== null) documentRef.body.append(markerFilter(markerLabel));

  const nav = new FakeElement("nav", { attrs: { "aria-label": "Paginação" } });
  nav.append(new FakeElement("a", { text: String(page), attrs: { "aria-current": "page" } }));
  for (const label of paginationLabels ?? []) {
    nav.append(new FakeElement("a", { text: String(label) }));
  }
  if (hasNext) nav.append(new FakeElement("a", { text: "Próxima", attrs: { "data-action": "next-page" } }));
  documentRef.body.append(nav);
  return documentRef;
}

export function markerFilter(selectedLabel = "Todos os marcadores") {
  const form = new FakeElement("form", { id: "process-filter" });
  const label = new FakeElement("label", { text: "Marcador:" });
  const select = new FakeElement("select", { id: "marcador" });
  const all = new FakeElement("option", { text: "Todos os marcadores", value: "" });
  const target = new FakeElement("option", {
    text: "PROFESSOR - IPERN - 2 RUBRICAS",
    value: "marker-2",
  });
  all.selected = selectedLabel === all.textContent;
  target.selected = selectedLabel === target.textContent;
  select.value = target.selected ? target.value : all.value;
  select.append(all, target);
  const consult = new FakeElement("button", { text: "Consultar", attrs: { "data-action": "consultar" } });
  form.append(label, select, consult);
  return form;
}

export function buildInterestedDocument({ processKey = "103401/2023", people = [] } = {}) {
  const documentRef = new FakeDocument({ screen: "interested" });
  const table = new FakeElement("table", { id: "PessoasAssocicadas" });
  for (const person of people) {
    const row = new FakeElement("tr");
    const radio = new FakeElement("input", { attrs: { type: "radio" } });
    radio.setAttribute("data-interested-name", person);
    const control = new FakeElement("td");
    control.append(radio);
    row.append(cell(person), control);
    table.append(row);
  }
  documentRef.body.append(table);
  const number = new FakeElement("input", { id: "txtNumeroProcesso", value: processKey.split("/")[0] });
  const year = new FakeElement("input", { id: "txtAnoProcesso", value: processKey.split("/")[1] });
  documentRef.body.append(number, year);
  return documentRef;
}

export function buildFormDocument({
  processKey = "103401/2023",
  fields = { txtModalidade: "aposentadoria voluntária" },
} = {}) {
  const documentRef = new FakeDocument({ screen: "form" });
  const form = new FakeElement("form", { id: "complementarAtoForm" });
  form.append(
    new FakeElement("input", { id: "txtNumeroProcesso", value: processKey.split("/")[0] }),
    new FakeElement("input", { id: "txtAnoProcesso", value: processKey.split("/")[1] })
  );
  for (const [id, value] of Object.entries(fields)) {
    form.append(new FakeElement("input", { id, value }));
  }
  documentRef.body.append(form);
  return documentRef;
}

export const ACT_FIELD_IDS = Object.freeze({
  modalidade: "txtModalidade",
  fundamento_legal: "txtFundamentoLegal",
  data_publicacao_doe: "txtDataDOE",
  cargo: "txtCargo",
  matricula: "txtMatricula",
  data_nascimento: "txtDataNascimento",
  genero: "txtGenero",
});

/** A frame element as the visibility rule sees it. */
export function buildFrameElement({ visible = true } = {}) {
  const frame = new FakeElement("iframe");
  frame.getBoundingClientRect = () => (visible ? { width: 800, height: 600 } : { width: 0, height: 0 });
  frame.getClientRects = () => (visible ? [{}] : []);
  return frame;
}

/**
 * The act form of the restricted portal: process identity, the seven mapped
 * controls (inputs and selects) and, when asked, the interested radio table.
 */
export function buildActFormDocument({
  processKey = "102390/2026",
  values = {},
  selects = {},
  selected = null,
  frame = null,
  hiddenAncestor = false,
  complete = true,
} = {}) {
  const documentRef = new FakeDocument({ screen: "form" });
  const parentWindow = frame ? { document: null } : null;
  documentRef.defaultView = {
    location: { href: "https://portal.test/complementarato.asp" },
    frameElement: frame,
    parent: frame ? parentWindow : null,
    getComputedStyle: () => ({}),
  };
  if (!frame) documentRef.defaultView.parent = documentRef.defaultView;

  const form = new FakeElement("form", { id: "complementarAtoForm" });
  const [number, year] = String(processKey).split("/");
  form.append(
    new FakeElement("input", { id: "txtNumeroProcesso", value: number ?? "" }),
    new FakeElement("input", { id: "txtAnoProcesso", value: year ?? "" })
  );
  for (const [name, id] of Object.entries(ACT_FIELD_IDS)) {
    if (selects[name]) {
      const select = new FakeElement("select", { id });
      for (const option of selects[name]) {
        const node = new FakeElement("option", {
          text: option.label ?? "",
          value: option.value ?? "",
        });
        if (option.selected) {
          node.selected = true;
          select.value = option.value;
        }
        select.append(node);
      }
      select.writeCount = 0;
      form.append(select);
      continue;
    }
    if (!complete && name === "genero") continue;
    const input = new FakeElement("input", { id, value: values[name] ?? "" });
    form.append(input);
  }
  documentRef.body.append(form);

  if (selected !== null) {
    const table = new FakeElement("table", { id: "PessoasAssocicadas" });
    for (const person of [selected]) {
      const row = new FakeElement("tr");
      const radio = new FakeElement("input", { attrs: { type: "radio" } });
      radio.setAttribute("data-interested-name", person);
      radio.checked = true;
      const control = new FakeElement("td");
      control.append(radio);
      row.append(cell(person), control);
      table.append(row);
    }
    documentRef.body.append(table);
  }

  if (hiddenAncestor) {
    const wrapper = new FakeElement("div", { attrs: { "aria-hidden": "true" } });
    wrapper.append(form);
    documentRef.body.append(wrapper);
  }
  return documentRef;
}
