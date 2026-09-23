import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { buildActFormDocument } from "./fake-dom.mjs";
import { COMMAND_TYPES, FORBIDDEN_COMMAND_TYPES } from "../lib/protocol.js";

await import("../lib/area-snapshot.js");
await import("../content/detect-form.js");
await import("../content/fill-form.js");

const here = dirname(fileURLToPath(import.meta.url));
const extensionRoot = join(here, "..");
const reader = globalThis.TCEFormReader;
const filler = globalThis.TCEFillForm;

function preparedForm(options = {}) {
  const documentRef = buildActFormDocument({ selected: "Pessoa Exemplo", ...options });
  return { documentRef, form: reader.readForm(documentRef) };
}

test("the native value setter is used and the events bubble", () => {
  const { documentRef, form } = preparedForm();

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor" },
  });

  assert.equal(result.ok, true);
  const control = documentRef.getElementById("txtCargo");
  assert.equal(control.value, "Professor");
  assert.equal(control.writeCount, 1);
  assert.deepEqual(control.events, ["input", "change", "blur"]);
  assert.deepEqual(result.field_results.cargo, {
    before: "",
    proposed: "Professor",
    after: "Professor",
    status: "changed",
  });
  assert.equal(result.generation_after, 2);
});

test("an already correct value is preserved and never rewritten", () => {
  const { documentRef, form } = preparedForm({ values: { cargo: "Professor" } });

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "preserved");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 0);
});

test("a select only accepts a value that exists in its current catalog", () => {
  const selects = {
    fundamento_legal: [{ value: "41", label: "Art. 6º e art. 7º da Emenda Constitucional 41/2003" }],
  };
  const absent = preparedForm({ selects });
  const refused = filler.applyFill({
    documentRef: absent.documentRef,
    identity: absent.form.identity,
    generation: absent.form.generation,
    fields: { fundamento_legal: "99" },
  });

  assert.equal(refused.ok, true);
  assert.equal(refused.field_results.fundamento_legal.status, "option_unavailable");
  assert.equal(absent.documentRef.getElementById("txtFundamentoLegal").writeCount, 0);

  const present = preparedForm({ selects });
  const accepted = filler.applyFill({
    documentRef: present.documentRef,
    identity: present.form.identity,
    generation: present.form.generation,
    fields: { fundamento_legal: "41" },
  });

  assert.equal(accepted.ok, true);
  assert.equal(accepted.field_results.fundamento_legal.status, "changed");
  assert.equal(present.documentRef.getElementById("txtFundamentoLegal").value, "41");
});

test("an identity mismatch writes nothing at all", () => {
  const { documentRef, form } = preparedForm();

  const result = filler.applyFill({
    documentRef,
    identity: { processKey: "999999/2026", interestedNormalized: "pessoa exemplo" },
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
  });

  assert.equal(result.ok, false);
  assert.equal(result.code, "IDENTITY_MISMATCH");
  assert.deepEqual(result.field_results, {});
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 0);
  assert.equal(documentRef.getElementById("txtMatricula").writeCount, 0);
});

test("a stale generation writes nothing at all", () => {
  const { documentRef, form } = preparedForm();

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation + 5,
    fields: { cargo: "Professor" },
  });

  assert.equal(result.ok, false);
  assert.equal(result.code, "STALE_GENERATION");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 0);
});

test("a generation that is not a positive integer writes nothing at all", () => {
  // CR-F2: an absent or malformed generation can never be "recent enough".
  for (const generation of [undefined, null, "3", 0, -1, 2.5, true, Number.NaN]) {
    const { documentRef, form } = preparedForm();

    const result = filler.applyFill({
      documentRef,
      identity: form.identity,
      generation,
      fields: { cargo: "Professor" },
    });

    const label = `generation=${String(generation)}`;
    assert.equal(result.ok, false, label);
    assert.equal(result.code, "GENERATION_MISSING", label);
    assert.deepEqual(result.field_results, {}, label);
    assert.equal(result.generation_after, form.generation, label);
    assert.equal(documentRef.getElementById("txtCargo").writeCount, 0, label);
  }
});

test("a disabled field does not stop an independent writable field", () => {
  const disabled = preparedForm();
  disabled.documentRef.getElementById("txtMatricula").disabled = true;
  const disabledForm = reader.readForm(disabled.documentRef);

  const disabledResult = filler.applyFill({
    documentRef: disabled.documentRef,
    identity: disabledForm.identity,
    generation: disabledForm.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
  });

  assert.equal(disabledResult.ok, true);
  assert.equal(disabledResult.field_results.cargo.status, "changed");
  assert.equal(disabledResult.field_results.matricula.status, "disabled");
  assert.equal(disabled.documentRef.getElementById("txtCargo").value, "Professor");
  assert.equal(disabled.documentRef.getElementById("txtCargo").writeCount, 1);
  assert.equal(disabled.documentRef.getElementById("txtMatricula").writeCount, 0);
});

test("a field that does not reread as proposed fails only that field", () => {
  const { documentRef, form } = preparedForm();
  let calls = 0;
  const lyingReader = {
    readForm: (documentReference) => {
      calls += 1;
      const real = reader.readForm(documentReference);
      if (calls === 1) return real;
      return { ...real, fields: { ...real.fields, cargo: { ...real.fields.cargo, value: "" } } };
    },
  };

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
    deps: { reader: lyingReader },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "failed");
  assert.equal(result.field_results.cargo.after, "");
  assert.equal(result.field_results.matricula.status, "changed");
  assert.equal(documentRef.getElementById("txtMatricula").value, "78.710-8/2");
});

