import test from "node:test";
import assert from "node:assert/strict";

import {
  executeCommand,
  installRouter,
  scanAreaPages,
  PORTAL_SELECTION_KEEPALIVE_MS,
} from "../background/router.js";
import { COMMAND_TYPES, MESSAGE_TYPES, PORTAL_ORIGIN } from "../lib/protocol.js";
import { fakeChrome } from "./helpers.mjs";

const PORTAL = "https://novaarearestrita.tce.rn.gov.br";

//: The exact shape ``readCurrentForm`` resolves for one open act form.
const OBSERVED_FORM = {
  identity: { processKey: "102390/2026", interestedNormalized: "pessoa exemplo" },
  generation: 4,
};

function page(rows, { page: number = 1, total_pages = 1 } = {}) {
  return { role: "list", source_scope: "sector_finalistic", marker: null, page: number, total_pages, rows };
}

function sendRuntime(chromeApi, message) {
  return new Promise((resolve) => {
    for (const listener of chromeApi.listeners) {
      const result = listener(message, {}, resolve);
      if (result === undefined) resolve({ ok: false, error: "message_not_handled" });
    }
  });
}

test("a SCAN_AREA command returns the sanitized snapshot", async () => {
  const command = { id: 7, type: "SCAN_AREA", payload: {} };

  const result = await executeCommand(command, {
    scanPortal: async () => ({
      source_scope: "sector_finalistic",
      marker: { label: "M", value: "6189" },
      rows: [{ process_key: "102390/2026", classification: "PRECISA_COMPLEMENTAR" }],
    }),
  });

  assert.equal(result.command_id, 7);
  assert.equal(result.rows.length, 1);
  assert.equal(result.ok, true);
  assert.equal(result.source_scope, "sector_finalistic");
});

test("a SCAN_AREA command exposes a lease renewal tied to its current claim", async () => {
  let renewalArgs;
  const result = await executeCommand(
    { id: 8, type: "SCAN_AREA", claim_token: "claim-token", payload: {} },
    {
      scanPortal: async (_payload, { renewLease }) => {
        await renewLease();
        return { source_scope: "sector_finalistic", marker: null, rows: [] };
      },
      renewLease: async (...args) => {
        renewalArgs = args;
        return { ok: true };
      },
    }
  );

  assert.equal(result.ok, true);
  assert.deepEqual(renewalArgs, [8, "claim-token"]);
});

test("a STATUS command reports readiness without touching the portal", async () => {
  let scanned = false;

  const result = await executeCommand(
    { id: 3, type: "STATUS", payload: {} },
    { scanPortal: async () => (scanned = true) }
  );

  assert.equal(result.command_id, 3);
  assert.equal(result.ok, true);
  assert.equal(scanned, false);
});

test("an unknown command type is refused, never guessed", async () => {
  const result = await executeCommand({ id: 5, type: "SUBMIT", payload: {} }, {});

  assert.equal(result.command_id, 5);
  assert.equal(result.ok, false);
  assert.match(result.error, /unsupported command/u);
});

const IDENTITY = { processKey: "102390/2026", interestedNormalized: "pessoa exemplo" };
const NEXT_IDENTITY = { processKey: "100/2026", interestedNormalized: "pessoa destino" };
const NEXT_PAYLOAD = {
  current_identity: IDENTITY,
  target_identity: NEXT_IDENTITY,
  context: {
    scan_id: 17,
    source_scope: "sector_finalistic",
    marker: { label: "Professor - fixture", value: "6189" },
  },
};

function nextActHarness({
  currentForm = null,
  pages = [{
    ok: true,
    frame: { tabId: 1, frameId: 5 },
    snapshot: page([{ process_key: NEXT_IDENTITY.processKey, interested_normalized: NEXT_IDENTITY.interestedNormalized }]),
  }],
  returnedListMarker = null,
  openResults = [{ ok: true, action: "open_act", waitingForFrame: true }],
  targetForms = [{ ok: true, form: { identity: NEXT_IDENTITY }, tabId: 9, frameId: 3 }],
} = {}) {
  const calls = [];
  let pageIndex = 0;
  let openIndex = 0;
  let formIndex = 0;
  const dependencies = {
    async readCurrentForm() {
      calls.push("readCurrentForm");
      return currentForm;
    },
    async returnToList(form, identity) {
      calls.push(["returnToList", form, identity]);
      return { ok: true, marker: returnedListMarker };
    },
    async readListPage() {
      calls.push("readListPage");
      const current = pages[Math.min(pageIndex, pages.length - 1)];
      return {
        ...current,
        snapshot: {
          ...current.snapshot,
          marker: returnedListMarker ?? current.snapshot.marker ?? NEXT_PAYLOAD.context.marker,
        },
      };
    },
    async advancePage(frame, currentPage) {
      calls.push(["advancePage", frame, currentPage]);
      pageIndex += 1;
      return { ok: true, page_after: currentPage + 1 };
    },
    async openAct(identity) {
      calls.push(["openAct", identity]);
      return openResults[Math.min(openIndex++, openResults.length - 1)];
    },
    async readTargetForm(identity) {
      calls.push(["readTargetForm", identity]);
      return targetForms[Math.min(formIndex++, targetForms.length - 1)] ?? null;
    },
    async activateTab(tabId) {
      calls.push(["activateTab", tabId]);
      return { ok: true };
    },
  };
  const router = installRouter({
    api: idleApi(),
    chromeApi: fakeChrome(),
    timing: { ...FAST, nextActAttempts: 4, nextActDelayMs: 1 },
    nextActDependencies: dependencies,
  });
  return { router, calls };
}

async function runNextAct(harness) {
  assert.equal(typeof harness.router.openNextAct, "function", "router must expose next-act orchestration");
  return harness.router.openNextAct(NEXT_PAYLOAD);
}

test("OPEN_NEXT_ACT dispatches through its dedicated navigation collaborator", async () => {
  let received;
  const result = await executeCommand(
    { id: 81, type: "OPEN_NEXT_ACT", payload: NEXT_PAYLOAD },
    { openNextAct: async (payload) => { received = payload; return { ok: true, action: "next_act_ready", identity: NEXT_IDENTITY, screen: "form" }; } }
  );

  assert.deepEqual(received, NEXT_PAYLOAD);
  assert.deepEqual(result, {
    command_id: 81,
    ok: true,
    action: "next_act_ready",
    identity: NEXT_IDENTITY,
    screen: "form",
  });
});

test("poll reports the reread target after OPEN_NEXT_ACT navigation", async () => {
  const reported = [];
  const calls = [];
  const router = installRouter({
    api: {
      nextCommand: async () => ({
        ok: true,
        command: {
          id: 82,
          type: "OPEN_NEXT_ACT",
          claim_token: "lease-next-act",
          payload: NEXT_PAYLOAD,
        },
      }),
      reportResult: async (commandId, result) => reported.push({ commandId, result }),
    },
    chromeApi: fakeChrome(),
    timing: FAST,
    nextActDependencies: {
      readCurrentForm: async () => ({ ok: true, form: null }),
      returnToList: async () => ({ ok: true }),
      readListPage: async () => ({
        ok: true,
        frame: { tabId: 1, frameId: 3 },
        snapshot: {
          ...page([]),
          marker: NEXT_PAYLOAD.context.marker,
        },
      }),
      openAct: async (identity) => {
        calls.push(["openAct", identity]);
        return { ok: true, action: "open_act" };
      },
      readTargetForm: async (identity) => {
        calls.push(["readTargetForm", identity]);
        return {
          ok: true,
          form: { identity },
          tabId: 9,
          frameId: 4,
        };
      },
      activateTab: async (tabId) => {
        calls.push(["activateTab", tabId]);
        return { ok: true };
      },
    },
  });

  await router.poll();

  assert.equal(reported.length, 1);
  assert.equal(reported[0].commandId, 82);
  const { diagnostic_events: diagnosticEvents, ...functionalResult } = reported[0].result;
  assert.deepEqual(functionalResult, {
    command_id: 82,
    ok: true,
    action: "next_act_ready",
    identity: NEXT_IDENTITY,
    screen: "form",
    claim_token: "lease-next-act",
  });
  assert.ok(Array.isArray(diagnosticEvents));
  assert.deepEqual(calls.map(([action]) => action), ["openAct", "readTargetForm", "activateTab"]);
});

test("next-act refuses a scan id that is not an actual positive integer", async () => {
  for (const scanId of ["17", true, 0, -1, 1.5]) {
    const harness = nextActHarness();
    const result = await harness.router.openNextAct({
      ...NEXT_PAYLOAD,
      context: { ...NEXT_PAYLOAD.context, scan_id: scanId },
    });

    assert.equal(result.ok, false, `scan_id=${String(scanId)} must be rejected`);
    assert.equal(result.code, "SCAN_CONTEXT_MISSING");
    assert.deepEqual(harness.calls, []);
  }
});

test("next-act returns the exact current form to list and reads the target form", async () => {
  const harness = nextActHarness({
    currentForm: { form: { identity: IDENTITY }, tabId: 1, frameId: 2 },
    openResults: [
      { ok: true, action: "open_act", waitingForFrame: true },
      { ok: true, action: "select_interested", waitingForFrame: true },
    ],
    targetForms: [null, { ok: true, form: { identity: NEXT_IDENTITY }, tabId: 9, frameId: 3 }],
  });

  const result = await runNextAct(harness);

  assert.deepEqual(result, { ok: true, action: "next_act_ready", identity: NEXT_IDENTITY, screen: "form" });
  assert.deepEqual(harness.calls.map((call) => Array.isArray(call) ? call[0] : call), [
    "readCurrentForm", "returnToList", "readListPage", "openAct", "readTargetForm", "openAct", "readTargetForm", "activateTab",
  ]);
});

