import test from 'node:test';
import assert from 'node:assert/strict';
import {
  requestLastDiagnostic,
  renderDiagnostic,
  subscribeDiagnosticUpdates,
} from '../../src/form/diagnostic-ui.mjs';

test('request_last_diagnostic_survives_unavailable_background', async () => {
  const result = await requestLastDiagnostic(async () => { throw new Error('service worker unavailable'); });
  assert.equal(result, null);
});

test('request_last_diagnostic_handles_negative_and_empty_responses', async () => {
  assert.equal(await requestLastDiagnostic(async () => ({ ok: false })), null);
  assert.equal(await requestLastDiagnostic(async () => undefined), null);
  assert.equal(await requestLastDiagnostic(async () => null), null);
});

test('request_last_diagnostic_returns_sanitized_payload', async () => {
  const diagnostic = { state: 'L1_SUCCESS', pagesCount: 1, totalChars: 10 };
  assert.deepEqual(await requestLastDiagnostic(async () => ({ ok: true, diagnostic })), diagnostic);
});

test('render_diagnostic_is_null_safe_and_updates_panel_and_dataset', () => {
  const host = { dataset: {} };
  const element = { textContent: '', style: {} };
  assert.doesNotThrow(() => renderDiagnostic(null, null, null));
  renderDiagnostic(host, element, {
    state: 'L1_SUCCESS',
    pagesCount: 1,
    totalChars: 10,
    elapsedMs: 20,
  });
  assert.match(element.textContent, /L1_SUCCESS/);
  assert.equal(element.style.display, 'block');
  assert.equal(host.dataset.lastDiagnosticState, 'L1_SUCCESS');
  assert.equal(host.dataset.lastDiagnosticPages, '1');
  assert.equal(host.dataset.lastDiagnosticChars, '10');
  assert.equal(host.dataset.lastDiagnosticElapsed, '20');
  renderDiagnostic(host, element, null);
  assert.equal(element.textContent, '');
  assert.equal(host.dataset.lastDiagnosticState, '');
});

test('subscribe_diagnostic_updates_is_safe_without_runtime', () => {
  assert.equal(typeof subscribeDiagnosticUpdates(null, () => {}), 'function');
});

test('subscribe_diagnostic_updates_receives_panel_messages', () => {
  const listeners = new Set();
  const runtime = {
    onMessage: {
      addListener: (listener) => listeners.add(listener),
      removeListener: (listener) => listeners.delete(listener),
    },
  };
  const received = [];
  const unsubscribe = subscribeDiagnosticUpdates(runtime, (value) => received.push(value));
  for (const listener of listeners) {
    listener({ type: 'DIAGNOSTIC_UPDATE', diagnostic: { state: 'L1_SUCCESS' } });
    listener({ type: 'OTHER', diagnostic: { state: 'L1_ERROR' } });
  }
  assert.deepEqual(received, [{ state: 'L1_SUCCESS' }]);
  unsubscribe();
  assert.equal(listeners.size, 0);
});