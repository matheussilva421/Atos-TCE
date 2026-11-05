import test from 'node:test';
import assert from 'node:assert/strict';
import {
  describeBatchState,
  describeControls,
  formatSummary,
  validateLimitsInput,
} from '../../src/list/list-ui.mjs';

test('limits_are_positive_integers', () => {
  assert.deepEqual(validateLimitsInput({ maxExamined: '5', maxSaved: '2' }), {
    ok: true,
    limits: { maxExamined: 5, maxSaved: 2 },
  });
  for (const input of [
    { maxExamined: '0', maxSaved: '1' },
    { maxExamined: '-2', maxSaved: '1' },
    { maxExamined: '1.5', maxSaved: '1' },
    { maxExamined: '', maxSaved: '1' },
    { maxExamined: 'abc', maxSaved: '1' },
  ]) {
    assert.equal(validateLimitsInput(input).ok, false, JSON.stringify(input));
  }
});

test('progress_renders_known_states', () => {
  assert.equal(describeBatchState('RUNNING').label, 'Em execução');
  assert.equal(describeBatchState('PAUSED').label, 'Pausado');
  assert.equal(describeBatchState('SUSPENDED').label, 'Suspenso');
  assert.equal(describeBatchState('COMPLETED').label, 'Concluído');
  assert.equal(describeBatchState('STOPPED').label, 'Parado');
  assert.equal(describeBatchState('SAVE_PENDING').label, 'Salvamento pendente');
});

test('pause_stop_continue_controls', () => {
  assert.deepEqual(describeControls(null), {
    canStart: true, canPause: false, canStop: false, canResume: false,
  });
  assert.deepEqual(describeControls({ state: 'RUNNING', current: null }), {
    canStart: false, canPause: true, canStop: true, canResume: false,
  });
  assert.deepEqual(describeControls({ state: 'PAUSED' }), {
    canStart: false, canPause: false, canStop: true, canResume: true,
  });
  assert.deepEqual(describeControls({ state: 'SUSPENDED', current: { saveAttemptId: 'a1' } }), {
    canStart: false, canPause: false, canStop: false, canResume: true,
  });
  assert.deepEqual(describeControls({ state: 'COMPLETED' }), {
    canStart: true, canPause: false, canStop: false, canResume: false,
  });
});

test('summary_reports_counts_without_personal_data', () => {
  const text = formatSummary({
    state: 'RUNNING',
    captured: 4,
    queueLength: 2,
    examined: 1,
    saved: 1,
    report: {
      totals: {
        captured: 4, skippedCompleted: 1, skippedUnknown: 1, queued: 1,
        examined: 1, saved: 1, confirmed: 1, skipped: 0, review: 0, failed: 0, uncertain: 0,
      },
    },
  });
  assert.equal(text.includes('4 capturados'), true);
  assert.equal(text.includes('1 salvos'), true);
  assert.equal(text.includes('1 pré-concluídos'), true);
  assert.equal(/\d{3}\.\d{3}\.\d{3}-\d{2}/.test(text), false);
});

test('summary_without_batch_is_safe', () => {
  assert.equal(formatSummary(null), 'Nenhum lote ativo.');
});

test('unknown_state_is_labeled', () => {
  assert.equal(describeBatchState('WEIRD').label, 'Estado desconhecido');
  assert.equal(describeBatchState('WEIRD').tone, 'warn');
});
