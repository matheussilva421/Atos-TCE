/**
 * Temporary M2 helper that advances the Área Restrita list pagination.
 *
 * Pagination is the only navigation M2 is allowed to perform. The selectors
 * belong to ``lib/area-snapshot.js`` (single owner of portal knowledge); this
 * file only clicks the control that the scanner located. M5 moves the whole
 * behaviour into ``content/navigate.js``.
 */

(() => {
  "use strict";

  if (globalThis.__tcePagingInstalled === true) return;
  globalThis.__tcePagingInstalled = true;

  const runtime = globalThis.chrome?.runtime;
  if (!runtime?.onMessage?.addListener) return;

  runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || message.type !== "LIST_PAGE") return undefined;
    const scanner = globalThis.TCEAreaSnapshot;
    try {
      if (!scanner) throw new Error("area-snapshot.js is not loaded");
      const action = String(message.payload?.action ?? "next").toLowerCase();
      const control =
        action === "first"
          ? scanner.findFirstPageControl(globalThis.document)
          : scanner.findNextPageControl(globalThis.document);
      if (!control) {
        sendResponse({ ok: true, changed: false, reason: "no_control" });
        return true;
      }
      const before = scanner.pageInfo(globalThis.document).page;
      const legacyPlan = scanner.legacyPaginationPlan?.(globalThis.document, control);
      if (legacyPlan?.error) {
        sendResponse({
          ok: false,
          changed: false,
          code: legacyPlan.error.code,
          error: legacyPlan.error.message,
        });
        return true;
      }
      if (legacyPlan) {
        if (!scanner.submitLegacyPagination?.(globalThis.document, legacyPlan)) {
          sendResponse({
            ok: false,
            changed: false,
            code: "PAGINATION_SUBMIT_FAILED",
            error: "the legacy pagination form could not be submitted",
          });
          return true;
        }
        sendResponse({
          ok: true,
          changed: true,
          page_before: before,
          page_after: Number(legacyPlan.spec.page),
        });
        return true;
      }
      control.click();
      sendResponse({ ok: true, changed: true, page_before: before, page_after: before + 1 });
    } catch (error) {
      sendResponse({ ok: false, changed: false, error: String(error?.message ?? error) });
    }
    return true;
  });
})();
