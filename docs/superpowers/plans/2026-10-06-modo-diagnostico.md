# Modo Diagnóstico sempre ativo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task. Keep each task test-first and commit each reviewable milestone.

**Goal:** Instrumentar o runtime portátil com uma timeline local, correlacionada, sanitizada, limitada e exportável, sempre ON por padrão.

**Architecture:** `DiagnosticRecorder` grava em arquivos JSONL sob o data root, separado do SQLite e do ledger de qualification. Servidor, `FillService`, extensão e Mesa emitem observações nos boundaries que já existem; os payloads diagnósticos são removidos antes do processamento funcional. A UI obtém status/controles e exporta um ZIP gerado sob demanda.

**Tech Stack:** Python 3.14 e `unittest`; JavaScript ES modules e `node:test`; servidor HTTP local existente; PowerShell builder/verifier do ZIP.

**Spec:** `docs/superpowers/specs/2026-10-06-modo-diagnostico-design.md`

## Global Constraints

- Código de produção somente em `app/`, `extension/`, `tests/`, `packaging/` e `scripts/`; não corrigir `work/tce-extractor/` como fonte.
- Não alterar identity resolution, qualification, capability gates, fill, AR-1/AR-2/AR-3 nem submit manual.
- Não adicionar eventos de Modo Diagnóstico ao ledger `reliability/events.jsonl` ou aos resultados/filas funcionais do SQLite.
- Iniciar ON em todo boot; Pausar é transitório e um reinício inicia ON.
- Não registrar senha, cookie, Authorization, Bearer, extension token, header ou segredo equivalente; exportação é local e iniciada pela pessoa operadora.
- Instrumentação é fail-open e nunca controla retry, ownership, TTL, identidade, escrita ou resultado funcional.
- Manter cinco sessões; limitar a timeline ativa a 8 MiB e aparar até 6 MiB; `SLOW` começa em 2.000 ms.
- Testes e smoke são sintéticos/offline; não acessar portal real nem promover capabilities.
- Reconstruir o ZIP após o commit final em árvore limpa, validar provenance e SHA-256, e nunca reaproveitar ZIP antigo.

## Review Focus

- Credencial embutida em chave, mensagem de erro, warning ou URL: cobrir com `test_record_redacts_secret_keys_and_text_and_strips_url_query` no Task 1.
- Payload de extensão malformado ou com evento arbitrário: cobrir com `test_command_result_diagnostic_sidecar_is_removed_before_functional_validation` no Task 2.
- Disco/recorder falha durante current-selection ou resultado: cobrir com `test_recorder_failure_does_not_change_current_selection_response` e `test_recorder_failure_does_not_change_fill_result` no Task 2.
- Limite de duração, trim e retenção podem perder estados recentes: cobrir fronteira `1999/2000 ms`, tail mais novo e cinco sessões no Task 1.
- Pausar/limpar simultâneo a heartbeat/export deve permanecer fail-closed e bounded: cobrir uso concorrente do lock e resultado exportável no Task 1.

---

### Task 1: Recorder local, schema, retenção e ZIP

**Files:**
- Create: `app/area_restrita/diagnostics.py`
- Create: `tests/test_area_restrita_diagnostics.py`
- Modify: `app/area_restrita/__init__.py` only if package exports are required by an existing import pattern.

**Interfaces:**
- `DiagnosticRecorder(data_root: Path, *, build_id: str, extension_version: str, utcnow: Callable[[], datetime] = ...)`
- `record(event: Mapping[str, Any]) -> bool`
- `status() -> dict[str, Any]`
- `pause() -> dict[str, Any]`, `resume() -> dict[str, Any]`, `clear() -> dict[str, Any]`
- `export_zip(*, capabilities: Mapping[str, Any]) -> tuple[str, bytes]` returns `(filename, zip_bytes)`.
- Storage: `<data_root>/diagnostics/settings.json`, then
  `<data_root>/diagnostics/sessions/<session-id>.jsonl`.
- Event input is an allowlisted mapping; the recorder adds UTC `timestamp`,
  current `session_id`, and `severity: SLOW` when `elapsed_ms >= 2000`.

