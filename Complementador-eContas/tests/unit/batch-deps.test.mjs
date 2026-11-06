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
  const transactions = [];
  const instance = createRunnerDeps({
    storage: options.storage || {},
    tabs,
    sendToTab: async (tabId, message) => {
      messages.push({ tabId, message });
      if (message.type === MESSAGE.BATCH_VERIFY_SAVED && options.verifyResponse) {
        return options.verifyResponse;
      }
      if (message.type === MESSAGE.BATCH_VERIFY_SAVED && options.verifyThrows) {
        throw new Error('verify failed');
      }
      return options.formResponse || { ok: true };
    },
    fillTransaction: async (payload) => {
      fills.push(payload);
      return options.fillResult || { ok: true };
    },
    now: () => 1000,
    executionEnabled: options.executionEnabled === true,
    beginTransaction: (tabId, requestId) => {
      transactions.push({ op: 'begin', tabId, requestId });
      return true;
    },
    finishTransaction: (tabId, requestId) => {
      transactions.push({ op: 'finish', tabId, requestId });
    },
  });
  return { instance, tabs, messages, fills, transactions };
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
  const { instance, fills, messages, transactions } = deps();
  const workspace = await instance.openWorkspace({ processId: '501' });
  await instance.fill({ processId: '501', formTabId: workspace.formTabId, autosTabId: workspace.autosTabId });
  assert.equal(fills.length, 1);
  assert.equal(messages[0].message.type, MESSAGE.BATCH_ENSURE_DOCUMENT);
  assert.deepEqual(fills[0].sourceTabs.map((tab) => tab.id), [1, 2]);
  assert.equal(fills[0].processId, '501');
  assert.equal(transactions[0].op, 'begin');
  assert.equal(transactions[1].op, 'finish');
  assert.equal(transactions[0].requestId, fills[0].requestId);
  assert.equal(transactions[0].tabId, workspace.autosTabId);
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

