const EXACT_SUBMIT_LABEL = "Complementar Ato";
const COMMAND_TTL_MS = 15_000;
const OUTCOME_TIMEOUT_MS = 30_000;
const OUTCOME_POLL_MS = 1_000;

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function clone(value) {
  return value === undefined ? undefined : structuredClone(value);
}

function sameIdentity(left, right) {
  return isRecord(left)
    && isRecord(right)
    && left.processKey === right.processKey
    && left.interestedNormalized === right.interestedNormalized
    && left.portalActId === right.portalActId;
}

function error(code, message) {
  const result = new Error(message);
  result.code = code;
  return result;
}

function hasPortalOutcomeObserver() {
  const adapter = globalThis.TCEPortalOutcome;
  return typeof adapter?.subscribe === "function" || typeof adapter?.read === "function";
}

function sanitizeEvidence(value) {
  if (!isRecord(value)) return {};
  return Object.fromEntries(Object.entries(value)
    .filter(([key, child]) => ["signal", "read", "reason", "status", "source"].includes(key)
      && (typeof child === "string" || typeof child === "boolean")));
}

function identityMatchesObservation(observation, expected) {
  return sameIdentity(observation?.identity, expected?.identity)
    || sameIdentity(observation?.postRead?.identity, expected?.identity)
    || sameIdentity(observation?.persistedIdentity, expected?.identity);
}

function classifyPortalOutcome(observation, expected = {}) {
  if (!isRecord(observation)) return { status: "unconfirmed", evidence: {} };
  if (observation.rejected === true || observation.status === "rejected") {
    return { status: "failed", evidence: sanitizeEvidence(observation.evidence ?? observation) };
  }
  const accepted = observation.accepted === true || observation.status === "accepted";
  const persisted = observation.persisted === true || isRecord(observation.postRead);
  if (accepted && persisted && identityMatchesObservation(observation, expected)) {
    return { status: "confirmed", evidence: sanitizeEvidence(observation.evidence) };
  }
  return { status: "unconfirmed", evidence: sanitizeEvidence(observation.evidence ?? observation) };
}

function commandId(command) {
  return command?.command_id ?? command?.commandId ?? null;
}

function commandFrame(command) {
  return command?.frame_id ?? command?.frameId ?? null;
}

function commandFormFrame(command) {
  return command?.form_frame_id ?? command?.formFrameId ?? commandFrame(command);
}

function commandGeneration(command) {
  return command?.generation ?? command?.expected_generation ?? null;
}

function commandFieldsHash(command) {
  return command?.expected_fields_hash ?? command?.expectedFieldsHash ?? null;
}

function commandExpiresAt(command) {
  return command?.expires_at ?? command?.expiresAt ?? null;
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (!isRecord(value)) return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableValue(value[key])]));
}