test("next-act opens an exact target already on the current list page", async () => {
  const harness = nextActHarness({ currentForm: null });

  const result = await runNextAct(harness);

  assert.equal(result.ok, true);
  assert.equal(harness.calls.some((call) => Array.isArray(call) && call[0] === "returnToList"), false);
});

test("next-act advances the list and opens a target on a later page", async () => {
  const harness = nextActHarness({
    currentForm: null,
    pages: [
      { ok: true, frame: { tabId: 1, frameId: 5 }, snapshot: page([{ process_key: "200/2026", interested_normalized: "pessoa outra" }], { page: 1, total_pages: 2 }) },
      { ok: true, frame: { tabId: 1, frameId: 5 }, snapshot: page([{ process_key: NEXT_IDENTITY.processKey, interested_normalized: NEXT_IDENTITY.interestedNormalized }], { page: 2, total_pages: 2 }) },
    ],
    openResults: [
      { ok: false, code: "ROW_ACTION_NOT_FOUND" },
      { ok: true, action: "open_act", waitingForFrame: true },
    ],
  });

  const result = await runNextAct(harness);

  assert.equal(result.ok, true);
  assert.equal(harness.calls.filter((call) => Array.isArray(call) && call[0] === "advancePage").length, 1);
  assert.equal(harness.calls.filter((call) => Array.isArray(call) && call[0] === "openAct").length, 2);
});

test("next-act refuses pagination drift before trying a row on the new page", async () => {
  const scenarios = [
    {
      label: "page jump",
      second: page(
        [{ process_key: NEXT_IDENTITY.processKey, interested_normalized: NEXT_IDENTITY.interestedNormalized }],
        { page: 3, total_pages: 3 },
      ),
    },
    {
      label: "page count changed",
      second: page(
        [{ process_key: NEXT_IDENTITY.processKey, interested_normalized: NEXT_IDENTITY.interestedNormalized }],
        { page: 2, total_pages: 3 },
      ),
    },
  ];

  for (const scenario of scenarios) {
    const harness = nextActHarness({
      currentForm: null,
      pages: [
        {
          ok: true,
          frame: { tabId: 1, frameId: 5 },
          snapshot: page([{ process_key: "200/2026", interested_normalized: "pessoa outra" }], {
            page: 1,
            total_pages: 2,
          }),
        },
        { ok: true, frame: { tabId: 1, frameId: 5 }, snapshot: scenario.second },
      ],
      openResults: [
        { ok: false, code: "ROW_ACTION_NOT_FOUND" },
        { ok: true, action: "open_act", waitingForFrame: true },
      ],
    });

    const result = await runNextAct(harness);

    assert.equal(result.ok, false, scenario.label);
    assert.equal(result.code, "PAGINATION_INCOHERENT", scenario.label);
    assert.equal(
      harness.calls.filter((call) => Array.isArray(call) && call[0] === "openAct").length,
      1,
      scenario.label,
    );
  }
});

test("next-act refuses a wrong marker without attempting marker restoration", async () => {
  const harness = nextActHarness({
    currentForm: { form: { identity: IDENTITY }, tabId: 1, frameId: 2 },
    returnedListMarker: { label: "different", value: "other" },
  });

  const result = await runNextAct(harness);

  assert.equal(result.ok, false);
  assert.equal(result.code, "MARKER_MISMATCH");
  assert.equal(Object.values(MESSAGE_TYPES).includes("ENSURE_MARKER"), false);
  assert.equal(harness.calls.some((call) => Array.isArray(call) && call[0] === "openAct"), false);
});

test("next-act reports TARGET_NOT_FOUND without selecting a neighboring row", async () => {
  const harness = nextActHarness({
    currentForm: null,
    pages: [{ ok: true, frame: { tabId: 1, frameId: 5 }, snapshot: page([{ process_key: "200/2026", interested_normalized: "pessoa outra" }]) }],
    openResults: [{ ok: false, code: "ROW_ACTION_NOT_FOUND" }],
  });

  const result = await runNextAct(harness);

  assert.equal(result.ok, false);
  assert.equal(result.code, "TARGET_NOT_FOUND");
  const openCalls = harness.calls.filter((call) => Array.isArray(call) && call[0] === "openAct");
  assert.equal(openCalls.length, 1);
  assert.deepEqual(openCalls[0][1], NEXT_IDENTITY);
});

test("next-act rejects a final form with a different identity", async () => {
  const harness = nextActHarness({
    currentForm: null,
    targetForms: [{ ok: true, form: { identity: { processKey: "999/2026", interestedNormalized: "outra pessoa" } }, tabId: 9, frameId: 3 }],
  });

  const result = await runNextAct(harness);

  assert.equal(result.ok, false);
  assert.equal(result.code, "TARGET_IDENTITY_MISMATCH");
});

test("next-act refuses multiple matching target form frames", async () => {
  const harness = nextActHarness({
    currentForm: null,
    targetForms: [{ ok: false, code: "FORM_AMBIGUOUS" }],
  });

  const result = await runNextAct(harness);

  assert.equal(result.ok, false);
  assert.equal(result.code, "FORM_AMBIGUOUS");
});

test("next-act activates the tab containing the reread exact target form", async () => {
  const harness = nextActHarness({
    currentForm: null,
    targetForms: [{ ok: true, form: { identity: NEXT_IDENTITY }, tabId: 42, frameId: 8 }],
  });

  const result = await runNextAct(harness);

  assert.equal(result.ok, true);
  assert.deepEqual(harness.calls.at(-1), ["activateTab", 42]);
});

test("OPEN_NEXT_ACT confirms a target in a second portal tab after focus moves to the Mesa", async () => {
  const tabs = [
    { id: 1, active: false, url: "http://127.0.0.1:18743/" },
    portalTab(2, { active: true }),
    { id: 3, active: false, url: `${PORTAL}/complementarAto.asp` },
  ];
  let currentReturnedToList = false;
  let targetOpened = false;
  let focusChangedToMesa = false;
  const activatedTabs = [];
  const chromeApi = fakeChrome({
    tabs,
    frames: {
      2: [{ frameId: 4, url: `${PORTAL}/ProcessonoSetor.asp` }],
      3: [{ frameId: 7, url: `${PORTAL}/complementarAto.asp` }],
    },
    onMessage: (message, tabId) => {
      if (message.type === MESSAGE_TYPES.READ_FORM) {
        if (!currentReturnedToList && !message.payload?.identity && tabId === 2) {
          return { ok: true, form: { identity: IDENTITY, generation: 4 } };
        }
        if (targetOpened && message.payload?.identity && tabId === 3) {
          return { ok: true, form: { identity: NEXT_IDENTITY, generation: 5 } };
        }
        return { ok: false, code: "FORM_NOT_AVAILABLE" };
      }
      if (message.type === MESSAGE_TYPES.RETURN_TO_LIST) {
        currentReturnedToList = true;
        tabs.forEach((tab) => { tab.active = false; });
        tabs[0].active = true;
        focusChangedToMesa = true;
        return { ok: true };
      }
      if (message.type === MESSAGE_TYPES.SCAN_PAGE) {
        return tabId === 2
          ? {
              ok: true,
              snapshot: {
                ...page([{ process_key: NEXT_IDENTITY.processKey, interested_normalized: NEXT_IDENTITY.interestedNormalized }]),
                marker: NEXT_PAYLOAD.context.marker,
              },
            }
          : { ok: true, snapshot: { role: "unknown" } };
      }
      if (message.type === MESSAGE_TYPES.OPEN_ACT && tabId === 2) {
        targetOpened = true;
        return { ok: true, action: "open_act", screen: "list", waitingForFrame: true };
      }
      return { ok: false };
    },
  });
  chromeApi.tabs.update = async (tabId, patch) => {
    tabs.forEach((tab) => { tab.active = false; });
    const updated = tabs.find((tab) => tab.id === tabId);
    Object.assign(updated, patch);
    activatedTabs.push(tabId);
    return updated;
  };
  const router = installRouter({
    api: idleApi(),
    chromeApi,
    timing: { ...FAST, nextActAttempts: 1, nextActDelayMs: 1 },
  });

  const result = await router.openNextAct(NEXT_PAYLOAD);

  assert.deepEqual(result, {
    ok: true,
    action: "next_act_ready",
    identity: NEXT_IDENTITY,
    screen: "form",
  });
  assert.equal(focusChangedToMesa, true);
  assert.deepEqual(activatedTabs, [3]);
  assert.equal(tabs[0].active, false);
  assert.equal(tabs[2].active, true);
  assert.ok(chromeApi.sent.some((entry) =>
    entry.tabId === 3 &&
    entry.message.type === MESSAGE_TYPES.READ_FORM &&
    entry.message.payload?.identity?.processKey === NEXT_IDENTITY.processKey
  ));
  assert.equal(chromeApi.sent.some((entry) => entry.tabId === 1), false);
});

test("an OPEN_ACT command reports the navigation outcome", async () => {
  const result = await executeCommand(
    { id: 21, type: "OPEN_ACT", payload: { identity: IDENTITY } },
    { openAct: async () => ({ ok: true, action: "open_act", screen: "list", waitingForFrame: true }) }
  );

  assert.equal(result.command_id, 21);
  assert.equal(result.ok, true);
  assert.equal(result.action, "open_act");
  assert.equal(result.waitingForFrame, true);
});

