/**
 * MV3 service worker: the extension's only decision point.
 *
 * It polls the Mesa, executes the specific command it received and reports one
 * sanitized result. It never chooses a process, never writes a form and never
 * finishes an act; an unknown command type is refused instead of guessed.
 *
 * Every portal action is addressed to one explicit frame. The Área Restrita
 * renders its list, its interested step and its act form inside nested frames,
 * so "send to the tab" can reach the wrong document: the router enumerates the
 * frames of the portal tabs, asks each one, and only acts on the frame whose
 * answer carries the exact requested identity. Two matching frames are an
 * ambiguity and block instead of being resolved by frame order.
 */

import { createApi } from "../lib/api.js";
import {
  COMMAND_TYPES,
  MAX_SCAN_PAGES,
  MESSAGE_TYPES,
  PORTAL_ORIGIN,
  isPortalUrl,
  isSupportedCommand,
} from "../lib/protocol.js";

const RETRY_ATTEMPTS = 4;
const RETRY_DELAY_MS = 300;
const FORM_READ_ATTEMPTS = 10;
const FORM_READ_DELAY_MS = 800;
const FRAME_LIST_ATTEMPTS = 3;
const FRAME_LIST_DELAY_MS = 250;

function delay(milliseconds) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds));
}

/** Mirrors app/core/identity.py: NFKD, drop marks, casefold, collapse, trim. */
function canonical(value) {
  return typeof value === "string"
    ? value
        .normalize("NFKD")
        .replace(/\p{M}+/gu, "")
        .toLowerCase()
        .replace(/\s+/gu, " ")
        .trim()
    : "";
}

function identityParts(identity) {
  return {
    processKey: String(identity?.processKey ?? identity?.process_key ?? "").trim(),
    interested: canonical(identity?.interestedNormalized ?? identity?.interested_normalized),
  };
}

function hasIdentity(identity) {
  const parts = identityParts(identity);
  return Boolean(parts.processKey && parts.interested);
}

function sameIdentity(left, right) {
  if (!hasIdentity(left) || !hasIdentity(right)) return false;
  const wanted = identityParts(left);
  const observed = identityParts(right);
  return wanted.processKey === observed.processKey && wanted.interested === observed.interested;
}

function markerKey(marker) {
  if (!marker) return "";
  return `${canonical(marker.label)}\u0000${String(marker.value ?? "")}`;
}

/** Pagination/context drift between the frozen first page and a later one. */
function contextDrift(frozen, observed) {
  if (observed.role !== frozen.role) {
    return `o papel da página mudou durante a varredura: ${frozen.role} -> ${observed.role}`;
  }
  if (observed.source_scope !== frozen.source_scope) {
    return "o escopo da Área Restrita mudou durante a varredura";
  }
  if (markerKey(observed.marker) !== markerKey(frozen.marker)) {
    return "o marcador da Área Restrita mudou durante a varredura";
  }
  if (observed.total_pages !== frozen.total_pages) {
    return `a paginação da Área Restrita mudou durante a varredura: ${frozen.total_pages} -> ${observed.total_pages}`;
  }
  if (!(observed.page > frozen.page)) {
    return `paginação incoerente: página ${observed.page} depois de ${frozen.page}`;
  }
  return null;
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
    const outcome = (await dependencies.readForm(command.payload ?? {})) ?? null;
    if (!outcome || outcome.ok !== true || !outcome.form) {
      return {
        command_id: commandId,
        ok: false,
        code: outcome?.code ?? "FORM_NOT_AVAILABLE",
        error: outcome?.error ?? "o formulário do ato não apareceu a tempo na Área Restrita",
      };
    }
    return { ...outcome.form, command_id: commandId, ok: true };
  }
  if (type === COMMAND_TYPES.FILL_FORM) {
    const outcome = (await dependencies.fillForm(command.payload ?? {})) ?? {};
    return { ...outcome, command_id: commandId };
  }
  // Declared by the protocol but not implemented yet: refuse instead of guessing.
  return { command_id: commandId, ok: false, error: `unsupported command: ${type}` };
}

