import { PORTAL_ORIGIN } from '../shared/config.mjs';
import { MESSAGE } from '../shared/protocol.mjs';
import { parseRoute } from '../shared/routes.mjs';
import { base64ToBytes, extractPagesFromPdf, getIframeSrc, readCurrentDocument } from './document-reader.mjs';
import { isBirthDocumentText } from './document-locator.mjs';
import { parsePdfUrl } from './pdf-identity.mjs';

let route = parseRoute(location.href, PORTAL_ORIGIN);

function updateRoute() {
  route = parseRoute(location.href, PORTAL_ORIGIN);
  if (route && route.kind === 'autos') {
    document.documentElement.setAttribute('data-complementador-autos', 'ready');
  } else {
    document.documentElement.removeAttribute('data-complementador-autos');
  }
}

updateRoute();
window.addEventListener('hashchange', updateRoute);
if (window.navigation && typeof window.navigation.addEventListener === 'function') {
  window.navigation.addEventListener('navigatesuccess', updateRoute);
}

const EVENT_CARD_SELECTOR = '.card-event';
const EVENT_HEADER_SELECTOR = '#header-eventos';

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function eventCardKey(card) {
  return card.id || card.getAttribute('data-id') || '';
}

function waitForIframeSrcChange(previous, timeoutMs = 250) {
  return new Promise((resolve) => {
    const started = Date.now();
    const tick = () => {
      const current = getIframeSrc(document);
      if (current && current !== previous) {
        resolve(current);
        return;
      }
      if (Date.now() - started >= timeoutMs) {
        resolve(null);
        return;
      }
      setTimeout(tick, 40);
    };
    tick();
  });
}

async function ensureEventCards() {
  let cards = [...document.querySelectorAll(EVENT_CARD_SELECTOR)];
  if (cards.length > 0) {
    return cards;
  }
  const header = document.querySelector(EVENT_HEADER_SELECTOR);
  if (header) {
    header.click();
  }
  for (let attempt = 0; attempt < 10; attempt += 1) {
    await wait(60);
    cards = [...document.querySelectorAll(EVENT_CARD_SELECTOR)];
    if (cards.length > 0) {
      return cards;
    }
  }
  return cards;
}

function restoreAutosView(originalSrc, selectedIds) {
  for (const card of document.querySelectorAll(EVENT_CARD_SELECTOR)) {
    card.classList.remove('escurecer');
  }
  for (const id of selectedIds) {
    const card = document.getElementById(id)
      || document.querySelector(EVENT_CARD_SELECTOR + '[data-id="' + id + '"]');
    if (card) {
      card.classList.add('escurecer');
    }
  }
  const iframe = document.querySelector('iframe#ifrm');
  if (iframe && originalSrc) {
    iframe.src = originalSrc;
  }
}

async function readCandidate(url, message) {
  try {
    const response = await chrome.runtime.sendMessage({
      type: MESSAGE.FETCH_PDF,
      url,
      requestId: message.requestId,
      expectedProcessId: message.expectedProcessId,
    });
    if (!response || response.ok !== true || typeof response.base64 !== 'string') {
      return null;
    }
    const pages = await extractPagesFromPdf(
      base64ToBytes(response.base64),
      { workerSrc: chrome.runtime.getURL('vendor/pdf.worker.mjs') },
      { maxPages: 2 },
    );
    return {
      pages,
      byteLength: typeof response.byteLength === 'number' ? response.byteLength : 0,
    };
  } catch {
    return null;
  }
}

