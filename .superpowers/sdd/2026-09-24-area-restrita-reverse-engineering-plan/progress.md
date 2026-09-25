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
- GitHub: commit `90d61ebe989af59426cecba5deb5650b73fc445e` (`docs: record authenticated portal L0 baseline`) was pushed; `git push` returned success and reported `9598871..90d61eb`. The local tracking ref matches. Two subsequent `git ls-remote` checks could not connect to GitHub port 443, so the remote SHA could not be independently rechecked.

## 2026-09-24 — Mesa bootstrap no Chrome QA

- Root cause: launcher `app.main` usa `webbrowser.open`, portanto o bootstrap seguia o browser padrão. Um helper exclusivo de Portal Lab agora direciona essa chamada ao CDP loopback do Chrome QA, mantendo o runtime/pacote sem dependência de DevTools.
- RED/GREEN: três contratos novos falharam antes do helper existir e passaram depois. `python -m unittest tests.test_portal_lab_contract -v`: 16/16. `py_compile` e help CLI passaram.
- Smoke real com data-root temporário: bootstrap de uso único foi aceito no mesmo Chrome QA e redirecionou para o dashboard. Aba e diretório temporários removidos; serviço temporário não ficou ativo. Token não foi impresso.
- Banco de produção local consultado em modo read-only: integridade `ok`, sem jobs/comandos ativos. O serviço real não estava escutando em `18743` nesta checagem; os jobs interrompidos e itens históricos foram mantidos.
- Código/documentação tocados: `scripts/portal-lab/launch_mesa_in_qa_chrome.py` (novo), `tests/test_portal_lab_contract.py`, `devtools/area-restrita/README.md`, handoff. Nenhum runtime ou portal foi alterado.
- Gate Python completo e `verify-project.ps1` ainda pendentes. Estado seguinte: executar ambos; iniciar Mesa real com o helper na porta 18743 e data-root existente; confirmar sessão do dashboard no Chrome QA; acionar análise uma única vez e observar apenas agregados. Task 8/9/10, Phase 0 e Next Process permanecem pendentes conforme os gates do plano; não implementar Next Process antes de Task 10 + Phase 0. Commit/push pendentes.


## Continuation — shared Chrome Mesa launch and live scan (2026-09-24)

- Goal objective from attachment `82e0b0b9-0d4e-4973-90a4-5794b6d71a3e` read. Best-Effort Task 10 + Next Process Phase 0 remain the first functional gate; no Próximo Processo runtime implemented.
- Dev-only CDP helper added with RED/GREEN tests and usage docs. Full tests: Python 635/634 pass/1 skip; integrated verify-project 1,259/1,257 pass/2 skips, all seven stages green.
- Root cause of first bootstrap 401: two Mesa processes simultaneously listened on 18743; the stale process consumed the request. After stopping it and restarting once, the new Chrome QA tab redirected to `/` successfully. Current portal page remains active in same Chrome.
- First analysis attempt failed because no authenticated portal tab was active. Re-activated the portal tab and clicked Analyze once from the background Mesa page. Extension command succeeded, but only 27 items were saved (24 completed, 3 pending); full 1,197-item reconciliation and pagination remain unresolved. No acts/forms were opened or filled.
- Raw selected marker retained only in ignored local file `tmp/portal-lab/2026-09-24-task8-live-scan/marker-private.json`; it was not changed or added to Git. DB `integrity_check=ok`; no active jobs or commands.
- Next: evidence-first diagnose the one-page scan, reconcile 1,198 vs 1,197, finish Task 10 and Phase 0 with operator supervision; only then consider Next Process Tasks 1–8. Final adversarial review, full gates, and standalone package remain outstanding.
- Commit/push for the helper block are pending.


- Launcher hardening follow-up: test was red for a userinfo URL and an extra fragment parameter; strict loopback bootstrap validation now rejects both before CDP requests. Focused contract suite 17/17. After this change root Python passed 636 tests (635 pass, 1 skip); integrated verify-project passed 1,259 (1,257 pass, 2 skips), all seven stages green.

- Duplicate-listener guard added after the live port collision: host must be `127.0.0.1`; an exclusive bind preflight refuses occupied Mesa ports before starting the server. RED/GREEN two tests passed, and a live CLI preflight against the current server returned exit 2 without creating another process. Final root Python 638/637 pass/1 skip; verify-project 1,259/1,257 pass/2 skips, all stages green.


## Git closeout — launcher block

- Commit `331a7e001dacc2d850007c872cdeef616d79507e` (`dev: launch Mesa inside QA Chrome`) pushed successfully from `f235b46`. Elevated `git ls-remote` returned the same full SHA.
- Implementation block is published. The overall user goal remains active: 27/1,197 scan reconciliation, Best-Effort Task 10, Phase 0, Next Process, adversarial review, and standalone packaging are not complete.

## Follow-up L0 — scan parcial de 27 itens (2026-09-24)

