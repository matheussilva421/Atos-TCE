import { rankPortalOptions } from "../lib/matcher.js";
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
import { validateLegalContext } from "../lib/automation-schema.js";
import { createAutomationController } from "./automation-controller.js";

export const FRAME_REGISTRATIONS_STORAGE_KEY = "frame-registrations:v1";

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
  const contextCache = new Map();
  const controller = automationController ?? (
    bridge
      && typeof bridge.createAutomationRun === "function"
      && typeof bridge.controlAutomationRun === "function"
      && typeof chromeApi?.tabs?.sendMessage === "function"
      ? createAutomationController({
        chromeApi,
        bridge,
        ranker,
        clock: () => now(),
      })
      : null
  );

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
    contextCache.clear();
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
      context,
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
    const identityKey = `${processKey}\u0000${interestedNormalized}`;
    const invalidateIdentity = () => {
      for (const key of contextCache.keys()) {
        if (key.startsWith(`${identityKey}\u0000`)) contextCache.delete(key);
      }
    };
    let cachedContext = null;
    if (context !== undefined) {
      if (context === null) {
        invalidateIdentity();
      } else {
        const verifiedContext = validateLegalContext(context, {
          processKey,
          interestedNormalized,
          datasetSha256: currentDatasetSha256,
        });
        const verifiedRevision = verifiedContext.context_revision;
        const verifiedRulesVersion = verifiedContext.rules_version;
        if (contextRevision !== undefined && verifiedRevision !== contextRevision) {
          throw contextError("CONTEXT_REVISION_MISMATCH", "context revision differs from the backend context");
        }
        if (rulesVersion !== undefined && verifiedRulesVersion !== rulesVersion) {
          throw contextError("RULES_VERSION_MISMATCH", "rules version differs from the backend context");
        }
        if (verifiedRevision === undefined || verifiedRulesVersion === undefined) {
          if (contextRevision !== undefined) {
            throw contextError("CONTEXT_REVISION_MISMATCH", "context has no authoritative revision");
          }
          if (rulesVersion !== undefined) {
            throw contextError("RULES_VERSION_MISMATCH", "context has no authoritative rules version");
          }
          cachedContext = verifiedContext;
        } else {
          invalidateIdentity();
          const contextKey = `${identityKey}\u0000${verifiedContext.dataset_sha256}\u0000${verifiedRulesVersion}\u0000${verifiedRevision}`;
          contextCache.set(contextKey, verifiedContext);
          cachedContext = verifiedContext;
        }
      }
    } else if (
      datasetSha256 === currentDatasetSha256
      && typeof rulesVersion === "string"
      && Number.isSafeInteger(contextRevision)
      && contextRevision >= 0
    ) {
      const contextKey = `${identityKey}\u0000${currentDatasetSha256}\u0000${rulesVersion}\u0000${contextRevision}`;
      cachedContext = contextCache.get(contextKey) ?? null;
    }

    const matches = {};
    for (const [field, fieldOptions] of Object.entries(options)) {
      const documentaryField = record.fields[field];
      const documentaryValue = documentaryField?.source_value ?? documentaryField?.form_value ?? "";
      matches[field] = ranker({
        field,
        documentaryValue,
        hints: {},
        options: fieldOptions,
        context: field === "fundamento_legal" ? cachedContext : null,
      });
    }
    return successResponse(message, {
      record: clone(record),
      matches,
      reviewed: reviewedValue(processKey, record.interested.normalized),
    });
  }

  function automationUnavailable(message) {
    return errorResponse(message.requestId, "AUTOMATION_UNAVAILABLE", "o serviço local não expõe a API de automação; o modo manual permanece disponível");
  }

  async function handleAutomationMessage(message, sender) {
    if (!senderIsExtensionPage(sender, chromeApi)) {
      return errorResponse(message.requestId, "UNAUTHORIZED", "somente páginas da extensão podem controlar a execução");
    }
    if (bridge === null || controller === null) return automationUnavailable(message);
    try {
      if (message.type === MESSAGE_TYPES.AUTO_START) {
        return successResponse(message, await controller.start(message.payload.spec, message.payload.eventId));
      }
      if (message.type === MESSAGE_TYPES.AUTO_STATUS) {
        return successResponse(message, await controller.status({ refresh: true, runId: message.payload.runId }));
      }
      const action = message.type.slice("AUTO_".length).toLowerCase();
      const control = controller[action];
      if (typeof control !== "function") return automationUnavailable(message);
      return successResponse(message, await control({
        runId: message.payload.runId,
        eventId: message.payload.eventId,
        expectedRevision: message.payload.expectedRevision,
      }));
    } catch (error) {
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
    if (controller === null || typeof controller.handlePortalEvent !== "function") {
      return automationUnavailable(message);
    }
    const event = {
      ...clone(message.payload.event),
      tabId,
      frameId,
    };
    return successResponse(message, await controller.handlePortalEvent(event));
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
        case MESSAGE_TYPES.AUTO_PAUSE:
        case MESSAGE_TYPES.AUTO_RESUME:
        case MESSAGE_TYPES.AUTO_STOP:
        case MESSAGE_TYPES.AUTO_STATUS:
          return await handleAutomationMessage(validated, sender);
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