test("a navigation refusal keeps its code", async () => {
  const result = await executeCommand(
    { id: 22, type: "OPEN_ACT", payload: {} },
    { openAct: async () => ({ ok: false, code: "ROW_ACTION_NOT_FOUND" }) }
  );

  assert.equal(result.ok, false);
  assert.equal(result.code, "ROW_ACTION_NOT_FOUND");
});

test("a READ_FORM command returns the sanitized form", async () => {
  const result = await executeCommand(
    { id: 23, type: "READ_FORM", payload: {} },
    { readForm: async () => ({ ok: true, form: { identity: IDENTITY, generation: 3, fields: {}, options: {} } }) }
  );

  assert.equal(result.command_id, 23);
  assert.equal(result.ok, true);
  assert.equal(result.generation, 3);
  assert.equal(result.identity.processKey, "102390/2026");
});

test("a refused READ_FORM keeps the code the router reported", async () => {
  const result = await executeCommand(
    { id: 27, type: "READ_FORM", payload: {} },
    { readForm: async () => ({ ok: false, code: "FORM_AMBIGUOUS", error: "mais de uma moldura" }) }
  );

  assert.equal(result.ok, false);
  assert.equal(result.code, "FORM_AMBIGUOUS");
  assert.match(result.error, /moldura/u);
});

test("a form that never appears fails instead of inventing a snapshot", async () => {
  const result = await executeCommand(
    { id: 24, type: "READ_FORM", payload: {} },
    { readForm: async () => null }
  );

  assert.equal(result.ok, false);
  assert.match(result.error, /formulário/u);
});

test("a FILL_FORM command returns changed and unresolved field results", async () => {
  const result = await executeCommand(
    {
      id: 25,
      type: "FILL_FORM",
      payload: { identity: IDENTITY, generation: 4, fields: { cargo: "Professor", matricula: "78.710-8/2" } },
    },
    {
      fillForm: async () => ({
        ok: true,
        identity: IDENTITY,
        generation_after: 5,
        field_results: {
          cargo: { before: "", proposed: "Professor", after: "Professor", status: "changed" },
          matricula: { before: "", proposed: "78.710-8/2", after: "", status: "disabled" },
        },
      }),
    }
  );

  assert.equal(result.command_id, 25);
  assert.equal(result.ok, true);
  assert.equal(result.generation_after, 5);
  assert.equal(result.field_results.cargo.status, "changed");
  assert.equal(result.field_results.matricula.status, "disabled");
});

test("a FILL_FORM command preserves a successful partial field report", async () => {
  const partialResults = {
    cargo: { before: "", proposed: "Professor", after: "Professor", status: "changed" },
    matricula: {
      before: "",
      proposed: "78.710-8/2",
      after: "",
      status: "disabled",
      warning: "control_disabled",
    },
  };
  const result = await executeCommand(
    {
      id: 27,
      type: "FILL_FORM",
      payload: { identity: IDENTITY, generation: 4, fields: { cargo: "Professor", matricula: "78.710-8/2" } },
    },
    {
      fillForm: async () => ({
        ok: true,
        identity: IDENTITY,
        generation_after: 5,
        field_results: partialResults,
      }),
    }
  );

  assert.equal(result.command_id, 27);
  assert.equal(result.ok, true);
  assert.deepEqual(result.field_results, partialResults);
});

test("a refused fill keeps its code", async () => {
  const result = await executeCommand(
    { id: 26, type: "FILL_FORM", payload: {} },
    { fillForm: async () => ({ ok: false, code: "STALE_GENERATION" }) }
  );

  assert.equal(result.ok, false);
  assert.equal(result.code, "STALE_GENERATION");
});

test("a command without a type is refused", async () => {
  const result = await executeCommand({ id: 6 }, {});

  assert.equal(result.ok, false);
});

test("scanAreaPages walks every page and de-duplicates rows", async () => {
  const pages = [
    page(
      [
        { process_key: "102390/2026", interested_normalized: "pessoa exemplo" },
        { process_key: "102391/2026", interested_normalized: "outra pessoa" },
      ],
      { page: 1, total_pages: 2 }
    ),
    page(
      [
        { process_key: "102391/2026", interested_normalized: "outra pessoa" },
        { process_key: "102392/2026", interested_normalized: "terceira pessoa" },
      ],
      { page: 2, total_pages: 2 }
    ),
  ];
  let index = 0;

  const snapshot = await scanAreaPages({
    scanPage: async () => pages[Math.min(index, pages.length - 1)],
    advancePage: async () => {
      index += 1;
      return true;
    },
  });

  assert.equal(snapshot.rows.length, 3);
  assert.deepEqual(
    snapshot.rows.map((row) => row.process_key),
    ["102390/2026", "102391/2026", "102392/2026"]
  );
  assert.equal(snapshot.source_scope, "sector_finalistic");
});

test("scanAreaPages renews its claim once per sanitized page checkpoint", async () => {
  const pages = [
    page([{ process_key: "102390/2026", interested_normalized: "pessoa exemplo" }], {
      page: 1,
      total_pages: 2,
    }),
    page([{ process_key: "102391/2026", interested_normalized: "outra pessoa" }], {
      page: 2,
      total_pages: 2,
    }),
  ];
  const checkpoints = [];
  let index = 0;

  await scanAreaPages({
    scanPage: async () => pages[Math.min(index, pages.length - 1)],
    advancePage: async () => {
      index += 1;
      return true;
    },
    onPage: async ({ page: pageNumber, total_pages: totalPages }) => {
      checkpoints.push({ page: pageNumber, total_pages: totalPages });
    },
  });

  assert.deepEqual(checkpoints, [
    { page: 1, total_pages: 2 },
    { page: 2, total_pages: 2 },
  ]);
});

test("scanAreaPages aborts when the portal keeps reporting the same page", async () => {
  let advances = 0;

  await assert.rejects(
    () =>
      scanAreaPages({
        scanPage: async () =>
          page([{ process_key: "102390/2026", interested_normalized: "p" }], { page: 1, total_pages: 9 }),
        advancePage: async () => {
          advances += 1;
          return true;
        },
      }),
    /paginação incoerente/u
  );

  assert.equal(advances, 1, "a mixed snapshot must never be persisted");
});

test("scanAreaPages refuses a scan that the page cap cut short", async () => {
  let pageNumber = 0;
  let advances = 0;

  await assert.rejects(
    () =>
      scanAreaPages({
        maxPages: 3,
        scanPage: async () => {
          pageNumber += 1;
          return page(
            [{ process_key: `10${pageNumber}/2026`, interested_normalized: `p${pageNumber}` }],
            { page: pageNumber, total_pages: 99 }
          );
        },
        advancePage: async () => {
          advances += 1;
          return true;
        },
      }),
    /PAGE_LIMIT_EXCEEDED/u
  );

  assert.equal(advances, 2);
});

test("scanAreaPages refuses a snapshot the portal stopped advancing", async () => {
  await assert.rejects(
    () =>
      scanAreaPages({
        scanPage: async () =>
          page([{ process_key: "102390/2026", interested_normalized: "p" }], {
            page: 1,
            total_pages: 4,
          }),
        advancePage: async () => false,
      }),
    /PAGINATION_STALLED/u
  );
});

test("scanAreaPages refuses a pagination jump", async () => {
  const pages = [
    page([{ process_key: "102390/2026", interested_normalized: "p" }], { page: 1, total_pages: 4 }),
    page([{ process_key: "102391/2026", interested_normalized: "p" }], { page: 3, total_pages: 4 }),
  ];
  let index = 0;

  await assert.rejects(
    () =>
      scanAreaPages({
        scanPage: async () => pages[Math.min(index, pages.length - 1)],
        advancePage: async () => {
          index += 1;
          return true;
        },
      }),
    /paginação incoerente/u
  );
});

test("scanAreaPages returns every page of a normal scan", async () => {
  const pages = [1, 2, 3].map((number) =>
    page([{ process_key: `10239${number}/2026`, interested_normalized: "p" }], {
      page: number,
      total_pages: 3,
    })
  );
  let index = 0;

  const snapshot = await scanAreaPages({
    scanPage: async () => pages[Math.min(index, pages.length - 1)],
    advancePage: async () => {
      index += 1;
      return true;
    },
  });

  assert.deepEqual(
    snapshot.rows.map((row) => row.process_key),
    ["102391/2026", "102392/2026", "102393/2026"]
  );
});

test("scanPortal refuses to run without an authenticated portal tab", async () => {
  const chromeApi = fakeChrome({ tabs: [] });
  const router = installRouter({ api: { nextCommand: async () => ({ ok: true, command: null }) }, chromeApi });

  await assert.rejects(() => router.scanPortal({}), /Área Restrita/u);
});

test("poll reports an unsupported command as a failed result", async () => {
  const chromeApi = fakeChrome();
  const reported = [];
  const router = installRouter({
    api: {
      nextCommand: async () => ({ ok: true, command: { id: 11, type: "SUBMIT", payload: {} } }),
      reportResult: async (commandId, result) => reported.push({ commandId, result }),
    },
    chromeApi,
  });

  const outcome = await router.poll();

  assert.equal(reported.length, 1);
  assert.equal(reported[0].result.ok, false);
  assert.equal(outcome.ok, true);
});

