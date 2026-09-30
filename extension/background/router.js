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
// The legacy portal can take several seconds to replace the list after the
// form submit. Keep polling long enough for a slow page without waiting
// forever; two identical snapshots are still required before advancing.
const PAGE_READY_ATTEMPTS = 40;
const PAGE_READY_DELAY_MS = 500;
const PAGE_ADVANCE_ATTEMPTS = 3;
const PAGE_ADVANCE_RETRY_DELAY_MS = 750;

function delay(milliseconds) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds));
}

function pageSnapshotSignature(snapshot) {
  return JSON.stringify({
    page: Number(snapshot?.page ?? 0),
    total_pages: Number(snapshot?.total_pages ?? 0),
    rows: (snapshot?.rows ?? [])
      .map((row) => [row.process_key, row.interested_normalized, row.classification])
      .sort(([left], [right]) => String(left).localeCompare(String(right))),
  });
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
    portalActId: String(identity?.portalActId ?? identity?.portal_act_id ?? "").trim(),
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
  return wanted.processKey === observed.processKey && (
    wanted.portalActId && observed.portalActId
      ? wanted.portalActId === observed.portalActId
      : wanted.interested === observed.interested
  );
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
  if (observed.page !== frozen.page + 1) {
    return `paginação incoerente: página ${observed.page} depois de ${frozen.page}`;
  }
  return null;
}

/**
 * Execute one command with injected collaborators, so the behaviour is testable
 * without a browser.
 */
/** A stable per-worker session id: no credential, no tab data, no identity. */
const BROWSER_SESSION_ID = (() => {
  const cryptoRef = globalThis.crypto;
  if (cryptoRef?.randomUUID) return cryptoRef.randomUUID();
  const bytes = new Uint8Array(8);
  if (cryptoRef?.getRandomValues) cryptoRef.getRandomValues(bytes);
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
})();

/** A route path with the query string and fragment removed. */
function routePath(url) {
  try {
    return new URL(String(url)).pathname;
  } catch {
    return "";
  }
}

/**
 * Sanitized structural diagnostics for one resolved form. The wrapper around
 * the form never carries identity, field values, cookies or a URL query.
 */
function formDiagnostics(tab, match) {
  const route = routePath(tab?.url);
  const generation = match?.form?.generation;
  return {
    browser_session_id: BROWSER_SESSION_ID,
    tab_ref: `tab-${Number(tab?.id) || 0}`,
    frame_ref: `frame-${Number(match?.frameId) || 0}`,
    ...(route ? { route } : {}),
    screen: "form",
    ...(Number.isInteger(generation) ? { generation } : {}),
  };
}

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
    const snapshot = await dependencies.scanPortal(command.payload ?? {}, {
      renewLease:
        typeof dependencies.renewLease === "function"
          ? () => dependencies.renewLease(command.id, command.claim_token)
          : null,
    });
    return { ...snapshot, command_id: commandId, ok: true };
  }
  if (type === COMMAND_TYPES.OPEN_ACT) {
    const outcome = (await dependencies.openAct(command.payload ?? {})) ?? {};
    return { ...outcome, command_id: commandId };
  }
  if (type === COMMAND_TYPES.OPEN_NEXT_ACT) {
    const outcome = (await dependencies.openNextAct(command.payload ?? {})) ?? {};
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
export async function scanAreaPages({
  scanPage,
  advancePage,
  onPage,
  maxPages = MAX_SCAN_PAGES,
}) {
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
    if (typeof onPage === "function") {
      await onPage({ page: observed.page, total_pages: observed.total_pages });
    }
    if (!(frozen.page < frozen.total_pages)) break;
    if (index >= maxPages) {
      throw new Error(
        `PAGE_LIMIT_EXCEEDED: a varredura parou na página ${frozen.page} de ${frozen.total_pages}`
      );
    }
    const advanced = await advancePage();
    if (!advanced) {
      throw new Error(
        `PAGINATION_STALLED: o portal não avançou e ainda havia páginas (${frozen.page} de ${frozen.total_pages})`
      );
    }
  }

  return { role: frozen.role, source_scope: frozen.source_scope, marker: frozen.marker, rows };
}

function nextActFailure(code) {
  return { ok: false, action: "next_act_failed", code, error: code };
}

