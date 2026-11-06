import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  BATCH_EXECUTION_ENABLED,
  BATCH_FILL_ONLY,
  BATCH_SAVE_ENABLED,
} from '../../src/background/batch-runner.mjs';


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
  assert.equal(runner.includes("typeof __BATCH_EXECUTION__ === 'boolean'"), true);
  const build = readFileSync('scripts/build.mjs', 'utf8');
  assert.equal(build.includes("process.env.BATCH_EXECUTION === '1'"), true);
  assert.equal(build.includes("process.env.BATCH_FILL_ONLY === '1'"), true);
  assert.equal(build.includes("process.env.BATCH_SAVE === '1'"), true);
  assert.equal(runner.includes('BATCH_SAVE_ENABLED = typeof __BATCH_SAVE__'), true);
  assert.equal(runner.includes('saveEnabled = BATCH_SAVE_ENABLED'), true);
  assert.equal(runner.includes('driveEnabled = BATCH_EXECUTION_ENABLED'), true);
});

test('distribution_build_defaults_keep_drive_fill_and_save_disabled', () => {
  assert.equal(BATCH_EXECUTION_ENABLED, false);
  assert.equal(BATCH_FILL_ONLY, false);
  assert.equal(BATCH_SAVE_ENABLED, false);
});

test('manifest_does_not_add_alarm_permission', () => {
  const manifest = JSON.parse(readFileSync('extension/manifest.json', 'utf8'));
  assert.deepEqual(manifest.permissions, ['storage']);
});

test('background_reenters_by_event_and_suspends_after_restart', () => {
  const background = readFileSync('src/background/index.mjs', 'utf8');
  assert.equal(background.includes('onStartup'), true);
  assert.equal(background.includes('initializeWake'), true);
  assert.equal(background.includes('WAKE_MARKER_KEY'), true);
  assert.equal(background.includes("type: 'SUSPEND'"), true);
  assert.equal(background.includes('await initializeWake();'), true);
  assert.equal(background.includes('void initializeWake();'), true);
});

test('fill_only_structurally_forces_save_off', () => {
  const runner = readFileSync('src/background/batch-runner.mjs', 'utf8');
  assert.equal(runner.includes('BATCH_FILL_ONLY === true ? false : saveEnabled === true'), true);
  assert.equal(runner.includes("enabled: driveEnabled === true || BATCH_FILL_ONLY === true"), true);
});
