import test from 'node:test';
import assert from 'node:assert/strict';
import { createTabSender } from '../../src/batch/tab-sender.mjs';

test('retries_undefined_until_real_response', async () => {
  let calls = 0;
  const sender = createTabSender(async () => {
    calls += 1;
    return calls < 4 ? undefined : { ok: true };
  }, { attempts: 6, delayMs: 1, sleep: async () => {} });
  const response = await sender(7, { type: 'X' });
  assert.deepEqual(response, { ok: true });
  assert.equal(calls, 4);
});

test('fails_after_limit_of_empty_responses', async () => {
  let calls = 0;
  const sender = createTabSender(async () => {
    calls += 1;
    return undefined;
  }, { attempts: 3, delayMs: 1, sleep: async () => {} });
  await assert.rejects(() => sender(7, { type: 'X' }), (error) => error.code === 'CONTENT_SCRIPT_NOT_READY');
  assert.equal(calls, 3);
});

test('passes_through_errors_and_valid_responses', async () => {
  const failing = createTabSender(async () => {
    throw new Error('no receiver');
  }, { attempts: 2, delayMs: 1, sleep: async () => {} });
  await assert.rejects(() => failing(1, {}), /no receiver/);
  const okSender = createTabSender(async () => ({ ok: false, code: 'X' }), { attempts: 2, delayMs: 1, sleep: async () => {} });
  assert.deepEqual(await okSender(1, {}), { ok: false, code: 'X' });
});
