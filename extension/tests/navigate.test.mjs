import test from "node:test";
import assert from "node:assert/strict";

import { buildActFormDocument, buildInterestedDocument, buildListDocument } from "./fake-dom.mjs";

await import("../lib/area-snapshot.js");
await import("../content/detect-form.js");
await import("../content/navigate.js");

const navigate = globalThis.TCENavigate;
const IDENTITY = { processKey: "102390/2026", interestedNormalized: "pessoa exemplo" };

test("openAct clicks the exact row control on the list", () => {
  const documentRef = buildListDocument({
    rows: [
      { processKey: "102391/2026", interested: "Outra Pessoa" },
      { processKey: "102390/2026", interested: "Pessoa Exemplo" },
    ],
  });

  const result = navigate.openAct({ documentRef, identity: IDENTITY });

  assert.equal(result.ok, true);
  assert.equal(result.action, "open_act");
  assert.equal(result.screen, "list");
  assert.equal(result.waitingForFrame, true);
  const link = documentRef.querySelectorAll("tbody tr")[1].querySelectorAll("a")[0];
  assert.equal(link.clickCount, 1);
  assert.equal(documentRef.querySelectorAll("tbody tr")[0].querySelectorAll("a")[0].clickCount, 0);
});

test("openAct refuses when the exact row is missing", () => {
  const documentRef = buildListDocument({
    rows: [{ processKey: "102390/2026", interested: "Outra Pessoa" }],
  });

  const result = navigate.openAct({ documentRef, identity: IDENTITY });

  assert.equal(result.ok, false);
  assert.equal(result.code, "ROW_ACTION_NOT_FOUND");
  assert.equal(documentRef.querySelectorAll("tbody tr")[0].querySelectorAll("a")[0].clickCount, 0);
});

test("openAct selects the exact interested person", () => {
  const documentRef = buildInterestedDocument({
    processKey: "102390/2026",
    people: ["Maria da Silva", "  PESSOA   Exemplo "],
  });

  const result = navigate.openAct({ documentRef, identity: IDENTITY });

  assert.equal(result.ok, true);
  assert.equal(result.action, "select_interested");
  assert.equal(result.screen, "interested");
  assert.equal(result.waitingForFrame, true);
  const radios = documentRef.querySelectorAll('input[type="radio"]');
  assert.equal(radios[1].clickCount, 1);
  assert.equal(radios[0].clickCount, 0);
});

test("openAct refuses a person that is not on the interested screen", () => {
  const documentRef = buildInterestedDocument({ people: ["Maria da Silva"] });

  const result = navigate.openAct({ documentRef, identity: IDENTITY });

  assert.equal(result.ok, false);
  assert.equal(result.code, "INTERESTED_NOT_FOUND");
  assert.equal(documentRef.querySelectorAll('input[type="radio"]')[0].clickCount, 0);
});

test("openAct is a no-op when the requested form is already open", () => {
  const documentRef = buildActFormDocument({ selected: "Pessoa Exemplo" });

  const result = navigate.openAct({ documentRef, identity: IDENTITY });

  assert.equal(result.ok, true);
  assert.equal(result.action, "already_open");
  assert.equal(result.waitingForFrame, false);
});

test("openAct refuses a form opened for a different person", () => {
  const documentRef = buildActFormDocument({ selected: "Outra Pessoa" });

  const result = navigate.openAct({ documentRef, identity: IDENTITY });

  assert.equal(result.ok, false);
  assert.equal(result.code, "FORM_IDENTITY_MISMATCH");
});

test("openAct refuses an unknown screen instead of clicking", () => {
  const documentRef = buildListDocument({ rows: [] });
  documentRef.body.children = [];

  const result = navigate.openAct({ documentRef, identity: IDENTITY });

  assert.equal(result.ok, false);
  assert.equal(result.code, "SCREEN_NOT_NAVIGABLE");
  assert.equal(result.screen, "unknown");
});

test("openAct refuses an identity without a person", () => {
  const documentRef = buildListDocument({ rows: [{ processKey: "102390/2026", interested: "Pessoa Exemplo" }] });

  const result = navigate.openAct({ documentRef, identity: { processKey: "102390/2026" } });

  assert.equal(result.ok, false);
  assert.equal(result.code, "ROW_ACTION_NOT_FOUND");
});

test("nextPage advances while pages remain and stops on the last page", () => {
  const withNext = buildListDocument({ page: "1", rows: [], paginationLabels: [2] });
  const advanced = navigate.nextPage({ documentRef: withNext });
  assert.equal(advanced.ok, true);
  assert.equal(advanced.advanced, true);

  const last = buildListDocument({ page: "2", rows: [], hasNext: false, paginationLabels: [2] });
  const stopped = navigate.nextPage({ documentRef: last });
  assert.equal(stopped.ok, true);
  assert.equal(stopped.advanced, false);
  assert.equal(stopped.reason, "last_page");
});

test("nextPage reports no_control when the portal offers none", () => {
  const result = navigate.nextPage({
    documentRef: {},
    deps: {
      snapshot: {
        pageInfo: () => ({ page: 1, total_pages: 3 }),
        findNextPageControl: () => null,
      },
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.advanced, false);
  assert.equal(result.reason, "no_control");
});

test("the navigation uses injected dependencies when they are provided", () => {
  const clicks = [];
  const control = { click: () => clicks.push("row") };

  const result = navigate.openAct({
    documentRef: {},
    identity: IDENTITY,
    deps: {
      screenOf: () => "list",
      snapshot: { findActControl: () => control },
    },
  });

  assert.equal(result.ok, true);
  assert.deepEqual(clicks, ["row"]);
});

test("the navigation module exposes no submit surface", () => {
  for (const forbidden of ["submit", "finalize", "complementAct"]) {
    assert.equal(Object.hasOwn(navigate, forbidden), false, `unexpected ${forbidden}`);
  }
});
