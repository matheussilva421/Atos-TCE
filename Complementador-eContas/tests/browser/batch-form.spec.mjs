import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import {
  launchExtension,
  openFormPage,
  startFixtureServer,
  waitForServiceWorker,
} from './harness.mjs';

const PROCESS_ID = '999001';
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

const PROPOSALS = {
  modalidade: {
    status: 'exact',
    value: 'Aposentadoria voluntária por tempo de contribuição com proventos integrais',
    source: 'teste',
  },
  dataDoeEstado: { status: 'exact', value: '07/11/2025', source: 'teste' },
  cargo: { status: 'exact', value: 'ANALISTA DE TESTES', source: 'teste' },
  matricula: { status: 'exact', value: '001234-5/1', source: 'teste' },
  dataNascimento: { status: 'exact', value: '01/02/1980', source: 'teste' },
};

after(async () => {
  if (sharedExtension) {
    await sharedExtension.close().catch(() => {});
    sharedExtension = null;
  }
});

test('batch_form_selects_applies_and_validates', async () => {
  const server = await startFixtureServer();
  let page = null;
  try {
    const extension = await getExtension();
    page = await openFormPage(extension.context, server.origin);
    const worker = await waitForServiceWorker(extension.context);
    const tabId = await worker.evaluate(async (processId) => {
      const tabs = await chrome.tabs.query({});
      for (const tab of tabs) {
        if (!Number.isInteger(tab.id)) continue;
        try {
          const response = await chrome.tabs.sendMessage(tab.id, {
            type: 'BATCH_FORM_SNAPSHOT',
            processId,
          });
          if (response && response.ok) return tab.id;
        } catch {
          // aba sem content script do formulário
        }
      }
      return null;
    }, PROCESS_ID);
    assert.equal(Number.isInteger(tabId), true);

    const selected = await worker.evaluate(
      ({ id, processId }) => chrome.tabs.sendMessage(id, { type: 'BATCH_SELECT_INTERESTED', processId }),
      { id: tabId, processId: PROCESS_ID },
    );
    assert.equal(selected.ok, true, JSON.stringify(selected));
    assert.equal(selected.interestedCount, 1);
    assert.equal(JSON.stringify(selected).includes('PESSOA UM'), false);

    const before = await worker.evaluate(
      ({ id, processId }) => chrome.tabs.sendMessage(id, { type: 'BATCH_VALIDATE_FORM', processId }),
      { id: tabId, processId: PROCESS_ID },
    );
    assert.equal(before.ok, false);
    assert.equal(before.code, 'MISSING_FIELDS');

    const applied = await worker.evaluate(
      ({ id, payload }) => chrome.tabs.sendMessage(id, payload),
      {
        id: tabId,
        payload: {
        type: 'BATCH_APPLY',
        requestId: 'batch-apply-test-1',
        proposals: PROPOSALS,
        expected: { processId: PROCESS_ID, interestedKey: selected.interestedKey },
        },
      },
    );
    assert.equal(applied.ok, true, JSON.stringify(applied));

    const values = await page.evaluate(() => ({
      dataDoeEstado: document.querySelector('tce-input-field[formcontrolname="dataDoeEstado"] input').value,
      cargo: document.querySelector('tce-input-field[formcontrolname="cargo"] input').value,
      matricula: document.querySelector('tce-input-field[formcontrolname="matricula"] input').value,
      dataNascimento: document.querySelector('tce-input-field[formcontrolname="dataNascimento"] input').value,
      modalidade: (document.querySelector('ng-select .ng-value') || {}).textContent || '',
    }));
    assert.equal(values.dataDoeEstado, '07/11/2025');
    assert.equal(values.cargo, 'ANALISTA DE TESTES');
    assert.equal(values.matricula, '001234-5/1');
    assert.equal(values.dataNascimento, '01/02/1980');
    assert.match(values.modalidade, /Aposentadoria voluntária/);

    const afterValidation = await worker.evaluate(
      ({ id, payload }) => chrome.tabs.sendMessage(id, payload),
      {
        id: tabId,
        payload: {
        type: 'BATCH_VALIDATE_FORM',
        processId: PROCESS_ID,
        interestedKey: selected.interestedKey,
        },
      },
    );
    assert.equal(afterValidation.ok, true);

    assert.equal(server.requests.every((request) => request.method === 'GET'), true);
  } finally {
    if (page) {
      await page.close().catch(() => {});
    }
    await server.close();
  }
});
