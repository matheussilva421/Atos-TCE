import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('background_registers_batch_driver', () => {
  const background = readFileSync('src/background/index.mjs', 'utf8');
  assert.equal(background.includes('createBatchDriver'), true);
  assert.equal(background.includes('getBatchDriver'), true);
  assert.equal(background.includes('driver.drive('), true);
  assert.equal(background.includes('BATCH_START'), true);
  assert.equal(background.includes('BATCH_RESUME'), true);
});

test('batch_execution_flag_is_closed', () => {
  const runner = readFileSync('src/background/batch-runner.mjs', 'utf8');
  assert.equal(runner.includes('export const BATCH_EXECUTION_ENABLED = false;'), true);
  assert.equal(runner.includes('saveEnabled = false'), true);
  assert.equal(runner.includes('driveEnabled = BATCH_EXECUTION_ENABLED'), true);
});

test('manifest_does_not_add_alarm_permission', () => {
  const manifest = JSON.parse(readFileSync('extension/manifest.json', 'utf8'));
  assert.deepEqual(manifest.permissions, ['storage']);
});
