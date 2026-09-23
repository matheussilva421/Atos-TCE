# Next Process Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-click “Próximo processo” action to the Mesa and extension side panel that reuses the already-authenticated Área Restrita tab, preserves/re-establishes the current marker, opens the next eligible process, selects the exact interested person when needed, verifies the destination identity, and leaves the target form ready for the operator.

**Architecture:** The Mesa remains the sole owner of “which process is next”; the extension never chooses the next DOM row by position. The backend resolves the next eligible identity from the latest valid Área Restrita scan order, queues one explicit `OPEN_NEXT_ACT` command with current identity + target identity + marker context, and the extension performs only the portal navigation needed to reach that exact target. A mandatory real-portal discovery phase runs before product implementation so return/list/marker behavior is based on observed portal mechanics instead of assumptions.

**Tech Stack:** Python 3 + `unittest` + SQLite backend, vanilla JavaScript MV3 extension, existing loopback Mesa API, vanilla Mesa web UI.

**Spec:** `docs/superpowers/specs/2026-09-23-best-effort-form-filling-design.md`

## Global Constraints

- Before implementation tasks, `codex/mesa-local-refactor` must have been promoted into `main`.
- Promotion is fast-forward/ancestry-safe only; never force-push or rewrite `main`.
- **Phase 0 real-portal discovery is mandatory before Task 1.**
- The extension receives an explicit target identity from the Mesa; it never decides “the next row”.
- The next target must be documentary `PRONTO` and still tied to the relevant Área Restrita scan/marker context.
- No full Area scan is triggered for every Next click; use the stored latest valid scan order for speed.
- No new browser tab is opened for each Next action; reuse the authenticated portal tab/frame flow already open when possible.
- Marker context must be verified and, if the discovery proves it can be safely restored, reselected before target navigation.
- Final target form identity must be reread and exactly match the requested target before reporting success.
- Ambiguous frames/forms/identities stop navigation instead of guessing.
- No submit/finalize capability is added.
- “Próximo processo” only navigates; it does not automatically fill fields in the same click.
- End of queue does not wrap to the beginning.

## Review Focus

1. **Current form disappears after manual submit:** the extension side panel must retain the last confirmed current identity long enough to request Next without choosing a target itself.
2. **Marker drift:** returning from a form lands on a list with a different/no marker — verify or restore the requested marker before opening the target.
3. **Cross-page next target:** the stored next item is on a later portal page — navigation must reach the exact target without using visual row position.
4. **Stale scan target:** the backend selected a PRONTO target that disappeared or changed before click execution — return a coded failure and request a rescan/retry, never open a neighbor.
5. **Multiple portal tabs/frames:** only an exact current/target identity match or a unique verified list context may be used; ambiguity must stop the command.

---

# Pre-execution Gate — Ensure the refactor branch is promoted into main

Run this before Phase 0.

- [ ] **Gate 1: Fetch refs**

```bash
git fetch origin --prune
git rev-parse origin/main
git rev-parse origin/codex/mesa-local-refactor
```

- [ ] **Gate 2: Handle the three allowed ancestry cases**

First test whether promotion already happened:

```bash
git merge-base --is-ancestor origin/codex/mesa-local-refactor origin/main
```

If exit code is 0, `main` already contains the refactor branch. Do not move `main` backward; continue.

If not, test whether `main` is an ancestor of the refactor branch:

```bash
git merge-base --is-ancestor origin/main origin/codex/mesa-local-refactor
```

If exit code is 0, promote by fast-forward:

```bash
git switch main
git pull --ff-only origin main
git merge --ff-only origin/codex/mesa-local-refactor
git push origin main
```

If both ancestry tests fail, stop. The histories diverged and require explicit reconciliation before this plan may continue.

- [ ] **Gate 3: Prove promotion**

```bash
git fetch origin
git merge-base --is-ancestor origin/codex/mesa-local-refactor origin/main
```

Expected: exit code 0.

- [ ] **Gate 4: Create a discovery branch from promoted main**

