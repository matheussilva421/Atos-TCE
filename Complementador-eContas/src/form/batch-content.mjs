import { PORTAL_ORIGIN } from '../shared/config.mjs';
import { normalizeText } from '../shared/identity.mjs';
import { MESSAGE } from '../shared/protocol.mjs';
import { parseRoute } from '../shared/routes.mjs';
import { validateBatchReady } from './batch-validation.mjs';
import { readForm } from './form-reader.mjs';
import { selectSingleInterested } from './interested-selector.mjs';

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
  if (!message || ![MESSAGE.BATCH_SELECT_INTERESTED, MESSAGE.BATCH_VALIDATE_FORM].includes(message.type)) {
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
