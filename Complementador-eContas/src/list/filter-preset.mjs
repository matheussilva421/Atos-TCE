export const FILTER_PRESET_KEY = 'complementadorFilterPreset';
export const FILTER_ROUTES = Object.freeze(['processos-no-setor', 'meus-processos']);

export function routeKeyFor(href) {
  const value = String(href || '');
  if (value.includes('/dashboard/meus/meus-processos')) {
    return 'meus-processos';
  }
  return 'processos-no-setor';
}

export function isKnownPresetRoute(value) {
  return FILTER_ROUTES.includes(value);
}

export function presetKeyFor(route) {
  return route === 'meus-processos'
    ? FILTER_PRESET_KEY + ':meus-processos'
    : FILTER_PRESET_KEY;
}

function clean(value) {
  return String(value || '').replace(/[×✕]/g, ' ').replace(/\s+/g, ' ').trim();
}

function selectedLabel(field) {
  if (!field) return '';
  const label = field.querySelector('.ng-value-label');
  if (label) return clean(label.textContent);
  const value = field.querySelector('.ng-value');
  return value ? clean(value.textContent) : '';
}

export function readFilterPreset(doc, now = () => Date.now()) {
  const selects = [];
  for (const field of doc.querySelectorAll('tce-select-field[formcontrolname]')) {
    const name = field.getAttribute('formcontrolname');
    const value = selectedLabel(field);
    if (name && value) selects.push({ name, value });
  }
  const checkboxes = [];
  for (const field of doc.querySelectorAll('tce-checkbox-field[formcontrolname]')) {
    const name = field.getAttribute('formcontrolname');
    const input = field.querySelector('input[type="checkbox"]');
    if (name && input) checkboxes.push({ name, checked: Boolean(input.checked) });
  }
  return { selects, checkboxes, savedAt: now() };
}

export function filterPresetIsUsable(preset) {
  return Boolean(preset
    && Array.isArray(preset.selects)
    && Array.isArray(preset.checkboxes)
    && (preset.selects.length > 0 || preset.checkboxes.length > 0));
}

export function sanitizePreset(value) {
  if (!value || typeof value !== 'object') return null;
  const selects = (Array.isArray(value.selects) ? value.selects : [])
    .filter((item) => item && typeof item.name === 'string' && typeof item.value === 'string')
    .filter((item) => /^[A-Za-z0-9_]{1,40}$/.test(item.name) && item.value.length > 0 && item.value.length <= 80)
    .slice(0, 20)
    .map((item) => ({ name: item.name, value: item.value }));
  const checkboxes = (Array.isArray(value.checkboxes) ? value.checkboxes : [])
    .filter((item) => item && typeof item.name === 'string' && /^[A-Za-z0-9_]{1,40}$/.test(item.name))
    .slice(0, 30)
    .map((item) => ({ name: item.name, checked: Boolean(item.checked) }));
  if (selects.length === 0 && checkboxes.length === 0) return null;
  return { selects, checkboxes };
}

function optionMatches(optionText, wanted) {
  return clean(optionText).toLowerCase() === clean(wanted).toLowerCase();
}

async function activateSelect(doc, name, wanted, sleep) {
  const field = doc.querySelector('tce-select-field[formcontrolname="' + name + '"]');
  if (!field) return false;
  if (selectedLabel(field).toLowerCase() === clean(wanted).toLowerCase()) return true;
  const container = field.querySelector('.ng-select-container');
  if (!container) return false;
  const view = field.ownerDocument ? field.ownerDocument.defaultView : null;
  const MouseEventCtor = (view && view.MouseEvent)
    || (typeof MouseEvent !== 'undefined' ? MouseEvent : null);
  if (!MouseEventCtor) return false;
  container.dispatchEvent(new MouseEventCtor('mousedown', { bubbles: true }));
  container.dispatchEvent(new MouseEventCtor('click', { bubbles: true }));
  await sleep(300);
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const panels = [...doc.querySelectorAll('.ng-dropdown-panel')]
      .filter((panel) => panel.offsetParent !== null || panel.querySelector('.ng-option'));
    const panel = panels[panels.length - 1];
    if (panel) {
      const option = [...panel.querySelectorAll('.ng-option')]
        .find((candidate) => optionMatches(candidate.textContent, wanted));
      if (option) {
        option.click();
        await sleep(200);
        return true;
      }
    }
    const input = field.querySelector('input');
    if (input && attempt === 0) {
      input.value = wanted;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    await sleep(300);
  }
  return false;
}

export async function applyFilterPreset(doc, preset, deps = {}) {
  if (!filterPresetIsUsable(preset)) {
    return { ok: false, code: 'NO_PRESET' };
  }
  const sleep = deps.sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const hiddenSelect = preset.selects.some((item) => {
    const field = doc.querySelector('tce-select-field[formcontrolname="' + item.name + '"]');
    return field && field.offsetParent === null;
  });
  if (hiddenSelect) {
    const expand = [...doc.querySelectorAll('button')]
      .find((button) => /Visualizar Opções de Filtro/i.test(button.textContent || ''));
    if (expand) {
      expand.click();
      await sleep(500);
    }
  }
  const failed = [];
  for (const item of preset.selects) {
    const ok = await activateSelect(doc, item.name, item.value, sleep);
    if (!ok) failed.push(item.name);
  }
  for (const item of preset.checkboxes) {
    const field = doc.querySelector('tce-checkbox-field[formcontrolname="' + item.name + '"]');
    const input = field ? field.querySelector('input[type="checkbox"]') : null;
    if (input && Boolean(input.checked) !== item.checked) {
      input.click();
    }
  }
  const search = deps.search === false
    ? null
    : [...doc.querySelectorAll('button')]
      .find((button) => /^BUSCAR$/i.test(clean(button.textContent)));
  if (search) {
    search.click();
    await sleep(800);
  }
  return { ok: failed.length === 0, failed };
}
