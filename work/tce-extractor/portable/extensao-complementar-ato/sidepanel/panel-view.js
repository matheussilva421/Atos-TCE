import { sameValue } from "../lib/automation-preflight.js";

const FIELD_ORDER = Object.freeze([
  "modalidade",
  "fundamento_legal",
  "data_publicacao_doe",
  "cargo",
  "matricula",
  "data_nascimento",
  "genero",
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

const PANEL_VIEWS = Object.freeze(["principal", "details", "automation", "execution", "history"]);

const KIND_LABELS = Object.freeze({ exact: "exato", probable: "aproximado", tie: "empate", "missing-source": "pendente" });

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function text(value) {
  return value === null || value === undefined ? "" : String(value);
}

function identityFrom({ record, snapshot }) {
  const processKey = snapshot?.process?.key ?? record?.process?.key ?? null;
  const interestedNormalized = snapshot?.interested?.normalized ?? record?.interested?.normalized ?? null;
  const interestedOriginal = snapshot?.interested?.original ?? record?.interested?.original ?? null;
  return { processKey, interestedNormalized, interestedOriginal };
}

function fieldKind(field, match) {
  if (match?.kind) return match.kind;
  if (!field?.form_value) return "missing-source";
  return field.status === "found" && field.confidence === "high" ? "exact" : "probable";
}

function buildFields(record, snapshot, matches) {
  if (!record && !snapshot) return [];
  return FIELD_ORDER.map((name) => {
    const field = record?.fields?.[name] ?? {};
    const match = matches?.[name] ?? null;
    const proposedValue = match?.optionValue ?? field.form_value ?? null;
    const currentValue = snapshot?.fields?.[name]?.value ?? "";
    const hasProposal = proposedValue !== null && proposedValue !== undefined && proposedValue !== "";
    return {
      id: name,
      label: FIELD_LABELS[name],
      documentaryValue: text(field.source_value),
      proposedValue: hasProposal ? text(proposedValue) : null,
      proposedLabel: text(match?.optionLabel ?? proposedValue),
      currentValue: text(currentValue),
      citation: field.citation ?? null,
      kind: fieldKind(field, match),
      divergent: hasProposal
        && currentValue !== ""
        && !sameValue(name, currentValue, text(proposedValue), snapshot?.options?.[name]),
      disabled: snapshot?.fields?.[name]?.disabled === true || snapshot?.fields?.[name]?.readOnly === true,
    };
  });
}

function runSummary(run) {
  const items = Array.isArray(run?.items) ? run.items : [];
  const counts = Object.fromEntries(["confirmed", "pending", "failed", "unconfirmed", "send_intent", "filled", "prepared", "queued"].map((state) => [state, 0]));
  for (const item of items) if (Object.hasOwn(counts, item?.state)) counts[item.state] += 1;
  return {
    total: items.length,
    analyzed: counts.confirmed + counts.pending + counts.failed + counts.unconfirmed,
    confirmed: counts.confirmed,
    pending: counts.pending,
    failed: counts.failed,
    unconfirmed: counts.unconfirmed,
    active: counts.send_intent + counts.filled + counts.prepared,
    current: items.find((item) => ["send_intent", "filled", "prepared"].includes(item?.state)) ?? null,
    lastConfirmed: run?.last_confirmed_item_id ?? null,
  };
}

function buildBanner({ mode, run, connection }) {
  if (mode !== "automatic") return { tone: "info", message: "Modo manual: preenche para revisão; não envia o ato." };
  if (!connection?.connected) return { tone: "attention", message: "Conecte o serviço local para consultar a execução." };
  if (!connection.automationAvailable) return { tone: "attention", message: "O serviço local não oferece automação compatível; o modo manual permanece disponível." };
  if (run?.status === "paused" && runSummary(run).unconfirmed > 0) {
    return { tone: "error", message: "Não foi possível confirmar um envio; concilie o resultado antes de qualquer retomada." };
  }
  if (run?.status === "paused") return { tone: "attention", message: "Execução pausada. Nenhum novo envio será iniciado." };
  if (run?.status === "running" || run?.status === "discovering") return { tone: "info", message: "O lote complementa os atos elegíveis; o painel não precisa permanecer aberto." };
  if (run?.status === "completed") return { tone: "success", message: "Execução concluída; confira as pendências e o relatório." };
  return { tone: "info", message: "Modo automático pronto para iniciar uma execução explícita." };
}

export function buildPanelViewModel({
  record = null,
  snapshot = null,
  matches = {},
  run = null,
  history = [],
  historyNextCursor = null,
  connection = {},
  selectedView = "principal",
  mode = "manual",
} = {}) {
  const identity = identityFrom({ record, snapshot });
  const summary = runSummary(run);
  const active = ["discovering", "running", "paused"].includes(run?.status);
  const manualAvailable = Boolean(record && snapshot && !active);
  const automationAvailable = Boolean(connection.connected && connection.automationAvailable);
  const pilotAvailable = automationAvailable
    && connection.pilotEnabled === true
    && connection.pilotConsumesRemaining === true
    && Boolean(identity.processKey && identity.interestedNormalized);
  const legalDecision = matches?.fundamento_legal?.legalDecision ?? null;
  const actions = [
    { id: "fill", label: "Preencher campos disponíveis", enabled: manualAvailable && mode === "manual", disabledReason: manualAvailable ? null : "Atualização manual indisponível durante uma execução ativa." },
    { id: "start", label: "Iniciar execução", enabled: automationAvailable && !active, disabledReason: automationAvailable ? (active ? "Já existe uma execução ativa." : null) : "Conecte um serviço compatível." },
    { id: "pilot", label: "Executar piloto de um ato", enabled: pilotAvailable && !active, disabledReason: pilotAvailable ? (active ? "Já existe uma execução ativa." : null) : "Habilite o piloto explícito no serviço e atualize um ato atual." },
    { id: "pause", label: "Pausar", enabled: run?.status === "running" || run?.status === "discovering", disabledReason: "Nenhuma execução em andamento." },
    { id: "resume", label: "Retomar após conciliação", enabled: run?.status === "paused" && summary.unconfirmed === 0, disabledReason: summary.unconfirmed ? "Concilie o resultado incerto antes de retomar." : "A execução não está pausada." },
    { id: "stop", label: "Encerrar execução", enabled: active, disabledReason: "Nenhuma execução ativa." },
    { id: "report", label: "Ver relatório parcial", enabled: Boolean(run?.run_id), disabledReason: "Relatório indisponível sem execução." },
  ];
  return {
    selectedView: PANEL_VIEWS.includes(selectedView) ? selectedView : "principal",
    identity,
    connection: {
      connected: connection.connected === true,
      automationAvailable,
      realSendEnabled: connection.realSendEnabled === true,
      pilotEnabled: connection.pilotEnabled === true,
      pilotConsumesRemaining: connection.pilotConsumesRemaining === true,
    },
    legalDecision,
    fields: buildFields(record, snapshot, matches),
    runSummary: summary,
    run: run ? {
      status: run.status,
      runId: run.run_id ?? run.runId ?? null,
      sector: run.spec?.sector ?? run.sector ?? null,
      marker: run.marker ?? run.spec?.marker ?? null,
    } : null,
    history: Array.isArray(history) ? history : [],
    historyNextCursor: typeof historyNextCursor === "string" && historyNextCursor ? historyNextCursor : null,
    actions,
    banner: buildBanner({ mode, run, connection }),
  };
}

function element(documentRef, tagName, value = "", attributes = {}) {
  const node = documentRef.createElement(tagName);
  node.textContent = value;
  for (const [key, attribute] of Object.entries(attributes)) node.setAttribute(key, attribute);
  return node;
}

function buttonFor(documentRef, action, handlers) {
  const button = element(documentRef, "button", action.label, { type: "button", "data-action": action.id });
  button.disabled = action.enabled !== true;
  if (!action.enabled && action.disabledReason) button.setAttribute("aria-label", `${action.label}: ${action.disabledReason}`);
  if (action.enabled && typeof handlers?.[action.id] === "function") button.addEventListener("click", handlers[action.id]);
  return button;
}

function renderDetails(documentRef, root, model, handlers) {
  const section = element(documentRef, "section", "", { id: "panel-details-view" });
  const identity = element(documentRef, "p", `${text(model.identity.processKey) || "Processo não detectado"} · ${text(model.identity.interestedOriginal) || "Interessado não detectado"}`, { class: "panel-identity" });
  const legal = element(documentRef, "section", "", { class: "foundation-trail" });
  legal.append(element(documentRef, "h2", "Fundamentação"));
  legal.append(element(documentRef, "p", `Método: ${model.legalDecision?.method === "similarity" ? "Por semelhança" : model.legalDecision?.method === "rule" ? "Por regra" : "Pendente"}`));
  legal.append(element(documentRef, "p", text(model.fields.find((field) => field.id === "fundamento_legal")?.documentaryValue) || "Fonte documental indisponível."));
  if (model.legalDecision?.reasons?.length) legal.append(element(documentRef, "p", model.legalDecision.reasons.join("; "), { class: "foundation-reasons" }));
  const fields = element(documentRef, "div", "", { class: "fields-list", id: "fields-list" });
  for (const field of model.fields) {
    const card = element(documentRef, "article", "", { class: "field-card", "data-field": field.id, "data-kind": field.kind });
    card.append(element(documentRef, "h3", field.label));
    card.append(element(documentRef, "p", `Documento: ${field.documentaryValue || "—"}`));
    card.append(element(documentRef, "p", `Portal: atual: ${field.currentValue || "vazio"}`));
    card.append(element(documentRef, "p", `Proposta: ${field.proposedLabel || "—"}`));
    card.append(element(documentRef, "p", `Status: ${KIND_LABELS[field.kind] ?? "pendente"}`, { class: "field-kind" }));
    card.append(element(documentRef, "p", field.divergent ? "Divergente" : field.disabled ? "Indisponível" : "Sem alteração", { class: "field-state" }));
    if (field.divergent && typeof handlers?.overrideField === "function") {
      const override = element(documentRef, "button", "Revisar divergência", { type: "button", "data-role": "override", "data-field": field.id });
      override.addEventListener("click", () => handlers.overrideField(field.id));
      card.append(override);
    }
    fields.append(card);
  }
  section.append(identity, legal, fields);
  root.append(section);
}

function renderExecution(documentRef, root, model, handlers) {
  const section = element(documentRef, "section", "", { id: "panel-execution-view" });
  const summary = model.runSummary;
  section.append(element(documentRef, "h2", "Execução"));
  section.append(element(documentRef, "p", model.run?.status ? `Estado: ${model.run.status}` : "Nenhuma execução iniciada."));
  section.append(element(documentRef, "p", `${summary.analyzed} analisados de ${summary.total} · ${summary.confirmed} confirmados · ${summary.pending} pendentes · ${summary.unconfirmed} incertos`));
  section.append(element(documentRef, "p", model.run?.sector ? `Setor: ${model.run.sector}` : "Setor ainda não informado."));
  if (model.run?.marker) section.append(element(documentRef, "p", `Marcador: ${model.run.marker}`));
  if (summary.current) section.append(element(documentRef, "p", `Agora: ${text(summary.current.identity?.processKey)}`));
  if (summary.lastConfirmed) section.append(element(documentRef, "p", `Último confirmado: ${summary.lastConfirmed}`));
  const actions = element(documentRef, "div", "", { class: "execution-actions" });
  for (const id of ["pilot", "start", "pause", "resume", "stop", "report"]) {
    const action = model.actions.find((candidate) => candidate.id === id);
    if (action) actions.append(buttonFor(documentRef, action, handlers));
  }
  section.append(actions);
  root.append(section);
}

function renderHistory(documentRef, root, model, handlers) {
  const section = element(documentRef, "section", "", { id: "panel-history-view" });
  section.append(element(documentRef, "h2", "Histórico"));
  const list = element(documentRef, "div", "", { class: "history-list" });
  for (const run of model.history) {
    const item = element(documentRef, "article", "", { class: "history-item" });
    item.append(element(documentRef, "h3", `${text(run.created_at)} · ${text(run.state)}`));
    item.append(element(documentRef, "p", `${text(run.run_id)} · ${text(run.totals?.confirmed ?? 0)} confirmados`));
    const details = buttonFor(documentRef, { id: "details", label: "Abrir detalhes", enabled: true, disabledReason: null }, {
      details: () => handlers?.openDetails?.(run.run_id),
    });
    item.append(details);
    const report = { id: "report", label: "HTML", enabled: true, disabledReason: null };
    const button = buttonFor(documentRef, report, { report: () => handlers?.openReport?.(run.run_id) });
    item.append(button);
    if (Array.isArray(run.events) && run.events.length > 0) {
      const events = element(documentRef, "ol", "", { class: "history-events" });
      for (const event of run.events) {
        events.append(element(documentRef, "li", `${text(event.created_at)} · ${text(event.type)}`));
      }
      item.append(events);
    }
    list.append(item);
  }
  if (model.history.length === 0) list.append(element(documentRef, "p", "Nenhuma execução persistida."));
  if (model.historyNextCursor) {
    list.append(buttonFor(documentRef, { id: "load-more", label: "Carregar mais", enabled: true, disabledReason: null }, {
      "load-more": () => handlers?.loadMore?.(),
    }));
  }
  section.append(list);
  root.append(section);
}

export function renderPanelView(root, model, handlers = {}) {
  const detailsRoot = root?.details ?? root;
  const executionRoot = root?.execution ?? null;
  const historyRoot = root?.history ?? null;
  if (!detailsRoot?.ownerDocument?.createElement || typeof detailsRoot.replaceChildren !== "function") return;
  const documentRef = detailsRoot.ownerDocument;
  detailsRoot.replaceChildren();
  renderDetails(documentRef, detailsRoot, model, handlers);
  if (executionRoot?.ownerDocument?.createElement && typeof executionRoot.replaceChildren === "function") {
    executionRoot.replaceChildren();
    renderExecution(documentRef, executionRoot, model, handlers);
  }
  if (historyRoot?.ownerDocument?.createElement && typeof historyRoot.replaceChildren === "function") {
    historyRoot.replaceChildren();
    renderHistory(documentRef, historyRoot, model, handlers);
  }
}
