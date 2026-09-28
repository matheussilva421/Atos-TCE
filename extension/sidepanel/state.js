export function describeMesaStatus(status) {
  if (status?.ok && status?.paired) {
    return {
      paired: true,
      tone: "ok",
      label: "Mesa conectada",
      diagnostic: "Pronto: a Mesa comanda o trabalho e você confirma o ato no portal.",
    };
  }

  if (status?.status === 0 || status?.error === "fetch_failed") {
    return {
      paired: false,
      tone: "error",
      label: "Mesa não encontrada",
      diagnostic: "Inicie a Mesa local; a conexão será tentada novamente automaticamente.",
    };
  }

  return {
    paired: false,
    tone: "warn",
    label: "Conectando à Mesa…",
    diagnostic: "A conexão automática está sendo estabelecida.",
  };
}

export function hasFormIdentity(identity) {
  return (
    typeof identity?.processKey === "string" &&
    identity.processKey.trim().length > 0 &&
    typeof identity?.interestedNormalized === "string" &&
    identity.interestedNormalized.trim().length > 0
  );
}

export function retainLastConfirmedIdentity(previous, response) {
  const identity = response?.ok === true ? response.form?.identity : null;
  if (!hasFormIdentity(identity)) return previous;
  return {
    processKey: identity.processKey,
    interestedNormalized: identity.interestedNormalized,
    ...(typeof identity.portalActId === "string" && identity.portalActId.trim()
      ? { portalActId: identity.portalActId }
      : {}),
  };
}

export function describeNextActOutcome(outcome) {
  if (outcome?.ok !== true) {
    return { state: "error", code: outcome?.error ?? "request_failed" };
  }

  const payload = outcome.payload;
  if (payload?.end_of_queue === true) {
    return { state: "end_of_queue", message: "Fim da fila" };
  }

  if (
    !Number.isSafeInteger(payload?.command_id) ||
    payload.command_id < 1 ||
    !hasFormIdentity(payload.target_identity)
  ) {
    return { state: "error", code: "invalid_next_act_response" };
  }

  return {
    state: "opening",
    commandId: payload.command_id,
    targetIdentity: {
      processKey: payload.target_identity.processKey,
      interestedNormalized: payload.target_identity.interestedNormalized,
      ...(typeof payload.target_identity.portalActId === "string" && payload.target_identity.portalActId.trim()
        ? { portalActId: payload.target_identity.portalActId }
        : {}),
    },
  };
}

export function describeNextActCommandStatus(outcome, targetIdentity) {
  if (outcome?.ok !== true || !outcome?.command) {
    const status = Number(outcome?.status);
    if (status >= 400 && status < 500) {
      const code = String(outcome?.error ?? "COMMAND_STATUS_UNAVAILABLE");
      return { state: "error", code, message: code };
    }
    return { state: "pending" };
  }
  const command = outcome.command;
  const state = String(command.state ?? "").trim().toUpperCase();
  if (["QUEUED", "CLAIMED"].includes(state)) return { state: "pending" };

  const result = command.result && typeof command.result === "object" ? command.result : {};
  if (state === "FAILED" || result.ok === false) {
    const code = String(result.code ?? command.error ?? result.error ?? "NAVIGATION_FAILED");
    return { state: "error", code, message: String(result.error ?? command.error ?? code) };
  }
  if (state !== "SUCCEEDED" || result.ok !== true) {
    return { state: "error", code: "COMMAND_RESULT_UNCONFIRMED", message: "COMMAND_RESULT_UNCONFIRMED" };
  }
  if (result.action !== "next_act_ready" || result.screen !== "form") {
    return { state: "error", code: "COMMAND_RESULT_UNCONFIRMED", message: "COMMAND_RESULT_UNCONFIRMED" };
  }
  if (!matchesFormIdentity(result.identity, targetIdentity)) {
    return { state: "error", code: "TARGET_IDENTITY_MISMATCH", message: "TARGET_IDENTITY_MISMATCH" };
  }
  return { state: "ready", identity: result.identity };
}

export async function pollForNextActCommand({
  readCommandStatus,
  commandId,
  targetIdentity,
  maxAttempts = 600,
  intervalMs = 500,
  sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
}) {
  const attempts = Number.isSafeInteger(maxAttempts) ? Math.max(0, maxAttempts) : 600;
  if (typeof readCommandStatus !== "function" || !Number.isSafeInteger(commandId) ||
      commandId < 1 || !hasFormIdentity(targetIdentity)) {
    return { state: "error", code: "INVALID_COMMAND_STATUS_REQUEST", message: "INVALID_COMMAND_STATUS_REQUEST" };
  }
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    let outcome;
    try {
      outcome = describeNextActCommandStatus(await readCommandStatus(commandId), targetIdentity);
    } catch {
      outcome = { state: "pending" };
    }
    if (outcome.state !== "pending") return outcome;
    if (attempt + 1 < attempts) await sleep(intervalMs);
  }
  return { state: "timeout", code: "COMMAND_STATUS_TIMEOUT", message: "COMMAND_STATUS_TIMEOUT" };
}

export function matchesFormIdentity(identity, expected) {
  if (!hasFormIdentity(identity) || !hasFormIdentity(expected) || identity.processKey !== expected.processKey) {
    return false;
  }
  const actualActId = String(identity.portalActId ?? "").trim();
  const expectedActId = String(expected.portalActId ?? "").trim();
  return actualActId && expectedActId
    ? actualActId === expectedActId
    : identity.interestedNormalized === expected.interestedNormalized;
}

export async function pollForTargetForm({
  readCurrentForm,
  targetIdentity,
  maxAttempts = 40,
  intervalMs = 500,
  sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
}) {
  if (typeof readCurrentForm !== "function" || !hasFormIdentity(targetIdentity)) return null;
  const attempts = Number.isSafeInteger(maxAttempts) ? Math.max(0, maxAttempts) : 40;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    await sleep(intervalMs);
    try {
      const response = await readCurrentForm();
      if (response?.ok === true && matchesFormIdentity(response.form?.identity, targetIdentity)) {
        return response.form;
      }
    } catch {
      // A transiently unavailable portal frame is retried within the bounded poll.
    }
  }

  return null;
}
