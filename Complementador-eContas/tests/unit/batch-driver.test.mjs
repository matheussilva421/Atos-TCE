import test from 'node:test';
import assert from 'node:assert/strict';
import { createBatchDriver } from '../../src/background/batch-runner.mjs';
import { createFrozenBatch } from '../../src/batch/queue.mjs';
import { reduceBatch } from '../../src/batch/state-machine.mjs';
import { loadBatch, saveBatch } from '../../src/batch/journal.mjs';
import { MESSAGE } from '../../src/shared/protocol.mjs';

const ORIGIN = 'https://processos.tce.rn.gov.br';

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
  };
}

async function runningBatch(storage) {
  const created = createFrozenBatch({
    batchId: 'batch-driver',
    listTabId: 7,
    contextKey: 'ctx-d',
    entries: [{ processId: '777', processLabel: '777/2020', status: 'pending' }],
    limits: { maxExamined: 1, maxSaved: 1 },
    startedAt: 10,
    saveAuthorized: true,
  });
  await saveBatch(storage, reduceBatch(created, { type: 'START', at: 11 }));
}

test('driver_is_disabled_by_default', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  const tabs = fakeTabs();
  let touched = 0;
  const driver = createBatchDriver({
    storage,
    tabs: { ...tabs, create: async () => { touched += 1; } },
    sendToTab: async () => { touched += 1; },
    runFillTransaction: async () => { touched += 1; },
  });
  const result = await driver.drive('batch-driver');
  assert.equal(result.state, 'DISABLED');
  assert.equal(touched, 0);
});

test('driver_runs_process_and_stops_at_save_gate', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  const tabs = fakeTabs();
  const messages = [];
  const fillCalls = [];
  const driver = createBatchDriver({
    storage,
    tabs,
    sendToTab: async (tabId, message) => {
      messages.push(message.type);
      if (message.type === MESSAGE.BATCH_SELECT_INTERESTED) {
        return { ok: true, interestedKey: 'key-1', interestedCount: 1 };
      }
      if (message.type === MESSAGE.BATCH_FORM_SNAPSHOT) {
        return { ok: true, snapshot: { processId: '777', interestedName: 'Pessoa', interestedKey: 'key-1' } };
      }
      if (message.type === MESSAGE.BATCH_VALIDATE_FORM) {
        return { ok: true };
      }
      return { ok: true };
    },
    runFillTransaction: async (payload) => {
      fillCalls.push(payload);
      return { ok: true, report: { filled: 5 } };
    },
    driveEnabled: true,
    saveEnabled: false,
  });
  const result = await driver.drive('batch-driver');
  assert.equal(result.state, 'COMPLETED');
  assert.equal(fillCalls.length, 1);
  assert.equal(fillCalls[0].applyMessageType, MESSAGE.BATCH_APPLY);
  assert.equal(fillCalls[0].sourceTabs.length, 1);
  assert.equal(fillCalls[0].sourceTabs[0].url.includes('/777/autos'), true);
  assert.equal(messages.includes(MESSAGE.BATCH_SELECT_INTERESTED), true);
  assert.equal(messages.includes(MESSAGE.BATCH_FORM_SNAPSHOT), true);
  const stored = await loadBatch(storage);
  assert.equal(stored.counters.examined, 1);
  assert.equal(stored.counters.saved, 0);
  assert.equal(stored.current, null);
  assert.equal(stored.queue[0].status, 'FILLED');
});

test('driver_resumes_after_step_limit_and_reuses_tabs', async () => {
  const storage = memoryStorage();
  await runningBatch(storage);
  const tabs = fakeTabs();
  let creates = 0;
  const wrappedTabs = {
    ...tabs,
    async create(properties) {
      creates += 1;
      return tabs.create(properties);
    },
  };
  const driver = createBatchDriver({
    storage,
    tabs: wrappedTabs,
    sendToTab: async (tabId, message) => {
      if (message.type === MESSAGE.BATCH_SELECT_INTERESTED) {
        return { ok: true, interestedKey: 'key-1', interestedCount: 1 };
      }
      if (message.type === MESSAGE.BATCH_FORM_SNAPSHOT) {
        return { ok: true, snapshot: { processId: '777', interestedName: 'Pessoa', interestedKey: 'key-1' } };
      }
      return { ok: true };
    },
    runFillTransaction: async () => ({ ok: true, report: { filled: 5 } }),
    driveEnabled: true,
    saveEnabled: false,
    maxSteps: 2,
  });
  let result = null;
  for (let attempt = 0; attempt < 8; attempt += 1) {
    result = await driver.drive('batch-driver');
    if (result.state !== 'STEP_LIMIT') {
      break;
    }
  }
  assert.equal(result.state, 'COMPLETED');
  assert.equal(creates, 2);
});