async function hashFields(snapshot) {
  const fields = Object.fromEntries(Object.keys(snapshot?.fields ?? {}).sort().map((field) => [
    field,
    String(snapshot.fields[field]?.value ?? ""),
  ]));
  const bytes = new TextEncoder().encode(JSON.stringify(stableValue(fields)));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function readDefaultCurrentState(documentRef, command) {
  const formSnapshot = globalThis.TCEFormDetector?.getFormSnapshot?.(documentRef);
  const portalSnapshot = globalThis.TCEPortalNavigation?.snapshotPortalScreen?.(documentRef);
  const processKey = formSnapshot?.process?.key;
  const interestedNormalized = formSnapshot?.interested?.normalized;
  if (!formSnapshot || !portalSnapshot || typeof processKey !== "string" || !processKey
    || typeof interestedNormalized !== "string" || !interestedNormalized) {
    return { ok: false, visible: false, paused: true };
  }
  return {
    ok: true,
    visible: true,
    paused: false,
    frame_id: commandFormFrame(command),
    generation: portalSnapshot.generation,
    identity: { processKey, interestedNormalized, portalActId: command.identity?.portalActId ?? null },
    fields_hash: await hashFields(formSnapshot),
  };
}

function currentMatches(command, current) {
  return isRecord(current)
    && current.ok === true
    && current.visible === true
    && current.paused !== true
    && current.frame_id === commandFormFrame(command)
    && current.generation === commandGeneration(command)
    && current.fields_hash === commandFieldsHash(command)
    && sameIdentity(current.identity, command.identity);
}

function waitForPortalOutcome({
  subscribe = null,
  readOutcome = null,
  timeoutMs = OUTCOME_TIMEOUT_MS,
  setTimeoutFn = globalThis.setTimeout,
  clearTimeoutFn = globalThis.clearTimeout,
} = {}) {
  const duration = Number.isFinite(timeoutMs) && timeoutMs >= 0
    ? timeoutMs
    : OUTCOME_TIMEOUT_MS;
  return new Promise((resolve) => {
    let settled = false;
    let timerId = null;
    let unsubscribe = null;

    const cleanup = () => {
      if (timerId !== null && typeof clearTimeoutFn === "function") {
        clearTimeoutFn(timerId);
      }
      if (typeof unsubscribe === "function") unsubscribe();
      timerId = null;
      unsubscribe = null;
    };
    const finish = (observation) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(observation ?? { timeout: true });
    };
    const onDeadline = async () => {
      if (settled) return;
      let observation = null;
      if (typeof readOutcome === "function") {
        try {
          observation = await readOutcome();
        } catch {
          observation = null;
        }
      }
      finish(observation ?? { timeout: true });
    };

    timerId = typeof setTimeoutFn === "function"
      ? setTimeoutFn(onDeadline, duration)
      : null;
    if (typeof subscribe === "function") {
      try {
        const candidate = subscribe((observation) => finish(observation));
        if (typeof candidate === "function") {
          if (settled) candidate();
          else unsubscribe = candidate;
        }
      } catch {
        finish({ timeout: true });
      }
    }
  });
}


/*
 * Observador de resultado do portal.
 *
 * O envio real exige prova posterior: `submitVerifiedAct` recusa clicar sem um
 * observador registrado (`OUTCOME_OBSERVER_UNAVAILABLE`). Este objeto e o
 * adaptador que produz essa prova lendo o DOM depois do clique - ele apenas
 * LE o portal para decidir `accepted`/`persisted`; nunca clica, preenche ou
 * navega.
 *
 * A evidencia de persistencia vem do snapshot tipado de portal-navigation
 * (role `list` com a identidade esperada ja classificada como ATO_COMPLEMENTADO),
 * que e a mesma leitura usada em toda a automacao. Sem essa leitura o resultado
 * permanece `unconfirmed`, e o controlador pausa em vez de reenviar.
 */
function navigationReader() {
  const adapter = globalThis.TCEPortalNavigation;
  if (typeof adapter?.snapshotPortalScreen !== "function") return null;
  return adapter.snapshotPortalScreen;
}

function complementedIn(snapshot, expected) {
  if (!isRecord(snapshot) || !Array.isArray(snapshot.identities)) return null;
  const wanted = expected?.identity;
  if (!isRecord(wanted)) return null;
  return snapshot.identities.find((candidate) => sameIdentity(candidate, wanted)) ?? null;
}

