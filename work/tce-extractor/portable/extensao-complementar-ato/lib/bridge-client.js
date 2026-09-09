const MIN_PORT = 18743;
const MAX_PORT = 18752;
const API_VERSION = 1;

import {
  validateAutomationCapabilities,
  validateAutomationEvent,
  validateAutomationIdentity,
  validateAutomationQueue,
  validateAutomationRunSpec,
  validateAutomationSnapshot,
  validateControlRequest,
  validateLegalContext,
} from "./automation-schema.js";

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

function wireIdentity(identity) {
  validateAutomationIdentity(identity);
  return {
    process_key: identity.processKey,
    interested_normalized: identity.interestedNormalized,
    portal_act_id: identity.portalActId,
  };
}

function wireRunSpec(spec, eventId) {
  validateAutomationRunSpec(spec);
  if (typeof eventId !== "string" || !eventId) throw bridgeError("eventId inválido", "INVALID_EVENT_ID");
  const wire = {
    tab_id: spec.tabId,
    sector: spec.sector,
    dataset_sha256: spec.datasetSha256,
    rules_version: spec.rulesVersion,
    event_id: eventId,
  };
  if (spec.mode !== undefined) wire.mode = spec.mode;
  if (spec.pilotIdentity !== undefined) wire.pilot_identity = wireIdentity(spec.pilotIdentity);
  return wire;
}

function wireQueue(value) {
  validateAutomationQueue(value);
  return {
    identities: value.identities.map(wireIdentity),
    event_id: value.eventId,
    expected_revision: value.expectedRevision,
  };
}

function wireEvent(value) {
  validateAutomationEvent(value);
  return {
    event_id: value.eventId,
    expected_revision: value.expectedRevision,
    item_id: value.itemId,
    type: value.type,
    payload: value.payload,
  };
}

function wireControl(value) {
  validateControlRequest(value);
  return {
    action: value.action,
    event_id: value.eventId,
    expected_revision: value.expectedRevision,
  };
}

function fromWireIdentity(identity) {
  if (identity === null || typeof identity !== "object" || Array.isArray(identity)) {
    throw invalidResponse("identity inválida");
  }
  const result = {
    processKey: identity.process_key,
    interestedNormalized: identity.interested_normalized,
    portalActId: identity.portal_act_id,
  };
  try {
    return validateAutomationIdentity(result);
  } catch {
    throw invalidResponse("identity inválida");
  }
}

function fromWireSnapshot(payload) {
  requireApiVersion(payload, "automation snapshot");
  const translated = {
    ...payload,
    items: Array.isArray(payload.items)
      ? payload.items.map((item) => ({
        ...item,
        identity: fromWireIdentity(item.identity),
      }))
      : payload.items,
  };
  try {
    return validateAutomationSnapshot(translated);
  } catch (error) {
    throw invalidResponse(error instanceof Error ? error.message : "snapshot inválido");
  }
}

function fromWireCommandConsumption(payload) {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw invalidResponse("consumo de comando inválido");
  }
  if (payload.dispatch_allowed !== true || typeof payload.command_id !== "string" || !payload.command_id) {
    throw invalidResponse("consumo de comando não autorizado");
  }
  const {
    dispatch_allowed: _dispatchAllowed,
    command_id: _commandId,
    ...snapshotPayload
  } = payload;
  return {
    ...fromWireSnapshot(snapshotPayload),
    dispatch_allowed: true,
    command_id: payload.command_id,
  };
}

function fromWireRunHistory(payload) {
  requireApiVersion(payload, "automation run history");
  if (!Array.isArray(payload.runs)) throw invalidResponse("automation run history.runs inválido");
  if (payload.next_cursor !== null && typeof payload.next_cursor !== "string") {
    throw invalidResponse("automation run history.next_cursor inválido");
  }
  for (const run of payload.runs) {
    if (run === null || typeof run !== "object" || Array.isArray(run)
      || typeof run.run_id !== "string" || !run.run_id
      || !Number.isSafeInteger(run.revision) || run.revision < 0
      || typeof run.state !== "string" || typeof run.created_at !== "string"
      || typeof run.updated_at !== "string" || run.totals === null
      || typeof run.totals !== "object" || Array.isArray(run.totals)) {
      throw invalidResponse("automation run history entry inválida");
    }
  }
  return payload;
}

