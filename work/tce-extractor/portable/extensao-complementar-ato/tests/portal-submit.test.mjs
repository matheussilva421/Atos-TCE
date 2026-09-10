import test from "node:test";
import assert from "node:assert/strict";

import {
  classifyPortalOutcome,
  installPortalSubmit,
  submitVerifiedAct,
  waitForPortalOutcome,
} from "../content/portal-submit.js";

const IDENTITY = {
  processKey: "103439/2023",
  interestedNormalized: "ana da silva",
  portalActId: "act-1",
};

function command(overrides = {}) {
  return {
    command_id: "command-1",
    state: "issued",
    issued_at: 1_000,
    expires_at: 16_000,
    frame_id: 12,
    generation: 3,
    identity: IDENTITY,
    expected_fields_hash: "a".repeat(64),
    ...overrides,
  };
}

function button({ id = "submit-1", text = "Complementar Ato", disabled = false } = {}) {
  return {
    id,
    disabled,
    hidden: false,
    textContent: text,
    clickCount: 0,
    click() { this.clickCount += 1; },
  };
}

function documentWith(...buttons) {
  return {
    querySelectorAll() { return buttons; },
  };
}

function state(overrides = {}) {
  return {
    ok: true,
    visible: true,
    paused: false,
    frame_id: 12,
    generation: 3,
    identity: IDENTITY,
    fields_hash: "a".repeat(64),
    ...overrides,
  };
}

test("classifies only an accepted signal with matching post-read as confirmed", () => {
  assert.deepEqual(
    classifyPortalOutcome({
      accepted: true,
      persisted: true,
      identity: IDENTITY,
      evidence: { signal: "portal-accepted", read: "post-read" },
    }, { identity: IDENTITY }),
    {
      status: "confirmed",
      evidence: { signal: "portal-accepted", read: "post-read" },
    },
  );
  assert.equal(classifyPortalOutcome({ accepted: true, persisted: true, identity: { ...IDENTITY, portalActId: "other" } }, { identity: IDENTITY }).status, "unconfirmed");
  assert.equal(classifyPortalOutcome({ rejected: true, reason: "validation" }, { identity: IDENTITY }).status, "failed");
  assert.equal(classifyPortalOutcome({ timeout: true }, { identity: IDENTITY }).status, "unconfirmed");
});

test("waits for an observed outcome and unsubscribes before the deadline", async () => {
  let timerCallback;
  let cleared = null;
  let unsubscribeCount = 0;
  const promise = waitForPortalOutcome({
    timeoutMs: 30_000,
    setTimeoutFn: (callback) => { timerCallback = callback; return 9; },
    clearTimeoutFn: (handle) => { cleared = handle; },
    subscribe: (notify) => {
      notify({ accepted: true, persisted: true, identity: IDENTITY });
      return () => { unsubscribeCount += 1; };
    },
  });

  const result = await promise;
  assert.equal(result.accepted, true);
  assert.equal(cleared, 9);
  assert.equal(unsubscribeCount, 1);
  assert.equal(timerCallback !== undefined, true);
});

test("performs one final read at 30 seconds and returns timeout when it has no proof", async () => {
  let timerCallback;
  let readCount = 0;
  const promise = waitForPortalOutcome({
    timeoutMs: 30_000,
    setTimeoutFn: (callback) => { timerCallback = callback; return 10; },
    clearTimeoutFn: () => {},
    readOutcome: async () => { readCount += 1; return null; },
  });
  await timerCallback();
  const result = await promise;
  assert.deepEqual(result, { timeout: true });
  assert.equal(readCount, 1);
});

test("consumes an issued command once and clicks only the exact enabled button", async () => {
  const target = button();
  const phases = [];
  const result = await submitVerifiedAct({
    documentRef: documentWith(target),
    command: command(),
    now: () => 2_000,
    verifyCurrentState: async (phase) => { phases.push(phase); return state(); },
    consumeCommand: async (commandId) => ({ dispatch_allowed: commandId === "command-1" }),
    waitForOutcome: async () => ({ accepted: true, persisted: true, identity: IDENTITY, evidence: { signal: "accepted" } }),
  });

  assert.equal(result.dispatched, true);
  assert.equal(result.status, "confirmed");
  assert.equal(target.clickCount, 1);
  assert.deepEqual(phases, ["before_consume", "before_click"]);
});

