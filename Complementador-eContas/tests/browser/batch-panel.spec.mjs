import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { launchExtension } from './harness.mjs';
import { startFixtureServer } from './harness.mjs';

const LIST_PATH = '/lista#/dashboard/processos-no-setor/no-setor';
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

async function withList(fn) {
  const server = await startFixtureServer();
  let extension = null;
  try {
    extension = await getExtension();
    const page = await extension.context.newPage();
    await page.goto(server.origin + LIST_PATH, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(
      document.querySelector('#complementador-econtas-batch-root')
        ?.shadowRoot
        ?.querySelector('button[data-action="preview"]'),
    ), null, { timeout: 15000 });
    return await fn(server, page);
  } finally {
    if (extension) {
      for (const page of extension.context.pages()) {
        if (page !== extension.keepalive) {
          await page.close().catch(() => {});
        }
      }
    }
    await server.close();
  }
}

function panelState(page) {
  return page.evaluate(() => {
    const shadow = document.querySelector('#complementador-econtas-batch-root').shadowRoot;
    return {
      status: shadow.querySelector('.status').textContent.trim(),
      summary: shadow.querySelector('.summary').textContent.trim(),
      disabled: Object.fromEntries([...shadow.querySelectorAll('button')]
        .map((button) => [button.getAttribute('data-action'), button.disabled])),
      keepProblem: shadow.querySelector('input[data-option="keep-problem-tabs"]')?.checked ?? null,
    };
  });
}

async function clickAction(page, action) {
  await page.evaluate((name) => {
    document.querySelector('#complementador-econtas-batch-root').shadowRoot
      .querySelector('button[data-action="' + name + '"]').click();
  }, action);
}

after(async () => {
  if (sharedExtension) {
    await sharedExtension.close().catch(() => {});
    sharedExtension = null;
  }
});

test('batch_panel_previews_starts_and_stops_on_current_page', async () => {
  await withList(async (server, page) => {
    const initial = await panelState(page);
    assert.equal(initial.disabled.pause, true);
    assert.equal(initial.keepProblem, true);
    assert.equal(initial.disabled.stop, true);

    await clickAction(page, 'preview');
    await page.waitForFunction(() => /pendentes/.test(
      document.querySelector('#complementador-econtas-batch-root').shadowRoot.querySelector('.status').textContent,
    ), null, { timeout: 10000 });
    const preview = await panelState(page);
    assert.match(preview.status, /1 pendentes, 1 concluídos, 1 sem status/);

    await clickAction(page, 'start');
    await page.waitForFunction(() => /Em execução/.test(
      document.querySelector('#complementador-econtas-batch-root').shadowRoot.querySelector('.status').textContent,
    ), null, { timeout: 10000 });
    const started = await panelState(page);
    assert.match(started.summary, /3 capturados/);
    assert.match(started.summary, /1 pré-concluídos/);
    assert.match(started.summary, /1 sem status/);
    assert.match(started.summary, /1 na fila/);
    assert.equal(started.disabled.start, true);
    assert.equal(started.disabled.stop, false);

    // O painel atualiza por polling; os contadores não podem zerar na atualização.
    await page.waitForTimeout(3500);
    const polled = await panelState(page);
    assert.match(polled.summary, /3 capturados/);
    assert.match(polled.summary, /1 na fila/);

    await clickAction(page, 'stop');
    await page.waitForFunction(() => /Parado/.test(
      document.querySelector('#complementador-econtas-batch-root').shadowRoot.querySelector('.status').textContent,
    ), null, { timeout: 10000 });
    const stopped = await panelState(page);
    assert.equal(stopped.disabled.start, false);
    assert.equal(stopped.disabled.pause, true);

    assert.equal(server.requests.every((request) => request.method === 'GET'), true);
  });
});
