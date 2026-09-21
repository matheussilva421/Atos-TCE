"use strict";

/**
 * Mesa shell.
 *
 * The Mesa owns the workflow; this screen reads the loopback API and writes
 * only through the explicit, session-authenticated actions (analisar, baixar,
 * parear). Every document is reached by SQLite id, never by a file path.
 */
import { clampScale, normalizeRotation, renderPdfPage, viewerUrl } from "/pdf-viewer.js";

let pdfjsPromise = null;

async function loadPdfjs() {
  // PDF.js is only fetched when the operator actually opens a document.
  if (!pdfjsPromise) pdfjsPromise = import("/vendor/pdfjs/pdf.mjs");
  return pdfjsPromise;
}
(() => {
  const STATUS_CLASS = {
    PENDENTE: "chip-neutral",
    IDENTIFICADO: "chip-info",
    BAIXANDO: "chip-busy",
    BAIXADO: "chip-info",
    ANALISANDO: "chip-busy",
    REVISAR: "chip-warn",
    PRONTO: "chip-ok",
    PREENCHIDO: "chip-ok",
    "CONCLUÍDO": "chip-ok",
    ERRO: "chip-error",
    BLOQUEADO: "chip-error",
    DIVERGENCIA: "chip-error",
  };

  const STORAGE_CLASS = { HOT: "chip-ok", ARCHIVED: "chip-info", MISSING: "chip-error" };

  const FIELD_LABELS = {
    modalidade: "Modalidade",
    fundamento_legal: "Fundamento legal",
    data_publicacao_doe: "Publicação no DOE",
    cargo: "Cargo",
    matricula: "Matrícula",
    data_nascimento: "Nascimento",
    genero: "Gênero",
  };

  const AREA_COUNTER_LABELS = {
    total: "Processos vistos",
    pending: "Precisam complementar",
    completed: "Já complementados",
    ambiguous: "Ambíguos",
    blocked: "Bloqueados",
    not_found: "Não encontrados",
  };

  const FILL_STATE_LABELS = {
    OPENING: "Abrindo o ato no portal…",
    READING: "Lendo o formulário…",
    PREFLIGHT: "Validando os campos…",
    FILLING: "Preenchendo e relendo…",
    PREENCHIDO: "Ato preenchido. Confira e conclua manualmente no portal.",
    BLOQUEADO: "Preenchimento bloqueado.",
    ERRO: "O preenchimento falhou.",
  };

  async function startFill() {
    const button = document.getElementById("fill-act");
    const status = document.getElementById("fill-status");
    if (!state.selectedId || !button || !status) return;
    button.disabled = true;
    status.textContent = "Solicitando o preenchimento…";
    try {
      const created = await postJson(`/api/v1/processes/${state.selectedId}/fill`, {});
      const deadline = Date.now() + 300000;
      for (;;) {
        await sleep(1000);
        const request = await getJson(`/api/v1/fill-requests/${created.fill_request_id}`);
        status.textContent = FILL_STATE_LABELS[request.state] || request.state;
        if (request.error) status.textContent += ` (${request.error})`;
        if (["PREENCHIDO", "BLOQUEADO", "ERRO"].includes(request.state)) break;
        if (Date.now() > deadline) {
          status.textContent = "O preenchimento não respondeu a tempo. Verifique a extensão.";
          break;
        }
      }
      await selectProcess(state.selectedId);
    } catch (error) {
      status.textContent = `Não foi possível preencher: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  }

  const state = {
    items: [],
    selectedId: null,
    query: "",
    status: "",
    acquisitionRunning: false,
    acquisitionJob: null,
    tab: "dados",
    detail: null,
    viewer: { documentId: null, page: 1, pageCount: 1, scale: 1.5, rotation: 0, rects: [] },
  };

  const numberFormat = new Intl.NumberFormat("pt-BR");

  function element(tag, options = {}, children = []) {
    const node = document.createElement(tag);
    if (options.className) node.className = options.className;
    if (options.text !== undefined) node.textContent = options.text;
    if (options.title) node.title = options.title;
    if (options.attrs) for (const [key, value] of Object.entries(options.attrs)) node.setAttribute(key, value);
    for (const child of children) if (child) node.append(child);
    return node;
  }

  function chip(label, statusKey = "") {
    const className = STATUS_CLASS[statusKey] || "chip-info";
    return element("span", { className: `chip ${className}`, text: label });
  }

  function formatBytes(value) {
    const bytes = Number(value) || 0;
    const units = ["B", "KB", "MB", "GB", "TB"];
    let index = 0;
    let size = bytes;
    while (size >= 1024 && index < units.length - 1) {
      size /= 1024;
      index += 1;
    }
    const digits = index === 0 ? 0 : size >= 10 ? 1 : 2;
    return `${size.toFixed(digits).replace(".", ",")} ${units[index]}`;
  }

  function formatDate(value) {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  }

  async function getJson(path) {
    const response = await fetch(path, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  async function postJson(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload && (payload.detail || payload.error);
      throw new Error(detail ? String(detail) : `${response.status} ${response.statusText}`);
    }
    return payload || {};
  }

  function renderFailures(items) {
    const host = document.getElementById("acquisition-failures");
    host.replaceChildren(
      ...(items || []).map((item) =>
        element("li", {
          text: `${item.process_key || "processo"} — ${item.error || "falha sem detalhe"}`,
        })
      )
    );
  }

  async function refreshAcquisition() {
    const button = document.getElementById("download-pending");
    try {
      const plan = await getJson("/api/v1/acquisition/plan");
      button.textContent =
        plan.total > 0
          ? `Baixar ${numberFormat.format(plan.total)} processos`
          : "Nada a baixar";
      button.disabled = plan.total === 0 || state.acquisitionRunning;
    } catch {
      button.disabled = true;
    }
  }

  /**
   * Show the "retomar" action only while a job is genuinely paused. Resuming
   * continues the same job; it never creates a second one.
   */
  function setResumableJob(jobId) {
    state.acquisitionJob = jobId ?? null;
    document.getElementById("resume-acquisition").hidden = !state.acquisitionJob;
  }

  async function followAcquisitionJob(jobId) {
    const status = document.getElementById("acquisition-status");
    const progress = document.getElementById("acquisition-progress");
    const deadline = Date.now() + 3600000;
    for (;;) {
      await sleep(1000);
      const job = await getJson(`/api/v1/jobs/${jobId}`);
      progress.textContent =
        `${numberFormat.format(job.completed)} de ${numberFormat.format(job.total)} baixados` +
        (job.failed ? ` · ${numberFormat.format(job.failed)} com falha` : "");
      if (job.status === "WAITING_FOR_LOGIN") {
        status.textContent = "Faça login no e-Contas e retome o download.";
        setResumableJob(jobId);
        break;
      }
      if (job.status === "INTERRUPTED") {
        status.textContent = "O download foi interrompido; retome para continuar de onde parou.";
        setResumableJob(jobId);
        break;
      }
      if (job.status === "COMPLETED" || job.status === "COMPLETED_WITH_ERRORS" || job.status === "FAILED") {
        status.textContent =
          job.status === "COMPLETED"
            ? "Download concluído."
            : `Download terminou com ${numberFormat.format(job.failed)} falha(s).`;
        renderFailures(job.failures);
        setResumableJob(null);
        break;
      }
      if (Date.now() > deadline) {
        status.textContent = "O download demorou demais; verifique o e-Contas.";
        setResumableJob(jobId);
        break;
      }
    }
  }

  async function startAcquisition() {
    const button = document.getElementById("download-pending");
    const status = document.getElementById("acquisition-status");
    state.acquisitionRunning = true;
    button.disabled = true;
    renderFailures([]);
    document.getElementById("acquisition-progress").textContent = "";
    status.textContent = "Iniciando o download dos processos pendentes…";
    setResumableJob(null);
    try {
      const created = await postJson("/api/v1/acquisition/jobs", {});
      await followAcquisitionJob(created.job_id);
      await refreshArea();
      await refreshProcesses();
      await refreshStorage();
    } catch (error) {
      status.textContent = `Não foi possível baixar: ${error.message}`;
    } finally {
      state.acquisitionRunning = false;
      await refreshAcquisition();
    }
  }

  async function resumeAcquisition() {
    const jobId = state.acquisitionJob;
    if (!jobId) return;
    const status = document.getElementById("acquisition-status");
    state.acquisitionRunning = true;
    setResumableJob(null);
    status.textContent = "Retomando o download de onde parou…";
    try {
      await postJson(`/api/v1/jobs/${jobId}/resume`, {});
      await followAcquisitionJob(jobId);
      await refreshArea();
      await refreshProcesses();
      await refreshStorage();
    } catch (error) {
      status.textContent = `Não foi possível retomar: ${error.message}`;
      setResumableJob(jobId);
    } finally {
      state.acquisitionRunning = false;
      await refreshAcquisition();
    }
  }

  function sleep(milliseconds) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  }

  function renderArea(payload, { placeholder = false } = {}) {
    const host = document.getElementById("area-counters");
    const counters = payload?.counters || {};
    host.replaceChildren(
      ...Object.entries(AREA_COUNTER_LABELS).map(([key, label]) =>
        element("div", {}, [
          element("dt", { text: label }),
          element("dd", { text: placeholder ? "—" : numberFormat.format(counters[key] ?? 0) }),
        ])
      )
    );
  }

  function clearAreaCounters() {
    renderArea(null, { placeholder: true });
  }

  async function refreshArea() {
    try {
      renderArea(await getJson("/api/v1/area/latest"));
    } catch (error) {
      document.getElementById("area-counters").replaceChildren(
        element("p", { className: "error-note", text: `Falha ao ler a análise: ${error.message}` })
      );
    }
  }

  async function handoffSession() {
    const button = document.getElementById("handoff-session");
    const status = document.getElementById("handoff-status");
    button.disabled = true;
    status.textContent = "Gerando URL de sessão…";
    try {
      const payload = await postJson("/api/v1/session/handoff", {});
      const url = String(payload.url || "");
      if (!url) throw new Error("a Mesa não devolveu uma URL de sessão");
      try {
        await navigator.clipboard.writeText(url);
        status.textContent = "URL copiada. Cole no Chrome QA em até 5 minutos.";
      } catch {
        window.prompt("Copie esta URL para o Chrome QA:", url);
        status.textContent = "URL exibida para cópia manual.";
      }
    } catch (error) {
      status.textContent = `Não foi possível gerar a URL: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  }

  async function analyzeArea() {
    const button = document.getElementById("analyze-area");
    const status = document.getElementById("analyze-status");
    button.disabled = true;
    clearAreaCounters();
    status.textContent = "Solicitando a leitura do portal…";
    try {
      const created = await postJson("/api/v1/area/analyze", {});
      status.textContent = "Analisando a Área Restrita…";
      const deadline = Date.now() + 180000;
      let ticks = 0;
      for (;;) {
        await sleep(1000);
        const command = await getJson(`/api/v1/extension/commands/${created.command_id}`);
        if (command.state === "SUCCEEDED") {
          status.textContent = "Análise concluída.";
          break;
        }
        if (command.state === "FAILED") {
          status.textContent = `Não foi possível analisar: ${command.error || "erro no portal"}`;
          break;
        }
        ticks += 1;
        if (ticks === 4) {
          status.textContent = "Aguardando a extensão (Área Restrita aberta e conectada)…";
        }
        if (Date.now() > deadline) {
          status.textContent = "A análise não respondeu a tempo. Verifique a extensão.";
          break;
        }
      }
      await refreshArea();
      await refreshProcesses();
    } catch (error) {
      status.textContent = `Não foi possível analisar: ${error.message}`;
      await refreshArea();
    } finally {
      button.disabled = false;
    }
  }

  async function analyzeAreaCdp() {
    const button = document.getElementById("analyze-area-cdp");
    const status = document.getElementById("analyze-status");
    button.disabled = true;
    clearAreaCounters();
    status.textContent = "Lendo o portal pelo modo de compatibilidade…";
    try {
      const result = await postJson("/api/v1/area/analyze-cdp", {});
      status.textContent = `Leitura por CDP concluída (${numberFormat.format(result.rows)} processos vistos).`;
      await refreshArea();
      await refreshProcesses();
    } catch (error) {
      status.textContent = `Modo de compatibilidade indisponível: ${error.message}`;
      await refreshArea();
    } finally {
      button.disabled = false;
    }
  }

  function renderHealth(payload) {
    const host = document.getElementById("health-status");
    host.replaceChildren(
      chip(`Mesa conectada · API v${payload.api_version}`, "chip-ok"),
      chip(`Banco schema v${payload.schema_version}`, "chip-info"),
      chip(`${numberFormat.format(payload.process_count)} processos`, "chip-info")
    );
    document.getElementById("summary").textContent = `${numberFormat.format(
      payload.process_count
    )} processos no acervo · banco em ${payload.database}`;
    document.getElementById("footer-note").textContent = `dados em ${payload.data_root}`;
  }

  function renderHealthError(error) {
    document.getElementById("health-status").replaceChildren(
      chip(`Mesa indisponível: ${error.message}`, "chip-error")
    );
  }

  function renderStorage(payload) {
    const host = document.getElementById("storage-summary");
    const archive = payload.archive || {};
    const database = payload.database || {};
    const entries = [
      ["Processos", numberFormat.format(database.processes?.total ?? 0)],
      ["Documentos", numberFormat.format(database.documents?.total ?? 0)],
      ["PDFs únicos (SHA-256)", numberFormat.format(database.documents?.unique_sha256 ?? 0)],
      ["Blobs canônicos", numberFormat.format(archive.blob_count ?? 0)],
      ["Bytes canônicos", formatBytes(archive.blob_bytes)],
      ["Arquivos na árvore de processos", numberFormat.format(archive.process_view_files ?? 0)],
      ["Bytes economizados por dedup", formatBytes(archive.deduplicated_bytes)],
      [
        "Arquivo externo",
        archive.external_root ? "configurado" : "não configurado",
      ],
    ];
    host.replaceChildren(
      ...entries.map(([label, value]) =>
        element("div", {}, [element("dt", { text: label }), element("dd", { text: value })])
      )
    );
  }

  function renderList() {
    const host = document.getElementById("process-list");
    const empty = document.getElementById("process-list-empty");
    host.replaceChildren(
      ...state.items.map((item) => {
        const button = element("button", { attrs: { type: "button" } }, [
          element("span", { className: "process-key", text: item.process_key }),
          element("span", { className: "process-interested", text: item.interested }),
          element("span", { className: "process-docs", text: `${item.document_count} doc.` }),
          chip(item.status, item.status),
        ]);
        button.addEventListener("click", () => selectProcess(item.id));
        const row = element("li", {}, [button]);
        row.setAttribute("aria-selected", String(item.id === state.selectedId));
        return row;
      })
    );
    empty.hidden = state.items.length > 0;
    document.getElementById("process-count").textContent = `${numberFormat.format(
      state.items.length
    )} processo(s) listado(s)`;
  }

  function fieldTable(fields) {
    if (!fields.length) return element("p", { className: "empty", text: "Nenhum campo extraído." });
    const head = element("tr", {}, [
      element("th", { text: "Campo" }),
      element("th", { text: "Valor" }),
      element("th", { text: "Situação" }),
      element("th", { text: "Fonte" }),
    ]);
    const rows = fields.map((field) => {
      const row = element("tr", {}, [
        element("td", { text: FIELD_LABELS[field.field_name] || field.field_name }),
        element("td", { text: field.value ?? "—" }),
        element("td", { text: field.status ?? "—" }),
        element("td", {}, [
          field.document_id
            ? element("button", {
                className: "source-link",
                text: field.page ? `ver fonte (pág. ${field.page})` : "ver fonte",
                attrs: { type: "button" },
              })
            : element("span", { className: "muted", text: "sem evidência" }),
        ]),
      ]);
      const button = row.querySelector("button.source-link");
      if (button) {
        button.addEventListener("click", () => openFieldEvidence(state.selectedId, field.field_name));
      }
      return row;
    });
    return element("table", { className: "grid" }, [element("thead", {}, [head]), element("tbody", {}, rows)]);
  }

  function documentTable(documents) {
    if (!documents.length) return element("p", { className: "empty", text: "Nenhum documento no acervo." });
    const head = element("tr", {}, [
      element("th", { text: "Evento" }),
      element("th", { text: "Título" }),
      element("th", { text: "Classificação" }),
      element("th", { text: "Páginas" }),
      element("th", { text: "Armazenamento" }),
      element("th", { text: "SHA-256" }),
      element("th", { text: "PDF" }),
    ]);
    const rows = documents.map((document) => {
      const row = element("tr", {}, [
        element("td", { text: document.event ?? "—" }),
        element("td", { text: document.title }),
        element("td", { text: document.classification ?? "—" }),
        element("td", { text: String(document.page_count ?? 0) }),
        element("td", {}, [chip(document.storage_state, STORAGE_CLASS[document.storage_state] ? document.storage_state : "")]),
        element("td", { className: "mono", text: `${String(document.sha256).slice(0, 12)}…` }),
        element("td", {}, [
          element("button", {
            className: "source-link",
            text: "abrir no visualizador",
            attrs: { type: "button" },
          }),
        ]),
      ]);
      row
        .querySelector("button.source-link")
        .addEventListener("click", () => openDocument(document.id, 1, []));
      return row;
    });
    return element("table", { className: "grid" }, [element("thead", {}, [head]), element("tbody", {}, rows)]);
  }

  function historyList(events) {
    if (!events.length) return element("p", { className: "empty", text: "Sem histórico registrado." });
    return element(
      "ul",
      { className: "history" },
      events
        .slice()
        .reverse()
        .map((event) =>
          element("li", {}, [
            element("time", { text: formatDate(event.created_at) }),
            element("span", { text: event.event_type }),
            element("span", {
              className: "muted",
              text: Object.keys(event.payload || {}).length ? JSON.stringify(event.payload) : "",
            }),
          ])
        )
    );
  }

  function renderDetail(process) {
    // The tab buttons re-render from this payload; without storing it the tabs
    // only repaint the bar and the documents/history tabs never open.
    state.detail = process;
    const host = document.getElementById("process-detail");
    const badges = element("div", { className: "detail-badges" }, [
      chip(process.status, process.status),
      process.source_scope ? chip(process.source_scope, "") : null,
      process.marker ? chip(process.marker, "") : null,
      chip(`atualizado ${formatDate(process.updated_at)}`, ""),
    ]);
    const tabs = {
      dados: () =>
        element("section", {}, [
          element("h4", { text: `Campos (${process.fields.length})` }),
          fieldTable(process.fields),
        ]),
      documentos: () =>
        element("section", {}, [
          element("h4", { text: `Documentos (${process.documents.length})` }),
          documentTable(process.documents),
        ]),
      historico: () =>
        element("section", {}, [
          element("h4", { text: `Histórico (${process.events.length})` }),
          historyList(process.events),
        ]),
    };
    host.replaceChildren(
      element("h3", { text: `${process.process_key}` }),
      element("p", { className: "detail-sub", text: process.interested }),
      badges,
      fillPanel(process),
      archivePanel(process),
      (tabs[state.tab] || tabs.dados)()
    );
    refreshTabBar();
  }

  /** The fill action exists only for a process the backend marked PRONTO. */
  const ARCHIVE_ELIGIBLE = new Set(["CONCLUÍDO", "PREENCHIDO"]);

  async function runArchiveAction(action, label) {
    const status = document.getElementById("archive-status");
    if (!state.selectedId || !status) return;
    status.textContent = `${label} em andamento…`;
    try {
      const result = await postJson(`/api/v1/processes/${state.selectedId}/${action}`, {});
      const moved = result.archived || result.restored || 0;
      status.textContent = result.ok
        ? `${label} concluída (${numberFormat.format(moved)} documento(s)).`
        : `${label} falhou: ${(result.errors || []).join("; ") || "sem detalhe"}`;
      await selectProcess(state.selectedId);
    } catch (error) {
      status.textContent = `${label} recusada: ${error.message}`;
    }
  }

  /** Archiving is offered only for finished work; MISSING is never "success". */
  function archivePanel(process) {
    const documents = process.documents || [];
    const archived = documents.filter((doc) => doc.storage_state === "ARCHIVED").length;
    const missing = documents.filter((doc) => doc.storage_state === "MISSING").length;
    const panel = element("div", { className: "archive-panel" }, [
      element("button", { className: "ghost", text: "Arquivar processo", attrs: { type: "button", id: "archive-process" } }),
      element("button", { className: "ghost", text: "Restaurar documentos", attrs: { type: "button", id: "restore-process" } }),
      element("span", { className: "muted", attrs: { id: "archive-status" } }),
    ]);
    const buttons = panel.querySelectorAll("button");
    if (ARCHIVE_ELIGIBLE.has(process.status)) {
      buttons[0].addEventListener("click", () => runArchiveAction("archive", "Arquivamento"));
    } else {
      buttons[0].hidden = true;
    }
    if (archived > 0) {
      buttons[1].addEventListener("click", () => runArchiveAction("restore", "Restauração"));
    } else {
      buttons[1].hidden = true;
    }
    if (missing > 0) {
      panel.append(
        element("span", {
          className: "error-note",
          text: `${numberFormat.format(missing)} documento(s) sem cópia local nem externa`,
        })
      );
    }
    return panel;
  }

  function fillPanel(process) {
    const panel = element("div", { className: "fill-panel" }, [
      element("button", {
        className: "primary",
        text: "Preencher ato",
        attrs: { type: "button", id: "fill-act" },
      }),
      element("span", { className: "muted", attrs: { id: "fill-status" } }),
    ]);
    if (process.status !== "PRONTO") {
      panel.hidden = true;
      return panel;
    }
    panel.querySelector("button").addEventListener("click", startFill);
    return panel;
  }

  function refreshTabBar() {
    for (const button of document.querySelectorAll("#detail-tabs button")) {
      button.setAttribute("aria-selected", String(button.dataset.tab === state.tab));
    }
  }

  // ------------------------------------------------------------- PDF viewer

  async function renderViewer() {
    const section = document.getElementById("pdf-viewer");
    const viewer = state.viewer;
    if (!viewer.documentId) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    document.getElementById("viewer-zoom-label").textContent = `${Math.round(viewer.scale * 100)}%`;
    document.getElementById("viewer-page-label").textContent =
      `página ${viewer.page} de ${viewer.pageCount}`;
    try {
      const pdfjs = await loadPdfjs();
      const result = await renderPdfPage({
        pdfjs,
        pdfUrl: viewerUrl(viewer.documentId),
        pageNumber: viewer.page,
        canvas: document.getElementById("viewer-canvas"),
        overlay: document.getElementById("viewer-overlay"),
        workerUrl: "/vendor/pdfjs/pdf.worker.mjs",
        evidence: { rects: viewer.rects },
        scale: viewer.scale,
        rotation: viewer.rotation,
      });
      viewer.pageCount = result.pageCount;
      viewer.page = result.pageNumber;
      viewer.scale = result.scale;
      viewer.rotation = result.rotation;
      document.getElementById("viewer-page-label").textContent =
        `página ${viewer.page} de ${viewer.pageCount}`;
      document.getElementById("viewer-zoom-label").textContent = `${Math.round(viewer.scale * 100)}%`;
    } catch (error) {
      document.getElementById("viewer-caption").textContent =
        `Não foi possível abrir o documento: ${error.message}`;
    }
  }

  async function openDocument(documentId, page = 1, rects = []) {
    const viewer = state.viewer;
    viewer.documentId = Number(documentId);
    viewer.page = Math.max(1, Number(page) || 1);
    viewer.rects = Array.isArray(rects) ? rects : [];
    viewer.scale = 1.5;
    viewer.rotation = 0;
    document.getElementById("viewer-caption").textContent = "";
    await renderViewer();
    document.getElementById("pdf-viewer").scrollIntoView({ block: "nearest" });
  }

  async function openFieldEvidence(processId, fieldName) {
    const caption = document.getElementById("viewer-caption");
    try {
      const evidence = await getJson(
        `/api/v1/processes/${processId}/evidence/${encodeURIComponent(fieldName)}`
      );
      await openDocument(evidence.document_id, evidence.page ?? 1, evidence.rects ?? []);
      caption.textContent = evidence.quote
        ? `Fonte: “${evidence.quote}”${evidence.method ? ` (${evidence.method})` : ""}`
        : "Fonte registrada sem trecho citado.";
    } catch (error) {
      caption.textContent = `Sem fonte registrada para este campo (${error.message}).`;
    }
  }

  function shiftPage(delta) {
    const viewer = state.viewer;
    const next = Math.min(Math.max(1, viewer.page + delta), viewer.pageCount || 1);
    if (next === viewer.page) return;
    viewer.page = next;
    renderViewer();
  }

  async function refreshHealth() {
    try {
      renderHealth(await getJson("/api/v1/health"));
    } catch (error) {
      renderHealthError(error);
    }
  }

  async function refreshStorage() {
    try {
      renderStorage(await getJson("/api/v1/storage"));
    } catch (error) {
      document.getElementById("storage-summary").replaceChildren(
        element("p", { className: "error-note", text: `Falha ao ler o armazenamento: ${error.message}` })
      );
    }
  }

  async function refreshProcesses() {
    const params = new URLSearchParams();
    if (state.query) params.set("q", state.query);
    if (state.status) params.set("status", state.status);
    const suffix = params.toString() ? `?${params}` : "";
    try {
      const payload = await getJson(`/api/v1/processes${suffix}`);
      state.items = payload.items;
      renderList();
    } catch (error) {
      document.getElementById("process-list").replaceChildren(
        element("li", { className: "error-note", text: `Falha ao listar processos: ${error.message}` })
      );
    }
  }

  async function selectProcess(processId) {
    state.selectedId = processId;
    state.detail = null;
    state.viewer = { documentId: null, page: 1, pageCount: 1, scale: 1.5, rotation: 0, rects: [] };
    document.getElementById("pdf-viewer").hidden = true;
    document.getElementById("viewer-caption").textContent = "";
    renderList();
    const host = document.getElementById("process-detail");
    host.replaceChildren(element("p", { className: "empty", text: "Carregando…" }));
    try {
      renderDetail(await getJson(`/api/v1/processes/${processId}`));
    } catch (error) {
      host.replaceChildren(
        element("p", { className: "error-note", text: `Falha ao abrir o processo: ${error.message}` })
      );
    }
  }

  function debounce(callback, delay) {
    let timer = null;
    return (...args) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => callback(...args), delay);
    };
  }

  function init() {
    const search = document.getElementById("process-search");
    search.addEventListener(
      "input",
      debounce(() => {
        state.query = search.value.trim();
        refreshProcesses();
      }, 250)
    );
    document.getElementById("process-status-filter").addEventListener("change", (event) => {
      state.status = event.target.value;
      refreshProcesses();
    });

    document.getElementById("analyze-area").addEventListener("click", analyzeArea);
    document.getElementById("analyze-area-cdp").addEventListener("click", analyzeAreaCdp);
    document.getElementById("download-pending").addEventListener("click", startAcquisition);

    for (const button of document.querySelectorAll("#detail-tabs button")) {
      button.addEventListener("click", () => {
        state.tab = button.dataset.tab || "dados";
        if (state.detail) renderDetail(state.detail);
        else refreshTabBar();
      });
    }

    document.getElementById("viewer-zoom-in").addEventListener("click", () => {
      state.viewer.scale = clampScale(state.viewer.scale + 0.25);
      renderViewer();
    });
    document.getElementById("viewer-zoom-out").addEventListener("click", () => {
      state.viewer.scale = clampScale(state.viewer.scale - 0.25);
      renderViewer();
    });
    document.getElementById("viewer-rotate").addEventListener("click", () => {
      state.viewer.rotation = normalizeRotation(state.viewer.rotation + 90);
      renderViewer();
    });
    document.getElementById("viewer-reset").addEventListener("click", () => {
      state.viewer.scale = 1.5;
      state.viewer.rotation = 0;
      renderViewer();
    });
    document.getElementById("viewer-prev").addEventListener("click", () => shiftPage(-1));
    document.getElementById("viewer-next").addEventListener("click", () => shiftPage(1));
    document.getElementById("viewer-close").addEventListener("click", () => {
      state.viewer.documentId = null;
      document.getElementById("pdf-viewer").hidden = true;
    });
    document.getElementById("handoff-session").addEventListener("click", handoffSession);
    document.getElementById("resume-acquisition").addEventListener("click", resumeAcquisition);

    refreshHealth();
    refreshStorage();
    refreshProcesses();
    refreshArea();
    refreshAcquisition();
    window.setInterval(() => {
      refreshHealth();
      if (!state.acquisitionRunning) refreshAcquisition();
    }, 5000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
