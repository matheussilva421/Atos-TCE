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

test('authenticated loopback requests explicitly opt into CORS', async () => {
  let requestOptions;
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async (_url, options) => {
      requestOptions = options;
      return {
        ok: true,
        status: 200,
        json: async () => ({ api_version: 1, revision: 0, dataset: {} }),
      };
    },
  });

  await bridge.getDataset();
  assert.equal(requestOptions.mode, 'cors');
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
            rules_version: 'legal-foundation-v3',
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
    rulesVersion: 'legal-foundation-v3',
    marker: 'PROFESSOR - IPERN - 2 RUBRICAS',
    markerValue: 'marker-1',
    sourceScope: 'my_processes',
    acquisitionSource: 'econtas',
    lotSize: 100,
    analysisId: `analysis-${'a'.repeat(24)}`,
    previewHash: 'a'.repeat(64),
    autoSubmit: true,
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
        rules_version: 'legal-foundation-v3',
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
    rules_version: 'legal-foundation-v3',
    marker: 'PROFESSOR - IPERN - 2 RUBRICAS',
    marker_value: 'marker-1',
    source_scope: 'my_processes',
    acquisition_source: 'econtas',
    lot_size: 100,
    analysis_id: `analysis-${'a'.repeat(24)}`,
    preview_hash: 'a'.repeat(64),
    auto_submit: true,
    event_id: 'start-1',
  });
  assert.deepEqual(JSON.parse(calls[3].options.body), {
    identities: [{ process_key: '103439/2023', interested_normalized: 'ana', portal_act_id: null }],
    event_id: 'queue-1',
    expected_revision: 0,
  });
  const eventBody = JSON.parse(calls[4].options.body);
  assert.equal(calls[4].options.method, 'POST');
  assert.match(calls[4].url, /\/automation\/runs\/run-1\/events$/u);
  assert.deepEqual(Object.keys(eventBody).sort(), ['event_id', 'expected_revision', 'item_id', 'payload', 'type']);
  assert.equal(eventBody.event_id, 'prepare-1');
  assert.equal(eventBody.expected_revision, 1);
  assert.equal(eventBody.item_id, '103439/2023');
  assert.equal(eventBody.type, 'item_prepared');
  assert.deepEqual(eventBody.payload.identity, {
    process_key: '103439/2023',
    interested_normalized: 'ana',
    portal_act_id: null,
  });
  assert.deepEqual(eventBody.payload.frame, { generation: 1, frameId: 0 });
  assert.deepEqual(eventBody.payload.legalDecision, {
    status: 'selected',
    method: 'rule',
    rule_id: 'rule-1',
    option_value: 'option-1',
    rules_version: 'legal-foundation-v3',
  });
  assert.deepEqual(eventBody.payload.before, redactedFieldEvidence());
  assert.deepEqual(JSON.parse(calls[5].options.body), {
    action: 'pause',
    event_id: 'pause-1',
    expected_revision: 2,
  });
});

test('event payload without identity is forwarded without fabricating one', async () => {
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
          run_id: 'run-1',
          revision: 2,
          status: 'running',
          items: [],
          last_confirmed_item_id: null,
        }),
      };
    },
  });

  await bridge.appendAutomationEvent('run-1', {
    eventId: 'pending-1',
    expectedRevision: 1,
    itemId: '103439/2023',
    type: 'item_pending',
    payload: { reason: 'contexto ausente', legalDecision: { status: 'pending' } },
  });

  assert.deepEqual(JSON.parse(calls[0].options.body), {
    event_id: 'pending-1',
    expected_revision: 1,
    item_id: '103439/2023',
    type: 'item_pending',
    payload: { reason: 'contexto ausente', legalDecision: { status: 'pending' } },
  });
});

test('bridge exposes authenticated analysis preview and deterministic lot methods', async () => {
  const calls = [];
  const analysis = {
    schema_version: 1,
    analysis_id: `analysis-${'a'.repeat(24)}`,
    dataset_sha256: 'a'.repeat(64),
    preview: { total_seen: 1, eligible: 1, lot_count: 1 },
    queue: [],
    blocked: [],
  };
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 200, json: async () => analysis };
    },
  });
  const spec = {
    schema_version: 2,
    source_scope: 'my_processes',
    marker: { label: 'Marcador', value: 'm-1' },
    acquisition_source: 'econtas',
    lot_size: 50,
    analysis_only: true,
    auto_prepare: true,
    auto_submit: false,
    dataset_sha256: null,
    area_snapshot_sha256: 'b'.repeat(64),
  };

  await bridge.createAnalysisPreview({ spec, rows: [], observedAt: '2026-09-10T12:00:00Z' });
  await bridge.getAnalysisPreview(analysis.analysis_id);
  await bridge.createAnalysisLots(analysis.analysis_id);

  assert.deepEqual(JSON.parse(calls[0].options.body), {
    spec,
    rows: [],
    observed_at: '2026-09-10T12:00:00Z',
  });
  assert.match(calls[1].url, /\/analysis\/analysis-aaaaaaaaaaaaaaaaaaaaaaaa$/u);
  assert.match(calls[2].url, /\/analysis\/analysis-aaaaaaaaaaaaaaaaaaaaaaaa\/lots$/u);
});

