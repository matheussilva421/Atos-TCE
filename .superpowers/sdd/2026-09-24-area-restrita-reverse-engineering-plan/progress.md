# SDD ledger — plan: docs/Atos-TCE-Area-Restrita-Implementation-Pack-2026-09-24/lab/2026-09-24-area-restrita-reverse-engineering-plan.md

Base: `c477026ce887cd4ac066b869d73e0e8049e8864d` on `codex/atos-tce-unified`; clean and equal to origin at setup.

## Authority and rulings

- The plan names `docs/superpowers/specs/2026-09-24-area-restrita-lab-design.md`, which is absent. The user-supplied package copy `docs/Atos-TCE-Area-Restrita-Implementation-Pack-2026-09-24/lab/2026-09-24-area-restrita-lab-design.md` was read in the required order and is the available design authority. Any ruling based on it remains provisional until the canonical spec path is reconciled.
- Ruling: work directly on `codex/atos-tce-unified`, the explicitly requested canonical development branch, instead of creating a competing branch/worktree. The base is already 44 commits ahead of `main` and clean. Cost if wrong: edits have less filesystem isolation than a linked worktree.
- Ruling: the MCP example/config must include both `--categoryExtensions` and `--browser-url=http://127.0.0.1:9222`, plus `--no-usage-statistics` and `--no-performance-crux`. Installed Chrome is 153.0.8010.53; the installed MCP CLI reports extension-category/browserUrl support is compatible from Chrome 149. Cost if wrong: a developer on an older Chrome cannot use this combined configuration; document/check the minimum before connection.
- Ruling: the Task 1 source scan omits `packaging/`, because the package verifier must name and reject development-tool artifacts. Runtime dependence is checked in `app/`, `extension/`, and `START.cmd`; the packaging boundary is exercised behaviorally by injecting artifacts into ZIP fixtures. Cost if wrong: a development dependency could enter packaging code, but packaging scripts are not shipped and are separately verified.
- Ruling: Task 2's suggested static launcher-token test is replaced by `-WhatIf` behavioral tests and a loopback HTTP fixture for `Test-CdpEndpoint.ps1`. This validates actual launch arguments and endpoint acceptance/rejection without launching Chrome or relying on source text. Cost if wrong: a formatting-only interface change may require updating the test harness.

## Pre-flight interface scan

- Task 1 and Task 11 share `tests/test_packaging_contract.py` and may share `packaging/verify-package.ps1`; complete Task 1 before Task 11.
- Tasks 2, 3, and 4 share `devtools/area-restrita/README.md`; execute in order.
- Tasks 2 and 5 share `tests/test_portal_lab_contract.py`; Task 2 precedes Task 5.
- Tasks 5, 6, 8, and 9 share the portal contract/fixtures; keep them sequential and sanitize before versioning.
- Tasks 6 and 10 share runtime portal-state knowledge; do not alter runtime until real evidence has produced a fixture and RED test.
- Portal observations in Tasks 8–9 share one authenticated browser session and must remain serial.

## Baseline

- `python -m unittest discover -s tests -p "test_*.py" -q`: baseline 616 run, 615 passed, 0 failed, 1 skipped; after Task 1 changes 619 run, 618 passed, 0 failed, 1 skipped.
- `npm test --prefix extension`: 145 passed, 0 failed.
- `node --test app/web/tests/*.test.mjs`: 28 passed, 0 failed (Node emitted a MODULE_TYPELESS_PACKAGE_JSON warning for `app/web/pdf-viewer.js`).
- `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1`: 1,259 executed, 1,257 passed, 0 failed, 2 skipped; all seven stages passed.
- `git diff --check`: passed at baseline; re-run before commit.

## Task status

- Task 1: complete in commit `6d809dc`; handoff/push commits `f0354f8` and `f588655` are confirmed at origin. RED: verifier accepted all seven injected lab/tool artifacts; raw/sanitized git-ignore test failed because sanitized paths were ignored. GREEN: `python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v` passed 15 tests, 1 skip; full root Python suite passed 619 tests, 1 skip.
- Task 2: complete and published (`777cab2`, handoff `9d5a248`); branch clean and synchronized.
- Task 3: artifacts are published (`298cac1`, handoff `d95b228`/`c3b2f42`); live connection gate is pending reload of the MCP process in the active session.
- Task 4: complete and published (`1a5250b`, handoff `afd6fb4`); package-boundary gate is green.
- Task 5: implementation and gates published in `c8cd3d0`; handoff in `3fb664f`. Full project gate: 1,259 executed, 1,257 passed, 0 failed, 2 skipped. Full Python suite: 632 run, 631 passed, 1 skipped. Two initial push attempts hit GitHub Internal Server Error; a later combined push succeeded. No real portal capture. MCP target reload remains pending.
- Task 6: published in `f9d62b4`; contract, schema, four synthetic fixtures, README, and parity test complete. Contract tests 7/7; extension 152/152; Portal Lab 13/13; full Python 632 run (1 skip); integrated verify-project 1,259 run (2 skips). No runtime changed. Local and remote SHA verified equal and checkout clean.
- Task 7: complete and published in commit `35ef33d5c14c6dcbb53fa334adac04ee08a3a967`; remote branch SHA confirmed equal.
- Task 8: in progress. Real authenticated-session L0 baseline captured and sanitized; current list and buttons frame observed. Interested/form screens remain unobserved; no L1 transition was made.
- Tasks 9–12: not started.
Task 1: complete (commits c477026..6d809dc, tests: python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v → OK (skipped=1))
Task 2: complete and published (`777cab2`, handoff `9d5a248`). RED: 5 behavior tests failed because both scripts were absent; GREEN: 5/5 passed. Full Python: 624 run, 623 passed, 1 skipped. verify-project: 1,259 executed, 1,257 passed, 0 failed, 2 skipped; all seven stages passed. Manual: Chrome PID 2800, private profile at %LOCALAPPDATA%\Atos-TCE\Chrome-Debug, CDP bound to 127.0.0.1:9222 and checker passed. No portal login or interaction. MCP tools are loaded, but connection to PID 2800 is not yet proven.
Task 3: artifacts `298cac1` and handoff `d95b228` are published. RED 2 tests because config example and safety policy were absent; GREEN 7/7 focused tests. Full Python 626 run, 625 passed, 1 skipped. verify-project 1,259 executed, 1,257 passed, 0 failed, 2 skipped. The user's global MCP entry now includes --browser-url=http://127.0.0.1:9222, --categoryExtensions, --no-usage-statistics and --no-performance-crux. The running tool session did not reload; a disposable about:blank marker remained absent from PID 2800's /json/list, then the MCP tab was restored and had no network requests. No portal login. This session's MCP target reload gate remains pending; a handoff status correction is being committed.
Task 3 follow-up: status commit `c3b2f42` published; actual user config is confirmed. Live target reload still pending.
Task 4: `playwright-cli` v0.1.13 and official workspace skill installed (vendor skill ignored by Git). Direct CDP attach to 127.0.0.1:9222, snapshot of chrome://new-tab-page/, and detach passed. RED test for ignoring `.agents/skills/playwright-cli/` failed first; GREEN after `.gitignore` update. Boundary tests: 15 run, 14 passed, 1 skipped (distribution ZIP absent), 0 failed. Commit `1a5250b` created; handoff update and push pending.
Task 4 closeout: commit `1a5250b` and handoff `afd6fb4` published. Task 3 MCP live connection target still needs a client reload.

