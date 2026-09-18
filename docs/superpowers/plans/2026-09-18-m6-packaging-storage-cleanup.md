# M6 — Portable Packaging, Storage Cleanup and Legacy Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Produce the new archive-free portable ZIP, eliminate operational dependency on work/tce-extractor/portable, safely reclaim duplicated storage, and retire the legacy surface only after verified equivalence.

**Architecture:** First promote the few legacy engines still used by adapters into root application modules. Then build the portable package exclusively from root app/ + extension/ + runtime. Storage cleanup is receipt-driven and fail-closed: no old archive/build is deleted unless every unique PDF it contains is already represented in the canonical data archive.

**Tech Stack:** Python standard library, PowerShell packaging, existing fixed runtime manifest/hashes, unittest/node:test, Git tags.

**Spec:** docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md

## Global Constraints

- Standard portable ZIP contains no process archive.
- Canonical data/ survives application upgrades untouched.
- Keep only current and previous standard builds.
- Backup containing PDFs is an explicit user action, not a release artifact.
- Cleanup defaults to dry-run.
- No cleanup may delete .git, data/, the current source tree, or the last unique PDF copy.
- Legacy runtime removal happens only after M1-M5 exit gates are green and a real supervised fill has succeeded.
- Final act submission remains manual.

## File map

Create packaging/build-portable.ps1, packaging/verify-package.ps1, packaging/runtime-manifest.json and packaging/licenses/. Create scripts/storage-audit.py, cleanup-storage.py and backup.py. Promote remaining collector/analysis runtime dependencies into app/. Modify START.cmd and README.md. Delete legacy runtime only in the final task.

### Task 1: Remove root application imports from work/tce-extractor/portable

**Files:**
- Create: app/econtas/runtime/Coletar-Processos-TCE.ps1
- Create: app/econtas/runtime/TcePortable.Core.psm1
- Create: app/econtas/runtime/TceFrozenQueue.psm1
- Create: app/econtas/runtime/TcePortal.Driver.js
- Create: app/analysis/engine/ modules required by the M4 adapter
- Modify: app/econtas/collector.py
- Modify: app/analysis/legacy_adapter.py
- Modify: tests/test_econtas_acquisition.py
- Modify: tests/test_analysis_service.py

**Interfaces:**
- Existing CollectorRequest and LegacyAnalysisAdapter signatures do not change.
- After this task, grep of root app/ for work/tce-extractor must return no runtime imports/paths.

- [ ] **Step 1: Write a failing dependency-boundary test**

~~~python
from pathlib import Path
import unittest

class NoLegacyPathTests(unittest.TestCase):
    def test_root_app_has_no_operational_legacy_path(self):
        offenders = []
        for path in Path("app").rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ps1", ".psm1", ".js"}:
                text = path.read_text(encoding="utf-8-sig", errors="ignore")
                if "work/tce-extractor" in text or "work\\tce-extractor" in text:
                    offenders.append(str(path))
        self.assertEqual(offenders, [])
~~~

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_no_legacy_paths -v

Expected: collector/analysis adapters still reference legacy paths.

- [ ] **Step 3: Promote only required proven code**

For e-Contas, copy the four proven runtime files listed above first, preserve their existing tests/behavior, then update collector.py to point at app/econtas/runtime/Coletar-Processos-TCE.ps1.

For analysis, move the functions actually reached by LegacyAnalysisAdapter into app/analysis/engine with explicit imports. Do not carry package_audit, menu, auto-submit, extension exporter or HTML-generation code unless a root feature still calls it.

Replace sys.path manipulation with normal app imports.

- [ ] **Step 4: Run full regression**

Run:
- all root Python tests;
- current PowerShell collector tests against the promoted modules;
- existing analysis tests whose behavior was promoted.

Expected: no behavioral change and dependency-boundary test PASS.

- [ ] **Step 5: Commit**

~~~text
git add app tests
git commit -m "refactor: promote remaining runtime engines"
~~~

### Task 2: Storage inventory and canonical-copy verifier

**Files:**
- Create: scripts/storage-audit.py
- Create: tests/test_storage_audit.py

**Interfaces:**
- audit_storage(repo_root: Path, data_root: Path) -> StorageAudit
- categories: canonical_data, dist, outputs, versions, staging, temp, legacy_archive, source, unknown.
- for every candidate deletion tree containing PDFs, report unique_pdf_count, bytes, and missing_from_canonical_sha256.
- CLI: python scripts/storage-audit.py --repo-root . --data-root data --json PATH

- [ ] **Step 1: Write failing audit test**

Create canonical blob A plus an old Versions tree containing duplicate A and unique B. Assert:
- duplicate A is reclaimable;
- unique B sets missing_from_canonical_sha256 to B hash;
- candidate is not safe_to_delete.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_storage_audit -v

Expected: module missing.

- [ ] **Step 3: Implement audit**

Protected roots:
- .git
- app
- extension
- packaging
- scripts
- tests
- docs
- data
- current dist build
- previous dist build.

Candidate historical roots include existing work/tce-extractor/outputs, work/tce-extractor/Versions, .package-staging-* and staging-* directories when present. The tool reports only; it never deletes.