function readPortalOutcome(documentRef = globalThis.document, expected = {}) {
  const readSnapshot = navigationReader();
  if (typeof readSnapshot !== "function") return { timeout: true };
  // O resultado pode ser renderizado no documento deste frame ou no topo
  // (o portal usa frames irmaos para formulario e quadro de acoes). Ambos sao
  // da mesma origem; leituras que falharem por acesso sao simplesmente
  // ignoradas, sem inventar evidencia.
  // A lista pode reaparecer no proprio documento, no documento de topo ou em
  // um frame irmao do mesmo portal. Todos sao da mesma origem; qualquer leitura
  // bloqueada por acesso e ignorada, sem inventar evidencia.
  const candidates = [documentRef];
  const pushDocument = (value) => {
    if (value && !candidates.includes(value)) candidates.push(value);
  };
  const topWindow = globalThis.top;
  if (topWindow && topWindow !== globalThis.self) {
    try {
      pushDocument(topWindow.document);
    } catch {
      /* acesso cross-document bloqueado */
    }
  }
  for (const candidate of [...candidates]) {
    let frames;
    try {
      frames = candidate?.querySelectorAll?.("iframe") ?? [];
    } catch {
      continue;
    }
    for (const frame of frames) {
      try {
        pushDocument(frame?.contentDocument);
      } catch {
        /* frame inacessivel */
      }
    }
  }
  let current = null;
  let observed = false;
  for (const candidate of candidates) {
    let snapshot;
    try {
      snapshot = readSnapshot(candidate);
    } catch {
      continue;
    }
    if (!isRecord(snapshot)) continue;
    observed = true;
    const match = complementedIn(snapshot, expected);
    if (isRecord(match)) {
      current = match;
      break;
    }
  }
  if (!observed) return { timeout: true };
  if (!isRecord(current)) {
    return {
      accepted: false,
      persisted: false,
      evidence: { signal: "identity_not_observed", read: true, source: "portal" },
    };
  }
  const identity = {
    processKey: current.processKey,
    interestedNormalized: current.interestedNormalized,
    portalActId: current.portalActId ?? null,
  };
  // `ATO_COMPLEMENTADO` e a unica classificacao que prova que o portal gravou o
  // ato. `PRECISA_COMPLEMENTAR` continua disponivel e NAO confirma nada.
  if (current.classification === "ATO_COMPLEMENTADO") {
    return {
      accepted: true,
      persisted: true,
      identity,
      postRead: { identity, classification: current.classification },
      evidence: { signal: "ato_complementado", read: true, source: "portal" },
    };
  }
  return {
    accepted: true,
    persisted: false,
    identity,
    evidence: { signal: "still_pending", read: true, source: "portal" },
  };
}

function createPortalOutcomeObserver({ documentRef = globalThis.document } = {}) {
  const subscribers = new Set();
  let timer = null;
  let mutationObserver = null;
  const stop = () => {
    if (mutationObserver && typeof mutationObserver.disconnect === "function") mutationObserver.disconnect();
    if (timer !== null && typeof globalThis.clearInterval === "function") globalThis.clearInterval(timer);
    mutationObserver = null;
    timer = null;
  };
  const deliver = (expected) => {
    const value = readPortalOutcome(documentRef, expected);
    // Somente persistencia observada e notificada; qualquer outra leitura
    // mantem o resultado `unconfirmed` e deixa o controlador pausar.
    if (value.persisted !== true) return;
    for (const subscriber of [...subscribers]) {
      try {
        subscriber(value);
      } catch {
        /* um assinante com defeito nao pode interromper os demais */
      }
    }
  };
  const watch = (expected, { intervalMs = OUTCOME_POLL_MS } = {}) => {
    const view = documentRef?.defaultView ?? globalThis;
    const MutationObserverConstructor = view?.MutationObserver ?? globalThis.MutationObserver;
    const target = documentRef?.body ?? documentRef?.documentElement ?? null;
    if (typeof MutationObserverConstructor === "function" && target) {
      try {
        mutationObserver = new MutationObserverConstructor(() => deliver(expected));
        mutationObserver.observe(target, { childList: true, subtree: true, characterData: true });
      } catch {
        mutationObserver = null;
      }
    }
    const setIntervalFn = view?.setInterval ?? globalThis.setInterval;
    if (intervalMs > 0 && typeof setIntervalFn === "function") {
      timer = setIntervalFn(() => deliver(expected), intervalMs);
    }
  };
  return Object.freeze({
    read(expected) {
      return readPortalOutcome(documentRef, expected);
    },
    subscribe(expected, notifySubscriber, options = {}) {
      if (typeof notifySubscriber !== "function") return () => {};
      subscribers.add(notifySubscriber);
      watch(expected, options);
      return () => {
        subscribers.delete(notifySubscriber);
        if (subscribers.size === 0) stop();
      };
    },
  });
}
function installPortalOutcomeObserver({ documentRef = globalThis.document, target = globalThis } = {}) {
  if (!documentRef || isRecord(target?.TCEPortalOutcome)) return false;
  const observer = createPortalOutcomeObserver({ documentRef });
  target.TCEPortalOutcome = Object.freeze({
    // A identidade esperada e obrigatoria: sem ela o observador nao consegue
    // distinguir o ato deste envio de qualquer outro listado no portal.
    read(documentReference, expected) {
      return observer.read(expected);
    },
    subscribe(documentReference, expected, notify) {
      return observer.subscribe(expected, notify);
    },
  });
  return true;
}

