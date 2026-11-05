import test from 'node:test';
import assert from 'node:assert/strict';
import { createFrozenBatch } from '../../src/batch/queue.mjs';
import { classifyRecovery } from '../../src/batch/recovery.mjs';

function batch(overrides = {}) {
  const base = createFrozenBatch({
    batchId: 'batch-rec',
    listTabId: 21,
    contextKey: 'ctx-1',
    entries: [{ processId: '901', processLabel: '901/2020', status: 'pending' }],
    limits: { maxExamined: 1, maxSaved: 1 },
    startedAt: 10,
  });
  return { ...base, state: 'RUNNING', ...overrides };
}

const HEALTHY = { sessionOk: true, tabOk: true, listContextKey: 'ctx-1', browserRestart: false };

test('batch_context_change_pauses', () => {
  const result = classifyRecovery(batch(), { ...HEALTHY, listContextKey: 'ctx-2' });
  assert.equal(result.action, 'pause');
  assert.equal(result.reason, 'filter_changed');
});

test('session_expired_requires_human_login', () => {
  const result = classifyRecovery(batch(), { ...HEALTHY, sessionOk: false });
  assert.equal(result.action, 'pause');
  assert.equal(result.reason, 'session_expired');
});

test('relogin_does_not_auto_resume', () => {
  const paused = batch({ state: 'PAUSED' });
  const result = classifyRecovery(paused, { ...HEALTHY, sessionOk: true });
  assert.equal(result.action, 'pause');
  assert.equal(result.reason, 'resume_not_authorized');
  const resumed = classifyRecovery(paused, { ...HEALTHY, sessionOk: true, resumeRequested: true });
  assert.equal(resumed.action, 'resume');
});

test('browser_restart_requires_continue', () => {
  const result = classifyRecovery(batch(), { ...HEALTHY, browserRestart: true });
  assert.equal(result.action, 'pause');
  assert.equal(result.reason, 'browser_restart');
  const confirmed = classifyRecovery(batch(), { ...HEALTHY, browserRestart: true, resumeRequested: true });
  assert.equal(confirmed.action, 'resume');
  assert.equal(confirmed.reason, 'browser_restart_confirmed');
});

test('normal_worker_wake_can_resume_safe_step', () => {
  const result = classifyRecovery(batch(), { ...HEALTHY, workerWake: true });
  assert.equal(result.action, 'resume');
  assert.equal(result.reason, 'normal_worker_wake');
});

test('uncertain_save_survives_restart', () => {
  const uncertain = batch({
    state: 'SUSPENDED',
    current: { processId: '901', phase: 'SAVE_UNCERTAIN', saveAttemptId: 'attempt-901' },
    queue: [{ processId: '901', processLabel: '901/2020', status: 'SAVE_UNCERTAIN' }],
  });
  for (const observation of [
    { ...HEALTHY, browserRestart: true },
    { ...HEALTHY, browserRestart: true, resumeRequested: true, workerWake: true },
  ]) {
    const result = classifyRecovery(uncertain, observation);
    assert.equal(result.action, 'suspend');
    assert.equal(result.reason, 'save_uncertain');
  }
});

test('no_wrong_tab_resume', () => {
  const result = classifyRecovery(batch({ state: 'PAUSED' }), { ...HEALTHY, tabOk: false, resumeRequested: true });
  assert.equal(result.action, 'pause');
  assert.equal(result.reason, 'tab_changed');
});

test('terminal_batches_complete', () => {
  assert.equal(classifyRecovery(batch({ state: 'COMPLETED' }), HEALTHY).action, 'complete');
  assert.equal(classifyRecovery(batch({ state: 'STOPPED' }), HEALTHY).action, 'complete');
});
