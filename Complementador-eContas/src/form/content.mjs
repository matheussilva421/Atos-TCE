import { PORTAL_ORIGIN } from '../shared/config.mjs';
import { requestLastDiagnostic, renderDiagnostic as renderDiagnosticPanel, subscribeDiagnosticUpdates } from './diagnostic-ui.mjs';
import { MESSAGE, createRequestId } from '../shared/protocol.mjs';
import { parseRoute } from '../shared/routes.mjs';
import { ensureModalityCatalog, readForm } from './form-reader.mjs';
import { applyFillPlan, createFillPlan } from './form-writer.mjs';
import { handleBatchFormMessage } from './batch-content.mjs';

const HOST_ID = 'complementador-econtas-root';
let route = parseRoute(location.href, PORTAL_ORIGIN);
let host = null;
let shadow = null;
let button = null;
let diagnosticButton = null;
let statusElement = null;
let sourceElement = null;
let diagnosticElement = null;
let inFlight = false;
let currentRequestId = null;
let timeoutHandle = null;

const FIELD_LABELS = Object.freeze({
  modalidade: 'Modalidade',
  dataDoeEstado: 'Data DOE',
  cargo: 'Cargo',
  matricula: 'Matrícula',
  dataNascimento: 'Nascimento',
});

function fieldLabel(name) {
  return FIELD_LABELS[name] || name || 'campo';
}

function pendingSummary(report) {
  const pending = [];
  for (const item of Array.isArray(report.skipped) ? report.skipped : []) {
    pending.push(fieldLabel(item.field));
  }
  for (const item of Array.isArray(report.errors) ? report.errors : []) {
    pending.push(fieldLabel(item.field) + (item.code ? ' (' + item.code + ')' : ''));
  }
  return [...new Set(pending)];
}

function ensureUi() {
  if (host && document.documentElement.contains(host)) {
    return;
  }
  host = document.createElement('div');
  host.id = HOST_ID;
  host.setAttribute('data-complementador-econtas', '1');
  shadow = host.attachShadow({ mode: 'open' });
  const buildVersion = chrome.runtime.getManifest().version;
  shadow.innerHTML = '<style>'
    + ':host{all:initial}'
    + '.wrap{position:fixed;right:16px;bottom:16px;z-index:2147483647;font:13px/1.45 system-ui,Segoe UI,sans-serif;color:#102a43;background:#fff;border:1px solid #b8c7d9;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.18);padding:10px 12px;max-width:290px;display:block}'
    + '.title{font-weight:700;margin-bottom:6px;font-size:12px;letter-spacing:.02em;color:#486581}'
    + 'button{appearance:none;border:0;border-radius:8px;background:#0b6e4f;color:#fff;font:600 14px/1.2 system-ui,Segoe UI,sans-serif;padding:9px 12px;cursor:pointer;width:100%}'
    + 'button:disabled{opacity:.65;cursor:wait}'
    + '.secondary{background:#fff;color:#0b6e4f;border:1px solid #0b6e4f;margin-top:6px;font-weight:600}'
    + '.status{font-size:12px;margin-top:7px;color:#334e68;min-height:32px}'
    + '.source{font-size:11px;margin-top:6px;color:#627d98}'
    + '.diagnostic{font-size:11px;margin-top:4px;color:#334e68}'
    + '[data-tone="error"]{color:#a61b1b}'
    + '[data-tone="warn"]{color:#8a5a00}'
    + '[data-tone="ok"]{color:#0b6e4f}'
    + '</style>'
    + '<div class="wrap"><div class="title">Complementador e-Contas ' + buildVersion + '</div>'
    + '<button type="button">⚡ Preencher</button>'
    + '<button type="button" class="secondary" data-action="diagnose">Diagnóstico L1 (somente leitura)</button>'
    + '<div class="status" data-tone="info">Pronto. Revise os campos antes de concluir.</div>'
    + '<div class="source" style="display:none"></div>'
    + '<div class="diagnostic" style="display:none"></div></div>';
  document.documentElement.appendChild(host);
  button = shadow.querySelector('button');
  diagnosticButton = shadow.querySelector('button[data-action="diagnose"]');
  statusElement = shadow.querySelector('.status');
  sourceElement = shadow.querySelector('.source');
  diagnosticElement = shadow.querySelector('.diagnostic');
  button.addEventListener('click', onClick);
  if (diagnosticButton) { diagnosticButton.addEventListener('click', onDiagnose); }
  subscribeDiagnosticUpdates(chrome.runtime, (value) => renderDiagnosticPanel(host, diagnosticElement, value));
  restoreDiagnostic();
}


