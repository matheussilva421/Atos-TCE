import test from 'node:test';
import assert from 'node:assert/strict';
import { cacheEntryFor, cacheMatches, DOCUMENT_CACHE_KEY, mergeCacheEntry, processHash } from '../../src/background/document-cache.mjs';

test('cache_is_bound_to_process_hash', () => {
  const entry = cacheEntryFor('577367', { resolutionEventId: 'id-1', guiaEventId: 'id-2' });
  assert.equal(entry.processHash, processHash('577367'));
  assert.equal(cacheMatches(entry, '577367'), true);
  assert.equal(cacheMatches(entry, '577368'), false);
  assert.equal(cacheMatches(null, '577367'), false);
});

test('cache_stores_only_technical_locators', () => {
  const entry = cacheEntryFor('577367', { resolutionEventId: 'id-1', guiaEventId: 'id-2' });
  assert.deepEqual(Object.keys(entry).sort(), ['guiaEventId', 'processHash', 'resolutionEventId', 'updatedAt']);
  assert.equal(JSON.stringify(entry).includes('http'), false);
  assert.equal(DOCUMENT_CACHE_KEY, 'complementadorDocumentCache');
});

test('failed_partial_search_preserves_valid_cache_for_same_process', () => {
  const existing = cacheEntryFor('577367', { resolutionEventId: 'id-1', guiaEventId: 'id-2' });
  const merged = mergeCacheEntry(existing, '577367', { resolutionEventId: 'id-3', guiaEventId: null });
  assert.equal(merged.resolutionEventId, 'id-3');
  assert.equal(merged.guiaEventId, 'id-2');
});

test('new_process_does_not_reuse_old_events', () => {
  const existing = cacheEntryFor('577367', { resolutionEventId: 'id-1', guiaEventId: 'id-2' });
  const merged = mergeCacheEntry(existing, '577368', { resolutionEventId: 'id-9', guiaEventId: null });
  assert.equal(merged.resolutionEventId, 'id-9');
  assert.equal(merged.guiaEventId, null);
});

test('dois_processos_em_sequencia_nao_reaproveitam_ids', () => {
  let stored = mergeCacheEntry(null, '577367', { resolutionEventId: 'res-a', guiaEventId: 'guia-a' });
  assert.equal(cacheMatches(stored, '577367'), true);
  stored = mergeCacheEntry(stored, '577368', { resolutionEventId: 'res-b', guiaEventId: 'guia-b' });
  assert.equal(cacheMatches(stored, '577367'), false);
  assert.equal(cacheMatches(stored, '577368'), true);
  assert.equal(stored.resolutionEventId, 'res-b');
  assert.equal(stored.guiaEventId, 'guia-b');
  stored = mergeCacheEntry(stored, '577367', { resolutionEventId: 'res-c', guiaEventId: null });
  assert.equal(stored.guiaEventId, null);
  assert.equal(stored.resolutionEventId, 'res-c');
});
