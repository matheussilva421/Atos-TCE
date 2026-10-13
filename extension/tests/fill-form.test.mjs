import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { ACT_FIELD_IDS, buildActFormDocument, FakeDocument, FakeElement } from "./fake-dom.mjs";
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

function applyFill(options = {}) {
  const documentRef = options.documentRef ?? globalThis.document;
  const current = reader.readForm(documentRef);
  return filler.applyFill({
    ...options,
    documentRef,
    documentNonce: options.documentNonce ?? current?.documentNonce,
  });
}

test("the filler writes only to the visible current form when IDs repeat in a hidden stale form", () => {
  const documentRef = new FakeDocument({ screen: "form" });
  documentRef.defaultView = {
    location: { href: "https://portal.test/complementarato.asp" },
    frameElement: null,
    parent: null,
    getComputedStyle: () => ({}),
  };
  documentRef.defaultView.parent = documentRef.defaultView;

  const addCandidate = (processKey, interested, hidden = false) => {
    const root = new FakeElement("form", { id: "complementarAtoForm" });
    const [number, year] = processKey.split("/");
    root.append(
      new FakeElement("input", { id: "txtNumeroProcesso", value: number }),
      new FakeElement("input", { id: "txtAnoProcesso", value: year }),
    );
    for (const id of Object.values(ACT_FIELD_IDS)) {
      root.append(new FakeElement("input", { id, value: "" }));
    }
    const table = new FakeElement("table", { id: "PessoasAssocicadas" });
    const row = new FakeElement("tr");
    const radio = new FakeElement("input", { attrs: { type: "radio" } });
    radio.checked = true;
    radio.setAttribute("data-interested-name", interested);
    row.append(new FakeElement("td", { text: interested }), radio);
    table.append(row);
    root.append(table);
    if (hidden) {
      const wrapper = new FakeElement("div", { attrs: { "aria-hidden": "true" } });
      wrapper.append(root);
      documentRef.body.append(wrapper);
    } else {
      documentRef.body.append(root);
    }
    return root;
  };

  const oldForm = addCandidate("999999/2025", "Pessoa Antiga", true);
  const currentForm = addCandidate("102390/2026", "Pessoa Exemplo");
  const oldCargo = oldForm.querySelector("#txtCargo");
  const currentCargo = currentForm.querySelector("#txtCargo");
  const form = reader.readForm(documentRef);
  assert.equal(form.identity.processKey, "102390/2026");
  assert.equal(reader.findFieldControl(documentRef, "cargo", form.identity, form.generation), currentCargo);
  assert.equal(
    reader.findFieldControl(documentRef, "cargo", { ...form.identity, processKey: "999999/2025" }, form.generation),
    null,
  );
  assert.equal(reader.findFieldControl(documentRef, "cargo", form.identity, form.generation + 1), null);

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor" },
  });

  assert.equal(result.field_results.cargo.status, "changed");
  assert.equal(oldCargo.writeCount, 0, "the hidden stale form is never a write target");
  assert.equal(currentCargo.value, "Professor");
  assert.equal(currentCargo.writeCount, 1);
});

test("the native value setter is used and the events bubble", () => {
  const { documentRef, form } = preparedForm();

  const result = applyFill({
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

test("field write and reread durations stay outside functional field results", () => {
  const { documentRef, form } = preparedForm();
  const ticks = [10, 13, 20, 25];

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor" },
    deps: { monotonicNow: () => ticks.shift() },
  });

  assert.deepEqual(result.diagnostic_events, [
    { step: "field_write", field: "cargo", elapsed_ms: 3, result: "ok" },
    { step: "field_reread", field: "cargo", elapsed_ms: 5, result: "ok" },
  ]);
  assert.deepEqual(result.field_results.cargo, {
    before: "",
    proposed: "Professor",
    after: "Professor",
    status: "changed",
  });
  assert.equal("diagnostic_events" in result.field_results.cargo, false);
});

test("an already correct value is preserved and never rewritten", () => {
  const { documentRef, form } = preparedForm({ values: { cargo: "Professor" } });

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "preserved");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 0);
});

test("an unavailable select option is reported without refusing the request", () => {
  const selects = {
    fundamento_legal: [{ value: "41", label: "Art. 6º e art. 7º da Emenda Constitucional 41/2003" }],
  };
  const absent = preparedForm({ selects });
  const refused = applyFill({
    documentRef: absent.documentRef,
    identity: absent.form.identity,
    generation: absent.form.generation,
    fields: { fundamento_legal: "99" },
  });

  assert.equal(refused.ok, true);
  assert.equal(refused.field_results.fundamento_legal.status, "option_unavailable");
  assert.equal(refused.field_results.fundamento_legal.warning, "option_unavailable");
  assert.equal(absent.documentRef.getElementById("txtFundamentoLegal").writeCount, 0);

  const present = preparedForm({ selects });
  const accepted = applyFill({
    documentRef: present.documentRef,
    identity: present.form.identity,
    generation: present.form.generation,
    fields: { fundamento_legal: "41" },
  });

  assert.equal(accepted.ok, true);
  assert.equal(accepted.field_results.fundamento_legal.status, "changed");
  assert.equal(present.documentRef.getElementById("txtFundamentoLegal").value, "41");
});

