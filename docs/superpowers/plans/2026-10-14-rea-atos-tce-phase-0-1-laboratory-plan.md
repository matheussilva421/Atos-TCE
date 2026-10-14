# Atos-TCE + REA — Phase 0–1 Laboratory & Evidence Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile the Atos-TCE baseline and deliver a synthetic, isolated REA investigation laboratory with a fail-closed Evidence Gateway and exclusive Chrome control, without accessing the real Área Restrita or changing the product runtime.

**Architecture:** Keep the root `app/`, `extension/`, `packaging/` and qualification ledger untouched in this plan. Build development-only Python tooling under `scripts/portal-lab/` using standard-library typed projections and synthetic browser fixtures; REA runs as a pinned, isolated subprocess whose raw output never reaches the Codex context. A proven security boundary is a prerequisite for **any later real-portal capture**, not something that can be claimed from sanitization tests alone.

**Tech Stack:** Python 3 standard library + unittest, Windows/PowerShell, Node.js compatible with REA (`^22.19.0 || ^24.11.0 || >=26.0.0`), REA `rea-agents@6.5.0` (pin and verify on execution), Chrome/Chromium fixture launch, Git/GitHub.

**Spec:** `docs/superpowers/specs/2026-10-14-atos-tce-rea-reliability-architecture-design.md` (D1–D10, approved 2026-10-14). Also read `docs/superpowers/specs/2026-09-30-area-restrita-reliability-reset-design.md`, `docs/superpowers/specs/2026-10-06-modo-diagnostico-design.md`, and `AGENTS.md`.

## Global Constraints

- **This is a plan for human review, not execution authorization.** Do not install dependencies, edit code, run the browser or change the portal before plan approval.
- This plan covers **Phase 0 + Phase 1 only**. No AR-1/2/3 repairs or qualification, MV3/Controller production integration, Navigation Adapter implementation, package updates, SQLite migrations or updater/rollback implementation.
- **No real portal access in this phase**: no TCE origin, authenticated Chrome profile, private DOM, real process data, cookies or operational credentials. Scenario scope is synthetic localhost only.
- Login is human. Never automate credentials, submission, signature, tramitação or **Complementar Ato**. Forbidden commands: SUBMIT/SEND/AUTO_SUBMIT/COMPLEMENT_ACT/FINALIZE.
- Maintain D1 REA+MV3+Controller (candidate only); D2 autonomous authorized investigation; D3 deterministic states; D4 evidence reconciliation; D5 exclusive Chrome QA; D6 gateway pre-egress; D7 equivalent benchmark; D8 single active controller/manual fallback; D9 transactional updater as separate later project; D10 worktree/TDD/review gates.
- Keep production sources under root `app/`, `extension/`, `packaging/`; do not fix `work/tce-extractor/` or modify current `DiagnosticRecorder`, `ReliabilityRecorder` and capabilities.
- All new lab tool files are in `scripts/portal-lab/*.py`, which the current `.gitignore` explicitly permits; captures under `tmp/portal-lab/` are ignored and **must not be staged**.
- REA is **not** a security sanitizer or origin firewall. Its default network capture can include URL and content; `capture.network.request_body`, `response_body`, and `header_values` must stay false. No direct REA MCP registration into the agent handling real captures.
- Never claim a security boundary if Codex has unrestricted shell/filesystem permissions under the **same OS principal** as the raw-capture process. Without a separately enforced principal/sandbox and tested denied access, leave `real_capture_enabled=false` and stop at synthetic validation.
- No public/versioned PII, tokens, bodies, DOM, screenshots or private files; identity HMAC uses a local key outside Git. Retention of `DiagnosticRecorder` remains unchanged.
- For future capabilities only: `QUALIFIED` requires 20/20 **real consecutive** same-build runs; `PRODUCTION` requires another 20/20 on clean portable/normal Chrome. Offline green and recovered runs never count; final click remains human.

## Review Focus

