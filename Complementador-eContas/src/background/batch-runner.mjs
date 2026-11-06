import { createRunnerDeps } from '../batch/deps.mjs';
import { runOneStep } from '../batch/runner.mjs';
import { createRequestId, MESSAGE } from '../shared/protocol.mjs';

export const BATCH_EXECUTION_ENABLED = typeof __BATCH_EXECUTION__ === 'boolean'
  ? __BATCH_EXECUTION__
  : false;
export const BATCH_FILL_ONLY = typeof __BATCH_FILL_ONLY__ === 'boolean'
  ? __BATCH_FILL_ONLY__
  : false;
export const BATCH_SAVE_ENABLED = typeof __BATCH_SAVE__ === 'boolean'
  ? __BATCH_SAVE__
  : false;

/**
 * Monta as dependências reais do runner e conduz os passos. Permanece desligado
 * até a homologação: com o flag falso, nenhuma aba é aberta e nenhum campo é escrito.
 */
export function createBatchDriver({
  storage,
  tabs,
  sendToTab,
  runFillTransaction,
  readDocumentCache,
  writeDocumentCache,
  extractFields,
  driveEnabled = BATCH_EXECUTION_ENABLED,
  saveEnabled = BATCH_SAVE_ENABLED,
  verify = null,
  maxSteps = 200,
  beginTransaction = null,
  finishTransaction = null,
}) {
  let deps = null;
  const getDeps = () => {
    if (!deps) {
      deps = createRunnerDeps({
        storage,
        tabs,
        sendToTab,
        executionEnabled: saveEnabled === true,
        verify,
        beginTransaction,
        finishTransaction,
        saveTransaction: async ({ processId, attemptId }) => {
          const values = await storage.get('complementadorKnownDialog').catch(() => ({}));
          const knownDialog = values && values.complementadorKnownDialog
            ? values.complementadorKnownDialog
            : null;
          const workspace = deps && deps.session ? deps.session.workspace : null;
          if (!workspace || !workspace.formTabId) {
            return { attempted: false, result: 'error', code: 'NO_FORM_TAB' };
          }
          return sendToTab(workspace.formTabId, {
            type: MESSAGE.BATCH_SAVE,
            processId,
            attemptId,
            knownDialog,
          });
        },
        fillTransaction: async ({ processId, formTabId, autosTabId, requestId }) => {
          const formTab = await tabs.get(formTabId);
          const autosTab = await tabs.get(autosTabId);
          const snapshot = await sendToTab(formTabId, {
            type: MESSAGE.BATCH_FORM_SNAPSHOT,
            processId,
          });
          if (!snapshot || snapshot.ok !== true || !snapshot.snapshot) {
            return { ok: false, code: (snapshot && snapshot.code) || 'FORM_NOT_READY' };
          }
          const cached = typeof readDocumentCache === 'function'
            ? await readDocumentCache(processId)
            : null;
          const result = await runFillTransaction({
            formTab,
            sourceTabs: [autosTab],
            requestId,
            formSnapshot: snapshot.snapshot,
            sendToSource: (tabId, payload) => sendToTab(tabId, payload),
            sendToForm: (tabId, payload) => sendToTab(tabId, payload),
            extract: extractFields,
            timeoutMs: 60000,
            documentTimeoutMs: 300000,
            cached,
            applyMessageType: MESSAGE.BATCH_APPLY,
            onDocumentsFound: (ids) => {
              if (typeof writeDocumentCache === 'function') {
                writeDocumentCache(processId, ids);
              }
            },
          });
          if (result && result.ok === true) {
            return { ok: true, report: result.report };
          }
          return {
            ok: false,
            code: (result && result.error && result.error.code) || 'FILL_FAILED',
          };
        },
      });
    }
    return deps;
  };
  return {
    enabled: driveEnabled === true || BATCH_FILL_ONLY === true,
    async drive(batchId) {
      const canDrive = driveEnabled === true || BATCH_FILL_ONLY === true;
      const canSave = BATCH_FILL_ONLY === true ? false : saveEnabled === true;
      if (!canDrive) {
        return { state: 'DISABLED', steps: 0 };
      }
      const activeDeps = { ...getDeps(), saveEnabled: canSave };
      let steps = 0;
      for (; steps < maxSteps; steps += 1) {
        const result = await runOneStep({ batchId, deps: activeDeps });
        if (!result.needsWake) {
          return { state: result.state, steps: steps + 1 };
        }
      }
      return { state: 'STEP_LIMIT', steps };
    },
  };
}