Before Phase 0:

```bash
git switch -c codex/next-process-navigation-discovery origin/main
```

Phase 0 is read-only with respect to production code; commit only its evidence note on this branch.

After Phase 0 is complete and the note is committed, create the production implementation branch **from the discovery commit**, not directly from bare `main`:

```bash
git switch -c codex/next-process-navigation
```

The implementation branch therefore contains the discovery evidence before Task 1 without requiring a direct documentation commit on `main`.

---

# Phase 0 — Mandatory real Área Restrita discovery

**No production implementation task may start until every Phase 0 checkbox is complete.**

**Files:**
- Create: `docs/notes/2026-09-23-area-restrita-next-navigation-discovery.md`
- Do not modify production files in this phase.

**Output contract:** the note must contain observed evidence, not guesses.

- [ ] **Phase 0.1: Establish an authenticated test path**

Open the current extension build and Mesa, authenticate to the real Área Restrita, select the same marker used by the normal scan flow, and choose a test sequence with at least:
- current process A;
- next eligible process B on the same page if available;
- a process C requiring interested-person selection if available;
- a cross-page target if the marker has more than one page.

If login is required, pause only for the operator to authenticate, then continue the discovery in the same execution session.

- [ ] **Phase 0.2: Record frame and screen transitions**

Using current extension diagnostics/DevTools/CDP without adding product behavior, record for:

```text
list -> act open -> interested -> form
form -> manual Complementar Ato / return -> resulting screen
form -> native back/list control -> resulting screen
```

For each transition record:
- top-level tab URL;
- frame URLs/roles visible to the existing router;
- whether frame IDs survive or are recreated;
- whether a sibling frame/tab is opened;
- time until the next stable screen is readable.

- [ ] **Phase 0.3: Determine the safest fastest return strategy**

Evaluate in this order:

1. **Native portal return/list control** — preferred if it returns to the correct list and retains marker context.
2. **Browser history/back** — acceptable only if observed to restore the correct list and marker deterministically.
3. **Direct portal URL/navigation** — acceptable only if discovery proves the route is stable, identity-safe, and preserves/re-establishes marker context without relying on hidden session state.

Record exactly one chosen strategy as:

```text
navigation_strategy: native_control
```

or:

```text
navigation_strategy: history_back
```

or:

```text
navigation_strategy: direct_route
```

Also record the exact observed control/URL evidence required to implement that strategy. Do not invent a selector that was not observed.

- [ ] **Phase 0.4: Map marker behavior**

Record:
- where marker label/value appears in the list DOM;
- whether current `SCAN_PAGE` snapshot reports it correctly;
- whether return from form retains it;
- if not retained, which exact control can restore it;
- whether restoring marker reloads the list/frame;
- how to detect the list is stable after marker change.

The note must state one of:

```text
marker_restore: not_needed
```

or:

```text
marker_restore: required
marker_control: <observed DOM/control description>
```

The actual observed selector/control description belongs in the note; the plan does not pre-invent it.

- [ ] **Phase 0.5: Verify stored scan order against portal order**

Compare the latest `area_scan_items` sequence with the visible portal order across at least two adjacent entries and one page boundary when available.

Record:
- whether insertion order preserves portal order;
- whether pagination appends rows in the same order;
- whether current process A followed by process B in `area_scan_items` matches the portal.

If it does not, stop this plan and revise the spec/selection strategy before Task 1; do not implement “next” using process-key sort.

- [ ] **Phase 0.6: Measure the manual baseline**

Record three manual click-to-form-ready timings for moving from one completed/reviewed act to the next exact process. The product should avoid extra full scans/reloads and minimize extension overhead relative to this baseline.

No hard millisecond target is invented before observing the portal; record the baseline and use it in final validation.

- [ ] **Phase 0.7: Write and commit discovery note**

