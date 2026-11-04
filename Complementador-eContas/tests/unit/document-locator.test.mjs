import test from 'node:test';
import assert from 'node:assert/strict';
import { isBirthDocumentText, isResolutionDocumentText } from '../../src/autos/document-locator.mjs';

test('recognizes_birth_guide_by_title', () => {
  assert.equal(isBirthDocumentText('Guia Financeira/Taxação de Proventos\nData de Nascimento: 01/02/1980'), true);
});

test('recognizes_birth_guide_without_accent', () => {
  assert.equal(isBirthDocumentText('GUIA FINANCEIRA/TAXACAO DE PROVENTOS'), true);
});

test('does_not_confuse_resolution_with_birth_guide', () => {
  const resolution = 'RESOLUÇÃO ADMINISTRATIVA Nº 017, DE 8 DE JANEIRO DE 2021. Concede aposentadoria voluntária.';
  assert.equal(isBirthDocumentText(resolution), false);
  assert.equal(isResolutionDocumentText(resolution), true);
});
