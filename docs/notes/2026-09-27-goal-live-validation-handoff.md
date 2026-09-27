# Goal live-validation handoff — 2026-09-27

## Repository and branch

- Repository: `Atos-TCE`.
- Branch: `codex/atos-tce-unified`.
- Starting HEAD: `3be93e1350cc24fa4ee8f9472dfebfc41d79e832`.
- Source code was not changed in this checkpoint.
- The prior scan remains scan 10; no new official scan was run.

## Live state and safety

- Chrome QA is the active DevTools target on loopback CDP `127.0.0.1:9222`; Mesa and the extension remain open.
- At the start of this checkpoint, Área Restrita was authenticated, scan 10's selected marker matched the live marker, and the form at scan position 301 was open.
- The scan still records 1,197 rows: 354 pending and 843 complemented; zero ambiguous, blocked, or not-found rows.
- No act was finalized, submitted, signed, or tramited. The portal's final **Complementar Ato** action remains manual.
- After one `OPEN_NEXT_ACT` failure, the active work frame remained empty. A single reload of the portal shell then showed login/password controls. The portal must be reauthenticated manually before live work resumes. No credentials or session material were read or handled.

## Live Próximo Processo evidence

- Previously recorded commands 59 and 60 succeeded: 298 → 300 on the same page (17.532 s upper bound) and 300 → 301 across a page boundary (24.442 s upper bound). Both reread the exact process/interested identity; command 60 had no following fill request.
- This checkpoint: commands 62–65 succeeded and each target matched exactly one scan identity; the stored scan marker matched the command context.
  - 301 → 302, same page; command 62.
  - 302 → 303, same page; command 63; click-to-ready upper bound 5.7 s.
  - 303 → 304, same page; command 64; click-to-ready upper bound 6.0 s.
  - 304 → 306, same page; command 65; the intervening row was not eligible; click-to-ready upper bound 5.4 s.
- Command 66, from 306 toward 307, failed closed with `FORM_NOT_AVAILABLE`. It created no fill request and no final action. The result does **not** establish a stale-target refusal: the command code was specifically `FORM_NOT_AVAILABLE`.
- Read-only diagnostics after command 66 found document requests returning HTTP 200 and no explicit login/expired-session text before reload. The active work frame had no body or form controls. A native list-tab click did not make the frame's DOM usable. The subsequent portal-shell reload exposed login/password controls, so live navigation must wait for manual reauthentication and a fresh structural check.
- No natural stale-ready process or ambiguous scan item exists in the persisted snapshot (`stale_ready_groups=[]`, scan ambiguous count 0). Do not edit the database or create ambiguity to force those cases.
- The last eligible scan position is 1083. The live end-of-queue case remains unrun.

## Best-Effort Task 10 real sample

- One authorized real fill was run for the eligible case at scan position 301, whose documentary evidence includes ECE/RN 20/2020.
- Request 20 / extension command 61 completed successfully. Exact identity echo matched the unique scan row. All six proposed fields were marked `changed`, and each stored `after` value equaled `proposed`; 0 fields were preserved and 0 unresolved. `mandatory_satisfied=true`; local process status is `PREENCHIDO`.
- Legal decision used `legal-foundation-v4`, method `best-available`, selected a catalog option, confidence `0.779545`, margin `0.000598`, and `hard_conflict=true`. Warnings: `low-confidence`, `low-margin`, `hard-conflict`. This is also evidence for the weak/nonliteral-match review case; preserve the warnings in the report.
- The portal's final action was not clicked. The Area Restrita scan still reflects the original pending state because no final act was completed.
- Remaining real Task 10 coverage: isolated EC 41/2003, isolated CF art. 40, preserve a previously valid EC 47/2005 value, and a genuine partial A/B/C case. Do not manufacture missing/disabled/divergent portal state with script.

## Tests, package, and GitHub

- No tests were run in this checkpoint; it made no source change. Previously recorded offline gates are historical and must not be presented as this checkpoint's final gate.
- ZIP and clean-extraction smoke remain pending for the final closeout sequence.
- Before this handoff edit, the checkout was clean and synced with `origin/codex/atos-tce-unified` at the starting HEAD above. This handoff still needs its own commit and push.

