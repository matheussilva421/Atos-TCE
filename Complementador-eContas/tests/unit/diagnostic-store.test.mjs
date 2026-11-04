import test from 'node:test';
import assert from 'node:assert/strict';
import {
  DIAGNOSTIC_KEY,
  DIAGNOSTIC_STATES,
  createDiagnosticRecorder,
  formatDiagnosticSummary,
  isFinalDiagnosticState,
} from '../../src/shared/diagnostic-store.mjs';

class MemoryStorage {
  constructor() {
    this.map = new Map();
  }

  async get(key) {
    const keys = Array.isArray(key) ? key : [key];
    const result = {};
    for (const item of keys) {
      if (this.map.has(item)) result[item] = structuredClone(this.map.get(item));
    }
    return result;
  }

  async set(values) {
    for (const [key, value] of Object.entries(values)) {
      this.map.set(key, structuredClone(value));
    }
  }

  async remove(key) {
    const keys = Array.isArray(key) ? key : [key];
    for (const item of keys) this.map.delete(item);
  }
}

test('records_stages_and_final_metrics', async () => {
  const storage = new MemoryStorage();
  const recorder = createDiagnosticRecorder(storage);
  await recorder.reset();
  await recorder.record(DIAGNOSTIC_STATES.L1_STARTED);
  await recorder.record(DIAGNOSTIC_STATES.SOURCE_TAB_RESOLVED);
  await recorder.record(DIAGNOSTIC_STATES.L1_SUCCESS, {
    pagesCount: 2,
    totalChars: 100,
    minPageChars: 40,
    maxPageChars: 60,
    byteLength: 877,
    sourceKind: 'pdf-bytes',
    elapsedMs: 123,
  });
  const stored = await recorder.read();
  assert.equal(stored.state, 'L1_SUCCESS');
  assert.equal(stored.pagesCount, 2);
  assert.equal(stored.totalChars, 100);
  assert.equal(stored.byteLength, 877);
  assert.equal(stored.elapsedMs, 123);
  assert.equal(stored.steps.length, 3);
  assert.deepEqual(stored.steps.map((step) => step.state), [
    'L1_STARTED',
    'SOURCE_TAB_RESOLVED',
    'L1_SUCCESS',
  ]);
});

test('discards_unapproved_identifying_details', async () => {
  const storage = new MemoryStorage();
  const recorder = createDiagnosticRecorder(storage);
  await recorder.reset();
  await recorder.record(DIAGNOSTIC_STATES.L1_SUCCESS, {
    pagesCount: 1,
    totalChars: 5,
    name: 'SENTINEL_NAME',
    cpf: '000.000.000-00',
    text: 'SENTINEL_TEXT',
    url: 'https://example.invalid/private',
    processId: '621600',
    documentKey: 'secret-hash',
  });
  const serialized = JSON.stringify(await recorder.read());
  assert.equal(serialized.includes('SENTINEL_NAME'), false);
  assert.equal(serialized.includes('SENTINEL_TEXT'), false);
  assert.equal(serialized.includes('000.000.000-00'), false);
  assert.equal(serialized.includes('621600'), false);
  assert.equal(serialized.includes('secret-hash'), false);
  assert.equal(serialized.includes('example.invalid'), false);
});

test('format_summary_is_technical_only', () => {
  const summary = formatDiagnosticSummary({
    state: 'L1_SUCCESS',
    pagesCount: 2,
    totalChars: 100,
    elapsedMs: 50,
  });
  assert.match(summary, /L1_SUCCESS/);
  assert.match(summary, /2 página/);
  assert.match(summary, /100 caractere/);
  assert.match(summary, /50 ms/);
  assert.equal(summary.includes('SENTINEL'), false);
  assert.match(formatDiagnosticSummary({ state: 'L1_ERROR', errorCode: 'PDF_FETCH_FAILED' }), /PDF_FETCH_FAILED/);
});

test('reset_clears_previous_result', async () => {
  const storage = new MemoryStorage();
  const recorder = createDiagnosticRecorder(storage);
  await recorder.record(DIAGNOSTIC_STATES.L1_SUCCESS, { pagesCount: 1 });
  await recorder.reset();
  assert.equal(await recorder.read(), null);
  assert.equal((await storage.get(DIAGNOSTIC_KEY))[DIAGNOSTIC_KEY], undefined);
});

test('final_state_detection', () => {
  assert.equal(isFinalDiagnosticState(DIAGNOSTIC_STATES.L1_SUCCESS), true);
  assert.equal(isFinalDiagnosticState(DIAGNOSTIC_STATES.L1_ERROR), true);
  assert.equal(isFinalDiagnosticState(DIAGNOSTIC_STATES.L1_TIMEOUT), true);
  assert.equal(isFinalDiagnosticState(DIAGNOSTIC_STATES.L1_CANCELLED), true);
  assert.equal(isFinalDiagnosticState(DIAGNOSTIC_STATES.PDF_FETCH_STARTED), false);
});