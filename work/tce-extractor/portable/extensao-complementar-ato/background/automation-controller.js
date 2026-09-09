import { MESSAGE_TYPES, createMessage } from "../lib/messages.js";
import {
  validateAutomationIdentity,
  validateAutomationRunSpec,
} from "../lib/automation-schema.js";
import { AUTOMATION_FIELDS, prepareAutomaticAct } from "../lib/automation-preflight.js";

export const PORTAL_FRAME_REGISTRATIONS_STORAGE_KEY = "portal-frame-registrations:v1";
const ACTIVE_STATUSES = new Set(["discovering", "running", "paused"]);
const PROCESS_KEY_RE = /^\d+\/\d{4}$/u;

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

function eventId(prefix = "event") {
  return `${prefix}-${Date.now()}`;
}

function statusToPublic(state) {
  return clone({
    runId: state.runId,
    run_id: state.runId,
    status: state.status,
    revision: state.revision,
    tabId: state.tabId,
    sector: state.sector,
    queueFrozen: state.queueFrozen,
    currentIdentity: state.currentIdentity,
    pausedReason: state.pausedReason,
    totals: state.totals,
    frame: state.frame,
    items: state.queue.map((identity, index) => ({
      item_id: itemId(identity),
      ordinal: index + 1,
      identity: clone(identity),
      state: index === 0 && state.currentIdentity ? "active" : "queued",
    })),
    simulation: {
      is_simulated: true,
      real_send_enabled: false,
      notice: "Navegação sintética/controlada; não comprova envio no portal real.",
    },
  });
}

