import test from 'node:test';
import assert from 'node:assert/strict';
import { parseRoute, sameProcess, selectSourceTabs } from '../../src/shared/routes.mjs';

const ORIGIN = 'https://processos.tce.rn.gov.br';
const autos = (id = '999001', extra = '') => ORIGIN + '/#/dashboard/processos/' + id + '/autos' + extra;
const complemento = (id = '999001') => ORIGIN + '/#/dashboard/complementar-ato/' + id;

test('parse_route_autos_and_complemento', () => {
  assert.deepEqual(parseRoute(autos()), { kind: 'autos', idProcesso: '999001' });
  assert.deepEqual(parseRoute(complemento()), { kind: 'complemento', idProcesso: '999001' });
  assert.deepEqual(parseRoute(autos('999001', '?esconderHeaderSideBar=true')), { kind: 'autos', idProcesso: '999001' });
});

test('reject_foreign_origin', () => {
  assert.equal(parseRoute('https://evil.example/#/dashboard/complementar-ato/999001'), null);
  assert.equal(parseRoute('http://processos.tce.rn.gov.br/#/dashboard/complementar-ato/999001'), null);
  assert.equal(parseRoute('https://processos.tce.rn.gov.br/#/dashboard/complementar-ato/abc'), null);
  assert.equal(parseRoute('not a url'), null);
});

test('two_source_tabs_are_ambiguous', () => {
  const result = selectSourceTabs([
    { id: 1, url: autos(), windowId: 10 },
    { id: 2, url: autos(), windowId: 11 },
  ], '999001');
  assert.equal(result.ok, false);
  assert.equal(result.code, 'SOURCE_AMBIGUOUS');
});

test('different_process_is_rejected', () => {
  const result = selectSourceTabs([{ id: 1, url: autos('999002') }], '999001');
  assert.equal(result.ok, false);
  assert.equal(result.code, 'SOURCE_NOT_FOUND');
});

test('cross_window_same_profile_resolves', () => {
  const result = selectSourceTabs([
    { id: 1, url: autos(), windowId: 10 },
    { id: 2, url: autos('999002'), windowId: 11 },
  ], '999001');
  assert.equal(result.ok, true);
  assert.equal(result.tabId, 1);
});

test('no_pdf_read_on_route_detection', () => {
  let reads = 0;
  globalThis.fetch = async () => { reads += 1; throw new Error('fetch must not be called'); };
  parseRoute(autos());
  parseRoute(complemento());
  selectSourceTabs([{ id: 1, url: autos() }], '999001');
  assert.equal(reads, 0);
});

test('same_process_requires_both_routes', () => {
  assert.equal(sameProcess(parseRoute(autos()), parseRoute(complemento())), true);
  assert.equal(sameProcess(parseRoute(autos('999001')), parseRoute(complemento('999002'))), false);
  assert.equal(sameProcess(null, parseRoute(complemento())), false);
});