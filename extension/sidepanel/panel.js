/**
 * Operational side panel: connection state, portal state, pairing when needed
 * and a shortcut to the Mesa. It is intentionally not a dashboard — the Mesa
 * owns the workflow.
 */

import { MESA_ORIGIN, MESSAGE_TYPES, PORTAL_ORIGIN } from "../lib/protocol.js";
import { describeMesaStatus } from "./state.js";

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
  const pairSection = document.getElementById("pair-section");
  const diagnostic = document.getElementById("diagnostic");
  try {
    const mesa = await refreshMesa();
    await refreshPortal();
    await refreshCurrentForm();
    pairSection.hidden = mesa.paired;
    diagnostic.className = "";
    diagnostic.textContent = mesa.diagnostic ?? "Pareie com o código de seis dígitos exibido na Mesa.";
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
  const button = document.getElementById("fill-current");
  try {
    const response = await globalThis.chrome.runtime.sendMessage({ type: "READ_CURRENT_FORM" });
    if (response?.ok && response.form) {
      info.textContent = `Processo atual: ${response.form.identity.processKey} — ${response.form.identity.interestedNormalized}`;
      button.disabled = false;
      return response.form;
    }
    info.textContent = "Nenhum formulário de ato aberto.";
    button.disabled = true;
    return null;
  } catch {
    info.textContent = "Abra a Área Restrita autenticada para o modo manual.";
    button.disabled = true;
    return null;
  }
}

document.getElementById("fill-current").addEventListener("click", async () => {
  const diagnostic = document.getElementById("diagnostic");
  const button = document.getElementById("fill-current");
  button.disabled = true;
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

document.getElementById("open-mesa").addEventListener("click", () => {
  globalThis.chrome.tabs.create({ url: `${MESA_ORIGIN}/` });
});

document.addEventListener("DOMContentLoaded", refresh);
globalThis.setInterval(refresh, 5000);
