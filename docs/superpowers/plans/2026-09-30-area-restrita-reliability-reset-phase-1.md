# Area Restrita Reliability Reset — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reestablish trust in the Área Restrita by qualifying manual-form fill first, then benchmarking MV3 navigation against an experimental Playwright/CDP controller through AR-2 and AR-3 before choosing the production navigation architecture.

**Architecture:** The root runtime (`app/`, `extension/`, `tests/`, `packaging/`) remains the shipped product because `START.cmd` runs `app.main` and the portable builder packages root `app/` and `extension/`. Reliability state and sanitized telemetry live in the local data root, while the competing Playwright/CDP controller stays under `devtools/` and `scripts/` until the benchmark selects it. This plan deliberately stops after AR-3 and an architecture decision; AR-4 through AR-6 require a second implementation plan written against the winning architecture.

**Tech Stack:** Python 3 embedded runtime, SQLite-backed Mesa, Chrome MV3 extension, Node test runner, Playwright/CDP for development-only benchmark, PowerShell packaging gates.

**Spec:** `docs/superpowers/specs/2026-09-30-area-restrita-reliability-reset-design.md`

## Global Constraints

- Initial Área Restrita capability state is `UNQUALIFIED`.
- Offline tests never promote a capability to `QUALIFIED` or `PRODUCTION`.
- `QUALIFIED` requires 20/20 real consecutive runs on one unchanged build.
- `PRODUCTION` requires another 20/20 real consecutive runs from the distributable artifact in normal Chrome.
- Any reproducible production regression returns the affected capability to `UNQUALIFIED`.
- The final **Complementar Ato** action remains manual; no SUBMIT/SEND/AUTO_SUBMIT/COMPLEMENT_ACT/FINALIZE capability may be introduced.
- Identity, ambiguity, generation, select-catalog and session guards remain fail-closed.
- Do not fix navigation by merely increasing delay/retry/timeout. A structural state predicate must be identified first.
- Real qualification uses one portal action at a time with the operator present.
- Never manufacture stale, ambiguous, denied or expired portal state by altering production data.
- Never persist process number, interested name, CPF, matrícula, cookies, tokens, credentials, response bodies or raw private HTML in versioned artifacts.
- The experimental controller must remain excluded from the portable package throughout Phase 1.
- No AR-4, AR-5 or AR-6 production implementation starts in this plan.

## Review Focus

1. **Old/hidden form remains mounted while another form is visible.** The reader and telemetry must bind a run only to one visible exact identity; tests belong to Tasks 3 and 4.
2. **MV3 worker/browser session restarts between request and result.** The run must terminate as a classified failure rather than silently resuming with a different session; tests belong to Tasks 2 and 4.
3. **Two interested rows normalize to the same identity.** Both MV3 and controller paths must return ambiguity with zero click; tests belong to Tasks 6 and 8.
4. **Portal returns access denied/login/session-expired content with HTTP 200.** State classification must stop navigation without blind retry; tests belong to Tasks 6 and 7.
5. **A qualification sequence mixes builds or uses technical recovery.** The evaluator must reset/refuse the sequence instead of counting it toward 20/20; tests belong to Tasks 1 and 5.

---

## File Structure

### Production reliability foundation

- Create: `app/area_restrita/reliability.py` — capability state, local HMAC identity hashing, append-only sanitized run telemetry, qualification evaluation.
- Modify: `app/api/server.py` — read-only reliability status endpoint and lifecycle hooks for manual fill.
- Modify: `app/area_restrita/fill_service.py` — AR-1 run lifecycle around `request_manual_fill` and command outcomes without changing legal/preflight semantics.
- Modify: `extension/lib/api.js` — fetch reliability status through the existing authenticated bridge.
- Modify: `extension/lib/protocol.js` — add read-only reliability status message only; forbidden final-action vocabulary remains unchanged.
- Modify: `extension/background/router.js` — route reliability status and emit sanitized browser/frame diagnostics for the current-form/manual-fill path.
- Modify: `extension/sidepanel/state.js` — derive capability labels and enablement.
- Modify: `extension/sidepanel/panel.js` and `extension/sidepanel/panel.html` — show EXPERIMENTAL/QUALIFIED/PRODUCTION status; hide/disable unqualified automatic navigation.

### Reliability tooling

