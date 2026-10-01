"use strict";

/**
 * Pure helpers for the "Portal atual" workspace.
 *
 * They decide exactly two things: how complete a process looks from the fields
 * the analysis actually found, and whether the Mesa should follow the form the
 * extension observed. Keeping them pure makes the follow rules testable without
 * a DOM, a server or a portal.
 */

export const PORTAL_SELECTION_POLL_MS = 1000;

const COMPLETE = "COMPLETO";
const PARTIAL = "PARCIAL";
const EMPTY = "SEM_DADOS";
const CONFLICT = "CONFLITO";

/** The seven fields the act form carries: six mandatory plus the optional one. */
export const KNOWN_PORTAL_FIELDS = Object.freeze([
  { name: "modalidade", label: "Modalidade", mandatory: true },
  { name: "fundamento_legal", label: "Fundamento legal", mandatory: true },
  { name: "data_publicacao_doe", label: "Publicação no DOE", mandatory: true },
  { name: "cargo", label: "Cargo", mandatory: true },
  { name: "matricula", label: "Matrícula", mandatory: true },
  { name: "data_nascimento", label: "Nascimento", mandatory: true },
  { name: "genero", label: "Gênero", mandatory: false },
]);

const MANDATORY_NAMES = KNOWN_PORTAL_FIELDS.filter((field) => field.mandatory).map(
  (field) => field.name
);

/**
 * A visual quality indicator. It is informative only: it never gates a fill.
 *
 * A conflict is reported before completeness, because a process whose fields
 * disagree with the portal needs a human even when every field is present.
 */
export function classifyPortalProcess(process) {
  const fields = Array.isArray(process?.fields) ? process.fields : [];
  const byName = new Map();
  for (const field of fields) {
    if (field && typeof field === "object" && field.field_name) {
      byName.set(String(field.field_name), field);
    }
  }
  const found = MANDATORY_NAMES.filter((name) => {
    const field = byName.get(name);
    return field?.status === "found" && String(field.value ?? "").trim() !== "";
  });
  const conflictCount = fields.filter((field) => field?.status === "conflict").length;
  const conflicted = String(process?.status ?? "") === "DIVERGENCIA" || conflictCount > 0;

  let state = EMPTY;
  if (conflicted) state = CONFLICT;
  else if (found.length === MANDATORY_NAMES.length) state = COMPLETE;
  else if (found.length > 0) state = PARTIAL;

  return {
    state,
    foundCount: found.length,
    pendingCount: MANDATORY_NAMES.length - found.length,
    conflictCount,
  };
}

/**
 * Decide what a fresh observation means for the Mesa.
 *
 * ``portalProcessId`` is the last MATCHED process, remembered even while the
 * follow is paused so "Retomar acompanhamento" can return to it. A selection is
 * requested only while the follow is active, only for a MATCHED observation, and
 * only when the observed process is not the one already selected — which is what
 * stops a repeated poll from stealing the sub-tab the operator chose.
 */
export function followAction({ followPortal, selectedId, portalProcessId, activeTab }, observation) {
  const state = String(observation?.state ?? "NO_ACTIVE_FORM");
  const observedId = Number.isInteger(observation?.process_id) ? observation.process_id : null;
  if (state !== "MATCHED" || observedId === null) {
    return { portalProcessId, selectProcessId: null, openPortalTab: false };
  }
  if (!followPortal) {
    // Pausing stops the Mesa from taking over; it does not forget the form.
    return { portalProcessId: observedId, selectProcessId: null, openPortalTab: false };
  }
  if (observedId === selectedId) {
    return { portalProcessId: observedId, selectProcessId: null, openPortalTab: false };
  }
  return {
    portalProcessId: observedId,
    selectProcessId: observedId,
    openPortalTab: activeTab !== "portal",
  };
}


/** The three verdicts a "Portal atual" field card can carry. */
export const PORTAL_VERDICT = Object.freeze({
  FOUND: "ENCONTRADO",
  REVIEW: "REVISAR",
  PENDING: "PENDENTE",
});

/**
 * One model per known field, for the "Portal atual" cards.
 *
 * A field the analysis never resolved stays PENDENTE with an empty value: the
 * view explains the pendency instead of inventing something to show.
 */
export function portalFieldModels(process) {
  const fields = Array.isArray(process?.fields) ? process.fields : [];
  const byName = new Map(fields.map((field) => [String(field?.field_name), field]));
  return KNOWN_PORTAL_FIELDS.map((field) => {
    const entry = byName.get(field.name) || null;
    const value = entry && String(entry.value ?? "").trim() !== "" ? String(entry.value) : "";
    const conflict = entry?.status === "conflict";
    const confirmed = entry?.status === "found" && value !== "";
    // A value the analysis did not confirm is never presented as found, so the
    // card and the completeness count above it always agree.
    let verdict = PORTAL_VERDICT.PENDING;
    if (conflict) verdict = PORTAL_VERDICT.REVIEW;
    else if (confirmed) verdict = PORTAL_VERDICT.FOUND;
    else if (value) verdict = PORTAL_VERDICT.REVIEW;
    return {
      name: field.name,
      label: field.label,
      mandatory: field.mandatory,
      entry,
      value,
      verdict,
    };
  });
}

/**
 * What "Retomar acompanhamento" may select.
 *
 * Resume returns to the form the portal is showing right now — never to a
 * process id remembered from an observation that already expired or was
 * replaced. With nothing matched, resuming only restores the follow state.
 */
export function resumeAction(observation) {
  const state = String(observation?.state ?? "NO_ACTIVE_FORM");
  const observedId = Number.isInteger(observation?.process_id) ? observation.process_id : null;
  if (state !== "MATCHED" || observedId === null) {
    return { selectProcessId: null, openPortalTab: false };
  }
  return { selectProcessId: observedId, openPortalTab: true };
}

/**
 * Whether the "Portal atual" tab may offer "Preencher dados encontrados".
 *
 * Offered only when the form the extension observed is the process on screen.
 * Every other state explains itself, so the operator never sees a button that
 * would fail and no click is ever attributed to a form that was not shown.
 */
export function currentFillAvailability(observation, processId) {
  const state = String(observation?.state ?? "NO_ACTIVE_FORM");
  const observedId = Number.isInteger(observation?.process_id) ? observation.process_id : null;
  if (state === "MATCHED" && observedId !== null && observedId === processId) {
    return {
      available: true,
      message: "O formulário aberto na Área Restrita corresponde a este processo.",
    };
  }
  if (state === "MATCHED" && observedId === null) {
    return {
      available: false,
      message: "O formulário aberto não pôde ser associado a um processo.",
    };
  }
  if (state === "MATCHED") {
    return {
      available: false,
      message: "O formulário aberto na Área Restrita pertence a outro processo.",
    };
  }
  if (state === "NOT_FOUND") {
    return {
      available: false,
      message: "Processo identificado no portal, mas não encontrado no acervo local.",
    };
  }
  if (state === "AMBIGUOUS") {
    return {
      available: false,
      message: "Correspondência ambígua. Nenhum processo foi selecionado automaticamente.",
    };
  }
  if (state === "INVALID") {
    return {
      available: false,
      message: "Observação estrutural inválida no portal. Nada foi preenchido.",
    };
  }
  return { available: false, message: "Nenhum formulário aberto na Área Restrita." };
}
