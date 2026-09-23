import test from "node:test";
import assert from "node:assert/strict";

import { FakeElement, buildActFormDocument, buildFrameElement, ACT_FIELD_IDS } from "./fake-dom.mjs";

await import("../lib/area-snapshot.js");
await import("../content/detect-form.js");

const reader = globalThis.TCEFormReader;

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

  const form = reader.readForm(partial);

  assert.notEqual(form, null);
  assert.equal(form.identity.processKey, "102390/2026");
  assert.equal(form.fields.matricula, undefined);
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
        { value: "41", label: "Art. 6º e art. 7º da Emenda Constitucional 41/2003" },
      ],
      genero: [{ value: "F", label: "Feminino" }],
    },
  });

  const form = reader.readForm(documentRef);

  assert.equal(form.options.fundamento_legal.length, 2);
  assert.deepEqual(form.options.fundamento_legal[1], {
    value: "41",
    label: "Art. 6º e art. 7º da Emenda Constitucional 41/2003",
    disabled: false,
  });
  assert.equal(form.fields.fundamento_legal.options.length, 2);
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
  const grouped = new FakeElement("option", { value: "43", text: "Emenda Constitucional 43/2003" });
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