function fromWireEvents(payload) {
  requireApiVersion(payload, "automation event history");
  if (!Array.isArray(payload.events) || typeof payload.has_more !== "boolean") {
    throw invalidResponse("automation event history inválida");
  }
  if (payload.next_after !== null && (!Number.isSafeInteger(payload.next_after) || payload.next_after < 0)) {
    throw invalidResponse("automation event history.next_after inválido");
  }
  for (const event of payload.events) {
    if (event === null || typeof event !== "object" || Array.isArray(event)
      || typeof event.event_id !== "string" || typeof event.run_id !== "string"
      || !Number.isSafeInteger(event.seq) || event.seq < 1
      || typeof event.type !== "string" || event.payload === null
      || typeof event.payload !== "object" || Array.isArray(event.payload)
      || typeof event.created_at !== "string") {
      throw invalidResponse("automation event history entry inválida");
    }
  }
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
      mode: 'cors',
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
      mode: 'cors',
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

  async function requestBinary(path) {
    const response = await fetchWithTimeout(fetchImpl, `${normalizedBaseUrl}/api/v1${path}`, {
      method: 'GET',
      mode: 'cors',
      headers: { Authorization: `Bearer ${token}` },
    }, timeoutMs, 'tempo limite do bridge excedido');
    if (response === null || typeof response !== 'object' || typeof response.ok !== 'boolean') {
      throw invalidResponse('resposta HTTP inválida');
    }
    if (!response.ok) {
      const payload = await readResponsePayload(response);
      throw errorFromResponse(response, payload);
    }
    if (typeof response.arrayBuffer !== 'function') throw invalidResponse('corpo binário ausente');
    const body = await response.arrayBuffer();
    if (!(body instanceof ArrayBuffer)) throw invalidResponse('corpo binário inválido');
    const contentType = typeof response.headers?.get === 'function'
      ? response.headers.get('Content-Type') || 'application/octet-stream'
      : 'application/octet-stream';
    return { body, contentType };
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
    async getAutomationCapabilities() {
      try {
        return await request('/automation/capabilities', { validate: (payload) => {
          try {
            return validateAutomationCapabilities(payload);
          } catch (error) {
            throw invalidResponse(error.message);
          }
        } });
      } catch (error) {
        if (error?.status === 404 || error?.code === 'NOT_FOUND') return null;
        throw error;
      }
    },
    async listAutomationRuns({ limit = 20, before } = {}) {
      if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) throw bridgeError("limit inválido", "INVALID_LIMIT");
      if (before !== undefined && (typeof before !== "string" || !before)) throw bridgeError("cursor inválido", "INVALID_CURSOR");
      const query = new URLSearchParams({ limit: String(limit) });
      if (before !== undefined) query.set("before", before);
      return request(`/automation/runs?${query.toString()}`, { validate: fromWireRunHistory });
    },
    async getAutomationEvents(runId, { after = 0, limit = 100 } = {}) {
      if (typeof runId !== "string" || !runId) throw bridgeError("runId inválido", "INVALID_RUN_ID");
      if (!Number.isSafeInteger(after) || after < 0) throw bridgeError("after inválido", "INVALID_AFTER");
      if (!Number.isSafeInteger(limit) || limit < 1 || limit > 500) throw bridgeError("limit inválido", "INVALID_LIMIT");
      const query = new URLSearchParams({ after: String(after), limit: String(limit) });
      return request(`/automation/runs/${encodeURIComponent(runId)}/events?${query.toString()}`, { validate: fromWireEvents });
    },
    async getAutomationReport(runId, format = 'html') {
      if (typeof runId !== 'string' || !runId) throw bridgeError('runId inválido', 'INVALID_RUN_ID');
      if (format !== 'html' && format !== 'csv') throw bridgeError('formato inválido', 'INVALID_REPORT_FORMAT');
      return requestBinary(`/automation/runs/${encodeURIComponent(runId)}/report?format=${encodeURIComponent(format)}`);
    },
    async getLegalContext(identity) {
      if (identity === null || typeof identity !== 'object' || Array.isArray(identity)
        || Object.keys(identity).length !== 2
        || typeof identity.processKey !== 'string'
        || typeof identity.interestedNormalized !== 'string'
        || !identity.processKey
        || !identity.interestedNormalized) {
        throw bridgeError('identidade inválida', 'INVALID_IDENTITY');
      }
      const query = new URLSearchParams({
        process_key: identity.processKey,
        interested_normalized: identity.interestedNormalized,
      });
      return request(`/legal-context?${query.toString()}`, {
        validate: (payload) => {
          requireApiVersion(payload, 'legal-context');
          try {
            validateLegalContext(payload.context, {
              processKey: identity.processKey,
              interestedNormalized: identity.interestedNormalized,
            });
          } catch (error) {
            throw invalidResponse(error instanceof Error ? error.message : 'legal-context.context inválido');
          }
          return payload;
        },
      });
    },
    async createAutomationRun(spec, eventId) {
      return request('/automation/runs', {
        method: 'POST',
        body: wireRunSpec(spec, eventId),
        validate: fromWireSnapshot,
      });
    },
    async freezeAutomationQueue(runId, body) {
      if (typeof runId !== 'string' || !runId) throw bridgeError('runId inválido', 'INVALID_RUN_ID');
      return request(`/automation/runs/${encodeURIComponent(runId)}/queue`, {
        method: 'POST',
        body: wireQueue(body),
        validate: fromWireSnapshot,
      });
    },
    async getAutomationRun(runId) {
      if (typeof runId !== 'string' || !runId) throw bridgeError('runId inválido', 'INVALID_RUN_ID');
      return request(`/automation/runs/${encodeURIComponent(runId)}`, { validate: fromWireSnapshot });
    },
    async appendAutomationEvent(runId, event) {
      if (typeof runId !== 'string' || !runId) throw bridgeError('runId inválido', 'INVALID_RUN_ID');
      return request(`/automation/runs/${encodeURIComponent(runId)}/events`, {
        method: 'POST',
        body: wireEvent(event),
        validate: fromWireSnapshot,
      });
    },
    async consumeAutomationCommand(runId, commandId, expectedRevision) {
      if (typeof runId !== 'string' || !runId || typeof commandId !== 'string' || !commandId
        || !Number.isSafeInteger(expectedRevision) || expectedRevision < 0) {
        throw bridgeError('comando inválido', 'INVALID_COMMAND');
      }
      return request(`/automation/runs/${encodeURIComponent(runId)}/commands/${encodeURIComponent(commandId)}/consume`, {
        method: 'POST',
        body: { expected_revision: expectedRevision },
        validate: fromWireCommandConsumption,
      });
    },
    async controlAutomationRun(runId, body) {
      if (typeof runId !== 'string' || !runId) throw bridgeError('runId inválido', 'INVALID_RUN_ID');
      return request(`/automation/runs/${encodeURIComponent(runId)}/control`, {
        method: 'POST',
        body: wireControl(body),
        validate: fromWireSnapshot,
      });
    },
  });
}
