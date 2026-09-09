import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { rankPortalOptions } from "../lib/matcher.js";

const options = (values) => values.map((value) => ({ value, label: value }));
const fixtureRoot = join(dirname(fileURLToPath(import.meta.url)), "../../../tests/fixtures");
const legalFoundationFixture = JSON.parse(
  readFileSync(join(fixtureRoot, "legal-foundations.json"), "utf8"),
);

test("loads the sanitized v1 catalog with canonical and auxiliary foundation options", () => {
  assert.equal(legalFoundationFixture.schema_version, 1);
  assert.deepEqual(legalFoundationFixture.dataset_fields, [
    "modalidade",
    "fundamento_legal",
    "data_publicacao_doe",
    "cargo",
    "matricula",
    "data_nascimento",
    "genero",
  ]);
  assert.deepEqual(
    legalFoundationFixture.options.slice(0, 3).map((option) => option.rule_id),
    ["EC41_SEM_P5", "EC41_COM_P5", "EC47_ART3"],
  );
  assert.deepEqual(legalFoundationFixture.options.slice(0, 3), [
    {
      rule_id: "EC41_SEM_P5",
      value: "synthetic-ec41-without-p5",
      label: "Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 2º da Emenda Constitucional nº 47/2005",
      selectable: true,
    },
    {
      rule_id: "EC41_COM_P5",
      value: "synthetic-ec41-with-p5",
      label: "Civil - Artigo 6º, incisos I a IV e artigo 7º, ambos da Emenda Constitucional nº 41/2003 c/c o artigo 40, § 5º, Constituição Federal e artigo 2º da Emenda Constitucional nº 47/2005",
      selectable: true,
    },
    {
      rule_id: "EC47_ART3",
      value: "synthetic-ec47-art3",
      label: "Civil - Artigo 3º, incisos I a III e parágrafo único, da Emenda Constitucional nº 47/2005",
      selectable: true,
    },
  ]);
  assert.deepEqual(
    legalFoundationFixture.options.slice(3).map((option) => option.rule_id),
    ["EC41_ART6A", "CF40_P1_II", "MILITAR", "PLACEHOLDER"],
  );
  const selectableValues = legalFoundationFixture.options
    .filter((option) => option.selectable)
    .map((option) => option.value);
  assert.ok(selectableValues.every((value) => (
    value === "" || /^synthetic-[a-z0-9-]+$/u.test(value)
  )));
  assert.ok(selectableValues.every((value) => value !== ""));
  assert.equal(new Set(selectableValues).size, selectableValues.length);
  assert.deepEqual(
    legalFoundationFixture.options.find((option) => option.rule_id === "PLACEHOLDER"),
    {
      rule_id: "PLACEHOLDER",
      value: "",
      label: "Selecione uma fundamentação",
      selectable: false,
    },
  );
});

test("keeps each automatic portal surface in a distinct sanitized simulated fixture", () => {
  const fixtures = [
    ["process-list-page-1.html", "process-list"],
    ["process-list-page-2.html", "process-list"],
    ["people.html", "people"],
    ["form.html", "form"],
    ["buttons-frame.html", "buttons-frame"],
  ];

  const listPages = [
    readFileSync(join(fixtureRoot, "automatic-portal", "process-list-page-1.html"), "utf8"),
    readFileSync(join(fixtureRoot, "automatic-portal", "process-list-page-2.html"), "utf8"),
  ];
  assert.notEqual(listPages[0], listPages[1]);
  assert.match(listPages[0], /SYN-0001\/2099/u);
  assert.match(listPages[1], /SYN-0003\/2099/u);

  for (const [filename, kind] of fixtures) {
    const content = readFileSync(join(fixtureRoot, "automatic-portal", filename), "utf8");
    assert.match(content, new RegExp(`data-fixture-kind="${kind}"`, "u"));
    assert.match(content, /data-fixture-status="simulated"/u);
    if (filename === "buttons-frame.html") {
      assert.equal((content.match(/id="botao"/gu) ?? []).length, 2);
      assert.equal((content.match(/data-action="signal-only"/gu) ?? []).length, 2);
      assert.match(content, /data-submission-mode="manual-signal-only"/u);
    }
  }

  const result = JSON.parse(
    readFileSync(join(fixtureRoot, "automatic-portal", "simulator-result.json"), "utf8"),
  );
  assert.equal(result.fixture_status, "simulated");
  assert.equal(result.simulation.is_simulated, true);
  assert.match(result.simulation.notice, /não comprova sucesso no portal real/u);
  assert.equal(result.request.sent, false);
  assert.equal(result.request.mode, "manual-signal-only");
  assert.equal(result.result.status, "simulated-success");
  assert.equal(result.result.persistent_portal_id, null);
});

