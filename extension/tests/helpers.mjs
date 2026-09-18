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

function matchesTabQuery(tab, info) {
  if (info?.active === true && tab.active !== true) return false;
  if (info?.lastFocusedWindow === true && tab.lastFocusedWindow === false) return false;
  if (!info?.url) return true;
  // A tab that does not declare a url stands for "the portal tab" in the
  // tests that do not care about the URL filter; a tab that declares one must
  // match the requested pattern.
  if (typeof tab.url !== "string") return true;
  const patterns = [].concat(info.url);
  return patterns.some((pattern) =>
    pattern.endsWith("*") ? tab.url.startsWith(pattern.slice(0, -1)) : tab.url === pattern
  );
}

/**
 * Minimal `chrome` double with tabs, frames, runtime and alarms.
 *
 * `frames` maps a tab id to the frame list that `webNavigation.getAllFrames`
 * reports. A tab without an entry is its own single top frame; a tab mapped to
 * `null` models a frame enumeration that fails.
 */
export function fakeChrome({ tabs = [], frames = {}, onMessage = null } = {}) {
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
      async query(info = {}) {
        return tabs.filter((tab) => matchesTabQuery(tab, info));
      },
      async sendMessage(tabId, message, options = {}) {
        const frameId = options.frameId ?? 0;
        sent.push({ tabId, frameId, message });
        return onMessage ? onMessage(message, tabId, frameId) : { ok: true };
      },
    },
    webNavigation: {
      async getAllFrames({ tabId }) {
        const declared = frames[tabId];
        if (declared === null) throw new Error(`tab ${tabId} has no frames`);
        if (Array.isArray(declared)) return declared;
        const tab = tabs.find((candidate) => candidate.id === tabId);
        return [{ frameId: 0, url: tab?.url }];
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