1. **REA capture leaks sensitive data via stdout/stderr or exceptions** — subprocess wrapper never forwards raw data or exception text to Codex; test in Task 4.
2. **A malicious synthetic scenario navigates off localhost, via redirect or injected action** — reject input and prove network confinement outside REA's own schema; tests in Tasks 1 and 5. If confinement cannot be demonstrated, fail closed.
3. **A stale/expired lease or two agent processes mutate one browser** — only one operation wins, old fencing token loses, ambiguous operation blocks takeover; tests in Task 3.
4. **Model has a direct shell path to raw files despite a 'sanitized' tool** — cross-principal denied-access probe must be demonstrated before real mode; tests in Task 6, default disabled.
5. **A browser attach misses early events or a synthetic page contains old hidden form** — report evidence completeness accurately and never equate a hidden old form with active FORM; tests in Task 5.

---

## 0. File structure and interfaces

| File | Responsibility |
|---|---|
| `docs/notes/2026-10-14-rea-phase-0-baseline.md` (create) | Source, branch, build and existing test gates; **no real qualification claims** |
| `scripts/portal-lab/rea_policy.py` (create) | Strict scenario schema/allowlist; synthetic launch-only, loopback origin, allowed action vocabulary |
| `scripts/portal-lab/rea_gateway.py` (create) | Pure allowlisted, schema-checked projection of REA evidence; no raw text, URL values or dumps |
| `scripts/portal-lab/rea_coordinator.py` (create) | SQLite-backed atomic lease/fencing for lab browser mutations; reconciliation flag |
| `scripts/portal-lab/rea_runner.py` (create) | Pinned REA CLI subprocess: write raw to restricted spool; return projected object only |
| `scripts/portal-lab/rea_fixture_server.py` (create) | Local synthetic pages demonstrating frames, hidden stale form, transitions, denial/login states |
| `scripts/portal-lab/rea_lab_smoke.py` (create) | Explicit synthetic-only integration command, gated on pinned REA/Chrome availability |
| `scripts/portal-lab/rea_isolation.py` (create) | External boundary attestation and denied-access test; never self-authorize real mode |
| `tests/test_rea_lab_policy.py` (create) | Scenario validation and off-origin input cases |
| `tests/test_rea_lab_gateway.py` (create) | Projection, redaction, completeness and adversarial sentinel cases |
| `tests/test_rea_lab_coordinator.py` (create) | Lease/fencing/collision/crash-restart tests |
| `tests/test_rea_lab_runner.py` (create) | Subprocess/stdout/error insulation tests using fake executable |
| `tests/test_rea_lab_isolation.py` (create) | Independent-principal checks, security mode default and blocked real-mode cases |
| `tests/test_rea_lab_smoke.py` (create) | Fake-browser fixture integration, no portal traffic and synthetic-state matrix |
| `tests/test_devtools_runtime_boundary.py` (modify) | Lab sources never enter production app/extension; raw ignored |
| `tests/test_packaging_contract.py` (modify) | Reject all new lab files in ZIP |
| `docs/notes/YYYY-MM-DD-rea-phase-0-1-handoff.md` (create at execution) | Test receipts, isolation verdict, pinned REA version, scope, SHA, risks |

**Canonical typed interfaces for all tasks:** Python `dict[str, object]` for fixture/scenario/evidence payloads, an integer `fencing_token`, opaque `operation_id`, explicit result `status` (`PASS`, `BLOCKED`, `INCOMPLETE`); no free-form exception string in exported objects. Prohibit private types or arbitrary serialized values at the gateway. Keep source modules small; never duplicate the app's form reader.

### Task 0: Reconcile source, baseline and isolated worktree

**Files:** Create `docs/notes/2026-10-14-rea-phase-0-baseline.md`; read `AGENTS.md`, `START.cmd`, `packaging/build-portable.ps1`, reliability and diagnostics specs.

**Interfaces:**
- Consumes: approved architecture spec commit, existing `main`, review PR #7, `git status`.
- Produces: baseline note with exact checkout SHA, command outputs, blocked/skipped gates and known status.

