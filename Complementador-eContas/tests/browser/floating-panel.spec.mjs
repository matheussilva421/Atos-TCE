import test from 'node:test';
import assert from 'node:assert/strict';
import { FORM_PATH, launchExtension, startFixtureServer } from './harness.mjs';

test('form and list panels drag, hide and reopen without losing their contents', async () => {
  const server = await startFixtureServer();
  let extension;
  try {
    extension = await launchExtension();
    for (const [path, hostId] of [
      [FORM_PATH, 'complementador-econtas-root'],
      ['/lista#/dashboard/processos-no-setor/no-setor', 'complementador-econtas-batch-root'],
    ]) {
      const page = await extension.context.newPage();
      await page.goto(server.origin + path);
      const root = page.locator('#' + hostId);
      const panel = root.locator('.wrap');
      const title = root.locator('.title');
      await title.waitFor();
      const before = await panel.boundingBox();
      const handle = await title.boundingBox();
      await page.mouse.move(handle.x + 15, handle.y + 10);
      await page.mouse.down();
      await page.mouse.move(handle.x - 165, handle.y - 90, { steps: 5 });
      await page.mouse.up();
      const moved = await panel.boundingBox();
      assert.ok(Math.abs(moved.x - Math.max(8, before.x - 180)) < 2);
      assert.ok(Math.abs(moved.y - Math.max(8, before.y - 100)) < 2);
      const status = await root.locator('.status').textContent();
      const number = root.locator('input[type="number"]').first();
      if (await number.count()) await number.fill('9');
      await root.getByRole('button', { name: 'Esconder Complementador e-Contas', exact: true }).click();
      assert.equal(await panel.isVisible(), false);
      await root.getByRole('button', { name: 'Mostrar Complementador e-Contas', exact: true }).click();
      assert.equal(await panel.isVisible(), true);
      assert.equal(await root.locator('.status').textContent(), status);
      if (await number.count()) assert.equal(await number.inputValue(), '9');
      const reopened = await panel.boundingBox();
      assert.equal(reopened.x, moved.x);
      await page.setViewportSize({ width: 360, height: 300 });
      await page.waitForTimeout(100);
      const small = await panel.boundingBox();
      assert.ok(small.x >= 0 && small.y >= 0);
      assert.ok(small.x + small.width <= 360 && small.y + small.height <= 300);
      await page.close();
    }
  } finally {
    await extension?.close();
    await server.close();
  }
});
