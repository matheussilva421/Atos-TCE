import { extractFields } from '../extract/fields.mjs';
import { parsePdfUrl } from '../autos/pdf-identity.mjs';
import { fetchPdfBytes } from './pdf-fetch.mjs';
import { PORTAL_ORIGIN, PDF_ORIGIN } from '../shared/config.mjs';
import { createDiagnosticRecorder, DIAGNOSTIC_STATES } from '../shared/diagnostic-store.mjs';
import { MESSAGE, errorResult, isRequestId } from '../shared/protocol.mjs';
import { DOCUMENT_CACHE_KEY, cacheMatches, mergeCacheEntry } from './document-cache.mjs';
import { parseRoute } from '../shared/routes.mjs';
import { runDocumentDiagnostic, runFillTransaction, TransactionManager } from './bridge.mjs';
import { BatchController } from '../batch/controller.mjs';
import { createBatchDriver, BATCH_SAVE_ENABLED } from './batch-runner.mjs';
import { retryAsync } from '../shared/retry.mjs';
import { createDriveTracker } from '../batch/runtime-state.mjs';
import { createTabSender } from '../batch/tab-sender.mjs';
import { isBatchFetchAllowed } from '../batch/runtime-state.mjs';
import { loadBatch, saveBatch } from '../batch/journal.mjs';
import { reduceBatch } from '../batch/state-machine.mjs';
import { decideWake, WAKE_MARKER_KEY } from '../batch/lifecycle.mjs';
import { FILTER_PRESET_KEY, isKnownPresetRoute, presetKeyFor, sanitizePreset } from '../list/filter-preset.mjs';

const transactions = new TransactionManager({ timeoutMs: 180000 });
let diagnosticRecorder = null;
let batchController = null;
let batchDriver = null;
const driveTracker = createDriveTracker();

function startDrive(driver, batchId) {
  if (!driver) {
    return;
  }
  void driver.drive(batchId).then(
    (result) => driveTracker.record(result),
    (error) => driveTracker.fail(error),
  );
}

let wakePromise = null;

async function initializeWake() {
  if (wakePromise) {
    return wakePromise;
  }
  wakePromise = (async () => {
    let marker = null;
    try {
      if (chrome.storage && chrome.storage.session) {
        const values = await chrome.storage.session.get(WAKE_MARKER_KEY);
        marker = values ? values[WAKE_MARKER_KEY] : null;
        await chrome.storage.session.set({
          [WAKE_MARKER_KEY]: { runtimeId: chrome.runtime.id, at: Date.now() },
        });
      }
    } catch {
      return { action: 'unavailable', reason: 'session_storage_failed' };
    }
    let batch = null;
    try {
      batch = await loadBatch(chrome.storage.local);
    } catch {
      return { action: 'unavailable', reason: 'journal_unavailable' };
    }
    const decision = decideWake({ batch, sessionMarker: marker, runtimeId: chrome.runtime.id });
    if (decision.action === 'suspend' && batch) {
      try {
        await saveBatch(chrome.storage.local, reduceBatch(batch, { type: 'SUSPEND', at: Date.now() }));
      } catch {
        return { action: 'unavailable', reason: 'suspend_failed' };
      }
    }
    if (decision.action === 'drive' && batch) {
      const driver = getBatchDriver();
      if (driver) {
        startDrive(driver, batch.batchId);
      }
    }
    return decision;
  })();
  return wakePromise;
}

void initializeWake();
if (chrome.runtime.onStartup && typeof chrome.runtime.onStartup.addListener === 'function') {
  chrome.runtime.onStartup.addListener(() => { void initializeWake(); });
}

const BATCH_TYPES = new Set([
  MESSAGE.BATCH_PREVIEW,
  MESSAGE.BATCH_START,
  MESSAGE.BATCH_STATUS,
  MESSAGE.BATCH_PAUSE,
  MESSAGE.BATCH_STOP,
  MESSAGE.BATCH_RESUME,
  MESSAGE.BATCH_RECONCILE_EXTERNAL,
]);

