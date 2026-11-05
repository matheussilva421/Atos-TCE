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
import { createBatchDriver } from './batch-runner.mjs';

const transactions = new TransactionManager({ timeoutMs: 180000 });
let diagnosticRecorder = null;
let batchController = null;
let batchDriver = null;

const BATCH_TYPES = new Set([
  MESSAGE.BATCH_PREVIEW,
  MESSAGE.BATCH_START,
  MESSAGE.BATCH_STATUS,
  MESSAGE.BATCH_PAUSE,
  MESSAGE.BATCH_STOP,
  MESSAGE.BATCH_RESUME,
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
    sendToTab: (tabId, payload) => chrome.tabs.sendMessage(tabId, payload),
    runFillTransaction,
    readDocumentCache,
    writeDocumentCache,
    extractFields,
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
      const started = await controller.start({ ...command, limits: message.limits, expectedContextKey: message.contextKey });
      if (started && started.ok) {
        const driver = getBatchDriver();
        if (driver) {
          void driver.drive(started.batchId);
        }
      }
      return started;
    }
    case MESSAGE.BATCH_STATUS:
      return controller.status(command);
    case MESSAGE.BATCH_PAUSE:
      return controller.pause({ ...command, batchId: message.batchId, revision: message.revision });
    case MESSAGE.BATCH_STOP:
      return controller.stop({ ...command, batchId: message.batchId, revision: message.revision });
    case MESSAGE.BATCH_RESUME: {
      const resumed = await controller.resume({ ...command, batchId: message.batchId, revision: message.revision });
      if (resumed && resumed.ok) {
        const driver = getBatchDriver();
        if (driver) {
          void driver.drive(resumed.batchId);
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
    return { ok: false, code: 'STALE_TRANSACTION' };
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
