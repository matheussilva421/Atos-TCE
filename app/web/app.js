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

  const state = { items: [], selectedId: null, query: "", status: "" };

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

    refreshHealth();
    refreshStorage();
    refreshProcesses();
    window.setInterval(refreshHealth, 5000);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