- [ ] **Step 1: Write the startup contract test**

Add `test_new_recorder_starts_on_and_restart_starts_a_new_on_session`. Construct
two recorders on the same temporary root. Assert `diagnostic_enabled` is true
in settings and both status responses are active, while session IDs differ.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest discover -s tests -p 'test_area_restrita_diagnostics.py' -k test_new_recorder_starts_on_and_restart_starts_a_new_on_session -v`
Expected: FAIL because the recorder module/API does not exist.

- [ ] **Step 3: Implement startup and persistent ON**

Create the settings file atomically with `diagnostic_enabled: true`, create a
new UUID session at recorder construction, and make pause state process-local.

- [ ] **Step 4: Write event, timing, code and privacy tests**

Add these named tests with literal event fixtures:

```text
test_record_stamps_session_timestamp_component_step_and_duration
test_record_marks_exactly_two_seconds_slow
test_record_preserves_result_code_and_redacts_full_error_text
test_record_redacts_secret_keys_and_text_and_strips_url_query
```

Assert `< 2000` is not slow, `2000` is slow, unknown keys are absent, error
codes remain unchanged, and no test secret appears in persisted JSONL.

- [ ] **Step 5: Verify RED, then implement the minimal schema sanitizer**

Run: `python -m unittest discover -s tests -p 'test_area_restrita_diagnostics.py' -k test_record -v`
Expected: failures for absent stamping/threshold/redaction. Add recursive
allowlisting, URL reduction, known secret-key filtering and text redaction;
preserve the full remaining error string.

- [ ] **Step 6: Write pause, clear, retention and export tests**

Add:

```text
test_pause_blocks_events_and_resume_records_again
test_clear_removes_prior_sessions_and_starts_a_fresh_session
test_retention_keeps_five_sessions_and_trims_active_timeline
test_export_contains_six_files_and_summary_identifies_failures_and_slow_steps
```

Inspect actual ZIP members and JSON/text contents; verify the latest events
survive trimming and credentials do not appear in any member.

- [ ] **Step 7: Verify RED, implement controls/retention/export, then run recorder suite**

Expected RED: methods/files absent or wrong. Keep at most five session files;
trim the active JSONL from 8 MiB to 6 MiB under the recorder lock. Export exactly
`resumo.txt`, `timeline.jsonl`, `ambiente.json`, `mesa.log`,
`extensao.log`, `ultima-sessao.json`.

Verify RED with:

```bash
python -m unittest discover -s tests -p 'test_area_restrita_diagnostics.py' -k test_pause -v
python -m unittest discover -s tests -p 'test_area_restrita_diagnostics.py' -k test_clear -v
python -m unittest discover -s tests -p 'test_area_restrita_diagnostics.py' -k test_retention -v
python -m unittest discover -s tests -p 'test_area_restrita_diagnostics.py' -k test_export -v
```

Run: `python -m unittest discover -s tests -p 'test_area_restrita_diagnostics.py' -q`
Expected: all recorder tests pass.

- [ ] **Step 8: Commit Task 1**

```bash
git add app/area_restrita/diagnostics.py tests/test_area_restrita_diagnostics.py
git commit -m "feat: add bounded local diagnostics recorder"
```

### Task 2: Mesa server, FillService and authenticated diagnostics API

**Files:**
- Modify: `app/api/server.py`
- Modify: `app/area_restrita/fill_service.py`
- Modify: `tests/test_api_server.py`
- Modify: `tests/test_fill_service.py`

**Interfaces:**
- `MesaServer` owns one eagerly-created `DiagnosticRecorder` for its data root;
  `FillService(..., diagnostics: DiagnosticRecorder | None = None)` receives it.
- `GET /api/v1/diagnostics` and `GET /api/v1/diagnostics/export` require a Mesa
  session.
- `POST /api/v1/diagnostics/control` accepts only `pause`, `resume`, `clear`.
- `POST /api/v1/diagnostics/events` accepts allowlisted Mesa events such as
  `COMMAND_TIMEOUT`; it never queues an operational command.
- Extension metadata is named `diagnostic_events`, extracted and recorded before
  that key is removed from the payload passed to existing result validation,
  `FillService`, and SQLite persistence.

- [ ] **Step 1: Write route and auth tests first**

Add these tests to `tests/test_api_server.py`:

```text
test_diagnostic_routes_require_a_mesa_session
test_diagnostic_status_reports_on_and_latest_extension_state
test_diagnostic_control_pauses_resumes_and_clears
test_diagnostic_export_returns_named_zip
test_mesa_diagnostic_event_records_command_timeout
```

Use the existing `ApiTestCase` session-cookie and extension-registration
helpers. Assert 401 without Mesa session, ZIP content type/name/members, and the
exact timeout code in the exported timeline.

- [ ] **Step 2: Verify RED and implement routes**

Run: `python -m unittest discover -s tests -p 'test_api_server.py' -k diagnostic -v`
Expected: route tests fail because paths/handlers are absent. Add authenticated
routes and use `_send_json`/binary response helpers already owned by the server.

- [ ] **Step 3: Write current-selection and command-sidecar tests**

Add:

```text
test_current_selection_records_safe_diagnostics_in_the_shared_session
test_command_result_diagnostic_sidecar_is_removed_before_functional_validation
test_recorder_failure_does_not_change_current_selection_response
```

Assert selected identity/route/nonce/observation metadata appears in the local
timeline, the full current-selection snapshot does not, malformed diagnostic
sidecars cannot make a functional command succeed or fail differently, and the
public response stays byte-for-byte equivalent in meaningful fields.

- [ ] **Step 4: Verify RED and instrument existing handlers fail-open**

Record current-selection start/result/elapsed in `post_portal_current_selection`;
extract `diagnostic_events` before `check_command_result`, record safe copies,
then remove it before functional service and persistence. Keep extension auth
and publisher/sequence validation unchanged.

Run: `python -m unittest discover -s tests -p 'test_api_server.py' -k diagnostic -v`
Expected: current-selection and command-sidecar tests fail before
instrumentation.

- [ ] **Step 5: Write FillService boundary tests**

Add:

```text
test_diagnostic_recorder_observes_preflight_and_fill_readback_values
test_diagnostic_events_do_not_enter_reliability_ledger_or_fill_snapshot
test_recorder_failure_does_not_change_fill_result
```

Assert the separate diagnostics timeline has `preflight` and `result`, including
safe `before`/`proposed`/`after` values; the existing reliability ledger has no
new diagnostic event/timing; and the fill-request snapshot contains no new
timing sidecar. The extension-owned `field_write` and `field_reread` timing
events are verified in Task 3, where the actual DOM operations occur.

- [ ] **Step 6: Verify RED, implement injected fail-open recording, run focused suites**

Instrument the existing preflight and terminal result boundaries with
`time.monotonic()`. A recorder exception is swallowed at the observability
boundary only. Do not edit identity/gating/fill decisions.

Run:

```bash
python -m unittest discover -s tests -p 'test_api_server.py' -k diagnostic -v
python -m unittest discover -s tests -p 'test_api_server.py' -k recorder_failure -v
python -m unittest discover -s tests -p 'test_fill_service.py' -k diagnostic -v
python -m unittest discover -s tests -p 'test_fill_service.py' -k recorder_failure -v
```

Expected: focused tests pass and reliability events/snapshots are unchanged.

- [ ] **Step 7: Commit Task 2**

```bash
git add app/api/server.py app/area_restrita/diagnostics.py app/area_restrita/fill_service.py tests/test_api_server.py tests/test_area_restrita_diagnostics.py tests/test_fill_service.py
git commit -m "feat: record Mesa and fill diagnostic boundaries"
```

### Task 3: Extension heartbeat, form scan, command and field timings

**Files:**
- Modify: `extension/background/router.js`
- Modify: `extension/content/fill-form.js`
- Modify: `extension/tests/router.test.mjs`
- Modify: `extension/tests/fill-form.test.mjs`

**Interfaces:**
- `installRouter` retains its injected clock and adds an injectable monotonic
  clock for duration tests.
- `publishCurrentSelection` sends a `diagnostic_events` sibling containing only
  timing/stage/structural data; the existing `active`, `form`, publisher and
  sequence shape is unchanged.
- `FILL_FORM` returns field write/readback timings in `diagnostic_events`, not
  inside functional `field_results`.
- `poll()` attaches command-received/execution timing events to its existing
  `reportResult` call; the API and server strip the sidecar before processing.

- [ ] **Step 1: Write form/heartbeat tests first**

Add to `extension/tests/router.test.mjs`:

```text
test("the form observation reports portal, frame-scan and detection timings")
test("current-selection timing is a diagnostic sidecar and preserves publisher fields")
```

Use the existing fake Chrome, known frames, and injected monotonic clock; assert
literal stage names and durations while the existing form identity/publication
fields remain unchanged.

- [ ] **Step 2: Verify RED, implement observation timings**

Run: `node --test extension/tests/router.test.mjs`
Expected: the two new diagnostic timing tests fail before instrumentation.

Time `portal_detected`, `frames_scanned`, `form_detected` or the existing
failure code, and `selection_published`. Coalesce heartbeat timeline events on
the server to first/change/every 10 seconds while updating heartbeat age on each
poll.

- [ ] **Step 3: Write field and command receive tests first**

Add to `extension/tests/fill-form.test.mjs`:

```text
test("field write and reread durations stay outside functional field results")
```

Add to `extension/tests/router.test.mjs`:

```text
test("poll reports command received and result timings without changing the result")
```

Assert real fake-DOM writes still occur once, functional statuses/values are
unchanged, and timings appear only under `diagnostic_events`.

- [ ] **Step 4: Verify RED, instrument, and run extension suite**

Run: `node --test extension/tests/fill-form.test.mjs extension/tests/router.test.mjs`
Expected: the new write/readback and command timing tests fail before
instrumentation.

Use `performance.now()` with the injected test clock; record per-field write and
reread durations even when a field fails, without changing safety branches.

Run: `npm test --prefix extension`
Expected: all extension tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add extension/background/router.js extension/content/fill-form.js extension/tests/router.test.mjs extension/tests/fill-form.test.mjs
git commit -m "feat: time extension diagnostic boundaries"
```

