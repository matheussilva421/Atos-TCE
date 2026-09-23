# Best-Effort Form Filling + Fundamento Legal v4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the M5 all-or-nothing filler with field-level best-effort filling while preserving hard identity safety and making `fundamento_legal` choose one deterministic best available portal option whenever documentary text and at least one selectable catalog option exist.

**Architecture:** Keep the Mesa/backend authoritative for target identity, field proposals, legal ranking and request state. Narrow hard blocks to target/form safety; represent content problems as warnings/field results. The extension remains a thin executor, but writes independent fields one by one and rereads each changed control instead of pre-refusing the whole plan.

**Tech Stack:** Python 3 + `unittest` + SQLite backend, vanilla JavaScript MV3 extension + Node test runner, vanilla Mesa web UI.

**Spec:** `docs/superpowers/specs/2026-09-23-best-effort-form-filling-design.md`

## Global Constraints

- **Before Task 1, promote `codex/mesa-local-refactor` to `main`.** Current planning-time relation: 154 commits ahead, 0 behind.
- Promotion must be fast-forward only; never force-push, rewrite `main`, or discard a divergent remote commit.
- After promotion, implementation work starts from the promoted `main`, not from the old refactor branch.
- Identity/process targeting remains fail-closed.
- Content-field problems are best-effort warnings and must not prevent independent valid fields from being attempted.
- Existing non-empty divergent portal values are preserved by default, never silently overwritten.
- No `SUBMIT`, `SEND`, `AUTO_SUBMIT`, `COMPLEMENT_ACT` or `FINALIZE` capability may be added.
- `fundamento_legal`: documentary proposal + at least one real selectable option => exactly one deterministic catalog option.
- `confidence`, `margin`, ties and hard conflicts remain diagnostics; they do not authorize an empty legal selection.
- A stale generation causes zero writes in that attempt and permits one automatic reread/replan; a second stale result ends the fill request as a technical error without corrupting the process's documentary status.
- A partial fill request may finish normally while the process remains `PRONTO`.
- Historical v3 legal oracles stay historical; do not silently mutate them into v4.

## Review Focus

1. **Partial DOM:** one mandatory control absent while two others are writable — writable fields must still change and the missing field must be reported.
2. **Existing divergent value:** one field already contains a different non-empty value — preserve it, warn, and continue writing independent fields.
3. **Stale generation race:** form changes between preflight and write — zero writes, one reread/replan, then fail technically if it races again.
4. **Legal catalog edge:** placeholder plus one real option, or every candidate carrying a hard conflict — always choose the real option when documentary text exists.
5. **Partial-success status:** fill request returns changed fields plus unresolved mandatory warnings — request may finish, but process must remain `PRONTO`, retryable, and visible in the Mesa.

---

# Pre-execution Gate — Promote the refactor branch to main

This gate runs **before Task 1** and is not optional.

- [ ] **Gate 1: Fetch and verify the exact branch relation**

```bash
git fetch origin --prune
git rev-parse origin/main
git rev-parse origin/codex/mesa-local-refactor
git merge-base --is-ancestor origin/main origin/codex/mesa-local-refactor
git rev-list --left-right --count origin/main...origin/codex/mesa-local-refactor
```

Expected at planning time:

```text
0 154
```

The first number must be `0`. If it is non-zero, stop: `main` has commits not contained in the refactor branch and must be reconciled explicitly before promotion.

- [ ] **Gate 2: Run the current branch baseline before moving main**

```bash
git switch codex/mesa-local-refactor
git pull --ff-only origin codex/mesa-local-refactor
python -m unittest discover -s tests -p "test_*.py" -q
npm test --prefix extension
node --test app/web/tests/*.test.mjs
powershell -ExecutionPolicy Bypass -File .\verify-project.ps1
git diff --check
```

Expected: all existing suites green. Any pre-existing failure must be recorded in `docs/notes/2026-09-23-pre-promotion-baseline.md` before proceeding; do not reinterpret a new implementation failure as baseline noise.

- [ ] **Gate 3: Fast-forward main to the refactor branch**

```bash
git switch main
git pull --ff-only origin main
git merge --ff-only origin/codex/mesa-local-refactor
git push origin main
```

- [ ] **Gate 4: Prove promotion completed without divergence**

```bash
git fetch origin
test "$(git rev-parse origin/main)" = "$(git rev-parse origin/codex/mesa-local-refactor)"
git log -1 --oneline origin/main
```

