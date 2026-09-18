# M5 — Thin Extension and Mesa-Driven Form Filling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Move form-opening and filling orchestration to the Mesa, reduce the new extension to portal observation/execution, provide manual fallback, and make auto-submit impossible in the new protocol.

**Architecture:** A fill request is a backend workflow. The Mesa creates it, the extension receives only specific OPEN_ACT, READ_FORM and FILL_FORM commands, and the backend validates every intermediate result. There is no SUBMIT command type. The legacy extension remains installed as rollback until real equivalence is proven.

**Tech Stack:** Python SQLite/HTTP, Chrome MV3 JavaScript, node:test, existing portal DOM behavior as migration source.

**Spec:** docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md

## Global Constraints

- The new protocol has no submit/finalize command.
- The new extension never chooses a process or legal outcome.
- The backend is authoritative for mandatory fields and legal decisions.
- Identity must match process + interested person before any field write.
- Existing divergent portal values block writing; no partial write on preflight failure.
- genero is optional; six other configured fields are mandatory.
- Manual fallback and automatic navigation must use the same fill-form implementation.
- The legacy extension is not deleted in M5.

## File map

Create app/area_restrita/fill_service.py and tests/test_fill_service.py. Expand root extension with content/navigate.js, detect-form.js and fill-form.js. Reduce root sidepanel to connection/current-form fallback. Extend protocol/router and Mesa UI.

### Task 1: Backend fill-request state machine

**Files:**
- Create: app/area_restrita/fill_service.py
- Modify: app/core/store.py
- Create: tests/test_fill_service.py

**Interfaces:**
- FillService.request_fill(process_id: int) -> int
- FillService.handle_command_result(command_id: int, result: dict) -> None
- FillService.request_manual_fill(form_snapshot: dict) -> int
- fill request states: OPENING, READING, PREFLIGHT, FILLING, PREENCHIDO, BLOQUEADO, ERRO.
- Store methods create_fill_request, get_fill_request, update_fill_request.
- extension command metadata contains fill_request_id.

- [ ] **Step 1: Write failing state-machine test**

~~~python
request_id = service.request_fill(process_id)
open_command = store.claim_extension_command("extension-test")
self.assertEqual(open_command["type"], "OPEN_ACT")

service.handle_command_result(open_command["id"], {
    "ok": True,
    "identity": {"processKey": "102390/2026", "interestedNormalized": "pessoa exemplo"},
})
read_command = store.claim_extension_command("extension-test")
self.assertEqual(read_command["type"], "READ_FORM")
~~~

Also test that a process not in PRONTO state is refused and that identity mismatch becomes BLOQUEADO.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_fill_service -v

Expected: fill service missing.

- [ ] **Step 3: Implement store migration and state machine**

Add portal_fill_requests with process_id, state, current_command_id, error, created_at, updated_at. request_fill validates PRONTO and creates OPEN_ACT. Result handling must transition only through the defined sequence and reject stale/foreign command ids.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_fill_service tests.test_area_scan -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add app/area_restrita app/core tests/test_fill_service.py
git commit -m "feat: add Mesa fill request state machine"
~~~

### Task 2: Form preflight and backend fill plan

**Files:**
- Create: app/area_restrita/preflight.py
- Modify: app/area_restrita/fill_service.py
- Modify: tests/test_fill_service.py
- Modify: tests/test_legal_rules.py

**Interfaces:**
- build_fill_plan(process: dict, form_snapshot: dict) -> FillPlan
- FillPlan: identity, generation, fields, preserved, legal_decision, warnings.
- Allowed fields: modalidade, fundamento_legal, data_publicacao_doe, cargo, matricula, data_nascimento, genero.
- Mandatory: all except genero.

- [ ] **Step 1: Write failing preflight tests**

Cases:
- exact identity + empty controls -> fill plan succeeds;
- missing data_nascimento -> block with FIELD_PROPOSAL_MISSING;
- existing portal value equal to proposal -> preserved;
- existing non-empty divergent value -> block with EXISTING_VALUE_DIVERGENCE;
- select proposal absent from current options -> block;
- fundamento_legal uses backend resolve_legal_foundation with current form options.

Example:

~~~python
plan = build_fill_plan(process, form_snapshot)
self.assertEqual(plan.fields["cargo"], "Professor")
self.assertEqual(plan.preserved, {})
self.assertEqual(plan.legal_decision["rules_version"], "legal-foundation-v3")
~~~

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_fill_service -v

