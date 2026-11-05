import http from 'node:http';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { chromium } from 'playwright';
import { makePdf } from '../helpers/make-pdf.mjs';

export const PROCESS_ID = '999001';
export const FORM_PATH = '/#/dashboard/complementar-ato/' + PROCESS_ID;
export const AUTOS_PATH = '/autos#/dashboard/processos/' + PROCESS_ID + '/autos';
const PDF_PATH = '/as/consultaprocessotemp/2026/11/3/11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222.pdf';
const GUIA_PATH = '/as/consultaprocessotemp/2026/11/3/55555555-5555-5555-5555-555555555555/66666666-6666-6666-6666-666666666666.pdf';
const OTHER_PATH = '/as/consultaprocessotemp/2026/11/3/77777777-7777-7777-7777-777777777777/88888888-8888-8888-8888-888888888888.pdf';

const RESOLUTION_TEXT = [
  'RESOLUCAO ADMINISTRATIVA N. 1234, DE 7 DE NOVEMBRO DE 2025.',
  'RESOLVE conceder aposentadoria voluntaria por tempo de contribuicao com proventos integrais a PESSOA UM, no cargo de ANALISTA DE TESTES, matricula 001234-5/1, nascida em 01/02/1980.',
  'Natal, 7 de novembro de 2025.',
].join(' ');

const RESOLUTION_TEXT_NO_BIRTH = [
  'RESOLUCAO ADMINISTRATIVA N. 1234, DE 7 DE NOVEMBRO DE 2025.',
  'RESOLVE conceder aposentadoria voluntaria por tempo de contribuicao com proventos integrais a PESSOA UM, no cargo de ANALISTA DE TESTES, matricula 001234-5/1.',
  'Natal, 7 de novembro de 2025.',
].join(' ');

const GUIA_TEXT = [
  'Guia Financeira/Taxacao de Proventos',
  'Processo N. 999001',
  'Segurado: PESSOA UM',
  'Data de Nascimento: 01/02/1980',
  'Assunto: NOVO FLUXO DE APOSENTADORIA POR TEMPO DE CONTRIBUICAO',
].join(' ');

const OTHER_TEXT = 'Documento diverso do processo, sem resolução administrativa ou guia financeira.';

