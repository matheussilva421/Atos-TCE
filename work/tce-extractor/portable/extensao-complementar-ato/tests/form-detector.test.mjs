import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  FIELD_MAP,
  applyFields,
  createMessageHandler,
  getFormSnapshot,
  hasCompleteForm,
  installContentScript,
  overrideField,
} from "../content/form-detector.js";
import { MESSAGE_TYPES, createMessage } from "../lib/messages.js";
import { normalizeInterestedName } from "../lib/schema.js";

const WORKSPACE = resolve(import.meta.dirname, "../../..");
const SHELL_FIXTURE = resolve(WORKSPACE, "tests/fixtures/complementar-ato-shell.html");
const FORM_FIXTURE = resolve(WORKSPACE, "tests/fixtures/complementar-ato-form.html");

class FakeEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.bubbles = init.bubbles === true;
  }
}

class FakeClassList {
  #classes = new Set();

  add(...classes) {
    classes.forEach((name) => this.#classes.add(name));
  }

  remove(...classes) {
    classes.forEach((name) => this.#classes.delete(name));
  }

  contains(name) {
    return this.#classes.has(name);
  }
}

class FakeElement {
  constructor(tagName, attributes = {}, text = "") {
    this.tagName = tagName.toUpperCase();
    this.attributes = new Map(Object.entries(attributes));
    this.children = [];
    this.parentElement = null;
    this.textContent = text;
    this.classList = new FakeClassList();
    this.eventListeners = new Map();
    this.disabled = false;
    this.readOnly = false;
    this.checked = false;
    this._value = "";
  }

  get id() {
    return this.getAttribute("id") ?? "";
  }

  get type() {
    return this.getAttribute("type") ?? "";
  }

  get value() {
    return this._value;
  }

  set value(nextValue) {
    this._value = String(nextValue);
  }

  get options() {
    return this.children.filter((child) => child.tagName === "OPTION");
  }

  get selectedOptions() {
    return this.options.filter((option) => option.selected);
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  append(...children) {
    for (const child of children) {
      child.parentElement = this;
      this.children.push(child);
    }
  }

  addEventListener(type, listener) {
    const listeners = this.eventListeners.get(type) ?? [];
    listeners.push(listener);
    this.eventListeners.set(type, listeners);
  }

  dispatchEvent(event) {
    for (const listener of this.eventListeners.get(event.type) ?? []) listener(event);
    return true;
  }

  closest(selector) {
    let current = this;
    while (current) {
      if (current.matches(selector)) return current;
      current = current.parentElement;
    }
    return null;
  }

  matches(selector) {
    if (selector === "tr") return this.tagName === "TR";
    if (selector === "option") return this.tagName === "OPTION";
    if (selector === "select") return this.tagName === "SELECT";
    if (selector === "input") return this.tagName === "INPUT";
    if (selector.startsWith(".")) return this.classList.contains(selector.slice(1));
    if (selector.startsWith("#")) return this.id === selector.slice(1);
    const attributeMatch = /^(\w+)\[([^=\]]+)(?:=["']?([^\]"']+)["']?)?\]$/u.exec(selector);
    if (attributeMatch) {
      const [, tag, attribute, expected] = attributeMatch;
      return this.tagName === tag.toUpperCase()
        && this.getAttribute(attribute) !== null
        && (expected === undefined || this.getAttribute(attribute) === expected);
    }
    const dataAttribute = /^\[([^\]]+)\]$/u.exec(selector);
    if (dataAttribute) return this.getAttribute(dataAttribute[1]) !== null;
    return this.tagName === selector.toUpperCase();
  }

  querySelectorAll(selector) {
    const descendants = [];
    const visit = (node) => {
      for (const child of node.children) {
        if (child.matches(selector)) descendants.push(child);
        visit(child);
      }
    };
    visit(this);
    return descendants;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] ?? null;
  }
}

class FakeDocument extends FakeElement {
  constructor() {
    super("document");
    this.defaultView = { Event: FakeEvent };
  }

  getElementById(id) {
    return this.querySelector(`#${id}`);
  }

  createEvent() {
    return new FakeEvent("event");
  }
}

