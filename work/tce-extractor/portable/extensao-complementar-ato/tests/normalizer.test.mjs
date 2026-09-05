import test from "node:test";
import assert from "node:assert/strict";

import { extractLegalSignals, normalizeLegalText } from "../lib/normalizer.js";

test("normalizes accents, case, whitespace, and punctuation for comparison", () => {
  assert.equal(
    normalizeLegalText(" Aposentadoria   Voluntária, por Tempo de Contribuição. "),
    "aposentadoria voluntaria por tempo de contribuicao",
  );
});

test("treats art. and artigo as equivalent legal signals", () => {
  assert.equal(
    normalizeLegalText("art. 40"),
    normalizeLegalText("Artigo 40"),
  );
});

test("treats section and number symbols as their written equivalents", () => {
  assert.equal(
    normalizeLegalText("art. 40, § 5º, nº 20"),
    normalizeLegalText("artigo 40, parágrafo 5, número 20"),
  );
});

test("canonicalizes roman numerals while preserving their numeric meaning", () => {
  assert.equal(
    normalizeLegalText("inciso IV"),
    normalizeLegalText("inciso 4"),
  );
});

test("deduplicates a repeated inciso without changing the displayed source value", () => {
  const sourceValue = "Art. 40, § 5º, inciso IV, inciso IV";

  assert.equal(
    normalizeLegalText(sourceValue),
    "artigo 40 paragrafo 5 inciso 4",
  );
  assert.equal(sourceValue, "Art. 40, § 5º, inciso IV, inciso IV");
});

test("keeps the same inciso when it belongs to different articles", () => {
  assert.equal(
    normalizeLegalText("art. 6º, inciso I; art. 7º, inciso I"),
    "artigo 6 inciso 1 artigo 7 inciso 1",
  );
});

test("does not infer article or paragraph from a leading number without markers", () => {
  const signals = extractLegalSignals("40 anos de contribuição para aposentadoria");

  assert.equal(signals.article, null);
  assert.equal(signals.paragraph, null);
});

test("extracts modality, benefit, parity, professor, article, paragraph, inciso, and diploma signals", () => {
  assert.deepEqual(
    extractLegalSignals(
      "Aposentadoria voluntária por tempo de contribuição com proventos integrais para professor, art. 40, § 5º, inciso IV, ECE nº 20/2020",
    ),
    {
      benefit: "aposentadoria",
      modality: "tempo de contribuicao",
      proportion: "integral",
      professor: true,
      article: "40",
      paragraph: "5",
      incisos: ["4"],
      diplomas: ["ece 20/2020"],
    },
  );
});
