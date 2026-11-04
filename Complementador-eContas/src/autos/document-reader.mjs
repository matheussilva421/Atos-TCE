import { PDF_ORIGIN } from '../shared/config.mjs';
import { DIAGNOSTIC_STATES } from '../shared/diagnostic-store.mjs';
import { hashString, isValidProcessId, normalizeProcessLabel } from '../shared/identity.mjs';

export const DOCUMENT_ERROR = Object.freeze({
  DOCUMENT_NOT_READABLE: 'DOCUMENT_NOT_READABLE',
  DOCUMENT_CHANGED: 'DOCUMENT_CHANGED',
  PARTIAL_DOCUMENT: 'PARTIAL_DOCUMENT',
  INVALID_PROCESS: 'INVALID_PROCESS',
  PDF_FETCH_FAILED: 'PDF_FETCH_FAILED',
});

export class DocumentError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'DocumentError';
    this.code = code;
  }
}

let pdfjsPromise = null;

async function getPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import('pdfjs-dist/legacy/build/pdf.mjs');
  }
  return pdfjsPromise;
}

export function readAutosProcessLabel(doc) {
  const headings = [...doc.querySelectorAll('h1,h2,h3,h4')];
  const heading = headings.find((element) => /AUTOS DO PROCESSO/i.test(element.textContent || ''));
  return normalizeProcessLabel(heading ? heading.textContent : '');
}
export function getIframeSrc(doc) {
  if (!doc || typeof doc.querySelector !== 'function') {
    return null;
  }
  const iframe = doc.querySelector('iframe#ifrm') || doc.querySelector('iframe[title="iframe de anexo"]');
  if (!iframe || !iframe.src) {
    return null;
  }
  return iframe.src;
}

export function parsePdfUrl(url, pdfOrigin = PDF_ORIGIN) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.origin !== pdfOrigin || parsed.username || parsed.password) {
    return null;
  }
  if (parsed.search || parsed.hash) {
    return null;
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    return null;
  }
  const guid = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
  const pattern = new RegExp('^/as/consultaprocessotemp/\\d{4}/\\d{1,2}/\\d{1,2}/' + guid + '/' + guid + '\\.pdf$', 'i');
  if (!pattern.test(parsed.pathname)) {
    return null;
  }
  return {
    url: parsed.href,
    documentKey: hashString(parsed.pathname),
    pathname: parsed.pathname,
  };
}

function looksLikePdf(bytes) {
  return bytes && bytes.length >= 5
    && bytes[0] === 0x25
    && bytes[1] === 0x50
    && bytes[2] === 0x44
    && bytes[3] === 0x46
    && bytes[4] === 0x2d;
}

export function bytesToBase64(bytes) {
  if (typeof Buffer !== 'undefined') {
    return Buffer.from(bytes).toString('base64');
  }
  let binary = '';
  const chunk = 0x8000;
  for (let index = 0; index < bytes.length; index += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(index, index + chunk));
  }
  return btoa(binary);
}

export function base64ToBytes(base64) {
  if (typeof Buffer !== 'undefined') {
    return new Uint8Array(Buffer.from(base64, 'base64'));
  }
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

export async function extractPagesFromPdf(bytes, deps = {}, options = {}) {
  const pdfjs = await getPdfjs();
  if (typeof pdfjs.GlobalWorkerOptions !== 'undefined' && deps.workerSrc) {
    pdfjs.GlobalWorkerOptions.workerSrc = deps.workerSrc;
  } else if (typeof pdfjs.GlobalWorkerOptions !== 'undefined'
    && typeof chrome !== 'undefined'
    && chrome.runtime
    && typeof chrome.runtime.getURL === 'function') {
    pdfjs.GlobalWorkerOptions.workerSrc = chrome.runtime.getURL('vendor/pdf.worker.mjs');
  }
  const loadingTask = pdfjs.getDocument({
    data: bytes,
    useWorkerFetch: false,
    isEvalSupported: false,
    disableFontFace: true,
    useSystemFonts: false,
    verbosity: 0,
  });
  const pdf = await loadingTask.promise;
  const pages = [];
  try {
    const pageLimit = Number.isInteger(options.maxPages)
      ? Math.min(pdf.numPages, options.maxPages)
      : pdf.numPages;
    for (let pageNumber = 1; pageNumber <= pageLimit; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber);
      const content = await page.getTextContent();
      let text = '';
      for (const item of content.items) {
        if (typeof item.str === 'string') {
          text += item.str;
          text += item.hasEOL ? '\n' : ' ';
        }
      }
      pages.push(text.replace(/\s+/g, ' ').trim());
      if (typeof page.cleanup === 'function') {
        page.cleanup();
      }
    }
  } finally {
    if (typeof pdf.destroy === 'function') {
      await pdf.destroy();
    }
  }
  return pages;
}