On PowerShell, use:

```powershell
if ((git rev-parse origin/main) -ne (git rev-parse origin/codex/mesa-local-refactor)) {
    throw "main was not promoted to the refactor HEAD"
}
```

- [ ] **Gate 5: Create the implementation branch/worktree from promoted main**

Use the execution method's worktree skill, then create:

```bash
git switch -c codex/best-effort-form-filling origin/main
```

Do not implement on `main` directly.

---

### Task 1: Establish the v4 selectable-catalog contract

**Files:**
- Modify: `app/analysis/legal.py`
- Modify: `tests/test_legal_rules.py`
- Modify: `tests/fixtures/legal-cases.json`

**Interfaces:**
- Produces: `selectable_legal_options(options: Any) -> list[dict[str, Any]]`
- Each returned item has `value`, `label`, `index`, preserving raw DOM value semantics.

- [ ] **Step 1: Add RED tests for canonical filtering**

Add tests that prove:

```python
def test_selectable_catalog_drops_placeholder_and_empty_values(self):
    options = [
        {"value": "", "label": "Selecione o Fundamento Legal"},
        {"value": "41", "label": "EC 41/2003"},
    ]
    self.assertEqual(
        legal.selectable_legal_options(options),
        [{"value": "41", "label": "EC 41/2003", "index": 1}],
    )

def test_selectable_catalog_never_replaces_empty_value_with_label(self):
    options = [{"value": "", "label": "EC 41/2003"}]
    self.assertEqual(legal.selectable_legal_options(options), [])
```

- [ ] **Step 2: Run focused tests and confirm failure**

```bash
python -m unittest tests.test_legal_rules -v
```

Expected: failures because `selectable_legal_options` does not exist.

- [ ] **Step 3: Implement one canonical filter**

Implement a single helper in `app/analysis/legal.py`:

```python
def selectable_legal_options(options: Any) -> list[dict[str, Any]]:
    option_list = options if isinstance(options, list) else []
    selected: list[dict[str, Any]] = []
    for index, raw in enumerate(option_list):
        if not isinstance(raw, Mapping):
            continue
        value = str(raw.get("value") or "").strip()
        label = str(raw.get("label") or "").strip()
        if not value or not label:
            continue
        if PLACEHOLDER_PATTERN.search(normalize_legal_text(label)):
            continue
        selected.append({**dict(raw), "value": value, "label": label, "index": index})
    return selected
```

Make the placeholder predicate cover the actual portal wording `Selecione o Fundamento Legal` and equivalent "Selecionar/Selecione..." prefixes.

- [ ] **Step 4: Route v4 decision code through the helper**

Replace ad hoc option filtering used by final legal selection. Do not use `_option_parts()` to determine whether a raw DOM option is selectable, because it currently falls back from empty `value` to `label`.

- [ ] **Step 5: Run focused tests**

```bash
python -m unittest tests.test_legal_rules -v
```

Expected: new catalog tests pass; existing v3 decision-parity failures are allowed only after Task 2 intentionally changes the final policy.

- [ ] **Step 6: Commit**

```bash
git add app/analysis/legal.py tests/test_legal_rules.py tests/fixtures/legal-cases.json
git commit -m "refactor: centralize selectable legal catalog filtering"
```

---

### Task 2: Implement legal-foundation-v4 best-available selection

**Files:**
- Modify: `app/analysis/legal.py`
- Modify: `tests/test_legal_rules.py`
- Modify: `tests/fixtures/legal-cases.json`
- Modify: `tests/legal_parity_harness.mjs`
- Modify: `tests/oracles/legal/README.md`

**Interfaces:**
- Consumes: `selectable_legal_options()`
- Produces: `resolve_legal_foundation(context, options)` with `rules_version == "legal-foundation-v4"` when a v4 selection is made.
- Produces: deterministic `option_value` whenever documentary text exists and selectable options are non-empty.

- [ ] **Step 1: Add v4 RED fixtures**

Add fixtures covering:
- exact match;
- low confidence;
- low margin;
- true tie;
- unknown `CATALOG_OPTION_*`;
- all candidates with hard conflicts;
- incomplete reference;
- contradictory reference;
- no parseable reference but documentary text present;
- placeholder + one real option;
- only placeholder.

For every case with at least one selectable option, assert:

