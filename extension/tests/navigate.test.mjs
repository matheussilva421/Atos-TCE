import test from "node:test";
import assert from "node:assert/strict";

import {
  FakeDocument,
  FakeElement,
  buildFrameElement,
  buildActFormDocument,
  buildInterestedDocument,
  buildListDocument,
} from "./fake-dom.mjs";

await import("../lib/area-snapshot.js");
await import("../content/detect-form.js");
await import("../content/navigate.js");

const navigate = globalThis.TCENavigate;
const IDENTITY = { processKey: "102390/2026", interestedNormalized: "pessoa exemplo" };

function attachNativeListTab(documentRef, label = "Proc./ Doc. Eletrônicos") {
  const parentDocument = new FakeDocument({ screen: "work" });
  const tab = new FakeElement("a", { text: label, attrs: { class: "tabs-inner" } });
  const frameElement = buildFrameElement();
  parentDocument.body.append(frameElement, tab);
  const parentWindow = parentDocument.defaultView;
  parentWindow.document = parentDocument;
  documentRef.defaultView.frameElement = frameElement;
  documentRef.defaultView.parent = parentWindow;
  return { parentDocument, tab };
}

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

test("native return control returns to the list after confirming the exact form identity", () => {
  const documentRef = buildActFormDocument({ processKey: IDENTITY.processKey, selected: "Pessoa Exemplo" });
  const { tab } = attachNativeListTab(documentRef);

  const result = navigate.returnToList({ documentRef, identity: IDENTITY });

  assert.deepEqual(result, {
    ok: true,
    action: "return_to_list",
    screen: "form",
    waitingForList: true,
  });
  assert.equal(tab.clickCount, 1);
});

test("native return refuses a different current identity without clicking", () => {
  const documentRef = buildActFormDocument({ processKey: IDENTITY.processKey, selected: "Pessoa Exemplo" });
  const { tab } = attachNativeListTab(documentRef);

  const result = navigate.returnToList({
    documentRef,
    identity: { processKey: "999/2026", interestedNormalized: "pessoa exemplo" },
  });

  assert.equal(result.ok, false);
  assert.equal(result.code, "CURRENT_IDENTITY_MISMATCH");
  assert.equal(tab.clickCount, 0);
});

test("native return fails closed when the observed list tab is missing or ambiguous", () => {
  const missing = buildActFormDocument({ processKey: IDENTITY.processKey, selected: "Pessoa Exemplo" });
  attachNativeListTab(missing, "Outro conteúdo");
  const missingResult = navigate.returnToList({ documentRef: missing, identity: IDENTITY });
  assert.equal(missingResult.code, "RETURN_CONTROL_NOT_FOUND");

  const ambiguous = buildActFormDocument({ processKey: IDENTITY.processKey, selected: "Pessoa Exemplo" });
  const { parentDocument } = attachNativeListTab(ambiguous);
  parentDocument.body.append(
    new FakeElement("a", {
      text: "Proc./ Doc. Eletrônicos",
      attrs: { class: "tabs-inner" },
    }),
  );
  const ambiguousResult = navigate.returnToList({ documentRef: ambiguous, identity: IDENTITY });
  assert.equal(ambiguousResult.code, "RETURN_CONTROL_AMBIGUOUS");
  assert.equal(parentDocument.querySelectorAll("a").every((control) => control.clickCount === 0), true);
});

test("native return ignores an incidental anchor with the same label", () => {
  const documentRef = buildActFormDocument({ processKey: IDENTITY.processKey, selected: "Pessoa Exemplo" });
  const { parentDocument, tab } = attachNativeListTab(documentRef);
  const incidental = new FakeElement("a", { text: "Proc./ Doc. Eletrônicos", attrs: { class: "other-tab" } });
  parentDocument.body.append(incidental);

  const result = navigate.returnToList({ documentRef, identity: IDENTITY });

  assert.equal(result.ok, true);
  assert.equal(tab.clickCount, 1);
  assert.equal(incidental.clickCount, 0);
});

test("native return requires a visible act form and does not add marker mutation", () => {
  const documentRef = buildListDocument({ rows: [] });
  const { tab } = attachNativeListTab(documentRef);

  const result = navigate.returnToList({ documentRef, identity: IDENTITY });

  assert.equal(result.ok, false);
  assert.equal(result.code, "CURRENT_FORM_NOT_AVAILABLE");
  assert.equal(tab.clickCount, 0);
  assert.equal(navigate.ensureMarker, undefined);
});

test("RETURN_TO_LIST runtime message uses the exact current identity", async () => {
  const documentRef = buildActFormDocument({ processKey: IDENTITY.processKey, selected: "Pessoa Exemplo" });
  const { tab } = attachNativeListTab(documentRef);
  const listeners = [];
  const previousChrome = globalThis.chrome;
  const previousDocument = globalThis.document;
  globalThis.chrome = {
    runtime: {
      onMessage: {
        addListener(listener) {
          listeners.push(listener);
        },
      },
    },
  };
  globalThis.document = documentRef;
  try {
    await import(`../content/navigate.js?return-message-test=${Date.now()}`);
    let response;
    const handled = listeners[0](
      { type: "RETURN_TO_LIST", payload: { identity: IDENTITY } },
      {},
      (value) => {
        response = value;
      },
    );

    assert.equal(handled, true);
    assert.deepEqual(response, {
      ok: true,
      action: "return_to_list",
      screen: "form",
      waitingForList: true,
    });
    assert.equal(tab.clickCount, 1);
  } finally {
    if (previousChrome === undefined) delete globalThis.chrome;
    else globalThis.chrome = previousChrome;
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
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