function defaultWaitForOutcome({ documentRef, command } = {}) {
  const adapter = globalThis.TCEPortalOutcome;
  // A identidade do comando e repassada como expectativa; sem ela a leitura
  // nao pode confirmar nada e o resultado permanece `unconfirmed`.
  const expected = { identity: command?.identity ?? null };
  return waitForPortalOutcome({
    subscribe: typeof adapter?.subscribe === "function"
      ? (notify) => adapter.subscribe(documentRef, expected, notify)
      : null,
    readOutcome: typeof adapter?.read === "function"
      ? () => adapter.read(documentRef, expected)
      : null,
  });
}

function textOf(button) {
  return typeof button?.textContent === "string" ? button.textContent.replace(/\s+/gu, " ").trim() : "";
}

function submitButtons(documentRef) {
  const candidates = typeof documentRef?.querySelectorAll === "function"
    ? [...documentRef.querySelectorAll("button, input[type=button], input[type=submit], a")]
    : [];
  return candidates.filter((candidate) => textOf(candidate) === EXACT_SUBMIT_LABEL
    && candidate.hidden !== true
    && candidate.disabled !== true
    && candidate.getAttribute?.("aria-disabled") !== "true");
}

function selectSubmitButton(documentRef, command) {
  const buttons = submitButtons(documentRef);
  if (buttons.length !== 1) throw error("SUBMIT_BLOCKED", "exatamente um botão habilitado Complementar Ato é necessário");
  const ids = buttons.map((candidate) => candidate.id).filter(Boolean);
  if (new Set(ids).size !== ids.length) throw error("SUBMIT_BLOCKED", "ID de botão de envio duplicado");
  if (command.button_id !== undefined && buttons[0].id !== command.button_id) {
    throw error("SUBMIT_BLOCKED", "o botão de envio não pertence ao comando");
  }
  return buttons[0];
}

function validateCommand(command, now) {
  if (!isRecord(command)) throw error("SUBMIT_BLOCKED", "comando de envio inválido");
  const id = commandId(command);
  const expiresAt = commandExpiresAt(command);
  if (typeof id !== "string" || !id || command.state !== "issued") throw error("SUBMIT_BLOCKED", "comando não está emitido");
  if (!Number.isFinite(expiresAt) || expiresAt <= now || expiresAt - now > COMMAND_TTL_MS) {
    throw error("SUBMIT_BLOCKED", "comando de envio expirado ou fora do prazo");
  }
  if (!Number.isSafeInteger(commandFrame(command)) || commandFrame(command) < 0
    || !Number.isSafeInteger(commandFormFrame(command)) || commandFormFrame(command) < 0
    || !Number.isSafeInteger(commandGeneration(command)) || commandGeneration(command) < 1
    || typeof commandFieldsHash(command) !== "string"
    || !/^[0-9a-f]{64}$/u.test(commandFieldsHash(command))) {
    throw error("SUBMIT_BLOCKED", "vínculo de frame, geração ou campos inválido");
  }
  return id;
}

