import { MESSAGE } from '../shared/protocol.mjs';
import { formatDiagnosticSummary } from '../shared/diagnostic-store.mjs';

export async function requestLastDiagnostic(sendMessage) {
  if (typeof sendMessage !== 'function') {
    return null;
  }
  try {
    const response = await sendMessage({ type: MESSAGE.GET_DIAGNOSTIC });
    return response && response.ok === true ? (response.diagnostic || null) : null;
  } catch {
    return null;
  }
}

export function renderDiagnostic(host, element, value) {
  if (!element) {
    return;
  }
  const summary = formatDiagnosticSummary(value);
  element.textContent = summary;
  if (element.style) {
    element.style.display = summary ? 'block' : 'none';
  }
  if (host && host.dataset) {
    host.dataset.lastDiagnosticState = value && value.state ? value.state : '';
    host.dataset.lastDiagnosticPages = value && typeof value.pagesCount === 'number' ? String(value.pagesCount) : '';
    host.dataset.lastDiagnosticChars = value && typeof value.totalChars === 'number' ? String(value.totalChars) : '';
    host.dataset.lastDiagnosticElapsed = value && typeof value.elapsedMs === 'number' ? String(value.elapsedMs) : '';
  }
}

export function subscribeDiagnosticUpdates(runtime, callback) {
  const noop = () => {};
  if (!runtime || !runtime.onMessage || typeof runtime.onMessage.addListener !== 'function') {
    return noop;
  }
  const listener = (message) => {
    if (!message || message.type !== MESSAGE.DIAGNOSTIC_UPDATE) {
      return;
    }
    try {
      callback(message.diagnostic || null);
    } catch {
      // O painel não pode derrubar o content script.
    }
  };
  runtime.onMessage.addListener(listener);
  return () => {
    try {
      if (typeof runtime.onMessage.removeListener === 'function') {
        runtime.onMessage.removeListener(listener);
      }
    } catch {
      // Remoção best-effort.
    }
  };
}