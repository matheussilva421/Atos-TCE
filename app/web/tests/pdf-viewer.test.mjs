import test from "node:test";
import assert from "node:assert/strict";

import {
  clampScale,
  normalizeRotation,
  renderPdfPage,
  showEvidence,
  validateRect,
  viewerUrl,
} from "../pdf-viewer.js";

test("viewerUrl always goes through the SQLite document id", () => {
  assert.equal(viewerUrl(7), "/api/v1/documents/7/pdf");
  assert.throws(() => viewerUrl(0), /document id/u);
  assert.throws(() => viewerUrl("../../etc/passwd"), /document id/u);
});

test("showEvidence keeps the document id, page and normalized rectangles", () => {
  const target = {};
  const result = showEvidence(target, {
    document_id: 12,
    page: 2,
    rects: [[0.1, 0.2, 0.4, 0.5]],
  });

  assert.deepEqual(result, { documentId: "12", page: 2, rects: [[0.1, 0.2, 0.4, 0.5]] });
  assert.deepEqual(target.evidence, result);
});

test("showEvidence rejects rectangles outside the normalized page", () => {
  assert.throws(
    () => showEvidence({}, { document_id: 1, page: 1, rects: [[-0.1, 0, 1, 1]] }),
    /rect/u
  );
  assert.throws(() => validateRect([0.5, 0.5, 0.2, 0.6]), /bounds/u);
});

test("showEvidence requires a document and a positive page", () => {
  assert.throws(() => showEvidence({}, { page: 1 }), /documentId/u);
  assert.throws(() => showEvidence({}, { document_id: 1, page: 0 }), /positive page/u);
});

test("zoom is bounded to 75% and 300%", () => {
  assert.equal(clampScale(0.1), 0.75);
  assert.equal(clampScale(10), 3);
  assert.equal(clampScale(2.25), 2.25);
  assert.equal(clampScale("nada"), 1.5);
});

test("rotation is a normalized quarter turn", () => {
  assert.equal(normalizeRotation(90), 90);
  assert.equal(normalizeRotation(-90), 270);
  assert.equal(normalizeRotation(450), 90);
  assert.equal(normalizeRotation(0), 0);
  assert.equal(normalizeRotation("nada"), 0);
});

test("renderPdfPage applies the bounded zoom and rotation to the viewport", async () => {
  let viewportOptions;
  const pdfjs = {
    getDocument: () => ({
      promise: Promise.resolve({
        numPages: 4,
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

  const result = await renderPdfPage({
    pdfjs,
    pdfUrl: viewerUrl(3),
    pageNumber: 1,
    canvas,
    scale: 2.25,
    rotation: 90,
  });

  assert.deepEqual(viewportOptions, { scale: 2.25, rotation: 90 });
  assert.equal(result.pageCount, 4);
  assert.equal(result.scale, 2.25);
});

test("renderPdfPage refuses a bad canvas, url or page", async () => {
  const pdfjs = { getDocument: () => ({ promise: Promise.resolve({}) }) };
  await assert.rejects(() => renderPdfPage({ pdfjs, pdfUrl: "/x", pageNumber: 1, canvas: null }), /canvas/u);
  await assert.rejects(
    () => renderPdfPage({ pdfjs, pdfUrl: "", pageNumber: 1, canvas: { getContext: () => ({}) } }),
    /pdfUrl/u
  );
  await assert.rejects(
    () => renderPdfPage({ pdfjs, pdfUrl: "/x", pageNumber: 0, canvas: { getContext: () => ({}) } }),
    /pageNumber/u
  );
});

test("renderPdfPage paints one marker per evidence rectangle", async () => {
  const appended = [];
  const overlay = {
    ownerDocument: { createElement: () => ({ style: {}, className: "" }) },
    replaceChildren: () => appended.splice(0, appended.length),
    append: (element) => appended.push(element),
  };
  const pdfjs = {
    getDocument: () => ({
      promise: Promise.resolve({
        numPages: 1,
        getPage: async () => ({
          getViewport: () => ({ width: 10, height: 10 }),
          render: () => ({ promise: Promise.resolve() }),
        }),
      }),
    }),
  };

  await renderPdfPage({
    pdfjs,
    pdfUrl: viewerUrl(1),
    pageNumber: 1,
    canvas: { getContext: () => ({}) },
    overlay,
    evidence: { rects: [[0.1, 0.2, 0.4, 0.5]] },
  });

  assert.equal(appended.length, 1);
  assert.equal(appended[0].className, "review-evidence-rect");
  assert.equal(appended[0].style.left, "10%");
  assert.equal(appended[0].style.width, "30.000000000000004%");
});
