import test from 'node:test';
import assert from 'node:assert/strict';
import { createBridgeClient, pairBridge } from '../lib/bridge-client.js';

const AUTOMATION_FIELDS = [
  'modalidade',
  'fundamento_legal',
  'data_publicacao_doe',
  'cargo',
  'matricula',
  'data_nascimento',
  'genero',
];

function redactedFieldEvidence() {
  return Object.fromEntries(AUTOMATION_FIELDS.map((field) => [field, {
    status: 'present',
    valueHash: 'a'.repeat(64),
    optionsHash: 'a'.repeat(64),
    disabled: false,
    readOnly: false,
    redacted: true,
  }]));
}

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

test('bridge exposes authenticated automation methods with closed wire payloads', async () => {
  const calls = [];
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/automation/capabilities')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            api_version: 1,
            automation_schema: 1,
            legal_context_schema: 1,
            rules_version: 'legal-foundation-v1',
            real_send_enabled: false,
          }),
        };
      }
      if (url.includes('/legal-context?')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            api_version: 1,
            context: {
              schema_version: 1,
              dataset_sha256: 'a'.repeat(64),
              process_key: '103439/2023',
              interested_normalized: 'ana',
              resolution_status: 'pending',
              operative_text: '',
              pages: [],
            },
          }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          api_version: 1,
          run_id: 'run-1',
          revision: 0,
          status: 'discovering',
          items: [],
          last_confirmed_item_id: null,
        }),
      };
    },
  });

  await bridge.getAutomationCapabilities();
  await bridge.getLegalContext({ processKey: '103439/2023', interestedNormalized: 'ana' });
  await bridge.createAutomationRun({
    tabId: 7,
    sector: 'aposentadorias',
    datasetSha256: 'a'.repeat(64),
    rulesVersion: 'legal-foundation-v1',
  }, 'start-1');
  await bridge.freezeAutomationQueue('run-1', {
    identities: [{ processKey: '103439/2023', interestedNormalized: 'ana', portalActId: null }],
    eventId: 'queue-1',
    expectedRevision: 0,
  });
  await bridge.appendAutomationEvent('run-1', {
    eventId: 'prepare-1',
    expectedRevision: 1,
    itemId: '103439/2023',
    type: 'item_prepared',
    payload: {
      reason: 'prepared',
      identity: { processKey: '103439/2023', interestedNormalized: 'ana', portalActId: null },
      frame: { generation: 1, frameId: 0 },
      dataset_sha256: 'a'.repeat(64),
      context_hash: 'a'.repeat(64),
      legalDecision: {
        status: 'selected',
        method: 'rule',
        rule_id: 'rule-1',
        option_value: 'option-1',
        rules_version: 'legal-foundation-v1',
      },
      matchKinds: Object.fromEntries(AUTOMATION_FIELDS.map((field) => [field, 'exact'])),
      before: redactedFieldEvidence(),
      after: redactedFieldEvidence(),
    },
  });
  await bridge.controlAutomationRun('run-1', { action: 'pause', eventId: 'pause-1', expectedRevision: 2 });

  assert.match(calls[0].url, /\/automation\/capabilities$/u);
  assert.match(calls[1].url, /process_key=103439%2F2023&interested_normalized=ana/u);
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    tab_id: 7,
    sector: 'aposentadorias',
    dataset_sha256: 'a'.repeat(64),
    rules_version: 'legal-foundation-v1',
    event_id: 'start-1',
  });
  assert.deepEqual(JSON.parse(calls[3].options.body), {
    identities: [{ process_key: '103439/2023', interested_normalized: 'ana', portal_act_id: null }],
    event_id: 'queue-1',
    expected_revision: 0,
  });
});

test('new automation client falls back to manual mode when an old service lacks capabilities', async () => {
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async () => ({
      ok: false,
      status: 404,
      json: async () => ({ error: { code: 'NOT_FOUND', message: 'rota não encontrada' } }),
    }),
  });
  assert.equal(await bridge.getAutomationCapabilities(), null);
});

test('bridge consumes a command once and returns dispatch authorization separately from the snapshot', async () => {
  const calls = [];
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return {
        ok: true,
        status: 200,
        json: async () => ({
          api_version: 1,
          dispatch_allowed: true,
          command_id: 'command-1',
          run_id: 'run-1',
          revision: 5,
          status: 'running',
          items: [],
          last_confirmed_item_id: null,
        }),
      };
    },
  });

  const result = await bridge.consumeAutomationCommand('run-1', 'command-1', 4);
  assert.equal(result.dispatch_allowed, true);
  assert.equal(result.command_id, 'command-1');
  assert.match(calls[0].url, /\/automation\/runs\/run-1\/commands\/command-1\/consume$/u);
  assert.deepEqual(JSON.parse(calls[0].options.body), { expected_revision: 4 });
});
