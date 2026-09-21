import test from "node:test";
import assert from "node:assert/strict";

import { createApi, STORAGE_KEYS } from "../lib/api.js";
import { fakeFetch, fakeStorage } from "./helpers.mjs";

const CLIENT_ID = "extension-test-client";

function build({ routes = [], data = new Map() } = {}) {
  const storage = fakeStorage();
  for (const [key, value] of data) storage.data.set(key, value);
  const fetchImpl = fakeFetch(routes);
  return {
    storage,
    fetchImpl,
    api: createApi({
      storage,
      fetchImpl,
      clientIdFactory: () => CLIENT_ID,
      baseUrl: "http://127.0.0.1:18743",
    }),
  };
}

test("pairing stores the token and the client id in extension storage", async () => {
  const { api, storage, fetchImpl } = build({
    routes: [{ path: "/api/v1/bridge/pair", method: "POST", body: { token: "token-123" } }],
  });

  const outcome = await api.pair("618900");

  assert.equal(outcome.ok, true);
  assert.equal(outcome.clientId, CLIENT_ID);
  assert.equal(storage.data.get(STORAGE_KEYS.token), "token-123");
  assert.equal(storage.data.get(STORAGE_KEYS.clientId), CLIENT_ID);
  const request = fetchImpl.calls.at(0);
  assert.equal(request.method, "POST");
  assert.equal(request.url, "http://127.0.0.1:18743/api/v1/bridge/pair");
  assert.deepEqual(JSON.parse(request.body), {
    client_id: CLIENT_ID,
    code: "618900",
    extension_id: null,
  });
});

test("a rejected pairing stores nothing", async () => {
  const { api, storage } = build({
    routes: [{ path: "/api/v1/bridge/pair", method: "POST", status: 401, body: { error: "pairing_rejected" } }],
  });

  const outcome = await api.pair("000000");

  assert.equal(outcome.ok, false);
  assert.equal(outcome.error, "pairing_rejected");
  assert.equal(storage.data.get(STORAGE_KEYS.token), undefined);
});

test("nextCommand sends the bearer token and the client header", async () => {
  const { api, fetchImpl } = build({
    data: new Map([
      [STORAGE_KEYS.clientId, CLIENT_ID],
      [STORAGE_KEYS.token, "token-123"],
    ]),
    routes: [
      {
        path: "/api/v1/extension/commands/next",
        body: { command: { id: 4, type: "SCAN_AREA", payload: {} } },
      },
    ],
  });

  const outcome = await api.nextCommand();

  assert.equal(outcome.ok, true);
  assert.equal(outcome.command.id, 4);
  const request = fetchImpl.calls.at(0);
  assert.equal(request.headers.Authorization, "Bearer token-123");
  assert.equal(request.headers["X-TCE-Client"], CLIENT_ID);
});

test("nextCommand reports not_paired without calling the Mesa", async () => {
  const { api, fetchImpl } = build();

  const outcome = await api.nextCommand();

  assert.equal(outcome.ok, false);
  assert.equal(outcome.error, "not_paired");
  assert.equal(outcome.command, null);
  assert.equal(fetchImpl.calls.length, 0);
});

test("an expired or invalid token surfaces as unauthorized", async () => {
  const { api } = build({
    data: new Map([
      [STORAGE_KEYS.clientId, CLIENT_ID],
      [STORAGE_KEYS.token, "velho"],
    ]),
    routes: [{ path: "/api/v1/extension/commands/next", status: 401, body: { error: "unauthorized" } }],
  });

  const outcome = await api.nextCommand();

  assert.equal(outcome.ok, false);
  assert.equal(outcome.status, 401);
  assert.equal(outcome.error, "unauthorized");
});

test("reportResult posts the sanitized result to the command route", async () => {
  const { api, fetchImpl } = build({
    data: new Map([
      [STORAGE_KEYS.clientId, CLIENT_ID],
      [STORAGE_KEYS.token, "token-123"],
    ]),
    routes: [{ path: "/api/v1/extension/commands/9/result", method: "POST", body: { ok: true } }],
  });

  const outcome = await api.reportResult(9, { command_id: 9, ok: true, rows: [] });

  assert.equal(outcome.ok, true);
  const request = fetchImpl.calls.at(0);
  assert.equal(request.url, "http://127.0.0.1:18743/api/v1/extension/commands/9/result");
  assert.deepEqual(JSON.parse(request.body), { command_id: 9, ok: true, rows: [] });
});

test("status reads the paired client without exposing the token", async () => {
  const { api } = build({
    data: new Map([
      [STORAGE_KEYS.clientId, CLIENT_ID],
      [STORAGE_KEYS.token, "token-123"],
    ]),
    routes: [
      {
        path: "/api/v1/bridge/status",
        body: { paired: true, client_id: CLIENT_ID, origin: "chrome-extension://abc" },
      },
    ],
  });

  const outcome = await api.status();

  assert.equal(outcome.ok, true);
  assert.equal(outcome.paired, true);
  assert.equal(outcome.payload.token, undefined);
});

test("status exposes an unauthorized response so the panel can recover the pairing", async () => {
  const { api } = build({
    data: new Map([
      [STORAGE_KEYS.clientId, CLIENT_ID],
      [STORAGE_KEYS.token, "velho"],
    ]),
    routes: [{ path: "/api/v1/bridge/status", status: 401, body: { error: "unauthorized" } }],
  });

  const outcome = await api.status();

  assert.equal(outcome.ok, false);
  assert.equal(outcome.status, 401);
  assert.equal(outcome.paired, false);
  assert.equal(outcome.error, "unauthorized");
});

test("a stored pairing can be cleared for a fresh code", async () => {
  const { api, storage } = build({
    data: new Map([
      [STORAGE_KEYS.clientId, CLIENT_ID],
      [STORAGE_KEYS.token, "token-123"],
    ]),
  });

  await api.clear();

  assert.equal(storage.data.get(STORAGE_KEYS.token), undefined);
  assert.equal(storage.data.get(STORAGE_KEYS.clientId), undefined);
});