### Task 4: Mesa diagnostic panel and actions

**Files:**
- Modify: `app/api/server.py` (add sanitized current-selection code fields to diagnostic status)
- Modify: `tests/test_api_server.py`
- Modify: `app/web/index.html`
- Modify: `app/web/app.js`
- Modify: `app/web/app.css`
- Modify: `app/web/tests/app-boot.test.mjs`
- Modify: `app/web/tests/ui-wiring.test.mjs`
- Modify: `LEIA-ME-OUTRO-PC.txt`

**Interfaces:**
- `refreshDiagnostics()` reads `GET /api/v1/diagnostics` and runs at the
  existing five-second dashboard cadence.
- Pause/resume/clear send the specified action to
  `POST /api/v1/diagnostics/control`; browser-observed command timeouts send a
  `COMMAND_TIMEOUT` event to `POST /api/v1/diagnostics/events`.
- Export downloads the response from `GET /api/v1/diagnostics/export` under its
  server-provided filename and delays object-URL revocation briefly so the
  browser can consume the download.

- [x] **Step 1: Write DOM and behavior tests before the panel**

Extend `app-boot.test.mjs` to assert the real boot starts a diagnostic refresh
and binds all three controls. Extend `ui-wiring.test.mjs` with:

```text
test("the Mesa diagnostic panel exposes required live statuses and actions")
test("the Mesa sends pause, resume, clear, timeout and export to diagnostic routes")
```

