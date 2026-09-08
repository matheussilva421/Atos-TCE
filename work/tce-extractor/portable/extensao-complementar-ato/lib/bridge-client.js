const MIN_PORT = 18743;
const MAX_PORT = 18752;
const API_VERSION = 1;

function bridgeError(message, code = 'BRIDGE_ERROR', status = null) {
  const error = new Error(message);
  error.code = code;
  if (status !== null) error.status = status;
  return error;
}

function invalidResponse(message) {
  return bridgeError(`envelope do bridge inválido: ${message}`, 'INVALID_RESPONSE');
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
    throw invalidResponse('resposta não é um objeto');
  }
  return value;
}

function nonNegativeInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) throw invalidResponse(`${label} inválido`);
}

function requireApiVersion(payload, label) {
  if (payload.api_version !== API_VERSION) throw invalidResponse(`${label}.api_version incompatível`);
}

function validatePairEnvelope(payload) {
  requireApiVersion(payload, 'pair');
  if (typeof payload.token !== 'string' || !payload.token) throw invalidResponse('pair.token ausente');
  return payload;
}

function validateStateEnvelope(payload) {
  requireApiVersion(payload, 'state');
  nonNegativeInteger(payload.revision, 'state.revision');
  if (Object.hasOwn(payload, 'unchanged') && typeof payload.unchanged !== 'boolean') {
    throw invalidResponse('state.unchanged inválido');
  }
  return payload;
}

function validateDatasetEnvelope(payload) {
  requireApiVersion(payload, 'dataset');
  nonNegativeInteger(payload.revision, 'dataset.revision');
  if (payload.dataset === null || typeof payload.dataset !== 'object' || Array.isArray(payload.dataset)) {
    throw invalidResponse('dataset.dataset inválido');
  }
  return payload;
}

function validateSelectionEnvelope(payload) {
  if (typeof payload.accepted !== 'boolean') throw invalidResponse('selection.accepted inválido');
  if (payload.accepted) nonNegativeInteger(payload.revision, 'selection.revision');
  else nonNegativeInteger(payload.sequence, 'selection.sequence');
  return payload;
}

function validateProgressEnvelope(payload) {
  requireApiVersion(payload, 'progress');
  nonNegativeInteger(payload.revision, 'progress.revision');
  return payload;
}

function validateSelection(selection) {
  if (selection === null || typeof selection !== 'object' || Array.isArray(selection)) {
    throw bridgeError('seleção inválida', 'INVALID_SELECTION');
  }
  const expectedKeys = ['process_key', 'interested_normalized', 'tab_id', 'frame_id', 'sequence'];
  const keys = Object.keys(selection);
  if (keys.length !== expectedKeys.length || expectedKeys.some((key) => !keys.includes(key))) {
    throw bridgeError('seleção inválida', 'INVALID_SELECTION');
  }
  if (typeof selection.process_key !== 'string' || !selection.process_key
    || typeof selection.interested_normalized !== 'string' || !selection.interested_normalized) {
    throw bridgeError('seleção inválida', 'INVALID_SELECTION');
  }
  if (!Number.isSafeInteger(selection.tab_id) || selection.tab_id < 0
    || !Number.isSafeInteger(selection.frame_id) || selection.frame_id < 0
    || !Number.isSafeInteger(selection.sequence) || selection.sequence <= 0) {
    throw bridgeError('seleção inválida', 'INVALID_SELECTION');
  }
  return selection;
}

async function fetchWithTimeout(fetchImpl, url, options, timeoutMs, timeoutMessage) {
  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  const requestOptions = controller ? { ...options, signal: controller.signal } : options;
  let timer = null;
  const request = Promise.resolve().then(() => fetchImpl(url, requestOptions));
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      controller?.abort();
      reject(bridgeError(timeoutMessage, 'BRIDGE_TIMEOUT'));
    }, timeoutMs);
  });
  try {
    return await Promise.race([request, timeout]);
  } catch (error) {
    if (error?.name === 'AbortError') throw bridgeError(timeoutMessage, 'BRIDGE_TIMEOUT');
    throw error;
  } finally {
    if (timer !== null) clearTimeout(timer);
  }
}

