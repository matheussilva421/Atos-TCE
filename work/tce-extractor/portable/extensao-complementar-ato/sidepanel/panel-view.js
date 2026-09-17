import { isAutomaticLegalDecision, sameValue } from "../lib/automation-preflight.js";

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

const KIND_LABELS = Object.freeze({ exact: "exato", probable: "aproximado", tie: "empate real", pending: "sem preenchimento automático", "missing-source": "pendente" });
const LEGAL_EVIDENCE_LABELS = Object.freeze({
  "modality:voluntary_contribution": "aposentadoria voluntária por tempo de contribuição",
  "modality:invalidity_permanent_disability": "aposentadoria por incapacidade permanente",
  "proventos:integral": "proventos integrais",
  "proventos:proportional": "proventos proporcionais",
  "transition:true": "regra de transição",
  "context:professor": "contexto funcional de professor",
  "rule:teacher-explicit": "regra docente expressa",
});
const PROFESSOR_WARNING = "Professor identificado pelo cargo, mas a regra docente não foi encontrada expressamente na fundamentação. Revisão recomendada.";

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
  // Only a real TRUE_TIE is shown as a tie; every other non-automatic legal
  // state stays pending instead of being presented as an equivalent option.
  if (match?.legalDecision
    && match.legalDecision.decision_state === "TRUE_TIE"
    && !isAutomaticLegalDecision(match.legalDecision)) return "tie";
  if (match?.legalDecision && !isAutomaticLegalDecision(match.legalDecision)) return "pending";
  if (match?.kind) return match.kind;
  if (!field?.form_value) return "missing-source";
  return field.status === "found" && field.confidence === "high" ? "exact" : "probable";
}

function uniqueStrings(values) {
  return [...new Set(values.filter((value) => typeof value === "string" && value.trim()))];
}

function percentLabel(value) {
  if (typeof value === "number" && Number.isFinite(value)) return `${Math.round(value * 100)}%`;
  return "indisponível";
}

function marginLabel(value) {
  if (typeof value === "number" && Number.isFinite(value)) return `${Math.round(value * 100)} p.p.`;
  return "indisponível";
}

const DECISION_STATE_LABELS = Object.freeze({
  AUTO_SELECTED: "seleção automática",
  REVIEW_REQUIRED: "revisão necessária",
  TRUE_TIE: "empate real",
  NO_COMPATIBLE_CANDIDATE: "sem candidato compatível",
  CONTEXT_BLOCKED: "contexto jurídico bloqueado",
  DOCUMENT_CONFLICT: "conflito documental",
  CATALOG_UNRECOGNIZED: "catálogo não reconhecido",
});

const CONTEXT_STATUS_LABELS = Object.freeze({
  ready: "disponível",
  rebuilt: "reconstruído",
  blocked: "bloqueado",
});

const CONTEXT_SOURCE_LABELS = Object.freeze({
  cache: "cache",
  sidecar: "sidecar",
  rebuilt: "evidências locais",
});

function decisionStateOf(decision) {
  const explicit = decision?.decision_state;
  if (typeof explicit === "string" && explicit) return explicit;
  const status = decision?.status ?? "pending";
  // Without an explicit v3 state the decision is never presented as an
  // automatic selection, matching the write guard that requires AUTO_SELECTED.
  if (status === "selected") return "REVIEW_REQUIRED";
  if (status === "review") return "REVIEW_REQUIRED";
  return "NO_COMPATIBLE_CANDIDATE";
}

function methodLabel(value) {
  return value === "similarity"
    ? "similaridade jurídica"
    : value === "rule"
      ? "regra estrutural"
      : value === "exact"
        ? "equivalência textual"
        : "pendente";
}

