/**
 * MV3 service worker: the extension's only decision point.
 *
 * It polls the Mesa, executes the specific command it received and reports one
 * sanitized result. It never chooses a process, never writes a form and never
 * finishes an act; an unknown command type is refused instead of guessed.
 */

import { createApi } from "../lib/api.js";
import {
  COMMAND_TYPES,
  MAX_SCAN_PAGES,
  MESSAGE_TYPES,
  PORTAL_ORIGIN,
  isSupportedCommand,
} from "../lib/protocol.js";

const RETRY_ATTEMPTS = 4;
const RETRY_DELAY_MS = 300;
const FORM_READ_ATTEMPTS = 10;
const FORM_READ_DELAY_MS = 800;

function delay(milliseconds) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds));
}

/**
 * Execute one command with injected collaborators, so the behaviour is testable
 * without a browser.
 */
export async function executeCommand(command, dependencies = {}) {
  const commandId = Number.isInteger(command?.id) ? command.id : null;
  const type = String(command?.type ?? "").trim().toUpperCase();
  if (!isSupportedCommand(type)) {
    return { command_id: commandId, ok: false, error: `unsupported command: ${type || "missing"}` };
  }
  if (type === COMMAND_TYPES.STATUS) {
    return { command_id: commandId, ok: true, status: "ready" };
  }
  if (type === COMMAND_TYPES.SCAN_AREA) {
    const snapshot = await dependencies.scanPortal(command.payload ?? {});
    return { ...snapshot, command_id: commandId, ok: true };
  }
  if (type === COMMAND_TYPES.OPEN_ACT) {
    const outcome = (await dependencies.openAct(command.payload ?? {})) ?? {};
    return { ...outcome, command_id: commandId };
  }
  if (type === COMMAND_TYPES.READ_FORM) {
    const form = await dependencies.readForm(command.payload ?? {});
    if (!form) {
      return {
        command_id: commandId,
        ok: false,
        error: "o formulário do ato não apareceu a tempo na Área Restrita",
      };
    }
    return { ...form, command_id: commandId, ok: true };
  }
  // Declared by the protocol but not implemented yet: refuse instead of guessing.
  return { command_id: commandId, ok: false, error: `unsupported command: ${type}` };
}

/**
 * Walk the list pages through content-script messages, collecting one sanitized
 * row set. Stops at the reported last page, at the page cap, when the portal
 * cannot advance, or when two consecutive pages look identical (a stalled
 * click must never become an infinite loop).
 */
export async function scanAreaPages({ scanPage, advancePage, maxPages = MAX_SCAN_PAGES }) {
  const rows = [];
  const seen = new Set();
  let sourceScope = null;
  let marker = null;
  let role = "unknown";
  let previousSignature = null;
  let stagnant = 0;

  for (let page = 1; page <= maxPages; page += 1) {
    const snapshot = await scanPage();
    role = snapshot?.role ?? "unknown";
    if (snapshot?.source_scope) sourceScope = snapshot.source_scope;
    if (snapshot?.marker) marker = snapshot.marker;
    for (const row of snapshot?.rows ?? []) {
      const key = `${row.process_key}\u0000${row.interested_normalized}`;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push(row);
    }

    const signature = `${snapshot?.page ?? page}:${(snapshot?.rows ?? []).length}`;
    if (signature === previousSignature) {
      stagnant += 1;
    } else {
      stagnant = 0;
      previousSignature = signature;
    }
    if (stagnant >= 2) break;

    const currentPage = Number(snapshot?.page ?? page);
    const totalPages = Number(snapshot?.total_pages ?? currentPage);
    if (!(currentPage < totalPages)) break;
    if (page >= maxPages) break;
    const advanced = await advancePage();
    if (!advanced) break;
  }

  return { role, source_scope: sourceScope, marker, rows };
}