async function restoreDiagnostic() {
  const last = await requestLastDiagnostic((message) => chrome.runtime.sendMessage(message));
  renderDiagnosticPanel(host, diagnosticElement, last);
}

function setStatus(text, tone) {
  if (!statusElement) {
    return;
  }
  statusElement.textContent = text;
  statusElement.setAttribute('data-tone', tone || 'info');
}

function setBusy(busy) {
  if (button) {
    button.disabled = Boolean(busy);
  }
  if (diagnosticButton) {
    diagnosticButton.disabled = Boolean(busy);
  }
}

function setUiVisible(visible) {
  if (host) {
    host.style.display = visible ? 'block' : 'none';
  }
}

function setSourceNote(note) {
  if (!sourceElement) {
    return;
  }
  if (note) {
    sourceElement.textContent = note;
    sourceElement.style.display = 'block';
  } else {
    sourceElement.textContent = '';
    sourceElement.style.display = 'none';
  }
}

function cancelLocal(message) {
  inFlight = false;
  currentRequestId = null;
  if (timeoutHandle) {
    clearTimeout(timeoutHandle);
    timeoutHandle = null;
  }
  setBusy(false);
  setStatus(message, 'error');
}

function describeError(response) {
  const code = response && response.error ? response.error.code : (response && response.code);
  if (code === 'SOURCE_NOT_FOUND') {
    return 'Abra os autos do mesmo processo em outra aba ou janela.';
  }
  if (code === 'SOURCE_AMBIGUOUS') {
    return 'Há mais de uma aba de autos deste processo. Feche a duplicada e tente novamente.';
  }
  if (code === 'DOCUMENT_NOT_READABLE') {
    return 'Não foi possível ler o documento aberto nos autos.';
  }
  if (code === 'DOCUMENT_CHANGED') {
    return 'O documento mudou durante a leitura. Nada foi preenchido.';
  }
  if (code === 'PARTIAL_DOCUMENT') {
    return 'O documento possui páginas sem texto legível. Nada foi preenchido.';
  }
  if (code === 'INTERESTED_CHANGED') {
    return 'O interessado mudou durante o preenchimento. Nada foi preenchido.';
  }
  if (code === 'PROCESS_CHANGED') {
    return 'O processo mudou durante o preenchimento. Nada foi preenchido.';
  }
  if (code === 'READ_TIMEOUT' || code === 'APPLY_TIMEOUT') {
    return 'Tempo esgotado. Tente novamente.';
  }
  return 'Não foi possível concluir. Nada foi salvo; revise e tente novamente.';
}

function updateRoute() {
  route = parseRoute(location.href, PORTAL_ORIGIN);
  if (route && route.kind === 'complemento') {
    ensureUi();
    setUiVisible(true);
    return;
  }
  if (inFlight) {
    cancelLocal('Cancelado: rota alterada. Nada foi salvo.');
  }
  setUiVisible(false);
}

