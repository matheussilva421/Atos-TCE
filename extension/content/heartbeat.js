/**
 * Wakes the MV3 service worker while an authenticated Área Restrita tab is
 * open, so the Mesa's queued commands are picked up even when the side panel is
 * closed. The worker performing the authenticated loopback fetch is what makes
 * this a browser event rather than a timer that could be suspended.
 */

(() => {
  "use strict";

  if (globalThis.__tceHeartbeatInstalled === true) return;
  globalThis.__tceHeartbeatInstalled = true;

  // Kept in sync with HEARTBEAT_INTERVAL_MS in lib/protocol.js; a classic
  // content script cannot import a module, so the test suite asserts equality.
  const INTERVAL_MS = 1500;

  const runtime = globalThis.chrome?.runtime;
  if (!runtime?.sendMessage) return;

  let inFlight = false;
  const tick = async () => {
    if (inFlight) return;
    inFlight = true;
    try {
      await runtime.sendMessage({ type: "POLL_COMMANDS" });
    } catch {
      // No worker listening (or it was suspended): the next tick retries.
    } finally {
      inFlight = false;
    }
  };

  globalThis.setInterval(tick, INTERVAL_MS);
})();
