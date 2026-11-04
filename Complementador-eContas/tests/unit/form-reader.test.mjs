import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { FORM_ERROR, readForm } from '../../src/form/form-reader.mjs';

const html = (name) => readFileSync(new URL('../fixtures/' + name, import.meta.url), 'utf8');

function load(name = 'form-complemento.html', hash = '#/dashboard/complementar-ato/999001') {
  const dom = new JSDOM(html(name), {
    url: 'https://processos.tce.rn.gov.br/' + hash,
    runScripts: 'dangerously',
  });
  return { dom, doc: dom.window.document };
}

test('modalidade_process_level_and_four_fields', () => {
  const { doc } = load();
  const form = readForm(doc);
  assert.equal(form.processId, '999001');
  assert.equal(form.processLabel, '999001/2026');
  assert.equal(form.modalitySelected, false);
  assert.equal(form.modalities.length, 11);
  assert.deepEqual(Object.keys(form.values).sort(), ['cargo', 'dataDoeEstado', 'dataNascimento', 'matricula']);
  assert.equal(form.interestedName, 'PESSOA UM');
  assert.equal(form.interestedCount, 1);
  assert.match(form.revisionMarker, /^[0-9a-f]{8}$/);
});

test('selected_person_name_strips_synthetic_cpf', () => {
  const { doc } = load();
  assert.equal(readForm(doc).interestedName, 'PESSOA UM');
  assert.equal(readForm(doc).interestedKey.length, 8);
});

test('revision_marker_changes_with_values', () => {
  const { doc } = load();
  const before = readForm(doc);
  doc.querySelector('tce-input-field[formcontrolname="cargo"] input').value = 'CARGO TESTE';
  const after = readForm(doc);
  assert.notEqual(before.revisionMarker, after.revisionMarker);
});

test('multi_interested_switch_changes_identity', () => {
  const { doc } = load('form-multi-interested.html');
  const first = readForm(doc);
  const cards = [...doc.querySelectorAll('button.cartao-item')];
  cards[0].classList.remove('selecionada');
  cards[1].classList.add('selecionada');
  const second = readForm(doc);
  assert.equal(first.interestedCount, 2);
  assert.equal(second.interestedName, 'PESSOA DOIS');
  assert.notEqual(first.interestedKey, second.interestedKey);
});

test('not_loaded_or_invalid_form_refused', () => {
  const empty = new JSDOM('<!doctype html><body></body>', { url: 'https://processos.tce.rn.gov.br/#/dashboard/complementar-ato/999001' });
  assert.throws(() => readForm(empty.window.document), (error) => error.code === FORM_ERROR.FORM_NOT_LOADED);
  const autos = new JSDOM('<!doctype html><body></body>', { url: 'https://processos.tce.rn.gov.br/#/dashboard/processos/999001/autos' });
  assert.throws(() => readForm(autos.window.document), (error) => error.code === FORM_ERROR.FORM_NOT_LOADED);
});

test('no_selected_person_is_refused', () => {
  const { doc } = load();
  doc.querySelector('button.cartao-item').classList.remove('selecionada');
  assert.throws(() => readForm(doc), (error) => error.code === FORM_ERROR.INTERESTED_NOT_SELECTED);
});