- [ ] **Step 1: Check repository and worktree state read-only.** Run `git fetch origin --prune`; `git branch --show-current`; `git status --short`; `git rev-parse HEAD`; `git worktree list --porcelain`. Preserve any existing uncommitted files. Never reset, clean or force checkout.
- [ ] **Step 2: Create an isolated implementation worktree** from the approved architecture branch using `superpowers:using-git-worktrees` and an unused `codex/rea-lab-phase-0-1` name, only after the plan is approved. If that branch name already exists, inspect rather than overwrite.
- [ ] **Step 3: Run baseline gates**, capturing exit code and test totals: `python -m unittest discover -s tests -p 'test_*.py' -q`; `npm test --prefix extension`; `node --test app/web/tests/*.test.mjs`; `python -m unittest tests.test_packaging_contract tests.test_devtools_runtime_boundary -v`; `git diff --check`. Legacy verifier only if current project runbook requires it; failure must be recorded, not silently waived.
- [ ] **Step 4: Record receipt** in the baseline note: source of truth, branch/HEAD, spec commit, unchanged runtime, actual gates, known AR-1 status **as read**, not inferred from dated handoffs.
- [ ] **Step 5: Commit only baseline note**; run `git status --short` to check for accidental changes.

### Task 1: Restrict REA scenario input to synthetic fixtures

**Files:** Create `scripts/portal-lab/rea_policy.py`; test `tests/test_rea_lab_policy.py`.

**Interfaces:**
- Produces `validate_synthetic_scenario(payload: dict[str, object]) -> dict[str, object]` raising `ScenarioRejected(code: str)`. Returns a canonical, deep-copied allowed input; no unknown keys or user-supplied capture-body flags.
- Future consumer: Task 4 runner. Defines `synthetic_origin` exactly as `http://127.0.0.1:<allocated_port>`; launch mode only. A fixed set of read-only/wait and synthetic click actions is allowed; never execute script evaluation, arbitrary URL navigation, file upload, storage/cookie seeding or real portal actions.

- [ ] **Step 1: Write RED unit tests** `test_rejects_connect_mode`, `test_rejects_public_and_tce_origins`, `test_rejects_arbitrary_redirect_action`, `test_rejects_network_body_header_capture`, `test_rejects_unknown_action_and_storage_seed`, `test_accepts_strict_local_fixture` with explicit `assertRaisesRegex(ScenarioRejected, "SCOPE_REJECTED")` for invalid cases.
- [ ] **Step 2: Run RED:** `python -m unittest tests.test_rea_lab_policy -v`. Expected: missing policy API/test assertions fail, not a green skip.
- [ ] **Step 3: Implement policy** and typed allowlist, validate strings and nested objects. Reject `launch` start URLs outside fixed loopback origin and any action that could navigate to a different URL; preserve only capture subsets `url`, `dom`, `accessibility`, `frame`, `page-errors` when needed, with DOM raw remaining local only. **No claim of redirect confinement from input validation alone.**
- [ ] **Step 4: Run GREEN** with the same unittest command; expected 0 failures.
- [ ] **Step 5: Commit** `rea_policy.py` and its test with `test(rea-lab): constrain synthetic REA scenarios`.

### Task 2: Build strict pre-egress Evidence Gateway

**Files:** Create `scripts/portal-lab/rea_gateway.py`; test `tests/test_rea_lab_gateway.py`.

**Interfaces:**
- Produces `project_evidence(raw: dict[str, object], *, run_id: str, controller: str = "rea") -> dict[str, object]` and `EvidenceRejected(code: str)`. Only fixed, typed output: `schema_version=1`, `run_id`, `controller`, `status`, `state_before`, `state_after`, `visible_frame_count`, `hidden_form_count`, `elapsed_ms`, `capture_complete`, `limitations` (enum codes only). Do not serialize raw evidence through `repr` or text.
- Consumes REA metadata locally; shared status enum `PASS | BLOCKED | INCOMPLETE`. No arbitrary URL, DOM node text, names, bodies, identifiers, error messages or secret strings in output.
- `capture_complete=true` only if all requested structural observations are present and no pre-attach/worker/popup coverage gaps. A `not_requested` artifact is not a negative observation.

