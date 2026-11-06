import { PORTAL_ORIGIN } from '../shared/config.mjs';
import { createRequestId, MESSAGE } from '../shared/protocol.mjs';
import { formUrlFor, openWorkspace, waitForWorkspace } from './workspace.mjs';

async function verifyInFreshTab({ tabs, sendToTab, processId, attemptId }) {
  if (!tabs || typeof tabs.create !== 'function' || typeof sendToTab !== 'function') {
    return { status: 'unknown', evidence: ['VERIFY_UNAVAILABLE'] };
  }
  let tab = null;
  try {
    tab = await tabs.create({ url: formUrlFor(processId), active: false });
    if (!tab || !Number.isInteger(tab.id)) {
      return { status: 'unknown', evidence: ['VERIFY_TAB_FAILED'] };
    }
    const result = await sendToTab(tab.id, {
      type: MESSAGE.BATCH_VERIFY_SAVED,
      processId,
      attemptId,
    });
    if (!result || result.ok !== true) {
      return { status: 'unknown', evidence: ['VERIFY_READ_FAILED'] };
    }
    if (result.processId !== processId) {
      return { status: 'unknown', evidence: ['VERIFY_WRONG_PROCESS'] };
    }
    if (result.hasForm !== true) {
      return { status: 'unknown', evidence: ['VERIFY_FORM_NOT_RENDERED'] };
    }
    if (result.saveButtonPresent !== false) {
      return { status: 'unknown', evidence: ['VERIFY_SAVE_BUTTON_PRESENT'] };
    }
    return {
      status: 'confirmed',
      evidence: ['fresh_tab', 'form_present', 'save_button_absent'],
      at: Date.now(),
    };
  } catch {
    return { status: 'unknown', evidence: ['VERIFY_FAILED'] };
  } finally {
    if (tab && Number.isInteger(tab.id) && typeof tabs.remove === 'function') {
      try {
        await tabs.remove(tab.id);
      } catch {
        // A aba de verificação é descartável.
      }
    }
  }
}

/**
 * Adapta as APIs do navegador às dependências do runner. A execução real e o
 * salvamento continuam desligados até homologação; o adaptador de salvamento
 * só será conectado quando o diálogo real estiver autorizado.
 */
export function createRunnerDeps({
  storage,
  tabs,
  sendToTab,
  fillTransaction,
  now = () => Date.now(),
  executionEnabled = false,
  verify = null,
  workspaceTimeoutMs = 30000,
  ensureRetryDelayMs = 1000,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  beginTransaction = null,
  finishTransaction = null,
  saveTransaction = null,
}) {
  const session = { workspace: null, processId: null, interestedKey: null };
  const keepForms = new Set();
  const keepAutos = new Set();
  return {
    storage,
    now,
    session,
    markFilled() {
      if (session.workspace) {
        keepForms.add(session.workspace.formTabId);
      }
    },
    keepWorkspace({ processId }) {
      if (session.workspace && session.processId === processId) {
        keepForms.add(session.workspace.formTabId);
        keepAutos.add(session.workspace.autosTabId);
      }
    },
    async cleanupWorkspace({ processId, status }) {
      const workspace = session.workspace;
      if (!workspace || session.processId !== processId || status !== 'CONFIRMED') {
        return { closed: 0 };
      }
      let closed = 0;
      if (typeof tabs.remove === 'function') {
        for (const tabId of [workspace.autosTabId, workspace.formTabId]) {
          try {
            await tabs.remove(tabId);
            closed += 1;
          } catch {
            // A aba pode já ter sido fechada.
          }
        }
      }
      session.workspace = null;
      session.processId = null;
      session.interestedKey = null;
      return { closed };
    },
    saveEnabled: executionEnabled === true,
    newAttemptId(processId) {
      return 'attempt-' + processId + '-' + now().toString(36);
    },
    async openWorkspace({ processId }) {
      const workspace = await openWorkspace({
        processId,
        previous: session.workspace,
        tabsApi: tabs,
        fresh: true,
        keepTabIds: [...keepForms, ...keepAutos],
      });
      const verified = await waitForWorkspace({
        processId,
        ids: workspace,
        tabsApi: tabs,
        timeoutMs: workspaceTimeoutMs,
      });
      if (!verified.ok) {
        const error = new Error(verified.code);
        error.code = verified.code;
        throw error;
      }
      session.workspace = workspace;
      session.processId = processId;
      return workspace;
    },
    async selectInterested({ processId, formTabId }) {
      const result = await sendToTab(formTabId, { type: MESSAGE.BATCH_SELECT_INTERESTED, processId });
      if (result && result.ok === true && typeof result.interestedKey === 'string') {
        session.interestedKey = result.interestedKey;
      }
      return result;
    },
    async fill({ processId, formTabId, autosTabId }) {
      const requestId = createRequestId();
      if (typeof beginTransaction === 'function'
        && beginTransaction(autosTabId, requestId) === false) {
        return { ok: false, code: 'BUSY' };
      }
      try {
      const requestEnsure = () => sendToTab(autosTabId, {
        type: MESSAGE.BATCH_ENSURE_DOCUMENT,
        expectedProcessId: processId,
      });
      let ensured = await requestEnsure();
      if (!ensured || ensured.ok !== true) {
        const code = ensured && ensured.code ? ensured.code : 'ENSURE_UNDEFINED';
        const retryable = code === 'NO_DOCUMENT' || code === 'NO_EVENT_CARD' || code.startsWith('ENSURE_');
        if (!retryable) {
          return { ok: false, code };
        }
        await sleep(ensureRetryDelayMs);
        ensured = await requestEnsure();
      }
      if (!ensured || ensured.ok !== true) {
        return {
          ok: false,
          code: ensured === undefined
            ? 'ENSURE_UNDEFINED'
            : 'ENSURE_' + String(ensured.code || 'NO_CODE'),
        };
      }
      const all = await tabs.query({});
      const sourceTabs = all
        .filter((tab) => tab && tab.url && tab.url.startsWith(PORTAL_ORIGIN))
        .map((tab) => ({ id: tab.id, url: tab.url, windowId: tab.windowId }));
      return fillTransaction({ processId, formTabId, autosTabId, sourceTabs, requestId });
      } finally {
        if (typeof finishTransaction === 'function') {
          finishTransaction(autosTabId, requestId);
        }
      }
    },
    async validate({ processId, formTabId, interestedKey }) {
      const response = await sendToTab(formTabId, {
        type: MESSAGE.BATCH_VALIDATE_FORM,
        processId,
        interestedKey,
      });
      if (!response || !response.ok) {
        return response || { ok: false, code: 'FORM_VALIDATION_FAILED' };
      }
      return { ok: true };
    },
    async save({ processId, attemptId }) {
      if (executionEnabled !== true) {
        return { attempted: false, result: 'error', code: 'SAVE_GATE_CLOSED' };
      }
      if (typeof saveTransaction === 'function') {
        return saveTransaction({ processId, attemptId });
      }
      return { attempted: false, result: 'error', code: 'SAVE_ADAPTER_NOT_WIRED' };
    },
    async verify(args) {
      if (typeof verify === 'function') {
        return verify(args);
      }
      return verifyInFreshTab({
        tabs,
        sendToTab,
        processId: args && args.processId,
        attemptId: args && args.attemptId,
      });
    },
  };
}