/**
 * Navigate to the backend-selected identity without rescanning the queue.
 * The injected operations keep frame/browser effects testable and bounded.
 */
async function orchestrateNextAct(payload, actions, {
  pageCap = MAX_SCAN_PAGES,
  attempts = FORM_READ_ATTEMPTS,
  retryDelayMs = FORM_READ_DELAY_MS,
  requireCurrentIdentity = true,
} = {}) {
  const currentIdentity = payload?.current_identity;
  const targetIdentity = payload?.target_identity;
  const context = payload?.context ?? {};
  const marker = context.marker;
  if (!hasIdentity(targetIdentity) || (requireCurrentIdentity && !hasIdentity(currentIdentity))) {
    return nextActFailure("INVALID_IDENTITY");
  }
  if (requireCurrentIdentity && sameIdentity(currentIdentity, targetIdentity)) {
    return nextActFailure("INVALID_TARGET_IDENTITY");
  }
  if (
    !Number.isInteger(context.scan_id) ||
    context.scan_id <= 0 ||
    !String(context.source_scope ?? "").trim() ||
    !String(marker?.label ?? "").trim() ||
    !String(marker?.value ?? "").trim()
  ) {
    return nextActFailure("SCAN_CONTEXT_MISSING");
  }

  if (!requireCurrentIdentity) {
    let existingTarget;
    try {
      existingTarget = await actions.readTargetForm(targetIdentity);
    } catch {
      existingTarget = { ok: false, code: "FORM_NOT_AVAILABLE" };
    }
    if (existingTarget?.code === "FORM_AMBIGUOUS") return nextActFailure("FORM_AMBIGUOUS");
    if (existingTarget?.ok === true && existingTarget.form) {
      if (!sameIdentity(existingTarget.form.identity, targetIdentity)) {
        return nextActFailure("TARGET_IDENTITY_MISMATCH");
      }
      const activated = await actions.activateTab(existingTarget.tabId);
      if (activated?.ok !== true) return nextActFailure("TARGET_TAB_ACTIVATION_FAILED");
      return {
        ok: true,
        action: "next_act_ready",
        identity: targetIdentity,
        screen: "form",
        already_open: true,
      };
    }
  } else {
    let current;
    try {
      current = await actions.readCurrentForm();
    } catch {
      return nextActFailure("CURRENT_FORM_UNAVAILABLE");
    }
    if (current?.ok === false) return nextActFailure(current.code ?? "CURRENT_FORM_UNAVAILABLE");
    if (current?.form) {
      if (!sameIdentity(current.form.identity, currentIdentity)) {
        return nextActFailure("CURRENT_IDENTITY_MISMATCH");
      }
      let returned;
      try {
        returned = await actions.returnToList(current, currentIdentity);
      } catch {
        return nextActFailure("RETURN_TO_LIST_FAILED");
      }
      if (returned?.ok !== true) return nextActFailure(returned?.code ?? "RETURN_TO_LIST_FAILED");
    }
  }

  let frozenTotalPages = null;
  let expectedPage = null;
  for (let pageNumber = 0; pageNumber < pageCap; pageNumber += 1) {
    let pageState;
    try {
      pageState = await actions.readListPage();
    } catch {
      return nextActFailure("LIST_NOT_AVAILABLE");
    }
    if (pageState?.ok !== true || pageState.snapshot?.role !== "list") {
      return nextActFailure(pageState?.code ?? "LIST_NOT_AVAILABLE");
    }
    const snapshot = pageState.snapshot;
    if (snapshot.source_scope !== context.source_scope) {
      return nextActFailure("SCOPE_MISMATCH");
    }
    if (
      snapshot.marker?.label !== marker.label ||
      snapshot.marker?.value !== marker.value
    ) {
      return nextActFailure("MARKER_MISMATCH");
    }
    const page = Number(snapshot.page);
    const totalPages = Number(snapshot.total_pages);
    if (!Number.isInteger(page) || !Number.isInteger(totalPages) || page < 1 || page > totalPages) {
      return nextActFailure("PAGINATION_INCOHERENT");
    }
    if (frozenTotalPages === null) {
      frozenTotalPages = totalPages;
      expectedPage = page;
    } else if (totalPages !== frozenTotalPages || page !== expectedPage) {
      return nextActFailure("PAGINATION_INCOHERENT");
    }

    let opened = null;
    let rowNotFound = false;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        opened = await actions.openAct(targetIdentity, pageState.frame);
      } catch {
        opened = { ok: false, code: "FRAME_UNREACHABLE" };
      }
      if (opened?.ok === true) {
        let targetForm;
        try {
          targetForm = await actions.readTargetForm(targetIdentity);
        } catch {
          targetForm = { ok: false, code: "FORM_NOT_AVAILABLE" };
        }
        if (targetForm?.code === "FORM_AMBIGUOUS") return nextActFailure("FORM_AMBIGUOUS");
        if (targetForm?.ok === true && targetForm.form) {
          if (!sameIdentity(targetForm.form.identity, targetIdentity)) {
            return nextActFailure("TARGET_IDENTITY_MISMATCH");
          }
          const activated = await actions.activateTab(targetForm.tabId);
          if (activated?.ok !== true) return nextActFailure("TARGET_TAB_ACTIVATION_FAILED");
          return {
            ok: true,
            action: "next_act_ready",
            identity: targetIdentity,
            screen: "form",
          };
        }
        if (targetForm?.code === "TARGET_IDENTITY_MISMATCH") {
          return nextActFailure("TARGET_IDENTITY_MISMATCH");
        }
        if (targetForm?.code && targetForm.code !== "FORM_NOT_AVAILABLE") {
          return nextActFailure(targetForm.code);
        }
      } else if (opened?.code === "ROW_ACTION_NOT_FOUND") {
        rowNotFound = true;
        break;
      } else if (!["FRAME_UNREACHABLE", "SCREEN_NOT_NAVIGABLE"].includes(opened?.code)) {
        return nextActFailure(opened?.code ?? "NAVIGATION_FAILED");
      }
      if (attempt + 1 < attempts) await delay(retryDelayMs);
    }

    if (!rowNotFound) return nextActFailure("FORM_NOT_AVAILABLE");
    if (page >= totalPages) return nextActFailure("TARGET_NOT_FOUND");
    if (pageNumber + 1 >= pageCap) return nextActFailure("PAGE_LIMIT_EXCEEDED");
    let advanced;
    try {
      advanced = await actions.advancePage(pageState.frame, page);
    } catch {
      return nextActFailure("PAGINATION_STALLED");
    }
    if (advanced?.ok !== true || advanced.page_after !== page + 1) {
      return nextActFailure(advanced?.code ?? "PAGINATION_STALLED");
    }
    expectedPage = page + 1;
  }
  return nextActFailure("PAGE_LIMIT_EXCEEDED");
}

