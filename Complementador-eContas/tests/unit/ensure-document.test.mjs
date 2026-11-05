import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { currentDocumentSrc, ensureDocumentOpen } from '../../src/autos/ensure-document.mjs';

function document(body) {
  return new JSDOM('<html><body>' + body + '</body></html>').window.document;
}

test('reports_existing_document_without_clicking', async () => {
  const doc = document('<iframe id="ifrm" src="/doc.pdf"></iframe><div class="card-event"></div>');
  let clicks = 0;
  doc.querySelector('.card-event').addEventListener('click', () => { clicks += 1; });
  const result = await ensureDocumentOpen(doc, { sleep: async () => {} });
  assert.equal(result.ok, true);
  assert.equal(result.alreadyOpen, true);
  assert.equal(clicks, 0);
  assert.equal(currentDocumentSrc(doc), '/doc.pdf');
});

test('selects_first_event_when_nothing_is_open', async () => {
  const doc = document('<iframe id="ifrm" src=""></iframe>'
    + '<div class="card-event" data-pdf="/one.pdf"></div>'
    + '<div class="card-event" data-pdf="/two.pdf"></div>');
  doc.querySelector('.card-event').addEventListener('click', (event) => {
    doc.querySelector('#ifrm').setAttribute('src', event.currentTarget.dataset.pdf);
  });
  const result = await ensureDocumentOpen(doc, { sleep: async () => {}, pollMs: 1 });
  assert.equal(result.ok, true);
  assert.equal(result.alreadyOpen, false);
  assert.equal(currentDocumentSrc(doc), '/one.pdf');
});

test('fails_closed_without_cards', async () => {
  const doc = document('<iframe id="ifrm" src=""></iframe>');
  const result = await ensureDocumentOpen(doc, { sleep: async () => {}, timeoutMs: 5, pollMs: 1 });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'NO_EVENT_CARD');
});

test('fails_closed_when_iframe_never_loads', async () => {
  const doc = document('<iframe id="ifrm" src=""></iframe><div class="card-event"></div>');
  const result = await ensureDocumentOpen(doc, {
    sleep: async () => {},
    timeoutMs: 5,
    pollMs: 1,
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'NO_DOCUMENT');
});