export async function startFixtureServer(options = {}) {
  const formHtml = await readFile(new URL('../fixtures/form-complemento.html', import.meta.url), 'utf8');
  const listHtml = await readFile(new URL('../fixtures/batch/list.html', import.meta.url), 'utf8');
  const listFiltersHtml = await readFile(new URL('../fixtures/batch/list-filters.html', import.meta.url), 'utf8');
  const requests = [];
  const resolutionPages = options.resolutionPages || options.pdfPages || [options.resolutionText || RESOLUTION_TEXT];
  const pdfBytes = makePdf(resolutionPages);
  const guiaBytes = makePdf(options.guiaPages || [options.guiaText || GUIA_TEXT]);
  const otherBytes = makePdf([options.otherText || OTHER_TEXT]);
  const delayMs = options.pdfDelayMs || 0;
  let pdfResponseCount = 0;
  const server = http.createServer((request, response) => {
    requests.push({ method: request.method, url: request.url, dest: request.headers['sec-fetch-dest'] || null, mode: request.headers['sec-fetch-mode'] || null });
    const url = new URL(request.url, 'http://127.0.0.1');
    if (url.pathname === '/' || url.pathname === '/complementar') {
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
      response.end(formHtml);
      return;
    }
    if (url.pathname === '/autos') {
      const origin = 'http://127.0.0.1:' + server.address().port;
      if (options.scanEvents) {
        const initialPath = options.initialDocument === 'guia'
          ? GUIA_PATH
          : (options.initialDocument === 'other' ? OTHER_PATH : PDF_PATH);
        const html = '<!doctype html><html><body><h4>AUTOS DO PROCESSO 999001 / 2026</h4>'
          + '<div class="card-event" id="event-0" data-id="event-0" data-pdf="' + origin + PDF_PATH + '">Evento 0 - Resolucao</div>'
          + '<div class="card-event" id="event-1" data-id="event-1" data-pdf="' + origin + GUIA_PATH + '">Evento 1 - Guia</div>'
          + '<div class="card-event" id="event-2" data-id="event-2" data-pdf="' + origin + OTHER_PATH + '">Evento 2 - Outro</div>'
          + '<iframe id="ifrm" title="iframe de anexo" src="' + origin + initialPath + '"></iframe>'
          + '<script>document.querySelectorAll(".card-event").forEach(function (card) { card.addEventListener("click", function () { document.querySelectorAll(".card-event").forEach(function (other) { other.classList.toggle("escurecer", other === card); }); var frame = document.querySelector("#ifrm"); if (frame && card.dataset.pdf) frame.src = card.dataset.pdf; }); });</script>'
          + '</body></html>';
        response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
        response.end(html);
        return;
      }
      const html = '<!doctype html><html><body><h4>AUTOS DO PROCESSO 999001 / 2026</h4>'
        + '<iframe id="ifrm" title="iframe de anexo" src="' + origin + PDF_PATH + '"></iframe>'
        + '</body></html>';
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
      response.end(html);
      return;
    }
    if (url.pathname === '/lista') {
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
      response.end(listHtml);
      return;
    }
    if (url.pathname === '/lista-filtros') {
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
      response.end(listFiltersHtml);
      return;
    }
    if (url.pathname.startsWith('/as/consultaprocessotemp/')) {
      pdfResponseCount += 1;
      const send = () => {
        const body = url.pathname === GUIA_PATH
          ? guiaBytes
          : (url.pathname === OTHER_PATH ? otherBytes : pdfBytes);
        response.writeHead(200, { 'content-type': 'application/pdf', 'content-length': String(body.length) });
        response.end(Buffer.from(body));
      };
      if (delayMs > 0) {
        setTimeout(send, delayMs);
      } else {
        send();
      }
      return;
    }
    response.writeHead(404);
    response.end('not found');
  });
  const port = options.port || 4173;
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', resolve);
  });
  const origin = 'http://127.0.0.1:' + server.address().port;
  return {
    server,
    origin,
    requests,
    pdfPath: PDF_PATH,
    guiaPath: GUIA_PATH,
    otherPath: OTHER_PATH,
    pdfBytesLength: pdfBytes.length,
    secondPdfPath: '/as/consultaprocessotemp/2026/11/3/33333333-3333-3333-3333-333333333333/44444444-4444-4444-4444-444444444444.pdf',
    pdfResponseCount: () => requests.filter((entry) => entry.url.startsWith('/as/consultaprocessotemp/') && entry.dest !== 'iframe').length,
    pdfAllCount: () => pdfResponseCount,
    close: () => {
      if (typeof server.closeAllConnections === 'function') {
        server.closeAllConnections();
      }
      return new Promise((resolve) => server.close(resolve));
    },
  };
}

export async function launchExtension() {
  const userDataDir = await mkdtemp(path.join(os.tmpdir(), 'econtas-'));
  const extensionPath = path.resolve('dist-test');
  const executablePath = process.env.TEST_BROWSER_EXECUTABLE || '';
  const args = [
    '--disable-extensions-except=' + extensionPath,
    '--load-extension=' + extensionPath,
    '--no-first-run',
    '--no-default-browser-check',
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-features=BlockInsecurePrivateNetworkRequests',
  ];
  if (!executablePath) {
    const context = await chromium.launchPersistentContext(userDataDir, {
      channel: process.env.TEST_BROWSER_CHANNEL || 'msedge',
      headless: true,
      args,
    });
    context.on('serviceworker', () => {});
    return {
      context,
      userDataDir,
      close: async () => {
        await context.close().catch(() => {});
        await rm(userDataDir, { recursive: true, force: true }).catch(() => {});
      },
    };
  }

  const headless = process.env.TEST_BROWSER_HEADLESS !== 'false';
  if (headless) {
    args.push('--headless=new');
  } else {
    args.push('--window-size=1280,900');
  }
  args.push('--remote-debugging-port=0', 'about:blank');
  const child = spawn(executablePath, args, {
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: headless,
  });
  let stderr = '';
  child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
  const portFile = path.join(userDataDir, 'DevToolsActivePort');
  let port = null;
  for (let attempt = 0; attempt < 200; attempt += 1) {
    try {
      const text = await readFile(portFile, 'utf8');
      const first = text.split(/\r?\n/)[0];
      const parsed = Number(first);
      if (Number.isInteger(parsed) && parsed > 0) {
        port = parsed;
        break;
      }
    } catch {
      // Chrome ainda não criou o arquivo.
    }
    const announced = stderr.match(/DevTools listening on ws:\/\/(?:127\.0\.0\.1|localhost):(\d+)\//);
    if (announced) {
      port = Number(announced[1]);
      break;
    }
    if (child.exitCode !== null) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  if (!port) {
    child.kill();
    throw new Error('Chrome for Testing não expôs CDP: ' + stderr.slice(0, 400));
  }
  let browser = null;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      browser = await chromium.connectOverCDP('http://127.0.0.1:' + port);
      break;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  if (!browser) {
    child.kill();
    throw new Error('Falha ao conectar ao Chrome for Testing em CDP.');
  }
  const context = browser.contexts()[0] || await browser.newContext();
  context.on('serviceworker', () => {});
  return {
    context,
    userDataDir,
    close: async () => {
      await browser.close().catch(() => {});
      if (child.exitCode === null) {
        child.kill();
      }
      await rm(userDataDir, { recursive: true, force: true }).catch(() => {});
    },
  };
}

export async function waitForServiceWorker(context, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const worker of context.serviceWorkers()) {
      if (!worker.url().startsWith('chrome-extension://')) {
        continue;
      }
      try {
        const name = await worker.evaluate(() => chrome.runtime.getManifest().name);
        if (name === 'Complementador e-Contas') {
          return worker;
        }
      } catch {
        // worker de outra extensão ou já encerrado
      }
    }
    try {
      await context.waitForEvent('serviceworker', { timeout: Math.min(1000, deadline - Date.now()) });
    } catch {
      // continua até o prazo
    }
  }
  throw new Error('EXTENSION_SERVICE_WORKER_NOT_FOUND');
}

