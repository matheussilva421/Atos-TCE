import { MESSAGE_TYPES, createMessage } from "../lib/messages.js";
import {
  validateAutomationIdentity,
  validateAutomationRunSpec,
  validateAutomationSnapshot,
} from "../lib/automation-schema.js";
import { AUTOMATION_FIELDS, prepareAutomaticAct } from "../lib/automation-preflight.js";

export const PORTAL_FRAME_REGISTRATIONS_STORAGE_KEY = "portal-frame-registrations:v1";
export const SUBMIT_FRAME_REGISTRATIONS_STORAGE_KEY = "portal-submit-frame-registrations:v1";
const ACTIVE_STATUSES = new Set(["discovering", "running", "paused"]);
const REHYDRATABLE_ITEM_STATES = new Set([
  "queued",
  "discovered",
  "eligibility_confirmed",
  "acquisition_pending",
  "downloaded",
  "ocr_pending",
  "ocr_ready",
  "ready_for_preflight",
]);
const TERMINAL_ITEM_STATES = new Set([
  "prepared",
  "filled",
  "awaiting_send_confirmation",
  "send_intent",
  "send_issued",
  "outcome_observed",
  "confirmed",
  "pending",
  "failed",
  "unconfirmed",
  "blocked",
]);
const PROCESS_KEY_RE = /^\d+\/\d{4}$/u;
const AREA_CLASSIFICATIONS = new Set([
  "PRECISA_COMPLEMENTAR",
  "ATO_COMPLEMENTADO",
  "NAO_ENCONTRADO_AREA_RESTRITA",
  "AMBIGUO",
  "BLOQUEADO",
]);
const AUTO_SUBMIT_TTL_MS = 15_000;
const UNRECOGNIZED_PORTAL_SCREEN_REASON = "portal screen not recognized; manual intervention required";
/*
 * The act screen is the only surface where the queue may write fields. It is
 * reached either as the form document itself or as the sibling buttons
 * document that submits it.
 */
const ACT_SURFACE_ROLES = new Set(["form", "buttons"]);

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function clone(value) {
  return value === undefined ? undefined : structuredClone(value);
}

function normalizeInterested(value) {
  return typeof value === "string"
    ? value.normalize("NFKD").replace(/\p{M}+/gu, "").toLowerCase().replace(/\s+/gu, " ").trim()
    : "";
}

function identityKey(identity) {
  return `${identity?.processKey ?? ""}\u0000${identity?.interestedNormalized ?? ""}`;
}

function areaClassification(candidate) {
  if (AREA_CLASSIFICATIONS.has(candidate?.classification)) return candidate.classification;
  if (candidate?.needsComplement === true
    && candidate?.actionSignature?.kind === "red_complement_icon") return "PRECISA_COMPLEMENTAR";
  // v2 snapshots predate the semantic control signature. Keep their
  // analysis compatible; v3 observations produced by the content script
  // always carry the red-icon evidence before becoming eligible.
  if (candidate?.needsComplement === true) return "PRECISA_COMPLEMENTAR";
  const observed = normalizeInterested(candidate?.actionObserved ?? candidate?.action_observed ?? "");
  if (observed === "ato complementado" || observed.includes("ato complementado")) return "ATO_COMPLEMENTADO";
  return "AMBIGUO";
}

function sameAreaEvidence(left, right) {
  return left?.portalActId === right?.portalActId
    && left?.needsComplement === right?.needsComplement
    && left?.classification === right?.classification
    && left?.actionObserved === right?.actionObserved
    && JSON.stringify(sortKeys(left?.actionSignature ?? null)) === JSON.stringify(sortKeys(right?.actionSignature ?? null));
}

function eventId(prefix = "event") {
  return `${prefix}-${Date.now()}`;
}

function epochMilliseconds(value) {
  if (typeof value === "number" && Number.isFinite(value)) return Math.trunc(value);
  const parsed = Date.parse(String(value ?? ""));
  return Number.isFinite(parsed) ? parsed : Date.now();
}

function statusToPublic(state) {
  return clone({
    runId: state.runId,
    run_id: state.runId,
    status: state.status,
    revision: state.revision,
    tabId: state.tabId,
    sector: state.sector,
    sourceScope: state.sourceScope,
    source_scope: state.sourceScope,
    mode: state.mode,
    marker: state.marker,
    autoSubmit: state.autoSubmit,
    pilotIdentity: state.pilotIdentity,
    queueFrozen: state.queueFrozen,
    currentIdentity: state.currentIdentity,
    pausedReason: state.pausedReason,
    totals: state.totals,
    frame: state.frame,
    submitFrame: state.submitFrame,
    items: state.queue.map((identity, index) => {
      const knownState = state.itemStates?.get(identityKey(identity));
      const isCurrent = state.currentIdentity && identityKey(state.currentIdentity) === identityKey(identity);
      return {
        item_id: itemId(identity),
        ordinal: index + 1,
        identity: clone(identity),
        state: isCurrent ? "active" : knownState ?? "queued",
      };
    }),
    simulation: {
      is_simulated: state.autoSubmit !== true,
      real_send_enabled: state.autoSubmit === true,
      notice: state.autoSubmit === true
        ? "Envio externo opt-in; cada comando exige qualificação local e resultado observado."
        : "Navegação sintética/controlada; não comprova envio no portal real.",
    },
  });
}

function snapshotStatus(state, snapshot) {
  if (!isRecord(snapshot)) return;
  if (typeof snapshot.status === "string") state.status = snapshot.status;
  if (Number.isSafeInteger(snapshot.revision)) state.revision = snapshot.revision;
  if (typeof snapshot.run_id === "string") state.runId = snapshot.run_id;
  if (Array.isArray(snapshot.items) && (snapshot.items.length > 0 || state.queue.length === 0)) {
    const itemStates = new Map();
    for (const item of snapshot.items) {
      const identity = resolvedIdentity(item?.identity);
      if (identity && typeof item?.state === "string") itemStates.set(identityKey(identity), item.state);
    }
    state.itemStates = itemStates;
  }
}

function resolvedIdentity(candidate) {
  if (!isRecord(candidate)) return null;
  const processKey = typeof candidate.processKey === "string" ? candidate.processKey : "";
  const interestedNormalized = typeof candidate.interestedNormalized === "string"
    ? normalizeInterested(candidate.interestedNormalized)
    : "";
  if (!PROCESS_KEY_RE.test(processKey) || !interestedNormalized) return null;
  const result = {
    processKey,
    interestedNormalized,
    portalActId: candidate.portalActId ?? null,
  };
  try {
    return validateAutomationIdentity(result);
  } catch {
    return null;
  }
}

function rehydratedIdentity(candidate) {
  if (!isRecord(candidate)) return null;
  return resolvedIdentity(Object.hasOwn(candidate, "process_key")
    ? {
      processKey: candidate.process_key,
      interestedNormalized: candidate.interested_normalized,
      portalActId: candidate.portal_act_id ?? null,
    }
    : candidate);
}

function identityFromAction(action) {
  return resolvedIdentity(action?.identity);
}

function isPortalSnapshot(value) {
  return isRecord(value)
    && typeof value.role === "string"
    && Number.isSafeInteger(value.generation)
    && Array.isArray(value.identities)
    && Array.isArray(value.actions);
}

function snapshotFromResponse(response) {
  if (response?.ok !== true) return null;
  const candidate = response.payload?.snapshot ?? response.payload;
  return isPortalSnapshot(candidate) ? candidate : null;
}

function staleGenerationReport(response, attemptGeneration) {
  if (response?.error?.code !== "STALE_GENERATION") return null;
  const live = response?.generation;
  if (!Number.isSafeInteger(live) || live < 1 || live === attemptGeneration) return null;
  return live;
}

function navigationFailureReason(response) {
  const code = response?.error?.code;
  if (code === "TAB_CLOSED") return "tab closed";
  /*
   * The act screen repaints itself while it boots, so a generation that is
   * still moving after the navigation retry is a screen changing under the
   * run rather than a lost frame, and the operator needs that distinction.
   */
  if (code === "STALE_GENERATION") return "portal screen changed under the run; manual intervention required";
  return "portal frame unavailable";
}

function actionFor(snapshot, action, identity = null) {
  return (snapshot?.actions ?? []).find((candidate) => (
    candidate?.action === action
    && candidate.enabled !== false
    && (identity === null
      || identityKey(identityFromAction(candidate)) === identityKey(identity)
      || (action === "return_list" && identityFromAction(candidate) === null))
  )) ?? null;
}

function resumeIdentityFromActSnapshot(snapshot) {
  // A "Complementar Ato" document publishes the canonical identity of the
  // interested party the portal already has selected on its return_list action.
  // Resuming a restarted run reads that identity instead of inventing one.
  if (snapshot?.role !== "form" && snapshot?.role !== "buttons") return null;
  for (const candidate of snapshot.actions ?? []) {
    if (candidate?.action !== "return_list" || candidate.enabled === false) continue;
    const identity = identityFromAction(candidate);
    if (identity) return identity;
  }
  return null;
}

function formSnapshotFromResponse(response) {
  if (response?.ok !== true || !isRecord(response.payload)) return null;
  const candidate = response.payload.snapshot ?? response.payload;
  if (!isRecord(candidate)
    || !isRecord(candidate.process)
    || !isRecord(candidate.interested)
    || !isRecord(candidate.options)
    || !isRecord(candidate.fields)) return null;
  return candidate;
}

function commandFormFrame(command) {
  return Number.isSafeInteger(command?.form_frame_id)
    ? command.form_frame_id
    : command?.frame_id ?? null;
}

function formIdentity(snapshot) {
  const processKey = snapshot?.process?.key;
  const interestedNormalized = snapshot?.interested?.normalized;
  if (typeof processKey !== "string" || typeof interestedNormalized !== "string") return null;
  return { processKey, interestedNormalized };
}

function sameCanonicalIdentity(left, right) {
  return Boolean(left && right)
    && left.processKey === right.processKey
    && left.interestedNormalized === right.interestedNormalized;
}

function decorateFormSnapshot(snapshot, portalSnapshot, frameId) {
  const identity = formIdentity(snapshot);
  const generation = portalSnapshot?.generation;
  return {
    ...clone(snapshot),
    role: "form",
    identity,
    generation,
    frameId,
    currentGeneration: generation,
    currentFrameId: frameId,
  };
}

