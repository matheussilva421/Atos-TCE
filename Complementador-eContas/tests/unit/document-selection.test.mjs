import test from 'node:test';
import assert from 'node:assert/strict';
import { chooseBirthCandidate, chooseResolutionCandidate } from '../../src/background/bridge.mjs';

function proposals(cargo) {
  return {
    modalidade: { status: 'exact', value: 'Aposentadoria voluntária por tempo de contribuição com proventos integrais' },
    dataDoeEstado: { status: 'exact', value: '07/11/2025' },
    cargo: { status: 'exact', value: cargo },
    matricula: { status: 'exact', value: '001234-5/1' },
    dataNascimento: { status: 'absent' },
  };
}

test('resolution_candidate_with_more_exact_fields_wins', () => {
  const result = chooseResolutionCandidate([
    { eventId: 'decoy', proposals: { ...proposals('OUTRO'), cargo: { status: 'absent' }, matricula: { status: 'absent' } } },
    { eventId: 'correct', proposals: proposals('ANALISTA DE TESTES') },
  ]);
  assert.equal(result.eventId, 'correct');
  assert.equal(result.score, 4);
  assert.equal(result.proposals.cargo.value, 'ANALISTA DE TESTES');
});

test('resolution_tie_with_different_values_is_ambiguous', () => {
  const result = chooseResolutionCandidate([
    { eventId: 'a', proposals: proposals('CARGO A') },
    { eventId: 'b', proposals: proposals('CARGO B') },
  ]);
  assert.equal(result.eventId, null);
  assert.equal(result.proposals.cargo.status, 'ambiguous');
});

test('birth_uses_current_guia_when_selected_person_is_exact', () => {
  const result = chooseBirthCandidate({
    currentProposals: { dataNascimento: { status: 'exact', value: '01/02/1980' } },
    currentIsGuia: true,
    currentIsResolution: false,
    currentEventId: 'current',
    guias: [],
    selectedInterested: 'PESSOA UM',
    selectedInterestedCpf: '00000000000',
  });
  assert.equal(result.proposal.value, '01/02/1980');
  assert.equal(result.source, 'guia');
});

test('birth_uses_guide_proposal_from_person_correlation', () => {
  const result = chooseBirthCandidate({
    currentProposals: { dataNascimento: { status: 'absent' } },
    currentIsGuia: false,
    currentIsResolution: false,
    currentEventId: '',
    guias: [{ eventId: 'guia', pages: ['texto'], birthProposal: { status: 'exact', value: '01/02/1980' } }],
    selectedInterested: 'PESSOA UM',
    selectedInterestedCpf: '00000000000',
  });
  assert.equal(result.proposal.value, '01/02/1980');
  assert.equal(result.eventId, 'guia');
});

test('birth_correlates_guide_with_two_people_by_cpf', () => {
  const guia = 'Guia Financeira/Taxacao de Proventos. PESSOA UM CPF: 000.000.000-00. Data de Nascimento: 01/02/1980. PESSOA DOIS CPF: 111.111.111-11. Data de Nascimento: 03/04/1985.';
  const result = chooseBirthCandidate({
    currentProposals: { dataNascimento: { status: 'absent' } },
    currentIsGuia: false,
    currentIsResolution: false,
    currentEventId: '',
    guias: [{ eventId: 'guia', pages: [guia] }],
    selectedInterested: 'PESSOA DOIS',
    selectedInterestedCpf: '11111111111',
  });
  assert.equal(result.proposal.value, '03/04/1985');
  assert.equal(result.eventId, 'guia');
});

test('conflicting_birth_dates_between_guides_are_ambiguous', () => {
  const one = 'Guia Financeira/Taxacao de Proventos. PESSOA UM CPF: 000.000.000-00. Data de Nascimento: 01/02/1980.';
  const two = 'Guia Financeira/Taxacao de Proventos. PESSOA UM CPF: 000.000.000-00. Data de Nascimento: 02/02/1980.';
  const result = chooseBirthCandidate({
    currentProposals: { dataNascimento: { status: 'absent' } },
    currentIsGuia: false,
    currentIsResolution: false,
    currentEventId: '',
    guias: [{ eventId: 'one', pages: [one] }, { eventId: 'two', pages: [two] }],
    selectedInterested: 'PESSOA UM',
    selectedInterestedCpf: '00000000000',
  });
  assert.equal(result.proposal.status, 'ambiguous');
});
