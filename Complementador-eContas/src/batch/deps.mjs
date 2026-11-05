import { PORTAL_ORIGIN } from '../shared/config.mjs';
import { MESSAGE } from '../shared/protocol.mjs';
import { openWorkspace, waitForWorkspace } from './workspace.mjs';

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
  workspaceTimeoutMs = 10000,
}) {
  const session = { workspace: null };
  return {
    storage,
    now,
    session,
    saveEnabled: executionEnabled === true,
    newAttemptId(processId) {
      return 'attempt-' + processId + '-' + now().toString(36);
    },
    async openWorkspace({ processId }) {
      const workspace = await openWorkspace({
        processId,
        previous: session.workspace,
        tabsApi: tabs,
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
      return workspace;
    },
    async selectInterested({ processId, formTabId }) {
      return sendToTab(formTabId, { type: MESSAGE.BATCH_SELECT_INTERESTED, processId });
    },
    async fill({ processId, formTabId, autosTabId }) {
      const ensured = await sendToTab(autosTabId, {
        type: MESSAGE.BATCH_ENSURE_DOCUMENT,
        expectedProcessId: processId,
      });
      if (!ensured || ensured.ok !== true) {
        return { ok: false, code: (ensured && ensured.code) || 'NO_DOCUMENT' };
      }
      const all = await tabs.query({});
      const sourceTabs = all
        .filter((tab) => tab && tab.url && tab.url.startsWith(PORTAL_ORIGIN))
        .map((tab) => ({ id: tab.id, url: tab.url, windowId: tab.windowId }));
      return fillTransaction({ processId, formTabId, autosTabId, sourceTabs });
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
    async save() {
      if (executionEnabled !== true) {
        return { attempted: false, result: 'error', code: 'SAVE_GATE_CLOSED' };
      }
      return { attempted: false, result: 'error', code: 'SAVE_ADAPTER_NOT_WIRED' };
    },
    async verify() {
      return { status: 'unknown', evidence: [] };
    },
  };
}
