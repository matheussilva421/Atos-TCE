import test from 'node:test';
import assert from 'node:assert/strict';
import { createBridgeClient, pairBridge } from '../lib/bridge-client.js';

test('selection update never applies fields', async () => {
  const calls = [];
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 200, json: async () => ({ accepted: true, revision: 1 }) };
    },
  });
  await bridge.publishSelection({
    process_key: '103439/2023',
    interested_normalized: 'PESSOA TESTE',
    tab_id: 1,
    frame_id: 0,
    sequence: 1,
  });
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/selection$/);
  assert.equal(calls[0].options.method, 'POST');
  assert.doesNotMatch(calls[0].options.body, /fields/i);
});

test('bridge rejects non-loopback and arbitrary base URLs', () => {
  assert.throws(() => createBridgeClient({ baseUrl: 'https://example.invalid', token: 'x' }), /loopback/i);
  assert.throws(() => createBridgeClient({ baseUrl: 'http://127.0.0.1:9000', token: 'x' }), /porta/i);
});

test('bridge maps stale progress response as a conflict', async () => {
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async () => ({
      ok: false,
      status: 409,
      json: async () => ({ error: { code: 'REVISION_CONFLICT', message: 'revisão conflitante' } }),
    }),
  });
  await assert.rejects(
    bridge.setCompleted('103439/2023', true, 0),
    (error) => error.code === 'REVISION_CONFLICT' && /conflitante/.test(error.message),
  );
});

test('pairing uses the fixed loopback endpoint and returns an ephemeral token', async () => {
  const calls = [];
  const token = await pairBridge({
    baseUrl: 'http://127.0.0.1:18743',
    code: '12345678',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 200, json: async () => ({ api_version: 1, token: 'ephemeral' }) };
    },
  });
  assert.equal(token, 'ephemeral');
  assert.equal(calls[0].url, 'http://127.0.0.1:18743/api/v1/pair');
  assert.deepEqual(JSON.parse(calls[0].options.body), { code: '12345678' });
});
