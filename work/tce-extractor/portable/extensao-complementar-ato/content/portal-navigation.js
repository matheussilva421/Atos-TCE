const ALLOWED_ACTIONS = new Set(["next_page", "open_act", "select_interested", "return_list", "filter_marker"]);
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

function controlLabel(control) {
  return [
    textOf(control),
    getAttribute(control, "aria-label"),
    getAttribute(control, "title"),
    getAttribute(control, "value"),
    typeof control?.value === "string" ? control.value : "",
    ...queryAll(control, "img").flatMap((image) => [getAttribute(image, "alt"), getAttribute(image, "title")]),
  ].filter(Boolean).join(" ");
}

function markerSelect(documentRef) {
  return queryAll(documentRef, "select").find((select) => {
    const metadata = [
      getAttribute(select, "id"),
      getAttribute(select, "name"),
      getAttribute(select, "aria-label"),
      getAttribute(select, "data-field"),
    ].join(" ");
    if (normalizeInterested(metadata).includes("marcador")) return true;
    const label = getAttribute(select, "id");
    if (label && queryAll(documentRef, "label").some((candidate) => (
      getAttribute(candidate, "for") === label && normalizeInterested(textOf(candidate)).includes("marcador")
    ))) return true;
    const row = select.closest?.("tr") ?? null;
    return normalizeInterested(textOf(row)).includes("marcador");
  }) ?? null;
}

function selectedOption(select) {
  const options = select?.options
    ? [...select.options]
    : queryAll(select, "option");
  return options.find((option) => option.selected === true)
    || options.find((option) => getAttribute(option, "selected") !== "")
    || options.find((option) => String(option.value ?? "") === String(select?.value ?? ""))
    || null;
}

function observedMarker(documentRef) {
  const select = markerSelect(documentRef);
  const option = selectedOption(select);
  if (!select || !option) return null;
  const label = textOf(option);
  const normalized = normalizeInterested(label);
  if (!label || ["todos", "todos os marcadores", "selecione", "selecione um marcador"].includes(normalized)) return null;
  return {
    label,
    value: typeof option.value === "string" && option.value ? option.value : null,
  };
}

function markerFilterControls(documentRef) {
  const select = markerSelect(documentRef);
  if (!select) return null;
  const scopes = [select.closest?.("form"), select.closest?.("tr"), select.parentElement, documentRef].filter(Boolean);
  for (const scope of scopes) {
    const submit = queryAll(scope, "button, input, a").find((control) => {
      const label = normalizeInterested(controlLabel(control));
      return label === "consultar" || label.startsWith("consultar ");
    });
    if (submit) return { select, submit };
  }
  return { select, submit: null };
}

function isComplementActControl(control) {
  const label = normalizeInterested(controlLabel(control));
  if (label.includes("complementar ato")) return true;
  const action = getAttribute(control, "data-action");
  if (action === "open-act" || action === "open_act") return true;
  return getAttribute(control, "href").toLowerCase().includes("complementarato");
}

function markerOption(select, requestedMarker) {
  const expected = normalizeInterested(requestedMarker);
  const options = select?.options
    ? [...select.options]
    : queryAll(select, "option");
  return options.find((option) => normalizeInterested(textOf(option)) === expected) ?? null;
}

function dispatchControlEvents(documentRef, control) {
  if (typeof control?.dispatchEvent !== "function") return;
  const EventConstructor = documentRef?.defaultView?.Event ?? globalThis.Event;
  if (typeof EventConstructor !== "function") return;
  for (const type of ["input", "change"]) control.dispatchEvent(new EventConstructor(type, { bubbles: true }));
}

