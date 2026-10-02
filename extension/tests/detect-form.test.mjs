import test from "node:test";
import assert from "node:assert/strict";

import {
  buildActFormDocument,
  buildFrameElement,
  FakeDocument,
  FakeElement,
  ACT_FIELD_IDS,
} from "./fake-dom.mjs";

const contentMessageListeners = [];
globalThis.chrome = {
  runtime: {
    onMessage: {
      addListener(listener) {
        contentMessageListeners.push(listener);
      },
    },
  },
};

await import("../lib/area-snapshot.js");
await import("../content/detect-form.js");

const reader = globalThis.TCEFormReader;

function appendCandidate(documentRef, {
  processKey,
  rootId = "complementarAtoForm",
  rootTag = "form",
  tableId = "PessoasAssocicadas",
  selected = "Pessoa Exemplo",
  hidden = false,
  omitNumber = false,
  omitYear = false,
} = {}) {
  const root = new FakeElement(rootTag, { id: rootId });
  const [number, year] = String(processKey ?? "102390/2026").split("/");
  if (!omitNumber) root.append(new FakeElement("input", { id: "txtNumeroProcesso", value: number }));
  if (!omitYear) root.append(new FakeElement("input", { id: "txtAnoProcesso", value: year }));
  for (const id of Object.values(ACT_FIELD_IDS)) {
    root.append(new FakeElement("input", { id, value: "" }));
  }

  if (selected !== null) {
    const table = new FakeElement("table", { id: tableId });
    const row = new FakeElement("tr");
    const name = new FakeElement("td", { text: selected });
    const control = new FakeElement("td");
    const radio = new FakeElement("input", { attrs: { type: "radio" } });
    radio.checked = true;
    radio.setAttribute("data-interested-name", selected);
    control.append(radio);
    row.append(name, control);
    table.append(row);
    root.append(table);
  }

  root.hidden = hidden;
  documentRef.body.append(root);
  return root;
}

function appendInterestedTable(root, { name, checked = true, hidden = false, tableId = "PessoasAssociadas" }) {
  const table = new FakeElement("table", { id: tableId });
  const row = new FakeElement("tr");
  const radio = new FakeElement("input", { attrs: { type: "radio" } });
  radio.checked = checked;
  radio.setAttribute("data-interested-name", name);
  row.append(new FakeElement("td", { text: name }), radio);
  table.append(row);
  if (hidden) {
    const wrapper = new FakeElement("div", { attrs: { "aria-hidden": "true" } });
    wrapper.append(table);
    root.append(wrapper);
  } else {
    root.append(table);
  }
  return table;
}

function newFormDocument() {
  return new FakeDocument({ screen: "form" });
}

function sendReadForm(documentRef) {
  const previousDocument = globalThis.document;
  globalThis.document = documentRef;
  return new Promise((resolve) => {
    contentMessageListeners[0]({ type: "READ_FORM" }, {}, resolve);
  }).finally(() => {
    globalThis.document = previousDocument;
  });
}

test("the form reader exposes the Mesa contract", () => {
  assert.equal(typeof reader.readForm, "function");
  assert.equal(typeof reader.isVisibleForm, "function");
  assert.deepEqual(reader.FIELD_NAMES, Object.keys(ACT_FIELD_IDS));
});

test("a complete visible form reports identity, generation and field state", () => {
  const documentRef = buildActFormDocument({
    processKey: "102390/2026",
    values: { cargo: "Professor", matricula: "78.710-8/2" },
    selected: "José D'Ávila",
  });

  const form = reader.readForm(documentRef);

  assert.equal(form.identity.processKey, "102390/2026");
  assert.equal(form.identity.interestedNormalized, "jose d'avila");
  assert.equal(form.process.number, "102390");
  assert.equal(form.process.year, "2026");
  assert.equal(form.interested.original, "José D'Ávila");
  assert.equal(form.generation, 1);
  assert.equal(form.fields.cargo.value, "Professor");
  assert.equal(form.fields.cargo.disabled, false);
  assert.equal(form.fields.cargo.readOnly, false);
  assert.deepEqual(form.fields.modalidade.options, []);
});

