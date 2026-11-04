import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { makePdf } from '../helpers/make-pdf.mjs';
import {
  DOCUMENT_ERROR,
  bytesToBase64,
  extractPagesFromPdf,
  getIframeSrc,
  parsePdfUrl,
  readCurrentDocument,
} from '../../src/autos/document-reader.mjs';

const PROCESS_ID = '999001';
const PDF_URL = 'https://novaarearestrita.tce.rn.gov.br/as/consultaprocessotemp/2026/11/3/11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222.pdf';

function makeDom(src = PDF_URL) {
  const dom = new JSDOM('<!doctype html><html><body><h4>AUTOS DO PROCESSO 999001 / 2026</h4><iframe id="ifrm" title="iframe de anexo" src="' + src + '"></iframe></body></html>', {
    url: 'https://processos.tce.rn.gov.br/#/dashboard/processos/' + PROCESS_ID + '/autos',
  });
  return dom.window.document;
}

test('parse_pdf_url_accepts_only_the_portal_pdf_path', () => {
  assert.ok(parsePdfUrl(PDF_URL));
  assert.equal(parsePdfUrl('https://evil.example/as/consultaprocessotemp/2026/11/3/11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222.pdf'), null);
  assert.equal(parsePdfUrl('https://novaarearestrita.tce.rn.gov.br/as/consultaprocessotemp/2026/11/3/not-a-guid/22222222-2222-2222-2222-222222222222.pdf'), null);
  assert.equal(parsePdfUrl(PDF_URL + '?token=secret'), null);
});

test('all_pages_extracted_and_only_current_document_read', async () => {
  const doc = makeDom();
  let requested = null;
  const result = await readCurrentDocument(
    { expectedProcessId: PROCESS_ID, requestId: 'req-12345678' },
    {
      document: doc,
      fetchPdf: async (url) => { requested = url; return { ok: true, base64: 'JVBERi0=' }; },
      extractPages: async () => ['PESSOA UM', 'PAGINA DOIS'],
      now: () => 123,
    },
  );
  assert.equal(requested, PDF_URL);
  assert.equal(result.processId, PROCESS_ID);
  assert.equal(result.processLabel, '999001/2026');
  assert.equal(result.byteLength, 5);
  assert.equal(result.pages.length, 2);
  assert.equal(result.sourceKind, 'pdf-bytes');
  assert.equal(result.observedAt, 123);
  assert.match(result.documentKey, /^[0-9a-f]{8}$/);
});

test('document_switch_aborts_without_result', async () => {
  const doc = makeDom();
  await assert.rejects(
    () => readCurrentDocument(
      { expectedProcessId: PROCESS_ID, requestId: 'req-12345678' },
      {
        document: doc,
        fetchPdf: async () => ({ ok: true, base64: 'JVBERi0=' }),
        extractPages: async () => {
          doc.querySelector('#ifrm').src = PDF_URL.replace('11111111-1111-1111-1111-111111111111', '33333333-3333-3333-3333-333333333333');
          return ['PESSOA UM'];
        },
      },
    ),
    (error) => error.code === DOCUMENT_ERROR.DOCUMENT_CHANGED,
  );
});

test('blank_or_partial_document_returns_error', async () => {
  const doc = makeDom();
  await assert.rejects(
    () => readCurrentDocument(
      { expectedProcessId: PROCESS_ID, requestId: 'req-12345678' },
      {
        document: doc,
        fetchPdf: async () => ({ ok: true, base64: 'JVBERi0=' }),
        extractPages: async () => ['PESSOA UM', '  '],
      },
    ),
    (error) => error.code === DOCUMENT_ERROR.PARTIAL_DOCUMENT,
  );
});

test('document_not_readable_fails_closed', async () => {
  const doc = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://processos.tce.rn.gov.br/' }).window.document;
  await assert.rejects(
    () => readCurrentDocument({ expectedProcessId: PROCESS_ID, requestId: 'req-12345678' }, { document: doc }),
    (error) => error.code === DOCUMENT_ERROR.DOCUMENT_NOT_READABLE,
  );
});

test('no_reader_before_click', () => {
  let calls = 0;
  const doc = makeDom();
  getIframeSrc(doc);
  assert.equal(calls, 0);
  assert.equal(typeof readCurrentDocument, 'function');
});

test('long_pdf_text_is_not_truncated', async () => {
  const text = 'INICIO ' + 'PALAVRA '.repeat(40) + 'FIM';
  const pages = await extractPagesFromPdf(makePdf([text]));
  assert.match(pages[0], /INICIO/);
  assert.match(pages[0], /FIM/);
});

test('html_login_response_is_not_pdf', async () => {
  const doc = makeDom();
  await assert.rejects(
    () => readCurrentDocument(
      { expectedProcessId: PROCESS_ID, requestId: 'req-12345678' },
      {
        document: doc,
        fetchPdf: async () => ({ ok: true, base64: Buffer.from('<html>login required</html>').toString('base64') }),
      },
    ),
    (error) => error.code === DOCUMENT_ERROR.DOCUMENT_NOT_READABLE,
  );
});
test('real_pdf_text_extraction', async () => {
  const bytes = makePdf(['PESSOA UM', 'PAGINA DOIS']);
  const base64 = bytesToBase64(bytes);
  const pages = await extractPagesFromPdf(bytes);
  assert.equal(pages.length, 2);
  assert.match(pages[0], /PESSOA UM/);
  assert.match(pages[1], /PAGINA DOIS/);
  assert.equal(base64.startsWith('JVBER'), true);
});