test("a field readback exception fails only that field and other writes continue", () => {
  const { documentRef, form } = preparedForm();
  const cargo = documentRef.getElementById("txtCargo");
  Object.defineProperty(cargo, "value", {
    configurable: true,
    get() {
      if (this._value) throw new Error("field readback failed");
      return this._value;
    },
  });

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "failed");
  assert.equal(result.field_results.cargo.warning, "field_read_failed");
  assert.equal(result.field_results.matricula.status, "changed");
});

test("a missing proposal is reported, not invented", () => {
  const { documentRef, form } = preparedForm();

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "", matricula: null },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "missing");
  assert.equal(result.field_results.matricula.status, "missing");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 0);
});

test("a later disabled field does not undo an earlier independent write", () => {
  const { documentRef } = preparedForm();
  documentRef.getElementById("txtMatricula").disabled = true;
  const form = reader.readForm(documentRef);

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.matricula.status, "disabled");
  assert.equal(result.field_results.cargo.status, "changed");
  assert.equal(documentRef.getElementById("txtCargo").value, "Professor");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 1);
  assert.equal(documentRef.getElementById("txtMatricula").writeCount, 0);
});

test("an option that is no longer available does not hold a text field back", () => {
  const selects = { fundamento_legal: [{ value: "41", label: "Emenda 41/2003" }] };
  const { documentRef, form } = preparedForm({ selects });

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", fundamento_legal: "99" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.fundamento_legal.status, "option_unavailable");
  assert.equal(result.field_results.cargo.status, "changed");
  assert.equal(documentRef.getElementById("txtCargo").value, "Professor");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 1);
  assert.equal(documentRef.getElementById("txtFundamentoLegal").writeCount, 0);
});

test("a disabled select option is unavailable and does not stop a text field", () => {
  const selects = { fundamento_legal: [{ value: "41", label: "Emenda 41/2003" }] };
  const { documentRef } = preparedForm({ selects });
  documentRef.getElementById("txtFundamentoLegal").querySelectorAll("option")[0].disabled = true;
  const form = reader.readForm(documentRef);

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", fundamento_legal: "41" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.fundamento_legal.status, "option_unavailable");
  assert.equal(result.field_results.cargo.status, "changed");
  assert.equal(documentRef.getElementById("txtFundamentoLegal").writeCount, 0);
});

test("a write failure is reported per field and later fields still run", () => {
  const { documentRef, form } = preparedForm();
  const cargo = documentRef.getElementById("txtCargo");
  Object.defineProperty(cargo, "value", {
    configurable: true,
    get() {
      return this._value;
    },
    set() {
      throw new Error("write blocked");
    },
  });

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "failed");
  assert.equal(result.field_results.matricula.status, "changed");
  assert.equal(documentRef.getElementById("txtMatricula").value, "78.710-8/2");
});

test("a control the plan asks for but the form does not have does not hold other fields back", () => {
  const { documentRef, form } = preparedForm();

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", campo_inexistente: "x" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.campo_inexistente.status, "not_found");
  assert.equal(result.field_results.cargo.status, "changed");
  assert.equal(documentRef.getElementById("txtCargo").value, "Professor");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 1);
});

test("a divergent existing value is preserved while another field is filled", () => {
  const { documentRef, form } = preparedForm({ values: { cargo: "Professor Classe H" } });

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "preserved");
  assert.equal(result.field_results.cargo.warning, "existing_value_divergence");
  assert.equal(result.field_results.matricula.status, "changed");
  assert.equal(documentRef.getElementById("txtCargo").value, "Professor Classe H");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 0);
});

test("the filler cannot submit anything", () => {
  for (const forbidden of FORBIDDEN_COMMAND_TYPES) {
    assert.equal(Object.values(COMMAND_TYPES).includes(forbidden), false, `${forbidden} must not exist`);
  }
  assert.equal(Object.hasOwn(filler, "submit"), false);
  assert.equal(Object.hasOwn(filler, "finalize"), false);
});

test("no ffill source mentions a submit command or a final button", () => {
  // lib/protocol.js is excluded on purpose: it names the forbidden types inside
  // FORBIDDEN_COMMAND_TYPES so the absence can be asserted at all.
  for (const relative of [
    "content/fill-form.js",
    "content/navigate.js",
    "content/detect-form.js",
    "background/router.js",
  ]) {
    const source = readFileSync(join(extensionRoot, relative), "utf8");
    for (const forbidden of ["AUTO_SUBMIT", "COMPLEMENT_ACT", "autoSubmit", "real_send"]) {
      assert.equal(source.includes(forbidden), false, `${relative} mentions ${forbidden}`);
    }
  }
  const fillerSource = readFileSync(join(extensionRoot, "content/fill-form.js"), "utf8");
  for (const forbidden of ["ComplementarAto", "btnComplementar", "finalizar", ".submit("]) {
    assert.equal(fillerSource.includes(forbidden), false, `the filler mentions ${forbidden}`);
  }
});
