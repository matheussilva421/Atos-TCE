/**
 * Read-only Área Restrita snapshot scanner.
 *
 * The behaviour here is ported, not reinvented, from the proven selectors and
 * rules of the retired legacy extension's portal navigation module (its path
 * lives in the Git history): the same marker select, the same row/identity
 * extraction and the same fail-closed classification (a red "Complementar Ato"
 * icon means PRECISA_COMPLEMENTAR, an "Ato Complementado" label means
 * ATO_COMPLEMENTADO and anything else is AMBIGUO).
 *
 * What changed is ownership and blast radius. Snapshot scanning only *reads*
 * the page and returns sanitized data: it never clicks and never touches
 * cookies, storage or credentials. The small legacy-pagination planner below
 * parses one allowlisted form command so the pagination content script can
 * submit the portal's form without executing a javascript: URL.
 */

(() => {
  "use strict";

  const PORTAL_ROLES = Object.freeze(["list", "interested", "form", "buttons", "unknown"]);

  const AREA_CLASSIFICATIONS = Object.freeze([
    "PRECISA_COMPLEMENTAR",
    "ATO_COMPLEMENTADO",
    "NAO_ENCONTRADO_AREA_RESTRITA",
    "AMBIGUO",
    "BLOQUEADO",
  ]);

  const FORM_FIELD_IDS = Object.freeze([
    "txtModalidade",
    "txtFundamentoLegal",
    "txtDataDOE",
    "txtCargo",
    "txtMatricula",
    "txtDataNascimento",
    "txtGenero",
  ]);

  const EMPTY_MARKERS = Object.freeze([
    "todos",
    "todos os marcadores",
    "selecione",
    "selecione um marcador",
  ]);

  const NEXT_LABELS = Object.freeze(["proxima", "next", "seguinte"]);

  // ------------------------------------------------------------- primitives

  function textOf(value) {
    return typeof value?.textContent === "string"
      ? value.textContent.replace(/\s+/gu, " ").trim()
      : "";
  }

  /** Mirrors app/core/identity.py exactly: NFKD, drop marks, lowercase, collapse. */
  function normalizeInterested(value) {
    return typeof value === "string"
      ? value
          .normalize("NFKD")
          .replace(/\p{M}+/gu, "")
          .toLowerCase()
          .replace(/\s+/gu, " ")
          .trim()
      : "";
  }

  function getAttribute(element, name) {
    const value = element?.getAttribute?.(name);
    return typeof value === "string" ? value : "";
  }

  function getDatasetValue(documentRef, name) {
    const attributeName = `data-${name.replace(/[A-Z]/gu, (letter) => `-${letter.toLowerCase()}`)}`;
    for (const candidate of [documentRef?.documentElement, documentRef?.body, documentRef]) {
      const value = candidate?.dataset?.[name] ?? getAttribute(candidate, attributeName);
      if (typeof value === "string" && value.trim()) return value.trim();
    }
    return "";
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

  // ------------------------------------------------------------ portal reads

  function sourceScopeFromDocument(documentRef) {
    const explicit =
      getDatasetValue(documentRef, "sourceScope") || getAttribute(documentRef, "data-source-scope");
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

  function controlLabel(control) {
    return [
      textOf(control),
      getAttribute(control, "aria-label"),
      getAttribute(control, "title"),
      getAttribute(control, "value"),
      typeof control?.value === "string" ? control.value : "",
      ...queryAll(control, "img").flatMap((image) => [
        getAttribute(image, "alt"),
        getAttribute(image, "title"),
      ]),
    ]
      .filter(Boolean)
      .join(" ");
  }

  function markerSelect(documentRef) {
    return (
      queryAll(documentRef, "select").find((select) => {
        const metadata = [
          getAttribute(select, "id"),
          getAttribute(select, "name"),
          getAttribute(select, "aria-label"),
          getAttribute(select, "data-field"),
        ].join(" ");
        if (normalizeInterested(metadata).includes("marcador")) return true;
        const label = getAttribute(select, "id");
        if (
          label &&
          queryAll(documentRef, "label").some(
            (candidate) =>
              getAttribute(candidate, "for") === label &&
              normalizeInterested(textOf(candidate)).includes("marcador")
          )
        )
          return true;
        const row = select.closest?.("tr") ?? null;
        return normalizeInterested(textOf(row)).includes("marcador");
      }) ?? null
    );
  }

  function selectedOption(select) {
    const options = select?.options ? [...select.options] : queryAll(select, "option");
    return (
      options.find((option) => option.selected === true) ??
      options.find((option) => getAttribute(option, "selected") !== "") ??
      options.find((option) => String(option.value ?? "") === String(select?.value ?? "")) ??
      null
    );
  }

  function observedMarker(documentRef) {
    const select = markerSelect(documentRef);
    const option = selectedOption(select);
    if (!select || !option) return null;
    const label = textOf(option);
    if (!label || EMPTY_MARKERS.includes(normalizeInterested(label))) return null;
    return {
      label,
      value: typeof option.value === "string" && option.value ? option.value : null,
    };
  }

  function isComplementActControl(control) {
    const label = normalizeInterested(controlLabel(control));
    if (label.includes("complementar ato")) return true;
    const action = getAttribute(control, "data-action");
    if (action === "open-act" || action === "open_act") return true;
    const href = getAttribute(control, "href").toLowerCase();
    const signal = [href, getAttribute(control, "onclick")].join(" ").toLowerCase();
    return signal.includes("complementarato") && (signal.includes("addtabsinformacao") || href.includes("complementarato"));
  }

  function pendingComplementIconSignature(control) {
    if (!isComplementActControl(control)) return null;
    const image =
      queryAll(control, "img").find((candidate) => {
        const semantic = normalizeInterested(
          [
            getAttribute(candidate, "alt"),
            getAttribute(candidate, "title"),
            getAttribute(candidate, "src"),
            getAttribute(candidate, "class"),
          ].join(" ")
        );
        const knownPortalRedAsset = /(?:^|[/\\_-])atov\.png(?:$|\s)/u.test(semantic);
        const red =
          knownPortalRedAsset ||
          semantic.includes("vermelh") ||
          semantic.includes("red") ||
          semantic.includes("pendente");
        return red && (semantic.includes("complementar ato") || semantic.includes("complementarato"));
      }) ?? null;
    if (!image) return null;
    return {
      kind: "red_complement_icon",
      alt: getAttribute(image, "alt"),
      title: getAttribute(image, "title"),
      src: getAttribute(image, "src"),
    };
  }

  // --------------------------------------------------------------- identities

  function processKeyFromText(value) {
    const match = String(value ?? "").match(/([A-Za-z0-9][A-Za-z0-9._-]*\/\d{4})/u);
    return match?.[1] ?? "";
  }

  function processKeyFromDocument(documentRef) {
    const explicit =
      getDatasetValue(documentRef, "processKey") || getAttribute(documentRef, "data-process-key");
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
    const headerRows = queryAll(table, "thead tr").filter(
      (candidate) => !queryOne(candidate, 'input[type="radio"]')
    );
    const candidates =
      headerRows.length > 0
        ? headerRows
        : queryAll(table, "tr").filter(
            (candidate) =>
              !queryOne(candidate, 'input[type="radio"]') &&
              normalizeInterested(textOf(candidate)).includes("interessado")
          );
    for (const headerRow of candidates) {
      const index = rowCells(headerRow).findIndex(
        (header) => normalizeInterested(textOf(header)) === "interessado"
      );
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
    const dataIndex = cells.findIndex((cell) =>
      [getAttribute(cell, "data-field"), getAttribute(cell, "data-column")].some(
        (value) => normalizeInterested(value) === "interessado"
      )
    );
    if (dataIndex >= 0) return textOf(cells[dataIndex]);
    if (radio) {
      const ignored = new Set(["interessado", "responsavel", "relator", "procurador"]);
      const personCell = cells
        .map((cell) => textOf(cell))
        .find(
          (value) =>
            value && !ignored.has(normalizeInterested(value)) && !/^\d[\d./ -]*$/u.test(value)
        );
      return personCell ?? "";
    }
    if (cells.length >= 2) return textOf(cells[1]);
    return "";
  }

  function portalActIdFromRow(row, control = null) {
    return (
      getAttribute(row, "data-portal-act-id") ||
      getAttribute(row, "data-act-id") ||
      getAttribute(control, "data-portal-act-id") ||
      getAttribute(control, "data-act-id") ||
      null
    );
  }

  function identityFromRow(row, { radio = null, processKey = "" } = {}) {
    const resolvedProcessKey =
      processKey ||
      getAttribute(row, "data-process-key") ||
      getAttribute(row, "data-process") ||
      processKeyFromText(textOf(row));
    const interestedOriginal = interestedTextFromRow(row, radio);
    const interestedNormalized = normalizeInterested(interestedOriginal);
    return {
      processKey: resolvedProcessKey || null,
      interestedOriginal,
      interestedNormalized: interestedNormalized || null,
      portalActId: portalActIdFromRow(row, radio),
      pending: !resolvedProcessKey || !interestedNormalized,
    };
  }

  function hasCanonicalIdentity(identity) {
    return Boolean(identity?.processKey && identity?.interestedNormalized);
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

  function listRows(documentRef) {
    const table =
      byId(documentRef, "tbproc01") ||
      queryOne(documentRef, 'table[data-screen="list"]') ||
      queryOne(documentRef, "table");
    const rows = queryAll(table, "tbody tr");
    return rows.length > 0
      ? rows
      : queryAll(table ?? documentRef, "tr").filter((row) => rowCells(row).length > 0);
  }

  function interestedRows(documentRef) {
    const table =
      byId(documentRef, "PessoasAssocicadas") ||
      byId(documentRef, "PessoasAssociadas") ||
      queryOne(documentRef, 'table[data-screen="interested"]');
    return queryAll(table, "tr").filter((row) => Boolean(queryOne(row, 'input[type="radio"]')));
  }

  function isVisibleDocument(documentRef) {
    const frameElement = documentRef?.defaultView?.frameElement;
    if (!frameElement) return true;
    if (frameElement.hidden === true) return false;
    const style = frameElement.style;
    if (style?.display === "none" || style?.visibility === "hidden" || style?.visibility === "collapse")
      return false;
    const computedStyle = documentRef.defaultView?.getComputedStyle?.(frameElement);
    if (
      computedStyle?.display === "none" ||
      computedStyle?.visibility === "hidden" ||
      computedStyle?.visibility === "collapse"
    )
      return false;
    const rect = frameElement.getBoundingClientRect?.();
    if (rect && (rect.width <= 0 || rect.height <= 0)) return false;
    return true;
  }

  function isFormScreen(documentRef) {
    return Boolean(
      byId(documentRef, "complementarAtoForm") ||
        byId(documentRef, "tbcomplementarato") ||
        (byId(documentRef, "txtNumeroProcesso") &&
          byId(documentRef, "txtAnoProcesso") &&
          FORM_FIELD_IDS.some((id) => byId(documentRef, id)))
    );
  }

  function hasSelectedInterested(documentRef) {
    return interestedRows(documentRef).some(
      (row) => queryOne(row, 'input[type="radio"]')?.checked === true
    );
  }

  function isListScreen(documentRef) {
    if (Boolean(byId(documentRef, "tbproc01"))) return true;
    return listRows(documentRef).some(
      (row) => processKeyFromText(textOf(row)) && queryAll(row, "a").length > 0
    );
  }

  function isButtonsScreen(documentRef) {
    return queryAll(documentRef, "button, a").some((control) => {
      const action = getAttribute(control, "data-action");
      const label = normalizeInterested(textOf(control));
      return action === "return-list" || action === "return_list" || label === "voltar" || label === "retornar";
    });
  }

  function detectDocumentRole(documentRef = globalThis.document) {
    if (!documentRef) return "unknown";
    if (!isVisibleDocument(documentRef)) return "unknown";
    if (isFormScreen(documentRef)) {
      // The restricted portal renders the person radio and the form fields in
      // the same document: before a radio is selected it is the interested
      // step, after selection it is the form step.
      if (interestedRows(documentRef).length > 0 && !hasSelectedInterested(documentRef))
        return "interested";
      return "form";
    }
    if (interestedRows(documentRef).length > 0) return "interested";
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
       * fixture. Real rows with several icons must expose the semantic action.
       */
      const candidates = controls.filter(
        (candidate) => !["signal-only", "submit"].includes(getAttribute(candidate, "data-action"))
      );
      const fallback = control ?? (candidates.length === 1 ? candidates[0] : null);
      const selectedControl =
        fallback && (candidates.length === 1 || isComplementActControl(fallback)) ? fallback : null;
      const identity = identityFromRow(row, { processKey: processKeyFromText(textOf(row)) });
      if (hasCanonicalIdentity(identity)) {
        const actionSignature = selectedControl ? pendingComplementIconSignature(selectedControl) : null;
        const observedLabel = normalizeInterested(selectedControl ? controlLabel(selectedControl) : "");
        const completed = observedLabel.includes("ato complementado");
        identity.classification = actionSignature
          ? "PRECISA_COMPLEMENTAR"
          : completed
            ? "ATO_COMPLEMENTADO"
            : "AMBIGUO";
        identity.needsComplement = identity.classification === "PRECISA_COMPLEMENTAR";
        identity.actionObserved = actionSignature
          ? "Complementar Ato"
          : completed
            ? "Ato Complementado"
            : null;
        identity.actionSignature = actionSignature;
      }
      return { identity, row, control: selectedControl };
    });
  }

  // -------------------------------------------------------------- pagination

  function paginationControls(documentRef) {
    const inNav = queryAll(
      documentRef,
      "nav a, nav button, [data-action='next-page'], [data-action='next_page'], a[rel='next'], button[rel='next'], [aria-current='page']"
    );
    if (inNav.length > 0) return inNav;
    return queryAll(documentRef, "a, button");
  }

  function isNextControl(control) {
    const action = getAttribute(control, "data-action");
    if (action === "next-page" || action === "next_page") return true;
    if (getAttribute(control, "rel") === "next") return true;
    return NEXT_LABELS.includes(normalizeInterested(textOf(control)));
  }

  /**
   * The proven legacy pagination discovery, including the old portal's
   * ``NumeroPagina.value=N`` javascript links whose Portuguese label may arrive
   * with a replacement character.
   */
  function findNextPageControl(documentRef) {
    const explicit = queryAll(
      documentRef,
      '[data-action="next-page"], [data-action="next_page"], a[rel="next"], button[rel="next"]'
    )[0];
    if (explicit) return explicit;
    const currentNumber = Number.parseInt(textOf(queryOne(documentRef, "[aria-current='page']")), 10);
    const labeled = queryAll(documentRef, "nav a, nav button, a, button").find((control) => {
      if (getAttribute(control, "aria-current") === "page") return false;
      if (NEXT_LABELS.includes(normalizeInterested(textOf(control)))) return true;
      const number = Number.parseInt(normalizeInterested(textOf(control)), 10);
      return Number.isInteger(number) && Number.isInteger(currentNumber) && number > currentNumber;
    });
    if (labeled) return labeled;

    const currentPageControl =
      byId(documentRef, "NumeroPagina") ||
      queryOne(documentRef, 'input[name="NumeroPagina"]') ||
      queryOne(documentRef, 'select[name="pagina"]');
    const legacyCurrent = Number.parseInt(String(currentPageControl?.value ?? ""), 10);
    const legacy = queryAll(documentRef, "a")
      .map((control) => {
        const match = getAttribute(control, "href").match(/NumeroPagina\.value\s*=\s*['"]?(\d+)/iu);
        return match ? { control, page: Number.parseInt(match[1], 10) } : null;
      })
      .filter(Boolean)
      .filter(({ page }) => Number.isInteger(legacyCurrent) && page > legacyCurrent)
      .sort((left, right) => left.page - right.page)[0];
    return legacy?.control ?? null;
  }

  function findFirstPageControl(documentRef) {
    const controls = queryAll(documentRef, "nav a, nav button, a, button");
    const explicit = controls.find((control) => {
      const action = getAttribute(control, "data-action");
      return action === "first-page" || action === "first_page";
    });
    if (explicit) return explicit;
    return (
      controls.find(
        (control) =>
          /NumeroPagina\.value\s*=\s*['"]?1(?:\D|$)/iu.test(getAttribute(control, "href")) &&
          /primeira|first|<<|NumeroPagina/iu.test(`${textOf(control)} ${getAttribute(control, "href")}`)
      ) ?? null
    );
  }

  function formField(form, name) {
    return queryOne(form, `[name="${name}"]`) || queryOne(form, `[id="${name}"]`);
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

  /**
   * Parse only the old portal's known pagination command. The href is never
   * evaluated: its page and two fixed routing values are copied to the form
   * only after the command passes the allowlist.
   */
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
    const form =
      control?.form ||
      control?.closest?.("form") ||
      byId(documentRef, "form1") ||
      forms.find((candidate) => getAttribute(candidate, "name") === "form1") ||
      forms.find((candidate) => formField(candidate, "NumeroPagina"));
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

    const nativeSubmit =
      documentRef?.defaultView?.HTMLFormElement?.prototype?.submit ||
      globalThis.HTMLFormElement?.prototype?.submit;
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

  /**
   * Page numbers come from the same controls the legacy driver paginated with.
   * Numeric labels are authoritative; when the portal only renders a "Próxima"
   * control, the total is the current page plus that pending step.
   */
  function pageInfo(documentRef) {
    const controls = paginationControls(documentRef);
    const currentPageLink = queryOne(documentRef, "[aria-current='page']");
    const legacyPageControl =
      byId(documentRef, "NumeroPagina") ||
      queryOne(documentRef, 'input[name="NumeroPagina"]') ||
      queryOne(documentRef, 'select[name="pagina"]');
    const currentValue = currentPageLink
      ? textOf(currentPageLink)
      : String(legacyPageControl?.value ?? "").trim() || textOf(legacyPageControl);
    const currentNumber = Number.parseInt(currentValue, 10);
    const page = Number.isInteger(currentNumber) && currentNumber > 0 ? currentNumber : 1;
    const labels = controls
      .map((control) => Number.parseInt(textOf(control), 10))
      .filter((value) => Number.isInteger(value) && value > 0);
    let total = labels.length > 0 ? Math.max(...labels) : page;
    if (controls.some((control) => isNextControl(control))) total = Math.max(total, page + 1);
    return { page, total_pages: Math.max(total, page) };
  }

  // -------------------------------------------------------------------- scan

  /**
   * Return a sanitized snapshot of the current Área Restrita document.
   *
   * Rows are only produced for list screens, because a row is the only place
   * where the portal states whether an act still needs complementation. An
   * interested/form/unknown screen reports its role with an empty row list so
   * the caller can react without guessing.
   */
  function scan(documentRef = globalThis.document) {
    const role = detectDocumentRole(documentRef);
    const rows = [];
    let skippedRows = 0;
    if (role === "list") {
      for (const entry of listIdentityEntries(documentRef)) {
        const identity = entry.identity;
        if (!hasCanonicalIdentity(identity)) {
          skippedRows += 1;
          continue;
        }
        rows.push({
          process_key: identity.processKey,
          interested: identity.interestedOriginal,
          interested_normalized: identity.interestedNormalized,
          portal_act_id: identity.portalActId ?? null,
          classification: identity.classification,
          needs_complement: identity.needsComplement === true,
          action_observed: identity.actionObserved ?? null,
        });
      }
    }
    const pagination = pageInfo(documentRef);
    return {
      role,
      source_scope: sourceScopeFromDocument(documentRef),
      marker: observedMarker(documentRef),
      page: pagination.page,
      total_pages: pagination.total_pages,
      rows: uniqueByProcessAndInterested(rows),
      skipped_rows: skippedRows,
    };
  }

  function uniqueByProcessAndInterested(rows) {
    const seen = new Set();
    return rows.filter((row) => {
      const key = `${row.process_key}\u0000${row.interested_normalized}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  /**
   * Locate the Complementar Ato control of one exact row on a list screen.
   * The caller decides whether to paginate first; this only reads.
   */
  function findActControl(documentRef, identity) {
    const wantedKey = String(identity?.processKey ?? "").trim();
    const wanted = normalizeInterested(identity?.interestedNormalized);
    if (!wantedKey || !wanted) return null;
    for (const entry of listIdentityEntries(documentRef)) {
      if (String(entry.identity.processKey ?? "") !== wantedKey) continue;
      if (normalizeInterested(entry.identity.interestedNormalized) !== wanted) continue;
      if (entry.control) return entry.control;
    }
    return null;
  }

  /**
   * Locate the radio of the exact interested person on the interested screen.
   * The name resolution is the proven row/header rule, shared with the scan.
   */
  function findInterestedRadio(documentRef, identity) {
    const wanted = normalizeInterested(identity?.interestedNormalized);
    if (!wanted) return null;
    for (const row of interestedRows(documentRef)) {
      const radio = queryOne(row, 'input[type="radio"]');
      if (!radio) continue;
      if (normalizeInterested(interestedTextFromRow(row, radio)) === wanted) return radio;
    }
    return null;
  }

  globalThis.TCEAreaSnapshot = Object.freeze({
    scan,
    normalizeInterested,
    detectDocumentRole,
    pageInfo,
    findNextPageControl,
    findFirstPageControl,
    legacyPaginationPlan,
    submitLegacyPagination,
    findActControl,
    findInterestedRadio,
    dom: Object.freeze({ queryAll, queryOne, byId, getAttribute, textOf, hasCanonicalIdentity }),
    PORTAL_ROLES,
    AREA_CLASSIFICATIONS,
  });
})();