function getBatchController() {
  if (batchController) {
    return batchController;
  }
  if (!chrome.storage || !chrome.storage.local) {
    return null;
  }
  batchController = new BatchController({
    storage: chrome.storage.local,
    runtimeId: chrome.runtime.id,
    newBatchId: () => 'batch-' + Date.now() + '-' + Math.random().toString(16).slice(2, 8),
    sendToTab: (tabId, payload) => chrome.tabs.sendMessage(tabId, payload),
    now: () => Date.now(),
    saveEnabled: BATCH_SAVE_ENABLED,
  });
  return batchController;
}

function getBatchDriver() {
  if (batchDriver) {
    return batchDriver;
  }
  if (!chrome.storage || !chrome.storage.local) {
    return null;
  }
  batchDriver = createBatchDriver({
    storage: chrome.storage.local,
    tabs: chrome.tabs,
    sendToTab: createTabSender((tabId, payload) => chrome.tabs.sendMessage(tabId, payload), { attempts: 160, delayMs: 250 }),
    runFillTransaction,
    readDocumentCache,
    writeDocumentCache,
    extractFields,
    saveEnabled: BATCH_SAVE_ENABLED,
    beginTransaction: (tabId, requestId) => transactions.begin(tabId, requestId),
    finishTransaction: (tabId, requestId) => transactions.finish(tabId, requestId),
  });
  return batchDriver;
}

try {
  if (chrome.storage && chrome.storage.local && typeof chrome.storage.local.setAccessLevel === 'function') {
    chrome.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' }).catch(() => {});
  }
} catch {
  // Versões sem setAccessLevel continuam funcionando; o diário não é enviado a content scripts.
}

async function handleBatchCommand(message, sender) {
  await initializeWake();
  const controller = getBatchController();
  if (!controller) {
    return { ok: false, code: 'STORAGE_UNAVAILABLE' };
  }
  const command = {
    sender: {
      id: sender && sender.id,
      tab: sender && sender.tab ? { id: sender.tab.id, url: sender.tab.url } : null,
    },
  };
  switch (message.type) {
    case MESSAGE.BATCH_PREVIEW:
      return controller.preview(command);
    case MESSAGE.BATCH_START: {
      const started = await controller.start({ ...command, limits: message.limits, expectedContextKey: message.contextKey, keepProblemTabs: message.keepProblemTabs });
      if (started && started.ok) {
        const driver = getBatchDriver();
        if (driver) {
          startDrive(driver, started.batchId);
        }
      }
      return {
        ...started,
        driverEnabled: Boolean(getBatchDriver() && getBatchDriver().enabled),
        lastDrive: driveTracker.read(),
      };
    }
    case MESSAGE.BATCH_STATUS:
      {
        const current = await controller.status(command);
        if (current && current.ok && current.state === 'RUNNING') {
          const driver = getBatchDriver();
          if (driver) {
            startDrive(driver, current.batchId);
          }
        }
        const driver = getBatchDriver();
        return {
          ...current,
          driverEnabled: Boolean(driver && driver.enabled),
          lastDrive: driveTracker.read(),
        };
      }
    case MESSAGE.BATCH_PAUSE:
      return controller.pause({ ...command, batchId: message.batchId, revision: message.revision });
    case MESSAGE.BATCH_STOP:
      return controller.stop({ ...command, batchId: message.batchId, revision: message.revision });
    case MESSAGE.BATCH_RECONCILE_EXTERNAL:
      return controller.reconcileExternal({
        ...command,
        batchId: message.batchId,
        revision: message.revision,
        processIds: message.processIds,
      });
    case MESSAGE.BATCH_RESUME: {
      const resumed = await controller.resume({ ...command, batchId: message.batchId, revision: message.revision });
      if (resumed && resumed.ok) {
        const driver = getBatchDriver();
        if (driver) {
          startDrive(driver, resumed.batchId);
        }
      }
      return resumed;
    }
    default:
      return { ok: false, code: 'UNKNOWN_BATCH_COMMAND' };
  }
}

