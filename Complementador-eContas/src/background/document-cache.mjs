import { hashString } from '../shared/identity.mjs';

export const DOCUMENT_CACHE_KEY = 'complementadorDocumentCache';

export function processHash(processId) {
  return hashString(String(processId));
}

export function cacheEntryFor(processId, ids = {}) {
  return {
    processHash: processHash(processId),
    resolutionEventId: typeof ids.resolutionEventId === 'string' ? ids.resolutionEventId : null,
    guiaEventId: typeof ids.guiaEventId === 'string' ? ids.guiaEventId : null,
    updatedAt: Date.now(),
  };
}

export function cacheMatches(value, processId) {
  return Boolean(value && value.processHash && value.processHash === processHash(processId));
}

export function mergeCacheEntry(existing, processId, ids = {}) {
  const sameProcess = cacheMatches(existing, processId);
  const resolutionEventId = typeof ids.resolutionEventId === 'string'
    ? ids.resolutionEventId
    : (sameProcess ? existing.resolutionEventId || null : null);
  const guiaEventId = typeof ids.guiaEventId === 'string'
    ? ids.guiaEventId
    : (sameProcess ? existing.guiaEventId || null : null);
  if (!resolutionEventId && !guiaEventId) {
    return null;
  }
  return {
    processHash: processHash(processId),
    resolutionEventId,
    guiaEventId,
    updatedAt: Date.now(),
  };
}
