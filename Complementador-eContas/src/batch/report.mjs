import { PORTAL_ORIGIN } from '../shared/config.mjs';
import { isValidProcessId } from '../shared/identity.mjs';

const REASON = Object.freeze({
  QUEUED: 'NOT_EXAMINED',
  IN_PROGRESS: 'IN_PROGRESS',
  CONFIRMED: null,
  SKIPPED: 'PROCESS_SKIPPED',
  REVIEW_REQUIRED: 'REVIEW_REQUIRED',
  FAILED: 'PROCESS_FAILED',
  SAVE_UNCERTAIN: 'SAVE_UNCERTAIN',
});

const IN_PROGRESS = new Set(['EXAMINING', 'READING', 'FILLING', 'VALIDATING', 'SAVE_PENDING', 'VERIFYING']);

function reasonFor(status) {
  if (IN_PROGRESS.has(status)) {
    return REASON.IN_PROGRESS;
  }
  return Object.prototype.hasOwnProperty.call(REASON, status) ? REASON[status] : 'UNKNOWN_STATE';
}

function trustedOrigin(value) {
  if (typeof value !== 'string' || value.length === 0) {
    return null;
  }
  if (value !== PORTAL_ORIGIN) {
    return null;
  }
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return null;
  }
  const loopback = parsed.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(parsed.hostname);
  const institutional = parsed.protocol === 'https:' && parsed.hostname === 'processos.tce.rn.gov.br';
  return loopback || institutional ? value : null;
}

function linkFor(processId, origin) {
  if (!origin || !isValidProcessId(processId)) {
    return null;
  }
  return origin + '/#/dashboard/processos/' + processId + '/autos';
}

/**
 * Relatório determinístico e sanitizado do lote: apenas IDs, status e códigos de motivo.
 * Nenhum valor de campo, nome, CPF, matrícula, nascimento ou texto documental é incluído.
 */
export function buildBatchReport(batch, options = {}) {
  const origin = trustedOrigin(options.portalOrigin ?? PORTAL_ORIGIN);
  const queue = Array.isArray(batch && batch.queue) ? batch.queue : [];
  const counters = batch && batch.counters ? batch.counters : {};
  const capture = batch && batch.capture ? batch.capture : {};
  const items = queue.map((entry) => {
    const status = typeof entry.status === 'string' ? entry.status : 'unknown';
    return {
      processId: typeof entry.processId === 'string' ? entry.processId : '',
      processLabel: typeof entry.processLabel === 'string' ? entry.processLabel : '',
      status,
      reasonCode: reasonFor(status),
      link: linkFor(entry.processId, origin),
    };
  });
  const count = (status) => items.filter((item) => item.status === status).length;
  return {
    batchId: batch && typeof batch.batchId === 'string' ? batch.batchId : '',
    state: batch && typeof batch.state === 'string' ? batch.state : 'unknown',
    totals: {
      captured: Number.isSafeInteger(capture.captured) ? capture.captured : 0,
      skippedCompleted: Number.isSafeInteger(capture.skippedCompleted) ? capture.skippedCompleted : 0,
      skippedUnknown: Number.isSafeInteger(capture.skippedUnknown) ? capture.skippedUnknown : 0,
      queued: count('QUEUED'),
      examined: Number.isSafeInteger(counters.examined) ? counters.examined : 0,
      saved: Number.isSafeInteger(counters.saved) ? counters.saved : 0,
      confirmed: count('CONFIRMED'),
      skipped: count('SKIPPED'),
      review: count('REVIEW_REQUIRED'),
      failed: count('FAILED'),
      uncertain: count('SAVE_UNCERTAIN'),
    },
    items,
  };
}