```python
decision = legal.resolve_legal_foundation(fixture["context"], fixture["options"])
self.assertEqual(decision["status"], "selected")
self.assertTrue(decision["automatic"])
self.assertTrue(decision["option_value"])
self.assertIn(
    decision["option_value"],
    {option["value"] for option in legal.selectable_legal_options(fixture["options"])},
)
```

For only-placeholder:

```python
self.assertIsNone(decision.get("option_value"))
self.assertIn("LEGAL_OPTIONS_EMPTY", decision.get("warnings", []) + decision.get("reasons", []))
```

- [ ] **Step 2: Run the legal suite and capture RED behavior**

```bash
python -m unittest tests.test_legal_rules -v
```

Expected: current threshold, early-return and hard-reject behavior causes v4 contract failures.

- [ ] **Step 3: Preserve raw compatibility score across hard conflicts**

In `_rank_one()`, stop replacing the useful weighted score with zero solely because `hard_reasons` is non-empty. Keep:
- raw/compatibility score;
- `hard_conflict`;
- `hard_reasons`;
- existing structural component details.

Sort so candidates without hard conflict remain preferred when available; if none exist, choose the highest-ranked candidate from all real options.

- [ ] **Step 4: Remove empty-selection early exits when usable documentary text exists**

In `resolve_legal_foundation()`, convert:
- `no-legal-references`;
- `reference-incomplete`;
- `contradictory-reference`;

from terminal empty decisions into warnings/source issues followed by best-available ranking. `context-incomplete` may continue only when usable operative/documentary text exists; truly absent text remains upstream-invalid and may return no selection.

- [ ] **Step 5: Make ties deterministic**

Use final sort key ending in original `option_index`. If the top candidates are equivalent before index tie-break:
- still return `AUTO_SELECTED`;
- set `tie_break_used = True`;
- add warnings `equivalent-candidates` and `tie-broken-by-option-index`.

- [ ] **Step 6: Convert thresholds to diagnostics**

Change the final policy so `confidence`, `margin`, and `hard_conflict` affect warnings/telemetry, not whether `option_value` is published.

Update `is_automatic_legal_decision()` to validate integrity only:

```python
return (
    decision.get("status") == "selected"
    and decision.get("decision_state") == "AUTO_SELECTED"
    and decision.get("rules_version") == RULES_VERSION
    and bool(str(decision.get("option_value") or "").strip())
    and decision.get("method") != "none"
)
```

Set `RULES_VERSION = "legal-foundation-v4"`.

- [ ] **Step 7: Prevent the adapter from erasing a valid v4 selection**

Update `_adapt_crosswalk_decision()` so a selected valid catalog option remains selected even when confidence/margin is low or `hard_conflict` is true. Preserve diagnostics in the returned decision.

- [ ] **Step 8: Keep v3 oracle history explicit**

Change full final-decision parity so v3 oracle output no longer gates the v4 final decision. Continue parity checks for unchanged parser/profile/signature primitives. Document in `tests/oracles/legal/README.md` that v3 remains historical and Python v4 contract tests own final selection policy.

- [ ] **Step 9: Run tests**

```bash
python -m unittest tests.test_legal_rules -v
```

Expected: all v4 contract tests green and unchanged parser/profile parity still green.

- [ ] **Step 10: Commit**

```bash
git add app/analysis/legal.py tests/test_legal_rules.py tests/fixtures/legal-cases.json tests/legal_parity_harness.mjs tests/oracles/legal/README.md
git commit -m "feat: add legal-foundation-v4 best-available selection"
```

---

### Task 3: Make backend preflight best-effort and resolve legal before literal select matching

**Files:**
- Modify: `app/area_restrita/preflight.py`
- Modify: `tests/test_fill_service.py`

**Interfaces:**
- Consumes: `resolve_legal_foundation()`, `selectable_legal_options()`
- Keeps: `FillBlocked` for process/form safety only.
- Produces: `FillPlan.fields`, `FillPlan.preserved`, `FillPlan.warnings`, `FillPlan.legal_decision`.

- [ ] **Step 1: Replace fail-closed content tests with RED best-effort tests**

Add tests equivalent to:

