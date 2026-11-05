import { PORTAL_ORIGIN } from '../shared/config.mjs';
import { MESSAGE } from '../shared/protocol.mjs';
import { parseListRoute } from '../shared/routes.mjs';
import { loadBatch, saveBatch } from './journal.mjs';
import { createFrozenBatch, validateLimits } from './queue.mjs';
import { buildBatchReport } from './report.mjs';
import { reduceBatch } from './state-machine.mjs';

const ACTIVE_STATES = new Set(['READY', 'RUNNING', 'PAUSE_REQUESTED', 'STOP_REQUESTED', 'PAUSED', 'SUSPENDED']);

function failure(code, extra = {}) {
  return { ok: false, code, ...extra };
}

function withTimeout(promise, timeoutMs, code) {
  let handle = null;
  const timeout = new Promise((resolve) => {
    handle = setTimeout(() => resolve({ __timeout: true, code }), timeoutMs);
    if (handle && typeof handle.unref === 'function') {
      handle.unref();
    }
  });
  return Promise.race([promise, timeout]).finally(() => {
    if (handle) {
      clearTimeout(handle);
    }
  });
}

function statusPayload(batch) {
  return {
    ok: true,
    batchId: batch.batchId,
    revision: batch.revision,
    state: batch.state,
    captured: batch.capture.captured,
    queueLength: batch.queue.length,
    examined: batch.counters.examined,
    saved: batch.counters.saved,
    report: buildBatchReport(batch),
  };
}

/**
 * Ponto único de mutação do lote dentro do service worker. Serializa todas as
 * operações para que dois eventos simultâneos não criem dois lotes.
 */
export class BatchController {
  constructor({ storage, runtimeId, sendToTab, newBatchId, now, timeouts, executionEnabled }) {
    this.storage = storage;
    this.runtimeId = runtimeId;
    this.sendToTab = sendToTab;
    this.newBatchId = newBatchId || (() => 'batch-' + Date.now());
    this.now = now || (() => Date.now());
    this.timeouts = { read: 4000, snapshot: 6000, command: 20000, ...(timeouts || {}) };
    this.executionEnabled = executionEnabled === true;
    this.lock = Promise.resolve();
  }

  serialize(task) {
    const run = this.lock.then(task, task);
    this.lock = run.then(() => undefined, () => undefined);
    return withTimeout(run, this.timeouts.command, 'BATCH_TIMEOUT');
  }

  trusted(sender) {
    return Boolean(sender && sender.id === this.runtimeId);
  }

  listTab(sender) {
    if (!sender || !sender.tab) {
      return null;
    }
    return parseListRoute(sender.tab.url, PORTAL_ORIGIN) ? sender.tab : null;
  }

  async read() {
    try {
      const result = await withTimeout(loadBatch(this.storage), this.timeouts.read, 'STORAGE_TIMEOUT');
      if (result && result.__timeout) {
        return { error: result.code };
      }
      return { batch: result };
    } catch (error) {
      return { error: error && error.code ? error.code : 'JOURNAL_UNAVAILABLE' };
    }
  }

  async snapshot(tabId) {
    const requestId = 'batchsnap-' + this.newBatchId();
    try {
      const result = await withTimeout(
        Promise.resolve(this.sendToTab(tabId, { type: MESSAGE.BATCH_LIST_SNAPSHOT, requestId })),
        this.timeouts.snapshot,
        'LIST_SNAPSHOT_TIMEOUT',
      );
      if (result && result.__timeout) {
        return { ok: false, code: result.code };
      }
      return result;
    } catch {
      return { ok: false, code: 'LIST_SNAPSHOT_FAILED' };
    }
  }

  async preview({ sender }) {
    return this.serialize(async () => {
      if (!this.trusted(sender)) {
        return failure('UNTRUSTED_SENDER');
      }
      const tab = this.listTab(sender);
      if (!tab) {
        return failure('INVALID_LIST_TAB');
      }
      const snapshot = await this.snapshot(tab.id);
      if (!snapshot || !snapshot.ok) {
        return failure((snapshot && snapshot.code) || 'EMPTY_LIST');
      }
      const entries = Array.isArray(snapshot.entries) ? snapshot.entries : [];
      return {
        ok: true,
        contextKey: snapshot.contextKey || null,
        hasPagination: Boolean(snapshot.hasPagination),
        captured: entries.length,
        pending: entries.filter((entry) => entry.status === 'pending').length,
        completed: entries.filter((entry) => entry.status === 'completed').length,
        unknown: entries.filter((entry) => entry.status === 'unknown').length,
      };
    });
  }

