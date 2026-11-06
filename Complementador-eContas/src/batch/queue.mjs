import { isValidProcessId } from '../shared/identity.mjs';

export class BatchQueueError extends Error {
  constructor(code) {
    super(code);
    this.name = 'BatchQueueError';
    this.code = code;
  }
}

const LIST_STATUS = new Set(['pending', 'completed', 'unknown']);

/**
 * Valida os dois limites independentes do lote.
 * @param {{maxExamined?: unknown, maxSaved?: unknown}} input
 * @returns {{maxExamined: number, maxSaved: number}}
 */
export function validateLimits(input) {
  const limits = {};
  for (const field of ['maxExamined', 'maxSaved']) {
    const value = input && typeof input === 'object' ? input[field] : undefined;
    if (!Number.isSafeInteger(value) || value <= 0) {
      throw new BatchQueueError('INVALID_LIMIT');
    }
    limits[field] = value;
  }
  return limits;
}

/**
 * Congela a fila da página atual, deduplicando IDs e excluindo o que não está pendente.
 * Processos pré-excluídos não consomem o limite de examinados.
 * @returns {object} BatchRecord mínimo conforme contrato do plano.
 */
export function createFrozenBatch({ batchId, listTabId, contextKey, entries, limits, startedAt, saveAuthorized = false }) {
  if (typeof batchId !== 'string' || !/^[A-Za-z0-9._:-]{6,80}$/.test(batchId)) {
    throw new BatchQueueError('INVALID_BATCH_ID');
  }
  if (!Number.isSafeInteger(listTabId) || listTabId < 0) {
    throw new BatchQueueError('INVALID_LIST_TAB');
  }
  if (typeof contextKey !== 'string' || contextKey.length === 0) {
    throw new BatchQueueError('INVALID_CONTEXT');
  }
  if (!Array.isArray(entries)) {
    throw new BatchQueueError('INVALID_ENTRIES');
  }
  const normalizedLimits = validateLimits(limits);
  const at = Number.isFinite(startedAt) ? startedAt : Date.now();
  const seen = new Set();
  const queue = [];
  let captured = 0;
  let skippedCompleted = 0;
  let skippedUnknown = 0;
  for (const entry of entries) {
    if (!entry || !isValidProcessId(entry.processId) || seen.has(entry.processId)) {
      continue;
    }
    seen.add(entry.processId);
    captured += 1;
    const status = LIST_STATUS.has(entry.status) ? entry.status : 'unknown';
    if (status === 'completed') {
      skippedCompleted += 1;
      continue;
    }
    if (status !== 'pending') {
      skippedUnknown += 1;
      continue;
    }
    queue.push({
      processId: entry.processId,
      processLabel: typeof entry.processLabel === 'string' ? entry.processLabel : '',
      status: 'QUEUED',
    });
  }
  return {
    schemaVersion: 1,
    batchId,
    revision: 1,
    listTabId,
    contextKey,
    limits: normalizedLimits,
    saveAuthorized: saveAuthorized === true,
    queue,
    cursor: 0,
    counters: { examined: 0, saved: 0 },
    state: 'READY',
    current: null,
    diagnostics: {},
    events: [{ processId: null, code: 'CAPTURED', at }],
    updatedAt: at,
    capture: { captured, skippedCompleted, skippedUnknown },
  };
}

export function hasReachedLimit(batch) {
  if (!batch || !batch.counters || !batch.limits) {
    return true;
  }
  return batch.counters.examined >= batch.limits.maxExamined
    || batch.counters.saved >= batch.limits.maxSaved;
}

export function nextEligibleProcess(batch) {
  if (!batch || batch.state !== 'RUNNING' || hasReachedLimit(batch)) {
    return null;
  }
  const entry = batch.queue.find((item) => item.status === 'QUEUED');
  return entry ? { processId: entry.processId, processLabel: entry.processLabel } : null;
}
