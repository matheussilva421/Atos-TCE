import { rankPortalOptions } from "../lib/matcher.js";
import { createMessage, MESSAGE_TYPES } from "../lib/messages.js";
import { sameValue } from "../lib/automation-preflight.js";
import {
  ALLOWED_FIELDS,
  STORAGE_KEYS,
  normalizeInterestedName,
  validateDataset,
} from "../lib/schema.js";
import { createBridgeClient, pairBridge } from "../lib/bridge-client.js";
import { buildPanelViewModel, renderPanelView } from "./panel-view.js";

export const PANEL_FIELD_ORDER = Object.freeze([...ALLOWED_FIELDS]);

export const PANEL_STATES = Object.freeze({
  NO_DATASET: "no-dataset",
  DATASET_IMPORTED: "dataset-imported",
  INCOMPATIBLE_SCREEN: "incompatible-screen",
  PROCESS_NOT_FOUND: "process-not-found",
  INTERESTED_NOT_SELECTED: "interested-not-selected",
  INTERESTED_NOT_FOUND: "interested-not-found",
  OPERATION_BLOCKED: "operation-blocked",
  PREVIEW_READY: "preview-ready",
  EXISTING_DIVERGENCE: "existing-divergence",
  FILLED_FOR_REVIEW: "filled-for-review",
});

const BRIDGE_ELEMENT_IDS = Object.freeze([
  "bridge-base-url",
  "bridge-pairing-code",
  "bridge-connect-button",
  "bridge-status",
]);

const FIELD_LABELS = Object.freeze({
  modalidade: "Modalidade",
  fundamento_legal: "Fundamento legal",
  data_publicacao_doe: "Data de publicação no DOE",
  cargo: "Cargo",
  matricula: "Matrícula",
  data_nascimento: "Data de nascimento",
  genero: "Gênero",
});
const SELECT_FIELDS = new Set(["modalidade", "fundamento_legal"]);
const MATCH_KINDS = new Set(["exact", "probable", "tie"]);
const KIND_LABELS = Object.freeze({
  exact: "exato",
  probable: "aproximado",
  tie: "empate",
  "missing-source": "pendente",
});
const ELEMENT_IDS = Object.freeze([
  "dataset-status",
  "screen-status",
  "identity-status",
  "panel-message",
  "result-summary",
  "last-imported",
  "permanent-warning",
  "import-button",
  "dataset-file",
  "refresh-button",
  "fill-button",
  "complement-button",
  "automation-auto-submit",
  "automation-marker",
  "automation-source-scope",
  "automation-lot-size",
  "analysis-preview-button",
  "analysis-lots-button",
  "analysis-lot-number",
  "analysis-acquisition-button",
  "analysis-acquisition-status",
  "analysis-status",
  "search-process",
  "search-interested",
  "search-results",
  "search-selection",
  "review-section",
  "reviewed-checkbox",
  "preview-body",
]);

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requestId() {
  if (typeof globalThis.crypto?.randomUUID === "function") return globalThis.crypto.randomUUID();
  requestId.counter += 1;
  return `panel-${Date.now()}-${requestId.counter}`;
}
requestId.counter = 0;

function unwrapResponse(response) {
  let payload = response?.payload;
  if (isRecord(payload) && payload.ok === false && Object.hasOwn(payload, "error")) {
    return { ok: false, payload: payload.payload, error: payload.error };
  }
  if (isRecord(payload) && typeof payload.ok === "boolean" && Object.hasOwn(payload, "payload")) {
    return { ok: payload.ok, payload: payload.payload, error: payload.error };
  }
  return { ok: response?.ok === true, payload, error: response?.error };
}

function identityFromSnapshot(snapshot) {
  const processKey = snapshot?.process?.key;
  const interestedNormalized = snapshot?.interested?.normalized;
  if (typeof processKey !== "string" || !processKey || typeof interestedNormalized !== "string" || !interestedNormalized) return null;
  return { processKey, interestedNormalized };
}

function sameIdentity(left, right) {
  return Boolean(left && right)
    && left.processKey === right.processKey
    && left.interestedNormalized === right.interestedNormalized;
}

function text(value) {
  return value === null || value === undefined ? "" : String(value);
}

function displayCitation(citation) {
  if (!citation) return "—";
  const document = citation.document ? ` · ${citation.document}` : "";
  return `Processo ${text(citation.process)} · evento ${text(citation.event)} · página ${text(citation.page)}${document}`;
}

function availableNames(dataset, processKey) {
  return dataset?.records
    ?.filter((record) => record.process.key === processKey)
    .map((record) => record.interested.original)
    .join(", ") || "nenhum";
}

function econtasRowsForAnalysis(rows, dataset) {
  return rows.map((row) => {
    const record = dataset?.records?.find((candidate) => (
      candidate?.process?.key === row.process_key
      && candidate?.interested?.normalized === row.interested_key
    ));
    const documents = [...new Set((record?.fields ? Object.values(record.fields) : [])
      .map((field) => field?.citation?.document)
      .filter((document) => typeof document === "string" && document.length > 0))]
      .map((document) => ({ label: document }));
    return {
      ...row,
      econtas: {
        match: record ? "exact" : "missing",
        documents,
        snapshot_hash: null,
        ocr_status: documents.length > 0 ? "ready" : "not_run",
      },
    };
  });
}

function fieldKind(field) {
  if (field?.form_value === null || field?.form_value === undefined || field?.form_value === "") return "missing-source";
  return field.status === "found" && field.confidence === "high" ? "exact" : "probable";
}

function createRows(record, snapshot, matches) {
  return PANEL_FIELD_ORDER.map((fieldName) => {
    const field = record.fields[fieldName];
    const match = SELECT_FIELDS.has(fieldName) ? matches?.[fieldName] : null;
    const kind = match?.kind ?? fieldKind(field);
    const proposedValue = SELECT_FIELDS.has(fieldName)
      ? (match?.optionValue ?? null)
      : (field?.form_value ?? null);
    const currentValue = text(snapshot.fields?.[fieldName]?.value);
    const hasProposal = proposedValue !== null && proposedValue !== undefined && proposedValue !== "";
    return {
      field: fieldName,
      label: FIELD_LABELS[fieldName],
      documentaryValue: text(field?.source_value),
      proposedValue: hasProposal ? text(proposedValue) : null,
      proposedLabel: SELECT_FIELDS.has(fieldName) ? text(match?.optionLabel ?? proposedValue) : text(proposedValue),
      currentValue,
      kind,
      statusText: KIND_LABELS[kind] ?? "pendente",
      confidence: text(field?.confidence),
      citation: displayCitation(field?.citation),
      disabled: snapshot.fields?.[fieldName]?.disabled === true || snapshot.fields?.[fieldName]?.readOnly === true,
      divergent: hasProposal
        && currentValue !== ""
        && !sameValue(fieldName, currentValue, text(proposedValue), snapshot.options?.[fieldName]),
      pending: !hasProposal,
      match,
    };
  });
}

