import test from 'node:test';
import assert from 'node:assert/strict';
import { createFrozenBatch } from '../../src/batch/queue.mjs';
import {
  BATCH_JOURNAL_KEY,
  compactJournal,
  loadBatch,
  saveBatch,
} from '../../src/batch/journal.mjs';

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    async get(keys) {
      if (typeof keys === 'string') {
        return keys in data ? { [keys]: data[keys] } : {};
      }
      return { ...data };
    },
    async set(values) {
      Object.assign(data, values);
    },
    async remove(keys) {
      for (const key of Array.isArray(keys) ? keys : [keys]) {
        delete data[key];
      }
    },
  };
}

function batch(overrides = {}) {
  const base = createFrozenBatch({
    batchId: 'batch-journal',
    listTabId: 3,
    contextKey: 'ctx-j',
    entries: [{ processId: '301', processLabel: '301/2022', status: 'pending' }],
    limits: { maxExamined: 1, maxSaved: 1 },
    startedAt: 10,
  });
  return { ...base, ...overrides };
}

test('journal_survives_service_worker_restart', async () => {
  const storage = memoryStorage();
  const original = batch();
  await saveBatch(storage, original);
  const restarted = memoryStorage(storage.data);
  const loaded = await loadBatch(restarted);
  assert.deepEqual(loaded, original);
});

test('journal_drops_pdf_and_personal_values', async () => {
  const storage = memoryStorage();
  const dirty = batch({
    interestedName: 'FULANO DE TAL',
    cpf: '123.456.789-00',
    pdfText: 'conteudo integral do documento',
    signedUrl: 'https://example.invalid/assinado?token=abc',
    queue: [{
      processId: '301',
      processLabel: '301/2022',
      status: 'QUEUED',
      interestedName: 'FULANO DE TAL',
      birthDate: '01/01/1970',
    }],
    fields: { matricula: '99999-9' },
  });
  await saveBatch(storage, dirty);
  const serialized = JSON.stringify(storage.data);
  assert.equal(serialized.includes('FULANO'), false);
  assert.equal(serialized.includes('12345678900'), false);
  assert.equal(serialized.includes('123.456.789-00'), false);
  assert.equal(serialized.includes('conteudo integral'), false);
  assert.equal(serialized.includes('token=abc'), false);
  assert.equal(serialized.includes('99999-9'), false);
  const stored = storage.data[BATCH_JOURNAL_KEY];
  assert.deepEqual(Object.keys(stored).sort(), [
    'batchId', 'capture', 'contextKey', 'counters', 'current', 'cursor', 'events',
    'limits', 'listTabId', 'queue', 'revision', 'saveAuthorized', 'schemaVersion', 'state', 'updatedAt',
  ]);
});

test('corrupted_checkpoint_suspends', async () => {
  for (const corrupt of ['not-an-object', 42, { schemaVersion: 1, batchId: '' }]) {
    const storage = memoryStorage({ [BATCH_JOURNAL_KEY]: corrupt });
    await assert.rejects(() => loadBatch(storage), (error) => error.code === 'CORRUPTED');
  }
});

test('retention_preserves_uncertain_and_interrupted', async () => {
  const old = Date.now() - 10 * 24 * 60 * 60 * 1000;
  for (const state of ['SUSPENDED', 'PAUSED', 'RUNNING', 'PAUSE_REQUESTED']) {
    const storage = memoryStorage();
    await saveBatch(storage, batch({ state, updatedAt: old }));
    const result = await compactJournal(storage, Date.now(), { maxCompletedAgeMs: 60 * 1000 });
    assert.deepEqual(result, { deleted: 0 }, state);
    assert.equal(BATCH_JOURNAL_KEY in storage.data, true, state);
  }
  const saved = memoryStorage();
  await saveBatch(saved, batch({ state: 'COMPLETED', updatedAt: old }));
  const result = await compactJournal(saved, Date.now(), { maxCompletedAgeMs: 60 * 1000 });
  assert.deepEqual(result, { deleted: 1 });
  assert.equal(BATCH_JOURNAL_KEY in saved.data, false);
});

test('quota_failure_fails_closed', async () => {
  const storage = memoryStorage();
  storage.set = async () => {
    throw new Error('QUOTA_BYTES quota exceeded');
  };
  await assert.rejects(() => saveBatch(storage, batch()), (error) => error.code === 'STORAGE_FAILURE');
});

test('schema_version_mismatch_suspends', async () => {
  const storage = memoryStorage({ [BATCH_JOURNAL_KEY]: { ...batch(), schemaVersion: 2 } });
  await assert.rejects(() => loadBatch(storage), (error) => error.code === 'SCHEMA_MISMATCH');
});
