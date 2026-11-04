import test from 'node:test';
import assert from 'node:assert/strict';
import { runDocumentDiagnostic, runFillTransaction } from '../../src/background/bridge.mjs';

const ORIGIN = 'https://processos.tce.rn.gov.br';
const formTab = { id: 10, url: ORIGIN + '/#/dashboard/complementar-ato/999001' };
const sourceTab = { id: 20, url: ORIGIN + '/#/dashboard/processos/999001/autos', windowId: 2 };
const snapshot = { interestedName: 'PESSOA UM', interestedKey: 'abcd1234', interestedCount: 1, processLabel: '999001/2026' };
const document = { documentKey: 'deadbeef', processId: '999001', processLabel: '999001/2026', pages: ['RESOLUÇÃO ADMINISTRATIVA N. 1, DE 7 DE NOVEMBRO DE 2025. RESOLVE conceder aposentadoria voluntária por tempo de contribuição com proventos integrais a PESSOA UM, no cargo de ANALISTA DE TESTES, matrícula 001234-5/1, nascida em 01/02/1980. Natal, 7 de novembro de 2025.'], sourceKind: 'pdf-bytes', observedAt: 1 };

const completeProposals = () => ({
  modalidade: { status: 'exact', value: 'Aposentadoria voluntária por tempo de contribuição com proventos integrais' },
  dataDoeEstado: { status: 'exact', value: '07/11/2025' },
  cargo: { status: 'exact', value: 'ANALISTA DE TESTES' },
  matricula: { status: 'exact', value: '001234-5/1' },
  dataNascimento: { status: 'exact', value: '01/02/1980' },
});

function deps(overrides = {}) {
  let sourceCalls = 0;
  let formCalls = 0;
  return {
    formTab,
    sourceTabs: [sourceTab],
    requestId: 'req-12345678',
    formSnapshot: snapshot,
    timeoutMs: 100,
    sendToSource: async () => { sourceCalls += 1; return { ok: true, document }; },
    sendToForm: async () => { formCalls += 1; return { ok: true, report: { ok: true, filled: [{ field: 'cargo' }] } }; },
    extract: () => completeProposals(),
    counts: () => ({ sourceCalls, formCalls }),
    ...overrides,
  };
}

test('run_fill_transaction_success', async () => {
  const input = deps();
  const result = await runFillTransaction(input);
  assert.equal(result.ok, true);
  assert.equal(result.document.pagesCount, 1);
  assert.equal(result.report.filled[0].field, 'cargo');
  assert.deepEqual(input.counts(), { sourceCalls: 1, formCalls: 1 });
});

test('different_process_is_rejected_before_reading', async () => {
  const input = deps({ sourceTabs: [{ ...sourceTab, url: ORIGIN + '/#/dashboard/processos/999002/autos' }] });
  const result = await runFillTransaction(input);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'SOURCE_NOT_FOUND');
  assert.deepEqual(input.counts(), { sourceCalls: 0, formCalls: 0 });
});

test('two_source_tabs_are_ambiguous_before_reading', async () => {
  const input = deps({ sourceTabs: [sourceTab, { ...sourceTab, id: 21, windowId: 3 }] });
  const result = await runFillTransaction(input);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'SOURCE_AMBIGUOUS');
  assert.deepEqual(input.counts(), { sourceCalls: 0, formCalls: 0 });
});

test('document_process_mismatch_is_rejected', async () => {
  const input = deps({ sendToSource: async () => ({ ok: true, document: { ...document, processId: '999002' } }) });
  const result = await runFillTransaction(input);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'DOCUMENT_PROCESS_MISMATCH');
  assert.equal(input.counts().formCalls, 0);
});

test('read_timeout_is_reported', async () => {
  const input = deps({ timeoutMs: 5, sendToSource: () => new Promise(() => {}) });
  const result = await runFillTransaction(input);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'READ_TIMEOUT');
});

test('apply_rejection_is_reported', async () => {
  const input = deps({ sendToForm: async () => ({ ok: false, code: 'APPLY_REJECTED' }) });
  const result = await runFillTransaction(input);
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'APPLY_REJECTED');
});
test('run_document_diagnostic_returns_only_sanitized_metrics', async () => {
  const input = deps({
    sendToSource: async () => ({
      ok: true,
      document: { ...document, pages: ['abc', 'defgh'] },
    }),
  });
  const result = await runDocumentDiagnostic({
    formTab: input.formTab,
    sourceTabs: input.sourceTabs,
    requestId: input.requestId,
    formSnapshot: input.formSnapshot,
    sendToSource: input.sendToSource,
    timeoutMs: 100,
  });
  assert.equal(result.ok, true);
  assert.equal(result.diagnostic.pagesCount, 2);
  assert.equal(result.diagnostic.totalChars, 8);
  assert.equal(result.diagnostic.minPageChars, 3);
  assert.equal(result.diagnostic.maxPageChars, 5);
  assert.equal(result.diagnostic.pages, undefined);
  assert.equal(JSON.stringify(result).includes('abc'), false);
});

test('diagnostic_cross_process_is_rejected_before_reading', async () => {
  const input = deps({
    sourceTabs: [{ ...sourceTab, url: ORIGIN + '/#/dashboard/processos/999002/autos' }],
  });
  const result = await runDocumentDiagnostic({
    formTab: input.formTab,
    sourceTabs: input.sourceTabs,
    requestId: input.requestId,
    formSnapshot: input.formSnapshot,
    sendToSource: input.sendToSource,
    timeoutMs: 100,
  });
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'SOURCE_NOT_FOUND');
  assert.deepEqual(input.counts(), { sourceCalls: 0, formCalls: 0 });
});
test('process_label_mismatch_is_rejected', async () => {
  const input = deps({
    sendToSource: async () => ({
      ok: true,
      document: { ...document, processLabel: '999999/2026' },
    }),
  });
  const result = await runDocumentDiagnostic({
    formTab: input.formTab,
    sourceTabs: input.sourceTabs,
    requestId: input.requestId,
    formSnapshot: input.formSnapshot,
    sendToSource: input.sendToSource,
    timeoutMs: 100,
  });
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'PROCESS_LABEL_MISMATCH');
});

test('diagnostic_cancelled_before_reading', async () => {
  const input = deps();
  const result = await runDocumentDiagnostic({
    formTab: input.formTab,
    sourceTabs: input.sourceTabs,
    requestId: input.requestId,
    formSnapshot: input.formSnapshot,
    sendToSource: input.sendToSource,
    timeoutMs: 100,
    isCancelled: () => true,
  });
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'TRANSACTION_CANCELLED');
  assert.deepEqual(input.counts(), { sourceCalls: 0, formCalls: 0 });
});
test('diagnostic_emits_stage_states', async () => {
  const input = deps();
  const states = [];
  const result = await runDocumentDiagnostic({
    formTab: input.formTab,
    sourceTabs: input.sourceTabs,
    requestId: input.requestId,
    formSnapshot: input.formSnapshot,
    sendToSource: input.sendToSource,
    timeoutMs: 100,
    onState: (state) => states.push(state),
  });
  assert.equal(result.ok, true);
  assert.deepEqual(states, ['SOURCE_TAB_RESOLVED', 'PDF_TEXT_EXTRACTED']);
});