async function findBirthDocument(message) {
  const originalSrc = getIframeSrc(document);
  const selectedIds = [...document.querySelectorAll(EVENT_CARD_SELECTOR + '.escurecer')]
    .map(eventCardKey)
    .filter(Boolean);
  const cards = await ensureEventCards();
  if (cards.length === 0) {
    return { ok: false, code: 'EVENTS_NOT_AVAILABLE' };
  }

  const seen = new Set();
  let previousSrc = originalSrc;
  let cachedUsed = false;

  const collectFromCard = async (card, timeoutMs) => {
    card.click();
    const src = await waitForIframeSrcChange(previousSrc, timeoutMs);
    if (!src) {
      return null;
    }
    previousSrc = src;
    const parsed = parsePdfUrl(src);
    const eventId = eventCardKey(card);
    if (!parsed || !eventId || seen.has(eventId)) {
      return null;
    }
    seen.add(eventId);
    return { eventId, src, documentKey: parsed.documentKey };
  };

  if (message.cachedEventId) {
    const cachedCard = cards.find((card) => eventCardKey(card) === message.cachedEventId);
    if (cachedCard) {
      const cachedCandidate = await collectFromCard(cachedCard, 900);
      if (cachedCandidate) {
        cachedUsed = true;
        const read = await readCandidate(cachedCandidate.src, message);
        if (read && isBirthDocumentText(read.pages.join('\n'))) {
          restoreAutosView(originalSrc, selectedIds);
          return {
            ok: true,
            pages: read.pages,
            documentKey: cachedCandidate.documentKey,
            sourceKind: 'pdf-bytes',
            byteLength: read.byteLength,
            eventId: cachedCandidate.eventId,
            cachedUsed: true,
          };
        }
      }
    }
  }

  let found = null;
  for (const card of cards) {
    if (message.cachedEventId && eventCardKey(card) === message.cachedEventId) {
      continue;
    }
    const candidate = await collectFromCard(card, 900);
    if (!candidate) {
      continue;
    }
    const read = await readCandidate(candidate.src, message);
    if (read && isBirthDocumentText(read.pages.join('\n'))) {
      found = { ...candidate, pages: read.pages, byteLength: read.byteLength };
      break;
    }
  }
  restoreAutosView(originalSrc, selectedIds);

  if (found) {
    return {
      ok: true,
      pages: found.pages,
      documentKey: found.documentKey,
      sourceKind: 'pdf-bytes',
      byteLength: found.byteLength,
      eventId: found.eventId,
      cachedUsed,
    };
  }
  return { ok: false, code: 'BIRTH_DOCUMENT_NOT_FOUND', cachedUsed };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || (message.type !== MESSAGE.READ_DOCUMENT && message.type !== MESSAGE.FIND_BIRTH_DOCUMENT)) {
      return false;
    }
    if (!sender || sender.id !== chrome.runtime.id) {
      sendResponse({ ok: false, code: 'UNTRUSTED_SENDER' });
      return true;
    }
    if (!route || route.kind !== 'autos' || message.expectedProcessId !== route.idProcesso) {
      sendResponse({ ok: false, code: 'PROCESS_CHANGED' });
      return true;
    }
    if (message.type === MESSAGE.FIND_BIRTH_DOCUMENT) {
      findBirthDocument(message).then(
        (result) => sendResponse(result),
        (error) => sendResponse({ ok: false, code: error.code || 'BIRTH_SEARCH_FAILED' }),
      );
      return true;
    }
    const workerSrc = chrome.runtime.getURL('vendor/pdf.worker.mjs');
    readCurrentDocument(
      { expectedProcessId: route.idProcesso, requestId: message.requestId },
      {
        document,
        fetchPdf: (url, context) => chrome.runtime.sendMessage({
          type: MESSAGE.FETCH_PDF,
          url,
          requestId: context.requestId,
          expectedProcessId: context.expectedProcessId,
        }),
        extractPages: (bytes) => extractPagesFromPdf(bytes, { workerSrc }),
        onState: (state, details) => {
          try {
            const pending = chrome.runtime.sendMessage({
              type: MESSAGE.DIAGNOSTIC_STATE,
              state,
              requestId: message.requestId,
              details: details || {},
            });
            if (pending && typeof pending.catch === 'function') pending.catch(() => {});
          } catch {
            // O observador nunca pode interromper a leitura.
          }
        },
        now: () => performance.now(),
      },
    ).then(
      (documentRead) => sendResponse({ ok: true, document: documentRead }),
      (error) => sendResponse({ ok: false, code: error.code || 'DOCUMENT_NOT_READABLE' }),
    );
    return true;
  });
