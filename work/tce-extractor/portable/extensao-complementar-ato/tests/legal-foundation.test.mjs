import test from "node:test";
import assert from "node:assert/strict";

import { parseLegalReferences, resolveLegalFoundation } from "../lib/legal-foundation.js";

const contextFor = (operativeText, overrides = {}) => ({
  schema_version: 1,
  process_key: "SYN-0001/2099",
  resolution_status: "complete",
  operative_text: operativeText,
  pages: [{
    text: operativeText,
    citation: {
      document_id: "resolution-synthetic",
      event_id: "event-1",
      page: 2,
      pdf_sha256: "a".repeat(64),
    },
  }],
  ...overrides,
});

const option = (rule_id, value, label, selectable = true) => ({
  rule_id,
  value,
  label,
  selectable,
});

test("parses an EC article reference without collapsing ECE or losing paragraph", () => {
  const references = parseLegalReferences(
    "Art. 6º, § 5º da EC nº 41/2003 e art. 7º da ECE nº 41/2003",
  );

  assert.equal(references.length, 2);
  assert.deepEqual(references[0], {
    raw: "Art. 6º, § 5º da EC nº 41/2003",
    diploma: { type: "ec", number: "41", year: "2003" },
    article: "6",
    suffix: null,
    paragraph: "5",
    incisos: [],
    qualifiers: [],
    complete: true,
  });
  assert.equal(references[1].diploma.type, "ece");
  assert.equal(references[1].article, "7");
});

test("keeps each article attached to its diploma through c/c and expands inciso ranges", () => {
  const references = parseLegalReferences(
    "Art. 6º, incisos I a IV e art. 7º, ambos da EC nº 41/2003 c/c o art. 2º da EC nº 47/2005",
  );

  assert.equal(references.length, 3);
  assert.deepEqual(references.slice(0, 2).map((reference) => reference.diploma), [
    { type: "ec", number: "41", year: "2003" },
    { type: "ec", number: "41", year: "2003" },
  ]);
  assert.deepEqual(references[0].incisos, ["1", "2", "3", "4"]);
  assert.deepEqual(references[0].qualifiers, ["ambos"]);
  assert.equal(references[1].article, "7");
  assert.deepEqual(references[2].diploma, { type: "ec", number: "47", year: "2005" });
});

test("parses inverted diploma references, article suffixes, unique paragraphs, and CF", () => {
  const references = parseLegalReferences(
    "EC 41/2003, art. 6º-A; Constituição Federal, art. 40, § 1º, inciso II; art. 3º, parágrafo único, da EC 47/2005",
  );

  assert.equal(references.length, 3);
  assert.equal(references[0].article, "6");
  assert.equal(references[0].suffix, "a");
  assert.equal(references[0].diploma.type, "ec");
  assert.equal(references[1].diploma.type, "cf");
  assert.equal(references[1].paragraph, "1");
  assert.deepEqual(references[1].incisos, ["2"]);
  assert.equal(references[2].paragraph, "unico");
});

test("expands plural article references before a shared diploma", () => {
  const references = parseLegalReferences("Arts. 6º e 7º da EC nº 41/2003.");

  assert.deepEqual(references.map((reference) => reference.article), ["6", "7"]);
  assert.deepEqual(references.map((reference) => reference.diploma), [
    { type: "ec", number: "41", year: "2003" },
    { type: "ec", number: "41", year: "2003" },
  ]);
});

test("resolves EC47 article 3 structurally and preserves ranking and citations", () => {
  const result = resolveLegalFoundation({
    context: contextFor(
      "RESOLVE: Art. 3º, incisos I a III e parágrafo único, da EC nº 47/2005.",
    ),
    options: [
      option("MILITAR", "military", "Regra militar"),
      option(
        "EC47_ART3",
        "ec47",
        "Civil - Artigo 3º, incisos I a III e parágrafo único, da Emenda Constitucional nº 47/2005",
      ),
    ],
  });

  assert.equal(result.status, "selected");
  assert.equal(result.method, "rule");
  assert.equal(result.rule_id, "EC47_ART3");
  assert.equal(result.option_value, "ec47");
  assert.equal(result.option_label.startsWith("Civil - Artigo 3"), true);
  assert.ok(result.score > 0);
  assert.equal(result.ranking.length, 2);
  assert.deepEqual(result.citations, [contextFor("x").pages[0].citation]);
});

test("selects EC41 without paragraph 5 and ignores cargo as a paragraph-5 signal", () => {
  const result = resolveLegalFoundation({
    context: contextFor(
      "RESOLVE: Art. 6º, incisos I a IV e art. 7º, ambos da EC nº 41/2003 c/c art. 2º da EC nº 47/2005.",
      { cargo: "Professor" },
    ),
    options: [
      option("EC41_COM_P5", "with-p5", "EC41 com art. 40, § 5º CF"),
      option("EC41_SEM_P5", "without-p5", "EC41 arts. 6º e 7º + EC47 art. 2º"),
    ],
  });

  assert.equal(result.status, "selected");
  assert.equal(result.rule_id, "EC41_SEM_P5");
  assert.equal(result.option_value, "without-p5");
});