The note must include:
- chosen navigation strategy;
- frame/screen sequence;
- exact return mechanism evidence;
- marker persistence/restore behavior;
- interested-radio behavior;
- scan-order verification;
- page-boundary behavior;
- observed error/ambiguity cases;
- manual timing baseline;
- concrete test fixtures/selectors needed by Tasks 3–4.

Commit:

```bash
git add docs/notes/2026-09-23-area-restrita-next-navigation-discovery.md
git commit -m "docs: map Area Restrita next-process navigation"
```

**Gate:** Task 1 starts only after this commit exists and contains all evidence above.

---

### Task 1: Resolve the next eligible process from the current scan order

**Files:**
- Create: `app/area_restrita/navigation_service.py`
- Create: `tests/test_navigation_service.py`
- Modify: `app/area_restrita/__init__.py`
- Modify if a focused query is needed: `app/core/store.py`, `tests/test_store.py`

**Interfaces:**
- Produces: `NavigationService.next_target(*, process_id: int | None = None, identity: Mapping[str, Any] | None = None) -> dict[str, Any] | None`
- Result includes `current_identity`, `target_identity`, `scan_id`, `source_scope`, and `marker: {"label": ..., "value": ...}`.
- `None` means end of queue.

- [ ] **Step 1: Add RED selection tests**

Build one scan with ordered items A, B, C, D where:
- A current;
- B process status `PRONTO`;
- C not `PRONTO`;
- D `PRONTO`.

Assert:
- from A => B;
- from B => D;
- from D => no target/end-of-queue;
- target comes from scan item order, not `process_key` lexical order;
- a process not present in its referenced scan is refused;
- identity lookup maps to exactly one current process or refuses ambiguity.

Example core assertion:

```python
target = service.next_target(process_id=current_id)
self.assertEqual(target["target_identity"]["processKey"], "portal-order-second")
self.assertEqual(target["scan_id"], scan_id)
self.assertEqual(target["marker"]["value"], "observed-marker-value")
```

- [ ] **Step 2: Run RED tests**

```bash
python -m unittest tests.test_navigation_service -v
```

Expected: module/service absent.

- [ ] **Step 3: Implement scan-order selection**

Use the current process's `last_area_scan_id` and that scan's `items` in stored order. Iterate only subsequent items; choose the first whose live process record is:
- `status == "PRONTO"`;
- still marked as needing complementation/currently eligible according to existing process data.

Do not wrap around.

- [ ] **Step 4: Return marker context from the scan**

Use `area_scans.marker_label` and `marker_value`, not a reconstructed label from process text.

- [ ] **Step 5: Run tests**

```bash
python -m unittest tests.test_navigation_service tests.test_store -v
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add app/area_restrita/navigation_service.py app/area_restrita/__init__.py tests/test_navigation_service.py app/core/store.py tests/test_store.py
git commit -m "feat: resolve next process from portal scan order"
```

Only stage store files if the implementation adds a focused store query.

---

### Task 2: Add one backend request that both Mesa and side panel can use

**Files:**
- Modify: `app/api/server.py`
- Modify: `tests/test_api_server.py`
- Modify: `extension/lib/api.js`
- Modify: `extension/tests/api.test.mjs`

**Interfaces:**
- Add: `POST /api/v1/portal/next-act`
- Body accepts either:
  - Mesa: `{"process_id": 123}`;
  - extension side panel: `{"identity": {"processKey": "...", "interestedNormalized": "..."}}`.
- Server resolves target and queues `OPEN_NEXT_ACT`.
- Response:
```json
{
  "ok": true,
  "command_id": 321,
  "target_process_id": 456,
  "target_identity": {
    "processKey": "...",
    "interestedNormalized": "..."
  }
}
```
- End of queue response uses HTTP 200 with `{"ok": true, "end_of_queue": true}`.

- [ ] **Step 1: Add RED API authentication/selection tests**

Test:
- Mesa session may call with `process_id`;
- extension bearer may call with current `identity`;
- no credential => rejected;
- ambiguous/unknown current identity => 409;
- end of queue => explicit non-error payload;
- server payload for queued command contains exact current identity, target identity and marker context.

