"use strict";

/**
 * Read-only Mesa shell (M1).
 *
 * The Mesa owns the workflow; this screen only reads. It performs no action
 * beyond GET requests against the loopback API, so the M1 milestone cannot
 * change any data from the browser.
 */
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

  const state = { items: [], selectedId: null, query: "", status: "", acquisitionRunning: false };

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

  async function startAcquisition() {
    const button = document.getElementById("download-pending");
    const status = document.getElementById("acquisition-status");
    const progress = document.getElementById("acquisition-progress");
    state.acquisitionRunning = true;
    button.disabled = true;
    renderFailures([]);
    progress.textContent = "";
    status.textContent = "Iniciando o download dos processos pendentes…";
    try {
      const created = await postJson("/api/v1/acquisition/jobs", {});
      const deadline = Date.now() + 3600000;
      for (;;) {
        await sleep(1000);
        const job = await getJson(`/api/v1/jobs/${created.job_id}`);
        progress.textContent =
          `${numberFormat.format(job.completed)} de ${numberFormat.format(job.total)} baixados` +
          (job.failed ? ` · ${numberFormat.format(job.failed)} com falha` : "");
        if (job.status === "WAITING_FOR_LOGIN") {
          status.textContent = "Faça login no e-Contas para continuar.";
          break;
        }
        if (job.status === "COMPLETED" || job.status === "COMPLETED_WITH_ERRORS" || job.status === "FAILED") {
          status.textContent =
            job.status === "COMPLETED"
              ? "Download concluído."
              : `Download terminou com ${numberFormat.format(job.failed)} falha(s).`;
          renderFailures(job.failures);
          break;
        }
        if (Date.now() > deadline) {
          status.textContent = "O download demorou demais; verifique o e-Contas.";
          break;
        }
      }
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

  function sleep(milliseconds) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  }

  function renderArea(payload) {
    const host = document.getElementById("area-counters");
    const counters = payload.counters || {};
    host.replaceChildren(
      ...Object.entries(AREA_COUNTER_LABELS).map(([key, label]) =>
        element("div", {}, [
          element("dt", { text: label }),
          element("dd", { text: numberFormat.format(counters[key] ?? 0) }),
        ])
      )
    );
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

  async function refreshPairing() {
    const section = document.getElementById("pairing");
    try {
      const payload = await getJson("/api/v1/bridge/pairing");
      if (payload.paired) {
        section.hidden = true;
        return;
      }
      section.hidden = false;
      document.getElementById("pairing-code").textContent = payload.code || "expirado — renove";
    } catch {
      // Without a session yet, the pairing panel simply stays hidden.
      section.hidden = true;
    }
  }

  async function renewPairing() {
    try {
      await postJson("/api/v1/bridge/pairing/renew", {});
    } finally {
      await refreshPairing();
    }
  }

  async function analyzeArea() {
    const button = document.getElementById("analyze-area");
    const status = document.getElementById("analyze-status");
    button.disabled = true;
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
          status.textContent = "Aguardando a extensão (Área Restrita aberta e pareada)…";
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
    } finally {
      button.disabled = false;
    }
  }

  async function analyzeAreaCdp() {
    const button = document.getElementById("analyze-area-cdp");
    const status = document.getElementById("analyze-status");
    button.disabled = true;
    status.textContent = "Lendo o portal pelo modo de compatibilidade…";
    try {
      const result = await postJson("/api/v1/area/analyze-cdp", {});
      status.textContent = `Leitura por CDP concluída (${numberFormat.format(result.rows)} processos vistos).`;
      await refreshArea();
      await refreshProcesses();
    } catch (error) {
      status.textContent = `Modo de compatibilidade indisponível: ${error.message}`;
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
      element("th", { text: "Página" }),
      element("th", { text: "Fonte" }),
    ]);
    const rows = fields.map((field) =>
      element("tr", {}, [
        element("td", { text: FIELD_LABELS[field.field_name] || field.field_name }),
        element("td", { text: field.value ?? "—" }),
        element("td", { text: field.status ?? "—" }),
        element("td", { text: field.page ? String(field.page) : "—" }),
        element("td", {}, [
          field.document_id
            ? element("a", {
                text: "abrir PDF",
                attrs: { href: `/api/v1/documents/${field.document_id}/pdf`, target: "_blank", rel: "noreferrer" },
              })
            : element("span", { className: "muted", text: "sem evidência" }),
        ]),
      ])
    );
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
    const rows = documents.map((document) =>
      element("tr", {}, [
        element("td", { text: document.event ?? "—" }),
        element("td", { text: document.title }),
        element("td", { text: document.classification ?? "—" }),
        element("td", { text: String(document.page_count ?? 0) }),
        element("td", {}, [chip(document.storage_state, STORAGE_CLASS[document.storage_state] ? document.storage_state : "")]),
        element("td", { className: "mono", text: `${String(document.sha256).slice(0, 12)}…` }),
        element("td", {}, [
          element("a", {
            text: "abrir",
            attrs: { href: `/api/v1/documents/${document.id}/pdf`, target: "_blank", rel: "noreferrer" },
          }),
        ]),
      ])
    );
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
    const host = document.getElementById("process-detail");
    const badges = element("div", { className: "detail-badges" }, [
      chip(process.status, process.status),
      process.source_scope ? chip(process.source_scope, "") : null,
      process.marker ? chip(process.marker, "") : null,
      chip(`atualizado ${formatDate(process.updated_at)}`, ""),
    ]);
    host.replaceChildren(
      element("h3", { text: `${process.process_key}` }),
      element("p", { className: "detail-sub", text: process.interested }),
      badges,
      element("section", {}, [
        element("h4", { text: `Campos (${process.fields.length})` }),
        fieldTable(process.fields),
      ]),
      element("section", {}, [
        element("h4", { text: `Documentos (${process.documents.length})` }),
        documentTable(process.documents),
      ]),
      element("section", {}, [
        element("h4", { text: `Histórico (${process.events.length})` }),
        historyList(process.events),
      ])
    );
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
    document.getElementById("renew-pairing").addEventListener("click", renewPairing);

    refreshHealth();
    refreshStorage();
    refreshProcesses();
    refreshArea();
    refreshPairing();
    refreshAcquisition();
    window.setInterval(() => {
      refreshHealth();
      refreshPairing();
      if (!state.acquisitionRunning) refreshAcquisition();
    }, 5000);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
