const MIN_PORT = 18743;
const MAX_PORT = 18752;

function bridgeError(message, code = 'BRIDGE_ERROR', status = null) {
  const error = new Error(message);
  error.code = code;
  if (status !== null) error.status = status;
  return error;
}

function normalizeBaseUrl(baseUrl) {
  if (typeof baseUrl !== 'string' || !baseUrl.trim()) throw bridgeError('baseUrl é obrigatório', 'INVALID_BASE_URL');
  let parsed;
  try { parsed = new URL(baseUrl); } catch { throw bridgeError('baseUrl inválida', 'INVALID_BASE_URL'); }
  const port = Number(parsed.port);
  if (parsed.protocol !== 'http:' || parsed.hostname !== '127.0.0.1' || !Number.isInteger(port) || port < MIN_PORT || port > MAX_PORT) {
    throw bridgeError('baseUrl deve usar o loopback HTTP em uma porta permitida', 'INVALID_BASE_URL');
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash || (parsed.pathname !== '' && parsed.pathname !== '/')) {
    throw bridgeError('baseUrl contém componentes não permitidos', 'INVALID_BASE_URL');
  }
  return `http://127.0.0.1:${port}`;
}

function objectPayload(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw bridgeError('resposta do bridge não é um objeto', 'INVALID_RESPONSE');
  }
  return value;
}

export async function pairBridge({ fetchImpl = globalThis.fetch, baseUrl, code, timeoutMs = 5000 } = {}) {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
  if (typeof fetchImpl !== 'function') throw bridgeError('fetch indisponível', 'FETCH_UNAVAILABLE');
  if (typeof code !== 'string' || !/^\d{8}$/u.test(code)) throw bridgeError('código de pareamento inválido', 'INVALID_PAIRING_CODE');
  if (!Number.isInteger(timeoutMs) || timeoutMs <= 0 || timeoutMs > 30000) throw bridgeError('timeout inválido', 'INVALID_TIMEOUT');
  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetchImpl(`${normalizedBaseUrl}/api/v1/pair`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
      ...(controller ? { signal: controller.signal } : {}),
    });
    let payload = null;
    try { payload = objectPayload(await response.json()); } catch (error) {
      if (response.ok) throw error;
    }
    if (!response.ok) {
      const detail = payload?.error;
      throw bridgeError(detail?.message || `bridge respondeu HTTP ${response.status}`, detail?.code || `HTTP_${response.status}`, response.status);
    }
    if (typeof payload.token !== 'string' || !payload.token) throw bridgeError('token não retornado pelo bridge', 'INVALID_PAIRING_RESPONSE');
    return payload.token;
  } catch (error) {
    if (error?.name === 'AbortError') throw bridgeError('tempo limite do pareamento excedido', 'BRIDGE_TIMEOUT');
    throw error;
  } finally {
    if (timer !== null) clearTimeout(timer);
  }
}

export function createBridgeClient({ fetchImpl = globalThis.fetch, baseUrl, token, timeoutMs = 5000 } = {}) {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
  if (typeof fetchImpl !== 'function') throw bridgeError('fetch indisponível', 'FETCH_UNAVAILABLE');
  if (typeof token !== 'string' || !token) throw bridgeError('token é obrigatório', 'TOKEN_REQUIRED');
  if (!Number.isInteger(timeoutMs) || timeoutMs <= 0 || timeoutMs > 30000) throw bridgeError('timeout inválido', 'INVALID_TIMEOUT');

  async function request(path, { method = 'GET', body } = {}) {
    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    try {
      const response = await fetchImpl(`${normalizedBaseUrl}/api/v1${path}`, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        ...(controller ? { signal: controller.signal } : {}),
      });
      let payload = null;
      try { payload = objectPayload(await response.json()); } catch (error) {
        if (response.ok) throw error;
      }
      if (!response.ok) {
        const detail = payload?.error;
        throw bridgeError(detail?.message || `bridge respondeu HTTP ${response.status}`, detail?.code || `HTTP_${response.status}`, response.status);
      }
      return payload;
    } catch (error) {
      if (error?.name === 'AbortError') throw bridgeError('tempo limite do bridge excedido', 'BRIDGE_TIMEOUT');
      throw error;
    } finally {
      if (timer !== null) clearTimeout(timer);
    }
  }

  return Object.freeze({
    async getState(since) {
      if (since !== undefined && (!Number.isInteger(since) || since < 0)) throw bridgeError('since inválido', 'INVALID_STATE_REVISION');
      return request(since === undefined ? '/state' : `/state?since=${encodeURIComponent(since)}`);
    },
    async getDataset() { return request('/dataset'); },
    async publishSelection(selection) {
      return request('/selection', { method: 'POST', body: { ...selection } });
    },
    async setCompleted(processKey, completed, expectedRevision) {
      if (typeof processKey !== 'string' || !processKey) throw bridgeError('processKey inválido', 'INVALID_PROCESS_KEY');
      if (typeof completed !== 'boolean' || !Number.isInteger(expectedRevision) || expectedRevision < 0) {
        throw bridgeError('progresso inválido', 'INVALID_PROGRESS');
      }
      return request(`/progress/${encodeURIComponent(processKey)}`, {
        method: 'PUT',
        body: { completed, expected_revision: expectedRevision },
      });
    },
  });
}
