import { hasReachedLimit } from './queue.mjs';

export class InvalidTransition extends Error {
  constructor(reason) {
    super(reason);
    this.name = 'InvalidTransition';
    this.code = 'INVALID_TRANSITION';
    this.reason = reason;
  }
}

const PHASES = ['EXAMINING', 'READING', 'FILLING', 'VALIDATING'];
const TERMINAL_STATUS = new Set(['CONFIRMED', 'SKIPPED', 'REVIEW_REQUIRED', 'FAILED']);

function fail(reason) {
  throw new InvalidTransition(reason);
}

/**
 * Redutor puro do lote. Cada evento aceito incrementa a revisão exatamente uma vez.
 * @param {object} batch
 * @param {{type: string, at?: number, [key: string]: unknown}} event
 * @returns {object} novo BatchRecord
 */
export function reduceBatch(batch, event) {
  if (!batch || typeof batch !== 'object') {
    fail('INVALID_BATCH');
  }
  if (!event || typeof event.type !== 'string') {
    fail('INVALID_EVENT');
  }
  const at = Number.isFinite(event.at) ? event.at : Date.now();
  const next = structuredClone(batch);
  const current = next.current;
  const entryFor = (processId) => next.queue.find((item) => item.processId === processId);

  const finishProcess = (status, code) => {
    if (!current) {
      fail('NO_CURRENT_PROCESS');
    }
    if (current.saveAttemptId) {
      fail('SAVE_ATTEMPT_ACTIVE');
    }
    const entry = entryFor(current.processId);
    if (!entry || TERMINAL_STATUS.has(entry.status)) {
      fail('PROCESS_FINISHED');
    }
    entry.status = status;
    next.current = null;
    next.events.push({ processId: current.processId, code, at });
    if (next.state === 'PAUSE_REQUESTED') {
      next.state = 'PAUSED';
    } else if (next.state === 'STOP_REQUESTED') {
      next.state = 'STOPPED';
    }
  };

  switch (event.type) {
    case 'START': {
      if (next.state !== 'READY') {
        fail('BATCH_NOT_READY');
      }
      next.state = 'RUNNING';
      break;
    }
    case 'BEGIN_PROCESS': {
      if (next.state !== 'RUNNING' || current) {
        fail('BATCH_NOT_RUNNING');
      }
      const entry = entryFor(event.processId);
      if (!entry || entry.status !== 'QUEUED') {
        fail('PROCESS_NOT_QUEUED');
      }
      if (next.counters.examined + 1 > next.limits.maxExamined) {
        fail('EXAMINED_LIMIT');
      }
      entry.status = 'EXAMINING';
      next.counters.examined += 1;
      next.cursor = next.queue.indexOf(entry) + 1;
      next.current = { processId: entry.processId, phase: 'EXAMINING', saveAttemptId: null };
      break;
    }
    case 'ADVANCE_PHASE': {
      if (next.state !== 'RUNNING' || !current) {
        fail('NO_CURRENT_PROCESS');
      }
      const from = PHASES.indexOf(current.phase);
      const to = PHASES.indexOf(event.phase);
      if (from < 0 || to !== from + 1) {
        fail('INVALID_PHASE_ORDER');
      }
      current.phase = event.phase;
      const entry = entryFor(current.processId);
      if (entry) {
        entry.status = event.phase;
      }
      break;
    }
    case 'SAVE_ARMED': {
      if (!current) {
        fail('NO_CURRENT_PROCESS');
      }
      if (current.saveAttemptId) {
        fail('ALREADY_ARMED');
      }
      if (current.phase !== 'VALIDATING') {
        fail('FORM_NOT_VALIDATED');
      }
      if (typeof event.saveAttemptId !== 'string' || event.saveAttemptId.length < 6) {
        fail('INVALID_ATTEMPT_ID');
      }
      current.phase = 'SAVE_PENDING';
      current.saveAttemptId = event.saveAttemptId;
      const entry = entryFor(current.processId);
      if (entry) {
        entry.status = 'SAVE_PENDING';
      }
      break;
    }
    case 'SAVE_ACK': {
      if (!current || !current.saveAttemptId) {
        fail('NO_SAVE_ATTEMPT');
      }
      if (!['SAVE_PENDING', 'VERIFYING', 'SAVE_UNCERTAIN'].includes(current.phase)) {
        fail('NOT_AWAITING_SAVE');
      }
      const entry = entryFor(current.processId);
      if (!entry || entry.status === 'CONFIRMED') {
        fail('ALREADY_CONFIRMED');
      }
      if (next.counters.saved + 1 > next.limits.maxSaved) {
        fail('SAVED_LIMIT');
      }
      entry.status = 'CONFIRMED';
      next.counters.saved += 1;
      next.current = null;
      if (next.state === 'PAUSE_REQUESTED') {
        next.state = 'PAUSED';
      } else if (next.state === 'STOP_REQUESTED') {
        next.state = 'STOPPED';
      }
      break;
    }
    case 'SAVE_NOT_DISPATCHED': {
      if (!current || !current.saveAttemptId) {
        fail('NO_SAVE_ATTEMPT');
      }
      const entry = entryFor(current.processId);
      if (!entry || TERMINAL_STATUS.has(entry.status)) {
        fail('PROCESS_FINISHED');
      }
      entry.status = 'FAILED';
      next.events.push({ processId: current.processId, code: 'SAVE_NOT_DISPATCHED', at });
      next.current = null;
      if (next.state === 'PAUSE_REQUESTED') {
        next.state = 'PAUSED';
      } else if (next.state === 'STOP_REQUESTED') {
        next.state = 'STOPPED';
      }
      break;
    }
    case 'MARK_SKIPPED':
      finishProcess('SKIPPED', 'SKIPPED');
      break;
    case 'MARK_FILLED':
      finishProcess('FILLED', 'FILLED');
      break;
    case 'MARK_REVIEW':
      finishProcess('REVIEW_REQUIRED', 'REVIEW_REQUIRED');
      break;
    case 'MARK_FAILED':
      finishProcess('FAILED', 'FAILED');
      break;
    case 'MARK_UNCERTAIN': {
      if (!current || !current.saveAttemptId) {
        fail('NO_SAVE_ATTEMPT');
      }
      const entry = entryFor(current.processId);
      if (!entry || entry.status === 'CONFIRMED') {
        fail('PROCESS_FINISHED');
      }
      entry.status = 'SAVE_UNCERTAIN';
      current.phase = 'SAVE_UNCERTAIN';
      next.state = 'SUSPENDED';
      break;
    }
    case 'REQUEST_PAUSE': {
      if (next.state !== 'RUNNING') {
        fail('BATCH_NOT_RUNNING');
      }
      next.state = current ? 'PAUSE_REQUESTED' : 'PAUSED';
      break;
    }
    case 'REQUEST_STOP': {
      if (!['RUNNING', 'PAUSE_REQUESTED'].includes(next.state)) {
        fail('BATCH_NOT_RUNNING');
      }
      next.state = current ? 'STOP_REQUESTED' : 'STOPPED';
      break;
    }
    case 'PAUSE_SAFE': {
      if (next.state !== 'PAUSE_REQUESTED' || current) {
        fail('NOT_SAFE_TO_PAUSE');
      }
      next.state = 'PAUSED';
      break;
    }
    case 'STOP_SAFE': {
      if (next.state !== 'STOP_REQUESTED' || current) {
        fail('NOT_SAFE_TO_STOP');
      }
      next.state = 'STOPPED';
      break;
    }
    case 'COMPLETE': {
      if (current) {
        fail('PROCESS_IN_PROGRESS');
      }
      const remaining = next.queue.some((entry) => entry.status === 'QUEUED');
      if (remaining && !hasReachedLimit(next)) {
        fail('WORK_REMAINING');
      }
      next.state = 'COMPLETED';
      break;
    }
    case 'SUSPEND': {
      if (!['RUNNING', 'PAUSE_REQUESTED', 'STOP_REQUESTED', 'PAUSED'].includes(next.state)) {
        fail('BATCH_NOT_ACTIVE');
      }
      next.state = 'SUSPENDED';
      break;
    }
    case 'RESUME_AUTHORIZED': {
      if (!['PAUSED', 'SUSPENDED'].includes(next.state)) {
        fail('BATCH_NOT_RESUMABLE');
      }
      next.state = 'RUNNING';
      break;
    }
    default:
      fail('UNKNOWN_EVENT');
  }

  next.revision = Number.isSafeInteger(next.revision) ? next.revision + 1 : 1;
  next.updatedAt = at;
  next.events.push({
    processId: event.processId ?? (next.current ? next.current.processId : null),
    code: event.type,
    at,
    ...(typeof event.reason === 'string' ? { reason: event.reason.slice(0, 40) } : {}),
  });
  return next;
}
