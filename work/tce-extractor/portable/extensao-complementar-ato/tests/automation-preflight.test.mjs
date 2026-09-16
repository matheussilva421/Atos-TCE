import test from "node:test";
import assert from "node:assert/strict";

import { prepareAutomaticAct } from "../lib/automation-preflight.js";

const HASH = "a".repeat(64);
const IDENTITY = {
  processKey: "103439/2023",
  interestedNormalized: "ana da silva",
};

const ALLOWED_FIELDS = [
  "modalidade",
  "fundamento_legal",
  "data_publicacao_doe",
  "cargo",
  "matricula",
  "data_nascimento",
  "genero",
];

const values = {
  modalidade: "m-special",
  fundamento_legal: "f-professor",
  data_publicacao_doe: "07/02/2020",
  cargo: "Professor",
  matricula: "103.870-2/1",
  data_nascimento: "30/04/1967",
  genero: "Feminino",
};

function field(value, overrides = {}) {
  return {
    status: "found",
    confidence: "high",
    source_value: value,
    form_value: value,
    citation: null,
    ...overrides,
  };
}

function missingField() {
  return field(null, {
    status: "missing",
    confidence: "none",
    source_value: null,
    form_value: null,
  });
}

function record(overrides = {}) {
  return {
    dataset_sha256: HASH,
    process: { key: IDENTITY.processKey, number: "103439", year: "2023" },
    interested: { original: "Ana da Silva", normalized: IDENTITY.interestedNormalized },
    status: "ready",
    fields: Object.fromEntries(ALLOWED_FIELDS.map((name) => [name, field(values[name])])),
    ...overrides,
  };
}

function snapshot(overrides = {}) {
  return {
    role: "form",
    generation: 8,
    frameId: 4,
    currentGeneration: 8,
    currentFrameId: 4,
    dataset_sha256: HASH,
    identity: IDENTITY,
    fields: Object.fromEntries(ALLOWED_FIELDS.map((name) => [
      name,
      { value: "", disabled: false, readOnly: false },
    ])),
    options: {
      modalidade: [{ value: values.modalidade, label: "Especial" }],
      fundamento_legal: [{ value: values.fundamento_legal, label: "Regra do professor" }],
      genero: [{ value: values.genero, label: values.genero }],
    },
    ...overrides,
  };
}

const context = {
  schema_version: 1,
  dataset_sha256: HASH,
  process_key: IDENTITY.processKey,
  interested_normalized: IDENTITY.interestedNormalized,
  resolution_status: "complete",
  operative_text: "RESOLVE: Art. 40, § 5º.",
  pages: [],
  context_revision: 12,
  rules_version: "legal-foundation-v1",
};

const legalDecision = {
  status: "selected",
  method: "rule",
  rule_id: "EC41_SEM_P5",
  option_value: values.fundamento_legal,
  option_label: "Regra do professor",
  confidence: 0.96,
  margin: 0.20,
  hard_conflict: false,
  rules_version: "legal-foundation-v1",
};

function input(overrides = {}) {
  return {
    record: record(),
    context,
    snapshot: snapshot(),
    legalDecision,
    ...overrides,
  };
}

test("prepares only the seven allowlisted fields when the snapshot is empty", () => {
  const result = prepareAutomaticAct(input());

  assert.equal(result.eligible, true);
  assert.deepEqual(Object.keys(result.fields), ALLOWED_FIELDS);
  assert.deepEqual(result.fields, values);
  assert.deepEqual(result.preserved, {});
  assert.deepEqual(result.reasons, []);
});

test("allows missing gender but rejects every other missing field", () => {
  const genderMissing = prepareAutomaticAct(input({
    record: record({
      fields: {
        ...record().fields,
        genero: missingField(),
      },
    }),
  }));

  assert.equal(genderMissing.eligible, true);
  assert.deepEqual(genderMissing.fields, Object.fromEntries(
    Object.entries(values).filter(([fieldName]) => fieldName !== "genero"),
  ));
  assert.deepEqual(genderMissing.reasons, []);

  for (const requiredField of ALLOWED_FIELDS.filter((fieldName) => fieldName !== "genero")) {
    const result = prepareAutomaticAct(input({
      record: record({
        fields: {
          ...record().fields,
          [requiredField]: missingField(),
        },
      }),
    }));

    assert.equal(result.eligible, false, `${requiredField} must block preflight`);
    assert.deepEqual(result.fields, {}, `${requiredField} must not produce a partial write`);
    assert.ok(result.reasons.includes("FIELD_PROPOSAL_MISSING"), requiredField);
  }
});