function snapshotStatus(state, snapshot) {
  if (!isRecord(snapshot)) return;
  if (typeof snapshot.status === "string") state.status = snapshot.status;
  if (Number.isSafeInteger(snapshot.revision)) state.revision = snapshot.revision;
  if (typeof snapshot.run_id === "string") state.runId = snapshot.run_id;
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

function actionFor(snapshot, action, identity = null) {
  return (snapshot?.actions ?? []).find((candidate) => (
    candidate?.action === action
    && candidate.enabled !== false
    && (identity === null
      || identityKey(identityFromAction(candidate)) === identityKey(identity)
      || (action === "return_list" && identityFromAction(candidate) === null))
  )) ?? null;
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
  let frameLoadPromise = null;
  let framePersistPromise = Promise.resolve();
  let inFlight = null;
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
    queueFrozen: false,
    currentIdentity: null,
    pausedReason: null,
    frame: null,
    queue: [],
    seenIdentities: new Set(),
    completedIdentities: new Set(),
    totals: { discovered: 0, unique: 0, pending: 0 },
    eventPrefix: "run",
  };

  async function loadFrames() {
    if (!frameLoadPromise) {
      frameLoadPromise = (async () => {
        if (typeof session?.get !== "function") return;
        const stored = await session.get([PORTAL_FRAME_REGISTRATIONS_STORAGE_KEY]);
        const entries = stored?.[PORTAL_FRAME_REGISTRATIONS_STORAGE_KEY];
        if (!Array.isArray(entries)) return;
        for (const entry of entries) {
          if (!isRecord(entry) || !Number.isSafeInteger(entry.tabId) || !Number.isSafeInteger(entry.frameId)) continue;
          frames.set(`${entry.tabId}:${entry.frameId}`, clone(entry));
        }
      })();
    }
    return frameLoadPromise;
  }

  function persistFrames() {
    if (typeof session?.set !== "function") return Promise.resolve();
    const entries = [...frames.values()].sort((left, right) => left.tabId - right.tabId || left.frameId - right.frameId);
    framePersistPromise = framePersistPromise.catch(() => undefined).then(() => session.set({
      [PORTAL_FRAME_REGISTRATIONS_STORAGE_KEY]: entries,
    }));
    return framePersistPromise;
  }

  function registerFrame(tabId, frameId, snapshot) {
    if (!Number.isSafeInteger(tabId) || tabId < 0 || !Number.isSafeInteger(frameId) || frameId < 0 || !isPortalSnapshot(snapshot)) return;
    const registration = {
      tabId,
      frameId,
      role: snapshot.role,
      generation: snapshot.generation,
      sector: snapshot.sector ?? null,
      observedAt: now(),
    };
    frames.set(`${tabId}:${frameId}`, registration);
    state.frame = { frameId, role: snapshot.role, generation: snapshot.generation, sector: snapshot.sector ?? null };
    void persistFrames().catch(() => undefined);
  }

  function invalidateFrames(tabId) {
    for (const key of [...frames.keys()]) {
      if (key.startsWith(`${tabId}:`)) frames.delete(key);
    }
    if (state.tabId === tabId) state.frame = null;
    void persistFrames().catch(() => undefined);
  }

  function setPaused(reason) {
    state.status = "paused";
    state.pausedReason = reason;
  }

  function collectSnapshot(snapshot) {
    if (state.queueFrozen) return;
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
      state.queue.push(identity);
    }
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
    if (portalBefore?.generation !== portalAfter?.generation) return "portal generation changed during preparation";
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
    return { stop: !verified };
  }

  async function readPortalSnapshot(tabId, frameId = state.frame?.frameId ?? null) {
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

  async function navigate(tabId, frameId, action, identity, generation) {
    const navigation = {
      token: `${state.eventPrefix}-navigation-${String(++navigationToken)}`,
      tabId,
      frameId,
      action,
      generation,
      loadingObserved: false,
    };
    expectedNavigation = navigation;
    try {
      const response = await sendPortalMessage(tabId, MESSAGE_TYPES.PORTAL_NAVIGATE, {
        action,
        identity: identity ?? null,
        expected_generation: generation,
      }, frameId, navigation.token);
      if (response?.ok !== true) {
        setPaused(response?.error?.code === "TAB_CLOSED" ? "tab closed" : "portal frame unavailable");
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
      return { ok: true, snapshot };
    } catch (error) {
      setPaused(error?.code === "TAB_CLOSED" ? "tab closed" : "portal frame unavailable");
      return { ok: false, error };
    } finally {
      if (expectedNavigation === navigation && !navigation.loadingObserved) expectedNavigation = null;
    }
  }

  async function discoverList(tabId, initial) {
    let current = initial;
    const pageSignatures = new Set();
    for (let index = 0; index < 100; index += 1) {
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
      const moved = await navigate(tabId, frameId, "next_page", null, current.generation);
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
      const nextSignature = (nextSnapshot.identities ?? []).map(identityKey).join("|");
      if (nextSignature === signature) {
        setPaused("page repeated without progress");
        return nextSnapshot;
      }
      current = nextSnapshot;
    }
    setPaused("pagination exceeded the safe page limit");
    return current;
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

  async function start(input, suppliedEventId) {
    const spec = input?.spec ?? input;
    const startEventId = input?.eventId ?? suppliedEventId ?? eventId("start");
    validateAutomationRunSpec(spec);
    if (ACTIVE_STATUSES.has(state.status)) {
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
      queueFrozen: false,
      currentIdentity: null,
      pausedReason: null,
      frame: null,
      queue: [],
      seenIdentities: new Set(),
      completedIdentities: new Set(),
      totals: { discovered: 0, unique: 0, pending: 0 },
      eventPrefix: eventPrefix(startEventId),
    };
    eventSequence = 0;
    const storedFrames = [...frames.values()].filter((entry) => entry.tabId === spec.tabId);
    if (storedFrames.length === 1) {
      const stored = storedFrames[0];
      state.frame = { frameId: stored.frameId, role: stored.role, generation: stored.generation, sector: stored.sector ?? null };
    }
    const run = await bridge.createAutomationRun(spec, startEventId);
    snapshotStatus(state, run);
    state.status = "discovering";
    const first = await readPortalSnapshot(spec.tabId);
    if (!first) return statusToPublic(state);
    if (first.snapshot.sector && first.snapshot.sector !== spec.sector) {
      setPaused("sector changed before discovery");
      return statusToPublic(state);
    }
    if (first.snapshot.role !== "list") {
      setPaused("manual navigation required: process list not visible");
      return statusToPublic(state);
    }
    const discovered = await discoverList(spec.tabId, first.snapshot);
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
        const moved = await navigate(spec.tabId, state.frame?.frameId ?? 0, "next_page", null, ready.generation);
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
          const moved = await navigate(tabId, frameId, "next_page", null, snapshot.generation);
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

      const identity = state.currentIdentity;
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
          if (preparation.stop) return;
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
    if (state.status !== "running" || inFlight) return;
    inFlight = processSnapshot(tabId, frameId, snapshot).finally(() => { inFlight = null; });
    await inFlight;
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
    if (state.frame && event.frameId !== state.frame.frameId) return statusToPublic(state);
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
    if (input.tabId !== state.tabId || input.frameId !== state.frame?.frameId
      || state.frame?.role !== "buttons" || input.generation !== state.frame?.generation) {
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
  if (chromeApi.tabs.onUpdated?.addListener) {
    chromeApi.tabs.onUpdated.addListener((tabId, changeInfo) => {
      if (tabId !== state.tabId || !ACTIVE_STATUSES.has(state.status)) return;
      const hasNavigationMarker = Number.isSafeInteger(changeInfo?.frameId)
        && typeof changeInfo?.navigationToken === "string"
        && changeInfo.navigationToken.length > 0;
      const matchesExpectedNavigation = hasNavigationMarker
        && expectedNavigation?.tabId === tabId
        && changeInfo.frameId === expectedNavigation.frameId
        && changeInfo.navigationToken === expectedNavigation.token;
      if (changeInfo?.status === "complete" && matchesExpectedNavigation) {
        expectedNavigation = null;
        return;
      }
      if (changeInfo?.status !== "loading") return;
      if (matchesExpectedNavigation) {
        expectedNavigation.loadingObserved = true;
        return;
      }
      if (expectedNavigation?.tabId === tabId) {
        setPaused("navigation token/frame mismatch");
        expectedNavigation = null;
        return;
      }
      invalidateFrames(tabId);
      setPaused("manual navigation detected");
    });
  }

  return Object.freeze({
    start,
    pause: (input) => control("pause", input),
    resume: (input) => control("resume", input),
    stop: (input) => control("stop", input),
    consumeCommand,
    status,
    handlePortalEvent,
    ranker,
  });
}
