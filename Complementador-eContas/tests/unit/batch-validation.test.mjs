import test from 'node:test';
import assert from 'node:assert/strict';
import { compareExistingFields, validateBatchReady } from '../../src/form/batch-validation.mjs';

function snapshot(overrides = {}) {
  return {
    processId: '601',
    processLabel: '601/2020',
    interestedKey: 'abc12345',
    interestedCount: 1,
    interestedIndex: 0,
    revisionMarker: 'rev-1',
    values: { dataDoeEstado: '', cargo: '', matricula: '', dataNascimento: '' },
    editable: { dataDoeEstado: true, cargo: true, matricula: true, dataNascimento: true },
    modalities: [{ id: 'm1', label: 'Aposentadoria voluntária por tempo de contribuição', disabled: false }],
    modalitySelected: false,
    modalitySelectedLabel: '',
    ...overrides,
  };
}

const PROPOSALS = {
  modalidade: 'Aposentadoria voluntária por tempo de contribuição',
  dataDoeEstado: '05/03/2020',
  cargo: 'AUXILIAR DE INFRAESTRUTURA',
  matricula: '81382-6/1',
  dataNascimento: '06/07/1964',
};

test('batch_existing_conflict_blocks_submit', () => {
  const result = compareExistingFields(
    snapshot({ values: { dataDoeEstado: '01/01/2020', cargo: '', matricula: '', dataNascimento: '' } }),
    PROPOSALS,
  );
  assert.equal(result.ok, false);
  assert.deepEqual(result.conflicts, ['dataDoeEstado']);
  assert.deepEqual(result.unknown, []);
});

test('equivalent_normalized_date_is_preserved', () => {
  for (const existing of ['05/03/2020', '5/3/2020', '2020-03-05']) {
    const result = compareExistingFields(
      snapshot({ values: { dataDoeEstado: existing, cargo: '', matricula: '', dataNascimento: '' } }),
      PROPOSALS,
    );
    assert.equal(result.ok, true, existing);
    assert.deepEqual(result.conflicts, [], existing);
  }
});

test('existing_modality_mismatch_blocks', () => {
  const result = compareExistingFields(
    snapshot({
      modalitySelected: true,
      modalitySelectedLabel: 'Reforma',
    }),
    PROPOSALS,
  );
  assert.equal(result.ok, false);
  assert.deepEqual(result.conflicts, ['modalidade']);
});

test('missing_expected_value_for_existing_field_routes_to_review', () => {
  const result = compareExistingFields(
    snapshot({ values: { dataDoeEstado: '', cargo: 'AUXILIAR', matricula: '', dataNascimento: '' } }),
    { ...PROPOSALS, cargo: '' },
  );
  assert.equal(result.ok, false);
  assert.deepEqual(result.unknown, ['cargo']);
});

test('all_five_required', () => {
  const filled = snapshot({
    values: { dataDoeEstado: '05/03/2020', cargo: PROPOSALS.cargo, matricula: PROPOSALS.matricula, dataNascimento: PROPOSALS.dataNascimento },
    modalitySelected: true,
    modalitySelectedLabel: PROPOSALS.modalidade,
  });
  const context = { processId: '601', interestedKey: 'abc12345', interestedCount: 1, status: 'pending', revisionMarker: 'rev-1' };
  assert.equal(validateBatchReady(filled, context).ok, true);
  const incomplete = snapshot({
    values: { dataDoeEstado: '05/03/2020', cargo: '', matricula: '', dataNascimento: '' },
    modalitySelected: true,
    modalitySelectedLabel: PROPOSALS.modalidade,
  });
  const blocked = validateBatchReady(incomplete, context);
  assert.equal(blocked.ok, false);
  assert.equal(blocked.code, 'MISSING_FIELDS');
});

test('visible_form_error_blocks', () => {
  const filled = snapshot({
    values: { dataDoeEstado: '05/03/2020', cargo: PROPOSALS.cargo, matricula: PROPOSALS.matricula, dataNascimento: PROPOSALS.dataNascimento },
    modalitySelected: true,
    modalitySelectedLabel: PROPOSALS.modalidade,
  });
  const result = validateBatchReady(filled, {
    processId: '601', interestedKey: 'abc12345', interestedCount: 1, status: 'pending', revisionMarker: 'rev-1', visibleErrors: true,
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'VISIBLE_ERROR');
});

test('wrong_identity_blocks', () => {
  const filled = snapshot({
    values: { dataDoeEstado: '05/03/2020', cargo: PROPOSALS.cargo, matricula: PROPOSALS.matricula, dataNascimento: PROPOSALS.dataNascimento },
    modalitySelected: true,
    modalitySelectedLabel: PROPOSALS.modalidade,
  });
  assert.equal(validateBatchReady(filled, {
    processId: '602', interestedKey: 'abc12345', interestedCount: 1, status: 'pending', revisionMarker: 'rev-1',
  }).code, 'PROCESS_MISMATCH');
  assert.equal(validateBatchReady(filled, {
    processId: '601', interestedKey: 'outra', interestedCount: 1, status: 'pending', revisionMarker: 'rev-1',
  }).code, 'INTERESTED_CHANGED');
  assert.equal(validateBatchReady(filled, {
    processId: '601', interestedKey: 'abc12345', interestedCount: 1, status: 'completed', revisionMarker: 'rev-1',
  }).code, 'PROCESS_NOT_PENDING');
  assert.equal(validateBatchReady(filled, {
    processId: '601', interestedKey: 'abc12345', interestedCount: 2, status: 'pending', revisionMarker: 'rev-1',
  }).code, 'MULTIPLE_INTERESTED');
  assert.equal(validateBatchReady(filled, {
    processId: '601', interestedKey: 'abc12345', interestedCount: 1, status: 'pending', revisionMarker: 'rev-2',
  }).code, 'FORM_REVISION_CHANGED');
});
