/**
 * Single owner of the bridge vocabulary between the extension and the Mesa.
 *
 * The protocol is intentionally tiny and has **no** command that finishes an
 * act: there is no SUBMIT, SEND, AUTO_SUBMIT, COMPLEMENT_ACT or FINALIZE type,
 * and ``FORBIDDEN_COMMAND_TYPES`` exists so a test can prove that absence.
 */

/** Content-script ↔ service-worker messages. */
export const MESSAGE_TYPES = Object.freeze({
  POLL_COMMANDS: "POLL_COMMANDS",
  SCAN_PAGE: "SCAN_PAGE",
  LIST_PAGE: "LIST_PAGE",
  OPEN_ACT: "OPEN_ACT",
  READ_FORM: "READ_FORM",
  FILL_FORM: "FILL_FORM",
  READ_CURRENT_FORM: "READ_CURRENT_FORM",
});

/** Command types the Mesa may queue. There is still no submit type. */
export const COMMAND_TYPES = Object.freeze({
  STATUS: "STATUS",
  SCAN_AREA: "SCAN_AREA",
  OPEN_ACT: "OPEN_ACT",
  READ_FORM: "READ_FORM",
  FILL_FORM: "FILL_FORM",
});

/**
 * Names that must never appear in this protocol. The test suite asserts that
 * none of them is declared, and that no shipped source mentions the runtime
 * switches of the retired auto-submit flow.
 */
export const FORBIDDEN_COMMAND_TYPES = Object.freeze([
  "SUBMIT",
  "SEND",
  "AUTO_SUBMIT",
  "COMPLEMENT_ACT",
  "FINALIZE",
]);

export const PORTAL_ORIGIN = "https://novaarearestrita.tce.rn.gov.br";
export const MESA_ORIGIN = "http://127.0.0.1:18743";

/**
 * A content script wakes the MV3 worker with this cadence while an
 * authenticated portal tab is open; ``content/heartbeat.js`` repeats the value
 * because a classic content script cannot import this module.
 */
export const HEARTBEAT_INTERVAL_MS = 1500;

/** Hard ceiling so a portal loop can never hang the worker. */
export const MAX_SCAN_PAGES = 50;

export function isSupportedCommand(type) {
  return Object.hasOwn(COMMAND_TYPES, String(type ?? "").trim().toUpperCase());
}

export function isPortalUrl(url) {
  return typeof url === "string" && url.startsWith(PORTAL_ORIGIN);
}
