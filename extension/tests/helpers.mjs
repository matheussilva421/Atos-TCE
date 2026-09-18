/** Shared test doubles for the extension suite. */

export function fakeStorage() {
  const data = new Map();
  return {
    data,
    async get(keys) {
      const result = {};
      for (const key of [].concat(keys ?? [])) if (data.has(key)) result[key] = data.get(key);
      return result;
    },
    async set(patch) {
      for (const [key, value] of Object.entries(patch)) data.set(key, value);
    },
    async remove(keys) {
      for (const key of [].concat(keys ?? [])) data.delete(key);
    },
  };
}

export function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async text() {
      return JSON.stringify(body);
    },
  };
}

/** Route-aware fetch double that records every call. */
export function fakeFetch(routes) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    const method = (init.method ?? "GET").toUpperCase();
    calls.push({ url, method, headers: init.headers ?? {}, body: init.body });
    const route = routes.find(
      (candidate) => url.endsWith(candidate.path) && (candidate.method ?? "GET").toUpperCase() === method
    );
    if (!route) return jsonResponse(404, { error: "not_found" });
    const body = typeof route.body === "function" ? route.body(calls.at(-1)) : route.body ?? {};
    return jsonResponse(route.status ?? 200, body);
  };
  fetchImpl.calls = calls;
  return fetchImpl;
}

/** Minimal `chrome` double with tabs, runtime and alarms. */
export function fakeChrome({ tabs = [], onMessage = null } = {}) {
  const listeners = [];
  const alarmListeners = [];
  const sent = [];
  if (onMessage) onMessage.sent = sent;
  return {
    sent,
    listeners,
    alarmListeners,
    runtime: {
      id: "abcdefghijklmnopabcdefghijklmnop",
      onMessage: { addListener: (listener) => listeners.push(listener) },
      async sendMessage(message) {
        sent.push(message);
        return onMessage ? onMessage(message) : { ok: true };
      },
    },
    tabs: {
      async query() {
        return tabs;
      },
      async sendMessage(tabId, message) {
        sent.push({ tabId, message });
        return onMessage ? onMessage(message, tabId) : { ok: true };
      },
    },
    alarms: {
      created: [],
      create(name, info) {
        this.created.push({ name, info });
      },
      onAlarm: { addListener: (listener) => alarmListeners.push(listener) },
    },
  };
}