export function buildLegalDiagnostics(decision, documentaryValue = "") {
  const classification = isRecord(decision?.portal_classification) ? decision.portal_classification : {};
  const foundation = isRecord(decision?.documentary_foundation) ? decision.documentary_foundation : {};
  const profile = isRecord(foundation.profile) ? foundation.profile : {};
  const references = Array.isArray(profile.references) ? profile.references : [];
  const ranking = Array.isArray(decision?.ranking) ? decision.ranking : [];
  const suggested = classification.option_label
    ?? decision?.option_label
    ?? ranking.find((candidate) => !candidate?.rejected)?.option_label
    ?? null;
  const method = classification.method ?? decision?.method ?? "none";
  const confidence = classification.confidence ?? decision?.confidence;
  const margin = classification.margin ?? decision?.margin;
  const evidence = Array.isArray(profile.evidence) ? profile.evidence : [];
  const coincidences = uniqueStrings(evidence.map((entry) => LEGAL_EVIDENCE_LABELS[entry]));
  const crosswalkReason = [...(classification.reasons ?? []), ...(decision?.reasons ?? [])]
    .some((reason) => String(reason).includes("ECE20_ART7_VOLUNTARY_TRANSITION"));
  const usesEce20 = references.some((reference) => reference?.diploma_type === "ece"
    && reference?.diploma_number === "20"
    && reference?.diploma_year === "2020");
  const usesHistoricalCatalog = typeof suggested === "string"
    && /\bEC\s*41\b|\bEC\s*47\b/iu.test(suggested);
  const differences = [];
  if ((crosswalkReason || usesEce20) && usesEce20 && usesHistoricalCatalog) {
    differences.push("resolução usa ECE 20/2020", "catálogo do portal usa classe histórica EC41/EC47");
  }
  const warnings = uniqueStrings([
    ...(Array.isArray(classification.warnings) ? classification.warnings : []),
    ...(Array.isArray(decision?.warnings) ? decision.warnings : []),
    ...(profile.professor_context === true
      && profile.professor_rule_explicit === false
      && /TEACHER|DOCENTE/iu.test(String(classification.class_id ?? ""))
      ? [PROFESSOR_WARNING]
      : []),
  ]);
  const decisionState = decisionStateOf(decision);
  const writeAllowed = isAutomaticLegalDecision(decision);
  return {
    status: decision?.status ?? "pending",
    decisionState,
    stateLabel: DECISION_STATE_LABELS[decisionState] ?? decisionState,
    writeAllowed,
    writeLabel: writeAllowed
      ? "Fundamento legal: será preenchido"
      : "Fundamento legal: não será preenchido automaticamente",
    contextStatus: decision?.context_status ?? null,
    contextStatusLabel: CONTEXT_STATUS_LABELS[decision?.context_status] ?? null,
    contextSource: decision?.context_source ?? null,
    contextSourceLabel: CONTEXT_SOURCE_LABELS[decision?.context_source] ?? null,
    contextReason: decision?.context_reason ?? null,
    documentary: text(foundation.operative_text ?? documentaryValue) || "Fonte documental indisponível.",
    suggested: suggested ? text(suggested) : "Proposta segura: nenhuma",
    candidateLabel: suggested ? text(suggested) : null,
    method,
    methodLabel: methodLabel(method),
    confidence,
    confidenceLabel: percentLabel(confidence),
    margin,
    marginLabel: marginLabel(margin),
    coincidences,
    differences,
    warnings,
  };
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
  const legalDiagnostics = buildLegalDiagnostics(
    legalDecision,
    record?.fields?.fundamento_legal?.source_value,
  );
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
    legalDiagnostics,
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
  const diagnostics = model.legalDiagnostics ?? buildLegalDiagnostics(model.legalDecision, model.fields.find((field) => field.id === "fundamento_legal")?.documentaryValue);
  legal.append(element(documentRef, "h2", "Fundamentação jurídica"));
  legal.append(element(documentRef, "p", `Fundamento documental: ${diagnostics.documentary}`, { class: "foundation-documentary" }));
  legal.append(element(documentRef, "p", `Contexto jurídico: ${diagnostics.contextStatusLabel ?? diagnostics.contextStatus ?? "não consultado"}`, { class: "foundation-context" }));
  if (diagnostics.contextSource !== null) {
    legal.append(element(documentRef, "p", `Origem: ${diagnostics.contextSourceLabel ?? diagnostics.contextSource}`, { class: "foundation-context-source" }));
  }
  if (diagnostics.contextReason !== null) {
    legal.append(element(documentRef, "p", `Motivo do contexto: ${diagnostics.contextReason}`, { class: "foundation-context-reason" }));
  }
  legal.append(element(documentRef, "p", `Regras: ${diagnostics.rulesVersion ?? "desconhecidas"}`, { class: "foundation-rules" }));
  legal.append(element(documentRef, "p", `Estado: ${diagnostics.stateLabel}`, { class: "foundation-state" }));
  legal.append(element(documentRef, "p", diagnostics.writeLabel, { class: "foundation-write" }));
  legal.append(element(documentRef, "p", diagnostics.candidateLabel
    ? `Candidato principal: ${diagnostics.candidateLabel}`
    : "Proposta segura: nenhuma", { class: "foundation-suggestion" }));
  legal.append(element(documentRef, "p", `Método: ${diagnostics.methodLabel}`));
  legal.append(element(documentRef, "p", `Confiança: ${diagnostics.confidenceLabel}`));
  legal.append(element(documentRef, "p", `Margem: ${diagnostics.marginLabel}`));
  if (diagnostics.coincidences.length > 0) {
    legal.append(element(documentRef, "h3", "Coincidências"));
    const list = element(documentRef, "ul", "", { class: "foundation-coincidences" });
    for (const item of diagnostics.coincidences) list.append(element(documentRef, "li", item));
    legal.append(list);
  }
  if (diagnostics.differences.length > 0) {
    legal.append(element(documentRef, "h3", "Diferenças esperadas pelo crosswalk"));
    const list = element(documentRef, "ul", "", { class: "foundation-differences" });
    for (const item of diagnostics.differences) list.append(element(documentRef, "li", item));
    legal.append(list);
  }
  if (diagnostics.warnings.length > 0) {
    legal.append(element(documentRef, "p", diagnostics.warnings.join("; "), { class: "foundation-warnings" }));
  }
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
