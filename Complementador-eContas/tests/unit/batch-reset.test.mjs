import test from 'node:test';
import assert from 'node:assert/strict';
import { BatchController } from '../../src/batch/controller.mjs';
import { createFrozenBatch } from '../../src/batch/queue.mjs';
import { loadBatch } from '../../src/batch/journal.mjs';

const RUNTIME_ID = 'ext-runtime';
const LIST_TAB = { id: 7, windowId: 1, url: 'https://processos.tce.rn.gov.br/#/dashboard/processos-no-setor/no-setor' };

function memoryStorage() {
  const data = {};
  return {
    data,
    async get(key) { return key in data ? { [key]: data[key] } : {}; },
    async set(values) { Object.assign(data, values); },
    async remove(key) { delete data[key]; },
  };
}

async function seed(storage, state = 'STOPPED', current = null) {
  const batch = createFrozenBatch({
    batchId: 'batch-reset',
    listTabId: 7,
    contextKey: 'ctx',
    entries: [{ processId: '301', processLabel: '301/2020', status: 'pending' }],
    limits: { maxExamined: 1, maxSaved: 1 },
    startedAt: 10,
    windowId: 1,
  });
  batch.state = state;
  batch.current = current;
  await storage.set({ complementadorBatchJournal: batch });
}

function makeController(storage) {
  return new BatchController({
    storage,
    runtimeId: RUNTIME_ID,
    newBatchId: () => 'batch-next',
    sendToTab: async () => ({ ok: true, contextKey: 'ctx', entries: [] }),
    now: () => 1000,
  });
}

const SENDER = { id: RUNTIME_ID, tab: LIST_TAB };

test('reset_clears_stopped_batch_and_allows_new_start', async () => {
  const storage = memoryStorage();
  await seed(storage, 'STOPPED');
  const controller = makeController(storage);
  const result = await controller.reset({ sender: SENDER });
  assert.equal(result.ok, true);
  assert.equal(await loadBatch(storage), null);
});

test('reset_refuses_active_save_attempt', async () => {
  const storage = memoryStorage();
  await seed(storage, 'SUSPENDED', { processId: '301', phase: 'SAVE_PENDING', saveAttemptId: 'attempt-301' });
  const controller = makeController(storage);
  const result = await controller.reset({ sender: SENDER });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'SAVE_UNCERTAIN_LOCKED');
  assert.equal((await loadBatch(storage)).current.saveAttemptId, 'attempt-301');
});

test('reset_clears_suspended_without_save_attempt', async () => {
  const storage = memoryStorage();
  await seed(storage, 'SUSPENDED', { processId: '301', phase: 'READING', saveAttemptId: null });
  const controller = makeController(storage);
  const result = await controller.reset({ sender: SENDER });
  assert.equal(result.ok, true);
  assert.equal(await loadBatch(storage), null);
});
