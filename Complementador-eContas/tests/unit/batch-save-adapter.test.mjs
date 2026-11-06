import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import {
  clickComplementarAtoOnce,
  inspectSaveUi,
  observeSaveOutcome,
  HOMOLOGATED_DIALOG,
} from '../../src/form/save-adapter.mjs';

const URL_COMPLEMENT = 'https://processos.tce.rn.gov.br/#/dashboard/complementar-ato/801';

function pages(body) {
  const dom = new JSDOM('<html><body>' + body + '</body></html>', { url: URL_COMPLEMENT });
  return dom.window.document;
}

const SAVE_BUTTON = '<button class="btn btn-primary ng-star-inserted">Complementar ato</button>';

function realDialog(overrides = {}) {
  return '<div class="modal show" role="dialog" aria-modal="true">'
    + '<h4 class="modal-title">' + (overrides.title || HOMOLOGATED_DIALOG.title) + '</h4>'
    + '<button class="cancelar">' + (overrides.cancelText || HOMOLOGATED_DIALOG.cancelText) + '</button>'
    + '<button class="confirmar">' + (overrides.confirmText || HOMOLOGATED_DIALOG.confirmText) + '</button>'
    + (overrides.extra || '')
    + '</div>';
}

test('known_dialog_can_confirm_once', async () => {
  const document = pages(SAVE_BUTTON + realDialog());
  let confirms = 0;
  document.querySelector('.confirmar').addEventListener('click', () => { confirms += 1; });
  const result = await clickComplementarAtoOnce(document, {
    processId: '801',
    attemptId: 'attempt-801-1',
    knownDialog: HOMOLOGATED_DIALOG,
  }, { wait: async () => {} });
  assert.equal(result.attempted, true);
  assert.equal(result.result, 'ack');
  assert.equal(confirms, 1);
});

test('unknown_dialog_is_not_accepted', async () => {
  const document = pages(SAVE_BUTTON + realDialog({ title: 'Mensagem inesperada' }));
  let confirms = 0;
  document.querySelector('.confirmar').addEventListener('click', () => { confirms += 1; });
  const result = await clickComplementarAtoOnce(document, { processId: '801', attemptId: 'attempt-801-2' }, { wait: async () => {} });
  assert.equal(result.attempted, true);
  assert.equal(result.result, 'unknown');
  assert.equal(result.code, 'UNKNOWN_DIALOG');
  assert.equal(confirms, 0);
});

test('missing_cancel_button_fails_closed', async () => {
  const document = pages(SAVE_BUTTON
    + '<div class="modal show" role="dialog" aria-modal="true">'
    + '<h4 class="modal-title">' + HOMOLOGATED_DIALOG.title + '</h4>'
    + '<button class="confirmar">' + HOMOLOGATED_DIALOG.confirmText + '</button>'
    + '</div>');
  let confirms = 0;
  document.querySelector('.confirmar').addEventListener('click', () => { confirms += 1; });
  const result = await clickComplementarAtoOnce(document, { processId: '801', attemptId: 'attempt-801-cancel' }, { wait: async () => {} });
  assert.equal(result.result, 'unknown');
  assert.equal(result.code, 'UNKNOWN_DIALOG');
  assert.equal(confirms, 0);
});

test('modal_without_dialog_role_fails_closed', async () => {
  const document = pages(SAVE_BUTTON
    + '<div class="modal show">'
    + '<h4 class="modal-title">' + HOMOLOGATED_DIALOG.title + '</h4>'
    + '<button class="cancelar">' + HOMOLOGATED_DIALOG.cancelText + '</button>'
    + '<button class="confirmar">' + HOMOLOGATED_DIALOG.confirmText + '</button>'
    + '</div>');
  let confirms = 0;
  document.querySelector('.confirmar').addEventListener('click', () => { confirms += 1; });
  const result = await clickComplementarAtoOnce(document, { processId: '801', attemptId: 'attempt-801-role' }, { wait: async () => {} });
  assert.equal(result.result, 'unknown');
  assert.equal(result.code, 'UNKNOWN_DIALOG');
  assert.equal(confirms, 0);
});

test('disabled_confirm_button_fails_closed', async () => {
  const document = pages(SAVE_BUTTON
    + '<div class="modal show" role="dialog" aria-modal="true">'
    + '<h4 class="modal-title">' + HOMOLOGATED_DIALOG.title + '</h4>'
    + '<button class="cancelar">' + HOMOLOGATED_DIALOG.cancelText + '</button>'
    + '<button class="confirmar" disabled>' + HOMOLOGATED_DIALOG.confirmText + '</button>'
    + '</div>');
  const result = await clickComplementarAtoOnce(document, { processId: '801', attemptId: 'attempt-801-disabled' }, { wait: async () => {} });
  assert.equal(result.result, 'unknown');
  assert.equal(result.code, 'UNKNOWN_DIALOG');
});

test('save_button_not_found_no_click', async () => {
  const document = pages('<div>sem botão</div>');
  assert.equal(inspectSaveUi(document).state, 'unknown');
  const result = await clickComplementarAtoOnce(document, { processId: '801', attemptId: 'attempt-801-3' }, { wait: async () => {} });
  assert.equal(result.attempted, false);
  assert.equal(result.code, 'SAVE_BUTTON_NOT_FOUND');
});

test('second_call_same_attempt_does_not_click', async () => {
  const document = pages(SAVE_BUTTON);
  const dispatched = new Set();
  const first = await clickComplementarAtoOnce(document, { processId: '801', attemptId: 'attempt-801-4' }, {
    wait: async () => {}, dispatched,
  });
  const second = await clickComplementarAtoOnce(document, { processId: '801', attemptId: 'attempt-801-4' }, {
    wait: async () => {}, dispatched,
  });
  assert.equal(first.attempted, true);
  assert.equal(second.attempted, false);
  assert.equal(second.code, 'ALREADY_ATTEMPTED');
});

test('portal_error_is_not_success', async () => {
  const document = pages(SAVE_BUTTON + '<div class="alert alert-danger">Falha ao salvar</div>');
  const result = await clickComplementarAtoOnce(document, { processId: '801', attemptId: 'attempt-801-5' }, { wait: async () => {} });
  assert.equal(result.result, 'error');
  assert.equal(result.code, 'PORTAL_ERROR');
});

test('different_process_identity_aborts', async () => {
  const document = pages(SAVE_BUTTON);
  const result = await clickComplementarAtoOnce(document, { processId: '899', attemptId: 'attempt-801-6' }, { wait: async () => {} });
  assert.equal(result.attempted, false);
  assert.equal(result.code, 'DIFFERENT_PROCESS');
});

test('outcome_is_unknown_without_verified_evidence', async () => {
  const document = pages(SAVE_BUTTON);
  const outcome = observeSaveOutcome(document, { processId: '801' });
  assert.equal(outcome.status, 'unknown');
  assert.deepEqual(outcome.evidence, []);
});