function emitState(deps, state, details = {}) {
  if (typeof deps.onState === 'function') {
    try {
      deps.onState(state, details);
    } catch {
      // O diagnóstico não pode falhar por causa do observador.
    }
  }
}
export async function readCurrentDocument(ctx, deps = {}) {
  if (!ctx || !isValidProcessId(ctx.expectedProcessId)) {
    throw new DocumentError(DOCUMENT_ERROR.INVALID_PROCESS, 'Processo esperado inválido.');
  }
  const doc = deps.document || (typeof document !== 'undefined' ? document : null);
  const beforeSrc = getIframeSrc(doc);
  if (!beforeSrc) {
    throw new DocumentError(DOCUMENT_ERROR.DOCUMENT_NOT_READABLE, 'Visualizador de documento não encontrado.');
  }
  const parsed = parsePdfUrl(beforeSrc, deps.pdfOrigin);
  if (!parsed) {
    throw new DocumentError(DOCUMENT_ERROR.DOCUMENT_NOT_READABLE, 'Documento atual não reconhecido.');
  }
  emitState(deps, DIAGNOSTIC_STATES.IFRAME_IDENTIFIED);
  if (typeof deps.fetchPdf !== 'function') {
    throw new DocumentError(DOCUMENT_ERROR.PDF_FETCH_FAILED, 'Leitura de bytes não configurada.');
  }
  emitState(deps, DIAGNOSTIC_STATES.PDF_FETCH_STARTED);
  let response;
  try {
    response = await deps.fetchPdf(beforeSrc, {
      requestId: ctx.requestId,
      expectedProcessId: ctx.expectedProcessId,
    });
  } catch {
    throw new DocumentError(DOCUMENT_ERROR.PDF_FETCH_FAILED, 'Falha ao obter o PDF atual.');
  }
  if (!response || response.ok !== true || typeof response.base64 !== 'string') {
    throw new DocumentError(
      (response && response.code) || DOCUMENT_ERROR.PDF_FETCH_FAILED,
      'Não foi possível obter o PDF atual.',
    );
  }
  emitState(deps, DIAGNOSTIC_STATES.PDF_FETCH_OK, { byteLength: typeof response.byteLength === 'number' ? response.byteLength : 0 });
  const bytes = base64ToBytes(response.base64);
  const byteLength = bytes.length;
  if (!looksLikePdf(bytes)) {
    throw new DocumentError(DOCUMENT_ERROR.DOCUMENT_NOT_READABLE, 'O conteúdo recebido não é um PDF.');
  }
  emitState(deps, DIAGNOSTIC_STATES.PDF_VALIDATED, { byteLength });
  let pages;
  try {
    pages = await (deps.extractPages || extractPagesFromPdf)(bytes);
  } catch {
    throw new DocumentError(DOCUMENT_ERROR.DOCUMENT_NOT_READABLE, 'Não foi possível extrair o texto do PDF.');
  }
  if (!Array.isArray(pages) || pages.length === 0) {
    throw new DocumentError(DOCUMENT_ERROR.PARTIAL_DOCUMENT, 'O documento não possui páginas legíveis.');
  }
  if (pages.some((page) => typeof page !== 'string' || page.trim().length === 0)) {
    throw new DocumentError(DOCUMENT_ERROR.PARTIAL_DOCUMENT, 'O documento possui páginas sem texto legível.');
  }
  const pageLengths = pages.map((page) => page.length);
  emitState(deps, DIAGNOSTIC_STATES.PDF_TEXT_EXTRACTED, {
    pagesCount: pages.length,
    totalChars: pageLengths.reduce((sum, length) => sum + length, 0),
    minPageChars: Math.min(...pageLengths),
    maxPageChars: Math.max(...pageLengths),
  });
  const afterSrc = getIframeSrc(doc);
  if (afterSrc !== beforeSrc) {
    throw new DocumentError(DOCUMENT_ERROR.DOCUMENT_CHANGED, 'O documento mudou durante a leitura.');
  }
  return {
    documentKey: parsed.documentKey,
    processId: ctx.expectedProcessId,
    processLabel: readAutosProcessLabel(doc),
    pages: pages.map((page) => page.replace(/\s+/g, ' ').trim()),
    sourceKind: 'pdf-bytes',
    byteLength,
    observedAt: typeof deps.now === 'function' ? deps.now() : Date.now(),
  };
}