test("matches a short voluntary retirement source to the voluntary portal family, never compulsory", () => {
  const result = rankPortalOptions({
    field: "modalidade",
    documentaryValue: "aposentadoria voluntária",
    options: [
      { value: "9", label: "Aposentadoria por invalidez" },
      { value: "10", label: "Aposentadoria compulsória" },
      { value: "11", label: "Aposentadoria proporcional ao tempo de contribuição" },
      { value: "12", label: "Aposentadoria voluntária por tempo de contribuição com proventos integrais" },
      { value: "13", label: "Aposentadoria voluntária por tempo de serviço com proventos integrais" },
    ],
  });
  assert.equal(result.optionValue, "12");
  assert.equal(result.kind, "tie");
});

test("selects exact normalized modalidade and preserves the portal option text", () => {
  const result = rankPortalOptions({
    field: "modalidade",
    documentaryValue: "Aposentação voluntária por tempo de contribuição com proventos integrais",
    hints: {},
    options: options([
      "Aposentadoria voluntária por tempo de contribuição com proventos integrais",
      "Aposentadoria voluntária por tempo de contribuição proporcional",
    ]),
  });

  assert.deepEqual(result, {
    kind: "exact",
    optionIndex: 0,
    optionValue: "Aposentadoria voluntária por tempo de contribuição com proventos integrais",
    optionLabel: "Aposentadoria voluntária por tempo de contribuição com proventos integrais",
    score: 100,
    reasons: ["normalized-equivalence"],
  });
});

test("ranks professor article 40 paragraph 5 above a generic legal option", () => {
  const result = rankPortalOptions({
    field: "fundamento_legal",
    documentaryValue: "Regra do professor prevista no art. 40, § 5º, sem rótulo idêntico",
    hints: {},
    options: options([
      "Artigo 40, parágrafo 5, regra para docente",
      "Artigo 40, parágrafo 1, regra geral",
    ]),
  });

  assert.equal(result.kind, "probable");
  assert.equal(result.optionIndex, 0);
  assert.equal(result.score, 95);
  assert.deepEqual(result.reasons, [
    "professor:50",
    "article-paragraph:40",
    "lexical-dice:5",
  ]);
});

test("preserves distinct option value, label, and portal index for exact, ordered probable, and tie", async (t) => {
  const cases = [
    {
      name: "exact",
      input: {
        field: "modalidade",
        documentaryValue: "Aposentação por invalidez",
        hints: {},
        options: [
          { value: "exact-wrong", label: "Regra diversa" },
          { value: "exact-code", label: "Aposentadoria por invalidez" },
        ],
      },
      expected: {
        kind: "exact",
        optionIndex: 1,
        optionValue: "exact-code",
        optionLabel: "Aposentadoria por invalidez",
      },
    },
    {
      name: "ordered probable",
      input: {
        field: "fundamento_legal",
        documentaryValue: "origem zeta",
        hints: { professor: true },
        options: [
          { value: "probable-wrong", label: "Regra geral" },
          { value: "probable-code", label: "Regra docente" },
        ],
      },
      expected: {
        kind: "probable",
        optionIndex: 1,
        optionValue: "probable-code",
        optionLabel: "Regra docente",
      },
    },
    {
      name: "tie",
      input: {
        field: "fundamento_legal",
        documentaryValue: "art. 40",
        hints: {},
        options: [
          { value: "tie-first", label: "Artigo 40 - Alfa" },
          { value: "tie-second", label: "Artigo 40 - Beta" },
        ],
      },
      expected: {
        kind: "tie",
        optionIndex: 0,
        optionValue: "tie-first",
        optionLabel: "Artigo 40 - Alfa",
      },
    },
  ];

  for (const { name, input, expected } of cases) {
    await t.test(name, () => {
      const result = rankPortalOptions(input);
      assert.deepEqual(
        {
          kind: result.kind,
          optionIndex: result.optionIndex,
          optionValue: result.optionValue,
          optionLabel: result.optionLabel,
        },
        expected,
      );
    });
  }
});

