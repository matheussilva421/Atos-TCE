import { MESSAGE } from '../shared/protocol.mjs';
import { normalizeProcessLabel } from '../shared/identity.mjs';
import { parseRoute, selectSourceTabs } from '../shared/routes.mjs';
import { isBirthDocumentText, isResolutionDocumentText } from '../autos/document-locator.mjs';
import { parseBirthDateForPerson } from '../extract/dates.mjs';

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

const RESOLUTION_FIELDS = ['modalidade', 'dataDoeEstado', 'cargo', 'matricula'];
const ABSENT_PROPOSAL = Object.freeze({ status: 'absent' });

function resolutionScore(proposals) {
  return RESOLUTION_FIELDS.filter((name) => proposals[name] && proposals[name].status === 'exact').length;
}

export function chooseResolutionCandidate(candidates) {
  const list = Array.isArray(candidates) ? candidates.filter((candidate) => candidate && candidate.proposals) : [];
  if (list.length === 0) {
    return {
      proposals: Object.fromEntries(RESOLUTION_FIELDS.map((name) => [name, ABSENT_PROPOSAL])),
      eventId: null,
      score: 0,
    };
  }
  const scored = list.map((candidate) => ({ ...candidate, score: resolutionScore(candidate.proposals) }));
  const topScore = Math.max(...scored.map((candidate) => candidate.score));
  const top = scored.filter((candidate) => candidate.score === topScore);
  if (top.length === 1) {
    return { proposals: top[0].proposals, eventId: top[0].eventId || null, score: topScore };
  }
  const proposals = {};
  for (const name of RESOLUTION_FIELDS) {
    const exact = top
      .map((candidate) => candidate.proposals[name])
      .filter((proposal) => proposal && proposal.status === 'exact');
    const values = [...new Set(exact.map((proposal) => proposal.value))];
    if (values.length === 1) {
      proposals[name] = exact[0];
    } else if (values.length > 1) {
      proposals[name] = { status: 'ambiguous', candidates: values };
    } else {
      proposals[name] = ABSENT_PROPOSAL;
    }
  }
  const eventId = top.every((candidate) => candidate.eventId === top[0].eventId)
    ? (top[0].eventId || null)
    : null;
  return { proposals, eventId, score: topScore };
}

