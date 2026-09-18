/**
 * Operational side panel: connection state, portal state, pairing when needed
 * and a shortcut to the Mesa. It is intentionally not a dashboard — the Mesa
 * owns the workflow.
 */

import { createApi } from "../lib/api.js";
import { MESA_ORIGIN, PORTAL_ORIGIN } from "../lib/protocol.js";

const api = createApi({ storage: globalThis.chrome?.storage?.local });

function setState(elementId, dotId, text, tone) {
  const label = document.getElementById(elementId);
  const dot = document.getElementById(dotId);
  if (label) label.textContent = text;
  if (dot) dot.className = `dot ${tone ?? ""}`.trim();
}

async function refreshMesa() {
  const credentials = await api.credentials();
  if (!credentials.paired) {
    setState("mesa-status", "mesa-dot", "Mesa: extensão não pareada", "warn");
    return { paired: false };
  }
  const status = await api.status();
  if (status.ok && status.paired) {
    setState("mesa-status", "mesa-dot", "Mesa conectada", "ok");
    return { paired: true };
  }
  setState("mesa-status", "mesa-dot", "Mesa indisponível ou token recusado", "error");
  return { paired: false };
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
    pairSection.hidden = mesa.paired;
    diagnostic.className = "";
    diagnostic.textContent = mesa.paired
      ? "Pronto: a Mesa comanda o trabalho e você confirma o ato no portal."
      : "Pareie com o código de seis dígitos exibido na Mesa.";
  } catch (error) {
    diagnostic.className = "error";
    diagnostic.textContent = `Falha ao consultar o estado: ${error?.message ?? error}`;
  }
}

document.getElementById("pair-action").addEventListener("click", async () => {
  const input = document.getElementById("pair-code");
  const diagnostic = document.getElementById("diagnostic");
  const outcome = await api.pair(input.value);
  if (!outcome.ok) {
    diagnostic.className = "error";
    diagnostic.textContent = `Pareamento recusado (${outcome.error}). Gere um novo código na Mesa.`;
    return;
  }
  input.value = "";
  await refresh();
});

document.getElementById("open-mesa").addEventListener("click", () => {
  globalThis.chrome.tabs.create({ url: `${MESA_ORIGIN}/` });
});

document.addEventListener("DOMContentLoaded", refresh);
globalThis.setInterval(refresh, 5000);
