/**
 * Mesa PDF viewer adapter.
 *
 * Ported from the proven legacy viewer: the same normalized-rectangle
 * validation, the same bounded zoom (75% to 300%) and the same quarter-turn
 * rotation contract. What changed is the source of the bytes: the Mesa serves
 * every document through SQLite by id, so the URL is always
 * ``/api/v1/documents/<id>/pdf`` and never a filesystem path.
 */

export const MIN_SCALE = 0.75;
export const MAX_SCALE = 3;
export const DEFAULT_SCALE = 1.5;

export function viewerUrl(documentId) {
  const id = Number(documentId);
  if (!Number.isInteger(id) || id < 1) throw new RangeError("document id is required");
  return `/api/v1/documents/${id}/pdf`;
}

export function validateRect(rect) {
  if (
    !Array.isArray(rect) ||
    rect.length !== 4 ||
    rect.some(
      (value) => typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1
    )
  ) {
    throw new RangeError("rect must use normalized coordinates");
  }
  if (rect[2] < rect[0] || rect[3] < rect[1]) throw new RangeError("rect bounds are invalid");
  return [...rect];
}

export function showEvidence(target, evidence) {
  if (!target || typeof target !== "object") throw new TypeError("viewer target is required");
  const documentId = evidence?.documentId ?? evidence?.document_id;
  if (documentId === undefined || documentId === null || documentId === "") {
    throw new TypeError("documentId is required");
  }
  if (!Number.isInteger(evidence?.page) || evidence.page < 1) {
    throw new TypeError("a positive page is required");
  }
  const result = {
    documentId: String(documentId),
    page: evidence.page,
    rects: (evidence.rects ?? []).map(validateRect),
  };
  target.evidence = result;
  return result;
}

export function createPdfViewer({ target = {} } = {}) {
  return {
    showEvidence: (evidence) => showEvidence(target, evidence),
    getEvidence: () => target.evidence ?? null,
  };
}

export function clampScale(scale) {
  const requested = Number(scale);
  if (!Number.isFinite(requested)) return DEFAULT_SCALE;
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, requested));
}

export function normalizeRotation(rotation) {
  const requested = Number(rotation);
  if (!Number.isFinite(requested)) return 0;
  return ((Math.round(requested / 90) * 90) % 360 + 360) % 360;
}

export async function renderPdfPage({
  pdfjs,
  pdfUrl,
  pageNumber,
  canvas,
  overlay,
  workerUrl,
  evidence = null,
  scale = DEFAULT_SCALE,
  rotation = 0,
}) {
  if (!pdfjs || typeof pdfjs.getDocument !== "function") {
    throw new TypeError("PDF.js local não está disponível");
  }
  if (!(canvas instanceof Object) || typeof canvas.getContext !== "function") {
    throw new TypeError("canvas inválido");
  }
  if (typeof pdfUrl !== "string" || !pdfUrl) throw new TypeError("pdfUrl é obrigatório");
  if (!Number.isInteger(pageNumber) || pageNumber < 1) throw new TypeError("pageNumber inválido");
  if (workerUrl && pdfjs.GlobalWorkerOptions) pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
  const document = await pdfjs.getDocument({ url: pdfUrl }).promise;
  const page = await document.getPage(pageNumber);
  const safeScale = clampScale(scale);
  const safeRotation = normalizeRotation(rotation);
  const viewport = page.getViewport({ scale: safeScale, rotation: safeRotation });
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
  if (overlay) {
    overlay.replaceChildren();
    for (const rect of evidence?.rects ?? []) {
      const marker = overlay.ownerDocument?.createElement?.("div") ?? { style: {} };
      marker.className = "review-evidence-rect";
      marker.style.left = `${rect[0] * 100}%`;
      marker.style.top = `${rect[1] * 100}%`;
      marker.style.width = `${(rect[2] - rect[0]) * 100}%`;
      marker.style.height = `${(rect[3] - rect[1]) * 100}%`;
      overlay.append(marker);
    }
  }
  return {
    pageNumber,
    width: viewport.width,
    height: viewport.height,
    pageCount: document.numPages,
    scale: safeScale,
    rotation: safeRotation,
  };
}