test("an identity-valid form is readable when one content control is absent", () => {
  const partial = buildActFormDocument({
    selected: "Pessoa Exemplo",
    missingFields: ["matricula"],
  });
  const complete = buildActFormDocument({ selected: "Pessoa Exemplo" });

  const form = reader.readForm(partial);
  assert.notEqual(form, null);
  assert.equal(form.identity.processKey, "102390/2026");
  assert.equal(form.fields.matricula, undefined);
  assert.notEqual(reader.readForm(complete), null);
});

test("a content-field read error is isolated from identity and other controls", () => {
  const documentRef = buildActFormDocument({ selected: "Pessoa Exemplo" });
  const cargo = documentRef.getElementById(ACT_FIELD_IDS.cargo);
  Object.defineProperty(cargo, "value", {
    configurable: true,
    get() {
      throw new Error("field getter failed");
    },
  });

  const form = reader.readForm(documentRef);

  assert.equal(form.identity.processKey, "102390/2026");
  assert.equal(form.fields.cargo.readable, false);
  assert.equal(form.fields.matricula.readable, true);
});

test("a form without process identity anchors is not readable", () => {
  const documentRef = buildActFormDocument({
    selected: "Pessoa Exemplo",
    missingFields: ["txtNumeroProcesso"],
  });

  assert.equal(reader.readForm(documentRef), null);
});

test("process identity fields outside the act form do not qualify as a form", () => {
  const documentRef = buildActFormDocument({ selected: "Pessoa Exemplo" });
  const formElement = documentRef.getElementById("complementarAtoForm");
  const controls = [...formElement.children];
  documentRef.body.children = documentRef.body.children.filter((child) => child !== formElement);
  formElement.children = [];
  for (const control of controls) control.parentElement = null;
  documentRef.body.append(...controls);

  assert.equal(reader.readForm(documentRef), null);
});

test("a form hidden by an ancestor is rejected", () => {
  const documentRef = buildActFormDocument({ hiddenAncestor: true });

  assert.equal(reader.isVisibleForm(documentRef), false);
  assert.equal(reader.readForm(documentRef), null);
});

test("a form inside a zero-size frame is rejected", () => {
  const documentRef = buildActFormDocument({ frame: buildFrameElement({ visible: false }) });

  assert.equal(reader.isVisibleForm(documentRef), false);
  assert.equal(reader.readForm(documentRef), null);
});

test("a form inside a visible frame is read", () => {
  const documentRef = buildActFormDocument({
    frame: buildFrameElement({ visible: true }),
    selected: "Pessoa Exemplo",
  });

  const form = reader.readForm(documentRef);

  assert.notEqual(form, null);
  assert.equal(form.identity.processKey, "102390/2026");
});

test("a form without a selected interested person has no identity", () => {
  const documentRef = buildActFormDocument({ selected: null });

  assert.notEqual(reader.isVisibleForm(documentRef), false);
  assert.equal(reader.readForm(documentRef), null);
});

test("the option catalog of every select is read", () => {
  const documentRef = buildActFormDocument({
    selected: "Pessoa Exemplo",
    selects: {
      fundamento_legal: [
        { value: "", label: "Selecione uma fundamentação", selected: true },
        { value: "41", label: "Art. 6º e art. 7º da Emenda Constitucional 41/2003", disabled: true },
        { value: "47", label: "Emenda Constitucional 47/2005" },
      ],
      genero: [{ value: "F", label: "Feminino" }],
    },
  });

  const form = reader.readForm(documentRef);

  assert.equal(form.options.fundamento_legal.length, 3);
  assert.deepEqual(form.options.fundamento_legal[1], {
    value: "41",
    label: "Art. 6º e art. 7º da Emenda Constitucional 41/2003",
    disabled: true,
  });
  assert.equal(form.options.fundamento_legal[2].disabled, false);
  assert.equal(form.fields.fundamento_legal.options.length, 3);
  assert.equal(form.fields.genero.options[0].value, "F");
});

