/**
 * Reconcilia o estado durável do lote com o que o portal mostra agora.
 * Nunca retoma sozinho após reinício do navegador, expiração de sessão,
 * troca de filtro/aba ou tentativa de salvamento com resultado incerto.
 */
export function classifyRecovery(batch, observation = {}) {
  if (!batch) {
    return { action: 'pause', reason: 'no_batch' };
  }
  const obs = observation || {};
  if (['COMPLETED', 'STOPPED'].includes(batch.state)) {
    return { action: 'complete', reason: 'terminal' };
  }
  const queue = Array.isArray(batch.queue) ? batch.queue : [];
  const uncertain = Boolean(batch.current && batch.current.saveAttemptId)
    || queue.some((entry) => entry && entry.status === 'SAVE_UNCERTAIN');
  if (uncertain) {
    return { action: 'suspend', reason: 'save_uncertain' };
  }
  if (obs.sessionOk === false) {
    return { action: 'pause', reason: 'session_expired' };
  }
  if (obs.tabOk === false) {
    return { action: 'pause', reason: 'tab_changed' };
  }
  if (typeof obs.listContextKey === 'string' && obs.listContextKey !== batch.contextKey) {
    return { action: 'pause', reason: 'filter_changed' };
  }
  if (obs.browserRestart) {
    return obs.resumeRequested
      ? { action: 'resume', reason: 'browser_restart_confirmed' }
      : { action: 'pause', reason: 'browser_restart' };
  }
  if (batch.state === 'PAUSED' || batch.state === 'SUSPENDED') {
    return obs.resumeRequested
      ? { action: 'resume', reason: 'resume_authorized' }
      : { action: 'pause', reason: 'resume_not_authorized' };
  }
  if (batch.state === 'RUNNING') {
    return { action: 'resume', reason: obs.workerWake ? 'normal_worker_wake' : 'active' };
  }
  return { action: 'pause', reason: 'unexpected_state' };
}
