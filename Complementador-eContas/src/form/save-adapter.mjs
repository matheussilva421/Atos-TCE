import { normalizeText } from '../shared/identity.mjs';
import { parseRoute } from '../shared/routes.mjs';

const SAVE_LABEL = 'complementar ato';
const DIALOG_SELECTOR = '.modal.show, ngb-modal-window, .swal2-popup';

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
  return doc.querySelector(DIALOG_SELECTOR);
}

function dialogMatches(dialog, knownDialog) {
  if (!dialog || !knownDialog) {
    return false;
  }
  const title = dialog.querySelector('.modal-title, h1, h2, h3, h4, .swal2-title');
  const titleText = normalizeText(title ? title.textContent : '');
  const confirm = [...dialog.querySelectorAll('button, a.btn')]
    .find((element) => normalizeText(element.textContent).toLowerCase()
      === normalizeText(knownDialog.confirmText).toLowerCase()) || null;
  return titleText === normalizeText(knownDialog.title) && Boolean(confirm);
}

/**
 * Lê a UI de salvamento observada no portal: botão "Complementar ato".
 * Diálogos conhecidos ainda não foram homologados; portanto o padrão é falhar fechado.
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
 * Executa no máximo um clique por tentativa. Nunca confirma diálogo desconhecido
 * e sinaliza 'unknown' quando não há prova de sucesso.
 */
export async function clickComplementarAtoOnce(doc, expected, deps = {}) {
  const route = parseRoute(locationHref(doc));
  if (!expected || !route || route.kind !== 'complemento' || route.idProcesso !== expected.processId) {
    return { attempted: false, result: 'error', code: 'DIFFERENT_PROCESS' };
  }
  if (typeof expected.attemptId !== 'string' || expected.attemptId.length < 6) {
    return { attempted: false, result: 'error', code: 'INVALID_ATTEMPT' };
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
    if (dialogMatches(dialog, expected.knownDialog)) {
      const confirm = [...dialog.querySelectorAll('button, a.btn')]
        .find((element) => normalizeText(element.textContent).toLowerCase()
          === normalizeText(expected.knownDialog.confirmText).toLowerCase());
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
