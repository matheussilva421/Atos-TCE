import test from "node:test";
import assert from "node:assert/strict";

import { buildActFormDocument, buildFrameElement, ACT_FIELD_IDS } from "./fake-dom.mjs";

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

test("a late form is absent until every mapped control exists", () => {
  const incomplete = buildActFormDocument({ complete: false, selected: "Pessoa Exemplo" });
  const complete = buildActFormDocument({ selected: "Pessoa Exemplo" });

  assert.equal(reader.readForm(incomplete), null);
  assert.equal(reader.hasCompleteForm(incomplete), false);
  assert.notEqual(reader.readForm(complete), null);
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
  });
  assert.equal(form.fields.fundamento_legal.options.length, 2);
  assert.equal(form.fields.genero.options[0].value, "F");
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
