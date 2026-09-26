import test from "node:test";
import assert from "node:assert/strict";

import {
  describeMesaStatus,
  describeNextActOutcome,
  hasFormIdentity,
  pollForTargetForm,
  retainLastConfirmedIdentity,
} from "../sidepanel/state.js";

const CURRENT_IDENTITY = {
  processKey: "current/2026",
  interestedNormalized: "pessoa atual",
};
const TARGET_IDENTITY = {
  processKey: "next/2026",
  interestedNormalized: "pessoa seguinte",
};

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

test("a confirmed form identity enables next-process navigation", () => {
  assert.equal(hasFormIdentity(null), false);
  assert.equal(hasFormIdentity(CURRENT_IDENTITY), true);
});

test("reading a current form remembers only its exact composed identity", () => {
  const remembered = retainLastConfirmedIdentity(null, {
    ok: true,
    form: { identity: { ...CURRENT_IDENTITY, extra: "discarded" } },
  });

  assert.deepEqual(remembered, CURRENT_IDENTITY);
});

test("a temporarily missing form does not erase the last confirmed identity", () => {
  const remembered = retainLastConfirmedIdentity(CURRENT_IDENTITY, {
    ok: true,
    form: null,
  });

  assert.equal(remembered, CURRENT_IDENTITY);
});

test("an end-of-queue response renders the explicit queue state", () => {
  assert.deepEqual(
    describeNextActOutcome({ ok: true, payload: { ok: true, end_of_queue: true } }),
    { state: "end_of_queue", message: "Fim da fila" },
  );
});

test("an accepted next-process response exposes the Mesa-selected target", () => {
  assert.deepEqual(
    describeNextActOutcome({
      ok: true,
      payload: { ok: true, command_id: 9, target_identity: TARGET_IDENTITY },
    }),
    { state: "opening", targetIdentity: TARGET_IDENTITY },
  );
});

test("target polling waits for an exact process and interested-person match", async () => {
  const reads = [
    { ok: true, form: null },
    { ok: true, form: { identity: { ...TARGET_IDENTITY, interestedNormalized: "outra pessoa" } } },
    { ok: true, form: { identity: TARGET_IDENTITY } },
  ];
  const delays = [];
  const result = await pollForTargetForm({
    readCurrentForm: async () => reads.shift(),
    targetIdentity: TARGET_IDENTITY,
    maxAttempts: 3,
    intervalMs: 250,
    sleep: async (milliseconds) => delays.push(milliseconds),
  });

  assert.deepEqual(result, { identity: TARGET_IDENTITY });
  assert.deepEqual(delays, [250, 250, 250]);
});
