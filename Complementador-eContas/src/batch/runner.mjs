import { loadBatch, saveBatch } from './journal.mjs';
import { nextEligibleProcess } from './queue.mjs';
import { reduceBatch } from './state-machine.mjs';

const REVIEW_CODES = new Set([
  'MULTIPLE_INTERESTED', 'NO_INTERESTED', 'CARDS_NOT_LOADED', 'INTERESTED_WITHOUT_IDENTITY',
  'SELECTION_NOT_CONFIRMED', 'WRONG_PROCESS', 'DOCUMENTS_NOT_FOUND', 'AMBIGUOUS_DOCUMENT',
  'FIELD_CONFLICT', 'MISSING_FIELDS', 'FORM_REVISION_CHANGED', 'PROCESS_NOT_PENDING',
  'WRONG_PROCESS_TAB', 'TAB_CLOSED', 'INVALID_WORKSPACE',
]);

function eventForFailure(code) {
  return REVIEW_CODES.has(code) ? 'MARK_REVIEW' : 'MARK_FAILED';
}

async function persist(storage, batch, event) {
  const next = reduceBatch(batch, event);
  await saveBatch(storage, next);
  return { state: next.state, needsWake: next.state === 'RUNNING' };
}

const inFlight = new Map();

/**
 * Executa no máximo uma transição por chamada. O estado é sempre recarregado do
 * diário antes de agir, e o checkpoint SAVE_PENDING é persistido antes do clique.
 */
export async function runOneStep({ batchId, deps }) {
  if (inFlight.has(batchId)) {
    return { state: 'BUSY', needsWake: true };
  }
  inFlight.set(batchId, true);
  try {
    return await stepOnce({ batchId, deps });
  } finally {
    inFlight.delete(batchId);
  }
}

async function stepOnce({ batchId, deps }) {
  if (!deps || !deps.storage) {
    return { state: 'IDLE', needsWake: false };
  }
  let batch;
  try {
    batch = await loadBatch(deps.storage);
  } catch {
    return { state: 'UNAVAILABLE', needsWake: false };
  }
  if (!batch || batch.batchId !== batchId) {
    return { state: 'IDLE', needsWake: false };
  }
  if (batch.state === 'SUSPENDED') {
    if (batch.current && batch.current.saveAttemptId) {
      const observed = await deps.verify({
        processId: batch.current.processId,
        attemptId: batch.current.saveAttemptId,
      }).catch(() => null);
      if (observed && observed.status === 'confirmed') {
        return persist(deps.storage, batch, { type: 'SAVE_ACK', at: deps.now() });
      }
    }
    return { state: 'SUSPENDED', needsWake: false };
  }
  if (batch.state !== 'RUNNING') {
    return { state: batch.state, needsWake: false };
  }

  if (!batch.current) {
    const next = nextEligibleProcess(batch);
    if (!next) {
      return persist(deps.storage, batch, { type: 'COMPLETE', at: deps.now() });
    }
    return persist(deps.storage, batch, { type: 'BEGIN_PROCESS', processId: next.processId, at: deps.now() });
  }

  const processId = batch.current.processId;
  const phase = batch.current.phase;
  try {
    if (phase === 'EXAMINING') {
      const workspace = await deps.openWorkspace({ processId });
      const selected = await deps.selectInterested({
        processId,
        autosTabId: workspace.autosTabId,
        formTabId: workspace.formTabId,
      });
      if (!selected || !selected.ok) {
        return persist(deps.storage, batch, {
          type: eventForFailure(selected && selected.code),
          reason: (selected && selected.code) || 'SELECTION_FAILED',
          at: deps.now(),
        });
      }
      deps.session = { processId, ...workspace, interestedKey: selected.interestedKey };
      return persist(deps.storage, batch, { type: 'ADVANCE_PHASE', phase: 'READING', at: deps.now() });
    }

    if (phase === 'READING') {
      const filled = await deps.fill({
        processId,
        autosTabId: deps.session && deps.session.autosTabId,
        formTabId: deps.session && deps.session.formTabId,
        interestedKey: deps.session && deps.session.interestedKey,
      });
      if (!filled || !filled.ok) {
        return persist(deps.storage, batch, {
          type: eventForFailure(filled && filled.code),
          reason: (filled && filled.code) || 'FILL_FAILED',
          at: deps.now(),
        });
      }
      return persist(deps.storage, batch, { type: 'ADVANCE_PHASE', phase: 'FILLING', at: deps.now() });
    }

    if (phase === 'FILLING') {
      const validated = await deps.validate({
        processId,
        formTabId: deps.session && deps.session.formTabId,
        interestedKey: deps.session && deps.session.interestedKey,
      });
      if (!validated || !validated.ok) {
        return persist(deps.storage, batch, {
          type: eventForFailure(validated && validated.code),
          reason: (validated && validated.code) || 'VALIDATION_FAILED',
          at: deps.now(),
        });
      }
      return persist(deps.storage, batch, { type: 'ADVANCE_PHASE', phase: 'VALIDATING', at: deps.now() });
    }

    if (phase === 'VALIDATING') {
      if (deps.saveEnabled !== true) {
        return persist(deps.storage, batch, { type: 'SUSPEND', at: deps.now() });
      }
      const attemptId = deps.newAttemptId(processId);
      const armed = await persist(deps.storage, batch, {
        type: 'SAVE_ARMED', saveAttemptId: attemptId, at: deps.now(),
      });
      const outcome = await deps.save({ processId, attemptId });
      const stored = await loadBatch(deps.storage);
      if (outcome && outcome.attempted === false) {
        return persist(deps.storage, stored, { type: 'SAVE_NOT_DISPATCHED', at: deps.now() });
      }
      if (!outcome || outcome.result !== 'ack') {
        return persist(deps.storage, stored, { type: 'MARK_UNCERTAIN', at: deps.now() });
      }
      const observed = await deps.verify({ processId, attemptId });
      if (observed && observed.status === 'confirmed') {
        return persist(deps.storage, stored, { type: 'SAVE_ACK', at: deps.now() });
      }
      return persist(deps.storage, stored, { type: 'MARK_UNCERTAIN', at: deps.now() });
    }
  } catch (error) {
    const code = error && error.code ? error.code : 'DEPENDENCY_ERROR';
    return persist(deps.storage, batch, {
      type: eventForFailure(code), reason: code, at: deps.now(),
    });
  }

  return { state: batch.state, needsWake: false };
}
