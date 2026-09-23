/**
 * Verified form filling with no submit capability.
 *
 * Ported from the proven content/form-detector.js write path: the native value
 * setter, the bubbling ``input``/``change``/``blur`` events and the rule that a
 * select only accepts a value that exists in its current catalog.
 *
 * What this module deliberately cannot do: locate or click the final
 * "Complementar Ato" button, submit a form, or invent a field that the backend
 * did not authorize. Identity and generation are guarded before writes; each
 * authorized field is then attempted and verified independently.
 */

(() => {
  "use strict";

  const FIELD_STATUS = Object.freeze({
    CHANGED: "changed",
    PRESERVED: "preserved",
    MISSING_PROPOSAL: "missing_proposal",
    DISABLED: "disabled",
    NOT_FOUND: "not_found",
    OPTION_UNAVAILABLE: "option_unavailable",
    FAILED: "failed",
  });

  function normalize(value) {
    const api = globalThis.TCEAreaSnapshot;
    return api ? api.normalizeInterested(value) : String(value ?? "").trim().toLowerCase();
  }

  function sameIdentity(left, right) {
    const leftProcess = String(left?.processKey ?? "").trim();
    const rightProcess = String(right?.processKey ?? "").trim();
    const leftInterested = normalize(left?.interestedNormalized);
    const rightInterested = normalize(right?.interestedNormalized);
    return Boolean(leftProcess && rightProcess && leftInterested && rightInterested) &&
      leftProcess === rightProcess && leftInterested === rightInterested;
  }

  function nativeValueSetter(control) {
    let prototype = control;
    while (prototype) {
      const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
      if (typeof descriptor?.set === "function") return descriptor.set.bind(control);
      prototype = Object.getPrototypeOf(prototype);
    }
    return null;
  }

  function dispatchBubblingEvents(documentRef, control) {
    const EventConstructor = documentRef?.defaultView?.Event ?? globalThis.Event;
    if (typeof EventConstructor !== "function" || typeof control?.dispatchEvent !== "function") {
      throw new Error("construtor de eventos do DOM indisponível");
    }
    for (const type of ["input", "change", "blur"]) {
      control.dispatchEvent(new EventConstructor(type, { bubbles: true }));
    }
  }

  function optionValueExists(control, proposedValue) {
    const options = control?.options
      ? [...control.options]
      : [...(control?.querySelectorAll?.("option") ?? [])];
    return options.some((option) => {
      const value = String(option.value ?? "");
      const label = String(option.label || option.textContent || "").trim();
      const normalizedLabel = normalize(label);
      return (
        value === proposedValue &&
        Boolean(value.trim() && label) &&
        option.disabled !== true &&
        option.parentElement?.disabled !== true &&
        !/^selecion(?:e|ar)\b/u.test(normalizedLabel)
      );
    });
  }

  function isSelectedPlaceholder(control, current) {
    if (String(control?.tagName ?? "").toUpperCase() !== "SELECT" || !current) return false;
    const options = control?.options
      ? [...control.options]
      : [...(control?.querySelectorAll?.("option") ?? [])];
    return options.some((option) => {
      const value = String(option.value ?? "");
      const label = String(option.label || option.textContent || "");
      return value === current && /^selecion(?:e|ar)\b/u.test(normalize(label));
    });
  }

  function writeControl(documentRef, control, proposedValue) {
    const setter = nativeValueSetter(control);
    if (!setter) throw new Error("native value setter indisponível");
    setter(proposedValue);
    dispatchBubblingEvents(documentRef, control);
  }

  function controlOf(documentRef, field) {
    const reader = globalThis.TCEFormReader;
    const id = reader?.FIELD_MAP?.[field];
    if (!id) return null;
    return typeof documentRef?.getElementById === "function" ? documentRef.getElementById(id) : null;
  }

  function identityFromReader(reader, documentRef) {
    if (typeof reader?.readIdentity === "function") return reader.readIdentity(documentRef);
    if (typeof reader?.readProcess !== "function" || typeof reader?.readInterested !== "function") return null;
    const process = reader.readProcess(documentRef);
    const interested = reader.readInterested(documentRef);
    return {
      processKey: process?.key ?? "",
      interestedNormalized: interested?.normalized ?? "",
    };
  }

  /**
   * Apply the authorized plan to the open form.
   *
   * Returns ``{ok, identity, generation_after, field_results, warnings, code}``.
   * Identity and generation are request-wide guards. After they pass, a field
   * problem is recorded locally and does not prevent later fields from running.
   */
  function applyFill({ documentRef = globalThis.document, identity, generation, fields = {}, deps = {} } = {}) {
    const reader = deps.reader ?? globalThis.TCEFormReader;
    if (!reader?.readForm) {
      return { ok: false, code: "FORM_READER_UNAVAILABLE", field_results: {} };
    }

    const before = reader.readForm(documentRef);
    if (!before) return { ok: false, code: "FORM_NOT_AVAILABLE", field_results: {} };
    if (!sameIdentity(before.identity, identity)) {
      return { ok: false, code: "IDENTITY_MISMATCH", generation_after: before.generation, field_results: {} };
    }
    // A generation is mandatory: an absent or malformed one can never mean
    // "recent enough", and the form could have changed since it was read.
    if (!Number.isInteger(generation) || generation < 1) {
      return {
        ok: false,
        code: "GENERATION_MISSING",
        generation_after: before.generation,
        field_results: {},
      };
    }
    if (before.generation !== generation) {
      return { ok: false, code: "STALE_GENERATION", generation_after: before.generation, field_results: {} };
    }
    if (!fields || typeof fields !== "object" || Array.isArray(fields)) {
      return {
        ok: false,
        code: "INVALID_FIELD_PLAN",
        generation_after: before.generation,
        field_results: {},
      };
    }

    const fieldResults = {};
    const plans = Object.entries(fields).map(([field, proposedValue]) => {
      const proposal = proposedValue === null || proposedValue === undefined ? "" : String(proposedValue);
      const control = controlOf(documentRef, field);
      const current = String(before.fields?.[field]?.value ?? control?.value ?? "");
      const entry = {
        before: current,
        proposed: proposal,
        after: current,
        status: FIELD_STATUS.MISSING_PROPOSAL,
      };
      fieldResults[field] = entry;
      return { field, entry, control, proposal };
    });

    let latest = before;
    let safetyFailure = null;
    for (let index = 0; index < plans.length; index += 1) {
      const { field, entry, control, proposal } = plans[index];
      if (proposal === "") {
        entry.warning = "missing_proposal";
        continue;
      }
      if (!control) {
        entry.status = FIELD_STATUS.NOT_FOUND;
        entry.warning = "control_not_found";
        continue;
      }
      if (control.disabled === true || control.readOnly === true) {
        entry.status = FIELD_STATUS.DISABLED;
        entry.warning = "control_disabled";
        continue;
      }
      let current = String(control.value ?? latest.fields?.[field]?.value ?? "");
      if (isSelectedPlaceholder(control, current)) current = "";
      const isSelect = String(control.tagName ?? "").toUpperCase() === "SELECT";
      const equivalent = isSelect ? current === proposal : normalize(current) === normalize(proposal);
      if (current.trim() && equivalent) {
        entry.status = FIELD_STATUS.PRESERVED;
        continue;
      }
      if (current.trim()) {
        entry.status = FIELD_STATUS.PRESERVED;
        entry.warning = "existing_value_divergence";
        continue;
      }
      if (isSelect && !optionValueExists(control, proposal)) {
        entry.status = FIELD_STATUS.OPTION_UNAVAILABLE;
        entry.warning = "option_unavailable";
        continue;
      }

      let writeError = null;
      try {
        writeControl(documentRef, control, proposal);
      } catch (error) {
        writeError = String(error?.message ?? error);
      }

      let reread = null;
      let rereadError = null;
      try {
        reread = reader.readForm(documentRef);
      } catch (error) {
        rereadError = String(error?.message ?? error);
      }

      if (!reread) {
        entry.status = FIELD_STATUS.FAILED;
        entry.after = String(control.value ?? "");
        entry.warning = "field_reread_failed";
        entry.error = rereadError ?? "form_not_available_during_reread";
        let identityAfterFailure = null;
        let visibleAfterFailure = false;
        try {
          visibleAfterFailure =
            typeof reader.isVisibleForm !== "function" || reader.isVisibleForm(documentRef) === true;
          identityAfterFailure = identityFromReader(reader, documentRef);
        } catch {
          visibleAfterFailure = false;
        }
        if (visibleAfterFailure && sameIdentity(identityAfterFailure, before.identity)) {
          continue;
        }
        safetyFailure = "FORM_NOT_AVAILABLE_AFTER_WRITE";
        for (const remaining of plans.slice(index + 1)) {
          remaining.entry.status = FIELD_STATUS.FAILED;
          remaining.entry.error = "not_attempted_after_form_unavailable";
        }
        break;
      }
      if (!sameIdentity(reread.identity, before.identity)) {
        entry.status = FIELD_STATUS.FAILED;
        entry.after = String(reread.fields?.[field]?.value ?? control.value ?? "");
        entry.warning = "form_identity_changed";
        entry.error = "identity_changed_during_fill";
        safetyFailure = "IDENTITY_MISMATCH_AFTER_WRITE";
        for (const remaining of plans.slice(index + 1)) {
          remaining.entry.status = FIELD_STATUS.FAILED;
          remaining.entry.error = "not_attempted_after_identity_change";
        }
        break;
      }
      latest = reread;
      const rereadField = reread.fields?.[field];
      if (!rereadField) {
        entry.status = FIELD_STATUS.FAILED;
        entry.warning = "field_reread_failed";
        entry.error = writeError ?? "control_not_reported_after_write";
        entry.after = String(control.value ?? "");
        continue;
      }
      entry.after = String(rereadField.value ?? "");
      if (writeError) {
        entry.status = FIELD_STATUS.FAILED;
        entry.warning = "field_write_failed";
        entry.error = writeError;
      } else if (entry.after === proposal) {
        entry.status = FIELD_STATUS.CHANGED;
      } else {
        entry.status = FIELD_STATUS.FAILED;
        entry.warning = "field_reread_mismatch";
        entry.error = "reread_did_not_match_proposal";
      }
    }

    const warnings = Object.entries(fieldResults)
      .filter(([, entry]) => entry.warning)
      .map(([field, entry]) => ({ field, code: entry.warning }));
    return {
      ok: safetyFailure === null,
      identity: latest.identity ?? before.identity,
      generation_after: latest.generation ?? before.generation,
      field_results: fieldResults,
      warnings,
      code: safetyFailure,
    };
  }

  globalThis.TCEFillForm = Object.freeze({ applyFill, FIELD_STATUS, nativeValueSetter, optionValueExists });

  const runtime = globalThis.chrome?.runtime;
  if (runtime?.onMessage?.addListener) {
    runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (!message || message.type !== "FILL_FORM") return undefined;
      try {
        const payload = message.payload ?? {};
        sendResponse(
          applyFill({
            documentRef: globalThis.document,
            identity: payload.identity ?? {},
            generation: payload.generation,
            fields: payload.fields ?? {},
          })
        );
      } catch (error) {
        sendResponse({ ok: false, code: "FILL_FAILED", error: String(error?.message ?? error) });
      }
      return true;
    });
  }
})();