test("an option in a disabled optgroup cannot be selected", () => {
  const prepared = preparedForm({
    selects: {
      fundamento_legal: [{ value: "41", label: "EC 41/2003" }],
    },
  });
  const select = prepared.documentRef.getElementById("txtFundamentoLegal");
  const option = select.querySelector("option");
  const group = new FakeElement("optgroup");
  group.disabled = true;
  select.children = [];
  group.append(option);
  select.append(group);
  const form = reader.readForm(prepared.documentRef);

  const result = applyFill({
    documentRef: prepared.documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { fundamento_legal: "41" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.fundamento_legal.status, "option_unavailable");
  assert.equal(select.writeCount, 0);
});

test("an identity mismatch writes nothing at all", () => {
  const { documentRef, form } = preparedForm();

  const result = applyFill({
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

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation + 5,
    fields: { cargo: "Professor" },
  });

  assert.equal(result.ok, false);
  assert.equal(result.code, "STALE_GENERATION");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 0);
});

test("a plan from another document with the same identity and generation writes nothing", () => {
  const documentA = preparedForm();
  const documentB = preparedForm();
  assert.deepEqual(documentA.form.identity, documentB.form.identity);
  assert.equal(documentA.form.generation, 1);
  assert.equal(documentB.form.generation, 1);

  const result = applyFill({
    documentRef: documentB.documentRef,
    identity: documentA.form.identity,
    generation: documentA.form.generation,
    documentNonce: documentA.form.documentNonce,
    fields: { cargo: "Professor" },
  });

  assert.equal(result.ok, false);
  assert.equal(result.code, "STALE_FORM");
  assert.equal(documentB.documentRef.getElementById("txtCargo").writeCount, 0);
  assert.equal(documentB.documentRef.getElementById("txtCargo").value, "");
});

test("a fill without a document nonce is refused before any field write", () => {
  const { documentRef, form } = preparedForm();

  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor" },
  });

  assert.equal(result.ok, false);
  assert.equal(result.code, "STALE_FORM");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 0);
});

test("a generation that is not a positive integer writes nothing at all", () => {
  // CR-F2: an absent or malformed generation can never be "recent enough".
  for (const generation of [undefined, null, "3", 0, -1, 2.5, true, Number.NaN]) {
    const { documentRef, form } = preparedForm();

    const result = applyFill({
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

test("a disabled or readOnly control is never written", () => {
  const disabled = preparedForm();
  disabled.documentRef.getElementById("txtCargo").disabled = true;
  const disabledForm = reader.readForm(disabled.documentRef);
  const readOnly = preparedForm();
  readOnly.documentRef.getElementById("txtMatricula").readOnly = true;
  const readOnlyForm = reader.readForm(readOnly.documentRef);

  const disabledResult = applyFill({
    documentRef: disabled.documentRef,
    identity: disabledForm.identity,
    generation: disabledForm.generation,
    fields: { cargo: "Professor" },
  });
  const readOnlyResult = applyFill({
    documentRef: readOnly.documentRef,
    identity: readOnlyForm.identity,
    generation: readOnlyForm.generation,
    fields: { matricula: "78.710-8/2" },
  });

  assert.equal(disabledResult.ok, true);
  assert.equal(disabledResult.field_results.cargo.status, "disabled");
  assert.equal(disabled.documentRef.getElementById("txtCargo").writeCount, 0);
  assert.equal(readOnlyResult.ok, true);
  assert.equal(readOnlyResult.field_results.matricula.status, "disabled");
  assert.equal(readOnly.documentRef.getElementById("txtMatricula").writeCount, 0);
});

test("a reread failure is field-local and a later field still runs", () => {
  const { documentRef, form } = preparedForm();
  let calls = 0;
  const lyingReader = {
    readForm: (documentReference) => {
      calls += 1;
      const real = reader.readForm(documentReference);
      if (calls !== 2) return real;
      return { ...real, fields: { ...real.fields, cargo: { ...real.fields.cargo, value: "" } } };
    },
    findFieldControl: reader.findFieldControl,
  };

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
    deps: { reader: lyingReader },
  });

  assert.equal(result.ok, true);
  assert.equal(result.code, null);
  assert.equal(result.field_results.cargo.status, "failed");
  assert.equal(result.field_results.cargo.warning, "field_reread_mismatch");
  assert.equal(result.field_results.cargo.after, "");
  assert.equal(result.field_results.matricula.status, "changed");
  assert.equal(documentRef.getElementById("txtMatricula").value, "78.710-8/2");
});

test("a field reread exception is local when identity can still be confirmed", () => {
  const { documentRef, form } = preparedForm();
  let calls = 0;
  const flakyReader = {
    readForm: (documentReference) => {
      calls += 1;
      if (calls === 2) throw new Error("releitura do cargo falhou");
      return reader.readForm(documentReference);
    },
    findFieldControl: reader.findFieldControl,
    readProcess: reader.readProcess,
    readInterested: reader.readInterested,
    isVisibleForm: reader.isVisibleForm,
  };

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
    deps: { reader: flakyReader },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "failed");
  assert.equal(result.field_results.cargo.warning, "field_reread_failed");
  assert.match(result.field_results.cargo.error, /releitura do cargo falhou/u);
  assert.equal(result.field_results.matricula.status, "changed");
  assert.equal(documentRef.getElementById("txtMatricula").value, "78.710-8/2");
});

test("a write event failure is field-local and a later field still runs", () => {
  const { documentRef, form } = preparedForm();
  documentRef.getElementById("txtCargo").dispatchEvent = () => {
    throw new Error("evento de escrita falhou");
  };

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "failed");
  assert.equal(result.field_results.cargo.warning, "field_write_failed");
  assert.match(result.field_results.cargo.error, /evento de escrita falhou/u);
  assert.equal(result.field_results.matricula.status, "changed");
  assert.equal(documentRef.getElementById("txtMatricula").value, "78.710-8/2");
});

test("a missing proposal is reported, not invented", () => {
  const { documentRef, form } = preparedForm();

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "", matricula: null },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "missing_proposal");
  assert.equal(result.field_results.matricula.status, "missing_proposal");
  assert.equal(result.field_results.cargo.warning, "missing_proposal");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 0);
});

