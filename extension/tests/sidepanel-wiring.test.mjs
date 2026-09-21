import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const extensionRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const page = readFileSync(join(extensionRoot, "sidepanel/panel.html"), "utf8");
const source = readFileSync(join(extensionRoot, "sidepanel/panel.js"), "utf8");

test("the sidepanel has no manual pairing controls", () => {
  for (const forbidden of ["pair-code", "pair-action", "pair-section", "Parear", "Reparear", "pairing"]) {
    assert.doesNotMatch(page, new RegExp(forbidden, "iu"), forbidden);
    assert.doesNotMatch(source, new RegExp(forbidden, "iu"), forbidden);
  }
});

test("the sidepanel delegates Mesa operations to the service worker", () => {
  assert.doesNotMatch(source, /createApi/u);
  assert.doesNotMatch(source, /api\.(status|requestManualFill|pair|clear)/u);
  assert.match(source, /MESSAGE_TYPES\.MESA_STATUS/u);
  assert.match(source, /MESSAGE_TYPES\.REQUEST_MANUAL_FILL/u);
});