Expected: preflight module missing.

- [ ] **Step 3: Implement fail-closed preflight**

The form snapshot must include identity, generation, fields with value/disabled/readOnly, and options for selects. Reject disabled/readOnly mandatory controls. Do not write any field if any mandatory field fails preflight.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_fill_service tests.test_legal_rules -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add app/area_restrita/preflight.py app/area_restrita/fill_service.py tests
git commit -m "feat: centralize form preflight in backend"
~~~

### Task 3: Extract navigation and form reader into thin extension

**Files:**
- Create: extension/content/navigate.js
- Create: extension/content/detect-form.js
- Create: extension/tests/navigate.test.mjs
- Create: extension/tests/detect-form.test.mjs
- Modify: extension/manifest.json
- Modify: extension/lib/protocol.js
- Modify: extension/background/router.js

**Interfaces:**
- OPEN_ACT payload: processKey, interestedNormalized, portalActId.
- READ_FORM result: identity, generation, fields, options.
- navigate.js knows list pagination, Complementar Ato opening, interested selection and return behavior.
- detect-form.js is read-only.

- [ ] **Step 1: Port failing behavior tests from legacy**

Port the relevant non-submit scenarios from:
- work/tce-extractor/portable/extensao-complementar-ato/tests/portal-navigation.test.mjs
- form-detector.test.mjs

Required cases: legacy frames, list pagination, opening dynamic act frame, interested screen, selecting exact interested person, late form appearance, process/year identity, hidden form rejection, option catalog read.

- [ ] **Step 2: Verify RED**

Run: cd extension && node --test tests/navigate.test.mjs tests/detect-form.test.mjs

Expected: new modules missing.

- [ ] **Step 3: Extract proven selectors and behavior**

Do not redesign selectors. Move only the behavior required by OPEN_ACT and READ_FORM from current portal-navigation.js and form-detector.js. Keep side effects isolated to explicit navigation commands.

- [ ] **Step 4: Run new and legacy suites**

Run new extension tests and then legacy npm test. Both must remain green.

- [ ] **Step 5: Commit**

~~~text
git add extension/content extension/tests extension/manifest.json extension/lib/protocol.js extension/background/router.js
git commit -m "feat: add thin portal navigation and form reader"
~~~

### Task 4: Single fill implementation with no submit capability

**Files:**
- Create: extension/content/fill-form.js
- Create: extension/tests/fill-form.test.mjs
- Modify: extension/lib/protocol.js
- Modify: extension/background/router.js

**Interfaces:**
- FILL_FORM payload: identity, generation, fields.
- FILL_FORM result: identity, generation_after, field_results.
- field_results per field: before, proposed, after, status.
- There is no SUBMIT, COMPLEMENT, SEND or AUTO_SUBMIT protocol type.

- [ ] **Step 1: Write failing fill tests**

Port write/verify behavior from the current form-detector.js and relevant preflight tests.

Required cases:
- native value setter is used;
- input/change/blur events bubble;
- select value must exist;
- identity mismatch writes nothing;
- stale generation writes nothing;
- disabled/readOnly writes nothing;
- a failed field verification returns failure and the backend does not mark PREENCHIDO.

- [ ] **Step 2: Add a protocol-negative test**

~~~javascript
const types = Object.values(MESSAGE_TYPES);
for (const forbidden of ["SUBMIT", "SEND", "AUTO_SUBMIT", "COMPLEMENT_ACT"]) {
  assert.equal(types.includes(forbidden), false);
}
~~~

Also scan root extension source in the test and fail if exact submit button click logic is added.

- [ ] **Step 3: Verify RED**

Run: cd extension && node --test tests/fill-form.test.mjs tests/protocol.test.mjs

Expected: fill module missing.

- [ ] **Step 4: Implement fill-form**

Reuse FIELD_MAP:
- modalidade -> txtModalidade
- fundamento_legal -> txtFundamentoLegal
- data_publicacao_doe -> txtDataDOE
- cargo -> txtCargo
- matricula -> txtMatricula
- data_nascimento -> txtDataNascimento
- genero -> txtGenero

Perform one pre-write identity/generation check, write all planned fields, then reread every written/preserved field. Return result; never locate or click the final Complementar Ato button.

- [ ] **Step 5: Verify and commit**