export function installRouter({
  api = createApi({ storage: globalThis.chrome?.storage?.local }),
  chromeApi = globalThis.chrome,
  verbose = false,
} = {}) {
  let running = false;

  async function findPortalTab() {
    const tabs = await chromeApi.tabs.query({ url: [`${PORTAL_ORIGIN}/*`] });
    return tabs?.[0] ?? null;
  }

  async function sendToTab(tabId, message) {
    let lastError = null;
    for (let attempt = 0; attempt < RETRY_ATTEMPTS; attempt += 1) {
      try {
        return await chromeApi.tabs.sendMessage(tabId, message);
      } catch (error) {
        // The tab is often mid-navigation; the content script comes back.
        lastError = error;
        await delay(RETRY_DELAY_MS);
      }
    }
    throw lastError ?? new Error("a aba da Área Restrita não respondeu");
  }

  async function scanPortal() {
    const tab = await findPortalTab();
    if (!tab) throw new Error("Nenhuma aba autenticada da Área Restrita está aberta.");
    return scanAreaPages({
      scanPage: async () => {
        const response = await sendToTab(tab.id, { type: MESSAGE_TYPES.SCAN_PAGE });
        if (response?.ok !== true) throw new Error(response?.error ?? "Falha ao ler a página do portal.");
        return response.snapshot;
      },
      advancePage: async () => {
        const response = await sendToTab(tab.id, {
          type: MESSAGE_TYPES.LIST_PAGE,
          payload: { action: "next" },
        });
        if (response?.ok !== true) return false;
        await delay(400);
        return true;
      },
    });
  }

  async function portalTabs() {
    return (await chromeApi.tabs.query({ url: [`${PORTAL_ORIGIN}/*`] })) ?? [];
  }

  /**
   * Ask every Área Restrita tab to open the act. The legacy portal opens the
   * form in a sibling tab, so the loop is over tabs, not over one document.
   */
  async function openAct(payload) {
    const tabs = await portalTabs();
    if (tabs.length === 0) {
      throw new Error("Nenhuma aba autenticada da Área Restrita está aberta.");
    }
    let lastRefusal = { ok: false, code: "SCREEN_NOT_NAVIGABLE" };
    for (const tab of tabs) {
      try {
        const response = await sendToTab(tab.id, { type: MESSAGE_TYPES.OPEN_ACT, payload });
        if (response?.ok === true) return response;
        if (response?.ok === false) lastRefusal = response;
      } catch (error) {
        lastRefusal = { ok: false, code: "TAB_UNREACHABLE", error: String(error?.message ?? error) };
      }
    }
    return lastRefusal;
  }

  /** Wait for the act form to appear, then return its sanitized state. */
  async function readForm(payload) {
    for (let attempt = 0; attempt < FORM_READ_ATTEMPTS; attempt += 1) {
      for (const tab of await portalTabs()) {
        try {
          const response = await sendToTab(tab.id, { type: MESSAGE_TYPES.READ_FORM, payload });
          if (response?.ok === true && response.form) return response.form;
        } catch {
          // The sibling tab is usually still loading on the first attempts.
        }
      }
      await delay(FORM_READ_DELAY_MS);
    }
    return null;
  }

  async function poll() {
    if (running) return { ok: true, skipped: true };
    running = true;
    try {
      const outcome = await api.nextCommand();
      if (!outcome.ok) return { ok: false, error: outcome.error, status: outcome.status };
      if (!outcome.command) return { ok: true, command: null };

      let result;
      try {
        result = await executeCommand(outcome.command, { scanPortal, openAct, readForm });
      } catch (error) {
        result = {
          command_id: outcome.command.id,
          ok: false,
          error: String(error?.message ?? error),
        };
      }
      await api.reportResult(outcome.command.id, result);
      if (verbose) console.debug(`ATOS TCE: comando ${outcome.command.id} (${result.ok ? "ok" : "falhou"})`);
      return { ok: true, command: outcome.command.id, result };
    } finally {
      running = false;
    }
  }

  chromeApi.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== MESSAGE_TYPES.POLL_COMMANDS) return undefined;
    poll()
      .then((outcome) => sendResponse(outcome))
      .catch((error) => sendResponse({ ok: false, error: String(error?.message ?? error) }));
    return true;
  });

  // Slow recovery path: the heartbeat is the primary wake-up, this catches the
  // case where no portal tab is open yet when a command is queued.
  chromeApi.alarms?.create?.("tce-recovery-poll", { periodInMinutes: 1 });
  chromeApi.alarms?.onAlarm?.addListener?.((alarm) => {
    if (alarm?.name === "tce-recovery-poll") poll();
  });

  return { poll, scanPortal, openAct, readForm };
}

if (globalThis.chrome?.runtime?.onMessage?.addListener) {
  installRouter();
}
