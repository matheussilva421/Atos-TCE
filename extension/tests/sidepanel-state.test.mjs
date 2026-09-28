import test from "node:test";
import assert from "node:assert/strict";

import {
  describeMesaStatus,
  describeNextActCommandStatus,
  describeNextActOutcome,
  hasFormIdentity,
  matchesFormIdentity,
  pollForTargetForm,
  pollForNextActCommand,
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

test("the confirmed identity retains a strong portal act id and may match a name alias", () => {
  const strongTarget = { ...TARGET_IDENTITY, portalActId: "act-fixture-42" };
  assert.deepEqual(
    retainLastConfirmedIdentity(null, { ok: true, form: { identity: strongTarget } }),
    strongTarget,
  );
  assert.equal(
    matchesFormIdentity(
      { ...strongTarget, interestedNormalized: "pessoa apelido" },
      strongTarget,
    ),
    true,
  );
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
    { state: "opening", commandId: 9, targetIdentity: TARGET_IDENTITY },
  );
});

test("an accepted next-process response retains its portal act id", () => {
  const outcome = describeNextActOutcome({
    ok: true,
    payload: {
      command_id: 9,
      target_identity: { ...TARGET_IDENTITY, portalActId: "act-fixture-42" },
    },
  });
  assert.equal(outcome.targetIdentity.portalActId, "act-fixture-42");
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

test("next-act status accepts success only from the terminal command result", () => {
  const states = [
    { ok: true, command: { state: "CLAIMED" } },
    {
      ok: true,
      command: {
        state: "SUCCEEDED",
        result: { ok: true, action: "next_act_ready", screen: "form", identity: TARGET_IDENTITY },
      },
    },
  ];
  assert.deepEqual(
    states.map((status) => describeNextActCommandStatus(status, TARGET_IDENTITY).state),
    ["pending", "ready"],
  );
});

test("next-act status preserves the command's terminal refusal code", () => {
  assert.deepEqual(
    describeNextActCommandStatus(
      {
        ok: true,
        command: {
          state: "FAILED",
          error: "TARGET_NOT_FOUND",
          result: { ok: false, code: "TARGET_NOT_FOUND", error: "target row not found" },
        },
      },
      TARGET_IDENTITY,
    ),
    { state: "error", code: "TARGET_NOT_FOUND", message: "target row not found" },
  );
});

test("a terminal status lookup refusal is surfaced without waiting for timeout", () => {
  assert.deepEqual(
    describeNextActCommandStatus(
      { ok: false, status: 404, error: "command_not_found" },
      TARGET_IDENTITY,
    ),
    { state: "error", code: "command_not_found", message: "command_not_found" },
  );
});

test("a terminal success for another identity is rejected", () => {
  const outcome = describeNextActCommandStatus(
    {
      ok: true,
      command: {
        state: "SUCCEEDED",
        result: {
          ok: true,
          action: "next_act_ready",
          screen: "form",
          identity: { ...TARGET_IDENTITY, processKey: "other/2026" },
        },
      },
    },
    TARGET_IDENTITY,
  );
  assert.deepEqual(outcome, { state: "error", code: "TARGET_IDENTITY_MISMATCH", message: "TARGET_IDENTITY_MISMATCH" });
});

test("next-act polling reads only the command status until its result is terminal", async () => {
  const responses = [
    { ok: true, command: { state: "QUEUED" } },
    {
      ok: true,
      command: {
        state: "SUCCEEDED",
        result: { ok: true, action: "next_act_ready", screen: "form", identity: TARGET_IDENTITY },
      },
    },
  ];
  const calls = [];
  const waits = [];
  const result = await pollForNextActCommand({
    readCommandStatus: async (commandId) => {
      calls.push(commandId);
      return responses.shift();
    },
    commandId: 17,
    targetIdentity: TARGET_IDENTITY,
    intervalMs: 200,
    sleep: async (ms) => waits.push(ms),
  });
  assert.equal(result.state, "ready");
  assert.deepEqual(calls, [17, 17]);
  assert.deepEqual(waits, [200]);
});
