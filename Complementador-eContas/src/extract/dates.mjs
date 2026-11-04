const MONTHS = Object.freeze({
  janeiro: 1,
  fevereiro: 2,
  marco: 3,
  abril: 4,
  maio: 5,
  junho: 6,
  julho: 7,
  agosto: 8,
  setembro: 9,
  outubro: 10,
  novembro: 11,
  dezembro: 12,
});

export const RESOLUTION_DATE_SOURCE = 'data da resolução administrativa';

function deaccent(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase();
}

function pad2(value) {
  return String(value).padStart(2, '0');
}

function isValidDate(day, month, year) {
  if (!Number.isInteger(day) || !Number.isInteger(month) || !Number.isInteger(year)) {
    return false;
  }
  if (day < 1 || day > 31 || month < 1 || month > 12 || year < 1900 || year > 2200) {
    return false;
  }
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year
    && date.getUTCMonth() === month - 1
    && date.getUTCDate() === day;
}

function toBrDate(day, month, year) {
  return pad2(day) + '/' + pad2(month) + '/' + String(year);
}

function dedupeByDate(candidates) {
  const seen = new Set();
  const result = [];
  for (const candidate of candidates) {
    if (!seen.has(candidate.dateBr)) {
      seen.add(candidate.dateBr);
      result.push(candidate);
    }
  }
  return result;
}

function contextOf(text, index, length) {
  return text.slice(Math.max(0, index - 90), Math.min(text.length, index + length + 90)).trim();
}

function sentenceAround(text, index, length) {
  const before = Math.max(text.lastIndexOf('.', index), text.lastIndexOf('\n', index), text.lastIndexOf(';', index));
  const ends = [text.indexOf('.', index + length), text.indexOf('\n', index + length), text.indexOf(';', index + length)]
    .filter((value) => value >= 0);
  const end = ends.length > 0 ? Math.min(...ends) : text.length;
  const sentence = text.slice(before + 1, end + 1).trim();
  return sentence.length <= 320 ? sentence : contextOf(text, index, length);
}

function isExcludedDateContext(context) {
  return /(nasciment|nascid|nasceu|data de nascimento|publicad|publicacao|diario oficial|\bdoe\b|assinatura|assinado|despacho|portaria|vigencia|a partir de)/.test(context);
}

function datePriority(context) {
  if (/(resolucao|data do ato)/.test(context)) {
    return 3;
  }
  if (/natal/.test(context)) {
    return 2;
  }
  if (/(resolv|concede|conceder)/.test(context)) {
    return 1;
  }
  return 0;
}

export function parseResolutionDate(text) {
  const normalized = deaccent(text);
  const candidates = [];
  const textual = /\b(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})\b/g;
  let match;
  while ((match = textual.exec(normalized)) !== null) {
    const day = Number(match[1]);
    const month = MONTHS[match[2]];
    const year = Number(match[3]);
    if (!month || !isValidDate(day, month, year)) {
      continue;
    }
    const context = sentenceAround(normalized, match.index, match[0].length);
    if (isExcludedDateContext(context)) {
      continue;
    }
    const priority = datePriority(context);
    if (priority === 0) {
      continue;
    }
    candidates.push({
      dateBr: toBrDate(day, month, year),
      evidence: context.slice(0, 180),
      priority,
    });
  }

  if (candidates.length === 0) {
    const numeric = /\b(\d{1,2})[\/ .](\d{1,2})[\/ .](\d{4})\b/g;
    while ((match = numeric.exec(normalized)) !== null) {
      const day = Number(match[1]);
      const month = Number(match[2]);
      const year = Number(match[3]);
      if (!isValidDate(day, month, year)) {
        continue;
      }
      const context = sentenceAround(normalized, match.index, match[0].length);
      if (isExcludedDateContext(context)) {
        continue;
      }
      if (!/(natal|data da resolucao|data do ato)/.test(context)) {
        continue;
      }
      const priority = datePriority(context);
      if (priority === 0) {
        continue;
      }
      candidates.push({
        dateBr: toBrDate(day, month, year),
        evidence: context.slice(0, 180),
        priority,
      });
    }
  }

  if (candidates.length === 0) {
    return { status: 'absent' };
  }
  const maxPriority = Math.max(...candidates.map((candidate) => candidate.priority));
  const unique = dedupeByDate(candidates.filter((candidate) => candidate.priority === maxPriority));
  if (unique.length === 1) {
    return {
      status: 'exact',
      dateBr: unique[0].dateBr,
      source: RESOLUTION_DATE_SOURCE,
      evidence: unique[0].evidence,
    };
  }
  if (unique.length > 1) {
    return {
      status: 'ambiguous',
      candidates: unique.map((candidate) => candidate.dateBr),
    };
  }
  return { status: 'absent' };
}