```python
def test_missing_control_warns_and_keeps_other_fields(self):
    plan = build_fill_plan(process_with_all_fields, snapshot_without_matricula)
    self.assertIn("cargo", plan.fields)
    self.assertNotIn("matricula", plan.fields)
    self.assertTrue(any("matricula" in warning for warning in plan.warnings))

def test_existing_divergence_is_preserved_and_does_not_block(self):
    plan = build_fill_plan(process_with_all_fields, snapshot_with_existing_other_cargo)
    self.assertEqual(plan.preserved["cargo"], "Valor já existente")
    self.assertIn("matricula", plan.fields)
    self.assertTrue(any("diverg" in warning.lower() for warning in plan.warnings))

def test_legal_nonliteral_value_is_resolved_before_generic_select_matching(self):
    plan = build_fill_plan(process_with_nonliteral_legal_text, snapshot_with_real_legal_catalog)
    self.assertIn(plan.fields["fundamento_legal"], {"41", "47"})
    self.assertEqual(plan.fields["fundamento_legal"], plan.legal_decision["option_value"])
```

Keep identity and generation tests expecting `FillBlocked`.

- [ ] **Step 2: Run RED tests**

```bash
python -m unittest tests.test_fill_service -v
```

Expected: current `CONTROL_NOT_FOUND`, `CONTROL_READONLY`, `EXISTING_VALUE_DIVERGENCE`, `FIELD_PROPOSAL_MISSING`, and literal legal-option behavior fail the new assertions.

- [ ] **Step 3: Narrow `FillBlocked` usage**

Keep blocks for:
- missing process;
- missing/incompatible identity;
- invalid/missing generation.

Turn content problems into `plan.warnings` and skip/preserve only that field.

- [ ] **Step 4: Resolve legal field before generic option mapping**

For `fundamento_legal`:
1. get current control/options;
2. call legal resolver;
3. validate chosen `option_value` belongs to current selectable catalog;
4. if catalog is empty, warn and leave field unresolved;
5. if resolver returns a value not in current catalog, warn/defensively skip rather than forwarding stale value;
6. never run the documentary legal text through the generic literal `_resolve_option_value()` first.

- [ ] **Step 5: Treat current placeholder as empty**

If the current select value corresponds to a placeholder option, do not classify it as an existing divergent real value.

- [ ] **Step 6: Keep non-legal select behavior conservative but non-blocking**

For ordinary selects:
- exact value/normalized label => plan field;
- no matching option => warning and skip field;
- never choose arbitrary option.

- [ ] **Step 7: Run tests**

```bash
python -m unittest tests.test_fill_service -v
```

Expected: content problems produce plan + warnings; identity/generation still block.

- [ ] **Step 8: Commit**

```bash
git add app/area_restrita/preflight.py tests/test_fill_service.py
git commit -m "refactor: make fill preflight best-effort"
```

---

### Task 4: Let the form reader identify a form even when an individual mapped field is missing

**Files:**
- Modify: `extension/content/detect-form.js`
- Modify: `extension/tests/detect-form.test.mjs`
- Modify if needed for fixtures: `extension/tests/fake-dom.mjs`

**Interfaces:**
- Produces: `TCEFormReader.readForm(documentRef)` for an identity-valid form even when a non-identity content control is absent.
- Preserves: form identity must still require process key + selected interested person.

- [ ] **Step 1: Rewrite the current "late form requires every mapped control" test**

Replace it with two explicit cases:

```javascript
test("an identity-valid form is readable when one content control is absent", () => {
  const documentRef = buildActFormDocument({
    selected: "Pessoa Exemplo",
    missingFields: ["matricula"],
  });
  const form = reader.readForm(documentRef);
  assert.notEqual(form, null);
  assert.equal(form.identity.processKey, "102390/2026");
  assert.equal(form.fields.matricula, undefined);
});

test("a form without identity anchors is not readable", () => {
  const documentRef = buildActFormDocument({ selected: null });
  assert.equal(reader.readForm(documentRef), null);
});
```

Adapt `fake-dom.mjs` with an explicit `missingFields` fixture option if it does not already support field removal.

- [ ] **Step 2: Run RED test**

```bash
node --test extension/tests/detect-form.test.mjs
```

Expected: current all-sentinel requirement returns `null`.

- [ ] **Step 3: Split identity/form sentinels from content controls**

Make form availability depend on the minimum identity/form anchors already proven by the portal model, not every field in `FIELD_MAP`. Continue collecting each available field independently.

- [ ] **Step 4: Run reader tests**

```bash
node --test extension/tests/detect-form.test.mjs
```