test("selects EC41 with paragraph 5 only when CF art. 40 § 5 is operative", () => {
  const result = resolveLegalFoundation({
    context: contextFor(
      "RESOLVE: Art. 6º, incisos I a IV e art. 7º, ambos da EC nº 41/2003 c/c art. 40, § 5º, Constituição Federal e art. 2º da EC nº 47/2005.",
    ),
    options: [
      option("EC41_SEM_P5", "without-p5", "EC41 sem art. 40, § 5º"),
      option("EC41_COM_P5", "with-p5", "EC41 com art. 40, § 5º CF"),
    ],
  });

  assert.equal(result.status, "selected");
  assert.equal(result.rule_id, "EC41_COM_P5");
  assert.equal(result.option_value, "with-p5");
});

test("ignores a historical CF paragraph 5 before the operative RESOLVE marker", () => {
  const result = resolveLegalFoundation({
    context: contextFor(
      "No ato histórico, Constituição Federal art. 40, § 5º. RESOLVE: Art. 7º da EC nº 41/2003.",
    ),
    options: [
      option("EC41_COM_P5", "with-p5", "EC41 com art. 40, § 5º CF"),
      option("EC41_SEM_P5", "without-p5", "EC41 sem art. 40, § 5º"),
    ],
  });

  assert.equal(result.status, "selected");
  assert.equal(result.rule_id, "EC41_SEM_P5");
  assert.equal(result.option_value, "without-p5");
});

test("accepts an isolated EC41 article 7 when it is linked to EC41/2003", () => {
  const result = resolveLegalFoundation({
    context: contextFor("RESOLVE: Art. 7º da EC nº 41/2003."),
    options: [option("EC41_SEM_P5", "without-p5", "EC41 sem art. 40, § 5º")],
  });

  assert.equal(result.status, "selected");
  assert.equal(result.option_value, "without-p5");
  assert.equal(result.rule_id, "EC41_SEM_P5");
});

test("does not let article 6-A participate in the EC41 article 6 rule", () => {
  const result = resolveLegalFoundation({
    context: contextFor("RESOLVE: Art. 6º-A da EC nº 41/2003."),
    options: [
      option("EC41_SEM_P5", "without-p5", "EC41 artigo 6º e artigo 7º"),
      option("EC41_ART6A", "article-6a", "EC41 artigo 6º-A"),
    ],
  });

  assert.equal(result.status, "selected");
  assert.equal(result.option_value, "article-6a");
  assert.equal(result.rule_id, null);
});

test("resolves CF article 40 paragraph 1 item II without an EC rule id", () => {
  const result = resolveLegalFoundation({
    context: contextFor("RESOLVE: Art. 40, § 1º, inciso II da Constituição Federal."),
    options: [
      option("EC47_ART3", "ec47", "EC47 artigo 3º"),
      option("CF40_P1_II", "cf40", "Constituição Federal artigo 40, § 1º, inciso II"),
    ],
  });

  assert.equal(result.status, "selected");
  assert.equal(result.option_value, "cf40");
  assert.equal(result.rule_id, null);
});

test("does not resolve an ECE reference against an EC option", () => {
  const result = resolveLegalFoundation({
    context: contextFor("RESOLVE: Art. 1º da ECE nº 20/2020."),
    options: [option(null, "ec", "Art. 1º da EC nº 20/1998.")],
  });

  assert.equal(result.status, "pending");
  assert.equal(result.option_value, null);
});

test("does not resolve a state constitution reference against a federal option", () => {
  const result = resolveLegalFoundation({
    context: contextFor("RESOLVE: Art. 40 da Constituição Estadual."),
    options: [option(null, "cf", "Art. 40 da Constituição Federal.")],
  });

  assert.equal(result.status, "pending");
  assert.equal(result.option_value, null);
});

test("leaves incompatible EC and ECE references pending", () => {
  const result = resolveLegalFoundation({
    context: contextFor(
      "RESOLVE: Art. 6º da EC nº 41/2003 e art. 7º da ECE nº 41/2003.",
    ),
    options: [option("EC41_SEM_P5", "ec41", "Art. 6º e 7º da EC nº 41/2003.")],
  });

  assert.equal(result.status, "pending");
  assert.equal(result.option_value, null);
});

test("does not select an unrecognized OTHER family by lexical similarity", () => {
  const result = resolveLegalFoundation({
    context: contextFor("RESOLVE: Art. 1º da EC nº 20/2020."),
    options: [option(null, "wrong", "Art. 1º da EC nº 19/1998.")],
  });

  assert.equal(result.status, "pending");
  assert.equal(result.option_value, null);
});

