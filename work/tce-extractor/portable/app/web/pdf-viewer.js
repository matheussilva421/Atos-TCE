/** Small viewer adapter; PDF rendering can be supplied by the pinned PDF.js bundle. */

function validateRect(rect) {
  if (!Array.isArray(rect) || rect.length !== 4 || rect.some((value) => typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1)) {
    throw new RangeError('rect must use normalized coordinates');
  }
  if (rect[2] < rect[0] || rect[3] < rect[1]) throw new RangeError('rect bounds are invalid');
  return [...rect];
}

export function showEvidence(target, evidence) {
  if (!target || typeof target !== 'object') throw new TypeError('viewer target is required');
  if (!evidence || typeof evidence.documentId !== 'string' || !Number.isInteger(evidence.page) || evidence.page < 1) {
    throw new TypeError('documentId and positive page are required');
  }
  const result = {
    documentId: evidence.documentId,
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

export async function renderPdfPage({ pdfjs, pdfUrl, pageNumber, canvas, overlay, workerUrl, evidence = null, scale = 1.5, rotation = 0 }) {
  if (!pdfjs || typeof pdfjs.getDocument !== 'function') throw new TypeError('PDF.js local não está disponível');
  if (!(canvas instanceof Object) || typeof canvas.getContext !== 'function') throw new TypeError('canvas inválido');
  if (typeof pdfUrl !== 'string' || !pdfUrl) throw new TypeError('pdfUrl é obrigatório');
  if (!Number.isInteger(pageNumber) || pageNumber < 1) throw new TypeError('pageNumber inválido');
  if (workerUrl && pdfjs.GlobalWorkerOptions) pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
  const document = await pdfjs.getDocument({ url: pdfUrl }).promise;
  const page = await document.getPage(pageNumber);
  const requestedScale = Number(scale);
  const safeScale = Number.isFinite(requestedScale)
    ? Math.min(3, Math.max(0.75, requestedScale))
    : 1.5;
  const requestedRotation = Number(rotation);
  const safeRotation = Number.isFinite(requestedRotation)
    ? ((requestedRotation % 360) + 360) % 360
    : 0;
  const viewport = page.getViewport({ scale: safeScale, rotation: safeRotation });
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
  if (overlay) {
    overlay.replaceChildren();
    for (const rect of evidence?.rects ?? []) {
      const marker = overlay.ownerDocument?.createElement?.('div') ?? { style: {} };
      marker.className = 'review-evidence-rect';
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
