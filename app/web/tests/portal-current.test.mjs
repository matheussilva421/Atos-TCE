import test from "node:test";
import assert from "node:assert/strict";

import {
  KNOWN_PORTAL_FIELDS,
  PORTAL_SELECTION_POLL_MS,
  classifyPortalProcess,
  currentFillAvailability,
  followAction,
  portalFieldModels,
  resumeAction,
} from "../portal-current.js";

const MANDATORY = KNOWN_PORTAL_FIELDS.filter((field) => field.mandatory).map(
  (field) => field.name
);

function portalProcess({
  found = [],
  conflicts = [],
  status = "PRONTO",
  id = 1,
} = {}) {
  return {
    id,
    status,
    fields: KNOWN_PORTAL_FIELDS.map((field) => ({
      field_name: field.name,
      value: found.includes(field.name) ? `valor ${field.name}` : "",
      status: conflicts.includes(field.name)
        ? "conflict"
        : found.includes(field.name)
          ? "found"
          : "missing",
    })),
  };
}

const FOLLOWING = {
  followPortal: true,
  selectedId: null,
  portalProcessId: null,
  activeTab: "dados",
};

test("the follow polls once a second and knows the seven portal fields", () => {
  assert.equal(PORTAL_SELECTION_POLL_MS, 1000);
  assert.equal(KNOWN_PORTAL_FIELDS.length, 7);
  assert.equal(MANDATORY.length, 6);
  for (const field of KNOWN_PORTAL_FIELDS) {
    assert.equal(typeof field.label, "string");
    assert.ok(field.label.length > 0);
  }
});

test("every mandatory field found is complete", () => {
  const result = classifyPortalProcess(portalProcess({ found: MANDATORY }));

  assert.equal(result.state, "COMPLETO");
  assert.equal(result.foundCount, 6);
  assert.equal(result.pendingCount, 0);
});

test("some mandatory fields found is partial", () => {
  const result = classifyPortalProcess(portalProcess({ found: MANDATORY.slice(0, 3) }));

  assert.equal(result.state, "PARCIAL");
  assert.equal(result.foundCount, 3);
  assert.equal(result.pendingCount, 3);
});

test("no usable field is reported as having no data, never as an error", () => {
  const result = classifyPortalProcess(portalProcess({ found: [] }));

  assert.equal(result.state, "SEM_DADOS");
  assert.equal(result.foundCount, 0);
  assert.equal(result.pendingCount, 6);
});

test("a divergence makes the classification a conflict", () => {
  const byField = classifyPortalProcess(
    portalProcess({ found: MANDATORY.slice(0, 5), conflicts: ["cargo"] })
  );
  const byStatus = classifyPortalProcess(portalProcess({ found: MANDATORY, status: "DIVERGENCIA" }));

  assert.equal(byField.state, "CONFLITO");
  assert.equal(byField.conflictCount, 1);
  assert.equal(byStatus.state, "CONFLITO");
});

test("the optional field never counts towards mandatory completion", () => {
  const result = classifyPortalProcess(portalProcess({ found: ["genero"] }));

  assert.equal(result.state, "SEM_DADOS");
  assert.equal(result.foundCount, 0);
});

test("a process without the expected shape is reported as having no data", () => {
  for (const process of [null, undefined, {}, { fields: null }]) {
    assert.equal(classifyPortalProcess(process).state, "SEM_DADOS");
  }
});

test("a matched form selects the process and opens the portal tab", () => {
  assert.deepEqual(followAction(FOLLOWING, { state: "MATCHED", process_id: 7 }), {
    portalProcessId: 7,
    selectProcessId: 7,
    openPortalTab: true,
  });
});

test("a repeated match for the already selected process never steals the sub-tab", () => {
  const decision = followAction(
    { ...FOLLOWING, selectedId: 7, portalProcessId: 7, activeTab: "documentos" },
    { state: "MATCHED", process_id: 7 }
  );

  assert.deepEqual(decision, {
    portalProcessId: 7,
    selectProcessId: null,
    openPortalTab: false,
  });
});

test("a newly observed process is followed and the portal tab is reopened", () => {
  const decision = followAction(
    { ...FOLLOWING, selectedId: 7, portalProcessId: 7, activeTab: "documentos" },
    { state: "MATCHED", process_id: 9 }
  );

  assert.deepEqual(decision, {
    portalProcessId: 9,
    selectProcessId: 9,
    openPortalTab: true,
  });
});

test("a paused follow remembers the observed process but selects nothing", () => {
  const decision = followAction(
    { ...FOLLOWING, followPortal: false, selectedId: 3, portalProcessId: null },
    { state: "MATCHED", process_id: 9 }
  );

  assert.deepEqual(decision, {
    portalProcessId: 9,
    selectProcessId: null,
    openPortalTab: false,
  });
});

