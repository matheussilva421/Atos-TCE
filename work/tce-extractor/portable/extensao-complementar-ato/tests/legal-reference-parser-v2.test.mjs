import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeLegalYear,
  parseLegalReferencesV2,
} from "../lib/legal-reference-parser-v2.js";

test("parses ECE20 art7 with several paragraphs and art6 paragraph11", () => {
  const refs = parseLegalReferencesV2(
    "art. 7º, incisos I a III, §§ 2º e 4º, inciso I, § 5º, inciso I, e § 11 do art. 6º da ECE nº 20/2020",
  );

  assert.ok(refs.some((ref) => (
    ref.diploma_type === "ece"
      && ref.diploma_number === "20"
      && ref.diploma_year === "2020"
      && ref.article === "7"
  )));
  const article6 = refs.find((ref) => ref.article === "6");
  assert.ok(article6);
  assert.ok(article6.paragraphs.some((paragraph) => paragraph.number === "11"));
  assert.deepEqual(article6.paragraphs.find((paragraph) => paragraph.number === "11"), {
    number: "11",
    incisos: ["1"],
    alineas: [],
    items: [],
  });
});

test("keeps CF art40 paragraph1 incisoIII alinea a distinct from b", () => {
  const [a] = parseLegalReferencesV2("Art. 40, §1º, inciso III, alínea a, da CF");
  const [b] = parseLegalReferencesV2("Art. 40, §1º, inciso III, alínea b, da CF");

  assert.deepEqual(a.alineas, ["a"]);
  assert.deepEqual(b.alineas, ["b"]);
  assert.notDeepEqual(a.alineas, b.alineas);
});

test("normalizes EC20 slash 98 to 1998 and EC41 slash 03 to 2003", () => {
  assert.equal(normalizeLegalYear("98"), "1998");
  assert.equal(normalizeLegalYear("03"), "2003");
  assert.equal(parseLegalReferencesV2("art. 8º da EC 20/98")[0].diploma_year, "1998");
  assert.equal(parseLegalReferencesV2("art. 6º da EC 41/03")[0].diploma_year, "2003");
});

test("recognizes the supported diploma families and keeps article suffix", () => {
  const refs = parseLegalReferencesV2(
    "art. 6º-A da EC 41/2003; art. 40 da CF; art. 29 da CE; art. 1º da LC 51/85; art. 2º da LCE 10/2010; art. 3º da Lei 8.213/91",
  );

  assert.deepEqual(refs.map((ref) => ref.diploma_type), ["ec", "cf", "ce", "lc", "lce", "lei"]);
  assert.equal(refs[0].article_suffix, "a");
  assert.equal(refs[3].diploma_number, "51");
  assert.equal(refs[5].diploma_year, "1991");
});