- [ ] **Step 1: Write RED tests** `test_raw_dom_text_and_names_never_egress`, `test_cpf_token_url_and_base64_sentinel_never_egress`, `test_nested_unknown_keys_are_dropped`, `test_missing_requested_artifact_is_incomplete`, `test_pre_attach_gap_is_incomplete`, `test_wrong_types_fail_closed`. Assert `json.dumps(projected)` contains no sentinel and keys are exactly allowlisted.
- [ ] **Step 2: Run RED:** `python -m unittest tests.test_rea_lab_gateway -v`. Expected: implementation absent/fails.
- [ ] **Step 3: Implement projection** using explicit field constructors, bounded integers/enums, no generic `dict.update(raw)`. Extract structural facts from allowed canonical fields only; if needed text would require parsing, do not export text and mark `INCOMPLETE` rather than inventing FORM.
- [ ] **Step 4: Run GREEN**; expected 0 failures. Include output-schema stability test against extra REA fields.
- [ ] **Step 5: Commit** gateway + test.

### Task 3: Exclusive Chrome lease coordinator and fencing

**Files:** Create `scripts/portal-lab/rea_coordinator.py`; test `tests/test_rea_lab_coordinator.py`.

**Interfaces:**
- Produces `LeaseCoordinator(db_path: Path)` with `acquire(session_id: str, owner: str, target_ref: str, ttl_seconds: int) -> dict[str, object]`, `require(operation_id: str, fencing_token: int) -> None`, `mark_uncertain(operation_id: str) -> None`, `release(operation_id: str, fencing_token: int, *, reconciled: bool) -> None`. May raise `LeaseRejected(code: str)`.
- SQLite transaction `BEGIN IMMEDIATE` ensures lease singleton; token monotonically increments across owner and process restarts; an uncertain lease blocks replacement until explicit reconciled state. No browser mutation occurs in this module.

- [ ] **Step 1: Write RED tests** `test_two_owners_one_lease`, `test_stale_fencing_token_rejected`, `test_expiry_does_not_release_uncertain_operation`, `test_restart_preserves_ownership`, `test_parallel_acquire_has_single_winner`. Use threads/processes and temp SQLite; ensure no wall-clock waiting by injecting test clock if needed.
- [ ] **Step 2: Run RED:** `python -m unittest tests.test_rea_lab_coordinator -v`.
- [ ] **Step 3: Implement** the specified API; return opaque session/operation refs, never identify portal process values. The runner checks `require` directly before each mutation and after reconnection.
- [ ] **Step 4: Run GREEN**; test crash/restart and stale tokens on Windows, expected 0 failures.
- [ ] **Step 5: Commit** coordinator + test.

### Task 4: Pinned REA subprocess runner with zero raw stdout

**Files:** Create `scripts/portal-lab/rea_runner.py`; test `tests/test_rea_lab_runner.py`.

**Interfaces:**
- Produces `run_synthetic_case(scenario: dict[str, object], *, runner_argv: list[str], work_root: Path, coordinator: LeaseCoordinator) -> dict[str, object]`.
- Consumes `validate_synthetic_scenario`, `project_evidence`, and active lease; runner_argv is an exact **administrator-reviewed pinned executable invocation**, never constructed from user strings. REA pinned to `rea-agents@6.5.0`; Node runtime must satisfy engine requirement.
- Stores temporary capture and stderr only in an operator-controlled spool outside agent workspace; stdout from the subprocess is redirected there, never printed by the Python wrapper. Exit status exposed as code only; stderr never logged verbatim. Bounded runtime and file sizes. On subprocess failure, return `{"status":"BLOCKED","code":"REA_EXECUTION_FAILED"}` and no raw text.

- [ ] **Step 1: Write RED tests** `test_fake_rea_secret_stdout_not_printed`, `test_fake_rea_secret_stderr_not_printed`, `test_exception_message_is_not_exported`, `test_wrong_version_is_blocked`, `test_failed_projection_fails_closed`, `test_lease_denied_prevents_spawn`. Use fake executable with secret markers, capture all parent stdout/stderr and assert absence.
- [ ] **Step 2: Run RED:** `python -m unittest tests.test_rea_lab_runner -v`.
- [ ] **Step 3: Implement subprocess and spool** without shell expansion; process environment allowlist; startup version check; strict timeout; use Gateway on parsed JSON before constructing any exposed result. No REA tools registered directly with the Codex session handling real evidence.
- [ ] **Step 4: Run GREEN:** identical unittest command, all pass. Explicitly verify no traceback containing raw payload is printed.
- [ ] **Step 5: Commit** runner + test.