## Resume instructions

1. If the session expires, have the operator authenticate in the already-open Chrome QA window; do not handle credentials or session tokens.
2. The sector process list has been restored through the portal UI. Recheck its page/frame structure and compare the selected marker with scan 10 before any further queue navigation; do not rerun the official scan.
3. Do not repeat command 66 or the later accepted-but-unconfirmed request. Reconcile the pending target through the official UI before any new **Próximo processo** action.
4. Continue Task 10 only on exact eligible identities, filling and rereading only; leave the final portal action manual.
5. Cover live stale/ambiguous/end-of-queue only if a natural safe case is available. Keep the already green automated fixtures distinct from portal-real evidence.
6. After all live work, perform adversarial review, final test gates, standalone ZIP verification, clean-extraction smoke, update this handoff, and push only `codex/atos-tce-unified`.

## 2026-09-27 — reauthenticated queue and accepted-but-unconfirmed navigation

- Chrome QA was already running under the DevTools connection. The user had reauthenticated manually; the portal shell and process list were reachable. No credentials or session material were read.
- Restored the sector process list by opening the portal's **Proc./Doc. Eletrônicos no Setor** view. One informational “Limite de 10 Abas” dialog appeared and was accepted. The list loaded; no official scan was rerun and scan 10 remains the source snapshot.
- The extension and Mesa both reported connected. Clicked **Próximo processo** exactly once. The extension accepted a target request, then completed its bounded wait without confirming the target form. Its diagnostic was `accepted_unconfirmed`; the portal remained on the list and no act form was confirmed.
- The extension kept both **Preencher formulário atual** and **Próximo processo** disabled after that result. Do not retry or submit another target request until the accepted request is reconciled through the normal portal/extension UI. Do not read or copy the target identity from extension state.
- No fill request was issued by this click, no act fields were changed, and no final action was taken. The previously recorded Task 10 fill remains the only real fill evidence.
- Structural check: the authenticated portal page and sector list frames were complete; no act form was found. The selected marker was not independently re-compared to scan 10 in this checkpoint.
- No source code changed and no tests ran. Before this handoff update, Git was clean on `codex/atos-tce-unified` at `cb1d305e47aba80dcb0e41342c6b22c7fe29fde3`, equal to `origin/codex/atos-tce-unified`.

### Resume from this checkpoint

1. Keep the current Chrome QA session and do not repeat the accepted navigation request. First inspect the extension diagnostic and portal frame state through the official UI; continue only after the pending target is resolved or safely reset and exact identity is confirmed.
2. Recompare the selected portal marker with scan 10 before any further queue navigation. Do not rerun the official scan.
3. Continue the remaining real Task 10 cases only after the portal opens an exact, eligible case; fill and reread only, with final **Complementar Ato** kept manual.
4. Complete live Next Process matrix cases only when naturally available; retain fail-closed status for stale/ambiguous and end-of-queue unless the live portal provides safe evidence.
5. Finish final review, all project gates, standalone ZIP verification, and clean-extraction smoke; then update this handoff and push only `codex/atos-tce-unified`.

## 2026-09-27 — offline gates and standalone package