async function submitVerifiedAct({
  documentRef,
  command,
  verifyCurrentState,
  consumeCommand,
  waitForOutcome = null,
  requireOutcomeObserver = false,
  click = null,
  now = () => Date.now(),
} = {}) {
  if (typeof verifyCurrentState !== "function" || typeof consumeCommand !== "function") {
    throw error("SUBMIT_BLOCKED", "verificação e consumo do comando são obrigatórios");
  }
  const currentTime = now();
  const id = validateCommand(command, currentTime);
  const button = selectSubmitButton(documentRef, command);
  if (requireOutcomeObserver && !hasPortalOutcomeObserver()) {
    throw error("OUTCOME_OBSERVER_UNAVAILABLE", "observador de resultado do portal não está disponível; nenhum clique foi executado");
  }
  const beforeConsume = await verifyCurrentState("before_consume");
  if (!currentMatches(command, beforeConsume)) throw error("SUBMIT_BLOCKED", "estado mudou antes do consumo");

  const consumed = await consumeCommand(id);
  if (consumed?.dispatch_allowed !== true) throw error("COMMAND_ALREADY_CONSUMED", "comando de envio já consumido");

  const beforeClick = await verifyCurrentState("before_click");
  if (!currentMatches(command, beforeClick)) {
    return { dispatched: false, command_id: id, status: "unconfirmed", evidence: { reason: "state_changed_after_consume" } };
  }
  const clickFn = typeof click === "function" ? click : () => button.click?.();
  await clickFn(button);
  const observation = typeof waitForOutcome === "function"
    ? await waitForOutcome({ command: clone(command), documentRef })
    : { timeout: true };
  const outcome = classifyPortalOutcome(observation, { identity: command.identity });
  return { dispatched: true, command_id: id, ...outcome };
}

function requestId() {
  return typeof globalThis.crypto?.randomUUID === "function"
    ? globalThis.crypto.randomUUID()
    : `portal-submit-${Date.now()}`;
}

function notifySubmitFrameReady(documentRef, chromeApi) {
  if (typeof chromeApi?.runtime?.sendMessage !== "function") return;
  const buttons = submitButtons(documentRef);
  const url = typeof documentRef?.location?.href === "string"
    ? documentRef.location.href
    : typeof globalThis.location?.href === "string" ? globalThis.location.href : "";
  if (buttons.length !== 1 || !url) return;
  const buttonId = typeof buttons[0].id === "string" && buttons[0].id
    ? { button_id: buttons[0].id }
    : {};
  void Promise.resolve(chromeApi.runtime.sendMessage({
    schemaVersion: 1,
    type: "SUBMIT_FRAME_READY",
    requestId: requestId(),
    payload: { url, ...buttonId },
  })).catch(() => undefined);
}

function submitErrorResponse(message, errorValue) {
  return {
    ok: false,
    requestId: message?.requestId,
    error: {
      code: errorValue?.code ?? "SUBMIT_BLOCKED",
      message: errorValue instanceof Error ? errorValue.message : String(errorValue ?? "submission blocked"),
    },
  };
}