- [ ] **Step 4: Run against real checkout**

Run: python scripts/storage-audit.py --repo-root . --data-root data --json data/logs/storage-audit.json

Expected: a byte total per category and explicit safe/unsafe candidates.

- [ ] **Step 5: Commit**

~~~text
git add scripts/storage-audit.py tests/test_storage_audit.py
git commit -m "feat: audit duplicated project storage"
~~~

### Task 3: Explicit full backup and restore manifest

**Files:**
- Create: scripts/backup.py
- Create: tests/test_backup.py

**Interfaces:**
- create_backup(data_root: Path, destination: Path) -> BackupManifest
- backup ZIP contains atos-tce.db, archive blobs and manifest.json.
- manifest includes schema_version, created_at, db_sha256, file_count, total_bytes and each blob SHA-256.
- CLI requires --output; no automatic scheduled backup is introduced.

- [ ] **Step 1: Write failing backup test**

Create tiny data root, build backup, inspect ZIP and verify manifest hashes match extracted bytes.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_backup -v

Expected: backup module missing.

- [ ] **Step 3: Implement backup**

Write to output.tmp.zip first, fsync/close, validate ZIP CRC and manifest, then os.replace to requested output. Refuse output paths inside data/archive to avoid recursive backup.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_backup -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add scripts/backup.py tests/test_backup.py
git commit -m "feat: add explicit full archive backup"
~~~

### Task 4: New archive-free portable builder

**Files:**
- Create: packaging/build-portable.ps1
- Create: packaging/verify-package.ps1
- Copy: work/tce-extractor/portable/runtime-manifest.json -> packaging/runtime-manifest.json
- Copy required license documentation -> packaging/licenses/
- Modify: START.cmd
- Create: tests/test_packaging_contract.py

**Interfaces:**
- packaging/build-portable.ps1 -OutputPath dist/Atos-TCE-portable.zip
- ZIP includes app/, extension/, runtime/, START.cmd, README.md and required licenses.
- ZIP must not contain data/, acervo-tce/, PDFs, private logs, browser profiles or pairing tokens.
- build uses the same fixed runtime versions/hashes currently enforced by build-portable-runtime.ps1.

- [ ] **Step 1: Write failing package allowlist test**

~~~python
FORBIDDEN = ("data/", "acervo-tce/", "dados-locais/", "profile/")
with ZipFile(zip_path) as zf:
    names = [name.replace("\\", "/") for name in zf.namelist()]
    self.assertTrue(any(name.startswith("app/") for name in names))
    self.assertTrue(any(name.startswith("extension/") for name in names))
    self.assertFalse(any(name.lower().endswith(".pdf") for name in names))
    for prefix in FORBIDDEN:
        self.assertFalse(any(name.startswith(prefix) for name in names))
~~~

- [ ] **Step 2: Verify RED**

Run packaging contract against a fixture ZIP or absent target and confirm failure.

- [ ] **Step 3: Implement builder by adapting, not discarding, existing supply-chain checks**

Carry forward:
- fixed Python version/hash;
- fixed Tesseract version/hash and traineddata;
- fixed dependency versions/hashes;
- HTTPS source enforcement;
- safe staging target validation;
- license materialization.

Change source allowlist to root app/, extension/, START.cmd and README. Never copy data/.

Update START.cmd:

~~~bat
@echo off
setlocal
cd /d "%~dp0"
set "EMBEDDED=%~dp0runtime\python\python.exe"
if exist "%EMBEDDED%" (
  "%EMBEDDED%" -m app.main %*
) else (
  python -m app.main %*
)
exit /b %ERRORLEVEL%
~~~

- [ ] **Step 4: Build and verify**

Run:

~~~text
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build-portable.ps1 -OutputPath dist\Atos-TCE-portable.zip
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\verify-package.ps1 -ZipPath dist\Atos-TCE-portable.zip
python -m unittest tests.test_packaging_contract -v
~~~

Expected: PASS and ZIP size is near application/runtime size rather than private archive size.

- [ ] **Step 5: Commit**

~~~text
git add packaging START.cmd tests/test_packaging_contract.py
git commit -m "build: add archive-free portable package"
~~~

### Task 5: Clean extraction smoke and build retention

**Files:**
- Modify: packaging/verify-package.ps1
- Create: scripts/rotate-builds.py
- Create: tests/test_build_retention.py

**Interfaces:**
- verifier extracts to a unique tmp/package-test-ID directory.
- on success, extraction is deleted.
- on failure, extraction path is printed and preserved.
- rotate_builds(dist_root) keeps Atos-TCE-portable.zip and Atos-TCE-portable.previous.zip only.

- [ ] **Step 1: Write failing retention tests**

Seed current, previous and three timestamped old ZIPs. Assert dry-run reports old ZIPs and apply keeps exactly two canonical names.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_build_retention -v

Expected: module missing.

- [ ] **Step 3: Implement smoke and rotation**

Smoke must:
1. extract cleanly;
2. start embedded START.cmd with --no-browser on an ephemeral port and isolated data root;
3. wait for /api/v1/health;
4. verify extension manifest and SQLite creation;
5. stop service;
6. delete extraction on PASS.