function input(id, value = "", attributes = {}) {
  const element = new FakeElement("input", { id, ...attributes });
  element.value = value;
  return element;
}

function option(value, label) {
  const element = new FakeElement("option", { value }, label);
  element.value = value;
  element.label = label;
  element.selected = false;
  return element;
}

function select(id, values) {
  const element = new FakeElement("select", { id });
  element.append(...values.map(([value, label]) => option(value, label)));
  element.value = "";
  return element;
}

function row(name, checked) {
  const result = new FakeElement("tr");
  const radio = new FakeElement("input", {
    type: "radio",
    name: "interessado",
    "data-interested-name": name,
  });
  radio.checked = checked;
  result.append(radio, new FakeElement("td", {}, name));
  return result;
}

function buildForm({ complete = true } = {}) {
  const documentRef = new FakeDocument();
  const form = new FakeElement("form", { id: "complementarAtoForm" });
  const controls = {
    txtNumeroProcesso: input("txtNumeroProcesso", "103439"),
    txtAnoProcesso: input("txtAnoProcesso", "2023"),
    txtModalidade: select("txtModalidade", [["", "Selecione"], ["m-ordinary", "Aposentadoria voluntária"], ["m-special", "Aposentadoria especial"]]),
    txtFundamentoLegal: select("txtFundamentoLegal", [["", "Selecione"], ["f-general", "Artigo 40, parágrafo 1"], ["f-professor", "Artigo 40, parágrafo 5, professor"]]),
    txtDataDOE: input("txtDataDOE"),
    txtCargo: input("txtCargo"),
    txtMatricula: input("txtMatricula"),
    txtDataNascimento: input("txtDataNascimento"),
    txtGenero: input("txtGenero"),
  };
  const interestedTable = new FakeElement("table", { id: "interessados" });
  interestedTable.append(row("João da Silva", false), row("Maria de Souza", true));
  form.append(input("txtNumeroProcesso", "103439"));
  form.append(input("txtAnoProcesso", "2023"));
  form.append(interestedTable);
  for (const [id, control] of Object.entries(controls)) {
    if (id !== "txtNumeroProcesso" && id !== "txtAnoProcesso") form.append(control);
  }
  form.append(input("txtValorProventos", "R$ 9.999,99"));
  form.append(new FakeElement("textarea", { id: "txtConclusaoAnalise" }, "Conclusão manual intacta"));
  form.append(new FakeElement("button", { id: "btnComplementar", "data-click-count": "0" }, "Complementar Ato"));
  form.append(new FakeElement("button", { id: "btnLimpar", "data-click-count": "0" }, "Limpar"));
  if (!complete) form.children = form.children.filter((child) => child.id !== "txtGenero");
  documentRef.append(form);
  return { documentRef, form, controls };
}

test("the sanitized fixtures model iframeOBJ to form and only the inner document has all sentinels", () => {
  const shell = readFileSync(SHELL_FIXTURE, "utf8");
  const formFixture = readFileSync(FORM_FIXTURE, "utf8");
  assert.deepEqual(FIELD_MAP, {
    modalidade: "txtModalidade",
    fundamento_legal: "txtFundamentoLegal",
    data_publicacao_doe: "txtDataDOE",
    cargo: "txtCargo",
    matricula: "txtMatricula",
    data_nascimento: "txtDataNascimento",
    genero: "txtGenero",
  });
  const sentinelIds = [
    "txtNumeroProcesso",
    "txtAnoProcesso",
    "txtModalidade",
    "txtFundamentoLegal",
    "txtDataDOE",
    "txtCargo",
    "txtMatricula",
    "txtDataNascimento",
    "txtGenero",
  ];
  assert.match(shell, /id="iframeOBJ"/u);
  assert.match(shell, /src="complementar-ato-form\.html"/u);
  for (const id of sentinelIds) {
    assert.doesNotMatch(shell, new RegExp(`id="${id}"`, "u"));
    assert.match(formFixture, new RegExp(`id="${id}"`, "u"));
  }
});