export function chooseBirthCandidate(input) {
  const {
    currentProposals,
    currentIsGuia,
    currentIsResolution,
    currentEventId,
    guias,
    selectedInterested,
    selectedInterestedCpf,
  } = input;
  if (currentIsGuia || currentIsResolution) {
    const current = currentProposals && currentProposals.dataNascimento;
    if (current && current.status === 'exact') {
      return {
        proposal: current,
        eventId: currentEventId || null,
        source: currentIsGuia ? 'guia' : 'resolution',
      };
    }
  }
  const exact = [];
  for (const guia of Array.isArray(guias) ? guias : []) {
    if (!guia) {
      continue;
    }
    let birth = guia.birthProposal;
    if (!birth && Array.isArray(guia.pages)) {
      birth = parseBirthDateForPerson(
        guia.pages.join('\n'),
        selectedInterested || '',
        selectedInterestedCpf || '',
      );
    }
    if (birth.status === 'exact') {
      exact.push({
        birth: {
          ...birth,
          dateBr: birth.dateBr || birth.value,
        },
        eventId: guia.eventId || null,
      });
    }
  }
  const dates = [...new Set(exact.map((entry) => entry.birth.dateBr))];
  if (dates.length === 1) {
    return {
      proposal: {
        status: 'exact',
        value: dates[0],
        source: 'data de nascimento na Guia Financeira/Taxação de Proventos',
      },
      eventId: exact[0].eventId,
      source: 'guia',
    };
  }
  if (dates.length > 1) {
    return { proposal: { status: 'ambiguous', candidates: dates }, eventId: null, source: 'guia' };
  }
  return { proposal: ABSENT_PROPOSAL, eventId: null, source: null };
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
    documentTimeoutMs = 90000,
    cached = null,
    onDocumentsFound,
    isCancelled,
    onState,
    applyMessageType = MESSAGE.APPLY_PLAN,
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

  const context = {
    processId: route.idProcesso,
    selectedInterested: formSnapshot.interestedName,
    selectedInterestedCpf: formSnapshot.interestedCpf || '',
    interestedCount: formSnapshot.interestedCount || 1,
  };
  let currentProposals;
  try {
    currentProposals = extract(read.document, context);
  } catch {
    return errorResponse(requestId, 'EXTRACT_FAILED', 'Não foi possível interpretar o documento.');
  }

  const currentText = Array.isArray(read.document.pages) ? read.document.pages.join('\n') : '';
  const currentIsResolution = isResolutionDocumentText(currentText);
  const currentIsGuia = isBirthDocumentText(currentText);
  const currentResolutionComplete = currentIsResolution
    && RESOLUTION_FIELDS.every((name) => currentProposals[name] && currentProposals[name].status === 'exact');
  const currentBirthComplete = Boolean(currentProposals.dataNascimento && currentProposals.dataNascimento.status === 'exact');

  let discovery = null;
  if (!currentResolutionComplete || !currentBirthComplete) {
    try {
      const pending = sendToForm(formTab.id, { type: MESSAGE.DOCUMENT_SEARCH, requestId });
      if (pending && typeof pending.catch === 'function') {
        pending.catch(() => {});
      }
    } catch {
      // O aviso de progresso é opcional.
    }
    try {
      discovery = await withTimeout(
        sendToSource(selection.tabId, {
          type: MESSAGE.DISCOVER_DOCUMENTS,
          requestId,
          expectedProcessId: route.idProcesso,
          cached: cached || null,
          needsResolution: !currentResolutionComplete,
          needsGuia: !currentBirthComplete,
          selectedInterested: formSnapshot.interestedName,
          selectedInterestedCpf: formSnapshot.interestedCpf || '',
        }),
        documentTimeoutMs,
        'DOCUMENT_SEARCH_TIMEOUT',
      );
    } catch {
      discovery = null;
    }
  }
  if (typeof isCancelled === 'function' && isCancelled()) {
    return errorResponse(requestId, 'TRANSACTION_CANCELLED', 'Transação cancelada.');
  }

  const currentEventId = discovery && discovery.currentEventId ? discovery.currentEventId : '';
  const resolutionCandidates = [];
  if (currentIsResolution) {
    resolutionCandidates.push({
      eventId: currentEventId || null,
      proposals: currentProposals,
      source: 'current',
    });
  }
  if (discovery && Array.isArray(discovery.resolutions)) {
    for (const candidate of discovery.resolutions) {
      if (!candidate || !Array.isArray(candidate.pages)) {
        continue;
      }
      try {
        const proposals = extract({
          pages: candidate.pages,
          documentKey: candidate.documentKey,
          processId: route.idProcesso,
          sourceKind: 'pdf-bytes',
          byteLength: candidate.byteLength,
          observedAt: Date.now(),
        }, context);
        resolutionCandidates.push({
          eventId: candidate.eventId || null,
          proposals,
          source: 'discovered',
        });
      } catch {
        // Um candidato inválido não impede os demais.
      }
    }
  }
  const resolution = chooseResolutionCandidate(resolutionCandidates);
  const guiaCandidates = [];
  if (discovery && Array.isArray(discovery.guias)) {
    for (const guia of discovery.guias) {
      if (!guia || !Array.isArray(guia.pages)) {
        continue;
      }
      let birthProposal = null;
      try {
        const guiaProposals = extract({
          pages: guia.pages,
          documentKey: guia.documentKey,
          processId: route.idProcesso,
          sourceKind: 'pdf-bytes',
          byteLength: guia.byteLength,
          observedAt: Date.now(),
        }, context);
        birthProposal = guiaProposals.dataNascimento || null;
      } catch {
        // A correlação por páginas continua como fallback.
      }
      guiaCandidates.push({ eventId: guia.eventId, pages: guia.pages, birthProposal });
    }
  }
  const birth = chooseBirthCandidate({
    currentProposals,
    currentIsGuia,
    currentIsResolution,
    currentEventId,
    guias: guiaCandidates,
    selectedInterested: formSnapshot.interestedName,
    selectedInterestedCpf: formSnapshot.interestedCpf || '',
  });

  const proposals = {
    modalidade: resolution.proposals.modalidade || ABSENT_PROPOSAL,
    dataDoeEstado: resolution.proposals.dataDoeEstado || ABSENT_PROPOSAL,
    cargo: resolution.proposals.cargo || ABSENT_PROPOSAL,
    matricula: resolution.proposals.matricula || ABSENT_PROPOSAL,
    dataNascimento: birth.proposal || ABSENT_PROPOSAL,
  };
  const sourceNotes = {};
  if (proposals.dataDoeEstado.status === 'exact') {
    sourceNotes.dataDoeEstado = 'Origem: data da resolução administrativa';
  }
  if (birth.source === 'guia') {
    sourceNotes.dataNascimento = 'Origem: Guia Financeira/Taxação de Proventos';
  } else if (birth.source === 'resolution') {
    sourceNotes.dataNascimento = 'Origem: resolução administrativa';
  }
  if (typeof onDocumentsFound === 'function' && (resolution.eventId || birth.eventId)) {
    await onDocumentsFound({
      resolutionEventId: resolution.eventId || null,
      guiaEventId: birth.eventId || null,
    });
  }

  let apply;
  try {
    apply = await withTimeout(
      sendToForm(formTab.id, {
        type: applyMessageType,
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

  const applyReport = apply.report && typeof apply.report === 'object' ? apply.report : {};
  const fieldDiagnostics = {
    resolutionFound: Boolean(resolution && resolution.eventId),
    guiaFound: Boolean(birth && (birth.eventId || birth.source === 'guia')),
    proposalStatus: Object.fromEntries(
      ['modalidade', 'dataDoeEstado', 'cargo', 'matricula', 'dataNascimento']
        .map((name) => [
          name,
          proposals[name] && typeof proposals[name].status === 'string'
            ? proposals[name].status
            : 'absent',
        ]),
    ),
    skipped: (Array.isArray(applyReport.skipped) ? applyReport.skipped : [])
      .slice(0, 10)
      .map((item) => ({ field: String(item.field || ''), reason: String(item.reason || '') })),
    errors: (Array.isArray(applyReport.errors) ? applyReport.errors : [])
      .slice(0, 10)
      .map((item) => ({ field: String(item.field || ''), code: String(item.code || '') })),
  };

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
    fieldDiagnostics,
    sourceNotes: { ...(apply.sourceNotes || {}), ...sourceNotes },
    discovery: discovery ? {
      scannedCount: discovery.scannedCount || 0,
      cachedUsed: Boolean(discovery.cachedUsed),
      clickMs: discovery.clickMs || 0,
      readMs: discovery.readMs || 0,
    } : null,
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