function resultFromResponse(response) {
  const forwarded = unwrapResponse(response);
  if (!forwarded.ok) throw new Error(responseFailure(forwarded, "preenchimento bloqueado"));
  const payload = forwarded.payload;
  if (!isRecord(payload)) throw new Error("resultado do formulário ausente");
  return {
    changed: Array.isArray(payload.changed) ? payload.changed : [],
    preserved: Array.isArray(payload.preserved) ? payload.preserved : [],
    missing: Array.isArray(payload.missing) ? payload.missing : [],
    disabled: Array.isArray(payload.disabled) ? payload.disabled : [],
    errors: Array.isArray(payload.errors) ? payload.errors : [],
  };
}

function responseFailure(response, fallback) {
  if (typeof response?.error === "string" && response.error) return response.error;
  return typeof response?.error?.message === "string" && response.error.message ? response.error.message : fallback;
}

export function createPanelApp({
  documentRef = globalThis.document,
  chromeApi = globalThis.chrome,
  confirmFn = (message) => typeof globalThis.confirm === "function" && globalThis.confirm(message),
  ranker = rankPortalOptions,
  bridgeClientFactory = createBridgeClient,
  pairingFactory = pairBridge,
  setTimeoutFn = globalThis.setTimeout,
  clearTimeoutFn = globalThis.clearTimeout,
} = {}) {
  const elements = Object.fromEntries(ELEMENT_IDS.map((id) => [id, documentRef?.getElementById?.(id)]));
  const missingElement = ELEMENT_IDS.find((id) => !elements[id]);
  if (missingElement) throw new TypeError(`panel element is missing: ${missingElement}`);
  const state = {
    kind: PANEL_STATES.NO_DATASET,
    dataset: null,
    snapshot: null,
    record: null,
    rows: [],
    reviewed: false,
    previewIdentity: null,
    result: null,
    searchSelection: null,
    bridgeClient: null,
    bridgeConnectionPromise: null,
    bridgeRevision: null,
    bridgeDatasetRevision: null,
    bridgePollTimer: null,
    bridgePollDelay: 500,
    automationPollTimer: null,
    bridgeSequence: 0,
    bridgeContext: null,
    selectedView: "current",
    matches: {},
    automationRun: null,
    automationCapabilities: null,
    automationHistory: [],
    automationHistoryCursor: null,
    analysis: null,
    acquisitionJob: null,
    automationMode: "manual",
    refreshGeneration: 0,
    message: "",
    listenersInstalled: false,
  };

  const bridgeElements = Object.fromEntries(BRIDGE_ELEMENT_IDS.map((id) => [id, documentRef?.getElementById?.(id)]));

  function setBridgeStatus(message, error = false) {
    if (!bridgeElements["bridge-status"]) return;
    bridgeElements["bridge-status"].textContent = text(message);
    bridgeElements["bridge-status"].setAttribute("data-state", error ? "error" : "info");
  }

  function setMessage(message, error = false) {
    state.message = text(message);
    if (error) elements["panel-message"].setAttribute("data-state", "error");
    else elements["panel-message"].setAttribute("data-state", "info");
  }

  function setBlocking(kind, screenText, identityText = "") {
    state.kind = kind;
    state.record = null;
    state.rows = [];
    state.matches = {};
    state.reviewed = false;
    state.previewIdentity = null;
    state.result = null;
    elements["screen-status"].setAttribute("data-state", "blocked");
    elements["screen-status"].textContent = screenText;
    elements["identity-status"].textContent = identityText;
  }

  function transitionToOperationBlocked(error) {
    state.snapshot = null;
    setBlocking(PANEL_STATES.OPERATION_BLOCKED, "Operação bloqueada; atualize a prévia.");
    setMessage(error instanceof Error ? error.message : String(error), true);
    render();
    return false;
  }

  function renderResult() {
    if (!state.result) {
      elements["result-summary"].textContent = "";
      return;
    }
    const pending = state.result.missing.length + state.result.disabled.length + state.result.errors.length;
    elements["result-summary"].textContent = `Alterados: ${state.result.changed.length} · Preservados: ${state.result.preserved.length} · Pendentes: ${pending}`;
  }

  function matchingSearchRecords() {
    if (!state.dataset) return [];
    const processQuery = text(elements["search-process"].value).trim().toLowerCase();
    const interestedQuery = normalizeInterestedName(elements["search-interested"].value);
    return state.dataset.records.filter((record) => (
      (!processQuery || record.process.key.toLowerCase().includes(processQuery))
      && (!interestedQuery || record.interested.normalized.includes(interestedQuery))
    )).slice(0, 50);
  }

  function selectSearchRecord(record) {
    state.searchSelection = {
      processKey: record.process.key,
      interestedNormalized: record.interested.normalized,
    };
    elements["search-selection"].textContent = `${record.process.key} · ${record.interested.original}`;
    setMessage("Registro localizado. Selecione o mesmo interessado no portal e atualize a prévia; a busca não altera o formulário.");
    render();
  }

  function renderSearchResults() {
    const results = elements["search-results"];
    results.replaceChildren();
    const records = matchingSearchRecords();
    if (!state.dataset) {
      results.textContent = "Importe um lote para pesquisar.";
      return;
    }
    if (records.length === 0) {
      results.textContent = "Nenhum registro encontrado.";
      return;
    }
    for (const record of records) {
      const button = documentRef.createElement("button");
      button.setAttribute("type", "button");
      button.setAttribute("data-role", "search-result");
      button.textContent = `${record.process.key} · ${record.interested.original}`;
      button.addEventListener("click", () => selectSearchRecord(record));
      results.append(button);
    }
  }

  function render() {
    const focusedId = typeof documentRef?.activeElement?.id === "string" ? documentRef.activeElement.id : "";
    const datasetStatus = state.dataset
      ? `Lote importado: ${state.dataset.batch.process_count} processo${state.dataset.batch.process_count === 1 ? "" : "s"}, ${state.dataset.batch.record_count} interessado${state.dataset.batch.record_count === 1 ? "" : "s"}.`
      : "Nenhum lote importado.";
    elements["dataset-status"].textContent = datasetStatus;
    elements["last-imported"].textContent = state.dataset ? `Última importação: ${state.dataset.generated_at}` : "";
    const connection = {
      connected: Boolean(state.bridgeClient),
      automationAvailable: Boolean(state.automationCapabilities),
      realSendEnabled: state.automationCapabilities?.real_send_enabled === true,
      pilotEnabled: state.automationCapabilities?.pilot_enabled === true,
      pilotConsumesRemaining: state.automationCapabilities?.pilot_consumes_remaining === true,
    };
    const viewModel = buildPanelViewModel({
      record: state.record,
      snapshot: state.snapshot,
      matches: state.matches,
      run: state.automationRun,
      history: state.automationHistory,
      historyNextCursor: state.automationHistoryCursor,
      connection,
      selectedView: state.selectedView,
      mode: state.automationMode,
    });
    elements["permanent-warning"].textContent = viewModel.banner.message;
    if (!state.message) elements["panel-message"].textContent = "";
    else elements["panel-message"].textContent = state.message;
    const canFill = Boolean(state.dataset && state.record && state.previewIdentity
      && !["discovering", "running", "paused"].includes(state.automationRun?.status)
      && (state.kind === PANEL_STATES.PREVIEW_READY || state.kind === PANEL_STATES.EXISTING_DIVERGENCE));
    elements["fill-button"].disabled = !canFill;
    elements["complement-button"].disabled = !canFill;
    elements["automation-auto-submit"].disabled = state.automationCapabilities?.real_send_enabled !== true
      && state.automationCapabilities?.pilot_enabled !== true;
    elements["analysis-preview-button"].disabled = !state.bridgeClient || !state.dataset;
    elements["analysis-lots-button"].disabled = !state.analysis?.analysis_id;
    const lots = Array.isArray(state.analysis?.lots) ? state.analysis.lots : [];
    const lotSelect = elements["analysis-lot-number"];
    const previousLot = lotSelect.value;
    lotSelect.replaceChildren();
    for (const [index, lot] of lots.entries()) {
      const option = documentRef.createElement("option");
      const lotNumber = Number.isSafeInteger(lot?.lot_number) ? lot.lot_number : index + 1;
      option.value = String(lotNumber);
      option.textContent = `Lote ${lotNumber} · ${Array.isArray(lot?.items) ? lot.items.length : 0} processo(s)`;
      lotSelect.append(option);
    }
    if (lots.some((lot, index) => String(Number.isSafeInteger(lot?.lot_number) ? lot.lot_number : index + 1) === previousLot)) {
      lotSelect.value = previousLot;
    } else if (lots.length > 0) {
      lotSelect.value = String(Number.isSafeInteger(lots[0]?.lot_number) ? lots[0].lot_number : 1);
    }
    lotSelect.disabled = !state.bridgeClient || lots.length === 0;
    const acquisitionRunning = ["started", "running"].includes(state.acquisitionJob?.status);
    elements["analysis-acquisition-button"].disabled = !state.bridgeClient
      || !state.analysis?.analysis_id
      || lots.length === 0
      || acquisitionRunning;
    elements["analysis-status"].textContent = state.analysis?.preview
      ? `Análise ${state.analysis.preview.needs_complement} processo(s) precisam complementar o ato · ${state.analysis.preview.eligible} pronto(s) para preflight · ${state.analysis.preview.acquisition_eligible ?? state.analysis.preview.eligible} no escopo de aquisição · ${state.analysis.preview.blocked} bloqueado(s) · ${state.analysis.preview.lot_count} lote(s).`
      : "Nenhuma análise da lista autenticada foi criada.";
    const acquisitionStatus = state.acquisitionJob;
    elements["analysis-acquisition-status"].textContent = acquisitionStatus
      ? `Aquisição do lote ${acquisitionStatus.lot_number}: ${acquisitionStatus.status}. Job ${acquisitionStatus.job_id}.`
      : "Nenhuma aquisição de lote iniciada.";
    elements["refresh-button"].disabled = !state.dataset;
    elements["search-process"].disabled = !state.dataset;
    elements["search-interested"].disabled = !state.dataset;
    elements["review-section"].hidden = !state.record;
    elements["reviewed-checkbox"].disabled = !state.record;
    elements["reviewed-checkbox"].checked = state.reviewed;
    renderPanelView(elements["preview-body"], viewModel, {
      selectView(view) {
        state.selectedView = view;
        void chromeApi?.storage?.session?.set?.({ [STORAGE_KEYS.PANEL_VIEW]: view });
        render();
      },
      overrideField(field) { void overrideField(field); },
      start() { void startAutomation(); },
      pilot() { void startAutomation("pilot"); },
      pause() { void controlAutomation("pause"); },
      resume() { void controlAutomation("resume"); },
      stop() { void controlAutomation("stop"); },
      openDetails(runId) { void openAutomationHistory(runId); },
      loadMore() { void loadMoreAutomationHistory(); },
      openReport(runId) { void openAutomationReport(runId); },
    });
    if (focusedId && typeof documentRef?.getElementById === "function") {
      documentRef.getElementById(focusedId)?.focus?.();
    }
    renderResult();
    renderSearchResults();
    if (bridgeElements["bridge-connect-button"]) bridgeElements["bridge-connect-button"].disabled = !bridgeElements["bridge-pairing-code"]?.value?.trim();
    if (bridgeElements["bridge-status"] && state.bridgeClient && !bridgeElements["bridge-status"].textContent) setBridgeStatus("Mesa local conectada.");
  }

  async function send(type, payload) {
    if (typeof chromeApi?.runtime?.sendMessage !== "function") throw new Error("chrome.runtime.sendMessage indisponível");
    return chromeApi.runtime.sendMessage(createMessage(type, payload, requestId()));
  }

  async function getSnapshot() {
    const response = await send(MESSAGE_TYPES.GET_FORM_SNAPSHOT, {});
    const forwarded = unwrapResponse(response);
    if (!forwarded.ok) throw new Error(responseFailure(forwarded, "formulário não detectado"));
    const payload = forwarded.payload;
    if (!payload || !isRecord(payload.process)) throw new Error("snapshot do formulário inválido");
    return payload;
  }

  async function publishBridgeSelection(snapshot, identity, refreshGeneration = state.refreshGeneration) {
    if (!state.bridgeClient || refreshGeneration !== state.refreshGeneration) return;
    const context = snapshot?.bridgeContext;
    if (!context || !Number.isInteger(context.tab_id) || !Number.isInteger(context.frame_id)) {
      setBridgeStatus("Ponte conectada, mas a aba/frame atual não foi identificado.", true);
      return;
    }
    state.bridgeSequence += 1;
    state.bridgeContext = context;
    const bridgeClient = state.bridgeClient;
    const sequence = state.bridgeSequence;
    try {
      await bridgeClient.publishSelection({
        process_key: identity.processKey,
        interested_normalized: identity.interestedNormalized,
        tab_id: context.tab_id,
        frame_id: context.frame_id,
        sequence,
      });
      if (refreshGeneration !== state.refreshGeneration || state.bridgeClient !== bridgeClient) return;
      if (typeof bridgeClient.getState === "function") {
        try {
          const current = await bridgeClient.getState();
          if (refreshGeneration === state.refreshGeneration && state.bridgeClient === bridgeClient) {
            state.bridgeRevision = Number.isInteger(current?.revision) ? current.revision : null;
          }
        } catch {
          if (refreshGeneration === state.refreshGeneration && state.bridgeClient === bridgeClient) state.bridgeRevision = null;
        }
      } else if (refreshGeneration === state.refreshGeneration && state.bridgeClient === bridgeClient) {
        state.bridgeRevision = null;
      }
      if (refreshGeneration === state.refreshGeneration && state.bridgeClient === bridgeClient) {
        setBridgeStatus("Mesa local acompanhando a seleção atual.");
      }
    } catch (error) {
      if (refreshGeneration === state.refreshGeneration && state.bridgeClient === bridgeClient) {
        setBridgeStatus(`Mesa local desconectada: ${error instanceof Error ? error.message : String(error)}`, true);
      }
    }
  }

  async function syncBridgeDataset({ force = false } = {}) {
    if (!state.bridgeClient || typeof state.bridgeClient.getDataset !== "function") return false;
    try {
      const envelope = await state.bridgeClient.getDataset();
      const revision = envelope?.revision;
      if (!Number.isInteger(revision) || revision < 0) throw new Error("revisão do dataset inválida");
      if (!force && Number.isInteger(state.bridgeDatasetRevision) && revision <= state.bridgeDatasetRevision) return false;
      await validateDataset(envelope?.dataset);
      const imported = await send(MESSAGE_TYPES.IMPORT_DATASET, { dataset: envelope.dataset, preserveReviewed: true });
      if (!imported?.ok) throw new Error(responseFailure(imported, "dataset incremental rejeitado"));
      const hadIdentity = Boolean(state.snapshot?.process?.key && state.snapshot?.interested);
      state.dataset = envelope.dataset;
      state.bridgeDatasetRevision = revision;
      if (hadIdentity) await refresh();
      else {
        state.kind = PANEL_STATES.DATASET_IMPORTED;
        setMessage("Dataset atualizado pela mesa local; atualize a prévia para conferir a tela atual.");
        render();
      }
      setBridgeStatus("Mesa local conectada. Dataset incremental sincronizado; nenhum campo foi preenchido.");
      return true;
    } catch (error) {
      setBridgeStatus(`Mesa local desconectada: ${error instanceof Error ? error.message : String(error)}`, true);
      return false;
    }
  }

  function stopBridgePolling() {
    if (state.bridgePollTimer !== null) {
      clearTimeoutFn(state.bridgePollTimer);
      state.bridgePollTimer = null;
    }
    if (state.automationPollTimer !== null) {
      clearTimeoutFn(state.automationPollTimer);
      state.automationPollTimer = null;
    }
  }

  function scheduleBridgePolling() {
    if (!state.bridgeClient || typeof state.bridgeClient.getDataset !== "function" || state.bridgePollTimer !== null) return;
    const hidden = documentRef?.visibilityState === "hidden";
    const delay = hidden ? 2000 : state.bridgePollDelay;
    state.bridgePollTimer = setTimeoutFn(async () => {
      state.bridgePollTimer = null;
      const synced = await syncBridgeDataset();
      state.bridgePollDelay = synced ? 500 : Math.min(10000, Math.max(500, state.bridgePollDelay * 2));
      scheduleBridgePolling();
    }, delay);
    if (typeof state.bridgePollTimer?.unref === "function") state.bridgePollTimer.unref();
  }

  function scheduleAutomationPolling() {
    if (!state.bridgeClient || typeof state.bridgeClient.getAutomationCapabilities !== "function"
      || state.automationPollTimer !== null) return;
    state.automationPollTimer = setTimeoutFn(async () => {
      state.automationPollTimer = null;
      await refreshAutomationState({ loadHistory: false });
      scheduleAutomationPolling();
    }, 2000);
    if (typeof state.automationPollTimer?.unref === "function") state.automationPollTimer.unref();
  }

  async function connectBridge() {
    if (!bridgeElements["bridge-base-url"] || !bridgeElements["bridge-pairing-code"]) return false;
    try {
      const baseUrl = bridgeElements["bridge-base-url"].value.trim();
      const code = bridgeElements["bridge-pairing-code"].value.trim();
      const token = await pairingFactory({ baseUrl, code });
      state.bridgeClient = bridgeClientFactory({ baseUrl, token });
      state.bridgeRevision = null;
      state.bridgeDatasetRevision = null;
      state.bridgePollDelay = 500;
      const session = chromeApi?.storage?.session;
      if (typeof session?.set === "function") {
        await session.set({
          [STORAGE_KEYS.BRIDGE_BASE_URL]: baseUrl,
          [STORAGE_KEYS.BRIDGE_TOKEN]: token,
          [STORAGE_KEYS.BRIDGE_REVISION]: null,
        });
      }
      setBridgeStatus("Mesa local conectada. A seleção será publicada, sem preencher campos.");
      render();
      await syncBridgeDataset({ force: true });
      await refreshAutomationState();
      scheduleBridgePolling();
      scheduleAutomationPolling();
      return true;
    } catch (error) {
      state.bridgeClient = null;
      setBridgeStatus(`Falha no pareamento: ${error instanceof Error ? error.message : String(error)}`, true);
      render();
      return false;
    }
  }

  function beginBridgeConnection() {
    const promise = connectBridge();
    state.bridgeConnectionPromise = promise;
    void promise.finally(() => {
      if (state.bridgeConnectionPromise === promise) state.bridgeConnectionPromise = null;
    });
    return promise;
  }

  async function restoreBridge() {
    const session = chromeApi?.storage?.session;
    if (typeof session?.get !== "function") return;
    const stored = await session.get([
      STORAGE_KEYS.BRIDGE_BASE_URL,
      STORAGE_KEYS.BRIDGE_TOKEN,
      STORAGE_KEYS.BRIDGE_REVISION,
    ]);
    if (typeof stored?.[STORAGE_KEYS.BRIDGE_BASE_URL] !== "string" || typeof stored?.[STORAGE_KEYS.BRIDGE_TOKEN] !== "string") return;
    try {
      state.bridgeClient = bridgeClientFactory({
        baseUrl: stored[STORAGE_KEYS.BRIDGE_BASE_URL],
        token: stored[STORAGE_KEYS.BRIDGE_TOKEN],
      });
      state.bridgeRevision = Number.isInteger(stored[STORAGE_KEYS.BRIDGE_REVISION]) ? stored[STORAGE_KEYS.BRIDGE_REVISION] : null;
      if (bridgeElements["bridge-base-url"]) bridgeElements["bridge-base-url"].value = stored[STORAGE_KEYS.BRIDGE_BASE_URL];
      setBridgeStatus("Mesa local restaurada nesta sessão.");
      await syncBridgeDataset({ force: true });
      await refreshAutomationState();
      scheduleBridgePolling();
      scheduleAutomationPolling();
    } catch {
      state.bridgeClient = null;
      setBridgeStatus("Pareamento salvo inválido; conecte novamente.", true);
    }
  }

  async function getMatch(snapshot) {
    const identity = identityFromSnapshot(snapshot);
    if (!identity) throw new Error("processo/ano/interessado não identificados");
    const contextPayload = {};
    if (typeof state.bridgeClient?.getLegalContext === "function") {
      const contextEnvelope = await state.bridgeClient.getLegalContext(identity);
      const context = contextEnvelope?.context;
      if (isRecord(context)) {
        contextPayload.context = context;
        if (typeof context.dataset_sha256 === "string") contextPayload.datasetSha256 = context.dataset_sha256;
        if (typeof context.rules_version === "string") contextPayload.rulesVersion = context.rules_version;
        if (Number.isSafeInteger(context.context_revision) && context.context_revision >= 0) {
          contextPayload.contextRevision = context.context_revision;
        }
      }
    }
    const response = await send(MESSAGE_TYPES.GET_MATCH, {
      processKey: identity.processKey,
      interestedNormalized: identity.interestedNormalized,
      options: snapshot.options ?? {},
      ...contextPayload,
    });
    if (!response?.ok) throw new Error(responseFailure(response, "não foi possível calcular a prévia"));
    const payload = response.payload;
    if (!isRecord(payload) || !payload.record) throw new Error("registro não encontrado no lote");
    return payload;
  }

  function showSnapshotChange(snapshot) {
    state.snapshot = snapshot;
    const processKey = snapshot?.process?.key;
    const interested = snapshot?.interested;
    if (!processKey || !state.dataset?.batch.process_keys.includes(processKey)) {
      setBlocking(PANEL_STATES.PROCESS_NOT_FOUND, `Processo ${processKey || "atual"} não está no lote.`);
    } else if (!interested) {
      setBlocking(PANEL_STATES.INTERESTED_NOT_SELECTED, "Interessado não selecionado.");
    } else {
      setBlocking(PANEL_STATES.INTERESTED_NOT_FOUND, "Tela compatível.", `Interessado não encontrado no lote. Disponíveis: ${availableNames(state.dataset, processKey)}.`);
    }
    setMessage("A tela mudou desde a prévia; atualize a prévia antes de preencher.", true);
    render();
  }

  async function resolveSnapshot(snapshot, refreshGeneration = state.refreshGeneration) {
    if (refreshGeneration !== state.refreshGeneration) return false;
    state.snapshot = snapshot;
    const identity = identityFromSnapshot(snapshot);
    if (!snapshot?.process?.key || !state.dataset.batch.process_keys.includes(snapshot.process.key)) {
      setBlocking(PANEL_STATES.PROCESS_NOT_FOUND, `Processo ${snapshot?.process?.key || "atual"} não está no lote.`);
      setMessage("Processo atual não encontrado no lote.", true);
      render();
      return false;
    }
    if (!snapshot.interested) {
      setBlocking(PANEL_STATES.INTERESTED_NOT_SELECTED, "Tela compatível; interessado não selecionado.", "Interessado não selecionado.");
      setMessage("Selecione um interessado no formulário.", true);
      render();
      return false;
    }
    const localRecord = state.dataset.records.find((record) => (
      record.process.key === identity?.processKey
      && record.interested.normalized === identity?.interestedNormalized
    ));
    if (!localRecord) {
      setBlocking(PANEL_STATES.INTERESTED_NOT_FOUND, "Tela compatível.", `Interessado não encontrado no lote. Disponíveis: ${availableNames(state.dataset, snapshot.process.key)}.`);
      setMessage("O interessado atual não tem registro neste lote.", true);
      render();
      return false;
    }
    try {
      const payload = await getMatch(snapshot);
      if (refreshGeneration !== state.refreshGeneration) return false;
      state.record = payload.record;
      state.matches = payload.matches ?? {};
      state.rows = createRows(payload.record, snapshot, payload.matches);
      state.reviewed = payload.reviewed === true;
      state.previewIdentity = identity;
      state.kind = state.rows.some((row) => row.divergent)
        ? PANEL_STATES.EXISTING_DIVERGENCE
        : PANEL_STATES.PREVIEW_READY;
      state.result = null;
      setMessage("Prévia pronta.");
      elements["screen-status"].setAttribute("data-state", "ready");
      elements["screen-status"].textContent = state.kind === PANEL_STATES.EXISTING_DIVERGENCE
        ? "Prévia pronta com divergência existente."
        : "Prévia pronta.";
      elements["identity-status"].textContent = `Processo ${identity.processKey} · Interessado: ${snapshot.interested.original}.`;
      render();
      await publishBridgeSelection(snapshot, identity, refreshGeneration);
      return true;
    } catch (error) {
      if (refreshGeneration !== state.refreshGeneration) return false;
      setBlocking(PANEL_STATES.INTERESTED_NOT_FOUND, "Registro atual não foi encontrado no lote.", `Interessado: ${text(snapshot.interested.original)}.`);
      setMessage(error instanceof Error ? error.message : String(error), true);
      render();
      return false;
    }
  }

  async function refresh() {
    const refreshGeneration = state.refreshGeneration + 1;
    state.refreshGeneration = refreshGeneration;
    if (!state.dataset) {
      state.kind = PANEL_STATES.NO_DATASET;
      state.result = null;
      render();
      return false;
    }
    try {
      const snapshot = await getSnapshot();
      if (refreshGeneration !== state.refreshGeneration) return false;
      return await resolveSnapshot(snapshot, refreshGeneration);
    } catch (error) {
      if (refreshGeneration !== state.refreshGeneration) return false;
      state.snapshot = null;
      setBlocking(PANEL_STATES.INCOMPATIBLE_SCREEN, "Tela incompatível: formulário Complementar Ato não detectado.");
      setMessage(error instanceof Error ? error.message : String(error), true);
      render();
      return false;
    }
  }

  async function importSelectedFile() {
    const file = elements["dataset-file"].files?.[0];
    if (!file) return false;
    const previous = { ...state };
    try {
      const raw = await file.text();
      const dataset = JSON.parse(raw);
      await validateDataset(dataset);
      const response = await send(MESSAGE_TYPES.IMPORT_DATASET, { dataset });
      if (!response?.ok) throw new Error(responseFailure(response, "importação rejeitada"));
      state.dataset = dataset;
      state.kind = PANEL_STATES.DATASET_IMPORTED;
      state.snapshot = null;
      state.record = null;
      state.rows = [];
      state.matches = {};
      state.previewIdentity = null;
      state.result = null;
      state.searchSelection = null;
      elements["search-selection"].textContent = "";
      state.message = "Lote importado; selecione ou atualize a tela atual para calcular a prévia.";
      render();
      return await refresh();
    } catch (error) {
      state.dataset = previous.dataset;
      state.snapshot = previous.snapshot;
      state.record = previous.record;
      state.rows = previous.rows;
      state.matches = previous.matches;
      state.reviewed = previous.reviewed;
      state.previewIdentity = previous.previewIdentity;
      state.result = previous.result;
      state.searchSelection = previous.searchSelection;
      state.kind = previous.kind;
      setMessage(`Lote inválido ou rejeitado: ${error instanceof Error ? error.message : String(error)}`, true);
      render();
      return false;
    } finally {
      elements["dataset-file"].value = "";
    }
  }

  function applyPayload() {
    const fields = {};
    const matchKinds = {};
    for (const row of state.rows) {
      if (row.proposedValue === null) continue;
      fields[row.field] = row.proposedValue;
      if (MATCH_KINDS.has(row.kind)) matchKinds[row.field] = row.kind;
    }
    return { fields, matchKinds };
  }

  async function fillAvailableFields() {
    if (!state.dataset || !state.record || !state.previewIdentity) return false;
    try {
      const freshSnapshot = await getSnapshot();
      const freshIdentity = identityFromSnapshot(freshSnapshot);
      if (!sameIdentity(state.previewIdentity, freshIdentity)) {
        showSnapshotChange(freshSnapshot);
        return false;
      }
      const payload = await getMatch(freshSnapshot);
      state.snapshot = freshSnapshot;
      state.record = payload.record;
      state.matches = payload.matches ?? {};
      state.rows = createRows(payload.record, freshSnapshot, payload.matches);
      state.reviewed = payload.reviewed === true;
      const apply = applyPayload();
      if (Object.keys(apply.fields).length === 0) {
        state.result = { changed: [], preserved: [], missing: state.rows.map((row) => row.field), disabled: [], errors: [] };
        state.kind = PANEL_STATES.FILLED_FOR_REVIEW;
        setMessage("Nenhum campo disponível para preenchimento.");
        render();
        return false;
      }
      const response = await send(MESSAGE_TYPES.APPLY_FIELDS, apply);
      if (!response?.ok) throw new Error(responseFailure(response, "preenchimento bloqueado"));
      state.result = resultFromResponse(response);
      state.kind = PANEL_STATES.FILLED_FOR_REVIEW;
      setMessage("Preenchimento concluído para revisão.");
      elements["screen-status"].textContent = "Preenchimento concluído para revisão.";
      render();
      return true;
    } catch (error) {
      return transitionToOperationBlocked(error);
    }
  }

  async function requestComplementarAto() {
    if (!state.dataset || !state.record || !state.previewIdentity) return false;
    try {
      const freshSnapshot = await getSnapshot();
      const freshIdentity = identityFromSnapshot(freshSnapshot);
      if (!sameIdentity(state.previewIdentity, freshIdentity)) {
        showSnapshotChange(freshSnapshot);
        return false;
      }
      const response = await send(MESSAGE_TYPES.REQUEST_COMPLEMENTAR_ATO, freshIdentity);
      if (!response?.ok) throw new Error(responseFailure(response, "sinal bloqueado"));
      setMessage("Sinal enviado à área restrita; nenhuma ação final foi executada pela extensão.");
      render();
      return true;
    } catch (error) {
      return transitionToOperationBlocked(error);
    }
  }

  async function overrideField(fieldName) {
    const row = state.rows.find((candidate) => candidate.field === fieldName);
    if (!row?.divergent || row.proposedValue === null || !state.previewIdentity) return false;
    const confirmed = confirmFn(`Substituir somente o campo "${row.label}" no processo ${state.previewIdentity.processKey}? Valor atual: "${row.currentValue}". Novo valor: "${row.proposedValue}".`);
    if (!confirmed) return false;
    try {
      const freshSnapshot = await getSnapshot();
      if (!sameIdentity(state.previewIdentity, identityFromSnapshot(freshSnapshot))) {
        showSnapshotChange(freshSnapshot);
        return false;
      }
      const response = await send(MESSAGE_TYPES.OVERRIDE_FIELD, {
        field: fieldName,
        proposedValue: row.proposedValue,
      });
      if (!response?.ok) throw new Error(responseFailure(response, "substituição bloqueada"));
      state.snapshot = freshSnapshot;
      row.currentValue = row.proposedValue;
      row.divergent = false;
      state.result = resultFromResponse(response);
      state.kind = PANEL_STATES.FILLED_FOR_REVIEW;
      setMessage("Campo substituído; revise o formulário antes de concluir o ato.");
      render();
      return true;
    } catch (error) {
      return transitionToOperationBlocked(error);
    }
  }

  async function setReviewed(reviewedValue) {
    if (!state.previewIdentity || !state.record) return false;
    const response = await send(MESSAGE_TYPES.SET_REVIEWED, {
      processKey: state.previewIdentity.processKey,
      interestedNormalized: state.previewIdentity.interestedNormalized,
      reviewed: reviewedValue === true,
    });
    if (!response?.ok) {
      elements["reviewed-checkbox"].checked = state.reviewed;
      setMessage(responseFailure(response, "não foi possível salvar a revisão"), true);
      render();
      return false;
    }
    if (state.bridgeClient) {
      try {
        if (!Number.isInteger(state.bridgeRevision)) {
          const current = await state.bridgeClient.getState();
          state.bridgeRevision = Number.isInteger(current?.revision) ? current.revision : 0;
        }
        const progress = await state.bridgeClient.setCompleted(
          state.previewIdentity.processKey,
          reviewedValue === true,
          state.bridgeRevision,
        );
        if (Number.isInteger(progress?.revision)) state.bridgeRevision = progress.revision;
      } catch (error) {
        await send(MESSAGE_TYPES.SET_REVIEWED, {
          processKey: state.previewIdentity.processKey,
          interestedNormalized: state.previewIdentity.interestedNormalized,
          reviewed: state.reviewed,
        }).catch(() => undefined);
        setMessage(`Conclusão não sincronizada com a mesa local: ${error instanceof Error ? error.message : String(error)}`, true);
        render();
        return false;
      }
    }
    state.reviewed = reviewedValue === true;
    render();
    return true;
  }

  async function refreshAutomationState({ loadHistory = true } = {}) {
    const bridgeClient = state.bridgeClient;
    if (!bridgeClient || typeof bridgeClient.getAutomationCapabilities !== "function") return false;
    try {
      state.automationCapabilities = await bridgeClient.getAutomationCapabilities();
      if (!state.automationCapabilities) {
        state.automationRun = null;
        state.automationHistory = [];
        state.automationHistoryCursor = null;
        state.automationMode = "manual";
        render();
        return false;
      }
      if (state.acquisitionJob && typeof bridgeClient.getAnalysisAcquisition === "function") {
        try {
          state.acquisitionJob = await bridgeClient.getAnalysisAcquisition(
            state.acquisitionJob.analysis_id,
            state.acquisitionJob.job_id,
          );
        } catch {
          // Preserve the last local status; a transient bridge failure must not
          // turn a running acquisition into a false failure.
        }
      }
      if (loadHistory && typeof bridgeClient.listAutomationRuns === "function") {
        const history = await bridgeClient.listAutomationRuns({ limit: 20 });
        state.automationHistory = Array.isArray(history?.runs) ? history.runs : [];
        state.automationHistoryCursor = typeof history?.next_cursor === "string" ? history.next_cursor : null;
      }
      const session = chromeApi?.storage?.session;
      const stored = typeof session?.get === "function"
        ? await session.get([STORAGE_KEYS.AUTOMATION_RUN_ID, STORAGE_KEYS.PANEL_VIEW])
        : {};
      const storedRunId = stored?.[STORAGE_KEYS.AUTOMATION_RUN_ID];
      let run = null;
      if (typeof storedRunId === "string" && typeof bridgeClient.getAutomationRun === "function") {
        try { run = await bridgeClient.getAutomationRun(storedRunId); } catch { run = null; }
      }
      if (!run) {
        const candidate = state.automationHistory.find((item) => ["discovering", "running", "paused"].includes(item.state));
        if (candidate && typeof bridgeClient.getAutomationRun === "function") {
          try { run = await bridgeClient.getAutomationRun(candidate.run_id); } catch { run = null; }
        }
      }
      state.automationRun = run;
      state.automationMode = run ? "automatic" : "manual";
      if (typeof stored?.[STORAGE_KEYS.PANEL_VIEW] === "string") state.selectedView = stored[STORAGE_KEYS.PANEL_VIEW];
      if (run && typeof session?.set === "function") await session.set({ [STORAGE_KEYS.AUTOMATION_RUN_ID]: run.run_id });
      render();
      return true;
    } catch (error) {
      state.automationCapabilities = null;
      setBridgeStatus(`Automação indisponível: ${error instanceof Error ? error.message : String(error)}`, true);
      render();
      return false;
    }
  }

  async function startAutomation(mode = "batch") {
    if (state.bridgeConnectionPromise) await state.bridgeConnectionPromise;
    if (!state.bridgeClient || !state.automationCapabilities || !state.dataset) {
      setMessage("Conecte um serviço local compatível antes de iniciar a execução.", true);
      render();
      return false;
    }
    const context = state.snapshot?.bridgeContext;
    if (!context || !Number.isSafeInteger(context.tab_id) || !Number.isSafeInteger(context.frame_id)) {
      setMessage("Aba/frame do portal não identificado; atualize a prévia antes de iniciar.", true);
      render();
      return false;
    }
    if (mode === "pilot" && (
      state.automationCapabilities.pilot_enabled !== true
      || state.automationCapabilities.pilot_consumes_remaining !== true
      || !state.previewIdentity
    )) {
      setMessage("Piloto indisponível: habilite o piloto no serviço e atualize um ato atual.", true);
      render();
      return false;
    }
    try {
      const spec = {
        tabId: context.tab_id,
        sector: context.sector ?? "setor atual",
        datasetSha256: state.dataset.batch.logical_sha256,
        rulesVersion: state.automationCapabilities.rules_version,
      };
      const marker = text(elements["automation-marker"]?.value).trim();
      if (marker) spec.marker = marker;
      const sourceScope = text(elements["automation-source-scope"]?.value).trim();
      if (sourceScope) spec.sourceScope = sourceScope;
      const lotSize = Number.parseInt(text(elements["automation-lot-size"]?.value).trim(), 10);
      if (Number.isSafeInteger(lotSize) && lotSize > 0) spec.lotSize = lotSize;
      spec.acquisitionSource = "econtas";
      const autoSubmit = elements["automation-auto-submit"]?.checked === true;
      const autoSubmitAllowed = mode === "pilot"
        ? state.automationCapabilities.pilot_enabled === true
          && state.automationCapabilities.pilot_consumes_remaining === true
        : state.automationCapabilities.real_send_enabled === true;
      if (autoSubmit && !autoSubmitAllowed) {
        setMessage("Envio automático indisponível: a mesa local não está qualificada para este modo.", true);
        render();
        return false;
      }
      if (autoSubmit) {
        const target = marker ? `o marcador "${marker}"` : "todos os atos elegíveis";
        if (!confirmFn(`ATENÇÃO: concluir automaticamente ${target} executará ações externas no portal, clicará em Complementar Ato e exigirá conciliação em caso de resultado incerto. Continuar?`)) {
          setMessage("Execução automática cancelada antes de qualquer ação externa.");
          render();
          return false;
        }
        spec.autoSubmit = true;
      }
      if (mode === "pilot") {
        spec.mode = "pilot";
        spec.pilotIdentity = { ...state.previewIdentity, portalActId: state.previewIdentity.portalActId ?? null };
      }
      const response = await send(MESSAGE_TYPES.AUTO_START, {
        spec,
        eventId: `panel-start-${Date.now()}`,
      });
      const forwarded = unwrapResponse(response);
      if (!forwarded.ok || !isRecord(forwarded.payload)) {
        throw new Error(responseFailure(forwarded, "worker não iniciou a execução"));
      }
      const run = forwarded.payload;
      state.automationRun = run;
      state.automationMode = "automatic";
      state.selectedView = "execution";
      const session = chromeApi?.storage?.session;
      if (typeof session?.set === "function") await session.set({ [STORAGE_KEYS.AUTOMATION_RUN_ID]: run.run_id });
      setMessage("Execução criada; a descoberta da fila ocorrerá no worker.");
      render();
      return true;
    } catch (error) {
      setMessage(`Execução não iniciada: ${error instanceof Error ? error.message : String(error)}`, true);
      render();
      return false;
    }
  }

  async function startAnalysis() {
    if (state.bridgeConnectionPromise) await state.bridgeConnectionPromise;
    if (!state.bridgeClient || !state.dataset) {
      setMessage("Conecte a mesa local e importe um dataset antes de analisar.", true);
      render();
      return false;
    }
    const marker = text(elements["automation-marker"]?.value).trim();
    if (!marker) {
      setMessage("Informe o marcador antes de iniciar a análise.", true);
      render();
      return false;
    }
    const sourceScope = text(elements["automation-source-scope"]?.value).trim();
    const lotSize = Number.parseInt(text(elements["automation-lot-size"]?.value).trim(), 10);
    const context = state.snapshot?.bridgeContext;
    const spec = {
      sector: context?.sector ?? "*",
      datasetSha256: state.dataset.batch.logical_sha256,
      rulesVersion: state.automationCapabilities?.rules_version ?? "legal-foundation-v1",
      marker,
      sourceScope,
      lotSize,
      acquisitionSource: "econtas",
    };
    if (Number.isSafeInteger(context?.tab_id)) spec.tabId = context.tab_id;
    try {
      const response = await send(MESSAGE_TYPES.AUTO_ANALYZE, {
        spec,
        eventId: `panel-analysis-${Date.now()}`,
      });
      const forwarded = unwrapResponse(response);
      if (!forwarded.ok || !isRecord(forwarded.payload) || !Array.isArray(forwarded.payload.rows)) {
        throw new Error(responseFailure(forwarded, "a análise da Área Restrita não foi concluída"));
      }
      if (!isRecord(forwarded.payload.marker)) throw new Error("o marcador não foi confirmado na lista autenticada");
      const analysisSpec = {
        schema_version: 2,
        source_scope: forwarded.payload.source_scope,
        marker: forwarded.payload.marker,
        acquisition_source: "econtas",
        lot_size: lotSize,
        analysis_only: true,
        auto_prepare: false,
        auto_submit: false,
        dataset_sha256: state.dataset.batch.logical_sha256,
      };
      const snapshot = await state.bridgeClient.createAnalysisPreview({
        spec: analysisSpec,
        rows: econtasRowsForAnalysis(forwarded.payload.rows, state.dataset),
        observedAt: new Date().toISOString(),
      });
      state.analysis = snapshot;
      state.acquisitionJob = null;
      setMessage("Análise concluída sem alterar o portal. Revise a contagem antes de criar os lotes.");
      render();
      return true;
    } catch (error) {
      setMessage(`Análise não concluída: ${error instanceof Error ? error.message : String(error)}`, true);
      render();
      return false;
    }
  }

  async function createAnalysisLots() {
    if (!state.analysis?.analysis_id || !state.bridgeClient?.createAnalysisLots) return false;
    try {
      state.analysis = await state.bridgeClient.createAnalysisLots(state.analysis.analysis_id);
      setMessage("Lotes criados a partir da fotografia imutável; nenhum envio foi iniciado.");
      render();
      return true;
    } catch (error) {
      setMessage(`Lotes não criados: ${error instanceof Error ? error.message : String(error)}`, true);
      render();
      return false;
    }
  }

  async function startAnalysisAcquisition() {
    if (!state.bridgeClient?.startAnalysisAcquisition || !state.analysis?.analysis_id) return false;
    const lotNumber = Number.parseInt(text(elements["analysis-lot-number"]?.value).trim(), 10);
    if (!Number.isSafeInteger(lotNumber) || lotNumber < 1) {
      setMessage("Selecione um lote congelado antes de iniciar a aquisição.", true);
      render();
      return false;
    }
    try {
      state.acquisitionJob = await state.bridgeClient.startAnalysisAcquisition(state.analysis.analysis_id, lotNumber);
      setMessage(`Aquisição/OCR do lote ${lotNumber} iniciada; nenhum ato foi enviado.`);
      render();
      return true;
    } catch (error) {
      setMessage(`Aquisição não iniciada: ${error instanceof Error ? error.message : String(error)}`, true);
      render();
      return false;
    }
  }

  async function openAutomationHistory(runId) {
    if (!state.bridgeClient || typeof state.bridgeClient.getAutomationEvents !== "function") {
      setMessage("O histórico detalhado não está disponível na ponte atual.", true);
      render();
      return false;
    }
    try {
      const result = await state.bridgeClient.getAutomationEvents(runId, { after: 0, limit: 100 });
      state.automationHistory = state.automationHistory.map((run) => (
        run.run_id === runId ? { ...run, events: Array.isArray(result?.events) ? result.events : [] } : run
      ));
      state.selectedView = "history";
      setMessage("Cronologia persistida carregada; nenhuma ação de retomada foi enviada.");
      render();
      return true;
    } catch (error) {
      setMessage(`Detalhes do histórico indisponíveis: ${error instanceof Error ? error.message : String(error)}`, true);
      render();
      return false;
    }
  }

  async function loadMoreAutomationHistory() {
    if (!state.bridgeClient || typeof state.bridgeClient.listAutomationRuns !== "function" || !state.automationHistoryCursor) return false;
    try {
      const history = await state.bridgeClient.listAutomationRuns({ limit: 20, before: state.automationHistoryCursor });
      state.automationHistory = [...state.automationHistory, ...(Array.isArray(history?.runs) ? history.runs : [])];
      state.automationHistoryCursor = typeof history?.next_cursor === "string" ? history.next_cursor : null;
      render();
      return true;
    } catch (error) {
      setMessage(`Mais histórico indisponível: ${error instanceof Error ? error.message : String(error)}`, true);
      render();
      return false;
    }
  }

  async function controlAutomation(action) {
    const run = state.automationRun;
    if (!run || !state.bridgeClient || typeof state.bridgeClient.controlAutomationRun !== "function") return false;
    const messageType = {
      pause: MESSAGE_TYPES.AUTO_PAUSE,
      resume: MESSAGE_TYPES.AUTO_RESUME,
      stop: MESSAGE_TYPES.AUTO_STOP,
    }[action];
    if (!messageType) return false;
    if (action === "resume" && run.items?.some((item) => item.state === "unconfirmed")) {
      setMessage("Concilie o resultado incerto antes de retomar.", true);
      render();
      return false;
    }
    try {
      const response = await send(messageType, {
        eventId: `panel-${action}-${Date.now()}`,
        runId: run.run_id,
        expectedRevision: run.revision,
      });
      const forwarded = unwrapResponse(response);
      if (!forwarded.ok || !isRecord(forwarded.payload)) {
        throw new Error(responseFailure(forwarded, "worker não alterou a execução"));
      }
      state.automationRun = forwarded.payload;
      state.selectedView = "execution";
      setMessage(action === "pause" ? "Execução pausada; nenhum novo envio será iniciado." : action === "stop" ? "Execução encerrada; o relatório foi preservado." : "Execução retomada após conciliação.");
      render();
      return true;
    } catch (error) {
      setMessage(`Controle da execução falhou: ${error instanceof Error ? error.message : String(error)}`, true);
      render();
      return false;
    }
  }

  async function openAutomationReport(runId) {
    if (!state.bridgeClient || typeof state.bridgeClient.getAutomationReport !== "function") {
      setMessage("O relatório está disponível na mesa local; a ponte atual não expõe download.", true);
      render();
      return false;
    }
    try {
      const report = await state.bridgeClient.getAutomationReport(runId, "html");
      if (typeof Blob !== "function" || typeof URL?.createObjectURL !== "function") throw new Error("download de relatório indisponível neste ambiente");
      const url = URL.createObjectURL(new Blob([report.body], { type: report.contentType }));
      if (typeof globalThis.open === "function") globalThis.open(url, "_blank", "noopener");
      setMessage("Relatório HTML aberto em uma nova aba.");
      render();
      return true;
    } catch (error) {
      setMessage(`Relatório indisponível: ${error instanceof Error ? error.message : String(error)}`, true);
      render();
      return false;
    }
  }

  async function init() {
    if (!state.listenersInstalled) {
      elements["import-button"].addEventListener("click", () => elements["dataset-file"].click?.());
      elements["dataset-file"].addEventListener("change", () => { void importSelectedFile(); });
      elements["refresh-button"].addEventListener("click", () => { void refresh(); });
      elements["fill-button"].addEventListener("click", () => { void fillAvailableFields(); });
      elements["complement-button"].addEventListener("click", () => { void requestComplementarAto(); });
      elements["analysis-preview-button"].addEventListener("click", () => { void startAnalysis(); });
      elements["analysis-lots-button"].addEventListener("click", () => { void createAnalysisLots(); });
      elements["analysis-acquisition-button"].addEventListener("click", () => { void startAnalysisAcquisition(); });
      elements["search-process"].addEventListener("input", () => { render(); });
      elements["search-interested"].addEventListener("input", () => { render(); });
      elements["reviewed-checkbox"].addEventListener("change", () => { void setReviewed(elements["reviewed-checkbox"].checked); });
      bridgeElements["bridge-pairing-code"]?.addEventListener("input", () => { render(); });
      bridgeElements["bridge-connect-button"]?.addEventListener("click", () => { void beginBridgeConnection(); });
      state.listenersInstalled = true;
    }
    const storedView = await chromeApi?.storage?.session?.get?.([STORAGE_KEYS.PANEL_VIEW]);
    if (typeof storedView?.[STORAGE_KEYS.PANEL_VIEW] === "string") state.selectedView = storedView[STORAGE_KEYS.PANEL_VIEW];
    await restoreBridge();
    try {
      const stored = await chromeApi?.storage?.local?.get?.([STORAGE_KEYS.DATASET]);
      if (stored?.[STORAGE_KEYS.DATASET] !== undefined) {
        await validateDataset(stored[STORAGE_KEYS.DATASET]);
        state.dataset = stored[STORAGE_KEYS.DATASET];
        state.kind = PANEL_STATES.DATASET_IMPORTED;
        await refresh();
      }
    } catch (error) {
      state.dataset = null;
      state.kind = PANEL_STATES.NO_DATASET;
      setMessage(`Lote persistido inválido: ${error instanceof Error ? error.message : String(error)}`, true);
    }
    await refreshAutomationState();
    scheduleAutomationPolling();
    render();
    return getState();
  }

  function getState() {
    return {
      kind: state.kind,
      dataset: state.dataset,
      snapshot: state.snapshot,
      record: state.record,
      rows: state.rows,
      reviewed: state.reviewed,
      previewIdentity: state.previewIdentity,
      result: state.result,
      searchSelection: state.searchSelection,
      message: state.message,
      selectedView: state.selectedView,
      automationRun: state.automationRun,
      automationCapabilities: state.automationCapabilities,
      automationHistory: state.automationHistory,
      automationHistoryCursor: state.automationHistoryCursor,
      automationMode: state.automationMode,
      analysis: state.analysis,
      acquisitionJob: state.acquisitionJob,
    };
  }

  return {
    getState,
    importSelectedFile,
    init,
    fillAvailableFields,
    overrideField,
    requestComplementarAto,
    refresh,
    setReviewed,
    syncBridgeDataset,
      stopBridgePolling,
    startAutomation,
    startAnalysis,
    createAnalysisLots,
    startAnalysisAcquisition,
    controlAutomation,
    openAutomationHistory,
    loadMoreAutomationHistory,
    refreshAutomationState,
  };
}

const runtimeDocument = typeof globalThis !== "undefined" ? globalThis.document : undefined;
const runtimeChrome = typeof globalThis !== "undefined" ? globalThis.chrome : undefined;
if (runtimeDocument && runtimeChrome?.runtime?.sendMessage) {
  const app = createPanelApp({ documentRef: runtimeDocument, chromeApi: runtimeChrome });
  void app.init();
}
