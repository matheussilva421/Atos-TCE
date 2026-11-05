import test from 'node:test';
import assert from 'node:assert/strict';
import { openWorkspace, recoverWorkspaceOnce, verifyWorkspace } from '../../src/batch/workspace.mjs';

const ORIGIN = 'https://processos.tce.rn.gov.br';

function fakeTabs(initial = {}) {
  const tabs = { ...initial };
  const calls = [];
  let nextId = 900;
  return {
    tabs,
    calls,
    async create(properties) {
      const id = nextId;
      nextId += 1;
      tabs[id] = { id, url: properties.url };
      calls.push({ op: 'create', id, url: properties.url });
      return tabs[id];
    },
    async update(tabId, properties) {
      calls.push({ op: 'update', id: tabId, url: properties.url });
      tabs[tabId] = { ...(tabs[tabId] || { id: tabId }), url: properties.url };
      return tabs[tabId];
    },
    async get(tabId) {
      if (!tabs[tabId]) {
        throw new Error('No tab with id: ' + tabId);
      }
      return tabs[tabId];
    },
  };
}

test('list_tab_never_navigated', async () => {
  const api = fakeTabs({ 12: { id: 12, url: ORIGIN + '/#/dashboard/processos-no-setor/no-setor' } });
  const workspace = await openWorkspace({ processId: '701', tabsApi: api });
  assert.equal(workspace.autosTabId > 0, true);
  assert.equal(workspace.formTabId > 0, true);
  assert.equal(api.calls.some((call) => call.id === 12), false);
  assert.equal(api.tabs[12].url.includes('processos-no-setor'), true);
});

test('workspace_reuses_two_tabs', async () => {
  const api = fakeTabs({
    31: { id: 31, url: ORIGIN + '/#/dashboard/processos/701/autos' },
    32: { id: 32, url: ORIGIN + '/#/dashboard/complementar-ato/701' },
  });
  const workspace = await openWorkspace({ processId: '701', previous: { autosTabId: 31, formTabId: 32 }, tabsApi: api });
  assert.deepEqual(workspace, { autosTabId: 31, formTabId: 32 });
  assert.equal(api.calls.every((call) => call.op === 'update'), true);
  assert.equal(api.calls.length, 2);
});

test('wrong_process_tab_fails_closed', async () => {
  const api = fakeTabs({
    41: { id: 41, url: ORIGIN + '/#/dashboard/processos/799/autos' },
    42: { id: 42, url: ORIGIN + '/#/dashboard/complementar-ato/701' },
  });
  const result = await verifyWorkspace({ processId: '701', ids: { autosTabId: 41, formTabId: 42 }, tabsApi: api });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'WRONG_PROCESS_TAB');
});

test('closed_tab_recovers_once_before_save', async () => {
  const api = fakeTabs({ 42: { id: 42, url: ORIGIN + '/#/dashboard/complementar-ato/701' } });
  const first = await recoverWorkspaceOnce({
    processId: '701', ids: { autosTabId: 41, formTabId: 42 }, tabsApi: api, saveAttempted: false, alreadyRecovered: false,
  });
  assert.equal(first.ok, true);
  assert.equal(Number.isInteger(first.workspace.autosTabId), true);
  assert.notEqual(first.workspace.autosTabId, 41);
  const second = await recoverWorkspaceOnce({
    processId: '701', ids: { autosTabId: 41, formTabId: 42 }, tabsApi: api, saveAttempted: false, alreadyRecovered: true,
  });
  assert.equal(second.ok, false);
  assert.equal(second.code, 'RECOVERY_EXHAUSTED');
});

test('no_recreate_after_save_attempt', async () => {
  const api = fakeTabs({});
  const result = await recoverWorkspaceOnce({
    processId: '701', ids: { autosTabId: 41, formTabId: 42 }, tabsApi: api, saveAttempted: true, alreadyRecovered: false,
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'SAVE_ATTEMPTED');
  assert.equal(api.calls.length, 0);
});

test('form_and_autos_tabs_must_differ', async () => {
  const api = fakeTabs({});
  await assert.rejects(
    () => openWorkspace({ processId: '701', previous: { autosTabId: 5, formTabId: 5 }, tabsApi: api }),
    (error) => error.code === 'INVALID_WORKSPACE',
  );
});