test("a scan that cannot be completed is reported as a failure", async () => {
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    onMessage: (message) =>
      message.type === "SCAN_PAGE"
        ? { ok: true, snapshot: page([], { page: 1, total_pages: 4 }) }
        : { ok: false },
  });
  const reported = [];
  const router = installRouter({
    api: {
      nextCommand: async () => ({ ok: true, command: { id: 31, type: "SCAN_AREA", payload: {} } }),
      reportResult: async (commandId, result) => reported.push({ commandId, result }),
    },
    chromeApi,
    timing: FAST,
  });

  await router.poll();

  assert.equal(reported.length, 1);
  assert.equal(reported[0].result.ok, false);
  assert.match(reported[0].result.error, /PAGINATION_STALLED/u);
});

test("poll does nothing when the Mesa has no command", async () => {
  const chromeApi = fakeChrome();
  const reported = [];
  const router = installRouter({
    api: {
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async (commandId, result) => reported.push({ commandId, result }),
    },
    chromeApi,
  });

  const outcome = await router.poll();

  assert.equal(outcome.command, null);
  assert.equal(reported.length, 0);
});

test("poll reports command received and execution timings without changing the result", async () => {
  const reported = [];
  const ticks = [100, 105, 110, 130];
  let tick = 0;
  const router = installRouter({
    api: {
      nextCommand: async () => ({
        ok: true,
        command: { id: 41, type: "STATUS", claim_token: "claim-41", payload: {} },
      }),
      reportResult: async (commandId, result) => reported.push({ commandId, result }),
    },
    chromeApi: fakeChrome(),
    monotonicNow: () => ticks[tick++],
  });

  const outcome = await router.poll();

  assert.deepEqual(outcome.result, { command_id: 41, ok: true, status: "ready" });
  assert.equal(reported[0].commandId, 41);
  assert.deepEqual(
    reported[0].result.diagnostic_events.map(({ step, elapsed_ms, result }) => ({ step, elapsed_ms, result })),
    [
      { step: "command_received", elapsed_ms: 5, result: "ok" },
      { step: "command_execution", elapsed_ms: 20, result: "ok" },
    ],
  );
  assert.equal(reported[0].result.claim_token, "claim-41");
  assert.deepEqual(
    Object.keys(reported[0].result).filter((key) => key !== "diagnostic_events").sort(),
    ["claim_token", "command_id", "ok", "status"],
  );
});

test("the router answers the content-script heartbeat", async () => {
  const chromeApi = fakeChrome();
  const polls = [];
  installRouter({
    api: {
      nextCommand: async () => {
        polls.push(1);
        return { ok: true, command: null };
      },
      reportResult: async () => {},
    },
    chromeApi,
  });

  const response = await new Promise((resolve) => {
    for (const listener of chromeApi.listeners) {
      listener({ type: "POLL_COMMANDS" }, {}, resolve);
    }
  });

  assert.equal(response.ok, true);
  assert.equal(polls.length, 1);
});

test("the sidepanel can read the form the operator opened by hand", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) =>
      message.type === "READ_FORM"
        ? { ok: true, form: { identity: { processKey: "102390/2026" }, generation: 4 } }
        : { ok: false, error: "unexpected" },
  });
  const router = installRouter({
    api: { nextCommand: async () => ({ ok: true, command: null }), reportResult: async () => {} },
    chromeApi,
  });

  const response = await router.readCurrentForm();

  assert.equal(response.ok, true);
  assert.equal(response.form.identity.processKey, "102390/2026");
  assert.equal(response.form.generation, 4);
});

