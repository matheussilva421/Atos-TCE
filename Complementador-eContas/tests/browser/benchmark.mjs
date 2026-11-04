import { writeFile, mkdir } from 'node:fs/promises';
import {
  clickFill,
  launchExtension,
  openAutosPage,
  openFormPage,
  startFixtureServer,
  waitForResult,
  waitForServiceWorker,
} from './harness.mjs';

const SAMPLES = 7;

async function resetForm(page) {
  await page.evaluate(() => {
    for (const name of ['dataDoeEstado', 'cargo', 'matricula', 'dataNascimento']) {
      const input = document.querySelector('tce-input-field[formcontrolname="' + name + '"] input');
      if (input) input.value = '';
    }
    const value = document.querySelector('tce-select-field .ng-value');
    if (value) { value.textContent = ''; value.style.display = 'none'; }
    const placeholder = document.querySelector('tce-select-field .ng-placeholder');
    if (placeholder) placeholder.style.display = '';
    const host = document.querySelector('#complementador-econtas-root');
    if (host) {
      host.dataset.lastStatus = '';
      host.dataset.lastElapsedMs = '';
      host.dataset.lastErrorCode = '';
      const source = host.shadowRoot.querySelector('.source');
      if (source) { source.textContent = ''; source.style.display = 'none'; }
    }
  });
}

function percentile(values, p) {
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[index];
}

const server = await startFixtureServer({ port: 4173 });
const extension = await launchExtension();
try {
  await waitForServiceWorker(extension.context);
  const formPage = await openFormPage(extension.context, server.origin);
  const autosPage = await openAutosPage(extension.context, server.origin);
  const samples = [];
  for (let index = 0; index < SAMPLES; index += 1) {
    await resetForm(formPage);
    await clickFill(formPage);
    const ui = await waitForResult(formPage);
    if (ui.tone !== 'ok') {
      throw new Error('sample failed: ' + JSON.stringify(ui));
    }
    const elapsed = Number(ui.lastElapsedMs);
    if (!Number.isFinite(elapsed) || elapsed < 0) {
      throw new Error('invalid elapsed value: ' + ui.lastElapsedMs);
    }
    samples.push(elapsed);
  }
  const p50 = percentile(samples, 50);
  const p95 = percentile(samples, 95);
  const lines = [
    '# Benchmark sintético — Complementador e-Contas',
    '',
    '- Data: 04/11/2026',
    '- Navegador: Microsoft Edge 156.0.4314.58 (motor Chromium), perfil temporário de teste',
    '- Node.js: 24.15.0',
    '- Extensão: build de teste, dist-test, permissões limitadas ao servidor local',
    '- Fixture: uma página HTML com formulário sintético, iframe de autos e PDF sintético de 1 página (' + server.pdfBytesLength + ' bytes)',
    '- Medição: performance.now() do clique em "⚡ Preencher" até a resposta final e readback',
    '- Amostras: ' + SAMPLES,
    '',
    '| Amostra | Tempo (ms) |',
    '|---|---:|',
    ...samples.map((value, index) => '| ' + (index + 1) + ' | ' + value + ' |'),
    '',
    '- p50: **' + p50 + ' ms**',
    '- p95: **' + p95 + ' ms**',
    '',
    '## Limitações',
    '',
    '- Medição sintética, não é SLA nem prova de desempenho no e-Contas real.',
    '- O PDF sintético é nato-digital, curto e de uma página; documentos maiores, digitalizações e o visualizador real podem ser mais lentos.',
    '- A meta experimental de ~1 segundo para PDF nato-digital curto não é garantida.',
    '- O acesso real aos bytes do PDF no portal permanece REAL_VIEWER_UNVERIFIED até teste autorizado no perfil profissional.',
    '',
  ];
  await mkdir('docs/evidence', { recursive: true });
  await writeFile('docs/evidence/benchmarks.md', lines.join(String.fromCharCode(10)), 'utf8');
  console.log('BENCHMARK', JSON.stringify({ samples, p50, p95, pdfBytes: server.pdfBytesLength }));
  await autosPage.close();
  await formPage.close();
} finally {
  await extension.close();
  await server.close();
}