const SHA256_RE = /^[a-f0-9]{64}$/u;

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function resolution(status, source, reason, context = null) {
  return { status, source, reason, context };
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
function contextDefect(context, { identity, datasetSha256, rulesVersion }) {
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
  if (!Array.isArray(context.pages)) return "CONTEXT_INCOMPLETE";
  if (!Number.isSafeInteger(context.context_revision) || context.context_revision < 0) {
    return "CONTEXT_REVISION_MISSING";
  }
  if (typeof rulesVersion === "string" && rulesVersion && context.rules_version !== rulesVersion) {
    return "RULES_VERSION_MISMATCH";
  }
  return null;
}

export function createLegalContextResolver({ bridge, rulesVersion }) {
  const cache = new Map();
  const identityKey = (identity) => `${identity.processKey}\u0000${identity.interestedNormalized}`;

  function cachedFor(key) {
    for (const [entryKey, context] of cache) {
      if (entryKey.startsWith(key)) return context;
    }
    return null;
  }

  async function rebuild(identity) {
    if (typeof bridge.rebuildLegalContext !== "function") return null;
    const envelope = await bridge.rebuildLegalContext(identity);
    return { source: "rebuilt", context: envelope?.context ?? null };
  }

  return {
    async ensureLegalContext({ identity, datasetSha256 = null } = {}) {
      const key = `${identityKey(identity)}\u0000${datasetSha256 ?? ""}\u0000${rulesVersion}\u0000`;
      const cached = cachedFor(key);
      if (cached !== null) return resolution("ready", "cache", null, cached);

      const expected = { identity, datasetSha256, rulesVersion };
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

      cache.set(`${key}${context.context_revision}`, context);
      return resolution(source === "rebuilt" ? "rebuilt" : "ready", source, null, context);
    },
  };
}
