const ALLOWED_ACTIONS = new Set(["next_page", "open_act", "select_interested", "return_list"]);
const NAVIGATION_TIMEOUT_MS = 30_000;
const DOCUMENT_STATE = new WeakMap();

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function textOf(value) {
  return typeof value?.textContent === "string"
    ? value.textContent.replace(/\s+/gu, " ").trim()
    : "";
}

function normalizeInterested(value) {
  return typeof value === "string"
    ? value.normalize("NFKD").replace(/\p{M}+/gu, "").toLowerCase().replace(/\s+/gu, " ").trim()
    : "";
}

function getAttribute(element, name) {
  const value = element?.getAttribute?.(name);
  return typeof value === "string" ? value : "";
}

function getDatasetValue(documentRef, name) {
  const candidates = [
    documentRef?.documentElement,
    documentRef?.body,
    documentRef,
  ];
  for (const candidate of candidates) {
    const value = candidate?.dataset?.[name] ?? getAttribute(candidate, `data-${name.replace(/[A-Z]/gu, (letter) => `-${letter.toLowerCase()}`)}`);
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function queryAll(documentRef, selector) {
  return typeof documentRef?.querySelectorAll === "function"
    ? [...documentRef.querySelectorAll(selector)]
    : [];
}

function queryOne(documentRef, selector) {
  return typeof documentRef?.querySelector === "function"
    ? documentRef.querySelector(selector)
    : queryAll(documentRef, selector)[0] ?? null;
}

function byId(documentRef, id) {
  return typeof documentRef?.getElementById === "function" ? documentRef.getElementById(id) : null;
}

function uniqueByIdentity(identities) {
  const seen = new Set();
  return identities.filter((identity) => {
    const key = `${identity.processKey}\u0000${identity.interestedNormalized}`;
    if (!identity.processKey || !identity.interestedNormalized || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function processKeyFromText(value) {
  const match = String(value ?? "").match(/([A-Za-z0-9][A-Za-z0-9._-]*\/\d{4})/u);
  return match?.[1] ?? "";
}

function processKeyFromDocument(documentRef) {
  const explicit = getDatasetValue(documentRef, "processKey")
    || getAttribute(documentRef, "data-process-key");
  if (explicit) return explicit;
  const number = String(byId(documentRef, "txtNumeroProcesso")?.value ?? "").trim();
  const year = String(byId(documentRef, "txtAnoProcesso")?.value ?? "").trim();
  return number && year ? `${number}/${year}` : "";
}

function rowCells(row) {
  return queryAll(row, "td").length > 0 ? queryAll(row, "td") : queryAll(row, "th");
}

function interestedTextFromRow(row, radio = null) {
  for (const candidate of [
    getAttribute(radio, "data-interested-name"),
    getAttribute(radio, "data-interessado"),
    getAttribute(radio, "aria-label"),
    textOf(radio?.labels?.[0]),
    textOf(queryOne(row, ".interested-name")),
  ]) {
    if (candidate) return candidate;
  }
  const cells = rowCells(row);
  if (cells.length >= 2) return textOf(cells[1]);
  return "";
}

function portalActIdFromRow(row, control = null) {
  return getAttribute(row, "data-portal-act-id")
    || getAttribute(row, "data-act-id")
    || getAttribute(control, "data-portal-act-id")
    || getAttribute(control, "data-act-id")
    || null;
}

function identityFromRow(row, { radio = null, processKey = "" } = {}) {
  const resolvedProcessKey = processKey
    || getAttribute(row, "data-process-key")
    || getAttribute(row, "data-process")
    || processKeyFromText(textOf(row));
  const interestedOriginal = interestedTextFromRow(row, radio);
  const interestedNormalized = normalizeInterested(interestedOriginal);
  if (!resolvedProcessKey || !interestedNormalized) return null;
  return {
    processKey: resolvedProcessKey,
    interestedOriginal,
    interestedNormalized,
    portalActId: portalActIdFromRow(row, radio),
    ...(radio ? { selected: radio.checked === true } : {}),
  };
}

function listRows(documentRef) {
  const table = byId(documentRef, "tbproc01")
    || queryOne(documentRef, 'table[data-screen="list"]')
    || queryOne(documentRef, "table");
  const rows = queryAll(table, "tbody tr");
  return rows.length > 0 ? rows : queryAll(table ?? documentRef, "tr").filter((row) => rowCells(row).length > 0);
}

function interestedRows(documentRef) {
  const table = byId(documentRef, "PessoasAssocicadas")
    || byId(documentRef, "PessoasAssociadas")
    || queryOne(documentRef, 'table[data-screen="interested"]')
    || queryOne(documentRef, 'table:has(input[type="radio"])');
  const rows = queryAll(table, "tr");
  return rows.filter((row) => Boolean(queryOne(row, 'input[type="radio"]')));
}

function isFormScreen(documentRef) {
  return Boolean(
    byId(documentRef, "complementarAtoForm")
    || byId(documentRef, "tbcomplementarato")
    || (byId(documentRef, "txtNumeroProcesso") && byId(documentRef, "txtAnoProcesso")),
  );
}

function isInterestedScreen(documentRef) {
  return interestedRows(documentRef).length > 0;
}

function isListScreen(documentRef) {
  if (Boolean(byId(documentRef, "tbproc01"))) return true;
  return listRows(documentRef).some((row) => processKeyFromText(textOf(row)) && queryAll(row, "a").length > 0);
}

function isButtonsScreen(documentRef) {
  return queryAll(documentRef, "button, a").some((control) => {
    const action = getAttribute(control, "data-action");
    const label = normalizeInterested(textOf(control));
    return action === "return-list" || action === "return_list" || label === "voltar" || label === "retornar";
  });
}

function detectPortalScreen(documentRef = globalThis.document) {
  if (!documentRef) return "unknown";
  if (isFormScreen(documentRef)) return "form";
  if (isInterestedScreen(documentRef)) return "interested";
  if (isListScreen(documentRef)) return "list";
  if (isButtonsScreen(documentRef)) return "buttons";
  return "unknown";
}

function listIdentityEntries(documentRef) {
  return listRows(documentRef).map((row) => {
    const control = queryAll(row, "a").find((link) => {
      const action = getAttribute(link, "data-action");
      return action !== "signal-only" && action !== "submit";
    }) ?? null;
    return identityFromRow(row, { processKey: processKeyFromText(textOf(row)) })
      ? { identity: identityFromRow(row, { processKey: processKeyFromText(textOf(row)) }), row, control }
      : null;
  }).filter(Boolean);
}

function interestedIdentityEntries(documentRef) {
  const processKey = processKeyFromDocument(documentRef);
  return interestedRows(documentRef).map((row) => {
    const radio = queryOne(row, 'input[type="radio"]');
    const identity = identityFromRow(row, { radio, processKey });
    return identity ? { identity, row, radio } : null;
  }).filter(Boolean);
}

function findNextControl(documentRef) {
  const explicit = queryAll(documentRef, '[data-action="next-page"], [data-action="next_page"], a[rel="next"], button[rel="next"]')[0];
  if (explicit) return explicit;
  const current = queryOne(documentRef, '[aria-current="page"]');
  const currentNumber = Number.parseInt(textOf(current), 10);
  return queryAll(documentRef, "nav a, nav button, a, button").find((control) => {
    if (getAttribute(control, "aria-current") === "page") return false;
    const label = normalizeInterested(textOf(control));
    if (["próxima", "proxima", "next", "seguinte"].includes(label)) return true;
    const number = Number.parseInt(label, 10);
    return Number.isInteger(number) && Number.isInteger(currentNumber) && number > currentNumber;
  }) ?? null;
}

function findReturnControl(documentRef) {
  return queryAll(documentRef, '[data-action="return-list"], [data-action="return_list"], a, button').find((control) => {
    const action = getAttribute(control, "data-action");
    const label = normalizeInterested(textOf(control));
    return action === "return-list" || action === "return_list" || label === "voltar" || label === "retornar";
  }) ?? null;
}

function actionSnapshot(documentRef, role) {
  const actions = [];
  if (role === "list") {
    for (const entry of listIdentityEntries(documentRef)) {
      if (entry.control) actions.push({ action: "open_act", enabled: true, identity: entry.identity });
    }
    if (findNextControl(documentRef)) actions.push({ action: "next_page", enabled: true });
  }
  if (role === "interested") {
    for (const entry of interestedIdentityEntries(documentRef)) {
      actions.push({ action: "select_interested", enabled: true, identity: entry.identity });
    }
    if (findReturnControl(documentRef)) actions.push({ action: "return_list", enabled: true });
  }
  if (role === "form" || role === "buttons") {
    const processKey = processKeyFromDocument(documentRef);
    if (processKey) {
      const interested = interestedIdentityEntries(documentRef).find((entry) => entry.identity.selected)?.identity;
      if (interested) actions.push({ action: "return_list", enabled: Boolean(findReturnControl(documentRef)), identity: interested });
    }
    if (findReturnControl(documentRef)) actions.push({ action: "return_list", enabled: true });
  }
  return actions;
}

function rawFingerprint(documentRef, role) {
  const marker = getDatasetValue(documentRef, "page") || getDatasetValue(documentRef, "screen");
  const list = listIdentityEntries(documentRef).map(({ identity }) => `${identity.processKey}:${identity.interestedNormalized}`);
  const interested = interestedIdentityEntries(documentRef).map(({ identity }) => `${identity.processKey}:${identity.interestedNormalized}:${identity.selected}`);
  return JSON.stringify([role, marker, processKeyFromDocument(documentRef), list, interested, textOf(documentRef?.body)]);
}

function currentGeneration(documentRef, role = detectPortalScreen(documentRef)) {
  let state = DOCUMENT_STATE.get(documentRef);
  if (!state) {
    state = { generation: 0, fingerprint: null };
    DOCUMENT_STATE.set(documentRef, state);
  }
  const fingerprint = rawFingerprint(documentRef, role);
  if (state.fingerprint !== fingerprint) {
    state.fingerprint = fingerprint;
    state.generation += 1;
  }
  return state.generation;
}

function snapshotPortalScreen(documentRef = globalThis.document) {
  const role = detectPortalScreen(documentRef);
  const identities = role === "list"
    ? listIdentityEntries(documentRef).map(({ identity }) => identity)
    : role === "interested"
      ? interestedIdentityEntries(documentRef).map(({ identity }) => identity)
      : [];
  return {
    role,
    generation: currentGeneration(documentRef, role),
    sector: getDatasetValue(documentRef, "sector") || null,
    identities: uniqueByIdentity(identities),
    actions: actionSnapshot(documentRef, role),
  };
}

function sameIdentity(left, right) {
  return Boolean(left && right)
    && left.processKey === right.processKey
    && left.interestedNormalized === right.interestedNormalized;
}

function selectedIdentity(documentRef) {
  return interestedIdentityEntries(documentRef).find(({ identity }) => identity.selected)?.identity ?? null;
}

function isProgress(documentRef, before, after, action, identity) {
  if (after.role === "unknown") return false;
  if (action === "next_page") {
    const beforeKeys = new Set(before.identities.map(({ processKey, interestedNormalized }) => `${processKey}\u0000${interestedNormalized}`));
    return after.role === "list"
      && after.generation !== before.generation
      && after.identities.some(({ processKey, interestedNormalized }) => !beforeKeys.has(`${processKey}\u0000${interestedNormalized}`));
  }
  if (action === "open_act") return before.role === "list" && after.role !== "list";
  if (action === "select_interested") return after.role === "interested" && sameIdentity(selectedIdentity(documentRef), identity);
  if (action === "return_list") return after.role === "list" && before.role !== "list";
  return false;
}

function navigationError(code, message, extra = {}) {
  return { ok: false, error: { code, message }, ...extra };
}

function resolveControl(documentRef, action, identity) {
  if (action === "next_page") return findNextControl(documentRef);
  if (action === "return_list") return findReturnControl(documentRef);
  if (action === "open_act") {
    return listIdentityEntries(documentRef).find((entry) => sameIdentity(entry.identity, identity))?.control ?? null;
  }
  if (action === "select_interested") {
    return interestedIdentityEntries(documentRef).find((entry) => sameIdentity(entry.identity, identity))?.radio ?? null;
  }
  return null;
}

async function waitForNavigation(documentRef, before, action, identity, timeoutMs) {
  const timerFactory = documentRef?.defaultView?.setTimeout ?? globalThis.setTimeout;
  const clearTimer = documentRef?.defaultView?.clearTimeout ?? globalThis.clearTimeout;
  let rereads = 0;
  let observer = null;
  let timer = null;

  const readOnce = () => {
    if (rereads >= 1) return null;
    rereads += 1;
    const after = snapshotPortalScreen(documentRef);
    return isProgress(documentRef, before, after, action, identity) ? after : null;
  };

  const immediate = readOnce();
  if (immediate) return { ok: true, action, snapshot: immediate, rereads };

  return new Promise((resolve) => {
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      observer?.disconnect?.();
      if (timer !== null) clearTimer(timer);
      resolve(result);
    };
    const check = () => {
      const after = readOnce();
      if (after) {
        finish({ ok: true, action, snapshot: after, rereads });
      } else if (rereads >= 1) {
        finish(navigationError("NAVIGATION_TIMEOUT", "navigation did not produce the expected portal screen", { action, rereads }));
      }
    };
    const Observer = documentRef?.defaultView?.MutationObserver ?? globalThis.MutationObserver;
    if (typeof Observer === "function") {
      observer = new Observer(check);
      observer.observe(documentRef?.body ?? documentRef, { childList: true, subtree: true, attributes: true });
    }
    timer = timerFactory(check, timeoutMs);
  });
}

async function executeNavigation(documentRef = globalThis.document, request = {}) {
  const action = request?.action;
  if (!ALLOWED_ACTIONS.has(action)) return navigationError("UNSUPPORTED_ACTION", `unsupported portal navigation action: ${action}`);
  if (!Number.isSafeInteger(request.expected_generation) || request.expected_generation < 1) {
    return navigationError("INVALID_GENERATION", "expected_generation must be a positive integer");
  }
  const before = snapshotPortalScreen(documentRef);
  if (before.generation !== request.expected_generation) {
    return navigationError("STALE_GENERATION", "portal screen generation changed before navigation", { generation: before.generation });
  }
  const control = resolveControl(documentRef, action, request.identity);
  if (!control) return navigationError(action === "open_act" ? "ROW_ACTION_NOT_FOUND" : "ACTION_NOT_FOUND", "the requested observed portal action is unavailable");
  if (getAttribute(control, "data-action") === "signal-only" || getAttribute(control, "data-action") === "submit") {
    return navigationError("ACTION_NOT_ALLOWED", "signal and submit controls are outside the navigation allowlist");
  }
  control.click?.();
  return waitForNavigation(
    documentRef,
    before,
    action,
    request.identity,
    Number.isInteger(request.timeoutMs) && request.timeoutMs > 0 ? Math.min(request.timeoutMs, NAVIGATION_TIMEOUT_MS) : NAVIGATION_TIMEOUT_MS,
  );
}

function createMessageHandler(documentRef = globalThis.document) {
  return async (message) => {
    if (!isRecord(message) || typeof message.type !== "string" || !isRecord(message.payload)) {
      return navigationError("INVALID_MESSAGE", "portal navigation message must contain type and payload");
    }
    if (message.type === "PORTAL_GET_SNAPSHOT") {
      return { ok: true, payload: snapshotPortalScreen(documentRef) };
    }
    if (message.type === "PORTAL_NAVIGATE") {
      return executeNavigation(documentRef, message.payload);
    }
    return navigationError("UNSUPPORTED_MESSAGE", `unsupported portal navigation message: ${message.type}`);
  };
}

function requestId() {
  return typeof globalThis.crypto?.randomUUID === "function" ? globalThis.crypto.randomUUID() : `portal-${Date.now()}`;
}

function installPortalNavigation({ documentRef = globalThis.document, chromeApi = globalThis.chrome } = {}) {
  const handleMessage = createMessageHandler(documentRef);
  if (!chromeApi?.runtime?.onMessage?.addListener) return { handleMessage, registered: false };
  chromeApi.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    Promise.resolve(handleMessage(message)).then(sendResponse);
    return true;
  });
  if (typeof chromeApi.runtime.sendMessage === "function") {
    chromeApi.runtime.sendMessage({
      schemaVersion: 1,
      type: "PORTAL_EVENT",
      requestId: requestId(),
      payload: { event: { type: "snapshot", snapshot: snapshotPortalScreen(documentRef) } },
    });
  }
  return { handleMessage, registered: true };
}

if (typeof module === "object" && module !== null && module.exports) {
  module.exports.ALLOWED_ACTIONS = ALLOWED_ACTIONS;
  module.exports.NAVIGATION_TIMEOUT_MS = NAVIGATION_TIMEOUT_MS;
  module.exports.detectPortalScreen = detectPortalScreen;
  module.exports.snapshotPortalScreen = snapshotPortalScreen;
  module.exports.executeNavigation = executeNavigation;
  module.exports.createMessageHandler = createMessageHandler;
  module.exports.installPortalNavigation = installPortalNavigation;
} else {
  globalThis.TCEPortalNavigation = Object.freeze({
    detectPortalScreen,
    snapshotPortalScreen,
    executeNavigation,
    createMessageHandler,
    installPortalNavigation,
  });
  if (globalThis.document && globalThis.chrome?.runtime?.onMessage) installPortalNavigation();
}
