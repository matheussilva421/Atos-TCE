export const DIAGNOSTIC_KEY = 'complementadorL1Diagnostic';

export const DIAGNOSTIC_STATES = Object.freeze({
  L1_STARTED: 'L1_STARTED',
  SOURCE_TAB_RESOLVED: 'SOURCE_TAB_RESOLVED',
  IFRAME_IDENTIFIED: 'IFRAME_IDENTIFIED',
  PDF_FETCH_STARTED: 'PDF_FETCH_STARTED',
  PDF_FETCH_OK: 'PDF_FETCH_OK',
  PDF_VALIDATED: 'PDF_VALIDATED',
  PDF_TEXT_EXTRACTED: 'PDF_TEXT_EXTRACTED',
  L1_SUCCESS: 'L1_SUCCESS',
  L1_ERROR: 'L1_ERROR',
  L1_TIMEOUT: 'L1_TIMEOUT',
  L1_CANCELLED: 'L1_CANCELLED',
});

const FINAL_STATES = new Set([
  DIAGNOSTIC_STATES.L1_SUCCESS,
  DIAGNOSTIC_STATES.L1_ERROR,
  DIAGNOSTIC_STATES.L1_TIMEOUT,
  DIAGNOSTIC_STATES.L1_CANCELLED,
]);

const METRIC_KEYS = Object.freeze([
  'elapsedMs',
  'byteLength',
  'pagesCount',
  'totalChars',
  'minPageChars',
  'maxPageChars',
  'sourceKind',
  'errorCode',
]);

const ALLOWED_STATES = new Set(Object.values(DIAGNOSTIC_STATES));
const SAFE_CODE = /^[A-Za-z0-9_.:-]{1,80}$/;

function safeInteger(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
    ? Math.floor(value)
    : undefined;
}

export function sanitizeDiagnosticDetails(details) {
  const source = details && typeof details === 'object' ? details : {};
  const safe = {};
  for (const key of METRIC_KEYS) {
    const value = source[key];
    if (key === 'sourceKind' || key === 'errorCode') {
      if (typeof value === 'string' && SAFE_CODE.test(value)) {
        safe[key] = value;
      }
      continue;
    }
    const number = safeInteger(value);
    if (number !== undefined) {
      safe[key] = number;
    }
  }
  return safe;
}

function sanitizeSteps(steps) {
  if (!Array.isArray(steps)) {
    return [];
  }
  return steps
    .filter((step) => step && ALLOWED_STATES.has(step.state))
    .map((step) => ({
      state: step.state,
      at: safeInteger(step.at) || 0,
      elapsedMs: safeInteger(step.elapsedMs) || 0,
    }))
    .slice(-64);
}

export function sanitizeDiagnostic(value) {
  if (!value || typeof value !== 'object' || !ALLOWED_STATES.has(value.state)) {
    return null;
  }
  const safe = sanitizeDiagnosticDetails(value);
  return {
    state: value.state,
    startedAt: safeInteger(value.startedAt) || 0,
    updatedAt: safeInteger(value.updatedAt) || 0,
    elapsedMs: safeInteger(value.elapsedMs) || 0,
    ...safe,
    steps: sanitizeSteps(value.steps),
  };
}

export function isFinalDiagnosticState(state) {
  return FINAL_STATES.has(state);
}

export function formatDiagnosticSummary(value) {
  const diagnostic = sanitizeDiagnostic(value);
  if (!diagnostic) {
    return '';
  }
  const parts = ['Último L1: ' + diagnostic.state];
  if (typeof diagnostic.pagesCount === 'number') {
    parts.push(diagnostic.pagesCount + ' página(s)');
  }
  if (typeof diagnostic.totalChars === 'number') {
    parts.push(diagnostic.totalChars + ' caractere(s)');
  }
  if (typeof diagnostic.elapsedMs === 'number') {
    parts.push(diagnostic.elapsedMs + ' ms');
  }
  if (diagnostic.errorCode) {
    parts.push(diagnostic.errorCode);
  }
  return parts.join(' · ');
}

export function createDiagnosticRecorder(storage) {
  if (!storage || typeof storage.get !== 'function' || typeof storage.set !== 'function' || typeof storage.remove !== 'function') {
    throw new Error('Storage do diagnóstico indisponível.');
  }
  let queue = Promise.resolve();

  function enqueue(task) {
    queue = queue.then(task, task).catch(() => null);
    return queue;
  }

  async function readStored() {
    const values = await storage.get(DIAGNOSTIC_KEY);
    return sanitizeDiagnostic(values ? values[DIAGNOSTIC_KEY] : null);
  }

  return {
    reset() {
      return enqueue(async () => {
        await storage.remove(DIAGNOSTIC_KEY);
        return null;
      });
    },
    read() {
      return enqueue(async () => {
        try {
          return await readStored();
        } catch {
          return null;
        }
      });
    },
    record(state, details = {}) {
      if (!ALLOWED_STATES.has(state)) {
        throw new Error('Estado de diagnóstico inválido.');
      }
      return enqueue(async () => {
        const current = await readStored();
        const now = Date.now();
        const starting = state === DIAGNOSTIC_STATES.L1_STARTED;
        const startedAt = starting ? now : (current ? current.startedAt : now);
        const safe = sanitizeDiagnosticDetails(details);
        const elapsed = typeof safe.elapsedMs === 'number' ? safe.elapsedMs : Math.max(0, now - startedAt);
        const steps = starting ? [] : (current ? current.steps : []);
        steps.push({ state, at: now, elapsedMs: elapsed });
        const metrics = starting || !current ? {} : sanitizeDiagnosticDetails(current);
        const next = sanitizeDiagnostic({
          ...metrics,
          ...safe,
          state,
          startedAt,
          updatedAt: now,
          elapsedMs: elapsed,
          steps,
        });
        await storage.set({ [DIAGNOSTIC_KEY]: next });
        return next;
      });
    },
  };
}