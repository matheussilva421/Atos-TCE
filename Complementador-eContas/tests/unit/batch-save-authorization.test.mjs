import test from 'node:test';
import assert from 'node:assert/strict';
import { createBatchDriver } from '../../src/background/batch-runner.mjs';
import { BatchController } from '../../src/batch/controller.mjs';
import { createFrozenBatch } from '../../src/batch/queue.mjs';
import { reduceBatch } from '../../src/batch/state-machine.mjs';
import { loadBatch, saveBatch } from '../../src/batch/journal.mjs';
import { MESSAGE } from '../../src/shared/protocol.mjs';

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

function fakeTabs() {
  const tabs = {};
  let nextId = 500;
  return {
    tabs,
    async query() {
      return Object.values(tabs);
    },
    async create({ url }) {
      const id = nextId;
      nextId += 1;
      tabs[id] = { id, url };
      return tabs[id];
    },
    async update(id, { url }) {
      tabs[id] = { ...(tabs[id] || { id }), url };
      return tabs[id];
    },
    async get(id) {
      if (!tabs[id]) throw new Error('missing tab');
      return tabs[id];
    },
    async remove(id) {
      delete tabs[id];
    },
  };
}

async function seedBatch(storage, saveAuthorized) {
  const created = createFrozenBatch({
    batchId: 'batch-auth',
    listTabId: 7,
    contextKey: 'ctx-auth',
    entries: [{ processId: '888', processLabel: '888/2020', status: 'pending' }],
    limits: { maxExamined: 1, maxSaved: 1 },
    startedAt: 10,
    saveAuthorized,
  });
  await saveBatch(storage, reduceBatch(created, { type: 'START', at: 11 }));
}

function driverFor(storage, overrides = {}) {
  const messages = [];
  const driver = createBatchDriver({
    storage,
    tabs: fakeTabs(),
    sendToTab: async (tabId, message) => {
      messages.push(message);
      if (message.type === MESSAGE.BATCH_SELECT_INTERESTED) {
        return { ok: true, interestedKey: 'key-1', interestedCount: 1 };
      }
      if (message.type === MESSAGE.BATCH_FORM_SNAPSHOT) {
        return {
          ok: true,
          snapshot: { processId: '888', interestedName: 'Pessoa', interestedKey: 'key-1' },
        };
      }
      if (message.type === MESSAGE.BATCH_VALIDATE_FORM) {
        return { ok: true };
      }
      if (message.type === MESSAGE.BATCH_SAVE) {
        return { ok: true, attempted: true, result: 'ack' };
      }
      return { ok: true };
    },
    runFillTransaction: async () => ({ ok: true, report: { filled: 5 } }),
    driveEnabled: true,
    ...overrides,
  });
  return { driver, messages };
}

test('real_driver_save_disabled_by_default', async () => {
  const storage = memoryStorage();
  await seedBatch(storage, true);
  const { driver, messages } = driverFor(storage);
  const result = await driver.drive('batch-auth');
  assert.equal(result.state, 'COMPLETED');
  assert.equal(messages.some((message) => message.type === MESSAGE.BATCH_SAVE), false);
  const stored = await loadBatch(storage);
  assert.equal(stored.queue[0].status, 'FILLED');
  assert.equal(stored.counters.saved, 0);
  assert.equal(stored.saveAuthorized, true);
});

test('batch_without_save_authorization_never_saves', async () => {
  const storage = memoryStorage();
  await seedBatch(storage, false);
  const { driver, messages } = driverFor(storage, { saveEnabled: true });
  const result = await driver.drive('batch-auth');
  assert.equal(result.state, 'COMPLETED');
  assert.equal(messages.some((message) => message.type === MESSAGE.BATCH_SAVE), false);
  const stored = await loadBatch(storage);
  assert.equal(stored.queue[0].status, 'FILLED');
  assert.equal(stored.counters.saved, 0);
  assert.equal(stored.saveAuthorized, false);
});

test('authorized_batch_with_explicit_save_capability_saves_once', async () => {
  const storage = memoryStorage();
  await seedBatch(storage, true);
  const { driver, messages } = driverFor(storage, {
    saveEnabled: true,
    verify: async () => ({ status: 'confirmed' }),
  });
  const result = await driver.drive('batch-auth');
  assert.equal(result.state, 'COMPLETED');
  assert.equal(messages.filter((message) => message.type === MESSAGE.BATCH_SAVE).length, 1);
  const stored = await loadBatch(storage);
  assert.equal(stored.queue[0].status, 'CONFIRMED');
  assert.equal(stored.counters.saved, 1);
});

test('controller_persists_save_authorization_in_the_batch', async () => {
  for (const saveEnabled of [false, true]) {
    const storage = memoryStorage();
    const controller = new BatchController({
      storage,
      runtimeId: RUNTIME_ID,
      newBatchId: () => 'batch-auth-' + String(saveEnabled),
      sendToTab: async () => ({
        ok: true,
        contextKey: 'ctx-live',
        entries: [{ processId: '888', processLabel: '888/2020', status: 'pending' }],
      }),
      now: () => 1000,
      saveEnabled,
    });
    const started = await controller.start({
      sender: { id: RUNTIME_ID, tab: LIST_TAB },
      limits: { maxExamined: 1, maxSaved: 1 },
    });
    assert.equal(started.ok, true);
    const stored = await loadBatch(storage);
    assert.equal(stored.saveAuthorized, saveEnabled);
  }
});
