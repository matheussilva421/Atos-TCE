import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { selectSourceTabs } from '../../src/shared/routes.mjs';
import { createFillPlan } from '../../src/form/form-writer.mjs';

const ORIGIN = 'https://processos.tce.rn.gov.br';
const autos = (id) => ORIGIN + '/#/dashboard/processos/' + id + '/autos';

function walk(dir) {
  if (!existsSync(dir)) {
    return [];
  }
  const result = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      result.push(...walk(full));
    } else {
      result.push(full);
    }
  }
  return result;
}

function sourceFiles() {
  return [...walk('src'), ...walk('scripts'), ...walk('extension')]
    .filter((file) => /.(mjs|js|json)$/.test(file));
}

function readAll(files) {
  return files.map((file) => ({ file, text: readFileSync(file, 'utf8') }));
}

test('manifest_permissions_limited_to_portal', () => {
  const manifest = JSON.parse(readFileSync('extension/manifest.json', 'utf8'));
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions, ['storage']);
  assert.deepEqual(manifest.host_permissions.sort(), [
    'https://novaarearestrita.tce.rn.gov.br/as/consultaprocessotemp/*',
    'https://processos.tce.rn.gov.br/*',
  ]);
  assert.equal(JSON.stringify(manifest).includes('<all_urls>'), false);
  assert.equal(manifest.content_scripts.length, 2);
  for (const script of manifest.content_scripts) {
    assert.deepEqual(script.matches, ['https://processos.tce.rn.gov.br/*']);
  }
  assert.deepEqual(manifest.web_accessible_resources[0].resources, ['vendor/pdf.worker.mjs']);
});

test('no_forbidden_apis_or_persistence', () => {
  const forbidden = [
    'indexedDB',
    'localStorage',
    'sessionStorage',
    'XMLHttpRequest',
    'sendBeacon',
    'new WebSocket',
    'chrome.downloads',
    'chrome.webRequest',
    'chrome.debugger',
    'chrome.cookies',
    'chrome.scripting',
    'document.write',
  ];
  for (const { file, text } of readAll(sourceFiles())) {
    for (const token of forbidden) {
      assert.equal(text.includes(token), false, file + ' contains ' + token);
    }
    assert.equal(/console.(log|info|warn|error)/.test(text), false, file + ' logs to console');
  }
const background = readFileSync('src/background/index.mjs', 'utf8');
  const pdfFetch = readFileSync('src/background/pdf-fetch.mjs', 'utf8');
  assert.equal(background.includes('fetchPdfBytes(fetch,'), true);
  assert.equal(background.includes('fetch('), false);
  assert.equal(pdfFetch.includes('fetchImpl(url'), true);
  assert.equal(pdfFetch.includes('fetch('), false);
});