The behavior test triggers click handlers in the existing stub DOM and checks
actual fetch/download effects, not only matching source strings.

The API status test also verifies that heartbeat refresh does not hide the
current selection's machine code. This required two additive fields sourced
from `portal_selection.public_state()`; the first test run failed on missing
`form_code`, then passed after the minimal API change.

- [x] **Step 2: Verify RED, implement the minimal panel and export flow**

Run: `node --test app/web/tests/app-boot.test.mjs app/web/tests/ui-wiring.test.mjs`
Expected: the new boot, status and action tests fail before panel wiring.

Render the required statuses and action labels in the existing panel style;
show machine codes and heartbeat age. Control/event request failures are shown
in the panel and never interrupt another Mesa action. Add a short other-PC guide
note explaining where to export the ZIP.

- [x] **Step 3: Run Mesa web suite**

Run: `node --test app/web/tests/*.test.mjs`
Expected: all web tests pass and `init()` still boots.

- [x] **Step 4: Commit Task 4**

```bash
git add app/web/index.html app/web/app.js app/web/app.css app/web/tests/app-boot.test.mjs app/web/tests/ui-wiring.test.mjs LEIA-ME-OUTRO-PC.txt
git commit -m "feat: add diagnostic controls to Mesa"
```

### Task 5: Synthetic export smoke, full gates and portable ZIP

