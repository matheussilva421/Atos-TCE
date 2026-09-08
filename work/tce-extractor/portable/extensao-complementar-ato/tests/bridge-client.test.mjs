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

test('bridge enforces endpoint response envelopes', async () => {
  const malformedResponses = [
    ['pairing', () => pairBridge({
      baseUrl: 'http://127.0.0.1:18743',
      code: '12345678',
      fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ api_version: 2, token: 'ephemeral' }) }),
    })],
    ['state', () => createBridgeClient({
      baseUrl: 'http://127.0.0.1:18743',
      token: 'test',
      fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ api_version: 1 }) }),
    }).getState()],
    ['dataset', () => createBridgeClient({
      baseUrl: 'http://127.0.0.1:18743',
      token: 'test',
      fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ api_version: 1, revision: 0 }) }),
    }).getDataset()],
    ['selection', () => createBridgeClient({
      baseUrl: 'http://127.0.0.1:18743',
      token: 'test',
      fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ revision: 1 }) }),
    }).publishSelection({
      process_key: '103439/2023',
      interested_normalized: 'pessoa teste',
      tab_id: 1,
      frame_id: 0,
      sequence: 1,
    })],
    ['progress', () => createBridgeClient({
      baseUrl: 'http://127.0.0.1:18743',
      token: 'test',
      fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ api_version: 1 }) }),
    }).setCompleted('103439/2023', true, 0)],
  ];

  for (const [label, operation] of malformedResponses) {
    await assert.rejects(operation, (error) => error.code === 'INVALID_RESPONSE', label);
  }
});

test('bridge rejects malformed error envelopes instead of trusting arbitrary JSON', async () => {
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async () => ({ ok: false, status: 401, json: async () => ({ message: 'not an error envelope' }) }),
  });

  await assert.rejects(bridge.getState(), (error) => error.code === 'INVALID_RESPONSE');
});

test('bridge timeout does not depend on fetch honoring AbortSignal', async () => {
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    timeoutMs: 10,
    fetchImpl: async () => new Promise(() => {}),
  });

  const result = Promise.race([
    bridge.getState(),
    new Promise((_, reject) => setTimeout(() => reject(new Error('test timeout')), 100)),
  ]);
  await assert.rejects(result, (error) => error.code === 'BRIDGE_TIMEOUT');
});

test('bridge accepts only the configured loopback port range and rejects invalid selection input', async () => {
  for (const baseUrl of [
    'http://127.0.0.1:18742',
    'http://127.0.0.1:18753',
    'http://localhost:18743',
    'http://[::1]:18743',
    'http://127.0.0.1:18743/path',
    'http://127.0.0.1:18743/?x=1',
  ]) {
    assert.throws(() => createBridgeClient({ baseUrl, token: 'test' }), (error) => error.code === 'INVALID_BASE_URL');
  }

  let called = false;
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18752',
    token: 'test',
    fetchImpl: async () => {
      called = true;
      return { ok: true, status: 200, json: async () => ({ accepted: true, revision: 1 }) };
    },
  });
  await assert.rejects(
    bridge.publishSelection({ process_key: '103439/2023', interested_normalized: 'pessoa teste', tab_id: 1, frame_id: 0, sequence: 0 }),
    (error) => error.code === 'INVALID_SELECTION',
  );
  assert.equal(called, false);
});
