import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { FormError, readForm } from '../../src/form/form-reader.mjs';
import { applyFillPlan, createFillPlan } from '../../src/form/form-writer.mjs';

const html = (name) => readFileSync(new URL('../fixtures/' + name, import.meta.url), 'utf8');

function load(name = 'form-complemento.html') {
  const dom = new JSDOM(html(name), {
    url: 'https://processos.tce.rn.gov.br/#/dashboard/complementar-ato/999001',
    runScripts: 'dangerously',
  });
  return { dom, doc: dom.window.document };
}

function proposals(overrides = {}) {
  return {
    modalidade: { status: 'exact', value: 'Aposentadoria voluntária por tempo de contribuição com proventos integrais' },
    dataDoeEstado: { status: 'exact', value: '07/11/2025', source: 'data da resolução administrativa' },
    cargo: { status: 'exact', value: 'ANALISTA DE TESTES' },
    matricula: { status: 'exact', value: '001234-5/1' },
    dataNascimento: { status: 'exact', value: '01/02/1980' },
    ...overrides,
  };
}

test('four_fields_and_unique_modality_are_filled', () => {
  const { doc } = load();
  const plan = createFillPlan(proposals(), readForm(doc));
  assert.equal(plan.modality.action, 'fill');
  assert.equal(plan.fields.cargo.action, 'fill');
  assert.equal(plan.fields.matricula.action, 'fill');
  assert.equal(plan.fields.dataDoeEstado.action, 'fill');
  assert.equal(plan.fields.dataNascimento.action, 'fill');
  assert.equal(plan.sourceNotes.dataDoeEstado, 'Origem: data da resolução administrativa');
});

test('existing_or_readonly_values_preserved', () => {
  const { doc } = load();
  const cargo = doc.querySelector('tce-input-field[formcontrolname="cargo"] input');
  cargo.value = 'CARGO EXISTENTE';
  const matricula = doc.querySelector('tce-input-field[formcontrolname="matricula"] input');
  matricula.value = '000001-2';
  matricula.readOnly = true;
  const plan = createFillPlan(proposals(), readForm(doc));
  assert.equal(plan.fields.cargo.action, 'preserve');
  assert.equal(plan.fields.cargo.reason, 'EXISTING_VALUE');
  assert.equal(plan.fields.matricula.action, 'preserve');
  assert.equal(plan.fields.matricula.reason, 'READONLY');
});

test('unique_catalog_option_only', () => {
  const { doc } = load();
  const first = [...doc.querySelectorAll('.ng-option')].find((option) => option.textContent.includes('voluntária por tempo de contribuição'));
  first.parentElement.appendChild(first.cloneNode(true));
  const plan = createFillPlan(proposals(), readForm(doc));
  assert.equal(plan.modality.action, 'skip');
  assert.equal(plan.modality.reason, 'MODALITY_AMBIGUOUS');
});

test('datepicker_readback_matches_ui', async () => {
  const { doc } = load();
  const form = readForm(doc);
  const plan = createFillPlan(proposals(), form);
  const report = await applyFillPlan(doc, plan, {
    processId: form.processId,
    interestedKey: form.interestedKey,
    revisionMarker: form.revisionMarker,
  });
  assert.equal(report.ok, true);
  assert.equal(doc.querySelector('tce-input-field[formcontrolname="dataDoeEstado"] input').value, '07/11/2025');
  assert.equal(doc.querySelector('tce-input-field[formcontrolname="cargo"] input').value, 'ANALISTA DE TESTES');
  assert.equal(doc.querySelector('tce-input-field[formcontrolname="matricula"] input').value, '001234-5/1');
  assert.equal(doc.querySelector('tce-input-field[formcontrolname="dataNascimento"] input').value, '01/02/1980');
  assert.equal(doc.querySelector('.ng-value').textContent.trim(), 'Aposentadoria voluntária por tempo de contribuição com proventos integrais');
  assert.ok(doc.querySelector('tce-input-field[formcontrolname="dataDoeEstado"] input').hasAttribute('bsdatepicker'));
});

test('async_form_marker_after_write_does_not_block_remaining_fields', async () => {
  const { doc } = load();
  const form = readForm(doc);
  const plan = createFillPlan(proposals(), form);
  let pendingMarker = null;
  const cargo = doc.querySelector('tce-input-field[formcontrolname="cargo"] input');
  cargo.addEventListener('change', () => {
    pendingMarker = 'async-marker-after-cargo-write';
  });
  const read = (document) => {
    const current = readForm(document);
    if (pendingMarker) {
      const marker = pendingMarker;
      pendingMarker = null;
      return { ...current, revisionMarker: marker };
    }
    return current;
  };
  const report = await applyFillPlan(doc, plan, {
    processId: form.processId,
    interestedKey: form.interestedKey,
    revisionMarker: form.revisionMarker,
  }, { readForm: read, wait: async () => {} });
  assert.equal(report.ok, true);
  assert.equal(report.filled.length, 5);
  assert.equal(doc.querySelector('tce-input-field[formcontrolname="matricula"] input').value, '001234-5/1');
  assert.equal(doc.querySelector('tce-input-field[formcontrolname="dataNascimento"] input').value, '01/02/1980');
});

