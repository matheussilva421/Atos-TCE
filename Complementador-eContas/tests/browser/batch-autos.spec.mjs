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

test('two_autos_tabs_do_not_cross_process', async () => {
  const server = await startFixtureServer({ scanEvents: true });
  let pageA = null;
  let pageB = null;
  try {
    const extension = await getExtension();
    pageA = await openAutosPage(extension.context, server.origin, '999001');
    pageB = await openAutosPage(extension.context, server.origin, '999002');
    const worker = await waitForServiceWorker(extension.context);
    const result = await worker.evaluate(async () => {
      const tabs = await chrome.tabs.query({});
      const tabA = tabs.find((tab) => tab.url && tab.url.includes('/999001/autos'));
      const tabB = tabs.find((tab) => tab.url && tab.url.includes('/999002/autos'));
      const ownA = await chrome.tabs.sendMessage(tabA.id, {
        type: 'BATCH_ENSURE_DOCUMENT',
        expectedProcessId: '999001',
      });
      const ownB = await chrome.tabs.sendMessage(tabB.id, {
        type: 'BATCH_ENSURE_DOCUMENT',
        expectedProcessId: '999002',
      });
      const crossed = await chrome.tabs.sendMessage(tabA.id, {
        type: 'BATCH_ENSURE_DOCUMENT',
        expectedProcessId: '999002',
      });
      return { ownA, ownB, crossed };
    });
    assert.equal(result.ownA.ok, true);
    assert.equal(result.ownB.ok, true);
    assert.equal(result.crossed.ok, false);
    assert.equal(result.crossed.code, 'PROCESS_CHANGED');
  } finally {
    if (pageA) await pageA.close().catch(() => {});
    if (pageB) await pageB.close().catch(() => {});
    await server.close();
  }
});