test("a disabled field does not stop an independent writable field", () => {
  const { documentRef } = preparedForm();
  documentRef.getElementById("txtMatricula").disabled = true;
  const form = reader.readForm(documentRef);

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.code, null);
  assert.equal(result.field_results.matricula.status, "disabled");
  assert.equal(result.field_results.matricula.warning, "control_disabled");
  assert.equal(result.field_results.cargo.status, "changed");
  assert.equal(documentRef.getElementById("txtCargo").value, "Professor");
  assert.equal(documentRef.getElementById("txtMatricula").writeCount, 0);
});

test("an unavailable select option does not stop a text field", () => {
  const selects = { fundamento_legal: [{ value: "41", label: "Emenda 41/2003" }] };
  const { documentRef, form } = preparedForm({ selects });

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", fundamento_legal: "99" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.fundamento_legal.status, "option_unavailable");
  assert.equal(result.field_results.fundamento_legal.warning, "option_unavailable");
  assert.equal(result.field_results.cargo.status, "changed");
  assert.equal(documentRef.getElementById("txtCargo").value, "Professor");
  assert.equal(documentRef.getElementById("txtFundamentoLegal").writeCount, 0);
});

test("a missing control is reported without stopping another field", () => {
  const { documentRef, form } = preparedForm();

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", campo_inexistente: "x" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.campo_inexistente.status, "not_found");
  assert.equal(result.field_results.campo_inexistente.warning, "control_not_found");
  assert.equal(result.field_results.cargo.status, "changed");
  assert.equal(documentRef.getElementById("txtCargo").value, "Professor");
});

test("legal option and independent text controls are written around a missing field and divergence", () => {
  const selects = {
    fundamento_legal: [{ value: "EC41", label: "EC 41/2003" }],
  };
  const { documentRef, form } = preparedForm({
    selects,
    values: { cargo: "Cargo divergente preenchido no portal" },
    missingFields: ["txtMatricula"],
  });

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: {
      fundamento_legal: "EC41",
      data_publicacao_doe: "27/03/2024",
      cargo: "Professor",
      matricula: "78.710-8/2",
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.fundamento_legal.status, "changed");
  assert.equal(result.field_results.fundamento_legal.after, "EC41");
  assert.equal(result.field_results.data_publicacao_doe.status, "changed");
  assert.equal(result.field_results.cargo.status, "preserved");
  assert.equal(result.field_results.cargo.warning, "existing_value_divergence");
  assert.equal(result.field_results.matricula.status, "not_found");
  assert.equal(documentRef.getElementById("txtFundamentoLegal").value, "EC41");
  assert.equal(documentRef.getElementById("txtDataDOE").value, "27/03/2024");
  assert.equal(documentRef.getElementById("txtCargo").value, "Cargo divergente preenchido no portal");
  assert.equal(documentRef.getElementById("txtCargo").writeCount, 0);
});

test("a divergent existing value is preserved while another field is changed", () => {
  const { documentRef, form } = preparedForm({ values: { cargo: "Cargo preenchido no portal" } });

  const result = applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "78.710-8/2" },
  });

  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "preserved");
  assert.equal(result.field_results.cargo.warning, "existing_value_divergence");
  assert.equal(result.field_results.matricula.status, "changed");
  assert.equal(documentRef.getElementById("txtCargo").value, "Cargo preenchido no portal");
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