- Playwright CLI attached ao CDP loopback do Chrome QA com diretórios auxiliares redirecionados para `tmp/portal-lab/`; captura estrutural sanitizada de 9 frames. O inventário atual tem frames `iframeOBJ` duplicados e uma rota `/SISTEMAS/Processo/expirou.asp`; a lista não está presente. Nenhuma navegação ou preenchimento foi feito.
- SQLite read-only: integridade `ok`; scan recente com 27 itens únicos. A ordem coincide exatamente com o sufixo 1.172–1.198 de scans completos anteriores com 1.198 itens. Causa provável: scanner iniciou na última página e não normaliza para a primeira. Evidência estática: `scanAreaPages` parte do `SCAN_PAGE` atual, avança adiante e encerra em `page >= total_pages`; o resultado persistido não guarda a página inicial, então falta confirmação direta.
- O estado 1.198/1.197 permanece aberto. Sem alteração de runtime: gate exige Task 10 real e Phase 0 real primeiro. Próximo passo é recuperar a observação da lista autenticada, fechar Task 10 com cinco casos e parcial best-effort, então completar Phase 0.
- Artefatos raw e sanitized são locais/ignorados: `tmp/portal-lab/2026-09-24-task8-live-scan/`. Nenhuma suíte automatizada foi executada nem código alterado. Reprodução sintética do `scanAreaPages`: iniciar em 40/40 produz 27 itens, 0 avanços; iniciar em 1/40 produz 1.197 itens, 39 avanços. A captura real não observou a paginação: a lista não estava carregada e o coletor não interpretou comandos `javascript:`.

## Atualização Task 8 — lease corrigido e scan live completo (2026-09-24)

- Causa operacional da tentativa falha: scan real de 40 páginas excedeu o lease fixo de 120s e foi re-reclamado (`attempt_count=2`); a tentativa final não encontrou moldura. Adicionado lease renewal autenticado por página, com testes de posse/token, expiração e integração API/extension.
- TDD RED/GREEN e validações: 5 testes Python focados + 3 JavaScript focados; suíte extensão 155/155; raiz 643 (642 pass/1 skip); extrator 528 (519 pass/9 skips); gate integrado 1.259 (1.257 pass/2 skips), sete estágios verdes.
- Mesa reiniciada pelo launcher Portal Lab e extensão recarregada no mesmo Chrome QA. A lista foi para a primeira página pela paginação allowlisted e a análise foi iniciada uma vez pela interface Mesa. Scan `SUCCEEDED`, tentativa 1, páginas 1–40, 1.197 linhas/chaves únicas: 843 complementados, 354 pendentes, sem ambiguidades ou duplicatas. O marcador selecionado na captura privada anterior bate com o scan atual.
- Reconciliação histórica 1.198/atual 1.197: mesmo escopo, marcador histórico diferente; 1.196 chaves compartilhadas, 2 apenas históricas (ambas já complementadas), 1 apenas atual. O conjunto histórico não é comparação de marcador equivalente; não atribuir a diferença a falha de paginação. SQLite íntegro, 0 comandos/jobs ativos.
- Task 8: cobertura agregada da lista atual completa. Task 9 ainda sem interessado/form; Task 10 (cinco casos reais + parcial best-effort) pendente; Phase 0 pendente; Next Process Tasks 1–8 bloqueadas até Task10 + Phase0; revisão adversarial e standalone pendentes. Nenhum ato aberto ou campo preenchido; clique final continua manual.
- Próximo passo: Task 9 com supervisão do operador; depois Task 10, Phase 0, Next Process, revisão adversarial e pacote. Handoff detalhado atualizado em `docs/notes/2026-09-24-area-restrita-lab-handoff.md`. Commit/push deste bloco ainda pendentes.

## Atualização: modalidade selecionada e gates pós-correção — 2026-09-24

- A proposta do portal é textual e pode não coincidir literalmente com os valores do `<select>`. `build_fill_plan` agora escolhe a melhor opção selecionável do catálogo atual para `modalidade`, registra confiança, margem, conflito/tie-break e avisos; opções inexistentes, todas desabilitadas, controle ausente ou não gravável continuam pendentes. `modalidade` já é campo obrigatório em `app.analysis.MANDATORY_FIELDS`.
- Testes TDD: fixture do catálogo ativo sanitizada, seleção da melhor opção, tie-break visível e conflito sem correspondência. RED observado antes da implementação; GREEN focado 71/71. Em live QA, somente o campo modalidade mudou no caso fraco; cinco campos foram preservados, a seleção foi relida da DOM e o estado local terminou `PREENCHIDO`. Nenhum clique final/submissão.
- Validação completa: Python raiz 644 (643 pass, 1 skip); extensão 155/155; web 28/28; suíte suplementar work/tce-extractor 528 (519 pass, 9 skips); `verify-project.ps1` 1.259 (1.257 pass, 2 skips, zero falhas, sete estágios); diff check verde.
- Task 10: cinco classes jurídicas e caso best-effort fraco já observados antes; o caso fraco foi revalidado após esta mudança. O registro live não inclui referências/nome de pessoa.
- Phase 0 ainda parcial: marcador/scan e intervalos conferidos em captura privada anterior; falta fechar ordem item a item, baseline de navegação estrutural e estado após conclusão manual. A comparação de 60 linhas com referências/nome foi rejeitada pelo auto-review por amplitude de dados pessoais; não foi repetida nem substituída por hashing. Uma tentativa limitada de timing não encontrou formulário/ação exata.
- Estado live atual: Chrome QA continua com um formulário de ato visível e Mesa autenticada. O formulário preenchido ficou aberto para revisão/conclusão manual; não naveguei para a lista nem acionei o botão final.
- Next Process Tasks 1–8 continuam bloqueadas até Phase 0 fechar. O clique final **Complementar Ato** é exclusivamente manual. Revisão adversarial final e package smoke continuam pendentes.
- Git: branch `codex/atos-tce-unified`, HEAD inicial `9b9cbe3f76fbb46ac214131c09618576ce32a136`; alterações de código/fixture e estes registros locais sem commit. `git ls-remote origin` não conectou ao GitHub; revalidar conectividade antes de publicar.