function itemId(identity) {
  return identity?.portalActId || identity?.processKey || "";
}

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (!isRecord(value)) return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortKeys(value[key])]));
}

  async function sha256Hex(value) {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new Error("SHA-256 indisponível para evidência de automação");
  const bytes = new TextEncoder().encode(JSON.stringify(sortKeys(value)));
  const digest = await subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function safeLegalDecision(value) {
  if (!isRecord(value)) return null;
  return Object.fromEntries(["status", "method", "rule_id", "option_value", "rules_version"]
    .filter((key) => typeof value[key] === "string")
    .map((key) => [key, value[key]]));
}

function safeMatchKinds(value) {
  if (!isRecord(value)) return {};
  return Object.fromEntries(AUTOMATION_FIELDS.map((field) => [field, value[field]]));
}

function safeCitation(value) {
  if (typeof value === "string" && value.trim()) return value.trim().slice(0, 512);
  if (!isRecord(value)) return null;
  const allowed = ["process", "event", "page", "document", "source", "dataset_sha256", "context_hash", "signal", "read", "status", "reason"];
  const result = Object.fromEntries(Object.entries(value)
    .filter(([key, child]) => allowed.includes(key)
      && (typeof child === "string" || typeof child === "number" || typeof child === "boolean"))
    .map(([key, child]) => [key, typeof child === "string" ? child.slice(0, 512) : child]));
  return Object.keys(result).length > 0 ? result : null;
}

function confirmationCitations(record, identity, datasetSha256, contextHash, outcomeEvidence) {
  const citations = [];
  for (const field of Object.values(record?.fields ?? {})) {
    const citation = safeCitation(field?.citation);
    if (citation !== null) citations.push(citation);
  }
  citations.push({ source: "dataset", process: identity.processKey, dataset_sha256: datasetSha256 });
  if (contextHash) citations.push({ source: "legal-context", process: identity.processKey, context_hash: contextHash });
  const outcome = safeCitation(outcomeEvidence);
  if (outcome !== null) citations.push({ source: "portal-outcome", ...outcome });
  return citations.slice(0, 20);
}

function fieldStatus(field) {
  if (!isRecord(field)) return "missing";
  if (field.disabled === true) return "disabled";
  if (field.readOnly === true) return "readOnly";
  return field.value ? "present" : "empty";
}

async function fieldEvidence(snapshot, values, statuses = {}) {
  const evidence = {};
  for (const field of AUTOMATION_FIELDS) {
    const fieldState = snapshot?.fields?.[field];
    const value = values?.[field] ?? fieldState?.value ?? "";
    evidence[field] = {
      status: statuses[field] ?? fieldStatus(fieldState),
      valueHash: await sha256Hex(String(value)),
      optionsHash: await sha256Hex(snapshot?.options?.[field] ?? []),
      disabled: fieldState?.disabled === true,
      readOnly: fieldState?.readOnly === true,
      redacted: true,
    };
  }
  return evidence;
}

async function fieldResults(before, after, preparation) {
  const expected = expectedFieldValuesForEvidence(before, preparation);
  return Object.fromEntries(await Promise.all(AUTOMATION_FIELDS.map(async (field) => {
    const actual = after?.fields?.[field]?.value ?? "";
    return [field, {
      status: String(actual) === String(expected[field]) ? "verified" : "mismatch",
      expectedHash: await sha256Hex(String(expected[field] ?? "")),
      actualHash: await sha256Hex(String(actual)),
      redacted: true,
    }];
  })));
}

function expectedFieldValuesForEvidence(before, preparation) {
  return Object.fromEntries(AUTOMATION_FIELDS.map((field) => [
    field,
    Object.hasOwn(preparation.fields, field)
      ? preparation.fields[field]
      : preparation.preserved[field] ?? before.fields[field]?.value ?? "",
  ]));
}

function contextEvidence(context) {
  if (!isRecord(context)) return null;
  const result = Object.fromEntries(["schema_version", "dataset_sha256", "process_key", "interested_normalized", "resolution_status"]
    .filter((key) => context[key] !== undefined)
    .map((key) => [key, context[key]]));
  for (const key of ["context_revision", "rules_version"]) {
    if (context[key] !== undefined) result[key] = context[key];
  }
  return result;
}

function eventPrefix(value) {
  const normalized = String(value ?? "run").replace(/[^A-Za-z0-9._:/-]/gu, "-");
  return normalized || "run";
}

export function createAutomationController({
  chromeApi,
  bridge,
  ranker = null,
  resolveAutomaticAct = null,
  clock = {},
} = {}) {
  if (!chromeApi?.tabs?.sendMessage) throw new TypeError("createAutomationController requires chromeApi.tabs.sendMessage");
  if (!bridge?.createAutomationRun || !bridge?.controlAutomationRun) {
    throw new TypeError("createAutomationController requires an automation bridge");
  }
  if (resolveAutomaticAct !== null && typeof resolveAutomaticAct !== "function") {
    throw new TypeError("resolveAutomaticAct must be a function when provided");
  }

  const now = typeof clock === "function" ? clock : clock.now ?? (() => Date.now());
  const session = chromeApi.storage?.session;
  const frames = new Map();
  const submitFrames = new Map();
  let frameLoadPromise = null;
  let framePersistPromise = Promise.resolve();
  let inFlight = null;
  let pendingPortalSnapshot = null;
  let expectedNavigation = null;
  let navigationToken = 0;
  let messageSequence = 0;
  let eventSequence = 0;
  let state = {
    runId: null,
    status: "stopped",
    revision: 0,
    tabId: null,
    sector: null,
    sourceScope: null,
    mode: "batch",
    marker: null,
    autoSubmit: false,
    pilotIdentity: null,
    queueFrozen: false,
    currentIdentity: null,
    pausedReason: null,
    frame: null,
    submitFrame: null,
    queue: [],
    itemStates: new Map(),
    areaObservations: new Map(),
    seenIdentities: new Set(),
    completedIdentities: new Set(),
    totals: { discovered: 0, unique: 0, pending: 0 },
    eventPrefix: "run",
  };

  async function loadFrames() {
    if (!frameLoadPromise) {
      frameLoadPromise = (async () => {
        if (typeof session?.get !== "function") return;
        const stored = await session.get([
          PORTAL_FRAME_REGISTRATIONS_STORAGE_KEY,
          SUBMIT_FRAME_REGISTRATIONS_STORAGE_KEY,
        ]);
        const entries = stored?.[PORTAL_FRAME_REGISTRATIONS_STORAGE_KEY];
        if (Array.isArray(entries)) {
          for (const entry of entries) {
            if (!isRecord(entry) || !Number.isSafeInteger(entry.tabId) || !Number.isSafeInteger(entry.frameId)) continue;
            frames.set(`${entry.tabId}:${entry.frameId}`, clone(entry));
          }
        }
        const submitEntries = stored?.[SUBMIT_FRAME_REGISTRATIONS_STORAGE_KEY];
        if (Array.isArray(submitEntries)) {
          for (const entry of submitEntries) {
            if (!isRecord(entry)
              || !Number.isSafeInteger(entry.tabId) || entry.tabId < 0
              || !Number.isSafeInteger(entry.frameId) || entry.frameId < 0) continue;
            submitFrames.set(`${entry.tabId}:${entry.frameId}`, clone(entry));
          }
        }
      })();
    }
    return frameLoadPromise;
  }

  function persistFrames() {
    if (typeof session?.set !== "function") return Promise.resolve();
    const entries = [...frames.values()].sort((left, right) => left.tabId - right.tabId || left.frameId - right.frameId);
    const submitEntries = [...submitFrames.values()].sort((left, right) => left.tabId - right.tabId || left.frameId - right.frameId);
    framePersistPromise = framePersistPromise.catch(() => undefined).then(() => session.set({
      [PORTAL_FRAME_REGISTRATIONS_STORAGE_KEY]: entries,
      [SUBMIT_FRAME_REGISTRATIONS_STORAGE_KEY]: submitEntries,
    }));
    return framePersistPromise;
  }

  function refreshSubmitFrame(tabId = state.tabId) {
    const candidates = [...submitFrames.values()].filter((entry) => entry.tabId === tabId);
    state.submitFrame = candidates.length === 1
      ? {
        tabId: candidates[0].tabId,
        frameId: candidates[0].frameId,
        buttonId: candidates[0].buttonId ?? null,
      }
      : null;
    return candidates;
  }

  async function handleSubmitFrameReady(input = {}) {
    if (!isRecord(input)
      || !Number.isSafeInteger(input.tabId) || input.tabId < 0
      || !Number.isSafeInteger(input.frameId) || input.frameId < 0
      || (input.buttonId !== null && input.buttonId !== undefined && typeof input.buttonId !== "string")) {
      return statusToPublic(state);
    }
    submitFrames.set(`${input.tabId}:${input.frameId}`, {
      tabId: input.tabId,
      frameId: input.frameId,
      buttonId: input.buttonId ?? null,
    });
    await loadFrames();
    if (state.tabId === input.tabId) refreshSubmitFrame(input.tabId);
    await persistFrames();
    return statusToPublic(state);
  }

  function registerFrame(tabId, frameId, snapshot) {
    if (!Number.isSafeInteger(tabId) || tabId < 0 || !Number.isSafeInteger(frameId) || frameId < 0 || !isPortalSnapshot(snapshot)) return;
    const registration = {
      tabId,
      frameId,
      role: snapshot.role,
      generation: snapshot.generation,
      sector: snapshot.sector ?? null,
      source_scope: snapshot.source_scope ?? null,
      observedAt: now(),
    };
    frames.set(`${tabId}:${frameId}`, registration);
    state.frame = {
      frameId,
      role: snapshot.role,
      generation: snapshot.generation,
      sector: snapshot.sector ?? null,
      source_scope: snapshot.source_scope ?? null,
    };
    void persistFrames().catch(() => undefined);
  }

  /*
   * The gate reports the generation the frame is actually on. Recording it
   * keeps the registry from handing the next navigation a value the portal has
   * already left behind, which would cost another rejection.
   */
  function noteFrameGeneration(tabId, frameId, generation) {
    if (!Number.isSafeInteger(tabId) || tabId < 0 || !Number.isSafeInteger(frameId) || frameId < 0) return;
    if (!Number.isSafeInteger(generation) || generation < 1) return;
    const registration = frames.get(`${tabId}:${frameId}`);
    if (registration) {
      registration.generation = generation;
      registration.observedAt = now();
    }
    if (state.tabId === tabId && state.frame?.frameId === frameId) state.frame.generation = generation;
    void persistFrames().catch(() => undefined);
  }

  function invalidateFrames(tabId) {
    for (const key of [...frames.keys()]) {
      if (key.startsWith(`${tabId}:`)) frames.delete(key);
    }
    if (state.tabId === tabId) state.frame = null;
    for (const key of [...submitFrames.keys()]) {
      if (key.startsWith(`${tabId}:`)) submitFrames.delete(key);
    }
    if (state.tabId === tabId) refreshSubmitFrame(tabId);
    void persistFrames().catch(() => undefined);
  }

  function setPaused(reason) {
    state.status = "paused";
    state.pausedReason = reason;
  }

  async function pauseAndPersist(reason, pauseEventId) {
    setPaused(reason);
    if (!state.runId || typeof bridge.controlAutomationRun !== "function") return statusToPublic(state);
    try {
      const result = await bridge.controlAutomationRun(state.runId, {
        action: "pause",
        eventId: pauseEventId ?? eventId("pause"),
        expectedRevision: state.revision,
      });
      snapshotStatus(state, result);
    } catch {
      // Keep the local controller fail-closed if the persistence bridge is unavailable.
    }
    state.status = "paused";
    state.pausedReason = reason;
    return statusToPublic(state);
  }

  function recordAreaObservations(snapshot) {
    for (const candidate of snapshot.identities ?? []) {
      const rawKey = identityKey(candidate);
      if (!state.areaObservations.has(rawKey) && candidate?.processKey) {
        state.areaObservations.set(rawKey, {
          candidate: clone(candidate),
          source_scope: snapshot.source_scope ?? null,
          marker: clone(snapshot.marker),
        });
      } else if (candidate?.processKey && !state.areaObservations.get(rawKey)?.conflict) {
        const existing = state.areaObservations.get(rawKey);
        if (existing && !sameAreaEvidence(existing.candidate, candidate)) {
          state.areaObservations.set(rawKey, {
            candidate: {
              processKey: candidate.processKey,
              interestedNormalized: null,
              portalActId: null,
              pending: true,
            },
            source_scope: snapshot.source_scope ?? null,
            marker: clone(snapshot.marker),
            conflict: true,
          });
        }
      }
    }
  }

  function collectSnapshot(snapshot) {
    if (state.queueFrozen) return;
    recordAreaObservations(snapshot);
    for (const candidate of snapshot.identities ?? []) {
      state.totals.discovered += 1;
      const rawKey = identityKey(candidate);
      if (state.seenIdentities.has(rawKey)) continue;
      state.seenIdentities.add(rawKey);
      state.totals.unique += 1;
      const identity = resolvedIdentity(candidate);
      if (!identity) {
        state.totals.pending += 1;
        continue;
      }
      if (state.marker && candidate.needsComplement !== true) {
        state.totals.pending += 1;
        continue;
      }
      state.queue.push(identity);
    }
  }

  async function analysisRows(spec) {
    const requestedKeys = Array.isArray(spec.inputKeys) && spec.inputKeys.length > 0
      ? [...spec.inputKeys]
      : [...new Set([...state.areaObservations.values()]
        .map((observation) => observation.candidate?.processKey)
        .filter((key) => typeof key === "string" && PROCESS_KEY_RE.test(key)))];
    const observationsByProcess = new Map();
    for (const observation of state.areaObservations.values()) {
      const key = observation.candidate?.processKey;
      if (!PROCESS_KEY_RE.test(String(key ?? ""))) continue;
      const observations = observationsByProcess.get(key) ?? [];
      observations.push(observation);
      observationsByProcess.set(key, observations);
    }
    const rows = [];
    for (const processKey of requestedKeys) {
      const observations = observationsByProcess.get(processKey) ?? [];
      const firstObservation = observations[0] ?? null;
      const marker = isRecord(firstObservation?.marker) ? firstObservation.marker : {
        label: spec.marker,
        value: spec.markerValue,
      };
      const rowObservations = observations.length === 0
        ? [null]
        : observations;
      for (const observation of rowObservations) {
        const candidate = observation?.candidate ?? null;
        const identity = resolvedIdentity(candidate);
        const classification = observation === null
          ? "NAO_ENCONTRADO_AREA_RESTRITA"
          : identity
            ? areaClassification(candidate)
            : "AMBIGUO";
        const actionSignature = classification === "PRECISA_COMPLEMENTAR"
          && isRecord(candidate?.actionSignature)
          ? clone(candidate.actionSignature)
          : null;
        const actionObserved = classification === "PRECISA_COMPLEMENTAR"
          ? "Complementar Ato"
          : classification === "ATO_COMPLEMENTADO"
            ? "Ato Complementado"
            : null;
        const snapshotHash = await sha256Hex({
          source_scope: spec.sourceScope,
          marker,
          process_key: processKey,
          identity: candidate,
          classification,
        });
        rows.push({
          process_key: processKey,
          interested_key: identity?.interestedNormalized ?? null,
          area_restrita: {
            scope: spec.sourceScope,
            marker_label: marker.label,
            marker_value: marker.value,
            classification,
            needs_complement: classification === "PRECISA_COMPLEMENTAR",
            action_observed: actionObserved,
            action_signature: actionSignature,
            snapshot_hash: snapshotHash,
          },
        });
      }
    }
    return rows;
  }

  function markerMatches(snapshot, expectedMarker, expectedValue = null) {
    return typeof expectedMarker === "string"
      && expectedMarker.trim() !== ""
      && normalizeInterested(snapshot?.marker?.label) === normalizeInterested(expectedMarker)
      && (expectedValue === null || snapshot?.marker?.value === expectedValue);
  }

  async function sendPortalMessage(tabId, type, payload, frameId = null, requestId = null) {
    const resolvedRequestId = requestId ?? `${state.eventPrefix}-${String(now())}-${String(++messageSequence)}`;
    const message = createMessage(type, payload, resolvedRequestId);
    const options = Number.isSafeInteger(frameId) && frameId >= 0 ? { frameId } : undefined;
    const response = options === undefined
      ? await chromeApi.tabs.sendMessage(tabId, message)
      : await chromeApi.tabs.sendMessage(tabId, message, options);
    return response;
  }

  async function sendPortalMessageBounded(tabId, type, payload, frameId, requestId, timeoutMs = 750) {
    let timer = null;
    try {
      return await Promise.race([
        sendPortalMessage(tabId, type, payload, frameId, requestId),
        new Promise((_, reject) => {
          timer = setTimeout(() => {
            const error = new Error("portal frame message timed out");
            error.code = "PORTAL_MESSAGE_TIMEOUT";
            reject(error);
          }, timeoutMs);
        }),
      ]);
    } finally {
      if (timer !== null) clearTimeout(timer);
    }
  }

  async function enumeratePortalFrameIds(tabId) {
    if (typeof chromeApi.webNavigation?.getAllFrames !== "function") return [];
    try {
      const entries = await chromeApi.webNavigation.getAllFrames({ tabId });
      return (Array.isArray(entries) ? entries : [])
        .map((entry) => entry?.frameId)
        .filter((candidate) => Number.isSafeInteger(candidate) && candidate >= 0)
        .filter((candidate, index, all) => all.indexOf(candidate) === index);
    } catch {
      // The optional API may be unavailable when its manifest permission is absent.
      return [];
    }
  }

  async function assertAutoSubmitCapability(spec) {
    if (spec.autoSubmit !== true) return;
    let capabilities = null;
    if (typeof bridge.getAutomationCapabilities === "function") {
      capabilities = await bridge.getAutomationCapabilities();
    }
    const allowed = spec.mode === "pilot"
      ? capabilities?.pilot_enabled === true && capabilities?.pilot_consumes_remaining === true
      : capabilities?.real_send_enabled === true;
    if (!allowed) {
      const error = new Error("envio automático exige uma qualificação local ativa");
      error.code = "REAL_SEND_DISABLED";
      throw error;
    }
  }

  async function appendAutomationEvent(identity, type, payload) {
    if (resolveAutomaticAct && typeof bridge.appendAutomationEvent !== "function") {
      setPaused("automation event persistence unavailable");
      return false;
    }
    if (typeof bridge.appendAutomationEvent !== "function") return true;
    const event = {
      eventId: `${eventPrefix(state.eventPrefix)}:${type}:${String(++eventSequence)}`,
      expectedRevision: state.revision,
      itemId: itemId(identity),
      type,
      payload: clone(payload),
    };
    try {
      const result = await bridge.appendAutomationEvent(state.runId, event);
      snapshotStatus(state, result);
      return true;
    } catch {
      setPaused("automation event persistence failed");
      return false;
    }
  }

  async function readFormSnapshot(tabId, frameId) {
    const snapshotRequestId = `${state.eventPrefix}-form-snapshot-${String(now())}-${String(++messageSequence)}`;
    const response = await sendPortalMessage(tabId, MESSAGE_TYPES.GET_FORM_SNAPSHOT, {}, frameId, snapshotRequestId);
    const requestedFrameId = Number.isSafeInteger(frameId) && frameId >= 0 ? frameId : null;
    const responseFrameId = Number.isSafeInteger(response?.frameId) && response.frameId >= 0 ? response.frameId : null;
    if (requestedFrameId !== null && responseFrameId !== null && requestedFrameId !== responseFrameId) {
      throw new Error("form snapshot frame mismatch");
    }
    const snapshot = formSnapshotFromResponse(response);
    if (!snapshot) throw new Error("form snapshot unavailable");
    return { snapshot, requestId: snapshotRequestId };
  }

  function expectedFieldValues(before, preparation) {
    return Object.fromEntries(AUTOMATION_FIELDS.map((field) => [
      field,
      Object.hasOwn(preparation.fields, field)
        ? preparation.fields[field]
        : preparation.preserved[field] ?? before.fields[field]?.value ?? "",
    ]));
  }

  function verifyPreparedSnapshot(before, after, preparation, portalBefore, portalAfter, frameId) {
    const afterIdentity = formIdentity(after);
    if (!sameCanonicalIdentity(afterIdentity, formIdentity(before))) return "reread identity mismatch";
    if (!sameCanonicalIdentity(afterIdentity, state.currentIdentity)) return "reread queue identity mismatch";
    if (after.frameId !== frameId || after.currentFrameId !== frameId) return "reread frame mismatch";
    if (after.generation !== portalAfter?.generation || after.currentGeneration !== portalAfter?.generation) {
      return "reread generation mismatch";
    }
    /*
     * portal generation is a per-document content fingerprint (currentGeneration
     * in portal-navigation.js), and the act screen revises its own DOM after the
     * first observation: the rendered act runs body onload="includeDataJs()" and
     * fades #dvLoading out on window load. Requiring equal generations across the
     * whole preparation window therefore rejected correct preparations. Drift is
     * proven structurally instead: the portal must still be showing an act surface
     * for the same frame and identity, and the per-field reread below must
     * reproduce every planned value over an unchanged option catalog.
     */
    if (!ACT_SURFACE_ROLES.has(portalBefore?.role) || !ACT_SURFACE_ROLES.has(portalAfter?.role)) {
      return "portal surface changed during preparation";
    }
    const expected = expectedFieldValues(before, preparation);
    for (const field of AUTOMATION_FIELDS) {
      if (after.fields[field]?.value !== expected[field]) return `reread field mismatch: ${field}`;
      if (!before.fields?.[field]
        || !after.fields?.[field]
        || before.fields[field].disabled !== after.fields[field].disabled
        || before.fields[field].readOnly !== after.fields[field].readOnly) {
        return `reread field state mismatch: ${field}`;
      }
      const beforeOptions = before.options?.[field] ?? [];
      const afterOptions = after.options?.[field] ?? [];
      if (JSON.stringify(beforeOptions) !== JSON.stringify(afterOptions)) {
        return `reread option catalog mismatch: ${field}`;
      }
    }
    for (const [field, proposed] of Object.entries(preparation.fields)) {
      const options = after.options?.[field];
      if (Array.isArray(options) && !options.some((option) => (isRecord(option) ? option.value : option) === proposed)) {
        return `reread option mismatch: ${field}`;
      }
    }
    return null;
  }

  async function recordItemFailure(identity, error, details = {}) {
    const payload = {
      error: typeof error === "string" && error ? error : "automatic preparation failed",
      ...details,
    };
    return appendAutomationEvent(identity, "item_failed", payload);
  }

  async function recordUnconfirmedSubmission(identity, after, reason) {
    const pauseReason = "portal outcome unconfirmed; reconcile before resuming";
    try {
      if (state.status === "running") {
        await control("pause", { eventId: eventId("pause-send"), reason: pauseReason });
      } else {
        setPaused(pauseReason);
      }
    } catch {
      setPaused(pauseReason);
      return false;
    }
    const persisted = await appendAutomationEvent(identity, "send_unconfirmed", {
      reason: typeof reason === "string" && reason ? reason : pauseReason,
      rereads: [{ identity: clone(identity), frame: after?.frameId ?? null, generation: after?.generation ?? null }],
      origin: "portal",
      timestamp: new Date(epochMilliseconds(now())).toISOString(),
    });
    setPaused(pauseReason);
    return persisted;
  }

  async function submitPreparedForm(tabId, frameId, before, after, preparation, resolved, identity) {
    let expected;
    let expectedFieldsHash;
    let verifiedFields;
    let contextHash;
    try {
      expected = expectedFieldValues(before, preparation);
      expectedFieldsHash = await sha256Hex(expected);
      verifiedFields = await fieldEvidence(after, expected);
      contextHash = await sha256Hex(contextEvidence(resolved?.context));
    } catch (error) {
      const persisted = await recordItemFailure(identity, error instanceof Error ? error.message : "automatic send evidence unavailable");
      return { stop: !persisted };
    }

    const submitCandidates = refreshSubmitFrame(tabId);
    if (submitCandidates.length > 1) {
      const persisted = await recordItemFailure(identity, "mais de um frame de botões do portal está disponível", {
        reason: "ambiguous submit frame",
      });
      return { stop: !persisted };
    }
    const submitTarget = state.submitFrame ?? {
      tabId,
      frameId,
      buttonId: null,
    };
    const issuedAt = epochMilliseconds(now());
    const command = {
      command_id: `${eventPrefix(state.eventPrefix)}:command:${String(++eventSequence)}`,
      state: "issued",
      issued_at: issuedAt,
      expires_at: issuedAt + AUTO_SUBMIT_TTL_MS,
      frame_id: submitTarget.frameId,
      form_frame_id: frameId,
      generation: after.generation,
      identity: clone(identity),
      expected_fields_hash: expectedFieldsHash,
      ...(submitTarget.buttonId ? { button_id: submitTarget.buttonId } : {}),
    };
    const intent = await appendAutomationEvent(identity, "send_intent", {
      expectedFieldsHash,
      command_id: command.command_id,
      expires_at: command.expires_at,
      identity: clone(identity),
      fields: verifiedFields,
      method: "portal-submit-click",
      origin: "portal",
      timestamp: new Date(issuedAt).toISOString(),
    });
    if (!intent) return { stop: true };

    let response;
    try {
      response = await sendPortalMessage(tabId, MESSAGE_TYPES.AUTO_SUBMIT_COMMAND, {
        runId: state.runId,
        expectedRevision: state.revision,
        command,
      }, submitTarget.frameId, `${state.eventPrefix}-submit-${String(++messageSequence)}`);
    } catch (error) {
      const persisted = await recordUnconfirmedSubmission(identity, after, error instanceof Error ? error.message : "automatic submit command failed");
      return { stop: !persisted, paused: true };
    }

    const outcome = response?.ok === true && isRecord(response.payload) ? response.payload : null;
    if (outcome?.status === "confirmed") {
      const citations = confirmationCitations(
        resolved?.record,
        identity,
        resolved?.context?.dataset_sha256 ?? resolved?.record?.dataset_sha256,
        contextHash,
        outcome.evidence,
      );
      const confirmed = await appendAutomationEvent(identity, "send_confirmed", {
        identity: clone(identity),
        origin: "portal",
        timestamp: new Date(epochMilliseconds(now())).toISOString(),
        fields: verifiedFields,
        citations,
      });
      return { stop: !confirmed, submitted: confirmed };
    }
    if (outcome?.status === "failed") {
      const evidenceReason = safeCitation(outcome.evidence)?.reason;
      const persisted = await recordItemFailure(identity, evidenceReason || "portal rejected the Complementar Ato submission", {
        reason: "portal rejected the Complementar Ato submission",
      });
      return { stop: !persisted };
    }
    const responseReason = safeCitation(outcome?.evidence)?.reason
      || response?.error?.message
      || "portal outcome was not confirmed";
    const persisted = await recordUnconfirmedSubmission(identity, after, responseReason);
    return { stop: !persisted, paused: true };
  }

  async function prepareAndVerifyForm(tabId, frameId, portalSnapshot, identity) {
    let before;
    let snapshotRequestId;
    let resolved;
    try {
      const beforeResponse = await readFormSnapshot(tabId, frameId);
      before = decorateFormSnapshot(beforeResponse.snapshot, portalSnapshot, frameId);
      snapshotRequestId = beforeResponse.requestId;
      resolved = await resolveAutomaticAct(identity, clone(before), clone(portalSnapshot));
    } catch (error) {
      const persisted = await recordItemFailure(identity, error instanceof Error ? error.message : "automatic resolver failed");
      return { stop: !persisted };
    }

    const preparation = prepareAutomaticAct({
      record: resolved?.record,
      context: resolved?.context,
      snapshot: before,
      legalDecision: resolved?.legalDecision,
      matchedValues: resolved?.matchedValues,
      matchKinds: resolved?.matchKinds,
    });
    if (!preparation.eligible) {
      const persisted = await appendAutomationEvent(identity, "item_pending", {
        reason: preparation.reasons.join(", ") || "automatic preparation is not eligible",
        ...(resolved?.legalDecision ? { legalDecision: clone(resolved.legalDecision) } : {}),
      });
      return { stop: !persisted };
    }

    let preparedPayload;
    try {
      const expected = expectedFieldValues(before, preparation);
      preparedPayload = {
        reason: "automatic preparation is eligible",
        identity: clone(identity),
        frame: { generation: before.generation, frameId },
        dataset_sha256: resolved?.context?.dataset_sha256 ?? resolved?.record?.dataset_sha256,
        context_hash: await sha256Hex(contextEvidence(resolved?.context)),
        legalDecision: safeLegalDecision(resolved?.legalDecision),
        matchKinds: safeMatchKinds(resolved?.matchKinds),
        before: await fieldEvidence(before, Object.fromEntries(AUTOMATION_FIELDS.map((field) => [field, before.fields[field]?.value ?? ""]))),
        after: await fieldEvidence(before, expected, Object.fromEntries(AUTOMATION_FIELDS.map((field) => [field, Object.hasOwn(preparation.fields, field) ? "planned" : "preserved"]))),
      };
    } catch (error) {
      const persisted = await recordItemFailure(identity, error instanceof Error ? error.message : "automatic evidence unavailable");
      return { stop: !persisted };
    }
    const prepared = await appendAutomationEvent(identity, "item_prepared", preparedPayload);
    if (!prepared) return { stop: true };

    let applyResponse;
    try {
      applyResponse = await sendPortalMessage(tabId, MESSAGE_TYPES.APPLY_FIELDS, {
        fields: clone(preparation.fields),
        matchKinds: clone(resolved?.matchKinds ?? {}),
      }, frameId, snapshotRequestId);
    } catch (error) {
      const persisted = await recordItemFailure(identity, error instanceof Error ? error.message : "APPLY_FIELDS failed");
      return { stop: !persisted };
    }
    if (applyResponse?.ok !== true || applyResponse?.payload?.errors?.length > 0) {
      const persisted = await recordItemFailure(identity, "APPLY_FIELDS blocked", {
        errors: Array.isArray(applyResponse?.payload?.errors) && applyResponse.payload.errors.length > 0
          ? applyResponse.payload.errors
          : [applyResponse?.error?.message ?? "APPLY_FIELDS returned an error"],
      });
      return { stop: !persisted };
    }

    let after;
    let portalAfter;
    try {
      after = decorateFormSnapshot((await readFormSnapshot(tabId, frameId)).snapshot, portalSnapshot, frameId);
      const rereadPortal = await readPortalSnapshot(tabId, frameId);
      if (!rereadPortal) throw new Error("portal snapshot unavailable after APPLY_FIELDS");
      portalAfter = rereadPortal.snapshot;
      after = decorateFormSnapshot(after, portalAfter, frameId);
    } catch (error) {
      const persisted = await recordItemFailure(identity, error instanceof Error ? error.message : "form reread failed");
      return { stop: !persisted };
    }
    const mismatch = verifyPreparedSnapshot(before, after, preparation, portalSnapshot, portalAfter, frameId);
    if (mismatch) {
      const persisted = await recordItemFailure(identity, mismatch, { reason: "fields verification failed" });
      return { stop: !persisted };
    }
    const verified = await appendAutomationEvent(identity, "fields_verified", {
      fieldResults: await fieldResults(before, after, preparation),
      rereads: [{ identity: after.identity, frame: frameId, generation: after.generation }],
    });
    if (!verified) return { stop: true };
    if (state.mode === "pilot" && state.autoSubmit !== true) {
      await pauseAndPersist("pilot prepared; review the fields before continuing");
      return { stop: true, paused: true };
    }
    if (state.autoSubmit !== true) return { stop: false };
    return submitPreparedForm(tabId, frameId, before, after, preparation, resolved, identity);
  }

  async function readPortalSnapshot(tabId, frameId = state.frame?.frameId ?? null) {
    const hasRequestedFrame = Number.isSafeInteger(frameId) && frameId >= 0;
    const registeredFrameIds = hasRequestedFrame
      ? [frameId]
      : [...frames.values()]
        .filter((entry) => entry.tabId === tabId && ["list", "unknown"].includes(entry.role)
          && (state.sourceScope == null || entry.source_scope === state.sourceScope))
        .sort((left, right) => (right.observedAt ?? 0) - (left.observedAt ?? 0) || right.frameId - left.frameId)
        .map((entry) => entry.frameId)
        .filter((candidate, index, all) => all.indexOf(candidate) === index);
    const frameIdsToProbe = hasRequestedFrame
      ? registeredFrameIds
      : [...registeredFrameIds, ...(await enumeratePortalFrameIds(tabId))]
        .filter((candidate, index, all) => all.indexOf(candidate) === index);
    for (const registeredFrameId of frameIdsToProbe) {
      try {
        const response = await sendPortalMessage(tabId, MESSAGE_TYPES.PORTAL_GET_SNAPSHOT, {}, registeredFrameId);
        const snapshot = snapshotFromResponse(response);
        const responseFrameId = Number.isSafeInteger(response?.frameId) && response.frameId >= 0 ? response.frameId : null;
        // chrome.tabs.sendMessage targets the requested frame but does not
        // echo that frame id in the content-script response. If a mock or a
        // future bridge does echo it, reject an inconsistent value.
        if (!snapshot || (responseFrameId !== null && responseFrameId !== registeredFrameId)
          || (!hasRequestedFrame && (snapshot.role !== "list"
            || (state.sourceScope !== null && snapshot.source_scope !== state.sourceScope)))) continue;
        registerFrame(tabId, registeredFrameId, snapshot);
        return { snapshot, frameId: registeredFrameId };
      } catch {
        // Try the next registered list frame before falling back to a broadcast.
      }
    }
    try {
      const response = await sendPortalMessage(tabId, MESSAGE_TYPES.PORTAL_GET_SNAPSHOT, {}, frameId);
      if (response?.ok !== true) {
        setPaused(response?.error?.code === "TAB_CLOSED" ? "tab closed" : "portal frame unavailable");
        return null;
      }
      const snapshot = snapshotFromResponse(response);
      if (!snapshot) {
        setPaused("portal frame unavailable");
        return null;
      }
      const requestedFrameId = Number.isSafeInteger(frameId) && frameId >= 0 ? frameId : null;
      const responseFrameId = Number.isSafeInteger(response?.frameId) && response.frameId >= 0 ? response.frameId : null;
      if (requestedFrameId !== null && responseFrameId !== null && requestedFrameId !== responseFrameId) {
        setPaused("navigation token/frame mismatch");
        return null;
      }
      const resolvedFrameId = requestedFrameId ?? responseFrameId;
      if (resolvedFrameId === null) {
        setPaused("portal frame unavailable");
        return null;
      }
      registerFrame(tabId, resolvedFrameId, snapshot);
      return { snapshot, frameId: resolvedFrameId };
    } catch (error) {
      setPaused(error?.code === "TAB_CLOSED" ? "tab closed" : "portal frame unavailable");
      return null;
    }
  }

  async function refreshListGeneration(tabId, current) {
    const frameId = state.frame?.frameId;
    if (!Number.isSafeInteger(frameId) || !isRecord(current) || current.role !== "list") return current;
    const observed = await readPortalSnapshot(tabId, frameId);
    const next = observed?.snapshot;
    if (!isRecord(next) || next.role !== "list") return current;
    if (state.sourceScope !== null && next.source_scope !== state.sourceScope) return current;
    if (state.marker && !markerMatches(next, state.marker)) return current;
    const currentSignature = (current.identities ?? []).map(identityKey).join("|");
    const nextSignature = (next.identities ?? []).map(identityKey).join("|");
    return currentSignature === nextSignature ? next : current;
  }

  async function verifySubmitState(input = {}) {
    const command = input.command;
    const formFrameId = commandFormFrame(command);
    if (state.status !== "running" || input.runId !== state.runId) {
      return { ok: false, visible: false, paused: true, reason: "automation command is not active" };
    }
    if (input.tabId !== state.tabId
      || !Number.isSafeInteger(formFrameId)
      || formFrameId < 0
      || !Number.isSafeInteger(input.frameId)
      || input.frameId < 0
      || (input.frameId !== command.frame_id)
      || (state.submitFrame && input.frameId !== state.submitFrame.frameId)
      || (state.frame && formFrameId !== state.frame.frameId)) {
      return { ok: false, visible: false, paused: true, reason: "automation command frame is not authorized" };
    }
    if (!sameCanonicalIdentity(command.identity, state.currentIdentity)) {
      return { ok: false, visible: false, paused: true, reason: "automation command identity changed" };
    }
    try {
      const form = await readFormSnapshot(input.tabId, formFrameId);
      const portal = await readPortalSnapshot(input.tabId, formFrameId);
      if (!portal || portal.snapshot.role !== "form") {
        return { ok: false, visible: false, paused: true, reason: "form frame is unavailable" };
      }
      const decorated = decorateFormSnapshot(form.snapshot, portal.snapshot, formFrameId);
      const currentIdentity = {
        processKey: decorated.process.key,
        interestedNormalized: decorated.interested.normalized,
        portalActId: command.identity.portalActId ?? null,
      };
      const currentFields = Object.fromEntries(AUTOMATION_FIELDS.map((field) => [
        field,
        String(decorated.fields[field]?.value ?? ""),
      ]));
      const fieldsHash = await sha256Hex(currentFields);
      if (portal.snapshot.generation !== command.generation
        || !sameCanonicalIdentity(currentIdentity, command.identity)
        || fieldsHash !== command.expected_fields_hash) {
        return { ok: false, visible: false, paused: true, reason: "form state changed before submission" };
      }
      return {
        ok: true,
        visible: true,
        paused: false,
        frame_id: formFrameId,
        generation: portal.snapshot.generation,
        identity: currentIdentity,
        fields_hash: fieldsHash,
      };
    } catch (error) {
      return {
        ok: false,
        visible: false,
        paused: true,
        reason: error instanceof Error ? error.message : "form state could not be verified",
      };
    }
  }

  function isProgressedListSnapshot(before, after) {
    if (!isRecord(before) || !isRecord(after)
      || before.role !== "list" || after.role !== "list") return false;
    const beforeKeys = new Set((before.identities ?? []).map(identityKey));
    return (after.identities ?? []).some((candidate) => !beforeKeys.has(identityKey(candidate)));
  }

  function acceptedProgressedPaginationSnapshot(beforeSnapshot, snapshot) {
    return isProgressedListSnapshot(beforeSnapshot, snapshot)
      && (state.sourceScope === null || snapshot.source_scope === state.sourceScope)
      && (!state.marker || markerMatches(snapshot, state.marker));
  }

  function takeExpectedProgressedPaginationSnapshot(tabId, beforeSnapshot) {
    const navigation = expectedNavigation;
    const pending = navigation?.progressedSnapshot;
    if (navigation?.action !== "next_page"
      || navigation.tabId !== tabId
      || !isRecord(pending)
      || !acceptedProgressedPaginationSnapshot(beforeSnapshot, pending.snapshot)) return null;
    navigation.progressedSnapshot = null;
    registerFrame(tabId, pending.frameId, pending.snapshot);
    return { snapshot: pending.snapshot, frameId: pending.frameId };
  }

  async function recoverPaginatedSnapshot(tabId, frameId, beforeSnapshot) {
    const attempts = 24;
    const delayMs = 250;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const eventSnapshot = takeExpectedProgressedPaginationSnapshot(tabId, beforeSnapshot);
      if (eventSnapshot) return eventSnapshot;
      // Native submission starts unloading the old legacy document only
      // after the content listener returns. Give Chrome one event-loop turn
      // before probing so the first read cannot pin the stale frame.
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      const discoveredFrameIds = await enumeratePortalFrameIds(tabId);
      const frameIds = [...new Set([frameId, ...discoveredFrameIds])]
        .filter((candidate) => Number.isSafeInteger(candidate) && candidate >= 0);
      for (const candidate of frameIds) {
        try {
          const response = await sendPortalMessageBounded(
            tabId,
            MESSAGE_TYPES.PORTAL_GET_SNAPSHOT,
            {},
            candidate,
            `${state.eventPrefix}-recovery-${String(attempt)}-${String(candidate)}`,
          );
          const snapshot = snapshotFromResponse(response);
          if (!acceptedProgressedPaginationSnapshot(beforeSnapshot, snapshot)) continue;
          registerFrame(tabId, candidate, snapshot);
          return { snapshot, frameId: candidate };
        } catch {
          // A frame can disappear while the portal replaces the iframe.
        }
      }
    }
    return null;
  }

  async function navigate(tabId, frameId, action, identity, generation, options = {}) {
    const navigation = {
      token: `${state.eventPrefix}-navigation-${String(++navigationToken)}`,
      tabId,
      frameId,
      action,
      generation,
      loadingObserved: false,
      beforeSnapshot: isRecord(options.beforeSnapshot) ? options.beforeSnapshot : null,
      progressedSnapshot: null,
    };
    expectedNavigation = navigation;
    try {
      const send = async (expectedGeneration) => {
        const payload = {
          action,
          identity: identity ?? null,
          expected_generation: expectedGeneration,
        };
        if (typeof options.marker === "string") payload.marker = options.marker;
        if (typeof options.processKey === "string") payload.process_key = options.processKey;
        return sendPortalMessage(tabId, MESSAGE_TYPES.PORTAL_NAVIGATE, payload, frameId, navigation.token);
      };
      let response = await send(generation);
      const liveGeneration = state.status === "running" ? staleGenerationReport(response, generation) : null;
      if (liveGeneration !== null) {
        /*
         * The restricted act screen repaints itself right after boot (the
         * rendered act runs body onload="includeDataJs()" and fades #dvLoading
         * out on window load), so a navigation prepared from the previous
         * observation is rejected by the gate before it touches any control.
         * That rejection is the guard doing its job: re-issue the same action
         * once against the generation the frame reported, and let the gate
         * resolve every control and identity again from the live screen.
         */
        noteFrameGeneration(tabId, frameId, liveGeneration);
        response = await send(liveGeneration);
      }
      if (response?.ok !== true) {
        if (["first_page", "next_page"].includes(action) && isRecord(options.beforeSnapshot)) {
          // The legacy portal can finish replacing the list iframe while its
          // navigation promise is already reporting a timeout/error. Probe
          // the current frames before pausing; a progressed snapshot is the
          // authoritative evidence that the page actually advanced.
          const recovered = await recoverPaginatedSnapshot(tabId, frameId, options.beforeSnapshot);
          if (recovered) {
            if (expectedNavigation === navigation) expectedNavigation = null;
            return { ok: true, snapshot: recovered.snapshot, frameId: recovered.frameId };
          }
        }
        setPaused(navigationFailureReason(response));
        return { ok: false, response };
      }
      const responseFrameId = Number.isSafeInteger(response?.frameId) && response.frameId >= 0 ? response.frameId : null;
      if (responseFrameId !== null && responseFrameId !== frameId) {
        setPaused("navigation token/frame mismatch");
        return { ok: false, response };
      }
      if (response?.navigationToken !== undefined && response.navigationToken !== navigation.token) {
        setPaused("navigation token/frame mismatch");
        return { ok: false, response };
      }
      const snapshot = snapshotFromResponse(response);
      if (snapshot) registerFrame(tabId, frameId, snapshot);
      if (["first_page", "next_page"].includes(action)
        && !snapshot
        && isRecord(options.beforeSnapshot)) {
        const eventSnapshot = takeExpectedProgressedPaginationSnapshot(tabId, options.beforeSnapshot);
        if (eventSnapshot) {
          if (expectedNavigation === navigation) expectedNavigation = null;
          return { ok: true, snapshot: eventSnapshot.snapshot, frameId: eventSnapshot.frameId };
        }
        const recovered = await recoverPaginatedSnapshot(tabId, frameId, options.beforeSnapshot);
        if (recovered) {
          if (expectedNavigation === navigation) expectedNavigation = null;
          return { ok: true, snapshot: recovered.snapshot, frameId: recovered.frameId };
        }
      }
      return { ok: true, snapshot };
    } catch (error) {
      if (["first_page", "next_page"].includes(action) && isRecord(options.beforeSnapshot)) {
        const recovered = await recoverPaginatedSnapshot(tabId, frameId, options.beforeSnapshot);
        if (recovered) {
          if (expectedNavigation === navigation) expectedNavigation = null;
          return { ok: true, snapshot: recovered.snapshot, frameId: recovered.frameId };
        }
      }
      setPaused(error?.code === "TAB_CLOSED" ? "tab closed" : "portal frame unavailable");
      return { ok: false, error };
    } finally {
      if (expectedNavigation === navigation) expectedNavigation = null;
    }
  }

  async function ensureMarkerFilter(tabId, initial, expectedMarker) {
    if (!expectedMarker) return initial;
    if (markerMatches(initial, expectedMarker)) return initial;
    const filter = actionFor(initial, "filter_marker");
    if (!filter) {
      setPaused("marcador não confirmado e filtro automático indisponível; intervenção manual necessária");
      return null;
    }
    const frameId = state.frame?.frameId ?? 0;
    const moved = await navigate(tabId, frameId, "filter_marker", null, initial.generation, { marker: expectedMarker });
    if (!moved.ok) {
      if (state.status !== "paused") setPaused("filtro de marcador exige intervenção manual");
      return null;
    }
    let filtered = moved.snapshot;
    if (!filtered) filtered = (await readPortalSnapshot(tabId, frameId))?.snapshot ?? null;
    if (!filtered || filtered.role !== "list" || !markerMatches(filtered, expectedMarker)) {
      setPaused("resultado não confirmou o marcador solicitado");
      return null;
    }
    return filtered;
  }

  async function discoverList(tabId, initial, spec = {}) {
    let current = await ensureMarkerFilter(tabId, initial, spec.marker);
    if (!current) return null;
    const firstPage = actionFor(current, "first_page");
    if (firstPage) {
      const frameId = state.frame?.frameId ?? 0;
      const moved = await navigate(tabId, frameId, "first_page", null, current.generation, { beforeSnapshot: current });
      if (!moved.ok) {
        if (state.status !== "paused") setPaused("não foi possível retornar à primeira página da lista");
        return current;
      }
      current = moved.snapshot ?? (await readPortalSnapshot(tabId, frameId))?.snapshot ?? null;
      if (!current || current.role !== "list"
        || !markerMatches(current, spec.marker, spec.markerValue ?? null)) {
        setPaused("a primeira página não confirmou origem e marcador selecionados");
        return current;
      }
    }
    const pageSignatures = new Set();
    let refreshBeforeAction = false;
    for (let index = 0; index < 100; index += 1) {
      if (refreshBeforeAction) {
        current = await refreshListGeneration(tabId, current);
        refreshBeforeAction = false;
      }
      if (spec.marker && !markerMatches(current, spec.marker, spec.markerValue ?? null)) {
        setPaused("o resultado da paginação perdeu o marcador solicitado");
        return current;
      }
      if (spec.mode === "pilot"
        && spec.marker
        && isRecord(spec.pilotIdentity)
        && (current.identities ?? []).some((candidate) => (
          identityKey(candidate) === identityKey(spec.pilotIdentity)
        ))) {
        // A pilot has one explicit identity. Once that identity is visible on
        // the already-confirmed filtered list, do not walk unrelated pages or
        // depend on the legacy portal's final-page reset behavior.
        collectSnapshot(current);
        return current;
      }
      const signature = (current.identities ?? []).map(identityKey).join("|");
      if (pageSignatures.has(signature)) {
        setPaused("page repeated without progress");
        return current;
      }
      pageSignatures.add(signature);
      collectSnapshot(current);
      const next = actionFor(current, "next_page");
      if (!next || next.direction === "first") return current;
      const frameId = state.frame?.frameId ?? 0;
      const moved = await navigate(tabId, frameId, "next_page", null, current.generation, { beforeSnapshot: current });
      if (!moved.ok) {
        if (state.status !== "paused") setPaused("navigation failed or requires manual intervention");
        return current;
      }
      let nextSnapshot = moved.snapshot;
      if (!nextSnapshot) nextSnapshot = (await readPortalSnapshot(tabId, frameId))?.snapshot ?? null;
      if (!nextSnapshot || nextSnapshot.role !== "list") {
        setPaused("list navigation did not produce a list screen");
        return current;
      }
      if (spec.marker && !markerMatches(nextSnapshot, spec.marker, spec.markerValue ?? null)) {
        setPaused("a próxima página não confirmou o marcador solicitado");
        return current;
      }
      const nextSignature = (nextSnapshot.identities ?? []).map(identityKey).join("|");
      if (nextSignature === signature) {
        setPaused("page repeated without progress");
        return nextSnapshot;
      }
      current = nextSnapshot;
      refreshBeforeAction = true;
    }
    setPaused("pagination exceeded the safe page limit");
    return current;
  }

  async function queryMissingProcesses(tabId, initial, spec) {
    if (!Array.isArray(spec.inputKeys) || spec.inputKeys.length === 0) return initial;
    let current = initial;
    const observedKeys = new Set([...state.areaObservations.values()]
      .map((observation) => observation.candidate?.processKey)
      .filter((key) => typeof key === "string"));
    for (const processKey of spec.inputKeys) {
      if (state.status === "paused") return null;
      if (observedKeys.has(processKey)) continue;
      if (!current || current.role !== "list"
        || !markerMatches(current, spec.marker, spec.markerValue ?? null)
        || (spec.sourceScope && current.source_scope !== spec.sourceScope)) {
        setPaused("origem ou marcador mudou durante a consulta exata");
        return null;
      }
      const find = actionFor(current, "find_process");
      if (!find) {
        setPaused("filtro exato de processo indisponível; intervenção manual necessária");
        return null;
      }
      const frameId = state.frame?.frameId ?? 0;
      const moved = await navigate(
        tabId,
        frameId,
        "find_process",
        null,
        current.generation,
        { beforeSnapshot: current, processKey },
      );
      if (!moved.ok) return null;
      current = moved.snapshot ?? (await readPortalSnapshot(tabId, frameId))?.snapshot ?? null;
      if (!current || current.role !== "list"
        || !markerMatches(current, spec.marker, spec.markerValue ?? null)
        || (spec.sourceScope && current.source_scope !== spec.sourceScope)) {
        setPaused("a busca exata não confirmou origem e marcador");
        return null;
      }
      const matches = (current.identities ?? []).filter((candidate) => candidate?.processKey === processKey);
      if (matches.length > 0) {
        recordAreaObservations({ ...current, identities: matches });
        observedKeys.add(processKey);
      } else {
        state.areaObservations.set(`${processKey}\u0000__absent`, {
          candidate: null,
          processKey,
          source_scope: current.source_scope,
          marker: clone(current.marker),
        });
      }
    }
    return current;
  }

  async function restoreAnalysisList(tabId, current, original, spec) {
    if (!current || state.status === "paused") return null;
    let restored = current;
    if (!markerMatches(restored, original.marker?.label, original.marker?.value ?? null)) {
      restored = await ensureMarkerFilter(tabId, restored, original.marker?.label);
    }
    if (!restored || state.status === "paused") return null;
    const first = actionFor(restored, "first_page");
    if (!first) return restored;
    const frameId = state.frame?.frameId ?? 0;
    const moved = await navigate(tabId, frameId, "first_page", null, restored.generation, { beforeSnapshot: restored });
    if (!moved.ok) return null;
    restored = moved.snapshot ?? (await readPortalSnapshot(tabId, frameId))?.snapshot ?? null;
    if (!restored || restored.role !== "list"
      || !markerMatches(restored, original.marker?.label, original.marker?.value ?? null)
      || (spec.sourceScope && restored.source_scope !== spec.sourceScope)) {
      setPaused("a restauração do filtro original não foi confirmada");
      return null;
    }
    return restored;
  }

  async function freezeQueue(spec, startEventId) {
    if (state.queueFrozen || state.status === "paused") return;
    if (typeof bridge.getDataset === "function") {
      const datasetEnvelope = await bridge.getDataset();
      const datasetHash = datasetEnvelope?.dataset?.batch?.logical_sha256;
      if (datasetHash && datasetHash !== spec.datasetSha256) {
        setPaused("dataset changed before queue freeze");
        return;
      }
    }
    if (typeof bridge.freezeAutomationQueue !== "function") {
      setPaused("automation bridge cannot freeze the queue");
      return;
    }
    try {
      const frozen = await bridge.freezeAutomationQueue(state.runId, {
        identities: state.queue.map(clone),
        eventId: `${startEventId}:queue`,
        expectedRevision: state.revision,
      });
      snapshotStatus(state, frozen);
      state.queueFrozen = true;
    } catch {
      setPaused("queue freeze failed");
    }
  }

  function rehydratedSpec(value) {
    if (!isRecord(value)) return null;
    const aliases = [
      ["tabId", "tab_id"],
      ["sector", "sector"],
      ["datasetSha256", "dataset_sha256"],
      ["rulesVersion", "rules_version"],
      ["mode", "mode"],
      ["marker", "marker"],
      ["markerValue", "marker_value"],
      ["autoSubmit", "auto_submit"],
      ["sourceScope", "source_scope"],
      ["acquisitionSource", "acquisition_source"],
      ["lotSize", "lot_size"],
      ["analysisId", "analysis_id"],
      ["previewHash", "preview_hash"],
      ["pilotIdentity", "pilot_identity"],
    ];
    const result = {};
    for (const [camel, wire] of aliases) {
      if (Object.hasOwn(value, camel)) result[camel] = clone(value[camel]);
      else if (Object.hasOwn(value, wire)) result[camel] = clone(value[wire]);
    }
    if (isRecord(result.pilotIdentity)) {
      result.pilotIdentity = rehydratedIdentity(result.pilotIdentity) ?? null;
    }
    return Object.keys(result).length > 0 ? result : null;
  }

  async function rehydrate(snapshot, specInput = null) {
    try {
      validateAutomationSnapshot(snapshot);
    } catch (error) {
      throw Object.assign(new Error(error instanceof Error ? error.message : "invalid automation snapshot"), {
        code: error?.code ?? "INVALID_AUTOMATION_SNAPSHOT",
      });
    }
    if (!ACTIVE_STATUSES.has(snapshot.status)) {
      throw Object.assign(new Error("automation run is not active"), { code: "RUN_NOT_FOUND" });
    }
    const spec = rehydratedSpec(specInput) ?? rehydratedSpec(snapshot.spec);
    const requiredSpecKeys = ["tabId", "sector", "datasetSha256", "rulesVersion"];
    if (spec && requiredSpecKeys.every((key) => Object.hasOwn(spec, key))) {
      try {
        validateAutomationRunSpec(spec);
      } catch (error) {
        throw Object.assign(new Error(error instanceof Error ? error.message : "invalid automation run spec"), {
          code: error?.code ?? "INVALID_AUTOMATION_SPEC",
        });
      }
    }
    const queue = [];
    const itemStates = new Map();
    const completedIdentities = new Set();
    for (const item of snapshot.items) {
      const identity = rehydratedIdentity(item.identity);
      if (!identity) {
        throw Object.assign(new Error("automation snapshot identity is invalid"), { code: "INVALID_AUTOMATION_SNAPSHOT" });
      }
      const key = identityKey(identity);
      if (itemStates.has(key)) {
        throw Object.assign(new Error("automation snapshot contains duplicate identities"), { code: "INVALID_AUTOMATION_SNAPSHOT" });
      }
      queue.push(identity);
      itemStates.set(key, item.state);
      if (TERMINAL_ITEM_STATES.has(item.state) || !REHYDRATABLE_ITEM_STATES.has(item.state)) {
        completedIdentities.add(key);
      }
    }
    state = {
      runId: snapshot.run_id,
      status: snapshot.status,
      revision: snapshot.revision,
      tabId: spec?.tabId ?? null,
      sector: spec?.sector ?? null,
      sourceScope: spec?.sourceScope ?? null,
      mode: spec?.mode ?? "batch",
      marker: spec?.marker ?? null,
      autoSubmit: spec?.autoSubmit === true,
      pilotIdentity: spec?.pilotIdentity ?? null,
      queueFrozen: queue.length > 0,
      currentIdentity: null,
      pausedReason: snapshot.status === "paused"
        ? "execution restored after service worker restart"
        : null,
      frame: null,
      submitFrame: null,
      queue,
      itemStates,
      areaObservations: new Map(),
      seenIdentities: new Set(queue.map(identityKey)),
      completedIdentities,
      totals: {
        discovered: queue.length,
        unique: queue.length,
        pending: queue.filter((identity) => {
          const itemState = itemStates.get(identityKey(identity));
          return ["pending", "failed", "unconfirmed", "blocked"].includes(itemState);
        }).length,
      },
      eventPrefix: eventPrefix(snapshot.run_id),
    };
    await loadFrames();
    if (Number.isSafeInteger(state.tabId)) {
      const candidates = [...frames.values()]
        .filter((entry) => entry.tabId === state.tabId
          && (state.sourceScope === null || entry.source_scope === state.sourceScope))
        .sort((left, right) => (right.observedAt ?? 0) - (left.observedAt ?? 0) || right.frameId - left.frameId);
      const restored = candidates.find((entry) => entry.role === "list") ?? candidates[0];
      if (restored) {
        state.frame = {
          frameId: restored.frameId,
          role: restored.role,
          generation: restored.generation,
          sector: restored.sector ?? null,
          source_scope: restored.source_scope ?? null,
        };
      }
      refreshSubmitFrame(state.tabId);
    }
    return statusToPublic(state);
  }

  async function start(input, suppliedEventId) {
    const spec = input?.spec ?? input;
    const startEventId = input?.eventId ?? suppliedEventId ?? eventId("start");
    validateAutomationRunSpec(spec);
    if (ACTIVE_STATUSES.has(state.status)) {
      const error = new Error("an automation run is already active");
      error.code = "ACTIVE_RUN";
      throw error;
    }
    await assertAutoSubmitCapability(spec);
    await loadFrames();
    state = {
      runId: null,
      status: "discovering",
      revision: 0,
      tabId: spec.tabId,
      sector: spec.sector,
      sourceScope: spec.sourceScope ?? null,
      mode: spec.mode ?? "batch",
      marker: spec.marker ?? null,
      autoSubmit: spec.autoSubmit === true,
      pilotIdentity: spec.pilotIdentity ?? null,
      queueFrozen: false,
      currentIdentity: null,
      pausedReason: null,
      frame: null,
      submitFrame: null,
      queue: [],
      itemStates: new Map(),
      areaObservations: new Map(),
      seenIdentities: new Set(),
      completedIdentities: new Set(),
      totals: { discovered: 0, unique: 0, pending: 0 },
      eventPrefix: eventPrefix(startEventId),
    };
    eventSequence = 0;
    const storedFrames = [...frames.values()].filter((entry) => entry.tabId === spec.tabId);
    if (storedFrames.length === 1
      && (!spec.sourceScope || storedFrames[0].source_scope === spec.sourceScope)) {
      const stored = storedFrames[0];
      state.frame = {
        frameId: stored.frameId,
        role: stored.role,
        generation: stored.generation,
        sector: stored.sector ?? null,
        source_scope: stored.source_scope ?? null,
      };
    }
    refreshSubmitFrame(spec.tabId);
    const run = await bridge.createAutomationRun(spec, startEventId);
    snapshotStatus(state, run);
    state.status = "discovering";
    const first = await readPortalSnapshot(spec.tabId);
    if (!first) return pauseAndPersist("portal frame unavailable", `${startEventId}:pause-frame`);
    if (first.snapshot.sector && first.snapshot.sector !== spec.sector) {
      return pauseAndPersist("sector changed before discovery", `${startEventId}:pause-sector`);
    }
    if (spec.sourceScope && first.snapshot.source_scope !== spec.sourceScope) {
      return pauseAndPersist("origem selecionada não corresponde à lista aberta; navegue para a tela escolhida antes de iniciar", `${startEventId}:pause-source`);
    }
    if (first.snapshot.role !== "list") {
      return pauseAndPersist("manual navigation required: process list not visible", `${startEventId}:pause-screen`);
    }
    const discovered = await discoverList(spec.tabId, first.snapshot, spec);
    if (!discovered) return statusToPublic(state);
    if (state.mode === "pilot") {
      const targetKey = identityKey(state.pilotIdentity);
      const target = state.queue.find((candidate) => identityKey(candidate) === targetKey);
      if (!target) {
        setPaused("pilot identity was not discovered in the current portal queue");
        return statusToPublic(state);
      }
      state.queue = [target];
      state.totals.unique = 1;
      state.totals.pending = 0;
    }
    await freezeQueue(spec, startEventId);
    if (state.status === "discovering") state.status = "running";
    if (state.status === "running") {
      let ready = discovered;
      const firstIdentity = nextQueuedIdentity();
      if (firstIdentity && !actionFor(ready, "open_act", firstIdentity)) {
        const reset = actionFor(ready, "next_page");
        if (reset?.direction !== "first") {
          setPaused("first queued process requires manual re-find");
          return statusToPublic(state);
        }
        const moved = await navigate(spec.tabId, state.frame?.frameId ?? 0, "next_page", null, ready.generation, { beforeSnapshot: ready });
        if (!moved.ok || !moved.snapshot || moved.snapshot.role !== "list") {
          setPaused("first queued process requires manual re-find");
          return statusToPublic(state);
        }
        ready = moved.snapshot;
      }
      await driveSnapshot(spec.tabId, state.frame?.frameId ?? 0, ready);
    }
    return statusToPublic(state);
  }

  async function analyze(input) {
    const requestedSpec = input?.spec ?? input;
    let spec = requestedSpec;
    validateAutomationRunSpec(spec);
    if (ACTIVE_STATUSES.has(state.status) && state.runId) {
      const error = new Error("an automation run is already active");
      error.code = "ACTIVE_RUN";
      throw error;
    }
    await loadFrames();
    state = {
      runId: null,
      status: "discovering",
      revision: 0,
      tabId: spec.tabId,
      sector: spec.sector,
      sourceScope: spec.sourceScope ?? null,
      mode: "batch",
      marker: spec.marker ?? null,
      autoSubmit: false,
      pilotIdentity: null,
      queueFrozen: false,
      currentIdentity: null,
      pausedReason: null,
      frame: null,
      submitFrame: null,
      queue: [],
      itemStates: new Map(),
      areaObservations: new Map(),
      seenIdentities: new Set(),
      completedIdentities: new Set(),
      totals: { discovered: 0, unique: 0, pending: 0 },
      eventPrefix: eventPrefix(input?.eventId ?? eventId("analysis")),
    };
    const first = await readPortalSnapshot(spec.tabId);
    if (!first) return { ok: false, error: "portal snapshot unavailable" };
    if (spec.sector !== "*" && first.snapshot.sector && first.snapshot.sector !== spec.sector) {
      setPaused("sector changed before analysis");
      return { ok: false, error: state.pausedReason, totals: state.totals };
    }
    if (spec.sourceScope && first.snapshot.source_scope !== spec.sourceScope) {
      setPaused("origem selecionada não corresponde à lista aberta; navegue para a tela escolhida antes de analisar");
      return { ok: false, error: state.pausedReason, totals: state.totals };
    }
    if (first.snapshot.role !== "list") {
      setPaused("manual navigation required: process list not visible");
      return { ok: false, error: state.pausedReason, totals: state.totals };
    }
    const selectedMarker = first.snapshot.marker;
    if (!isRecord(selectedMarker)
      || typeof selectedMarker.label !== "string" || selectedMarker.label.trim() === ""
      || typeof selectedMarker.value !== "string" || selectedMarker.value.trim() === "") {
      setPaused("nenhum marcador específico está selecionado na Área Restrita");
      return { ok: false, error: state.pausedReason, totals: state.totals };
    }
    if (spec.marker && !markerMatches(first.snapshot, spec.marker, spec.markerValue ?? null)) {
      setPaused("o marcador selecionado na Área Restrita mudou antes da análise");
      return { ok: false, error: state.pausedReason, totals: state.totals };
    }
    spec = {
      ...spec,
      marker: selectedMarker.label,
      markerValue: selectedMarker.value,
    };
    state.marker = selectedMarker.label;
    const discovered = await discoverList(spec.tabId, first.snapshot, spec);
    if (!discovered || state.status === "paused") {
      return { ok: false, error: state.pausedReason ?? "analysis paused", totals: state.totals };
    }
    let restored = discovered;
    if (Array.isArray(spec.inputKeys) && spec.inputKeys.length > 0) {
      restored = await queryMissingProcesses(spec.tabId, discovered, spec);
      if (!restored || state.status === "paused") {
        return { ok: false, error: state.pausedReason ?? "analysis paused", totals: state.totals };
      }
      restored = await restoreAnalysisList(spec.tabId, restored, first.snapshot, spec);
      if (!restored || state.status === "paused") {
        return { ok: false, error: state.pausedReason ?? "analysis paused", totals: state.totals };
      }
    }
    const rows = await analysisRows(spec);
    const marker = rows[0]?.area_restrita
      ? { label: rows[0].area_restrita.marker_label, value: rows[0].area_restrita.marker_value }
      : { label: selectedMarker.label, value: selectedMarker.value };
    const areaSnapshotSha256 = await sha256Hex({
      source_scope: spec.sourceScope,
      marker,
      rows,
    });
    const result = {
      ...(typeof spec.inputListId === "string" ? { input_list_id: spec.inputListId } : {}),
      ...(typeof spec.inputSha256 === "string" ? { input_sha256: spec.inputSha256 } : {}),
      ...(Number.isSafeInteger(spec.inputUniqueCount) ? { input_unique_count: spec.inputUniqueCount } : {}),
      source_scope: spec.sourceScope,
      marker,
      area_snapshot_sha256: areaSnapshotSha256,
      rows,
      totals: clone(state.totals),
      tab_id: spec.tabId,
      frame_id: state.frame?.frameId ?? 0,
    };
    state.status = "stopped";
    state.pausedReason = null;
    return result;
  }

  async function control(action, input = {}) {
    if (!state.runId) throw Object.assign(new Error("no automation run is active"), { code: "RUN_NOT_FOUND" });
    if (input.runId && input.runId !== state.runId) {
      throw Object.assign(new Error("automation run does not match the active controller run"), { code: "RUN_NOT_FOUND" });
    }
    const result = await bridge.controlAutomationRun(state.runId, {
      action,
      eventId: input.eventId ?? eventId(action),
      expectedRevision: Number.isSafeInteger(input.expectedRevision) ? input.expectedRevision : state.revision,
    });
    snapshotStatus(state, result);
    if (action === "pause") state.pausedReason = input.reason ?? state.pausedReason ?? "paused by operator";
    if (action === "resume") state.pausedReason = null;
    if (action === "stop") state.currentIdentity = null;
    return statusToPublic(state);
  }

  async function refreshStatus() {
    if (state.runId && typeof bridge.getAutomationRun === "function") {
      snapshotStatus(state, await bridge.getAutomationRun(state.runId));
    }
    return statusToPublic(state);
  }

  function status(options = {}) {
    if (options.runId && state.runId && options.runId !== state.runId) {
      throw Object.assign(new Error("automation run does not match the active controller run"), { code: "RUN_NOT_FOUND" });
    }
    if (options.refresh) return refreshStatus();
    return statusToPublic(state);
  }

  function nextQueuedIdentity() {
    return state.queue.find((candidate) => !state.completedIdentities.has(identityKey(candidate))) ?? null;
  }

  async function processSnapshot(tabId, frameId, initialSnapshot) {
    let snapshot = initialSnapshot;
    let selectedConfirmed = false;
    const listSignatures = new Set();

    for (let step = 0; step < 100 && state.status === "running"; step += 1) {
      if (snapshot.sector && snapshot.sector !== state.sector) {
        setPaused("setor mudou durante a navegação");
        return;
      }
      if (state.sourceScope
        && (snapshot.role === "list" || snapshot.source_scope !== null)
        && snapshot.source_scope !== state.sourceScope) {
        setPaused("a tela atual não corresponde à origem selecionada");
        return;
      }
      if (state.marker && snapshot.role === "list" && !markerMatches(snapshot, state.marker)) {
        setPaused("a tela atual não confirma o marcador da execução");
        return;
      }
      collectSnapshot(snapshot);

      if (snapshot.role === "list") {
        const signature = (snapshot.identities ?? []).map(identityKey).join("|");
        if (listSignatures.has(signature)) {
          setPaused("page repeated without progress");
          return;
        }
        listSignatures.add(signature);
        const identity = state.currentIdentity ?? nextQueuedIdentity();
        if (!identity) {
          state.status = "completed";
          state.pausedReason = null;
          return;
        }
        const open = actionFor(snapshot, "open_act", identity);
        if (!open) {
          const next = actionFor(snapshot, "next_page");
          if (!next) {
            setPaused("process not found after return; manual intervention required");
            return;
          }
          const moved = await navigate(tabId, frameId, "next_page", null, snapshot.generation, { beforeSnapshot: snapshot });
          if (!moved.ok || !moved.snapshot || moved.snapshot.role !== "list") {
            setPaused("process lookup pagination requires manual intervention");
            return;
          }
          snapshot = moved.snapshot;
          continue;
        }
        const moved = await navigate(tabId, frameId, "open_act", identity, snapshot.generation);
        if (!moved.ok) {
          if (state.status !== "paused") setPaused("process link changed; manual intervention required");
          return;
        }
        state.currentIdentity = identity;
        selectedConfirmed = false;
        if (!moved.snapshot) return;
        snapshot = moved.snapshot;
        continue;
      }

      let identity = state.currentIdentity;
      if (!identity && snapshot.role === "interested") {
        const queued = nextQueuedIdentity();
        if (queued && actionFor(snapshot, "select_interested", queued)) {
          state.currentIdentity = queued;
          identity = queued;
        }
      }
      if (!identity && (snapshot.role === "form" || snapshot.role === "buttons")) {
        // A service worker restart between "abrir ato" and the act frame boot
        // leaves the run without a current identity. Resume only the next queued
        // item, and only when the act screen confirms that exact identity.
        const resumed = resumeIdentityFromActSnapshot(snapshot);
        const queued = nextQueuedIdentity();
        if (resumed && queued && identityKey(resumed) === identityKey(queued)) {
          state.currentIdentity = queued;
          identity = queued;
        }
      }
      if (!identity) return;
      if (snapshot.role === "interested") {
        if (selectedConfirmed) {
          const back = actionFor(snapshot, "return_list", identity);
          if (!back) return;
          const moved = await navigate(tabId, frameId, "return_list", identity, snapshot.generation);
          if (!moved.ok) {
            if (state.status !== "paused") setPaused("return to process list requires manual intervention");
            return;
          }
          state.completedIdentities.add(identityKey(identity));
          state.currentIdentity = null;
          selectedConfirmed = false;
          listSignatures.clear();
          if (!moved.snapshot) return;
          snapshot = moved.snapshot;
          continue;
        }
        const select = actionFor(snapshot, "select_interested", identity);
        if (!select) {
          setPaused("interessado não localizado; manual intervention required");
          return;
        }
        const moved = await navigate(tabId, frameId, "select_interested", identity, snapshot.generation);
        if (!moved.ok) {
          if (state.status !== "paused") setPaused("interested selection changed; manual intervention required");
          return;
        }
        selectedConfirmed = true;
        if (!moved.snapshot) return;
        snapshot = moved.snapshot;
        continue;
      }

      if (snapshot.role === "form" || snapshot.role === "buttons") {
        if (resolveAutomaticAct) {
          const preparation = await prepareAndVerifyForm(tabId, frameId, snapshot, identity);
          if (preparation.stop || preparation.paused) return;
        }
        const back = actionFor(snapshot, "return_list", identity);
        if (!back) return;
        const moved = await navigate(tabId, frameId, "return_list", identity, snapshot.generation);
        if (!moved.ok) {
          if (state.status !== "paused") setPaused("return to process list requires manual intervention");
          return;
        }
        state.completedIdentities.add(identityKey(identity));
        state.currentIdentity = null;
        listSignatures.clear();
        if (!moved.snapshot) return;
        snapshot = moved.snapshot;
        continue;
      }
      return;
    }
    if (state.status === "running") setPaused("navigation loop exceeded the safe action limit");
  }

  async function driveSnapshot(tabId, frameId, snapshot) {
    if (state.status !== "running") return;
    if (inFlight) {
      pendingPortalSnapshot = { tabId, frameId, snapshot: clone(snapshot) };
      return;
    }
    const currentFlight = processSnapshot(tabId, frameId, snapshot);
    inFlight = currentFlight;
    try {
      await currentFlight;
    } finally {
      if (inFlight === currentFlight) inFlight = null;
      const pending = pendingPortalSnapshot;
      pendingPortalSnapshot = null;
      if (pending && state.status === "running") {
        await driveSnapshot(pending.tabId, pending.frameId, pending.snapshot);
      }
    }
  }

  async function handlePortalEvent(event) {
    if (!isRecord(event) || !Number.isSafeInteger(event.tabId) || !Number.isSafeInteger(event.frameId)) return statusToPublic(state);
    const eventType = event.type ?? event.event?.type;
    const snapshot = event.snapshot ?? event.event?.snapshot ?? null;
    if (state.tabId === null) {
      if (isPortalSnapshot(snapshot)) registerFrame(event.tabId, event.frameId, snapshot);
      return statusToPublic(state);
    }
    if (event.tabId !== state.tabId) return statusToPublic(state);
    const expectedPagination = expectedNavigation?.action === "next_page"
      && expectedNavigation.tabId === event.tabId;
    const progressedPaginationEvent = expectedPagination
      && eventType === "snapshot"
      && isPortalSnapshot(snapshot)
      && snapshot.role === "list"
      && acceptedProgressedPaginationSnapshot(expectedNavigation.beforeSnapshot, snapshot);
    // Area Restrita opens Complementar Ato in a new sibling frame. The first
    // event from that frame is the unselected interested-party surface, not a
    // form yet, so it must be accepted before the controller can select the
    // radio and continue with field preparation.
    if (state.frame
      && event.frameId !== state.frame.frameId
      && !["interested", "form"].includes(snapshot?.role)
      && !progressedPaginationEvent) return statusToPublic(state);
    if (progressedPaginationEvent) {
      expectedNavigation.progressedSnapshot = {
        frameId: event.frameId,
        snapshot: clone(snapshot),
      };
      registerFrame(event.tabId, event.frameId, snapshot);
      return statusToPublic(state);
    }
    if (eventType === "navigation") invalidateFrames(event.tabId);
    if (eventType === "frame_unavailable" || eventType === "tab_closed") {
      setPaused(eventType === "tab_closed" ? "tab closed" : "portal frame unavailable");
      return statusToPublic(state);
    }
    if (eventType === "manual_navigation") {
      setPaused("manual navigation detected");
      return statusToPublic(state);
    }
    if (eventType === "sector_changed" || (snapshot?.sector && state.sector && snapshot.sector !== state.sector)) {
      setPaused("setor mudou durante a navegação");
      return statusToPublic(state);
    }
    if (eventType === "snapshot"
      && snapshot?.role === "unknown"
      && expectedNavigation?.action === "next_page"
      && expectedNavigation.tabId === event.tabId
      && expectedNavigation.frameId === event.frameId) {
      // The legacy form submit briefly exposes an incomplete document in the
      // same frame. The replacement list snapshot is the authoritative guard.
      return statusToPublic(state);
    }
    if (["discovering", "running"].includes(state.status)
      && isPortalSnapshot(snapshot) && snapshot.role === "unknown") {
      return pauseAndPersist(UNRECOGNIZED_PORTAL_SCREEN_REASON);
    }
    if (isPortalSnapshot(snapshot)) {
      registerFrame(event.tabId, Number.isSafeInteger(event.frameId) ? event.frameId : 0, snapshot);
      await driveSnapshot(event.tabId, Number.isSafeInteger(event.frameId) ? event.frameId : 0, snapshot);
    }
    return statusToPublic(state);
  }

  async function consumeCommand(input = {}) {
    if (typeof bridge.consumeAutomationCommand !== "function") {
      throw Object.assign(new Error("automation bridge cannot consume commands"), { code: "AUTOMATION_UNAVAILABLE" });
    }
    if (state.status !== "running" || input.runId !== state.runId) {
      throw Object.assign(new Error("automation command is not active"), { code: "COMMAND_NOT_READY" });
    }
    const expectedFrameId = state.submitFrame?.frameId ?? state.frame?.frameId;
    if (input.tabId !== state.tabId || input.frameId !== expectedFrameId
      || !["form", "buttons"].includes(state.frame?.role) || input.generation !== state.frame?.generation) {
      throw Object.assign(new Error("automation command frame is not authorized"), { code: "COMMAND_FRAME_MISMATCH" });
    }
    if (!sameCanonicalIdentity(input.identity, state.currentIdentity)) {
      throw Object.assign(new Error("automation command identity changed"), { code: "COMMAND_IDENTITY_MISMATCH" });
    }
    const result = await bridge.consumeAutomationCommand(
      state.runId,
      input.commandId,
      input.expectedRevision,
    );
    snapshotStatus(state, result);
    return result;
  }

  if (chromeApi.tabs.onRemoved?.addListener) {
    chromeApi.tabs.onRemoved.addListener((tabId) => {
      if (tabId === state.tabId && ACTIVE_STATUSES.has(state.status)) {
        setPaused("tab closed");
        expectedNavigation = null;
        invalidateFrames(tabId);
      }
    });
  }
  const hasNativeNavigationEvents = typeof chromeApi.webNavigation?.onBeforeNavigate?.addListener === "function";
  if (hasNativeNavigationEvents) {
    chromeApi.webNavigation.onBeforeNavigate.addListener(({ tabId, frameId }) => {
      if (tabId !== state.tabId || frameId !== 0 || !ACTIVE_STATUSES.has(state.status)) return;
      expectedNavigation = null;
      invalidateFrames(tabId);
      setPaused("manual navigation detected");
    });
  }
  if (chromeApi.tabs.onUpdated?.addListener) {
    chromeApi.tabs.onUpdated.addListener((tabId, changeInfo) => {
      if (tabId !== state.tabId || !ACTIVE_STATUSES.has(state.status)) return;
      // Native tabs.onUpdated reports aggregate tab loading without a frameId.
      // Only webNavigation can distinguish a top-level navigation from the
      // legacy portal loading a child frame. Retain the fallback for adapters
      // without webNavigation and their explicitly attributed notifications.
      if (hasNativeNavigationEvents && !Number.isSafeInteger(changeInfo?.frameId)) return;
      const hasNavigationMarker = Number.isSafeInteger(changeInfo?.frameId)
        && typeof changeInfo?.navigationToken === "string"
        && changeInfo.navigationToken.length > 0;
      const matchesExpectedNavigation = hasNavigationMarker
        && expectedNavigation?.tabId === tabId
        && changeInfo.frameId === expectedNavigation.frameId
        && changeInfo.navigationToken === expectedNavigation.token;
      const sameExpectedFrame = Number.isSafeInteger(changeInfo?.frameId)
        && expectedNavigation?.tabId === tabId
        && changeInfo.frameId === expectedNavigation.frameId;
      if (changeInfo?.status === "complete" && matchesExpectedNavigation) {
        expectedNavigation = null;
        return;
      }
      if (changeInfo?.status !== "loading") return;
      if (matchesExpectedNavigation || sameExpectedFrame) {
        expectedNavigation.loadingObserved = true;
        return;
      }
      if (expectedNavigation?.action === "next_page") {
        // A legacy form submit can emit loading for the wrapper or a sibling
        // portal frame before the list iframe is recreated. The replacement
        // snapshot below is the authoritative guard for scope and progress.
        expectedNavigation.loadingObserved = true;
        return;
      }
      if (expectedNavigation?.tabId === tabId) {
        setPaused("navigation token/frame mismatch");
        expectedNavigation = null;
        return;
      }
      // Explicitly attributed adapter events for child frames are checked by
      // the act identity, generation and field-equality gates instead.
      if (Number.isSafeInteger(changeInfo?.frameId) && changeInfo.frameId !== 0) return;
      invalidateFrames(tabId);
      setPaused("manual navigation detected");
    });
  }

  return Object.freeze({
    start,
    analyze,
    pause: (input) => control("pause", input),
    resume: (input) => control("resume", input),
    stop: (input) => control("stop", input),
    consumeCommand,
    verifySubmitState,
    handleSubmitFrameReady,
    rehydrate,
    status,
    handlePortalEvent,
    ranker,
  });
}
