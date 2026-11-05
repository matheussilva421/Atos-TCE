import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createFillPlan } from '../../src/form/form-writer.mjs';
import { MESSAGE } from '../../src/shared/protocol.mjs';
import { BATCH_JOURNAL_KEY } from '../../src/batch/journal.mjs';
import { DOCUMENT_CACHE_KEY } from '../../src/background/document-cache.mjs';

const PROPOSALS = {
  dataDoeEstado: { status: 'exact', value: '05/03/2020' },
  cargo: { status: 'exact', value: 'AUXILIAR DE INFRAESTRUTURA' },
  matricula: { status: 'exact', value: '81382-6/1' },
  dataNascimento: { status: 'exact', value: '06/07/1964' },
};

function form(overrides = {}) {
  return {
    values: { dataDoeEstado: '', cargo: '', matricula: '', dataNascimento: '', ...(overrides.values || {}) },
    editable: { dataDoeEstado: true, cargo: true, matricula: true, dataNascimento: true, ...(overrides.editable || {}) },
    maxlength: { dataDoeEstado: null, cargo: null, matricula: null, dataNascimento: null },
    modalities: [],
    modalitySelected: false,
  };
}

test('manual_fill_preserves_existing_values', () => {
  const plan = createFillPlan(PROPOSALS, form({
    values: { cargo: 'OUTRO CARGO' },
    editable: { matricula: false },
  }));
  assert.deepEqual(plan.fields.cargo, { action: 'preserve', reason: 'EXISTING_VALUE' });
  assert.deepEqual(plan.fields.matricula, { action: 'preserve', reason: 'READONLY' });
  assert.deepEqual(plan.fields.dataDoeEstado.action, 'fill');
});

test('manual_button_and_message_are_unchanged', () => {
  const content = readFileSync('src/form/content.mjs', 'utf8');
  assert.equal(content.includes('⚡ Preencher'), true);
  assert.equal(content.includes('Rodar automação'), false);
  assert.equal(MESSAGE.REQUEST_FILL, 'REQUEST_FILL');
});

test('batch_apply_does_not_relax_manual_transaction_gate', () => {
  const content = readFileSync('src/form/content.mjs', 'utf8');
  const manualStart = content.indexOf("message.type !== MESSAGE.APPLY_PLAN");
  const batchStart = content.indexOf('message.type !== MESSAGE.BATCH_APPLY');
  assert.equal(manualStart > 0, true);
  assert.equal(batchStart > manualStart, true);
  const manualBlock = content.slice(manualStart, batchStart);
  assert.equal(manualBlock.includes('STALE_TRANSACTION'), true);
  const batchBlock = content.slice(batchStart, batchStart + 900);
  assert.equal(batchBlock.includes('STALE_TRANSACTION'), false);
  assert.equal(batchBlock.includes('UNTRUSTED_SENDER'), true);
});

test('manual_path_never_imports_batch_save', () => {
  for (const file of ['src/form/content.mjs', 'src/background/index.mjs']) {
    const source = readFileSync(file, 'utf8');
    assert.equal(source.includes('save-adapter'), false, file);
    assert.equal(source.includes('batch/runner'), false, file);
  }
});

test('background_request_fill_still_uses_transaction_bridge', () => {
  const background = readFileSync('src/background/index.mjs', 'utf8');
  assert.equal(background.includes('runFillTransaction('), true);
  const fillHandler = background.slice(
    background.indexOf('async function handleRequestFill'),
    background.indexOf('async function handleDiagnoseDocument'),
  );
  assert.equal(fillHandler.includes('runFillTransaction('), true);
  assert.equal(fillHandler.includes('save'), false);
});

test('batch_and_manual_use_different_storage_keys', () => {
  assert.notEqual(BATCH_JOURNAL_KEY, DOCUMENT_CACHE_KEY);
  const form = readFileSync('src/form/content.mjs', 'utf8');
  assert.equal(form.includes(BATCH_JOURNAL_KEY), false);
  assert.equal(form.includes('chrome.storage'), false);
});

test('manual_untrusted_sender_is_still_rejected', () => {
  const background = readFileSync('src/background/index.mjs', 'utf8');
  assert.equal(background.includes('UNTRUSTED_SENDER'), true);
  const fillHandler = background.slice(
    background.indexOf('async function handleRequestFill'),
    background.indexOf('async function handleDiagnoseDocument'),
  );
  assert.equal(fillHandler.includes('isTrusted(sender)'), true);
  assert.equal(fillHandler.includes('isRequestId(message.requestId)'), true);
});