test("detects only a complete form and snapshots process, selected interested party, options, and field state", () => {
  const { documentRef, controls } = buildForm();
  controls.txtCargo.value = "Cargo já existente";
  controls.txtGenero.disabled = true;
  controls.txtMatricula.readOnly = true;

  assert.equal(hasCompleteForm(documentRef), true);
  const snapshot = getFormSnapshot(documentRef);

  assert.deepEqual(snapshot.process, { number: "103439", year: "2023", key: "103439/2023" });
  assert.deepEqual(snapshot.interested, {
    original: "Maria de Souza",
    normalized: "maria de souza",
  });
  assert.deepEqual(snapshot.options.modalidade, [
    { value: "", label: "Selecione" },
    { value: "m-ordinary", label: "Aposentadoria voluntária" },
    { value: "m-special", label: "Aposentadoria especial" },
  ]);
  assert.deepEqual(snapshot.options.fundamento_legal, [
    { value: "", label: "Selecione" },
    { value: "f-general", label: "Artigo 40, parágrafo 1" },
    { value: "f-professor", label: "Artigo 40, parágrafo 5, professor" },
  ]);
  assert.deepEqual(snapshot.fields.cargo, { value: "Cargo já existente", disabled: false, readOnly: false });
  assert.deepEqual(snapshot.fields.matricula, { value: "", disabled: false, readOnly: true });
  assert.deepEqual(snapshot.fields.genero, { value: "", disabled: true, readOnly: false });
});

test("reads the Nome column, not the complete portal row containing CPF and function", () => {
  const { documentRef } = buildForm();
  const table = documentRef.getElementById("interessados");
  table.children = [];
  const heading = new FakeElement("tr");
  heading.append(...["", "Nome", "CPF/CNPJ", "Função no Processo"].map((title) => new FakeElement("td", {}, title)));
  const selected = new FakeElement("tr", {}, "MARIA DAS GRACAS DE SA 00000000000 Interessado");
  const cell = new FakeElement("td");
  const radio = input("interessado-1", "42", { type: "radio" });
  radio.checked = true;
  cell.append(radio);
  selected.append(cell, new FakeElement("td", {}, "MARIA DAS GRACAS DE SA"), new FakeElement("td", {}, "00000000000"), new FakeElement("td", {}, "Interessado"));
  table.append(heading, selected);
  const snapshot = getFormSnapshot(documentRef);
  assert.equal(snapshot.interested.original, "MARIA DAS GRACAS DE SA");
  assert.equal(snapshot.interested.normalized, normalizeInterestedName("MARIA DAS GRAÇAS DE SÁ"));
});

test("does not use a numeric radio identity or an unstructured full row as a person name", () => {
  const { documentRef } = buildForm();
  const table = documentRef.getElementById("interessados");
  table.children = [];
  const selected = new FakeElement("tr", {}, "Pessoa 00000000000 Interessado");
  const radio = input("interessado-1", "42", { type: "radio" });
  radio.checked = true;
  selected.append(radio);
  table.append(selected);
  assert.equal(getFormSnapshot(documentRef).interested, null);
});

test("fills only the seven allowed fields, uses select option values, dispatches bubbling events, and colors confidence", () => {
  const { documentRef, controls } = buildForm();
  const events = [];
  for (const element of Object.values(controls)) {
    for (const type of ["input", "change", "blur"]) {
      element.addEventListener(type, (event) => events.push({ id: element.id, type: event.type, bubbles: event.bubbles }));
    }
  }
  controls.txtCargo.value = "Cargo já existente";
  controls.txtGenero.disabled = true;

  const result = applyFields(documentRef, {
    modalidade: "m-special",
    fundamento_legal: "f-professor",
    data_publicacao_doe: "07/02/2020",
    cargo: "Cargo novo",
    matricula: "103.870-2/1",
    data_nascimento: "30/04/1967",
    genero: "Feminino",
  }, {
    matchKinds: { modalidade: "exact", fundamento_legal: "probable" },
  });

  assert.deepEqual(result.changed, ["modalidade", "fundamento_legal", "data_publicacao_doe", "matricula", "data_nascimento"]);
  assert.deepEqual(result.preserved, ["cargo"]);
  assert.deepEqual(result.disabled, ["genero"]);
  assert.deepEqual(result.missing, []);
  assert.deepEqual(result.errors, []);
  assert.equal(controls.txtModalidade.value, "m-special");
  assert.equal(controls.txtFundamentoLegal.value, "f-professor");
  assert.equal(controls.txtCargo.value, "Cargo já existente");
  assert.equal(controls.txtGenero.value, "");
  assert.equal(controls.txtModalidade.classList.contains("complementar-ato-match-green"), true);
  assert.equal(controls.txtFundamentoLegal.classList.contains("complementar-ato-match-yellow"), true);
  assert.equal(documentRef.getElementById("btnComplementar").getAttribute("data-click-count"), "0");
  assert.equal(documentRef.getElementById("btnLimpar").getAttribute("data-click-count"), "0");
  assert.ok(events.some((event) => event.id === "txtDataDOE" && event.type === "input" && event.bubbles));
  assert.ok(events.some((event) => event.id === "txtFundamentoLegal" && event.type === "change" && event.bubbles));
  assert.ok(events.some((event) => event.id === "txtMatricula" && event.type === "blur" && event.bubbles));
});