### Task 5: Synthetic browser fixture, structural cases and origin confinement

**Files:** Create `scripts/portal-lab/rea_fixture_server.py` and `scripts/portal-lab/rea_lab_smoke.py`; test `tests/test_rea_lab_smoke.py`.

**Interfaces:**
- Produces `create_fixture_server(host: str = "127.0.0.1", port: int = 0) -> object` with a synthetic page containing nested frames, hidden obsolete form, visible form, alternate interested selection and login/denied UI (NO real portal data).
- Produces `run_smoke(*, browser_path: Path, rea_argv: list[str], work_root: Path) -> dict[str, object]`: `status=PASS` only if REA captures synthetic states and network isolation is demonstrated. Missing pinned REA/browser is `BLOCKED`, never a silent `PASS`.

- [ ] **Step 1: Write RED tests** `test_visible_form_wins_over_hidden_stale_frame`, `test_denied_screen_is_not_form`, `test_fixture_serves_only_loopback`, `test_redirect_off_origin_is_blocked_by_outer_sandbox`, `test_missing_rea_is_blocked_not_pass`, `test_missing_structural_capture_is_incomplete`. Use `REA` fake evidence initially, then real REA fixture smoke.
- [ ] **Step 2: Run RED:** `python -m unittest tests.test_rea_lab_smoke -v`.
- [ ] **Step 3: Implement fixture and orchestrator** with a strict offline network confinement strategy **outside** REA (OS firewall/container/isolated network namespace as appropriate to Windows host). Restrict navigation and browser egress to the owned loopback fixture. If confinement is unavailable, stop integration test as `BLOCKED`; REA has no native origin allowlist and a start_url filter alone is insufficient.
- [ ] **Step 4: Run GREEN offline:** same unittest command. For an available reviewed, pinned REA and Chrome, run `python scripts/portal-lab/rea_lab_smoke.py --synthetic-only`; expected a sanitized `PASS` receipt and no egress; otherwise record `BLOCKED`, not `PASS`.
- [ ] **Step 5: Commit** fixtures/smoke/tests, excluding every raw capture and browser profile.

### Task 6: Prove the model cannot bypass the Evidence Gateway

**Files:** Create `scripts/portal-lab/rea_isolation.py`; test `tests/test_rea_lab_isolation.py`.

**Interfaces:**
- Produces `attest_boundary(*, operator_spool: Path, agent_context: dict[str, object], probe_reader: Callable[[Path], bool]) -> dict[str, object]`; `real_capture_enabled` is hard-false in Phase 0–1. The result includes only `PASS | BLOCKED` and enum reasons such as `SAME_PRINCIPAL`, `RAW_READABLE`, `DIRECT_MCP_ACCESS`, `UNVERIFIED_NETWORK`.
- Consumes explicit evidence of a distinct OS-security principal or enforceable sandbox, denied read access from the agent, no REA/CDP/raw-command bypass, and confinement/egress checks. **Documentation or chmod alone is not attestation.** No generic shell operation from the agent may reach restricted files.

- [ ] **Step 1: Write RED tests** `test_same_principal_is_blocked`, `test_agent_raw_readable_is_blocked`, `test_direct_mcp_or_cdp_tool_is_blocked`, `test_unknown_protection_is_blocked`, `test_success_requires_cross_principal_denied_access`. Use injected principal identity and probe results; exercise negative paths.
- [ ] **Step 2: Run RED:** `python -m unittest tests.test_rea_lab_isolation -v`.
- [ ] **Step 3: Implement explicit attestation** with fail-closed result, do not attempt to create Windows accounts or modify administrator policies implicitly; only document prerequisites for a future authorized deployment of the separate capture service.
- [ ] **Step 4: Run GREEN:** all tests pass. Record `real_capture_enabled=false` even if synthetic attestation tests are green. An actual cross-principal denial test remains a **separate future real-mode gate**.
- [ ] **Step 5: Commit** isolation + test.

### Task 7: Product boundary, package exclusion and full offline regression

