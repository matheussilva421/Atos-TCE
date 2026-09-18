import test from "node:test";
import assert from "node:assert/strict";

import { executeCommand, installRouter, scanAreaPages } from "../background/router.js";
import { fakeChrome } from "./helpers.mjs";

function page(rows, { page: number = 1, total_pages = 1 } = {}) {
  return { role: "list", source_scope: "sector_finalistic", marker: null, page: number, total_pages, rows };
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
    { readForm: async () => ({ identity: IDENTITY, generation: 3, fields: {}, options: {} }) }
  );

  assert.equal(result.command_id, 23);
  assert.equal(result.ok, true);
  assert.equal(result.generation, 3);
  assert.equal(result.identity.processKey, "102390/2026");
});

test("a form that never appears fails instead of inventing a snapshot", async () => {
  const result = await executeCommand(
    { id: 24, type: "READ_FORM", payload: {} },
    { readForm: async () => null }
  );

  assert.equal(result.ok, false);
  assert.match(result.error, /formulário/u);
});

test("a FILL_FORM command returns the verified per-field result", async () => {
  const result = await executeCommand(
    { id: 25, type: "FILL_FORM", payload: { identity: IDENTITY, generation: 4, fields: { cargo: "Professor" } } },
    {
      fillForm: async () => ({
        ok: true,
        identity: IDENTITY,
        generation_after: 5,
        field_results: { cargo: { before: "", proposed: "Professor", after: "Professor", status: "changed" } },
      }),
    }
  );

  assert.equal(result.command_id, 25);
  assert.equal(result.ok, true);
  assert.equal(result.generation_after, 5);
  assert.equal(result.field_results.cargo.status, "changed");
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

test("scanAreaPages stops when the portal stops changing", async () => {
  let advances = 0;

  const snapshot = await scanAreaPages({
    scanPage: async () => page([{ process_key: "102390/2026", interested_normalized: "p" }], { page: 1, total_pages: 9 }),
    advancePage: async () => {
      advances += 1;
      return true;
    },
  });

  assert.equal(snapshot.rows.length, 1);
  assert.ok(advances <= 2, `expected an early stop, advanced ${advances} times`);
});

test("scanAreaPages honours the page cap", async () => {
  let pageNumber = 0;
  let advances = 0;

  await scanAreaPages({
    maxPages: 3,
    scanPage: async () => {
      pageNumber += 1;
      return page([{ process_key: `10${pageNumber}/2026`, interested_normalized: `p${pageNumber}` }], {
        page: pageNumber,
        total_pages: 99,
      });
    },
    advancePage: async () => {
      advances += 1;
      return true;
    },
  });

  assert.equal(advances, 2);
});

test("scanAreaPages stops when the portal cannot advance", async () => {
  const snapshot = await scanAreaPages({
    scanPage: async () => page([{ process_key: "102390/2026", interested_normalized: "p" }], { page: 1, total_pages: 4 }),
    advancePage: async () => false,
  });

  assert.equal(snapshot.rows.length, 1);
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
    tabs: [{ id: 7 }],
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
    tabs: [{ id: 7 }],
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
    tabs: [{ id: 3 }],
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
