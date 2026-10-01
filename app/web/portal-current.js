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