- [ ] **Step 2: Run RED backend tests**

```bash
python -m unittest tests.test_api_server tests.test_navigation_service -v
```

- [ ] **Step 3: Wire `NavigationService` into the server**

Instantiate/reuse one service from the Mesa application object. Add the mixed-auth route using the same established credential pattern as `/api/v1/portal/manual-form`.

Do not allow the extension request body to supply `target_identity`; target selection belongs to the Mesa.

- [ ] **Step 4: Queue `OPEN_NEXT_ACT`**

Add the command to the backend allowlist and queue through the existing extension command table. Payload:

```json
{
  "current_identity": {"processKey": "...", "interestedNormalized": "..."},
  "target_identity": {"processKey": "...", "interestedNormalized": "..."},
  "context": {
    "scan_id": 123,
    "source_scope": "...",
    "marker": {"label": "...", "value": "..."}
  }
}
```

- [ ] **Step 5: Add extension API client method**

In `createApi()`, add:

```javascript
async requestNextAct(currentIdentity) {
  const response = await authenticatedRequest("/api/v1/portal/next-act", {
    method: "POST",
    body: { identity: currentIdentity },
  });
  return {
    ok: response.ok,
    status: response.status,
    payload: response.payload,
    error: response.ok ? null : response.payload?.detail ?? response.error ?? "request_failed",
  };
}
```

- [ ] **Step 6: Run API tests**

```bash
python -m unittest tests.test_api_server tests.test_navigation_service -v
node --test extension/tests/api.test.mjs
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
git add app/api/server.py tests/test_api_server.py extension/lib/api.js extension/tests/api.test.mjs
git commit -m "api: queue next-process navigation"
```

---

### Task 3: Add the explicit OPEN_NEXT_ACT protocol and router orchestration

**Files:**
- Modify: `extension/lib/protocol.js`
- Modify: `extension/background/router.js`
- Modify: `extension/tests/protocol.test.mjs`
- Modify: `extension/tests/router.test.mjs`

**Interfaces:**
- Add command type: `OPEN_NEXT_ACT`.
- Add internal message types needed by the observed strategy:
  - `RETURN_TO_LIST`;
  - `ENSURE_MARKER` only if Phase 0 says marker restore is required.
- Produces router result:
```json
{
  "ok": true,
  "action": "next_act_ready",
  "identity": {"processKey": "...", "interestedNormalized": "..."},
  "screen": "form"
}
```

- [ ] **Step 1: Add RED protocol tests**

Assert:
- `OPEN_NEXT_ACT` is supported;
- forbidden submit/finalize names are still absent;
- internal return/marker messages are not backend command types.

- [ ] **Step 2: Add RED router orchestration tests**

With injected doubles, test:
1. current form exact match -> return to list -> marker already correct -> open target row -> select target interested -> target form read -> success;
2. same-page target;
3. target appears after list pagination/portal transition;
4. return lands on wrong marker -> marker restore is called only when Phase 0 requires it;
5. target disappears -> `TARGET_NOT_FOUND`, no neighbor selected;
6. final form identity mismatch -> failure;
7. multiple target form frames -> `FORM_AMBIGUOUS`;
8. final target tab becomes active.

- [ ] **Step 3: Run RED extension tests**

```bash
node --test extension/tests/protocol.test.mjs extension/tests/router.test.mjs
```

- [ ] **Step 4: Implement command dispatch**

Extend `executeCommand()` with `COMMAND_TYPES.OPEN_NEXT_ACT` and a dedicated `openNextAct(payload)` collaborator.

- [ ] **Step 5: Implement the orchestration loop without a full scan**

Algorithm:

```text
verify current identity when current form is still present
-> return to stable list using Phase 0 strategy
-> read list snapshot
-> verify expected marker
-> restore marker only if required/observed-safe
-> repeatedly invoke existing exact OPEN_ACT navigation for target
-> allow row-open and interested-selection transitions
-> locate exact target form
-> reread target identity
-> activate target tab
-> return next_act_ready
```

