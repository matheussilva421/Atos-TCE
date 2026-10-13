/**
 * Explicit portal navigation for the Mesa's ``OPEN_ACT`` command and the
 * internal ``RETURN_TO_LIST`` message.
 *
 * Ported from the proven content/portal-navigation.js, reduced to what an
 * OPEN_ACT/READ_FORM cycle needs: locate the exact row on the list, open the
 * act, select the exact interested person, advance a page, or return to the
 * list through the one Phase 0-observed native tab.
 *
 * Side effects happen only when a command asks for them, and each function
 * returns a coded result instead of guessing: an unknown screen is reported,
 * never clicked. It clicks only the exact row/person/page controls or the
 * observed list tab after confirming the current form identity. The legacy
 * portal opens the act in a *sibling* tab/frame, so the caller is told
 * ``waitingForFrame`` and must look at the new frame.
 */

(() => {
  "use strict";

  const NATIVE_LIST_TAB_LABEL = "Proc./ Doc. Eletrônicos";
  const NATIVE_LIST_TAB_CLASS = "tabs-inner";

  function normalize(value) {
    const api = globalThis.TCEAreaSnapshot;
    return api ? api.normalizeInterested(value) : String(value ?? "").trim().toLowerCase();
  }

  function sameIdentity(left, right) {
    if (!left || !right || String(left.processKey) !== String(right.processKey)) return false;
    const leftActId = String(left.portalActId ?? left.portal_act_id ?? "").trim();
    const rightActId = String(right.portalActId ?? right.portal_act_id ?? "").trim();
    return leftActId && rightActId
      ? leftActId === rightActId
      : normalize(left.interestedNormalized) === normalize(right.interestedNormalized);
  }

  /** The form wins over every other role: an open, complete form is the target. */
  function screenOf(documentRef = globalThis.document) {
    if (globalThis.TCEFormReader?.readForm?.(documentRef)) return "form";
    const api = globalThis.TCEAreaSnapshot;
    return api ? api.detectDocumentRole(documentRef) : "unknown";
  }

  function clickControl(control) {
    if (typeof control?.click !== "function") return false;
    control.click();
    return true;
  }

  function defaultDependencies() {
    return {
      screenOf,
      formReader: globalThis.TCEFormReader ?? null,
      snapshot: globalThis.TCEAreaSnapshot ?? null,
      click: clickControl,
      findNativeListTab,
    };
  }

  /** Locate only the observed native list tab in the form frame's ancestors. */
  function findNativeListTab(documentRef) {
    const ancestorDocuments = [];
    const visitedWindows = new Set();
    let currentWindow = documentRef?.defaultView;
    while (currentWindow && !visitedWindows.has(currentWindow)) {
      visitedWindows.add(currentWindow);
      let parentWindow;
      try {
        parentWindow = currentWindow.parent;
      } catch {
        return { ok: false, code: "RETURN_CONTEXT_UNAVAILABLE" };
      }
      if (!parentWindow || parentWindow === currentWindow) break;
      try {
        const parentDocument = parentWindow.document;
        if (!parentDocument) return { ok: false, code: "RETURN_CONTEXT_UNAVAILABLE" };
        ancestorDocuments.push(parentDocument);
      } catch {
        return { ok: false, code: "RETURN_CONTEXT_UNAVAILABLE" };
      }
      currentWindow = parentWindow;
    }

    const matches = [];
    try {
      for (const ancestorDocument of ancestorDocuments) {
        for (const anchor of ancestorDocument.querySelectorAll("a")) {
          const classes = String(anchor.getAttribute?.("class") ?? "").split(/\s+/u);
          if (
            classes.includes(NATIVE_LIST_TAB_CLASS) &&
            normalize(anchor.textContent) === normalize(NATIVE_LIST_TAB_LABEL)
          ) {
            matches.push(anchor);
          }
        }
      }
    } catch {
      return { ok: false, code: "RETURN_CONTEXT_UNAVAILABLE" };
    }
    if (matches.length > 1) return { ok: false, code: "RETURN_CONTROL_AMBIGUOUS" };
    if (matches.length === 0) return { ok: false, code: "RETURN_CONTROL_NOT_FOUND" };
    return { ok: true, control: matches[0] };
  }

  /**
   * Open the act of one exact identity.
   *
   * Returns ``{ok, action, screen, waitingForFrame}`` on success and a coded
   * refusal otherwise. It never clicks a control that is not the requested
   * row, the requested person or the pagination control.
   */
  function openAct({ documentRef = globalThis.document, identity, deps = {} } = {}) {
    const helpers = { ...defaultDependencies(), ...deps };
    const screen = helpers.screenOf(documentRef);

    if (screen === "form") {
      const form = helpers.formReader?.readForm?.(documentRef);
      if (form && sameIdentity(form.identity, identity)) {
        return { ok: true, action: "already_open", screen, waitingForFrame: false };
      }
      return { ok: false, code: "FORM_IDENTITY_MISMATCH", screen };
    }

    if (screen === "buttons") {
      return { ok: true, action: "already_open", screen, waitingForFrame: false };
    }

    if (screen === "list") {
      const control = helpers.snapshot?.findActControl?.(documentRef, identity);
      if (!control) return { ok: false, code: "ROW_ACTION_NOT_FOUND", screen };
      if (!helpers.click(control)) return { ok: false, code: "ROW_ACTION_NOT_CLICKABLE", screen };
      return { ok: true, action: "open_act", screen, waitingForFrame: true };
    }

    if (screen === "interested") {
      const candidates = helpers.snapshot?.findInterestedRadioCandidates?.(documentRef, identity);
      if (Array.isArray(candidates) && candidates.length > 1) {
        return { ok: false, code: "INTERESTED_AMBIGUOUS", screen };
      }
      const radio = Array.isArray(candidates)
        ? candidates[0]
        : helpers.snapshot?.findInterestedRadio?.(documentRef, identity);
      if (!radio) return { ok: false, code: "INTERESTED_NOT_FOUND", screen };
      if (!helpers.click(radio)) return { ok: false, code: "INTERESTED_NOT_CLICKABLE", screen };
      return { ok: true, action: "select_interested", screen, waitingForFrame: true };
    }

    return { ok: false, code: "SCREEN_NOT_NAVIGABLE", screen };
  }

  /** Use the one Phase 0-proven native tab, after rereading the current form. */
  function returnToList({ documentRef = globalThis.document, identity, deps = {} } = {}) {
    const helpers = { ...defaultDependencies(), ...deps };
    const screen = helpers.screenOf(documentRef);
    if (screen !== "form") {
      return { ok: false, code: "CURRENT_FORM_NOT_AVAILABLE", screen };
    }

    let form;
    try {
      form = helpers.formReader?.readForm?.(documentRef);
    } catch {
      form = null;
    }
    if (!form?.identity) {
      return { ok: false, code: "CURRENT_FORM_NOT_AVAILABLE", screen };
    }
    if (!sameIdentity(form.identity, identity)) {
      return { ok: false, code: "CURRENT_IDENTITY_MISMATCH", screen };
    }

    let located;
    try {
      located = helpers.findNativeListTab(documentRef);
    } catch {
      return { ok: false, code: "RETURN_CONTEXT_UNAVAILABLE", screen };
    }
    if (located?.ok !== true || !located.control) {
      return {
        ok: false,
        code: located?.code ?? "RETURN_CONTROL_NOT_FOUND",
        screen,
      };
    }
    try {
      if (!helpers.click(located.control)) {
        return { ok: false, code: "RETURN_CONTROL_NOT_CLICKABLE", screen };
      }
    } catch {
      return { ok: false, code: "RETURN_CONTROL_FAILED", screen };
    }
    return { ok: true, action: "return_to_list", screen, waitingForList: true };
  }

  /**
   * Advance one list page using the proven pagination control. The caller owns
   * the loop and the page budget; this only reports whether it advanced.
   */
  function nextPage({ documentRef = globalThis.document, deps = {} } = {}) {
    const helpers = { ...defaultDependencies(), ...deps };
    const info = helpers.snapshot?.pageInfo?.(documentRef);
    if (info && info.total_pages > 0 && info.page >= info.total_pages) {
      return { ok: true, advanced: false, reason: "last_page" };
    }
    const control = helpers.snapshot?.findNextPageControl?.(documentRef);
    if (!control) return { ok: true, advanced: false, reason: "no_control" };
    if (!helpers.click(control)) return { ok: false, code: "PAGINATION_NOT_CLICKABLE" };
    return { ok: true, advanced: true, reason: null };
  }

  globalThis.TCENavigate = Object.freeze({
    openAct,
    returnToList,
    nextPage,
    screenOf,
    sameIdentity,
  });

  const runtime = globalThis.chrome?.runtime;
  if (runtime?.onMessage?.addListener) {
    runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (!message) return undefined;
      if (message.type === "RETURN_TO_LIST") {
        try {
          sendResponse(
            returnToList({
              documentRef: globalThis.document,
              identity: message.payload?.identity ?? {},
            })
          );
        } catch (error) {
          sendResponse({
            ok: false,
            code: "RETURN_CONTROL_FAILED",
            error: String(error?.message ?? error),
          });
        }
        return true;
      }
      if (message.type !== "OPEN_ACT") return undefined;
      try {
        sendResponse(
          openAct({ documentRef: globalThis.document, identity: message.payload?.identity ?? {} })
        );
      } catch (error) {
        sendResponse({ ok: false, code: "NAVIGATION_FAILED", error: String(error?.message ?? error) });
      }
      return true;
    });
  }
})();