test("applies each approved legal signal weight as an isolated numeric score", async (t) => {
  const cases = [
    {
      name: "benefit 100",
      hints: { benefit: "aposentadoria" },
      label: "Aposentadoria",
      score: 100,
      reasons: ["benefit:100"],
    },
    {
      name: "modality 100",
      hints: { modality: "invalidez" },
      label: "Invalidez",
      score: 100,
      reasons: ["modality:100"],
    },
    {
      name: "proportion 60",
      hints: { proportion: "integral" },
      label: "Integral",
      score: 60,
      reasons: ["proportion:integral:60"],
    },
    {
      name: "professor 50",
      hints: { professor: true },
      label: "Professor",
      score: 50,
      reasons: ["professor:50"],
    },
    {
      name: "legal reference 40",
      hints: { article: "40", paragraph: "5" },
      label: "Artigo 40, parágrafo 5",
      score: 40,
      reasons: ["article-paragraph:40"],
    },
    {
      name: "diploma 25",
      hints: { diplomas: ["ECE 20/2020"] },
      label: "EC 20/1998",
      score: 25,
      reasons: ["diploma:25"],
    },
  ];

  for (const entry of cases) {
    await t.test(entry.name, () => {
      const result = rankPortalOptions({
        field: "fundamento_legal",
        documentaryValue: "origem zeta",
        hints: entry.hints,
        options: [{ value: `${entry.name}-code`, label: entry.label }],
      });

      assert.equal(result.kind, "probable");
      assert.equal(result.score, entry.score);
      assert.deepEqual(result.reasons, entry.reasons);
    });
  }
});

test("keeps lexical Dice scores within the exact 0 to 10 range", async (t) => {
  const cases = [
    {
      name: "zero",
      documentaryValue: "alfa",
      optionLabel: "beta",
      score: 0,
      reasons: ["no-positive-signal"],
    },
    {
      name: "middle",
      documentaryValue: "alfa beta",
      optionLabel: "alfa gama",
      score: 5,
      reasons: ["lexical-dice:5"],
    },
    {
      name: "maximum",
      documentaryValue: "alfa beta",
      optionLabel: "beta alfa",
      score: 10,
      reasons: ["lexical-dice:10"],
    },
  ];

  for (const entry of cases) {
    await t.test(entry.name, () => {
      const result = rankPortalOptions({
        field: "fundamento_legal",
        documentaryValue: entry.documentaryValue,
        hints: {},
        options: [{ value: `${entry.name}-code`, label: entry.optionLabel }],
      });

      assert.equal(result.score, entry.score);
      assert.deepEqual(result.reasons, entry.reasons);
      assert.ok(result.score >= 0 && result.score <= 10);
    });
  }
});

test("distinguishes integral, proportional, and special options", () => {
  for (const [proportion, expected] of [
    ["integral", "Integral"],
    ["proporcional", "Proporcional"],
    ["especial", "Especial"],
  ]) {
    const documentaryProportion = {
      integral: "integrais",
      proporcional: "proporcionais",
      especial: "especiais",
    }[proportion];
    const result = rankPortalOptions({
      field: "modalidade",
      documentaryValue: `Aposentadoria por tempo de contribuição com proventos ${documentaryProportion}`,
      hints: {},
      options: options([
        "Aposentadoria por tempo de contribuição - integral",
        "Aposentadoria por tempo de contribuição - proporcional",
        "Aposentadoria por tempo de contribuição - especial",
      ]),
    });

    assert.equal(result.optionLabel, `Aposentadoria por tempo de contribuição - ${expected.toLowerCase()}`);
    assert.ok(result.score >= 160);
    assert.ok(result.reasons.includes("benefit:100"));
    assert.ok(result.reasons.includes(`proportion:${proportion}:60`));
  }
});

