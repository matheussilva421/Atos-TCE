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

test("the sidepanel offers next-process navigation after a form identity is known", () => {
  assert.match(page, /<button[^>]+id="next-process"[^>]+disabled[^>]*>Próximo processo →<\/button>/iu);
  assert.match(source, /MESSAGE_TYPES\.REQUEST_NEXT_ACT/u);
  assert.match(source, /lastConfirmedFormIdentity/u);
});

test("next-process feedback polls the accepted command result, not the active tab form", () => {
  const handler = source.slice(source.indexOf('document.getElementById("next-process").addEventListener'));
  const body = handler.slice(0, handler.indexOf('document.getElementById("open-mesa")'));

  assert.match(body, /pollForNextActCommand/u);
  assert.match(body, /MESSAGE_TYPES\.READ_NEXT_ACT_STATUS/u);
  assert.doesNotMatch(body, /MESSAGE_TYPES\.READ_CURRENT_FORM/u);
});

test("the sidepanel never includes a target identity in its request", () => {
  assert.match(source, /payload:\s*\{\s*identity:\s*lastConfirmedFormIdentity\s*\}/u);
  assert.doesNotMatch(source, /target_identity\s*:/u);
});

test("the sidepanel gates the operator UI with the capability status", () => {
  assert.match(source, /MESSAGE_TYPES\.RELIABILITY_STATUS/u);
  assert.match(source, /describeManualFillCapability/u);
  assert.match(source, /describeNextProcessCapability/u);
  assert.match(source, /nextButton\.disabled\s*=/u);
  assert.match(page, /id="capability-status"/u);
});

test("the sidepanel offers no hidden bypass for an unqualified capability", () => {
  assert.doesNotMatch(source, /bypass|forceEnabled|overrideQualification/iu);
});

test("the sidepanel reports a trial that found no form instead of hiding it", () => {
  assert.match(source, /MESSAGE_TYPES\.REPORT_AR1_ATTEMPT/u);
  assert.match(source, /lastFormReadCode/u);
  const start = source.indexOf('document.getElementById("fill-current").addEventListener');
  const end = source.indexOf('document.getElementById("next-process").addEventListener');
  assert.notEqual(start, -1, "the sidepanel owns the manual fill action");
  assert.notEqual(end, -1, "the fill action precedes next-process");
  const body = source.slice(start, end);

  assert.match(body, /MESSAGE_TYPES\.REPORT_AR1_ATTEMPT/u, "the miss is reported to the Mesa");
  assert.match(body, /lastFormReadCode/u, "the panel reports the code it actually saw");
});

test("a press is a trial, so the fill action is gated by capability only", () => {
  const start = source.indexOf("function updateActionButtons");
  const end = source.indexOf("function setNextActFeedback");
  const body = source.slice(start, end);

  assert.match(body, /fillButton\.disabled = !manualFill\.enabled/u);
  assert.doesNotMatch(body, /!currentFormAvailable/u, "a missing form must not hide the attempt");
});