Do not run `SCAN_AREA` over every page to select a target; the backend already selected it.

- [ ] **Step 6: Bound retries**

Use short retry/poll loops around frame recreation and target form appearance. Reuse current router timing injection so tests do not sleep. Do not add an unbounded loop.

- [ ] **Step 7: Run router/protocol tests**

```bash
node --test extension/tests/protocol.test.mjs extension/tests/router.test.mjs
```

Expected: green.

- [ ] **Step 8: Commit**

```bash
git add extension/lib/protocol.js extension/background/router.js extension/tests/protocol.test.mjs extension/tests/router.test.mjs
git commit -m "feat: orchestrate next-act navigation"
```

---

### Task 4: Implement return-to-list and marker restore from observed portal behavior

**Files:**
- Modify: `extension/content/navigate.js`
- Modify: `extension/tests/navigate.test.mjs`
- Modify if fixture support is needed: `extension/tests/fake-dom.mjs`

**Interfaces:**
- Produces: `TCENavigate.returnToList({documentRef, identity, deps})`
- Produces, only when Phase 0 recorded `marker_restore: required`: `TCENavigate.ensureMarker({documentRef, marker, deps})`
- Both functions return coded results and never guess.

- [ ] **Step 1: Translate Phase 0 evidence into deterministic fixtures**

Create fixture controls matching the exact observed return mechanism and, if needed, marker control behavior. Name tests after the observed strategy, for example:
- `native return control returns to list`;
- `marker select chooses exact marker value`.

Do not create a generic selector fallback chain.

- [ ] **Step 2: Add RED navigation tests**

Mandatory:
- current form identity must match before clicking a form-local return control;
- wrong current identity => no click;
- return control missing => coded failure;
- exact marker already active => no rewrite;
- wrong marker + known restore control => choose exact marker value;
- requested marker option missing => coded failure, no arbitrary first option.

- [ ] **Step 3: Run RED test**

```bash
node --test extension/tests/navigate.test.mjs
```

- [ ] **Step 4: Implement exactly the Phase 0 strategy**

If `navigation_strategy: native_control`, click only the observed native return control.

If `history_back`, use the observed safe history path and verify resulting role/marker before proceeding.

If `direct_route`, use only the exact observed deterministic route and still reread role/marker after navigation.

No implementation may contain all three speculative strategies as fallbacks; ship the one proven by Phase 0.

- [ ] **Step 5: Implement marker restore only if the discovery requires it**

If Phase 0 says `marker_restore: not_needed`, do not add marker mutation code. Router still verifies marker.

If required, select exact raw marker `value` observed in scan context, dispatch the same events the portal requires, then wait for a stable list snapshot before opening target.

- [ ] **Step 6: Run navigation suite**

```bash
node --test extension/tests/navigate.test.mjs extension/tests/router.test.mjs
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
git add extension/content/navigate.js extension/tests/navigate.test.mjs extension/tests/fake-dom.mjs
git commit -m "feat: navigate back to portal queue safely"
```

Only stage `fake-dom.mjs` if changed.

---

### Task 5: Add one-click Next to the extension side panel

**Files:**
- Modify: `extension/sidepanel/panel.html`
- Modify: `extension/sidepanel/panel.js`
- Modify: `extension/sidepanel/state.js` if state helpers are useful
- Modify: `extension/tests/sidepanel-wiring.test.mjs`
- Modify: `extension/tests/sidepanel-state.test.mjs`

**Interfaces:**
- Side panel sends only the **current** confirmed identity to Mesa.
- It never computes target identity.
- Retains `lastConfirmedFormIdentity` in panel memory while the panel is open so Next remains usable immediately after the portal leaves the just-submitted form.

- [ ] **Step 1: Add RED wiring/state tests**

Assert:
- a `Próximo processo →` button exists;
- it is disabled before any current/last-confirmed form identity exists;
- reading a current form stores the identity;
- temporary disappearance of the form does not immediately erase the last confirmed identity;
- click calls `requestNextAct(lastConfirmedFormIdentity)`;
- `end_of_queue` renders “Fim da fila”;
- the side panel never submits target identity.

