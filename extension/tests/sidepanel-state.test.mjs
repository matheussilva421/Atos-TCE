import test from "node:test";
import assert from "node:assert/strict";

import { describeMesaStatus } from "../sidepanel/state.js";

test("an unauthorized Mesa status requests a fresh pairing in this profile", () => {
  const state = describeMesaStatus({ ok: false, status: 401, error: "unauthorized" });

  assert.equal(state.paired, false);
  assert.equal(state.stale, true);
  assert.equal(state.tone, "error");
  assert.equal(state.label, "Mesa: pareamento deste perfil recusado");
  assert.match(state.diagnostic, /Reparear extensão/);
});

test("a connected Mesa status keeps the panel ready", () => {
  const state = describeMesaStatus({ ok: true, status: 200, paired: true });

  assert.equal(state.paired, true);
  assert.equal(state.stale, false);
  assert.equal(state.label, "Mesa conectada");
});
