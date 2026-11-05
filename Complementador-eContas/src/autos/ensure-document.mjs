export function currentDocumentSrc(doc) {
  const iframe = doc.querySelector('iframe#ifrm');
  return iframe ? String(iframe.getAttribute('src') || '').trim() : '';
}

/**
 * Garante que a aba de Autos tenha um documento carregado no visualizador.
 * Se nenhum estiver aberto, clica no primeiro cartão de evento e aguarda o src.
 */
export async function ensureDocumentOpen(doc, options = {}) {
  const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 6000;
  const pollMs = Number.isFinite(options.pollMs) ? options.pollMs : 250;
  const sleep = options.sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const click = options.click || ((element) => element.click());

  if (currentDocumentSrc(doc)) {
    return { ok: true, alreadyOpen: true };
  }
  const card = doc.querySelector('.card-event[data-pdf]') || doc.querySelector('.card-event');
  if (!card) {
    return { ok: false, code: 'NO_EVENT_CARD' };
  }
  click(card);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await sleep(pollMs);
    if (currentDocumentSrc(doc)) {
      return { ok: true, alreadyOpen: false };
    }
  }
  return { ok: false, code: 'NO_DOCUMENT' };
}
