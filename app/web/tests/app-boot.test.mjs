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
  const make = () => {
    const node = {
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
      append(...nodes) {
        node.children.push(...nodes);
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
  return {
    readyState: "complete",
    getElementById(id) {
      if (!byId.has(id)) byId.set(id, make());
      return byId.get(id);
    },
    createElement() {
      return make();
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
}

function withBootGlobals() {
  const html = stubDocument();
  const intervals = [];
  const previous = new Map();
  const overrides = {
    document: html,
    window: {
      setInterval: (...args) => {
        intervals.push(args);
        return 1;
      },
      setTimeout: () => 1,
      clearTimeout: () => {},
      addEventListener: () => {},
    },
    navigator: { clipboard: { writeText: async () => {} } },
    // The shell only reads through fetch while rendering; a pending promise
    // keeps the boot itself synchronous.
    fetch: () => new Promise(() => {}),
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
    restore() {
      for (const [name, descriptor] of previous) {
        if (descriptor) Object.defineProperty(globalThis, name, descriptor);
        else delete globalThis[name];
      }
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