test("the sidepanel is told when no form is open", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/ProcessonoSetor.asp` }],
    onMessage: () => ({ ok: false, error: "o formulário do ato ainda não está disponível" }),
  });
  const router = installRouter({
    api: { nextCommand: async () => ({ ok: true, command: null }), reportResult: async () => {} },
    chromeApi,
  });

  const response = await router.readCurrentForm();

  assert.equal(response.ok, false);
  assert.match(response.error, /nenhum formulário/u);
});

test("the router answers the sidepanel READ_CURRENT_FORM message", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 3, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) =>
      message.type === "READ_FORM"
        ? { ok: true, form: { identity: { processKey: "102391/2026" } } }
        : { ok: false },
  });
  installRouter({
    api: { nextCommand: async () => ({ ok: true, command: null }), reportResult: async () => {} },
    chromeApi,
  });

  const response = await new Promise((resolve) => {
    for (const listener of chromeApi.listeners) {
      listener({ type: "READ_CURRENT_FORM" }, {}, resolve);
    }
  });

  assert.equal(response.ok, true);
  assert.equal(response.form.identity.processKey, "102391/2026");
});

test("READ_CURRENT_FORM preserves FORM_AMBIGUOUS reported inside one frame", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 8, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) =>
      message.type === "READ_FORM"
        ? { ok: false, code: "FORM_AMBIGUOUS", error: "duas estruturas visíveis" }
        : { ok: false },
  });
  installRouter({
    api: { nextCommand: async () => ({ ok: true, command: null }), reportResult: async () => {} },
    chromeApi,
  });

  const response = await sendRuntime(chromeApi, { type: "READ_CURRENT_FORM" });

  assert.equal(response.ok, false);
  assert.equal(response.code, "FORM_AMBIGUOUS");
});

test("the background heartbeat preserves a current-form ambiguity when Mesa is active", async () => {
  const published = [];
  const chromeApi = fakeChrome({
    tabs: [
      { id: 1, active: true, url: "http://127.0.0.1:18743/" },
      { id: 2, active: false, url: `${PORTAL}/complementarato.asp` },
    ],
    onMessage: (message, tabId) =>
      message.type === "READ_FORM" && tabId === 2
        ? { ok: false, code: "FORM_AMBIGUOUS", error: "duas estruturas visíveis" }
        : { ok: false },
  });
  const router = installRouter({
    api: {
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
      publishCurrentSelection: async (observation) => {
        published.push(observation);
        return { ok: true };
      },
    },
    chromeApi,
  });

  await router.observeCurrentForm();

  assert.equal(published.length, 1);
  assertPublishedObservation(published[0], { active: false, code: "FORM_AMBIGUOUS" }, 1);
});

test("the form observation reports portal, frame-scan and detection timings", async () => {
  const published = [];
  const portalUrl = `${PORTAL}/complementarato.asp`;
  const ticks = [100, 105, 200, 210, 500, 525];
  let tick = 0;
  const chromeApi = fakeChrome({
    tabs: [{ id: 3, active: true, url: portalUrl }],
    frames: {
      3: [
        { frameId: 0, url: portalUrl },
        { frameId: 4, url: portalUrl },
      ],
    },
    onMessage: (message, _tabId, frameId) =>
      message.type === "READ_FORM" && frameId === 4
        ? { ok: true, form: OBSERVED_FORM }
        : { ok: false, code: "FORM_NOT_AVAILABLE" },
  });
  const router = installRouter({
    api: {
      publishCurrentSelection: async (observation) => {
        published.push(observation);
        return { ok: true };
      },
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
    monotonicNow: () => ticks[tick++],
  });

  await router.observeCurrentForm();

  const events = published[0].diagnostic_events;
  assert.deepEqual(events.map((event) => event.step), [
    "portal_detected",
    "frames_scanned",
    "form_detected",
  ]);
  assert.deepEqual(events.map((event) => event.elapsed_ms), [5, 10, 25]);
  assert.equal(published[0].active, true);
  assert.deepEqual(published[0].form, OBSERVED_FORM);
});

test("current-selection timing is a diagnostic sidecar and preserves publisher fields", async () => {
  const published = [];
  const chromeApi = fakeChrome({
    tabs: [portalTab(6, { active: true })],
    onMessage: (message) =>
      message.type === "READ_FORM" ? { ok: true, form: OBSERVED_FORM } : { ok: false },
  });
  const router = installRouter({
    api: {
      publishCurrentSelection: async (observation) => {
        published.push(observation);
        return { ok: true };
      },
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
    monotonicNow: () => 10,
  });

  await router.observeCurrentForm();

  const observation = published[0];
  assert.deepEqual(
    Object.keys(observation).filter((key) => key !== "diagnostic_events").sort(),
    ["active", "form", "publisher_id", "sequence"],
  );
  assert.deepEqual(observation.form, OBSERVED_FORM);
  assert.equal(typeof observation.publisher_id, "string");
  assert.equal(observation.sequence, 1);
  assert.ok(Array.isArray(observation.diagnostic_events));
  assert.ok(observation.diagnostic_events.every((event) => !("form" in event)));
});

test("the router answers MESA_STATUS through the Mesa API", async () => {
  const chromeApi = fakeChrome();
  installRouter({
    api: {
      status: async () => ({ ok: true, status: 200, paired: true }),
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
  });

  const response = await sendRuntime(chromeApi, { type: "MESA_STATUS" });

  assert.equal(response.ok, true);
  assert.equal(response.paired, true);
});

test("the router sends manual fill through its Mesa API", async () => {
  const chromeApi = fakeChrome();
  let received = null;
  installRouter({
    api: {
      status: async () => ({ ok: true, paired: true }),
      requestManualFill: async (form) => {
        received = form;
        return { ok: true, status: 201, payload: { state: "READY" } };
      },
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
  });

  const form = { identity: { processKey: "102390/2026" } };
  const response = await sendRuntime(chromeApi, {
    type: "REQUEST_MANUAL_FILL",
    payload: form,
  });

  assert.equal(response.ok, true);
  assert.deepEqual(received, form);
});

test("the router forwards only the current identity and strong act id for next-process", async () => {
  const chromeApi = fakeChrome();
  let received = null;
  installRouter({
    api: {
      requestNextAct: async (identity) => {
        received = identity;
        return { ok: true, status: 201, payload: { command_id: 9 } };
      },
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
  });

  const response = await sendRuntime(chromeApi, {
    type: MESSAGE_TYPES.REQUEST_NEXT_ACT,
    payload: {
      identity: {
        processKey: "current/2026",
        interestedNormalized: "pessoa atual",
        portalActId: "act-current",
        target_identity: { processKey: "forged/2026", interestedNormalized: "forjada" },
      },
    },
  });

  assert.equal(response.ok, true);
  assert.deepEqual(received, {
    processKey: "current/2026",
    interestedNormalized: "pessoa atual",
    portalActId: "act-current",
  });
});

test("the router refuses next-process requests without both current identity fields", async () => {
  const chromeApi = fakeChrome();
  let requestCount = 0;
  installRouter({
    api: {
      requestNextAct: async () => {
        requestCount += 1;
        return { ok: true };
      },
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
  });

  const response = await sendRuntime(chromeApi, {
    type: MESSAGE_TYPES.REQUEST_NEXT_ACT,
    payload: { identity: { processKey: "current/2026" } },
  });

  assert.deepEqual(response, { ok: false, error: "current_identity_required" });
  assert.equal(requestCount, 0);
});

test("the sidepanel can read one authoritative next-act command status", async () => {
  const chromeApi = fakeChrome();
  let requestedId = null;
  const command = { id: 42, type: "OPEN_NEXT_ACT", state: "FAILED", error: "TARGET_NOT_FOUND" };
  installRouter({
    api: {
      commandStatus: async (commandId) => {
        requestedId = commandId;
        return { ok: true, status: 200, command };
      },
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
  });

  const response = await sendRuntime(chromeApi, {
    type: "READ_NEXT_ACT_STATUS",
    payload: { command_id: 42 },
  });

  assert.equal(requestedId, 42);
  assert.deepEqual(response.command, command);
});

test("the router registers a slow recovery alarm", () => {
  const chromeApi = fakeChrome();

  installRouter({
    api: { nextCommand: async () => ({ ok: true, command: null }), reportResult: async () => {} },
    chromeApi,
  });

  assert.equal(chromeApi.alarms.created.length, 1);
  assert.ok(chromeApi.alarms.created[0].info.periodInMinutes >= 1);
  assert.equal(chromeApi.alarmListeners.length, 1);
});

test("the extension action opens the operational side panel", () => {
  const chromeApi = fakeChrome();

  installRouter({
    api: { nextCommand: async () => ({ ok: true, command: null }), reportResult: async () => {} },
    chromeApi,
  });

  assert.deepEqual(chromeApi.sidePanelBehaviors, [{ openPanelOnActionClick: true }]);
});

// ------------------------------------------------------------- CR-02/03/04

/** A router whose retries and waits are instantaneous. */
const FAST = { retryAttempts: 2, retryDelayMs: 1, formReadAttempts: 1, formReadDelayMs: 1, pageDelayMs: 1 };

function idleApi() {
  return { nextCommand: async () => ({ ok: true, command: null }), reportResult: async () => {} };
}

function portalTab(id, { active = false } = {}) {
  return { id, active, url: `${PORTAL}/ProcessonoSetor.asp` };
}

test("OPEN_ACT keeps a list frame's specific refusal when another frame is unknown", async () => {
  let openCalls = 0;
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [
      { frameId: 4, url: `${PORTAL}/ProcessonoSetor.asp` },
      { frameId: 0, url: `${PORTAL}/telaPrincipalMenu.asp` },
    ] },
    onMessage: (message, _tabId, frameId) => {
      if (message.type === "READ_FORM") return { ok: false, code: "FORM_NOT_AVAILABLE" };
      if (message.type === "SCAN_PAGE") {
        return { ok: true, snapshot: { role: frameId === 4 ? "list" : "unknown" } };
      }
      if (message.type === "OPEN_ACT") {
        openCalls += 1;
        return frameId === 4
          ? { ok: false, code: "ROW_ACTION_NOT_FOUND" }
          : { ok: false, code: "SCREEN_NOT_NAVIGABLE" };
      }
      return { ok: false };
    },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const result = await router.openAct({ identity: IDENTITY });

  assert.equal(result.code, "ROW_ACTION_NOT_FOUND");
  assert.equal(openCalls, 1);
});

test("OPEN_ACT recognizes an exact form in another portal tab before clicking a list row", async () => {
  let openCalls = 0;
  const chromeApi = fakeChrome({
    tabs: [portalTab(1), portalTab(2)],
    frames: {
      1: [{ frameId: 4, url: `${PORTAL}/ProcessonoSetor.asp` }],
      2: [{ frameId: 7, url: `${PORTAL}/complementarAto.asp` }],
    },
    onMessage: (message, tabId, frameId) => {
      if (message.type === "READ_FORM") {
        return tabId === 2 && frameId === 7
          ? { ok: true, form: { identity: IDENTITY } }
          : { ok: false, code: "FORM_NOT_AVAILABLE" };
      }
      if (message.type === "SCAN_PAGE") return { ok: true, snapshot: { role: "list" } };
      if (message.type === "OPEN_ACT") {
        openCalls += 1;
        return { ok: true, action: "open_act", screen: "list", waitingForFrame: true };
      }
      return { ok: false };
    },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const result = await router.openAct({ identity: IDENTITY });

  assert.equal(result.action, "already_open");
  assert.equal(result.screen, "form");
  assert.equal(openCalls, 0);
});

test("OPEN_ACT refuses multiple list frames before causing navigation", async () => {
  let openCalls = 0;
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [
      { frameId: 4, url: `${PORTAL}/ProcessonoSetor.asp` },
      { frameId: 5, url: `${PORTAL}/MeusProcessos.asp` },
    ] },
    onMessage: (message) => {
      if (message.type === "READ_FORM") return { ok: false, code: "FORM_NOT_AVAILABLE" };
      if (message.type === "SCAN_PAGE") return { ok: true, snapshot: { role: "list" } };
      if (message.type === "OPEN_ACT") {
        openCalls += 1;
        return { ok: true, action: "open_act", screen: "list" };
      }
      return { ok: false };
    },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const result = await router.openAct({ identity: IDENTITY });

  assert.equal(result.code, "LIST_AMBIGUOUS");
  assert.equal(openCalls, 0);
});

test("OPEN_ACT reuses the frozen paginated navigator for a target on a later page", async () => {
  const context = {
    scan_id: 8,
    source_scope: "sector_finalistic",
    marker: { label: "M", value: "marker-8" },
  };
  let pageNumber = 1;
  let opened = false;
  let advances = 0;
  let openCalls = 0;
  const router = installRouter({
    api: idleApi(),
    chromeApi: fakeChrome(),
    timing: { ...FAST, nextActPageCap: 3, nextActAttempts: 1 },
    nextActDependencies: {
      async readTargetForm(identity) {
        return opened
          ? { ok: true, form: { identity }, tabId: 4, frameId: 3 }
          : { ok: false, code: "FORM_NOT_AVAILABLE" };
      },
      async readListPage() {
        return {
          ok: true,
          frame: { tabId: 4, frameId: 6 },
          snapshot: {
            role: "list",
            source_scope: context.source_scope,
            marker: context.marker,
            page: pageNumber,
            total_pages: 2,
          },
        };
      },
      async openAct(_identity, frame) {
        openCalls += 1;
        assert.deepEqual(frame, { tabId: 4, frameId: 6 });
        if (pageNumber === 1) return { ok: false, code: "ROW_ACTION_NOT_FOUND" };
        opened = true;
        return { ok: true, action: "open_act", screen: "list" };
      },
      async advancePage(_frame, currentPage) {
        advances += 1;
        pageNumber = currentPage + 1;
        return { ok: true, page_after: pageNumber };
      },
      async activateTab(tabId) {
        assert.equal(tabId, 4);
        return { ok: true };
      },
    },
  });

  const result = await router.openAct({ identity: IDENTITY, context });

  assert.equal(result.ok, true);
  assert.equal(result.action, "open_act");
  assert.equal(result.screen, "form");
  assert.equal(openCalls, 2);
  assert.equal(advances, 1);
});

test("the scan is addressed to the list frame, not to the top frame", async () => {
  let pageAdvances = 0;
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: {
      1: [
        { frameId: 0, url: `${PORTAL}/telaPrincipalMenu.asp` },
        { frameId: 4, url: `${PORTAL}/ProcessonoSetor.asp` },
      ],
    },
    onMessage: (message, tabId, frameId) => {
      if (message.type === "SCAN_PAGE") {
        if (frameId !== 4) {
          return { ok: true, snapshot: { role: "unknown", rows: [], page: 1, total_pages: 1 } };
        }
        const listPageNumber = Math.min(1 + pageAdvances, 2);
        return {
          ok: true,
          snapshot: page(
            [{ process_key: `10239${listPageNumber}/2026`, interested_normalized: "pessoa exemplo" }],
            { page: listPageNumber, total_pages: 2 }
          ),
        };
      }
      if (message.type === "LIST_PAGE") {
        pageAdvances += 1;
        return { ok: true, changed: true };
      }
      return { ok: false };
    },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const snapshot = await router.scanPortal({});

  assert.equal(snapshot.rows.length, 2);
  const advances = chromeApi.sent.filter((entry) => entry.message.type === "LIST_PAGE");
  assert.equal(advances.length, 1);
  assert.equal(advances[0].frameId, 4);
});

test("the scan waits for a reloaded page instead of reading the stale frame", async () => {
  let pageAdvances = 0;
  let listScans = 0;
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [{ frameId: 4, url: `${PORTAL}/ProcessonoSetor.asp` }] },
    onMessage: (message, _tabId, frameId) => {
      if (frameId !== 4) return { ok: true, snapshot: { role: "unknown", rows: [], page: 1, total_pages: 1 } };
      if (message.type === "SCAN_PAGE") {
        listScans += 1;
        const pageNumber = pageAdvances === 0 || listScans <= 3 ? 1 : 2;
        return {
          ok: true,
          snapshot: page(
            [{ process_key: `10239${pageNumber}/2026`, interested_normalized: "pessoa exemplo" }],
            { page: pageNumber, total_pages: 2 }
          ),
        };
      }
      if (message.type === "LIST_PAGE") {
        pageAdvances += 1;
        return { ok: true, changed: true, page_before: 1, page_after: 2 };
      }
      return { ok: false };
    },
  });
  const router = installRouter({
    api: idleApi(),
    chromeApi,
    timing: { ...FAST, pageReadyAttempts: 5, pageReadyDelayMs: 1 },
  });

  const snapshot = await router.scanPortal({});

  assert.equal(snapshot.rows.length, 2);
  assert.ok(listScans >= 5);
});

test("the scan tolerates a slow portal page refresh", async () => {
  let pageAdvances = 0;
  let listScans = 0;
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [{ frameId: 4, url: `${PORTAL}/ProcessonoSetor.asp` }] },
    onMessage: (message, _tabId, frameId) => {
      if (frameId !== 4) return { ok: true, snapshot: { role: "unknown", rows: [], page: 1, total_pages: 1 } };
      if (message.type === "SCAN_PAGE") {
        listScans += 1;
        const pageNumber = pageAdvances === 0 || listScans <= 21 ? 1 : 2;
        return {
          ok: true,
          snapshot: page(
            [{ process_key: `10239${pageNumber}/2026`, interested_normalized: "pessoa exemplo" }],
            { page: pageNumber, total_pages: 2 }
          ),
        };
      }
      if (message.type === "LIST_PAGE") {
        pageAdvances += 1;
        return { ok: true, changed: true, page_before: 1, page_after: 2 };
      }
      return { ok: false };
    },
  });
  const router = installRouter({
    api: idleApi(),
    chromeApi,
    timing: { ...FAST, pageReadyDelayMs: 1 },
  });

  const snapshot = await router.scanPortal({});

  assert.equal(snapshot.rows.length, 2);
  assert.ok(listScans >= 23);
});

test("the scan retries a page advance that did not take effect", async () => {
  let pageNumber = 1;
  let advanceCalls = 0;
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [{ frameId: 4, url: `${PORTAL}/ProcessonoSetor.asp` }] },
    onMessage: (message, _tabId, frameId) => {
      if (frameId !== 4) return { ok: true, snapshot: { role: "unknown", rows: [], page: 1, total_pages: 1 } };
      if (message.type === "SCAN_PAGE") {
        return {
          ok: true,
          snapshot: page(
            [{ process_key: `10239${pageNumber}/2026`, interested_normalized: "pessoa exemplo" }],
            { page: pageNumber, total_pages: 2 }
          ),
        };
      }
      if (message.type === "LIST_PAGE") {
        advanceCalls += 1;
        if (advanceCalls === 2) pageNumber = 2;
        return { ok: true, changed: true, page_before: 1, page_after: 2 };
      }
      return { ok: false };
    },
  });
  const router = installRouter({
    api: idleApi(),
    chromeApi,
    timing: { ...FAST, pageReadyAttempts: 3, pageReadyDelayMs: 1 },
  });

  const snapshot = await router.scanPortal({});

  assert.equal(snapshot.rows.length, 2);
  assert.equal(advanceCalls, 2);
});

test("two frames claiming to be the list are refused", async () => {
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [{ frameId: 0 }, { frameId: 4 }] },
    onMessage: () => ({ ok: true, snapshot: page([]) }),
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  await assert.rejects(() => router.scanPortal({}), /mais de uma moldura/u);
});

test("a portal without a list frame is refused", async () => {
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    onMessage: () => ({ ok: true, snapshot: { role: "unknown", rows: [] } }),
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  await assert.rejects(() => router.scanPortal({}), /lista de processos/u);
});

test("READ_FORM ignores a frame whose form is another act", async () => {
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [{ frameId: 0 }, { frameId: 2 }] },
    onMessage: (message, tabId, frameId) => {
      if (message.type !== "READ_FORM") return { ok: false };
      return frameId === 2
        ? { ok: true, form: { identity: IDENTITY, generation: 4 } }
        : {
            ok: true,
            form: {
              identity: { processKey: "999999/2026", interestedNormalized: "outra pessoa" },
              generation: 1,
            },
          };
    },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.readForm({ identity: IDENTITY });

  assert.equal(outcome.ok, true);
  assert.equal(outcome.form.generation, 4);
});

test("two frames with the same act block instead of picking one", async () => {
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [{ frameId: 0 }, { frameId: 2 }] },
    onMessage: () => ({ ok: true, form: { identity: IDENTITY, generation: 4 } }),
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.readForm({ identity: IDENTITY });

  assert.equal(outcome.ok, false);
  assert.equal(outcome.code, "FORM_AMBIGUOUS");
});

test("a form that never appears is reported after the bounded wait", async () => {
  let attempts = 0;
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    onMessage: () => {
      attempts += 1;
      return { ok: false, error: "ainda não" };
    },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.readForm({ identity: IDENTITY });

  assert.equal(outcome.ok, false);
  assert.equal(outcome.code, "FORM_NOT_AVAILABLE");
  assert.ok(attempts >= 1);
});

test("FILL_FORM is written in exactly one confirmed frame", async () => {
  const documentNonce = "a".repeat(32);
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [{ frameId: 0 }, { frameId: 2 }, { frameId: 5 }] },
    onMessage: (message, tabId, frameId) => {
      if (message.type === "READ_FORM") {
        if (frameId === 2) {
          return { ok: true, form: { identity: IDENTITY, generation: 4, documentNonce } };
        }
        if (frameId === 5) {
          return {
            ok: true,
            form: {
              identity: { processKey: "999999/2026", interestedNormalized: "outra pessoa" },
              generation: 1,
            },
          };
        }
        return { ok: false, error: "sem formulário" };
      }
      if (message.type === "FILL_FORM") {
        return { ok: true, field_results: { cargo: { status: "changed", proposed: "Professor", after: "Professor" } } };
      }
      return { ok: false };
    },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.fillForm({
    identity: IDENTITY,
    generation: 4,
    document_nonce: documentNonce,
    fields: { cargo: "Professor" },
  });

  assert.equal(outcome.ok, true);
  const writes = chromeApi.sent.filter((entry) => entry.message.type === "FILL_FORM");
  assert.equal(writes.length, 1);
  assert.equal(writes[0].frameId, 2);
});

test("a fill without a confirmed frame writes nowhere", async () => {
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    onMessage: () => ({ ok: false, error: "sem formulário" }),
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.fillForm({
    identity: IDENTITY,
    document_nonce: "a".repeat(32),
    fields: { cargo: "Professor" },
  });

  assert.equal(outcome.ok, false);
  assert.equal(outcome.code, "FORM_NOT_AVAILABLE");
  assert.equal(chromeApi.sent.filter((entry) => entry.message.type === "FILL_FORM").length, 0);
});

test("a matching identity in a different document nonce is stale and receives no fill", async () => {
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [{ frameId: 2 }] },
    onMessage: (message) => message.type === "READ_FORM"
      ? { ok: true, form: { identity: IDENTITY, generation: 1, documentNonce: "b".repeat(32) } }
      : { ok: true },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.fillForm({
    identity: IDENTITY,
    generation: 1,
    document_nonce: "a".repeat(32),
    fields: { cargo: "Professor" },
  });

  assert.equal(outcome.ok, false);
  assert.equal(outcome.code, "STALE_FORM");
  assert.equal(chromeApi.sent.filter((entry) => entry.message.type === "FILL_FORM").length, 0);
});

test("the router selects the one frame with the expected document nonce", async () => {
  const expectedNonce = "b".repeat(32);
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [{ frameId: 2 }, { frameId: 5 }] },
    onMessage: (message, _tabId, frameId) => message.type === "READ_FORM"
      ? {
          ok: true,
          form: {
            identity: IDENTITY,
            generation: 1,
            documentNonce: frameId === 2 ? "a".repeat(32) : expectedNonce,
          },
        }
      : { ok: true },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.fillForm({
    identity: IDENTITY,
    generation: 1,
    document_nonce: expectedNonce,
    fields: { cargo: "Professor" },
  });

  assert.equal(outcome.ok, true);
  const writes = chromeApi.sent.filter((entry) => entry.message.type === "FILL_FORM");
  assert.equal(writes.length, 1);
  assert.equal(writes[0].frameId, 5);
});

test("a frame that disappears is retried and then reported", async () => {
  let attempts = 0;
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [{ frameId: 0 }, { frameId: 9 }] },
    onMessage: (message, tabId, frameId) => {
      if (frameId === 9) {
        attempts += 1;
        throw new Error("frame removed");
      }
      return { ok: false, error: "sem formulário" };
    },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.readForm({ identity: IDENTITY });

  assert.equal(outcome.ok, false);
  assert.equal(outcome.code, "FORM_NOT_AVAILABLE");
  assert.equal(attempts, 2, "the bounded retry must be visible in the count");
});

test("the manual fallback never reads another tab", async () => {
  const chromeApi = fakeChrome({
    tabs: [portalTab(1, { active: true }), portalTab(2)],
    onMessage: (message, tabId) =>
      message.type === "READ_FORM" && tabId === 2
        ? { ok: true, form: { identity: IDENTITY } }
        : { ok: false, error: "sem formulário" },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.readCurrentForm();

  assert.equal(outcome.ok, false);
  assert.equal(outcome.code, "FORM_NOT_AVAILABLE");
});

test("the manual fallback reads the form of the active tab", async () => {
  const chromeApi = fakeChrome({
    tabs: [portalTab(1, { active: true }), portalTab(2)],
    onMessage: (message, tabId) =>
      message.type === "READ_FORM" && tabId === 1
        ? { ok: true, form: { identity: IDENTITY, generation: 7 } }
        : { ok: false, error: "sem formulário" },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.readCurrentForm();

  assert.equal(outcome.ok, true);
  assert.equal(outcome.form.generation, 7);
});

test("two forms in the active tab block the manual fallback", async () => {
  const chromeApi = fakeChrome({
    tabs: [portalTab(1, { active: true })],
    frames: { 1: [{ frameId: 0 }, { frameId: 3 }] },
    onMessage: (message) =>
      message.type === "READ_FORM" ? { ok: true, form: { identity: IDENTITY } } : { ok: false },
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.readCurrentForm();

  assert.equal(outcome.ok, false);
  assert.equal(outcome.code, "FORM_AMBIGUOUS");
});

test("an active tab outside the portal blocks the manual fallback", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 1, active: true, url: "https://example.com/" }],
    onMessage: () => ({ ok: true, form: { identity: IDENTITY } }),
  });
  const router = installRouter({ api: idleApi(), chromeApi, timing: FAST });

  const outcome = await router.readCurrentForm();

  assert.equal(outcome.ok, false);
  assert.equal(outcome.code, "PORTAL_TAB_NOT_ACTIVE");
});

// ------------------------------------------------------------------- CR-14

function listPage({ page: number = 1, total_pages = 2, scope = "sector_finalistic", marker = null, role = "list" } = {}) {
  return { role, source_scope: scope, marker, page: number, total_pages, rows: [] };
}

test("scanAreaPages aborts when the sector changes between pages", async () => {
  const pages = [listPage({ page: 1 }), listPage({ page: 2, scope: "sector_other" })];
  let index = 0;

  await assert.rejects(
    () =>
      scanAreaPages({
        scanPage: async () => pages[Math.min(index, pages.length - 1)],
        advancePage: async () => {
          index += 1;
          return true;
        },
      }),
    /escopo/u
  );
});

test("scanAreaPages aborts when the marker changes between pages", async () => {
  const pages = [
    listPage({ page: 1, marker: { label: "A", value: "1" } }),
    listPage({ page: 2, marker: { label: "B", value: "2" } }),
  ];
  let index = 0;

  await assert.rejects(
    () =>
      scanAreaPages({
        scanPage: async () => pages[Math.min(index, pages.length - 1)],
        advancePage: async () => {
          index += 1;
          return true;
        },
      }),
    /marcador/u
  );
});

test("scanAreaPages aborts when the role changes between pages", async () => {
  const pages = [listPage({ page: 1 }), listPage({ page: 2, role: "form" })];
  let index = 0;

  await assert.rejects(
    () =>
      scanAreaPages({
        scanPage: async () => pages[Math.min(index, pages.length - 1)],
        advancePage: async () => {
          index += 1;
          return true;
        },
      }),
    /papel/u
  );
});

test("scanAreaPages freezes the scope and the marker of the first page", async () => {
  const pages = [
    listPage({ page: 1, marker: { label: "M", value: "6189" } }),
    listPage({ page: 2, marker: { label: "M", value: "6189" } }),
  ];
  let index = 0;

  const snapshot = await scanAreaPages({
    scanPage: async () => pages[Math.min(index, pages.length - 1)],
    advancePage: async () => {
      index += 1;
      return true;
    },
  });

  assert.equal(snapshot.role, "list");
  assert.equal(snapshot.source_scope, "sector_finalistic");
  assert.deepEqual(snapshot.marker, { label: "M", value: "6189" });
});

test("the router serves the reliability status through the service worker", async () => {
  const chromeApi = fakeChrome();
  const capabilities = {
    manual_form_fill: { state: "UNQUALIFIED", real_dev_streak: 0, portable_streak: 0 },
  };
  let calls = 0;
  installRouter({
    api: {
      reliabilityStatus: async () => {
        calls += 1;
        return { ok: true, status: 200, capabilities };
      },
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
  });

  const response = await sendRuntime(chromeApi, { type: MESSAGE_TYPES.RELIABILITY_STATUS });

  assert.equal(calls, 1);
  assert.equal(response.ok, true);
  assert.deepEqual(response.capabilities, capabilities);
});

test("the reliability status route is a request, never a queued command", () => {
  assert.equal(Object.hasOwn(MESSAGE_TYPES, "RELIABILITY_STATUS"), true);
  assert.equal(Object.hasOwn(COMMAND_TYPES, "RELIABILITY_STATUS"), false);
});

test("the router forwards a reported AR-1 attempt failure", async () => {
  const chromeApi = fakeChrome();
  let received = null;
  installRouter({
    api: {
      reportAr1Attempt: async (payload) => {
        received = payload;
        return { ok: true, status: 201, payload: { recorded: true, code: payload.code } };
      },
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
  });

  const response = await sendRuntime(chromeApi, {
    type: MESSAGE_TYPES.REPORT_AR1_ATTEMPT,
    payload: { code: "form_not_available" },
  });

  assert.deepEqual(received, { code: "FORM_NOT_AVAILABLE" });
  assert.equal(response.ok, true);
});

test("the router refuses an AR-1 attempt report without a code", async () => {
  const chromeApi = fakeChrome();
  let calls = 0;
  installRouter({
    api: {
      reportAr1Attempt: async () => {
        calls += 1;
        return { ok: true };
      },
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
  });

  const response = await sendRuntime(chromeApi, { type: MESSAGE_TYPES.REPORT_AR1_ATTEMPT });

  assert.deepEqual(response, { ok: false, error: "attempt_code_required" });
  assert.equal(calls, 0);
});

test("readCurrentForm returns only sanitized structural diagnostics", async () => {
  const url = `${PORTAL_ORIGIN}/SISTEMAS/PROCESSO/ComplementarAto.asp?processo=102390&doc=9#top`;
  const chromeApi = fakeChrome({
    tabs: [{ id: 1, url, active: true, lastFocusedWindow: true }],
    frames: { 1: [{ frameId: 0, url }] },
    onMessage: () => ({ ok: true, form: { identity: IDENTITY, generation: 4, fields: {} } }),
  });
  const router = installRouter({
    api: { nextCommand: async () => ({ ok: true, command: null }) },
    chromeApi,
    timing: FAST,
  });

  const response = await router.readCurrentForm();

  assert.equal(response.ok, true);
  assert.deepEqual(Object.keys(response.diagnostics).sort(), [
    "browser_session_id",
    "frame_ref",
    "generation",
    "route",
    "screen",
    "tab_ref",
  ]);
  assert.equal(response.diagnostics.route, "/SISTEMAS/PROCESSO/ComplementarAto.asp");
  assert.equal(response.diagnostics.screen, "form");
  assert.equal(response.diagnostics.generation, 4);
  assert.equal(response.diagnostics.tab_ref, "tab-1");
  assert.equal(response.diagnostics.frame_ref, "frame-0");
  assert.deepEqual(response.form.identity, IDENTITY);
  const serialized = JSON.stringify(response);
  assert.doesNotMatch(serialized, /processo=|doc=9|#top/u);
});

