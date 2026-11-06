import test from 'node:test';
import assert from 'node:assert/strict';
import { decideWake } from '../../src/batch/lifecycle.mjs';

const RUNTIME = 'extension-id';

function batch(overrides = {}) {
  return {
    batchId: 'batch-wake',
    state: 'RUNNING',
    current: null,
    ...overrides,
  };
}

test('no_batch_is_idle', () => {
  assert.equal(decideWake({ batch: null, sessionMarker: null, runtimeId: RUNTIME }).action, 'idle');
});

test('terminal_batch_is_noop', () => {
  for (const state of ['COMPLETED', 'STOPPED']) {
    assert.equal(decideWake({ batch: batch({ state }), sessionMarker: null, runtimeId: RUNTIME }).action, 'noop');
  }
});

test('missing_session_marker_means_browser_restart_and_suspends', () => {
  const result = decideWake({ batch: batch(), sessionMarker: null, runtimeId: RUNTIME });
  assert.equal(result.action, 'suspend');
  assert.equal(result.reason, 'browser_restart');
});

test('marker_from_another_extension_runtime_suspends', () => {
  const result = decideWake({
    batch: batch(),
    sessionMarker: { runtimeId: 'older-extension', at: 1 },
    runtimeId: RUNTIME,
  });
  assert.equal(result.action, 'suspend');
});

test('normal_worker_wake_drives_running_batch', () => {
  const result = decideWake({
    batch: batch(),
    sessionMarker: { runtimeId: RUNTIME, at: 10 },
    runtimeId: RUNTIME,
  });
  assert.equal(result.action, 'drive');
  assert.equal(result.reason, 'normal_worker_wake');
});

test('save_pending_normal_wake_is_reconciliation_only', () => {
  const result = decideWake({
    batch: batch({
      current: { processId: '301', phase: 'SAVE_PENDING', saveAttemptId: 'attempt-1' },
    }),
    sessionMarker: { runtimeId: RUNTIME, at: 10 },
    runtimeId: RUNTIME,
  });
  assert.equal(result.action, 'drive');
  assert.equal(result.reason, 'save_reconciliation');
});

test('paused_and_suspended_batches_do_not_auto_resume', () => {
  for (const state of ['PAUSED', 'SUSPENDED', 'PAUSE_REQUESTED', 'STOP_REQUESTED']) {
    const result = decideWake({
      batch: batch({ state }),
      sessionMarker: { runtimeId: RUNTIME, at: 10 },
      runtimeId: RUNTIME,
    });
    assert.equal(result.action, 'noop');
  }
});
