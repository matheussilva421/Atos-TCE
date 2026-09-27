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

1. Have the operator manually authenticate in the already-open Chrome QA window; do not handle credentials or session tokens.
2. Recheck the page/frame structure and extension state. Restore the normal sector process list through the portal's UI and compare the selected marker with scan 10 without rerunning the official scan.
3. Reconcile the Mesa selection with the last confirmed navigation result before clicking **Próximo processo** again. Do not repeat command 66 blindly.
4. Continue Task 10 only on exact eligible identities, filling and rereading only; leave the final portal action manual.
5. Cover live stale/ambiguous/end-of-queue only if a natural safe case is available. Keep the already green automated fixtures distinct from portal-real evidence.
6. After all live work, perform adversarial review, final test gates, standalone ZIP verification, clean-extraction smoke, update this handoff, and push only `codex/atos-tce-unified`.
