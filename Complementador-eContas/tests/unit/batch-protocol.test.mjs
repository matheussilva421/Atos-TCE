import test from 'node:test';
import assert from 'node:assert/strict';
import { BatchController } from '../../src/batch/controller.mjs';
import { MESSAGE } from '../../src/shared/protocol.mjs';

const RUNTIME_ID = 'extension-runtime';
const LIST_TAB = { id: 7, url: 'https://processos.tce.rn.gov.br/#/dashboard/processos-no-setor/no-setor' };
const OTHER_TAB = { id: 8, url: 'https://processos.tce.rn.gov.br/#/dashboard/processos/501/autos' };

function memoryStorage(initial = {}) {
  const data = { ...initial };
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

function controller(options = {}) {
  const sent = [];
  const instance = new BatchController({
    storage: options.storage || memoryStorage(),
    runtimeId: RUNTIME_ID,
    newBatchId: () => 'batch-0001',
    sendToTab: async (tabId, message) => {
      sent.push({ tabId, message });
      return {
        ok: true,
        contextKey: 'ctx-live',
        hasPagination: true,
        entries: [
          { processId: '101', processLabel: '101/2020', status: 'pending' },
          { processId: '102', processLabel: '102/2020', status: 'completed' },
        ],
      };
    },
    now: () => 1000,
  });
  return { instance, sent };
}

const SENDER = { id: RUNTIME_ID, tab: LIST_TAB };

test('double_start_creates_one_batch', async () => {
  const { instance } = controller();
  const [first, second] = await Promise.all([
    instance.start({ sender: SENDER, limits: { maxExamined: 2, maxSaved: 1 } }),
    instance.start({ sender: SENDER, limits: { maxExamined: 2, maxSaved: 1 } }),
  ]);
  const accepted = [first, second].filter((result) => result.ok);
  assert.equal(accepted.length, 1);
  assert.equal([first, second].filter((result) => result.code === 'BATCH_ALREADY_ACTIVE').length, 1);
});

test('untrusted_sender_rejected', async () => {
  const { instance } = controller();
  const result = await instance.start({ sender: { id: 'evil', tab: LIST_TAB }, limits: { maxExamined: 1, maxSaved: 1 } });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'UNTRUSTED_SENDER');
});

test('wrong_list_tab_rejected', async () => {
  const { instance } = controller();
  const result = await instance.start({
    sender: { id: RUNTIME_ID, tab: OTHER_TAB },
    limits: { maxExamined: 1, maxSaved: 1 },
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'INVALID_LIST_TAB');
});

test('stale_batch_revision_rejected', async () => {
  const { instance } = controller();
  const started = await instance.start({ sender: SENDER, limits: { maxExamined: 2, maxSaved: 1 } });
  assert.equal(started.ok, true);
  const paused = await instance.pause({ sender: SENDER, batchId: started.batchId, revision: started.revision });
  assert.equal(paused.ok, true);
  const stale = await instance.pause({ sender: SENDER, batchId: started.batchId, revision: started.revision });
  assert.equal(stale.ok, false);
  assert.equal(stale.code, 'STALE_REVISION');
});

test('start_captures_only_pending_and_reports_counts', async () => {
  const { instance, sent } = controller();
  const started = await instance.start({ sender: SENDER, limits: { maxExamined: 2, maxSaved: 1 } });
  assert.equal(sent[0].message.type, MESSAGE.BATCH_LIST_SNAPSHOT);
  assert.equal(started.captured, 2);
  assert.equal(started.queueLength, 1);
  assert.equal(started.saved, 0);
  assert.equal(started.state, 'RUNNING');
});

test('empty_queue_does_not_create_batch', async () => {
  const instance = new BatchController({
    storage: memoryStorage(),
    runtimeId: RUNTIME_ID,
    newBatchId: () => 'batch-0002',
    sendToTab: async () => ({ ok: false, code: 'EMPTY_LIST', entries: [], contextKey: null }),
    now: () => 1000,
  });
  const result = await instance.start({ sender: SENDER, limits: { maxExamined: 1, maxSaved: 1 } });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'EMPTY_LIST');
  const status = await instance.status({ sender: SENDER });
  assert.equal(status.batch, null);
});

test('manual_fill_protocol_is_untouched', () => {
  assert.equal(MESSAGE.REQUEST_FILL, 'REQUEST_FILL');
  assert.equal(MESSAGE.BATCH_START, 'BATCH_START');
  assert.equal(MESSAGE.BATCH_PAUSE, 'BATCH_PAUSE');
  assert.equal(MESSAGE.BATCH_STOP, 'BATCH_STOP');
  assert.equal(MESSAGE.BATCH_RESUME, 'BATCH_RESUME');
  assert.equal(MESSAGE.BATCH_STATUS, 'BATCH_STATUS');
  assert.equal(MESSAGE.BATCH_PREVIEW, 'BATCH_PREVIEW');
  assert.equal(MESSAGE.BATCH_UI_UPDATE, 'BATCH_UI_UPDATE');
});

test('hung_journal_read_fails_closed_with_timeout', async () => {
  const instance = new BatchController({
    storage: { get: () => new Promise(() => {}) },
    runtimeId: RUNTIME_ID,
    newBatchId: () => 'batch-hung',
    sendToTab: async () => ({}),
    timeouts: { read: 30 },
  });
  const started = Date.now();
  const result = await instance.status({ sender: SENDER });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'STORAGE_TIMEOUT');
  assert.equal(Date.now() - started < 2000, true);
});

test('context_change_blocks_start_before_freezing_queue', async () => {
  const { instance } = controller();
  const result = await instance.start({
    sender: SENDER,
    limits: { maxExamined: 2, maxSaved: 1 },
    expectedContextKey: 'ctx-from-another-filter-state',
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'CONTEXT_CHANGED');
  const status = await instance.status({ sender: SENDER });
  assert.equal(status.batch, null);
});
