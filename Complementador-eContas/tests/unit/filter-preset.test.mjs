import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import {
  applyFilterPreset,
  filterPresetIsUsable,
  readFilterPreset,
  presetKeyFor,
  routeKeyFor,
  sanitizePreset,
} from '../../src/list/filter-preset.mjs';

function doc(body) {
  return new JSDOM('<html><body>' + body + '</body></html>').window.document;
}

test('reads_selected_filters_only', () => {
  const document = doc(
    '<tce-select-field formcontrolname="idMarcador"><ng-select><span class="ng-value-label">Mutirão - Educação×</span></ng-select></tce-select-field>'
    + '<tce-select-field formcontrolname="atoComplementado"><ng-select><span class="ng-value-label">Não</span></ng-select></tce-select-field>'
    + '<tce-select-field formcontrolname="vazio"><ng-select></ng-select></tce-select-field>'
    + '<tce-checkbox-field formcontrolname="ProcessosNoSetor"><input type="checkbox" checked></tce-checkbox-field>'
    + '<tce-checkbox-field formcontrolname="semMarcador"><input type="checkbox"></tce-checkbox-field>',
  );
  const preset = readFilterPreset(document, () => 42);
  assert.deepEqual(preset.selects, [
    { name: 'idMarcador', value: 'Mutirão - Educação' },
    { name: 'atoComplementado', value: 'Não' },
  ]);
  assert.deepEqual(preset.checkboxes, [
    { name: 'ProcessosNoSetor', checked: true },
    { name: 'semMarcador', checked: false },
  ]);
  assert.equal(preset.savedAt, 42);
  assert.equal(filterPresetIsUsable(preset), true);
});

test('rejects_empty_or_malformed_preset', () => {
  assert.equal(filterPresetIsUsable(null), false);
  assert.equal(filterPresetIsUsable({ selects: [], checkboxes: [] }), false);
  const result = applyFilterPreset(doc('<div></div>'), null).then((value) => value);
  return result.then((value) => assert.equal(value.code, 'NO_PRESET'));
});

test('applies_selects_checkboxes_and_search', async () => {
  const document = doc(
    '<tce-select-field formcontrolname="idMarcador"><ng-select><div class="ng-select-container">'
    + '<input></div></ng-select></tce-select-field>'
    + '<tce-checkbox-field formcontrolname="ProcessosNoSetor"><input type="checkbox" checked></tce-checkbox-field>'
    + '<button>BUSCAR</button>',
  );
  const field = document.querySelector('tce-select-field');
  const ngSelect = field.querySelector('ng-select');
  let searched = 0;
  document.querySelector('button').addEventListener('click', () => { searched += 1; });
  ngSelect.querySelector('.ng-select-container').addEventListener('click', () => {
    if (document.querySelector('.ng-dropdown-panel')) return;
    const panel = document.createElement('div');
    panel.className = 'ng-dropdown-panel';
    for (const label of ['Outro', 'Mutirão - Educação']) {
      const option = document.createElement('div');
      option.className = 'ng-option';
      option.textContent = label;
      option.addEventListener('click', () => {
        field.querySelector('ng-select').innerHTML = '<span class="ng-value-label">' + label + '</span>';
      });
      panel.appendChild(option);
    }
    document.body.appendChild(panel);
  });
  const result = await applyFilterPreset(document, {
    selects: [{ name: 'idMarcador', value: 'Mutirão - Educação' }],
    checkboxes: [{ name: 'ProcessosNoSetor', checked: true }],
  }, { sleep: async () => {} });
  assert.equal(result.ok, true);
  assert.equal(searched, 1);
});

test('sanitizes_preset_payload', () => {
  assert.equal(sanitizePreset(null), null);
  assert.equal(sanitizePreset({ selects: [], checkboxes: [] }), null);
  const clean = sanitizePreset({
    selects: [
      { name: 'idMarcador', value: 'Mutirão - Educação' },
      { name: 'x'.repeat(60), value: 'fora' },
      { name: 'ok', value: '' },
    ],
    checkboxes: [{ name: 'ProcessosNoSetor', checked: 1 }],
    extra: 'ignorado',
  });
  assert.deepEqual(clean, {
    selects: [{ name: 'idMarcador', value: 'Mutirão - Educação' }],
    checkboxes: [{ name: 'ProcessosNoSetor', checked: true }],
  });
});

test('preset_keys_are_scoped_by_list_route', () => {
  const meus = 'https://processos.tce.rn.gov.br/#/dashboard/meus/meus-processos?setor=CBP';
  const setor = 'https://processos.tce.rn.gov.br/#/dashboard/processos-no-setor/no-setor';
  assert.equal(routeKeyFor(meus), 'meus-processos');
  assert.equal(routeKeyFor(setor), 'processos-no-setor');
  assert.equal(presetKeyFor('meus-processos'), 'complementadorFilterPreset:meus-processos');
  assert.equal(presetKeyFor('processos-no-setor'), 'complementadorFilterPreset');
});