/**
 * Walk the list pages through content-script messages, collecting one sanitized
 * row set. The context of the first page (role, scope, marker and expected
 * pagination) is frozen: a later page that changes it, or that reports a page
 * which did not advance, aborts the scan instead of persisting a mixed partial
 * snapshot. The scan also stops at the reported last page, at the page cap or
 * when the portal cannot advance.
 */
export async function scanAreaPages({ scanPage, advancePage, maxPages = MAX_SCAN_PAGES }) {
  const rows = [];
  const seen = new Set();
  let frozen = null;

  for (let index = 1; index <= maxPages; index += 1) {
    const snapshot = (await scanPage()) ?? {};
    const observed = {
      role: String(snapshot.role ?? "unknown"),
      source_scope: snapshot.source_scope ?? null,
      marker: snapshot.marker ?? null,
      page: Number(snapshot.page ?? index),
      total_pages: Number(snapshot.total_pages ?? snapshot.page ?? index),
    };
    if (frozen === null) {
      frozen = observed;
    } else {
      const drift = contextDrift(frozen, observed);
      if (drift) throw new Error(drift);
      frozen = { ...frozen, page: observed.page };
    }
    for (const row of snapshot.rows ?? []) {
      const key = `${row.process_key}\u0000${row.interested_normalized}`;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push(row);
    }
    if (!(frozen.page < frozen.total_pages)) break;
    if (index >= maxPages) break;
    const advanced = await advancePage();
    if (!advanced) break;
  }

  return { role: frozen.role, source_scope: frozen.source_scope, marker: frozen.marker, rows };
}

