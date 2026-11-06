import test from 'node:test';
import assert from 'node:assert/strict';
import { createFrozenBatch, nextEligibleProcess } from '../../src/batch/queue.mjs';
import { reduceBatch } from '../../src/batch/state-machine.mjs';

const ENTRIES = [
  { processId: '201', processLabel: '201/2021', status: 'pending' },
  { processId: '202', processLabel: '202/2021', status: 'pending' },
];

function ready(limits = { maxExamined: 2, maxSaved: 2 }) {
  return createFrozenBatch({
    batchId: 'batch-sm',
    listTabId: 9,
    contextKey: 'ctx-sm',
    entries: ENTRIES,
    limits,
    startedAt: 500,
  });
}

function apply(batch, events) {
  return events.reduce((current, event, index) => reduceBatch(current, { at: 600 + index, ...event }), batch);
}

function validating(batch = ready()) {
  return apply(batch, [
    { type: 'START' },
    { type: 'BEGIN_PROCESS', processId: '201' },
    { type: 'ADVANCE_PHASE', phase: 'READING' },
    { type: 'ADVANCE_PHASE', phase: 'FILLING' },
    { type: 'ADVANCE_PHASE', phase: 'VALIDATING' },
  ]);
}

test('illegal_transition_rejected', () => {
  const batch = ready();
  assert.throws(() => reduceBatch(batch, { type: 'SAVE_ACK' }), (error) => error.code === 'INVALID_TRANSITION');
  assert.throws(() => reduceBatch({ ...batch, state: 'COMPLETED' }, { type: 'START' }),
    (error) => error.code === 'INVALID_TRANSITION');
  const running = apply(batch, [{ type: 'START' }]);
  assert.throws(() => reduceBatch(running, { type: 'ADVANCE_PHASE', phase: 'FILLING' }),
    (error) => error.code === 'INVALID_TRANSITION');
});

test('save_uncertain_is_nonterminal_for_reconciliation', () => {
  const armed = apply(validating(), [{ type: 'SAVE_ARMED', saveAttemptId: 'attempt-1' }]);
  const uncertain = apply(armed, [{ type: 'MARK_UNCERTAIN' }]);
  assert.equal(uncertain.state, 'SUSPENDED');
  assert.equal(uncertain.queue[0].status, 'SAVE_UNCERTAIN');
  assert.equal(uncertain.current.saveAttemptId, 'attempt-1');
  assert.equal(uncertain.counters.saved, 0);
  const resumed = reduceBatch(uncertain, { type: 'RESUME_AUTHORIZED', at: 900 });
  assert.equal(resumed.state, 'RUNNING');
  assert.equal(resumed.current.saveAttemptId, 'attempt-1');
});

test('only_ack_increments_saved', () => {
  const armed = apply(validating(), [{ type: 'SAVE_ARMED', saveAttemptId: 'attempt-2' }]);
  assert.equal(armed.counters.saved, 0);
  const acked = apply(armed, [{ type: 'SAVE_ACK' }]);
  assert.equal(acked.counters.saved, 1);
  assert.equal(acked.queue[0].status, 'CONFIRMED');
  assert.equal(acked.current, null);
});

test('begin_process_increments_examined_once', () => {
  const running = apply(ready(), [{ type: 'START' }]);
  const begun = apply(running, [{ type: 'BEGIN_PROCESS', processId: '201' }]);
  assert.equal(begun.counters.examined, 1);
  assert.throws(() => reduceBatch(begun, { type: 'BEGIN_PROCESS', processId: '201' }),
    (error) => error.code === 'INVALID_TRANSITION');
  assert.equal(begun.counters.examined, 1);
  const again = apply(begun, [{ type: 'MARK_REVIEW' }, { type: 'BEGIN_PROCESS', processId: '202' }]);
  assert.equal(again.counters.examined, 2);
  assert.equal(again.counters.examined <= again.limits.maxExamined, true);
});

test('pause_request_stops_next_process', () => {
  const started = apply(validating(), []);
  const paused = reduceBatch(started, { type: 'REQUEST_PAUSE', at: 950 });
  assert.equal(paused.state, 'PAUSE_REQUESTED');
  assert.equal(nextEligibleProcess(paused), null);
  const armed = reduceBatch(paused, { type: 'SAVE_ARMED', saveAttemptId: 'attempt-3', at: 951 });
  const acked = reduceBatch(armed, { type: 'SAVE_ACK', at: 952 });
  assert.equal(acked.counters.saved, 1);
  assert.equal(acked.state, 'PAUSED');
  assert.equal(nextEligibleProcess(acked), null);
  const resumed = reduceBatch(acked, { type: 'RESUME_AUTHORIZED', at: 954 });
  assert.equal(resumed.state, 'RUNNING');
});

test('confirmed_id_cannot_confirm_twice', () => {
  const armed = apply(validating(), [{ type: 'SAVE_ARMED', saveAttemptId: 'attempt-4' }]);
  const acked = apply(armed, [{ type: 'SAVE_ACK' }]);
  assert.throws(() => reduceBatch(acked, { type: 'SAVE_ACK' }), (error) => error.code === 'INVALID_TRANSITION');
  assert.equal(acked.counters.saved, 1);
});

test('fill_only_marks_filled_without_saving', () => {
  const filled = reduceBatch(validating(ready()), { type: 'MARK_FILLED', at: 950 });
  assert.equal(filled.queue[0].status, 'FILLED');
  assert.equal(filled.counters.saved, 0);
  assert.equal(filled.current, null);
  assert.equal(filled.state, 'RUNNING');
});
