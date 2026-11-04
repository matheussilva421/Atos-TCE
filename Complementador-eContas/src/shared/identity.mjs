export function normalizeText(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function stripCpf(value) {
  return String(value ?? '')
    .replace(/\d{3}\.\d{3}\.\d{3}-\d{2}/g, ' ')
    .replace(/\d{11}/g, ' ');
}

export function extractInterestedName(text) {
  return normalizeText(stripCpf(text))
    .replace(/^[\s\-–—:;,./]+|[\s\-–—:;,./]+$/g, '')
    .trim();
}

export function hashString(value) {
  const input = String(value ?? '');
  let hash = 0x811c9dc5;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

export function documentKeyFromUrl(url) {
  const parsed = new URL(url);
  return hashString(parsed.pathname);
}

export function isValidProcessId(value) {
  return typeof value === 'string' && /^\d{1,12}$/.test(value);
}

export function normalizeLabel(value) {
  return normalizeText(value).toLowerCase();
}
export function normalizeProcessLabel(value) {
  const text = normalizeText(value);
  const match = /(\d{1,6})\s*\/\s*(\d{4})/.exec(text);
  return match ? match[1] + '/' + match[2] : '';
}
