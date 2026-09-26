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
    targetIdentity: {
      processKey: payload.target_identity.processKey,
      interestedNormalized: payload.target_identity.interestedNormalized,
    },
  };
}

export function matchesFormIdentity(identity, expected) {
  return (
    hasFormIdentity(identity) &&
    hasFormIdentity(expected) &&
    identity.processKey === expected.processKey &&
    identity.interestedNormalized === expected.interestedNormalized
  );
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
