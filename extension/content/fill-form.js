/**
 * Verified form filling with no submit capability.
 *
 * Ported from the proven content/form-detector.js write path: the native value
 * setter, the bubbling ``input``/``change``/``blur`` events and the rule that a
 * select only accepts a value that exists in its current catalog.
 *
 * What this module deliberately cannot do: locate or click the final
 * "Complementar Ato" button, submit a form, or invent a field that the backend
 * did not authorize. Every write is reread and reported; a single failed
 * verification makes the whole fill fail so the backend never marks the act as
 * filled on partial evidence.
 */

(() => {
  "use strict";

  const FIELD_STATUS = Object.freeze({
    CHANGED: "changed",
    PRESERVED: "preserved",
    MISSING: "missing",
    DISABLED: "disabled",
    NOT_FOUND: "not_found",
    FAILED: "failed",
    //: A field that would have been written, but was held back because another
    //: field failed the local check. It proves that nothing was written.
    SKIPPED: "skipped",
  });

  function normalize(value) {
    const api = globalThis.TCEAreaSnapshot;
    return api ? api.normalizeInterested(value) : String(value ?? "").trim().toLowerCase();
  }

  function sameIdentity(left, right) {
    return (
      Boolean(left && right) &&
      String(left.processKey) === String(right.processKey) &&
      normalize(left.interestedNormalized) === normalize(right.interestedNormalized)
    );
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
    return options.some((option) => String(option.value ?? "") === proposedValue);
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

  /**
   * Apply the authorized plan to the open form.
   *
   * Returns ``{ok, identity, generation_after, field_results, code}``. Nothing
   * is written unless the identity, the generation and every planned control
   * agree beforehand; every written or preserved field is reread afterwards.
   *
   * The fill runs in two phases. Phase A validates every field without
   * touching a control; a single invalid field ends the whole fill with zero
   * writes, because a partially written act is worse than an untouched one.
   * Phase B writes only after phase A passed completely.
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

    // ------------------------------------------------- phase A: no writes
    const fieldResults = {};
    const plans = [];
    for (const [field, proposedValue] of Object.entries(fields)) {
      const proposal = proposedValue === null || proposedValue === undefined ? "" : String(proposedValue);
      const control = controlOf(documentRef, field);
      const current = before.fields?.[field]?.value ?? "";
      const entry = { before: current, proposed: proposal, after: current, status: FIELD_STATUS.MISSING };
      const plan = { field, entry, control, proposal, writable: false };
      fieldResults[field] = entry;
      plans.push(plan);
      if (proposal === "") {
        continue;
      }
      if (!control) {
        entry.status = FIELD_STATUS.NOT_FOUND;
        continue;
      }
      if (control.disabled === true || control.readOnly === true) {
        entry.status = FIELD_STATUS.DISABLED;
        continue;
      }
      if (current === proposal) {
        entry.status = FIELD_STATUS.PRESERVED;
        continue;
      }
      if (String(control.tagName ?? "").toUpperCase() === "SELECT" && !optionValueExists(control, proposal)) {
        entry.status = FIELD_STATUS.FAILED;
        continue;
      }
      entry.status = FIELD_STATUS.CHANGED;
      plan.writable = true;
    }

    const refused = plans.some(
      (plan) => plan.entry.status !== FIELD_STATUS.PRESERVED && plan.writable !== true
    );
    if (refused) {
      for (const plan of plans) {
        if (plan.writable) plan.entry.status = FIELD_STATUS.SKIPPED;
      }
      return {
        ok: false,
        code: "FILL_PRECHECK_FAILED",
        identity: before.identity,
        generation_after: before.generation,
        field_results: fieldResults,
      };
    }

    // ------------------------------------------- phase B: write and reread
    for (const plan of plans) {
      if (!plan.writable) continue;
      try {
        writeControl(documentRef, plan.control, plan.proposal);
        plan.entry.after = String(plan.control.value ?? "");
      } catch (error) {
        plan.entry.status = FIELD_STATUS.FAILED;
        plan.entry.after = String(plan.control.value ?? "");
        plan.entry.error = String(error?.message ?? error);
      }
    }

    // Reread the form: only what the DOM really reports counts as filled.
    const after = reader.readForm(documentRef);
    let verified = true;
    for (const plan of plans) {
      if (plan.entry.status !== FIELD_STATUS.CHANGED) continue;
      const reported = after?.fields?.[plan.field]?.value ?? "";
      plan.entry.after = reported;
      if (reported !== plan.proposal) {
        plan.entry.status = FIELD_STATUS.FAILED;
        verified = false;
      }
    }
    for (const entry of Object.values(fieldResults)) {
      if (
        [
          FIELD_STATUS.FAILED,
          FIELD_STATUS.DISABLED,
          FIELD_STATUS.NOT_FOUND,
          FIELD_STATUS.MISSING,
          FIELD_STATUS.SKIPPED,
        ].includes(entry.status)
      ) {
        verified = false;
      }
    }
    return {
      ok: verified && Boolean(after),
      identity: after?.identity ?? before.identity,
      generation_after: after?.generation ?? before.generation,
      field_results: fieldResults,
      code: verified && after ? null : "FILL_VERIFICATION_FAILED",
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
