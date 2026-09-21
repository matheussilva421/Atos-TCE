/**
 * Storage-authoritative Mesa client used by the extension service worker.
 *
 * chrome.storage.local is the only credential source. The token is attached
 * to authenticated requests, returned only by the registration response and
 * never logged or persisted by the Mesa in plaintext.
 */

import { MESA_ORIGIN } from "./protocol.js";

export const STORAGE_KEYS = Object.freeze({
  clientId: "tce.bridge.clientId",
  token: "tce.bridge.token",
  baseUrl: "tce.bridge.baseUrl",
});

export function createClientId() {
  const cryptoRef = globalThis.crypto;
  if (cryptoRef?.randomUUID) return cryptoRef.randomUUID();
  const bytes = new Uint8Array(16);
  if (cryptoRef?.getRandomValues) cryptoRef.getRandomValues(bytes);
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

/**
 * @param {object} options
 * @param {object} options.storage ``chrome.storage.local`` (or a double).
 * @param {Function} [options.fetchImpl] Injectable for tests.
 * @param {string} [options.baseUrl] Loopback Mesa origin.
 * @param {Function} [options.clientIdFactory]
 */
export function createApi({
  storage,
  fetchImpl = globalThis.fetch,
  baseUrl = MESA_ORIGIN,
  clientIdFactory = createClientId,
} = {}) {
  let registrationInFlight = null;

  async function readStoredState() {
    const stored = (await storage?.get?.(Object.values(STORAGE_KEYS))) ?? {};
    return {
      clientId: stored[STORAGE_KEYS.clientId] ?? null,
      token: stored[STORAGE_KEYS.token] ?? null,
      baseUrl: stored[STORAGE_KEYS.baseUrl] ?? baseUrl,
    };
  }

  async function saveCredentials({ clientId, token, baseUrl: currentBaseUrl }) {
    const credentials = {
      clientId,
      token,
      baseUrl: currentBaseUrl,
    };
    await storage?.set?.({
      [STORAGE_KEYS.clientId]: credentials.clientId,
      [STORAGE_KEYS.token]: credentials.token,
      [STORAGE_KEYS.baseUrl]: credentials.baseUrl,
    });
    return credentials;
  }

  async function request(
    path,
    { method = "GET", body, token, clientId, currentBaseUrl = baseUrl } = {},
  ) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;
    if (clientId) headers["X-TCE-Client"] = clientId;

    let response;
    try {
      response = await fetchImpl(`${currentBaseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      return { ok: false, status: 0, payload: null, error: "fetch_failed" };
    }

    let text;
    try {
      text = await response.text();
    } catch {
      text = "";
    }
    let payload = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = null;
    }
    return {
      ok: response.ok === true,
      status: response.status,
      payload,
      error: response.ok ? null : payload?.error ?? "request_failed",
    };
  }

  function sameCredentials(left, right) {
    return left.clientId === right.clientId && left.token === right.token;
  }

  async function register() {
    if (registrationInFlight) return registrationInFlight;

    const operation = (async () => {
      const before = await readStoredState();
      const clientId = before.clientId || clientIdFactory();
      const response = await request("/api/v1/bridge/register", {
        method: "POST",
        body: { client_id: clientId },
        currentBaseUrl: before.baseUrl,
      });
      const token = response.payload?.token;
      if (!response.ok || !token) {
        return {
          ok: false,
          status: response.status,
          error: response.error ?? "registration_failed",
        };
      }

      const current = await readStoredState();
      if (current.clientId && current.token && !sameCredentials(current, before)) {
        return { ok: true, status: response.status, clientId: current.clientId, adopted: true };
      }
      await saveCredentials({ clientId, token, baseUrl: before.baseUrl });
      return { ok: true, status: response.status, clientId };
    })();

    let shared;
    shared = operation.finally(() => {
      if (registrationInFlight === shared) registrationInFlight = null;
    });
    registrationInFlight = shared;
    return shared;
  }

  async function authenticatedRequest(path, options = {}) {
    let credentials = await readStoredState();
    if (!credentials.clientId || !credentials.token) {
      const registration = await register();
      if (!registration.ok) return registration;
      credentials = await readStoredState();
    }

    let response = await request(path, {
      ...options,
      token: credentials.token,
      clientId: credentials.clientId,
      currentBaseUrl: credentials.baseUrl,
    });
    if (response.status !== 401) return response;

    const current = await readStoredState();
    if (sameCredentials(credentials, current)) {
      const registration = await register();
      if (!registration.ok) return registration;
    }

    const retryCredentials = await readStoredState();
    if (!retryCredentials.clientId || !retryCredentials.token) {
      return { ok: false, status: 0, payload: null, error: "not_paired" };
    }
    response = await request(path, {
      ...options,
      token: retryCredentials.token,
      clientId: retryCredentials.clientId,
      currentBaseUrl: retryCredentials.baseUrl,
    });
    return response;
  }

  return {
    register,

    async nextCommand() {
      const response = await authenticatedRequest("/api/v1/extension/commands/next");
      if (!response.ok) {
        return {
          ok: false,
          status: response.status,
          error: response.error ?? "request_failed",
          command: null,
        };
      }
      return { ok: true, status: response.status, command: response.payload?.command ?? null };
    },

    async reportResult(commandId, result) {
      const response = await authenticatedRequest(`/api/v1/extension/commands/${Number(commandId)}/result`, {
        method: "POST",
        body: result,
      });
      return {
        ok: response.ok,
        status: response.status,
        error: response.ok ? null : response.error ?? "request_failed",
      };
    },

    async status() {
      const response = await authenticatedRequest("/api/v1/bridge/status");
      return {
        ok: response.ok,
        status: response.status,
        paired: response.ok && response.payload?.paired === true,
        payload: response.payload,
        error: response.ok ? null : response.error ?? "request_failed",
      };
    },

    /** Hand the operator-opened form to the Mesa (M5 Task 6, manual fallback). */
    async requestManualFill(snapshot) {
      const response = await authenticatedRequest("/api/v1/portal/manual-form", {
        method: "POST",
        body: snapshot,
      });
      return {
        ok: response.ok,
        status: response.status,
        payload: response.payload,
        error: response.ok
          ? null
          : response.payload?.detail ?? response.error ?? "request_failed",
      };
    },
  };
}
