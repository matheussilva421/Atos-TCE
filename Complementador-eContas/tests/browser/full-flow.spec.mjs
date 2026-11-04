import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PROCESS_ID,
  clickDiagnostic,
  clickFill,
  launchExtension,
  openAutosPage,
  openFormPage,
  readFields,
  readUi,
  startFixtureServer,
  waitForContentScript,
  waitForResult,
  waitForServiceWorker,
} from './harness.mjs';

async function withStack(fn, serverOptions = {}) {
  const server = await startFixtureServer(serverOptions);
  const extension = await launchExtension();
  try {
    await waitForServiceWorker(extension.context);
    return await fn(server, extension);
  } finally {
    await extension.close();
    await server.close();
  }
}

test('button_only_on_complement_route_and_no_read_before_click', async () => {
  await withStack(async (server, extension) => {
    const formPage = await openFormPage(extension.context, server.origin);
    const autosPage = await openAutosPage(extension.context, server.origin);
    const formHost = await formPage.evaluate(() => Boolean(document.querySelector('#complementador-econtas-root')));
    const autosHost = await autosPage.evaluate(() => Boolean(document.querySelector('#complementador-econtas-root')));
    assert.equal(formHost, true);
    assert.equal(autosHost, false);
    assert.equal(server.pdfResponseCount(), 0);
    await autosPage.close();
    await formPage.close();
  });
});

test('spa_push_state_injects_form_ui', async () => {
  await withStack(async (server, extension) => {
    const page = await extension.context.newPage();
    await page.goto(server.origin + '/#/dashboard/inicio', { waitUntil: 'domcontentloaded' });
    assert.equal(await waitForContentScript(page), true);
    assert.equal(await page.evaluate(() => Boolean(document.querySelector('#complementador-econtas-root'))), false);
    await page.evaluate((path) => history.pushState({}, '', path), '/#/dashboard/complementar-ato/' + PROCESS_ID);
    await page.waitForFunction(() => Boolean(document.querySelector('#complementador-econtas-root')), null, { timeout: 5000 });
    const buttons = await page.evaluate(() => {
      const host = document.querySelector('#complementador-econtas-root');
      return host && host.shadowRoot
        ? [...host.shadowRoot.querySelectorAll('button')].map((button) => button.textContent)
        : [];
    });
    assert.deepEqual(buttons, ['⚡ Preencher', 'Diagnóstico L1 (somente leitura)']);
    await page.close();
  });
});

test('spa_push_state_marks_autos_route', async () => {
  await withStack(async (server, extension) => {
    const page = await extension.context.newPage();
    await page.goto(server.origin + '/autos#/dashboard/inicio', { waitUntil: 'domcontentloaded' });
    assert.equal(await waitForContentScript(page), true);
    assert.equal(await page.evaluate(() => document.documentElement.getAttribute('data-complementador-autos')), null);
    await page.evaluate((path) => history.pushState({}, '', path), '/autos#/dashboard/processos/' + PROCESS_ID + '/autos');
    await page.waitForFunction(() => document.documentElement.getAttribute('data-complementador-autos') === 'ready', null, { timeout: 5000 });
    assert.equal(await page.evaluate(() => document.documentElement.getAttribute('data-complementador-autos')), 'ready');
    await page.close();
  });
});

test('spa_replace_state_and_hashchange_inject_form_ui', async () => {
  await withStack(async (server, extension) => {
    const replacePage = await extension.context.newPage();
    await replacePage.goto(server.origin + '/#/dashboard/inicio', { waitUntil: 'domcontentloaded' });
    assert.equal(await waitForContentScript(replacePage), true);
    assert.equal(await replacePage.evaluate(() => Boolean(document.querySelector('#complementador-econtas-root'))), false);
    await replacePage.evaluate(() => history.replaceState({}, '', '/#/dashboard/complementar-ato/' + '999001'));
    const replaceVisible = await replacePage.waitForFunction(
      () => Boolean(document.querySelector('#complementador-econtas-root')),
      null,
      { timeout: 5000 },
    ).then(() => true).catch(() => false);
    assert.equal(replaceVisible, true, 'replaceState deve injetar o painel');
    await replacePage.close();

    const hashPage = await extension.context.newPage();
    await hashPage.goto(server.origin + '/#/dashboard/inicio', { waitUntil: 'domcontentloaded' });
    assert.equal(await waitForContentScript(hashPage), true);
    assert.equal(await hashPage.evaluate(() => Boolean(document.querySelector('#complementador-econtas-root'))), false);
    await hashPage.evaluate(() => { location.hash = '#/dashboard/complementar-ato/999001'; });
    const hashVisible = await hashPage.waitForFunction(
      () => Boolean(document.querySelector('#complementador-econtas-root')),
      null,
      { timeout: 5000 },
    ).then(() => true).catch(() => false);
    assert.equal(hashVisible, true, 'hashchange deve injetar o painel');
    await hashPage.close();
  });
});

