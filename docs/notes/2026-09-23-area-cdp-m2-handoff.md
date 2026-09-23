# M2 CDP comparison handoff — 2026-09-23

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
  the QA profile is not attached to CDP and when the scan command fails.

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

At handoff creation, the implementation and this note are not yet committed.
Preserve the pre-existing untracked `work/tce-extractor/.codex-live-pilot.py`;
do not stage it. After commit/push, update this section with the commit SHA and
push result. M2 remains pending the live QA scan and comparison.