test('no_submit_commands_or_network_writes', () => {
  for (const { file, text } of readAll(sourceFiles())) {
    assert.equal(text.includes('Complementar ato'), false, file + ' references the final button');
    assert.equal(text.includes('Salvar modalidade'), false, file + ' references save');
    assert.equal(/\.submit\(|requestSubmit|dispatchEvent\(new [A-Za-z]*Event\('submit'/.test(text), false, file + ' may submit');
  }
});

test('no_external_network', () => {
  const allowed = new Set([
    'https://processos.tce.rn.gov.br',
    'https://novaarearestrita.tce.rn.gov.br',
  ]);
  for (const { file, text } of readAll([...walk('src'), ...walk('extension')])) {
    const urls = text.match(/https?:\/\/[^'"\s)]+/g) || [];
    for (const url of urls) {
      const origin = url.split('/').slice(0, 3).join('/');
      assert.equal(allowed.has(origin), true, file + ' references ' + origin);
    }
  }
});

test('no_read_before_click', () => {
  const text = readFileSync('src/autos/content.mjs', 'utf8');
  const listener = text.indexOf('chrome.runtime.onMessage.addListener');
  const reader = text.indexOf('readCurrentDocument(');
  assert.ok(listener >= 0, 'listener missing');
  assert.ok(reader > listener, 'reader must be called only inside the message handler');
  assert.equal(text.includes('MutationObserver'), false);
  assert.equal(text.includes('setInterval'), false);
  assert.equal(text.includes('fetch('), false);
});

test('cross_process_refused_and_two_source_tabs_are_ambiguous', () => {
  assert.equal(selectSourceTabs([{ id: 1, url: autos('999002') }], '999001').code, 'SOURCE_NOT_FOUND');
  assert.equal(selectSourceTabs([{ id: 1, url: autos('999001') }, { id: 2, url: autos('999001') }], '999001').code, 'SOURCE_AMBIGUOUS');
});

test('readonly_preserved_in_plan', () => {
  const form = {
    processId: '999001',
    interestedKey: 'abcd1234',
    values: { dataDoeEstado: '', cargo: '', matricula: '000001-2', dataNascimento: '' },
    editable: { dataDoeEstado: true, cargo: true, matricula: false, dataNascimento: true },
    maxlength: { dataDoeEstado: null, cargo: 50, matricula: 20, dataNascimento: null },
    modalities: [{ id: 'm1', label: 'Reforma', disabled: false }],
    modalitySelected: false,
  };
  const plan = createFillPlan({
    modalidade: { status: 'exact', value: 'Reforma' },
    dataDoeEstado: { status: 'exact', value: '07/11/2025' },
    cargo: { status: 'exact', value: 'ANALISTA DE TESTES' },
    matricula: { status: 'exact', value: '001234-5/1' },
    dataNascimento: { status: 'exact', value: '01/02/1980' },
  }, form);
  assert.equal(plan.fields.matricula.action, 'preserve');
  assert.equal(plan.fields.matricula.reason, 'READONLY');
});

test('no_personal_data_persisted_in_sources_or_docs', () => {
  const allowed = new Set(['000.000.000-00', '111.111.111-11']);
  for (const { file, text } of readAll([...sourceFiles(), ...walk('docs')])) {
    const cpfs = text.match(/\b\d{3}\.\d{3}\.\d{3}-\d{2}\b/g) || [];
    for (const cpf of cpfs) {
      assert.equal(allowed.has(cpf), true, file + ' contains an unexpected CPF-like identifier');
    }
  }
});

test('build_has_manifest_and_scripts', () => {
  const manifestPath = path.join('dist', 'manifest.json');
  if (!existsSync(manifestPath)) {
    return;
  }
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  assert.equal(manifest.version, '0.1.1');
  for (const file of ['background.js', 'form-content.js', 'autos-content.js', 'vendor/pdf.worker.mjs']) {
    assert.equal(existsSync(path.join('dist', file)), true, 'missing ' + file);
  }
  assert.deepEqual(manifest.host_permissions.sort(), [
    'https://novaarearestrita.tce.rn.gov.br/as/consultaprocessotemp/*',
    'https://processos.tce.rn.gov.br/*',
  ]);
  const files = walk('dist');
  assert.equal(files.some((file) => file.endsWith('.pdf')), false);
  assert.equal(files.some((file) => file.endsWith('.har')), false);
  assert.equal(files.some((file) => file.endsWith('.png')), false);
});

test('package_has_no_personal_data', () => {
  if (!existsSync('dist')) {
    return;
  }
  const allowed = new Set(['000.000.000-00', '111.111.111-11']);
  for (const file of walk('dist')) {
    const text = readFileSync(file, 'latin1');
    const cpfs = text.match(/\b\d{3}\.\d{3}\.\d{3}-\d{2}\b/g) || [];
    for (const cpf of cpfs) {
      assert.equal(allowed.has(cpf), true, file + ' contains an unexpected CPF-like identifier');
    }
  }
});
test('diagnostic_path_cannot_call_fill_or_submit', () => {
  const form = readFileSync('src/form/content.mjs', 'utf8');
  const formStart = form.indexOf('async function onDiagnose');
  const formEnd = form.indexOf('async function handleApplyPlan');
  assert.ok(formStart >= 0 && formEnd > formStart, 'diagnostic function boundaries missing');
  const formBody = form.slice(formStart, formEnd);
  for (const token of ['applyFillPlan', 'setNativeValue', 'createFillPlan', '.submit(', 'requestSubmit', 'Complementar ato', 'Salvar']) {
    assert.equal(formBody.includes(token), false, 'diagnostic form path contains ' + token);
  }

  const background = readFileSync('src/background/index.mjs', 'utf8');
  const bgStart = background.indexOf('async function handleDiagnoseDocument');
  const bgEnd = background.indexOf('async function handleFetchPdf');
  assert.ok(bgStart >= 0 && bgEnd > bgStart, 'diagnostic background boundaries missing');
  const bgBody = background.slice(bgStart, bgEnd);
  for (const token of ['extractFields', 'runFillTransaction', 'createFillPlan', 'applyFillPlan']) {
    assert.equal(bgBody.includes(token), false, 'diagnostic background path contains ' + token);
  }
});
test('diagnostic_recovery_is_session_scoped', () => {
  const background = readFileSync('src/background/index.mjs', 'utf8');
  const form = readFileSync('src/form/content.mjs', 'utf8');
  const bridge = readFileSync('src/form/diagnostic-ui.mjs', 'utf8');
  assert.equal(background.includes('chrome.storage.session'), true);
  assert.equal(background.includes('GET_DIAGNOSTIC'), true);
  assert.equal(background.includes('chrome.storage.local'), false);
  assert.equal(background.includes('chrome.storage.sync'), false);
  assert.equal(form.includes('chrome.storage'), false);
  assert.equal(bridge.includes('chrome.storage'), false);
  assert.equal(bridge.includes('GET_DIAGNOSTIC'), true);
});