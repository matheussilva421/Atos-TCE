export const BATCH_JOURNAL_KEY = 'complementadorBatchJournal';
export const JOURNAL_SCHEMA_VERSION = 1;

export class JournalError extends Error {
  constructor(code, cause) {
    super(code);
    this.name = 'JournalError';
    this.code = code;
    if (cause) {
      this.cause = cause;
    }
  }
}

function toInt(value, fallback = 0) {
  return Number.isSafeInteger(value) ? value : fallback;
}

function normalizeCurrent(current) {
  if (!current || typeof current !== 'object') {
    return null;
  }
  return {
    processId: typeof current.processId === 'string' ? current.processId : '',
    phase: typeof current.phase === 'string' ? current.phase : 'EXAMINING',
    saveAttemptId: typeof current.saveAttemptId === 'string' ? current.saveAttemptId : null,
  };
}

/**
 * Reduz o lote ao subconjunto persistível: apenas identificadores e estados técnicos.
 * Nome, CPF, matrícula, nascimento, PDFs, HTML, URLs assinadas e valores de campo são descartados.
 */
export function sanitizeBatch(batch) {
  if (!batch || typeof batch !== 'object' || Array.isArray(batch)) {
    throw new JournalError('CORRUPTED');
  }
  if (batch.schemaVersion !== JOURNAL_SCHEMA_VERSION) {
    throw new JournalError('SCHEMA_MISMATCH');
  }
  if (typeof batch.batchId !== 'string' || batch.batchId.length === 0) {
    throw new JournalError('CORRUPTED');
  }
  if (!Array.isArray(batch.queue)) {
    throw new JournalError('CORRUPTED');
  }
  const counters = batch.counters && typeof batch.counters === 'object' ? batch.counters : {};
  const limits = batch.limits && typeof batch.limits === 'object' ? batch.limits : {};
  const capture = batch.capture && typeof batch.capture === 'object' ? batch.capture : {};
  return {
    schemaVersion: JOURNAL_SCHEMA_VERSION,
    batchId: batch.batchId,
    revision: toInt(batch.revision, 1),
    listTabId: toInt(batch.listTabId),
    contextKey: typeof batch.contextKey === 'string' ? batch.contextKey : '',
    limits: {
      maxExamined: toInt(limits.maxExamined),
      maxSaved: toInt(limits.maxSaved),
    },
    saveAuthorized: batch.saveAuthorized === true,
    queue: batch.queue.map((entry) => ({
      processId: typeof entry?.processId === 'string' ? entry.processId : '',
      processLabel: typeof entry?.processLabel === 'string' ? entry.processLabel : '',
      status: typeof entry?.status === 'string' ? entry.status : 'unknown',
    })),
    cursor: toInt(batch.cursor),
    counters: {
      examined: toInt(counters.examined),
      saved: toInt(counters.saved),
    },
    state: typeof batch.state === 'string' ? batch.state : 'SUSPENDED',
    current: normalizeCurrent(batch.current),
    events: (Array.isArray(batch.events) ? batch.events : [])
      .filter((event) => event && typeof event === 'object')
      .slice(-200)
      .map((event) => ({
        processId: typeof event.processId === 'string' ? event.processId : null,
        code: typeof event.code === 'string' ? event.code.slice(0, 40) : '',
        at: toInt(event.at),
        ...(typeof event.reason === 'string' ? { reason: event.reason.slice(0, 40) } : {}),
      })),
    updatedAt: toInt(batch.updatedAt),
    capture: {
      captured: toInt(capture.captured),
      skippedCompleted: toInt(capture.skippedCompleted),
      skippedUnknown: toInt(capture.skippedUnknown),
    },
  };
}

export async function loadBatch(storage) {
  let raw;
  try {
    raw = await storage.get(BATCH_JOURNAL_KEY);
  } catch (error) {
    throw new JournalError('STORAGE_FAILURE', error);
  }
  const value = raw && typeof raw === 'object' ? raw[BATCH_JOURNAL_KEY] : undefined;
  if (value === undefined || value === null) {
    return null;
  }
  return sanitizeBatch(value);
}

export async function saveBatch(storage, batch) {
  const clean = sanitizeBatch(batch);
  try {
    await storage.set({ [BATCH_JOURNAL_KEY]: clean });
  } catch (error) {
    throw new JournalError('STORAGE_FAILURE', error);
  }
}

/**
 * Remove apenas lotes terminais e antigos. Lotes suspensos, pausados, ativos ou com
 * tentativa de salvamento pendente são preservados explicitamente.
 */
export async function compactJournal(storage, now = Date.now(), policy = {}) {
  const maxAge = Number.isFinite(policy.maxCompletedAgeMs)
    ? policy.maxCompletedAgeMs
    : 24 * 60 * 60 * 1000;
  let batch;
  try {
    batch = await loadBatch(storage);
  } catch {
    return { deleted: 0 };
  }
  if (!batch || batch.current) {
    return { deleted: 0 };
  }
  if (!['COMPLETED', 'STOPPED'].includes(batch.state)) {
    return { deleted: 0 };
  }
  if (now - batch.updatedAt < maxAge) {
    return { deleted: 0 };
  }
  await storage.remove(BATCH_JOURNAL_KEY);
  return { deleted: 1 };
}