test("marks an explicitly selected tie as yellow without changing the chosen option value", () => {
  const { documentRef, controls } = buildForm();

  const result = applyFields(documentRef, { fundamento_legal: "f-general" }, {
    matchKinds: { fundamento_legal: "tie" },
  });

  assert.deepEqual(result.changed, ["fundamento_legal"]);
  assert.equal(controls.txtFundamentoLegal.value, "f-general");
  assert.equal(controls.txtFundamentoLegal.classList.contains("complementar-ato-match-yellow"), true);
});

test("override changes one explicitly requested divergent field and leaves forbidden controls untouched", () => {
  const { documentRef, controls } = buildForm();
  controls.txtCargo.value = "Cargo já existente";
  const conclusion = documentRef.getElementById("txtConclusaoAnalise");
  const financial = documentRef.getElementById("txtValorProventos");
  const before = { conclusion: conclusion.textContent, financial: financial.value };

  const result = overrideField(documentRef, "cargo", "Cargo substituído");

  assert.deepEqual(result, {
    changed: ["cargo"],
    preserved: [],
    missing: [],
    disabled: [],
    errors: [],
  });
  assert.equal(controls.txtCargo.value, "Cargo substituído");
  assert.deepEqual({ conclusion: conclusion.textContent, financial: financial.value }, before);
  assert.equal(documentRef.getElementById("btnComplementar").getAttribute("data-click-count"), "0");
  assert.equal(documentRef.getElementById("btnLimpar").getAttribute("data-click-count"), "0");
});

test("applyFields cannot turn an options flag into a batch override", () => {
  const { documentRef, controls } = buildForm();
  controls.txtCargo.value = "Cargo existente";
  controls.txtMatricula.value = "Matrícula existente";

  const result = applyFields(documentRef, {
    cargo: "Cargo substituído em lote",
    matricula: "Matrícula substituída em lote",
  }, { override: true });

  assert.deepEqual(result.changed, []);
  assert.deepEqual(result.preserved, ["cargo", "matricula"]);
  assert.equal(controls.txtCargo.value, "Cargo existente");
  assert.equal(controls.txtMatricula.value, "Matrícula existente");
});

test("rejects any payload key outside FIELD_MAP before writing, including financial and conclusion fields", () => {
  const { documentRef, controls } = buildForm();
  assert.throws(
    () => applyFields(documentRef, {
      cargo: "Permitido",
      txtValorProventos: "R$ 0,00",
      txtConclusaoAnalise: "Conclusão maliciosa",
    }),
    /unsupported field/u,
  );
  assert.equal(controls.txtCargo.value, "");
  assert.equal(documentRef.getElementById("txtValorProventos").value, "R$ 9.999,99");
  assert.equal(documentRef.getElementById("txtConclusaoAnalise").textContent, "Conclusão manual intacta");
});

test("blocks incomplete DOM before any write", () => {
  const { documentRef, controls } = buildForm({ complete: false });
  assert.equal(hasCompleteForm(documentRef), false);
  const result = applyFields(documentRef, { cargo: "Nunca escrever" });
  assert.deepEqual(result.changed, []);
  assert.equal(controls.txtCargo.value, "");
  assert.ok(result.errors.some((error) => /sentinel/u.test(error)));
});

