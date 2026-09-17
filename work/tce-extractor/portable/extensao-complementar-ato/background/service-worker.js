import { rankPortalOptions } from "../lib/matcher.js";
import { LEGAL_FOUNDATION_RULES_VERSION } from "../lib/legal-foundation.js";
import {
  buildDatasetIndex,
  resolveIndexedRecord,
  STORAGE_KEYS,
  validateDataset,
  validatePortalUrl,
} from "../lib/schema.js";
import {
  MESSAGE_TYPES,
  createMessage,
  validateMessage,
} from "../lib/messages.js";

import { AUTOMATION_FIELDS, isAutomaticLegalDecision } from "../lib/automation-preflight.js";
import { createBridgeClient } from "../lib/bridge-client.js";
import { createAutomationController } from "./automation-controller.js";
import { createLegalContextResolver } from "./legal-context-resolver.js";

export const FRAME_REGISTRATIONS_STORAGE_KEY = "frame-registrations:v1";
export const AUTOMATION_WATCHDOG_ALARM = "automation-watchdog-v1";

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function errorResponse(requestId, code, message) {
  const response = {
    ok: false,
    error: { code, message },
  };
  if (typeof requestId === "string" && requestId.length > 0) response.requestId = requestId;
  return response;
}

function successResponse(message, payload = {}) {
  return {
    ok: true,
    requestId: message.requestId,
    type: message.type,
    payload,
  };
}

function tabIdFromSender(sender) {
  const tabId = sender?.tab?.id;
  return Number.isInteger(tabId) && tabId >= 0 ? tabId : null;
}

function frameIdFromSender(sender) {
  const frameId = sender?.frameId;
  return Number.isInteger(frameId) && frameId >= 0 ? frameId : null;
}

function senderIsExtension(sender, chromeApi) {
  if (typeof sender?.id === "string" && typeof chromeApi?.runtime?.id === "string") {
    return sender.id === chromeApi.runtime.id;
  }
  return typeof sender?.url === "string" && sender.url.startsWith("chrome-extension://");
}

function senderIsExtensionPage(sender, chromeApi) {
  const extensionId = chromeApi?.runtime?.id;
  if (typeof extensionId !== "string" || !extensionId || sender?.id !== extensionId) return false;
  if (!senderIsExtension(sender, chromeApi) || typeof sender?.url !== "string") return false;
  try {
    const parsed = new URL(sender.url);
    return parsed.protocol === "chrome-extension:"
      && parsed.hostname === extensionId
      && parsed.username === ""
      && parsed.password === ""
      && parsed.port === "";
  } catch {
    return false;
  }
}

function clone(value) {
  return value === undefined ? undefined : structuredClone(value);
}

function contextError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

