import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyFailure, waitForCondition } from '../../src/batch/waits.mjs';

test('condition_satisfied_exits_immediately', async () => {
  let calls = 0;
  const result = await waitForCondition(() => {
    calls += 1;
    return true;
  }, { timeoutMs: 5000, pollMs: 50 });
  assert.equal(result, true);
  assert.equal(calls, 1);
});

test('bounded_timeout_reports_failure', async () => {
  let calls = 0;
  const started = Date.now();
  const result = await waitForCondition(() => {
    calls += 1;
    return false;
  }, { timeoutMs: 80, pollMs: 5 });
  assert.equal(result, false);
  assert.equal(calls > 1, true);
  assert.equal(Date.now() - started < 2000, true);
});

test('transient_read_retry_limited', () => {
  assert.equal(classifyFailure('read', { code: 'TRANSIENT_READ' }, []), 'retry');
  assert.equal(classifyFailure('read', { code: 'FORM_NOT_LOADED' }, []), 'retry');
  const history = [
    { code: 'TRANSIENT_READ' },
    { code: 'TRANSIENT_READ' },
    { code: 'TRANSIENT_READ' },
  ];
  assert.equal(classifyFailure('read', { code: 'TRANSIENT_READ' }, history), 'pause');
});

test('repeated_systemic_failure_pauses', () => {
  const history = [{ code: 'SYSTEMIC' }, { code: 'SYSTEMIC' }, { code: 'SYSTEMIC' }];
  assert.equal(classifyFailure('navigate', { code: 'SYSTEMIC' }, history), 'pause');
  assert.equal(classifyFailure('navigate', { code: 'UNEXPECTED' }, []), 'review');
});

test('no_retry_for_save_unknown', () => {
  assert.equal(classifyFailure('save', { code: 'SAVE_RESULT_UNKNOWN' }, []), 'suspend');
  assert.equal(classifyFailure('save', { code: 'TIMEOUT' }, []), 'suspend');
  assert.equal(classifyFailure('save', { code: 'SAVE_BUTTON_NOT_FOUND' }, []), 'review');
});

test('abort_on_route_change', async () => {
  let calls = 0;
  const result = await waitForCondition(() => {
    calls += 1;
    const error = new Error('rota mudou');
    error.code = 'ROUTE_CHANGED';
    throw error;
  }, { timeoutMs: 5000, pollMs: 5 });
  assert.equal(result, false);
  assert.equal(calls, 1);
});
