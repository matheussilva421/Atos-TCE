import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { handleBatchFormMessage, handleBatchSave } from '../../src/form/batch-content.mjs';

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

test('snapshot_returns_form_identity_transiently', async () => {
  const doc = document(filledForm());
  const result = await handleBatchFormMessage(
    { type: 'BATCH_FORM_SNAPSHOT', processId: '901' },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  assert.equal(result.ok, true);
  assert.equal(result.snapshot.processId, '901');
  assert.equal(result.snapshot.interestedCount, 1);
  assert.equal(typeof result.snapshot.interestedKey, 'string');
});

test('batch_save_reports_unknown_dialog_for_learning', async () => {
  const doc = document(filledForm({
    extra: '<button class="btn btn-primary">Complementar ato</button>'
      + '<div class="modal show"><h4 class="modal-title">Confirma a complementação?</h4>'
      + '<button>Cancelar</button><button>Confirmar</button></div>',
  }));
  const snapshot = await handleBatchFormMessage(
    { type: 'BATCH_FORM_SNAPSHOT', processId: '901' },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  const result = await handleBatchSave(
    {
      type: 'BATCH_SAVE',
      processId: '901',
      attemptId: 'attempt-901-learn',
      interestedKey: snapshot.snapshot.interestedKey,
    },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  assert.equal(result.ok, false);
  assert.equal(result.code, 'DIALOG_UNKNOWN');
  assert.match(result.dialog.title, /Confirma/);
  assert.deepEqual(result.dialog.buttons, ['Cancelar', 'Confirmar']);
});

test('batch_save_confirms_known_dialog_once', async () => {
  const doc = document(filledForm({
    extra: '<button class="btn btn-primary">Complementar ato</button>'
      + '<div class="modal show" role="dialog" aria-modal="true">'
      + '<h4 class="modal-title">Complementar ato</h4>'
      + '<button class="cancelar">NÃO</button>'
      + '<button class="confirmar">sim, complementar</button></div>',
  }));
  const snapshot = await handleBatchFormMessage(
    { type: 'BATCH_FORM_SNAPSHOT', processId: '901' },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  let confirms = 0;
  doc.querySelector('.confirmar').addEventListener('click', () => { confirms += 1; });
  const result = await handleBatchSave(
    {
      type: 'BATCH_SAVE',
      processId: '901',
      attemptId: 'attempt-901-known',
      interestedKey: snapshot.snapshot.interestedKey,
      knownDialog: { title: 'Complementar ato', confirmText: 'sim, complementar', cancelText: 'NÃO' },
    },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  assert.equal(result.ok, true);
  assert.equal(result.result, 'ack');
  assert.equal(confirms, 1);
});

test('batch_save_blocks_missing_fields_before_click', async () => {
  const doc = document('<tce-container>' + card('Pessoa A', true) + '</tce-container>'
    + '<tce-input-field formcontrolname="dataDoeEstado"><input value=""></tce-input-field>'
    + '<tce-input-field formcontrolname="cargo"><input value=""></tce-input-field>'
    + '<tce-input-field formcontrolname="matricula"><input value=""></tce-input-field>'
    + '<tce-input-field formcontrolname="dataNascimento"><input value=""></tce-input-field>'
    + '<button class="btn btn-primary">Complementar ato</button>');
  const snapshot = await handleBatchFormMessage(
    { type: 'BATCH_FORM_SNAPSHOT', processId: '901' },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  let clicks = 0;
  doc.querySelector('button.btn').addEventListener('click', () => { clicks += 1; });
  const result = await handleBatchSave(
    {
      type: 'BATCH_SAVE',
      processId: '901',
      attemptId: 'attempt-901-missing',
      interestedKey: snapshot.snapshot.interestedKey,
    },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  assert.equal(result.ok, false);
  assert.equal(result.code, 'MISSING_FIELDS');
  assert.equal(clicks, 0);
});

test('batch_save_blocks_changed_interested_before_click', async () => {
  const doc = document(filledForm({
    extra: '<button class="btn btn-primary">Complementar ato</button>',
  }));
  let clicks = 0;
  doc.querySelector('button.btn').addEventListener('click', () => { clicks += 1; });
  const result = await handleBatchSave(
    {
      type: 'BATCH_SAVE',
      processId: '901',
      attemptId: 'attempt-901-changed',
      interestedKey: 'another-key',
    },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  assert.equal(result.ok, false);
  assert.equal(result.code, 'INTERESTED_CHANGED');
  assert.equal(clicks, 0);
});

test('batch_save_blocks_visible_error_before_click', async () => {
  const doc = document(filledForm({
    extra: '<div class="invalid-feedback">Campo obrigatório</div>'
      + '<button class="btn btn-primary">Complementar ato</button>',
  }));
  const snapshot = await handleBatchFormMessage(
    { type: 'BATCH_FORM_SNAPSHOT', processId: '901' },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  let clicks = 0;
  doc.querySelector('button.btn').addEventListener('click', () => { clicks += 1; });
  const result = await handleBatchSave(
    {
      type: 'BATCH_SAVE',
      processId: '901',
      attemptId: 'attempt-901-error',
      interestedKey: snapshot.snapshot.interestedKey,
    },
    SENDER,
    doc,
    RUNTIME_ID,
  );
  assert.equal(result.ok, false);
  assert.equal(result.code, 'VISIBLE_ERROR');
  assert.equal(clicks, 0);
});