function uniqueByIdentity(identities) {
  const seen = new Set();
  return identities.filter((identity) => {
    const key = `${identity.processKey ?? ""}\u0000${identity.interestedNormalized ?? ""}\u0000${identity.portalActId ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function hasCanonicalIdentity(identity) {
  return Boolean(identity?.processKey && identity?.interestedNormalized);
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

function interestedColumnIndex(row) {
  const table = row?.closest?.("table") ?? null;
  if (!table) return -1;
  const headerRows = queryAll(table, "thead tr");
  const candidates = headerRows.length > 0
    ? headerRows
    : queryAll(table, "tr").filter((candidate) => normalizeInterested(textOf(candidate)).includes("interessado"));
  for (const headerRow of candidates) {
    const headers = rowCells(headerRow);
    const index = headers.findIndex((header) => normalizeInterested(textOf(header)) === "interessado");
    if (index >= 0) return index;
  }
  return -1;
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
  const headedIndex = interestedColumnIndex(row);
  if (headedIndex >= 0 && cells[headedIndex]) return textOf(cells[headedIndex]);
  const dataIndex = cells.findIndex((cell) => (
    [getAttribute(cell, "data-field"), getAttribute(cell, "data-column")]
      .some((value) => normalizeInterested(value) === "interessado")
  ));
  if (dataIndex >= 0) return textOf(cells[dataIndex]);
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
  return {
    processKey: resolvedProcessKey || null,
    interestedOriginal,
    interestedNormalized: interestedNormalized || null,
    portalActId: portalActIdFromRow(row, radio),
    pending: !resolvedProcessKey || !interestedNormalized,
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
    const controls = queryAll(row, "a, button");
    const control = controls.find((candidate) => isComplementActControl(candidate)) ?? null;
    /*
     * A single unlabelled control is retained for the minimal legacy portal
     * fixture. Real rows with multiple icons must expose the semantic action.
     */
    const candidates = controls.filter((candidate) => !["signal-only", "submit"].includes(getAttribute(candidate, "data-action")));
    const fallback = control ?? (candidates.length === 1 ? candidates[0] : null);
    const selectedControl = fallback && (candidates.length === 1 || isComplementActControl(fallback)) ? fallback : null;
    const identity = identityFromRow(row, { processKey: processKeyFromText(textOf(row)) });
    if (hasCanonicalIdentity(identity)) identity.needsComplement = Boolean(selectedControl);
    return {
      identity,
      row,
      control: selectedControl,
    };
  });
}

function interestedIdentityEntries(documentRef) {
  const processKey = processKeyFromDocument(documentRef);
  return interestedRows(documentRef).map((row) => {
    const radio = queryOne(row, 'input[type="radio"]');
    const identity = identityFromRow(row, { radio, processKey });
    return { identity, row, radio };
  });
}

function findNextNavigation(documentRef) {
  const explicit = queryAll(documentRef, '[data-action="next-page"], [data-action="next_page"], a[rel="next"], button[rel="next"]')[0];
  if (explicit) return { control: explicit, direction: "next" };
  const current = queryOne(documentRef, '[aria-current="page"]');
  const currentNumber = Number.parseInt(textOf(current), 10);
  const next = queryAll(documentRef, "nav a, nav button, a, button").find((control) => {
    if (getAttribute(control, "aria-current") === "page") return false;
    const label = normalizeInterested(textOf(control));
    if (["próxima", "proxima", "next", "seguinte"].includes(label)) return true;
    const number = Number.parseInt(label, 10);
    return Number.isInteger(number) && Number.isInteger(currentNumber) && number > currentNumber;
  }) ?? null;
  if (next) return { control: next, direction: "next" };
  const first = queryAll(documentRef, "nav a, nav button").find((control) => {
    if (getAttribute(control, "aria-current") === "page") return false;
    return getAttribute(control, "data-action") === "first-page" || normalizeInterested(textOf(control)) === "1";
  }) ?? null;
  return first ? { control: first, direction: "first" } : null;
}

function findNextControl(documentRef) {
  return findNextNavigation(documentRef)?.control ?? null;
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
      if (entry.control && hasCanonicalIdentity(entry.identity)) actions.push({ action: "open_act", enabled: true, identity: entry.identity });
    }
    const next = findNextNavigation(documentRef);
    if (next) actions.push({ action: "next_page", enabled: true, direction: next.direction });
    if (markerFilterControls(documentRef)?.submit) actions.push({ action: "filter_marker", enabled: true });
  }
  if (role === "interested") {
    for (const entry of interestedIdentityEntries(documentRef)) {
      if (hasCanonicalIdentity(entry.identity)) actions.push({ action: "select_interested", enabled: true, identity: entry.identity });
    }
    const selected = selectedIdentity(documentRef);
    if (findReturnControl(documentRef)) {
      actions.push({
        action: "return_list",
        enabled: true,
        ...(selected ? { identity: actionIdentity(selected) } : {}),
      });
    }
  }
  if (role === "form" || role === "buttons") {
    const processKey = processKeyFromDocument(documentRef);
    if (processKey) {
      const interested = interestedIdentityEntries(documentRef).find((entry) => entry.identity.selected && hasCanonicalIdentity(entry.identity))?.identity;
      if (interested) actions.push({ action: "return_list", enabled: Boolean(findReturnControl(documentRef)), identity: interested });
    }
    if (findReturnControl(documentRef)) actions.push({ action: "return_list", enabled: true });
  }
  return actions;
}

function rawFingerprint(documentRef, role) {
  const marker = getDatasetValue(documentRef, "page") || getDatasetValue(documentRef, "screen");
  const selectedMarker = observedMarker(documentRef);
  const list = listIdentityEntries(documentRef).map(({ identity }) => `${identity.processKey ?? ""}:${identity.interestedNormalized ?? ""}:${identity.portalActId ?? ""}`);
  const interested = interestedIdentityEntries(documentRef).map(({ identity }) => `${identity.processKey ?? ""}:${identity.interestedNormalized ?? ""}:${identity.selected}`);
  return JSON.stringify([role, marker, selectedMarker, processKeyFromDocument(documentRef), list, interested, textOf(documentRef?.body)]);
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
    marker: observedMarker(documentRef),
    identities: uniqueByIdentity(identities),
    actions: actionSnapshot(documentRef, role),
  };
}

function sameIdentity(left, right) {
  return hasCanonicalIdentity(left) && hasCanonicalIdentity(right)
    && left.processKey === right.processKey
    && left.interestedNormalized === right.interestedNormalized;
}

function selectedIdentity(documentRef) {
  return interestedIdentityEntries(documentRef).find(({ identity }) => identity.selected && hasCanonicalIdentity(identity))?.identity ?? null;
}

function actionIdentity(identity) {
  if (!identity) return null;
  return {
    processKey: identity.processKey,
    interestedOriginal: identity.interestedOriginal,
    interestedNormalized: identity.interestedNormalized,
    portalActId: identity.portalActId ?? null,
  };
}

function isProgress(documentRef, before, after, action, identity, requestedMarker = "") {
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
  if (action === "filter_marker") return after.role === "list"
    && after.generation !== before.generation
    && normalizeInterested(after.marker?.label) === normalizeInterested(requestedMarker);
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
  if (action === "filter_marker") return markerFilterControls(documentRef)?.select ?? null;
  return null;
}

async function waitForNavigation(documentRef, before, action, identity, timeoutMs, performClick, requestedMarker = "") {
  const timerFactory = documentRef?.defaultView?.setTimeout ?? globalThis.setTimeout;
  const clearTimer = documentRef?.defaultView?.clearTimeout ?? globalThis.clearTimeout;
  let rereads = 0;
  let observer = null;
  let timer = null;

  const readOnce = () => {
    if (rereads >= 1) return null;
    rereads += 1;
    const after = snapshotPortalScreen(documentRef);
    return isProgress(documentRef, before, after, action, identity, requestedMarker) ? after : null;
  };

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
      timer = timerFactory(check, timeoutMs);
      performClick();
      return;
    }
    performClick();
    const immediate = readOnce();
    if (immediate) {
      finish({ ok: true, action, snapshot: immediate, rereads });
      return;
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
  if (action === "filter_marker") {
    const controls = markerFilterControls(documentRef);
    const option = markerOption(control, request.marker);
    if (!controls?.submit) return navigationError("MARKER_FILTER_NOT_FOUND", "the marker filter Consultar control is unavailable");
    if (!option) return navigationError("MARKER_OPTION_NOT_FOUND", "the requested marker is not present in the current catalog");
    return waitForNavigation(
      documentRef,
      before,
      action,
      null,
      Number.isInteger(request.timeoutMs) && request.timeoutMs > 0 ? Math.min(request.timeoutMs, NAVIGATION_TIMEOUT_MS) : NAVIGATION_TIMEOUT_MS,
      () => {
        for (const candidate of control?.options ?? queryAll(control, "option")) candidate.selected = candidate === option;
        control.value = option.value;
        dispatchControlEvents(documentRef, control);
        controls.submit.click?.();
      },
      request.marker,
    );
  }
  if (getAttribute(control, "data-action") === "signal-only" || getAttribute(control, "data-action") === "submit") {
    return navigationError("ACTION_NOT_ALLOWED", "signal and submit controls are outside the navigation allowlist");
  }
  return waitForNavigation(
    documentRef,
    before,
    action,
    request.identity,
    Number.isInteger(request.timeoutMs) && request.timeoutMs > 0 ? Math.min(request.timeoutMs, NAVIGATION_TIMEOUT_MS) : NAVIGATION_TIMEOUT_MS,
    () => control.click?.(),
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
      const result = await executeNavigation(documentRef, message.payload);
      return result?.ok === true
        ? { ...result, navigationToken: message.requestId }
        : result;
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
    if (!["PORTAL_GET_SNAPSHOT", "PORTAL_NAVIGATE"].includes(message?.type)) return false;
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