- Integrated gate: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\verify-project.ps1` from `work/tce-extractor` exited 0. Seven stages passed; 1,260 checks executed, 1,258 passed, 0 failed, 2 skipped.
- Full supplemental Python suite: `python -m unittest discover -s . -p 'test_*.py' -q` from `work/tce-extractor` exited 0; 529 tests ran, 520 passed, 0 failed, 9 skipped. The run emitted the existing PyMuPDF deprecation and expected simulated HTTP/CLI warnings.
- Built a fresh standalone package to `tmp/goal-package-2026-09-27.zip`, leaving `dist/Atos-TCE-portable.zip` untouched. The builder reused the pinned runtime. Package: 96,155,474 bytes, 516 entries, runtime included (430 files), extension version 0.1.0; SHA-256 `216f10546370c1215ee0aef6554b397c33b4c562fa4b46bf98409b8c47f55627`.
- The fresh package hash is identical to the existing `dist/Atos-TCE-portable.zip`; no promotion/rotation or overwrite was needed. `START.cmd` selects the bundled Python runtime.
- `verify-package.ps1` passed twice without `-SkipSmoke`; each clean extraction reported health `ok`, API v1/schema 7, zero process data, and extension 0.1.0. Both runs printed a `taskkill` Access Denied warning, then cleanup checks confirmed the exact extraction root removed, no package child process, and the smoke port closed. Record that warning alongside the passing result.
- Final two-axis review against `origin/main...HEAD` completed with read-only Standards and Spec reviewers; findings are recorded below.
- The live accepted-but-unconfirmed navigation and remaining Task 10 cases are unchanged and remain the only real-portal blockers. No source code changed in this block.

## 2026-09-27 — final two-axis review

- Fixed point: `origin/main` at `b1d41e848c39cb61947b011501925c40f86793fb`; merge-base equals that SHA. Review diff was `git diff origin/main...HEAD` (151 commits at review time).
- Standards axis: the repo's `AGENTS.md` says the code source of truth is `work/tce-extractor`, while `docs/ESTRUTURA.md` and `README.md` say root `app/` and `extension/` are supported and `work/tce-extractor` is legacy. This is an unresolved documentation authority conflict; no code change was made. The reviewer also noted a judgement-call Data Clumps smell for the process/interested identity pair across navigation layers; no functional defect was established.
- Spec axis: live stale/ambiguous/end-of-queue Next Process cases and the remaining Task 10 cases are incomplete. No high-confidence out-of-scope or incorrect implementation finding was reported. The spec does not define an expected decision status for weak legal matches with hard conflicts.
- The reviewer initially marked package acceptance pending based on the earlier handoff text. Two subsequent clean-extraction smokes passed with health `ok`; that package finding is superseded by the later evidence above.
- Overall goal remains active because portal-real acceptance is incomplete. Do not promote to `main` or claim completion.

## 2026-09-27 — Chrome QA foreground e marcador divergente

- O Chrome QA já estava conectado ao MCP em `127.0.0.1:9222`; a página da Área Restrita foi selecionada e trazida para primeiro plano. A Mesa Local e a extensão `ATOS TCE — Ponte da Mesa` v0.1.0 Enabled continuam abertas no mesmo perfil.
- A página autenticada está na lista de processos (`ProcessonoSetor.asp`); o frame da lista está completo e contém a tabela. Não foi aberto formulário de ato neste checkpoint.
- Comparação somente de leitura entre o scan oficial 10 e os controles da lista: o seletor que `extension/lib/area-snapshot.js` identifica por metadados como marcador (índice DOM 7, 73 opções, seleção na posição 0) não corresponde ao marcador persistido no scan 10, nem pelo rótulo normalizado nem pelo valor. Os outros dois candidatos (índices 8 e 11) só correspondem porque o texto da linha ancestral menciona marcador; também não correspondem ao scan.
- A checagem usou hashes locais para comparar os valores, sem imprimir os identificadores do marcador. Nenhum seletor foi alterado. Não foi repetido o scan oficial, o comando Próximo Processo, nem qualquer preenchimento ou ação final.
- Este estado bloqueia navegação/fill live seguros até que a operadora restaure manualmente na Área Restrita o mesmo marcador usado pelo scan 10. Depois, revalidar a correspondência e reconciliar a navegação aceita anteriormente antes de emitir qualquer novo comando.
- Nenhum código/teste foi alterado ou executado neste checkpoint. A janela do Chrome QA está aberta e em primeiro plano; a intervenção humana necessária é somente selecionar novamente o marcador correto na lista e avisar quando a página terminar de carregar.

- A captura estrutural L0 previamente autorizada foi salva em `tmp/portal-lab/2026-09-27-foreground-session/raw/area-restrita-l0.json` (9 frames; 1 seletor de marcador; 5.061 bytes). O caminho está coberto por `.gitignore`; verificação confirmou ausência de valores, texto de página e campos de sessão.