export function installRouter({
  api = createApi({ storage: globalThis.chrome?.storage?.local }),
  chromeApi = globalThis.chrome,
  verbose = false,
  timing = {},
} = {}) {
  let running = false;
  const retryAttempts = timing.retryAttempts ?? RETRY_ATTEMPTS;
  const retryDelayMs = timing.retryDelayMs ?? RETRY_DELAY_MS;
  const formReadAttempts = timing.formReadAttempts ?? FORM_READ_ATTEMPTS;
  const formReadDelayMs = timing.formReadDelayMs ?? FORM_READ_DELAY_MS;
  const pageDelayMs = timing.pageDelayMs ?? 400;

  async function portalTabs() {
    return (await chromeApi.tabs.query({ url: [`${PORTAL_ORIGIN}/*`] })) ?? [];
  }

  /** Every frame of one portal tab, addressed as (tabId, frameId). */
  async function framesOfTab(tabId) {
    let listed = null;
    for (let attempt = 0; attempt < FRAME_LIST_ATTEMPTS && listed === null; attempt += 1) {
      try {
        listed = (await chromeApi.webNavigation?.getAllFrames?.({ tabId })) ?? null;
      } catch {
        await delay(FRAME_LIST_DELAY_MS);
      }
    }
    const frames = [];
    for (const frame of Array.isArray(listed) ? listed : []) {
      if (!Number.isInteger(frame?.frameId)) continue;
      if (frame.url !== undefined && !isPortalUrl(frame.url)) continue;
      frames.push({ tabId, frameId: frame.frameId });
    }
    if (frames.length === 0) frames.push({ tabId, frameId: 0 });
    return frames;
  }

  /** Every frame of every portal tab, addressed explicitly. */
  async function portalFrames() {
    const frames = [];
    for (const tab of await portalTabs()) {
      if (tab?.id === undefined || tab?.id === null) continue;
      frames.push(...(await framesOfTab(tab.id)));
    }
    return frames;
  }

  async function sendToFrame(tabId, frameId, message) {
    let lastError = null;
    for (let attempt = 0; attempt < retryAttempts; attempt += 1) {
      try {
        return await chromeApi.tabs.sendMessage(tabId, message, { frameId });
      } catch (error) {
        // The frame is often mid-navigation; the content script comes back.
        lastError = error;
        await delay(retryDelayMs);
      }
    }
    throw lastError ?? new Error("a moldura da Área Restrita não respondeu");
  }

  /** Ask every portal frame and keep all the answers, never a single first one. */
  async function askFrames(message) {
    const answers = [];
    for (const frame of await portalFrames()) {
      try {
        answers.push({ ...frame, response: await sendToFrame(frame.tabId, frame.frameId, message) });
      } catch (error) {
        answers.push({ ...frame, error: String(error?.message ?? error) });
      }
    }
    return answers;
  }

  /** The single frame that really is the act list; zero or several refuse. */
  async function findListFrame() {
    const answers = await askFrames({ type: MESSAGE_TYPES.SCAN_PAGE });
    if (answers.length === 0) {
      throw new Error("Nenhuma aba autenticada da Área Restrita está aberta.");
    }
    const listFrames = answers.filter(
      (answer) => answer.response?.ok === true && answer.response.snapshot?.role === "list"
    );
    if (listFrames.length === 1) return listFrames[0];
    if (listFrames.length === 0) {
      throw new Error("nenhuma moldura da Área Restrita responde como lista de processos");
    }
    throw new Error(`mais de uma moldura (${listFrames.length}) responde como lista de processos`);
  }

  async function scanPortal() {
    const frame = await findListFrame();
    return scanAreaPages({
      scanPage: async () => {
        const response = await sendToFrame(frame.tabId, frame.frameId, {
          type: MESSAGE_TYPES.SCAN_PAGE,
        });
        if (response?.ok !== true) throw new Error(response?.error ?? "Falha ao ler a página do portal.");
        return response.snapshot;
      },
      advancePage: async () => {
        const response = await sendToFrame(frame.tabId, frame.frameId, {
          type: MESSAGE_TYPES.LIST_PAGE,
          payload: { action: "next" },
        });
        if (response?.ok !== true) return false;
        await delay(pageDelayMs);
        return true;
      },
    });
  }

  /**
   * Ask every frame to open the act. The portal opens the form in a sibling
   * tab/frame, so the loop is over frames, not over one document; each content
   * script only clicks the row or the radio of the exact requested identity.
   */
  async function openAct(payload) {
    const frames = await portalFrames();
    if (frames.length === 0) {
      throw new Error("Nenhuma aba autenticada da Área Restrita está aberta.");
    }
    let lastRefusal = { ok: false, code: "SCREEN_NOT_NAVIGABLE" };
    for (const frame of frames) {
      try {
        const response = await sendToFrame(frame.tabId, frame.frameId, {
          type: MESSAGE_TYPES.OPEN_ACT,
          payload,
        });
        if (response?.ok === true) return response;
        if (response?.ok === false) lastRefusal = response;
      } catch (error) {
        lastRefusal = {
          ok: false,
          code: "FRAME_UNREACHABLE",
          error: String(error?.message ?? error),
        };
      }
    }
    return lastRefusal;
  }

  /**
   * The single frame whose form reports exactly the requested identity.
   * No match means "not there yet"; more than one is an ambiguity that must
   * never be resolved by frame order.
   */
  async function locateFormFrame(identity) {
    const answers = await askFrames({ type: MESSAGE_TYPES.READ_FORM, payload: { identity } });
    const matches = answers.filter(
      (answer) =>
        answer.response?.ok === true &&
        answer.response.form &&
        sameIdentity(answer.response.form.identity, identity)
    );
    if (matches.length === 1) return matches[0];
    if (matches.length === 0) return null;
    return { ambiguous: matches.length };
  }

  /** Wait for the exact act form to appear, then return its sanitized state. */
  async function readForm(payload) {
    const identity = payload?.identity ?? {};
    for (let attempt = 0; attempt < formReadAttempts; attempt += 1) {
      const located = await locateFormFrame(identity);
      if (located?.ambiguous) {
        return {
          ok: false,
          code: "FORM_AMBIGUOUS",
          error: `mais de uma moldura (${located.ambiguous}) tem o formulário do ato`,
        };
      }
      if (located) return { ok: true, form: located.response.form };
      await delay(formReadDelayMs);
    }
    return {
      ok: false,
      code: "FORM_NOT_AVAILABLE",
      error: "o formulário do ato não apareceu a tempo na Área Restrita",
    };
  }

  /** Write only into the one frame whose identity was confirmed by reading. */
  async function fillForm(payload) {
    const located = await locateFormFrame(payload?.identity ?? {});
    if (located?.ambiguous) {
      return {
        ok: false,
        code: "FORM_AMBIGUOUS",
        error: `mais de uma moldura (${located.ambiguous}) tem o formulário do ato`,
      };
    }
    if (!located) {
      return {
        ok: false,
        code: "FORM_NOT_AVAILABLE",
        error: "nenhuma moldura tem o formulário do ato com a identidade pedida",
      };
    }
    try {
      return await sendToFrame(located.tabId, located.frameId, {
        type: MESSAGE_TYPES.FILL_FORM,
        payload,
      });
    } catch (error) {
      return { ok: false, code: "FORM_UNREACHABLE", error: String(error?.message ?? error) };
    }
  }

  /**
   * Read the form the operator opened by hand, for the sidepanel fallback.
   * The fallback is bound to the *active* tab: falling back to another portal
   * tab would offer to fill an act the operator is not looking at.
   */
  async function readCurrentForm() {
    const tabs = (await chromeApi.tabs.query({ active: true, lastFocusedWindow: true })) ?? [];
    const tab = tabs[0] ?? null;
    if (!tab || !isPortalUrl(tab.url)) {
      return {
        ok: false,
        code: "PORTAL_TAB_NOT_ACTIVE",
        error: "a aba ativa não é uma página autenticada da Área Restrita",
      };
    }
    const matches = [];
    for (const frame of await framesOfTab(tab.id)) {
      try {
        const response = await sendToFrame(tab.id, frame.frameId, { type: MESSAGE_TYPES.READ_FORM });
        if (response?.ok === true && response.form) matches.push(response.form);
      } catch {
        // A frame that is navigating is simply not a candidate.
      }
    }
    if (matches.length === 1) return { ok: true, form: matches[0] };
    if (matches.length === 0) {
      return {
        ok: false,
        code: "FORM_NOT_AVAILABLE",
        error: "nenhum formulário de ato está aberto na aba ativa da Área Restrita",
      };
    }
    return {
      ok: false,
      code: "FORM_AMBIGUOUS",
      error: `mais de um formulário (${matches.length}) está aberto na aba ativa`,
    };
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
        result = await executeCommand(outcome.command, { scanPortal, openAct, readForm, fillForm });
      } catch (error) {
        result = {
          command_id: outcome.command.id,
          ok: false,
          error: String(error?.message ?? error),
        };
      }
      // The claim token proves this client still holds the lease, so a stale
      // result can never finish a command another poller already took over.
      await api.reportResult(outcome.command.id, {
        ...result,
        claim_token: outcome.command.claim_token ?? null,
      });
      if (verbose) console.debug(`ATOS TCE: comando ${outcome.command.id} (${result.ok ? "ok" : "falhou"})`);
      return { ok: true, command: outcome.command.id, result };
    } finally {
      running = false;
    }
  }

  chromeApi.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === MESSAGE_TYPES.READ_CURRENT_FORM) {
      readCurrentForm()
        .then((outcome) => sendResponse(outcome))
        .catch((error) => sendResponse({ ok: false, error: String(error?.message ?? error) }));
      return true;
    }
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

  return { poll, scanPortal, openAct, readForm, fillForm, readCurrentForm };
}

if (globalThis.chrome?.runtime?.onMessage?.addListener) {
  installRouter();
}