- [ ] **Step 2: Run RED sidepanel tests**

```bash
node --test extension/tests/sidepanel-state.test.mjs extension/tests/sidepanel-wiring.test.mjs
```

- [ ] **Step 3: Add compact UI**

Add one secondary/arrow-style button near the current-form action:

```text
Preencher formulário atual
Próximo processo →
```

Feedback states:
- `Abrindo próximo…`
- `Marcador confirmado…` only if router/API exposes that intermediate state locally; otherwise do not invent progress.
- `Formulário pronto: <processo>`
- `Fim da fila`
- coded error message on navigation failure.

- [ ] **Step 4: Poll the active/current form locally for completion**

After backend queues the command and returns `target_identity`, the side panel can use existing `READ_CURRENT_FORM` periodically until:
- target identity appears => success;
- end/timeout => show retry guidance.

Do not require a new extension-authenticated command-status endpoint solely for this UI.

- [ ] **Step 5: Run sidepanel tests**

```bash
node --test extension/tests/sidepanel-state.test.mjs extension/tests/sidepanel-wiring.test.mjs
npm test --prefix extension
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add extension/sidepanel/panel.html extension/sidepanel/panel.js extension/sidepanel/state.js extension/tests/sidepanel-state.test.mjs extension/tests/sidepanel-wiring.test.mjs
git commit -m "ui: add next-process action to extension"
```

Only stage `state.js` if changed.

---

### Task 6: Add one-click Next to the Mesa

**Files:**
- Modify: `app/web/app.js`
- Modify: `app/web/index.html`
- Modify: `app/web/app.css`
- Modify: `app/web/tests/ui-wiring.test.mjs`
- Modify: `tests/test_api_server.py` if response shape gets refined.

**Interfaces:**
- Mesa calls `POST /api/v1/portal/next-act` with selected/current `process_id`.
- Mesa may poll existing `GET /api/v1/extension/commands/{command_id}` because it has Mesa session auth.
- On success, select target process in Mesa and show “Formulário pronto”.

- [ ] **Step 1: Add RED UI wiring test**

Assert source/DOM has:
- `Próximo processo →` control;
- click handler posts current selected process id;
- end-of-queue handling;
- command status polling or equivalent completion feedback;
- selection moves to returned target process;
- no automatic fill call after navigation success.

- [ ] **Step 2: Run RED web tests**

```bash
node --test app/web/tests/*.test.mjs
```

- [ ] **Step 3: Add Mesa action**

Behavior:
1. disable button during request;
2. POST current process id;
3. if end-of-queue, show `Fim da fila`;
4. otherwise show `Abrindo próximo…`;
5. poll command status until completed/failed;
6. on success, select `target_process_id` in Mesa and show `Formulário pronto`;
7. do not trigger `/fill` automatically.

- [ ] **Step 4: Keep action lightweight**

Do not refresh the entire Area scan or process acquisition pipeline. Refresh only process detail/list state needed to select/render the target.

- [ ] **Step 5: Run web/API tests**

```bash
node --test app/web/tests/*.test.mjs
python -m unittest tests.test_api_server tests.test_web_suite -v
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add app/web/app.js app/web/index.html app/web/app.css app/web/tests/ui-wiring.test.mjs tests/test_api_server.py
git commit -m "ui: add next-process action to Mesa"
```

Only stage API test file if changed.

---

### Task 7: Harden cross-page, stale-target, ambiguity and focus behavior

**Files:**
- Modify: `tests/test_navigation_service.py`
- Modify: `extension/tests/router.test.mjs`
- Modify: `extension/tests/navigate.test.mjs`

**Interfaces:**
- No new production interface unless a test exposes a missing coded failure.

- [ ] **Step 1: Add the five Review Focus tests**

