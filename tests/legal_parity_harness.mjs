/**
 * Runs the historical legal-foundation-v3 JavaScript oracle over a fixture
 * file and prints one JSON document with its legacy results.
 *
 * Used by tests/test_legal_rules.py as the parity oracle: the same fixtures are
 * fed to app/analysis/legal.py for parity of unchanged parsers, profiles and
 * catalog signatures. The final v4 selection policy has separate Python tests.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
// The proven JavaScript oracle ships inside the repository (tests/oracles/legal)
// so the M4 parity gate keeps working after the legacy tree is retired.
const legacy = join(here, "oracles", "legal");

const load = (name) => import(pathToFileURL(join(legacy, name)).href);

const { resolveLegalFoundation, parseLegalReferences } = await load("legal-foundation.js");
const { normalizeLegalText } = await load("normalizer.js");
const { parseLegalReferencesV2 } = await load("legal-reference-parser-v2.js");
const { buildRetirementLegalProfile } = await load("retirement-legal-profile.js");
const { buildCatalogOptionSignature } = await load("catalog-option-signature.js");

const fixturePath = process.argv[2];
if (!fixturePath) {
  console.error("uso: node tests/legal_parity_harness.mjs <fixtures.json>");
  process.exit(2);
}

const fixtures = JSON.parse(readFileSync(fixturePath, "utf8"));
const output = fixtures.map((fixture) => ({
  name: fixture.name,
  normalize: normalizeLegalText(fixture.context?.operative_text ?? ""),
  references: parseLegalReferences(fixture.context?.operative_text ?? ""),
  references_v2: parseLegalReferencesV2(fixture.context?.operative_text ?? ""),
  profile: buildRetirementLegalProfile({
    operativeText: fixture.context?.operative_text ?? "",
    cargo: fixture.context?.cargo ?? "",
  }),
  signatures: (fixture.options ?? []).map((option, index) =>
    buildCatalogOptionSignature(option, index)
  ),
  decision: resolveLegalFoundation({ context: fixture.context, options: fixture.options ?? [] }),
}));

console.log(JSON.stringify(output));
