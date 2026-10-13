import test from "node:test";
import assert from "node:assert/strict";

import {
  describeManualFillCapability,
  describeNextProcessCapability,
  normalizeCapabilityState,
} from "../sidepanel/state.js";

test("manual fill is disabled and labelled while UNQUALIFIED", () => {
  const described = describeManualFillCapability({
    manual_form_fill: { state: "UNQUALIFIED", real_dev_streak: 0, portable_streak: 0 },
  });

  assert.equal(described.state, "UNQUALIFIED");
  assert.equal(described.enabled, false);
  assert.equal(described.label, "Indisponível — não qualificado");
});

test("a missing capability payload is treated as UNQUALIFIED", () => {
  for (const capabilities of [null, undefined, {}, { manual_form_fill: {} }]) {
    const described = describeManualFillCapability(capabilities);
    assert.equal(described.state, "UNQUALIFIED", JSON.stringify(capabilities));
    assert.equal(described.enabled, false, JSON.stringify(capabilities));
  }
});

test("manual fill becomes available and visibly experimental once EXPERIMENTAL", () => {
  const described = describeManualFillCapability({ manual_form_fill: { state: "EXPERIMENTAL" } });

  assert.equal(described.state, "EXPERIMENTAL");
  assert.equal(described.enabled, true);
  assert.equal(described.label, "Experimental");
});

test("manual fill is labelled Qualified once QUALIFIED", () => {
  const described = describeManualFillCapability({ manual_form_fill: { state: "QUALIFIED" } });

  assert.equal(described.enabled, true);
  assert.equal(described.label, "Qualificado");
});

test("manual fill uses the normal production label once PRODUCTION", () => {
  const described = describeManualFillCapability({ manual_form_fill: { state: "PRODUCTION" } });

  assert.equal(described.enabled, true);
  assert.equal(described.label, "Produção");
});

test("an unknown capability state is treated as UNQUALIFIED", () => {
  assert.equal(normalizeCapabilityState("banana"), "UNQUALIFIED");
  assert.equal(normalizeCapabilityState("  qualified "), "QUALIFIED");
  const described = describeManualFillCapability({ manual_form_fill: { state: "banana" } });
  assert.equal(described.enabled, false);
});

test("next-process stays unavailable for the operator throughout Phase 1", () => {
  for (const state of ["UNQUALIFIED", "EXPERIMENTAL", "QUALIFIED", "PRODUCTION"]) {
    const described = describeNextProcessCapability({ next_process: { state } });
    assert.equal(described.enabled, false, state);
    assert.equal(described.label, "Indisponível", state);
  }
});