test('spa_leave_route_hides_form_ui', async () => {
  await withStack(async (server, extension) => {
    const page = await openFormPage(extension.context, server.origin);
    await page.evaluate(() => history.pushState({}, '', '/#/dashboard/inicio'));
    const hidden = await page.waitForFunction(() => {
      const host = document.querySelector('#complementador-econtas-root');
      return Boolean(host && host.style.display === 'none');
    }, null, { timeout: 5000 }).then(() => true).catch(() => false);
    assert.equal(hidden, true, 'sair da rota deve ocultar o painel');
    await page.close();
  });
});

test('full_click_to_read_to_fill', async () => {
  await withStack(async (server, extension) => {
    const formPage = await openFormPage(extension.context, server.origin);
    const autosPage = await openAutosPage(extension.context, server.origin);
    assert.equal(server.pdfResponseCount(), 0);
    await clickFill(formPage);
    const ui = await waitForResult(formPage);
    const fields = await readFields(formPage);
    assert.equal(ui.tone, 'ok', JSON.stringify(ui));
    assert.equal(ui.sourceVisible, true);
    assert.equal(ui.lastSourceNote, 'data da resolução administrativa');
    assert.equal(fields.dataDoeEstado, '07/11/2025');
    assert.equal(fields.cargo, 'ANALISTA DE TESTES');
    assert.equal(fields.matricula, '001234-5/1');
    assert.equal(fields.dataNascimento, '01/02/1980');
    assert.equal(fields.modalidade, 'Aposentadoria voluntária por tempo de contribuição com proventos integrais');
    assert.equal(server.pdfResponseCount(), 1);
    assert.equal(server.requests.some((entry) => entry.method === 'POST' || entry.method === 'PUT'), false);
    await autosPage.close();
    await formPage.close();
  });
});

test('two_source_tabs_are_ambiguous', async () => {
  await withStack(async (server, extension) => {
    const formPage = await openFormPage(extension.context, server.origin);
    const first = await openAutosPage(extension.context, server.origin);
    const second = await openAutosPage(extension.context, server.origin);
    await clickFill(formPage);
    const ui = await waitForResult(formPage);
    assert.equal(ui.tone, 'error');
    assert.match(ui.status, /mais de uma aba/i);
    assert.equal(server.pdfResponseCount(), 0);
    await second.close();
    await first.close();
    await formPage.close();
  });
});

test('different_process_is_rejected', async () => {
  await withStack(async (server, extension) => {
    const formPage = await openFormPage(extension.context, server.origin);
    const autosPage = await openAutosPage(extension.context, server.origin, '999002');
    await clickFill(formPage);
    const ui = await waitForResult(formPage);
    assert.equal(ui.tone, 'error');
    assert.match(ui.status, /mesmo processo/i);
    assert.equal(server.pdfResponseCount(), 0);
    await autosPage.close();
    await formPage.close();
  });
});

