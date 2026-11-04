export const MESSAGE = Object.freeze({
  REQUEST_FILL: 'REQUEST_FILL',
  READ_DOCUMENT: 'READ_DOCUMENT',
  APPLY_PLAN: 'APPLY_PLAN',
  FETCH_PDF: 'FETCH_PDF',
  DIAGNOSE_DOCUMENT: 'DIAGNOSE_DOCUMENT',
  FIND_BIRTH_DOCUMENT: 'FIND_BIRTH_DOCUMENT',
  BIRTH_SEARCH: 'BIRTH_SEARCH',
  DIAGNOSTIC_STATE: 'DIAGNOSTIC_STATE',
  GET_DIAGNOSTIC: 'GET_DIAGNOSTIC',
  DIAGNOSTIC_UPDATE: 'DIAGNOSTIC_UPDATE',
  RESULT: 'RESULT',
  CANCEL: 'CANCEL',
});

export const RESULT_STATUS = Object.freeze({
  OK: 'ok',
  PARTIAL: 'partial',
  ERROR: 'error',
});

export function createRequestId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return 'req-' + Date.now() + '-' + Math.random().toString(16).slice(2);
}

export function isRequestId(value) {
  return typeof value === 'string' && /^[A-Za-z0-9._:-]{8,80}$/.test(value);
}

export function errorResult(requestId, code, message, details = undefined) {
  return {
    type: MESSAGE.RESULT,
    requestId,
    ok: false,
    status: RESULT_STATUS.ERROR,
    error: { code, message, ...(details ? { details } : {}) },
  };
}

export function okResult(requestId, payload = {}) {
  return { type: MESSAGE.RESULT, requestId, ok: true, status: RESULT_STATUS.OK, ...payload };
}
