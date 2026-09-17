import test from "node:test";
import assert from "node:assert/strict";

import { buildCatalogOptionSignature } from "../lib/catalog-option-signature.js";

const signatureOf = (label, value = "catalog-option") => buildCatalogOptionSignature({ value, label }, 0);

test("detecta transição EC41 geral sem metadata artificial", () => {
  const result = buildCatalogOptionSignature({
    value: "general",
    label: "Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 2º da Emenda Constitucional nº 47/2005",
  }, 0);
  assert.equal(result.class_id, "EC41_TRANSITION_GENERAL");
  assert.equal(result.scope, "civil");
  assert.equal(result.teacher_rule, false);
});

test("detecta regra docente por CF art. 40 § 5º", () => {
  const result = buildCatalogOptionSignature({
    value: "teacher",
    label: "Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 40, § 5º, Constituição Federal e artigo 2º da Emenda Constitucional nº 47/2005",
  }, 0);
  assert.equal(result.class_id, "EC41_TRANSITION_TEACHER");
  assert.equal(result.teacher_rule, true);
});

test("detecta EC47 art. 3º estruturalmente", () => {
  const result = signatureOf("Civil - Artigo 3º, incisos I a III e parágrafo único, da Emenda Constitucional nº 47/2005");
  assert.equal(result.class_id, "EC47_ART3");
  assert.equal(result.modality, "voluntary_contribution");
  assert.equal(result.proportionality, "integral");
});

test("detecta EC41 art. 6º-A com EC 70/2012", () => {
  const result = signatureOf("Civil - Artigo 6º-A, parágrafo único, da Emenda Constitucional nº 41/2003, com redação dada pela Emenda Constitucional nº 70/2012");
  assert.equal(result.class_id, "EC41_ART6A_EC70");
  assert.equal(result.modality, "invalidity_permanent_disability");
});

test("detecta EC 20/1998 art. 8º", () => {
  const result = signatureOf("Civil - Artigo 8º, incisos I e II, §1º, alíneas a e b, da Emenda Constitucional nº 20/1998");
  assert.equal(result.class_id, "EC20_ART8");
  assert.equal(result.scope, "civil");
});

test("detecta CF art. 40 § 1º inciso I", () => {
  const result = signatureOf("Civil - Artigo 40, § 1º, inciso I, da Constituição Federal");
  assert.equal(result.class_id, "CF40_I");
  assert.equal(result.modality, "invalidity_permanent_disability");
});

test("detecta CF art. 40 § 1º inciso III alínea a", () => {
  const result = signatureOf("Civil - Artigo 40, § 1º, inciso III, alínea a, da Constituição Federal");
  assert.equal(result.class_id, "CF40_III_A");
  assert.equal(result.modality, "voluntary_contribution");
});

test("detecta CF art. 40 § 1º inciso III alínea b", () => {
  const result = signatureOf("Civil - Artigo 40, § 1º, inciso III, alínea b, da Constituição Federal");
  assert.equal(result.class_id, "CF40_III_B");
});

test("separa CF art. 40 § 1º III a combinado com § 5º", () => {
  const result = signatureOf("Civil - Artigo 40, §1º, inciso III, alínea a, combinado com o §5º, da Constituição Federal");
  assert.equal(result.class_id, "CF40_III_A_P5");
  assert.equal(result.teacher_rule, true);
});

test("detecta opção militar", () => {
  const result = signatureOf("Militar - regra de transição de militar", "military");
  assert.equal(result.class_id, "MILITARY_TRANSITION");
  assert.equal(result.scope, "military");
});

test("placeholder não é selecionável e não inventa classe", () => {
  const result = buildCatalogOptionSignature({ value: "", label: "Selecione uma fundamentação" }, 3);
  assert.equal(result.selectable, false);
  assert.equal(result.class_id, "CATALOG_OPTION_3");
  assert.equal(result.teacher_rule, false);
  assert.deepEqual(result.references, []);
});

test("catalogo cru de EC41 com EC47 não declara regra docente", () => {
  const result = signatureOf("Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 2º da Emenda Constitucional nº 47/2005");
  assert.equal(result.class_id, "EC41_TRANSITION_GENERAL");
  assert.equal(result.teacher_rule, false);
  assert.ok(result.references.some((reference) => reference.diploma_type === "ec" && reference.diploma_number === "47"));
});

test("aceita opção string simples sem metadata", () => {
  const result = buildCatalogOptionSignature("Civil - Artigo 40, § 1º, inciso II, da Constituição Federal", 1);
  assert.equal(result.class_id, "CF40_II");
  assert.equal(result.value, "Civil - Artigo 40, § 1º, inciso II, da Constituição Federal");
  assert.equal(result.label, "Civil - Artigo 40, § 1º, inciso II, da Constituição Federal");
  assert.equal(result.selectable, true);
});
