import { normalizeLabel, normalizeText } from '../shared/identity.mjs';
import { FIELD_NAMES, FormError, openModalityDropdown, readForm, readSelectedModalityLabel } from './form-reader.mjs';

const DATE_FIELDS = new Set(['dataDoeEstado', 'dataNascimento']);

function isValidBrDate(value) {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(String(value || ''));
  if (!match) {
    return false;
  }
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year
    && date.getUTCMonth() === month - 1
    && date.getUTCDate() === day;
}

export function createFillPlan(proposals, form) {
  const plan = {
    modality: { action: 'skip', reason: 'NOT_EXACT' },
    fields: {},
    sourceNotes: {},
    warnings: [],
  };

  for (const name of FIELD_NAMES) {
    const proposal = proposals ? proposals[name] : null;
    if (!proposal || proposal.status !== 'exact' || !proposal.value) {
      plan.fields[name] = { action: 'skip', reason: 'NOT_EXACT' };
      continue;
    }
    if (!form.editable[name]) {
      plan.fields[name] = { action: 'preserve', reason: 'READONLY' };
      continue;
    }
    const current = String(form.values[name] || '');
    if (current.trim().length > 0) {
      plan.fields[name] = normalizeText(current) === normalizeText(proposal.value)
        ? { action: 'preserve', reason: 'ALREADY_EQUAL' }
        : { action: 'preserve', reason: 'EXISTING_VALUE' };
      continue;
    }
    if (DATE_FIELDS.has(name) && !isValidBrDate(proposal.value)) {
      plan.fields[name] = { action: 'skip', reason: 'INVALID_DATE' };
      continue;
    }
    if (form.maxlength[name] && proposal.value.length > form.maxlength[name]) {
      plan.fields[name] = { action: 'skip', reason: 'TOO_LONG' };
      continue;
    }
    plan.fields[name] = {
      action: 'fill',
      value: proposal.value,
      source: proposal.source || 'documento atual',
    };
  }

  if (form.modalitySelected) {
    plan.modality = { action: 'preserve', reason: 'ALREADY_SELECTED' };
  } else {
    const proposal = proposals ? proposals.modalidade : null;
    if (!proposal || proposal.status !== 'exact' || !proposal.value) {
      plan.modality = { action: 'skip', reason: 'NOT_EXACT' };
    } else {
      const matches = form.modalities.filter(
        (modality) => !modality.disabled && normalizeLabel(modality.label) === normalizeLabel(proposal.value),
      );
      if (matches.length === 1) {
        plan.modality = { action: 'fill', label: matches[0].label, id: matches[0].id };
      } else if (matches.length === 0) {
        plan.modality = { action: 'skip', reason: 'MODALITY_NOT_FOUND' };
      } else {
        plan.modality = { action: 'skip', reason: 'MODALITY_AMBIGUOUS' };
      }
    }
  }

  if (plan.fields.dataDoeEstado.action === 'fill') {
    plan.sourceNotes.dataDoeEstado = 'Origem: data da resolução administrativa';
  }
  return plan;
}

function setNativeValue(input, value) {
  const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value');
  if (descriptor && typeof descriptor.set === 'function') {
    descriptor.set.call(input, value);
  } else {
    input.value = value;
  }
  const view = input.ownerDocument && input.ownerDocument.defaultView;
  const EventCtor = view ? view.Event : Event;
  input.dispatchEvent(new EventCtor('input', { bubbles: true }));
  input.dispatchEvent(new EventCtor('change', { bubbles: true }));
  input.dispatchEvent(new EventCtor('blur', { bubbles: true }));
}

function readback(doc, name) {
  const input = doc.querySelector('tce-input-field[formcontrolname="' + name + '"] input, tce-input-field[formcontrolname="' + name + '"] textarea');
  return input ? input.value : '';
}

async function stabilizeForm(doc, read, expected, marker, wait, stabilizeMs = 50) {
  let currentMarker = marker;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await wait(stabilizeMs);
    const next = read(doc);
    if (next.processId !== expected.processId || next.interestedKey !== expected.interestedKey) {
      return { ok: false, code: 'INTERESTED_CHANGED' };
    }
    if (next.revisionMarker === currentMarker) {
      return { ok: true, marker: currentMarker };
    }
    currentMarker = next.revisionMarker;
  }
  return { ok: false, code: 'FORM_CHANGED' };
}

async function selectModalityInDom(doc, label, deps = {}) {
  const scope = doc.querySelector('tce-select-field.modalidade-campo') || doc.querySelector('tce-select-field');
  if (!scope) {
    throw new FormError('MODALITY_NOT_FOUND', 'Campo de modalidade não localizado.');
  }
  const panel = scope.querySelector('.ng-dropdown-panel');
  if (!panel || panel.style.display === 'none') {
    await openModalityDropdown(doc, deps);
  }
  const options = [...scope.querySelectorAll('.ng-option')].filter(
    (option) => !option.classList.contains('ng-option-disabled')
      && normalizeLabel(option.textContent) === normalizeLabel(label),
  );
  if (options.length === 0) {
    throw new FormError('MODALITY_NOT_FOUND', 'Modalidade não encontrada no catálogo.');
  }
  if (options.length > 1) {
    throw new FormError('MODALITY_AMBIGUOUS', 'Mais de uma modalidade corresponde ao texto.');
  }
  const option = options[0];
  const view = doc.defaultView || undefined;
  const MouseEventCtor = (view && view.MouseEvent) || (typeof MouseEvent !== 'undefined' ? MouseEvent : null);
  if (!MouseEventCtor) { throw new FormError('WRITE_FAILED', 'Eventos DOM indisponíveis.'); }
  option.dispatchEvent(new MouseEventCtor('click', { bubbles: true, cancelable: true, view }));
  const wait = deps.wait || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const readbackMs = typeof deps.modalityReadbackMs === 'number' ? deps.modalityReadbackMs : 50;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    await wait(attempt === 0 ? 0 : readbackMs);
    const selected = readSelectedModalityLabel(scope.querySelector('ng-select'));
    if (normalizeLabel(selected) === normalizeLabel(label)) {
      return;
    }
  }
  throw new FormError('READBACK_MISMATCH', 'Modalidade não refletiu a seleção.');
}

