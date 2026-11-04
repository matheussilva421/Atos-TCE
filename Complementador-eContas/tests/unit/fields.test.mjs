import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { extractFields } from '../../src/extract/fields.mjs';

const fixture = (name) => readFileSync(new URL('../fixtures/' + name, import.meta.url), 'utf8');
const doc = (text) => ({ documentKey: 'synthetic', processId: '999001', pages: [text], sourceKind: 'pdf-bytes', observedAt: 1 });
const ctx = (overrides = {}) => ({ processId: '999001', selectedInterested: 'PESSOA UM', interestedCount: 1, ...overrides });

test('extracts_exact_modality_and_person_fields', () => {
  const result = extractFields(doc(fixture('resolucao-natodigital.txt')), ctx());
  assert.equal(result.modalidade.status, 'exact');
  assert.equal(result.modalidade.value, 'Aposentadoria voluntária por tempo de contribuição com proventos integrais');
  assert.equal(result.dataDoeEstado.status, 'exact');
  assert.equal(result.dataDoeEstado.value, '07/11/2025');
  assert.equal(result.cargo.status, 'exact');
  assert.equal(result.cargo.value, 'ANALISTA DE TESTES');
  assert.equal(result.matricula.status, 'exact');
  assert.equal(result.matricula.value, '001234-5/1');
  assert.equal(result.dataNascimento.status, 'exact');
  assert.equal(result.dataNascimento.value, '01/02/1980');
});

test('preserve_matricula_slash_and_zeros', () => {
  const result = extractFields(doc(fixture('resolucao-natodigital.txt')), ctx());
  assert.equal(result.matricula.value, '001234-5/1');
});

test('cargo_not_inferred_from_unrelated_section', () => {
  const text = 'RESOLVE conceder aposentadoria compulsória à PESSOA UM, matrícula 001234-5/1. O cargo em comissão foi exercido em outro período. Natal, 7 de novembro de 2025.';
  const result = extractFields(doc(text), ctx());
  assert.equal(result.modalidade.value, 'Aposentadoria compulsória');
  assert.equal(result.cargo.status, 'absent');
});

test('birth_not_invented', () => {
  const text = 'RESOLVE conceder aposentadoria compulsória à PESSOA UM, matrícula 001234-5/1. Natal, 7 de novembro de 2025.';
  const result = extractFields(doc(text), ctx());
  assert.equal(result.dataNascimento.status, 'absent');
});

test('interest_mismatch_drops_person_fields', () => {
  const result = extractFields(doc(fixture('resolucao-natodigital.txt')), ctx({ selectedInterested: 'PESSOA DOIS' }));
  assert.equal(result.modalidade.status, 'exact');
  assert.equal(result.cargo.status, 'absent');
  assert.equal(result.matricula.status, 'absent');
  assert.equal(result.dataNascimento.status, 'absent');
});

test('unmapped_modality_is_ambiguous', () => {
  const text = 'RESOLVE conceder um benefício não catalogado à PESSOA UM, matrícula 001234-5/1. Natal, 7 de novembro de 2025.';
  const result = extractFields(doc(text), ctx());
  assert.equal(result.modalidade.status, 'absent');
});