test("preserves empty and conservatively equivalent current values", () => {
  const result = prepareAutomaticAct(input({
    snapshot: snapshot({
      fields: {
        ...snapshot().fields,
        cargo: { value: "  Professor ", disabled: false, readOnly: false },
        matricula: { value: "", disabled: false, readOnly: false },
      },
    }),
  }));

  assert.equal(result.eligible, true);
  assert.equal(result.fields.cargo, undefined);
  assert.equal(result.fields.matricula, values.matricula);
  assert.deepEqual(result.preserved, { cargo: "  Professor " });
});

test("aborts the whole preparation on any existing-value divergence", () => {
  const result = prepareAutomaticAct(input({
    snapshot: snapshot({
      fields: {
        ...snapshot().fields,
        cargo: { value: "Analista", disabled: false, readOnly: false },
        matricula: { value: "Outra matrícula", disabled: false, readOnly: false },
      },
    }),
  }));

  assert.equal(result.eligible, false);
  assert.deepEqual(result.fields, {});
  assert.ok(result.reasons.includes("EXISTING_VALUE_CONFLICT"));
  assert.deepEqual(result.preserved, {
    cargo: "Analista",
    matricula: "Outra matrícula",
  });
});

test("preserves disabled and readOnly controls without treating them as writable", () => {
  const result = prepareAutomaticAct(input({
    snapshot: snapshot({
      fields: {
        ...snapshot().fields,
        cargo: { value: "", disabled: true, readOnly: false },
        matricula: { value: "", disabled: false, readOnly: true },
      },
    }),
  }));

  assert.equal(result.eligible, false);
  assert.deepEqual(result.fields, {});
  assert.deepEqual(result.preserved, { cargo: "", matricula: "" });
  assert.ok(result.reasons.includes("FIELD_DISABLED"));
  assert.ok(result.reasons.includes("FIELD_READ_ONLY"));
});

test("accepts valid civil dates and rejects impossible dates before preparing fields", () => {
  assert.equal(prepareAutomaticAct(input()).eligible, true);

  const result = prepareAutomaticAct(input({
    record: record({
      fields: {
        ...record().fields,
        data_publicacao_doe: field("31/02/2020"),
      },
    }),
  }));

  assert.equal(result.eligible, false);
  assert.deepEqual(result.fields, {});
  assert.ok(result.reasons.includes("INVALID_CIVIL_DATE"));
});

test("treats DD/MM/YYYY and ISO YYYY-MM-DD as the same civil date in either direction", () => {
  const result = prepareAutomaticAct(input({
    record: record({
      fields: {
        ...record().fields,
        data_publicacao_doe: field("07/02/2020"),
        data_nascimento: field("1967-04-30"),
      },
    }),
    snapshot: snapshot({
      fields: {
        ...snapshot().fields,
        data_publicacao_doe: { value: "2020-02-07", disabled: false, readOnly: false },
        data_nascimento: { value: "30/04/1967", disabled: false, readOnly: false },
      },
    }),
  }));

  assert.equal(result.eligible, true);
  assert.deepEqual(result.preserved, {
    data_publicacao_doe: "2020-02-07",
    data_nascimento: "30/04/1967",
  });
  assert.deepEqual(result.fields, Object.fromEntries(
    Object.entries(values).filter(([fieldName]) => !["data_publicacao_doe", "data_nascimento"].includes(fieldName)),
  ));
});

