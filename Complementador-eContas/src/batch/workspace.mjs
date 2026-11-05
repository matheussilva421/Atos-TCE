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

function autosUrl(processId) {
  return PORTAL_ORIGIN + '/#/dashboard/processos/' + processId + '/autos';
}

function formUrl(processId) {
  return PORTAL_ORIGIN + '/#/dashboard/complementar-ato/' + processId;
}

function sameIds(ids) {
  return Boolean(ids && Number.isInteger(ids.autosTabId) && Number.isInteger(ids.formTabId));
}

/**
 * Abre ou reaproveita exatamente duas abas de trabalho do processo.
 * A aba da listagem nunca é recebida nem alterada.
 */
export async function openWorkspace({ processId, previous = null, tabsApi }) {
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
    await tabsApi.update(previous.autosTabId, { url: autosUrl(processId), active: false });
    await tabsApi.update(previous.formTabId, { url: formUrl(processId), active: false });
    return { autosTabId: previous.autosTabId, formTabId: previous.formTabId };
  }
  const autos = await tabsApi.create({ url: autosUrl(processId), active: false });
  const form = await tabsApi.create({ url: formUrl(processId), active: false });
  return { autosTabId: autos.id, formTabId: form.id };
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