async function readDocumentCache(processId) {
  if (!chrome.storage || !chrome.storage.session) {
    return null;
  }
  try {
    const values = await chrome.storage.session.get(DOCUMENT_CACHE_KEY);
    const value = values ? values[DOCUMENT_CACHE_KEY] : null;
    if (!cacheMatches(value, processId)) {
      return null;
    }
    return {
      processHash: value.processHash,
      resolutionEventId: value.resolutionEventId || null,
      guiaEventId: value.guiaEventId || null,
    };
  } catch {
    return null;
  }
}

async function writeDocumentCache(processId, ids) {
  if (!chrome.storage || !chrome.storage.session) {
    return;
  }
  try {
    const values = await chrome.storage.session.get(DOCUMENT_CACHE_KEY);
    const existing = values ? values[DOCUMENT_CACHE_KEY] : null;
    const entry = mergeCacheEntry(existing, processId, ids || {});
    if (!entry) {
      await chrome.storage.session.remove(DOCUMENT_CACHE_KEY);
      return;
    }
    await chrome.storage.session.set({
      [DOCUMENT_CACHE_KEY]: entry,
    });
  } catch {
    // O cache é opcional.
  }
}

function getDiagnosticRecorder() {
  if (diagnosticRecorder) {
    return diagnosticRecorder;
  }
  if (!chrome.storage || !chrome.storage.session) {
    return null;
  }
  try {
    diagnosticRecorder = createDiagnosticRecorder(chrome.storage.session);
  } catch {
    diagnosticRecorder = null;
  }
  return diagnosticRecorder;
}

async function resetDiagnostic() {
  const recorder = getDiagnosticRecorder();
  if (!recorder) {
    return null;
  }
  try {
    return await recorder.reset();
  } catch {
    return null;
  }
}

async function recordDiagnostic(state, details = {}) {
  const recorder = getDiagnosticRecorder();
  if (!recorder) {
    return null;
  }
  try {
    return await recorder.record(state, details);
  } catch {
    return null;
  }
}

async function readDiagnostic() {
  const recorder = getDiagnosticRecorder();
  if (!recorder) {
    return null;
  }
  try {
    return await recorder.read();
  } catch {
    return null;
  }
}

async function notifyDiagnostic(tabId) {
  const diagnostic = await readDiagnostic();
  if (!diagnostic) {
    return;
  }
  try {
    await chrome.tabs.sendMessage(tabId, { type: MESSAGE.DIAGNOSTIC_UPDATE, diagnostic });
  } catch {
    // O content script pode ainda não estar pronto; GET_DIAGNOSTIC recupera depois.
  }
}
const MAX_PDF_BYTES = 25 * 1024 * 1024;

function isTrusted(sender) {
  return Boolean(sender && sender.id === chrome.runtime.id);
}

async function handleRequestFill(message, sender) {
  if (!isTrusted(sender) || !sender.tab || !isRequestId(message.requestId)) {
    return errorResult(message.requestId || 'unknown', 'UNTRUSTED_SENDER', 'Origem não autorizada.');
  }
  const route = parseRoute(sender.tab.url, PORTAL_ORIGIN);
  if (!route || route.kind !== 'complemento') {
    return errorResult(message.requestId, 'INVALID_TARGET', 'Aba não é o Complementar Ato.');
  }
  if (!transactions.begin(sender.tab.id, message.requestId)) {
    return errorResult(message.requestId, 'BUSY', 'Já existe um preenchimento em andamento.');
  }
  try {
    const cached = await readDocumentCache(route.idProcesso);
    const tabs = await chrome.tabs.query({});
    const sourceTabs = tabs
      .filter((tab) => tab && tab.url && tab.url.startsWith(PORTAL_ORIGIN))
      .map((tab) => ({ id: tab.id, url: tab.url, windowId: tab.windowId }));
    return await runFillTransaction({
      formTab: { id: sender.tab.id, url: sender.tab.url },
      sourceTabs,
      requestId: message.requestId,
      formSnapshot: message.formSnapshot,
      sendToSource: (tabId, payload) => chrome.tabs.sendMessage(tabId, payload),
      sendToForm: (tabId, payload) => chrome.tabs.sendMessage(tabId, payload),
      extract: extractFields,
      timeoutMs: 20000,
      documentTimeoutMs: 90000,
      cached,
      onDocumentsFound: (ids) => writeDocumentCache(route.idProcesso, ids),
      isCancelled: () => !transactions.isActive(sender.tab.id, message.requestId),
    });
  } finally {
    transactions.finish(sender.tab.id, message.requestId);
  }
}