Expected: partial-content form is readable; identity-less form stays rejected.

- [ ] **Step 5: Commit**

```bash
git add extension/content/detect-form.js extension/tests/detect-form.test.mjs extension/tests/fake-dom.mjs
git commit -m "fix: read forms with partial content controls"
```

---

### Task 5: Change the extension filler from global pre-refusal to per-field execution

**Files:**
- Modify: `extension/content/fill-form.js`
- Modify: `extension/tests/fill-form.test.mjs`

**Interfaces:**
- Consumes: explicit identity, generation, and backend field map.
- Produces: `field_results` containing a result for every proposed field.
- Global `ok: false` is reserved for request/form safety failures, not one field-level failure.

- [ ] **Step 1: Add RED tests proving independent writes continue**

Add:

```javascript
test("a disabled field does not stop an independent writable field", () => {
  const { documentRef, form } = preparedForm({ disabled: ["matricula"] });
  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", matricula: "123" },
  });
  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "changed");
  assert.equal(result.field_results.matricula.status, "disabled");
  assert.equal(documentRef.getElementById("txtCargo").value, "Professor");
});

test("an unavailable select option does not stop a text field", () => {
  const { documentRef, form } = preparedForm({
    selects: { fundamento_legal: [{ value: "41", label: "EC 41/2003" }] },
  });
  const result = filler.applyFill({
    documentRef,
    identity: form.identity,
    generation: form.generation,
    fields: { cargo: "Professor", fundamento_legal: "99" },
  });
  assert.equal(result.ok, true);
  assert.equal(result.field_results.cargo.status, "changed");
  assert.equal(result.field_results.fundamento_legal.status, "option_unavailable");
});
```

Also add a write/reread failure case where a later field still runs.

- [ ] **Step 2: Run RED tests**

```bash
node --test extension/tests/fill-form.test.mjs
```

Expected: current Phase A sets global refusal and marks valid fields `skipped`.

- [ ] **Step 3: Keep global guards before first write**

Before touching controls, still reject the entire command on:
- identity mismatch;
- missing/stale generation;
- unreadable/wrong form.

These return `ok: false` and zero writes.

- [ ] **Step 4: Execute proposed fields independently**

For each proposed field:
- empty proposal => `missing_proposal`;
- missing control => `not_found`;
- disabled/readOnly => `disabled`;
- current equal => `preserved`;
- invalid select value => `option_unavailable`;
- writable => set, dispatch events, reread, then `changed` or `failed`.

Do not convert another valid field to `skipped`.

- [ ] **Step 5: Define operation-level success**

Return `ok: true` when:
- identity/generation guards passed; and
- the filler completed its per-field pass and produced `field_results`.

Individual field failures remain in `field_results`.

- [ ] **Step 6: Run extension tests**

```bash
node --test extension/tests/fill-form.test.mjs
npm test --prefix extension
```

Expected: all extension tests green with no submit command introduced.

- [ ] **Step 7: Commit**

```bash
git add extension/content/fill-form.js extension/tests/fill-form.test.mjs
git commit -m "refactor: fill portal fields independently"
```

---

### Task 6: Separate fill-request outcome from process documentary status

**Files:**
- Modify: `app/area_restrita/fill_service.py`
- Modify: `tests/test_fill_service.py`
- Modify if schema persistence needs an attempt counter: `app/core/store.py`, `tests/test_store.py`

**Interfaces:**
- Produces helper: `summarize_field_results(field_results, mandatory_fields) -> dict[str, Any]`
- Fill request may become `PREENCHIDO` with warnings while process remains `PRONTO`.
- Hard identity ambiguity may set fill request `BLOQUEADO` without rewriting a valid process's documentary classification.
- Technical failure sets fill request `ERRO` without automatically setting process `ERRO`.

- [ ] **Step 1: Add RED state tests**

Add tests proving:
1. `changed cargo + disabled matricula` => request terminal report, process still `PRONTO`;
2. all mandatory fields satisfied => process `PREENCHIDO`;
3. technical extension refusal => request `ERRO`, process still `PRONTO`;
4. identity mismatch => request `BLOQUEADO`, no accidental fill command;
5. process remains eligible for a new request after partial/technical failure.

- [ ] **Step 2: Run RED tests**

```bash
python -m unittest tests.test_fill_service -v
```

Expected: current `_verified_fields()`, `_block()`, and `_fail()` rewrite process status too aggressively.