export function installRouter({
  api = createApi({ storage: globalThis.chrome?.storage?.local }),
  chromeApi = globalThis.chrome,
  verbose = false,
  timing = {},
  nextActDependencies = {},
} = {}) {
  let running = false;
  // Diagnostics of the last form the operator's active tab resolved to. They
  // ride along with a manual-fill request so the Mesa can bind the run to the
  // exact frame it came from; they never carry identity or field values.
  let lastFormDiagnostics = null;
  const retryAttempts = timing.retryAttempts ?? RETRY_ATTEMPTS;
  const retryDelayMs = timing.retryDelayMs ?? RETRY_DELAY_MS;
  const formReadAttempts = timing.formReadAttempts ?? FORM_READ_ATTEMPTS;
  const formReadDelayMs = timing.formReadDelayMs ?? FORM_READ_DELAY_MS;
  const pageDelayMs = timing.pageDelayMs ?? 400;
  const pageReadyAttempts = timing.pageReadyAttempts ?? PAGE_READY_ATTEMPTS;
  const pageReadyDelayMs = timing.pageReadyDelayMs ?? PAGE_READY_DELAY_MS;
  const pageAdvanceAttempts = timing.pageAdvanceAttempts ?? PAGE_ADVANCE_ATTEMPTS;
  const pageAdvanceRetryDelayMs = timing.pageAdvanceRetryDelayMs ?? PAGE_ADVANCE_RETRY_DELAY_MS;

  const sidePanelBehavior = chromeApi.sidePanel?.setPanelBehavior?.({
    openPanelOnActionClick: true,
  });
  sidePanelBehavior?.catch?.(() => {});

  async function portalTabs() {
    return (await chromeApi.tabs.query({ url: [`${PORTAL_ORIGIN}/*`] })) ?? [];
  }

  function manualFillPayload(payload) {
    const body = { ...(payload && typeof payload === "object" ? payload : {}) };
    if (body.diagnostics === undefined && lastFormDiagnostics) {
      body.diagnostics = lastFormDiagnostics;
    }
    return body;
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
  async function askFrames(message, frames = null) {
    const answers = [];
    for (const frame of frames ?? (await portalFrames())) {
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
      const error = new Error("Nenhuma aba autenticada da Área Restrita está aberta.");
      error.code = "PORTAL_NOT_AVAILABLE";
      throw error;
    }
    const listFrames = answers.filter(
      (answer) => answer.response?.ok === true && answer.response.snapshot?.role === "list"
    );
    if (listFrames.length === 1) return listFrames[0];
    if (listFrames.length === 0) {
      const error = new Error("nenhuma moldura da Área Restrita responde como lista de processos");
      error.code = "LIST_NOT_AVAILABLE";
      throw error;
    }
    const error = new Error(`mais de uma moldura (${listFrames.length}) responde como lista de processos`);
    error.code = "LIST_AMBIGUOUS";
    throw error;
  }

  async function openActInListFrame(identity, frame = null) {
    let targetFrame = frame;
    try {
      targetFrame ??= await findListFrame();
      return (await sendToFrame(targetFrame.tabId, targetFrame.frameId, {
        type: MESSAGE_TYPES.OPEN_ACT,
        payload: { identity },
      })) ?? { ok: false, code: "NAVIGATION_RESPONSE_MISSING" };
    } catch (error) {
      return {
        ok: false,
        code: error?.code ?? "FRAME_UNREACHABLE",
        error: String(error?.message ?? error),
      };
    }
  }

  async function waitForPageReady(frame, expectedPage) {
    let previousSignature = null;
    let stableSamples = 0;
    for (let attempt = 0; attempt < pageReadyAttempts; attempt += 1) {
      await delay(attempt === 0 ? pageDelayMs : pageReadyDelayMs);
      let response;
      try {
        response = await sendToFrame(frame.tabId, frame.frameId, { type: MESSAGE_TYPES.SCAN_PAGE });
      } catch {
        continue;
      }
      if (response?.ok !== true) continue;
      const snapshot = response.snapshot ?? {};
      if (Number(snapshot.page) !== expectedPage) continue;
      const signature = pageSnapshotSignature(snapshot);
      if (signature === previousSignature) {
        stableSamples += 1;
      } else {
        previousSignature = signature;
        stableSamples = 1;
      }
      if (stableSamples >= 2) return true;
    }
    return false;
  }

  async function scanPortal(_payload = {}, { renewLease } = {}) {
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
        for (let attempt = 0; attempt < pageAdvanceAttempts; attempt += 1) {
          const response = await sendToFrame(frame.tabId, frame.frameId, {
            type: MESSAGE_TYPES.LIST_PAGE,
            payload: { action: "next" },
          });
          if (response?.ok !== true) return false;
          const before = Number(response.page_before);
          const after = Number(response.page_after);
          const expectedPage = Number.isInteger(after)
            ? after
            : Number.isInteger(before)
              ? before + 1
              : null;
          if (!Number.isInteger(expectedPage)) {
            await delay(pageDelayMs);
            return true;
          }
          if (await waitForPageReady(frame, expectedPage)) return true;
          if (attempt + 1 < pageAdvanceAttempts) {
            await delay(pageAdvanceRetryDelayMs);
          }
        }
        return false;
      },
      onPage: async () => {
        if (typeof renewLease !== "function") return;
        const renewed = await renewLease();
        if (renewed?.ok !== true) {
          throw new Error("o lease do comando de varredura expirou ou mudou de responsável");
        }
      },
    });
  }

  /** Open one proven target, preserving the precise refusal from its screen. */
  async function openAct(payload) {
    const identity = payload?.identity ?? {};
    if (payload?.context) {
      const outcome = await orchestrateNextAct(
        { target_identity: identity, context: payload.context },
        {
          readCurrentForm: readCurrentPortalForm,
          returnToList,
          readListPage: readListPageForNextAct,
          advancePage: advanceListPageForNextAct,
          openAct: openExactNextTarget,
          readTargetForm: readExactTargetForm,
          activateTab: activatePortalTab,
          ...nextActDependencies,
        },
        {
          pageCap: timing.nextActPageCap ?? MAX_SCAN_PAGES,
          attempts: timing.nextActAttempts ?? FORM_READ_ATTEMPTS,
          retryDelayMs: timing.nextActDelayMs ?? FORM_READ_DELAY_MS,
          requireCurrentIdentity: false,
        },
      );
      if (outcome?.ok !== true) return outcome;
      return {
        ok: true,
        action: outcome.already_open ? "already_open" : "open_act",
        screen: "form",
        waitingForFrame: false,
      };
    }

    let frames;
    try {
      frames = await portalFrames();
    } catch (error) {
      return { ok: false, code: "PORTAL_NOT_AVAILABLE", error: String(error?.message ?? error) };
    }
    if (frames.length === 0) {
      return { ok: false, code: "PORTAL_NOT_AVAILABLE", error: "Nenhuma aba autenticada da Área Restrita está aberta." };
    }
    const formAnswers = await askFrames({ type: MESSAGE_TYPES.READ_FORM }, frames);
    const exactForms = formAnswers.filter(
      (answer) => answer.response?.ok === true && answer.response.form &&
        sameIdentity(answer.response.form.identity, identity)
    );
    if (exactForms.length > 1) {
      return { ok: false, code: "FORM_AMBIGUOUS", error: `mais de uma moldura (${exactForms.length}) tem o formulário do ato` };
    }
    if (exactForms.length === 1) {
      return { ok: true, action: "already_open", screen: "form", waitingForFrame: false };
    }

    const screens = await askFrames({ type: MESSAGE_TYPES.SCAN_PAGE }, frames);
    const listFrames = screens.filter(
      (answer) => answer.response?.ok === true && answer.response.snapshot?.role === "list"
    );
    if (listFrames.length > 1) {
      return { ok: false, code: "LIST_AMBIGUOUS", error: `mais de uma moldura (${listFrames.length}) responde como lista` };
    }
    if (listFrames.length === 1) {
      const frame = listFrames[0];
      return openActInListFrame(identity, { tabId: frame.tabId, frameId: frame.frameId });
    }

    const interestedFrames = screens.filter(
      (answer) => answer.response?.ok === true && answer.response.snapshot?.role === "interested"
    );
    if (interestedFrames.length > 1) {
      return { ok: false, code: "INTERESTED_AMBIGUOUS", error: `mais de uma moldura (${interestedFrames.length}) mostra a seleção do interessado` };
    }
    if (interestedFrames.length === 1) {
      const frame = interestedFrames[0];
      try {
        return (await sendToFrame(frame.tabId, frame.frameId, {
          type: MESSAGE_TYPES.OPEN_ACT,
          payload: { identity },
        })) ?? { ok: false, code: "NAVIGATION_RESPONSE_MISSING" };
      } catch (error) {
        return { ok: false, code: "FRAME_UNREACHABLE", error: String(error?.message ?? error) };
      }
    }

    const wrongForms = formAnswers.filter(
      (answer) => answer.response?.ok === true && answer.response.form?.identity &&
        String(answer.response.form.identity.processKey ?? "") === String(identity.processKey ?? "")
    );
    if (wrongForms.length > 0) {
      return { ok: false, code: "FORM_IDENTITY_MISMATCH", error: "o formulário aberto pertence a outro interessado" };
    }
    const frameError = [...screens, ...formAnswers].find((answer) => answer.error);
    if (frameError) {
      return { ok: false, code: "FRAME_UNREACHABLE", error: frameError.error };
    }
    const refusalPriority = [
      "FORM_IDENTITY_MISMATCH",
      "FORM_AMBIGUOUS",
      "INTERESTED_AMBIGUOUS",
      "INTERESTED_NOT_FOUND",
      "ROW_ACTION_NOT_FOUND",
      "LIST_NOT_AVAILABLE",
      "SCREEN_NOT_NAVIGABLE",
    ];
    const refusals = [...screens, ...formAnswers]
      .map((answer) => answer.response?.code)
      .filter((code) => typeof code === "string");
    const code = refusalPriority.find((candidate) => refusals.includes(candidate));
    return code
      ? { ok: false, code }
      : { ok: false, code: "SCREEN_NOT_NAVIGABLE", screen: "unknown" };
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

  async function readCurrentPortalForm() {
    const forms = (await askFrames({ type: MESSAGE_TYPES.READ_FORM })).filter(
      (answer) => answer.response?.ok === true && answer.response.form
    );
    if (forms.length > 1) return { ok: false, code: "FORM_AMBIGUOUS" };
    if (forms.length === 0) return { ok: true, form: null };
    const found = forms[0];
    return { ok: true, form: found.response.form, tabId: found.tabId, frameId: found.frameId };
  }

  async function returnToList(current, identity) {
    try {
      return await sendToFrame(current.tabId, current.frameId, {
        type: MESSAGE_TYPES.RETURN_TO_LIST,
        payload: { identity },
      });
    } catch {
      return { ok: false, code: "RETURN_TO_LIST_FAILED" };
    }
  }

  async function readListPageForNextAct() {
    try {
      const frame = await findListFrame();
      const response = await sendToFrame(frame.tabId, frame.frameId, {
        type: MESSAGE_TYPES.SCAN_PAGE,
      });
      if (response?.ok !== true || response.snapshot?.role !== "list") {
        return { ok: false, code: "LIST_NOT_AVAILABLE" };
      }
      return { ok: true, frame, snapshot: response.snapshot };
    } catch (error) {
      return { ok: false, code: error?.code ?? "LIST_NOT_AVAILABLE" };
    }
  }

  async function advanceListPageForNextAct(frame, currentPage) {
    const expectedPage = currentPage + 1;
    for (let attempt = 0; attempt < pageAdvanceAttempts; attempt += 1) {
      let response;
      try {
        response = await sendToFrame(frame.tabId, frame.frameId, {
          type: MESSAGE_TYPES.LIST_PAGE,
          payload: { action: "next" },
        });
      } catch {
        response = null;
      }
      if (response?.ok === true) {
        const before = Number(response.page_before);
        const after = Number(response.page_after);
        if (Number.isInteger(before) && before !== currentPage) {
          return { ok: false, code: "PAGINATION_STALLED" };
        }
        if (Number.isInteger(after) && after !== expectedPage) {
          return { ok: false, code: "PAGINATION_STALLED" };
        }
        if (await waitForPageReady(frame, expectedPage)) {
          return { ok: true, page_after: expectedPage };
        }
      } else {
        return { ok: false, code: "PAGINATION_STALLED" };
      }
      if (attempt + 1 < pageAdvanceAttempts) await delay(pageAdvanceRetryDelayMs);
    }
    return { ok: false, code: "PAGINATION_STALLED" };
  }

  async function openExactNextTarget(identity, frame) {
    return openActInListFrame(identity, frame);
  }

  async function readExactTargetForm(identity) {
    const forms = (await askFrames({
      type: MESSAGE_TYPES.READ_FORM,
      payload: { identity },
    })).filter((answer) => answer.response?.ok === true && answer.response.form);
    if (forms.length > 1) return { ok: false, code: "FORM_AMBIGUOUS" };
    if (forms.length === 0) return { ok: false, code: "FORM_NOT_AVAILABLE" };
    const found = forms[0];
    if (!sameIdentity(found.response.form.identity, identity)) {
      return { ok: false, code: "TARGET_IDENTITY_MISMATCH" };
    }
    return {
      ok: true,
      form: found.response.form,
      tabId: found.tabId,
      frameId: found.frameId,
    };
  }

  async function activatePortalTab(tabId) {
    if (!Number.isInteger(tabId)) return { ok: false, code: "TARGET_TAB_ACTIVATION_FAILED" };
    try {
      await chromeApi.tabs.update(tabId, { active: true });
      return { ok: true };
    } catch {
      return { ok: false, code: "TARGET_TAB_ACTIVATION_FAILED" };
    }
  }

  async function openNextAct(payload) {
    return orchestrateNextAct(
      payload,
      {
        readCurrentForm: readCurrentPortalForm,
        returnToList,
        readListPage: readListPageForNextAct,
        advancePage: advanceListPageForNextAct,
        openAct: openExactNextTarget,
        readTargetForm: readExactTargetForm,
        activateTab: activatePortalTab,
        ...nextActDependencies,
      },
      {
        pageCap: timing.nextActPageCap ?? MAX_SCAN_PAGES,
        attempts: timing.nextActAttempts ?? FORM_READ_ATTEMPTS,
        retryDelayMs: timing.nextActDelayMs ?? FORM_READ_DELAY_MS,
      },
    );
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
        if (response?.ok === true && response.form) {
          matches.push({ form: response.form, frameId: frame.frameId });
        }
      } catch {
        // A frame that is navigating is simply not a candidate.
      }
    }
    if (matches.length === 1) {
      lastFormDiagnostics = formDiagnostics(tab, matches[0]);
      return { ok: true, form: matches[0].form, diagnostics: lastFormDiagnostics };
    }
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
        result = await executeCommand(outcome.command, {
          scanPortal,
          openAct,
          openNextAct,
          readForm,
          fillForm,
          ...(typeof api.renewCommandLease === "function"
            ? { renewLease: (commandId, claimToken) => api.renewCommandLease(commandId, claimToken) }
            : {}),
        });
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
    if (message?.type === MESSAGE_TYPES.MESA_STATUS) {
      api
        .status()
        .then((outcome) => sendResponse(outcome))
        .catch((error) => sendResponse({ ok: false, status: 0, error: String(error?.message ?? error) }));
      return true;
    }
    if (message?.type === MESSAGE_TYPES.REQUEST_MANUAL_FILL) {
      api
        .requestManualFill(manualFillPayload(message.payload))
        .then((outcome) => sendResponse(outcome))
        .catch((error) => sendResponse({ ok: false, status: 0, error: String(error?.message ?? error) }));
      return true;
    }
    if (message?.type === MESSAGE_TYPES.REQUEST_NEXT_ACT) {
      const identity = message.payload?.identity;
      if (
        typeof identity?.processKey !== "string" ||
        !identity.processKey.trim() ||
        typeof identity?.interestedNormalized !== "string" ||
        !identity.interestedNormalized.trim()
      ) {
        sendResponse({ ok: false, error: "current_identity_required" });
        return false;
      }
      api
        .requestNextAct({
          processKey: identity.processKey,
          interestedNormalized: identity.interestedNormalized,
          ...(typeof identity.portalActId === "string" && identity.portalActId.trim()
            ? { portalActId: identity.portalActId.trim() }
            : {}),
        })
        .then((outcome) => sendResponse(outcome))
        .catch((error) => sendResponse({ ok: false, status: 0, error: String(error?.message ?? error) }));
      return true;
    }
    if (message?.type === MESSAGE_TYPES.READ_NEXT_ACT_STATUS) {
      const commandId = Number(message.payload?.command_id);
      if (!Number.isSafeInteger(commandId) || commandId < 1) {
        sendResponse({ ok: false, error: "invalid_command_id" });
        return false;
      }
      Promise.resolve()
        .then(() => api.commandStatus(commandId))
        .then((outcome) => sendResponse(outcome))
        .catch((error) => sendResponse({ ok: false, status: 0, error: String(error?.message ?? error) }));
      return true;
    }
    if (message?.type === MESSAGE_TYPES.READ_CURRENT_FORM) {
      readCurrentForm()
        .then((outcome) => sendResponse(outcome))
        .catch((error) => sendResponse({ ok: false, error: String(error?.message ?? error) }));
      return true;
    }
    if (message?.type === MESSAGE_TYPES.RELIABILITY_STATUS) {
      api
        .reliabilityStatus()
        .then((outcome) => sendResponse(outcome))
        .catch((error) => sendResponse({ ok: false, status: 0, error: String(error?.message ?? error) }));
      return true;
    }
    if (message?.type === MESSAGE_TYPES.REPORT_AR1_ATTEMPT) {
      const code = String(message.payload?.code ?? "").trim().toUpperCase();
      if (!code) {
        sendResponse({ ok: false, error: "attempt_code_required" });
        return false;
      }
      Promise.resolve()
        .then(() => api.reportAr1Attempt({ code }))
        .then((outcome) => sendResponse(outcome))
        .catch((error) => sendResponse({ ok: false, status: 0, error: String(error?.message ?? error) }));
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

  return { poll, scanPortal, openAct, openNextAct, readForm, fillForm, readCurrentForm };
}

if (globalThis.chrome?.runtime?.onMessage?.addListener) {
  installRouter();
}