export async function applyFillPlan(doc, plan, expected, deps = {}) {
  const read = deps.readForm || readForm;
  const wait = deps.wait || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const selectModality = deps.selectModality || selectModalityInDom;
  const filled = [];
  const preserved = [];
  const skipped = [];
  const errors = [];

  for (const name of FIELD_NAMES) {
    const action = plan.fields ? plan.fields[name] : null;
    if (!action) {
      continue;
    }
    if (action.action === 'preserve') {
      preserved.push({ field: name, reason: action.reason });
    } else if (action.action !== 'fill') {
      skipped.push({ field: name, reason: action.reason });
    }
  }
  if (plan.modality && plan.modality.action === 'preserve') {
    preserved.push({ field: 'modalidade', reason: plan.modality.reason });
  }
  if (plan.modality && plan.modality.action === 'skip') {
    skipped.push({ field: 'modalidade', reason: plan.modality.reason });
  }

  let current = read(doc);
  if (current.processId !== expected.processId) {
    return { ok: false, filled, preserved, skipped, errors: [{ field: null, code: 'PROCESS_CHANGED' }], elapsedMs: 0 };
  }
  if (current.interestedKey !== expected.interestedKey) {
    return { ok: false, filled, preserved, skipped, errors: [{ field: null, code: 'INTERESTED_CHANGED' }], elapsedMs: 0 };
  }
  let lastMarker = current.revisionMarker;
  const started = Date.now();

  if (plan.modality && plan.modality.action === 'fill') {
    current = read(doc);
    if (current.processId !== expected.processId || current.interestedKey !== expected.interestedKey) {
      errors.push({ field: 'modalidade', code: 'INTERESTED_CHANGED' });
      return { ok: false, filled, preserved, skipped, errors, elapsedMs: Date.now() - started };
    }
    if (current.revisionMarker !== lastMarker) {
      errors.push({ field: 'modalidade', code: 'FORM_CHANGED' });
      return { ok: false, filled, preserved, skipped, errors, elapsedMs: Date.now() - started };
    }
    try {
      await selectModality(doc, plan.modality.label, deps);
      const after = read(doc);
      if (normalizeLabel(after.modalitySelectedLabel) !== normalizeLabel(plan.modality.label)) {
        errors.push({ field: 'modalidade', code: 'READBACK_MISMATCH' });
        return { ok: false, filled, preserved, skipped, errors, elapsedMs: Date.now() - started };
      }
      filled.push({ field: 'modalidade', value: plan.modality.label });
      lastMarker = after.revisionMarker;
      const stabilized = await stabilizeForm(doc, read, expected, lastMarker, wait, deps.stabilizeMs);
      if (!stabilized.ok) {
        errors.push({ field: 'modalidade', code: stabilized.code });
        return { ok: false, filled, preserved, skipped, errors, elapsedMs: Date.now() - started };
      }
      lastMarker = stabilized.marker;
    } catch (error) {
      errors.push({ field: 'modalidade', code: error.code || 'WRITE_FAILED' });
      return { ok: false, filled, preserved, skipped, errors, elapsedMs: Date.now() - started };
    }
  }

  for (const name of FIELD_NAMES) {
    const action = plan.fields ? plan.fields[name] : null;
    if (!action || action.action !== 'fill') {
      continue;
    }
    current = read(doc);
    if (current.processId !== expected.processId || current.interestedKey !== expected.interestedKey) {
      errors.push({ field: name, code: 'INTERESTED_CHANGED' });
      break;
    }
    if (current.revisionMarker !== lastMarker) {
      errors.push({ field: name, code: 'FORM_CHANGED' });
      break;
    }
    try {
      const input = doc.querySelector('tce-input-field[formcontrolname="' + name + '"] input, tce-input-field[formcontrolname="' + name + '"] textarea');
      if (!input) {
        errors.push({ field: name, code: 'FIELD_NOT_FOUND' });
        break;
      }
      setNativeValue(input, action.value);
      await wait(0);
      if (normalizeText(readback(doc, name)) !== normalizeText(action.value)) {
        errors.push({ field: name, code: 'READBACK_MISMATCH' });
        break;
      }
      const after = read(doc);
      if (after.processId !== expected.processId || after.interestedKey !== expected.interestedKey) {
        errors.push({ field: name, code: 'INTERESTED_CHANGED' });
        break;
      }
      filled.push({ field: name, value: action.value, source: action.source });
      const stabilized = await stabilizeForm(doc, read, expected, after.revisionMarker, wait, deps.stabilizeMs);
      if (!stabilized.ok) {
        errors.push({ field: name, code: stabilized.code });
        break;
      }
      lastMarker = stabilized.marker;
    } catch (error) {
      errors.push({ field: name, code: error.code || 'WRITE_FAILED' });
      break;
    }
  }

  return {
    ok: errors.length === 0,
    filled,
    preserved,
    skipped,
    errors,
    elapsedMs: Date.now() - started,
  };
}
