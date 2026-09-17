const FIELD_MAP = Object.freeze({
  modalidade: "txtModalidade",
  fundamento_legal: "txtFundamentoLegal",
  data_publicacao_doe: "txtDataDOE",
  cargo: "txtCargo",
  matricula: "txtMatricula",
  data_nascimento: "txtDataNascimento",
  genero: "txtGenero",
});

const FIELD_NAMES = Object.freeze(Object.keys(FIELD_MAP));
const SENTINEL_IDS = Object.freeze([
  "txtNumeroProcesso",
  "txtAnoProcesso",
  ...FIELD_NAMES.map((field) => FIELD_MAP[field]),
]);

const MATCH_CLASSES = Object.freeze({
  exact: ["complementar-ato-match-exact", "complementar-ato-match-green"],
  probable: ["complementar-ato-match-probable", "complementar-ato-match-yellow"],
  tie: ["complementar-ato-match-tie", "complementar-ato-match-yellow"],
});

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function clone(value) {
  return value === undefined ? undefined : structuredClone(value);
}

function normalizeInterestedName(value) {
  if (typeof value !== "string") return "";
  return value
    .normalize("NFKD")
    .replace(/\p{M}+/gu, "")
    .toLowerCase()
    .replace(/\s+/gu, " ")
    .trim();
}

function getById(documentRef, id) {
  return typeof documentRef?.getElementById === "function"
    ? documentRef.getElementById(id)
    : null;
}

function getFieldControl(documentRef, field) {
  return getById(documentRef, FIELD_MAP[field]);
}

function hasCompleteForm(documentRef = globalThis.document) {
  return SENTINEL_IDS.every((id) => Boolean(getById(documentRef, id)));
}

function computedStyleValue(windowRef, element, property) {
  const ownerWindow = element?.ownerDocument?.defaultView ?? windowRef;
  const computed = ownerWindow?.getComputedStyle?.(element);
  return String(computed?.[property] ?? element?.style?.[property] ?? "").trim().toLowerCase();
}

function inspectVisibleAncestors(root, windowRef, seenElements, checkRootRect = false) {
  let element = root;
  let isRoot = true;
  while (element) {
    if (!seenElements.has(element)) {
      seenElements.add(element);
      const isDocumentNode = element.nodeType === 9 || element.tagName === "DOCUMENT";
      if (!isDocumentNode) {
        if (element.hidden === true || element.getAttribute?.("aria-hidden") === "true") return false;
        if (["display", "visibility", "opacity"].some((property) => {
          const value = computedStyleValue(windowRef, element, property);
          return property === "display" ? value === "none"
            : property === "visibility" ? ["hidden", "collapse"].includes(value)
              : value === "0";
        })) return false;
        if (checkRootRect && isRoot) {
          const rect = element.getBoundingClientRect?.();
          if (rect && (rect.width <= 0 || rect.height <= 0)) return false;
          const clientRects = element.getClientRects?.();
          if (clientRects && clientRects.length === 0) return false;
        }
      }
    }
    element = element.parentElement;
    isRoot = false;
  }
  return true;
}

function isVisibleForm(documentRef = globalThis.document) {
  try {
    if (!documentRef?.defaultView) return false;

    const documentWindow = documentRef.defaultView;
    const seenWindows = new Set();
    const seenElements = new Set();
    let currentWindow = documentWindow;
    while (currentWindow) {
      if (seenWindows.has(currentWindow)) return false;
      seenWindows.add(currentWindow);

      const frameElement = currentWindow.frameElement ?? null;
      const parentWindow = currentWindow.parent;
      if (!frameElement && parentWindow && parentWindow !== currentWindow) return false;
      if (frameElement && !inspectVisibleAncestors(frameElement, parentWindow ?? currentWindow, seenElements, true)) {
        return false;
      }
      if (parentWindow === undefined || parentWindow === null || parentWindow === currentWindow) break;
      currentWindow = parentWindow;
    }

    const formElement = getById(documentRef, "complementarAtoForm")
      ?? getById(documentRef, SENTINEL_IDS[0])?.closest?.("form")
      ?? null;
    return inspectVisibleAncestors(formElement, documentWindow, seenElements);
  } catch {
    return false;
  }
}