export function parseBirthDate(text) {
  const normalized = deaccent(text);
  const candidates = [];
  const patterns = [
    /(?:nascid[oa]|nasceu)\s*(?:em|a)?\s*(\d{1,2})[\/ .](\d{1,2})[\/ .](\d{4})/g,
    /data de nascimento\s*:?\s*(\d{1,2})[\/ .](\d{1,2})[\/ .](\d{4})/g,
  ];
  for (const pattern of patterns) {
    let match;
    while ((match = pattern.exec(normalized)) !== null) {
      const day = Number(match[1]);
      const month = Number(match[2]);
      const year = Number(match[3]);
      if (isValidDate(day, month, year)) {
        candidates.push({
          dateBr: toBrDate(day, month, year),
          evidence: contextOf(normalized, match.index, match[0].length).slice(0, 180),
        });
      }
    }
  }
  const textual = /(?:nascid[oa]|nasceu)\s*(?:em|a)?\s*(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})/g;
  let match;
  while ((match = textual.exec(normalized)) !== null) {
    const day = Number(match[1]);
    const month = MONTHS[match[2]];
    const year = Number(match[3]);
    if (month && isValidDate(day, month, year)) {
      candidates.push({
        dateBr: toBrDate(day, month, year),
        evidence: contextOf(normalized, match.index, match[0].length).slice(0, 180),
      });
    }
  }

  const birthLabel = /data de nascimento/g;
  let labelMatch;
  while ((labelMatch = birthLabel.exec(normalized)) !== null) {
    const windowText = normalized.slice(labelMatch.index, Math.min(normalized.length, labelMatch.index + 320));
    const windowDates = /\b(\d{1,2})\s*[\/.-]\s*(\d{1,2})\s*[\/.-]\s*(\d{4})\b/g;
    let dateMatch;
    while ((dateMatch = windowDates.exec(windowText)) !== null) {
      const day = Number(dateMatch[1]);
      const month = Number(dateMatch[2]);
      const year = Number(dateMatch[3]);
      if (isValidDate(day, month, year)) {
        candidates.push({
          dateBr: toBrDate(day, month, year),
          evidence: contextOf(normalized, labelMatch.index, windowText.length).slice(0, 180),
        });
      }
    }
  }
  const unique = dedupeByDate(candidates);
  if (unique.length === 1) {
    return {
      status: 'exact',
      dateBr: unique[0].dateBr,
      source: 'data de nascimento no documento',
      evidence: unique[0].evidence,
    };
  }
  if (unique.length > 1) {
    return {
      status: 'ambiguous',
      candidates: unique.map((candidate) => candidate.dateBr),
    };
  }
  return { status: 'absent' };
}

function cpfDigits(value) {
  return String(value ?? '').replace(/\D/g, '');
}

function allCpfAnchors(text) {
  const anchors = [];
  const pattern = /\d{3}\.?\s?\d{3}\.?\s?\d{3}-?\s?\d{2}/g;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    anchors.push({ index: match.index, digits: cpfDigits(match[0]) });
  }
  return anchors;
}