async function handleDiagnoseDocument(message, sender) {
  if (!isTrusted(sender) || !sender.tab || !isRequestId(message.requestId)) {
    return errorResult(message.requestId || 'unknown', 'UNTRUSTED_SENDER', 'Origem não autorizada.');
  }
  const route = parseRoute(sender.tab.url, PORTAL_ORIGIN);
  if (!route || route.kind !== 'complemento') {
    return errorResult(message.requestId, 'INVALID_TARGET', 'Aba não é o Complementar Ato.');
  }
  await resetDiagnostic();
  await recordDiagnostic(DIAGNOSTIC_STATES.L1_STARTED);
  if (!transactions.begin(sender.tab.id, message.requestId, 'diagnostic')) {
    await recordDiagnostic(DIAGNOSTIC_STATES.L1_ERROR, { errorCode: 'BUSY' });
    return errorResult(message.requestId, 'BUSY', 'Já existe uma operação em andamento.');
  }
  const startedAt = Date.now();
  try {
    const tabs = await chrome.tabs.query({});
    const sourceTabs = tabs
      .filter((tab) => tab && tab.url && tab.url.startsWith(PORTAL_ORIGIN))
      .map((tab) => ({ id: tab.id, url: tab.url, windowId: tab.windowId }));
    const result = await runDocumentDiagnostic({
      formTab: { id: sender.tab.id, url: sender.tab.url },
      sourceTabs,
      requestId: message.requestId,
      formSnapshot: message.formSnapshot,
      sendToSource: (tabId, payload) => chrome.tabs.sendMessage(tabId, payload),
      timeoutMs: 20000,
      isCancelled: () => !transactions.isActive(sender.tab.id, message.requestId),
      onState: (state, details) => recordDiagnostic(state, details),
    });
    const elapsedMs = Date.now() - startedAt;
    if (result && result.ok === true) {
      const diagnostic = result.diagnostic || {};
      await recordDiagnostic(DIAGNOSTIC_STATES.L1_SUCCESS, {
        pagesCount: diagnostic.pagesCount,
        totalChars: diagnostic.totalChars,
        minPageChars: diagnostic.minPageChars,
        maxPageChars: diagnostic.maxPageChars,
        byteLength: diagnostic.byteLength,
        sourceKind: diagnostic.sourceKind,
        elapsedMs,
      });
    } else {
      const code = result && result.error ? result.error.code : 'L1_ERROR';
      const state = code === 'TRANSACTION_CANCELLED'
        ? DIAGNOSTIC_STATES.L1_CANCELLED
        : String(code).includes('TIMEOUT') ? DIAGNOSTIC_STATES.L1_TIMEOUT : DIAGNOSTIC_STATES.L1_ERROR;
      await recordDiagnostic(state, { errorCode: code, elapsedMs });
    }
    await notifyDiagnostic(sender.tab.id);
    return result;
  } catch {
    await recordDiagnostic(DIAGNOSTIC_STATES.L1_ERROR, {
      errorCode: 'INTERNAL_ERROR',
      elapsedMs: Date.now() - startedAt,
    });
    await notifyDiagnostic(sender.tab.id);
    return errorResult(message.requestId, 'INTERNAL_ERROR', 'Falha interna.');
  } finally {
    transactions.finish(sender.tab.id, message.requestId);
  }
}