Run root extension npm test and legacy npm test.

~~~text
git add extension
git commit -m "feat: add verified form filling without submission"
~~~

### Task 5: Complete backend orchestration OPEN -> READ -> PREFLIGHT -> FILL

**Files:**
- Modify: app/area_restrita/fill_service.py
- Modify: app/api/server.py
- Modify: app/web/index.html
- Modify: app/web/app.js
- Modify: tests/test_fill_service.py
- Modify: tests/test_api_server.py

**Interfaces:**
- POST /api/v1/processes/ID/fill -> fill_request_id
- GET /api/v1/fill-requests/ID -> state/result
- successful READ_FORM result runs build_fill_plan and queues FILL_FORM.
- successful verified FILL_FORM sets process status PREENCHIDO and workflow event form_filled.
- blocked preflight keeps process REVISAR or BLOQUEADO and writes no FILL_FORM command.

- [ ] **Step 1: Write failing full-chain test**

Mock extension command results:
1. OPEN_ACT success;
2. READ_FORM with exact identity/options;
3. FILL_FORM with after values equal proposals.

Assert final fill request is PREENCHIDO and process workflow has form_filled.

- [ ] **Step 2: Verify RED**

Run Python fill/API tests.

- [ ] **Step 3: Implement routes and Mesa action**

Show Preencher ato only for PRONTO. While running show Abrindo ato, Lendo formulário, Validando and Preenchendo. Technical command ids remain hidden.

- [ ] **Step 4: Verify GREEN**

Run all Python tests and root extension tests.

- [ ] **Step 5: Commit**

~~~text
git add app tests
git commit -m "feat: drive verified act filling from Mesa"
~~~

### Task 6: Manual current-form fallback using the same filler

**Files:**
- Modify: extension/sidepanel/panel.html
- Modify: extension/sidepanel/panel.js
- Modify: extension/background/router.js
- Modify: app/api/server.py
- Modify: app/area_restrita/fill_service.py
- Modify: extension/tests/router.test.mjs
- Modify: tests/test_fill_service.py

**Interfaces:**
- sidepanel action: Preencher formulário atual.
- extension first READ_FORMs the current tab.
- POST /api/v1/portal/manual-form with snapshot creates a fill request for the matching PRONTO process.
- backend queues the same FILL_FORM command used by automatic navigation.

- [ ] **Step 1: Write failing manual-flow tests**

Assert current form identity finds exactly one PRONTO process. Zero or multiple matches block. Assert the resulting FILL_FORM payload is identical to automatic mode for the same snapshot.

- [ ] **Step 2: Verify RED**

Run Python and root extension tests.

- [ ] **Step 3: Implement minimal sidepanel**

Sidepanel contains only:
- Mesa connected status;
- Área Restrita detected status;
- current process identity if form is open;
- Preencher formulário atual;
- Abrir Mesa;
- diagnostic text.

No dataset import, lot, acquisition, legal-rule or auto-submit controls.

- [ ] **Step 4: Verify GREEN**

Run all root extension tests and fill service tests.

- [ ] **Step 5: Commit**

~~~text
git add extension/sidepanel extension/background app tests
git commit -m "feat: add manual current-form fallback"
~~~

### Task 7: Supervised real filling equivalence gate

**Files:** code only when a defect is reproduced and tested.

- [ ] **Step 1: Use one real PRONTO process and automatic Open/Read only.**

Confirm identity and option catalogs without writing.

- [ ] **Step 2: Run backend preflight and inspect proposed values in the Mesa.**

Do not issue FILL_FORM if any value is unexpected.

- [ ] **Step 3: Authorize FILL_FORM for that process and verify DOM reread.**

No final click. Compare all six mandatory values and optional genero behavior.

- [ ] **Step 4: Repeat with manual current-form fallback.**

The same process/snapshot must generate the same fill plan.

- [ ] **Step 5: Expand to a supervised sample of at least five acts before making the new extension the default.**

Any portal-side mismatch blocks M5 exit. Final submission remains manual throughout.

## M5 Exit Gate

- Mesa owns fill workflow.
- New extension supports scan, navigation, form read and form fill only.
- New protocol cannot submit an act.
- Automatic and manual paths share one fill-form implementation.
- Backend preflight is authoritative.
- Real supervised fills reread exactly as proposed.
- Legacy extension remains available for rollback until packaging/cleanup M6.
