import test from 'node:test';
import assert from 'node:assert/strict';
import { createRunnerDeps } from '../../src/batch/deps.mjs';
import { MESSAGE } from '../../src/shared/protocol.mjs';

const ORIGIN = 'https://processos.tce.rn.gov.br';

function fakeTabs() {
  const tabs = {};
  const calls = [];
  let nextId = 100;
  return {
    calls,
    tabs,
    async query() {
      return [
        { id: 1, url: ORIGIN + '/#/dashboard/processos-no-setor/no-setor', windowId: 1 },
        { id: 2, url: ORIGIN + '/#/dashboard/processos/501/autos', windowId: 1 },
        { id: 3, url: 'https://example.invalid/', windowId: 1 },
      ];
    },
    async create({ url }) {
      const id = nextId;
      nextId += 1;
      tabs[id] = { id, url };
      calls.push({ op: 'create', id, url });
      return tabs[id];
    },
    async update(id, { url }) {
      tabs[id] = { ...(tabs[id] || { id }), url };
      calls.push({ op: 'update', id, url });
      return tabs[id];
    },
    async get(id) {
      if (!tabs[id]) throw new Error('missing');
      return tabs[id];
    },
    async remove(id) {
      calls.push({ op: 'remove', id });
      delete tabs[id];
    },
  };
}

function deps(options = {}) {
  const tabs = options.tabs || fakeTabs();
  const messages = [];
  const fills = [];
  const instance = createRunnerDeps({
    storage: options.storage || {},
    tabs,
    sendToTab: async (tabId, message) => {
      messages.push({ tabId, message });
      return options.formResponse || { ok: true };
    },
    fillTransaction: async (payload) => {
      fills.push(payload);
      return options.fillResult || { ok: true };
    },
    now: () => 1000,
    executionEnabled: options.executionEnabled === true,
  });
  return { instance, tabs, messages, fills };
}

test('open_workspace_replaces_tabs_between_processes', async () => {
  const { instance, tabs } = deps();
  const first = await instance.openWorkspace({ processId: '501' });
  const second = await instance.openWorkspace({ processId: '502' });
  assert.notDeepEqual(second, first);
  assert.equal(tabs.calls.filter((call) => call.op === 'create').length, 4);
  assert.equal(tabs.tabs[first.autosTabId], undefined);
  assert.equal(tabs.tabs[second.autosTabId].url.includes('/502/autos'), true);
});

test('fill_filters_source_tabs_to_portal_origin', async () => {
  const { instance, fills, messages } = deps();
  const workspace = await instance.openWorkspace({ processId: '501' });
  await instance.fill({ processId: '501', formTabId: workspace.formTabId, autosTabId: workspace.autosTabId });
  assert.equal(fills.length, 1);
  assert.equal(messages[0].message.type, MESSAGE.BATCH_ENSURE_DOCUMENT);
  assert.deepEqual(fills[0].sourceTabs.map((tab) => tab.id), [1, 2]);
  assert.equal(fills[0].processId, '501');
});

test('select_and_validate_use_dedicated_messages', async () => {
  const { instance, messages } = deps({
    formResponse: { ok: false, code: 'INTERESTED_CHANGED' },
  });
  await instance.selectInterested({ processId: '501', formTabId: 77 });
  const validation = await instance.validate({ processId: '501', formTabId: 77, interestedKey: 'k' });
  assert.deepEqual(messages.map((item) => item.message.type), [
    MESSAGE.BATCH_SELECT_INTERESTED,
    MESSAGE.BATCH_VALIDATE_FORM,
  ]);
  assert.equal(validation.ok, false);
  assert.equal(validation.code, 'INTERESTED_CHANGED');
});

test('save_is_closed_by_default', async () => {
  const { instance } = deps();
  assert.equal(instance.saveEnabled, false);
  const outcome = await instance.save({ processId: '501', attemptId: 'attempt-1' });
  assert.equal(outcome.attempted, false);
  assert.equal(outcome.code, 'SAVE_GATE_CLOSED');
  const verified = await instance.verify({ processId: '501' });
  assert.equal(verified.status, 'unknown');
});

test('execution_flag_does_not_enable_real_save_adapter', async () => {
  const { instance } = deps({ executionEnabled: true });
  assert.equal(instance.saveEnabled, true);
  const outcome = await instance.save({ processId: '501', attemptId: 'attempt-1' });
  assert.equal(outcome.result, 'error');
  assert.equal(outcome.code, 'SAVE_ADAPTER_NOT_WIRED');
});

test('workspace_is_verified_before_use', async () => {
  const tabs = fakeTabs();
  const get = tabs.get.bind(tabs);
  tabs.get = async (id) => {
    const tab = await get(id);
    return { ...tab, url: tab.url.replace(/\/\d{3}\//, '/999/') };
  };
  const messages = [];
  const instance = createRunnerDeps({
    storage: {},
    tabs,
    sendToTab: async (tabId, message) => { messages.push(message); return { ok: true }; },
    fillTransaction: async () => ({ ok: true }),
    now: () => 1000,
    workspaceTimeoutMs: 20,
  });
  await assert.rejects(
    () => instance.openWorkspace({ processId: '501' }),
    (error) => error.code === 'WRONG_PROCESS_TAB',
  );
  assert.equal(messages.length, 0);
});
