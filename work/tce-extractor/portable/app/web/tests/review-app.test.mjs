import test from 'node:test';
import assert from 'node:assert/strict';
import { installReviewAppModule, resolveDocument, setSelection } from '../review-app.js';

test('same event number does not select another document', () => {
  const docs = [{ id: 'a', event: 9 }, { id: 'b', event: 9 }];
  assert.equal(resolveDocument(docs, 'b').id, 'b');
});

test('manual selection pauses portal follow without mutating field values', () => {
  const state = { followPortal: true, processKey: 'old', interestedNormalized: 'OLD' };
  const selected = setSelection(state, {
    processKey: '103439/2023',
    interestedNormalized: 'joana da silva',
  });
  assert.equal(selected.followPortal, false);
  assert.equal(selected.processKey, '103439/2023');
  assert.equal(selected.interestedNormalized, 'joana da silva');
  assert.equal('fields' in selected, false);
});

test('served document installs the shared review module state', () => {
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  const body = { setAttribute: (name, value) => { body[name] = value; } };
  globalThis.document = {
    body,
    getElementById: () => ({ textContent: JSON.stringify({ processes: [] }) }),
  };
  globalThis.window = {};
  try {
    const app = installReviewAppModule(globalThis.document);
    assert.ok(app);
    assert.equal(body['data-review-module'], 'review-app');
    assert.equal(globalThis.window.TceReviewApp, app);
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
  }
});
