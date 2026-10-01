import test from "node:test";
import assert from "node:assert/strict";

import {
  KNOWN_PORTAL_FIELDS,
  PORTAL_SELECTION_POLL_MS,
  classifyPortalProcess,
  followAction,
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

