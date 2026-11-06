import test from 'node:test';
import assert from 'node:assert/strict';
import { MESSAGE, createRequestId, errorResult, isRequestId } from '../../src/shared/protocol.mjs';
import { TransactionManager, withTimeout } from '../../src/background/bridge.mjs';

test('protocol_messages_are_stable_and_serializable', () => {
  assert.deepEqual(Object.values(MESSAGE).sort(), [
    'APPLY_PLAN', 'BATCH_APPLY', 'BATCH_ENSURE_DOCUMENT', 'BATCH_FORM_SNAPSHOT', 'BATCH_LIST_SNAPSHOT', 'BATCH_PAUSE', 'BATCH_PREVIEW', 'BATCH_PREFS_GET', 'BATCH_PREFS_SET', 'BATCH_RECONCILE_EXTERNAL', 'BATCH_RESET', 'BATCH_RESUME', 'BATCH_SAVE', 'BATCH_SELECT_INTERESTED', 'BATCH_START', 'BATCH_STATUS', 'BATCH_STOP', 'BATCH_UI_UPDATE', 'BATCH_VALIDATE_FORM', 'BATCH_VERIFY_SAVED', 'CANCEL', 'DIAGNOSE_DOCUMENT', 'DIAGNOSTIC_STATE', 'DIAGNOSTIC_UPDATE', 'DISCOVER_DOCUMENTS', 'DOCUMENT_SEARCH', 'FETCH_PDF', 'FILTER_AUTO_CLAIM', 'FILTER_AUTO_DONE', 'FILTER_PRESET_GET', 'FILTER_PRESET_SET', 'GET_DIAGNOSTIC', 'READ_DOCUMENT', 'REQUEST_FILL', 'RESULT',
  ].sort());
  const result = errorResult('req-12345678', 'X', 'message');
  assert.deepEqual(JSON.parse(JSON.stringify(result)), result);
});

test('request_id_is_ephemeral_and_valid', () => {
  const first = createRequestId();
  const second = createRequestId();
  assert.equal(isRequestId(first), true);
  assert.equal(isRequestId(second), true);
  assert.notEqual(first, second);
  assert.equal(isRequestId('short'), false);
});

test('double_click_is_single_transaction', () => {
  const manager = new TransactionManager({ timeoutMs: 1000 });
  assert.equal(manager.begin(1, 'req-12345678'), true);
  assert.equal(manager.begin(1, 'req-87654321'), false);
  assert.equal(manager.isActive(1, 'req-12345678'), true);
  assert.equal(manager.finish(1, 'req-12345678'), true);
  assert.equal(manager.begin(1, 'req-87654321'), true);
  manager.cancel(1);
});

test('worker_restart_aborts_without_replay', () => {
  const first = new TransactionManager({ timeoutMs: 1000 });
  first.begin(1, 'req-12345678');
  const restarted = new TransactionManager({ timeoutMs: 1000 });
  assert.equal(restarted.isActive(1, 'req-12345678'), false);
  assert.equal(restarted.get(1), null);
});

test('timeout_aborts', async () => {
  await assert.rejects(
    () => withTimeout(new Promise(() => {}), 5, 'READ_TIMEOUT'),
    (error) => error.code === 'READ_TIMEOUT',
  );
});