async function handleDiagnosticState(message, sender) {
  if (!isTrusted(sender) || !isRequestId(message.requestId)) {
    return { ok: false, code: 'UNTRUSTED_SENDER' };
  }
  if (!Object.values(DIAGNOSTIC_STATES).includes(message.state)) {
    return { ok: false, code: 'INVALID_STATE' };
  }
  const active = [...transactions.active.values()].some((entry) => (
    entry.requestId === message.requestId && entry.kind === 'diagnostic' && !entry.cancelled
  ));
  if (!active) {
    return { ok: false, code: 'STALE_TRANSACTION' };
  }
  const recorded = await recordDiagnostic(message.state, message.details || {});
  return { ok: true, recorded: Boolean(recorded) };
}

async function handleGetDiagnostic(message, sender) {
  if (!isTrusted(sender)) {
    return { ok: false, code: 'UNTRUSTED_SENDER' };
  }
  return { ok: true, diagnostic: await readDiagnostic() };
}

const BATCH_PREFS_KEY = 'complementadorBatchPrefs';

async function handleBatchPrefs(message, sender) {
  if (!isTrusted(sender)) {
    return { ok: false, code: 'UNTRUSTED_SENDER' };
  }
  if (!chrome.storage || !chrome.storage.local) {
    return { ok: false, code: 'STORAGE_UNAVAILABLE' };
  }
  if (message.type === MESSAGE.BATCH_PREFS_GET) {
    const values = await chrome.storage.local.get(BATCH_PREFS_KEY);
    const stored = values ? values[BATCH_PREFS_KEY] : null;
    return { ok: true, prefs: { keepProblemTabs: !stored || stored.keepProblemTabs !== false } };
  }
  const keepProblemTabs = Boolean(message.prefs && message.prefs.keepProblemTabs !== false);
  await chrome.storage.local.set({ [BATCH_PREFS_KEY]: { keepProblemTabs } });
  return { ok: true, prefs: { keepProblemTabs } };
}

async function handleFilterPreset(message, sender) {
  if (!isTrusted(sender)) {
    return { ok: false, code: 'UNTRUSTED_SENDER' };
  }
  if (!chrome.storage || !chrome.storage.local) {
    return { ok: false, code: 'STORAGE_UNAVAILABLE' };
  }
  const route = isKnownPresetRoute(message.route) ? message.route : 'processos-no-setor';
  const key = presetKeyFor(route);
  if (message.type === MESSAGE.FILTER_PRESET_GET) {
    const values = await chrome.storage.local.get(key);
    return { ok: true, preset: values[key] || null };
  }
  const preset = sanitizePreset(message.preset);
  if (!preset) {
    return { ok: false, code: 'INVALID_PRESET' };
  }
  await chrome.storage.local.set({ [key]: preset });
  return { ok: true };
}

const filterAutoAppliedTabs = new Set();

async function handleFilterAutoClaim(message, sender) {
  if (!isTrusted(sender) || !sender.tab || !Number.isInteger(sender.tab.id)) {
    return { apply: false };
  }
  const tabId = sender.tab.id;
  if (chrome.storage && chrome.storage.session) {
    const key = 'filterAutoApplied:' + tabId;
    const values = await chrome.storage.session.get(key);
    return { apply: !(values && values[key]) };
  }
  return { apply: !filterAutoAppliedTabs.has(tabId) };
}