test("two visible forms in the active tab never become the current form", async () => {
  const url = `${PORTAL_ORIGIN}/SISTEMAS/PROCESSO/ComplementarAto.asp`;
  const chromeApi = fakeChrome({
    tabs: [{ id: 1, url, active: true, lastFocusedWindow: true }],
    frames: { 1: [{ frameId: 0, url }, { frameId: 1, url }] },
    onMessage: () => ({ ok: true, form: { identity: IDENTITY, generation: 4 } }),
  });
  const router = installRouter({
    api: { nextCommand: async () => ({ ok: true, command: null }) },
    chromeApi,
    timing: FAST,
  });

  const response = await router.readCurrentForm();

  assert.equal(response.ok, false);
  assert.equal(response.code, "FORM_AMBIGUOUS");
  assert.equal(response.diagnostics, undefined);
});

function observingApi(published) {
  return {
    nextCommand: async () => ({ ok: true, command: null }),
    reportResult: async () => {},
    publishCurrentSelection: async (observation) => {
      published.push(observation);
      return { ok: true, status: 200 };
    },
  };
}

function assertPublishedObservation(actual, expected, sequence) {
  const {
    publisher_id: publisherId,
    sequence: actualSequence,
    diagnostic_events: _diagnosticEvents,
    ...observation
  } = actual;
  assert.match(publisherId, /^[a-f0-9]{32}$/u);
  assert.equal(actualSequence, sequence);
  assert.deepEqual(observation, expected);
  return publisherId;
}

