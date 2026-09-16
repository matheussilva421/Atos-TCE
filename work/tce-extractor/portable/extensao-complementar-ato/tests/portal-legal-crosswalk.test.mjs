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
});