test("treats valid portal date separators as the same civil date", () => {
  const result = prepareAutomaticAct(input({
    record: record({
      fields: {
        ...record().fields,
        data_publicacao_doe: field("10-09-2024"),
      },
    }),
    snapshot: snapshot({
      fields: {
        ...snapshot().fields,
        data_publicacao_doe: { value: "2024/09/10", disabled: false, readOnly: false },
      },
    }),
  }));

  assert.equal(result.eligible, true);
  assert.equal(result.reasons.includes("EXISTING_VALUE_CONFLICT"), false);
  assert.equal(result.preserved.data_publicacao_doe, "2024/09/10");
  assert.equal(result.fields.data_publicacao_doe, undefined);
});

test("does not treat equal unknown or invalid date strings as equivalent", () => {
  const invalid = "31.02.2020";
  const result = prepareAutomaticAct(input({
    record: record({
      fields: {
        ...record().fields,
        data_publicacao_doe: field(invalid),
      },
    }),
    snapshot: snapshot({
      fields: {
        ...snapshot().fields,
        data_publicacao_doe: { value: invalid, disabled: false, readOnly: false },
      },
    }),
  }));

  assert.equal(result.eligible, false);
  assert.ok(result.reasons.includes("INVALID_CIVIL_DATE"));
  assert.ok(result.reasons.includes("CURRENT_CIVIL_DATE_INVALID"));
  assert.ok(result.reasons.includes("EXISTING_VALUE_CONFLICT"));
});

test("requires every proposed select value to remain in the current catalog", () => {
  const result = prepareAutomaticAct(input({
    snapshot: snapshot({
      options: {
        ...snapshot().options,
        fundamento_legal: [{ value: "other-foundation", label: "Outra regra" }],
      },
    }),
  }));

  assert.equal(result.eligible, false);
  assert.deepEqual(result.fields, {});
  assert.ok(result.reasons.includes("OPTION_VALUE_NOT_PRESENT"));
});

test("uses resolver-selected option values instead of documentary select labels", () => {
  const result = prepareAutomaticAct(input({
    record: record({
      fields: {
        ...record().fields,
        modalidade: field("Especial"),
        fundamento_legal: field("Regra do professor"),
      },
    }),
    matchedValues: {
      modalidade: values.modalidade,
      fundamento_legal: values.fundamento_legal,
    },
    matchKinds: {
      modalidade: "exact",
      fundamento_legal: "exact",
    },
  }));

  assert.equal(result.eligible, true);
  assert.deepEqual(result.fields, values);
});

test("preserves a tied select match when the current value equals the matched catalog value", () => {
  for (const fieldName of ["modalidade", "fundamento_legal"]) {
    const result = prepareAutomaticAct(input({
      snapshot: snapshot({
        fields: {
          ...snapshot().fields,
          [fieldName]: { value: values[fieldName], disabled: false, readOnly: false },
        },
      }),
      matchedValues: {
        modalidade: values.modalidade,
        fundamento_legal: values.fundamento_legal,
      },
      matchKinds: {
        modalidade: "exact",
        fundamento_legal: "exact",
        [fieldName]: "tie",
      },
    }));

    assert.equal(result.eligible, true, fieldName);
    assert.equal(result.reasons.includes("SELECT_MATCH_TIE"), false, fieldName);
    assert.equal(result.fields[fieldName], undefined, fieldName);
    assert.equal(result.preserved[fieldName], values[fieldName], fieldName);
  }
});

test("keeps an empty tied select field blocked", () => {
  const result = prepareAutomaticAct(input({
    matchedValues: {
      modalidade: values.modalidade,
      fundamento_legal: values.fundamento_legal,
    },
    matchKinds: {
      modalidade: "tie",
      fundamento_legal: "exact",
    },
  }));

  assert.equal(result.eligible, false);
  assert.deepEqual(result.fields, {});
  assert.ok(result.reasons.includes("SELECT_MATCH_TIE"));
});

test("keeps a divergent tied select field blocked", () => {
  const result = prepareAutomaticAct(input({
    snapshot: snapshot({
      fields: {
        ...snapshot().fields,
        modalidade: { value: "m-other", disabled: false, readOnly: false },
      },
    }),
    matchedValues: {
      modalidade: values.modalidade,
      fundamento_legal: values.fundamento_legal,
    },
    matchKinds: {
      modalidade: "tie",
      fundamento_legal: "exact",
    },
  }));

  assert.equal(result.eligible, false);
  assert.deepEqual(result.fields, {});
  assert.ok(result.reasons.includes("SELECT_MATCH_TIE"));
});