test("blocks a form without exactly one selected interested radio", () => {
  const { documentRef, controls } = buildForm();
  for (const radio of documentRef.querySelectorAll('input[type="radio"]')) radio.checked = false;

  assert.equal(getFormSnapshot(documentRef).interested, null);
  const result = applyFields(documentRef, { cargo: "Nunca escrever" });

  assert.deepEqual(result.changed, []);
  assert.equal(controls.txtCargo.value, "");
  assert.ok(result.errors.some((error) => /identity/u.test(error)));
});

test("preserves readOnly fields and reports them separately from ordinary divergence", () => {
  const { documentRef, controls } = buildForm();
  controls.txtMatricula.readOnly = true;

  const result = applyFields(documentRef, {
    matricula: "103.870-2/1",
    cargo: "Cargo completo",
  });

  assert.deepEqual(result.changed, ["cargo"]);
  assert.deepEqual(result.disabled, ["matricula"]);
  assert.equal(controls.txtMatricula.value, "");
  assert.equal(controls.txtCargo.value, "Cargo completo");
});

test("revalidates identity before every write and stops when the selected interested party changes", () => {
  const { documentRef, controls } = buildForm();
  controls.txtModalidade.addEventListener("input", () => {
    const radios = documentRef.querySelectorAll('input[type="radio"]');
    radios[0].checked = true;
    radios[1].checked = false;
  });

  const result = applyFields(documentRef, {
    modalidade: "m-special",
    cargo: "Não deve ser escrito após troca de interessado",
  });

  assert.deepEqual(result.changed, ["modalidade"]);
  assert.equal(controls.txtCargo.value, "");
  assert.ok(result.errors.some((error) => /identity/u.test(error)));
});

test("revalidates frame visibility before every write and stops when the form becomes hidden", () => {
  const { documentRef, form, controls } = buildForm();
  controls.txtModalidade.addEventListener("input", () => {
    form.hidden = true;
  });

  const result = applyFields(documentRef, {
    modalidade: "m-special",
    cargo: "Não deve ser escrito após o frame ficar oculto",
  });

  assert.deepEqual(result.changed, ["modalidade"]);
  assert.equal(controls.txtCargo.value, "");
  assert.ok(result.errors.some((error) => /visible/u.test(error)));
});

test("walks nested frame windows and blocks a form inside a hidden outer iframe", async () => {
  const { documentRef } = buildForm();
  const innerFrameElement = new FakeElement("iframe");
  const outerFrameElement = new FakeElement("iframe");
  outerFrameElement.hidden = true;
  const topWindow = {};
  topWindow.parent = topWindow;
  const outerWindow = { frameElement: outerFrameElement, parent: topWindow };
  const innerWindow = { frameElement: innerFrameElement, parent: outerWindow };
  documentRef.defaultView = innerWindow;

  const response = await createMessageHandler(documentRef)(
    createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "nested-hidden"),
  );

  assert.equal(response.ok, false);
  assert.equal(response.error.code, "FORM_NOT_VISIBLE");
});

test("does not use the top-level document hidden state as the frame visibility signal", async () => {
  const { documentRef } = buildForm();
  documentRef.hidden = true;
  documentRef.visibilityState = "hidden";

  const response = await createMessageHandler(documentRef)(
    createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "document-hidden-state"),
  );

  assert.equal(response.ok, true);
});

test("fails closed when the parent frame visibility chain is unreadable", async () => {
  const { documentRef } = buildForm();
  documentRef.defaultView = {
    get frameElement() {
      throw new Error("cross-origin frameElement");
    },
  };

  const response = await createMessageHandler(documentRef)(
    createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "cross-origin-frame"),
  );

  assert.equal(response.ok, false);
  assert.equal(response.error.code, "FORM_NOT_VISIBLE");
});

test("fails closed when a cross-origin child cannot expose its frame element", async () => {
  const { documentRef } = buildForm();
  documentRef.defaultView = {
    frameElement: null,
    parent: {},
  };

  const response = await createMessageHandler(documentRef)(
    createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "cross-origin-null-frame"),
  );

  assert.equal(response.ok, false);
  assert.equal(response.error.code, "FORM_NOT_VISIBLE");
});

