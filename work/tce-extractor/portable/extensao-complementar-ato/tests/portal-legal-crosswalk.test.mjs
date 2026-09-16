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
