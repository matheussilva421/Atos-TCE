/**
 * Read-only act form reader.
 *
 * Ported from the proven content/form-detector.js: the same field map, the same
 * visibility rule (nested frames, hidden ancestors, zero-size roots) and the
 * same identity resolution through the process number/year and the selected
 * interested person. It only reads; writing lives in fill-form.js and is never
 * reachable from here.
 */

(() => {
  "use strict";

  const FIELD_MAP = Object.freeze({
    modalidade: "txtModalidade",
    fundamento_legal: "txtFundamentoLegal",
    data_publicacao_doe: "txtDataDOE",
    cargo: "txtCargo",
    matricula: "txtMatricula",
    data_nascimento: "txtDataNascimento",
    genero: "txtGenero",
  });

  const FIELD_NAMES = Object.freeze(Object.keys(FIELD_MAP));
  const SENTINEL_IDS = Object.freeze([
    "txtNumeroProcesso",
    "txtAnoProcesso",
    ...FIELD_NAMES.map((field) => FIELD_MAP[field]),
  ]);

  const GENERATION = new WeakMap();

  function normalize(value) {
    const api = globalThis.TCEAreaSnapshot;
    return api ? api.normalizeInterested(value) : "";
  }

  function getById(documentRef, id) {
    return typeof documentRef?.getElementById === "function" ? documentRef.getElementById(id) : null;
  }

  function textFrom(element) {
    return typeof element?.textContent === "string"
      ? element.textContent.replace(/\s+/gu, " ").trim()
      : "";
  }

  function hasCompleteForm(documentRef = globalThis.document) {
    return SENTINEL_IDS.every((id) => Boolean(getById(documentRef, id)));
  }

  function computedStyleValue(windowRef, element, property) {
    const ownerWindow = element?.ownerDocument?.defaultView ?? windowRef;
    const computed = ownerWindow?.getComputedStyle?.(element);
    return String(computed?.[property] ?? element?.style?.[property] ?? "").trim().toLowerCase();
  }

  function inspectVisibleAncestors(root, windowRef, seenElements, checkRootRect = false) {
    let element = root;
    let isRoot = true;
    while (element) {
      if (!seenElements.has(element)) {
        seenElements.add(element);
        const isDocumentNode = element.nodeType === 9 || element.tagName === "DOCUMENT";
        if (!isDocumentNode) {
          if (element.hidden === true || element.getAttribute?.("aria-hidden") === "true") return false;
          const hiddenByStyle = ["display", "visibility", "opacity"].some((property) => {
            const value = computedStyleValue(windowRef, element, property);
            if (property === "display") return value === "none";
            if (property === "visibility") return ["hidden", "collapse"].includes(value);
            return value === "0";
          });
          if (hiddenByStyle) return false;
          if (checkRootRect && isRoot) {
            const rect = element.getBoundingClientRect?.();
            if (rect && (rect.width <= 0 || rect.height <= 0)) return false;
            const clientRects = element.getClientRects?.();
            if (clientRects && clientRects.length === 0) return false;
          }
        }
      }
      element = element.parentElement;
      isRoot = false;
    }
    return true;
  }

  /** A form hidden behind a closed frame, a hidden ancestor or a zero rect is absent. */
  function isVisibleForm(documentRef = globalThis.document) {
    try {
      if (!documentRef?.defaultView) return false;
      const documentWindow = documentRef.defaultView;
      const seenWindows = new Set();
      const seenElements = new Set();
      let currentWindow = documentWindow;
      while (currentWindow) {
        if (seenWindows.has(currentWindow)) return false;
        seenWindows.add(currentWindow);
        const frameElement = currentWindow.frameElement ?? null;
        const parentWindow = currentWindow.parent;
        if (!frameElement && parentWindow && parentWindow !== currentWindow) return false;
        if (frameElement && !inspectVisibleAncestors(frameElement, parentWindow ?? currentWindow, seenElements, true)) {
          return false;
        }
        if (parentWindow === undefined || parentWindow === null || parentWindow === currentWindow) break;
        currentWindow = parentWindow;
      }
      const formElement =
        getById(documentRef, "complementarAtoForm") ??
        getById(documentRef, SENTINEL_IDS[0])?.closest?.("form") ??
        null;
      return inspectVisibleAncestors(formElement, documentWindow, seenElements);
    } catch {
      return false;
    }
  }

  function selectedRadio(documentRef) {
    if (typeof documentRef?.querySelectorAll !== "function") return null;
    const selected = [...documentRef.querySelectorAll('input[type="radio"]')].filter(
      (radio) => radio.checked === true
    );
    return selected.length === 1 ? selected[0] : null;
  }

  function selectedInterestedName(documentRef) {
    const radio = selectedRadio(documentRef);
    if (!radio) return "";
    for (const attribute of ["data-interested-name", "data-interessado", "aria-label"]) {
      const value = radio.getAttribute?.(attribute);
      if (typeof value === "string" && value.trim()) return value.trim();
    }
    const labelText = textFrom(radio.labels?.[0]);
    if (labelText) return labelText;
    const row = radio.closest?.("tr");
    const namedCell = row?.querySelector?.(".interested-name");
    if (textFrom(namedCell)) return textFrom(namedCell);
    // The legacy portal has no semantic marker on its name cell: resolve the
    // column by its header, never by the whole row or by the radio value.
    const cellsOf = (element) =>
      [...(element?.children ?? [])].filter((cell) =>
        ["TD", "TH"].includes(String(cell.tagName).toUpperCase())
      );
    const table = row?.closest?.("table");
    const cells = cellsOf(row);
    const headerRows = [...(table?.querySelectorAll?.("tr") ?? [])].filter(
      (candidate) => candidate.closest?.("table") === table
    );
    for (const header of headerRows) {
      if (header === row) break;
      const titles = cellsOf(header).map((cell) => normalize(textFrom(cell)));
      const indexes = titles.flatMap((title, index) => (title === "nome" ? [index] : []));
      if (indexes.length === 1 && titles.length === cells.length) {
        return textFrom(cells[indexes[0]]);
      }
    }
    return "";
  }

  function readProcess(documentRef) {
    const number = String(getById(documentRef, "txtNumeroProcesso")?.value ?? "").trim();
    const year = String(getById(documentRef, "txtAnoProcesso")?.value ?? "").trim();
    return { number, year, key: number && year ? `${number}/${year}` : null };
  }

  function readInterested(documentRef) {
    const original = selectedInterestedName(documentRef);
    return original ? { original, normalized: normalize(original) } : null;
  }

  function readOptions(control) {
    const options = control?.options ? [...control.options] : [...(control?.querySelectorAll?.("option") ?? [])];
    return options.map((option) => ({
      value: String(option.value ?? ""),
      label: String(option.label || option.textContent || "").trim(),
    }));
  }

  function readIdentity(documentRef) {
    if (!hasCompleteForm(documentRef)) return null;
    const process = readProcess(documentRef);
    const interested = readInterested(documentRef);
    if (!process.key || !interested?.normalized) return null;
    return { processKey: process.key, interestedNormalized: interested.normalized };
  }

  function nextGeneration(documentRef, identity, fields) {
    const state = GENERATION.get(documentRef) ?? { generation: 0, fingerprint: null };
    const current = JSON.stringify([identity.processKey, identity.interestedNormalized, fields]);
    if (state.fingerprint !== current) {
      state.fingerprint = current;
      state.generation += 1;
    }
    GENERATION.set(documentRef, state);
    return state.generation;
  }

  /**
   * Return the sanitized form state, or ``null`` while the form is absent.
   * ``null`` is the answer for a late or hidden form: the caller retries.
   */
  function readForm(documentRef = globalThis.document) {
    if (!isVisibleForm(documentRef) || !hasCompleteForm(documentRef)) return null;
    const identity = readIdentity(documentRef);
    if (!identity) return null;
    const fields = {};
    const options = {};
    for (const name of FIELD_NAMES) {
      const control = getById(documentRef, FIELD_MAP[name]);
      const list = readOptions(control);
      fields[name] = {
        value: String(control?.value ?? ""),
        disabled: control?.disabled === true,
        readOnly: control?.readOnly === true,
        options: list,
      };
      if (list.length > 0) options[name] = list;
    }
    return {
      identity,
      generation: nextGeneration(documentRef, identity, fields),
      process: readProcess(documentRef),
      interested: readInterested(documentRef),
      fields,
      options,
    };
  }

  globalThis.TCEFormReader = Object.freeze({
    readForm,
    isVisibleForm,
    hasCompleteForm,
    readProcess,
    readInterested,
    readOptions,
    FIELD_MAP,
    FIELD_NAMES,
    SENTINEL_IDS,
  });

  const runtime = globalThis.chrome?.runtime;
  if (runtime?.onMessage?.addListener) {
    runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (!message || message.type !== "READ_FORM") return undefined;
      try {
        const form = readForm(globalThis.document);
        sendResponse(
          form ? { ok: true, form } : { ok: false, error: "o formulário do ato ainda não está disponível" }
        );
      } catch (error) {
        sendResponse({ ok: false, error: String(error?.message ?? error) });
      }
      return true;
    });
  }
})();