test("leaves EC41 references with divergent years pending across articles", () => {
  const result = resolveLegalFoundation({
    context: contextFor(
      "RESOLVE: Art. 6º da EC nº 41/2003 e art. 7º da EC nº 41/2004.",
    ),
    options: [option("EC41_SEM_P5", "ec41", "Art. 6º e 7º da EC nº 41/2003.")],
  });

  assert.equal(result.status, "pending");
  assert.equal(result.option_value, null);
  assert.ok(result.reasons.includes("contradictory-reference"));
});

test("resolves bare EC47 article 3 and keeps extra qualifiers optional", () => {
  const result = resolveLegalFoundation({
    context: contextFor("RESOLVE: Art. 3º da EC nº 47/2005."),
    options: [option(
      "EC47_ART3",
      "ec47",
      "Civil - Artigo 3º, incisos I a III e parágrafo único, da EC nº 47/2005",
    )],
  });

  assert.equal(result.status, "selected");
  assert.equal(result.method, "rule");
  assert.equal(result.rule_id, "EC47_ART3");
  assert.equal(result.option_value, "ec47");
});

test("exposes only the public LegalDecision statuses and methods", () => {
  const cases = [
    {
      name: "text exact",
      context: contextFor("Artigo 1º da EC nº 20/2020."),
      options: [option(null, "exact", "Artigo 1º da EC nº 20/2020.")],
      status: "selected",
      method: "exact",
    },
    {
      name: "structural family rule",
      context: contextFor("RESOLVE: Art. 7º da EC nº 41/2003."),
      options: [option("EC41_SEM_P5", "structural", "Artigo 7º da EC nº 41/2003")],
      status: "selected",
      method: "rule",
    },
    {
      name: "operational rule",
      context: contextFor("RESOLVE: Art. 3º da EC nº 47/2005."),
      options: [option("EC47_ART3", "rule", "Artigo 3º, parágrafo único, da EC nº 47/2005")],
      status: "selected",
      method: "rule",
    },
    {
      name: "similarity",
      context: contextFor("RESOLVE: Art. 1º da EC nº 20/2020."),
      options: [option(null, "similar", "Artigo 2º da EC nº 20/2020")],
      status: "selected",
      method: "similarity",
    },
    {
      name: "pending",
      context: contextFor("", { resolution_status: "incomplete" }),
      options: [option(null, "pending", "Artigo 1º da EC nº 20/2020")],
      status: "pending",
      method: "none",
    },
  ];

  for (const entry of cases) {
    const result = resolveLegalFoundation({ context: entry.context, options: entry.options });
    assert.ok(["selected", "pending"].includes(result.status), entry.name);
    assert.ok(["exact", "rule", "similarity", "none"].includes(result.method), entry.name);
    assert.equal(result.status, entry.status, entry.name);
    assert.equal(result.method, entry.method, entry.name);
  }
});

test("uses structural equivalence before rule or similarity", () => {
  const result = resolveLegalFoundation({
    context: contextFor("RESOLVE: Art. 7º da EC nº 41/2003."),
    options: [option(
      "EC41_SEM_P5",
      "equivalent",
      "Civil - Artigo 7º da Emenda Constitucional nº 41/2003",
    )],
  });

  assert.equal(result.status, "selected");
  assert.equal(result.method, "rule");
  assert.equal(result.option_value, "equivalent");
});

test("returns pending for empty, incomplete, contradictory, conflicting, and unmatched contexts", () => {
  const cases = [
    [contextFor("   ", { resolution_status: "incomplete" }), "context-incomplete"],
    [contextFor("RESOLVE: Art. 6º da EC nº 41."), "reference-incomplete"],
    [contextFor("RESOLVE: Art. 6º da EC nº 41/2003 e art. 6º da EC nº 41/2004."), "contradictory-reference"],
    [contextFor("RESOLVE: Art. 3º da EC nº 47/2005 e art. 6º da EC nº 41/2003."), "family-conflict"],
  ];

  for (const [context, reason] of cases) {
    const result = resolveLegalFoundation({
      context,
      options: [option("EC41_SEM_P5", "without-p5", "EC41 sem art. 40, § 5º")],
    });
    assert.equal(result.status, "pending");
    assert.equal(result.option_value, null);
    assert.ok(result.reasons.includes(reason), reason);
  }
});

test("excludes placeholders and leaves equivalent best options pending", () => {
  const result = resolveLegalFoundation({
    context: contextFor("RESOLVE: Art. 3º, incisos I a III e parágrafo único, da EC nº 47/2005."),
    options: [
      option("PLACEHOLDER", "", "Selecione uma fundamentação", false),
      option("EC47_ART3", "first", "EC47 artigo 3º, parágrafo único"),
      option("EC47_ART3", "second", "EC47 artigo 3º, parágrafo único"),
    ],
  });

  assert.equal(result.status, "pending");
  assert.equal(result.option_value, null);
  assert.equal(result.ranking.length, 2);
  assert.equal(result.reasons.includes("equivalent-candidates"), true);
});
