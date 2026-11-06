import { normalizeText } from '../shared/identity.mjs';
import { parseRoute } from '../shared/routes.mjs';

const SAVE_LABEL = 'complementar ato';
const DIALOG_SELECTOR = '.modal.show, ngb-modal-window, .swal2-popup';

export const HOMOLOGATED_DIALOG = Object.freeze({
  title: 'Complementar ato',
  confirmText: 'sim, complementar',
  cancelText: 'NÃO',
});

function locationHref(doc) {
  return (doc && doc.location && doc.location.href)
    || (doc && doc.defaultView && doc.defaultView.location && doc.defaultView.location.href)
    || '';
}

function findSaveButton(doc) {
  return [...doc.querySelectorAll('button, a.btn')]
    .find((element) => normalizeText(element.textContent).toLowerCase() === SAVE_LABEL) || null;
}

function findDialog(doc) {
  return [...doc.querySelectorAll(DIALOG_SELECTOR)].find((dialog) => !dialog.hidden) || null;
}

function normalizeKnownDialog(value) {
  if (!value || typeof value !== 'object') {
    return HOMOLOGATED_DIALOG;
  }
  const title = normalizeText(value.title).toLowerCase();
  const confirmText = normalizeText(value.confirmText).toLowerCase();
  const cancelText = normalizeText(value.cancelText).toLowerCase();
  if (title !== normalizeText(HOMOLOGATED_DIALOG.title).toLowerCase()) {
    return null;
  }
  if (confirmText !== normalizeText(HOMOLOGATED_DIALOG.confirmText).toLowerCase()) {
    return null;
  }
  if (cancelText && cancelText !== normalizeText(HOMOLOGATED_DIALOG.cancelText).toLowerCase()) {
    return null;
  }
  return HOMOLOGATED_DIALOG;
}

function isStructuredDialog(dialog) {
  if (!dialog || dialog.hidden) {
    return false;
  }
  const tag = dialog.tagName.toLowerCase();
  const role = dialog.getAttribute('role');
  const ariaModal = dialog.getAttribute('aria-modal');
  if (tag === 'ngb-modal-window') {
    return role === 'dialog' || ariaModal === 'true';
  }
  return role === 'dialog';
}

function dialogButtons(dialog) {
  return [...dialog.querySelectorAll('button, a.btn')];
}

function buttonWithText(dialog, text) {
  const expected = normalizeText(text).toLowerCase();
  return dialogButtons(dialog).filter((element) => normalizeText(element.textContent).toLowerCase() === expected);
}

function dialogMatches(dialog, knownDialog) {
  if (!dialog || !knownDialog || !isStructuredDialog(dialog)) {
    return false;
  }
  const title = dialog.querySelector('.modal-title, h1, h2, h3, h4, .swal2-title');
  if (!title) {
    return false;
  }
  const titleText = normalizeText(title.textContent).toLowerCase();
  if (titleText !== normalizeText(knownDialog.title).toLowerCase()) {
    return false;
  }
  const confirm = buttonWithText(dialog, knownDialog.confirmText);
  const cancel = buttonWithText(dialog, knownDialog.cancelText);
  if (confirm.length !== 1 || cancel.length < 1) {
    return false;
  }
  const button = confirm[0];
  return !(button.disabled || button.getAttribute('aria-disabled') === 'true');
}

/**
 * Lê a UI de salvamento observada no portal: botão "Complementar ato".
 */
export function inspectSaveUi(doc) {
  const button = findSaveButton(doc);
  if (!button) {
    return { state: 'unknown', reason: 'SAVE_BUTTON_NOT_FOUND' };
  }
  if (button.disabled || button.getAttribute('aria-disabled') === 'true') {
    return { state: 'blocked', reason: 'SAVE_BUTTON_DISABLED' };
  }
  return { state: 'ready' };
}

/**
 * Executa no máximo um clique por tentativa. Aceita apenas o contrato de diálogo
 * homologado em H2; qualquer variação de título, confirmação, cancelamento ou
 * estrutura retorna 'unknown' e não confirma. Um ack de UI não prova salvamento.
 */
export async function clickComplementarAtoOnce(doc, expected, deps = {}) {
  const route = parseRoute(locationHref(doc));
  if (!expected || !route || route.kind !== 'complemento' || route.idProcesso !== expected.processId) {
    return { attempted: false, result: 'error', code: 'DIFFERENT_PROCESS' };
  }
  if (typeof expected.attemptId !== 'string' || expected.attemptId.length < 6) {
    return { attempted: false, result: 'error', code: 'INVALID_ATTEMPT' };
  }
  const knownDialog = normalizeKnownDialog(expected.knownDialog);
  if (!knownDialog) {
    return { attempted: false, result: 'unknown', code: 'DIALOG_CONTRACT_UNKNOWN' };
  }
  const dispatched = deps.dispatched instanceof Set ? deps.dispatched : null;
  if (dispatched && dispatched.has(expected.attemptId)) {
    return { attempted: false, result: 'unknown', code: 'ALREADY_ATTEMPTED' };
  }
  const ui = inspectSaveUi(doc);
  if (ui.state !== 'ready') {
    return { attempted: false, result: 'error', code: ui.reason };
  }
  const button = findSaveButton(doc);
  if (dispatched) {
    dispatched.add(expected.attemptId);
  }
  button.click();
  const wait = deps.wait || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  await wait(Number.isFinite(deps.settleMs) ? deps.settleMs : 120);

  const dialog = findDialog(doc);
  if (dialog) {
    if (dialogMatches(dialog, knownDialog)) {
      const confirm = buttonWithText(dialog, knownDialog.confirmText)[0];
      confirm.click();
      await wait(60);
      return { attempted: true, result: 'ack' };
    }
    return { attempted: true, result: 'unknown', code: 'UNKNOWN_DIALOG' };
  }
  const error = doc.querySelector('.alert-danger, .alert.alert-danger, tce-error-msg .text-danger');
  if (error && normalizeText(error.textContent)) {
    return { attempted: true, result: 'error', code: 'PORTAL_ERROR' };
  }
  return { attempted: true, result: 'unknown', code: 'NO_ACK' };
}

/**
 * Prova de resultado só existe com evidência explicitamente homologada.
 * Sem isso, o status permanece 'unknown' e o lote suspende.
 */
export function observeSaveOutcome(doc, expected = {}) {
  const selector = expected.confirmedSelector;
  if (typeof selector === 'string' && selector.length > 0) {
    const element = doc.querySelector(selector);
    if (element) {
      return { status: 'confirmed', evidence: [selector] };
    }
  }
  return { status: 'unknown', evidence: [] };
}
