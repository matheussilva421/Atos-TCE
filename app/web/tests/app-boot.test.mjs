import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");

/**
 * Boot the real Mesa shell against a minimal DOM.
 *
 * Every other web test asserts on the source text, which cannot see a
 * declaration that nests ``init()`` inside another function: the file still
 * reads correctly and every focused suite stays green while the browser dies
 * with ``ReferenceError: init is not defined``. Importing the module is the only
 * check that actually fails on that.
 */

function stubDocument() {
  const byId = new Map();
  const created = [];
  const make = (tagName = "div") => {
    const node = {
      tagName: tagName.toUpperCase(),
      hidden: false,
      disabled: false,
      className: "",
      textContent: "",
      value: "",
      dataset: {},
      children: [],
      handlers: {},
      setAttribute(name, value) {
        node[name] = value;
      },
      addEventListener(type, handler) {
        node.handlers[type] = handler;
      },
      async click() {
        return node.handlers.click?.({ target: node });
      },
      append(...nodes) {
        node.children.push(...nodes);
      },
      remove() {
        document.body.children = document.body.children.filter((child) => child !== node);
      },
      replaceChildren(...nodes) {
        node.children = [...nodes];
      },
      replaceChildrenAnd() {},
      querySelector() {
        return null;
      },
      querySelectorAll() {
        return [];
      },
      scrollIntoView() {},
      getContext() {
        return null;
      },
    };
    return node;
  };
  const body = make("body");
  return {
    readyState: "complete",
    body,
    created,
    getElementById(id) {
      if (!byId.has(id)) byId.set(id, make());
      return byId.get(id);
    },
    createElement(tagName) {
      const node = make(tagName);
      created.push(node);
      return node;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
}

function withBootGlobals({ fetchImpl = () => new Promise(() => {}), now = null } = {}) {
  const html = stubDocument();
  const intervals = [];
  const timeouts = [];
  const calls = [];
  const previous = new Map();
  const originalDateNow = Date.now;
  let fakeNow = now;
  if (now !== null) Date.now = () => fakeNow;
  const overrides = {
    document: html,
    window: {
      setInterval: (...args) => {
        intervals.push(args);
        return 1;
      },
      setTimeout: (callback, milliseconds) => {
        timeouts.push(milliseconds);
        if (now !== null) {
          fakeNow += Math.max(milliseconds, 60000);
          callback();
        }
        return 1;
      },
      clearTimeout: () => {},
      addEventListener: () => {},
    },
    navigator: { clipboard: { writeText: async () => {} } },
    // The shell only reads through fetch while rendering; a pending promise
    // keeps the boot itself synchronous.
    fetch: (url, init) => {
      calls.push({ url: String(url), init: init || {} });
      return fetchImpl(url, init);
    },
  };
  for (const [name, value] of Object.entries(overrides)) {
    // ``navigator`` is a getter-only global on modern Node, so describe it.
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
    Object.defineProperty(globalThis, name, {
      value,
      configurable: true,
      writable: true,
    });
  }
  return {
    html,
    intervals,
    timeouts,
    calls,
    async flush() {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    },
    restore() {
      for (const [name, descriptor] of previous) {
        if (descriptor) Object.defineProperty(globalThis, name, descriptor);
        else delete globalThis[name];
      }
      Date.now = originalDateNow;
    },
  };
}

test("the Mesa shell boots and init() runs", async () => {
  const dir = mkdtempSync(join(tmpdir(), "mesa-boot-"));
  const file = join(dir, "app-under-test.mjs");
  const patched = source
    .replace('from "/pdf-viewer.js"', `from ${JSON.stringify(new URL("../pdf-viewer.js", import.meta.url).href)}`)
    .replace('from "/portal-current.js"', `from ${JSON.stringify(new URL("../portal-current.js", import.meta.url).href)}`);
  writeFileSync(file, patched, "utf8");

  const boot = withBootGlobals();
  try {
    await assert.doesNotReject(
      () => import(pathToFileURL(file).href),
      "the shell must evaluate and reach init()"
    );
    // init() registers the follow poller: proof the boot actually ran.
    assert.ok(boot.intervals.length >= 2, "init() must have registered its pollers");
  } finally {
    boot.restore();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("the Mesa boot refreshes diagnostics and binds its three controls", async () => {
  const dir = mkdtempSync(join(tmpdir(), "mesa-diagnostics-boot-"));
  const file = join(dir, "app-under-test.mjs");
  const patched = source
    .replace('from "/pdf-viewer.js"', `from ${JSON.stringify(new URL("../pdf-viewer.js", import.meta.url).href)}`)
    .replace('from "/portal-current.js"', `from ${JSON.stringify(new URL("../portal-current.js", import.meta.url).href)}`);
  writeFileSync(file, patched, "utf8");
  const boot = withBootGlobals({
    fetchImpl: async () => ({ ok: true, json: async () => ({ diagnostic_enabled: true, active: true }) }),
  });

  try {
    await import(pathToFileURL(file).href);
    const dashboardRefresh = boot.intervals.find(([, milliseconds]) => milliseconds === 5000);
    assert.ok(dashboardRefresh, "the existing five-second dashboard interval remains active");
    await dashboardRefresh[0]();
    await boot.flush();
    assert.ok(boot.calls.some(({ url }) => url === "/api/v1/diagnostics"));
    for (const id of ["diagnostics-toggle", "diagnostics-clear", "diagnostics-export"]) {
      assert.equal(typeof boot.html.getElementById(id).handlers.click, "function", `${id} is bound`);
    }
  } finally {
    boot.restore();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("diagnostic controls and command timeout use the local API and export filename", async () => {
  const dir = mkdtempSync(join(tmpdir(), "mesa-diagnostics-actions-"));
  const file = join(dir, "app-under-test.mjs");
  const patched = source
    .replace('from "/pdf-viewer.js"', `from ${JSON.stringify(new URL("../pdf-viewer.js", import.meta.url).href)}`)
    .replace('from "/portal-current.js"', `from ${JSON.stringify(new URL("../portal-current.js", import.meta.url).href)}`);
  writeFileSync(file, patched, "utf8");
  const calls = [];
  const filename = "diagnostico-atos-tce-20261006-120000.zip";
  const diag = {
    diagnostic_enabled: true,
    active: true,
    paused: false,
    mesa_state: "OK",
    extension_state: "STALE",
    portal_state: "NO_ACTIVE_FORM",
    heartbeat_age_ms: 7654,
    form_state: "NO_ACTIVE_FORM",
    form_code: "FORM_NOT_AVAILABLE",
    current_selection_state: "NO_ACTIVE_FORM",
    current_selection_code: "FORM_NOT_AVAILABLE",
    last_command_type: "FILL_FORM",
    last_result_code: "COMMAND_TIMEOUT",
    last_error_code: "COMMAND_TIMEOUT",
  };
  const jsonResponse = (payload) => ({ ok: true, status: 200, json: async () => payload });
  let fakeNow = 100000;
  const previousDateNow = Date.now;
  const previousUrl = Object.getOwnPropertyDescriptor(globalThis, "URL");
  Date.now = () => fakeNow;
  const urlCalls = [];
  globalThis.URL = Object.assign(function URL() {}, {
    createObjectURL: (blob) => {
      urlCalls.push(["create", blob]);
      return "blob:diagnostics";
    },
    revokeObjectURL: (value) => urlCalls.push(["revoke", value]),
  });
  const boot = withBootGlobals({
    now: fakeNow,
    fetchImpl: async (url, init = {}) => {
      const path = String(url);
      const method = (init.method || "GET").toUpperCase();
      calls.push({ path, method, body: init.body ? JSON.parse(init.body) : null });
      if (path === "/api/v1/diagnostics/export") {
        return {
          ok: true,
          status: 200,
          headers: { get: () => `attachment; filename="${filename}"` },
          blob: async () => "zip-bytes",
        };
      }
      if (path === "/api/v1/diagnostics/control") {
        const action = JSON.parse(init.body).action;
        diag.paused = action === "pause";
        diag.active = !diag.paused;
        return jsonResponse(diag);
      }
      if (path === "/api/v1/diagnostics/events") return jsonResponse({ recorded: true });
      if (path === "/api/v1/diagnostics") return jsonResponse(diag);
      if (path === "/api/v1/area/analyze" && method === "POST") return jsonResponse({ command_id: 77 });
      if (path === "/api/v1/extension/commands/77") return jsonResponse({ state: "RUNNING" });
      if (path === "/api/v1/processes") return jsonResponse({ items: [] });
      if (path === "/api/v1/acquisition/plan") return jsonResponse({ active_job: null });
      return jsonResponse({});
    },
  });

  try {
    await import(pathToFileURL(file).href);
    await boot.flush();
    assert.equal(boot.html.getElementById("diagnostics-extension").textContent, "STALE");
    assert.equal(boot.html.getElementById("diagnostics-heartbeat").textContent, "7.7 s");
    assert.equal(boot.html.getElementById("diagnostics-form-code").textContent, "FORM_NOT_AVAILABLE");
    assert.equal(boot.html.getElementById("diagnostics-error").textContent, "COMMAND_TIMEOUT");

    await boot.html.getElementById("diagnostics-toggle").click();
    await boot.html.getElementById("diagnostics-toggle").click();
    await boot.html.getElementById("diagnostics-clear").click();
    await boot.html.getElementById("diagnostics-export").click();
    assert.ok(boot.timeouts.includes(1000), "the ZIP object URL stays valid briefly after the download click");
    const analyze = boot.html.getElementById("analyze-area");
    await analyze.click();
    await boot.flush();

    assert.deepEqual(
      calls.filter(({ path }) => path === "/api/v1/diagnostics/control").map(({ body }) => body.action),
      ["pause", "resume", "clear"],
    );
    assert.ok(calls.some(({ path, body }) => path === "/api/v1/diagnostics/events" && body.event.code === "COMMAND_TIMEOUT"));
    const anchor = boot.html.created.find((node) => node.tagName === "A");
    assert.equal(anchor.download, filename);
    assert.equal(anchor.href, "blob:diagnostics");
    assert.deepEqual(urlCalls.map(([action]) => action), ["create", "revoke"]);
  } finally {
    boot.restore();
    Date.now = previousDateNow;
    if (previousUrl) Object.defineProperty(globalThis, "URL", previousUrl);
    else delete globalThis.URL;
    rmSync(dir, { recursive: true, force: true });
  }
});
