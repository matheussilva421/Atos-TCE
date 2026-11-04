import { PORTAL_ORIGIN } from './config.mjs';
import { isValidProcessId } from './identity.mjs';

export function parseRoute(url, portalOrigin = PORTAL_ORIGIN) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.origin !== portalOrigin || parsed.username || parsed.password) {
    return null;
  }
  const rawHash = parsed.hash.startsWith('#') ? parsed.hash.slice(1) : parsed.hash;
  const hashPath = rawHash.split('?')[0].replace(/\/+$/, '');
  const parts = hashPath.split('/').filter(Boolean);
  if (parts[0] !== 'dashboard') {
    return null;
  }
  if (parts[1] === 'processos' && parts.length === 4 && parts[3] === 'autos') {
    return isValidProcessId(parts[2]) ? { kind: 'autos', idProcesso: parts[2] } : null;
  }
  if (parts[1] === 'complementar-ato' && parts.length === 3) {
    return isValidProcessId(parts[2]) ? { kind: 'complemento', idProcesso: parts[2] } : null;
  }
  return null;
}

export function sameProcess(left, right) {
  return Boolean(left && right && left.idProcesso && left.idProcesso === right.idProcesso);
}

export function selectSourceTabs(tabs, targetId, portalOrigin = PORTAL_ORIGIN) {
  if (!isValidProcessId(targetId)) {
    return { ok: false, code: 'INVALID_TARGET' };
  }
  const seen = new Set();
  const matches = [];
  for (const tab of Array.isArray(tabs) ? tabs : []) {
    if (!tab || tab.id == null || seen.has(tab.id)) {
      continue;
    }
    const route = parseRoute(tab.url, portalOrigin);
    if (route && route.kind === 'autos' && route.idProcesso === targetId) {
      seen.add(tab.id);
      matches.push(tab);
    }
  }
  if (matches.length === 0) {
    return { ok: false, code: 'SOURCE_NOT_FOUND' };
  }
  if (matches.length > 1) {
    return { ok: false, code: 'SOURCE_AMBIGUOUS' };
  }
  return { ok: true, tabId: matches[0].id, tab: matches[0] };
}