test('async_modality_readback_is_waited_for', async () => {
  const { doc } = load();
  const form = readForm(doc);
  const plan = createFillPlan(proposals(), form);
  const original = [...doc.querySelectorAll('.ng-option')]
    .find((option) => option.textContent.includes('voluntária por tempo de contribuição'));
  const option = original.cloneNode(true);
  original.parentElement.replaceChild(option, original);
  option.addEventListener('click', () => {
    setTimeout(() => {
      const value = doc.querySelector('.ng-value');
      value.textContent = option.textContent.trim();
      value.style.display = 'block';
    }, 30);
  });
  const report = await applyFillPlan(doc, plan, {
    processId: form.processId,
    interestedKey: form.interestedKey,
    revisionMarker: form.revisionMarker,
  });
  assert.equal(report.ok, true, JSON.stringify(report.errors));
  assert.equal(report.filled[0].field, 'modalidade');
  assert.equal(doc.querySelector('tce-input-field[formcontrolname="cargo"] input').value, 'ANALISTA DE TESTES');
});

test('modality_readback_ignores_clear_icon', async () => {
  const { doc } = load();
  const form = readForm(doc);
  const plan = createFillPlan(proposals(), form);
  const value = doc.querySelector('ng-select .ng-value');
  const option = [...doc.querySelectorAll('.ng-option')]
    .find((item) => item.textContent.includes('voluntária por tempo de contribuição'));
  option.addEventListener('click', () => {
    value.innerHTML = '<span class="ng-value-label">' + option.textContent.trim() + '</span><span class="ng-value-icon">×</span>';
    value.style.display = 'block';
  });
  const report = await applyFillPlan(doc, plan, {
    processId: form.processId,
    interestedKey: form.interestedKey,
    revisionMarker: form.revisionMarker,
  });
  assert.equal(report.ok, true, JSON.stringify(report.errors));
  assert.equal(report.filled[0].field, 'modalidade');
  assert.equal(doc.querySelector('tce-input-field[formcontrolname="cargo"] input').value, 'ANALISTA DE TESTES');
});

test('wrong_interested_never_receives_values', async () => {
  const { doc } = load('form-multi-interested.html');
  const form = readForm(doc);
  const plan = createFillPlan(proposals(), form);
  const cards = [...doc.querySelectorAll('button.cartao-item')];
  cards[0].classList.remove('selecionada');
  cards[1].classList.add('selecionada');
  const report = await applyFillPlan(doc, plan, {
    processId: form.processId,
    interestedKey: form.interestedKey,
    revisionMarker: form.revisionMarker,
  });
  assert.equal(report.ok, false);
  assert.equal(report.errors[0].code, 'INTERESTED_CHANGED');
  assert.equal(doc.querySelector('tce-input-field[formcontrolname="cargo"] input').value, '');
});

test('recheck_identity_before_each_write', async () => {
  const { doc } = load('form-multi-interested.html');
  const form = readForm(doc);
  const plan = createFillPlan(proposals(), form);
  const firstInput = doc.querySelector('tce-input-field[formcontrolname="dataDoeEstado"] input');
  firstInput.addEventListener('change', () => {
    const cards = [...doc.querySelectorAll('button.cartao-item')];
    cards[0].classList.remove('selecionada');
    cards[1].classList.add('selecionada');
  });
  const report = await applyFillPlan(doc, plan, {
    processId: form.processId,
    interestedKey: form.interestedKey,
    revisionMarker: form.revisionMarker,
  });
  assert.equal(report.ok, false);
  assert.ok(report.errors.some((error) => error.code === 'INTERESTED_CHANGED'));
  assert.equal(doc.querySelector('tce-input-field[formcontrolname="cargo"] input').value, '');
});

test('no_submit_commands_or_network_writes', async () => {
  const { doc } = load();
  const form = readForm(doc);
  let submits = 0;
  doc.querySelectorAll('form').forEach((element) => element.addEventListener('submit', () => { submits += 1; }));
  const report = await applyFillPlan(doc, createFillPlan(proposals(), form), {
    processId: form.processId,
    interestedKey: form.interestedKey,
    revisionMarker: form.revisionMarker,
  });
  assert.equal(report.ok, true);
  assert.equal(submits, 0);
});
