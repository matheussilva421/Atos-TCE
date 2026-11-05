import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { handleBatchFormMessage } from '../../src/form/batch-content.mjs';

const RUNTIME_ID = 'ext-runtime';
const URL_COMPLEMENT = 'https://processos.tce.rn.gov.br/#/dashboard/complementar-ato/901';

function document(body, url = URL_COMPLEMENT) {
  return new JSDOM('<html><body>' + body + '</body></html>', { url }).window.document;
}

function card(name, selected = false) {
  return '<button class="cartao-item' + (selected ? ' selecionada' : '') + '">'
    + '<span>' + name + '</span><small>123.456.789-00</small></button>';
}

function filledForm(overrides = {}) {
  return '<tce-container>' + card('Pessoa A', true) + '</tce-container>'
    + '<tce-input-field formcontrolname="dataDoeEstado"><input value="05/03/2020"></tce-input-field>'
    + '<tce-input-field formcontrolname="cargo"><input value="AUXILIAR"></tce-input-field>'
    + '<tce-input-field formcontrolname="matricula"><input value="81382-6/1"></tce-input-field>'
    + '<tce-input-field formcontrolname="dataNascimento"><input value="06/07/1964"></tce-input-field>'
    + '<tce-select-field class="modalidade-campo"><ng-select><div class="ng-value">'
    + '<span class="ng-value-label">Aposentadoria voluntária</span></div></ng-select></tce-select-field>'
    + (overrides.extra || '');
}

const SENDER = { id: RUNTIME_ID };

test('select_interested_returns_only_transient_key', async () => {
  const doc = document('<tce-container>' + card('Pessoa A') + '</tce-container>');
  doc.querySelector('button.cartao-item').addEventListener('click', (event) => {
    event.currentTarget.classList.add('selecionada');
  });
  const result = await handleBatchFormMessage(
    { type: 'BATCH_SELECT_INTERESTED', processId: '901' },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  assert.equal(result.ok, true);
  assert.equal(result.interestedCount, 1);
  assert.equal(typeof result.interestedKey, 'string');
  assert.equal(JSON.stringify(result).includes('Pessoa A'), false);
  assert.equal(JSON.stringify(result).includes('123.456.789-00'), false);
});

test('validate_blocks_multiple_interested', async () => {
  const doc = document(filledForm({ extra: card('B') }));
  const result = await handleBatchFormMessage(
    { type: 'BATCH_VALIDATE_FORM', processId: '901' },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  assert.equal(result.ok, false);
  assert.equal(result.code, 'MULTIPLE_INTERESTED');
});

test('validate_blocks_missing_fields', async () => {
  const doc = document('<tce-container>' + card('A', true) + '</tce-container>'
    + '<tce-input-field formcontrolname="cargo"><input value=""></tce-input-field>'
    + '<tce-input-field formcontrolname="matricula"><input value=""></tce-input-field>'
    + '<tce-input-field formcontrolname="dataNascimento"><input value=""></tce-input-field>'
    + '<tce-input-field formcontrolname="dataDoeEstado"><input value=""></tce-input-field>');
  const result = await handleBatchFormMessage(
    { type: 'BATCH_VALIDATE_FORM', processId: '901' },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  assert.equal(result.ok, false);
  assert.equal(result.code, 'MISSING_FIELDS');
});

test('validate_blocks_visible_error', async () => {
  const doc = document(filledForm({ extra: '<div class="invalid-feedback">Campo obrigatório</div>' }));
  const result = await handleBatchFormMessage(
    { type: 'BATCH_VALIDATE_FORM', processId: '901' },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  assert.equal(result.ok, false);
  assert.equal(result.code, 'VISIBLE_ERROR');
});

test('wrong_process_and_untrusted_blocked', async () => {
  const doc = document(filledForm());
  const wrong = await handleBatchFormMessage(
    { type: 'BATCH_SELECT_INTERESTED', processId: '902' },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  assert.equal(wrong.code, 'PROCESS_MISMATCH');
  const untrusted = await handleBatchFormMessage(
    { type: 'BATCH_SELECT_INTERESTED', processId: '901' },
    { id: 'evil' },
    doc,
    RUNTIME_ID,
  );
  assert.equal(untrusted.code, 'UNTRUSTED_SENDER');
});
