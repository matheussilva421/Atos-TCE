const TRANSIENT_CODES = new Set(['TRANSIENT_READ', 'DOM_NOT_READY', 'FORM_NOT_LOADED']);
const PAUSE_CODES = new Set(['ROUTE_CHANGED', 'SESSION_EXPIRED', 'CONTEXT_CHANGED', 'LIST_CHANGED']);
const SYSTEMIC_LIMIT = 3;
const TRANSIENT_LIMIT = 3;

/**
 * Aguarda uma condição observável com timeout e cancelamento. Nunca usa espera fixa longa:
 * repete a leitura em intervalos curtos e encerra no primeiro sinal de mudança de contexto.
 * @param {() => boolean | Promise<boolean>} predicate
 * @param {{timeoutMs?: number, pollMs?: number, signal?: AbortSignal}} options
 * @returns {Promise<boolean>}
 */
export async function waitForCondition(predicate, options = {}) {
  const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 5000;
  const pollMs = Number.isFinite(options.pollMs) ? Math.max(1, options.pollMs) : 100;
  const signal = options.signal;
  const sleep = options.sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const started = Date.now();
  for (;;) {
    if (signal && signal.aborted) {
      return false;
    }
    try {
      if (await predicate()) {
        return true;
      }
    } catch (error) {
      if (error && (PAUSE_CODES.has(error.code) || error.code === 'ABORT')) {
        return false;
      }
      throw error;
    }
    if (Date.now() - started >= timeoutMs) {
      return false;
    }
    await sleep(pollMs);
  }
}

function countCode(history, predicate) {
  return (Array.isArray(history) ? history : []).filter((entry) => predicate(entry && entry.code)).length;
}

/**
 * Classifica uma falha: 'retry' | 'review' | 'pause' | 'suspend'.
 * Falha de salvamento com resultado desconhecido nunca gera repetição.
 */
export function classifyFailure(stage, error, history = []) {
  const code = error && error.code ? error.code : 'UNKNOWN';
  if (stage === 'save') {
    if (code === 'SAVE_RESULT_UNKNOWN' || code === 'TIMEOUT' || code === 'NO_ACK') {
      return 'suspend';
    }
    return 'review';
  }
  if (PAUSE_CODES.has(code)) {
    return 'pause';
  }
  if (TRANSIENT_CODES.has(code)) {
    return countCode(history, (previous) => TRANSIENT_CODES.has(previous)) >= TRANSIENT_LIMIT
      ? 'pause'
      : 'retry';
  }
  if (countCode(history, (previous) => previous === 'SYSTEMIC') >= SYSTEMIC_LIMIT) {
    return 'pause';
  }
  return 'review';
}