**Files:**
- Create: `scripts/portal-lab/diagnostics-smoke.py`
- Modify: `tests/test_area_restrita_diagnostics.py` only if smoke uncovers a
  missing contract.
- No generated ZIP, database, event logs, profile or credentials are committed.

- [x] **Step 1: Write the smoke harness against the recorder contract**

In a temporary data root, write the sequence `form_detected` at 4800 ms,
`FORM_NOT_AVAILABLE`, `STALE_FORM`, successful `FILL_FORM` with field write and
readback, and `COMMAND_TIMEOUT`. Export and assert all six members plus codes,
durations, `SLOW`, build/version/capabilities, and secret absence. The process
must exit nonzero on any mismatch and print only concise pass/fail counts.

- [x] **Step 2: Run smoke and record exact evidence**

Run: `python scripts/portal-lab/diagnostics-smoke.py`
Expected: five requested scenarios are identified in the exported ZIP; no
portal, credentials, live Chrome or permanent data root is used.

- [ ] **Step 3: Run full repository gates**

Run each command and record counts:

```bash
python -m unittest discover -s tests -p 'test_*.py' -q
npm test --prefix extension
node --test app/web/tests/*.test.mjs
python -m unittest tests.test_packaging_contract -v
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1
```

Expected: all root Python, extension, web, package-contract and selected legacy
verifier gates pass; the legacy verifier is supplementary and is not a source
tree substitute.

Execution evidence: the root Python suite passed 901/901; extension 267/267;
web 69/69; package contract 20/20; diagnostic smoke 14/14. The supplementary
`work/tce-extractor/verify-project.ps1` exits 1 after `Test-ProjectVerification.ps1`
prints 23 passes and exits before its PID probe and summary. Other legacy scripts
passed individually or earlier in that wrapper. Leave this step open until the
legacy verifier passes or its specific host limitation is resolved and
documented; do not infer a production failure from the incomplete test output.

- [ ] **Step 4: Commit all final code/handoff before release build**

Verify `git diff --check`, update the handoff with test evidence, commit, and
push the final source. Confirm `HEAD == @{u}` before building.

- [ ] **Step 5: Build a new portable ZIP from the final clean SHA**

Run:

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\packaging\build-portable.ps1 -OutputPath .\dist\Atos-TCE-diagnostic.zip -Force
$diagnosticBuildId = (git rev-parse HEAD).Trim()
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\packaging\verify-package.ps1 -ZipPath .\dist\Atos-TCE-diagnostic.zip -ExpectedBuildId $diagnosticBuildId
Get-FileHash -LiteralPath .\dist\Atos-TCE-diagnostic.zip -Algorithm SHA256
```

Confirm manifest `build_id` equals `HEAD`, required diagnostic source is in the
ZIP, package smoke passes, no private/prohibited entries exist, and the SHA-256
reported by the builder equals the independent `Get-FileHash` result. Write a
`.sha256` sidecar from that verified hash if the current `dist/` convention
requires it.

- [ ] **Step 6: Confirm GitHub CI and complete the handoff**

Check the workflow run for the final pushed SHA; report status and any missing
external CI permission honestly. Update the handoff with final SHA, CI run,
artifact path/size/hash, gate counts, synthetic-only boundary and remaining
human steps. Commit/push that handoff and verify a clean synchronized branch.