  async start({ sender, limits, expectedContextKey }) {
    return this.serialize(async () => {
      if (!this.trusted(sender)) {
        return failure('UNTRUSTED_SENDER');
      }
      const tab = this.listTab(sender);
      if (!tab) {
        return failure('INVALID_LIST_TAB');
      }
      let normalized;
      try {
        normalized = validateLimits(limits);
      } catch {
        return failure('INVALID_LIMIT');
      }
      const existing = await this.read();
      if (existing.error) {
        return failure(existing.error);
      }
      if (existing.batch && ACTIVE_STATES.has(existing.batch.state)) {
        return failure('BATCH_ALREADY_ACTIVE', { batchId: existing.batch.batchId });
      }
      const snapshot = await this.snapshot(tab.id);
      if (!snapshot || !snapshot.ok) {
        return failure((snapshot && snapshot.code) || 'LIST_SNAPSHOT_FAILED');
      }
      if (expectedContextKey && snapshot.contextKey !== expectedContextKey) {
        return failure('CONTEXT_CHANGED');
      }
      let batch;
      try {
        batch = createFrozenBatch({
          batchId: this.newBatchId(),
          listTabId: tab.id,
          contextKey: snapshot.contextKey || 'unknown',
          entries: snapshot.entries,
          limits: normalized,
          startedAt: this.now(),
        });
      } catch (error) {
        return failure(error && error.code ? error.code : 'INVALID_BATCH');
      }
      if (batch.queue.length === 0) {
        return failure('EMPTY_QUEUE', {
          captured: batch.capture.captured,
          skippedCompleted: batch.capture.skippedCompleted,
          skippedUnknown: batch.capture.skippedUnknown,
        });
      }
      const running = reduceBatch(batch, { type: 'START', at: this.now() });
      await saveBatch(this.storage, running);
      return { ...statusPayload(running), executionEnabled: this.executionEnabled };
    });
  }

  async status({ sender }) {
    return this.serialize(async () => {
      if (!this.trusted(sender)) {
        return failure('UNTRUSTED_SENDER');
      }
      const existing = await this.read();
      if (existing.error) {
        return failure(existing.error, { batch: null });
      }
      if (!existing.batch) {
        return { ok: true, batch: null };
      }
      return { ...statusPayload(existing.batch), batch: existing.batch, executionEnabled: this.executionEnabled };
    });
  }

  async transition({ sender, batchId, revision, event, allowed }) {
    return this.serialize(async () => {
      if (!this.trusted(sender)) {
        return failure('UNTRUSTED_SENDER');
      }
      const existing = await this.read();
      if (existing.error) {
        return failure(existing.error);
      }
      const batch = existing.batch;
      if (!batch || batch.batchId !== batchId) {
        return failure('NO_BATCH');
      }
      if (batch.revision !== revision) {
        return failure('STALE_REVISION', { revision: batch.revision, state: batch.state });
      }
      if (!allowed.includes(batch.state)) {
        return failure('INVALID_STATE', { state: batch.state });
      }
      let next;
      try {
        next = reduceBatch(batch, { type: event, at: this.now() });
      } catch (error) {
        return failure(error && error.code ? error.code : 'INVALID_TRANSITION');
      }
      await saveBatch(this.storage, next);
      return { ...statusPayload(next), executionEnabled: this.executionEnabled };
    });
  }

  pause({ sender, batchId, revision }) {
    return this.transition({ sender, batchId, revision, event: 'REQUEST_PAUSE', allowed: ['RUNNING'] });
  }

  stop({ sender, batchId, revision }) {
    return this.transition({
      sender, batchId, revision, event: 'REQUEST_STOP', allowed: ['RUNNING', 'PAUSE_REQUESTED'],
    });
  }

  resume({ sender, batchId, revision }) {
    return this.transition({
      sender, batchId, revision, event: 'RESUME_AUTHORIZED', allowed: ['PAUSED', 'SUSPENDED'],
    });
  }
}