test("does not answer snapshot discovery from a hidden form frame", async () => {
  const { documentRef } = buildForm();
  const frameElement = new FakeElement("iframe");
  frameElement.style = { display: "none" };
  documentRef.defaultView.frameElement = frameElement;
  let listener;
  const responses = [];
  const chromeApi = {
    runtime: {
      onMessage: { addListener(next) { listener = next; } },
      async sendMessage() {},
    },
  };
  const installed = installContentScript({ documentRef, chromeApi, locationRef: { href: "https://example.test" } });

  const direct = await installed.handleMessage(createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "hidden-direct"));
  assert.equal(direct.ok, false);
  assert.equal(direct.error.code, "FORM_NOT_VISIBLE");

  const listenerResult = listener(
    createMessage(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, "hidden-discovery"),
    {},
    (response) => responses.push(response),
  );
  assert.equal(listenerResult, false);
  await Promise.resolve();
  assert.deepEqual(responses, []);
});

test("message handler exposes snapshots and field results without allowing unsupported operations", async () => {
  const { documentRef, controls } = buildForm();
  const handler = createMessageHandler(documentRef);
  const snapshot = await handler({ type: "GET_FORM_SNAPSHOT", payload: {} });
  assert.equal(snapshot.ok, true);
  assert.equal(snapshot.payload.process.key, "103439/2023");

  const applied = await handler({
    type: "APPLY_FIELDS",
    payload: { fields: { data_publicacao_doe: "07/02/2020" } },
  });
  assert.equal(applied.ok, true);
  assert.deepEqual(applied.payload.changed, ["data_publicacao_doe"]);
  assert.equal(controls.txtDataDOE.value, "07/02/2020");

  const unsupported = await handler({ type: "UNKNOWN", payload: {} });
  assert.equal(unsupported.ok, false);
  assert.match(unsupported.error.code, /UNSUPPORTED_MESSAGE/u);
});

test("validated APPLY_FIELDS transports matchKinds through the handler to green and yellow classes", async () => {
  const { documentRef, controls } = buildForm();
  const handler = createMessageHandler(documentRef);
  const snapshot = await handler(createMessage(
    MESSAGE_TYPES.GET_FORM_SNAPSHOT,
    {},
    "snapshot-for-colors",
  ));
  assert.equal(snapshot.ok, true);

  const applied = await handler(createMessage(
    MESSAGE_TYPES.APPLY_FIELDS,
    {
      fields: {
        modalidade: "m-special",
        fundamento_legal: "f-professor",
      },
      matchKinds: {
        modalidade: "exact",
        fundamento_legal: "probable",
      },
    },
    "apply-with-colors",
  ));

  assert.equal(applied.ok, true);
  assert.deepEqual(applied.payload.changed, ["modalidade", "fundamento_legal"]);
  assert.equal(controls.txtModalidade.classList.contains("complementar-ato-match-green"), true);
  assert.equal(controls.txtFundamentoLegal.classList.contains("complementar-ato-match-yellow"), true);
});

test("emits a Complementar Ato signal only for the current verified identity", async () => {
  const { documentRef } = buildForm();
  const events = [];
  documentRef.addEventListener("tce:complementar-ato", (event) => events.push(event));
  const response = await createMessageHandler(documentRef)(
    createMessage(
      MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO,
      { processKey: "103439/2023", interestedNormalized: "maria de souza" },
      "signal-1",
    ),
  );
  assert.equal(response.ok, true);
  assert.equal(events.length, 1);
  assert.deepEqual(events[0].detail, {
    processKey: "103439/2023",
    interestedNormalized: "maria de souza",
  });
});

test("blocks a Complementar Ato signal when identity changed", async () => {
  const { documentRef } = buildForm();
  const response = await createMessageHandler(documentRef)(
    createMessage(
      MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO,
      { processKey: "999999/2024", interestedNormalized: "outra pessoa" },
      "signal-2",
    ),
  );
  assert.equal(response.ok, false);
  assert.equal(response.error.code, "COMPLEMENTAR_ATO_BLOCKED");
});
