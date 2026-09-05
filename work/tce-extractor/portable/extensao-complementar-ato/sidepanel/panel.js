import { rankPortalOptions } from "../lib/matcher.js";
import { createMessage, MESSAGE_TYPES } from "../lib/messages.js";
import {
  ALLOWED_FIELDS,
  STORAGE_KEYS,
  validateDataset,
} from "../lib/schema.js";

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
      divergent: hasProposal && currentValue !== "" && currentValue !== text(proposedValue),
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
  return response?.error?.message || fallback;
}

export function createPanelApp({
  documentRef = globalThis.document,
  chromeApi = globalThis.chrome,
  confirmFn = (message) => typeof globalThis.confirm === "function" && globalThis.confirm(message),
  ranker = rankPortalOptions,
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
    message: "",
    listenersInstalled: false,
  };

  function setMessage(message, error = false) {
    state.message = text(message);
    if (error) elements["panel-message"].setAttribute("data-state", "error");
    else elements["panel-message"].setAttribute("data-state", "info");
  }

  function setBlocking(kind, screenText, identityText = "") {
    state.kind = kind;
    state.record = null;
    state.rows = [];
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

  function renderRows() {
    const body = elements["preview-body"];
    body.replaceChildren();
    for (const rowModel of state.rows) {
      const row = documentRef.createElement("tr");
      row.setAttribute("data-field", rowModel.field);
      const values = [
        rowModel.label,
        rowModel.documentaryValue || "—",
        rowModel.divergent
          ? `${rowModel.proposedLabel || "—"} · atual: ${rowModel.currentValue}`
          : (rowModel.proposedLabel || "—"),
      ];
      for (const value of values) {
        const cell = documentRef.createElement("td");
        cell.textContent = value;
        row.append(cell);
      }
      const statusCell = documentRef.createElement("td");
      statusCell.setAttribute("data-kind", rowModel.kind);
      statusCell.textContent = `${rowModel.statusText}${rowModel.confidence ? ` · ${rowModel.confidence}` : ""}`;
      row.append(statusCell);
      const sourceCell = documentRef.createElement("td");
      sourceCell.textContent = rowModel.citation;
      row.append(sourceCell);
      const actionCell = documentRef.createElement("td");
      if (rowModel.divergent) {
        const button = documentRef.createElement("button");
        button.setAttribute("type", "button");
        button.setAttribute("data-role", "override");
        button.setAttribute("data-field", rowModel.field);
        button.textContent = "Substituir este campo";
        button.addEventListener("click", () => { void overrideField(rowModel.field); });
        actionCell.append(button);
      }
      row.append(actionCell);
      body.append(row);
    }
  }

  function renderResult() {
    if (!state.result) {
      elements["result-summary"].textContent = "";
      return;
    }
    const pending = state.result.missing.length + state.result.disabled.length + state.result.errors.length;
    elements["result-summary"].textContent = `Alterados: ${state.result.changed.length} · Preservados: ${state.result.preserved.length} · Pendentes: ${pending}`;
  }

  function render() {
    const datasetStatus = state.dataset
      ? `Lote importado: ${state.dataset.batch.process_count} processo${state.dataset.batch.process_count === 1 ? "" : "s"}, ${state.dataset.batch.record_count} interessado${state.dataset.batch.record_count === 1 ? "" : "s"}.`
      : "Nenhum lote importado.";
    elements["dataset-status"].textContent = datasetStatus;
    elements["last-imported"].textContent = state.dataset ? `Última importação: ${state.dataset.generated_at}` : "";
    elements["permanent-warning"].textContent = "A extensão não conclui o ato";
    if (!state.message) elements["panel-message"].textContent = "";
    else elements["panel-message"].textContent = state.message;
    const canFill = Boolean(state.dataset && state.record && state.previewIdentity
      && (state.kind === PANEL_STATES.PREVIEW_READY || state.kind === PANEL_STATES.EXISTING_DIVERGENCE));
    elements["fill-button"].disabled = !canFill;
    elements["refresh-button"].disabled = !state.dataset;
    elements["review-section"].hidden = !state.record;
    elements["reviewed-checkbox"].disabled = !state.record;
    elements["reviewed-checkbox"].checked = state.reviewed;
    renderRows();
    renderResult();
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

  async function getMatch(snapshot) {
    const identity = identityFromSnapshot(snapshot);
    if (!identity) throw new Error("processo/ano/interessado não identificados");
    const response = await send(MESSAGE_TYPES.GET_MATCH, {
      processKey: identity.processKey,
      interestedNormalized: identity.interestedNormalized,
      options: snapshot.options ?? {},
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

  async function resolveSnapshot(snapshot) {
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
      state.record = payload.record;
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
      return true;
    } catch (error) {
      setBlocking(PANEL_STATES.INTERESTED_NOT_FOUND, "Registro atual não foi encontrado no lote.", `Interessado: ${text(snapshot.interested.original)}.`);
      setMessage(error instanceof Error ? error.message : String(error), true);
      render();
      return false;
    }
  }

  async function refresh() {
    if (!state.dataset) {
      state.kind = PANEL_STATES.NO_DATASET;
      state.result = null;
      render();
      return false;
    }
    try {
      const snapshot = await getSnapshot();
      return await resolveSnapshot(snapshot);
    } catch (error) {
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
      state.previewIdentity = null;
      state.result = null;
      state.message = "Lote importado; selecione ou atualize a tela atual para calcular a prévia.";
      render();
      return await refresh();
    } catch (error) {
      state.dataset = previous.dataset;
      state.snapshot = previous.snapshot;
      state.record = previous.record;
      state.rows = previous.rows;
      state.reviewed = previous.reviewed;
      state.previewIdentity = previous.previewIdentity;
      state.result = previous.result;
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
    state.reviewed = reviewedValue === true;
    render();
    return true;
  }

  async function init() {
    if (!state.listenersInstalled) {
      elements["import-button"].addEventListener("click", () => elements["dataset-file"].click?.());
      elements["dataset-file"].addEventListener("change", () => { void importSelectedFile(); });
      elements["refresh-button"].addEventListener("click", () => { void refresh(); });
      elements["fill-button"].addEventListener("click", () => { void fillAvailableFields(); });
      elements["reviewed-checkbox"].addEventListener("change", () => { void setReviewed(elements["reviewed-checkbox"].checked); });
      state.listenersInstalled = true;
    }
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
      message: state.message,
    };
  }

  return {
    getState,
    importSelectedFile,
    init,
    fillAvailableFields,
    overrideField,
    refresh,
    setReviewed,
  };
}

const runtimeDocument = typeof globalThis !== "undefined" ? globalThis.document : undefined;
const runtimeChrome = typeof globalThis !== "undefined" ? globalThis.chrome : undefined;
if (runtimeDocument && runtimeChrome?.runtime?.sendMessage) {
  const app = createPanelApp({ documentRef: runtimeDocument, chromeApi: runtimeChrome });
  void app.init();
}
