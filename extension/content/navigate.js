/**
 * Explicit portal navigation for the Mesa's ``OPEN_ACT`` command.
 *
 * Ported from the proven content/portal-navigation.js, reduced to what an
 * OPEN_ACT/READ_FORM cycle needs: locate the exact row on the list, open the
 * act, select the exact interested person, and know how to advance a list page.
 *
 * Side effects happen only when a command asks for them, and each function
 * returns a coded result instead of guessing: an unknown screen is reported,
 * never clicked. The legacy portal opens the act in a *sibling* tab/frame, so
 * the caller is told ``waitingForFrame`` and must look at the new frame.
 */

(() => {
  "use strict";

  function normalize(value) {
    const api = globalThis.TCEAreaSnapshot;
    return api ? api.normalizeInterested(value) : String(value ?? "").trim().toLowerCase();
  }

  function sameIdentity(left, right) {
    return (
      Boolean(left && right) &&
      String(left.processKey) === String(right.processKey) &&
      normalize(left.interestedNormalized) === normalize(right.interestedNormalized)
    );
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
    };
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
      const radio = helpers.snapshot?.findInterestedRadio?.(documentRef, identity);
      if (!radio) return { ok: false, code: "INTERESTED_NOT_FOUND", screen };
      if (!helpers.click(radio)) return { ok: false, code: "INTERESTED_NOT_CLICKABLE", screen };
      return { ok: true, action: "select_interested", screen, waitingForFrame: true };
    }

    return { ok: false, code: "SCREEN_NOT_NAVIGABLE", screen };
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

  globalThis.TCENavigate = Object.freeze({ openAct, nextPage, screenOf, sameIdentity });

  const runtime = globalThis.chrome?.runtime;
  if (runtime?.onMessage?.addListener) {
    runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (!message || message.type !== "OPEN_ACT") return undefined;
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
