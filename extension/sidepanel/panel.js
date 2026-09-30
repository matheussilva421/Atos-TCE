/**
 * Operational side panel: connection state, portal state and a shortcut to
 * the Mesa. It is intentionally not a dashboard — the Mesa
 * owns the workflow.
 */

import { MESA_ORIGIN, MESSAGE_TYPES, PORTAL_ORIGIN } from "../lib/protocol.js";
import {
  describeMesaStatus,
  describeManualFillCapability,
  describeNextActOutcome,
  describeNextProcessCapability,
  pollForNextActCommand,
  hasFormIdentity,
  retainLastConfirmedIdentity,
} from "./state.js";

let lastConfirmedFormIdentity = null;
let currentFormAvailable = false;
let nextActInProgress = false;
let acceptedNextTarget = null;
let nextActFeedback = null;
let reliabilityCapabilities = null;

function setState(elementId, dotId, text, tone) {
  const label = document.getElementById(elementId);
  const dot = document.getElementById(dotId);
  if (label) label.textContent = text;
  if (dot) dot.className = `dot ${tone ?? ""}`.trim();
}

async function refreshMesa() {
  const status = await globalThis.chrome.runtime.sendMessage({ type: MESSAGE_TYPES.MESA_STATUS });
  const state = describeMesaStatus(status);
  setState("mesa-status", "mesa-dot", state.label, state.tone);
  return state;
}

/**
 * The sidepanel never decides a capability's state: it reads the read-only
 * ledger summary from the Mesa and reflects it on the operator controls.
 */
async function refreshReliability() {
  try {
    const outcome = await globalThis.chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.RELIABILITY_STATUS,
    });
    reliabilityCapabilities = outcome?.ok === true ? outcome.capabilities ?? {} : null;
  } catch {
    reliabilityCapabilities = null;
  }
  updateCapabilityStatus();
  return reliabilityCapabilities;
}

function updateCapabilityStatus() {
  const element = document.getElementById("capability-status");
  const manualFill = describeManualFillCapability(reliabilityCapabilities);
  if (element) element.textContent = `Preencher formulário atual: ${manualFill.label}`;
  updateActionButtons();
}

async function refreshPortal() {
  const tabs = await globalThis.chrome.tabs.query({ url: [`${PORTAL_ORIGIN}/*`] });
  if (tabs?.length > 0) {
    setState("portal-status", "portal-dot", "Área Restrita detectada", "ok");
    return true;
  }
  setState("portal-status", "portal-dot", "Área Restrita não está aberta", "warn");
  return false;
}

async function refresh() {
  const diagnostic = document.getElementById("diagnostic");
  try {
    const mesa = await refreshMesa();
    await refreshReliability();
    await refreshPortal();
    await refreshCurrentForm();
    if (!nextActFeedback) {
      diagnostic.className = "";
      diagnostic.textContent = mesa.diagnostic ?? "A conexão automática está sendo estabelecida.";
    }
  } catch (error) {
    diagnostic.className = "error";
    diagnostic.textContent = `Falha ao consultar o estado: ${error?.message ?? error}`;
  }
}

/**
 * The sidepanel never decides anything: it reads the form the operator opened
 * and hands the snapshot to the Mesa, which owns the whole fill workflow.
 */
async function refreshCurrentForm() {
  const info = document.getElementById("form-info");
  try {
    const response = await globalThis.chrome.runtime.sendMessage({ type: MESSAGE_TYPES.READ_CURRENT_FORM });
    lastConfirmedFormIdentity = retainLastConfirmedIdentity(lastConfirmedFormIdentity, response);
    currentFormAvailable = response?.ok === true && hasFormIdentity(response.form?.identity);
    if (currentFormAvailable) {
      info.textContent = `Processo atual: ${response.form.identity.processKey} — ${response.form.identity.interestedNormalized}`;
      updateActionButtons();
      return response.form;
    }
    info.textContent = hasFormIdentity(lastConfirmedFormIdentity)
      ? "Nenhum formulário aberto; a última identidade confirmada foi mantida."
      : "Nenhum formulário de ato aberto.";
    updateActionButtons();
    return null;
  } catch {
    info.textContent = "Abra a Área Restrita autenticada para o modo manual.";
    currentFormAvailable = false;
    updateActionButtons();
    return null;
  }
}