test("does not consume or click on duplicate, expired, paused, wrong-frame, or ambiguous buttons", async () => {
  const cases = [
    { name: "expired", cmd: command({ expires_at: 1_999 }) },
    { name: "paused", cmd: command(), current: state({ paused: true }) },
    { name: "wrong frame", cmd: command({ frame_id: 99 }) },
    { name: "duplicate button", cmd: command(), buttons: [button({ id: "same" }), button({ id: "same" })] },
    { name: "wrong text", cmd: command(), buttons: [button({ text: "Salvar" })] },
  ];

  for (const item of cases) {
    const buttons = item.buttons ?? [button()];
    let consumed = 0;
    await assert.rejects(
      submitVerifiedAct({
        documentRef: documentWith(...buttons),
        command: item.cmd,
        now: () => 2_000,
        verifyCurrentState: async () => item.current ?? state(),
        consumeCommand: async () => { consumed += 1; return { dispatch_allowed: true }; },
      }),
      (error) => error.code === "SUBMIT_BLOCKED" || error.code === "COMMAND_ALREADY_CONSUMED",
      item.name,
    );
    assert.equal(consumed, 0, item.name);
    assert.equal(buttons.every((candidate) => candidate.clickCount === 0), true, item.name);
  }
});

test("an already consumed command never authorizes a second click", async () => {
  const target = button();
  let consumed = 0;
  await assert.rejects(
    submitVerifiedAct({
      documentRef: documentWith(target),
      command: command(),
      now: () => 2_000,
      verifyCurrentState: async () => state(),
      consumeCommand: async () => { consumed += 1; return { dispatch_allowed: false, error: "COMMAND_ALREADY_CONSUMED" }; },
    }),
    (error) => error.code === "COMMAND_ALREADY_CONSUMED",
  );
  assert.equal(consumed, 1);
  assert.equal(target.clickCount, 0);
});

test("a failure after consumption is uncertain and is never retried automatically", async () => {
  const target = button();
  let clicks = 0;
  const result = await submitVerifiedAct({
    documentRef: documentWith(target),
    command: command(),
    now: () => 2_000,
    verifyCurrentState: async (phase) => phase === "before_click" ? state({ ok: false, reason: "identity changed" }) : state(),
    consumeCommand: async () => ({ dispatch_allowed: true }),
    click: async () => { clicks += 1; },
  });
  assert.equal(result.dispatched, false);
  assert.equal(result.status, "unconfirmed");
  assert.equal(clicks, 0);
  assert.equal(target.clickCount, 0);
});

test("installs a typed button-frame listener that consumes before the single click", async () => {
  const target = button();
  let listener;
  const sent = [];
  const runtime = {
    onMessage: { addListener(handler) { listener = handler; } },
    async sendMessage(message) {
      sent.push(message);
      return { ok: true, payload: { dispatch_allowed: true, command_id: "command-1" } };
    },
  };
  const result = installPortalSubmit({
    documentRef: documentWith(target),
    chromeApi: { runtime },
    readCurrentState: async () => state(),
    waitForOutcome: async () => ({ accepted: true, persisted: true, identity: IDENTITY }),
    now: () => 2_000,
  });

  assert.equal(result.registered, true);
  const response = await new Promise((resolve) => {
    listener({
      schemaVersion: 1,
      type: "AUTO_SUBMIT_COMMAND",
      requestId: "submit-request-1",
      payload: { runId: "run-1", expectedRevision: 4, command: command() },
    }, {}, resolve);
  });

  assert.equal(response.ok, true);
  assert.equal(response.payload.status, "confirmed");
  assert.equal(target.clickCount, 1);
  assert.equal(sent[0].type, "AUTO_CONSUME_COMMAND");
  assert.equal(sent[0].payload.commandId, "command-1");
  assert.equal(sent[0].payload.expectedRevision, 4);
});

test("blocks the production listener before consuming or clicking when no outcome observer exists", async () => {
  const target = button();
  let listener;
  let consumed = 0;
  const result = installPortalSubmit({
    documentRef: documentWith(target),
    chromeApi: {
      runtime: {
        onMessage: { addListener(handler) { listener = handler; } },
        async sendMessage() { consumed += 1; return { ok: true, payload: { dispatch_allowed: true } }; },
      },
    },
    readCurrentState: async () => state(),
    now: () => 2_000,
  });

  assert.equal(result.registered, true);
  const response = await new Promise((resolve) => {
    listener({
      schemaVersion: 1,
      type: "AUTO_SUBMIT_COMMAND",
      requestId: "submit-no-observer",
      payload: { runId: "run-1", expectedRevision: 4, command: command() },
    }, {}, resolve);
  });

  assert.equal(response.ok, false);
  assert.equal(response.error.code, "OUTCOME_OBSERVER_UNAVAILABLE");
  assert.equal(consumed, 0);
  assert.equal(target.clickCount, 0);
});