async function onClick(event) {
  if (!event || event.isTrusted !== true) {
    return;
  }
  if (inFlight) {
    return;
  }
  updateRoute();
  if (!route || route.kind !== 'complemento') {
    return;
  }
  let form;
  try {
    form = readForm(document);
  } catch {
    setStatus('Formulário não carregado. Abra o Complementar Ato e selecione o interessado.', 'error');
    return;
  }
  inFlight = true;
  currentRequestId = createRequestId();
  setBusy(true);
  setSourceNote('');
  setStatus('Lendo documento…', 'info');
  if (host) {
    host.dataset.lastElapsedMs = '';
    host.dataset.lastStatus = 'running';
    host.dataset.lastErrorCode = '';
    host.dataset.lastSourceNote = '';
  }
  const started = performance.now();
  timeoutHandle = setTimeout(() => {
    if (inFlight) {
      cancelLocal('Tempo esgotado. Nada foi salvo; tente novamente.');
    }
  }, 120000);
  try {
    const response = await chrome.runtime.sendMessage({
      type: MESSAGE.REQUEST_FILL,
      requestId: currentRequestId,
      formSnapshot: {
        processId: form.processId,
        processLabel: form.processLabel,
        interestedKey: form.interestedKey,
        interestedName: form.interestedName,
        interestedCpf: form.interestedCpf,
        interestedCount: form.interestedCount,
      },
    });
    if (!inFlight || !response || response.requestId !== currentRequestId) {
      return;
    }
    const elapsed = Math.round(performance.now() - started);
    if (host) {
      host.dataset.lastElapsedMs = String(elapsed);
      host.dataset.lastStatus = response.ok && response.report && response.report.ok === false ? 'partial' : (response.ok ? 'ok' : 'error');
    }
    if (!response.ok) {
      if (host) {
        host.dataset.lastErrorCode = (response.error && response.error.code) || response.code || '';
      }
      setStatus(describeError(response), 'error');
      return;
    }
    const report = response.report || {};
    const filled = Array.isArray(report.filled) ? report.filled.length : 0;
    const preserved = Array.isArray(report.preserved) ? report.preserved.length : 0;
    const pending = pendingSummary(report);
    const notes = [];
    for (const key of ['dataDoeEstado', 'dataNascimento']) {
      const note = response.sourceNotes && response.sourceNotes[key];
      if (note) {
        notes.push(note);
      }
    }
    if (notes.length > 0) {
      setSourceNote(notes.join(' · '));
      if (host) {
        host.dataset.lastSourceNote = notes
          .map((note) => note.replace(/^Origem:\s*/, ''))
          .join(' · ');
      }
    }
    if (pending.length === 0 && filled + preserved > 0) {
      setStatus('Concluído: ' + filled + ' campo(s) preenchido(s), ' + preserved + ' preservado(s). Revise antes de complementar.', 'ok');
    } else if (filled + preserved === 0) {
      setStatus('Nenhum campo preenchido. Pendentes: ' + (pending.join(', ') || 'nenhum campo identificado') + '.', 'warn');
    } else {
      setStatus('Parcial: ' + filled + ' preenchido(s), ' + preserved + ' preservado(s), ' + pending.length + ' pendente(s): ' + pending.join(', ') + '. Revise os campos.', 'warn');
    }
  } catch {
    if (inFlight) {
      setStatus('Falha de comunicação com a extensão. Nada foi salvo; tente novamente.', 'error');
    }
  } finally {
    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
      timeoutHandle = null;
    }
    inFlight = false;
    currentRequestId = null;
    setBusy(false);
  }
}

