import { extractInterestedName, hashString, normalizeLabel } from '../shared/identity.mjs';
import { parseRoute } from '../shared/routes.mjs';

const CARD_SELECTOR = 'button.cartao-item';

function locationHref(doc) {
  return (doc && doc.location && doc.location.href)
    || (doc && doc.defaultView && doc.defaultView.location && doc.defaultView.location.href)
    || '';
}

/**
 * Garante exatamente um interessado no formulário Complementar Ato do processo esperado.
 * A chave retornada é transitória e não deve ser persistida.
 */
export async function selectSingleInterested(doc, expectedProcessId, deps = {}) {
  const route = parseRoute(locationHref(doc));
  if (!route || route.kind !== 'complemento' || route.idProcesso !== expectedProcessId) {
    return { ok: false, code: 'WRONG_PROCESS' };
  }
  const wait = deps.wait || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const timeoutMs = Number.isFinite(deps.timeoutMs) ? deps.timeoutMs : 400;
  const pollMs = Number.isFinite(deps.pollMs) ? deps.pollMs : 20;
  let cards = [...doc.querySelectorAll(CARD_SELECTOR)];
  if (cards.length === 0) {
    const started = Date.now();
    while (cards.length === 0 && Date.now() - started < timeoutMs) {
      await wait(pollMs);
      cards = [...doc.querySelectorAll(CARD_SELECTOR)];
    }
  }
  if (cards.length === 0) {
    return {
      ok: false,
      code: doc.querySelector('tce-container') ? 'NO_INTERESTED' : 'CARDS_NOT_LOADED',
    };
  }
  if (cards.length > 1) {
    return { ok: false, code: 'MULTIPLE_INTERESTED' };
  }
  let selected = [...doc.querySelectorAll(CARD_SELECTOR + '.selecionada')];
  if (selected.length === 0) {
    cards[0].click();
    const started = Date.now();
    while (selected.length === 0 && Date.now() - started < timeoutMs) {
      await wait(pollMs);
      selected = [...doc.querySelectorAll(CARD_SELECTOR + '.selecionada')];
    }
  }
  if (selected.length !== 1) {
    return { ok: false, code: 'SELECTION_NOT_CONFIRMED' };
  }
  const name = extractInterestedName(selected[0].textContent || '');
  if (!name) {
    return { ok: false, code: 'INTERESTED_WITHOUT_IDENTITY' };
  }
  return {
    ok: true,
    interestedKey: hashString(normalizeLabel(name)),
    interestedCount: 1,
  };
}
