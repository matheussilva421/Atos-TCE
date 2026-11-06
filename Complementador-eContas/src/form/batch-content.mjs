import { PORTAL_ORIGIN } from '../shared/config.mjs';
import { normalizeText } from '../shared/identity.mjs';
import { MESSAGE } from '../shared/protocol.mjs';
import { parseRoute } from '../shared/routes.mjs';
import { validateBatchReady } from './batch-validation.mjs';
import { readForm } from './form-reader.mjs';
import { selectSingleInterested } from './interested-selector.mjs';
import { clickComplementarAtoOnce, hasSaveButton } from './save-adapter.mjs';

const dispatchedAttempts = new Set();

function maskDigits(value) {
  return String(value || '').replace(/\d/g, '9').replace(/\s+/g, ' ').trim();
}

function captureDialog(doc) {
  const dialog = doc.querySelector('.modal.show, ngb-modal-window, .swal2-popup');
  if (!dialog) return null;
  const title = dialog.querySelector('.modal-title, h1, h2, h3, h4, .swal2-title');
  const buttons = [...dialog.querySelectorAll('button, a.btn')]
    .map((button) => maskDigits(normalizeText(button.textContent)))
    .filter((label) => label.length > 0)
    .slice(0, 6);
  return {
    title: maskDigits(normalizeText(title ? title.textContent : '')),
    buttons,
  };
}

export async function handleBatchSave(message, sender, doc, runtimeId) {
  if (!sender || sender.id !== runtimeId) {
    return { ok: false, code: 'UNTRUSTED_SENDER' };
  }
  const route = parseRoute(locationHref(doc), PORTAL_ORIGIN);
  if (!route || route.kind !== 'complemento') {
    return { ok: false, code: 'INVALID_TARGET' };
  }
  if (message.processId !== route.idProcesso) {
    return { ok: false, code: 'PROCESS_MISMATCH' };
  }
  let snapshot;
  try {
    snapshot = readForm(doc);
  } catch (error) {
    return { ok: false, code: error && error.code ? error.code : 'FORM_NOT_READY' };
  }
  const ready = validateBatchReady(snapshot, {
    processId: message.processId,
    interestedKey: typeof message.interestedKey === 'string' ? message.interestedKey : '',
    interestedCount: snapshot.interestedCount,
    status: 'pending',
    revisionMarker: snapshot.revisionMarker,
    visibleErrors: hasVisibleErrors(doc),
  });
  if (!ready.ok) {
    return { ok: false, code: ready.code, fields: ready.fields || [] };
  }
  const result = await clickComplementarAtoOnce(doc, {
    processId: message.processId,
    attemptId: message.attemptId,
    knownDialog: message.knownDialog || null,
  }, { dispatched: dispatchedAttempts });
  if (result.result === 'unknown' && result.code === 'UNKNOWN_DIALOG') {
    return { ok: false, code: 'DIALOG_UNKNOWN', dialog: captureDialog(doc) };
  }
  return {
    ok: result.result === 'ack',
    attempted: result.attempted,
    result: result.result,
    code: result.code || null,
  };
}

export function handleBatchVerifySaved(message, sender, doc, runtimeId) {
  if (!sender || sender.id !== runtimeId) {
    return { ok: false, code: 'UNTRUSTED_SENDER' };
  }
  const route = parseRoute(locationHref(doc), PORTAL_ORIGIN);
  if (!route || route.kind !== 'complemento') {
    return { ok: false, code: 'INVALID_TARGET' };
  }
  if (message.processId !== route.idProcesso) {
    return { ok: false, code: 'PROCESS_MISMATCH' };
  }
  const hasForm = Boolean(doc.querySelector('tce-input-field[formcontrolname="cargo"]')
    || doc.querySelector('tce-input-field[formcontrolname="dataDoeEstado"]')
    || doc.querySelector('tce-select-field.modalidade-campo')
    || doc.querySelector('form'));
  return {
    ok: true,
    processId: route.idProcesso,
    attemptId: typeof message.attemptId === 'string' ? message.attemptId : null,
    hasForm,
    saveButtonPresent: hasSaveButton(doc),
  };
}

function locationHref(doc) {
  return (doc && doc.location && doc.location.href)
    || (doc && doc.defaultView && doc.defaultView.location && doc.defaultView.location.href)
    || '';
}

function isVisible(element) {
  let node = element;
  while (node && node.nodeType === 1) {
    if (node.hidden) {
      return false;
    }
    const style = node.getAttribute ? node.getAttribute('style') : '';
    if (style && /display\s*:\s*none/i.test(style)) {
      return false;
    }
    node = node.parentElement;
  }
  return true;
}

function hasVisibleErrors(doc) {
  return [...doc.querySelectorAll('.invalid-feedback, tce-error-msg .text-danger')]
    .some((element) => normalizeText(element.textContent).length > 0 && isVisible(element));
}

/**
 * Comandos de lote aceitos pelo formulário. Devolve apenas booleanos, códigos e a
 * chave transitória do interessado; nunca persiste nem devolve nome, CPF ou valores.
 */
export async function handleBatchFormMessage(message, sender, doc, runtimeId) {
  if (!sender || sender.id !== runtimeId) {
    return { ok: false, code: 'UNTRUSTED_SENDER' };
  }
  if (!message || ![
    MESSAGE.BATCH_SELECT_INTERESTED,
    MESSAGE.BATCH_VALIDATE_FORM,
    MESSAGE.BATCH_FORM_SNAPSHOT,
  ].includes(message.type)) {
    return { ok: false, code: 'UNKNOWN_COMMAND' };
  }
  const route = parseRoute(locationHref(doc), PORTAL_ORIGIN);
  if (!route || route.kind !== 'complemento') {
    return { ok: false, code: 'INVALID_TARGET' };
  }
  if (message.processId !== route.idProcesso) {
    return { ok: false, code: 'PROCESS_MISMATCH' };
  }
  if (message.type === MESSAGE.BATCH_SELECT_INTERESTED) {
    const selected = await selectSingleInterested(doc, message.processId);
    if (!selected.ok) {
      return { ok: false, code: selected.code };
    }
    return { ok: true, interestedKey: selected.interestedKey, interestedCount: 1 };
  }
  if (message.type === MESSAGE.BATCH_FORM_SNAPSHOT) {
    try {
      return { ok: true, snapshot: readForm(doc) };
    } catch (error) {
      return { ok: false, code: error && error.code ? error.code : 'FORM_NOT_READY' };
    }
  }
  let snapshot;
  try {
    snapshot = readForm(doc);
  } catch (error) {
    return { ok: false, code: error && error.code ? error.code : 'FORM_NOT_READY' };
  }
  const ready = validateBatchReady(snapshot, {
    processId: message.processId,
    interestedKey: typeof message.interestedKey === 'string' ? message.interestedKey : snapshot.interestedKey,
    interestedCount: snapshot.interestedCount,
    status: 'pending',
    revisionMarker: snapshot.revisionMarker,
    visibleErrors: hasVisibleErrors(doc),
  });
  if (!ready.ok) {
    return { ok: false, code: ready.code, fields: ready.fields || [] };
  }
  return { ok: true, revisionMarker: snapshot.revisionMarker };
}