function installPortalSubmit({
  documentRef = globalThis.document,
  chromeApi = globalThis.chrome,
  readCurrentState = readDefaultCurrentState,
  waitForOutcome = defaultWaitForOutcome,
  now = () => Date.now(),
} = {}) {
  const resolvedReadCurrentState = (currentDocument, currentCommand, phase) => {
    const formFrameId = commandFormFrame(currentCommand);
    const submitFrameId = commandFrame(currentCommand);
    if (formFrameId !== submitFrameId) {
      if (typeof chromeApi?.runtime?.sendMessage !== "function") {
        return Promise.resolve({ ok: false, visible: false, paused: true, reason: "worker de automação indisponível" });
      }
      return Promise.resolve(chromeApi.runtime.sendMessage({
        schemaVersion: 1,
        type: "AUTO_VERIFY_SUBMIT_STATE",
        requestId: requestId(),
        payload: {
          runId: currentCommand?.runId,
          expectedRevision: currentCommand?.expectedRevision,
          command: clone(currentCommand),
          phase,
        },
      })).then((response) => response?.ok === true
        ? response.payload
        : { ok: false, visible: false, paused: true, reason: response?.error?.message ?? "estado do formulário não verificado" });
    }
    return readCurrentState(currentDocument, currentCommand, phase);
  };

  const handleMessage = async (message) => {
    if (!isRecord(message) || message.type !== "AUTO_SUBMIT_COMMAND" || !isRecord(message.payload)) {
      throw error("SUBMIT_BLOCKED", "comando de envio não reconhecido");
    }
    const { runId, expectedRevision, command } = message.payload;
    if (typeof runId !== "string" || !Number.isSafeInteger(expectedRevision) || !isRecord(command)) {
      throw error("SUBMIT_BLOCKED", "payload de envio inválido");
    }
    if (typeof chromeApi?.runtime?.sendMessage !== "function") {
      throw error("SUBMIT_BLOCKED", "worker de automação indisponível");
    }
    const consumeCommand = async (commandId) => {
      const response = await chromeApi.runtime.sendMessage({
        schemaVersion: 1,
        type: "AUTO_CONSUME_COMMAND",
        requestId: requestId(),
        payload: {
          runId,
          commandId,
          expectedRevision,
          generation: commandGeneration(command),
          identity: command.identity,
        },
      });
      return response?.ok === true
        ? response.payload
        : { dispatch_allowed: false, error: response?.error?.code ?? "COMMAND_ERROR" };
    };
    const result = await submitVerifiedAct({
      documentRef,
      command,
      verifyCurrentState: (phase) => resolvedReadCurrentState(documentRef, {
        ...command,
        runId,
        expectedRevision,
      }, phase),
      consumeCommand,
      waitForOutcome: (context) => waitForOutcome({ ...context, command, documentRef }),
      requireOutcomeObserver: waitForOutcome === defaultWaitForOutcome,
      now,
    });
    return { ok: true, requestId: message.requestId, payload: result };
  };

  if (!chromeApi?.runtime?.onMessage?.addListener) return { handleMessage, registered: false };
  notifySubmitFrameReady(documentRef, chromeApi);
  chromeApi.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "AUTO_SUBMIT_COMMAND") return false;
    Promise.resolve(handleMessage(message))
      .then(sendResponse)
      .catch((errorValue) => sendResponse(submitErrorResponse(message, errorValue)));
    return true;
  });
  return { handleMessage, registered: true };
}

if (typeof module === "object" && module !== null && module.exports) {
  module.exports.COMMAND_TTL_MS = COMMAND_TTL_MS;
  module.exports.OUTCOME_TIMEOUT_MS = OUTCOME_TIMEOUT_MS;
  module.exports.classifyPortalOutcome = classifyPortalOutcome;
  module.exports.createPortalOutcomeObserver = createPortalOutcomeObserver;
  module.exports.installPortalOutcomeObserver = installPortalOutcomeObserver;
  module.exports.readPortalOutcome = readPortalOutcome;
  module.exports.installPortalSubmit = installPortalSubmit;
  module.exports.submitVerifiedAct = submitVerifiedAct;
  module.exports.waitForPortalOutcome = waitForPortalOutcome;
} else {
  globalThis.TCEPortalSubmit = Object.freeze({
    classifyPortalOutcome,
    createPortalOutcomeObserver,
    installPortalSubmit,
    submitVerifiedAct,
    waitForPortalOutcome,
  });
  installPortalOutcomeObserver();
  if (globalThis.document && globalThis.chrome?.runtime?.onMessage) installPortalSubmit();
}
