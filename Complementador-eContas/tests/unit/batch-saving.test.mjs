import test from 'node:test';
import assert from 'node:assert/strict';
import { createFrozenBatch } from '../../src/batch/queue.mjs';
import { reduceBatch } from '../../src/batch/state-machine.mjs';
import { loadBatch, saveBatch, BATCH_JOURNAL_KEY } from '../../src/batch/journal.mjs';
import { runOneStep } from '../../src/batch/runner.mjs';

function memoryStorage() {
  const data = {};
  const writes = [];
  return {
    data,
    writes,
    async get(key) {
      return key in data ? { [key]: data[key] } : {};
    },
    async set(values) {
      for (const [key, value] of Object.entries(values)) {
        data[key] = value;
        writes.push({ key, value });
      }
    },
    async remove(key) {
      delete data[key];
    },
  };
}

async function runningBatch(storage, limits = { maxExamined: 1, maxSaved: 1 }) {
  const created = createFrozenBatch({
    batchId: 'batch-runner',
    listTabId: 7,
    contextKey: 'ctx-r',
    entries: [{ processId: '301', processLabel: '301/2020', status: 'pending' }],
    limits,
    startedAt: 10,
  });
  const running = reduceBatch(created, { type: 'START', at: 11 });
  await saveBatch(storage, running);
  return running;
}

function deps(overrides = {}) {
  const calls = [];
  return {
    calls,
    storage: overrides.storage,
    now: () => 1000,
    newAttemptId: () => 'attempt-301-1',
    openWorkspace: async ({ processId }) => { calls.push('open'); return { autosTabId: 41, formTabId: 42 }; },
    selectInterested: async () => { calls.push('select'); return { ok: true, interestedKey: 'key-1' }; },
    fill: async () => { calls.push('fill'); return { ok: true }; },
    validate: async () => { calls.push('validate'); return { ok: true }; },
    saveEnabled: true,
    save: async () => { calls.push('save'); return { attempted: true, result: 'ack' }; },
    verify: async () => ({ status: 'confirmed' }),
    ...overrides,
  };
}

test('checkpoint_precedes_actual_click', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  let sawCheckpoint = false;
  const options = deps({
    storage,
    save: async () => {
      const stored = storage.data[BATCH_JOURNAL_KEY];
      sawCheckpoint = stored.current && stored.current.phase === 'SAVE_PENDING'
        && stored.current.saveAttemptId === 'attempt-301-1';
      return { attempted: true, result: 'ack' };
    },
  });
  for (let step = 0; step < 6; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: options });
  }
  assert.equal(sawCheckpoint, true);
  const final = await loadBatch(storage);
  assert.equal(final.counters.saved, 1);
  assert.equal(final.queue[0].status, 'CONFIRMED');
});

test('one_ack_counts_once', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  const options = deps({ storage });
  for (let step = 0; step < 8; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: options });
  }
  const final = await loadBatch(storage);
  assert.equal(final.counters.saved, 1);
});

test('crash_after_click_without_ack_never_reclicks', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  let saves = 0;
  const options = deps({
    storage,
    save: async () => { saves += 1; return { attempted: true, result: 'unknown', code: 'NO_ACK' }; },
    verify: async () => ({ status: 'unknown' }),
  });
  for (let step = 0; step < 6; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: options });
  }
  const stored = await loadBatch(storage);
  assert.equal(saves, 1);
  assert.equal(stored.state, 'SUSPENDED');
  assert.equal(stored.queue[0].status, 'SAVE_UNCERTAIN');
  assert.equal(stored.counters.saved, 0);
  await runOneStep({ batchId: 'batch-runner', deps: options });
  assert.equal(saves, 1);
});

test('unknown_timeout_suspends', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  const options = deps({
    storage,
    save: async () => ({ attempted: true, result: 'unknown', code: 'TIMEOUT' }),
    verify: async () => ({ status: 'unknown' }),
  });
  for (let step = 0; step < 6; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: options });
  }
  const stored = await loadBatch(storage);
  assert.equal(stored.state, 'SUSPENDED');
});

test('portal_confirms_existing_save_on_reconcile', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  const uncertain = deps({
    storage,
    save: async () => ({ attempted: true, result: 'unknown', code: 'NO_ACK' }),
    verify: async () => ({ status: 'unknown' }),
  });
  for (let step = 0; step < 6; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: uncertain });
  }
  const confirmed = deps({ storage, verify: async () => ({ status: 'confirmed' }) });
  await runOneStep({ batchId: 'batch-runner', deps: confirmed });
  const stored = await loadBatch(storage);
  assert.equal(stored.counters.saved, 1);
  assert.equal(stored.queue[0].status, 'CONFIRMED');
});

test('no_auto_save_after_unknown', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  let saves = 0;
  const options = deps({
    storage,
    save: async () => { saves += 1; return { attempted: true, result: 'unknown' }; },
    verify: async () => ({ status: 'unknown' }),
  });
  for (let step = 0; step < 6; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: options });
  }
  for (let step = 0; step < 3; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: options });
  }
  assert.equal(saves, 1);
});

test('save_gate_closed_suspends_before_click', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  let saves = 0;
  const options = deps({
    storage,
    saveEnabled: false,
    save: async () => { saves += 1; return { attempted: true, result: 'ack' }; },
  });
  for (let step = 0; step < 6; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: options });
  }
  const stored = await loadBatch(storage);
  assert.equal(saves, 0);
  assert.equal(stored.state, 'SUSPENDED');
  assert.equal(stored.current.phase, 'VALIDATING');
});

test('multiple_interested_marks_review_without_save', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  let saves = 0;
  const options = deps({
    storage,
    selectInterested: async () => ({ ok: false, code: 'MULTIPLE_INTERESTED' }),
    save: async () => { saves += 1; return { attempted: true, result: 'ack' }; },
  });
  for (let step = 0; step < 6; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: options });
  }
  const stored = await loadBatch(storage);
  assert.equal(saves, 0);
  assert.equal(stored.queue[0].status, 'REVIEW_REQUIRED');
  assert.equal(stored.counters.saved, 0);
});

test('concurrent_wake_does_not_duplicate_step', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  const options = deps({ storage });
  const results = await Promise.all([
    runOneStep({ batchId: 'batch-runner', deps: options }),
    runOneStep({ batchId: 'batch-runner', deps: options }),
  ]);
  assert.equal(results.filter((result) => result.state === 'BUSY').length, 1);
  const stored = await loadBatch(storage);
  assert.equal(stored.counters.examined, 1);
  assert.equal(stored.current.phase, 'EXAMINING');
});
