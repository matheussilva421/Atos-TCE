import test from 'node:test';
import assert from 'node:assert/strict';
import { renderPdfPage, showEvidence } from '../pdf-viewer.js';

test('showEvidence keeps document id and normalized rectangles', () => {
  const target = {};
  const result = showEvidence(target, {
    documentId: 'doc-1',
    page: 2,
    rects: [[0.1, 0.2, 0.4, 0.5]],
  });
  assert.deepEqual(result, {
    documentId: 'doc-1',
    page: 2,
    rects: [[0.1, 0.2, 0.4, 0.5]],
  });
  assert.deepEqual(target.evidence, result);
});

test('showEvidence rejects rectangles outside the normalized page', () => {
  assert.throws(
    () => showEvidence({}, { documentId: 'doc-1', page: 1, rects: [[-0.1, 0, 1, 1]] }),
    /rect/i,
  );
});

test('renderPdfPage applies bounded zoom and quarter-turn rotation', async () => {
  let viewportOptions;
  const pdfjs = {
    getDocument: () => ({
      promise: Promise.resolve({
        getPage: async () => ({
          getViewport: (options) => {
            viewportOptions = options;
            return { width: 800, height: 1200 };
          },
          render: () => ({ promise: Promise.resolve() }),
        }),
      }),
    }),
  };
  const canvas = { getContext: () => ({}) };

  await renderPdfPage({
    pdfjs,
    pdfUrl: 'processos/1-2026/documento.pdf',
    pageNumber: 1,
    canvas,
    scale: 2.25,
    rotation: 90,
  });

  assert.deepEqual(viewportOptions, { scale: 2.25, rotation: 90 });
});
