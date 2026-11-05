import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import {
  PROCESS_ID,
  launchExtension,
  openAutosPage,
  startFixtureServer,
  waitForServiceWorker,
} from './harness.mjs';

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

test('autos_content_responds_to_ensure_document', async () => {
  const server = await startFixtureServer({ scanEvents: true });
  let page = null;
  try {
    const extension = await getExtension();
    page = await openAutosPage(extension.context, server.origin, PROCESS_ID);
    const worker = await waitForServiceWorker(extension.context);
    const response = await worker.evaluate(async (processId) => {
      const tabs = await chrome.tabs.query({});
      for (const tab of tabs) {
        if (!Number.isInteger(tab.id)) continue;
        try {
          const result = await chrome.tabs.sendMessage(tab.id, {
            type: 'BATCH_ENSURE_DOCUMENT',
            expectedProcessId: processId,
          });
          if (result !== undefined && result !== null) return result;
        } catch {
          // aba sem o content script de Autos
        }
      }
      return { ok: false, code: 'NO_RESPONSE' };
    }, PROCESS_ID);
    assert.equal(response.ok, true, JSON.stringify(response));
    assert.equal(response.alreadyOpen, true);
    assert.equal(server.requests.every((request) => request.method === 'GET'), true);
  } finally {
    if (page) {
      await page.close().catch(() => {});
    }
    await server.close();
  }
});