Pin:
1. last-confirmed current identity after form disappears;
2. marker drift/restore;
3. cross-page target;
4. stale target disappears;
5. multiple portal frames.

For stale target, expected behavior is a coded failure such as `TARGET_NOT_FOUND` with no alternative row clicked.

- [ ] **Step 2: Add end-of-marker/end-of-queue test**

No eligible item after current => backend returns `end_of_queue`; extension receives no navigation command.

- [ ] **Step 3: Add focus test**

After exact target form is located, assert router calls `chrome.tabs.update(targetTabId, {active: true})` or the equivalent observed focus action supported by the existing browser API.

- [ ] **Step 4: Run focused suites**

```bash
python -m unittest tests.test_navigation_service tests.test_api_server -v
node --test extension/tests/router.test.mjs extension/tests/navigate.test.mjs extension/tests/sidepanel-wiring.test.mjs
```

Expected: green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_navigation_service.py extension/tests/router.test.mjs extension/tests/navigate.test.mjs extension/tests/sidepanel-wiring.test.mjs
git commit -m "test: harden next-process navigation"
```

---

### Task 8: Validate on the real portal and compare against manual timing

**Files:**
- Create: `docs/notes/2026-09-23-next-process-navigation-validation.md`

**Interfaces:**
- No new runtime interface.

- [ ] **Step 1: Run complete automated gates**

```bash
python -m unittest discover -s tests -p "test_*.py" -q
npm test --prefix extension
node --test app/web/tests/*.test.mjs
powershell -ExecutionPolicy Bypass -File .\verify-project.ps1
git diff --check
```

Expected: all green.

- [ ] **Step 2: Real-portal scenario matrix**

Validate:
1. next target same list page;
2. next target across page boundary;
3. target requiring interested-person radio selection;
4. marker retained;
5. marker restore path if Phase 0 said required;
6. manual submit caused form to disappear before Next click;
7. stale/removed target;
8. end of queue.

For each record:
- current identity;
- target identity;
- scan id + marker;
- elapsed click-to-form-ready time;
- number of portal page/frame transitions;
- whether a full scan/reload occurred;
- final identity reread result.

- [ ] **Step 3: Compare timing with Phase 0 manual baseline**

Acceptance:
- no extra full Area scan per click;
- no new portal tab per click unless the portal itself necessarily creates its normal sibling form frame/tab;
- automation overhead does not add avoidable fixed waits;
- if automated median is materially slower than manual baseline, profile the slow poll/retry step and reduce only unnecessary extension delay without weakening identity checks.

- [ ] **Step 4: Verify workflow separation**

Confirm:
- Next click navigates only;
- form fields are unchanged until operator separately invokes fill;
- final Complementar Ato remains manual.

- [ ] **Step 5: Write validation note**

Include:
- discovery strategy actually shipped;
- commit SHA;
- automated test results;
- scenario matrix;
- manual vs automated timing;
- observed portal limitations;
- confirmation of exact target identity and marker behavior.

- [ ] **Step 6: Commit**

```bash
git add docs/notes/2026-09-23-next-process-navigation-validation.md
git commit -m "docs: validate next-process navigation"
```

---

## Final Acceptance Gate

```text
[ ] codex/mesa-local-refactor is contained in main before implementation
[ ] Phase 0 real-portal discovery note exists before production navigation code
[ ] next target is chosen by Mesa from stored portal scan order
[ ] extension never chooses a target by DOM row position
[ ] no full Area rescan runs on every Next click
[ ] authenticated portal tab is reused
[ ] marker is verified and restored only by observed-safe mechanism
[ ] exact interested person is selected
[ ] final form identity is reread and matches target
[ ] same-page and cross-page next targets work
[ ] stale target and ambiguous frames fail safely
[ ] side panel keeps last confirmed current identity through a short form disappearance
[ ] Mesa and extension both expose one-click Next
[ ] Next does not auto-fill
[ ] no submit/finalize capability was added
[ ] real-portal timing is documented against manual baseline
[ ] Python, extension, web and project verification gates are green
```