export async function waitForContentScript(page, name = 'Complementador e-Contas', timeoutMs = 5000) {
  const client = await page.context().newCDPSession(page);
  const contexts = [];
  client.on('Runtime.executionContextCreated', (event) => contexts.push(event.context));
  try {
    await client.send('Runtime.enable');
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (contexts.some((context) => context.name === name
        && context.auxData
        && context.auxData.type === 'isolated')) {
        return true;
      }
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    return false;
  } finally {
    await client.detach().catch(() => {});
  }
}

export async function openFormPage(context, origin) {
  const page = await context.newPage();
  await page.goto(origin + FORM_PATH, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => {
    const host = document.querySelector('#complementador-econtas-root');
    return Boolean(host && host.shadowRoot && host.shadowRoot.querySelector('button'));
  }, null, { timeout: 10000 });
  return page;
}

export async function openAutosPage(context, origin, processId = PROCESS_ID) {
  const page = await context.newPage();
  await page.goto(origin + '/autos#/dashboard/processos/' + processId + '/autos', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.documentElement.getAttribute('data-complementador-autos') === 'ready', null, { timeout: 10000 });
  await page.waitForFunction(() => Boolean(document.querySelector('#ifrm')), null, { timeout: 10000 });
  return page;
}

export async function readUi(page) {
  return page.evaluate(() => {
    const host = document.querySelector('#complementador-econtas-root');
    if (!host) {
      return null;
    }
    const root = host.shadowRoot;
    return {
      status: root.querySelector('.status') ? root.querySelector('.status').textContent : null,
      tone: root.querySelector('.status') ? root.querySelector('.status').getAttribute('data-tone') : null,
      source: root.querySelector('.source') ? root.querySelector('.source').textContent : null,
      sourceVisible: root.querySelector('.source') ? root.querySelector('.source').style.display !== 'none' : false,
      buttonDisabled: root.querySelector('button') ? root.querySelector('button').disabled : null,
      lastStatus: host.dataset.lastStatus || null,
      lastElapsedMs: host.dataset.lastElapsedMs || null,
      lastSourceNote: host.dataset.lastSourceNote || null,
      lastErrorCode: host.dataset.lastErrorCode || null,
    };
  });
}

export async function clickFill(page) {
  await page.locator('#complementador-econtas-root button').first().click();
}

export async function waitForResult(page, timeoutMs = 30000) {
  await page.waitForFunction(() => {
    const host = document.querySelector('#complementador-econtas-root');
    return Boolean(host && host.dataset.lastStatus && host.dataset.lastStatus !== 'running');
  }, null, { timeout: timeoutMs });
  return readUi(page);
}

export async function readFields(page) {
  return page.evaluate(() => {
    const value = (name) => {
      const input = document.querySelector('tce-input-field[formcontrolname="' + name + '"] input');
      return input ? input.value : null;
    };
    const selected = document.querySelector('tce-select-field .ng-value');
    return {
      dataDoeEstado: value('dataDoeEstado'),
      cargo: value('cargo'),
      matricula: value('matricula'),
      dataNascimento: value('dataNascimento'),
      modalidade: selected ? selected.textContent.trim() : '',
    };
  });
}
export async function clickDiagnostic(page) {
  await page.locator('#complementador-econtas-root button[data-action="diagnose"]').click();
}
