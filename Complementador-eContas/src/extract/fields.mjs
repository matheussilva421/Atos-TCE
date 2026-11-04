import { parseBirthDate, parseResolutionDate } from './dates.mjs';

const MODALITY_OPTIONS = Object.freeze([
  'Aposentadoria compulsória',
  'Aposentadoria Especial com fundamento na LC nº 51/1985',
  'Aposentadoria Especial com fundamento no art. 57 da Lei nº 8.213/91',
  'Aposentadoria por invalidez',
  'Aposentadoria proporcional ao tempo de contribuição',
  'Aposentadoria proporcional ao tempo de serviço',
  'Aposentadoria voluntária por tempo de contribuição com proventos integrais',
  'Aposentadoria voluntária por tempo de serviço com proventos integrais',
  'Reforma',
  'Revisão de Benefício',
  'Transferência a pedido para a reserva remunerada',
]);

function deaccent(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

function snippet(text, index, length) {
  return text.slice(Math.max(0, index - 70), Math.min(text.length, index + length + 70)).trim();
}

function uniqueValues(values) {
  const seen = new Set();
  const result = [];
  for (const value of values) {
    if (!seen.has(value)) {
      seen.add(value);
      result.push(value);
    }
  }
  return result;
}

function matchModality(text) {
  const normalized = deaccent(text);
  const matches = [];
  const add = (label, pattern) => {
    const found = normalized.search(pattern);
    if (found >= 0) {
      matches.push({ label, source: snippet(normalized, found, 40) });
    }
  };

  add(MODALITY_OPTIONS[0], /aposentadoria compulsoria/);
  add(MODALITY_OPTIONS[1], /aposentadoria especial[^.]{0,200}(?:lc\s*n?[ºo°.]?\s*51\/1985|lei complementar\s*n?[ºo°.]?\s*51\/1985)/);
  add(MODALITY_OPTIONS[2], /aposentadoria especial[^.]{0,200}(?:art\.?\s*57|8\.213)/);
  add(MODALITY_OPTIONS[3], /aposentadoria por invalidez/);
  add(MODALITY_OPTIONS[4], /aposentadoria proporcional ao tempo de contribuicao/);
  add(MODALITY_OPTIONS[5], /aposentadoria proporcional ao tempo de servico/);
  add(MODALITY_OPTIONS[6], /aposentadoria voluntaria por tempo de contribuicao[^.]{0,200}proventos integrais/);
  add(MODALITY_OPTIONS[7], /aposentadoria voluntaria por tempo de servico[^.]{0,200}proventos integrais/);
  add(MODALITY_OPTIONS[8], /(?:concede|conceder)\s+reforma(?:\s+remunerada)?/);
  add(MODALITY_OPTIONS[9], /revisao de beneficio/);
  add(MODALITY_OPTIONS[10], /transferencia a pedido para a reserva remunerada/);

  const unique = uniqueValues(matches.map((match) => match.label));
  if (unique.length === 1) {
    const matched = matches.find((match) => match.label === unique[0]);
    return { status: 'exact', value: unique[0], source: 'trecho da resolução', evidence: matched.source };
  }
  if (unique.length > 1) {
    return { status: 'ambiguous', candidates: unique };
  }
  return { status: 'absent' };
}

function personWindows(text, selectedInterested, selectedCpf = '') {
  const name = deaccent(selectedInterested);
  const normalized = deaccent(text);
  const windows = [];
  if (name) {
    let from = 0;
    while (from < normalized.length) {
      const index = normalized.indexOf(name, from);
      if (index < 0) {
        break;
      }
      windows.push(text.slice(Math.max(0, index - 80), Math.min(text.length, index + name.length + 700)));
      from = index + name.length;
    }
  }
  const cpf = String(selectedCpf ?? '').replace(/\D/g, '');
  if (/^\d{11}$/.test(cpf)) {
    const pattern = /\d{3}\.?\s?\d{3}\.?\s?\d{3}-?\s?\d{2}/g;
    let match;
    while ((match = pattern.exec(normalized)) !== null) {
      if (match[0].replace(/\D/g, '') === cpf) {
        windows.push(text.slice(Math.max(0, match.index - 80), Math.min(text.length, match.index + 700)));
      }
    }
  }
  return windows;
}

function extractMatricula(windowText) {
  const normalized = deaccent(windowText);
  const matches = [];
  const pattern = /matricula\s*(?:n[ºo°.]*)?\s*:?\s*([0-9][0-9.\-\/]{2,})/g;
  let match;
  while ((match = pattern.exec(normalized)) !== null) {
    const value = match[1].replace(/[.,;:]+$/, '').trim();
    if (/^[0-9][0-9.\-\/]{1,19}$/.test(value)) {
      matches.push({ value, evidence: snippet(normalized, match.index, match[0].length) });
    }
  }
  const unique = uniqueValues(matches.map((match) => match.value));
  if (unique.length === 1) {
    return { status: 'exact', value: unique[0], source: 'trecho do interessado', evidence: matches[0].evidence };
  }
  if (unique.length > 1) {
    return { status: 'ambiguous', candidates: unique };
  }
  return { status: 'absent' };
}

function extractCargo(windowText) {
  const matches = [];
  const patterns = [
    /no\s+cargo\s+de\s+([^,;.\n]+)/gi,
    /cargo\s+de\s+([^,;.\n]+)/gi,
  ];
  for (const pattern of patterns) {
    let match;
    while ((match = pattern.exec(windowText)) !== null) {
      const value = match[1].replace(/\s+/g, ' ').replace(/^["'“”]+|["'“”]+$/g, '').trim();
      if (value && value.length <= 50) {
        matches.push({ value, evidence: snippet(windowText, match.index, match[0].length) });
      }
    }
  }
  const unique = uniqueValues(matches.map((match) => match.value));
  if (unique.length === 1) {
    return { status: 'exact', value: unique[0], source: 'trecho do interessado', evidence: matches[0].evidence };
  }
  if (unique.length > 1) {
    return { status: 'ambiguous', candidates: unique };
  }
  return { status: 'absent' };
}

function extractPersonFields(text, ctx) {
  const windows = personWindows(text, ctx.selectedInterested, ctx.selectedInterestedCpf);
  if (windows.length === 0) {
    return {
      cargo: { status: 'absent', reason: 'INTEREST_NOT_FOUND' },
      matricula: { status: 'absent', reason: 'INTEREST_NOT_FOUND' },
      dataNascimento: { status: 'absent', reason: 'INTEREST_NOT_FOUND' },
    };
  }
  const windowText = windows.join('\n');
  const cargo = extractCargo(windowText);
  const matricula = extractMatricula(windowText);
  const birth = parseBirthDate(windowText);
  const dataNascimento = birth.status === 'exact'
    ? { status: 'exact', value: birth.dateBr, source: birth.source, evidence: birth.evidence }
    : birth;
  return { cargo, matricula, dataNascimento };
}

export function extractFields(doc, ctx) {
  const text = Array.isArray(doc && doc.pages) ? doc.pages.join('\n\f\n') : '';
  const modality = matchModality(text);
  const resolutionDate = parseResolutionDate(text);
  const person = extractPersonFields(text, ctx || {});

  const dataDoeEstado = resolutionDate.status === 'exact'
    ? {
        status: 'exact',
        value: resolutionDate.dateBr,
        source: resolutionDate.source,
        evidence: resolutionDate.evidence,
      }
    : resolutionDate;

  return {
    modalidade: modality,
    dataDoeEstado,
    cargo: person.cargo,
    matricula: person.matricula,
    dataNascimento: person.dataNascimento,
  };
}
