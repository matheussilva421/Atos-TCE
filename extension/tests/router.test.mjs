import test from "node:test";
import assert from "node:assert/strict";

import { executeCommand, installRouter, scanAreaPages } from "../background/router.js";
import { fakeChrome } from "./helpers.mjs";

const PORTAL = "https://novaarearestrita.tce.rn.gov.br";

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
  const chromeApi = fakeChrome({
    tabs: [portalTab(1)],
    frames: { 1: [{ frameId: 0 }, { frameId: 2 }, { frameId: 5 }] },
    onMessage: (message, tabId, frameId) => {
      if (message.type === "READ_FORM") {
        if (frameId === 2) return { ok: true, form: { identity: IDENTITY, generation: 4 } };
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

  const outcome = await router.fillForm({ identity: IDENTITY, generation: 4, fields: { cargo: "Professor" } });

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

  const outcome = await router.fillForm({ identity: IDENTITY, fields: { cargo: "Professor" } });

  assert.equal(outcome.ok, false);
  assert.equal(outcome.code, "FORM_NOT_AVAILABLE");
  assert.equal(chromeApi.sent.filter((entry) => entry.message.type === "FILL_FORM").length, 0);
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