test('document_switch_aborts_without_write', async () => {
  const server = await startFixtureServer({ pdfDelayMs: 300 });
  const extension = await launchExtension();
  try {
    await waitForServiceWorker(extension.context);
    const formPage = await openFormPage(extension.context, server.origin);
    const autosPage = await openAutosPage(extension.context, server.origin);
    await clickFill(formPage);
    await new Promise((resolve) => setTimeout(resolve, 60));
    await autosPage.evaluate((path) => {
      document.querySelector('#ifrm').src = path;
    }, server.origin + server.secondPdfPath);
    const ui = await waitForResult(formPage);
    const fields = await readFields(formPage);
    assert.equal(ui.tone, 'error', JSON.stringify(ui));
    assert.match(ui.status, /documento mudou/i);
    assert.equal(fields.dataDoeEstado, '');
    assert.equal(fields.cargo, '');
    assert.equal(fields.matricula, '');
    assert.equal(fields.dataNascimento, '');
    await autosPage.close();
    await formPage.close();
  } finally {
    await extension.close();
    await server.close();
  }
});

test('readonly_and_existing_values_preserved', async () => {
  await withStack(async (server, extension) => {
    const formPage = await openFormPage(extension.context, server.origin);
    const autosPage = await openAutosPage(extension.context, server.origin);
    await formPage.evaluate(() => {
      const cargo = document.querySelector('tce-input-field[formcontrolname="cargo"] input');
      cargo.value = 'CARGO EXISTENTE';
      const matricula = document.querySelector('tce-input-field[formcontrolname="matricula"] input');
      matricula.value = '000001-2';
      matricula.readOnly = true;
    });
    await clickFill(formPage);
    const ui = await waitForResult(formPage);
    const fields = await readFields(formPage);
    assert.equal(ui.tone, 'ok', JSON.stringify(ui));
    assert.equal(fields.cargo, 'CARGO EXISTENTE');
    assert.equal(fields.matricula, '000001-2');
    assert.equal(fields.dataDoeEstado, '07/11/2025');
    assert.equal(fields.dataNascimento, '01/02/1980');
    assert.equal(server.requests.some((entry) => entry.method === 'POST' || entry.method === 'PUT'), false);
    await autosPage.close();
    await formPage.close();
  });
});
test('l1_diagnostic_reads_without_writing', async () => {
  await withStack(async (server, extension) => {
    const formPage = await openFormPage(extension.context, server.origin);
    const autosPage = await openAutosPage(extension.context, server.origin);
    await clickDiagnostic(formPage);
    const ui = await waitForResult(formPage);
    const fields = await readFields(formPage);
    assert.equal(ui.lastStatus, 'diagnostic', JSON.stringify(ui));
    assert.match(ui.status, /Diagnóstico L1/i);
    assert.match(ui.status, /1 página/i);
    assert.equal(fields.dataDoeEstado, '');
    assert.equal(fields.cargo, '');
    assert.equal(fields.matricula, '');
    assert.equal(fields.dataNascimento, '');
    assert.equal(server.pdfResponseCount(), 1);
    assert.equal(server.requests.some((entry) => entry.method === 'POST' || entry.method === 'PUT'), false);
    await autosPage.close();
    await formPage.close();
  });
});
test('l1_diagnostic_multi_page', async () => {
  await withStack(async (server, extension) => {
    const formPage = await openFormPage(extension.context, server.origin);
    const autosPage = await openAutosPage(extension.context, server.origin);
    await clickDiagnostic(formPage);
    const ui = await waitForResult(formPage);
    const fields = await readFields(formPage);
    assert.equal(ui.lastStatus, 'diagnostic', JSON.stringify(ui));
    assert.match(ui.status, /2 página/i);
    assert.equal(fields.dataDoeEstado, '');
    assert.equal(fields.cargo, '');
    assert.equal(fields.matricula, '');
    assert.equal(fields.dataNascimento, '');
    assert.equal(server.pdfResponseCount(), 1);
    await autosPage.close();
    await formPage.close();
  }, { pdfPages: ['PAGINA UM', 'PAGINA DOIS'] });
});
test('synthetic_click_does_not_start_fill', async () => {
  await withStack(async (server, extension) => {
    const formPage = await openFormPage(extension.context, server.origin);
    const autosPage = await openAutosPage(extension.context, server.origin);
    await formPage.evaluate(() => {
      const host = document.querySelector('#complementador-econtas-root');
      host.shadowRoot.querySelector('button').click();
    });
    await new Promise((resolve) => setTimeout(resolve, 300));
    const ui = await readUi(formPage);
    const fields = await readFields(formPage);
    assert.notEqual(ui.lastStatus, 'running');
    assert.notEqual(ui.lastStatus, 'ok');
    assert.equal(fields.dataDoeEstado, '');
    assert.equal(fields.cargo, '');
    assert.equal(server.pdfResponseCount(), 0);
    await autosPage.close();
    await formPage.close();
  });
});
test('l1_result_recovered_after_form_reload', async () => {
  await withStack(async (server, extension) => {
    const formPage = await openFormPage(extension.context, server.origin);
    const autosPage = await openAutosPage(extension.context, server.origin);
    await clickDiagnostic(formPage);
    await new Promise((resolve) => setTimeout(resolve, 150));
    await formPage.reload();
    await formPage.waitForFunction(() => Boolean(document.querySelector('#complementador-econtas-root')), null, { timeout: 15000 });
    await formPage.waitForFunction(() => {
      const host = document.querySelector('#complementador-econtas-root');
      return Boolean(host && host.dataset.lastDiagnosticState === 'L1_SUCCESS');
    }, null, { timeout: 20000 });
    const recovered = await formPage.evaluate(() => {
      const host = document.querySelector('#complementador-econtas-root');
      const root = host.shadowRoot;
      return {
        state: host.dataset.lastDiagnosticState || '',
        pages: host.dataset.lastDiagnosticPages || '',
        chars: host.dataset.lastDiagnosticChars || '',
        elapsed: host.dataset.lastDiagnosticElapsed || '',
        panel: root.querySelector('.diagnostic') ? root.querySelector('.diagnostic').textContent : '',
      };
    });
    const fields = await readFields(formPage);
    assert.equal(recovered.state, 'L1_SUCCESS');
    assert.equal(recovered.pages, '1');
    assert.ok(Number(recovered.chars) > 0);
    assert.match(recovered.panel, /L1_SUCCESS/);
    assert.equal(fields.dataDoeEstado, '');
    assert.equal(fields.cargo, '');
    assert.equal(fields.matricula, '');
    assert.equal(fields.dataNascimento, '');
    assert.equal(server.requests.some((entry) => entry.method === 'POST' || entry.method === 'PUT'), false);
    await autosPage.close();
    await formPage.close();
  });
});

