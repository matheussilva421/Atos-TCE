import { bytesToBase64, looksLikePdf } from '../autos/pdf-identity.mjs';

export const PDF_FETCH_MAX_BYTES = 25 * 1024 * 1024;

class TooLargeError extends Error {}

async function readLimitedBody(response, maxBytes) {
  if (response.body && typeof response.body.getReader === 'function') {
    const reader = response.body.getReader();
    const chunks = [];
    let total = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        total += value.byteLength;
        if (total > maxBytes) {
          throw new TooLargeError('too large');
        }
        chunks.push(value);
      }
    } catch (error) {
      try {
        await reader.cancel();
      } catch {
        // O cancelamento é best-effort.
      }
      throw error;
    }
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return bytes;
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > maxBytes) {
    throw new TooLargeError('too large');
  }
  return new Uint8Array(buffer);
}

export async function fetchPdfBytes(fetchImpl, url, options = {}) {
  const maxBytes = options.maxBytes || PDF_FETCH_MAX_BYTES;
  let response;
  try {
    response = await fetchImpl(url, {
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
    });
  } catch {
    return { ok: false, code: 'PDF_FETCH_FAILED' };
  }
  if (!response || response.ok !== true) {
    return { ok: false, code: 'PDF_FETCH_FAILED' };
  }
  const contentType = response.headers && typeof response.headers.get === 'function'
    ? response.headers.get('content-type') || ''
    : '';
  if (contentType.toLowerCase().indexOf('application/pdf') === -1) {
    return { ok: false, code: 'DOCUMENT_NOT_READABLE' };
  }
  const declaredLength = response.headers && typeof response.headers.get === 'function'
    ? Number(response.headers.get('content-length') || 0)
    : 0;
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) {
    return { ok: false, code: 'DOCUMENT_TOO_LARGE' };
  }
  let bytes;
  try {
    bytes = await readLimitedBody(response, maxBytes);
  } catch (error) {
    return { ok: false, code: error instanceof TooLargeError ? 'DOCUMENT_TOO_LARGE' : 'PDF_FETCH_FAILED' };
  }
  if (!looksLikePdf(bytes)) {
    return { ok: false, code: 'DOCUMENT_NOT_READABLE' };
  }
  return {
    ok: true,
    base64: bytesToBase64(bytes),
    byteLength: bytes.length,
    contentType,
  };
}