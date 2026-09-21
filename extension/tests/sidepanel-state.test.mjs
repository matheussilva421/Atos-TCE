import test from "node:test";
import assert from "node:assert/strict";

import { describeMesaStatus } from "../sidepanel/state.js";

test("connected status is simple", () => {
  const state = describeMesaStatus({ ok: true, status: 200, paired: true });

  assert.equal(state.label, "Mesa conectada");
  assert.equal(state.tone, "ok");
});

test("startup or recovery status says connecting", () => {
  const state = describeMesaStatus({ ok: false, status: 401, recovering: true });

  assert.equal(state.label, "Conectando à Mesa…");
  assert.equal(state.tone, "warn");
});

test("network failure says Mesa not found", () => {
  const state = describeMesaStatus({ ok: false, status: 0, error: "fetch_failed" });

  assert.equal(state.label, "Mesa não encontrada");
  assert.equal(state.tone, "error");
});
