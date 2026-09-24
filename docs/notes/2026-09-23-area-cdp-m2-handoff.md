# M2 CDP comparison handoff — 2026-09-23

## Current status — live comparison attempt

M2 remains **incomplete**. The user asked to reuse existing evidence and not
repeat the 40-page portal scan. The complete page-level CDP payload is not
available locally, so do not describe M2 as passed.

Available comparison report: `data/logs/area-compare.json`, timestamped
2026-09-23 08:38. It compares a first-page CDP sample of 30 rows with the latest
extension scan of 1,198 rows. Scope and stable marker ID match
(`sector_finalistic`, marker value `5159`); the 30 overlapping rows have no
classification or act-ID mismatches. The sample omitted 1,168 Mesa rows, so
`equal` is false and this is only a partial check.

A later scanner attempt briefly produced an aggregate for pages 27–40: 14 of 40
pages, 419 unique rows (176 pending, 243 completed), same scope and marker
value. Its row-level JSON was overwritten when a subsequent attempt started;
the counts cannot be compared against the Mesa scan. That later attempt exposed
two scanner defects: it accepted page 27 while waiting to reset to page 1, then
mistook reaching page 40 for complete coverage; it also treated the changing
count in the marker label (1198→1199) as a marker change despite stable value
5159. The user stopped a new full scan and explicitly asked not to repeat it.
The Chrome portal was left on page 1; its manually selected marker value is
still 5159.

The scanner now waits for the exact expected page, verifies consecutive page
numbers and requires `pagesVisited == total_pages`. Marker continuity uses the
stable option value, falling back to the label only when no value exists. The
comparator applies the same marker identity rule and reports/rejects incomplete
CDP page coverage. These changes have focused regression tests.

Do not start another full scan unless the user requests resuming M2. To resume,
confirm the user wants the long portal traversal, ensure the authenticated QA
tab still has the intended human-selected marker, run the command in section 6
of `2026-09-21-guia-reexecucao-testes-mesa-local.md`, and compare only after the
scanner exits 0 and writes the full JSON. The latest persisted extension scan
remains ID 5: 1,198 rows (482 pending, 716 completed), marker value 5159.

## Result

The failed comparison came from two sequential issues in the command path:

1. `scan-area-cdp.ps1` evaluated `Split-Path -Parent $PSScriptRoot` while binding
   its parameters. In the user's Windows PowerShell invocation,
   `$PSScriptRoot` was empty at that point, so the scanner stopped before
   connecting to Chrome and redirected an error message into `area-cdp.json`.
2. Windows PowerShell 5.1 redirection writes UTF-16LE with a BOM, while
   `compare-area-scans.py` previously read only UTF-8.

The scanner now derives `RepoRoot` after parameter binding. The comparison
reader accepts BOM-marked UTF-16 and UTF-8, and reports malformed text as a
normal `ComparisonError`. The command example no longer advertises a nonexistent
`-Output` parameter. The M2 runbook checks that the QA profile has an active CDP
port and stops before comparing a failed/incomplete scan.

The file currently at `data/logs/area-cdp.json` is a PowerShell error message,
not a portal snapshot. It must be replaced by a successful scan before running
the comparison. The live Chrome QA profile was not available during this run:
the known QA profile had no `DevToolsActivePort`, and the port recorded by the
default Chrome profile did not answer locally. Therefore M2 real remains
**pending**, with no conclusion about scan equality.

## Follow-up attempt

The user then ran the M2 commands while the target profile still had no
`DevToolsActivePort`. The initial guard correctly stopped. The subsequent
commands were entered anyway, so the scanner wrote its missing-port diagnostic
to `area-cdp.json`; the comparer correctly rejected that text as non-JSON. This
was not a portal scan or a comparison mismatch. The target profile directory
contains its Chrome data and extension folder but had neither an active port
file nor a profile lock at inspection time. The runbook now starts this profile
with `--remote-debugging-port=9222`, waits for its endpoint, and opens without
a URL so the user can paste the Mesa session URL in the address bar.

