import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseResolutionDate, parseBirthDate } from '../../src/extract/dates.mjs';

const fixture = (name) => readFileSync(new URL('../fixtures/' + name, import.meta.url), 'utf8');

test('seven_november_to_07_11_2025', () => {
  const result = parseResolutionDate('Natal, 7 de novembro de 2025.');
  assert.equal(result.status, 'exact');
  assert.equal(result.dateBr, '07/11/2025');
  assert.equal(result.source, 'data da resolução administrativa');
});

test('resolution_date_not_birth_or_other_date', () => {
  const text = 'A interessada nasceu em 7 de novembro de 1980. RESOLVE conceder o benefício. Natal, 7 de novembro de 2025.';
  const result = parseResolutionDate(text);
  assert.equal(result.status, 'exact');
  assert.equal(result.dateBr, '07/11/2025');
});

test('header_date_wins_over_later_natal_date', () => {
  const result = parseResolutionDate(fixture('resolucao-ambigua.txt'));
  assert.equal(result.status, 'exact');
  assert.equal(result.dateBr, '07/11/2025');
});

test('header_date_wins_over_body_resolv_date', () => {
  const text = 'RESOLUÇÃO ADMINISTRATIVA Nº 1, DE 7 DE NOVEMBRO DE 2025. RESOLVE conceder o benefício em 8 de novembro de 2025.';
  const result = parseResolutionDate(text);
  assert.equal(result.status, 'exact');
  assert.equal(result.dateBr, '07/11/2025');
});

test('body_date_is_used_when_no_header_or_natal_date', () => {
  const result = parseResolutionDate('RESOLVE conceder o benefício em 8 de novembro de 2025.');
  assert.equal(result.status, 'exact');
  assert.equal(result.dateBr, '08/11/2025');
});

test('two_header_dates_are_ambiguous', () => {
  const text = 'RESOLUÇÃO ADMINISTRATIVA Nº 1, DE 7 DE NOVEMBRO DE 2025. RESOLUÇÃO ADMINISTRATIVA Nº 2, DE 8 DE NOVEMBRO DE 2025.';
  const result = parseResolutionDate(text);
  assert.equal(result.status, 'ambiguous');
});

test('invalid_calendar_date_is_absent', () => {
  const result = parseResolutionDate('Natal, 31 de fevereiro de 2025.');
  assert.equal(result.status, 'absent');
});

test('birth_date_requires_explicit_birth_context', () => {
  const text = 'PESSOA UM, nascida em 01/02/1980, matrícula 001234-5/1.';
  const result = parseBirthDate(text);
  assert.equal(result.status, 'exact');
  assert.equal(result.dateBr, '01/02/1980');
  assert.equal(parseBirthDate('PESSOA UM, 01/02/1980.').status, 'absent');
});

test('birth_date_after_other_fields_in_guia_layout', () => {
  const text = 'Guia Financeira/Taxacao de Proventos. Processo N. 999001. Segurado: PESSOA UM. CPF: 000.000.000-00. RG: 0000000. Data de Nascimento: Assunto: NOVO FLUXO. Regra: REGRA DE TRANSICAO. Data: 01/02/1980.';
  const result = parseBirthDate(text);
  assert.equal(result.status, 'exact');
  assert.equal(result.dateBr, '01/02/1980');
});

test('resolution_fixture_is_exact', () => {
  const result = parseResolutionDate(fixture('resolucao-natodigital.txt'));
  assert.equal(result.status, 'exact');
  assert.equal(result.dateBr, '07/11/2025');
});
