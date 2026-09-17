import test from "node:test";
import assert from "node:assert/strict";

import { createLegalContextResolver } from "../background/legal-context-resolver.js";

const HASH = "a".repeat(64);
const RULES = "legal-foundation-v3";
const IDENTITY = { processKey: "103439/2023", interestedNormalized: "maria da silva" };

const COMPLETE_PAGES = [{ text: "RESOLVE: Art. 6º da EC nº 41/2003.", citation: { document_id: "resolution-9", page: 1 } }];

function contextRecord(overrides = {}) {
  return {
    schema_version: 1,
    dataset_sha256: HASH,
    process_key: IDENTITY.processKey,
    interested_normalized: IDENTITY.interestedNormalized,
    resolution_status: "complete",
    operative_text: "RESOLVE: Art. 6º da EC nº 41/2003.",
    pages: COMPLETE_PAGES,
    extraction_version: "legal-context-v4",
    context_revision: 4,
    rules_version: RULES,
    ...overrides,
  };
}

function bridgeStub({ context = contextRecord(), getError = null, rebuildError = null } = {}) {
  const calls = { get: 0, rebuild: 0 };
  return {
    calls,
    async getLegalContext() {
      calls.get += 1;
      if (getError) throw getError;
      return { api_version: 1, context };
    },
    async rebuildLegalContext() {
      calls.rebuild += 1;
      if (rebuildError) throw rebuildError;
      return { api_version: 1, context };
    },
  };
}

function notFound() {
  const error = new Error("contexto jurídico não encontrado");
  error.status = 404;
  error.code = "LEGAL_CONTEXT_NOT_FOUND";
  return error;
}

test("reuses a valid cached context without consulting the bridge again", async () => {
  const bridge = bridgeStub();
  const resolver = createLegalContextResolver({ bridge, rulesVersion: RULES });

  const first = await resolver.ensureLegalContext({ identity: IDENTITY, datasetSha256: HASH });
  const second = await resolver.ensureLegalContext({ identity: IDENTITY, datasetSha256: HASH });

  assert.equal(first.status, "ready");
  assert.equal(first.source, "sidecar");
  assert.equal(first.reason, null);
  assert.equal(second.status, "ready");
  assert.equal(second.source, "cache");
  assert.equal(bridge.calls.get, 1);
  assert.equal(bridge.calls.rebuild, 0);
});

test("rebuilds the context when the sidecar has no record for the identity", async () => {
  const bridge = bridgeStub({ context: contextRecord() });
  bridge.getLegalContext = async () => { bridge.calls.get += 1; throw notFound(); };
  const resolver = createLegalContextResolver({ bridge, rulesVersion: RULES });

  const resolution = await resolver.ensureLegalContext({ identity: IDENTITY, datasetSha256: HASH });

  assert.equal(resolution.status, "rebuilt");
  assert.equal(resolution.source, "rebuilt");
  assert.equal(resolution.reason, null);
  assert.equal(bridge.calls.get, 1);
  assert.equal(bridge.calls.rebuild, 1);
});

test("rebuilds when the sidecar hash belongs to another dataset", async () => {
  const stale = contextRecord({ dataset_sha256: "b".repeat(64) });
  const bridge = bridgeStub({ context: stale });
  // The resolver validates defensively even if an older bridge returns the raw record.
  bridge.getLegalContext = async () => { bridge.calls.get += 1; return { api_version: 1, context: stale }; };
  bridge.rebuildLegalContext = async () => {
    bridge.calls.rebuild += 1;
    return { api_version: 1, context: contextRecord() };
  };
  const resolver = createLegalContextResolver({ bridge, rulesVersion: RULES });

  const resolution = await resolver.ensureLegalContext({ identity: IDENTITY, datasetSha256: HASH });

  assert.equal(resolution.status, "rebuilt");
  assert.equal(resolution.source, "rebuilt");
  assert.equal(bridge.calls.rebuild, 1);
});

