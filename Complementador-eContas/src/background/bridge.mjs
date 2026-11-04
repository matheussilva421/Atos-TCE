import { MESSAGE } from '../shared/protocol.mjs';
import { normalizeProcessLabel } from '../shared/identity.mjs';
import { parseRoute, selectSourceTabs } from '../shared/routes.mjs';

export class BridgeError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'BridgeError';
    this.code = code;
  }
}

export class TransactionManager {
  constructor(options = {}) {
    this.timeoutMs = options.timeoutMs || 20000;
    this.now = options.now || (() => Date.now());
    this.setTimer = options.setTimer || ((callback, ms) => setTimeout(callback, ms));
    this.clearTimer = options.clearTimer || ((timer) => clearTimeout(timer));
    this.active = new Map();
  }

  begin(tabId, requestId, kind = 'fill') {
    if (this.active.has(tabId)) {
      return false;
    }
    const entry = { requestId, kind, startedAt: this.now(), timer: null };
    entry.timer = this.setTimer(() => {
      entry.cancelled = true;
      entry.cancelReason = 'TIMEOUT';
    }, this.timeoutMs);
    this.active.set(tabId, entry);
    return true;
  }

  get(tabId) {
    return this.active.get(tabId) || null;
  }

  isActive(tabId, requestId) {
    const entry = this.active.get(tabId);
    return Boolean(entry && !entry.cancelled && (!requestId || entry.requestId === requestId));
  }

  cancel(tabId, reason = 'CANCELLED') {
    const entry = this.active.get(tabId);
    if (!entry) {
      return false;
    }
    entry.cancelled = true;
    entry.cancelReason = reason;
    if (entry.timer) {
      this.clearTimer(entry.timer);
    }
    this.active.delete(tabId);
    return true;
  }

  finish(tabId, requestId) {
    const entry = this.active.get(tabId);
    if (!entry) {
      return false;
    }
    if (requestId && entry.requestId !== requestId) {
      return false;
    }
    if (entry.timer) {
      this.clearTimer(entry.timer);
    }
    this.active.delete(tabId);
    return true;
  }
}

export function withTimeout(promise, timeoutMs, code = 'TIMEOUT') {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        reject(new BridgeError(code, 'Tempo limite excedido.'));
      }
    }, timeoutMs);
    Promise.resolve(promise).then(
      (value) => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          resolve(value);
        }
      },
      (error) => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          reject(error);
        }
      },
    );
  });
}

function validateProcessBinding(formSnapshot, document, requestId) {
  const expected = normalizeProcessLabel(formSnapshot && formSnapshot.processLabel ? formSnapshot.processLabel : '');
  const actual = normalizeProcessLabel(document && document.processLabel ? document.processLabel : '');
  if (!expected || !actual) {
    return errorResponse(requestId, 'PROCESS_BINDING_UNVERIFIED', 'Rótulo de processo ausente no formulário ou nos autos.');
  }
  if (expected !== actual) {
    return errorResponse(requestId, 'PROCESS_LABEL_MISMATCH', 'Processo do formulário diverge do processo dos autos.');
  }
  return null;
}
function errorResponse(requestId, code, message) {
  return {
    ok: false,
    requestId,
    status: 'error',
    error: { code, message },
  };
}

