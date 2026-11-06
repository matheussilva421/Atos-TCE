import test from 'node:test';
import assert from 'node:assert/strict';
import { createFrozenBatch } from '../../src/batch/queue.mjs';
import { reduceBatch } from '../../src/batch/state-machine.mjs';
import { loadBatch, saveBatch, BATCH_JOURNAL_KEY } from '../../src/batch/journal.mjs';
import { runOneStep } from '../../src/batch/runner.mjs';

function memoryStorage() {
  const data = {};
  return {
    data,
    async get(key) {
      return key in data ? { [key]: data[key] } : {};
    },
    async set(values) {
      for (const [key, value] of Object.entries(values)) {
        data[key] = value;
      }
    },
    async remove(key) {
      delete data[key];
    },
  };
}

function deps(storage, overrides = {}) {
  const calls = [];
  const session = { processId: null, workspace: null };
  return {
    calls,
    session,
    storage,
    now: () => 1000,
    newAttemptId: () => 'attempt-301-1',
    cleanupWorkspace: async ({ processId, status }) => {
      calls.push('cleanup:' + status + ':' + processId);
      return { closed: 2 };
    },
    keepWorkspace: ({ processId, status }) => {
      calls.push('keep:' + status + ':' + processId);
    },
    openWorkspace: async ({ processId }) => {
      calls.push('open');
      session.processId = processId;
      session.workspace = { autosTabId: 41, formTabId: 42 };
      return session.workspace;
    },
    selectInterested: async () => { calls.push('select'); return { ok: true, interestedKey: 'key-1' }; },
    fill: async () => { calls.push('fill'); return { ok: true }; },
    validate: async () => { calls.push('validate'); return { ok: true }; },
    saveEnabled: false,
    save: async () => { calls.push('save'); return { attempted: false, result: 'error', code: 'SAVE_GATE_CLOSED' }; },
    verify: async () => ({ status: 'unknown' }),
    ...overrides,
  };
}

function startedBatch() {
  const created = createFrozenBatch({
    batchId: 'batch-stop',
    listTabId: 7,
    contextKey: 'ctx-stop',
    entries: [
      { processId: '301', processLabel: '301/2020', status: 'pending' },
      { processId: '302', processLabel: '302/2020', status: 'pending' },
    ],
    limits: { maxExamined: 5, maxSaved: 1 },
    startedAt: 10,
    saveAuthorized: false,
  });
  return reduceBatch(created, { type: 'START', at: 11 });
}

test('stop_requested_releases_the_in_flight_process_and_reaches_stopped', async () => {
  const storage = memoryStorage();
  let batch = reduceBatch(startedBatch(), { type: 'BEGIN_PROCESS', processId: '301', at: 12 });
  batch = reduceBatch(batch, { type: 'REQUEST_STOP', at: 13 });
  assert.equal(batch.state, 'STOP_REQUESTED');
  await saveBatch(storage, batch);

  const options = deps(storage);
  options.session.processId = '301';
  options.session.workspace = { autosTabId: 41, formTabId: 42 };
  const result = await runOneStep({ batchId: 'batch-stop', deps: options });

  assert.equal(result.state, 'STOPPED');
  assert.equal(result.needsWake, false);
  const final = await loadBatch(storage);
  assert.equal(final.state, 'STOPPED');
  assert.equal(final.current, null);
  assert.equal(final.queue[0].status, 'REVIEW_REQUIRED');
  assert.equal(final.queue[1].status, 'QUEUED');
  assert.deepEqual(options.calls, ['keep:REVIEW_REQUIRED:301']);
});

test('stop_never_opens_or_writes_after_the_request', async () => {
  const storage = memoryStorage();
  let batch = reduceBatch(startedBatch(), { type: 'BEGIN_PROCESS', processId: '301', at: 12 });
  batch = reduceBatch(batch, { type: 'REQUEST_STOP', at: 13 });
  await saveBatch(storage, batch);

  const options = deps(storage);
  await runOneStep({ batchId: 'batch-stop', deps: options });
  await runOneStep({ batchId: 'batch-stop', deps: options });

  assert.equal(options.calls.includes('open'), false);
  assert.equal(options.calls.includes('fill'), false);
  assert.equal(options.calls.includes('save'), false);
  const final = await loadBatch(storage);
  assert.equal(final.state, 'STOPPED');
  assert.equal(final.counters.examined, 1);
});

test('stop_closes_review_tabs_when_keep_problem_tabs_is_off', async () => {
  const storage = memoryStorage();
  const created = createFrozenBatch({
    batchId: 'batch-stop',
    listTabId: 7,
    contextKey: 'ctx-stop',
    entries: [{ processId: '301', processLabel: '301/2020', status: 'pending' }],
    limits: { maxExamined: 5, maxSaved: 1 },
    startedAt: 10,
    saveAuthorized: false,
    keepProblemTabs: false,
  });
  let batch = reduceBatch(created, { type: 'START', at: 11 });
  batch = reduceBatch(batch, { type: 'BEGIN_PROCESS', processId: '301', at: 12 });
  batch = reduceBatch(batch, { type: 'REQUEST_STOP', at: 13 });
  await saveBatch(storage, batch);

  const options = deps(storage);
  options.session.processId = '301';
  options.session.workspace = { autosTabId: 41, formTabId: 42 };
  await runOneStep({ batchId: 'batch-stop', deps: options });

  const final = await loadBatch(storage);
  assert.equal(final.state, 'STOPPED');
  assert.equal(final.keepProblemTabs, false);
  assert.equal(options.calls.includes('cleanup:REVIEW_REQUIRED:301'), true);
});

test('pause_requested_finishes_the_current_process_before_pausing', async () => {
  const storage = memoryStorage();
  let batch = reduceBatch(startedBatch(), { type: 'BEGIN_PROCESS', processId: '301', at: 12 });
  batch = reduceBatch(batch, { type: 'REQUEST_PAUSE', at: 13 });
  assert.equal(batch.state, 'PAUSE_REQUESTED');
  await saveBatch(storage, batch);

  const options = deps(storage);
  for (let step = 0; step < 6; step += 1) {
    await runOneStep({ batchId: 'batch-stop', deps: options });
  }

  const final = await loadBatch(storage);
  assert.equal(final.state, 'PAUSED');
  assert.equal(final.current, null);
  assert.equal(final.queue[0].status, 'FILLED');
  assert.equal(options.calls.includes('open'), true);
});

test('stop_state_is_not_written_twice', async () => {
  const storage = memoryStorage();
  let batch = reduceBatch(startedBatch(), { type: 'BEGIN_PROCESS', processId: '301', at: 12 });
  batch = reduceBatch(batch, { type: 'REQUEST_STOP', at: 13 });
  await saveBatch(storage, batch);
  const options = deps(storage);
  await runOneStep({ batchId: 'batch-stop', deps: options });
  const afterFirst = storage.data[BATCH_JOURNAL_KEY].revision;
  await runOneStep({ batchId: 'batch-stop', deps: options });
  assert.equal(storage.data[BATCH_JOURNAL_KEY].revision, afterFirst);
});
