import test from 'node:test';
import assert from 'node:assert/strict';
import { createDriveTracker } from '../../src/batch/runtime-state.mjs';

test('records_only_sanitized_drive_fields', () => {
  const tracker = createDriveTracker(() => 123);
  tracker.record({ state: 'SUSPENDED', steps: 4, interestedName: 'FULANO', cpf: '123' });
  assert.deepEqual(tracker.read(), { state: 'SUSPENDED', steps: 4, at: 123 });
});

test('records_drive_error_code', () => {
  const tracker = createDriveTracker(() => 456);
  const error = new Error('x');
  error.code = 'WRONG_PROCESS_TAB';
  tracker.fail(error);
  assert.deepEqual(tracker.read(), { state: 'ERROR', steps: 0, code: 'WRONG_PROCESS_TAB', at: 456 });
});

test('read_returns_copy_and_handles_empty', () => {
  const tracker = createDriveTracker(() => 1);
  assert.equal(tracker.read(), null);
  tracker.record({ state: 'IDLE' });
  const value = tracker.read();
  value.state = 'mutated';
  assert.equal(tracker.read().state, 'IDLE');
});