- Create: `scripts/portal-reliability/qualification.py` — evaluate latest consecutive runs for a capability/build/environment.
- Create: `scripts/portal-reliability/report.py` — generate sanitized benchmark/qualification summaries.
- Create: `docs/notes/2026-09-30-area-restrita-runtime-source.md` — source-of-truth and baseline record.
- Create during execution: `docs/notes/YYYY-MM-DD-area-restrita-ar1-qualification.md`.
- Create during execution: `docs/notes/YYYY-MM-DD-area-restrita-ar2-ar3-benchmark.md`.
- Create during execution: `docs/notes/YYYY-MM-DD-area-restrita-navigation-architecture-decision.md`.

### Experimental controller

- Create: `devtools/area-restrita/controller/model.mjs` — portal states and normalized outcomes.
- Create: `devtools/area-restrita/controller/shared-runtime.mjs` — inject/read the canonical root `extension/lib/area-snapshot.js` and `extension/content/detect-form.js`; do not duplicate selector maps.
- Create: `devtools/area-restrita/controller/browser.mjs` — CDP connection, tab/frame enumeration and structural observation.
- Create: `devtools/area-restrita/controller/navigation.mjs` — experimental `openAct` and `selectInterested` only.
- Create: `scripts/portal-reliability/controller-trial.mjs` — one supervised controller trial at a time.
- Create: `scripts/portal-reliability/mv3-trial.py` — one supervised MV3 trial using existing Mesa/extension commands; exact target resolved locally, identities never printed.

### Tests

- Create: `tests/test_area_restrita_reliability.py`.
- Modify: `tests/test_fill_service.py`.
- Modify: `tests/test_api_server.py`.
- Modify: `tests/test_packaging_contract.py`.
- Modify: `tests/test_devtools_runtime_boundary.py`.
- Create: `extension/tests/reliability-state.test.mjs`.
- Modify: `extension/tests/router.test.mjs`.
- Modify: `extension/tests/sidepanel-state.test.mjs`.
- Modify: `extension/tests/sidepanel-wiring.test.mjs`.
- Create: `devtools/area-restrita/controller/controller.test.mjs`.

---

### Task 0: Lock the shipped runtime source and baseline

**Files:**
- Create: `docs/notes/2026-09-30-area-restrita-runtime-source.md`
- Read: `START.cmd`
- Read: `packaging/build-portable.ps1`
- Read: `packaging/verify-package.ps1`
- Read: `README.md`
- Read: `docs/ESTRUTURA.md` when present
- Read: `work/tce-extractor/verify-project.ps1`

**Interfaces:**
- Consumes: repository HEAD and packaging scripts.
- Produces: one authoritative statement naming the production tree and the verifier-only/legacy tree for this goal.

- [ ] **Step 1: Create an isolated worktree from the approved spec branch**

Use `superpowers:using-git-worktrees`.

Run:

```powershell
git fetch origin --prune
git worktree add ..\Atos-TCE-reliability -b codex/area-restrita-reliability-reset origin/codex/area-restrita-reliability-reset-spec
```

Expected: new worktree with a clean status and the approved spec present.

- [ ] **Step 2: Prove the shipped source tree from executable/build inputs**

Record exact evidence:

```text
START.cmd -> python -m app.main
build-portable.ps1 -> root app/ + extension/ + START.cmd
verify-package.ps1 -> validates the root portable artifact
```

Do not infer source authority from old handoffs.

- [ ] **Step 3: Write the runtime-source note**

The note must explicitly state:

```text
Production source for Reliability Reset: root app/, extension/, tests/, packaging/
work/tce-extractor: verifier/legacy compatibility tree for this goal unless an executable build input proves otherwise
No dual implementation of the same fix
```

