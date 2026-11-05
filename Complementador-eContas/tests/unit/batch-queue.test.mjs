import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createFrozenBatch,
  hasReachedLimit,
  nextEligibleProcess,
  validateLimits,
} from '../../src/batch/queue.mjs';

const ENTRIES = [
  { processId: '101', processLabel: '101/2020', status: 'pending' },
  { processId: '102', processLabel: '102/2020', status: 'completed' },
  { processId: '103', processLabel: '103/2020', status: 'pending' },
  { processId: '101', processLabel: '101/2020', status: 'pending' },
  { processId: '104', processLabel: '104/2020', status: 'unknown' },
  { processId: '105', processLabel: '105/2020', status: 'pending' },
];

function build(overrides = {}) {
  return createFrozenBatch({
    batchId: 'batch-test-1',
    listTabId: 7,
    contextKey: 'ctx-a',
    entries: ENTRIES,
    limits: { maxExamined: 3, maxSaved: 2 },
    startedAt: 1000,
    ...overrides,
  });
}

test('limit_rejects_zero_negative_fraction_nan', () => {
  for (const limits of [
    { maxExamined: 0, maxSaved: 1 },
    { maxExamined: 1, maxSaved: -1 },
    { maxExamined: 1.5, maxSaved: 1 },
    { maxExamined: Number.NaN, maxSaved: 1 },
    { maxExamined: Number.POSITIVE_INFINITY, maxSaved: 1 },
    { maxExamined: '2', maxSaved: 1 },
    { maxSaved: 1 },
    null,
  ]) {
    assert.throws(() => validateLimits(limits), (error) => error.code === 'INVALID_LIMIT');
  }
  assert.deepEqual(validateLimits({ maxExamined: 2, maxSaved: 1 }), { maxExamined: 2, maxSaved: 1 });
});

test('precompleted_not_examined', () => {
  const batch = build();
  assert.deepEqual(batch.queue.map((entry) => entry.processId), ['101', '103', '105']);
  assert.deepEqual(batch.capture, { captured: 5, skippedCompleted: 1, skippedUnknown: 1 });
  assert.deepEqual(batch.counters, { examined: 0, saved: 0 });
});

test('captured_not_examined_until_started', () => {
  const batch = build();
  assert.equal(batch.counters.examined, 0);
  assert.equal(batch.state, 'READY');
  assert.equal(nextEligibleProcess(batch), null);
});

test('max_saved_one_never_submits_second', () => {
  const batch = build({ limits: { maxExamined: 5, maxSaved: 1 } });
  const running = { ...batch, state: 'RUNNING' };
  assert.equal(hasReachedLimit(running), false);
  assert.deepEqual(nextEligibleProcess(running), { processId: '101', processLabel: '101/2020' });
  const savedOnce = { ...running, counters: { examined: 1, saved: 1 } };
  assert.equal(hasReachedLimit(savedOnce), true);
  assert.equal(nextEligibleProcess(savedOnce), null);
});

test('freeze_preserves_initial_order', () => {
  const batch = build();
  assert.deepEqual(batch.queue.map((entry) => entry.processId), ['101', '103', '105']);
  assert.equal(batch.queue[0].status, 'QUEUED');
  assert.equal(batch.cursor, 0);
});

test('queue_exhaustion_stops', () => {
  const batch = build();
  const finished = {
    ...batch,
    state: 'RUNNING',
    queue: batch.queue.map((entry) => ({ ...entry, status: 'CONFIRMED' })),
  };
  assert.equal(nextEligibleProcess(finished), null);
});

test('no_pagination', () => {
  const batch = build({ pages: [{ entries: [] }], nextPage: 2 });
  assert.equal(batch.queue.length, 3);
  assert.equal(batch.capture.captured, 5);
  assert.equal('pages' in batch, false);
  assert.equal('nextPage' in batch, false);
});