test('bridge accepts schema v3 analysis with authoritative input provenance', async () => {
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: 3,
        analysis_id: `analysis-${'c'.repeat(24)}`,
        dataset_sha256: 'd'.repeat(64),
        preview: { total_seen: 1, eligible: 1, lot_count: 1 },
        spec: {
          input_list_id: `input-${'f'.repeat(24)}`,
          input_sha256: 'a'.repeat(64),
          input_unique_count: 1128,
        },
        queue: [],
        blocked: [],
      }),
    }),
  });
  await bridge.createAnalysisPreview({
    spec: {
      schema_version: 3,
      source_scope: 'sector_finalistic',
      marker: { label: 'Marcador', value: 'm-1' },
      acquisition_source: 'econtas',
      lot_size: 300,
      analysis_only: true,
      auto_prepare: false,
      auto_submit: false,
      dataset_sha256: null,
      area_snapshot_sha256: 'e'.repeat(64),
      input_list_id: `input-${'f'.repeat(24)}`,
      input_sha256: 'a'.repeat(64),
      input_unique_count: 1128,
    },
    rows: [],
    observedAt: '2026-09-14T12:00:00Z',
  });
});

test('bridge imports and reads the active authoritative process list', async () => {
  const calls = [];
  const manifest = {
    schema_version: 1,
    input_list_id: `input-${'a'.repeat(24)}`,
    input_sha256: 'b'.repeat(64),
    source_filename: 'professor-ipern.xlsx',
    sheet_name: 'Planilha2',
    row_count: 1,
    unique_count: 1,
    duplicate_count: 0,
    ordered_unique_keys: ['101/2023'],
    rows: [{ source_row: 2, process_key: '101/2023', duplicate_of_row: null }],
  };
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 200, json: async () => manifest };
    },
  });
  const imported = await bridge.importProcessList({ filename: manifest.source_filename, contentBase64: 'UEsDBA==' });
  const active = await bridge.getActiveProcessList();
  assert.equal(imported.input_list_id, manifest.input_list_id);
  assert.equal(active.input_list_id, manifest.input_list_id);
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].options.body), { filename: manifest.source_filename, content_base64: 'UEsDBA==' });
});

test('bridge exposes authenticated acquisition start and status for a frozen analysis lot', async () => {
  const calls = [];
  const analysisId = `analysis-${'a'.repeat(24)}`;
  const jobId = `acq-${'b'.repeat(24)}`;
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      const status = url.endsWith(`/analysis/${analysisId}/acquire/${jobId}`)
        ? { api_version: 1, analysis_id: analysisId, job_id: jobId, lot_number: 2, status: 'running', pid: 4321 }
        : { api_version: 1, analysis_id: analysisId, job_id: jobId, lot_number: 2, status: 'started', pid: 4321 };
      return { ok: true, status: 202, json: async () => status };
    },
  });

  const started = await bridge.startAnalysisAcquisition(analysisId, { selection: 'lot', lotNumber: 2 });
  const observed = await bridge.getAnalysisAcquisition(analysisId, jobId);

  assert.equal(started.job_id, jobId);
  assert.equal(observed.status, 'running');
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].options.body), { selection: 'lot', lot_number: 2 });
  assert.match(calls[1].url, /\/analysis\/analysis-aaaaaaaaaaaaaaaaaaaaaaaa\/acquire\/acq-bbbbbbbbbbbbbbbbbbbbbbbb$/u);
});

test('bridge starts acquisition for every frozen lot with the typed all selection', async () => {
  const calls = [];
  const analysisId = `analysis-${'a'.repeat(24)}`;
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 202, json: async () => ({ api_version: 1, analysis_id: analysisId, job_id: `acq-${'c'.repeat(24)}`, selection: 'all', lot_number: 0, status: 'started', pid: 4321 }) };
    },
  });

  const started = await bridge.startAnalysisAcquisition(analysisId, { selection: 'all' });

  assert.equal(started.selection, 'all');
  assert.deepEqual(JSON.parse(calls[0].options.body), { selection: 'all' });
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

test('bridge exposes paginated run history and event cursors', async () => {
  const calls = [];
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'test',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.includes('/events?')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            api_version: 1,
            events: [{ event_id: 'event-1', run_id: 'run-1', seq: 1, type: 'queue_frozen', payload: {}, created_at: '2026-09-09T12:00:00Z' }],
            next_after: 1,
            has_more: false,
          }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          api_version: 1,
          runs: [{ run_id: 'run-1', state: 'paused', revision: 3, created_at: '2026-09-09T12:00:00Z', updated_at: '2026-09-09T12:01:00Z', totals: { confirmed: 0 } }],
          next_cursor: null,
        }),
      };
    },
  });

  const runs = await bridge.listAutomationRuns({ limit: 20 });
  const events = await bridge.getAutomationEvents('run-1', { after: 0, limit: 100 });
  assert.equal(runs.runs[0].run_id, 'run-1');
  assert.equal(events.events[0].type, 'queue_frozen');
  assert.match(calls[0].url, /\/automation\/runs\?limit=20$/u);
  assert.match(calls[1].url, /\/automation\/runs\/run-1\/events\?after=0&limit=100$/u);
});

test('bridge downloads an authenticated automation report without exposing its token', async () => {
  const calls = [];
  const bridge = createBridgeClient({
    baseUrl: 'http://127.0.0.1:18743',
    token: 'secret-token',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return {
        ok: true,
        status: 200,
        headers: { get: (name) => name === 'Content-Type' ? 'text/html; charset=utf-8' : null },
        async arrayBuffer() { return new TextEncoder().encode('<h1>relatório</h1>').buffer; },
      };
    },
  });
  const report = await bridge.getAutomationReport('run-1', 'html');
  assert.equal(report.contentType, 'text/html; charset=utf-8');
  assert.equal(new TextDecoder().decode(report.body), '<h1>relatório</h1>');
  assert.match(calls[0].url, /\/automation\/runs\/run-1\/report\?format=html$/u);
  assert.equal(calls[0].options.headers.Authorization, 'Bearer secret-token');
  assert.equal(calls[0].url.includes('secret-token'), false);
});
