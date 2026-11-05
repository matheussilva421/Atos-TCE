import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { readListContext, readVisibleList } from '../../src/list/list-reader.mjs';
import { parseListRoute } from '../../src/shared/routes.mjs';

const LIST_URL = 'https://processos.tce.rn.gov.br/#/dashboard/processos-no-setor/no-setor';

async function load(url = LIST_URL) {
  const html = await readFile(new URL('../fixtures/batch/list.html', import.meta.url), 'utf8');
  return new JSDOM(html, { url }).window.document;
}

test('batch_list_excludes_hidden_and_duplicates', async () => {
  const document = await load();
  const snapshot = readVisibleList(document);
  assert.equal(snapshot.ok, true);
  assert.deepEqual(snapshot.entries.map((entry) => entry.processId), ['501', '502', '503']);
  assert.equal(snapshot.entries.filter((entry) => entry.processId === '501').length, 1);
  assert.equal(snapshot.entries.some((entry) => entry.processId === '504'), false);
  assert.equal(snapshot.entries.some((entry) => entry.processId === '505'), false);
});

test('completed_and_unknown_are_distinct', async () => {
  const document = await load();
  const snapshot = readVisibleList(document);
  const byId = Object.fromEntries(snapshot.entries.map((entry) => [entry.processId, entry.status]));
  assert.equal(byId['501'], 'pending');
  assert.equal(byId['502'], 'completed');
  assert.equal(byId['503'], 'unknown');
});

test('only_current_page_is_captured', async () => {
  const document = await load();
  const snapshot = readVisibleList(document);
  assert.equal(snapshot.entries.length, 3);
  assert.equal(snapshot.entries.every((entry) => entry.processId.length <= 12), true);
  assert.equal(snapshot.hasPagination, true);
});

test('list_route_requires_verified_pattern', () => {
  assert.deepEqual(parseListRoute(LIST_URL), { kind: 'list' });
  assert.equal(parseListRoute('https://processos.tce.rn.gov.br/#/dashboard/processos/501/autos'), null);
  assert.equal(parseListRoute('https://processos.tce.rn.gov.br/#/dashboard/complementar-ato/501'), null);
  assert.equal(parseListRoute('https://evil.invalid/#/dashboard/processos-no-setor/no-setor'), null);
  assert.equal(parseListRoute('https://processos.tce.rn.gov.br/#/dashboard/outra-rota'), null);
});

test('empty_list_fails_closed', async () => {
  const empty = new JSDOM(
    '<tce-table id="tabela-processos-consulta-id"><table><tbody></tbody></table></tce-table>',
    { url: LIST_URL },
  ).window.document;
  const snapshot = readVisibleList(empty);
  assert.equal(snapshot.ok, false);
  assert.equal(snapshot.code, 'EMPTY_LIST');
  assert.deepEqual(snapshot.entries, []);
  assert.equal(readListContext(empty), null);
});

test('non_list_document_is_rejected', async () => {
  const document = await load('https://processos.tce.rn.gov.br/#/dashboard/processos/501/autos');
  const snapshot = readVisibleList(document);
  assert.equal(snapshot.ok, false);
  assert.equal(snapshot.code, 'NOT_LIST_ROUTE');
  assert.equal(readListContext(document), null);
});

test('context_fingerprint_tracks_filters_only', async () => {
  const document = await load();
  const first = readListContext(document);
  assert.equal(typeof first, 'string');
  assert.equal(first.length > 0, true);
  const marker = document.querySelector('tce-select-field[formcontrolname="idMarcador"] .ng-value-label');
  marker.textContent = 'Outro marcador';
  const second = readListContext(document);
  assert.notEqual(second, first);
  assert.equal(JSON.stringify(second).includes('Mutirão'), false);
});
