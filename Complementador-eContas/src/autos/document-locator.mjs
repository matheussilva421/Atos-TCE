function deaccent(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase();
}

export function isBirthDocumentText(text) {
  const normalized = deaccent(text);
  return /guia financeira/.test(normalized) || /taxacao de proventos/.test(normalized);
}

export function isResolutionDocumentText(text) {
  return /resolucao administrativa/.test(deaccent(text));
}
