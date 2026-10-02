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
  const IDENTITY_SENTINEL_IDS = Object.freeze([
    "txtNumeroProcesso",
    "txtAnoProcesso",
  ]);

  const GENERATION = new WeakMap();
  const DOCUMENT_NONCES = new WeakMap();

  const FORM_ROOT_IDS = Object.freeze(["complementarAtoForm", "tbcomplementarato"]);

  function queryAll(scope, selector) {
    return typeof scope?.querySelectorAll === "function" ? [...scope.querySelectorAll(selector)] : [];
  }

  function elementsById(scope, id) {
    const matches = scope?.id === id ? [scope] : [];
    matches.push(...queryAll(scope, `#${id}`));
    return matches;
  }

  function structureWithin(root) {
    const number = elementsById(root, IDENTITY_SENTINEL_IDS[0]);
    const year = elementsById(root, IDENTITY_SENTINEL_IDS[1]);
    if (number.length !== 1 || year.length !== 1) return null;

    const fieldControls = {};
    for (const name of FIELD_NAMES) {
      const controls = elementsById(root, FIELD_MAP[name]);
      if (controls.length > 1) return null;
      if (controls.length === 1) fieldControls[name] = controls[0];
    }
    if (Object.keys(fieldControls).length === 0) return null;
    return { root, number: number[0], year: year[0], fieldControls };
  }

  function candidateRoots(documentRef = globalThis.document) {
    const roots = new Set();
    for (const id of FORM_ROOT_IDS) {
      for (const root of elementsById(documentRef, id)) roots.add(root);
    }
    for (const number of elementsById(documentRef, IDENTITY_SENTINEL_IDS[0])) {
      let ancestor = number.parentElement;
      const seen = new Set();
      while (ancestor && !seen.has(ancestor)) {
        seen.add(ancestor);
        const tag = String(ancestor.tagName ?? "").toUpperCase();
        if (tag === "BODY" || tag === "HTML" || tag === "DOCUMENT") break;
        roots.add(ancestor);
        ancestor = ancestor.parentElement;
      }
    }
    return [...roots].filter((root) => structureWithin(root) !== null);
  }

  function containsRoot(ancestor, descendant) {
    let current = descendant?.parentElement ?? null;
    while (current) {
      if (current === ancestor) return true;
      current = current.parentElement;
    }
    return false;
  }

  function mostSpecificRoots(candidates) {
    return candidates.filter(
      (candidate) =>
        !candidates.some(
          (other) => other.root !== candidate.root && containsRoot(candidate.root, other.root)
        )
    );
  }

  function hasIdentityAnchors(documentRef = globalThis.document) {
    return candidateRoots(documentRef).length > 0;
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

  /** A candidate hidden behind a closed frame, hidden ancestor or zero rect is absent. */
  function isVisibleRoot(documentRef, root) {
    try {
      if (!documentRef?.defaultView || !root) return false;
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
      return inspectVisibleAncestors(root, documentWindow, seenElements, true);
    } catch {
      return false;
    }
  }

  function isVisibleForm(documentRef = globalThis.document) {
    return candidateRoots(documentRef).some((root) => isVisibleRoot(documentRef, root));
  }

  function readProcess(scope) {
    const number = elementsById(scope, IDENTITY_SENTINEL_IDS[0]);
    const year = elementsById(scope, IDENTITY_SENTINEL_IDS[1]);
    if (number.length !== 1 || year.length !== 1) return { number: "", year: "", key: null };
    const numberValue = String(number[0]?.value ?? "").trim();
    const yearValue = String(year[0]?.value ?? "").trim();
    return {
      number: numberValue,
      year: yearValue,
      key: numberValue && yearValue ? `${numberValue}/${yearValue}` : null,
    };
  }

  function readInterested(scope) {
    const isDocument = scope?.nodeType === 9 || String(scope?.tagName ?? "").toUpperCase() === "DOCUMENT";
    const documentRef = isDocument ? scope : scope?.ownerDocument ?? globalThis.document;
    const resolution = interestedSelection(documentRef, scope);
    const selected = resolution.selected;
    if (selected.length !== 1 || !selected[0].normalized) return null;
    return { original: selected[0].original, normalized: selected[0].normalized };
  }

  function interestedSelection(documentRef, scope) {
    const snapshot = globalThis.TCEAreaSnapshot;
    if (
      typeof snapshot?.interestedTablesInScope !== "function" ||
      typeof snapshot?.selectedInterestedInTable !== "function"
    ) {
      return { ambiguous: false, selected: [] };
    }
    const visibleTables = snapshot
      .interestedTablesInScope(scope)
      .filter((table) => isVisibleRoot(documentRef, table));
    if (visibleTables.length > 1) return { ambiguous: true, selected: [] };
    if (visibleTables.length === 0) return { ambiguous: false, selected: [] };
    return {
      ambiguous: false,
      selected:
        snapshot.selectedInterestedInTable(
          visibleTables[0],
          (element) => isVisibleRoot(documentRef, element)
        ) ?? [],
    };
  }

  function readOptions(control) {
    const options = control?.options ? [...control.options] : [...(control?.querySelectorAll?.("option") ?? [])];
    return options.map((option) => ({
      value: String(option.value ?? ""),
      label: String(option.label || option.textContent || "").trim(),
      disabled: option.disabled === true || option.parentElement?.disabled === true,
    }));
  }

  function formFromCandidate(documentRef, candidate, selectedInterested) {
    if (!isVisibleRoot(documentRef, candidate.root)) return null;
    const documentNonce = nonceForDocument(documentRef);
    if (!documentNonce) return null;
    const process = readProcess(candidate.root);
    const interested = {
      original: selectedInterested.original,
      normalized: selectedInterested.normalized,
    };
    if (!process.key || !interested.normalized) return null;
    const identity = {
      processKey: process.key,
      interestedNormalized: interested.normalized,
    };

    const fields = {};
    const options = {};
    for (const name of FIELD_NAMES) {
      const control = candidate.fieldControls[name];
      if (!control) continue;
      let list;
      try {
        list = readOptions(control);
        fields[name] = {
          value: String(control.value ?? ""),
          disabled: control.disabled === true,
          readOnly: control.readOnly === true,
          readable: true,
          options: list,
        };
      } catch {
        fields[name] = {
          value: "",
          disabled: false,
          readOnly: false,
          readable: false,
          options: [],
        };
        continue;
      }
      if (list.length > 0) options[name] = list;
    }
    return {
      documentNonce,
      identity,
      generation: nextGeneration(documentRef, identity, fields),
      process,
      interested,
      fields,
      options,
    };
  }

  function resolveFormCandidate(documentRef = globalThis.document) {
    const valid = [];
    for (const root of candidateRoots(documentRef)) {
      const structure = structureWithin(root);
      if (!structure || !isVisibleRoot(documentRef, root)) continue;
      const selection = interestedSelection(documentRef, root);
      if (selection.ambiguous) {
        return {
          ok: false,
          code: "FORM_AMBIGUOUS",
          error: "mais de uma tabela visível de interessados corresponde ao formulário",
        };
      }
      const selected = selection.selected;
      if (selected.length > 1) {
        return {
          ok: false,
          code: "FORM_AMBIGUOUS",
          error: "mais de um interessado está marcado no formulário visível",
        };
      }
      if (selected.length !== 1 || !selected[0].normalized) continue;
      const form = formFromCandidate(documentRef, structure, selected[0]);
      if (form) valid.push({ root, structure, form });
    }
    const selectedRoots = mostSpecificRoots(valid);
    if (selectedRoots.length > 1) {
      return {
        ok: false,
        code: "FORM_AMBIGUOUS",
        error: "mais de um formulário visível corresponde à estrutura do ato",
      };
    }
    if (selectedRoots.length === 0) {
      return { ok: false, code: "FORM_NOT_AVAILABLE", error: "o formulário do ato ainda não está disponível" };
    }
    return { ok: true, candidate: selectedRoots[0] };
  }

  function readFormResult(documentRef = globalThis.document) {
    const outcome = resolveFormCandidate(documentRef);
    return outcome.ok === true ? { ok: true, form: outcome.candidate.form } : outcome;
  }

  function findFieldControl(
    documentRef,
    fieldName,
    expectedIdentity,
    expectedGeneration,
    expectedDocumentNonce = null,
  ) {
    if (!Object.hasOwn(FIELD_MAP, fieldName) || !Number.isInteger(expectedGeneration) || expectedGeneration < 1) {
      return null;
    }
    const outcome = resolveFormCandidate(documentRef);
    if (outcome.ok !== true) return null;

    const { candidate } = outcome;
    const processKey = String(expectedIdentity?.processKey ?? "").trim();
    const normalize = globalThis.TCEAreaSnapshot?.normalizeInterested;
    const interested = typeof normalize === "function"
      ? normalize(expectedIdentity?.interestedNormalized)
      : String(expectedIdentity?.interestedNormalized ?? "").trim().toLowerCase();
    if (
      !processKey ||
      !interested ||
      candidate.form.identity.processKey !== processKey ||
      candidate.form.identity.interestedNormalized !== interested ||
      candidate.form.generation !== expectedGeneration ||
      (expectedDocumentNonce !== null && candidate.form.documentNonce !== expectedDocumentNonce)
    ) {
      return null;
    }
    return candidate.structure.fieldControls[fieldName] ?? null;
  }

  function readForm(documentRef = globalThis.document) {
    const outcome = readFormResult(documentRef);
    return outcome.ok === true ? outcome.form : null;
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

  function nonceForDocument(documentRef) {
    if (!documentRef || (typeof documentRef !== "object" && typeof documentRef !== "function")) {
      return null;
    }
    const existing = DOCUMENT_NONCES.get(documentRef);
    if (existing) return existing;
    const cryptoRef = globalThis.crypto;
    if (typeof cryptoRef?.getRandomValues !== "function") return null;
    const bytes = new Uint8Array(16);
    cryptoRef.getRandomValues(bytes);
    const nonce = [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
    DOCUMENT_NONCES.set(documentRef, nonce);
    return nonce;
  }

  globalThis.TCEFormReader = Object.freeze({
    readForm,
    readFormResult,
    findFieldControl,
    isVisibleForm,
    hasIdentityAnchors,
    readProcess,
    readInterested,
    readOptions,
    FIELD_MAP,
    FIELD_NAMES,
    IDENTITY_SENTINEL_IDS,
  });

  const runtime = globalThis.chrome?.runtime;
  if (runtime?.onMessage?.addListener) {
    runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (!message || message.type !== "READ_FORM") return undefined;
      try {
        sendResponse(readFormResult(globalThis.document));
      } catch (error) {
        sendResponse({
          ok: false,
          code: "FORM_NOT_AVAILABLE",
          error: String(error?.message ?? "o formulário do ato ainda não está disponível"),
        });
      }
      return true;
    });
  }
})();
