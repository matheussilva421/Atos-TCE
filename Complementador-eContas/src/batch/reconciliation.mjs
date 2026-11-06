import { isValidProcessId } from '../shared/identity.mjs';

export const EXTERNAL_COMPLETION_STATUS = 'COMPLETED_EXTERNALLY';

/**
 * Reconcilia atos que foram concluídos fora do motor (por exemplo, salvamento
 * supervisionado pelo operador). Só transforma FILLED em COMPLETED_EXTERNALLY;
 * nunca conta como salvamento do motor, nunca altera CONFIRMED e é idempotente.
 */
export function reconcileExternalCompletions(batch, processIds, options = {}) {
  if (!batch || !Array.isArray(batch.queue)) {
    return { batch, changed: 0 };
  }
  const ids = new Set(
    (Array.isArray(processIds) ? processIds : [])
      .filter((processId) => typeof processId === 'string' && isValidProcessId(processId)),
  );
  if (ids.size === 0) {
    return { batch, changed: 0 };
  }
  const at = Number.isFinite(options.at) ? options.at : Date.now();
  const next = structuredClone(batch);
  let changed = 0;
  for (const entry of next.queue) {
    if (!entry || entry.status !== 'FILLED' || !ids.has(entry.processId)) {
      continue;
    }
    entry.status = EXTERNAL_COMPLETION_STATUS;
    changed += 1;
  }
  if (changed === 0) {
    return { batch, changed: 0 };
  }
  next.events = Array.isArray(next.events) ? next.events : [];
  next.events.push({
    processId: null,
    code: 'EXTERNAL_COMPLETION_RECONCILED',
    at,
    reason: 'FILLED->COMPLETED_EXTERNALLY',
  });
  next.revision = Number.isSafeInteger(next.revision) ? next.revision + 1 : 1;
  next.updatedAt = at;
  return { batch: next, changed };
}