test('fill_reports_missing_ensure_response', async () => {
  const tabs = fakeTabs();
  const instance = createRunnerDeps({
    storage: {},
    tabs,
    sendToTab: async () => undefined,
    fillTransaction: async () => ({ ok: true }),
    now: () => 1000,
    workspaceTimeoutMs: 20,
    ensureRetryDelayMs: 0,
  });
  const workspace = await instance.openWorkspace({ processId: '501' });
  const result = await instance.fill({
    processId: '501',
    formTabId: workspace.formTabId,
    autosTabId: workspace.autosTabId,
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'ENSURE_UNDEFINED');
});

test('filled_form_tabs_are_kept_for_manual_review', async () => {
  const { instance, tabs } = deps();
  const first = await instance.openWorkspace({ processId: '501' });
  instance.markFilled({ processId: '501' });
  const second = await instance.openWorkspace({ processId: '502' });
  assert.equal(tabs.tabs[first.formTabId] !== undefined, true);
  assert.equal(tabs.tabs[first.autosTabId], undefined);
  assert.notEqual(second.formTabId, first.formTabId);
});

test('save_uses_injected_save_transaction_when_enabled', async () => {
  const calls = [];
  const instance = createRunnerDeps({
    storage: {},
    tabs: fakeTabs(),
    sendToTab: async () => ({ ok: true }),
    fillTransaction: async () => ({ ok: true }),
    now: () => 1000,
    executionEnabled: true,
    saveTransaction: async ({ processId, attemptId }) => {
      calls.push({ processId, attemptId });
      return { attempted: true, result: 'ack' };
    },
  });
  const outcome = await instance.save({ processId: '501', attemptId: 'attempt-1' });
  assert.deepEqual(outcome, { attempted: true, result: 'ack' });
  assert.deepEqual(calls, [{ processId: '501', attemptId: 'attempt-1' }]);
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

test('verify_confirms_from_fresh_tab_without_save_button', async () => {
  const { instance, tabs, messages } = deps({
    verifyResponse: { ok: true, processId: '501', hasForm: true, saveButtonPresent: false },
  });
  const result = await instance.verify({ processId: '501', attemptId: 'attempt-1' });
  assert.equal(result.status, 'confirmed');
  assert.deepEqual(result.evidence, ['fresh_tab', 'form_present', 'save_button_absent']);
  const created = tabs.calls.filter((call) => call.op === 'create');
  assert.equal(created.length, 1);
  assert.equal(created[0].url.includes('/complementar-ato/501'), true);
  assert.equal(messages[0].message.type, MESSAGE.BATCH_VERIFY_SAVED);
  assert.equal(tabs.calls.some((call) => call.op === 'remove' && call.id === created[0].id), true);
});

test('verify_stays_unknown_when_save_button_is_present', async () => {
  const { instance } = deps({
    verifyResponse: { ok: true, processId: '501', hasForm: true, saveButtonPresent: true },
  });
  const result = await instance.verify({ processId: '501', attemptId: 'attempt-2' });
  assert.equal(result.status, 'unknown');
  assert.deepEqual(result.evidence, ['VERIFY_SAVE_BUTTON_PRESENT']);
});

test('verify_stays_unknown_for_wrong_process_or_unreadable_form', async () => {
  const wrong = deps({
    verifyResponse: { ok: true, processId: '999', hasForm: true, saveButtonPresent: false },
  });
  assert.equal((await wrong.instance.verify({ processId: '501' })).status, 'unknown');
  const noForm = deps({
    verifyResponse: { ok: true, processId: '501', hasForm: false, saveButtonPresent: false },
  });
  assert.equal((await noForm.instance.verify({ processId: '501' })).status, 'unknown');
});

test('verify_closes_temp_tab_when_read_fails', async () => {
  const { instance, tabs } = deps({ verifyThrows: true });
  const result = await instance.verify({ processId: '501', attemptId: 'attempt-3' });
  assert.equal(result.status, 'unknown');
  const created = tabs.calls.filter((call) => call.op === 'create');
  assert.equal(created.length, 1);
  assert.equal(tabs.calls.some((call) => call.op === 'remove' && call.id === created[0].id), true);
});

test('fill_retries_conditionally_after_no_document', async () => {
  let ensures = 0;
  const tabs = fakeTabs();
  const instance = createRunnerDeps({
    storage: {},
    tabs,
    sendToTab: async (tabId, message) => {
      if (message.type === MESSAGE.BATCH_ENSURE_DOCUMENT) {
        ensures += 1;
        return ensures === 1 ? { ok: false, code: 'NO_DOCUMENT' } : { ok: true };
      }
      return { ok: true };
    },
    fillTransaction: async () => ({ ok: true }),
    now: () => 1000,
    ensureRetryDelayMs: 0,
    workspaceTimeoutMs: 20,
  });
  const workspace = await instance.openWorkspace({ processId: '501' });
  const result = await instance.fill({
    processId: '501',
    formTabId: workspace.formTabId,
    autosTabId: workspace.autosTabId,
  });
  assert.equal(result.ok, true);
  assert.equal(ensures, 2);
});

test('fill_does_not_retry_when_process_changed', async () => {
  let ensures = 0;
  const tabs = fakeTabs();
  const instance = createRunnerDeps({
    storage: {},
    tabs,
    sendToTab: async (tabId, message) => {
      if (message.type === MESSAGE.BATCH_ENSURE_DOCUMENT) {
        ensures += 1;
        return { ok: false, code: 'PROCESS_CHANGED' };
      }
      return { ok: true };
    },
    fillTransaction: async () => ({ ok: true }),
    now: () => 1000,
    ensureRetryDelayMs: 0,
    workspaceTimeoutMs: 20,
  });
  const workspace = await instance.openWorkspace({ processId: '501' });
  const result = await instance.fill({
    processId: '501',
    formTabId: workspace.formTabId,
    autosTabId: workspace.autosTabId,
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'PROCESS_CHANGED');
  assert.equal(ensures, 1);
});

test('cleanup_closes_confirmed_tabs_but_preserves_review_state', async () => {
  const { instance, tabs } = deps();
  const workspace = await instance.openWorkspace({ processId: '501' });
  const review = await instance.cleanupWorkspace({ processId: '501', status: 'REVIEW_REQUIRED' });
  assert.equal(review.closed, 0);
  assert.equal(tabs.tabs[workspace.autosTabId] !== undefined, true);
  assert.equal(tabs.tabs[workspace.formTabId] !== undefined, true);
  const confirmed = await instance.cleanupWorkspace({ processId: '501', status: 'CONFIRMED' });
  assert.equal(confirmed.closed, 2);
  assert.equal(tabs.tabs[workspace.autosTabId], undefined);
  assert.equal(tabs.tabs[workspace.formTabId], undefined);
});