- [ ] **Step 3: Replace all-fields verification with result summarization**

Implement summary logic:
- `changed` and equivalent `preserved` are satisfied;
- `missing_proposal`, `not_found`, `disabled`, `option_unavailable`, `failed`, and divergent-preserved mandatory fields remain unresolved;
- collect changed, preserved, warnings/unresolved;
- process becomes `PREENCHIDO` only if every mandatory field that has a proposal is satisfied and there are no unresolved mandatory review conditions.

Keep exact field names from `MANDATORY_FIELDS`.

- [ ] **Step 4: Stop operational failure from rewriting process documentary state**

Change:
- `_fail()`: update fill request/event only;
- `_block()`: block the fill request; do not blindly set the process workflow status;
- success promotion: set process `PREENCHIDO` only from the summary rule.

Record workflow events such as `fill_failed`, `fill_blocked`, `form_filled_partial`, `form_filled` without abusing process status.

- [ ] **Step 5: Add one stale-generation reread/replan retry**

When extension returns a typed stale-generation result:
1. queue one new `READ_FORM`;
2. mark retry count in request state/snapshot metadata;
3. rebuild preflight from the fresh snapshot;
4. on second stale-generation outcome, finish fill request as `ERRO` and leave process status unchanged.

Never retry identity mismatch.

- [ ] **Step 6: Run state-machine tests**

```bash
python -m unittest tests.test_fill_service -v
python -m unittest tests.test_store -v
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add app/area_restrita/fill_service.py app/core/store.py tests/test_fill_service.py tests/test_store.py
git commit -m "fix: separate fill attempts from process status"
```

If `app/core/store.py` is not needed after implementing retry metadata in the existing snapshot JSON, omit it from the commit rather than making an unnecessary schema change.

---

### Task 7: Update API validation and fill-request payloads for partial results

**Files:**
- Modify: `app/api/server.py`
- Modify: `tests/test_api_server.py`

**Interfaces:**
- `_fill_result_problem()` accepts the new field statuses.
- `GET /api/v1/fill-requests/{id}` exposes summary/warnings needed by Mesa.
- No new unauthenticated mutation route.

- [ ] **Step 1: Add RED API tests**

Test:
- FILL_FORM result with `changed` + `disabled` is accepted as a structurally valid result;
- missing `field_results` remains invalid;
- fill-request GET exposes `changed`, `preserved`, unresolved/warnings or equivalent stored summary;
- retryable process remains `PRONTO`.

- [ ] **Step 2: Run RED API tests**

```bash
python -m unittest tests.test_api_server -v
```

- [ ] **Step 3: Relax result contract only at the field-content level**

`_fill_result_problem()` should validate structure and status presence, not require all field statuses to be successful. Keep command ownership/session/authentication unchanged.

- [ ] **Step 4: Expose the stored fill summary**

Extend the existing fill-request response; do not create a parallel status API.

- [ ] **Step 5: Run API tests**

```bash
python -m unittest tests.test_api_server -v
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add app/api/server.py tests/test_api_server.py
git commit -m "api: expose best-effort fill results"
```

---

### Task 8: Show partial-fill results and keep retry available in the Mesa

**Files:**
- Modify: `app/web/app.js`
- Modify: `app/web/index.html` if a dedicated summary container is required
- Modify: `app/web/app.css`
- Modify: `app/web/tests/ui-wiring.test.mjs`

**Interfaces:**
- Consumes existing process detail + fill-request response.
- Produces user-facing summary: changed/preserved/review counts.
- Fill action stays available while process is documentary `PRONTO`.

- [ ] **Step 1: Add RED wiring assertions**

Add assertions that source contains/rendering exposes:
- partial summary text;
- warnings list;
- retry button/action for `PRONTO`;
- no final-submit action.

Use the existing DOM/wiring test style rather than introducing a browser framework.

- [ ] **Step 2: Run RED web tests**

```bash
node --test app/web/tests/*.test.mjs
```

- [ ] **Step 3: Render a compact fill summary**

Show text equivalent to:

```text
Ato preenchido — 4 alterados, 1 preservado, 1 para revisar.
Confira o formulário e conclua manualmente no portal.
```

Warnings should name field + code/reason.

- [ ] **Step 4: Keep the action available after partial/technical attempts**

