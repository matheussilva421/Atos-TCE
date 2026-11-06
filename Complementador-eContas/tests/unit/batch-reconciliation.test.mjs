import test from 'node:test';
import assert from 'node:assert/strict';
import { createFrozenBatch } from '../../src/batch/queue.mjs';
import { BatchController } from '../../src/batch/controller.mjs';
import { reconcileExternalCompletions } from '../../src/batch/reconciliation.mjs';
import { buildBatchReport } from '../../src/batch/report.mjs';
import { loadBatch } from '../../src/batch/journal.mjs';

const RUNTIME_ID = 'ext-runtime';
const LIST_TAB = { id: 7, url: 'https://processos.tce.rn.gov.br/#/dashboard/processos-no-setor/no-setor' };

function memoryStorage() {
  const data = {};
  return {
    data,
    async get(key) {
      return key in data ? { [key]: data[key] } : {};
    },
    async set(values) {
      Object.assign(data, values);
    },
    async remove(key) {
      delete data[key];
    },
  };
}

function baseBatch() {
  const batch = createFrozenBatch({
    batchId: 'batch-reconcile',
    listTabId: 7,
    contextKey: 'ctx-r',
    entries: [
      { processId: '301', processLabel: '301/2020', status: 'pending' },
      { processId: '302', processLabel: '302/2020', status: 'pending' },
      { processId: '303', processLabel: '303/2020', status: 'pending' },
    ],
    limits: { maxExamined: 3, maxSaved: 1 },
    startedAt: 10,
    saveAuthorized: true,
  });
  batch.state = 'RUNNING';
  batch.queue[0].status = 'FILLED';
  batch.queue[1].status = 'CONFIRMED';
  batch.queue[2].status = 'SAVE_UNCERTAIN';
  batch.counters = { examined: 3, saved: 1 };
  return batch;
}

test('external_completion_marks_filled_without_counting_engine_save', () => {
  const batch = baseBatch();
  const result = reconcileExternalCompletions(batch, ['301'], { at: 2000 });
  assert.equal(result.changed, 1);
  assert.equal(result.batch.queue[0].status, 'COMPLETED_EXTERNALLY');
  assert.equal(result.batch.queue[1].status, 'CONFIRMED');
  assert.equal(result.batch.queue[2].status, 'SAVE_UNCERTAIN');
  assert.deepEqual(result.batch.counters, { examined: 3, saved: 1 });
  assert.equal(result.batch.events.some((event) => event.code === 'EXTERNAL_COMPLETION_RECONCILED'), true);
});

test('external_completion_is_idempotent', () => {
  const first = reconcileExternalCompletions(baseBatch(), ['301'], { at: 2000 });
  const second = reconcileExternalCompletions(first.batch, ['301'], { at: 3000 });
  assert.equal(second.changed, 0);
  assert.equal(second.batch, first.batch);
});

test('external_completion_ignores_unknown_confirmed_and_invalid_ids', () => {
  const batch = baseBatch();
  const result = reconcileExternalCompletions(batch, ['302', '303', '999', 'not-a-process'], { at: 2000 });
  assert.equal(result.changed, 0);
  assert.equal(result.batch.queue[0].status, 'FILLED');
  assert.equal(result.batch.queue[1].status, 'CONFIRMED');
  assert.equal(result.batch.counters.saved, 1);
});

test('report_shows_external_completion_without_changing_saved', () => {
  const result = reconcileExternalCompletions(baseBatch(), ['301'], { at: 2000 });
  const report = buildBatchReport(result.batch);
  assert.equal(report.totals.completedExternally, 1);
  assert.equal(report.totals.filled, 0);
  assert.equal(report.totals.saved, 1);
  const item = report.items.find((entry) => entry.processId === '301');
  assert.equal(item.status, 'COMPLETED_EXTERNALLY');
  assert.equal(item.reasonCode, 'COMPLETED_EXTERNALLY');
});

test('controller_reconciles_external_completion_from_list_tab', async () => {
  const storage = memoryStorage();
  const controller = new BatchController({
    storage,
    runtimeId: RUNTIME_ID,
    newBatchId: () => 'batch-reconcile',
    sendToTab: async () => ({
      ok: true,
      contextKey: 'ctx-live',
      entries: [
        { processId: '301', processLabel: '301/2020', status: 'pending' },
        { processId: '302', processLabel: '302/2020', status: 'pending' },
      ],
    }),
    now: () => 1000,
    saveEnabled: true,
  });
  const started = await controller.start({
    sender: { id: RUNTIME_ID, tab: LIST_TAB },
    limits: { maxExamined: 2, maxSaved: 1 },
  });
  assert.equal(started.ok, true);
  const stored = await loadBatch(storage);
  stored.queue[0].status = 'FILLED';
  await storage.set({ complementadorBatchJournal: stored });
  const result = await controller.reconcileExternal({
    sender: { id: RUNTIME_ID, tab: LIST_TAB },
    batchId: started.batchId,
    revision: stored.revision,
    processIds: ['301'],
  });
  assert.equal(result.ok, true);
  assert.equal(result.changed, 1);
  const final = await loadBatch(storage);
  assert.equal(final.queue[0].status, 'COMPLETED_EXTERNALLY');
  assert.equal(final.counters.saved, 0);
});