test("the option catalog reports disabled options and disabled optgroups", () => {
  const documentRef = buildActFormDocument({
    selected: "Pessoa Exemplo",
    selects: {
      fundamento_legal: [
        { value: "41", label: "Emenda Constitucional 41/2003" },
        { value: "42", label: "Emenda Constitucional 42/2003" },
      ],
    },
  });
  const select = documentRef.getElementById(ACT_FIELD_IDS.fundamento_legal);
  const options = select.querySelectorAll("option");
  options[1].disabled = true;

  const group = new FakeElement("optgroup");
  group.disabled = true;
  const grouped = new FakeElement("option", {
    value: "43",
    text: "Emenda Constitucional 43/2003",
  });
  group.append(grouped);
  select.append(group);

  const form = reader.readForm(documentRef);

  assert.deepEqual(form.options.fundamento_legal, [
    { value: "41", label: "Emenda Constitucional 41/2003", disabled: false },
    { value: "42", label: "Emenda Constitucional 42/2003", disabled: true },
    { value: "43", label: "Emenda Constitucional 43/2003", disabled: true },
  ]);
});

test("the generation advances only when the form state changes", () => {
  const documentRef = buildActFormDocument({ values: { cargo: "Professor" }, selected: "Pessoa Exemplo" });

  assert.equal(reader.readForm(documentRef).generation, 1);
  assert.equal(reader.readForm(documentRef).generation, 1);

  documentRef.getElementById("txtCargo").value = "Professor Classe H";

  assert.equal(reader.readForm(documentRef).generation, 2);
});

test("the reader never exposes a write surface", () => {
  for (const forbidden of ["applyFields", "overrideField", "writeControl", "submit"]) {
    assert.equal(Object.hasOwn(reader, forbidden), false, `unexpected ${forbidden}`);
  }
});

test("a hidden old form never wins over the one visible current form", async () => {
  const documentRef = newFormDocument();
  appendCandidate(documentRef, { processKey: "OLD/2025", hidden: true });
  appendCandidate(documentRef, { processKey: "CURRENT/2025" });

  const outcome = await sendReadForm(documentRef);

  assert.equal(outcome?.ok, true);
  assert.equal(outcome?.form.identity.processKey, "CURRENT/2025");
});

test("duplicate IDs in a hidden stale form do not contaminate the visible form", async () => {
  const documentRef = newFormDocument();
  appendCandidate(documentRef, { processKey: "OLD/2025", hidden: true });
  appendCandidate(documentRef, { processKey: "CURRENT/2025" });

  const outcome = await sendReadForm(documentRef);

  assert.equal(outcome?.ok, true);
  assert.equal(outcome?.form.process.number, "CURRENT");
  assert.equal(outcome?.form.process.year, "2025");
});

test("a checked radio in a hidden stale table does not contaminate the visible interested table", async () => {
  const documentRef = newFormDocument();
  const root = appendCandidate(documentRef, { processKey: "CURRENT/2025" });
  appendInterestedTable(root, { name: "Pessoa Antiga", hidden: true });

  const outcome = await sendReadForm(documentRef);

  assert.equal(outcome?.ok, true);
  assert.equal(outcome?.form.identity.interestedNormalized, "pessoa exemplo");
});

test("a hidden checked table cannot supply the selection when the visible table is unselected", async () => {
  const documentRef = newFormDocument();
  const root = appendCandidate(documentRef, { processKey: "CURRENT/2025", selected: null });
  appendInterestedTable(root, { name: "Pessoa Visível", checked: false });
  appendInterestedTable(root, { name: "Pessoa Antiga", hidden: true, tableId: "PessoasAssocicadas" });

  const outcome = await sendReadForm(documentRef);

  assert.equal(outcome?.ok, false);
  assert.equal(outcome?.code, "FORM_NOT_AVAILABLE");
});

test("multiple visible interested tables are ambiguous even if only one has a selection", async () => {
  const documentRef = newFormDocument();
  const root = appendCandidate(documentRef, { processKey: "CURRENT/2025" });
  appendInterestedTable(root, { name: "Pessoa Outra", checked: false });

  const outcome = await sendReadForm(documentRef);

  assert.equal(outcome?.ok, false);
  assert.equal(outcome?.code, "FORM_AMBIGUOUS");
});