Eligibility follows current process documentary status. If the process is still `PRONTO`, a previous fill request warning/error must not hide the action.

- [ ] **Step 5: Run web tests**

```bash
node --test app/web/tests/*.test.mjs
python -m unittest tests.test_web_suite -v
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add app/web/app.js app/web/index.html app/web/app.css app/web/tests/ui-wiring.test.mjs
git commit -m "ui: report partial form filling"
```

Only stage `index.html` if it actually changes.

---

### Task 9: Validate full backend-to-extension best-effort flow

**Files:**
- Modify: `tests/test_fill_service.py`
- Modify: `extension/tests/router.test.mjs`
- Modify: `extension/tests/fill-form.test.mjs`

**Interfaces:**
- Contract chain: `READ_FORM -> build_fill_plan -> FILL_FORM -> field_results -> FillService summary`.

- [ ] **Step 1: Add integration-style RED tests**

Cover:
- legal documentary text not equal to portal label;
- one missing content control plus two writable controls;
- existing divergent field preserved;
- valid legal option written from v4;
- field result reread matches proposed;
- process remains `PRONTO` when one mandatory field is unresolved.

- [ ] **Step 2: Run focused integration suites**

```bash
python -m unittest tests.test_legal_rules tests.test_fill_service tests.test_api_server -v
node --test extension/tests/detect-form.test.mjs extension/tests/fill-form.test.mjs extension/tests/router.test.mjs
```

Expected: green after Tasks 1–8.

- [ ] **Step 3: Verify forbidden commands remain absent**

```bash
node --test extension/tests/protocol.test.mjs
python -m unittest tests.test_extension_parity -v
```

- [ ] **Step 4: Commit test-only hardening**

```bash
git add tests/test_fill_service.py extension/tests/router.test.mjs extension/tests/fill-form.test.mjs
git commit -m "test: cover best-effort fill integration"
```

---

### Task 10: Run full gates and record supervised portal validation

**Files:**
- Create: `docs/notes/2026-09-23-best-effort-fill-validation-handoff.md`

**Interfaces:**
- No new runtime interface.

- [ ] **Step 1: Run the complete automated gate**

```bash
python -m unittest discover -s tests -p "test_*.py" -q
npm test --prefix extension
node --test app/web/tests/*.test.mjs
powershell -ExecutionPolicy Bypass -File .\verify-project.ps1
git diff --check
```

Expected: all green.

- [ ] **Step 2: Validate at least five supervised real portal cases**

Use:
1. ECE 20/2020 non-literal case;
2. EC 41/2003;
3. EC 47/2005;
4. CF art. 40;
5. deliberately weak/non-literal legal match.

For each, record:
- process identity;
- documentary legal text;
- current portal options;
- top legal candidates;
- chosen option;
- confidence/margin/hard conflict;
- changed/preserved/unresolved fields;
- reread result;
- process status after attempt.

Do not click final completion automatically.

- [ ] **Step 3: Verify the key operational acceptance case**

Create one controlled case where a non-critical field cannot be filled but independent fields can. Confirm:
- valid fields are written;
- unresolved field is reported;
- no valid field is skipped solely because another failed;
- process remains retryable when a mandatory field is unresolved.

- [ ] **Step 4: Write the handoff**

The note must contain:
- commit SHA tested;
- exact test commands and results;
- five supervised cases;
- any portal-specific anomalies;
- confirmation that no submit automation was introduced.

- [ ] **Step 5: Commit**

```bash
git add docs/notes/2026-09-23-best-effort-fill-validation-handoff.md
git commit -m "docs: record best-effort fill validation"
```

---

## Final Acceptance Gate

Before merge/review, verify:

```text
[ ] main was promoted from codex/mesa-local-refactor before Task 1
[ ] implementation branch started from promoted main
[ ] hard identity safety remains fail-closed
[ ] one field problem no longer prevents independent valid writes
[ ] existing divergent values are preserved, not silently overwritten
[ ] legal-foundation-v4 always picks one real option when documentary text + real catalog exist
[ ] placeholder cannot win
[ ] low confidence/margin/tie/hard conflict do not leave legal field empty
[ ] stale generation writes nothing and gets only one automatic reread/replan
[ ] operational failure does not corrupt process documentary status
[ ] partial fill remains retryable
[ ] no submit/finalize capability exists
[ ] Python, extension, web and project verification gates are green
[ ] supervised portal validation is documented
```