function selectedRadio(documentRef) {
  if (typeof documentRef?.querySelectorAll !== "function") return null;
  const radios = [...documentRef.querySelectorAll('input[type="radio"]')];
  const selected = radios.filter((radio) => radio.checked === true);
  return selected.length === 1 ? selected[0] : null;
}

function textFromElement(element) {
  return typeof element?.textContent === "string"
    ? element.textContent.replace(/\s+/gu, " ").trim()
    : "";
}

function selectedInterestedName(documentRef) {
  const radio = selectedRadio(documentRef);
  if (!radio) return "";

  for (const attribute of ["data-interested-name", "data-interessado", "aria-label"]) {
    const value = radio.getAttribute?.(attribute);
    if (typeof value === "string" && value.trim()) return value.trim();
  }

  const labelText = textFromElement(radio.labels?.[0]);
  if (labelText) return labelText;

  const row = radio.closest?.("tr");
  const namedCell = row?.querySelector?.(".interested-name");
  if (textFromElement(namedCell)) return textFromElement(namedCell);

  // The legacy portal has no semantic marker on its name cell. Resolve the
  // column by its header, never by the entire row (which also contains CPF,
  // role and other values) or by a radio value (an internal person ID).
  const cellsOf = (element) => [...(element?.children ?? [])]
    .filter((cell) => ["TD", "TH"].includes(String(cell.tagName).toUpperCase()));
  const table = row?.closest?.("table");
  const cells = cellsOf(row);
  const headerRows = [...(table?.querySelectorAll?.("tr") ?? [])]
    .filter((candidate) => candidate.closest?.("table") === table);
  for (const header of headerRows) {
    if (header === row) break;
    const titles = cellsOf(header).map((cell) => normalizeInterestedName(textFromElement(cell)));
    const indexes = titles.flatMap((title, index) => title === "nome" ? [index] : []);
    if (indexes.length === 1 && titles.length === cells.length) {
      return textFromElement(cells[indexes[0]]);
    }
  }
  return "";
}

function readProcess(documentRef) {
  const number = String(getById(documentRef, "txtNumeroProcesso")?.value ?? "").trim();
  const year = String(getById(documentRef, "txtAnoProcesso")?.value ?? "").trim();
  return { number, year, key: number && year ? `${number}/${year}` : null };
}

function readInterested(documentRef) {
  const original = selectedInterestedName(documentRef);
  return original
    ? { original, normalized: normalizeInterestedName(original) }
    : null;
}

function readOptions(control) {
  const options = control?.options
    ? [...control.options]
    : [...(control?.querySelectorAll?.("option") ?? [])];
  return options.map((option) => ({
    value: String(option.value ?? ""),
    label: String(option.label || option.textContent || "").trim(),
  }));
}

function readFieldState(control) {
  return {
    value: String(control?.value ?? ""),
    disabled: control?.disabled === true,
    readOnly: control?.readOnly === true,
  };
}

function readIdentity(documentRef) {
  if (!hasCompleteForm(documentRef)) return null;
  const process = readProcess(documentRef);
  const interested = readInterested(documentRef);
  if (!process.key || !interested?.normalized) return null;
  return {
    processKey: process.key,
    interestedNormalized: interested.normalized,
  };
}

function identitiesEqual(left, right) {
  return Boolean(left && right)
    && left.processKey === right.processKey
    && left.interestedNormalized === right.interestedNormalized;
}

function identityFromOptions(options) {
  if (!isRecord(options)) return null;
  const candidate = options.expectedIdentity ?? options.identity;
  if (isRecord(candidate)) {
    if (typeof candidate.processKey === "string" && typeof candidate.interestedNormalized === "string") {
      return {
        processKey: candidate.processKey,
        interestedNormalized: candidate.interestedNormalized,
      };
    }
    if (isRecord(candidate.process) && isRecord(candidate.interested)) {
      return {
        processKey: candidate.process.key,
        interestedNormalized: candidate.interested.normalized,
      };
    }
  }
  if (isRecord(options.snapshot)) return identityFromOptions({ expectedIdentity: options.snapshot });
  return null;
}

