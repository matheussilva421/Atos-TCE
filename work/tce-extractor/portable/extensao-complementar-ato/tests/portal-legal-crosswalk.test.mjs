import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { classifyPortalLegalFoundation } from "../lib/portal-legal-crosswalk.js";

const fixturePath = join(
  dirname(fileURLToPath(import.meta.url)),
  "../../../tests/fixtures/legal-foundations-professores-v2.json",
);
const fixture = JSON.parse(await readFile(fixturePath, "utf8"));
const portalOptions = fixture.catalog.map(({ class_id, scope, label }, index) => ({
  class_id,
  scope,
  label,
  value: `fixture-${index + 1}`,
  selectable: true,
}));
const CASE = fixture.cases.find(({ case_id }) => case_id === "ece20_prof_voluntary_integral");

test("ECE 20/2020 professor voluntary integral can map to a legacy civil portal class", () => {
  const result = classifyPortalLegalFoundation({
    operativeText: CASE.operative_text,
    cargo: CASE.hints.cargo,
    options: portalOptions,
  });

  assert.notEqual(result.status, "pending");
  assert.equal(result.scope, "civil");
  assert.notEqual(result.reason, "family-conflict");
  assert.ok(["EC41_TRANSITION_GENERAL", "EC41_TRANSITION_TEACHER"].includes(result.ranking[0].class_id));
  assert.ok(result.ranking.every((candidate) => candidate.scope !== "military" || candidate.rejected));
  assert.ok(result.reasons.some((reason) => reason.includes("ECE20_ART7_VOLUNTARY_TRANSITION")));
  assert.equal(result.score_components.lexical_weight, 0.05);
});

test("rejects a sibling option with a different discriminating alinea", () => {
  const result = classifyPortalLegalFoundation({
    operativeText: "aposentadoria voluntária por tempo de contribuição, art. 40, §1º, inciso III, alínea a, da Constituição Federal",
    cargo: "PROFESSOR",
    options: portalOptions.filter(({ class_id }) => ["CF40_III_A", "CF40_III_B"].includes(class_id)),
  });

  assert.equal(result.ranking[0].class_id, "CF40_III_A");
  assert.equal(result.ranking.find(({ class_id }) => class_id === "CF40_III_B").rejected, true);
  assert.ok(result.ranking.find(({ class_id }) => class_id === "CF40_III_B").reasons.includes("hard-reject:alinea-mismatch"));
});

test("does not route incapacity for a professor to the voluntary teacher class", () => {
  const result = classifyPortalLegalFoundation({
    operativeText: "aposentadoria por incapacidade permanente, com proventos integrais, a servidor ocupante do cargo de PROFESSOR",
    cargo: "PROFESSOR",
    options: portalOptions.filter(({ class_id }) => ["CF40_I", "EC41_TRANSITION_TEACHER"].includes(class_id)),
  });

  assert.equal(result.ranking[0].class_id, "CF40_I");
  assert.notEqual(result.ranking[0].class_id, "EC41_TRANSITION_TEACHER");
  assert.equal(result.automatic, false);
  assert.equal(result.status, "review");
});

test("keeps loose lexical similarity out of automatic selection", () => {
  const result = classifyPortalLegalFoundation({
    operativeText: "aposentadoria voluntária por tempo de contribuição com fundamento no art. 9º da EC 41/2003",
    cargo: "SERVIDOR",
    options: [
      { class_id: "EC41_ART1", scope: "civil", value: "first", label: "Civil - Artigo 1º da Emenda Constitucional nº 41/2003", selectable: true },
      { class_id: "EC41_ART2", scope: "civil", value: "second", label: "Civil - Artigo 2º da Emenda Constitucional nº 41/2003", selectable: true },
    ],
  });

  assert.notEqual(result.status, "selected");
  assert.equal(result.automatic, false);
  assert.equal(result.method, "none");
});

test("covers the professor validation matrix with explicit expected outcomes", () => {
  assert.equal(fixture.cases.length, 12);
  const categoryCounts = fixture.cases.reduce((counts, testCase) => {
    counts[testCase.category] = (counts[testCase.category] ?? 0) + 1;
    return counts;
  }, {});
  assert.deepEqual(categoryCounts, {
    voluntary_integral: 4,
    voluntary_proportional: 3,
    incapacity: 3,
    ambiguous: 1,
    negative: 1,
  });
  const knownClasses = new Set(portalOptions.map(({ class_id }) => class_id));

  for (const testCase of fixture.cases) {
    const allowedClasses = testCase.option_class_ids ?? [...knownClasses];
    assert.ok(allowedClasses.length > 0, `${testCase.case_id}: empty option set`);
    const options = portalOptions.filter(({ class_id }) => allowedClasses.includes(class_id));
    assert.equal(options.length, allowedClasses.length, `${testCase.case_id}: fixture class is absent from catalog`);
    const result = classifyPortalLegalFoundation({
      operativeText: testCase.operative_text,
      cargo: testCase.hints?.cargo,
      options,
    });

    assert.equal(result.status, testCase.expected_status, testCase.case_id);
    assert.equal(result.automatic, testCase.expected_automatic, testCase.case_id);
    assert.equal(result.scope, testCase.expected_scope, testCase.case_id);
    if (testCase.expected_class_id) assert.equal(result.class_id, testCase.expected_class_id, testCase.case_id);
    if (testCase.expected_reason) assert.equal(result.reason, testCase.expected_reason, testCase.case_id);
    assert.ok(result.profile.evidence.length > 0, `${testCase.case_id}: missing profile evidence`);
  }
});
