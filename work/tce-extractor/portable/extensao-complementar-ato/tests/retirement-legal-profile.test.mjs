import test from "node:test";
import assert from "node:assert/strict";

import { buildRetirementLegalProfile } from "../lib/retirement-legal-profile.js";

const ECE20_CASE = "RESOLVE conceder aposentadoria voluntária por tempo de contribuição, com proventos integrais, a servidor ocupante do cargo de PROFESSOR, com fundamento no art. 7º, incisos I a III, §§ 2º e 4º, inciso I, § 5º, inciso I, e § 11 do art. 6º da Emenda Constitucional Estadual nº 20/2020.";

test("builds voluntary contribution integral profile from ECE20 teacher act", () => {
  const profile = buildRetirementLegalProfile({
    operativeText: ECE20_CASE,
    cargo: "PROFESSOR",
  });

  assert.equal(profile.scope, "civil");
  assert.equal(profile.modality, "voluntary_contribution");
  assert.equal(profile.proportionality, "integral");
  assert.equal(profile.professor_context, true);
  assert.equal(profile.transition_rule, true);
  assert.ok(profile.references.some((reference) => reference.diploma_type === "ece"));
  assert.ok(profile.evidence.includes("proventos:integral"));
});

test("professor cargo alone does not invent explicit teacher constitutional rule", () => {
  const profile = buildRetirementLegalProfile({
    operativeText: "RESOLVE conceder aposentadoria por incapacidade permanente com proventos proporcionais.",
    cargo: "PROFESSOR",
  });

  assert.equal(profile.professor_context, true);
  assert.equal(profile.professor_rule_explicit, false);
  assert.equal(profile.modality, "invalidity_permanent_disability");
  assert.equal(profile.proportionality, "proportional");
});

test("integral proventos do not automatically mean remuneration basis or parity", () => {
  const profile = buildRetirementLegalProfile({
    operativeText: "aposentadoria voluntária por tempo de contribuição com proventos integrais calculados pela média",
    cargo: "PROFESSOR",
  });

  assert.equal(profile.proportionality, "integral");
  assert.equal(profile.calculation_basis, "average");
  assert.notEqual(profile.parity, "yes");
});

test("marks explicit CF paragraph five as a teacher rule without relying on cargo", () => {
  const profile = buildRetirementLegalProfile({
    operativeText: "aposentadoria voluntária por tempo de contribuição com proventos integrais, art. 40, § 5º, da Constituição Federal",
    cargo: "OUTRO CARGO",
  });

  assert.equal(profile.professor_context, false);
  assert.equal(profile.professor_rule_explicit, true);
});