function getFormSnapshot(documentRef = globalThis.document) {
  if (!isVisibleForm(documentRef) || !hasCompleteForm(documentRef)) return null;

  const fields = Object.fromEntries(FIELD_NAMES.map((field) => [
    field,
    readFieldState(getFieldControl(documentRef, field)),
  ]));
  const options = {};
  for (const field of FIELD_NAMES) {
    const control = getFieldControl(documentRef, field);
    if (String(control?.tagName ?? "").toUpperCase() === "SELECT") {
      options[field] = readOptions(control);
    }
  }

  return {
    process: readProcess(documentRef),
    interested: readInterested(documentRef),
    options,
    fields,
  };
}

function sameFormSnapshot(left, right) {
  if (!left || !right
    || left.process?.key !== right.process?.key
    || left.interested?.normalized !== right.interested?.normalized) return false;
  for (const field of FIELD_NAMES) {
    const before = left.fields?.[field];
    const after = right.fields?.[field];
    if (!before || !after
      || before.value !== after.value
      || before.disabled !== after.disabled
      || before.readOnly !== after.readOnly) return false;
    const beforeOptions = left.options?.[field] ?? [];
    const afterOptions = right.options?.[field] ?? [];
    if (JSON.stringify(beforeOptions) !== JSON.stringify(afterOptions)) return false;
  }
  return true;
}

function emptyResult() {
  return {
    changed: [],
    preserved: [],
    missing: [],
    disabled: [],
    errors: [],
  };
}

function validateFieldPayload(fields) {
  if (!isRecord(fields)) throw new TypeError("fields must be an object");
  for (const field of Object.keys(fields)) {
    if (!Object.hasOwn(FIELD_MAP, field)) throw new TypeError(`unsupported field ${field}`);
    if (fields[field] !== null && typeof fields[field] !== "string") {
      throw new TypeError(`field ${field} must be a string or null`);
    }
  }
}

function nativeValueSetter(control) {
  let prototype = control;
  while (prototype) {
    const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
    if (typeof descriptor?.set === "function") return descriptor.set.bind(control);
    prototype = Object.getPrototypeOf(prototype);
  }
  return null;
}

function dispatchBubblingEvents(documentRef, control) {
  const EventConstructor = documentRef?.defaultView?.Event ?? globalThis.Event;
  if (typeof EventConstructor !== "function" || typeof control?.dispatchEvent !== "function") {
    throw new Error("DOM event constructor is unavailable");
  }
  for (const type of ["input", "change", "blur"]) {
    control.dispatchEvent(new EventConstructor(type, { bubbles: true }));
  }
}

function optionValueExists(control, proposedValue) {
  const options = control?.options
    ? [...control.options]
    : [...(control?.querySelectorAll?.("option") ?? [])];
  return options.some((option) => String(option.value ?? "") === proposedValue);
}

function writeControl(documentRef, control, proposedValue) {
  const setter = nativeValueSetter(control);
  if (!setter) throw new Error("native value setter is unavailable");
  setter(proposedValue);
  dispatchBubblingEvents(documentRef, control);
}

function applyMatchClass(control, kind) {
  const classes = MATCH_CLASSES[kind];
  if (!classes || !control?.classList?.add) return;
  control.classList.add(...classes);
}

function validateBeforeWrite(documentRef, expectedIdentity) {
  if (!isVisibleForm(documentRef)) return "form is not visible";
  if (!hasCompleteForm(documentRef)) return "DOM sentinel set is incomplete";
  const currentIdentity = readIdentity(documentRef);
  if (!currentIdentity) return "process/year/interested identity is incomplete";
  if (expectedIdentity && !identitiesEqual(expectedIdentity, currentIdentity)) {
    return "process/year/interested identity changed";
  }
  return null;
}

const AUTOMATIC_LEGAL_DECISION_RULES = "legal-foundation-v3";

/**
 * Independent barrier for the legal foundation field: the content script only
 * writes it when the caller proves an authorized automatic v3 decision.
 */
