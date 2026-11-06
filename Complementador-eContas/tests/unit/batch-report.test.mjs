import test from 'node:test';
import assert from 'node:assert/strict';
import { createFrozenBatch } from '../../src/batch/queue.mjs';
import { buildBatchReport } from '../../src/batch/report.mjs';

function batch(overrides = {}) {
  const base = createFrozenBatch({
    batchId: 'batch-report',
    listTabId: 4,
    contextKey: 'ctx-r',
    entries: [
      { processId: '401', processLabel: '401/2020', status: 'pending' },
      { processId: '402', processLabel: '402/2020', status: 'completed' },
      { processId: '403', processLabel: '403/2020', status: 'pending' },
      { processId: '404', processLabel: '404/2020', status: 'unknown' },
    ],
    limits: { maxExamined: 2, maxSaved: 2 },
    startedAt: 10,
  });
  return { ...base, ...overrides };
}

test('report_reconciles_totals', () => {
  const report = buildBatchReport(batch({
    queue: [
      { processId: '401', processLabel: '401/2020', status: 'CONFIRMED' },
      { processId: '403', processLabel: '403/2020', status: 'REVIEW_REQUIRED' },
    ],
    counters: { examined: 2, saved: 1 },
  }));
  assert.equal(report.totals.captured, 4);
  assert.equal(report.totals.skippedCompleted, 1);
  assert.equal(report.totals.skippedUnknown, 1);
  assert.equal(report.totals.examined, 2);
  assert.equal(report.totals.confirmed, 1);
  assert.equal(report.totals.review, 1);
  assert.equal(report.items.length, 2);
});

test('preexcluded_not_examined', () => {
  const report = buildBatchReport(batch());
  assert.equal(report.totals.examined, 0);
  assert.equal(report.totals.confirmed, 0);
  assert.equal(report.totals.queued, 2);
  assert.equal(report.totals.skippedCompleted, 1);
  assert.equal(report.totals.skippedUnknown, 1);
  assert.equal(report.items.every((item) => item.processId !== '402'), true);
});

test('uncertain_not_counted_as_saved', () => {
  const report = buildBatchReport(batch({
    queue: [
      { processId: '401', processLabel: '401/2020', status: 'SAVE_UNCERTAIN' },
      { processId: '403', processLabel: '403/2020', status: 'QUEUED' },
    ],
    state: 'SUSPENDED',
    counters: { examined: 1, saved: 0 },
  }));
  assert.equal(report.totals.confirmed, 0);
  assert.equal(report.totals.uncertain, 1);
  assert.equal(report.totals.saved, 0);
});

test('filled_without_save_is_not_confirmed', () => {
  const report = buildBatchReport(batch({
    queue: [{ processId: '401', processLabel: '401/2020', status: 'FILLED' }],
    counters: { examined: 1, saved: 0 },
  }));
  assert.equal(report.totals.filled, 1);
  assert.equal(report.totals.confirmed, 0);
  assert.equal(report.totals.saved, 0);
});

test('reasons_are_sanitized', () => {
  const report = buildBatchReport(batch({
    queue: [{
      processId: '401',
      processLabel: '401/2020',
      status: 'FAILED',
      reason: 'falha com CPF 123.456.789-00 e nome FULANO',
      interestedName: 'FULANO',
    }],
  }));
  const serialized = JSON.stringify(report);
  assert.equal(serialized.includes('FULANO'), false);
  assert.equal(serialized.includes('123.456.789-00'), false);
  assert.equal(report.items.find((item) => item.processId === '401').reasonCode, 'PROCESS_FAILED');
});

test('no_pii_in_report', () => {
  const report = buildBatchReport(batch({
    interestedName: 'FULANO DE TAL',
    cpf: '12345678900',
    birthDate: '01/01/1970',
    matricula: '12345-6',
    pdfText: 'texto integral',
  }));
  const serialized = JSON.stringify(report);
  for (const fragment of ['FULANO', '12345678900', '01/01/1970', '12345-6', 'texto integral']) {
    assert.equal(serialized.includes(fragment), false, fragment);
  }
});

test('links_reject_untrusted_origin', () => {
  const trusted = buildBatchReport(batch(), { portalOrigin: 'https://processos.tce.rn.gov.br' });
  const approved = trusted.items.find((item) => item.processId === '401');
  assert.equal(approved.link.startsWith('https://processos.tce.rn.gov.br/'), true);
  const untrusted = buildBatchReport(batch(), { portalOrigin: 'https://evil.invalid' });
  assert.equal(untrusted.items.every((item) => item.link === null), true);
  const injection = buildBatchReport(batch({
    queue: [{ processId: 'javascript:alert(1)', processLabel: '', status: 'QUEUED' }],
  }), { portalOrigin: 'https://processos.tce.rn.gov.br' });
  assert.equal(injection.items[0].link, null);
});

test('report_includes_sanitized_missing_field_cause', () => {
  const report = buildBatchReport(batch({
    queue: [{ processId: '401', processLabel: '401/2020', status: 'REVIEW_REQUIRED' }],
    counters: { examined: 1, saved: 0 },
    diagnostics: {
      '401': { cause: 'GUIA_NOT_MATCHED', fields: ['dataNascimento'], at: 10 },
    },
  }));
  const item = report.items.find((entry) => entry.processId === '401');
  assert.equal(item.reasonCode, 'REVIEW_REQUIRED');
  assert.equal(item.cause, 'GUIA_NOT_MATCHED');
  assert.deepEqual(item.fields, ['dataNascimento']);
});