## Current session update — 2026-09-24

- Repository baseline at start: `4af5d00fb7549c19acf8d0f18bbd02666130d1e5`, clean and equal to `origin/codex/atos-tce-unified`; root Python 632 run/631 pass/1 skip, extension 152/152, web 28/28, integrated gate 1,259 run/1,257 pass/2 skips.
- MCP was already installed; no install/reinstall. The isolated Portal Lab Chrome was started as PID 2272 with the dedicated profile. `Test-CdpEndpoint.ps1` passed. A temporary `about:blank` marker was visible via MCP `list_pages` and CDP `/json/list`, then the tab was closed. No portal navigation or login.
- Task 7 implemented in `.agents/skills/area-restrita/SKILL.md`, `references/portal-states.md`, `references/safety.md`, and `references/workflow.md`. It contains the required A–M sequence, exact timeout-first and selector-owner rules, L0/L1/L2/L3 boundaries, manual final action, and contract-versus-real-evidence distinction.
- Three independent pressure scenarios first exposed timeout-first and selector ownership gaps; after the update, all three decisions met the expected safety boundaries. No evaluator edited files or accessed a browser.
- Focused gate `python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v`: 15 run, 14 pass, 0 fail, 1 skip (portable ZIP absent).
- Integrated `verify-project.ps1`: 1,259 executed, 1,257 passed, 0 failed, 2 skips; all seven stages passed. `git diff --check` passed before the latest handoff update; rerun before commit.
- Task 7 commit `35ef33d5c14c6dcbb53fa334adac04ee08a3a967` was pushed; `git ls-remote origin refs/heads/codex/atos-tce-unified` returned the same SHA. At the time of this note, Task 8 real L0 observation after human login was pending; the status is superseded by the update below. Do not begin production Next Process runtime before Task 10 and Phase 0 are closed.

## Task 8 L0 update — 2026-09-24

- The operator reported that portal login was completed manually. The active page is `/telaPrincipalMenu.asp`, `readyState=complete`.
- Read-only recursive frame inventory found 9 page/frame documents: `/frameSession.asp`, `/IncludesTelaPrincipal/ConteudoNotificacoes.asp`, two `/telaDeTrabalho.asp` frames, `/Home.asp`, `/SISTEMAS/Processo/ProcessonoSetor.asp`, two `/botoes_vazio.htm`/`/botoesNOVO.asp` button frames. The list and button frame were already loaded; no click, fill, or navigation was performed.
- On the list frame, structural counts were 110 hidden inputs, 20 text inputs, 13 selects, 5 input-buttons, 26 radios, 36 checkboxes, and 272 links (482 total; no values or labels read). `/botoesNOVO.asp` had 17 input-buttons.
- Current-page network summary: 198 parsed requests (197 GET, 1 OPTIONS), with 196 status 200, one 204, one 206. Console summary: 7 lines and 5 message IDs; no error classification claimed. Accessibility snapshot parser counted 1,023 lines / 987 `uid` tokens; raw snapshot text was not saved to Git or printed.
- `sanitize-capture.py` exited 0; sanitized local output is 4,263 bytes under ignored `tmp/portal-lab/2026-09-24-task8-l0/sanitized/`. Existing contract/fixtures were unchanged because the observed routes already exist and no new selector/sentinel is confirmed. Contract parity: `node --test tests/portal-contract.test.mjs` — 7/7 passed.
- Interested/form screens are not currently loaded. The next concrete action is Task 9's single `LIST -> INTERESTED` L1 transition, after the operator identifies an authorized test act. Do not select an interested party, fill fields, or perform L3 actions during that transition.
- No runtime, contract, or fixture changes. Handoff updated at `docs/notes/2026-09-24-area-restrita-lab-handoff.md`. `git diff --check` passed. Repository gate `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1`: 1,259 executed, 1,257 passed, 0 failed, 2 skips; all seven stages passed. Contract parity: 7/7 passed.
- Current GitHub status before this documentation update: Task 7 commit is confirmed at origin. Documentation changes remain to commit and push.
