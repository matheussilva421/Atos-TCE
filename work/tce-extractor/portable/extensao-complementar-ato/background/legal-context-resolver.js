const SHA256_RE = /^[a-f0-9]{64}$/u;

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function resolution(status, source, reason, context = null) {
  return { status, source, reason, context };
}

/**
 * Exact cache keys: revisions are compared as values, never as string
 * prefixes, so revision 4 can never be served by a revision 44 entry.
 */
function baseCacheKey({ identity, datasetSha256, rulesVersion }) {
  return JSON.stringify([
    identity.processKey,
    identity.interestedNormalized,
    datasetSha256 ?? null,
    rulesVersion,
  ]);
}

function revisionCacheKey(baseKey, revision) {
  return JSON.stringify([baseKey, revision]);
}

function errorReason(error) {
  const code = typeof error?.code === "string" && error.code ? error.code : "";
  if (code === "LEGAL_CONTEXT_NOT_FOUND" || error?.status === 404) return "LEGAL_CONTEXT_NOT_FOUND";
  if (code) return code;
  return "LEGAL_CONTEXT_UNAVAILABLE";
}

/**
 * Validates a legal context defensively before it can authorize the legal
 * foundation field. Any divergence blocks only `fundamento_legal`.
 */
function contextDefect(context, { identity, datasetSha256, rulesVersion, contextRevision = null }) {
  if (!isRecord(context)) return "CONTEXT_INCOMPLETE";
  if (context.schema_version !== 1) return "CONTEXT_INCOMPLETE";
  if (typeof context.dataset_sha256 !== "string" || !SHA256_RE.test(context.dataset_sha256)) return "CONTEXT_INCOMPLETE";
  if (datasetSha256 !== null && datasetSha256 !== undefined && context.dataset_sha256 !== datasetSha256) {
    return "DATASET_MISMATCH";
  }
  if (context.process_key !== identity.processKey
    || context.interested_normalized !== identity.interestedNormalized) {
    return "IDENTITY_MISMATCH";
  }
  if (context.resolution_status !== "complete") return "CONTEXT_INCOMPLETE";
  if (typeof context.operative_text !== "string" || !context.operative_text.trim()) return "CONTEXT_INCOMPLETE";
  if (context.extraction_version !== "legal-context-v4") return "CONTEXT_INCOMPLETE";
  if (!Array.isArray(context.pages)) return "CONTEXT_INCOMPLETE";
  if (context.pages.length === 0) return "CONTEXT_INCOMPLETE";
  if (!Number.isSafeInteger(context.context_revision) || context.context_revision < 0) {
    return "CONTEXT_REVISION_MISSING";
  }
  if (Number.isSafeInteger(contextRevision) && context.context_revision !== contextRevision) {
    return "CONTEXT_REVISION_MISMATCH";
  }
  if (typeof rulesVersion === "string" && rulesVersion && context.rules_version !== rulesVersion) {
    return "RULES_VERSION_MISMATCH";
  }
  return null;
}

export function createLegalContextResolver({ bridge, rulesVersion }) {
  const cache = new Map();

  async function rebuild(identity) {
    if (typeof bridge.rebuildLegalContext !== "function") return null;
    const envelope = await bridge.rebuildLegalContext(identity);
    return { source: "rebuilt", context: envelope?.context ?? null };
  }

  return {
    async ensureLegalContext({ identity, datasetSha256 = null, contextRevision = null } = {}) {
      const baseKey = baseCacheKey({ identity, datasetSha256, rulesVersion });
      // Only a pinned revision may be served from cache: without an explicit
      // revision the current source is always consulted, so a newer sidecar
      // revision can never be masked by an older cached entry.
      if (Number.isSafeInteger(contextRevision)) {
        const cached = cache.get(revisionCacheKey(baseKey, contextRevision));
        if (cached !== undefined) return resolution("ready", "cache", null, cached);
      }

      const expected = { identity, datasetSha256, rulesVersion, contextRevision };
      let source = "sidecar";
      let context = null;
      let defect = "LEGAL_CONTEXT_NOT_FOUND";
      try {
        const envelope = await bridge.getLegalContext(identity);
        context = envelope?.context ?? null;
        defect = context === null
          ? "CONTEXT_INCOMPLETE"
          : contextDefect(context, expected);
      } catch (error) {
        defect = errorReason(error);
      }

      // An explicit incomplete or conflicting document resolution cannot be
      // repaired by rebuilding the same evidence: block the field directly.
      if (context !== null && context.resolution_status !== "complete") {
        return resolution("blocked", null, "CONTEXT_INCOMPLETE");
      }

      if (defect !== null) {
        try {
          const rebuilt = await rebuild(identity);
          if (rebuilt !== null) {
            source = rebuilt.source;
            context = rebuilt.context;
            defect = context === null ? "CONTEXT_INCOMPLETE" : contextDefect(context, expected);
          }
        } catch (error) {
          return resolution("blocked", null, errorReason(error));
        }
      }

      if (defect === "LEGAL_CONTEXT_NOT_FOUND") defect = "LEGAL_CONTEXT_UNAVAILABLE";
      if (defect !== null) return resolution("blocked", null, defect);

      cache.set(revisionCacheKey(baseKey, context.context_revision), context);
      return resolution(source === "rebuilt" ? "rebuilt" : "ready", source, null, context);
    },
  };
}
