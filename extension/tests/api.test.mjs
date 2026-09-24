import test from "node:test";
import assert from "node:assert/strict";

import { createApi, STORAGE_KEYS } from "../lib/api.js";
import { fakeFetch, fakeStorage } from "./helpers.mjs";

const CLIENT_ID = "extension-test-client";
const EXTENSION_ID = "nhpklhieopdbomkojifcengjaklabjng";

function build({ routes = [], data = new Map(), storage = fakeStorage() } = {}) {
  for (const [key, value] of data) storage.data.set(key, value);
  const fetchImpl = fakeFetch(routes);
  const api = createApi({
    storage,
    fetchImpl,
    clientIdFactory: () => CLIENT_ID,
    baseUrl: "http://127.0.0.1:18743",
    extensionId: EXTENSION_ID,
  });
  return { api, storage, fetchImpl };
}

function pairedData(token = "token-123") {
  return new Map([
    [STORAGE_KEYS.clientId, CLIENT_ID],
    [STORAGE_KEYS.token, token],
  ]);
}

test("empty storage automatically registers before status", async () => {
  const { api, storage, fetchImpl } = build({
    routes: [
      {
        path: "/api/v1/bridge/register",
        method: "POST",
        body: { token: "fresh-token", client_id: CLIENT_ID },
      },
      {
        path: "/api/v1/bridge/status",
        body: { paired: true, client_id: CLIENT_ID },
      },
    ],
  });

  const outcome = await api.status();

  assert.equal(outcome.ok, true);
  assert.equal(outcome.paired, true);
  assert.equal(storage.data.get(STORAGE_KEYS.token), "fresh-token");
  assert.equal(fetchImpl.calls[0].url.endsWith("/api/v1/bridge/register"), true);
  assert.deepEqual(JSON.parse(fetchImpl.calls[0].body), { client_id: CLIENT_ID });
  assert.equal(fetchImpl.calls[0].headers.Authorization, undefined);
  assert.equal(fetchImpl.calls[1].headers.Authorization, "Bearer fresh-token");
});

test("a valid stored credential is used without registration", async () => {
  const { api, fetchImpl } = build({
    data: pairedData(),
    routes: [{ path: "/api/v1/bridge/status", body: { paired: true } }],
  });

  const outcome = await api.status();

  assert.equal(outcome.ok, true);
  assert.equal(fetchImpl.calls.length, 1);
  assert.equal(fetchImpl.calls[0].headers.Authorization, "Bearer token-123");
  assert.equal(fetchImpl.calls[0].headers["X-TCE-Client"], CLIENT_ID);
});

test("authenticated requests identify the MV3 extension for service-worker fetches", async () => {
  const { api, fetchImpl } = build({
    data: pairedData(),
    routes: [{ path: "/api/v1/bridge/status", body: { paired: true } }],
  });

  await api.status();

  assert.equal(fetchImpl.calls[0].headers["X-TCE-Extension-ID"], EXTENSION_ID);
});

test("401 automatically registers and retries exactly once", async () => {
  let statusCalls = 0;
  const { api, fetchImpl } = build({
    data: pairedData("stale-token"),
    routes: [
      {
        path: "/api/v1/bridge/status",
        body: () => {
          statusCalls += 1;
          return statusCalls === 1
            ? { status: 401, body: { error: "unauthorized" } }
            : { status: 200, body: { paired: true, client_id: CLIENT_ID } };
        },
      },
      {
        path: "/api/v1/bridge/register",
        method: "POST",
        body: { token: "fresh-token", client_id: CLIENT_ID },
      },
    ],
  });

  const outcome = await api.status();

  assert.equal(outcome.ok, true);
  assert.equal(statusCalls, 2);
  assert.equal(
    fetchImpl.calls.filter((call) => call.url.endsWith("/api/v1/bridge/register")).length,
    1,
  );
  assert.equal(fetchImpl.calls.at(-1).headers.Authorization, "Bearer fresh-token");
});

test("a second 401 after recovery stops without looping", async () => {
  let statusCalls = 0;
  const { api, fetchImpl } = build({
    data: pairedData("stale-token"),
    routes: [
      {
        path: "/api/v1/bridge/status",
        body: () => {
          statusCalls += 1;
          return { status: 401, body: { error: "unauthorized" } };
        },
      },
      {
        path: "/api/v1/bridge/register",
        method: "POST",
        body: { token: "still-rejected", client_id: CLIENT_ID },
      },
    ],
  });

  const outcome = await api.status();

  assert.equal(outcome.ok, false);
  assert.equal(outcome.status, 401);
  assert.equal(outcome.error, "unauthorized");
  assert.equal(statusCalls, 2);
  assert.equal(
    fetchImpl.calls.filter((call) => call.url.endsWith("/api/v1/bridge/register")).length,
    1,
  );
});

test("Mesa offline leaves stored credentials untouched", async () => {
  const { api, storage } = build({
    data: pairedData("still-valid-locally"),
    routes: [
      {
        path: "/api/v1/bridge/status",
        body: () => {
          throw new Error("connect ECONNREFUSED");
        },
      },
    ],
  });

  const outcome = await api.status();

  assert.equal(outcome.ok, false);
  assert.equal(outcome.status, 0);
  assert.equal(outcome.error, "fetch_failed");
  assert.equal(storage.data.get(STORAGE_KEYS.token), "still-valid-locally");
  assert.equal(storage.data.get(STORAGE_KEYS.clientId), CLIENT_ID);
});

