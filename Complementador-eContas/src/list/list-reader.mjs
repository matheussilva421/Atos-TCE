import { hashString, normalizeLabel, normalizeProcessLabel } from '../shared/identity.mjs';
import { parseListRoute } from '../shared/routes.mjs';

export const LIST_TABLE_ID = 'tabela-processos-consulta-id';
export const PENDING_CLASS = 'complemento-ato-pendente';
export const COMPLETED_CLASS = 'complemento-ato-completo';

const CONTEXT_SELECTS = ['idMarcador', 'atoComplementado', 'PossuiPendenciaAto', 'UltimaTramitacao', 'OptInformacao'];
const CONTEXT_CHECKBOXES = ['ProcessosNoSetor', 'ProcessosFinalisticosNoSetor', 'ProcessosAdministrativosNoSetor', 'semMarcador'];

function locationHref(doc) {
  return (doc && doc.location && doc.location.href)
    || (doc && doc.defaultView && doc.defaultView.location && doc.defaultView.location.href)
    || '';
}

function isHidden(element) {
  let node = element;
  while (node && node.nodeType === 1) {
    if (node.hidden) {
      return true;
    }
    if (node.getAttribute && node.getAttribute('aria-hidden') === 'true') {
      return true;
    }
    const style = node.getAttribute ? node.getAttribute('style') : '';
    if (style && /display\s*:\s*none/i.test(style)) {
      return true;
    }
    const classes = node.getAttribute ? node.getAttribute('class') : '';
    if (classes && /(^|\s)(d-none|ng-hide|hidden)(\s|$)/.test(classes)) {
      return true;
    }
    node = node.parentElement;
  }
  return false;
}

function processIdFromRow(row) {
  const anchor = row.querySelector('.cel-processo a[href]');
  if (!anchor) {
    return '';
  }
  const href = anchor.getAttribute('href') || '';
  const match = /#\/dashboard\/processos\/(\d{1,12})(?:$|[/?#])/.exec(href);
  return match ? match[1] : '';
}

function statusFromRow(row) {
  const cell = row.querySelector('.cel-acoes') || row;
  if (cell.querySelector('.' + PENDING_CLASS)) {
    return 'pending';
  }
  if (cell.querySelector('.' + COMPLETED_CLASS)) {
    return 'completed';
  }
  return 'unknown';
}

export function readListContext(doc) {
  if (!parseListRoute(locationHref(doc))) {
    return null;
  }
  const parts = [];
  let observed = 0;
  for (const name of CONTEXT_SELECTS) {
    const field = doc.querySelector('tce-select-field[formcontrolname="' + name + '"]');
    if (!field) {
      continue;
    }
    observed += 1;
    parts.push(name + '=' + normalizeLabel(field.textContent || ''));
  }
  for (const name of CONTEXT_CHECKBOXES) {
    const field = doc.querySelector('tce-checkbox-field[formcontrolname="' + name + '"]');
    if (!field) {
      continue;
    }
    observed += 1;
    const input = field.querySelector('input[type="checkbox"]');
    parts.push(name + '=' + (input && input.checked ? '1' : '0'));
  }
  if (observed === 0) {
    return null;
  }
  return hashString(parts.join('|'));
}

/**
 * Lê somente a página atual da listagem do e-Contas, usando o contrato observado no QA:
 * tce-table#tabela-processos-consulta-id, link #/dashboard/processos/<id> e
 * as classes complemento-ato-pendente / complemento-ato-completo.
 * Nunca usa cor isolada, nunca lê outras páginas e falha fechado sem tabela ou sem linhas.
 */
export function readVisibleList(doc) {
  if (!parseListRoute(locationHref(doc))) {
    return { ok: false, code: 'NOT_LIST_ROUTE', contextKey: null, entries: [], hasPagination: false };
  }
  const table = doc.querySelector('#' + LIST_TABLE_ID) || doc.querySelector('tce-table#' + LIST_TABLE_ID);
  if (!table) {
    return { ok: false, code: 'LIST_TABLE_NOT_FOUND', contextKey: null, entries: [], hasPagination: false };
  }
  const contextKey = readListContext(doc);
  const hasPagination = Boolean(table.querySelector('.ngx-pagination, pagination-controls'));
  const entries = [];
  const seen = new Set();
  for (const row of table.querySelectorAll('tbody tr')) {
    if (isHidden(row)) {
      continue;
    }
    const processId = processIdFromRow(row);
    if (!processId || seen.has(processId)) {
      continue;
    }
    seen.add(processId);
    const labelCell = row.querySelector('.cel-processo');
    entries.push({
      processId,
      processLabel: normalizeProcessLabel(labelCell ? labelCell.textContent : ''),
      status: statusFromRow(row),
    });
  }
  if (entries.length === 0) {
    return { ok: false, code: 'EMPTY_LIST', contextKey, entries: [], hasPagination };
  }
  return { ok: true, contextKey, entries, hasPagination };
}