export function createServiceWorker({
  chromeApi,
  ranker = rankPortalOptions,
  now = () => new Date().toISOString(),
  storageArea = chromeApi?.storage?.local,
  bridge = null,
  bridgeClientFactory = createBridgeClient,
  automationController = null,
} = {}) {
  if (!chromeApi?.storage?.local) {
    throw new TypeError("createServiceWorker requires chromeApi.storage.local");
  }

  const storage = storageArea;
  const frameStorage = chromeApi?.storage?.session;
  const frameRegistrations = new Map();
  const clearedTabs = new Set();
  let dataset = null;
  let datasetIndex = null;
  let reviewed = { schemaVersion: 1, records: {} };
  let loadPromise = null;
  let frameRegistrationsLoadPromise = null;
  let framePersistencePromise = Promise.resolve();
  let listenerRegistered = false;
  let bridgeLoadPromise = null;
  let activeBridge = bridge;
  let activeController = automationController;
  let activeAutomationSpec = null;
  let activeAutomationRunId = null;
  let automationStartInFlight = false;
  const legalContextResolver = createLegalContextResolver({
    bridge: {
      getLegalContext: (identity) => {
        if (typeof activeBridge?.getLegalContext !== "function") {
          throw Object.assign(new Error("legal context endpoint unavailable"), {
            code: "LEGAL_CONTEXT_NOT_FOUND",
            status: 404,
          });
        }
        return activeBridge.getLegalContext(identity);
      },
      rebuildLegalContext: (identity) => {
        if (typeof activeBridge?.rebuildLegalContext !== "function") {
          throw Object.assign(new Error("legal context rebuild unavailable"), {
            code: "LEGAL_CONTEXT_NOT_FOUND",
            status: 404,
          });
        }
        return activeBridge.rebuildLegalContext(identity);
      },
    },
    rulesVersion: LEGAL_FOUNDATION_RULES_VERSION,
  });

  function scheduleAutomationWatchdog() {
    if (typeof chromeApi?.alarms?.create !== "function") return;
    chromeApi.alarms.create(AUTOMATION_WATCHDOG_ALARM, { periodInMinutes: 1 });
  }

  function clearAutomationWatchdog() {
    if (typeof chromeApi?.alarms?.clear !== "function") return;
    void Promise.resolve(chromeApi.alarms.clear(AUTOMATION_WATCHDOG_ALARM)).catch(() => undefined);
  }

  function bridgeCredentials(value) {
    if (!isRecord(value)) return null;
    const baseUrl = value[STORAGE_KEYS.BRIDGE_BASE_URL];
    const token = value[STORAGE_KEYS.BRIDGE_TOKEN];
    if (typeof baseUrl !== "string" || !baseUrl || typeof token !== "string" || !token) return null;
    return { baseUrl, token };
  }

  async function loadBridge() {
    if (activeBridge !== null) return activeBridge;
    if (!bridgeLoadPromise) {
      bridgeLoadPromise = (async () => {
        const [localState, sessionState] = await Promise.all([
          typeof storage?.get === "function"
            ? storage.get([STORAGE_KEYS.BRIDGE_BASE_URL, STORAGE_KEYS.BRIDGE_TOKEN])
            : {},
          typeof frameStorage?.get === "function"
            ? frameStorage.get([STORAGE_KEYS.BRIDGE_BASE_URL, STORAGE_KEYS.BRIDGE_TOKEN])
            : {},
        ]);
        const credentials = bridgeCredentials(localState) ?? bridgeCredentials(sessionState);
        if (!credentials || typeof bridgeClientFactory !== "function") return null;
        try {
          activeBridge = bridgeClientFactory(credentials);
        } catch {
          activeBridge = null;
        }
        return activeBridge;
      })().catch(() => null);
    }
    const resolved = await bridgeLoadPromise;
    if (resolved === null) bridgeLoadPromise = null;
    return resolved;
  }

  function controllerFor(currentBridge) {
    if (activeController !== null) return activeController;
    if (!currentBridge
      || typeof currentBridge.createAutomationRun !== "function"
      || typeof currentBridge.controlAutomationRun !== "function"
      || typeof chromeApi?.tabs?.sendMessage !== "function") return null;
    activeController = createAutomationController({
      chromeApi,
      bridge: currentBridge,
      ranker,
      resolveAutomaticAct,
      clock: () => now(),
    });
    return activeController;
  }

  async function storedAutomationSession() {
    if (typeof frameStorage?.get !== "function") return {};
    try {
      return await frameStorage.get([
        STORAGE_KEYS.AUTOMATION_RUN_ID,
        STORAGE_KEYS.AUTOMATION_SPEC,
      ]);
    } catch {
      return {};
    }
  }

  async function persistAutomationSession(runId, spec) {
    if (typeof frameStorage?.set !== "function") return;
    try {
      await frameStorage.set({
        [STORAGE_KEYS.AUTOMATION_RUN_ID]: runId,
        [STORAGE_KEYS.AUTOMATION_SPEC]: clone(spec),
      });
    } catch {
      // The bridge remains the durable source of run state if session storage is unavailable.
    }
  }

  async function clearAutomationSpec() {
    if (typeof frameStorage?.set !== "function") return;
    try {
      await frameStorage.set({ [STORAGE_KEYS.AUTOMATION_SPEC]: null });
    } catch {
      // A historical run id may still be useful to the panel after a stop.
    }
  }

  function specMatchesSnapshot(spec, snapshot) {
    if (!isRecord(spec) || !isRecord(snapshot?.spec)) return true;
    const aliases = [
      ["mode", "mode"],
      ["sector", "sector"],
      ["marker", "marker"],
      ["markerValue", "marker_value"],
      ["autoSubmit", "auto_submit"],
      ["sourceScope", "source_scope"],
      ["acquisitionSource", "acquisition_source"],
      ["lotSize", "lot_size"],
      ["analysisId", "analysis_id"],
      ["previewHash", "preview_hash"],
    ];
    return aliases.every(([camel, wire]) => {
      if (!Object.hasOwn(snapshot.spec, wire) || !Object.hasOwn(spec, camel)) return true;
      return JSON.stringify(snapshot.spec[wire]) === JSON.stringify(spec[camel]);
    });
  }

  async function rehydrateAutomationState(currentBridge, requestedRunId) {
    if (currentBridge === null || typeof currentBridge.getAutomationRun !== "function") return null;
    const stored = await storedAutomationSession();
    const runId = requestedRunId ?? stored?.[STORAGE_KEYS.AUTOMATION_RUN_ID];
    if (typeof runId !== "string" || !runId) return null;
    if (activeController !== null && activeAutomationRunId === runId) {
      return { controller: activeController, snapshot: null };
    }
    const snapshot = await currentBridge.getAutomationRun(runId);
    const active = ["discovering", "running", "paused"].includes(snapshot?.status);
    if (!active) return { controller: null, snapshot };
    let currentController = controllerFor(currentBridge);
    if (currentController === null || typeof currentController.rehydrate !== "function") {
      return { controller: currentController, snapshot };
    }
    const spec = stored?.[STORAGE_KEYS.AUTOMATION_RUN_ID] === snapshot.run_id
      && isRecord(stored?.[STORAGE_KEYS.AUTOMATION_SPEC])
      && specMatchesSnapshot(stored[STORAGE_KEYS.AUTOMATION_SPEC], snapshot)
      ? stored[STORAGE_KEYS.AUTOMATION_SPEC]
      : null;
    await currentController.rehydrate(snapshot, spec);
    activeAutomationRunId = snapshot.run_id;
    activeAutomationSpec = spec;
    scheduleAutomationWatchdog();
    return { controller: currentController, snapshot };
  }

  function isStoredFrameRegistration(value) {
    return isRecord(value)
      && Number.isInteger(value.tabId)
      && value.tabId >= 0
      && Number.isInteger(value.frameId)
      && value.frameId >= 0;
  }

  async function loadFrameRegistrations() {
    if (!frameRegistrationsLoadPromise) {
      frameRegistrationsLoadPromise = (async () => {
        if (typeof frameStorage?.get !== "function") return;
        const stored = await frameStorage.get([FRAME_REGISTRATIONS_STORAGE_KEY]);
        const entries = stored?.[FRAME_REGISTRATIONS_STORAGE_KEY];
        if (!Array.isArray(entries)) return;
        for (const entry of entries) {
          if (!isStoredFrameRegistration(entry) || clearedTabs.has(entry.tabId)) continue;
          const registrations = frameRegistrations.get(entry.tabId) ?? new Map();
          if (!registrations.has(entry.frameId)) {
            registrations.set(entry.frameId, { frameId: entry.frameId });
          }
          frameRegistrations.set(entry.tabId, registrations);
        }
      })();
    }
    return frameRegistrationsLoadPromise;
  }

  function serializedFrameRegistrations() {
    const serialized = [];
    for (const [tabId, registrations] of frameRegistrations) {
      for (const frameId of registrations.keys()) {
        serialized.push({ tabId, frameId });
      }
    }
    return serialized.sort((left, right) => left.tabId - right.tabId || left.frameId - right.frameId);
  }

  function persistFrameRegistrations() {
    if (typeof frameStorage?.set !== "function") return Promise.resolve();
    const state = {
      [FRAME_REGISTRATIONS_STORAGE_KEY]: serializedFrameRegistrations(),
    };
    framePersistencePromise = framePersistencePromise
      .catch(() => undefined)
      .then(() => frameStorage.set(state));
    return framePersistencePromise;
  }

  function clearFrame(tabId) {
    clearedTabs.add(tabId);
    frameRegistrations.delete(tabId);
    void loadFrameRegistrations()
      .then(() => {
        frameRegistrations.delete(tabId);
        return persistFrameRegistrations();
      })
      .catch(() => undefined);
  }

  function registrationsForTab(tabId) {
    const registrations = frameRegistrations.get(tabId);
    return registrations ? [...registrations.values()].map(clone) : [];
  }

  function clearRegisteredFrame(tabId, frameId) {
    const registrations = frameRegistrations.get(tabId);
    if (!registrations) return;
    registrations.delete(frameId);
    if (registrations.size === 0) frameRegistrations.delete(tabId);
    void persistFrameRegistrations().catch(() => undefined);
  }

  function getFrameRegistration(tabId) {
    const registrations = registrationsForTab(tabId);
    if (registrations.length === 0) return null;
    return registrations.length === 1 ? registrations[0] : null;
  }

  function getFrameRegistrations(tabId) {
    return registrationsForTab(tabId);
  }

  async function loadState() {
    if (!loadPromise) {
      loadPromise = storage.get([
        STORAGE_KEYS.DATASET,
        STORAGE_KEYS.DATASET_INDEX,
        STORAGE_KEYS.REVIEWED,
      ]).then(async (stored) => {
        const storedDataset = stored?.[STORAGE_KEYS.DATASET];
        if (storedDataset !== undefined) {
          await validateDataset(storedDataset);
          dataset = storedDataset;
          datasetIndex = buildDatasetIndex(storedDataset);
        }
        const storedReviewed = stored?.[STORAGE_KEYS.REVIEWED];
        if (isRecord(storedReviewed) && isRecord(storedReviewed.records)) {
          reviewed = storedReviewed;
        }
      });
    }
    return loadPromise;
  }

  function reviewedValue(processKey, interestedNormalized) {
    return reviewed.records?.[`${processKey}\u0000${interestedNormalized}`] === true;
  }

  async function currentTabRegistration(sender) {
    await loadFrameRegistrations();
    const tabId = tabIdFromSender(sender);
    const extensionSender = senderIsExtension(sender, chromeApi);
    if (!extensionSender && tabId !== null) {
      const registrations = frameRegistrations.get(tabId);
        if (registrations?.size > 0) return { tabId };
    }

    if (extensionSender && typeof chromeApi.tabs?.query === "function") {
      const activeTabs = await chromeApi.tabs.query({ active: true, currentWindow: true });
      for (const activeTab of activeTabs ?? []) {
        const activeTabId = activeTab?.id;
        if (!Number.isInteger(activeTabId) || activeTabId < 0) continue;
        const registrations = frameRegistrations.get(activeTabId);
        if (registrations?.size > 0) return { tabId: activeTabId };
      }
    }

    if (tabId === null) return { error: errorResponse(null, "TAB_REQUIRED", "a tab sender is required") };
    return { error: errorResponse(null, "FRAME_NOT_REGISTERED", "no form frame is registered for this tab") };
  }

  function isFormSnapshotResponse(response) {
    return response?.ok === true
      && isRecord(response.payload)
      && isRecord(response.payload.process)
      && Object.hasOwn(response.payload, "interested")
      && isRecord(response.payload.options)
      && isRecord(response.payload.fields);
  }

  async function discoverCurrentFrame(tabId, requestId) {
    await loadFrameRegistrations();
    const registrations = registrationsForTab(tabId);
    if (registrations.length === 0) {
      return { error: errorResponse(requestId, "FRAME_NOT_REGISTERED", "no form frame is registered for this tab") };
    }

    const candidates = [];
    for (const registration of registrations.sort((left, right) => left.frameId - right.frameId)) {
      const discovery = createMessage(
        MESSAGE_TYPES.GET_FORM_SNAPSHOT,
        {},
        requestId,
      );
      try {
        const response = await chromeApi.tabs.sendMessage(
          tabId,
          discovery,
          { frameId: registration.frameId },
        );
        if (isFormSnapshotResponse(response)) candidates.push({ registration, response });
      } catch {
        // A frame that is hidden or mid-navigation may not answer. Keep its
        // registration so it can become the visible frame on a later request.
      }
    }

    if (candidates.length === 0) {
      return { error: errorResponse(requestId, "FORM_NOT_VISIBLE", "no visible valid form frame is available") };
    }
    if (candidates.length > 1) {
      return { error: errorResponse(requestId, "AMBIGUOUS_FORM_FRAME", "more than one visible valid form frame is available") };
    }
    return candidates[0];
  }

  async function forwardToFrame(message, sender) {
    if (typeof chromeApi.tabs?.sendMessage !== "function") {
      return errorResponse(message.requestId, "TABS_API_UNAVAILABLE", "chrome.tabs.sendMessage is unavailable");
    }
    const target = await currentTabRegistration(sender);
    if (target.error) return errorResponse(message.requestId, target.error.error.code, target.error.error.message);
    const discovered = await discoverCurrentFrame(target.tabId, message.requestId);
    if (discovered.error) return discovered.error;
    if (message.type === MESSAGE_TYPES.GET_FORM_SNAPSHOT) {
      const forwarded = clone(discovered.response);
      if (isRecord(forwarded?.payload)) {
        forwarded.payload.bridgeContext = {
          tab_id: target.tabId,
          frame_id: discovered.registration.frameId,
        };
      }
      return successResponse(message, forwarded);
    }
    try {
      const result = await chromeApi.tabs.sendMessage(
        target.tabId,
        message,
        { frameId: discovered.registration.frameId },
      );
      return successResponse(message, result === undefined ? {} : result);
    } catch (error) {
      clearRegisteredFrame(target.tabId, discovered.registration.frameId);
      return errorResponse(message.requestId, "FRAME_UNAVAILABLE", error instanceof Error ? error.message : "form frame is unavailable");
    }
  }

  async function importDataset(message) {
    const importedDataset = message.payload.dataset;
    await validateDataset(importedDataset);
    const nextIndex = buildDatasetIndex(importedDataset);
    await loadState();
    const nextReviewed = message.payload.preserveReviewed === true
      ? { schemaVersion: 1, records: clone(reviewed.records) }
      : { schemaVersion: 1, records: {} };
    await storage.set({
      [STORAGE_KEYS.DATASET]: importedDataset,
      [STORAGE_KEYS.DATASET_INDEX]: nextIndex,
      [STORAGE_KEYS.REVIEWED]: nextReviewed,
    });
    dataset = importedDataset;
    datasetIndex = nextIndex;
    reviewed = nextReviewed;
    loadPromise = Promise.resolve();
    return successResponse(message, {
      batchId: importedDataset.batch.id,
      processCount: importedDataset.batch.process_count,
      recordCount: importedDataset.batch.record_count,
    });
  }

  async function getMatch(message) {
    await loadState();
    if (!dataset || !datasetIndex) {
      return successResponse(message, { record: null, matches: {}, reason: "NO_DATASET" });
    }
    const {
      processKey,
      interestedNormalized,
      options,
      datasetSha256,
      rulesVersion,
      contextRevision,
    } = message.payload;
    const record = resolveIndexedRecord(datasetIndex, processKey, interestedNormalized);
    if (!record) return successResponse(message, { record: null, matches: {}, reason: "RECORD_NOT_FOUND" });

    const currentDatasetSha256 = dataset.batch.logical_sha256;
    if (datasetSha256 !== undefined && datasetSha256 !== currentDatasetSha256) {
      throw contextError("CONTEXT_DATASET_MISMATCH", "context dataset hash differs from the loaded dataset");
    }
    // The panel no longer owns the legal context: the worker resolves it and
    // the guard below fails closed when the resolution is blocked.
    await loadBridge();
    const resolution = await legalContextResolver.ensureLegalContext({
      identity: { processKey, interestedNormalized },
      datasetSha256: currentDatasetSha256,
    });

    const matches = {};
    for (const [field, fieldOptions] of Object.entries(options)) {
      const documentaryField = record.fields[field];
      const documentaryValue = documentaryField?.source_value ?? documentaryField?.form_value ?? "";
      matches[field] = ranker({
        field,
        documentaryValue,
        hints: {},
        options: fieldOptions,
        context: field === "fundamento_legal" ? resolution.context : null,
      });
    }
    const payload = {
      record: clone(record),
      matches,
      reviewed: reviewedValue(processKey, record.interested.normalized),
    };
    if (matches.fundamento_legal !== undefined) {
      payload.context_status = resolution.status;
      payload.context_source = resolution.source;
      payload.context_reason = resolution.reason;
      const legalMatch = matches.fundamento_legal;
      if (legalMatch !== null && typeof legalMatch === "object") {
        legalMatch.legalDecision = {
          ...(legalMatch.legalDecision ?? {}),
          context_status: resolution.status,
          context_source: resolution.source,
          context_reason: resolution.reason,
        };
        const rulesVersion = resolution.context?.rules_version;
        if (typeof rulesVersion === "string" && rulesVersion) {
          legalMatch.legalDecision.rules_version = rulesVersion;
        } else if (typeof LEGAL_FOUNDATION_RULES_VERSION === "string") {
          // Fall back to the rules the worker itself is enforcing, so the UI
          // can always tell which legal rules produced the decision.
          legalMatch.legalDecision.rules_version = LEGAL_FOUNDATION_RULES_VERSION;
        }
      }
    }
    return successResponse(message, payload);
  }

  async function resolveAutomaticAct(identity, formSnapshot, portalSnapshot) {
    await loadState();
    const record = datasetIndex
      ? resolveIndexedRecord(datasetIndex, identity.processKey, identity.interestedNormalized)
      : null;
    if (!record) {
      return {
        record: null,
        context: null,
        legalDecision: null,
        matchedValues: {},
        matchKinds: {},
      };
    }

    // Automatic and manual preparation resolve the legal context through the
    // same worker-owned resolver.
    await loadBridge();
    const resolution = await legalContextResolver.ensureLegalContext({
      identity: {
        processKey: identity.processKey,
        interestedNormalized: identity.interestedNormalized,
      },
      datasetSha256: dataset.batch.logical_sha256,
    });
    const context = resolution.context;
    if (context !== null
      && activeAutomationSpec?.rulesVersion
      && context.rules_version !== activeAutomationSpec.rulesVersion) {
      throw contextError("RULES_VERSION_MISMATCH", "context rules version differs from the active automation run");
    }

    const matches = {};
    const matchedValues = {};
    let legalDecision = null;
    for (const field of AUTOMATION_FIELDS) {
      const options = Array.isArray(formSnapshot?.options?.[field]) ? formSnapshot.options[field] : [];
      const documentaryValue = record.fields?.[field]?.source_value
        ?? record.fields?.[field]?.form_value
        ?? "";
      const result = ranker({
        field,
        documentaryValue,
        hints: {},
        options,
        context: field === "fundamento_legal" ? context : null,
      });
      if (field === "fundamento_legal") legalDecision = result?.legalDecision ?? null;
      const optionValue = result?.optionValue;
      const optionValueIsPresent = Array.isArray(options) && options.some((option) => (
        isRecord(option) ? option.value === optionValue : option === optionValue
      ));
      const legalDecisionAutomatic = field !== "fundamento_legal"
        || isAutomaticLegalDecision(result?.legalDecision);
      if ((field === "modalidade" || field === "fundamento_legal")
        && typeof optionValue === "string"
        && optionValue.trim() !== ""
        && optionValueIsPresent
        && legalDecisionAutomatic) {
        matchedValues[field] = optionValue;
      }
      const kind = result?.kind;
      matches[field] = field === "fundamento_legal" && !legalDecisionAutomatic
        ? "tie"
        : kind === "exact" || kind === "probable" || kind === "tie"
          ? kind
          : "probable";
    }
    return {
      record: {
        ...clone(record),
        dataset_sha256: dataset.batch.logical_sha256,
      },
      context: clone(context),
      legalDecision: clone(legalDecision),
      matchedValues,
      matchKinds: matches,
    };
  }

  function automationUnavailable(message) {
    return errorResponse(message.requestId, "AUTOMATION_UNAVAILABLE", "o serviço local não expõe a API de automação; o modo manual permanece disponível");
  }

  function authorizedPortalFrame(sender) {
    if (senderIsExtensionPage(sender, chromeApi)) return null;
    const tabId = tabIdFromSender(sender);
    const frameId = frameIdFromSender(sender);
    const senderUrl = typeof sender?.url === "string" ? sender.url : sender?.tab?.url;
    const tabUrl = sender?.tab?.url;
    if (
      tabId === null
      || frameId === null
      || typeof chromeApi?.runtime?.id !== "string"
      || sender?.id !== chromeApi.runtime.id
      || !validatePortalUrl(senderUrl)
      || (tabUrl !== undefined && !validatePortalUrl(tabUrl))
    ) return null;
    return { tabId, frameId, senderUrl };
  }

  async function handleConsumeCommandMessage(message, sender) {
    const frame = authorizedPortalFrame(sender);
    if (frame === null) {
      return errorResponse(message.requestId, "UNAUTHORIZED", "consumo deve vir do frame de botões autorizado");
    }
    const currentBridge = await loadBridge();
    let currentController = controllerFor(currentBridge);
    const restored = await rehydrateAutomationState(currentBridge, message.payload.runId);
    if (restored?.controller) currentController = restored.controller;
    if (currentController === null || typeof currentController.consumeCommand !== "function") {
      return automationUnavailable(message);
    }
    try {
      const result = await currentController.consumeCommand({
        ...message.payload,
        tabId: frame.tabId,
        frameId: frame.frameId,
      });
      return successResponse(message, result);
    } catch (error) {
      return errorResponse(message.requestId, error?.code || "COMMAND_ERROR", error instanceof Error ? error.message : "command consumption failed");
    }
  }

  async function handleVerifySubmitStateMessage(message, sender) {
    if (senderIsExtensionPage(sender, chromeApi)
      || typeof chromeApi?.runtime?.id !== "string"
      || sender?.id !== chromeApi.runtime.id) {
      return errorResponse(message.requestId, "UNAUTHORIZED", "a verificação deve vir do frame de botões autorizado");
    }
    const frame = authorizedPortalFrame(sender);
    if (frame === null || message.payload.command.frame_id !== frame.frameId) {
      return errorResponse(message.requestId, "UNAUTHORIZED", "a verificação deve vir do frame de botões autorizado");
    }
    const currentBridge = await loadBridge();
    let currentController = controllerFor(currentBridge);
    const restored = await rehydrateAutomationState(currentBridge, message.payload.runId);
    if (restored?.controller) currentController = restored.controller;
    if (currentController === null || typeof currentController.verifySubmitState !== "function") {
      return automationUnavailable(message);
    }
    try {
      const result = await currentController.verifySubmitState({
        ...message.payload,
        tabId: frame.tabId,
        frameId: frame.frameId,
      });
      return successResponse(message, result);
    } catch (error) {
      return errorResponse(message.requestId, error?.code || "COMMAND_ERROR", error instanceof Error ? error.message : "submit state verification failed");
    }
  }

  async function handleSubmitFrameReadyMessage(message, sender) {
    if (senderIsExtensionPage(sender, chromeApi)
      || typeof chromeApi?.runtime?.id !== "string"
      || sender?.id !== chromeApi.runtime.id) {
      return errorResponse(message.requestId, "UNAUTHORIZED", "o registro deve vir do frame de botões autorizado");
    }
    const frame = authorizedPortalFrame(sender);
    if (frame === null || message.payload.url !== frame.senderUrl) {
      return errorResponse(message.requestId, "INVALID_ORIGIN", "SUBMIT_FRAME_READY must come from the allowed portal frame");
    }
    const currentBridge = await loadBridge();
    const currentController = controllerFor(currentBridge);
    if (currentController === null || typeof currentController.handleSubmitFrameReady !== "function") {
      return automationUnavailable(message);
    }
    try {
      const result = await currentController.handleSubmitFrameReady({
        tabId: frame.tabId,
        frameId: frame.frameId,
        buttonId: message.payload.button_id ?? null,
      });
      return successResponse(message, result);
    } catch (error) {
      return errorResponse(message.requestId, error?.code || "COMMAND_ERROR", error instanceof Error ? error.message : "submit frame registration failed");
    }
  }

  async function handleAutomationMessage(message, sender) {
    if (!senderIsExtensionPage(sender, chromeApi)) {
      return errorResponse(message.requestId, "UNAUTHORIZED", "somente páginas da extensão podem controlar a execução");
    }
    const currentBridge = await loadBridge();
    let currentController = controllerFor(currentBridge);
    if (currentBridge === null || currentController === null) return automationUnavailable(message);
    try {
      if (message.type === MESSAGE_TYPES.AUTO_START) {
        if (automationStartInFlight) {
          return errorResponse(message.requestId, "ACTIVE_RUN", "an automation run is already starting");
        }
        automationStartInFlight = true;
        try {
          const stored = await storedAutomationSession();
          const existingRunId = stored?.[STORAGE_KEYS.AUTOMATION_RUN_ID];
          if (typeof existingRunId === "string" && existingRunId) {
            let restored = null;
            try {
              restored = await rehydrateAutomationState(currentBridge, existingRunId);
            } catch (error) {
              if (!new Set(["NOT_FOUND", "RUN_NOT_FOUND"]).has(error?.code)) throw error;
            }
            if (restored?.controller && activeAutomationRunId === existingRunId) {
              return errorResponse(message.requestId, "ACTIVE_RUN", "an automation run is already active");
            }
          }
          activeAutomationSpec = clone(message.payload.spec);
          const started = await currentController.start(message.payload.spec, message.payload.eventId);
          activeAutomationRunId = typeof started?.run_id === "string" ? started.run_id : null;
          if (activeAutomationRunId !== null) {
            await persistAutomationSession(activeAutomationRunId, activeAutomationSpec);
          }
          scheduleAutomationWatchdog();
          return successResponse(message, started);
        } finally {
          automationStartInFlight = false;
        }
      }
      if (message.type === MESSAGE_TYPES.AUTO_ANALYZE) {
        let spec = clone(message.payload.spec);
        if (!Number.isSafeInteger(spec.tabId)) {
          if (typeof chromeApi.tabs?.query !== "function") {
            return errorResponse(message.requestId, "TAB_REQUIRED", "não foi possível identificar a aba autenticada da Área Restrita");
          }
          const activeTabs = await chromeApi.tabs.query({ active: true, currentWindow: true });
          const activePortal = (activeTabs ?? []).find((tab) => validatePortalUrl(tab?.url));
          if (!Number.isSafeInteger(activePortal?.id) || activePortal.id < 0) {
            return errorResponse(message.requestId, "TAB_REQUIRED", "abra a Área Restrita autenticada antes de analisar");
          }
          spec = { ...spec, tabId: activePortal.id };
        }
        const analyzed = await currentController.analyze({ spec, eventId: message.payload.eventId });
        return successResponse(message, analyzed);
      }
      if (message.type === MESSAGE_TYPES.AUTO_STATUS) {
        const restored = await rehydrateAutomationState(currentBridge, message.payload.runId);
        if (restored?.controller) currentController = restored.controller;
        else if (restored?.snapshot) return successResponse(message, restored.snapshot);
        return successResponse(message, await currentController.status({ refresh: true, runId: message.payload.runId }));
      }
      const restored = await rehydrateAutomationState(currentBridge, message.payload.runId);
      if (restored?.controller) currentController = restored.controller;
      const action = message.type.slice("AUTO_".length).toLowerCase();
      const control = currentController[action];
      if (typeof control !== "function") return automationUnavailable(message);
      const result = await control({
        runId: message.payload.runId,
        eventId: message.payload.eventId,
        expectedRevision: message.payload.expectedRevision,
      });
      if (action === "stop") {
        activeAutomationSpec = null;
        activeAutomationRunId = null;
        await clearAutomationSpec();
        clearAutomationWatchdog();
      }
      return successResponse(message, result);
    } catch (error) {
      if (error?.code === "ACTIVE_RUN") {
        return errorResponse(message.requestId, "ACTIVE_RUN", error instanceof Error ? error.message : "an automation run is already active");
      }
      if (message.type === MESSAGE_TYPES.AUTO_START) {
        activeAutomationSpec = null;
        activeAutomationRunId = null;
        clearAutomationWatchdog();
      }
      if (error?.code === "NOT_FOUND" || error?.code === "AUTOMATION_UNAVAILABLE") {
        return automationUnavailable(message);
      }
      return errorResponse(message.requestId, error?.code || "AUTOMATION_ERROR", error instanceof Error ? error.message : "automation bridge request failed");
    }
  }

  async function handlePortalEventMessage(message, sender) {
    if (senderIsExtensionPage(sender, chromeApi)) {
      return errorResponse(message.requestId, "UNAUTHORIZED", "PORTAL_EVENT must come from a portal content frame");
    }
    const tabId = tabIdFromSender(sender);
    const frameId = frameIdFromSender(sender);
    const senderUrl = typeof sender?.url === "string" ? sender.url : sender?.tab?.url;
    const tabUrl = sender?.tab?.url;
    if (
      tabId === null
      || frameId === null
      || typeof chromeApi?.runtime?.id !== "string"
      || sender?.id !== chromeApi.runtime.id
      || !validatePortalUrl(senderUrl)
      || (tabUrl !== undefined && !validatePortalUrl(tabUrl))
    ) {
      return errorResponse(message.requestId, "INVALID_ORIGIN", "PORTAL_EVENT must come from an allowed portal frame");
    }
    const currentBridge = await loadBridge();
    let currentController = controllerFor(currentBridge);
    const restored = await rehydrateAutomationState(currentBridge);
    if (restored?.controller) currentController = restored.controller;
    if (currentController === null || typeof currentController.handlePortalEvent !== "function") {
      return automationUnavailable(message);
    }
    const event = {
      ...clone(message.payload.event),
      tabId,
      frameId,
    };
    return successResponse(message, await currentController.handlePortalEvent(event));
  }

  async function setReviewed(message) {
    await loadState();
    if (!datasetIndex || !resolveIndexedRecord(datasetIndex, message.payload.processKey, message.payload.interestedNormalized)) {
      return errorResponse(message.requestId, "RECORD_NOT_FOUND", "cannot mark an unknown process/interested record");
    }
    const { processKey, interestedNormalized, reviewed: nextValue } = message.payload;
    const nextReviewed = clone(reviewed);
    if (!isRecord(nextReviewed.records)) nextReviewed.records = {};
    const reviewKey = `${processKey}\u0000${interestedNormalized}`;
    if (nextValue) nextReviewed.records[reviewKey] = true;
    else delete nextReviewed.records[reviewKey];
    await storage.set({ [STORAGE_KEYS.REVIEWED]: nextReviewed });
    reviewed = nextReviewed;
    return successResponse(message, { reviewed: nextValue });
  }

  async function handleMessage(message, sender = {}) {
    let validated;
    try {
      validated = validateMessage(message);
    } catch (error) {
      return errorResponse(message?.requestId, "INVALID_MESSAGE", error instanceof Error ? error.message : "message validation failed");
    }

    try {
      switch (validated.type) {
        case MESSAGE_TYPES.AUTO_START:
        case MESSAGE_TYPES.AUTO_ANALYZE:
        case MESSAGE_TYPES.AUTO_PAUSE:
        case MESSAGE_TYPES.AUTO_RESUME:
        case MESSAGE_TYPES.AUTO_STOP:
        case MESSAGE_TYPES.AUTO_STATUS:
          return await handleAutomationMessage(validated, sender);
        case MESSAGE_TYPES.AUTO_CONSUME_COMMAND:
          return await handleConsumeCommandMessage(validated, sender);
        case MESSAGE_TYPES.AUTO_VERIFY_SUBMIT_STATE:
          return await handleVerifySubmitStateMessage(validated, sender);
        case MESSAGE_TYPES.SUBMIT_FRAME_READY:
          return await handleSubmitFrameReadyMessage(validated, sender);
        case MESSAGE_TYPES.PORTAL_EVENT:
          return await handlePortalEventMessage(validated, sender);
        case MESSAGE_TYPES.FORM_READY: {
          const tabId = tabIdFromSender(sender);
          const frameId = frameIdFromSender(sender);
          if (tabId === null || frameId === null || !validatePortalUrl(sender.url) || sender.url !== validated.payload.url) {
            return errorResponse(validated.requestId, "INVALID_ORIGIN", "FORM_READY must come from the allowed portal URL");
          }
          await loadFrameRegistrations();
          clearedTabs.delete(tabId);
          const registration = {
            frameId,
            url: sender.url,
            registeredAt: now(),
          };
          const registrations = frameRegistrations.get(tabId) ?? new Map();
          registrations.set(frameId, registration);
          frameRegistrations.set(tabId, registrations);
          await persistFrameRegistrations();
          return successResponse(validated, { registered: true, frame: clone(registration) });
        }
        case MESSAGE_TYPES.IMPORT_DATASET:
          if (!senderIsExtension(sender, chromeApi)) return errorResponse(validated.requestId, "UNAUTHORIZED", "only the extension may import a dataset");
          return await importDataset(validated);
        case MESSAGE_TYPES.GET_MATCH:
          if (!senderIsExtension(sender, chromeApi)) return errorResponse(validated.requestId, "UNAUTHORIZED", "only the extension may request a match");
          return await getMatch(validated);
        case MESSAGE_TYPES.SET_REVIEWED:
          if (!senderIsExtension(sender, chromeApi)) return errorResponse(validated.requestId, "UNAUTHORIZED", "only the extension may set review state");
          return await setReviewed(validated);
        case MESSAGE_TYPES.GET_FORM_SNAPSHOT:
        case MESSAGE_TYPES.APPLY_FIELDS:
        case MESSAGE_TYPES.OVERRIDE_FIELD:
        case MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO:
          if (!senderIsExtension(sender, chromeApi)) return errorResponse(validated.requestId, "UNAUTHORIZED", "only the extension may route form actions");
          return await forwardToFrame(validated, sender);
        default:
          return errorResponse(validated.requestId, "UNSUPPORTED_MESSAGE", "message type is unsupported");
      }
    } catch (error) {
      const contextCodes = new Set([
        "CONTEXT_DATASET_MISMATCH",
        "CONTEXT_IDENTITY_MISMATCH",
        "CONTEXT_REVISION_MISMATCH",
        "RULES_VERSION_MISMATCH",
      ]);
      const code = contextCodes.has(error?.code)
        ? error.code
        : validated.type === MESSAGE_TYPES.IMPORT_DATASET ? "INVALID_DATASET" : "STORAGE_ERROR";
      return errorResponse(validated.requestId, code, error instanceof Error ? error.message : "service worker request failed");
    }
  }

  function register() {
    if (!listenerRegistered && chromeApi.runtime?.onMessage?.addListener) {
      chromeApi.runtime.onMessage.addListener((message, sender, sendResponse) => {
        void handleMessage(message, sender).then(sendResponse);
        return true;
      });
      listenerRegistered = true;
    }
    if (typeof chromeApi.sidePanel?.setPanelBehavior === "function") {
      void Promise.resolve(chromeApi.sidePanel.setPanelBehavior({
        openPanelOnActionClick: true,
      })).catch(() => undefined);
    }
    return api;
  }

  if (chromeApi.tabs?.onRemoved?.addListener) {
    chromeApi.tabs.onRemoved.addListener((tabId) => clearFrame(tabId));
  }

  if (chromeApi.alarms?.onAlarm?.addListener) {
    chromeApi.alarms.onAlarm.addListener((alarm) => {
      if (alarm?.name !== AUTOMATION_WATCHDOG_ALARM || activeAutomationSpec === null
        || activeAutomationRunId === null || activeController === null
        || typeof activeController.status !== "function") return;
      void activeController.status({ refresh: true, runId: activeAutomationRunId })
        .then((snapshot) => {
          if (snapshot?.status === "stopped" || snapshot?.status === "completed") {
            activeAutomationSpec = null;
            activeAutomationRunId = null;
            clearAutomationWatchdog();
          }
        })
        .catch(() => undefined);
    });
  }

  const api = {
    clearFrame,
    getFrameRegistration,
    getFrameRegistrations,
    handleMessage,
    register,
  };
  return api;
}

export function installServiceWorker(chromeApi, options = {}) {
  return createServiceWorker({ chromeApi, ...options }).register();
}

const runtimeChrome = typeof globalThis !== "undefined" ? globalThis.chrome : undefined;
if (runtimeChrome?.runtime?.onMessage && runtimeChrome?.storage?.local) {
  installServiceWorker(runtimeChrome);
}
