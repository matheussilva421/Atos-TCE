export const MESSAGE = Object.freeze({
  REQUEST_FILL: 'REQUEST_FILL',
  READ_DOCUMENT: 'READ_DOCUMENT',
  APPLY_PLAN: 'APPLY_PLAN',
  FETCH_PDF: 'FETCH_PDF',
  DIAGNOSE_DOCUMENT: 'DIAGNOSE_DOCUMENT',
  DISCOVER_DOCUMENTS: 'DISCOVER_DOCUMENTS',
  DOCUMENT_SEARCH: 'DOCUMENT_SEARCH',
  DIAGNOSTIC_STATE: 'DIAGNOSTIC_STATE',
  GET_DIAGNOSTIC: 'GET_DIAGNOSTIC',
  DIAGNOSTIC_UPDATE: 'DIAGNOSTIC_UPDATE',
  BATCH_PREVIEW: 'BATCH_PREVIEW',
  BATCH_START: 'BATCH_START',
  BATCH_STATUS: 'BATCH_STATUS',
  BATCH_PAUSE: 'BATCH_PAUSE',
  BATCH_STOP: 'BATCH_STOP',
  BATCH_RESUME: 'BATCH_RESUME',
  BATCH_LIST_SNAPSHOT: 'BATCH_LIST_SNAPSHOT',
  BATCH_SELECT_INTERESTED: 'BATCH_SELECT_INTERESTED',
  BATCH_VALIDATE_FORM: 'BATCH_VALIDATE_FORM',
  BATCH_APPLY: 'BATCH_APPLY',
  BATCH_SAVE: 'BATCH_SAVE',
  BATCH_FORM_SNAPSHOT: 'BATCH_FORM_SNAPSHOT',
  BATCH_ENSURE_DOCUMENT: 'BATCH_ENSURE_DOCUMENT',
  BATCH_UI_UPDATE: 'BATCH_UI_UPDATE',
  FILTER_PRESET_GET: 'FILTER_PRESET_GET',
  FILTER_PRESET_SET: 'FILTER_PRESET_SET',
  FILTER_AUTO_CLAIM: 'FILTER_AUTO_CLAIM',
  FILTER_AUTO_DONE: 'FILTER_AUTO_DONE',
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