export async function runFillTransaction(input) {
  const {
    formTab,
    sourceTabs,
    requestId,
    formSnapshot,
    sendToSource,
    sendToForm,
    extract,
    timeoutMs = 20000,
    birthTimeoutMs = timeoutMs,
    cachedBirthEventId = null,
    onBirthFound,
    isCancelled,
    onState,
  } = input;

  const route = parseRoute(formTab && formTab.url);
  if (!route || route.kind !== 'complemento') {
    return errorResponse(requestId, 'INVALID_TARGET', 'Aba de complementação inválida.');
  }
  if (!formSnapshot || typeof formSnapshot.interestedName !== 'string' || !formSnapshot.interestedName) {
    return errorResponse(requestId, 'INVALID_FORM_SNAPSHOT', 'Interessado não identificado.');
  }
  const selection = selectSourceTabs(sourceTabs, route.idProcesso);
  if (!selection.ok) {
    return errorResponse(requestId, selection.code, 'Aba de autos não resolvida com segurança.');
  }

  let read;
  try {
    read = await withTimeout(
      sendToSource(selection.tabId, {
        type: MESSAGE.READ_DOCUMENT,
        requestId,
        expectedProcessId: route.idProcesso,
      }),
      timeoutMs,
      'READ_TIMEOUT',
    );
  } catch (error) {
    return errorResponse(requestId, error.code || 'READ_FAILED', 'Falha ao ler o documento atual.');
  }
  if (!read || read.ok !== true || !read.document) {
    return errorResponse(requestId, (read && read.code) || 'DOCUMENT_NOT_READABLE', 'Documento atual não legível.');
  }
  if (read.document.processId !== route.idProcesso) {
    return errorResponse(requestId, 'DOCUMENT_PROCESS_MISMATCH', 'Documento pertence a outro processo.');
  }
  const processError = validateProcessBinding(formSnapshot, read.document, requestId);
  if (processError) {
    return processError;
  }
  if (typeof isCancelled === 'function' && isCancelled()) {
    return errorResponse(requestId, 'TRANSACTION_CANCELLED', 'Transação cancelada.');
  }
  if (typeof extract !== 'function') {
    return errorResponse(requestId, 'EXTRACT_NOT_CONFIGURED', 'Extração não configurada.');
  }
  let proposals;
  try {
    proposals = extract(read.document, {
      processId: route.idProcesso,
      selectedInterested: formSnapshot.interestedName,
      interestedCount: formSnapshot.interestedCount || 1,
    });
  } catch {
    return errorResponse(requestId, 'EXTRACT_FAILED', 'Não foi possível interpretar o documento.');
  }

  const sourceNotes = {};
  if (proposals.dataNascimento && proposals.dataNascimento.status !== 'exact') {
    try {
      const pending = sendToForm(formTab.id, { type: MESSAGE.BIRTH_SEARCH, requestId });
      if (pending && typeof pending.catch === 'function') {
        pending.catch(() => {});
      }
    } catch {
      // O aviso de progresso é opcional.
    }
    let birthRead = null;
    try {
      birthRead = await withTimeout(
        sendToSource(selection.tabId, {
          type: MESSAGE.FIND_BIRTH_DOCUMENT,
          requestId,
          expectedProcessId: route.idProcesso,
          cachedEventId: cachedBirthEventId || null,
        }),
        birthTimeoutMs,
        'BIRTH_SEARCH_TIMEOUT',
      );
    } catch {
      birthRead = null;
    }
    if (birthRead && birthRead.ok === true && Array.isArray(birthRead.pages)) {
      try {
        const birthProposals = extract({ pages: birthRead.pages }, {
          processId: route.idProcesso,
          selectedInterested: formSnapshot.interestedName,
          interestedCount: formSnapshot.interestedCount || 1,
        });
        if (birthProposals.dataNascimento && birthProposals.dataNascimento.status === 'exact') {
          proposals.dataNascimento = birthProposals.dataNascimento;
          sourceNotes.dataNascimento = 'Origem: Guia Financeira/Taxação de Proventos';
          if (typeof onBirthFound === 'function' && birthRead.eventId) {
            await onBirthFound(birthRead.eventId);
          }
        }
      } catch {
        // A busca da Guia não pode impedir o preenchimento dos demais campos.
      }
    }
  }

  let apply;
  try {
    apply = await withTimeout(
      sendToForm(formTab.id, {
        type: MESSAGE.APPLY_PLAN,
        requestId,
        proposals,
        expected: {
          processId: route.idProcesso,
          interestedKey: formSnapshot.interestedKey,
        },
      }),
      timeoutMs,
      'APPLY_TIMEOUT',
    );
  } catch (error) {
    return errorResponse(requestId, error.code || 'APPLY_FAILED', 'Falha ao aplicar o preenchimento.');
  }
  if (!apply || apply.ok !== true) {
    return errorResponse(requestId, (apply && apply.code) || 'APPLY_REJECTED', 'Preenchimento recusado pelo formulário.');
  }

  return {
    ok: true,
    requestId,
    status: apply.report && apply.report.ok === false ? 'partial' : 'ok',
    route,
    sourceTabId: selection.tabId,
    document: {
      documentKey: read.document.documentKey,
      pagesCount: Array.isArray(read.document.pages) ? read.document.pages.length : 0,
      sourceKind: read.document.sourceKind,
      byteLength: typeof read.document.byteLength === 'number' ? read.document.byteLength : 0,
      observedAt: read.document.observedAt,
    },
    report: apply.report,
    sourceNotes: { ...(apply.sourceNotes || {}), ...sourceNotes },
  };
}
export async function runDocumentDiagnostic(input) {
  const {
    formTab,
    sourceTabs,
    requestId,
    formSnapshot,
    sendToSource,
    timeoutMs = 20000,
    isCancelled,
    onState,
  } = input;

  const route = parseRoute(formTab && formTab.url);
  if (!route || route.kind !== 'complemento') {
    return errorResponse(requestId, 'INVALID_TARGET', 'Aba de complementação inválida.');
  }
  const selection = selectSourceTabs(sourceTabs, route.idProcesso);
  if (!selection.ok) {
    return errorResponse(requestId, selection.code, 'Aba de autos não resolvida com segurança.');
  }
  if (typeof onState === 'function') {
    onState('SOURCE_TAB_RESOLVED');
  }
  if (typeof isCancelled === 'function' && isCancelled()) {
    return errorResponse(requestId, 'TRANSACTION_CANCELLED', 'Transação cancelada.');
  }
  let read;
  try {
    read = await withTimeout(
      sendToSource(selection.tabId, {
        type: MESSAGE.READ_DOCUMENT,
        requestId,
        expectedProcessId: route.idProcesso,
      }),
      timeoutMs,
      'READ_TIMEOUT',
    );
  } catch (error) {
    return errorResponse(requestId, error.code || 'READ_FAILED', 'Falha ao ler o documento atual.');
  }
  if (!read || read.ok !== true || !read.document) {
    return errorResponse(requestId, (read && read.code) || 'DOCUMENT_NOT_READABLE', 'Documento atual não legível.');
  }
  if (read.document.processId !== route.idProcesso) {
    return errorResponse(requestId, 'DOCUMENT_PROCESS_MISMATCH', 'Documento pertence a outro processo.');
  }
  const processError = validateProcessBinding(formSnapshot, read.document, requestId);
  if (processError) {
    return processError;
  }
  if (typeof isCancelled === 'function' && isCancelled()) {
    return errorResponse(requestId, 'TRANSACTION_CANCELLED', 'Transação cancelada.');
  }
  const pages = Array.isArray(read.document.pages) ? read.document.pages : [];
  if (pages.length === 0) {
    return errorResponse(requestId, 'PARTIAL_DOCUMENT', 'Documento sem páginas legíveis.');
  }
  const lengths = pages.map((page) => String(page).length);
  if (typeof onState === 'function') {
    onState('PDF_TEXT_EXTRACTED', {
      pagesCount: pages.length,
      totalChars: lengths.reduce((sum, length) => sum + length, 0),
      minPageChars: Math.min(...lengths),
      maxPageChars: Math.max(...lengths),
    });
  }
  return {
    ok: true,
    requestId,
    status: 'ok',
    diagnostic: {
      documentKey: read.document.documentKey,
      processId: route.idProcesso,
      pagesCount: pages.length,
      totalChars: lengths.reduce((sum, length) => sum + length, 0),
      minPageChars: Math.min(...lengths),
      maxPageChars: Math.max(...lengths),
      sourceKind: read.document.sourceKind,
      byteLength: typeof read.document.byteLength === 'number' ? read.document.byteLength : 0,
      observedAt: read.document.observedAt,
    },
  };
}
