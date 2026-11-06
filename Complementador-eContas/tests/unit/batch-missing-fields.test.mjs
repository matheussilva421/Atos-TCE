import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyMissingFields } from '../../src/batch/missing-fields.mjs';

function diag(overrides = {}) {
  return {
    resolutionFound: true,
    guiaFound: true,
    proposalStatus: {
      modalidade: 'exact',
      dataDoeEstado: 'exact',
      cargo: 'exact',
      matricula: 'exact',
      dataNascimento: 'exact',
    },
    skipped: [],
    errors: [],
    ...overrides,
  };
}

test('interests_mismatch_has_priority', () => {
  assert.equal(classifyMissingFields({
    fields: ['cargo'],
    diagnostics: diag(),
    errorCode: 'INTERESTED_CHANGED',
  }).cause, 'INTERESTED_MISMATCH');
});

test('timeout_is_classified', () => {
  assert.equal(classifyMissingFields({ fields: [], diagnostics: diag(), errorCode: 'READ_TIMEOUT' }).cause, 'TIMEOUT');
});

test('unreadable_pdf_is_classified', () => {
  assert.equal(classifyMissingFields({
    fields: [],
    diagnostics: diag({ documentCode: 'PDF_NOT_READABLE' }),
  }).cause, 'PDF_NOT_READABLE');
});

test('missing_documents_are_classified', () => {
  assert.equal(classifyMissingFields({
    fields: ['cargo'],
    diagnostics: diag({ resolutionFound: false, guiaFound: false }),
  }).cause, 'DOCUMENT_NOT_FOUND');
});

test('ambiguous_value_is_classified', () => {
  assert.equal(classifyMissingFields({
    fields: ['cargo'],
    diagnostics: diag({ proposalStatus: { ...diag().proposalStatus, cargo: 'ambiguous' } }),
  }).cause, 'AMBIGUOUS_VALUE');
});

test('resolution_not_matched_is_classified', () => {
  assert.equal(classifyMissingFields({
    fields: ['dataDoeEstado'],
    diagnostics: diag({
      resolutionFound: false,
      guiaFound: true,
      proposalStatus: { ...diag().proposalStatus, dataDoeEstado: 'absent' },
    }),
  }).cause, 'RESOLUTION_NOT_MATCHED');
});

test('guia_not_matched_is_classified', () => {
  assert.equal(classifyMissingFields({
    fields: ['dataNascimento'],
    diagnostics: diag({
      guiaFound: false,
      proposalStatus: { ...diag().proposalStatus, dataNascimento: 'absent' },
    }),
  }).cause, 'GUIA_NOT_MATCHED');
});

test('field_not_present_is_classified', () => {
  assert.equal(classifyMissingFields({
    fields: ['matricula'],
    diagnostics: diag({
      proposalStatus: { ...diag().proposalStatus, matricula: 'absent' },
      skipped: [{ field: 'matricula', reason: 'NOT_EXACT' }],
    }),
  }).cause, 'FIELD_NOT_PRESENT');
});

test('classifier_returns_only_known_sanitized_fields', () => {
  const result = classifyMissingFields({
    fields: ['cargo', 'FULANO', 'cpf'],
    diagnostics: diag({ proposalStatus: { ...diag().proposalStatus, cargo: 'absent' } }),
  });
  assert.deepEqual(result.fields, ['cargo']);
  assert.equal(JSON.stringify(result).includes('FULANO'), false);
});
