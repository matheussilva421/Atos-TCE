import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { launchExtension, startFixtureServer, waitForServiceWorker } from './harness.mjs';

const LIST_PATH = '/lista-filtros#/dashboard/processos-no-setor/no-setor';
let sharedExtension = null;

async function getExtension() {
  if (!sharedExtension) {
    sharedExtension = await launchExtension();
    const keepalive = await sharedExtension.context.newPage();
    await keepalive.goto('about:blank');
    sharedExtension.keepalive = keepalive;
  }
  return sharedExtension;
}

after(async () => {
  if (sharedExtension) {
    await sharedExtension.close().catch(() => {});
    sharedExtension = null;
  }
});

test('saved_filters_are_applied_and_searched_automatically', async () => {
  const server = await startFixtureServer();
  let page = null;
  try {
    const extension = await getExtension();
    const worker = await waitForServiceWorker(extension.context);
    await worker.evaluate(async (preset) => {
      await chrome.storage.local.set({ complementadorFilterPreset: preset });
    }, {
      selects: [{ name: 'idMarcador', value: 'Mutirão - Educação' }],
      checkboxes: [{ name: 'ProcessosNoSetor', checked: true }],
    });
    page = await extension.context.newPage();
    await page.goto(server.origin + LIST_PATH, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(document.querySelector('#complementador-econtas-batch-root')), null, { timeout: 20000 });
    await page.waitForFunction(() => window.__searches >= 1, null, { timeout: 20000 });
    const state = await page.evaluate(() => {
      const label = document.querySelector('tce-select-field[formcontrolname="idMarcador"] .ng-value-label');
      const checkbox = document.querySelector('tce-checkbox-field[formcontrolname="ProcessosNoSetor"] input');
      return {
        marker: label ? label.textContent.trim() : '',
        checked: checkbox ? checkbox.checked : null,
        searches: window.__searches,
      };
    });
    assert.match(state.marker, /Mutirão - Educação/);
    assert.equal(state.checked, true);
    assert.equal(state.searches, 1);
    assert.equal(server.requests.every((request) => request.method === 'GET'), true);
  } finally {
    if (page) {
      await page.close().catch(() => {});
    }
    await server.close();
  }
});

test('batch_panel_appears_on_meus_processos_route', async () => {
  const server = await startFixtureServer();
  let page = null;
  try {
    const extension = await getExtension();
    page = await extension.context.newPage();
    await page.goto(server.origin + '/lista-filtros#/dashboard/meus/meus-processos?ProcessosFinalisticosNoSetor=true&setor=CBP', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(
      document.querySelector('#complementador-econtas-batch-root')?.shadowRoot?.querySelector('button[data-action="preview"]'),
    ), null, { timeout: 20000 });
    const state = await page.evaluate(() => ({
      rows: document.querySelectorAll('#tabela-processos-consulta-id tbody tr').length,
      panel: Boolean(document.querySelector('#complementador-econtas-batch-root')),
    }));
    assert.equal(state.panel, true);
    assert.equal(state.rows > 0, true);
    assert.equal(server.requests.every((request) => request.method === 'GET'), true);
  } finally {
    if (page) await page.close().catch(() => {});
    await server.close();
  }
});
