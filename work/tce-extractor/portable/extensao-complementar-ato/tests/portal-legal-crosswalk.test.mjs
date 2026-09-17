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
// The real portal publishes only value and label: the whole matrix below runs
// against the raw catalog shape and never injects class_id, scope or rule_id.
const catalogLabels = [...new Set(fixture.catalog.map(({ label }) => label))];
const labelForClass = Object.fromEntries(fixture.catalog.map(({ class_id, label }) => [class_id, label]));
const classForValue = Object.fromEntries(catalogLabels.map((label, index) => [`raw-${index + 1}`, fixture.catalog.find((entry) => entry.label === label).class_id]));
const portalOptions = catalogLabels.map((label, index) => ({ value: `raw-${index + 1}`, label, selectable: true }));
const optionsForClasses = (classIds) => portalOptions.filter(({ value }) => classIds.includes(classForValue[value]));
const CASE = fixture.cases.find(({ case_id }) => case_id === "ece20_prof_voluntary_integral");

test("rejects the teacher rule when the professor rule is absent from the operative text", () => {
  const options = optionsForClasses(["EC41_TRANSITION_GENERAL", "EC41_TRANSITION_TEACHER"]);
  const result = classifyPortalLegalFoundation({
    operativeText: "RESOLVE conceder aposentadoria voluntária por tempo de contribuição, com proventos integrais, a servidor ocupante do cargo de PROFESSOR, com fundamento no art. 7º da Emenda Constitucional Estadual nº 20/2020.",
    cargo: "PROFESSOR",
    options,
  });

  const teacher = result.ranking.find(({ class_id }) => class_id === "EC41_TRANSITION_TEACHER");
  assert.equal(teacher.rejected, true);
  assert.ok(teacher.reasons.includes("hard-reject:teacher-rule-not-operative"));
  assert.equal(result.class_id, "EC41_TRANSITION_GENERAL");
});

test("keeps the teacher candidate viable when the operative text states the professor rule", () => {
  const options = optionsForClasses(["EC41_TRANSITION_GENERAL", "EC41_TRANSITION_TEACHER"]);
  const result = classifyPortalLegalFoundation({
    operativeText: "RESOLVE conceder aposentadoria voluntária por tempo de contribuição, com proventos integrais, a servidor ocupante do cargo de PROFESSOR, com fundamento no art. 6º e art. 7º da Emenda Constitucional nº 41/2003 c/c o artigo 40, § 5º, Constituição Federal e artigo 2º da Emenda Constitucional nº 47/2005.",
    cargo: "PROFESSOR",
    options,
  });

  const teacher = result.ranking.find(({ class_id }) => class_id === "EC41_TRANSITION_TEACHER");
  assert.equal(teacher.rejected, false);
  assert.equal(result.ranking[0].class_id, "EC41_TRANSITION_TEACHER");
});

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
    options: optionsForClasses(["CF40_III_A", "CF40_III_B"]),
  });

  assert.equal(result.ranking[0].class_id, "CF40_III_A");
  assert.equal(result.ranking.find(({ class_id }) => class_id === "CF40_III_B").rejected, true);
  assert.ok(result.ranking.find(({ class_id }) => class_id === "CF40_III_B").reasons.includes("hard-reject:alinea-mismatch"));
});

test("does not route incapacity for a professor to the voluntary teacher class", () => {
  const result = classifyPortalLegalFoundation({
    operativeText: "aposentadoria por incapacidade permanente, com proventos integrais, a servidor ocupante do cargo de PROFESSOR",
    cargo: "PROFESSOR",
    options: optionsForClasses(["CF40_I", "EC41_TRANSITION_TEACHER"]),
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
  const knownClasses = new Set(Object.values(classForValue));

  for (const testCase of fixture.cases) {
    const allowedClasses = testCase.option_class_ids ?? [...knownClasses];
    assert.ok(allowedClasses.length > 0, `${testCase.case_id}: empty option set`);
    const options = optionsForClasses(allowedClasses);
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
