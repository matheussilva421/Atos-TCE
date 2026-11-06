import { PORTAL_ORIGIN } from '../shared/config.mjs';
import { MESSAGE, createRequestId } from '../shared/protocol.mjs';
import { parseListRoute } from '../shared/routes.mjs';
import { readVisibleList } from './list-reader.mjs';
import { describeBatchState, describeControls, formatSummary, validateLimitsInput } from './list-ui.mjs';
import { applyFilterPreset, readFilterPreset, routeKeyFor } from './filter-preset.mjs';

const HOST_ID = 'complementador-econtas-batch-root';
let host = null;
let statusElement = null;
let summaryElement = null;
let startButton = null;
let previewButton = null;
let pauseButton = null;
let stopButton = null;
let resumeButton = null;
let examinedInput = null;
let savedInput = null;
let keepProblemInput = null;
let currentStatus = null;
let pollHandle = null;
let busy = false;
let autoRestored = false;

function onListRoute() {
  return Boolean(parseListRoute(location.href, PORTAL_ORIGIN));
}

function send(message) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(message, (response) => resolve(response || { ok: false, code: 'NO_RESPONSE' }));
    } catch {
      resolve({ ok: false, code: 'RUNTIME_UNAVAILABLE' });
    }
  });
}

function ensureUi() {
  if (!onListRoute()) {
    return;
  }
  if (host && document.documentElement.contains(host)) {
    return;
  }
  host = document.createElement('div');
  host.id = HOST_ID;
  const shadow = host.attachShadow({ mode: 'open' });
  const version = chrome.runtime.getManifest().version;
  shadow.innerHTML = '<style>'
    + ':host{all:initial}'
    + '.wrap{position:fixed;right:16px;bottom:16px;z-index:2147483646;font:13px/1.45 system-ui,Segoe UI,sans-serif;'
    + 'color:#102a43;background:#fff;border:1px solid #b8c7d9;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.18);'
    + 'padding:10px 12px;width:290px}'
    + '.title{font-weight:700;margin-bottom:6px;font-size:12px;letter-spacing:.02em;color:#486581}'
    + '.row{display:flex;gap:6px;margin-bottom:6px}'
    + 'label{flex:1;font-size:11px;color:#334e68}'
    + 'input{width:100%;box-sizing:border-box;margin-top:2px;padding:5px 6px;border:1px solid #bcccdc;border-radius:6px;font-size:13px}'
    + 'button{appearance:none;border:0;border-radius:8px;background:#0b6e4f;color:#fff;font:600 13px/1.2 system-ui,Segoe UI,sans-serif;'
    + 'padding:8px 10px;cursor:pointer;flex:1}'
    + 'button:disabled{opacity:.5;cursor:not-allowed}'
    + '.secondary{background:#fff;color:#0b6e4f;border:1px solid #0b6e4f}'
    + '.danger{background:#fff;color:#a61b1b;border:1px solid #a61b1b}'
    + '.option{display:flex;align-items:center;gap:6px;font-size:11px;color:#334e68;margin-bottom:6px}'
    + '.option input{width:auto;margin:0}'
    + '.status{font-size:12px;margin-top:6px;color:#334e68;min-height:18px}'
    + '.summary{font-size:11px;margin-top:4px;color:#627d98}'
    + '[data-tone="error"]{color:#a61b1b}[data-tone="warn"]{color:#8a5a00}[data-tone="ok"]{color:#0b6e4f}'
    + '</style>'
    + '<div class="wrap" role="region" aria-label="Automação em lote">'
    + '<div class="title">Complementador e-Contas ' + version + '</div>'
    + '<div class="row"><label>Máx. examinados<input type="number" min="1" step="1" value="5" aria-label="Máximo de processos examinados"></label>'
    + '<label>Máx. salvos<input type="number" min="1" step="1" value="1" aria-label="Máximo de atos confirmados"></label></div>'
    + '<div class="option"><label><input type="checkbox" data-option="keep-problem-tabs" checked> Manter abas de processos com problema</label></div>'
    + '<div class="row"><button type="button" data-action="preview" class="secondary">Pré-visualizar</button>'
    + '<button type="button" data-action="start">⚡ Rodar automação</button></div>'
    + '<div class="row"><button type="button" data-action="save-filters" class="secondary">Salvar filtros</button>'
    + '<button type="button" data-action="restore-filters" class="secondary">Restaurar filtros</button></div>'
    + '<div class="row"><button type="button" data-action="pause" class="secondary">Pausar</button>'
    + '<button type="button" data-action="stop" class="danger">Parar</button>'
    + '<button type="button" data-action="resume" class="secondary">Continuar</button></div>'
    + '<div class="status" role="status" aria-live="polite">Pronto para ler a página atual.</div>'
    + '<div class="summary"></div></div>';
  document.documentElement.appendChild(host);
  statusElement = shadow.querySelector('.status');
  summaryElement = shadow.querySelector('.summary');
  startButton = shadow.querySelector('button[data-action="start"]');
  previewButton = shadow.querySelector('button[data-action="preview"]');
  pauseButton = shadow.querySelector('button[data-action="pause"]');
  stopButton = shadow.querySelector('button[data-action="stop"]');
  resumeButton = shadow.querySelector('button[data-action="resume"]');
  const saveFiltersButton = shadow.querySelector('button[data-action="save-filters"]');
  const restoreFiltersButton = shadow.querySelector('button[data-action="restore-filters"]');
  examinedInput = shadow.querySelectorAll('input[type="number"]')[0];
  savedInput = shadow.querySelectorAll('input[type="number"]')[1];
  keepProblemInput = shadow.querySelector('input[data-option="keep-problem-tabs"]');
  keepProblemInput.addEventListener('change', onKeepProblemTabsChange);
  startButton.addEventListener('click', onStart);
  previewButton.addEventListener('click', onPreview);
  pauseButton.addEventListener('click', () => onControl('pause'));
  stopButton.addEventListener('click', () => onControl('stop'));
  resumeButton.addEventListener('click', () => onControl('resume'));
  saveFiltersButton.addEventListener('click', onSaveFilters);
  restoreFiltersButton.addEventListener('click', onRestoreFilters);
  applyControls(null);
  void loadBatchPrefs();
  void refreshStatus();
  setTimeout(() => { void autoRestoreFilters(); }, 1200);
}

