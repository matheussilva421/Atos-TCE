export const WAKE_MARKER_KEY = 'complementadorBatchRuntimeMarker';

const ACTIVE_STATES = new Set([
  'READY', 'RUNNING', 'PAUSE_REQUESTED', 'STOP_REQUESTED', 'PAUSED', 'SUSPENDED',
]);

/**
 * Decide a reentrada após o service worker acordar. O marcador fica em
 * chrome.storage.session, que sobrevive à suspensão do worker mas é limpo quando
 * o navegador reinicia. Reinício => suspender e exigir "Continuar".
 */
export function decideWake({ batch, sessionMarker, runtimeId }) {
  if (!batch) {
    return { action: 'idle', reason: 'no_batch' };
  }
  if (!ACTIVE_STATES.has(batch.state)) {
    return { action: 'noop', reason: 'terminal' };
  }
  const markerValid = Boolean(
    sessionMarker
    && typeof sessionMarker === 'object'
    && sessionMarker.runtimeId === runtimeId,
  );
  if (!markerValid) {
    return { action: 'suspend', reason: 'browser_restart' };
  }
  if (batch.state !== 'RUNNING') {
    return { action: 'noop', reason: 'not_running' };
  }
  if (batch.current && batch.current.saveAttemptId) {
    return { action: 'drive', reason: 'save_reconciliation' };
  }
  return { action: 'drive', reason: 'normal_worker_wake' };
}
