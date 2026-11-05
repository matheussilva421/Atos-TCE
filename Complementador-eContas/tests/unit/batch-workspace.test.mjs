import test from 'node:test';
import assert from 'node:assert/strict';
import {
  openWorkspace,
  recoverWorkspaceOnce,
  verifyWorkspace,
  waitForWorkspace,
} from '../../src/batch/workspace.mjs';

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

test('waits_for_tab_url_before_verifying', async () => {
  const api = fakeTabs({
    51: { id: 51, url: '' },
    52: { id: 52, url: ORIGIN + '/#/dashboard/complementar-ato/701' },
  });
  let polls = 0;
  const result = await waitForWorkspace({
    processId: '701',
    ids: { autosTabId: 51, formTabId: 52 },
    tabsApi: {
      ...api,
      async get(id) {
        polls += 1;
        if (id === 51 && polls >= 3) {
          api.tabs[51] = { id: 51, url: ORIGIN + '/#/dashboard/processos/701/autos' };
        }
        return api.tabs[id];
      },
    },
    timeoutMs: 2000,
    pollMs: 1,
    sleep: async () => {},
  });
  assert.equal(result.ok, true);
  assert.equal(polls >= 2, true);
});

test('wait_for_workspace_times_out_on_wrong_tab', async () => {
  const api = fakeTabs({
    61: { id: 61, url: ORIGIN + '/#/dashboard/processos/799/autos' },
    62: { id: 62, url: ORIGIN + '/#/dashboard/complementar-ato/701' },
  });
  const result = await waitForWorkspace({
    processId: '701',
    ids: { autosTabId: 61, formTabId: 62 },
    tabsApi: api,
    timeoutMs: 5,
    pollMs: 1,
    sleep: async () => {},
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'WRONG_PROCESS_TAB');
});

test('fresh_workspace_replaces_previous_tabs', async () => {
  const api = fakeTabs({
    71: { id: 71, url: ORIGIN + '/#/dashboard/processos/701/autos' },
    72: { id: 72, url: ORIGIN + '/#/dashboard/complementar-ato/701' },
  });
  const removed = [];
  api.remove = async (tabId) => {
    removed.push(tabId);
    delete api.tabs[tabId];
  };
  const workspace = await openWorkspace({
    processId: '702',
    previous: { autosTabId: 71, formTabId: 72 },
    tabsApi: api,
    fresh: true,
  });
  assert.deepEqual(removed, [71, 72]);
  assert.notEqual(workspace.autosTabId, 71);
  assert.notEqual(workspace.formTabId, 72);
  assert.equal(api.tabs[workspace.autosTabId].url.includes('/702/autos'), true);
});