test('birth_date_from_guia_document', async () => {
  await withStack(async (server, extension) => {
    const sw = await waitForServiceWorker(extension.context);
    await sw.evaluate(() => chrome.storage.session.clear());
    const formPage = await openFormPage(extension.context, server.origin);
    const autosPage = await openAutosPage(extension.context, server.origin);
    const initialSrc = await autosPage.evaluate(() => document.querySelector('#ifrm').src);
    await clickFill(formPage);
    const ui = await waitForResult(formPage, 40000);
    const fields = await readFields(formPage);
    assert.equal(ui.tone, 'ok', JSON.stringify(ui));
    assert.equal(fields.dataDoeEstado, '07/11/2025');
    assert.equal(fields.cargo, 'ANALISTA DE TESTES');
    assert.equal(fields.matricula, '001234-5/1');
    assert.equal(fields.dataNascimento, '01/02/1980');
    assert.equal(fields.modalidade, 'Aposentadoria voluntária por tempo de contribuição com proventos integrais');
    assert.match(ui.source || '', /Guia Financeira/i);
    assert.equal(server.requests.some((entry) => entry.url === server.guiaPath), true);
    const restoredSrc = await autosPage.evaluate(() => document.querySelector('#ifrm').src);
    assert.equal(restoredSrc, initialSrc);
    assert.equal(server.requests.some((entry) => entry.method === 'POST' || entry.method === 'PUT'), false);
    await autosPage.close();
    await formPage.close();
  }, {
    scanEvents: true,
    resolutionText: 'RESOLUCAO ADMINISTRATIVA N. 1234, DE 7 DE NOVEMBRO DE 2025. RESOLVE conceder aposentadoria voluntaria por tempo de contribuicao com proventos integrais a PESSOA UM, no cargo de ANALISTA DE TESTES, matricula 001234-5/1. Natal, 7 de novembro de 2025.',
  });
});
