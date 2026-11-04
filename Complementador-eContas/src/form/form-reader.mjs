import { extractInterestedName, hashString, normalizeLabel, normalizeProcessLabel, normalizeText } from '../shared/identity.mjs';
import { parseRoute } from '../shared/routes.mjs';

export const FORM_ERROR = Object.freeze({
  FORM_NOT_LOADED: 'FORM_NOT_LOADED',
  INTERESTED_NOT_SELECTED: 'INTERESTED_NOT_SELECTED',
  FIELD_NOT_FOUND: 'FIELD_NOT_FOUND',
  INVALID_PROCESS: 'INVALID_PROCESS',
});

export const FIELD_NAMES = Object.freeze(['dataDoeEstado', 'cargo', 'matricula', 'dataNascimento']);

export class FormError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'FormError';
    this.code = code;
  }
}

function locationHref(doc) {
  return (doc && doc.location && doc.location.href)
    || (doc && doc.defaultView && doc.defaultView.location && doc.defaultView.location.href)
    || '';
}

function findField(doc, name) {
  return doc.querySelector('tce-input-field[formcontrolname="' + name + '"]')
    || doc.querySelector('[formcontrolname="' + name + '"]');
}

function findInput(doc, name) {
  const field = findField(doc, name);
  return field ? field.querySelector('input, textarea') : null;
}

export function readFormProcessLabel(doc) {
  const headings = [...doc.querySelectorAll('h1,h2,h3,h4')];
  const heading = headings.find((element) => /COMPLEMENTAR ATO\s*-\s*PROCESSO/i.test(element.textContent || ''));
  return normalizeProcessLabel(heading ? heading.textContent : '');
}
export function readCatalogFromDom(doc) {
  const scope = doc.querySelector('tce-select-field.modalidade-campo')
    || doc.querySelector('tce-select-field')
    || doc;
  return [...scope.querySelectorAll('.ng-option')].map((option, index) => ({
    id: option.id || hashString(normalizeText(option.textContent) + ':' + index),
    label: normalizeText(option.textContent),
    disabled: option.classList.contains('ng-option-disabled') || option.getAttribute('aria-disabled') === 'true',
  }));
}

function modalityScope(doc) {
  return doc.querySelector('tce-select-field.modalidade-campo') || doc.querySelector('tce-select-field');
}

export function readSelectedModalityLabel(ngSelect) {
  if (!ngSelect) {
    return '';
  }
  const label = ngSelect.querySelector('.ng-value-label');
  if (label) {
    return normalizeText(label.textContent || '');
  }
  const value = ngSelect.querySelector('.ng-value');
  if (!value) {
    return '';
  }
  const clone = value.cloneNode(true);
  if (clone.querySelectorAll) {
    for (const icon of clone.querySelectorAll('.ng-value-icon, .ng-clear-wrapper, .ng-clear')) {
      icon.remove();
    }
  }
  return normalizeText(clone.textContent || '').replace(/[×✕]/g, ' ').replace(/\s+/g, ' ').trim();
}

export function readForm(doc) {
  const route = parseRoute(locationHref(doc));
  if (!route || route.kind !== 'complemento') {
    throw new FormError(FORM_ERROR.FORM_NOT_LOADED, 'Formulário Complementar Ato não carregado.');
  }
  const cards = [...doc.querySelectorAll('button.cartao-item')];
  if (cards.length === 0) {
    throw new FormError(FORM_ERROR.FORM_NOT_LOADED, 'Pessoas do processo não localizadas.');
  }
  const selectedCards = cards.filter((card) => card.classList.contains('selecionada'));
  if (selectedCards.length !== 1) {
    throw new FormError(FORM_ERROR.INTERESTED_NOT_SELECTED, 'Selecione exatamente um interessado.');
  }
  const selectedIndex = cards.indexOf(selectedCards[0]);
  const interestedName = extractInterestedName(selectedCards[0].textContent || '');
  if (!interestedName) {
    throw new FormError(FORM_ERROR.INTERESTED_NOT_SELECTED, 'Interessado selecionado sem identificação.');
  }
  const interestedKey = hashString(normalizeLabel(interestedName));
  const values = {};
  const editable = {};
  const maxlength = {};
  for (const name of FIELD_NAMES) {
    const field = findField(doc, name);
    const input = findInput(doc, name);
    if (!input) {
      throw new FormError(FORM_ERROR.FORM_NOT_LOADED, 'Campo não localizado: ' + name);
    }
    values[name] = input.value || '';
    editable[name] = !input.readOnly && !input.disabled;
    const rawMax = input.getAttribute('maxlength') || (field && field.getAttribute('maxlength')) || '';
    maxlength[name] = rawMax ? Number(rawMax) : null;
  }
  const scope = modalityScope(doc);
  const ngSelect = scope ? scope.querySelector('ng-select') : null;
  const valueElement = ngSelect ? ngSelect.querySelector('.ng-value') : null;
  const modalitySelectedLabel = readSelectedModalityLabel(ngSelect);
  const modalitySelected = modalitySelectedLabel.length > 0
    && Boolean(valueElement)
    && (!valueElement.style || valueElement.style.display !== 'none');
  const modalities = readCatalogFromDom(doc);
  const revisionMarker = hashString([
    route.idProcesso,
    interestedKey,
    String(selectedIndex),
    ...FIELD_NAMES.map((name) => values[name]),
    modalitySelected ? modalitySelectedLabel : '',
    modalities.map((modality) => modality.label + ':' + (modality.disabled ? '1' : '0')).join('|'),
  ].join('|'));
  return {
    processId: route.idProcesso,
    processLabel: readFormProcessLabel(doc),
    interestedKey,
    interestedName,
    interestedIndex: selectedIndex,
    interestedCount: cards.length,
    values,
    editable,
    maxlength,
    modalities,
    modalitySelected,
    modalitySelectedLabel: modalitySelected ? modalitySelectedLabel : '',
    revisionMarker,
  };
}

export async function openModalityDropdown(doc, deps = {}) {
  const scope = modalityScope(doc);
  const ngSelect = scope ? scope.querySelector('ng-select') : null;
  if (!ngSelect) {
    return false;
  }
  const container = ngSelect.querySelector('.ng-select-container') || ngSelect;
  const view = doc.defaultView || undefined;
  const MouseEventCtor = (view && view.MouseEvent) || (typeof MouseEvent !== 'undefined' ? MouseEvent : null);
  if (!MouseEventCtor) { return false; }
  container.dispatchEvent(new MouseEventCtor('mousedown', { bubbles: true, cancelable: true, view }));
  container.dispatchEvent(new MouseEventCtor('click', { bubbles: true, cancelable: true, view }));
  const wait = deps.wait || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  await wait(60);
  return true;
}

export async function ensureModalityCatalog(doc, deps = {}) {
  if (readCatalogFromDom(doc).length > 0) {
    return true;
  }
  await openModalityDropdown(doc, deps);
  const wait = deps.wait || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  for (let attempt = 0; attempt < 8; attempt += 1) {
    if (readCatalogFromDom(doc).length > 0) {
      return true;
    }
    await wait(50);
  }
  return false;
}
