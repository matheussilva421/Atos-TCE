const STATE_LABELS = Object.freeze({
  READY: { label: 'Pronto', tone: 'info' },
  RUNNING: { label: 'Em execução', tone: 'ok' },
  PAUSE_REQUESTED: { label: 'Pausa solicitada', tone: 'warn' },
  STOP_REQUESTED: { label: 'Parada solicitada', tone: 'warn' },
  PAUSED: { label: 'Pausado', tone: 'warn' },
  SUSPENDED: { label: 'Suspenso', tone: 'warn' },
  COMPLETED: { label: 'Concluído', tone: 'ok' },
  STOPPED: { label: 'Parado', tone: 'warn' },
  SAVE_PENDING: { label: 'Salvamento pendente', tone: 'warn' },
});

const IDLE_CONTROLS = Object.freeze({
  canStart: true, canPause: false, canStop: false, canResume: false,
});

function toPositiveInteger(value) {
  const text = String(value ?? '').trim();
  if (!/^\d+$/.test(text)) {
    return null;
  }
  const parsed = Number(text);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

export function validateLimitsInput(input) {
  const maxExamined = toPositiveInteger(input ? input.maxExamined : '');
  const maxSaved = toPositiveInteger(input ? input.maxSaved : '');
  if (maxExamined === null || maxSaved === null) {
    return { ok: false, code: 'INVALID_LIMIT' };
  }
  return { ok: true, limits: { maxExamined, maxSaved } };
}

export function describeBatchState(state) {
  return STATE_LABELS[state] || { label: 'Estado desconhecido', tone: 'warn' };
}

export function describeControls(status) {
  if (!status || !status.state) {
    return { ...IDLE_CONTROLS };
  }
  switch (status.state) {
    case 'RUNNING':
      return { canStart: false, canPause: true, canStop: true, canResume: false };
    case 'PAUSE_REQUESTED':
      return { canStart: false, canPause: false, canStop: true, canResume: false };
    case 'STOP_REQUESTED':
      return { canStart: false, canPause: false, canStop: false, canResume: false };
    case 'PAUSED':
      return { canStart: false, canPause: false, canStop: true, canResume: true };
    case 'SUSPENDED':
      return { canStart: false, canPause: false, canStop: false, canResume: true };
    case 'COMPLETED':
    case 'STOPPED':
      return { ...IDLE_CONTROLS };
    default:
      return { canStart: false, canPause: false, canStop: false, canResume: false };
  }
}

export function formatSummary(status) {
  if (!status) {
    return 'Nenhum lote ativo.';
  }
  const totals = status.report && status.report.totals ? status.report.totals : null;
  const captured = totals ? totals.captured : status.captured || 0;
  const skippedCompleted = totals ? totals.skippedCompleted : 0;
  const skippedUnknown = totals ? totals.skippedUnknown : 0;
  const queued = totals ? totals.queued : status.queueLength || 0;
  const examined = totals ? totals.examined : status.examined || 0;
  const saved = totals ? totals.saved : status.saved || 0;
  const confirmed = totals ? totals.confirmed : 0;
  const state = describeBatchState(status.state).label;
  return state + '. ' + captured + ' capturados, ' + skippedCompleted + ' pré-concluídos, '
    + skippedUnknown + ' sem status, ' + queued + ' na fila. '
    + examined + ' examinados, ' + saved + ' salvos, ' + confirmed + ' confirmados.';
}
