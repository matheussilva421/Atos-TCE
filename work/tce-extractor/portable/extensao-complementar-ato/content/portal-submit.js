const EXACT_SUBMIT_LABEL = "Complementar Ato";
const COMMAND_TTL_MS = 15_000;

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
    frame_id: commandFrame(command),
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
    && current.frame_id === commandFrame(command)
    && current.generation === commandGeneration(command)
    && current.fields_hash === commandFieldsHash(command)
    && sameIdentity(current.identity, command.identity);
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
  click = null,
  now = () => Date.now(),
} = {}) {
  if (typeof verifyCurrentState !== "function" || typeof consumeCommand !== "function") {
    throw error("SUBMIT_BLOCKED", "verificação e consumo do comando são obrigatórios");
  }
  const currentTime = now();
  const id = validateCommand(command, currentTime);
  const button = selectSubmitButton(documentRef, command);
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
  waitForOutcome = async () => ({ timeout: true }),
  now = () => Date.now(),
} = {}) {
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
      verifyCurrentState: (phase) => readCurrentState(documentRef, command, phase),
      consumeCommand,
      waitForOutcome: (context) => waitForOutcome({ ...context, command, documentRef }),
      now,
    });
    return { ok: true, requestId: message.requestId, payload: result };
  };

  if (!chromeApi?.runtime?.onMessage?.addListener) return { handleMessage, registered: false };
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
  module.exports.classifyPortalOutcome = classifyPortalOutcome;
  module.exports.installPortalSubmit = installPortalSubmit;
  module.exports.submitVerifiedAct = submitVerifiedAct;
} else {
  globalThis.TCEPortalSubmit = Object.freeze({ classifyPortalOutcome, installPortalSubmit, submitVerifiedAct });
  if (globalThis.document && globalThis.chrome?.runtime?.onMessage) installPortalSubmit();
}
