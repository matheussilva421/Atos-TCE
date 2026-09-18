/**
 * Content-script adapter for the read-only Área Restrita scanner.
 *
 * Its whole job is to answer a ``SCAN_PAGE`` message with one sanitized
 * snapshot produced by ``lib/area-snapshot.js``. It performs no navigation, no
 * form write and no credential access.
 */

(() => {
  "use strict";

  if (globalThis.__tceScanAreaInstalled === true) return;
  globalThis.__tceScanAreaInstalled = true;

  const runtime = globalThis.chrome?.runtime;
  if (!runtime?.onMessage?.addListener) return;

  runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || message.type !== "SCAN_PAGE") return undefined;
    try {
      if (!globalThis.TCEAreaSnapshot) throw new Error("area-snapshot.js is not loaded");
      sendResponse({ ok: true, snapshot: globalThis.TCEAreaSnapshot.scan(globalThis.document) });
    } catch (error) {
      sendResponse({ ok: false, error: String(error?.message ?? error) });
    }
    return true;
  });
})();
