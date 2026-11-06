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
    saveAuthorized: true,
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
  assert.equal(stored.state, 'COMPLETED');
  assert.equal(stored.queue[0].status, 'FILLED');
  assert.equal(stored.counters.saved, 0);
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

test('save_not_dispatched_does_not_leave_attempt_armed', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  const options = deps({
    storage,
    save: async () => ({ attempted: false, result: 'error', code: 'SAVE_BUTTON_NOT_FOUND' }),
  });
  for (let step = 0; step < 8; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: options });
  }
  const stored = await loadBatch(storage);
  assert.equal(stored.queue[0].status, 'FAILED');
  assert.equal(stored.current, null);
  assert.equal(stored.counters.saved, 0);
});


test('exception_after_save_dispatch_keeps_uncertainty', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  let saves = 0;
  const options = deps({
    storage,
    save: async () => { saves += 1; throw new Error('boom'); },
    verify: async () => ({ status: 'unknown' }),
  });
  let rejected = null;
  for (let step = 0; step < 8; step += 1) {
    try {
      await runOneStep({ batchId: 'batch-runner', deps: options });
    } catch (error) {
      rejected = error;
      break;
    }
  }
  assert.equal(rejected, null);
  const stored = await loadBatch(storage);
  assert.equal(saves, 1);
  assert.equal(stored.state, 'SUSPENDED');
  assert.equal(stored.queue[0].status, 'SAVE_UNCERTAIN');
  assert.equal(stored.current && stored.current.saveAttemptId, 'attempt-301-1');
  assert.equal(stored.counters.saved, 0);
});

test('ack_without_readback_not_confirmed', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  const options = deps({
    storage,
    save: async () => ({ attempted: true, result: 'ack' }),
    verify: async () => ({ status: 'unknown' }),
  });
  for (let step = 0; step < 6; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: options });
  }
  const stored = await loadBatch(storage);
  assert.equal(stored.state, 'SUSPENDED');
  assert.equal(stored.queue[0].status, 'SAVE_UNCERTAIN');
  assert.equal(stored.counters.saved, 0);
});

async function seedSavePending(storage) {
  const stored = await loadBatch(storage);
  stored.state = 'RUNNING';
  stored.current = { processId: '301', phase: 'SAVE_PENDING', saveAttemptId: 'attempt-301-1' };
  stored.queue[0].status = 'SAVE_PENDING';
  await saveBatch(storage, stored);
}

test('pending_save_after_worker_wake_never_reclicks', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  await seedSavePending(storage);
  let saves = 0;
  const options = deps({
    storage,
    save: async () => { saves += 1; return { attempted: true, result: 'ack' }; },
    verify: async () => ({ status: 'unknown' }),
  });
  const result = await runOneStep({ batchId: 'batch-runner', deps: options });
  assert.equal(saves, 0);
  assert.equal(result.state, 'SUSPENDED');
  const stored = await loadBatch(storage);
  assert.equal(stored.state, 'SUSPENDED');
  assert.equal(stored.queue[0].status, 'SAVE_UNCERTAIN');
});

test('pending_save_confirmed_on_wake_without_reclick', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  await seedSavePending(storage);
  let saves = 0;
  const options = deps({
    storage,
    save: async () => { saves += 1; return { attempted: true, result: 'ack' }; },
    verify: async () => ({ status: 'confirmed' }),
  });
  await runOneStep({ batchId: 'batch-runner', deps: options });
  assert.equal(saves, 0);
  const stored = await loadBatch(storage);
  assert.equal(stored.queue[0].status, 'CONFIRMED');
  assert.equal(stored.counters.saved, 1);
  assert.equal(stored.current, null);
});

test('suspended_reconciled_requires_manual_resume', async () => {
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
  const afterAck = await runOneStep({ batchId: 'batch-runner', deps: confirmed });
  assert.equal(afterAck.state, 'SUSPENDED');
  let stored = await loadBatch(storage);
  assert.equal(stored.state, 'SUSPENDED');
  assert.equal(stored.queue[0].status, 'CONFIRMED');
  assert.equal(stored.counters.saved, 1);
  stored = reduceBatch(stored, { type: 'RESUME_AUTHORIZED', at: 2000 });
  await saveBatch(storage, stored);
  for (let step = 0; step < 2; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: confirmed });
  }
  const final = await loadBatch(storage);
  assert.equal(final.state, 'COMPLETED');
});

test('pause_requested_ack_becomes_paused', () => {
  const storage = memoryStorage();
  return (async () => {
    await runningBatch(storage);
    const stored = await loadBatch(storage);
    stored.state = 'PAUSE_REQUESTED';
    stored.current = { processId: '301', phase: 'SAVE_PENDING', saveAttemptId: 'attempt-301-1' };
    stored.queue[0].status = 'SAVE_PENDING';
    const next = reduceBatch(stored, { type: 'SAVE_ACK', at: 2000 });
    assert.equal(next.state, 'PAUSED');
    assert.equal(next.queue[0].status, 'CONFIRMED');
    assert.equal(next.counters.saved, 1);
  })();
});

test('missing_fields_records_sanitized_cause_and_fields', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  const options = deps({
    storage,
    fill: async () => ({
      ok: true,
      diagnostics: {
        resolutionFound: true,
        guiaFound: false,
        proposalStatus: {
          modalidade: 'exact',
          dataDoeEstado: 'exact',
          cargo: 'exact',
          matricula: 'exact',
          dataNascimento: 'absent',
        },
        skipped: [],
        errors: [],
      },
    }),
    validate: async () => ({ ok: false, code: 'MISSING_FIELDS', fields: ['dataNascimento'] }),
  });
  for (let step = 0; step < 7; step += 1) {
    await runOneStep({ batchId: 'batch-runner', deps: options });
  }
  const stored = await loadBatch(storage);
  assert.equal(stored.queue[0].status, 'REVIEW_REQUIRED');
  assert.equal(stored.diagnostics['301'].cause, 'GUIA_NOT_MATCHED');
  assert.deepEqual(stored.diagnostics['301'].fields, ['dataNascimento']);
  assert.equal(JSON.stringify(stored.diagnostics).includes('Pessoa'), false);
});
