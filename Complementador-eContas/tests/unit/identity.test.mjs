import test from 'node:test';
import assert from 'node:assert/strict';
import { extractInterestedCpf, extractInterestedName } from '../../src/shared/identity.mjs';

test('strips_cpf_concatenated_to_last_name', () => {
  assert.equal(extractInterestedName('PESSOA UM000.000.000-00'), 'PESSOA UM');
});

test('strips_cpf_without_space_and_trailing_punctuation', () => {
  assert.equal(extractInterestedName('PESSOA UM 000.000.000-00.'), 'PESSOA UM');
  assert.equal(extractInterestedName('PESSOA UM00000000000'), 'PESSOA UM');
});

test('extracts_transient_cpf_from_card_text', () => {
  assert.equal(extractInterestedCpf('PESSOA UM 000.000.000-00'), '00000000000');
  assert.equal(extractInterestedCpf('PESSOA UM 00000000000'), '00000000000');
  assert.equal(extractInterestedCpf('PESSOA UM'), '');
});
