import test from 'node:test';
import assert from 'node:assert/strict';
import { makePdf } from '../helpers/make-pdf.mjs';
import { fetchPdfBytes } from '../../src/background/pdf-fetch.mjs';

function makeResponse(options = {}) {
  const headers = new Map();
  if (options.contentType) headers.set('content-type', options.contentType);
  if (options.contentLength !== undefined) headers.set('content-length', String(options.contentLength));
  const body = options.body;
  return {
    ok: options.ok !== false,
    status: options.status || (options.ok === false ? 403 : 200),
    headers: { get: (name) => headers.get(String(name).toLowerCase()) || null },
    body: body && typeof body.getReader === 'function' ? body : undefined,
    arrayBuffer: async () => {
      if (!body) return new ArrayBuffer(0);
      if (body instanceof Uint8Array) return body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength);
      throw new Error('arrayBuffer unavailable');
    },
  };
}

function streamOf(chunks) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
}

const fetchReturning = (response) => async () => response;

test('valid_pdf_is_returned_as_base64', async () => {
  const pdf = makePdf(['PESSOA UM']);
  const result = await fetchPdfBytes(fetchReturning(makeResponse({
    contentType: 'application/pdf',
    body: pdf,
    contentLength: pdf.length,
  })), 'https://pdf.invalid/current.pdf', { maxBytes: 1024 * 1024 });
  assert.equal(result.ok, true);
  assert.equal(result.byteLength, pdf.length);
  assert.match(result.base64, /^JVBER/);
});

test('http_401_and_403_fail_closed', async () => {
  for (const status of [401, 403]) {
    const result = await fetchPdfBytes(fetchReturning(makeResponse({ ok: false, status })), 'https://pdf.invalid/current.pdf');
    assert.equal(result.ok, false);
    assert.equal(result.code, 'PDF_FETCH_FAILED');
  }
});

test('redirect_or_network_error_fails_closed', async () => {
  const result = await fetchPdfBytes(async () => { throw new TypeError('redirect blocked'); }, 'https://pdf.invalid/current.pdf');
  assert.equal(result.ok, false);
  assert.equal(result.code, 'PDF_FETCH_FAILED');
});

test('html_200_is_not_a_pdf', async () => {
  const html = new Uint8Array(Buffer.from('<html>login</html>'));
  const result = await fetchPdfBytes(fetchReturning(makeResponse({
    contentType: 'text/html',
    body: html,
    contentLength: html.length,
  })), 'https://pdf.invalid/current.pdf');
  assert.equal(result.ok, false);
  assert.equal(result.code, 'DOCUMENT_NOT_READABLE');
});

test('pdf_content_type_with_non_pdf_bytes_is_rejected', async () => {
  const html = new Uint8Array(Buffer.from('<html>login</html>'));
  const result = await fetchPdfBytes(fetchReturning(makeResponse({
    contentType: 'application/pdf',
    body: html,
    contentLength: html.length,
  })), 'https://pdf.invalid/current.pdf');
  assert.equal(result.ok, false);
  assert.equal(result.code, 'DOCUMENT_NOT_READABLE');
});

test('declared_content_length_above_limit_is_rejected', async () => {
  const pdf = makePdf(['PESSOA UM']);
  const result = await fetchPdfBytes(fetchReturning(makeResponse({
    contentType: 'application/pdf',
    body: pdf,
    contentLength: 1025,
  })), 'https://pdf.invalid/current.pdf', { maxBytes: 1024 });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'DOCUMENT_TOO_LARGE');
});

test('streamed_body_above_limit_is_rejected_without_content_length', async () => {
  const result = await fetchPdfBytes(fetchReturning(makeResponse({
    contentType: 'application/pdf',
    body: streamOf([new Uint8Array(800), new Uint8Array(800)]),
  })), 'https://pdf.invalid/current.pdf', { maxBytes: 1024 });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'DOCUMENT_TOO_LARGE');
});

test('valid_pdf_without_content_length_uses_streaming', async () => {
  const pdf = makePdf(['PESSOA UM']);
  const result = await fetchPdfBytes(fetchReturning(makeResponse({
    contentType: 'application/pdf; charset=binary',
    body: streamOf([pdf.subarray(0, 10), pdf.subarray(10)]),
  })), 'https://pdf.invalid/current.pdf', { maxBytes: 1024 * 1024 });
  assert.equal(result.ok, true);
  assert.equal(result.byteLength, pdf.length);
});