async function loadBatchPrefs() {
  const response = await send({ type: MESSAGE.BATCH_PREFS_GET, requestId: createRequestId() });
  if (response && response.ok && response.prefs && keepProblemInput) {
    keepProblemInput.checked = response.prefs.keepProblemTabs !== false;
  }
}

async function onKeepProblemTabsChange() {
  if (!keepProblemInput) {
    return;
  }
  await send({
    type: MESSAGE.BATCH_PREFS_SET,
    requestId: createRequestId(),
    prefs: { keepProblemTabs: keepProblemInput.checked },
  });
}

async function onSaveFilters() {
  const preset = readFilterPreset(document);
  const route = routeKeyFor(location.href);
  const response = await send({ type: MESSAGE.FILTER_PRESET_SET, requestId: createRequestId(), preset, route });
  if (statusElement) {
    statusElement.dataset.tone = response && response.ok ? 'ok' : 'error';
    statusElement.textContent = response && response.ok
      ? 'Filtros salvos para as próximas sessões.'
      : 'Não foi possível salvar os filtros.';
  }
}

async function onRestoreFilters() {
  const route = routeKeyFor(location.href);
  const response = await send({ type: MESSAGE.FILTER_PRESET_GET, requestId: createRequestId(), route });
  if (!response || !response.ok || !response.preset) {
    if (statusElement) {
      statusElement.dataset.tone = 'warn';
      statusElement.textContent = 'Nenhum filtro salvo.';
    }
    return;
  }
  await applyFilterPreset(document, response.preset);
  if (statusElement) {
    statusElement.dataset.tone = 'ok';
    statusElement.textContent = 'Filtros restaurados.';
  }
}

async function autoRestoreFilters() {
  if (autoRestored) {
    return;
  }
  autoRestored = true;
  const claim = await send({ type: MESSAGE.FILTER_AUTO_CLAIM, requestId: createRequestId() });
  if (!claim || claim.apply !== true) {
    return;
  }
  const route = routeKeyFor(location.href);
  const response = await send({ type: MESSAGE.FILTER_PRESET_GET, requestId: createRequestId(), route });
  if (response && response.ok && response.preset) {
    const applied = await applyFilterPreset(document, response.preset, { search: false });
    if (!applied || applied.ok !== true) {
      return;
    }
    await send({ type: MESSAGE.FILTER_AUTO_DONE, requestId: createRequestId() });
    const search = [...document.querySelectorAll('button')]
      .find((button) => /^BUSCAR$/i.test((button.textContent || '').replace(/\s+/g, ' ').trim()));
    if (search) {
      search.click();
    }
  }
}

function removeUi() {
  if (host && host.parentNode) {
    host.parentNode.removeChild(host);
  }
  host = null;
}

function applyControls(status) {
  const controls = describeControls(status);
  if (startButton) startButton.disabled = !controls.canStart || busy;
  if (previewButton) previewButton.disabled = busy;
  if (pauseButton) pauseButton.disabled = !controls.canPause || busy;
  if (stopButton) stopButton.disabled = !controls.canStop || busy;
  if (resumeButton) resumeButton.disabled = !controls.canResume || busy;
}

function renderStatus(status) {
  currentStatus = status;
  const info = describeBatchState(status ? status.state : null);
  if (statusElement) {
    statusElement.dataset.tone = info.tone;
    statusElement.textContent = status ? info.label : 'Nenhum lote ativo.';
  }
  if (summaryElement) {
    summaryElement.textContent = formatSummary(status);
  }
  applyControls(status);
  schedulePoll();
}