**Files:** Modify `tests/test_devtools_runtime_boundary.py` and `tests/test_packaging_contract.py`; read `packaging/verify-package.ps1` and `.gitignore`.

**Interfaces:**
- Consumes new lab sources, no production import.
- Produces verified assertions that the portable package and root runtime do not depend on the lab.

- [ ] **Step 1: Write RED** `test_rea_gateway_lab_modules_are_not_imported_by_product`, `test_rea_private_capture_paths_ignored`, `test_rea_lab_modules_rejected_from_portable_zip`, `test_no_rea_cdp_mcp_dependency_in_runtime`. Add sentinel ZIP entries as fixture inputs and assert packaging rejects them.
- [ ] **Step 2: Run RED:** `python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v`; confirm new assertions catch an intentionally bad fixture.
- [ ] **Step 3: Implement only test/packaging guard changes needed.** Existing `verify-package.ps1` already blocks `scripts/portal-lab/` indirectly via its allowlist, so do not change production packaging code if current rejection holds. If `.gitignore` or verifier needs a narrow fix, justify from RED failure and keep actual product unchanged.
- [ ] **Step 4: Run GREEN and broader gates:** `python -m unittest discover -s tests -p 'test_*.py' -q`; `npm test --prefix extension`; `node --test app/web/tests/*.test.mjs`; `git diff --check`. Packaging verifier may be exercised against a fabricated **runtime-free test fixture** only; no production ZIP build is required in this phase.
- [ ] **Step 5: Commit** boundary assertions and narrowly justified configuration changes, not raw artifacts.

### Task 8: Handoff, threat-model review and stop gate

**Files:** Create `docs/notes/YYYY-MM-DD-rea-phase-0-1-handoff.md`; no product code changes.

**Interfaces:**
- Consumes test receipts, branch SHA, file diff, offline smoke and isolation results.
- Produces acceptance recommendation for **laboratory synthetic readiness only**, not qualification or permission for real capture.

- [ ] **Step 1: Review coverage D1/D2/D5/D6/D10** against spec and enumerate deferred D3/D4/D7/D8/D9 requirements for later plans; report any missing security test as blocking.
- [ ] **Step 2: Inspect `git diff --name-only <base>...HEAD`**, `git status --short`, `git check-ignore tmp/portal-lab/raw/capture.json`, CI results (if available), and source SHA. Confirm no PDFs, private logs, DOM, auth data, production code changes, packaging surprises or new runtime dependencies.
- [ ] **Step 3: Write handoff** with actual pass/fail counts, pinned REA version, Node/Chrome details when verified, exact spool boundary status, unresolved privacy risks, `real_capture_enabled=false`, no real qualification, phase score and next proposed review.
- [ ] **Step 4: Commit** handoff and push implementation branch **only after** plan approval and required tests, without merging into main; request independent code/security review before advancing to Phase 2.
- [ ] **Step 5: STOP.** Do not enable live TCE capture, promote AR-1/2/3 or write the next plan as if the laboratory had passed a real-site gate.

---

## Definition of Done and downstream gates

**Phase 0–1 may be accepted** when the baseline is reconciled, unit and fixture tests are green, the pinned REA synthetic capture is proven or explicitly labeled BLOCKED, the evidence projector never emits raw data, browser mutator lease has atomic fencing, product/package boundaries pass, and handoff accurately reports isolation limitations. **Full laboratory operational readiness requires an actual pinned REA synthetic smoke PASS and a demonstrated external confinement mechanism**; otherwise this phase remains partially blocked, not silently approved.

**Real-site investigation is NOT authorized by this plan:** first prepare a future separate plan and explicitly verify cross-principal agent isolation, restricted CDP access, operator-presence requirements, raw-capture retention, network egress policy and an allowlist of permitted portal actions. Only after those gates can approved real investigations begin. Subsequent separate plans cover AR-1 qualification, AR-2/AR-3 benchmark, Controller choice, Navigation Adapter and portable 20/20 gates; the D9 updater requires its own spec/plan.

**Suggested execution method after review:** Superpowers subagent-driven-development, because independent RED→GREEN task reviews and security gates are important; never run independent agents with concurrent browser mutation.