async function onDiagnose(event) {
  if (!event || event.isTrusted !== true) {
    return;
  }
  if (inFlight) {
    return;
  }
  updateRoute();
  if (!route || route.kind !== 'complemento') {
    return;
  }
  let form;
  try {
    form = readForm(document);
  } catch {
    setStatus('Formulário não carregado. Abra o Complementar Ato e selecione o interessado.', 'error');
    return;
  }
  inFlight = true;
  currentRequestId = createRequestId();
  setBusy(true);
  setSourceNote('');
  setStatus('Lendo PDF em modo somente leitura…', 'info');
  if (host) {
    host.dataset.lastElapsedMs = '';
    host.dataset.lastStatus = 'running';
    host.dataset.lastErrorCode = '';
    host.dataset.lastSourceNote = '';
  }
  const started = performance.now();
  timeoutHandle = setTimeout(() => {
    if (inFlight) {
      cancelLocal('Tempo esgotado. Nada foi alterado; tente novamente.');
    }
  }, 30000);
  try {
    const response = await chrome.runtime.sendMessage({
      type: MESSAGE.DIAGNOSE_DOCUMENT,
      requestId: currentRequestId,
      formSnapshot: { processId: form.processId, processLabel: form.processLabel },
    });
    if (!inFlight || !response || response.requestId !== currentRequestId) {
      return;
    }
    const elapsed = Math.round(performance.now() - started);
    if (host) {
      host.dataset.lastElapsedMs = String(elapsed);
      host.dataset.lastStatus = response.ok ? 'diagnostic' : 'error';
    }
    if (!response.ok) {
      if (host) {
        host.dataset.lastErrorCode = (response.error && response.error.code) || response.code || '';
      }
      setStatus(describeError(response), 'error');
      return;
    }
    const diagnostic = response.diagnostic || {};
    setStatus(
      'Diagnóstico L1: ' + diagnostic.pagesCount + ' página(s), ' + diagnostic.totalChars + ' caractere(s), ' + elapsed + ' ms. Nenhum campo foi alterado.',
      'ok',
    );
  } catch {
    if (inFlight) {
      setStatus('Falha de comunicação com a extensão. Nada foi alterado.', 'error');
    }
  } finally {
    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
      timeoutHandle = null;
    }
    inFlight = false;
    currentRequestId = null;
    setBusy(false);
  }
}
async function handleApplyPlan(message) {
  await ensureModalityCatalog(document);
  const form = readForm(document);
  if (form.processId !== message.expected.processId) {
    return { ok: false, code: 'PROCESS_CHANGED' };
  }
  if (form.interestedKey !== message.expected.interestedKey) {
    return { ok: false, code: 'INTERESTED_CHANGED' };
  }
  const plan = createFillPlan(message.proposals, form);
  const report = await applyFillPlan(document, plan, {
    processId: form.processId,
    interestedKey: form.interestedKey,
    revisionMarker: form.revisionMarker,
  });
  return { ok: true, report, sourceNotes: plan.sourceNotes };
}

chrome.runtime.onMessage.addListener((message, sender) => {
  if (!message || message.type !== MESSAGE.DOCUMENT_SEARCH) {
    return false;
  }
  if (!sender || sender.id !== chrome.runtime.id) {
    return false;
  }
  if (!inFlight || message.requestId !== currentRequestId) {
    return false;
  }
  setStatus('Procurando Resolução e Guia Financeira…', 'info');
  return false;
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== MESSAGE.APPLY_PLAN) {
    return false;
  }
  if (!sender || sender.id !== chrome.runtime.id) {
    sendResponse({ ok: false, code: 'UNTRUSTED_SENDER' });
    return true;
  }
  if (!inFlight || message.requestId !== currentRequestId) {
    sendResponse({ ok: false, code: 'STALE_TRANSACTION' });
    return true;
  }
  handleApplyPlan(message).then(
    (response) => sendResponse(response),
    (error) => sendResponse({ ok: false, code: error.code || 'APPLY_FAILED' }),
  );
  return true;
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || (message.type !== MESSAGE.BATCH_SELECT_INTERESTED && message.type !== MESSAGE.BATCH_VALIDATE_FORM)) {
    return false;
  }
  handleBatchFormMessage(message, sender, document, chrome.runtime.id).then(
    (response) => sendResponse(response),
    (error) => sendResponse({ ok: false, code: error && error.code ? error.code : 'BATCH_FORM_FAILED' }),
  );
  return true;
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== MESSAGE.BATCH_APPLY) {
    return false;
  }
  if (!sender || sender.id !== chrome.runtime.id) {
    sendResponse({ ok: false, code: 'UNTRUSTED_SENDER' });
    return true;
  }
  handleApplyPlan(message).then(
    (response) => sendResponse(response),
    (error) => sendResponse({ ok: false, code: error && error.code ? error.code : 'BATCH_APPLY_FAILED' }),
  );
  return true;
});

window.addEventListener('hashchange', updateRoute);
if (window.navigation && typeof window.navigation.addEventListener === 'function') {
  window.navigation.addEventListener('navigatesuccess', updateRoute);
}
updateRoute();