async function readResponsePayload(response) {
  if (response === null || typeof response !== 'object' || typeof response.ok !== 'boolean') {
    throw invalidResponse('resposta HTTP inválida');
  }
  if (typeof response.json !== 'function') throw invalidResponse('corpo JSON ausente');
  try {
    return objectPayload(await response.json());
  } catch (error) {
    if (error?.code === 'INVALID_RESPONSE') throw error;
    throw invalidResponse('JSON ilegível');
  }
}

function errorFromResponse(response, payload) {
  const detail = payload?.error;
  if (detail === null || typeof detail !== 'object' || Array.isArray(detail)
    || typeof detail.code !== 'string' || !detail.code
    || typeof detail.message !== 'string' || !detail.message) {
    throw invalidResponse('error ausente ou inválido');
  }
  return bridgeError(detail.message, detail.code, response.status);
}

export async function pairBridge({ fetchImpl = globalThis.fetch, baseUrl, code, timeoutMs = 5000 } = {}) {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
  if (typeof fetchImpl !== 'function') throw bridgeError('fetch indisponível', 'FETCH_UNAVAILABLE');
  if (typeof code !== 'string' || !/^\d{8}$/u.test(code)) throw bridgeError('código de pareamento inválido', 'INVALID_PAIRING_CODE');
  if (!Number.isInteger(timeoutMs) || timeoutMs <= 0 || timeoutMs > 30000) throw bridgeError('timeout inválido', 'INVALID_TIMEOUT');
  try {
    const response = await fetchWithTimeout(fetchImpl, `${normalizedBaseUrl}/api/v1/pair`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    }, timeoutMs, 'tempo limite do pareamento excedido');
    const payload = await readResponsePayload(response);
    if (!response.ok) throw errorFromResponse(response, payload);
    return validatePairEnvelope(payload).token;
  } catch (error) {
    throw error;
  }
}

export function createBridgeClient({ fetchImpl = globalThis.fetch, baseUrl, token, timeoutMs = 5000 } = {}) {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
  if (typeof fetchImpl !== 'function') throw bridgeError('fetch indisponível', 'FETCH_UNAVAILABLE');
  if (typeof token !== 'string' || !token) throw bridgeError('token é obrigatório', 'TOKEN_REQUIRED');
  if (!Number.isInteger(timeoutMs) || timeoutMs <= 0 || timeoutMs > 30000) throw bridgeError('timeout inválido', 'INVALID_TIMEOUT');

  async function request(path, { method = 'GET', body, validate } = {}) {
    const response = await fetchWithTimeout(fetchImpl, `${normalizedBaseUrl}/api/v1${path}`, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      }, timeoutMs, 'tempo limite do bridge excedido');
    const payload = await readResponsePayload(response);
    if (!response.ok) throw errorFromResponse(response, payload);
    return validate ? validate(payload) : payload;
  }

  return Object.freeze({
    async getState(since) {
      if (since !== undefined && (!Number.isInteger(since) || since < 0)) throw bridgeError('since inválido', 'INVALID_STATE_REVISION');
      return request(since === undefined ? '/state' : `/state?since=${encodeURIComponent(since)}`, { validate: validateStateEnvelope });
    },
    async getDataset() { return request('/dataset', { validate: validateDatasetEnvelope }); },
    async publishSelection(selection) {
      return request('/selection', { method: 'POST', body: { ...validateSelection(selection) }, validate: validateSelectionEnvelope });
    },
    async setCompleted(processKey, completed, expectedRevision) {
      if (typeof processKey !== 'string' || !processKey) throw bridgeError('processKey inválido', 'INVALID_PROCESS_KEY');
      if (typeof completed !== 'boolean' || !Number.isInteger(expectedRevision) || expectedRevision < 0) {
        throw bridgeError('progresso inválido', 'INVALID_PROGRESS');
      }
      return request(`/progress/${encodeURIComponent(processKey)}`, {
        method: 'PUT',
        body: { completed, expected_revision: expectedRevision },
        validate: validateProgressEnvelope,
      });
    },
  });
}
