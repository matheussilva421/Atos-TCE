import { createRunnerDeps } from '../batch/deps.mjs';
import { runOneStep } from '../batch/runner.mjs';
import { createRequestId, MESSAGE } from '../shared/protocol.mjs';

export const BATCH_EXECUTION_ENABLED = false;

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
  saveEnabled = false,
  maxSteps = 25,
}) {
  return {
    enabled: driveEnabled === true,
    async drive(batchId) {
      if (driveEnabled !== true) {
        return { state: 'DISABLED', steps: 0 };
      }
      const deps = createRunnerDeps({
        storage,
        tabs,
        sendToTab,
        executionEnabled: saveEnabled === true,
        fillTransaction: async ({ processId, formTabId, autosTabId }) => {
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
            requestId: createRequestId(),
            formSnapshot: snapshot.snapshot,
            sendToSource: (tabId, payload) => sendToTab(tabId, payload),
            sendToForm: (tabId, payload) => sendToTab(tabId, payload),
            extract: extractFields,
            timeoutMs: 20000,
            documentTimeoutMs: 90000,
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
      let steps = 0;
      for (; steps < maxSteps; steps += 1) {
        const result = await runOneStep({ batchId, deps });
        if (!result.needsWake) {
          return { state: result.state, steps: steps + 1 };
        }
      }
      return { state: 'STEP_LIMIT', steps };
    },
  };
}