test("the heartbeat publishes the open form with no sidepanel message at all", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) =>
      message.type === "READ_FORM" ? { ok: true, form: OBSERVED_FORM } : { ok: false },
  });
  const published = [];
  const router = installRouter({ api: observingApi(published), chromeApi });

  await router.poll();

  assert.equal(published.length, 1);
  assertPublishedObservation(published[0], { active: true, form: OBSERVED_FORM }, 1);
});

test("an identical observation is deduplicated until the keepalive window", async () => {
  let clock = 0;
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) =>
      message.type === "READ_FORM" ? { ok: true, form: OBSERVED_FORM } : { ok: false },
  });
  const published = [];
  const router = installRouter({ api: observingApi(published), chromeApi, now: () => clock });

  await router.poll();
  assert.equal(published.length, 1);

  clock = 1500;
  await router.poll();
  assert.equal(published.length, 1, "a repeat inside the window is not republished");

  clock = PORTAL_SELECTION_KEEPALIVE_MS;
  await router.poll();
  assert.equal(published.length, 2, "the keepalive renews the TTL");
  const publisherId = assertPublishedObservation(published[0], { active: true, form: OBSERVED_FORM }, 1);
  assert.equal(assertPublishedObservation(published[1], { active: true, form: OBSERVED_FORM }, 2), publisherId);
});