test("rebuilds when the sidecar was written under older legal rules", async () => {
  const bridge = bridgeStub({ context: contextRecord({ rules_version: "legal-foundation-v2" }) });
  bridge.rebuildLegalContext = async () => {
    bridge.calls.rebuild += 1;
    return { api_version: 1, context: contextRecord() };
  };
  const resolver = createLegalContextResolver({ bridge, rulesVersion: RULES });

  const resolution = await resolver.ensureLegalContext({ identity: IDENTITY, datasetSha256: HASH });

  assert.equal(resolution.status, "rebuilt");
  assert.equal(bridge.calls.rebuild, 1);
});

test("rebuilds when the sidecar revision is not an authoritative integer", async () => {
  const bridge = bridgeStub({ context: contextRecord({ context_revision: undefined }) });
  bridge.rebuildLegalContext = async () => {
    bridge.calls.rebuild += 1;
    return { api_version: 1, context: contextRecord() };
  };
  const resolver = createLegalContextResolver({ bridge, rulesVersion: RULES });

  const resolution = await resolver.ensureLegalContext({ identity: IDENTITY, datasetSha256: HASH });

  assert.equal(resolution.status, "rebuilt");
  assert.equal(bridge.calls.rebuild, 1);
});

test("blocks the legal field when resolution is not complete", async () => {
  const bridge = bridgeStub({ context: contextRecord({ resolution_status: "conflict" }) });
  const resolver = createLegalContextResolver({ bridge, rulesVersion: RULES });

  const resolution = await resolver.ensureLegalContext({ identity: IDENTITY, datasetSha256: HASH });

  assert.equal(resolution.status, "blocked");
  assert.equal(resolution.source, null);
  assert.equal(resolution.reason, "CONTEXT_INCOMPLETE");
  assert.equal(resolution.context, null);
  assert.equal(bridge.calls.rebuild, 0);
});

test("blocks the legal field when the operative text is empty", async () => {
  const bridge = bridgeStub({ context: contextRecord({ operative_text: "   " }) });
  const resolver = createLegalContextResolver({ bridge, rulesVersion: RULES });

  const resolution = await resolver.ensureLegalContext({ identity: IDENTITY, datasetSha256: HASH });

  assert.equal(resolution.status, "blocked");
  assert.equal(resolution.reason, "CONTEXT_INCOMPLETE");
});

test("blocks the legal field when the identity diverges from the request", async () => {
  const bridge = bridgeStub({ context: contextRecord({ interested_normalized: "outra pessoa" }) });
  bridge.getLegalContext = async () => {
    bridge.calls.get += 1;
    return { api_version: 1, context: contextRecord({ interested_normalized: "outra pessoa" }) };
  };
  const resolver = createLegalContextResolver({ bridge, rulesVersion: RULES });

  const resolution = await resolver.ensureLegalContext({ identity: IDENTITY, datasetSha256: HASH });

  assert.equal(resolution.status, "blocked");
  assert.equal(resolution.reason, "IDENTITY_MISMATCH");
});

test("blocks the legal field with a typed reason when the rebuild fails", async () => {
  const bridge = bridgeStub();
  bridge.getLegalContext = async () => { bridge.calls.get += 1; throw notFound(); };
  bridge.rebuildLegalContext = async () => {
    bridge.calls.rebuild += 1;
    const error = new Error("evidência documental local insuficiente");
    error.status = 409;
    error.code = "DOCUMENT_EVIDENCE_MISSING";
    throw error;
  };
  const resolver = createLegalContextResolver({ bridge, rulesVersion: RULES });

  const resolution = await resolver.ensureLegalContext({ identity: IDENTITY, datasetSha256: HASH });

  assert.equal(resolution.status, "blocked");
  assert.equal(resolution.source, null);
  assert.equal(resolution.reason, "DOCUMENT_EVIDENCE_MISSING");
  assert.equal(resolution.context, null);
});

test("rebuilds when the bridge exposes no context endpoint at all", async () => {
  const bridge = bridgeStub();
  bridge.getLegalContext = async () => { bridge.calls.get += 1; throw notFound(); };
  const resolver = createLegalContextResolver({ bridge, rulesVersion: RULES });

  const resolution = await resolver.ensureLegalContext({ identity: IDENTITY, datasetSha256: HASH });

  assert.equal(resolution.status, "rebuilt");
  assert.equal(resolution.source, "rebuilt");
});
