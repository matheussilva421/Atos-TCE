(async function (payload) {
  'use strict';

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const currentUser = (() => {
    try { return JSON.parse(localStorage.getItem('currentUser') || 'null'); }
    catch (_) { return null; }
  })();
  const authHeaders = currentUser && currentUser.token ? { Authorization: currentUser.token } : {};

  async function requestJson(path) {
    const response = await fetch(path, { credentials: 'include', headers: { Accept: 'application/json', ...authHeaders } });
    if (!response.ok) throw new Error(`HTTP ${response.status} em ${path.split('?')[0]}`);
    return response.json();
  }

  function asArray(value) {
    if (Array.isArray(value)) return value;
    for (const key of ['items', 'data', 'results', 'resources']) {
      if (Array.isArray(value && value[key])) return value[key];
    }
    return value ? [value] : [];
  }

  function processRows() {
    const found = new Map();
    const candidates = [...document.querySelectorAll('tr, [role="row"], processos-card, .card')];
    for (const row of candidates) {
      const text = (row.innerText || row.textContent || '').replace(/\s+/g, ' ').trim();
      const match = text.match(/\b(\d{5,8})\s*\/\s*(20\d{2})\b/);
      if (!match) continue;
      const key = `${match[1]}/${match[2]}`;
      if (!found.has(key)) found.set(key, { key, number: match[1], year: Number(match[2]), label: text.slice(0, 260) });
    }
    if (!found.size) {
      const text = document.body.innerText || '';
      for (const match of text.matchAll(/\b(\d{5,8})\s*\/\s*(20\d{2})\b/g)) {
        const key = `${match[1]}/${match[2]}`;
        if (!found.has(key)) found.set(key, { key, number: match[1], year: Number(match[2]), label: key });
      }
    }
    return [...found.values()];
  }

  function nextButton() {
    const candidates = [...document.querySelectorAll('button, a, [role="button"]')];
    return candidates.find(element => {
      const text = [element.getAttribute('aria-label'), element.getAttribute('title'), element.textContent, element.className]
        .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
      const disabled = element.disabled || element.getAttribute('aria-disabled') === 'true' ||
        element.classList.contains('disabled') || (element.closest('li') && element.closest('li').classList.contains('disabled'));
      return !disabled && /(pr.xim|next|pagination-next|^\s*[›»]\s*$)/i.test(text);
    });
  }

  async function enumerateProcesses() {
    const all = new Map();
    let unchanged = 0;
    for (let page = 0; page < 200; page++) {
      await sleep(page ? 700 : 300);
      const rows = processRows();
      const before = all.size;
      for (const row of rows) all.set(row.key, row);
      unchanged = all.size === before ? unchanged + 1 : 0;
      const next = nextButton();
      if (!next || unchanged >= 2) break;
      const signature = rows.map(item => item.key).join('|');
      next.click();
      for (let attempt = 0; attempt < 30; attempt++) {
        await sleep(200);
        if (processRows().map(item => item.key).join('|') !== signature) break;
      }
    }
    return [...all.values()];
  }

  async function resolveProcess(number, year) {
    const result = asArray(await requestJson(`/api/Processo?numeroProcesso=${encodeURIComponent(number)}&anoProcesso=${encodeURIComponent(year)}`));
    const process = result.find(item => String(item.numeroProcesso) === String(number) && Number(item.anoProcesso) === Number(year)) || result[0];
    if (!process || !process.idProcesso) throw new Error(`Processo ${number}/${year} não foi resolvido pela API`);
    return process;
  }

  function extensionOf(attachment) {
    let extension = String(attachment.extensao || '').trim();
    if (!extension && attachment.nomeInicialArquivo) {
      const match = String(attachment.nomeInicialArquivo).match(/(\.[A-Za-z0-9]{1,10})$/);
      extension = match ? match[1] : '';
    }
    if (!extension) extension = '.pdf';
    return extension.startsWith('.') ? extension : `.${extension}`;
  }

  async function buildManifest(number, year) {
    const process = await resolveProcess(number, year);
    const events = asArray(await requestJson(`/api/Processo/${process.idProcesso}/eventos?sortDesc=false&trazerInativas=true`));
    const normalizedEvents = [];

    for (const event of events) {
      const info = event.informacao || null;
      const documents = [];
      if (info && (event.idInformacao || info.idInformacao)) {
        const infoId = event.idInformacao || info.idInformacao;
        try {
          const pdf = await requestJson(`/api/informacao/${infoId}/pdf`);
          if (pdf && pdf.urlConsultaTemp) {
            documents.push({ id: `informacao-${infoId}`, title: info.resumo || `Informação ${infoId}`, extension: '.pdf', url: pdf.urlConsultaTemp, requires_auth: false, remote_signature: JSON.stringify({ id: infoId, date: event.dataInclusao || '', inactive: !!info.inativa, summary: info.resumo || '', path: pdf.pathPdf || pdf.caminho || '' }) });
          }
        } catch (error) {
          documents.push({ id: `informacao-${infoId}`, title: info.resumo || `Informação ${infoId}`, extension: '.pdf', error: String(error.message || error), remote_signature: `erro-${infoId}` });
        }
      }

      for (const attachment of (info && Array.isArray(info.anexos) ? info.anexos : [])) {
        const attachmentId = attachment.idAtaInformacaoAnexo;
        if (!attachmentId) continue;
        const extension = extensionOf(attachment);
        let url = `/api/informacaoanexo/${attachmentId}/download?extensao=${encodeURIComponent(extension.replace('.', ''))}`;
        let requiresAuth = true;
        if (extension.toLowerCase() === '.pdf') {
          try {
            const link = await requestJson(`/api/InformacaoAnexo/${attachmentId}/url`);
            if (link && link.url) { url = link.url; requiresAuth = false; }
          } catch (_) { /* fallback autenticado */ }
        }
        documents.push({ id: `anexo-${attachmentId}`, title: attachment.nomeInicialArquivo || attachment.codigo || `Anexo ${attachmentId}`, extension, url, requires_auth: requiresAuth, remote_signature: JSON.stringify({ id: attachmentId, extension, name: attachment.nomeInicialArquivo || '', code: attachment.codigo || '', date: attachment.dataInclusao || '' }) });
      }

      normalizedEvents.push({
        event: Number(event.sequencialProcessoEvento || event.numeroEvento || 0),
        event_id: String(event.idProcessoEvento || event.idItemLote || `ordem-${normalizedEvents.length + 1}`),
        date: event.dataInclusao || '',
        title: info ? `${info.setor || ''}${info.resumo ? ` - ${info.resumo}` : ''}`.trim() : 'Tramitação',
        active: !(info && info.inativa),
        documents
      });
    }

    return { process: { key: `${process.numeroProcesso}/${process.anoProcesso}`, id: process.idProcesso, number: String(process.numeroProcesso), year: Number(process.anoProcesso) }, events: normalizedEvents };
  }

  switch (payload.operation) {
    case 'session':
      return { authenticated: !!(currentUser && currentUser.token), token: currentUser && currentUser.token || '', sector: currentUser && currentUser.setorSelecionado && currentUser.setorSelecionado.codigoSetor || '' };
    case 'enumerateProcesses':
      return enumerateProcesses();
    case 'manifest':
      return buildManifest(payload.number, payload.year);
    default:
      throw new Error(`Operação desconhecida: ${payload.operation}`);
  }
})