function schedulePoll() {
  if (pollHandle) {
    clearTimeout(pollHandle);
    pollHandle = null;
  }
  if (!currentStatus) {
    return;
  }
  if (!['RUNNING', 'PAUSE_REQUESTED', 'STOP_REQUESTED'].includes(currentStatus.state)) {
    return;
  }
  pollHandle = setTimeout(() => { void refreshStatus(); }, 3000);
}

async function refreshStatus() {
  const response = await send({ type: MESSAGE.BATCH_STATUS, requestId: createRequestId() });
  if (response && response.ok) {
    renderStatus(response.report ? response : (response.batch || (response.batchId ? response : null)));
  }
}

function readLimits() {
  return validateLimitsInput({
    maxExamined: examinedInput ? examinedInput.value : '',
    maxSaved: savedInput ? savedInput.value : '',
  });
}

async function onPreview() {
  if (busy) {
    return;
  }
  busy = true;
  applyControls(currentStatus);
  if (statusElement) statusElement.textContent = 'Lendo a página atual...';
  const response = await send({ type: MESSAGE.BATCH_PREVIEW, requestId: createRequestId() });
  busy = false;
  applyControls(currentStatus);
  if (!response || !response.ok) {
    if (statusElement) {
      statusElement.dataset.tone = 'error';
      statusElement.textContent = response && response.code === 'EMPTY_LIST'
        ? 'Nenhum processo visível nesta página.'
        : 'Falha ao ler a listagem.';
    }
    return;
  }
  if (statusElement) {
    statusElement.dataset.tone = 'ok';
    statusElement.textContent = response.pending + ' pendentes, ' + response.completed
      + ' concluídos, ' + response.unknown + ' sem status.';
  }
}

async function onStart() {
  if (busy) {
    return;
  }
  const parsed = readLimits();
  if (!parsed.ok) {
    if (statusElement) {
      statusElement.dataset.tone = 'error';
      statusElement.textContent = 'Informe limites inteiros maiores que zero.';
    }
    return;
  }
  busy = true;
  applyControls(currentStatus);
  if (statusElement) statusElement.textContent = 'Congelando a fila da página atual...';
  const response = await send({
    type: MESSAGE.BATCH_START,
    requestId: createRequestId(),
    limits: parsed.limits,
    keepProblemTabs: keepProblemInput ? keepProblemInput.checked : true,
  });
  busy = false;
  if (!response || !response.ok) {
    applyControls(currentStatus);
    if (statusElement) {
      statusElement.dataset.tone = 'error';
      statusElement.textContent = response && response.code === 'BATCH_ALREADY_ACTIVE'
        ? 'Já existe um lote ativo.'
        : response && response.code === 'EMPTY_QUEUE'
          ? 'Nenhum processo pendente na página atual.'
          : 'Não foi possível iniciar o lote.';
    }
    return;
  }
  renderStatus(response);
}

async function onControl(action) {
  if (busy || !currentStatus || !currentStatus.batchId) {
    return;
  }
  busy = true;
  applyControls(currentStatus);
  const type = action === 'pause'
    ? MESSAGE.BATCH_PAUSE
    : action === 'stop' ? MESSAGE.BATCH_STOP : MESSAGE.BATCH_RESUME;
  const response = await send({
    type,
    requestId: createRequestId(),
    batchId: currentStatus.batchId,
    revision: currentStatus.revision,
  });
  busy = false;
  if (response && response.ok) {
    renderStatus(response);
  } else {
    applyControls(currentStatus);
    if (statusElement) {
      statusElement.dataset.tone = 'error';
      statusElement.textContent = response && response.code === 'STALE_REVISION'
        ? 'O lote mudou; estado atualizado.'
        : 'Comando recusado.';
    }
    void refreshStatus();
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== MESSAGE.BATCH_LIST_SNAPSHOT) {
    return false;
  }
  if (sender && sender.id && sender.id !== chrome.runtime.id) {
    sendResponse({ ok: false, code: 'UNTRUSTED_SENDER' });
    return false;
  }
  sendResponse(readVisibleList(document));
  return false;
});

function syncRoute() {
  if (onListRoute()) {
    ensureUi();
  }
}

try {
  navigation.addEventListener('navigatesuccess', syncRoute);
} catch {
  // Navegador sem Navigation API.
}
window.addEventListener('hashchange', syncRoute);
window.addEventListener('popstate', syncRoute);
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', syncRoute, { once: true });
} else {
  syncRoute();
}
const routeObserver = new MutationObserver(() => {
  if (!onListRoute()) {
    removeUi();
    return;
  }
  if (!host) {
    ensureUi();
  }
});
routeObserver.observe(document.documentElement, { childList: true, subtree: true });