test("a selected radio from a nested unrecognized table is not assigned to the outer row", async () => {
  const documentRef = newFormDocument();
  const root = appendCandidate(documentRef, { processKey: "CURRENT/2025", selected: null });
  const table = appendInterestedTable(root, { name: "Pessoa Atual" });
  const nested = new FakeElement("table", { id: "nestedUnrecognizedTable" });
  const nestedRow = new FakeElement("tr");
  const staleRadio = new FakeElement("input", { attrs: { type: "radio" } });
  staleRadio.checked = true;
  staleRadio.setAttribute("data-interested-name", "Pessoa Antiga");
  nestedRow.append(new FakeElement("td", { text: "Pessoa Antiga" }), staleRadio);
  nested.append(nestedRow);
  table.querySelector("tr").append(nested);

  const outcome = await sendReadForm(documentRef);

  assert.equal(outcome?.ok, true);
  assert.equal(outcome?.form.identity.interestedNormalized, "pessoa atual");
});

test("a selected radio in a hidden row cannot supply the interested-person identity", async () => {
  const documentRef = newFormDocument();
  const root = appendCandidate(documentRef, { processKey: "CURRENT/2025", selected: null });
  const table = appendInterestedTable(root, { name: "Pessoa Oculta" });
  table.querySelector("tr").hidden = true;

  const outcome = await sendReadForm(documentRef);

  assert.equal(outcome?.ok, false);
  assert.equal(outcome?.code, "FORM_NOT_AVAILABLE");
});

test("a checked radio outside the interested-person table is ignored", async () => {
  const documentRef = newFormDocument();
  appendCandidate(documentRef, { processKey: "CURRENT/2025" });
  const unrelatedRadio = new FakeElement("input", { attrs: { type: "radio" } });
  unrelatedRadio.checked = true;
  unrelatedRadio.setAttribute("data-interested-name", "Pessoa Externa");
  documentRef.body.append(unrelatedRadio);

  const outcome = await sendReadForm(documentRef);

  assert.equal(outcome?.ok, true);
  assert.equal(outcome?.form.identity.processKey, "CURRENT/2025");
  assert.equal(outcome?.form.identity.interestedNormalized, "pessoa exemplo");
});

test("the tbcomplementarato root is recognized", async () => {
  const documentRef = newFormDocument();
  appendCandidate(documentRef, {
    processKey: "CURRENT/2025",
    rootId: "tbcomplementarato",
    rootTag: "div",
  });

  assert.equal((await sendReadForm(documentRef))?.form?.identity.processKey, "CURRENT/2025");
});

test("the correctly spelled PessoasAssociadas table alias is recognized", async () => {
  const documentRef = newFormDocument();
  appendCandidate(documentRef, { processKey: "CURRENT/2025", tableId: "PessoasAssociadas" });

  const outcome = await sendReadForm(documentRef);

  assert.equal(outcome?.ok, true);
  assert.equal(outcome?.form.identity.interestedNormalized, "pessoa exemplo");
});

test("an unlabelled structural root is recognized from its form sentinels", async () => {
  const documentRef = newFormDocument();
  appendCandidate(documentRef, { processKey: "CURRENT/2025", rootId: "", rootTag: "div" });

  assert.equal((await sendReadForm(documentRef))?.form?.identity.processKey, "CURRENT/2025");
});

test("two visible valid forms are reported as FORM_AMBIGUOUS", async () => {
  const documentRef = newFormDocument();
  appendCandidate(documentRef, { processKey: "FIRST/2025" });
  appendCandidate(documentRef, { processKey: "SECOND/2025" });

  const outcome = await sendReadForm(documentRef);

  assert.equal(outcome?.ok, false);
  assert.equal(outcome?.code, "FORM_AMBIGUOUS");
});

test("a zero-size stale form does not make the visible current form ambiguous", async () => {
  const documentRef = newFormDocument();
  const stale = appendCandidate(documentRef, { processKey: "OLD/2025" });
  stale.getBoundingClientRect = () => ({ width: 0, height: 0 });
  stale.getClientRects = () => [];
  appendCandidate(documentRef, { processKey: "CURRENT/2025" });

  const outcome = await sendReadForm(documentRef);

  assert.equal(outcome?.ok, true);
  assert.equal(outcome?.form.identity.processKey, "CURRENT/2025");
});

test("a visible form without complete process identity fails closed", async () => {
  const documentRef = newFormDocument();
  appendCandidate(documentRef, { processKey: "CURRENT/2025", omitYear: true });

  const outcome = await sendReadForm(documentRef);
  assert.equal(outcome?.ok, false);
  assert.equal(outcome?.code, "FORM_NOT_AVAILABLE");
});
