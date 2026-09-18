import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  COMMAND_TYPES,
  FORBIDDEN_COMMAND_TYPES,
  HEARTBEAT_INTERVAL_MS,
  MESSAGE_TYPES,
  MESA_ORIGIN,
  PORTAL_ORIGIN,
  isPortalUrl,
  isSupportedCommand,
} from "../lib/protocol.js";

const here = dirname(fileURLToPath(import.meta.url));
const extensionRoot = join(here, "..");

test("M2 supports exactly STATUS and SCAN_AREA", () => {
  assert.deepEqual(Object.values(COMMAND_TYPES).sort(), ["SCAN_AREA", "STATUS"]);
  assert.ok(isSupportedCommand("SCAN_AREA"));
  assert.ok(isSupportedCommand("scan_area"));
  assert.ok(isSupportedCommand("STATUS"));
  assert.equal(isSupportedCommand("OPEN_ACT"), false);
  assert.equal(isSupportedCommand(""), false);
  assert.equal(isSupportedCommand(undefined), false);
});

test("the protocol has no way to finish an act", () => {
  const declared = new Set([...Object.values(COMMAND_TYPES), ...Object.values(MESSAGE_TYPES)]);
  for (const forbidden of FORBIDDEN_COMMAND_TYPES) {
    assert.equal(declared.has(forbidden), false, `${forbidden} must not exist`);
  }
});

test("no shipped source declares a submit command or clicks a final action", () => {
  // lib/protocol.js is excluded because it *names* these types inside
  // FORBIDDEN_COMMAND_TYPES precisely so the absence can be asserted above;
  // it declares no command of its own.
  const files = [
    "lib/api.js",
    "background/router.js",
    "content/scan-area.js",
    "content/paging.js",
    "content/heartbeat.js",
    "sidepanel/panel.js",
  ];
  for (const relative of files) {
    const source = readFileSync(join(extensionRoot, relative), "utf8");
    for (const forbidden of ["AUTO_SUBMIT", "COMPLEMENT_ACT", "autoSubmit", "real_send"]) {
      assert.equal(source.includes(forbidden), false, `${relative} mentions ${forbidden}`);
    }
  }
});

test("only the Área Restrita host and the loopback Mesa are addressed", () => {
  assert.equal(isPortalUrl(`${PORTAL_ORIGIN}/processonosetor.asp`), true);
  assert.equal(isPortalUrl("https://econtas.tce.rn.gov.br/qualquer"), false);
  assert.equal(isPortalUrl("https://evil.example.com/"), false);
  assert.match(MESA_ORIGIN, /^http:\/\/127\.0\.0\.1:/u);
});

test("the manifest requests no e-Contas access and no scripting permission", () => {
  const manifest = JSON.parse(readFileSync(join(extensionRoot, "manifest.json"), "utf8"));

  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual([...manifest.permissions].sort(), ["alarms", "sidePanel", "storage"]);
  assert.equal(JSON.stringify(manifest).includes("econtas"), false);
  assert.equal(JSON.stringify(manifest).includes("<all_urls>"), false);
  assert.deepEqual(manifest.host_permissions, [
    "https://novaarearestrita.tce.rn.gov.br/*",
    "http://127.0.0.1/*",
  ]);
  assert.equal(manifest.content_scripts[0].matches.length, 1);
  assert.equal(manifest.content_scripts[0].matches[0].includes("novaarearestrita"), true);
});

test("the heartbeat interval matches the protocol constant", () => {
  const source = readFileSync(join(extensionRoot, "content/heartbeat.js"), "utf8");
  const match = source.match(HEARTBEAT_RE);
  assert.ok(match, "heartbeat.js must declare its interval");
  assert.equal(Number(match[1]), HEARTBEAT_INTERVAL_MS);
});

const HEARTBEAT_RE = /INTERVAL_MS\s*=\s*(\d+)/u;