test("a portal tab that is already open is not reopened", () => {
  const decision = followAction(
    { ...FOLLOWING, portalProcessId: 7, activeTab: "portal" },
    { state: "MATCHED", process_id: 9 }
  );

  assert.equal(decision.selectProcessId, 9);
  assert.equal(decision.openPortalTab, false);
});

test("a non-matched state never selects or opens anything", () => {
  for (const observation of [
    { state: "NOT_FOUND" },
    { state: "AMBIGUOUS" },
    { state: "INVALID" },
    { state: "NO_ACTIVE_FORM" },
    { state: "MATCHED" },
    {},
    null,
  ]) {
    const decision = followAction(
      { ...FOLLOWING, selectedId: 3, portalProcessId: 7 },
      observation
    );

    assert.equal(decision.selectProcessId, null, JSON.stringify(observation));
    assert.equal(decision.openPortalTab, false, JSON.stringify(observation));
    assert.equal(decision.portalProcessId, 7, "the last matched process is remembered");
  }
});


test("each known field becomes one model, and no value is ever invented", () => {
  const models = portalFieldModels(portalProcess({ found: ["cargo"], conflicts: ["matricula"] }));

  assert.equal(models.length, 7);
  const byName = new Map(models.map((model) => [model.name, model]));
  assert.equal(byName.get("cargo").verdict, "ENCONTRADO");
  assert.equal(byName.get("cargo").value, "valor cargo");
  assert.equal(byName.get("matricula").verdict, "REVISAR");
  assert.equal(byName.get("genero").verdict, "PENDENTE");
  assert.equal(byName.get("genero").value, "");
  for (const model of models) {
    if (model.verdict === "PENDENTE") assert.equal(model.value, "");
    assert.equal(typeof model.label, "string");
  }
});

test("a process without the expected shape still yields seven pending models", () => {
  for (const process of [null, undefined, {}, { fields: null }]) {
    const models = portalFieldModels(process);
    assert.equal(models.length, 7);
    assert.ok(models.every((model) => model.verdict === "PENDENTE" && model.value === ""));
  }
});

test("a value the analysis did not confirm is never labelled as found", () => {
  const stale = portalProcess({ found: [] });
  stale.fields[3].value = "valor antigo";
  stale.fields[3].status = "missing";

  const models = portalFieldModels(stale);
  const cargo = models.find((model) => model.name === "cargo");

  assert.equal(cargo.verdict, "REVISAR", "an unconfirmed value must not claim to be found");
  assert.equal(cargo.value, "valor antigo");
  // The header count already excludes it, so the card must agree.
  assert.equal(classifyPortalProcess(stale).foundCount, 0);
});

test("resuming never returns to a process the portal no longer shows", () => {
  for (const observation of [
    { state: "NO_ACTIVE_FORM" },
    { state: "NOT_FOUND" },
    { state: "AMBIGUOUS" },
    { state: "INVALID" },
    { state: "MATCHED" },
    null,
  ]) {
    assert.deepEqual(
      resumeAction(observation),
      { selectProcessId: null, openPortalTab: false },
      JSON.stringify(observation)
    );
  }
});

test("resuming returns to the form the portal is showing right now", () => {
  assert.deepEqual(resumeAction({ state: "MATCHED", process_id: 9 }), {
    selectProcessId: 9,
    openPortalTab: true,
  });
});

test("the fill button is offered only for the process the portal is showing", () => {
  assert.equal(
    currentFillAvailability(
      { state: "MATCHED", process_id: 7, observation_id: "opaque-observation-a" },
      7
    ).available,
    true
  );
  assert.equal(currentFillAvailability({ state: "MATCHED", process_id: 7 }, 7).available, false);
  assert.equal(
    currentFillAvailability(
      { state: "MATCHED", process_id: 9, observation_id: "opaque-observation-b" },
      7
    ).available,
    false
  );
  assert.equal(currentFillAvailability({ state: "MATCHED" }, 7).available, false);
  assert.equal(currentFillAvailability(null, 7).available, false);
  for (const state of ["NOT_FOUND", "AMBIGUOUS", "INVALID", "NO_ACTIVE_FORM", "FILL_RESERVED"]) {
    assert.equal(currentFillAvailability({ state }, 7).available, false, state);
  }
});

test("every unavailable state explains itself instead of failing silently", () => {
  assert.match(currentFillAvailability({ state: "NO_ACTIVE_FORM" }, 7).message, /[Nn]enhum formulário/u);
  assert.match(currentFillAvailability({ state: "NOT_FOUND" }, 7).message, /não encontrado/u);
  assert.match(currentFillAvailability({ state: "AMBIGUOUS" }, 7).message, /[Aa]mbígua/u);
  assert.match(currentFillAvailability({ state: "INVALID" }, 7).message, /inválida/u);
  assert.match(
    currentFillAvailability({ state: "FILL_RESERVED" }, 7).message,
    /já foi solicitado/u
  );
  assert.match(
    currentFillAvailability({ state: "MATCHED", process_id: 9 }, 7).message,
    /outro processo/u
  );
});