async function handleFilterAutoDone(message, sender) {
  if (!isTrusted(sender) || !sender.tab || !Number.isInteger(sender.tab.id)) {
    return { ok: false };
  }
  const tabId = sender.tab.id;
  if (chrome.storage && chrome.storage.session) {
    await chrome.storage.session.set({ ['filterAutoApplied:' + tabId]: true });
  }
  filterAutoAppliedTabs.add(tabId);
  return { ok: true };
}
async function handleFetchPdf(message, sender) {
  if (!isTrusted(sender) || !sender.tab || !isRequestId(message.requestId)) {
    return { ok: false, code: 'UNTRUSTED_SENDER' };
  }
  const route = parseRoute(sender.tab.url, PORTAL_ORIGIN);
  if (!route || route.kind !== 'autos') {
    return { ok: false, code: 'INVALID_TARGET' };
  }
  if (message.expectedProcessId !== route.idProcesso) {
    return { ok: false, code: 'PROCESS_CHANGED' };
  }
  const active = [...transactions.active.values()].some((entry) => entry.requestId === message.requestId && !entry.cancelled);
  if (!active) {
    let batch = null;
    try {
      batch = await loadBatch(chrome.storage.local);
    } catch {
      batch = null;
    }
    if (!isBatchFetchAllowed(batch, message.expectedProcessId)) {
      return { ok: false, code: 'STALE_TRANSACTION' };
    }
  }
  const parsed = parsePdfUrl(message.url, PDF_ORIGIN);
  if (!parsed) {
    return { ok: false, code: 'INVALID_PDF_URL' };
  }
  return fetchPdfBytes(fetch, parsed.url, { maxBytes: MAX_PDF_BYTES });
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message.type !== 'string') {
    return false;
  }
  if (message.type === MESSAGE.REQUEST_FILL) {
    handleRequestFill(message, sender).then(
      (response) => sendResponse(response),
      () => sendResponse(errorResult(message.requestId || 'unknown', 'INTERNAL_ERROR', 'Falha interna.')),
    );
    return true;
  }
  if (message.type === MESSAGE.DIAGNOSE_DOCUMENT) {
    handleDiagnoseDocument(message, sender).then(
      (response) => sendResponse(response),
      () => sendResponse(errorResult(message.requestId || 'unknown', 'INTERNAL_ERROR', 'Falha interna.')),
    );
    return true;
  }  if (message.type === MESSAGE.DIAGNOSTIC_STATE) {
    handleDiagnosticState(message, sender).then(
      (response) => sendResponse(response),
      () => sendResponse({ ok: false, code: 'DIAGNOSTIC_STATE_FAILED' }),
    );
    return true;
  }  if (message.type === MESSAGE.GET_DIAGNOSTIC) {
    handleGetDiagnostic(message, sender).then(
      (response) => sendResponse(response),
      () => sendResponse({ ok: false, code: 'DIAGNOSTIC_READ_FAILED' }),
    );
    return true;
  }  if (message.type === MESSAGE.FETCH_PDF) {
    handleFetchPdf(message, sender).then(
      (response) => sendResponse(response),
      () => sendResponse({ ok: false, code: 'PDF_FETCH_FAILED' }),
    );
    return true;
  }
  if (BATCH_TYPES.has(message.type)) {
    handleBatchCommand(message, sender).then(
      (response) => sendResponse(response),
      () => sendResponse({ ok: false, code: 'BATCH_COMMAND_FAILED' }),
    );
    return true;
  }
  if (message.type === MESSAGE.BATCH_PREFS_GET || message.type === MESSAGE.BATCH_PREFS_SET) {
    handleBatchPrefs(message, sender).then(
      (response) => sendResponse(response),
      () => sendResponse({ ok: false, code: 'BATCH_PREFS_FAILED' }),
    );
    return true;
  }
  if (message.type === MESSAGE.FILTER_PRESET_GET || message.type === MESSAGE.FILTER_PRESET_SET) {
    handleFilterPreset(message, sender).then(
      (response) => sendResponse(response),
      () => sendResponse({ ok: false, code: 'FILTER_PRESET_FAILED' }),
    );
    return true;
  }
  if (message.type === MESSAGE.FILTER_AUTO_CLAIM) {
    handleFilterAutoClaim(message, sender).then(
      (response) => sendResponse(response),
      () => sendResponse({ apply: false }),
    );
    return true;
  }
  if (message.type === MESSAGE.FILTER_AUTO_DONE) {
    handleFilterAutoDone(message, sender).then(
      (response) => sendResponse(response),
      () => sendResponse({ ok: false }),
    );
    return true;
  }
  return false;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  const entry = transactions.get(tabId);
  if (entry && entry.kind === 'diagnostic') { return; }
  transactions.cancel(tabId, 'TAB_CLOSED');
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  const entry = transactions.get(tabId);
  if (entry && entry.kind === 'diagnostic') { return; }
  if (changeInfo.url || changeInfo.status === 'loading') {
    transactions.cancel(tabId, 'TAB_CHANGED');
  }
});