Rotation happens only after new package verification passes.

- [ ] **Step 4: Run complete portable smoke**

Expected: package starts with an empty data root and does not contain the real ~700-process archive.

- [ ] **Step 5: Commit**

~~~text
git add packaging scripts/rotate-builds.py tests/test_build_retention.py
git commit -m "build: verify clean portable extraction and retain two builds"
~~~

### Task 6: Receipt-driven cleanup tool

**Files:**
- Create: scripts/cleanup-storage.py
- Create: tests/test_cleanup_storage.py

**Interfaces:**
- CLI default is dry-run.
- Apply requires --apply --audit data/logs/storage-audit.json.
- A candidate is deletable only when audit.safe_to_delete is true and canonical data exists.
- tool accepts only paths discovered by the audit, never arbitrary deletion paths.

- [ ] **Step 1: Write failing safety tests**

Cases:
- unsafe candidate with one missing SHA -> refuse;
- protected data/ -> refuse even if manually added to audit fixture;
- safe old Versions extraction -> dry-run lists, apply removes;
- current/previous dist -> refuse;
- symlink/reparse point escaping candidate root -> refuse.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_cleanup_storage -v

Expected: cleanup module missing.

- [ ] **Step 3: Implement fail-closed cleanup**

Before each deletion, re-read the candidate and verify its size/file count has not changed from the audit receipt materially; if changed, require a new audit. Log every removed path and bytes to data/logs/storage-cleanup-UTC.json.

Do not delete work/tce-extractor/acervo-tce in this task unless the audit confirms all of its unique PDFs exist in canonical data and the M1 migration receipt is present.

- [ ] **Step 4: Run dry-run on real checkout**

Run: python scripts/cleanup-storage.py --audit data/logs/storage-audit.json

Review categories and expected reclaimed bytes before apply.

- [ ] **Step 5: Apply only verified candidates**

Run: python scripts/cleanup-storage.py --audit data/logs/storage-audit.json --apply

After apply, rerun storage-audit and compare actual reclaimed bytes.

- [ ] **Step 6: Commit code only**

~~~text
git add scripts/cleanup-storage.py tests/test_cleanup_storage.py
git commit -m "feat: add verified storage cleanup"
~~~

### Task 7: Make new app/extension/package the default and retire legacy surface

**Files:**
- Modify: README.md
- Modify: docs/ESTRUTURA.md
- Delete only after gates: obsolete work/tce-extractor portable UI/extension/menu/packagers and superseded active scripts.
- Preserve historical notes in Git history; do not move private outputs into Git.

**Interfaces:**
- START.cmd is the single normal launcher.
- root extension/ is the supported extension.
- packaging/build-portable.ps1 is the supported build.
- no supported runtime path depends on work/tce-extractor/portable.

- [ ] **Step 1: Create safety tag before deletion**

Run:

~~~text
git tag pre-legacy-retirement
git push origin pre-legacy-retirement
~~~

If tag push is unavailable, stop deletion until the tag exists locally and a remote backup is confirmed.

- [ ] **Step 2: Run every gate before deletion**

Required:
- all root Python tests;
- root extension npm test;
- promoted collector PowerShell tests;
- package clean-extraction smoke;
- M2 real read-only Area scan;
- M3 real bounded acquisition;
- M4 analysis equivalence;
- M5 supervised fill without final submit.

Any failure blocks deletion.

- [ ] **Step 3: Inventory remaining references**

Run a repository search for work/tce-extractor/portable, INICIAR.cmd, ABRIR-MESA, automation-controller.js, real_send_enabled and AUTO_SUBMIT. Classify documentation references as historical versus runtime references. Runtime references must be zero before removal.

- [ ] **Step 4: Delete obsolete runtime surface**

Delete only files no longer referenced. Expected removals include the old portable sidepanel/automation controller, old menu launchers, duplicate package builders and auto-submit qualification runtime. Do not delete root promoted collector/analysis engines.

- [ ] **Step 5: Run full gates again**

The same gate set must pass after deletion.

- [ ] **Step 6: Update documentation and commit**

README describes:
- START.cmd;
- Mesa workflow;
- root extension installation;
- archive-free portable ZIP;
- explicit backup;
- storage cleanup;
- manual final submission.

Commit:

~~~text
git add -A
git commit -m "refactor: retire legacy Atos-TCE runtime surface"
~~~

- [ ] **Step 7: Create completion tag**

Run:

~~~text
git tag mesa-migration-complete
git push origin mesa-migration-complete
~~~

## M6 Exit Gate

- Standard ZIP contains application/runtime only, no process PDFs.
- Canonical data/ is independent from application versions.
- Current and previous build are the only retained standard ZIPs.
- Full archive backup is explicit.
- Storage cleanup is SHA/receipt verified and has reclaimed redundant local copies.
- No supported runtime depends on work/tce-extractor/portable.
- START.cmd and root Mesa are the normal workflow.
- Root extension is thin and has no final-submit protocol.
- Final supervised regression is green before the legacy surface is removed.