test("a new router lifecycle receives a distinct publisher identity", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) =>
      message.type === "READ_FORM" ? { ok: true, form: OBSERVED_FORM } : { ok: false },
  });
  const firstPublished = [];
  const secondPublished = [];
  const firstRouter = installRouter({ api: observingApi(firstPublished), chromeApi });
  const secondRouter = installRouter({ api: observingApi(secondPublished), chromeApi });

  await firstRouter.poll();
  await secondRouter.poll();

  const firstPublisher = assertPublishedObservation(
    firstPublished[0],
    { active: true, form: OBSERVED_FORM },
    1,
  );
  const secondPublisher = assertPublishedObservation(
    secondPublished[0],
    { active: true, form: OBSERVED_FORM },
    1,
  );
  assert.notEqual(secondPublisher, firstPublisher);
});

test("the router fails closed when secure publisher randomness is unavailable", async () => {
  const originalCrypto = Object.getOwnPropertyDescriptor(globalThis, "crypto");
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) =>
      message.type === "READ_FORM" ? { ok: true, form: OBSERVED_FORM } : { ok: false },
  });
  const published = [];
  try {
    Object.defineProperty(globalThis, "crypto", { configurable: true, value: undefined });
    const router = installRouter({ api: observingApi(published), chromeApi });

    const outcome = await router.poll();

    assert.equal(outcome.ok, true);
    assert.equal(published.length, 0);
  } finally {
    if (originalCrypto) Object.defineProperty(globalThis, "crypto", originalCrypto);
    else delete globalThis.crypto;
  }
});

test("a refused publisher retries with a new sequence and deduplicates after acceptance", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) =>
      message.type === "READ_FORM" ? { ok: true, form: OBSERVED_FORM } : { ok: false },
  });
  const published = [];
  let attempt = 0;
  const api = {
    ...observingApi(published),
    publishCurrentSelection: async (observation) => {
      published.push(observation);
      attempt += 1;
      return attempt === 1
        ? { ok: false, status: 409, error: "PUBLISHER_OWNED" }
        : { ok: true, status: 200 };
    },
  };
  const router = installRouter({ api, chromeApi, now: () => 0 });

  await router.poll();
  await router.poll();
  await router.poll();

  assert.equal(published.length, 2);
  const publisherId = assertPublishedObservation(
    published[0],
    { active: true, form: OBSERVED_FORM },
    1,
  );
  assert.equal(
    assertPublishedObservation(published[1], { active: true, form: OBSERVED_FORM }, 2),
    publisherId,
  );
});

test("a changed form is published immediately, without waiting for the keepalive", async () => {
  let clock = 0;
  let current = OBSERVED_FORM;
  const other = {
    identity: { processKey: "100/2026", interestedNormalized: "outra pessoa" },
    generation: 9,
  };
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) => (message.type === "READ_FORM" ? { ok: true, form: current } : { ok: false }),
  });
  const published = [];
  const router = installRouter({ api: observingApi(published), chromeApi, now: () => clock });

  await router.poll();
  clock = 1500;
  current = other;
  await router.poll();

  assert.equal(published.length, 2);
  const publisherId = assertPublishedObservation(published[0], { active: true, form: OBSERVED_FORM }, 1);
  assert.equal(assertPublishedObservation(published[1], { active: true, form: other }, 2), publisherId);
});

test("a new document nonce republishes even when identity and generation repeat", async () => {
  let clock = 0;
  let current = { ...OBSERVED_FORM, documentNonce: "a".repeat(32) };
  const firstDocument = current;
  const nextDocument = { ...OBSERVED_FORM, documentNonce: "b".repeat(32) };
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) => (message.type === "READ_FORM" ? { ok: true, form: current } : { ok: false }),
  });
  const published = [];
  const router = installRouter({ api: observingApi(published), chromeApi, now: () => clock });

  await router.poll();
  clock = 1500;
  current = nextDocument;
  await router.poll();

  assert.equal(published.length, 2);
  const publisherId = assertPublishedObservation(published[0], { active: true, form: firstDocument }, 1);
  assert.equal(assertPublishedObservation(published[1], { active: true, form: nextDocument }, 2), publisherId);
});

test("the selection is cleared when no single form is open", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: () => ({ ok: false }),
  });
  const published = [];
  const router = installRouter({ api: observingApi(published), chromeApi });

  await router.poll();
  await router.poll();

  assert.equal(published.length, 1, "an identical clear is deduplicated");
  assertPublishedObservation(published[0], { active: false, code: "FORM_NOT_AVAILABLE" }, 1);
});

test("two candidate forms are published as ambiguous, never as a match", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    frames: {
      7: [
        { frameId: 0, url: `${PORTAL}/complementarato.asp` },
        { frameId: 4, url: `${PORTAL}/formulario.asp` },
      ],
    },
    onMessage: (message) =>
      message.type === "READ_FORM" ? { ok: true, form: OBSERVED_FORM } : { ok: false },
  });
  const published = [];
  const router = installRouter({ api: observingApi(published), chromeApi });

  await router.poll();

  assert.equal(published.length, 1);
  assertPublishedObservation(published[0], { active: false, code: "FORM_AMBIGUOUS" }, 1);
});

test("the keepalive still renews while the operator is looking at the Mesa", async () => {
  const chromeApi = fakeChrome({
    tabs: [
      { id: 1, active: true, url: "http://127.0.0.1:18743/" },
      { id: 7, active: false, url: `${PORTAL}/complementarato.asp` },
    ],
    onMessage: (message) =>
      message.type === "READ_FORM" ? { ok: true, form: OBSERVED_FORM } : { ok: false },
  });
  const published = [];
  const router = installRouter({ api: observingApi(published), chromeApi });

  await router.poll();

  assert.equal(published.length, 1);
  assertPublishedObservation(published[0], { active: true, form: OBSERVED_FORM }, 1);
});

test("no Área Restrita tab at all is reported as an inactive portal tab", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 1, active: true, url: "http://127.0.0.1:18743/" }],
  });
  const published = [];
  const router = installRouter({ api: observingApi(published), chromeApi });

  await router.poll();

  assertPublishedObservation(published[0], { active: false, code: "PORTAL_TAB_NOT_ACTIVE" }, 1);
});

test("publishing never replaces command polling", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) =>
      message.type === "READ_FORM" ? { ok: true, form: OBSERVED_FORM } : { ok: false },
  });
  const reported = [];
  const published = [];
  const router = installRouter({
    api: {
      nextCommand: async () => ({ ok: true, command: { id: 11, type: "STATUS", payload: {} } }),
      reportResult: async (commandId, result) => reported.push({ commandId, result }),
      publishCurrentSelection: async (observation) => {
        published.push(observation);
        return { ok: true };
      },
    },
    chromeApi,
  });

  const outcome = await router.poll();

  assert.equal(published.length, 1);
  assert.equal(outcome.command, 11);
  assert.equal(reported.length, 1);
  assert.equal(reported[0].result.ok, true);
  assert.equal(reported[0].result.command_id, 11);
});

test("a slow observation cannot let an older tick overwrite a newer one", async () => {
  const chromeApi = fakeChrome({
    tabs: [{ id: 7, active: true, url: `${PORTAL}/complementarato.asp` }],
    onMessage: (message) =>
      message.type === "READ_FORM" ? { ok: true, form: OBSERVED_FORM } : { ok: false },
  });
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const published = [];
  const router = installRouter({
    api: {
      nextCommand: async () => {
        await gate;
        return { ok: true, command: null };
      },
      reportResult: async () => {},
      publishCurrentSelection: async (observation) => {
        published.push(observation);
        return { ok: true };
      },
    },
    chromeApi,
  });

  const first = router.poll();
  const second = await router.poll();

  assert.deepEqual(second, { ok: true, skipped: true }, "poll is serialized by its latch");
  release();
  await first;
  assert.equal(published.length, 1);
});