The runbook's Chrome QA launch section was updated after this attempt: it now
checks for an existing profile lock, launches the installed Chrome binary with
the custom QA data directory and CDP port, waits up to 15 seconds for
`DevToolsActivePort`, and verifies `/json/version` before scanning. The user
should stop if any guard fails; the CDP scan and comparison must not be run
after an earlier `throw`.

## Changes

- `scripts/scan-area-cdp.ps1`: resolve the default repository root in the script
  body, after parameter binding.
- `scripts/compare-area-scans.py`: accept UTF-16LE/BE BOM and UTF-8 scan files;
  correct the invocation example.
- `tests/test_cdp_fallback.py`: regression test invokes Windows PowerShell with
  a temporary profile and proves it reaches the expected missing-CDP-port
  check without failing in `Split-Path`.
- `tests/test_compare_area_scans.py`: regression test reads a PowerShell-style
  UTF-16 JSON file.
- `docs/notes/2026-09-21-guia-reexecucao-testes-mesa-local.md`: fail fast when
  the QA profile is not attached to CDP or the scan command fails; start the QA
  profile with CDP and verify its endpoint before scanning.

## Validation

- RED confirmed for each regression before its implementation change.
- `python -m unittest discover -s tests -p test_cdp_fallback.py -v`: 15 passed.
- `python -m unittest discover -s tests -p test_compare_area_scans.py -v`: 12
  passed.
- `python -m unittest discover -s tests -p 'test_*.py' -q`: 573 run, 572 passed,
  0 failed, 1 skipped.
- `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass
  -File .\work\tce-extractor\verify-project.ps1`: 1,258 executed, 1,256
  passed, 0 failed, 2 skipped; all seven stages passed.
- The official gate was rerun after the Chrome QA launch instructions changed:
  same result, all seven stages passed.
- `git diff --check`: passed in the official gate.
- The live comparison was attempted against the failed output file and correctly
  stopped with a JSON parse error. No portal scan was performed in this run.

## Resume M2

Start the Chrome QA instance with the existing authenticated portal session and
the documented profile. From the repository root, use:

```powershell
$qaProfile = "$env:LOCALAPPDATA\AtosTCE\perfil-qa-20260921"
if (-not (Test-Path -LiteralPath (Join-Path $qaProfile 'DevToolsActivePort'))) {
    throw "Chrome QA is not active with CDP on this profile: $qaProfile"
}
New-Item -ItemType Directory -Force data\logs | Out-Null
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\scripts\scan-area-cdp.ps1 -ChromeUserData $qaProfile 1> data\logs\area-cdp.json 2> data\logs\area-cdp-diagnostics.log
if ($LASTEXITCODE -ne 0) {
    Get-Content -LiteralPath data\logs\area-cdp-diagnostics.log
    throw 'CDP scan failed; do not compare its output.'
}
Get-Content -LiteralPath data\logs\area-cdp-diagnostics.log
python scripts/compare-area-scans.py --cdp-json data\logs\area-cdp.json --db data\atos-tce.db --json data\logs\area-compare.json
if ($LASTEXITCODE -ne 0) { throw 'M2 is not equal; inspect data\logs\area-compare.json.' }
```

M2 passes only if the command exits `0` and the report says `"equal": true`,
with the same marker and source scope as the latest extension scan. The latest
persisted extension scan at handoff time was `sector_finalistic`, marker
`PROFESSOR - IPERN (1198)` / value `5159`, 1,198 rows (482 pending, 716
completed). Keep the portal marker human-selected.

## GitHub and remaining work

Commits `fe95da8` (`fix: repair M2 CDP scan comparison`), `61719fc`
(`docs: record M2 CDP handoff status`), and `9c1f38d`
(`docs: clarify Chrome QA CDP launch`) are pushed to
`origin/codex/mesa-local-refactor`. The pre-existing untracked
`work/tce-extractor/.codex-live-pilot.py` remains untouched. M2 remains pending
the live QA scan and comparison.
