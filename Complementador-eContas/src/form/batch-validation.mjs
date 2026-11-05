import { normalizeText } from '../shared/identity.mjs';

const FIELDS = ['dataDoeEstado', 'cargo', 'matricula', 'dataNascimento'];
const DATE_FIELDS = new Set(['dataDoeEstado', 'dataNascimento']);

function parseDateValue(value) {
  const text = String(value || '').trim();
  let match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(text);
  if (match) {
    return match[3] + '-' + match[2].padStart(2, '0') + '-' + match[1].padStart(2, '0');
  }
  match = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(text);
  if (match) {
    return match[1] + '-' + match[2].padStart(2, '0') + '-' + match[3].padStart(2, '0');
  }
  return null;
}

function equivalent(field, existing, proposal) {
  if (DATE_FIELDS.has(field)) {
    const left = parseDateValue(existing);
    const right = parseDateValue(proposal);
    if (left && right) {
      return left === right;
    }
  }
  return normalizeText(existing).toLowerCase() === normalizeText(proposal).toLowerCase();
}

/**
 * Compara valores já presentes no formulário com a proposta documental.
 * Vazio pode ser preenchido; equivalente é preservado; divergente bloqueia;
 * existente sem valor documental confiável vai para revisão.
 */
export function compareExistingFields(formSnapshot, proposals) {
  const conflicts = [];
  const unknown = [];
  const values = formSnapshot && formSnapshot.values ? formSnapshot.values : {};
  for (const field of FIELDS) {
    if (!normalizeText(values[field])) {
      continue;
    }
    const proposal = proposals ? proposals[field] : '';
    if (!normalizeText(proposal)) {
      unknown.push(field);
      continue;
    }
    if (!equivalent(field, values[field], proposal)) {
      conflicts.push(field);
    }
  }
  if (formSnapshot && formSnapshot.modalitySelected && normalizeText(formSnapshot.modalitySelectedLabel)) {
    const proposal = proposals ? proposals.modalidade : '';
    if (!normalizeText(proposal)) {
      unknown.push('modalidade');
    } else if (normalizeText(formSnapshot.modalitySelectedLabel).toLowerCase()
      !== normalizeText(proposal).toLowerCase()) {
      conflicts.push('modalidade');
    }
  }
  return { ok: conflicts.length === 0 && unknown.length === 0, conflicts, unknown };
}

/**
 * Revalidacão imediatamente antes de armar o salvamento: cinco campos, identidade,
 * pendência, revisão do formulário e ausência de erro visível.
 */
export function validateBatchReady(formSnapshot, processContext) {
  const context = processContext || {};
  if (!formSnapshot || context.processId !== formSnapshot.processId) {
    return { ok: false, code: 'PROCESS_MISMATCH' };
  }
  if (context.interestedCount !== 1 || formSnapshot.interestedCount !== 1) {
    return { ok: false, code: 'MULTIPLE_INTERESTED' };
  }
  if (context.interestedKey !== formSnapshot.interestedKey) {
    return { ok: false, code: 'INTERESTED_CHANGED' };
  }
  if (context.status !== 'pending') {
    return { ok: false, code: 'PROCESS_NOT_PENDING' };
  }
  if (context.revisionMarker !== formSnapshot.revisionMarker) {
    return { ok: false, code: 'FORM_REVISION_CHANGED' };
  }
  if (context.visibleErrors) {
    return { ok: false, code: 'VISIBLE_ERROR' };
  }
  const values = formSnapshot.values || {};
  const missing = FIELDS.filter((field) => !normalizeText(values[field]));
  if (!formSnapshot.modalitySelected || !normalizeText(formSnapshot.modalitySelectedLabel)) {
    missing.push('modalidade');
  }
  if (missing.length > 0) {
    return { ok: false, code: 'MISSING_FIELDS', fields: missing };
  }
  return { ok: true };
}