function updateActionButtons() {
  const fillButton = document.getElementById("fill-current");
  const nextButton = document.getElementById("next-process");
  const manualFill = describeManualFillCapability(reliabilityCapabilities);
  const nextProcess = describeNextProcessCapability(reliabilityCapabilities);
  if (fillButton) {
    fillButton.disabled =
      !manualFill.enabled || !currentFormAvailable || nextActInProgress || Boolean(acceptedNextTarget);
    fillButton.textContent = manualFill.enabled
      ? `Preencher formulário atual — ${manualFill.label}`
      : "Preencher formulário atual";
  }
  if (nextButton) {
    // Phase 1: automatic navigation is never offered to the operator.
    nextButton.disabled =
      !nextProcess.enabled ||
      !hasFormIdentity(lastConfirmedFormIdentity) ||
      nextActInProgress ||
      Boolean(acceptedNextTarget);
  }
}

function setNextActFeedback(message, isError = false) {
  nextActFeedback = message;
  const diagnostic = document.getElementById("diagnostic");
  diagnostic.className = isError ? "error" : "";
  diagnostic.textContent = message;
}

document.getElementById("fill-current").addEventListener("click", async () => {
  const diagnostic = document.getElementById("diagnostic");
  const button = document.getElementById("fill-current");
  button.disabled = true;
  nextActFeedback = null;
  diagnostic.className = "";
  diagnostic.textContent = "Enviando o formulário atual para a Mesa…";
  try {
    const form = await refreshCurrentForm();
    if (!form) {
      diagnostic.textContent = "Abra o formulário do ato antes de preencher.";
      return;
    }
    const outcome = await globalThis.chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.REQUEST_MANUAL_FILL,
      payload: form,
    });
    if (!outcome.ok) {
      diagnostic.className = "error";
      diagnostic.textContent = `A Mesa recusou o preenchimento: ${outcome.error}`;
      return;
    }
    diagnostic.textContent =
      `Estado ${outcome.payload?.state ?? ""}. Acompanhe os campos na Mesa; a conclusão do ato continua manual.`;
  } catch (error) {
    diagnostic.className = "error";
    diagnostic.textContent = `Falha ao preencher: ${error?.message ?? error}`;
  } finally {
    await refreshCurrentForm();
  }
});

document.getElementById("next-process").addEventListener("click", async () => {
  if (nextActInProgress || acceptedNextTarget || !hasFormIdentity(lastConfirmedFormIdentity)) return;

  nextActInProgress = true;
  updateActionButtons();
  setNextActFeedback("Abrindo próximo…");

  try {
    const response = await globalThis.chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.REQUEST_NEXT_ACT,
      payload: { identity: lastConfirmedFormIdentity },
    });
    const outcome = describeNextActOutcome(response);
    if (outcome.state === "end_of_queue") {
      setNextActFeedback(outcome.message);
      return;
    }
    if (outcome.state !== "opening") {
      setNextActFeedback(`Não foi possível abrir o próximo processo: ${outcome.code}`, true);
      return;
    }

    acceptedNextTarget = outcome.targetIdentity;
    updateActionButtons();
    const commandOutcome = await pollForNextActCommand({
      readCommandStatus: (commandId) =>
        globalThis.chrome.runtime.sendMessage({
          type: MESSAGE_TYPES.READ_NEXT_ACT_STATUS,
          payload: { command_id: commandId },
        }),
      commandId: outcome.commandId,
      targetIdentity: outcome.targetIdentity,
    });
    if (commandOutcome.state === "ready") {
      const identity = commandOutcome.identity;
      lastConfirmedFormIdentity = retainLastConfirmedIdentity(lastConfirmedFormIdentity, {
        ok: true,
        form: { identity },
      });
      currentFormAvailable = true;
      document.getElementById("form-info").textContent =
        `Processo atual: ${identity.processKey} — ${identity.interestedNormalized}`;
      acceptedNextTarget = null;
      setNextActFeedback(`Formulário pronto: ${identity.processKey}`);
    } else if (commandOutcome.state === "error") {
      acceptedNextTarget = null;
      setNextActFeedback(
        `Não foi possível abrir o próximo processo (${commandOutcome.code}): ${commandOutcome.message}`,
        true,
      );
    } else {
      setNextActFeedback(
        `A confirmação do comando ${outcome.commandId} ainda não chegou. A solicitação continua em acompanhamento; não a repita agora.`,
        true,
      );
    }
  } catch (error) {
    setNextActFeedback(`Falha ao abrir o próximo processo: ${error?.message ?? error}`, true);
  } finally {
    nextActInProgress = false;
    updateActionButtons();
  }
});

document.getElementById("open-mesa").addEventListener("click", () => {
  globalThis.chrome.tabs.create({ url: `${MESA_ORIGIN}/` });
});

document.addEventListener("DOMContentLoaded", refresh);
globalThis.setInterval(refresh, 5000);
