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

  function normalizeMarker(value) {
    return String(value || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, " ").trim().toUpperCase();
  }

  async function applyMarkerFilter(marker) {
    if (!marker || !marker.label) return;
    const host = document.querySelector("tce-select-field[formcontrolname=idMarcador]");
    const input = host?.querySelector("input[role=combobox]");
    if (!host || !input) throw new Error("Filtro de marcador do e-Contas não foi encontrado.");
    const rawLabel = String(marker.label).trim();
    const countMatch = rawLabel.match(/\((\d+)\)\s*$/u);
    const expectedCount = countMatch ? countMatch[1] : null;
    const label = rawLabel.replace(/\s*\(\d+\)\s*$/u, "").trim();
    const expected = normalizeMarker(label);
    input.click();
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    if (!setter) throw new Error("Campo de marcador do e-Contas não é editável.");
    setter.call(input, label);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    let option = null;
    for (let attempt = 0; attempt < 30; attempt++) {
      option = [...document.querySelectorAll(".ng-option")].find(candidate => {
        const text = normalizeMarker(candidate.textContent);
        return text === expected || text.startsWith(`${expected} `);
      }) || null;
      if (option) break;
      await sleep(200);
    }
    if (!option) throw new Error(`Marcador não encontrado no e-Contas: ${label}`);
    let selectedValue = false;
    for (let attempt = 0; attempt < 5 && !selectedValue; attempt++) {
      await sleep(100);
      option = [...document.querySelectorAll(".ng-option")].find(candidate => {
        const text = normalizeMarker(candidate.textContent);
        return text === expected || text.startsWith(`${expected} `);
      }) || null;
      if (!option) continue;
      for (const type of ["mousedown", "mouseup", "click"]) {
        option.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
      }
      await sleep(250);
      selectedValue = [...host.querySelectorAll(".ng-value")].some(value =>
        normalizeMarker(value.textContent).includes(expected),
      );
    }
    if (!selectedValue) throw new Error(`O marcador não foi selecionado no e-Contas: ${label}`);
    const search = [...document.querySelectorAll("button")].find(button =>
      (button.textContent || "").trim().toUpperCase() === "BUSCAR",
    );
    if (!search) throw new Error("Botão BUSCAR do filtro do e-Contas não foi encontrado.");
    search.click();
    for (let attempt = 0; attempt < 30; attempt++) {
      await sleep(200);
      const text = document.body.innerText || "";
      if (!expectedCount || text.includes(`de ${expectedCount} no total`)) return;
    }
    if (expectedCount) throw new Error(`O e-Contas não confirmou a contagem do marcador ${label}: esperado ${expectedCount}`);
  }

  async function selectLargestPageSize() {
    const select = [...document.querySelectorAll("select")].find(element =>
      [...element.options].some(option => option.textContent.trim() === "100"),
    );
    if (!select || String(select.value) === "100") return;
    const option = [...select.options].find(candidate => candidate.textContent.trim() === "100");
    if (!option) return;
    select.value = option.value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await sleep(1500);
  }

  function currentPageNumber() {
    const current = document.querySelector("ul.ngx-pagination li.current");
    const match = (current?.textContent || "").match(/(\d+)\s*$/u);
    return match ? Number(match[1]) : null;
  }

  function pageButton(number) {
    if (!Number.isInteger(number)) return null;
    const wanted = `page ${number}`;
    return [...document.querySelectorAll("ul.ngx-pagination a")].find(control =>
      (control.textContent || "").replace(/\s+/g, " ").trim().toLowerCase() === wanted,
    ) || null;
  }

  async function waitForPageRows(pageNumber, previousSignature = null) {
    for (let attempt = 0; attempt < 120; attempt++) {
      const rows = processRows();
      const pageAfter = currentPageNumber();
      const signature = rows.map(item => item.key).join('|');
      if (rows.length > 0 && (pageNumber === null || pageAfter === pageNumber) &&
        (previousSignature === null || signature !== previousSignature)) return rows;
      await sleep(250);
    }
    return [];
  }

  async function goToFirstPage() {
    for (let attempt = 0; attempt < 20; attempt++) {
      if (currentPageNumber() === 1) {
        if ((await waitForPageRows(1)).length > 0) return true;
      }
      const first = [...document.querySelectorAll("button, a, [role=button]")].find(control => {
        const label = (control.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
        return label === "page 1" || label === "1";
      });
      if (!first) {
        await sleep(300);
        continue;
      }
      first.click();
      if ((await waitForPageRows(1)).length > 0) return true;
    }
    return false;
  }

  async function advanceToNextPage(signature, pageBefore) {
    const next = pageButton((pageBefore || 0) + 1) || nextButton();
    if (!next) return false;
    next.click();
    const rows = await waitForPageRows(pageBefore === null ? null : pageBefore + 1, signature);
    return rows.length > 0;
  }

  async function enumerateProcesses(targetKeys = [], marker = null) {
    const wanted = new Set((Array.isArray(targetKeys) ? targetKeys : []).map(String));
    await applyMarkerFilter(marker);
    await selectLargestPageSize();
    if (!await goToFirstPage()) throw new Error("O e-Contas não carregou a primeira página para enumeração.");
    const all = new Map();
    let unchanged = 0;
    const seenSignatures = new Set();
    for (let page = 0; page < 100; page++) {
      await sleep(page ? 700 : 300);
      const rows = processRows();
      const before = all.size;
      for (const row of rows) all.set(row.key, row);
      if (wanted.size && [...wanted].every(key => all.has(key))) break;
      unchanged = all.size === before ? unchanged + 1 : 0;
      const next = nextButton();
      if (!next || unchanged >= 2) break;
      const signature = rows.map(item => item.key).join('|');
      if (seenSignatures.has(signature)) break;
      seenSignatures.add(signature);
      const pageBefore = currentPageNumber();
      if (!await advanceToNextPage(signature, pageBefore)) break;
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
      return enumerateProcesses(payload.targetKeys, payload.marker);
    case 'manifest':
      return buildManifest(payload.number, payload.year);
    default:
      throw new Error(`Operação desconhecida: ${payload.operation}`);
  }
})
