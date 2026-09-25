import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildFormDocument,
  buildInterestedDocument,
  buildListDocument,
  FakeDocument,
  FakeElement,
} from "./fake-dom.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const extensionRoot = join(here, "..");
const contractRoot = join(extensionRoot, "..", "devtools", "area-restrita");
const allowedStates = ["list", "interested", "form", "buttons", "transitioning", "unknown", "ambiguous"];

await import("../lib/area-snapshot.js");
await import("../content/detect-form.js");

const snapshot = globalThis.TCEAreaSnapshot;
const formReader = globalThis.TCEFormReader;

function readJSON(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function contract() {
  return readJSON(join(contractRoot, "portal-contract.json"));
}

function fixture(name) {
  return readJSON(join(contractRoot, "fixtures", name));
}

function setRoute(documentRef, route) {
  documentRef.defaultView.location.href = `https://portal.test/${route}`;
  return documentRef;
}

function addPersonRadio(root, interestedName, { checked = false, name = "escolha" } = {}) {
  const table = new FakeElement("table", { id: "PessoasAssocicadas" });
  const row = new FakeElement("tr");
  const radio = new FakeElement("input", {
    attrs: {
      type: "radio",
      name,
      "data-interested-name": interestedName,
    },
  });
  radio.checked = checked;
  row.append(radio, new FakeElement("td", { text: interestedName }));
  table.append(row);
  root.append(table);
  return radio;
}

function formDocument(formFixture, fields = formFixture.field_ids) {
  const values = Object.fromEntries(fields.map((id) => [id, "valor fictício"]));
  const documentRef = setRoute(
    buildFormDocument({ processKey: formFixture.process_key, fields: values }),
    formFixture.route
  );
  const root = documentRef.getElementById("complementarAtoForm");
  if (formFixture.root_id !== "complementarAtoForm") root.setAttribute("id", formFixture.root_id);
  if (formFixture.root_name) root.setAttribute("name", formFixture.root_name);
  addPersonRadio(root, formFixture.interested_normalized, {
    checked: true,
    name: formFixture.interested_radio_name,
  });
  return documentRef;
}

test("the contract exposes the approved state vocabulary and matches current scanner roles", () => {
  const schema = readJSON(join(contractRoot, "portal-contract.schema.json"));
  const value = contract();

  assert.equal(schema.properties.schema_version.minimum, 1);
  assert.ok(Number.isInteger(value.schema_version) && value.schema_version >= 1);
  assert.deepEqual(Object.keys(value.states).sort(), [...allowedStates].sort());
  assert.ok(snapshot.PORTAL_ROLES.every((role) => allowedStates.includes(role)));
  assert.deepEqual(value.forbidden_actions, ["finalize", "submit", "sign", "tramitate"]);
});

test("form contract sentinels are covered by the reader and structural scanner", () => {
  const formSpec = contract().states.form;
  const formFixture = fixture("form.json");

  assert.equal(formSpec.root_id, formFixture.root_id);
  assert.deepEqual(formSpec.identity_sentinel_ids, [...formReader.IDENTITY_SENTINEL_IDS]);
  assert.deepEqual(formSpec.field_ids, Object.values(formReader.FIELD_MAP));
  assert.deepEqual(formFixture.identity_sentinel_ids, formSpec.identity_sentinel_ids);
  assert.deepEqual(formFixture.field_ids, formSpec.field_ids);

  for (const fieldId of formSpec.field_ids) {
    const documentRef = formDocument(formFixture, [fieldId]);
    assert.equal(snapshot.detectDocumentRole(documentRef), "form", `${fieldId} must identify a form`);
    assert.ok(formReader.readForm(documentRef), `${fieldId} must be readable by the form reader`);
  }
});

test("the sanitized LIST fixture is classified by the runtime scanner", () => {
  const current = fixture("list-page.json");
  assert.ok(contract().states.list.sentinels.includes(`#${current.pagination_id}`));
  assert.equal(current.table_id, "tbproc01");
  assert.equal(current.state, "list");
  const documentRef = setRoute(
    buildListDocument({
      page: current.page_number,
      rows: [{ processKey: current.process_key, interested: "Pessoa Teste" }],
      hasNext: false,
    }),
    current.route
  );
  documentRef.body.append(new FakeElement("input", { id: "NumeroPagina", value: current.page_number }));

  assert.equal(snapshot.scan(documentRef).role, "list");
  assert.equal(snapshot.pageInfo(documentRef).page, Number(current.page_number));
});

test("the sanitized INTERESTED fixture is classified by the runtime scanner", () => {
  const current = fixture("interested.json");
  assert.ok(contract().states.interested.sentinels.includes(current.radio_selector));
  assert.ok(contract().states.interested.sentinels.includes(`#${current.table_id}`));
  assert.equal(current.state, "interested");
  const documentRef = setRoute(
    buildInterestedDocument({ processKey: current.process_key, people: ["Pessoa Teste"] }),
    current.route
  );
  documentRef.querySelector('input[type="radio"]').setAttribute("name", "escolha");
  assert.ok(documentRef.querySelector(current.radio_selector));

  assert.equal(snapshot.scan(documentRef).role, "interested");
});

test("the sanitized FORM fixture is recognized by both scanner and form reader", () => {
  const current = fixture("form.json");
  const documentRef = formDocument(current);

  assert.equal(snapshot.scan(documentRef).role, "form");
  assert.equal(formReader.readForm(documentRef).identity.processKey, current.process_key);
  assert.equal(
    formReader.readForm(documentRef).identity.interestedNormalized,
    current.interested_normalized
  );
});

test("the live sanitized FORM structure records its legacy form root and remains readable", () => {
  const observed = fixture("live-form-structure.json");
  const current = fixture("form.json");
  const documentRef = formDocument({
    ...current,
    root_id: observed.form.id,
    root_name: observed.form.name,
  });

  assert.equal(observed.state, "form");
  assert.ok(observed.route.endsWith("/ComplementarAto.asp"));
  assert.deepEqual(observed.framePath, ["iframe#iframeOBJ", "frame#form"]);
  assert.deepEqual(observed.form, { id: "Form1", name: "form1", method: "POST", controlCount: 26 });
  assert.equal(observed.childFrameCount, 0);
  assert.equal(contract().states.form.root_id, observed.form.id);
  assert.equal(documentRef.getElementById(observed.form.id).getAttribute("name"), "form1");
  assert.equal(formReader.hasIdentityAnchors(documentRef), true);
  assert.equal(formReader.readForm(documentRef).identity.processKey, current.process_key);
});

test("the live frame tree distinguishes one visible form from stale sibling documents", () => {
  const observed = fixture("live-frame-tree.json");
  const forms = observed.frames.filter((frame) => frame.route.endsWith("/ComplementarAto.asp"));
  const visibleForms = forms.filter((frame) => frame.frameBox.width > 0 && frame.frameBox.height > 0);

  assert.equal(forms.length, 3);
  assert.equal(visibleForms.length, 1);
  assert.equal(visibleForms[0].framePath[0].name, "iframe4");
  assert.equal(visibleForms[0].forms[0].controlCount, 26);
  assert.ok(forms.filter((frame) => frame.frameBox.width === 0).length >= 2);
  assert.equal(Object.hasOwn(visibleForms[0].forms[0], "value"), false);
});

test("the BUTTONS fixture is classified as buttons and cannot be mistaken for a form", () => {
  const current = fixture("buttons.json");
  assert.ok(contract().states.buttons.sentinels.includes(`[data-action=${current.data_action}]`));
  const documentRef = setRoute(new FakeDocument({ screen: "buttons" }), current.route);
  documentRef.body.append(
    new FakeElement(current.control_tag, { text: current.control_text, attrs: { "data-action": current.data_action } })
  );

  assert.equal(snapshot.scan(documentRef).role, "buttons");
  assert.equal(formReader.readForm(documentRef), null);
});

test("the live process chooser route stays unknown and is not read as the legal form", () => {
  const current = fixture("process-chooser.json");
  const documentRef = setRoute(new FakeDocument({ screen: "unknown" }), current.route);
  for (const control of current.controls) {
    documentRef.body.append(
      new FakeElement(control.tag, {
        id: control.id ?? "",
        attrs: { name: control.name ?? "", type: control.type ?? "" },
      })
    );
  }

  assert.equal(snapshot.scan(documentRef).role, "unknown");
  assert.equal(formReader.readForm(documentRef), null);
  assert.ok(contract().routes[current.route].allowed_roles.includes(current.state));
});

test("known routes and the list/buttons sibling-frame relation are explicit", () => {
  const routes = contract().routes;

  assert.deepEqual(Object.keys(routes).sort(), ["ComplementarAto.asp", "ProcessonoSetor.asp", "botoesNOVO.asp"]);
  assert.deepEqual(routes["ComplementarAto.asp"].allowed_roles, ["interested", "form", "unknown"]);
  assert.equal(routes["botoesNOVO.asp"].frame_relation.relative_to, "ProcessonoSetor.asp");
  assert.equal(routes["botoesNOVO.asp"].frame_relation.relation, "sibling");

  for (const name of ["list-page.json", "interested.json", "form.json", "buttons.json", "process-chooser.json"]) {
    const current = fixture(name);
    assert.ok(routes[current.route].allowed_roles.includes(current.state), name);
  }
});

test("the live pagination fixture records the actual page window and scan mismatch", () => {
  const observed = fixture("live-pagination.json");

  assert.equal(observed.state, "list");
  assert.ok(contract().routes["ProcessonoSetor.asp"].allowed_roles.includes(observed.state));
  assert.equal(observed.marker.raw_value, "5159");
  assert.equal(observed.page_window.total, 1197);
  assert.equal(observed.pagination.page_count, 40);
  assert.equal(observed.page_window.end, 30);
  assert.equal(observed.next_page_window.start, 31);
  assert.equal(observed.next_page_window.duplicate_composite_identities, 0);
  assert.equal(observed.scan_page_observation.reported_total_pages, 100249);
  assert.notEqual(observed.scan_page_observation.reported_total_pages, observed.pagination.page_count);
  assert.equal(Object.hasOwn(observed, "process_keys"), false);
  assert.equal(Object.hasOwn(observed, "interested_names"), false);
});

test("the live modality server error remains an incomplete unknown form", () => {
  const observed = fixture("live-modality-error.json");
  const formSpec = contract().states.form;

  assert.equal(observed.state, "unknown");
  assert.ok(contract().routes["ComplementarAto.asp"].allowed_roles.includes(observed.state));
  assert.equal(observed.form.control_count, 15);
  assert.deepEqual(observed.form.present_sentinels, [
    "txtNumeroProcesso",
    "txtAnoProcesso",
    "txtModalidade",
  ]);
  assert.deepEqual(observed.form.missing_sentinels, [
    "txtFundamentoLegal",
    "txtDataDOE",
    "txtCargo",
    "txtMatricula",
    "txtDataNascimento",
    "txtGenero",
  ]);
  assert.deepEqual(
    observed.form.missing_sentinels,
    [...new Set([...formSpec.identity_sentinel_ids, ...formSpec.field_ids])]
      .filter((id) => !observed.form.present_sentinels.includes(id)),
  );
  assert.match(observed.modality_option.error, /800a005e/u);
  assert.equal(observed.modality_option.line, 773);
  assert.equal(observed.extension.form_detected, false);
  assert.equal(observed.extension.fill_enabled, false);
  assert.equal(observed.outcome.fields_written, 0);
  assert.equal(observed.outcome.final_action_clicked, false);
  assert.equal(Object.hasOwn(observed, "process_key"), false);
  assert.equal(Object.hasOwn(observed, "interested_name"), false);
});
