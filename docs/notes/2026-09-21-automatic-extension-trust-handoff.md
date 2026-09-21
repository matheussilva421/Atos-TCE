# Handoff — automatic Mesa/extension trust

Data: 2026-09-21
Branch: `codex/mesa-local-refactor`
Implementation SHA: `489a2cc`

## Resultado

The six-digit extension pairing flow was removed. The shipped Manifest V3
extension now has a stable public key and trusted id
`nhpklhieopdbomkojifcengjaklabjng`. The Mesa accepts only that exact
`chrome-extension://` origin at `POST /api/v1/bridge/register`.

The service worker owns Mesa calls. `chrome.storage.local` is the credential
source of truth, registration is single-flight, missing or rejected credentials
recover automatically once, and network failures preserve stored credentials.
The sidepanel and Mesa web UI no longer expose Pair, Parear, Reparear, code or
repair controls. Mesa session bootstrap and one-time handoff remain available.

## Commits in this implementation block

- `0b9aec5` — pin trusted extension identity
- `9a74fe1` — add automatic extension registration
- `93b668f` — auto-recover extension credentials
- `6462074` — centralize Mesa access in service worker
- `b3cef03` — remove extension pairing UI
- `ffab274` — remove Mesa pairing controls
- `28a9854` — retire manual bridge pairing routes and state
- `489a2cc` — remove remaining pairing dependencies and verify package identity

## Validation

- `npm test --prefix extension`: 123/123 passed.
- `node --test app/web/tests/*.test.mjs`: 16/16 passed.
- `python -m unittest tests.test_web_suite -v`: 2/2 passed.
- `python -m unittest tests.test_extension_identity tests.test_bridge -q`: 28/28 passed.
- `python -m unittest tests.test_api_server -q`: 84/84 passed.
- `python -m unittest tests.test_area_scan tests.test_main -q`: 35/35 passed.
- `python -m unittest tests.test_packaging_contract -q`: 12/12 passed.
- `python -m unittest discover -s tests -p 'test_*.py' -q`: 559/559 passed.
- `verify-project.ps1`: 1,254 executed, 1,252 passed, 0 failed, 2 expected skips.
  All seven stages passed: extension, web, portable Python, PowerShell,
  package/audit, automation and diff check.
- Package build: `dist/Atos-TCE-portable.zip`, 512 entries, runtime 430 files,
  SHA-256 `706ae6dc98b844e6e383bea7510ae95bb939c389245239d0d5c27f942ef7315c`.
- `verify-package.ps1 -SkipSmoke`: passed; manifest key/id parity is covered by
  source and built-package tests.

The literal `python -m unittest discover -s . -p 'test_*.py' -q` command does
not discover this checkout's non-package `tests/` directory and returned
`NO TESTS RAN` with code 5. The effective full suite is the explicit
`-s tests` command recorded above.

## Manual acceptance matrix

No clean Chrome/Edge QA profile was available for a new physical run in this
coding session. The entries below distinguish automated evidence from the
manual browser steps still required.

1. **PARTIAL** — launcher/API startup is covered by `test_api_server`; clean
   profile run with `START.cmd --data-root data --port 18743` remains manual.
2. **SKIPPED** — extension reload in a clean profile.
3. **PASS_STATIC** — no code/password/pairing action is present in the shipped
   extension or Mesa web UI tests.
4. **PASS_AUTOMATED** — sidepanel state tests cover connecting/connected and
   offline labels; physical profile transition remains manual.
5. **PASS_AUTOMATED** — registration/status/authentication integration tests
   cover the registered client and persisted `last_seen_at`; live browser check
   remains manual.
6. **SKIPPED** — close/reopen Chrome clean-profile test.
7. **PASS_AUTOMATED** — server restart/token persistence tests pass; live
   browser restart test remains manual.
8. **PASS_AUTOMATED** — empty storage registration tests pass; DevTools removal
   of only `tce.bridge.token` remains manual.
9. **PASS_AUTOMATED** — stale-token 401 recovery and single retry tests pass;
   deliberately editing the token in DevTools remains manual.
10. **PASS_AUTOMATED** — untrusted registration origin returns 403 and invalid
    authenticated origin/token returns 401.
11. **PASS_AUTOMATED** — command claim/result integration tests pass.
12. **PASS_AUTOMATED** — manual form request is routed through the worker and
    `/api/v1/portal/manual-form` tests pass.
13. **PASS_STATIC** — pairing controls/routes/state are absent in both UIs;
    clean-profile visual confirmation remains manual.

No bearer token was recorded in this handoff or logs. No private key was
generated or committed; only the public Manifest V3 key is shipped.

## Retomada

Continue on `codex/mesa-local-refactor`. Reload the unpacked `extension/`
directory in a clean Chrome/Edge profile, start the Mesa with the bootstrap URL,
and execute manual cases 1–9 and 13. Preserve the untracked local file
`work/tce-extractor/.codex-live-pilot.py`; it is unrelated to this change.