test("requires a complete context with a matching dataset hash", async (t) => {
  for (const [name, changedContext, reason] of [
    ["missing", null, "CONTEXT_MISSING"],
    ["incomplete", { ...context, resolution_status: "incomplete" }, "CONTEXT_INCOMPLETE"],
    ["hash mismatch", { ...context, dataset_sha256: "b".repeat(64) }, "CONTEXT_HASH_MISMATCH"],
  ]) {
    await t.test(name, () => {
      const result = prepareAutomaticAct(input({ context: changedContext }));
      assert.equal(result.eligible, false);
      assert.deepEqual(result.fields, {});
      assert.ok(result.reasons.includes(reason));
    });
  }
});

test("requires canonical identity and the current generation and frame", async (t) => {
  const cases = [
    ["identity", { identity: { processKey: "9/2024", interestedNormalized: "ana da silva" } }, "IDENTITY_MISMATCH"],
    ["generation", { currentGeneration: 7 }, "STALE_GENERATION"],
    ["frame", { currentFrameId: 3 }, "STALE_FRAME"],
  ];

  for (const [name, changedSnapshot, reason] of cases) {
    await t.test(name, () => {
      const result = prepareAutomaticAct(input({ snapshot: snapshot(changedSnapshot) }));
      assert.equal(result.eligible, false);
      assert.deepEqual(result.fields, {});
      assert.ok(result.reasons.includes(reason));
    });
  }
});

test("requires a selected legal decision instead of pending or tied candidates", async (t) => {
  for (const status of ["pending", "tie"]) {
    await t.test(status, () => {
      const result = prepareAutomaticAct(input({ legalDecision: { ...legalDecision, status } }));
      assert.equal(result.eligible, false);
      assert.deepEqual(result.fields, {});
      assert.ok(result.reasons.includes("LEGAL_DECISION_NOT_SELECTED"));
    });
  }
});

test("prepares fields for a selected legal decision based on similarity", () => {
  const result = prepareAutomaticAct(input({
    legalDecision: { ...legalDecision, method: "similarity" },
  }));

  assert.equal(result.eligible, true);
  assert.deepEqual(result.fields, values);
  assert.deepEqual(result.preserved, {});
  assert.deepEqual(result.reasons, []);
});

test("requires v2 confidence and margin before preparing the legal field", () => {
  for (const [name, decision, reason] of [
    ["low confidence", { confidence: 0.82, margin: 0.20 }, "LEGAL_DECISION_REVIEW_REQUIRED"],
    ["small margin", { confidence: 0.95, margin: 0.03 }, "LEGAL_DECISION_REVIEW_REQUIRED"],
    ["hard conflict", { confidence: 0.99, margin: 0.30, hard_conflict: true }, "LEGAL_DECISION_REVIEW_REQUIRED"],
  ]) {
    const result = prepareAutomaticAct(input({
      legalDecision: { ...legalDecision, ...decision },
    }));

    assert.equal(result.eligible, false, name);
    assert.deepEqual(result.fields, {}, name);
    assert.ok(result.reasons.includes(reason), name);
  }
});

test("does not return private keys, DOM nodes, or token values", () => {
  const domNode = { nodeType: 1, nodeName: "INPUT", value: "secret-token" };
  const result = prepareAutomaticAct(input({
    record: {
      ...record(),
      token: "secret-token",
      fields: {
        ...record().fields,
        cargo: field("Bearer secret-token"),
      },
    },
    snapshot: snapshot({ dom: domNode }),
  }));
  const serialized = JSON.stringify(result);

  assert.equal(result.eligible, false);
  assert.deepEqual(result.fields, {});
  assert.doesNotMatch(serialized, /secret-token/u);
  assert.doesNotMatch(serialized, /"(?:token|cookie|session|password|url|dom|node)"/iu);
  assert.equal(Object.values(result).some((value) => value === domNode), false);
});