function isAuthorizedLegalDecision(decision) {
  return decision !== null
    && typeof decision === "object"
    && decision.status === "selected"
    && decision.decision_state === "AUTO_SELECTED"
    && decision.rules_version === AUTOMATIC_LEGAL_DECISION_RULES
    && decision.method !== "none"
    && decision.hard_conflict !== true
    && typeof decision.confidence === "number"
    && Number.isFinite(decision.confidence)
    && decision.confidence >= 0.90
    && typeof decision.margin === "number"
    && Number.isFinite(decision.margin)
    && decision.margin >= 0.12;
}

function applyFieldsInternal(documentRef, fields, options = {}, allowOverride = false) {
  validateFieldPayload(fields);
  const result = emptyResult();
  const expectedIdentity = identityFromOptions(options) ?? readIdentity(documentRef);
  if (!hasCompleteForm(documentRef)) {
    result.errors.push("DOM sentinel set is incomplete");
    return result;
  }
  if (!isVisibleForm(documentRef)) {
    result.errors.push("form is not visible");
    return result;
  }
  if (!expectedIdentity) {
    result.errors.push("process/year/interested identity is incomplete");
    return result;
  }

  for (const field of Object.keys(fields)) {
    const beforeWriteError = validateBeforeWrite(documentRef, expectedIdentity);
    if (beforeWriteError) {
      result.errors.push(beforeWriteError);
      break;
    }
    const proposedValue = fields[field];
    if (field === "fundamento_legal") {
      const decision = options.legalDecision;
      // REVIEW, TRUE_TIE, CONTEXT_BLOCKED and PENDING proposals are never
      // written, and a valid decision only writes its own authorized option.
      if (!isAuthorizedLegalDecision(decision) || decision.option_value !== proposedValue) {
        result.preserved.push(field);
        continue;
      }
    }
    if (proposedValue === null || proposedValue === "") {
      result.missing.push(field);
      continue;
    }

    const control = getFieldControl(documentRef, field);
    if (!control) {
      result.missing.push(field);
      continue;
    }
    if (control.disabled === true || control.readOnly === true) {
      result.disabled.push(field);
      continue;
    }

    const currentValue = String(control.value ?? "");
    if (!allowOverride && currentValue !== "" && currentValue !== proposedValue) {
      result.preserved.push(field);
      continue;
    }
    if (currentValue === proposedValue) {
      result.preserved.push(field);
      applyMatchClass(control, options.matchKinds?.[field]);
      continue;
    }
    if (String(control.tagName ?? "").toUpperCase() === "SELECT" && !optionValueExists(control, proposedValue)) {
      result.errors.push(`${field}: proposed option value is not present in the current select`);
      continue;
    }

    try {
      writeControl(documentRef, control, proposedValue);
      applyMatchClass(control, options.matchKinds?.[field]);
      result.changed.push(field);
    } catch (error) {
      result.errors.push(`${field}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  return result;
}

function applyFields(documentRef = globalThis.document, fields, options = {}) {
  return applyFieldsInternal(documentRef, fields, options, false);
}

function overrideField(documentRef = globalThis.document, field, proposedValue, options = {}) {
  if (!Object.hasOwn(FIELD_MAP, field)) throw new TypeError(`unsupported field ${field}`);
  if (typeof proposedValue !== "string") throw new TypeError("proposed value must be a string");
  return applyFieldsInternal(documentRef, { [field]: proposedValue }, options, true);
}

function errorResponse(code, message) {
  return { ok: false, error: { code, message } };
}

function emitComplementarAtoSignal(documentRef, identity) {
  if (typeof documentRef?.dispatchEvent !== "function") {
    return errorResponse("COMPLEMENTAR_ATO_SIGNAL_UNAVAILABLE", "portal document cannot receive a signal");
  }
  const EventConstructor = documentRef?.defaultView?.CustomEvent ?? globalThis.CustomEvent;
  let event;
  if (typeof EventConstructor === "function") {
    event = new EventConstructor("tce:complementar-ato", { bubbles: true, detail: identity });
  } else {
    event = { type: "tce:complementar-ato", bubbles: true, detail: identity };
  }
  if (!event.detail) event.detail = identity;
  documentRef.dispatchEvent(event);
  return { ok: true, payload: { signaled: true } };
}

function createMessageHandler(documentRef = globalThis.document) {
  let lastIdentity = null;
  let activeSnapshotPlan = null;
  const usedSnapshotRequestIds = new Set();

  return async function handleMessage(message) {
    if (!isRecord(message) || typeof message.type !== "string" || !isRecord(message.payload)) {
      return errorResponse("INVALID_MESSAGE", "message type and payload are required");
    }
    try {
      if (message.type === "GET_FORM_SNAPSHOT") {
        activeSnapshotPlan = null;
        lastIdentity = null;
        if (typeof message.requestId === "string" && usedSnapshotRequestIds.has(message.requestId)) {
          return errorResponse("SNAPSHOT_PLAN_INVALID", "snapshot request id was already used");
        }
        const snapshot = getFormSnapshot(documentRef);
        if (!isVisibleForm(documentRef)) return errorResponse("FORM_NOT_VISIBLE", "Complementar Ato form is not visible");
        if (!snapshot) return errorResponse("FORM_NOT_FOUND", "Complementar Ato form sentinels are incomplete");
        lastIdentity = readIdentity(documentRef);
        if (typeof message.requestId === "string" && message.requestId) {
          usedSnapshotRequestIds.add(message.requestId);
          activeSnapshotPlan = {
            requestId: message.requestId,
            identity: clone(lastIdentity),
            snapshot: clone(snapshot),
          };
        }
        return { ok: true, payload: snapshot };
      }
      if (message.type === "APPLY_FIELDS") {
        if (!activeSnapshotPlan || activeSnapshotPlan.requestId !== message.requestId) {
          const result = emptyResult();
          result.errors.push("a valid form snapshot plan is required before APPLY_FIELDS");
          return { ok: false, payload: result, error: { code: "APPLY_BLOCKED", message: result.errors[0] } };
        }
        if (!sameFormSnapshot(activeSnapshotPlan.snapshot, getFormSnapshot(documentRef))) {
          activeSnapshotPlan = null;
          const result = emptyResult();
          result.errors.push("form snapshot changed since GET_FORM_SNAPSHOT");
          return { ok: false, payload: result, error: { code: "APPLY_BLOCKED", message: result.errors[0] } };
        }
        const result = applyFields(documentRef, message.payload.fields, {
          expectedIdentity: activeSnapshotPlan.identity,
          matchKinds: message.payload.matchKinds,
          legalDecision: message.payload.legalDecision,
        });
        activeSnapshotPlan = null;
        return result.errors.length > 0
          ? { ok: false, payload: result, error: { code: "APPLY_BLOCKED", message: result.errors.join("; ") } }
          : { ok: true, payload: result };
      }
      if (message.type === "OVERRIDE_FIELD") {
        const result = overrideField(
          documentRef,
          message.payload.field,
          message.payload.proposedValue,
          { expectedIdentity: lastIdentity, legalDecision: message.payload.legalDecision },
        );
        return result.errors.length > 0
          ? { ok: false, payload: result, error: { code: "OVERRIDE_BLOCKED", message: result.errors.join("; ") } }
          : { ok: true, payload: result };
      }
      if (message.type === "REQUEST_COMPLEMENTAR_ATO") {
        const currentIdentity = readIdentity(documentRef);
        const requestedIdentity = {
          processKey: message.payload.processKey,
          interestedNormalized: message.payload.interestedNormalized,
        };
        if (!currentIdentity || !identitiesEqual(currentIdentity, requestedIdentity)) {
          return errorResponse("COMPLEMENTAR_ATO_BLOCKED", "processo/interessado mudou; atualize a prévia");
        }
        return emitComplementarAtoSignal(documentRef, requestedIdentity);
      }
      return errorResponse("UNSUPPORTED_MESSAGE", `unsupported message type ${message.type}`);
    } catch (error) {
      return errorResponse("INVALID_PAYLOAD", error instanceof Error ? error.message : String(error));
    }
  };
}

function createRequestId() {
  if (typeof globalThis.crypto?.randomUUID === "function") return globalThis.crypto.randomUUID();
  return `form-ready-${Date.now()}`;
}

function installContentScript({
  documentRef = globalThis.document,
  chromeApi = globalThis.chrome,
  locationRef = globalThis.location,
} = {}) {
  const handleMessage = createMessageHandler(documentRef);
  if (!chromeApi?.runtime?.onMessage?.addListener) return { handleMessage, registered: false };

  chromeApi.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!["GET_FORM_SNAPSHOT", "APPLY_FIELDS", "OVERRIDE_FIELD", "REQUEST_COMPLEMENTAR_ATO"].includes(message?.type)) return false;
    if (message?.type === "GET_FORM_SNAPSHOT" && !isVisibleForm(documentRef)) return false;
    Promise.resolve(handleMessage(message)).then(sendResponse);
    return true;
  });

  const sendMessage = chromeApi.runtime.sendMessage;
  if (typeof sendMessage !== "function") return { handleMessage, registered: true };

  let readySent = false;
  let observer = null;
  const disconnectObserver = () => {
    observer?.disconnect?.();
    observer = null;
  };
  const documentIsUsable = () => {
    try {
      return Boolean(
        documentRef
          && typeof documentRef.getElementById === "function"
          && documentRef.defaultView,
      );
    } catch {
      return false;
    }
  };
  const emitReady = () => {
    if (readySent) return;
    let url = "";
    try {
      url = typeof locationRef?.href === "string" ? locationRef.href : "";
    } catch {
      // A non-browser location object must not prevent installation cleanup.
    }
    const readyMessage = {
      schemaVersion: 1,
      type: "FORM_READY",
      requestId: createRequestId(),
      payload: { url },
    };
    readySent = true;
    disconnectObserver();
    sendMessage.call(chromeApi.runtime, readyMessage);
  };
  const emitReadyIfAvailable = () => {
    if (readySent) return;
    if (!documentIsUsable()) {
      disconnectObserver();
      return;
    }
    try {
      if (!hasCompleteForm(documentRef) || !isVisibleForm(documentRef)) return;
    } catch {
      disconnectObserver();
      return;
    }
    emitReady();
  };

  let formIsComplete = false;
  try {
    formIsComplete = hasCompleteForm(documentRef);
  } catch {
    return { handleMessage, registered: true };
  }
  if (formIsComplete) {
    emitReady();
  } else if (documentIsUsable()) {
    try {
      const Observer = documentRef.defaultView?.MutationObserver ?? globalThis.MutationObserver;
      const target = documentRef.body ?? documentRef.documentElement ?? documentRef;
      if (typeof Observer === "function" && target && typeof target === "object") {
        observer = new Observer(emitReadyIfAvailable);
        observer.observe(target, { childList: true, subtree: true, attributes: true });
      }
    } catch {
      disconnectObserver();
    }
  }
  return { handleMessage, registered: true };
}

if (typeof module === "object" && module !== null && module.exports) {
  module.exports.FIELD_MAP = FIELD_MAP;
  module.exports.SENTINEL_IDS = SENTINEL_IDS;
  module.exports.hasCompleteForm = hasCompleteForm;
  module.exports.isVisibleForm = isVisibleForm;
  module.exports.getFormSnapshot = getFormSnapshot;
  module.exports.applyFields = applyFields;
  module.exports.overrideField = overrideField;
  module.exports.createMessageHandler = createMessageHandler;
  module.exports.installContentScript = installContentScript;
} else {
  globalThis.TCEFormDetector = Object.freeze({
    getFormSnapshot,
    applyFields,
    overrideField,
  });
  const runtimeDocument = typeof globalThis !== "undefined" ? globalThis.document : undefined;
  const runtimeChrome = typeof globalThis !== "undefined" ? globalThis.chrome : undefined;
  if (runtimeDocument && runtimeChrome?.runtime?.onMessage) {
    installContentScript({ documentRef: runtimeDocument, chromeApi: runtimeChrome });
  }
}