- [ ] **Step 4: Run the complete pre-change baseline**

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -q
npm test --prefix extension
node --test app/web/tests/*.test.mjs
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1
git diff --check
```

Expected: all mandatory gates green. If the current branch already has a failing gate, stop and diagnose it before Task 1.

- [ ] **Step 5: Commit only the source-of-truth note**

```powershell
git add docs/notes/2026-09-30-area-restrita-runtime-source.md
git commit -m "docs: lock Area Restrita runtime source"
```

---

### Task 1: Add the reliability ledger and qualification evaluator

**Files:**
- Create: `app/area_restrita/reliability.py`
- Create: `tests/test_area_restrita_reliability.py`

**Interfaces:**
- Produces:
  - `CapabilityState`: `UNQUALIFIED | EXPERIMENTAL | QUALIFIED | PRODUCTION`.
  - `ReliabilityRecorder(data_root: Path, build_id: str)`.
  - `ReliabilityRecorder.start(capability: str, environment: str, browser_session_id: str | None = None) -> str`.
  - `ReliabilityRecorder.transition(run_id: str, *, boundary: str, state_before: str | None, state_after: str | None, result_code: str, elapsed_ms: int | None = None, expected_identity: Mapping | None = None, observed_identity: Mapping | None = None, generation_before: int | None = None, generation_after: int | None = None) -> None`.
  - `ReliabilityRecorder.intervention(run_id: str, kind: str) -> None`.
  - `ReliabilityRecorder.finish(run_id: str, *, passed: bool, result_code: str) -> None`.
  - `ReliabilityRecorder.summary(capability: str, environment: str) -> dict`.
  - `ReliabilityRecorder.evaluate(capability: str, environment: str, required: int = 20) -> dict`.
  - `ReliabilityRecorder.set_state(capability: str, state: CapabilityState, *, reason: str) -> None`.
- Storage under the local data root:
  - `reliability/events.jsonl`
  - `reliability/capabilities.json`
  - `reliability/identity.key`
- Identity hashing: local HMAC-SHA256; serialized events never contain raw identity values.

- [ ] **Step 1: Write RED tests for default capability state and local-only storage**

Tests:

```python
def test_capabilities_default_to_unqualified(): ...
def test_reliability_files_live_under_data_root(): ...
```

Assert every spec capability begins `UNQUALIFIED`.

Run:

```powershell
python -m unittest tests.test_area_restrita_reliability -v
```

Expected: FAIL because the module does not exist.

- [ ] **Step 2: Write RED tests for sanitization**

Tests:

```python
def test_identity_is_persisted_only_as_local_hmac(): ...
def test_event_rejects_forbidden_private_keys(): ...
def test_event_never_serializes_process_or_interested_text(): ...
```

Forbidden serialized keys include `processKey`, `process_key`, `interested`, `interestedNormalized`, `cpf`, `matricula`, `cookie`, `token`, `authorization`.

- [ ] **Step 3: Write RED tests for the 20/20 sequence rules**

Tests:

```python
def test_twenty_consecutive_same_build_passes_qualification(): ...
def test_failure_resets_the_counted_sequence(): ...
def test_build_change_breaks_the_sequence(): ...
def test_intervention_breaks_the_sequence(): ...
def test_offline_environment_never_qualifies_real_capability(): ...
def test_production_requires_portable_normal_chrome_environment(): ...
```

Use environments exactly:

```text
offline
real-dev
portable-normal-chrome
```

- [ ] **Step 4: Implement the minimal reliability module**

Use atomic replacement for `capabilities.json`; append JSONL events with flush. Generate `identity.key` locally if absent. Do not use SQLite or change schema in Phase 1.

- [ ] **Step 5: Run the focused tests**

```powershell
python -m unittest tests.test_area_restrita_reliability -v
```

Expected: PASS.

- [ ] **Step 6: Run root Python tests and commit**

```powershell
python -m unittest discover -s tests -p "test_*.py" -q
git diff --check
git add app/area_restrita/reliability.py tests/test_area_restrita_reliability.py
git commit -m "feat: add Area Restrita reliability ledger"
```

---

### Task 2: Expose capability status and gate the operator UI

**Files:**
- Modify: `app/api/server.py`
- Modify: `tests/test_api_server.py`
- Modify: `extension/lib/api.js`
- Modify: `extension/lib/protocol.js`
- Modify: `extension/background/router.js`
- Modify: `extension/sidepanel/state.js`
- Modify: `extension/sidepanel/panel.js`
- Modify: `extension/sidepanel/panel.html`
- Create: `extension/tests/reliability-state.test.mjs`
- Modify: `extension/tests/router.test.mjs`
- Modify: `extension/tests/sidepanel-state.test.mjs`
- Modify: `extension/tests/sidepanel-wiring.test.mjs`

**Interfaces:**
- Backend read-only route: `GET /api/v1/portal/reliability`.
- Response:
  ```json
  {
    "capabilities": {
      "manual_form_fill": {"state": "UNQUALIFIED", "real_dev_streak": 0, "portable_streak": 0},
      "open_act": {"state": "UNQUALIFIED"},
      "select_interested": {"state": "UNQUALIFIED"},
      "return_to_list": {"state": "UNQUALIFIED"},
      "pagination": {"state": "UNQUALIFIED"},
      "next_process": {"state": "UNQUALIFIED"},
      "area_restrita_end_to_end": {"state": "UNQUALIFIED"}
    }
  }
  ```
- Extension message: `RELIABILITY_STATUS`.
- No new mutation route for qualification state.

- [ ] **Step 1: Write backend RED for the read-only endpoint**

Tests:

```python
def test_reliability_endpoint_returns_only_sanitized_capability_state(): ...
def test_reliability_endpoint_has_no_identity_or_event_payloads(): ...
```

Run focused server tests and confirm FAIL.

- [ ] **Step 2: Implement the backend route**

Instantiate/read `ReliabilityRecorder` from the Mesa data root. Return only state and streak counts.

- [ ] **Step 3: Write extension RED for message routing**

Assert `RELIABILITY_STATUS` goes through the service worker and returns the backend response without direct sidepanel fetch.

- [ ] **Step 4: Implement API/protocol/router status flow**

Do not add any command type to `COMMAND_TYPES`; this is sidepanel ↔ service-worker request/response only.

- [ ] **Step 5: Write UI-state RED**

Tests must assert:

```text
manual_form_fill UNQUALIFIED -> button disabled, label "Indisponível — não qualificado"
manual_form_fill EXPERIMENTAL -> manual fill enabled, visibly "Experimental"
manual_form_fill QUALIFIED -> manual fill enabled, "Qualificado"
manual_form_fill PRODUCTION -> manual fill enabled, normal production label
next_process UNQUALIFIED/EXPERIMENTAL/QUALIFIED -> disabled in normal operator UI during Phase 1
```

- [ ] **Step 6: Implement UI gating**

Do not add a hidden bypass. Controller/MV3 AR-2/AR-3 experiments are invoked from supervised benchmark tooling, not the normal `Próximo processo` button.

- [ ] **Step 7: Run focused and complete extension tests**

```powershell
node --test extension/tests/reliability-state.test.mjs extension/tests/router.test.mjs extension/tests/sidepanel-state.test.mjs extension/tests/sidepanel-wiring.test.mjs
npm test --prefix extension
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add app/api/server.py tests/test_api_server.py extension
git commit -m "feat: expose Area Restrita capability status"
```

---

### Task 3: Make AR-1 a navigation-independent manual-fill capability

**Files:**
- Modify: `app/area_restrita/fill_service.py`
- Modify: `app/api/server.py`
- Modify: `tests/test_fill_service.py`
- Modify: `tests/test_api_server.py`
- Modify: `extension/background/router.js`
- Modify: `extension/tests/router.test.mjs`

**Interfaces:**
- Existing `FillService.request_manual_fill(form_snapshot)` remains the AR-1 entrypoint.
- A manual AR-1 request must never queue `OPEN_ACT` or `OPEN_NEXT_ACT`.
- `run_id` for AR-1 is stable and derived from the created fill request, e.g. `manual-fill:<request_id>`.
- Browser diagnostics attached to the request/result may contain only:
  - sanitized session id;
  - tab/frame synthetic refs;
  - route path;
  - structural screen;
  - generation.
- Raw identity is used in-memory for safety but converted to HMAC before reliability persistence.

- [ ] **Step 1: Write RED proving manual fill never enters navigation**

Add:

```python
def test_manual_fill_never_queues_open_act_or_open_next_act(): ...
```

After `request_manual_fill(snapshot)`, inspect all commands for the request and assert only the existing read/fill path is used.

- [ ] **Step 2: Write RED for hidden/stale form safety**

Tests:

```python
def test_manual_fill_rejects_identity_change_before_write(): ...
def test_manual_fill_records_form_not_available_as_ar1_failure(): ...
```

Retain existing fail-closed behavior; do not broaden eligibility by weakening identity.

- [ ] **Step 3: Write RED for AR-1 telemetry lifecycle**

Assert boundaries in order:

```text
current_form_detected
manual_fill_requested
preflight_completed
fill_command_completed
reread_completed
run_finished
```

A refusal before write finishes the run with `passed=false`; a successful best-effort fill passes only when the final identity is exact and reread is structurally valid.

- [ ] **Step 4: Add sanitized frame diagnostics in the router**

When resolving `READ_CURRENT_FORM`, include structural metadata in the returned wrapper without modifying `form.identity` or field values. Never persist tab URLs with query strings.

Test old hidden forms: only one visible exact form may become the current form.

- [ ] **Step 5: Implement the reliability hooks**

Do not modify `legal-foundation-v4`, field-status semantics or `fill-form.js` unless a focused RED proves an AR-1 defect there.

- [ ] **Step 6: Mark `manual_form_fill` EXPERIMENTAL only after the offline AR-1 contract is green**

The state change reason must include the current build SHA. It does not count as qualification.

- [ ] **Step 7: Run focused tests**

```powershell
python -m unittest tests.test_fill_service tests.test_api_server tests.test_area_restrita_reliability -v
node --test extension/tests/router.test.mjs extension/tests/reliability-state.test.mjs
```

Expected: PASS.

- [ ] **Step 8: Run full offline gates and commit**

```powershell
python -m unittest discover -s tests -p "test_*.py" -q
npm test --prefix extension
node --test app/web/tests/*.test.mjs
git diff --check
git add app extension tests
git commit -m "feat: isolate manual Area Restrita fill capability"
```

---

### Task 4: Add qualification/report tooling and package boundaries

**Files:**
- Create: `scripts/portal-reliability/qualification.py`
- Create: `scripts/portal-reliability/report.py`
- Modify: `tests/test_area_restrita_reliability.py`
- Modify: `tests/test_devtools_runtime_boundary.py`
- Modify: `tests/test_packaging_contract.py`
- Modify: `.gitignore` if needed for raw/local reliability output.

**Interfaces:**
- `qualification.py --data-root <path> --capability <name> --environment <real-dev|portable-normal-chrome> --required 20 --build <sha>`
- Exit 0 only when the latest valid consecutive sequence satisfies the requested gate.
- `report.py` emits aggregate Markdown/JSON with counts, result codes, median and p95; never identities.

- [ ] **Step 1: Write RED for CLI qualification**

Use a temporary data root and assert exit codes:

```text
19 pass -> nonzero
20 pass same build -> 0
19 pass + 1 failure -> nonzero
20 pass split across builds -> nonzero
20 pass with intervention -> nonzero
```

- [ ] **Step 2: Implement qualification CLI**

The script is a reader of the reliability ledger; it does not mutate capability state.

- [ ] **Step 3: Write RED for aggregate report privacy**

Assert generated reports do not contain fixture process keys/interested names and contain only aggregate codes/timings.

- [ ] **Step 4: Implement report CLI**

Calculate median and p95 deterministically.

- [ ] **Step 5: Strengthen package/runtime-boundary tests**

Assert the portable ZIP excludes:

```text
devtools/area-restrita/controller/
scripts/portal-reliability/controller-trial.mjs
Playwright dev profiles
raw reliability captures
tmp/portal-reliability/
```

Production scripts `qualification.py` and `report.py` may remain source-only unless the final plan explicitly chooses to ship them; Phase 1 must not require them for normal use.

- [ ] **Step 6: Run tests and commit**

```powershell
python -m unittest tests.test_area_restrita_reliability tests.test_devtools_runtime_boundary tests.test_packaging_contract -v
git diff --check
git add scripts/portal-reliability tests .gitignore
git commit -m "test: add Area Restrita qualification tooling"
```

---

### Task 5: Execute and close AR-1 real qualification

**Files:**
- Create: `docs/notes/YYYY-MM-DD-area-restrita-ar1-qualification.md`
- Local-only: `<data-root>/reliability/*`

**Interfaces:**
- Consumes: manual form fill capability from Task 3 and evaluator from Task 4.
- Produces: AR-1 `QUALIFIED` and then `PRODUCTION`, or a root-cause blocker that returns execution to Task 3/4.

- [ ] **Step 1: Freeze the build**

Record:

```powershell
git rev-parse HEAD
git status --short
```

No code changes are allowed during one 20-run sequence.

- [ ] **Step 2: Run 20 supervised real-dev trials**

For each trial:

1. operator manually opens the exact act and interested person;
2. sidepanel must detect one visible form;
3. operator uses **Experimental — Preencher formulário atual**;
4. wait for terminal fill result;
5. verify exact identity and reread result through normal UI/API;
6. do **not** click final **Complementar Ato** as part of the automated capability;
7. return manually to a safe starting point for the next controlled case.

No DevTools correction, service restart or technical reload during the sequence.

- [ ] **Step 3: Evaluate the real-dev sequence**

```powershell
python scripts/portal-reliability/qualification.py --data-root data --capability manual_form_fill --environment real-dev --required 20 --build <HEAD>
```

Expected: exit 0.

If it fails, stop. Use `superpowers:systematic-debugging`; produce one RED from the failing boundary, fix only that root cause, rerun offline gates, then start the 20-run count again at zero.

- [ ] **Step 4: Promote AR-1 to QUALIFIED**

Use the explicit reliability state API/class from Task 1 with reason referencing the qualification report and HEAD. Do not hand-edit JSON.

- [ ] **Step 5: Build a fresh portable artifact and verify it**

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\packaging\build-portable.ps1 -Force
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\packaging\verify-package.ps1
```

Expected: clean extraction smoke green.

- [ ] **Step 6: Run another 20/20 in the clean portable + normal Chrome environment**

Requirements:

```text
START.cmd
normal Chrome
packaged extension
no Codex
no MCP
no DevTools
no lab scripts
no manual DB edits
```

- [ ] **Step 7: Evaluate production qualification**

```powershell
python scripts/portal-reliability/qualification.py --data-root <portable-data-root> --capability manual_form_fill --environment portable-normal-chrome --required 20 --build <HEAD>
```

Expected: exit 0.

- [ ] **Step 8: Promote AR-1 to PRODUCTION and write the qualification note**

The note must record only:

- build SHA;
- package SHA-256;
- 20/20 + 20/20;
- aggregate durations;
- aggregate result codes;
- zero wrong-form events;
- zero technical intervention;
- confirmation that final action remained manual.

- [ ] **Step 9: Commit documentation only**

```powershell
git add docs/notes/*area-restrita-ar1-qualification.md
git commit -m "docs: qualify assisted Area Restrita fill"
```

**Hard gate:** Do not begin Task 6 unless AR-1 is PRODUCTION.

---

### Task 6: Build the experimental controller contract without shipping it

**Files:**
- Create: `devtools/area-restrita/controller/model.mjs`
- Create: `devtools/area-restrita/controller/shared-runtime.mjs`
- Create: `devtools/area-restrita/controller/browser.mjs`
- Create: `devtools/area-restrita/controller/navigation.mjs`
- Create: `devtools/area-restrita/controller/controller.test.mjs`
- Modify: `tests/test_devtools_runtime_boundary.py`

**Interfaces:**
- `PortalState`: `PORTAL_MENU | LIST | OPENING_ACT | INTERESTED | FORM | FORM_FILLED | LOGIN_REQUIRED | ACCESS_DENIED | TRANSITIONING | AMBIGUOUS | SESSION_EXPIRED | UNKNOWN`.
- `observePortal(browser) -> Promise<PortalObservation>`.
- `openAct(browser, identity) -> Promise<NavigationOutcome>`.
- `selectInterested(browser, identity) -> Promise<NavigationOutcome>`.
- Controller actions never include fill, submit, return-list, pagination or next-process in Phase 1.
- Structural code is reused by loading root `extension/lib/area-snapshot.js` and `extension/content/detect-form.js`; no controller selector map is permitted.

- [ ] **Step 1: Write RED for state model and forbidden actions**

Assert exported navigation surface contains exactly:

```text
observePortal
openAct
selectInterested
```

and no `fillForm`, `nextProcess`, `submit` or `finalize`.

- [ ] **Step 2: Write RED proving selector ownership**

Test that `shared-runtime.mjs` resolves the root shared scripts and fails if a local controller selector map is introduced.

- [ ] **Step 3: Write RED state-classification tests**

Fixtures/fakes must cover:

```text
LIST
INTERESTED
FORM
ACCESS_DENIED
LOGIN_REQUIRED/SESSION_EXPIRED
two visible matching forms -> AMBIGUOUS
unknown structural document -> UNKNOWN
```

HTTP 200 does not override an access-denied/login structural state.

- [ ] **Step 4: Implement model/shared runtime/browser observation**

No fixed sleep as a success predicate.

- [ ] **Step 5: Write RED for exact open_act**

Tests:

```text
one exact row -> click once
zero exact row -> ROW_ACTION_NOT_FOUND
two exact candidates -> AMBIGUOUS, zero click
transition ends in INTERESTED or FORM only
ACCESS_DENIED -> terminal refusal, zero retry loop
SESSION_EXPIRED -> terminal refusal
```

- [ ] **Step 6: Implement `openAct`**

Use bounded condition waiting over structural observations.

- [ ] **Step 7: Write RED for exact select_interested**

Tests:

```text
one exact radio -> click once -> FORM
two normalized matches -> AMBIGUOUS -> zero click
identity mismatch after FORM -> TARGET_IDENTITY_MISMATCH
```

- [ ] **Step 8: Implement `selectInterested`**

- [ ] **Step 9: Prove controller remains out of package**

```powershell
python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v
node --test devtools/area-restrita/controller/controller.test.mjs
```

- [ ] **Step 10: Commit**

```powershell
git add devtools/area-restrita/controller tests/test_devtools_runtime_boundary.py
git commit -m "dev: add experimental Area Restrita controller"
```

---

### Task 7: Add one-trial benchmark adapters for MV3 and Controller

**Files:**
- Create: `scripts/portal-reliability/controller-trial.mjs`
- Create: `scripts/portal-reliability/mv3-trial.py`
- Modify: `tests/test_area_restrita_reliability.py`
- Create or Modify: `devtools/area-restrita/controller/controller.test.mjs`

**Interfaces:**
- Every invocation executes at most **one** AR-2 or AR-3 portal action.
- Inputs use a local `process_id` or an in-memory identity resolved from Store/NavigationService; scripts must not print identity.
- Required labels in reliability events:
  - `driver=mv3`
  - `driver=controller`
  - `capability=open_act|select_interested`
- Both adapters write the same normalized outcome vocabulary.

- [ ] **Step 1: Write RED for one-action-only contract**

Attempting `--count 2` or a combined `open-and-fill` mode must be rejected.

- [ ] **Step 2: Write RED that target identity never reaches stdout/stderr/report**

Use fixture identity values and capture output.

- [ ] **Step 3: Implement MV3 trial adapter**

Use existing Mesa command machinery. Do not add a new production command type.

AR-2 invokes only the existing exact `OPEN_ACT` path. AR-3 starts from a manually prepared interested screen and invokes only the interested-selection step through the existing router/content path.

- [ ] **Step 4: Implement Controller trial adapter**

Attach to the existing supervised Chrome/CDP session and call exactly one controller action.

- [ ] **Step 5: Normalize terminal codes**

At minimum:

```text
SUCCEEDED
ROW_ACTION_NOT_FOUND
INTERESTED_NOT_FOUND
AMBIGUOUS
ACCESS_DENIED
SESSION_EXPIRED
TARGET_IDENTITY_MISMATCH
TRANSITION_TIMEOUT
UNKNOWN
```

- [ ] **Step 6: Run tests and commit**

```powershell
python -m unittest tests.test_area_restrita_reliability -v
node --test devtools/area-restrita/controller/controller.test.mjs
git diff --check
git add scripts/portal-reliability devtools/area-restrita/controller tests
git commit -m "dev: add Area Restrita navigation benchmark adapters"
```

---

### Task 8: Qualify and benchmark AR-2 — open exact act

**Files:**
- Local reliability ledger.
- Append findings to: `docs/notes/YYYY-MM-DD-area-restrita-ar2-ar3-benchmark.md`

**Interfaces:**
- Precondition: operator manually prepares the correct list/marker before each trial.
- Outcome must end in exactly `INTERESTED` or `FORM`.
- No fill.

- [ ] **Step 1: Freeze one build for both drivers**

Record HEAD and browser/runtime versions. Do not change code between the two 20-run sets.

- [ ] **Step 2: Execute 20 MV3 AR-2 trials**

One trial at a time. Between trials the operator may manually return to the documented safe list state; that is setup, not technical recovery.

Any wrong target, ambiguous auto-choice, reload needed to recover, worker restart used as a fix, access denied or unknown state fails the sequence.

- [ ] **Step 3: Execute 20 Controller AR-2 trials**

Use the same qualification rules and comparable target distribution where safe.

- [ ] **Step 4: Generate aggregate report**

```powershell
python scripts/portal-reliability/report.py --data-root data --capability open_act --build <HEAD> --format markdown
```

Report:

- attempts;
- passes/failures;
- median;
- p95;
- result-code counts;
- frame/session loss counts;
- technical-intervention counts.

- [ ] **Step 5: Apply the root-cause loop if either driver is below 20/20**

Do not patch both drivers simultaneously. Diagnose one failing boundary, add RED, fix, rerun offline tests, then restart that driver's sequence at zero.

- [ ] **Step 6: Mark AR-2 driver result**

A driver can be `QUALIFIED_FOR_BENCHMARK` in the report after 20/20; this is not yet a production capability state.

---

### Task 9: Qualify and benchmark AR-3 — select exact interested person

**Files:**
- Modify only if a reproduced root cause requires it:
  - `extension/lib/area-snapshot.js`
  - `extension/content/navigate.js`
  - `extension/tests/area-snapshot.test.mjs`
  - `extension/tests/navigate.test.mjs`
  - controller files/tests.
- Append findings to benchmark note.

**Interfaces:**
- Precondition: operator/controller test setup reaches an `INTERESTED` screen for the exact controlled process.
- Success: exactly one matching interested control selected and exact identity confirmed in `FORM`.

- [ ] **Step 1: Re-run the synthetic ambiguity guards before live work**

```powershell
npm test --prefix extension
node --test devtools/area-restrita/controller/controller.test.mjs
```

Expected: duplicate normalized interested identities produce ambiguity and zero click in both implementations.

- [ ] **Step 2: Execute 20 MV3 AR-3 trials**

One selection per trial.

- [ ] **Step 3: Execute 20 Controller AR-3 trials**

Same gate.

- [ ] **Step 4: Generate the combined AR-2/AR-3 benchmark report**

No identities in report.

- [ ] **Step 5: Root-cause loop for failures**

Same rule as Task 8. Three distinct failed fix attempts for the same class of failure trigger architectural stop, not fix #4.

- [ ] **Step 6: Commit only code justified by reproduced REDs plus sanitized report documentation**

No opportunistic navigation refactor.

---

### Task 10: Select the production navigation architecture and stop Phase 1

**Files:**
- Create: `docs/notes/YYYY-MM-DD-area-restrita-navigation-architecture-decision.md`
- Update: `docs/notes/YYYY-MM-DD-area-restrita-ar2-ar3-benchmark.md`

**Interfaces:**
- Consumes AR-2/AR-3 benchmark evidence.
- Produces exactly one decision:
  - `MV3_NAVIGATION`
  - `LOCAL_CONTROLLER_NAVIGATION`
  - `NO_ARCHITECTURE_QUALIFIED`

- [ ] **Step 1: Verify both benchmark sets use unchanged comparable builds**

If not, invalidate the comparison and rerun the affected set.

- [ ] **Step 2: Apply the spec decision order**

A candidate must first satisfy 20/20 for AR-2 and 20/20 for AR-3.

Among candidates that pass, compare:

1. unclassified states;
2. recovery/intervention count;
3. normal-Chrome viability;
4. packaging reproducibility;
5. fail-closed identity behavior;
6. operational complexity;
7. median/p95 only after correctness criteria.

Do not choose a faster failing implementation.

- [ ] **Step 3: Write the architecture decision record**

Include:

```text
Decision
Build SHA
MV3 AR-2 result
MV3 AR-3 result
Controller AR-2 result
Controller AR-3 result
Median/p95 aggregates
Failure-code aggregates
Packaging implications
Why the losing option was not selected
Known limits
```

- [ ] **Step 4: Run complete offline gates at the Phase 1 fixed point**

```powershell
python -m unittest discover -s tests -p "test_*.py" -q
npm test --prefix extension
node --test app/web/tests/*.test.mjs
node --test devtools/area-restrita/controller/controller.test.mjs
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1
git diff --check
```

Expected: green.

- [ ] **Step 5: Commit the Phase 1 decision**

```powershell
git add docs/notes
git commit -m "docs: select Area Restrita navigation architecture"
```

- [ ] **Step 6: STOP and write Phase 2 plan**

Do **not** implement AR-4, AR-5 or AR-6 from this plan.

Create:

```text
docs/superpowers/plans/YYYY-MM-DD-area-restrita-reliability-reset-phase-2.md
```

using `superpowers:writing-plans`, grounded in the selected architecture:

- if `MV3_NAVIGATION`: compose AR-4/AR-5/AR-6 using the qualified MV3 boundaries and remove/retain controller only as lab evidence;
- if `LOCAL_CONTROLLER_NAVIGATION`: first productionize/package the controller, then build AR-4/AR-5/AR-6 on it;
- if `NO_ARCHITECTURE_QUALIFIED`: return to architectural brainstorming; do not continue implementation.

---

## Phase 1 Acceptance Checklist

- [ ] Runtime source-of-truth recorded from executable/build evidence.
- [ ] Pre-change baseline green.
- [ ] Reliability ledger persists no raw identity.
- [ ] Qualification evaluator enforces same-build 20/20 and intervention reset.
- [ ] UI does not present unqualified `Próximo processo` as a normal feature.
- [ ] AR-1 manual fill path is independent from automatic navigation.
- [ ] AR-1 passes 20/20 real-dev.
- [ ] AR-1 passes 20/20 portable + normal Chrome.
- [ ] AR-1 state is PRODUCTION.
- [ ] Experimental controller has no submit/fill/next-process surface.
- [ ] Controller reuses canonical root structural scripts instead of duplicating selectors.
- [ ] AR-2 benchmark complete for MV3 and Controller.
- [ ] AR-3 benchmark complete for MV3 and Controller.
- [ ] Architecture decision is evidence-based and documented.
- [ ] All offline gates green at the Phase 1 fixed point.
- [ ] No final Complementar Ato action automated.
- [ ] No AR-4/AR-5/AR-6 implementation started.
