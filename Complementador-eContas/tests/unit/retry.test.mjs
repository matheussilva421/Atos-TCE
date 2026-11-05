import test from 'node:test';
import assert from 'node:assert/strict';
import { retryAsync } from '../../src/shared/retry.mjs';

test('returns_first_success_without_extra_sleep', async () => {
  let calls = 0;
  const sleeps = [];
  const value = await retryAsync(async () => {
    calls += 1;
    return 'ok';
  }, { attempts: 3, sleep: async (ms) => { sleeps.push(ms); } });
  assert.equal(value, 'ok');
  assert.equal(calls, 1);
  assert.deepEqual(sleeps, []);
});

test('retries_until_receiver_exists_then_succeeds', async () => {
  let calls = 0;
  const value = await retryAsync(async () => {
    calls += 1;
    if (calls < 4) {
      throw new Error('Could not establish connection. Receiving end does not exist.');
    }
    return 'ready';
  }, { attempts: 5, delayMs: 1, sleep: async () => {} });
  assert.equal(value, 'ready');
  assert.equal(calls, 4);
});

test('gives_up_after_attempt_limit', async () => {
  let calls = 0;
  await assert.rejects(
    () => retryAsync(async () => {
      calls += 1;
      throw new Error('still missing');
    }, { attempts: 3, delayMs: 1, sleep: async () => {} }),
    /still missing/,
  );
  assert.equal(calls, 3);
});