function cpfAnchors(text, cpf) {
  if (!/^\d{11}$/.test(cpf)) {
    return [];
  }
  return allCpfAnchors(text)
    .filter((anchor) => anchor.digits === cpf)
    .map((anchor) => anchor.index);
}

export function parseBirthDateForPerson(text, selectedName, selectedCpf) {
  const normalized = deaccent(text);
  const anchors = [];
  anchors.push(...cpfAnchors(normalized, cpfDigits(selectedCpf)));
  const name = deaccent(selectedName).replace(/\s+/g, ' ').trim();
  if (name) {
    let from = 0;
    while (from < normalized.length) {
      const index = normalized.indexOf(name, from);
      if (index < 0) {
        break;
      }
      anchors.push(index);
      from = index + name.length;
    }
  }

  const candidates = [];
  const labels = [...normalized.matchAll(/data de nascimento/g)].map((match) => match.index);
  const cpf = cpfDigits(selectedCpf);
  const allCpfs = allCpfAnchors(normalized);
  if (/^\d{11}$/.test(cpf) && allCpfs.some((anchor) => anchor.digits === cpf)) {
    const cpfCandidates = [];
    for (const anchor of allCpfs.filter((item) => item.digits === cpf)) {
      const nextCpf = allCpfs.find((item) => item.index > anchor.index);
      const block = normalized.slice(anchor.index, nextCpf ? nextCpf.index : normalized.length);
      const datePattern = /\b(\d{1,2})\s*[\/.-]\s*(\d{1,2})\s*[\/.-]\s*(\d{4})\b/g;
      let dateMatch;
      while ((dateMatch = datePattern.exec(block)) !== null) {
        const day = Number(dateMatch[1]);
        const month = Number(dateMatch[2]);
        const year = Number(dateMatch[3]);
        if (isValidDate(day, month, year)) {
          cpfCandidates.push({
            dateBr: toBrDate(day, month, year),
            evidence: contextOf(normalized, anchor.index, block.length).slice(0, 180),
          });
        }
      }
    }
    const uniqueCpf = dedupeByDate(cpfCandidates);
    if (uniqueCpf.length === 1) {
      return {
        status: 'exact',
        dateBr: uniqueCpf[0].dateBr,
        source: 'data de nascimento no documento',
        evidence: uniqueCpf[0].evidence,
      };
    }
    if (uniqueCpf.length > 1) {
      return { status: 'ambiguous', candidates: uniqueCpf.map((candidate) => candidate.dateBr) };
    }
  }
  for (const index of anchors) {
    if (labels.length === 0) {
      continue;
    }
    const distances = labels.map((label) => Math.abs(label - index));
    const nearestDistance = Math.min(...distances);
    if (distances.filter((distance) => distance === nearestDistance).length > 1) {
      return { status: 'ambiguous' };
    }
    const labelIndex = labels[distances.indexOf(nearestDistance)];
    const nextLabel = labels.find((label) => label > labelIndex);
    const block = normalized.slice(labelIndex, nextLabel === undefined ? normalized.length : nextLabel);
    const parsed = parseBirthDate(block);
    if (parsed.status === 'ambiguous') {
      return parsed;
    }
    if (parsed.status === 'exact') {
      candidates.push(parsed);
    }
  }
  const unique = dedupeByDate(candidates);
  if (unique.length === 1) {
    return {
      status: 'exact',
      dateBr: unique[0].dateBr,
      source: 'data de nascimento no documento',
      evidence: unique[0].evidence,
    };
  }
  if (unique.length > 1) {
    return { status: 'ambiguous', candidates: unique.map((candidate) => candidate.dateBr) };
  }

  const labelCount = (normalized.match(/data de nascimento/g) || []).length;
  const dates = [...normalized.matchAll(/\b\d{1,2}\s*[\/.-]\s*\d{1,2}\s*[\/.-]\s*\d{4}\b/g)];
  if (labelCount === 1 && dates.length === 1) {
    return parseBirthDate(normalized);
  }
  return { status: 'absent' };
}