test("a token changed after 401 is retried before registration", async () => {
  const storage = fakeStorage();
  storage.data.set(STORAGE_KEYS.clientId, CLIENT_ID);
  storage.data.set(STORAGE_KEYS.token, "token-old");
  let statusCalls = 0;
  const { api, fetchImpl } = build({
    storage,
    routes: [
      {
        path: "/api/v1/bridge/status",
        body: (request) => {
          statusCalls += 1;
          if (statusCalls === 1) {
            storage.data.set(STORAGE_KEYS.token, "token-new");
            return { status: 401, body: { error: "unauthorized" } };
          }
          return {
            status: request.headers.Authorization === "Bearer token-new" ? 200 : 401,
            body: { paired: request.headers.Authorization === "Bearer token-new" },
          };
        },
      },
      {
        path: "/api/v1/bridge/register",
        method: "POST",
        body: { token: "should-not-be-used", client_id: CLIENT_ID },
      },
    ],
  });

  const outcome = await api.status();

  assert.equal(outcome.ok, true);
  assert.equal(statusCalls, 2);
  assert.equal(fetchImpl.calls.some((call) => call.url.endsWith("/register")), false);
  assert.equal(fetchImpl.calls.at(-1).headers.Authorization, "Bearer token-new");
});

test("separate API instances read the newest shared storage credential", async () => {
  const storage = fakeStorage();
  storage.data.set(STORAGE_KEYS.clientId, CLIENT_ID);
  storage.data.set(STORAGE_KEYS.token, "token-old");
  const sharedFetch = fakeFetch([{ path: "/api/v1/bridge/status", body: { paired: true } }]);
  const options = {
    storage,
    fetchImpl: sharedFetch,
    clientIdFactory: () => CLIENT_ID,
    baseUrl: "http://127.0.0.1:18743",
  };
  const firstApi = createApi(options);
  const secondApi = createApi(options);

  await firstApi.status();
  storage.data.set(STORAGE_KEYS.token, "token-new");
  await secondApi.status();
  await firstApi.status();

  assert.deepEqual(
    sharedFetch.calls.map((call) => call.headers.Authorization),
    ["Bearer token-old", "Bearer token-new", "Bearer token-new"],
  );
});

test("two simultaneous operations share one registration promise", async () => {
  let registrations = 0;
  const { api, fetchImpl } = build({
    routes: [
      {
        path: "/api/v1/bridge/register",
        method: "POST",
        body: async () => {
          registrations += 1;
          await new Promise((resolve) => setTimeout(resolve, 10));
          return { token: "shared-token", client_id: CLIENT_ID };
        },
      },
      { path: "/api/v1/bridge/status", body: { paired: true } },
      { path: "/api/v1/extension/commands/next", body: { command: null } },
    ],
  });

  const [status, command] = await Promise.all([api.status(), api.nextCommand()]);

  assert.equal(status.ok, true);
  assert.equal(command.ok, true);
  assert.equal(registrations, 1);
  assert.equal(
    fetchImpl.calls.filter((call) => call.url.endsWith("/api/v1/bridge/register")).length,
    1,
  );
});

test("nextCommand sends the bearer token and client header", async () => {
  const { api, fetchImpl } = build({
    data: pairedData(),
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
  assert.equal(fetchImpl.calls[0].headers.Authorization, "Bearer token-123");
  assert.equal(fetchImpl.calls[0].headers["X-TCE-Client"], CLIENT_ID);
});

test("reportResult posts the result through the authenticated request", async () => {
  const { api, fetchImpl } = build({
    data: pairedData(),
    routes: [{ path: "/api/v1/extension/commands/9/result", method: "POST", body: { ok: true } }],
  });

  const outcome = await api.reportResult(9, { command_id: 9, ok: true, rows: [] });

  assert.equal(outcome.ok, true);
  assert.equal(fetchImpl.calls[0].url, "http://127.0.0.1:18743/api/v1/extension/commands/9/result");
  assert.deepEqual(JSON.parse(fetchImpl.calls[0].body), { command_id: 9, ok: true, rows: [] });
});

test("renewCommandLease posts the current claim token through the authenticated request", async () => {
  const { api, fetchImpl } = build({
    data: pairedData(),
    routes: [{ path: "/api/v1/extension/commands/9/lease", method: "POST", body: { ok: true } }],
  });

  const outcome = await api.renewCommandLease(9, "claim-token");

  assert.equal(outcome.ok, true);
  assert.equal(fetchImpl.calls[0].url, "http://127.0.0.1:18743/api/v1/extension/commands/9/lease");
  assert.deepEqual(JSON.parse(fetchImpl.calls[0].body), { claim_token: "claim-token" });
  assert.equal(fetchImpl.calls[0].headers.Authorization, "Bearer token-123");
  assert.equal(fetchImpl.calls[0].headers["X-TCE-Client"], CLIENT_ID);
});

test("manual fill uses the authenticated request", async () => {
  const { api, fetchImpl } = build({
    data: pairedData(),
    routes: [{ path: "/api/v1/portal/manual-form", method: "POST", body: { state: "READY" } }],
  });
  const form = { identity: { processKey: "102390/2026" } };

  const outcome = await api.requestManualFill(form);

  assert.equal(outcome.ok, true);
  assert.deepEqual(outcome.payload, { state: "READY" });
  assert.equal(fetchImpl.calls[0].headers.Authorization, "Bearer token-123");
});

test("the public API has no manual pairing or credential clearing methods", () => {
  const { api } = build();

  assert.equal(api.pair, undefined);
  assert.equal(api.clear, undefined);
  assert.equal(api.credentials, undefined);
});
