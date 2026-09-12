const ALLOWED_ACTIONS = new Set(["next_page", "open_act", "select_interested", "return_list", "filter_marker"]);
const NAVIGATION_TIMEOUT_MS = 30_000;
const DOCUMENT_STATE = new WeakMap();

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function textOf(value) {
  return typeof value?.textContent === "string"
    ? value.textContent.replace(/\s+/gu, " ").trim()
    : "";
}

function normalizeInterested(value) {
  return typeof value === "string"
    ? value.normalize("NFKD").replace(/\p{M}+/gu, "").toLowerCase().replace(/\s+/gu, " ").trim()
    : "";
}

function getAttribute(element, name) {
  const value = element?.getAttribute?.(name);
  return typeof value === "string" ? value : "";
}

function getDatasetValue(documentRef, name) {
  const candidates = [
    documentRef?.documentElement,
    documentRef?.body,
    documentRef,
  ];
  for (const candidate of candidates) {
    const value = candidate?.dataset?.[name] ?? getAttribute(candidate, `data-${name.replace(/[A-Z]/gu, (letter) => `-${letter.toLowerCase()}`)}`);
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function sourceScopeFromDocument(documentRef) {
  const explicit = getDatasetValue(documentRef, "sourceScope")
    || getAttribute(documentRef, "data-source-scope");
  if (explicit === "sector_finalistic" || explicit === "my_processes") return explicit;
  let href = "";
  try {
    href = String(documentRef?.defaultView?.location?.href ?? "").toLowerCase();
  } catch {
    href = "";
  }
  if (/meusprocessos(?:eletronicos)?\.asp/iu.test(href)) return "my_processes";
  if (/processonosetor\.asp/iu.test(href)) return "sector_finalistic";
  return null;
}

function queryAll(documentRef, selector) {
  return typeof documentRef?.querySelectorAll === "function"
    ? [...documentRef.querySelectorAll(selector)]
    : [];
}

function queryOne(documentRef, selector) {
  return typeof documentRef?.querySelector === "function"
    ? documentRef.querySelector(selector)
    : queryAll(documentRef, selector)[0] ?? null;
}

function byId(documentRef, id) {
  return typeof documentRef?.getElementById === "function" ? documentRef.getElementById(id) : null;
}

function controlLabel(control) {
  return [
    textOf(control),
    getAttribute(control, "aria-label"),
    getAttribute(control, "title"),
    getAttribute(control, "value"),
    typeof control?.value === "string" ? control.value : "",
    ...queryAll(control, "img").flatMap((image) => [getAttribute(image, "alt"), getAttribute(image, "title")]),
  ].filter(Boolean).join(" ");
}

function markerSelect(documentRef) {
  return queryAll(documentRef, "select").find((select) => {
    const metadata = [
      getAttribute(select, "id"),
      getAttribute(select, "name"),
      getAttribute(select, "aria-label"),
      getAttribute(select, "data-field"),
    ].join(" ");
    if (normalizeInterested(metadata).includes("marcador")) return true;
    const label = getAttribute(select, "id");
    if (label && queryAll(documentRef, "label").some((candidate) => (
      getAttribute(candidate, "for") === label && normalizeInterested(textOf(candidate)).includes("marcador")
    ))) return true;
    const row = select.closest?.("tr") ?? null;
    return normalizeInterested(textOf(row)).includes("marcador");
  }) ?? null;
}

function selectedOption(select) {
  const options = select?.options
    ? [...select.options]
    : queryAll(select, "option");
  return options.find((option) => option.selected === true)
    || options.find((option) => getAttribute(option, "selected") !== "")
    || options.find((option) => String(option.value ?? "") === String(select?.value ?? ""))
    || null;
}

function observedMarker(documentRef) {
  const select = markerSelect(documentRef);
  const option = selectedOption(select);
  if (!select || !option) return null;
  const label = textOf(option);
  const normalized = normalizeInterested(label);
  if (!label || ["todos", "todos os marcadores", "selecione", "selecione um marcador"].includes(normalized)) return null;
  return {
    label,
    value: typeof option.value === "string" && option.value ? option.value : null,
  };
}

function markerFilterControls(documentRef) {
  const select = markerSelect(documentRef);
  if (!select) return null;
  const scopes = [select.closest?.("form"), select.closest?.("tr"), select.parentElement, documentRef].filter(Boolean);
  for (const scope of scopes) {
    const submit = queryAll(scope, "button, input, a").find((control) => {
      const label = normalizeInterested(controlLabel(control));
      return label === "consultar" || label.startsWith("consultar ");
    });
    if (submit) return { select, submit };
  }
  // Area Restrita keeps the filter in the process-list frame but renders its
  // action bar in a sibling botoesNOVO.asp frame.
  const topWindow = topWindowFor(documentRef);
  // window.frames is array-like and has no Symbol.iterator; iterate by index.
  const frameList = topWindow?.frames;
  for (let index = 0; index < (frameList?.length ?? 0); index += 1) {
    try {
      const sibling = frameList[index]?.document;
      if (!sibling || sibling === documentRef) continue;
      const siblingUrl = String(sibling.defaultView?.location?.href ?? "").toLowerCase();
      if (!siblingUrl.includes("botoesnovo.asp") || !siblingUrl.includes("processonosetor")) continue;
      const submit = queryAll(sibling, "button, input, a").find((control) => {
        const label = normalizeInterested(controlLabel(control));
        return label === "consultar" || label.startsWith("consultar ");
      });
      if (submit) return { select, submit };
    } catch {
      // Ignore detached or inaccessible sibling frames.
    }
  }
  return { select, submit: null };
}

function isComplementActControl(control) {
  const label = normalizeInterested(controlLabel(control));
  if (label.includes("complementar ato")) return true;
  const action = getAttribute(control, "data-action");
  if (action === "open-act" || action === "open_act") return true;
  const signal = [getAttribute(control, "href"), getAttribute(control, "onclick")].join(" ").toLowerCase();
  return signal.includes("complementarato")
    && (signal.includes("addtabsinformacao") || getAttribute(control, "href").toLowerCase().includes("complementarato"));
}

function opensRestrictedComplementTab(control) {
  const signal = [
    getAttribute(control, "onclick"),
    getAttribute(control, "href"),
  ].join(" ").toLowerCase();
  return signal.includes("addtabsinformacao") || signal.includes("complementarato.asp");
}

function markerOption(select, requestedMarker) {
  const expected = normalizeInterested(requestedMarker);
  const options = select?.options
    ? [...select.options]
    : queryAll(select, "option");
  return options.find((option) => normalizeInterested(textOf(option)) === expected) ?? null;
}

function dispatchControlEvents(documentRef, control) {
  if (typeof control?.dispatchEvent !== "function") return;
  const EventConstructor = documentRef?.defaultView?.Event ?? globalThis.Event;
  if (typeof EventConstructor !== "function") return;
  for (const type of ["input", "change"]) control.dispatchEvent(new EventConstructor(type, { bubbles: true }));
}

function uniqueByIdentity(identities) {
  const seen = new Set();
  return identities.filter((identity) => {
    const key = `${identity.processKey ?? ""}\u0000${identity.interestedNormalized ?? ""}\u0000${identity.portalActId ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function hasCanonicalIdentity(identity) {
  return Boolean(identity?.processKey && identity?.interestedNormalized);
}

function processKeyFromText(value) {
  const match = String(value ?? "").match(/([A-Za-z0-9][A-Za-z0-9._-]*\/\d{4})/u);
  return match?.[1] ?? "";
}

function processKeyFromDocument(documentRef) {
  const explicit = getDatasetValue(documentRef, "processKey")
    || getAttribute(documentRef, "data-process-key");
  if (explicit) return explicit;
  const number = String(byId(documentRef, "txtNumeroProcesso")?.value ?? "").trim();
  const year = String(byId(documentRef, "txtAnoProcesso")?.value ?? "").trim();
  return number && year ? `${number}/${year}` : "";
}

function rowCells(row) {
  return queryAll(row, "td").length > 0 ? queryAll(row, "td") : queryAll(row, "th");
}

function interestedColumnIndex(row) {
  const table = row?.closest?.("table") ?? null;
  if (!table) return -1;
  const headerRows = queryAll(table, "thead tr").filter((candidate) => !queryOne(candidate, 'input[type="radio"]'));
  const candidates = headerRows.length > 0
    ? headerRows
    : queryAll(table, "tr").filter((candidate) => (
      !queryOne(candidate, 'input[type="radio"]')
      && normalizeInterested(textOf(candidate)).includes("interessado")
    ));
  for (const headerRow of candidates) {
    const headers = rowCells(headerRow);
    const index = headers.findIndex((header) => normalizeInterested(textOf(header)) === "interessado");
    if (index >= 0) return index;
  }
  return -1;
}

function interestedTextFromRow(row, radio = null) {
  for (const candidate of [
    getAttribute(radio, "data-interested-name"),
    getAttribute(radio, "data-interessado"),
    getAttribute(radio, "aria-label"),
    textOf(radio?.labels?.[0]),
    textOf(queryOne(row, ".interested-name")),
  ]) {
    if (candidate) return candidate;
  }
  const cells = rowCells(row);
  const headedIndex = interestedColumnIndex(row);
  if (headedIndex >= 0 && cells[headedIndex]) return textOf(cells[headedIndex]);
  const dataIndex = cells.findIndex((cell) => (
    [getAttribute(cell, "data-field"), getAttribute(cell, "data-column")]
      .some((value) => normalizeInterested(value) === "interessado")
  ));
  if (dataIndex >= 0) return textOf(cells[dataIndex]);
  if (radio) {
    const ignored = new Set(["interessado", "responsavel", "relator", "procurador"]);
    const personCell = cells
      .map((cell) => textOf(cell))
      .find((value) => value
        && !ignored.has(normalizeInterested(value))
        && !/^\d[\d./ -]*$/u.test(value));
    return personCell ?? "";
  }
  if (cells.length >= 2) return textOf(cells[1]);
  return "";
}

function portalActIdFromRow(row, control = null) {
  return getAttribute(row, "data-portal-act-id")
    || getAttribute(row, "data-act-id")
    || getAttribute(control, "data-portal-act-id")
    || getAttribute(control, "data-act-id")
    || null;
}

function identityFromRow(row, { radio = null, processKey = "" } = {}) {
  const resolvedProcessKey = processKey
    || getAttribute(row, "data-process-key")
    || getAttribute(row, "data-process")
    || processKeyFromText(textOf(row));
  const interestedOriginal = interestedTextFromRow(row, radio);
  const interestedNormalized = normalizeInterested(interestedOriginal);
  return {
    processKey: resolvedProcessKey || null,
    interestedOriginal,
    interestedNormalized: interestedNormalized || null,
    portalActId: portalActIdFromRow(row, radio),
    pending: !resolvedProcessKey || !interestedNormalized,
    ...(radio ? { selected: radio.checked === true } : {}),
  };
}

function listRows(documentRef) {
  const table = byId(documentRef, "tbproc01")
    || queryOne(documentRef, 'table[data-screen="list"]')
    || queryOne(documentRef, "table");
  const rows = queryAll(table, "tbody tr");
  return rows.length > 0 ? rows : queryAll(table ?? documentRef, "tr").filter((row) => rowCells(row).length > 0);
}

function interestedRows(documentRef) {
  const table = byId(documentRef, "PessoasAssocicadas")
    || byId(documentRef, "PessoasAssociadas")
    || queryOne(documentRef, 'table[data-screen="interested"]');
  const rows = queryAll(table, "tr");
  return rows.filter((row) => Boolean(queryOne(row, 'input[type="radio"]')));
}

function isFormScreen(documentRef) {
  return Boolean(
    byId(documentRef, "complementarAtoForm")
    || byId(documentRef, "tbcomplementarato")
    || (byId(documentRef, "txtNumeroProcesso")
      && byId(documentRef, "txtAnoProcesso")
      && [
        "txtModalidade",
        "txtFundamentoLegal",
        "txtDataDOE",
        "txtCargo",
        "txtMatricula",
        "txtDataNascimento",
        "txtGenero",
      ].some((id) => byId(documentRef, id))),
  );
}

function hasSelectedInterested(documentRef) {
  return interestedRows(documentRef).some((row) => queryOne(row, 'input[type="radio"]')?.checked === true);
}

function isInterestedScreen(documentRef) {
  return interestedRows(documentRef).length > 0;
}

function isVisibleDocument(documentRef) {
  const frameElement = documentRef?.defaultView?.frameElement;
  if (!frameElement) return true;
  if (frameElement.hidden === true) return false;
  const style = frameElement.style;
  if (style?.display === "none"
    || style?.visibility === "hidden"
    || style?.visibility === "collapse") return false;
  const computedStyle = documentRef.defaultView?.getComputedStyle?.(frameElement);
  if (computedStyle?.display === "none"
    || computedStyle?.visibility === "hidden"
    || computedStyle?.visibility === "collapse") return false;
  const rect = frameElement.getBoundingClientRect?.();
  if (rect && (rect.width <= 0 || rect.height <= 0)) return false;
  return true;
}

function isListScreen(documentRef) {
  if (Boolean(byId(documentRef, "tbproc01"))) return true;
  return listRows(documentRef).some((row) => processKeyFromText(textOf(row)) && queryAll(row, "a").length > 0);
}

function isButtonsScreen(documentRef) {
  return queryAll(documentRef, "button, a").some((control) => {
    const action = getAttribute(control, "data-action");
    const label = normalizeInterested(textOf(control));
    return action === "return-list" || action === "return_list" || label === "voltar" || label === "retornar";
  });
}

function detectPortalScreen(documentRef = globalThis.document) {
  if (!documentRef) return "unknown";
  if (!isVisibleDocument(documentRef)) return "unknown";
  if (isFormScreen(documentRef)) {
    // The restricted portal renders the person radio and the form fields in
    // the same document. Before a radio is selected, automation must treat it
    // as the interested-party step; after selection it is the form step.
    if (interestedRows(documentRef).length > 0 && !hasSelectedInterested(documentRef)) return "interested";
    return "form";
  }
  if (isInterestedScreen(documentRef)) return "interested";
  if (isListScreen(documentRef)) return "list";
  if (isButtonsScreen(documentRef)) return "buttons";
  return "unknown";
}

function listIdentityEntries(documentRef) {
  return listRows(documentRef).map((row) => {
    const controls = queryAll(row, "a, button");
    const control = controls.find((candidate) => isComplementActControl(candidate)) ?? null;
    /*
     * A single unlabelled control is retained for the minimal legacy portal
     * fixture. Real rows with multiple icons must expose the semantic action.
     */
    const candidates = controls.filter((candidate) => !["signal-only", "submit"].includes(getAttribute(candidate, "data-action")));
    const fallback = control ?? (candidates.length === 1 ? candidates[0] : null);
    const selectedControl = fallback && (candidates.length === 1 || isComplementActControl(fallback)) ? fallback : null;
    const identity = identityFromRow(row, { processKey: processKeyFromText(textOf(row)) });
    if (hasCanonicalIdentity(identity)) identity.needsComplement = Boolean(selectedControl);
    return {
      identity,
      row,
      control: selectedControl,
    };
  });
}

function interestedIdentityEntries(documentRef) {
  const processKey = processKeyFromDocument(documentRef);
  return interestedRows(documentRef).map((row) => {
    const radio = queryOne(row, 'input[type="radio"]');
    const identity = identityFromRow(row, { radio, processKey });
    return { identity, row, radio };
  });
}

function findNextNavigation(documentRef) {
  const explicit = queryAll(documentRef, '[data-action="next-page"], [data-action="next_page"], a[rel="next"], button[rel="next"]')[0];
  if (explicit) return { control: explicit, direction: "next" };
  const current = queryOne(documentRef, '[aria-current="page"]');
  const currentNumber = Number.parseInt(textOf(current), 10);
  const next = queryAll(documentRef, "nav a, nav button, a, button").find((control) => {
    if (getAttribute(control, "aria-current") === "page") return false;
    const label = normalizeInterested(textOf(control));
    if (["próxima", "proxima", "next", "seguinte"].includes(label)) return true;
    const number = Number.parseInt(label, 10);
    return Number.isInteger(number) && Number.isInteger(currentNumber) && number > currentNumber;
  }) ?? null;
  if (next) return { control: next, direction: "next" };

  // The legacy Area Restrita posts pagination through javascript links such
  // as `NumeroPagina.value=4`; the visible Portuguese label may be decoded
  // with a replacement character by the old page charset.
  const currentPageControl = byId(documentRef, "NumeroPagina")
    || queryAll(documentRef, 'input[name="NumeroPagina"]')[0]
    || queryAll(documentRef, 'select[name="pagina"]')[0];
  const legacyCurrentPage = Number.parseInt(String(currentPageControl?.value ?? ""), 10);
  const legacyTargets = queryAll(documentRef, "a").map((control) => {
    const href = getAttribute(control, "href");
    const match = href.match(/NumeroPagina\.value\s*=\s*['"]?(\d+)/iu);
    return match ? { control, page: Number.parseInt(match[1], 10) } : null;
  }).filter(Boolean);
  const legacyNext = legacyTargets
    .filter(({ page }) => Number.isInteger(legacyCurrentPage) && page > legacyCurrentPage)
    .sort((left, right) => left.page - right.page)[0];
  if (legacyNext) return { control: legacyNext.control, direction: "next" };

  const first = queryAll(documentRef, "nav a, nav button").find((control) => {
    if (getAttribute(control, "aria-current") === "page") return false;
    return getAttribute(control, "data-action") === "first-page" || normalizeInterested(textOf(control)) === "1";
  }) ?? null;
  if (first) return { control: first, direction: "first" };
  const legacyFirst = legacyTargets.find(({ page }) => page === 1);
  return legacyFirst ? { control: legacyFirst.control, direction: "first" } : null;
}

function findNextControl(documentRef) {
  return findNextNavigation(documentRef)?.control ?? null;
}

function formField(form, name) {
  return queryOne(form, `[name="${name}"]`)
    || queryOne(form, `[id="${name}"]`);
}

function legacyPaginationSpec(control) {
  const href = getAttribute(control, "href");
  const page = href.match(/NumeroPagina\.value\s*=\s*['"]?(\d+)/iu);
  if (!page) return null;
  const pagination = href.match(/Paginacao\.value\s*=\s*['"]([^'"]+)['"]/iu);
  const group = href.match(/GrupoProcesso\.value\s*=\s*['"]([^'"]+)['"]/iu);
  return {
    page: page[1],
    pagination: pagination?.[1] ?? null,
    group: group?.[1] ?? null,
    allowed: pagination?.[1] === "S" && group?.[1] === "NS",
  };
}

function legacyPaginationPlan(documentRef, control) {
  const spec = legacyPaginationSpec(control);
  if (!spec) return null;
  if (!spec.allowed) {
    return {
      error: {
        code: "ACTION_NOT_ALLOWED",
        message: "the legacy pagination command is outside the navigation allowlist",
      },
    };
  }

  const forms = queryAll(documentRef, "form");
  const form = control?.form
    || control?.closest?.("form")
    || byId(documentRef, "form1")
    || forms.find((candidate) => getAttribute(candidate, "name") === "form1")
    || forms.find((candidate) => formField(candidate, "NumeroPagina"));
  const page = formField(form, "NumeroPagina");
  const pagination = formField(form, "Paginacao");
  const group = formField(form, "GrupoProcesso");
  if (!form || !page || !pagination || !group) {
    return {
      error: {
        code: "PAGINATION_FORM_NOT_FOUND",
        message: "the legacy pagination form is unavailable",
      },
    };
  }
  return { form, page, pagination, group, spec };
}

function submitLegacyPagination(documentRef, plan) {
  if (!plan || plan.error) return false;
  plan.page.value = plan.spec.page;
  plan.pagination.value = plan.spec.pagination;
  plan.group.value = plan.spec.group;

  const nativeSubmit = documentRef?.defaultView?.HTMLFormElement?.prototype?.submit
    || globalThis.HTMLFormElement?.prototype?.submit;
  if (typeof nativeSubmit === "function") {
    try {
      nativeSubmit.call(plan.form);
      return true;
    } catch {
      return false;
    }
  }
  if (typeof plan.form.submit === "function") {
    try {
      plan.form.submit();
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

function findReturnControl(documentRef) {
  const local = queryAll(documentRef, '[data-action="return-list"], [data-action="return_list"], a, button').find((control) => {
    const action = getAttribute(control, "data-action");
    const label = normalizeInterested(textOf(control));
    return action === "return-list" || action === "return_list" || label === "voltar" || label === "retornar";
  });
  if (local) return local;

  // Area Restrita closes the dynamically-created Complementar Ato tab from
  // the top-level shell; there is no return button inside the form iframe.
  let topDocument = null;
  try {
    topDocument = documentRef?.defaultView?.top?.document ?? null;
  } catch {
    topDocument = null;
  }
  if (!topDocument || topDocument === documentRef) return null;
  for (const tabTitle of queryAll(topDocument, "a")) {
    const classes = getAttribute(tabTitle, "class").split(/\s+/u);
    if (!classes.includes("tabs-inner") || normalizeInterested(textOf(tabTitle)) !== "complementar ato") continue;
    const tab = tabTitle.closest?.("li");
    const close = queryAll(tab, "a").find((candidate) => getAttribute(candidate, "class").split(/\s+/u).includes("tabs-close"));
    if (close) return close;
  }
  return null;
}

function topWindowFor(documentRef) {
  try {
    return documentRef?.defaultView?.top ?? null;
  } catch {
    return null;
  }
}

function topContainsControl(topDocument, control) {
  return Boolean(topDocument && control && queryAll(topDocument, "a, button, input").includes(control));
}

function topHasComplementarTab(topDocument) {
  return Boolean(topDocument && queryAll(topDocument, "a").some((candidate) => (
    getAttribute(candidate, "class").split(/\s+/u).includes("tabs-inner")
    && normalizeInterested(textOf(candidate)) === "complementar ato"
  )));
}

function listDocumentFromTop(documentRef) {
  const topWindow = topWindowFor(documentRef);
  const listDocuments = [];
  // window.frames is array-like and has no Symbol.iterator; iterate by index.
  const frameList = topWindow?.frames;
  for (let index = 0; index < (frameList?.length ?? 0); index += 1) {
    try {
      const candidate = frameList[index]?.document;
      if (candidate && isListScreen(candidate)) listDocuments.push(candidate);
    } catch {
      // Ignore inaccessible or already-detached sibling frames.
    }
  }
  return listDocuments.find((candidate) => markerFilterControls(candidate)?.select) ?? listDocuments.at(-1) ?? null;
}

async function closeRestrictedActTab(documentRef, control, timeoutMs) {
  const topWindow = topWindowFor(documentRef);
  const topDocument = topWindow?.document ?? null;
  if (!topDocument || !topContainsControl(topDocument, control)) return null;
  // A local Voltar control belongs to the generic wait path; closing the
  // restricted tab only applies when the top shell owns the control.
  if (topDocument === documentRef) return null;
  const timerFactory = documentRef?.defaultView?.setTimeout ?? globalThis.setTimeout;
  const clearTimer = documentRef?.defaultView?.clearTimeout ?? globalThis.clearTimeout;
  const timeout = Math.min(timeoutMs, NAVIGATION_TIMEOUT_MS);
  return new Promise((resolve) => {
    let settled = false;
    let timer = null;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      if (timer !== null) clearTimer(timer);
      resolve(result);
    };
    const check = () => {
      const listDocument = listDocumentFromTop(documentRef);
      if (!topHasComplementarTab(topDocument) && listDocument) {
        finish({ ok: true, action: "return_list", snapshot: snapshotPortalScreen(listDocument) });
        return;
      }
      timer = timerFactory(check, 25);
    };
    control.click?.();
    timer = timerFactory(() => finish(navigationError("NAVIGATION_TIMEOUT", "restricted portal tab did not return to a process list", {
      action: "return_list",
    })), timeout);
    check();
  });
}

function actionSnapshot(documentRef, role) {
  const actions = [];
  if (role === "list") {
    for (const entry of listIdentityEntries(documentRef)) {
      if (entry.control && hasCanonicalIdentity(entry.identity)) actions.push({ action: "open_act", enabled: true, identity: entry.identity });
    }
    const next = findNextNavigation(documentRef);
    if (next) actions.push({ action: "next_page", enabled: true, direction: next.direction });
    if (markerFilterControls(documentRef)?.submit) actions.push({ action: "filter_marker", enabled: true });
  }
  if (role === "interested") {
    for (const entry of interestedIdentityEntries(documentRef)) {
      if (hasCanonicalIdentity(entry.identity)) actions.push({ action: "select_interested", enabled: true, identity: entry.identity });
    }
    const selected = selectedIdentity(documentRef);
    if (findReturnControl(documentRef)) {
      actions.push({
        action: "return_list",
        enabled: true,
        ...(selected ? { identity: actionIdentity(selected) } : {}),
      });
    }
  }
  if (role === "form" || role === "buttons") {
    const processKey = processKeyFromDocument(documentRef);
    if (processKey) {
      const interested = interestedIdentityEntries(documentRef).find((entry) => entry.identity.selected && hasCanonicalIdentity(entry.identity))?.identity;
      if (interested) actions.push({ action: "return_list", enabled: Boolean(findReturnControl(documentRef)), identity: interested });
    }
    if (findReturnControl(documentRef)) actions.push({ action: "return_list", enabled: true });
  }
  return actions;
}

function rawFingerprint(documentRef, role) {
  const marker = getDatasetValue(documentRef, "page") || getDatasetValue(documentRef, "screen");
  const selectedMarker = observedMarker(documentRef);
  const list = listIdentityEntries(documentRef).map(({ identity }) => `${identity.processKey ?? ""}:${identity.interestedNormalized ?? ""}:${identity.portalActId ?? ""}`);
  const interested = interestedIdentityEntries(documentRef).map(({ identity }) => `${identity.processKey ?? ""}:${identity.interestedNormalized ?? ""}:${identity.selected}`);
  return JSON.stringify([role, marker, selectedMarker, processKeyFromDocument(documentRef), list, interested, textOf(documentRef?.body)]);
}

function currentGeneration(documentRef, role = detectPortalScreen(documentRef)) {
  let state = DOCUMENT_STATE.get(documentRef);
  if (!state) {
    state = { generation: 0, fingerprint: null };
    DOCUMENT_STATE.set(documentRef, state);
  }
  const fingerprint = rawFingerprint(documentRef, role);
  if (state.fingerprint !== fingerprint) {
    state.fingerprint = fingerprint;
    state.generation += 1;
  }
  return state.generation;
}

function snapshotPortalScreen(documentRef = globalThis.document) {
  const role = detectPortalScreen(documentRef);
  const identities = role === "list"
    ? listIdentityEntries(documentRef).map(({ identity }) => identity)
    : role === "interested"
      ? interestedIdentityEntries(documentRef).map(({ identity }) => identity)
      : [];
  return {
    role,
    generation: currentGeneration(documentRef, role),
    sector: getDatasetValue(documentRef, "sector") || null,
    source_scope: sourceScopeFromDocument(documentRef),
    marker: observedMarker(documentRef),
    identities: uniqueByIdentity(identities),
    actions: actionSnapshot(documentRef, role),
  };
}

function sameIdentity(left, right) {
  return hasCanonicalIdentity(left) && hasCanonicalIdentity(right)
    && left.processKey === right.processKey
    && left.interestedNormalized === right.interestedNormalized;
}

function selectedIdentity(documentRef) {
  return interestedIdentityEntries(documentRef).find(({ identity }) => identity.selected && hasCanonicalIdentity(identity))?.identity ?? null;
}

function actionIdentity(identity) {
  if (!identity) return null;
  return {
    processKey: identity.processKey,
    interestedOriginal: identity.interestedOriginal,
    interestedNormalized: identity.interestedNormalized,
    portalActId: identity.portalActId ?? null,
  };
}

function isProgress(documentRef, before, after, action, identity, requestedMarker = "") {
  if (after.role === "unknown") return false;
  if (action === "next_page") {
    const beforeKeys = new Set(before.identities.map(({ processKey, interestedNormalized }) => `${processKey}\u0000${interestedNormalized}`));
    return after.role === "list"
      && after.generation !== before.generation
      && after.identities.some(({ processKey, interestedNormalized }) => !beforeKeys.has(`${processKey}\u0000${interestedNormalized}`));
  }
  if (action === "open_act") return before.role === "list" && after.role !== "list";
  if (action === "select_interested") {
    const selected = selectedIdentity(documentRef);
    return before.role === "interested"
      && (after.role === "interested" || after.role === "form")
      && sameIdentity(selected, identity);
  }
  if (action === "return_list") return after.role === "list" && before.role !== "list";
  if (action === "filter_marker") return after.role === "list"
    && after.generation !== before.generation
    && normalizeInterested(after.marker?.label) === normalizeInterested(requestedMarker);
  return false;
}

function navigationError(code, message, extra = {}) {
  return { ok: false, error: { code, message }, ...extra };
}

function resolveControl(documentRef, action, identity) {
  if (action === "next_page") return findNextControl(documentRef);
  if (action === "return_list") return findReturnControl(documentRef);
  if (action === "open_act") {
    return listIdentityEntries(documentRef).find((entry) => sameIdentity(entry.identity, identity))?.control ?? null;
  }
  if (action === "select_interested") {
    return interestedIdentityEntries(documentRef).find((entry) => sameIdentity(entry.identity, identity))?.radio ?? null;
  }
  if (action === "filter_marker") return markerFilterControls(documentRef)?.select ?? null;
  return null;
}

async function waitForNavigation(documentRef, before, action, identity, timeoutMs, performClick, requestedMarker = "") {
  const timerFactory = documentRef?.defaultView?.setTimeout ?? globalThis.setTimeout;
  const clearTimer = documentRef?.defaultView?.clearTimeout ?? globalThis.clearTimeout;
  let rereads = 0;
  let observer = null;
  let timer = null;

  const readOnce = () => {
    rereads += 1;
    const after = snapshotPortalScreen(documentRef);
    return isProgress(documentRef, before, after, action, identity, requestedMarker) ? after : null;
  };

  return new Promise((resolve) => {
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      observer?.disconnect?.();
      if (timer !== null) clearTimer(timer);
      resolve(result);
    };
    const check = (timedOut = false) => {
      const after = readOnce();
      if (after) {
        finish({ ok: true, action, snapshot: after, rereads });
      } else if (timedOut) {
        finish(navigationError("NAVIGATION_TIMEOUT", "navigation did not produce the expected portal screen", { action, rereads }));
      }
    };
    const Observer = documentRef?.defaultView?.MutationObserver ?? globalThis.MutationObserver;
    if (typeof Observer === "function") {
      observer = new Observer(check);
      observer.observe(documentRef?.body ?? documentRef, { childList: true, subtree: true, attributes: true });
      timer = timerFactory(() => check(true), timeoutMs);
      performClick();
      return;
    }
    performClick();
    const immediate = readOnce();
    if (immediate) {
      finish({ ok: true, action, snapshot: immediate, rereads });
      return;
    }
    timer = timerFactory(() => check(true), timeoutMs);
  });
}

async function executeNavigation(documentRef = globalThis.document, request = {}) {
  const action = request?.action;
  if (!ALLOWED_ACTIONS.has(action)) return navigationError("UNSUPPORTED_ACTION", `unsupported portal navigation action: ${action}`);
  if (!Number.isSafeInteger(request.expected_generation) || request.expected_generation < 1) {
    return navigationError("INVALID_GENERATION", "expected_generation must be a positive integer");
  }
  const before = snapshotPortalScreen(documentRef);
  if (before.generation !== request.expected_generation) {
    return navigationError("STALE_GENERATION", "portal screen generation changed before navigation", { generation: before.generation });
  }
  const control = resolveControl(documentRef, action, request.identity);
  if (!control) return navigationError(action === "open_act" ? "ROW_ACTION_NOT_FOUND" : "ACTION_NOT_FOUND", "the requested observed portal action is unavailable");
  if (action === "filter_marker") {
    const controls = markerFilterControls(documentRef);
    const option = markerOption(control, request.marker);
    if (!controls?.submit) return navigationError("MARKER_FILTER_NOT_FOUND", "the marker filter Consultar control is unavailable");
    if (!option) return navigationError("MARKER_OPTION_NOT_FOUND", "the requested marker is not present in the current catalog");
    return waitForNavigation(
      documentRef,
      before,
      action,
      null,
      Number.isInteger(request.timeoutMs) && request.timeoutMs > 0 ? Math.min(request.timeoutMs, NAVIGATION_TIMEOUT_MS) : NAVIGATION_TIMEOUT_MS,
      () => {
        for (const candidate of control?.options ?? queryAll(control, "option")) candidate.selected = candidate === option;
        control.value = option.value;
        dispatchControlEvents(documentRef, control);
        controls.submit.click?.();
      },
      request.marker,
    );
  }
  if (getAttribute(control, "data-action") === "signal-only" || getAttribute(control, "data-action") === "submit") {
    return navigationError("ACTION_NOT_ALLOWED", "signal and submit controls are outside the navigation allowlist");
  }
  if (action === "open_act" && opensRestrictedComplementTab(control)) {
    // The legacy Area Restrita list remains mounted while addtabsinformacao
    // creates a sibling tab/frame. Let that frame's typed snapshot drive the
    // rest of the run instead of waiting for a mutation in this list frame.
    control.click?.();
    return { ok: true, action, snapshot: null, waitingForFrame: true };
  }
  const legacyPlan = action === "next_page" ? legacyPaginationPlan(documentRef, control) : null;
  if (legacyPlan?.error) return navigationError(legacyPlan.error.code, legacyPlan.error.message);
  if (action === "return_list") {
    const topReturn = await closeRestrictedActTab(
      documentRef,
      control,
      Number.isInteger(request.timeoutMs) && request.timeoutMs > 0 ? request.timeoutMs : NAVIGATION_TIMEOUT_MS,
    );
    if (topReturn) return topReturn;
  }
  if (action === "next_page" && legacyPlan) {
    if (!submitLegacyPagination(documentRef, legacyPlan)) {
      return navigationError("PAGINATION_SUBMIT_FAILED", "the legacy pagination form could not be submitted");
    }
    // Native form submission unloads this document. The controller must
    // probe the replacement frame instead of waiting on this old document's
    // MutationObserver, which otherwise times out after the page has moved.
    return { ok: true, action, snapshot: null, waitingForFrame: true };
  }
  return waitForNavigation(
    documentRef,
    before,
    action,
    request.identity,
    Number.isInteger(request.timeoutMs) && request.timeoutMs > 0 ? Math.min(request.timeoutMs, NAVIGATION_TIMEOUT_MS) : NAVIGATION_TIMEOUT_MS,
    () => {
      control.click?.();
    },
  );
}

function createMessageHandler(documentRef = globalThis.document) {
  return async (message) => {
    if (!isRecord(message) || typeof message.type !== "string" || !isRecord(message.payload)) {
      return navigationError("INVALID_MESSAGE", "portal navigation message must contain type and payload");
    }
    if (message.type === "PORTAL_GET_SNAPSHOT") {
      return { ok: true, payload: snapshotPortalScreen(documentRef) };
    }
    if (message.type === "PORTAL_NAVIGATE") {
      const result = await executeNavigation(documentRef, message.payload);
      return result?.ok === true
        ? { ...result, navigationToken: message.requestId }
        : result;
    }
    return navigationError("UNSUPPORTED_MESSAGE", `unsupported portal navigation message: ${message.type}`);
  };
}

function requestId() {
  return typeof globalThis.crypto?.randomUUID === "function" ? globalThis.crypto.randomUUID() : `portal-${Date.now()}`;
}

function installPortalNavigation({ documentRef = globalThis.document, chromeApi = globalThis.chrome } = {}) {
  const handleMessage = createMessageHandler(documentRef);
  if (!chromeApi?.runtime?.onMessage?.addListener) return { handleMessage, registered: false };
  chromeApi.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!["PORTAL_GET_SNAPSHOT", "PORTAL_NAVIGATE"].includes(message?.type)) return false;
    Promise.resolve(handleMessage(message)).then(sendResponse);
    return true;
  });
  if (typeof chromeApi.runtime.sendMessage === "function") {
    chromeApi.runtime.sendMessage({
      schemaVersion: 1,
      type: "PORTAL_EVENT",
      requestId: requestId(),
      payload: { event: { type: "snapshot", snapshot: snapshotPortalScreen(documentRef) } },
    });
  }
  return { handleMessage, registered: true };
}

if (typeof module === "object" && module !== null && module.exports) {
  module.exports.ALLOWED_ACTIONS = ALLOWED_ACTIONS;
  module.exports.NAVIGATION_TIMEOUT_MS = NAVIGATION_TIMEOUT_MS;
  module.exports.detectPortalScreen = detectPortalScreen;
  module.exports.snapshotPortalScreen = snapshotPortalScreen;
  module.exports.sourceScopeFromDocument = sourceScopeFromDocument;
  module.exports.executeNavigation = executeNavigation;
  module.exports.createMessageHandler = createMessageHandler;
  module.exports.installPortalNavigation = installPortalNavigation;
} else {
  globalThis.TCEPortalNavigation = Object.freeze({
    detectPortalScreen,
    snapshotPortalScreen,
    executeNavigation,
    createMessageHandler,
    installPortalNavigation,
  });
  if (globalThis.document && globalThis.chrome?.runtime?.onMessage) installPortalNavigation();
}