test("matches an ECE 20/2020 professor rule to the closest legacy catalog entry", () => {
  const result = rankPortalOptions({
    field: "fundamento_legal",
    documentaryValue: "REGRA DE TRANSIÇÃO PROFESSOR - ART. 7º, § 1º - ECE 20/2020 - INTEGRAL",
    hints: { professor: true, proportion: "integral" },
    options: options([
      "Regra geral do artigo 6º e artigo 7º da EC 41/2003 combinada com o artigo 2º da EC 47/2005",
      "Regra geral do artigo 6º e artigo 7º da EC 41/2003 combinada com o artigo 2º da EC 47/2005, com artigo 40, § 5º, específica para professor e integral",
    ]),
  });

  assert.equal(result.kind, "probable");
  assert.equal(result.optionIndex, 1);
  assert.ok(result.score > 0);
  assert.ok(result.reasons.includes("professor:50"));
});

test("scores the ECE number against the corresponding legacy EC entry", () => {
  const result = rankPortalOptions({
    field: "fundamento_legal",
    documentaryValue: "ECE 20/2020",
    hints: {},
    options: [
      { value: "legacy-20", label: "Emenda Constitucional nº 20/1998" },
      { value: "legacy-19", label: "Emenda Constitucional nº 19/1998" },
    ],
  });

  assert.equal(result.kind, "probable");
  assert.equal(result.optionIndex, 0);
  assert.equal(result.optionValue, "legacy-20");
  assert.ok(result.reasons.includes("diploma:25"));
});

test("marks equal best scores as tie and chooses the lower portal index", () => {
  const result = rankPortalOptions({
    field: "fundamento_legal",
    documentaryValue: "art. 40",
    hints: {},
    options: options(["Artigo 40 - opção A", "Artigo 40 - opção B"]),
  });

  assert.equal(result.kind, "tie");
  assert.equal(result.optionIndex, 0);
  assert.ok(result.score > 0);
  assert.ok(result.reasons.includes("tie:2"));
});

test("returns missing-source without selecting an option for an empty documentary value", () => {
  assert.deepEqual(
    rankPortalOptions({
      field: "modalidade",
      documentaryValue: "  ",
      hints: {},
      options: options(["Integral"]),
    }),
    {
      kind: "missing-source",
      optionIndex: null,
      optionValue: null,
      optionLabel: null,
      score: 0,
      reasons: ["missing-source"],
    },
  );
});

test("does not select an option when the source has no positive legal signal", () => {
  const result = rankPortalOptions({
    field: "fundamento_legal",
    documentaryValue: "texto sem referências",
    hints: {},
    options: legalFoundationFixture.options,
  });

  assert.equal(result.optionValue, null);
});

test("returns pending with a null option when foundation scoring has no positive signal", () => {
  const result = rankPortalOptions({
    field: "fundamento_legal",
    documentaryValue: "texto sem referências",
    hints: {},
    options: legalFoundationFixture.options,
  });

  assert.equal(result.kind, "pending");
  assert.equal(result.optionIndex, null);
  assert.equal(result.optionValue, null);
  assert.equal(result.optionLabel, null);
});

test("carries a selected legal decision without changing the legacy matcher fields", () => {
  const result = rankPortalOptions({
    field: "fundamento_legal",
    documentaryValue: "texto legado",
    context: {
      resolution_status: "complete",
      operative_text: "RESOLVE: Art. 3º, incisos I a III e parágrafo único, da EC nº 47/2005.",
      pages: [],
    },
    options: [
      legalFoundationFixture.options[0],
      legalFoundationFixture.options[2],
    ],
  });

  assert.equal(result.kind, "probable");
  assert.equal(result.optionValue, "synthetic-ec47-art3");
  assert.equal(result.legalDecision.status, "selected");
  assert.equal(result.legalDecision.rule_id, "EC47_ART3");
});
