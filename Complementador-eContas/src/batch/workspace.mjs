import { PORTAL_ORIGIN } from '../shared/config.mjs';
import { isValidProcessId } from '../shared/identity.mjs';
import { parseRoute } from '../shared/routes.mjs';

export class WorkspaceError extends Error {
  constructor(code) {
    super(code);
    this.name = 'WorkspaceError';
    this.code = code;
  }
}

// Rota documentada como observada em 03/11/2026 (docs/evidence/dom-contract.md):
// /#/dashboard/processos/<id>/autos. Não foi revalidada em 05/11/2026; a varredura
// dos chunks carregados não a contradiz (rotas do Angular não ficam no chunk inicial).
function autosUrl(processId) {
  return PORTAL_ORIGIN + '/#/dashboard/processos/' + processId + '/autos';
}

export function formUrlFor(processId) {
  return PORTAL_ORIGIN + '/#/dashboard/complementar-ato/' + processId;
}

function sameIds(ids) {
  return Boolean(ids && Number.isInteger(ids.autosTabId) && Number.isInteger(ids.formTabId));
}

/**
 * Abre ou reaproveita exatamente duas abas de trabalho do processo.
 * A aba da listagem nunca é recebida nem alterada.
 */
export async function openWorkspace({
  processId, previous = null, tabsApi, fresh = false, keepTabIds = [], windowId = null,
}) {
  if (!isValidProcessId(processId)) {
    throw new WorkspaceError('INVALID_PROCESS');
  }
  if (!tabsApi || typeof tabsApi.create !== 'function') {
    throw new WorkspaceError('INVALID_TABS_API');
  }
  if (sameIds(previous)) {
    if (previous.autosTabId === previous.formTabId) {
      throw new WorkspaceError('INVALID_WORKSPACE');
    }
    if (fresh) {
      for (const tabId of [previous.autosTabId, previous.formTabId]) {
        if (keepTabIds.includes(tabId)) {
          continue;
        }
        if (typeof tabsApi.remove === 'function') {
          try {
            await tabsApi.remove(tabId);
          } catch {
            // A aba pode já ter sido fechada.
          }
        }
      }
    } else {
      await tabsApi.update(previous.autosTabId, { url: autosUrl(processId), active: false });
      await tabsApi.update(previous.formTabId, { url: formUrlFor(processId), active: false });
      return { autosTabId: previous.autosTabId, formTabId: previous.formTabId };
    }
  }
  const properties = (url) => {
    const value = { url, active: false };
    if (Number.isInteger(windowId)) {
      value.windowId = windowId;
    }
    return value;
  };
  const autos = await tabsApi.create(properties(autosUrl(processId)));
  const form = await tabsApi.create(properties(formUrlFor(processId)));
  return {
    autosTabId: autos.id,
    formTabId: form.id,
    ...(Number.isInteger(autos.windowId) ? { windowId: autos.windowId } : {}),
  };
}

export async function verifyWorkspace({ processId, ids, tabsApi }) {
  if (!isValidProcessId(processId) || !sameIds(ids)) {
    return { ok: false, code: 'INVALID_WORKSPACE' };
  }
  if (ids.autosTabId === ids.formTabId) {
    return { ok: false, code: 'INVALID_WORKSPACE' };
  }
  let autos;
  let form;
  try {
    autos = await tabsApi.get(ids.autosTabId);
    form = await tabsApi.get(ids.formTabId);
  } catch {
    return { ok: false, code: 'TAB_CLOSED' };
  }
  const autosRoute = parseRoute(autos && autos.url ? autos.url : '');
  const formRoute = parseRoute(form && form.url ? form.url : '');
  if (!autosRoute || autosRoute.kind !== 'autos' || autosRoute.idProcesso !== processId) {
    return { ok: false, code: 'WRONG_PROCESS_TAB' };
  }
  if (!formRoute || formRoute.kind !== 'complemento' || formRoute.idProcesso !== processId) {
    return { ok: false, code: 'WRONG_PROCESS_TAB' };
  }
  return { ok: true };
}

/**
 * Aguarda a aba recém-criada/atualizada expor a URL do processo. Imediatamente
 * após tabs.create/update, tab.url pode estar vazio; verificar uma única vez
 * produziria WRONG_PROCESS_TAB falso-positivo.
 */
export async function waitForWorkspace({
  processId,
  ids,
  tabsApi,
  timeoutMs = 10000,
  pollMs = 200,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
}) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const result = await verifyWorkspace({ processId, ids, tabsApi });
    if (result.ok || Date.now() >= deadline) {
      return result;
    }
    await sleep(pollMs);
  }
}

/**
 * No máximo uma restauração, e nunca depois de uma tentativa de salvamento.
 */
export async function recoverWorkspaceOnce({
  processId, ids, tabsApi, saveAttempted, alreadyRecovered,
}) {
  if (saveAttempted) {
    return { ok: false, code: 'SAVE_ATTEMPTED' };
  }
  if (alreadyRecovered) {
    return { ok: false, code: 'RECOVERY_EXHAUSTED' };
  }
  const workspace = await openWorkspace({ processId, previous: null, tabsApi });
  return { ok: true, workspace };
}
