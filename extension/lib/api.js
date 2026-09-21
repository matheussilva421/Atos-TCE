/**
 * Mesa client used by the extension.
 *
 * Only two credentials exist: the paired bearer token and the client id, both
 * kept in ``chrome.storage.local``. The token is attached to requests and never
 * logged, returned to a page or written anywhere else.
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
  let state = null;

  async function readStoredState() {
    const stored = (await storage?.get?.(Object.values(STORAGE_KEYS))) ?? {};
    return {
      clientId: stored[STORAGE_KEYS.clientId] ?? null,
      token: stored[STORAGE_KEYS.token] ?? null,
      baseUrl: stored[STORAGE_KEYS.baseUrl] ?? baseUrl,
    };
  }

  async function readState() {
    if (state) return state;
    state = await readStoredState();
    return state;
  }

  async function save(patch) {
    state = { ...(await readState()), ...patch };
    await storage?.set?.({
      [STORAGE_KEYS.clientId]: state.clientId,
      [STORAGE_KEYS.token]: state.token,
      [STORAGE_KEYS.baseUrl]: state.baseUrl,
    });
    return state;
  }

  async function request(path, { method = "GET", body, token, clientId } = {}) {
    const current = await readState();
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;
    if (clientId) headers["X-TCE-Client"] = clientId;
    const response = await fetchImpl(`${current.baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await response.text();
    let payload = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = null;
    }
    return { ok: response.ok === true, status: response.status, payload };
  }

  return {
    async pair(code) {
      const current = await readState();
      const clientId = current.clientId || clientIdFactory();
      const response = await request("/api/v1/bridge/pair", {
        method: "POST",
        body: {
          client_id: clientId,
          code: String(code ?? "").trim(),
          extension_id: globalThis.chrome?.runtime?.id ?? null,
        },
      });
      const token = response.payload?.token;
      if (!response.ok || !token) {
        return { ok: false, status: response.status, error: response.payload?.error ?? "pairing_failed" };
      }
      await save({ clientId, token });
      return { ok: true, status: response.status, clientId };
    },

    async nextCommand() {
      const { clientId, token } = await readState();
      if (!clientId || !token) return { ok: false, status: 0, error: "not_paired", command: null };
      const response = await request("/api/v1/extension/commands/next", { token, clientId });
      if (!response.ok) {
        return {
          ok: false,
          status: response.status,
          error: response.payload?.error ?? "request_failed",
          command: null,
        };
      }
      return { ok: true, status: response.status, command: response.payload?.command ?? null };
    },

    async reportResult(commandId, result) {
      const { clientId, token } = await readState();
      if (!clientId || !token) return { ok: false, status: 0, error: "not_paired" };
      const response = await request(`/api/v1/extension/commands/${Number(commandId)}/result`, {
        method: "POST",
        body: result,
        token,
        clientId,
      });
      return {
        ok: response.ok,
        status: response.status,
        error: response.ok ? null : response.payload?.error ?? "request_failed",
      };
    },

    async status() {
      const { clientId, token } = await readState();
      if (!clientId || !token) return { ok: false, status: 0, error: "not_paired", paired: false };
      const response = await request("/api/v1/bridge/status", { token, clientId });
      return {
        ok: response.ok,
        status: response.status,
        paired: response.payload?.paired === true,
        payload: response.payload,
        error: response.ok ? null : response.payload?.error ?? "request_failed",
      };
    },

    /** Hand the operator-opened form to the Mesa (M5 Task 6, manual fallback). */
    async requestManualFill(snapshot) {
      const { clientId, token } = await readState();
      if (!clientId || !token) return { ok: false, status: 0, error: "not_paired" };
      const response = await request("/api/v1/portal/manual-form", {
        method: "POST",
        body: snapshot,
        token,
        clientId,
      });
      return {
        ok: response.ok,
        status: response.status,
        payload: response.payload,
        error: response.ok ? null : response.payload?.detail ?? response.payload?.error ?? "request_failed",
      };
    },

    async clear(expected) {
      const current = expected ? await readStoredState() : await readState();
      if (
        expected &&
        (expected.clientId !== current.clientId || expected.token !== current.token)
      ) {
        return false;
      }
      state = { clientId: null, token: null, baseUrl }; 
      await storage?.remove?.([STORAGE_KEYS.clientId, STORAGE_KEYS.token]);
      return true;
    },

    async reload() {
      state = await readStoredState();
      return state;
    },

    async credentials() {
      const { clientId, token } = await readState();
      return { clientId, token, paired: Boolean(clientId && token) };
    },
  };
}
