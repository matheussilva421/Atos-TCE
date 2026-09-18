# Atos-TCE — Plano Completo de Refatoração da Mesa

Este documento consolida o Master Plan e os marcos M1–M6 aprovados em 18/09/2026.



---

<!-- Source: docs/superpowers/plans/2026-09-18-master-mesa-refactor.md -->

# Atos-TCE Mesa Refactor — Master Implementation Plan

> **For agentic workers:** Execute the milestone plans in order. REQUIRED SUB-SKILL for implementation: superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Do not start a later milestone until the previous milestone Exit Gate is green.

**Goal:** Replace the tangled portable/menu/sidepanel-centered architecture with one Mesa-owned workflow while preserving the proven Área Restrita, e-Contas, analysis, PDF and form-filling behavior.

**Architecture:** This is a strangler migration. M1-M5 add and validate the new system beside the legacy runtime. M6 promotes the remaining proven engines, creates the archive-free portable package, verifies canonical storage, and only then removes obsolete legacy runtime surfaces.

**Tech Stack:** Python, SQLite, vanilla web UI, Chrome/Edge MV3 extension, PowerShell compatibility/runtime adapters, existing Tesseract/PDF pipeline.

**Spec:** docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md

## Execution Order

### M1 — Foundation, SQLite and Read-Only Mesa

Plan: docs/superpowers/plans/2026-09-18-m1-foundation-sqlite-mesa.md

Delivers:
- root-level app/;
- SQLite schema v1;
- safe migration of the existing approximately 700 logical processes;
- canonical SHA-256 blob store;
- legacy-compatible process tree using hardlinks where supported;
- read-only Mesa;
- no removal of the legacy workflow.

Hard gate before M2:
- real archive dry-run completed;
- source archive remains untouched;
- imported processes visible in Mesa;
- no private data staged by Git.

Rollback: use the existing work/tce-extractor workflow unchanged.

### M2 — Área Restrita Integration

Plan: docs/superpowers/plans/2026-09-18-m2-area-restrita-integration.md

Depends on: M1.

Delivers:
- SQLite schema v2;
- authenticated Mesa session;
- persistent authenticated extension bridge;
- root thin extension scanner;
- Analisar Área Restrita action in Mesa;
- read-only CDP compatibility fallback;
- completed acts mapped to CONCLUÍDO.

Hard gate before M3:
- extension scan and CDP fallback agree on the same real marker/sample;
- no portal write occurs;
- legacy extension remains usable.

Rollback: use legacy extension/Área Restrita capture; M1 Mesa remains read-only.

### M3 — e-Contas Acquisition Controlled by Mesa

Plan: docs/superpowers/plans/2026-09-18-m3-econtas-acquisition.md

Depends on: M1 and M2.

Delivers:
- SQLite schema v3;
- Mesa acquisition jobs;
- automatic internal lots of 50;
- exact legacy frozen-queue compatibility;
- Mesa-owned selection of missing pending processes;
- proven legacy collector used as the initial download engine;
- new downloads canonicalized into the SHA blob store after each lot.

Hard gate before M4:
- bounded real acquisition downloads only requested process keys;
- authentication failures pause safely;
- one normal internal lot passes;
- legacy collector fallback remains available.

Rollback: invoke the proven legacy collector with the preserved queue contract.

### M4 — Analysis, Legal Rules and Evidence

Plan: docs/superpowers/plans/2026-09-18-m4-analysis-evidence.md

Depends on: M3.

Delivers:
- acquisition-only mode in the legacy collector to prevent duplicate analysis;
- automatic backend analysis after download;
- centralized PRONTO/REVISAR/ERRO decisions;
- backend legal-foundation-v3 parity;
- evidence API;
- PDF Range support;
- integrated field-source/PDF review.

Hard gate before M5:
- 10-process real equivalence sample passes;
- mandatory field values and evidence match legacy expectations;
- backend legal decisions match approved JS parity fixtures;
- each successful acquisition triggers analysis exactly once.

Rollback: disable the new analysis worker and use legacy progressive preparation.

### M5 — Thin Extension and Mesa-Driven Filling

Plan: docs/superpowers/plans/2026-09-18-m5-extension-filling.md

Depends on: M2 and M4.

Delivers:
- SQLite schema v4;
- backend fill-request state machine;
- backend fail-closed preflight;
- thin navigation/form-reader/filler extension;
- automatic Preencher ato flow;
- Preencher formulário atual manual fallback;
- no SUBMIT/SEND/AUTO_SUBMIT protocol.

Hard gate before M6:
- one real form is first tested read-only;
- at least five supervised real fills reread exactly as proposed;
- no final portal action is clicked by the new extension;
- legacy extension remains installed for rollback until M6.

Rollback: use the legacy extension while keeping the new Mesa/acquisition/analysis data.

### M6 — Packaging, Hybrid Archive, Storage Cleanup and Legacy Retirement

Plan: docs/superpowers/plans/2026-09-18-m6-packaging-storage-cleanup.md

Depends on: all prior milestones.

Delivers:
- SQLite schema v5;
- HOT / ARCHIVED / MISSING archive manager;
- optional external archive location with verified restore;
- promoted collector/analysis engines with no supported runtime dependency on work/tce-extractor/portable;
- storage audit;
- explicit full backup;
- archive-free portable ZIP;
- clean-extraction smoke;
- current + previous build retention;
- receipt-driven cleanup of Versions/staging/old ZIPs;
- final legacy runtime retirement.

Hard gate before any destructive cleanup:
- canonical archive contains every unique PDF SHA from the candidate deletion tree;
- storage audit says safe_to_delete=true;
- M1 migration receipt exists;
- full root tests and real M2-M5 gates are green;
- pre-legacy-retirement Git tag exists.

Rollback before final deletion: use pre-legacy-retirement tag plus canonical data/ archive.

## Schema Sequence

- M1: schema_version 1 — processes/documents/fields/workflow_events/jobs.
- M2: schema_version 2 — Área Restrita scans, bridge clients and extension commands.
- M3: schema_version 3 — acquisition job items and acquisition state.
- M4: no schema bump required unless an implementation need is explicitly proven; reuse v3 tables/fields.
- M5: schema_version 4 — portal fill requests.
- M6: schema_version 5 — canonical/external archive blob locations.

Every migration is transactional. metadata.schema_version changes only after the migration transaction commits.

## Security Invariants

- Local write APIs require an authenticated Mesa loopback session.
- Extension APIs require an independently paired bearer token bound to the extension client/origin.
- Pairing code is short-lived and attempt-limited.
- No credential, cookie, token, CPF or arbitrary absolute file path is accepted in portal snapshot payloads.
- PDF access is by SQLite document id, never arbitrary filesystem path.
- Root extension protocol never contains a final-submit command.
- Cleanup accepts audit-discovered candidates only and defaults to dry-run.

## Storage Invariants

- data/ is independent from application versions.
- One canonical SHA-256 blob owns each locally retained PDF byte sequence.
- data/archive/processos preserves the proven process-folder interface using hardlinks where supported.
- New downloads are canonicalized after acquisition.
- Standard ZIP contains no process archive.
- Full process/PDF backup is explicit, not part of release versioning.
- Versions, staging and package-test extractions are not permanent storage.
- No cleanup deletes the final verified copy of a unique SHA.

## Review Checkpoints

After every task:
1. run that task's exact tests;
2. review the diff;
3. commit the independently testable deliverable.

After every milestone:
1. run the full milestone Exit Gate;
2. record any private evidence under ignored data/logs or tmp only;
3. verify git status contains no private archive/runtime output;
4. do not proceed if a gate is red.

## Recommended Execution Mode

Use one isolated Git worktree/branch for the migration. Execute one milestone at a time. For each task, use a fresh implementation agent and a separate review pass before moving to the next task.

Do not parallelize tasks that mutate the same schema, protocol or portal behavior. In particular:
- M2 command/auth work is sequential;
- M3 collector/job integration is sequential;
- M4 analysis cutover must land before M5 fill preflight;
- M6 cleanup is always last.



---

<!-- Source: docs/superpowers/plans/2026-09-18-m1-foundation-sqlite-mesa.md -->

# M1 — Foundation, SQLite and Read-Only Mesa Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Create the root application, SQLite source of truth, safe import of the current ~700-process archive, and a read-only Mesa without changing legacy collection or portal automation.

**Architecture:** New code is added beside the legacy system. SQLite is the new read model; the current work/tce-extractor workflow remains the operational fallback until later milestones.

**Tech Stack:** Python 3 standard library, sqlite3, http.server, unittest, vanilla HTML/CSS/JavaScript, Windows CMD.

**Spec:** docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md

## Global Constraints

- Preserve the approximately 700 current logical processes.
- Never delete the last known copy of a document.
- New runtime data lives under ignored data/.
- Standard builds must not embed the process archive.
- No legacy runtime file is removed in M1.
- No auto-submit behavior is added.

## File map

Create app/core/models.py and store.py for domain persistence; app/archive/legacy_import.py for safe import; app/api/server.py for read-only HTTP; app/web/ for the Mesa; scripts/migrate-legacy.py for migration; tests/ for new tests; START.cmd for the new launcher.

### Task 1: Root layout and Git safety

**Files:**
- Create: app/__init__.py, app/core/__init__.py, app/archive/__init__.py, app/api/__init__.py
- Create: START.cmd
- Modify: .gitignore
- Test: tests/test_store.py

**Interfaces:**
- Produces importable package app.
- Produces ignored directories data/, dist/, tmp/.
- Produces launcher START.cmd forwarding arguments to python -m app.main.

- [ ] **Step 1: Write the failing import test**

~~~python
import importlib
import unittest

class PackageLayoutTests(unittest.TestCase):
    def test_packages_import(self):
        for name in ("app", "app.core", "app.archive", "app.api"):
            self.assertIsNotNone(importlib.import_module(name))
~~~

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_store.PackageLayoutTests -v

Expected: ModuleNotFoundError for app.

- [ ] **Step 3: Create package markers and update .gitignore**

Add allow rules for /app/**, /scripts/*.py, /tests/** and /START.cmd to the existing default-deny file. Add explicit ignores:

~~~gitignore
/data/
/dist/
/tmp/
~~~

Create START.cmd:

~~~bat
@echo off
setlocal
cd /d "%~dp0"
python -m app.main %*
exit /b %ERRORLEVEL%
~~~

- [ ] **Step 4: Verify GREEN and ignores**

Run:

~~~text
python -m unittest tests.test_store.PackageLayoutTests -v
git check-ignore data\atos-tce.db
git check-ignore dist\Atos-TCE-portable.zip
git check-ignore tmp\package-test
~~~

Expected: test PASS and all three paths ignored.

- [ ] **Step 5: Commit**

~~~text
git add .gitignore START.cmd app tests/test_store.py
git commit -m "chore: add root Mesa application skeleton"
~~~

### Task 2: SQLite schema v1

**Files:**
- Create: app/core/models.py
- Create: app/core/store.py
- Modify: tests/test_store.py

**Interfaces:**
- Store.open(path: Path) -> Store
- Store.upsert_process(record: ProcessRecord) -> int
- Store.get_process(process_id: int) -> dict | None
- Store.list_processes(status: str | None = None) -> list[dict]
- Store.replace_documents(process_id: int, documents: list[DocumentRecord]) -> None
- Store.replace_fields(process_id: int, fields: list[FieldRecord]) -> None
- Store.add_workflow_event(process_id: int, event_type: str, payload: dict) -> int
- Store.storage_summary() -> dict
- Store.schema_version == 1

- [ ] **Step 1: Write failing round-trip tests**

~~~python
from pathlib import Path
from tempfile import TemporaryDirectory
from app.core.models import ProcessRecord
from app.core.store import Store

def test_round_trip(self):
    with TemporaryDirectory() as td:
        store = Store.open(Path(td) / "atos-tce.db")
        process_id = store.upsert_process(ProcessRecord(
            process_key="102390/2026",
            interested="Pessoa Exemplo",
            interested_normalized="pessoa exemplo",
            source_scope="sector_finalistic",
            marker="PROFESSOR - IPERN - 2 RUBRICAS",
            status="PRONTO",
        ))
        store.add_workflow_event(process_id, "analysis_finished", {"status": "PRONTO"})
        loaded = store.get_process(process_id)
        self.assertEqual(loaded["process_key"], "102390/2026")
        self.assertEqual(loaded["events"][0]["event_type"], "analysis_finished")
        self.assertEqual(store.schema_version, 1)
~~~

Also test that two upserts for the same process_key + interested_normalized return the same id.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_store -v

Expected: import failure for app.core.models/store.

- [ ] **Step 3: Implement models and schema**

Define frozen dataclasses ProcessRecord, DocumentRecord and FieldRecord. Store.open must enable foreign_keys, WAL and create metadata, processes, documents, fields, workflow_events and jobs tables. Use UNIQUE(process_key, interested_normalized) for processes and parameterized SQL only.

Core schema:

~~~sql
CREATE TABLE processes (
  id INTEGER PRIMARY KEY,
  process_key TEXT NOT NULL,
  interested TEXT NOT NULL,
  interested_normalized TEXT NOT NULL,
  source_scope TEXT,
  marker TEXT,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(process_key, interested_normalized)
);

CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  process_id INTEGER NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL,
  event TEXT,
  title TEXT NOT NULL,
  relative_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  page_count INTEGER NOT NULL,
  classification TEXT,
  storage_state TEXT NOT NULL,
  UNIQUE(process_id, source_id)
);
~~~

Create matching fields, workflow_events and jobs tables exactly as described in the design spec.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_store -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add app/core tests/test_store.py
git commit -m "feat: add SQLite Mesa store"
~~~

### Task 3: Safe legacy archive import and SHA-256 deduplication

**Files:**
- Create: app/archive/legacy_import.py
- Create: scripts/migrate-legacy.py
- Create: tests/test_legacy_import.py

**Interfaces:**
- scan_legacy_archive(root: Path) -> LegacyScan
- import_legacy_archive(root: Path, data_root: Path, store: Store, apply: bool) -> ImportReport
- canonicalize_process_tree(data_root: Path, store: Store) -> ImportReport
- CLI: python scripts/migrate-legacy.py --archive-root PATH --data-root PATH [--apply]
- ImportReport fields: processes_seen, documents_seen, unique_pdfs, duplicate_pdfs, bytes_source, bytes_unique, copied_files, errors.

- [ ] **Step 1: Write failing deduplication tests**

~~~python
PDF = b"%PDF-1.4\nfixture\n%%EOF\n"

def test_duplicate_pdf_is_materialized_once(self):
    with TemporaryDirectory() as td:
        root = Path(td) / "legacy"
        data = Path(td) / "data"
        a = root / "processos" / "102390-2026" / "a.pdf"
        b = root / "processos" / "102391-2026" / "b.pdf"
        a.parent.mkdir(parents=True)
        b.parent.mkdir(parents=True)
        a.write_bytes(PDF)
        b.write_bytes(PDF)
        store = Store.open(data / "atos-tce.db")

        report = import_legacy_archive(root, data, store, apply=True)

        self.assertTrue(a.exists())
        self.assertTrue(b.exists())
        self.assertEqual(report.unique_pdfs, 1)
        self.assertEqual(report.duplicate_pdfs, 1)
        self.assertEqual(report.copied_files, 1)
~~~

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_legacy_import -v

Expected: import failure for legacy_import.

- [ ] **Step 3: Implement safe import**

Rules:
- recurse only below the supplied archive root and do not follow directory symlinks;
- hash PDFs in 1 MiB chunks;
- store one canonical physical blob at data/archive/blobs/AA/SHA256.pdf;
- materialize the legacy-shaped view under data/archive/processos/... using a hardlink to the canonical blob whenever the source and data root are on the same volume;
- use shutil.copy2 only when a hardlink cannot be created, and count those fallback copies separately in the migration report;
- scan process PDFs from known legacy process roots and explicitly exclude data/archive/blobs from recursive source discovery;
- verify the target hash before reusing an existing blob or process-view file;
- never unlink, rename or rewrite source files;
- default CLI mode is dry-run;
- --apply is required to materialize files;
- write a JSON receipt to data/logs/legacy-import-UTC.json;
- infer canonical process keys from existing folder/index metadata and upsert records into SQLite;
- expose canonicalize_process_tree for later acquisition jobs: it scans only data/archive/processos. For a newly downloaded unique PDF on the same volume, atomically move the verified bytes to the SHA blob path and recreate the process-view path as a hardlink to that blob. For an already-known SHA, replace the process-view file with a hardlink only after both hashes match. If hardlinks are unavailable, preserve a normal copy and report duplicated fallback bytes. It never touches a file outside data/archive/processos.

- [ ] **Step 4: Verify GREEN**

Run:

~~~text
python -m unittest tests.test_store tests.test_legacy_import -v
python scripts/migrate-legacy.py --archive-root tests\fixtures\legacy-archive --data-root tmp\m1-dry-run
~~~

Expected: tests PASS; dry-run performs no source mutation.

- [ ] **Step 5: Commit**

~~~text
git add app/archive scripts/migrate-legacy.py tests/test_legacy_import.py
git commit -m "feat: add safe legacy archive importer"
~~~

### Task 4: Read-only Mesa API

**Files:**
- Create: app/api/views.py
- Create: app/api/server.py
- Create: tests/test_api_server.py

**Interfaces:**
- GET /api/v1/health
- GET /api/v1/processes
- GET /api/v1/processes/ID
- GET /api/v1/storage
- GET /api/v1/documents/ID/pdf
- serve(store, data_root, host="127.0.0.1", port=18743)

- [ ] **Step 1: Write failing loopback API test**

~~~python
server = serve(store, data_root, port=0)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
port = server.server_address[1]
health = json.load(urlopen(f"http://127.0.0.1:{port}/api/v1/health"))
rows = json.load(urlopen(f"http://127.0.0.1:{port}/api/v1/processes"))
self.assertEqual(health["api_version"], 1)
self.assertEqual(rows["items"][0]["process_key"], "102390/2026")
~~~

Also assert that a nonexistent PDF is 404 and that no route accepts an arbitrary filesystem path.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_api_server -v

Expected: import failure for app.api.server.

- [ ] **Step 3: Implement explicit routes**

Use BaseHTTPRequestHandler and ThreadingHTTPServer. Serve PDFs only after resolving a document id from SQLite and confirming the resolved path remains beneath data_root. Do not create a generic file route.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_store tests.test_legacy_import tests.test_api_server -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add app/api tests/test_api_server.py
git commit -m "feat: add read-only Mesa API"
~~~

### Task 5: Read-only Mesa UI and launcher

**Files:**
- Create: app/web/index.html
- Create: app/web/app.js
- Create: app/web/app.css
- Create: app/main.py
- Modify: README.md
- Modify: tests/test_api_server.py

**Interfaces:**
- CLI: python -m app.main --data-root data --port 18743 [--no-browser]
- UI shows health, storage summary, process list, process detail, fields, documents and workflow history.
- UI has no collect, analyze or fill action yet.

- [ ] **Step 1: Add failing static-page test**

~~~python
body = urlopen(f"http://127.0.0.1:{port}/").read().decode("utf-8")
self.assertIn('id="process-list"', body)
self.assertIn('id="storage-summary"', body)
self.assertIn('src="/app.js"', body)
~~~

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_api_server -v

Expected: root page test fails.

- [ ] **Step 3: Implement minimal Mesa**

index.html must contain health-status, summary, storage-summary, process-search, process-list and process-detail elements. app.js fetches health/processes/storage and loads detail on click. app.main creates the data root, opens the store, starts the server, opens the default browser unless --no-browser, and stops cleanly on Ctrl+C.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_store tests.test_legacy_import tests.test_api_server -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add app/main.py app/web README.md tests/test_api_server.py
git commit -m "feat: add read-only Mesa"
~~~

### Task 6: Real archive migration rehearsal

**Files:**
- Modify code only if the rehearsal exposes a defect.
- Evidence is written only under ignored data/logs or tmp.

**Interfaces:**
- Input: work/tce-extractor/acervo-tce
- Output: new data/ archive and SQLite database.
- The legacy source remains untouched.

- [ ] **Step 1: Dry-run the real archive**

Run: python scripts/migrate-legacy.py --archive-root work\tce-extractor\acervo-tce --data-root data

Expected: non-zero process/document counts and no copied blobs.

- [ ] **Step 2: Enforce free-space gate**

Require free space greater than or equal to bytes_unique from the report plus 2 GiB. If not available, stop. Do not delete existing ZIPs or Versions yet; verified deletion belongs to M6.

- [ ] **Step 3: Apply**

Run: python scripts/migrate-legacy.py --archive-root work\tce-extractor\acervo-tce --data-root data --apply

Expected: source remains intact; each unique PDF SHA has one blob in data/archive/blobs, while data/archive/processos preserves the legacy folder view through hardlinks wherever possible so the proven collector/analyzer can continue operating without duplicating file bytes.

- [ ] **Step 4: Verify Mesa against real imported data**

Run the full M1 tests, then start: python -m app.main --data-root data --port 18753 --no-browser

Query /api/v1/storage and /api/v1/processes and confirm real records are visible.

- [ ] **Step 5: Commit only code fixes**

Never add data/. If no code changed, make no commit.

## M1 Exit Gate

- SQLite schema v1 is operational.
- The current archive can be imported without deleting the source.
- Physical duplicate PDFs are deduplicated by SHA-256, with a legacy-compatible process tree backed by hardlinks where supported.
- Real imported processes are visible in the read-only Mesa.
- The existing legacy operational workflow remains untouched.



---

<!-- Source: docs/superpowers/plans/2026-09-18-m2-area-restrita-integration.md -->

# M2 — Área Restrita Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Let the Mesa initiate a read-only scan of the authenticated Área Restrita through a new thin extension, persist the result in SQLite, and retain a CDP read-only compatibility fallback.

**Architecture:** The Mesa creates commands in a local command queue. The extension polls for commands, reads the portal DOM, and returns sanitized results. The extension does not own workflow state. A one-time pairing token is persisted on both sides so ordinary restarts do not require a new pairing code.

**Tech Stack:** Python standard library HTTP/SQLite, Chrome MV3, vanilla JavaScript, node:test, PowerShell CDP fallback.

**Spec:** docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md

## Global Constraints

- Área Restrita scan is read-only in M2.
- No form fields are written in this milestone.
- No final action is submitted.
- The new extension is installed beside the legacy extension until M5.
- Authentication secrets never appear in scan payloads or logs.
- The extension executes specific commands; it does not decide which processes should be downloaded or analyzed.

## File map

Create app/area_restrita/, extend app/core/store.py and app/api/server.py, create root extension/ with a scanner-only implementation, create tests/test_area_scan.py and extension/tests/, and create scripts/scan-area-cdp.ps1.

### Task 1: SQLite schema v2 for portal scans and extension commands

**Files:**
- Modify: app/core/store.py
- Modify: app/core/models.py
- Create: tests/test_area_scan.py

**Interfaces:**
- Store.create_area_scan(source_scope, marker_label, marker_value, rows) -> int
- Store.get_area_scan(scan_id) -> dict | None
- Store.latest_area_scan() -> dict | None
- Store.create_extension_command(command_type, payload) -> int
- Store.claim_extension_command(client_id) -> dict | None
- Store.complete_extension_command(command_id, result, error=None) -> None
- Store.pair_bridge_client(client_id, token_hash) -> None
- Store.verify_bridge_token(client_id, token_hash) -> bool
- schema_version becomes 2.

- [ ] **Step 1: Write failing store tests**

~~~python
def test_area_scan_updates_processes_and_counts(self):
    scan_id = store.create_area_scan(
        source_scope="sector_finalistic",
        marker_label="PROFESSOR - IPERN - 2 RUBRICAS",
        marker_value="6189",
        rows=[{
            "process_key": "102390/2026",
            "interested": "Pessoa Exemplo",
            "interested_normalized": "pessoa exemplo",
            "portal_act_id": "123",
            "classification": "PRECISA_COMPLEMENTAR",
            "needs_complement": True,
            "action_observed": "Complementar Ato",
        }],
    )
    scan = store.get_area_scan(scan_id)
    self.assertEqual(scan["pending"], 1)
    self.assertEqual(store.list_processes()[0]["status"], "PENDENTE")

    completed_id = store.create_area_scan(
        source_scope="sector_finalistic",
        marker_label="PROFESSOR - IPERN - 2 RUBRICAS",
        marker_value="6189",
        rows=[{
            "process_key": "102390/2026",
            "interested": "Pessoa Exemplo",
            "interested_normalized": "pessoa exemplo",
            "portal_act_id": "123",
            "classification": "ATO_COMPLEMENTADO",
            "needs_complement": False,
            "action_observed": "Ato Complementado",
        }],
    )
    self.assertEqual(store.get_process(store.list_processes()[0]["id"])["status"], "CONCLUÍDO")

def test_extension_command_is_claimed_once(self):
    command_id = store.create_extension_command("SCAN_AREA", {})
    first = store.claim_extension_command("extension-test")
    second = store.claim_extension_command("extension-test")
    self.assertEqual(first["id"], command_id)
    self.assertIsNone(second)
~~~

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_area_scan -v

Expected: missing methods/schema.

- [ ] **Step 3: Implement migration 1 to 2**

Add tables area_scans, area_scan_items, bridge_clients and extension_commands. Add process columns portal_act_id, area_classification, needs_complement and last_area_scan_id. Mapping is fail-closed: PRECISA_COMPLEMENTAR -> PENDENTE unless a later workflow state is more advanced; ATO_COMPLEMENTADO -> CONCLUÍDO with portal_completed workflow event; AMBIGUO/BLOQUEADO never become PRONTO automatically.

Command states are QUEUED, CLAIMED, SUCCEEDED, FAILED. Claim must be atomic using BEGIN IMMEDIATE so two pollers cannot claim one command.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_store tests.test_area_scan -v

Expected: PASS and Store.schema_version == 2.

- [ ] **Step 5: Commit**

~~~text
git add app/core tests/test_area_scan.py
git commit -m "feat: persist Área Restrita scans and extension commands"
~~~

### Task 2: Persistent bridge pairing and authenticated command API

**Files:**
- Create: app/api/bridge.py
- Modify: app/api/server.py
- Modify: app/api/views.py
- Modify: app/web/index.html
- Modify: app/web/app.js
- Modify: tests/test_api_server.py

**Interfaces:**
- POST /api/v1/bridge/pair with client_id + six-digit code -> bearer token
- GET /api/v1/bridge/status with bearer token
- POST /api/v1/session/bootstrap consumes a one-time Mesa bootstrap token and sets an HttpOnly SameSite=Strict loopback session cookie
- Every state-changing Mesa route requires that session cookie plus same-origin Origin/Sec-Fetch-Site validation
- POST /api/v1/extension/commands with authenticated same-origin Mesa request
- GET /api/v1/extension/commands/next with bearer token + X-TCE-Client
- POST /api/v1/extension/commands/ID/result with bearer token
- POST /api/v1/area/scans is internal command-result handling, not public unauthenticated input.

- [ ] **Step 1: Write failing auth tests**

Test that an unpaired extension receives 401, a valid pairing code returns one token, the token survives a new server instance because only its SHA-256 hash is persisted in SQLite, and an invalid token is rejected.

Example assertion:

~~~python
request = Request(
    base + "/api/v1/extension/commands/next",
    headers={"Authorization": f"Bearer {token}", "X-TCE-Client": "extension-test"},
)
payload = json.load(urlopen(request))
self.assertIsNone(payload["command"])
~~~

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_api_server -v

Expected: pairing/command routes are 404.

- [ ] **Step 3: Implement pairing**

Generate a six-digit in-memory pairing code at server startup with a 120-second TTL and at most five failed attempts, preserving the current fail-closed behavior. Display it in the Mesa only while no valid bridge client is connected. Bind the paired client record to the observed chrome-extension origin/extension id as well as client_id. On successful pairing, return a 32-byte URL-safe token and persist SHA-256(token) with client_id. Never persist plaintext token or pairing code.

For the Mesa itself, app.main generates a separate one-time bootstrap token and opens /bootstrap#token=TOKEN. Bootstrap JavaScript posts that token to /api/v1/session/bootstrap; the server consumes it once and sets an HttpOnly, SameSite=Strict session cookie. Reject state-changing Mesa requests without that cookie or with a non-loopback/non-same-origin Origin.

Allow CORS only for chrome-extension origins on authenticated extension routes. Extension bearer authentication and Mesa session authentication are separate contracts.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_api_server tests.test_area_scan -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add app/api app/web tests/test_api_server.py
git commit -m "feat: add persistent authenticated extension bridge"
~~~

### Task 3: Pure DOM scanner extracted from current portal knowledge

**Files:**
- Create: extension/package.json
- Create: extension/lib/area-snapshot.js
- Create: extension/content/scan-area.js
- Create: extension/tests/area-snapshot.test.mjs
- Modify: .gitignore

**Interfaces:**
- globalThis.TCEAreaSnapshot.scan(document) -> sanitized page snapshot
- snapshot fields: role, source_scope, marker, page, total_pages, rows
- each row: process_key, interested, interested_normalized, portal_act_id, classification, needs_complement, action_observed
- scan code never reads cookies, localStorage, sessionStorage or credential fields.

- [ ] **Step 1: Port failing fixtures from the proven legacy tests**

Build sanitized HTML fixtures from the same structures asserted in work/tce-extractor/portable/extensao-complementar-ato/tests/portal-navigation.test.mjs.

Test:

~~~javascript
await import("../lib/area-snapshot.js");
const snapshot = globalThis.TCEAreaSnapshot.scan(document);
assert.equal(snapshot.source_scope, "sector_finalistic");
assert.equal(snapshot.rows[0].process_key, "102390/2026");
assert.equal(snapshot.rows[0].classification, "PRECISA_COMPLEMENTAR");
~~~

Also assert that a completed row becomes ATO_COMPLEMENTADO and that unknown actions become AMBIGUO.

- [ ] **Step 2: Verify RED**

Run: cd extension && node --test tests/area-snapshot.test.mjs

Expected: module/file not found.

- [ ] **Step 3: Implement scanner by extracting behavior, not inventing new selectors**

Use the proven selector/normalization rules from the current portal-navigation.js. Keep the scanner side-effect free. scan-area.js only listens for a SCAN_PAGE message and returns TCEAreaSnapshot.scan(document).

- [ ] **Step 4: Verify parity tests**

Run:

~~~text
cd extension
node --test tests/area-snapshot.test.mjs
cd ..\work\tce-extractor\portable\extensao-complementar-ato
npm test
~~~

Expected: new tests PASS and legacy extension suite remains green.

- [ ] **Step 5: Commit**

~~~text
git add .gitignore extension
git commit -m "feat: extract read-only Área Restrita scanner"
~~~

### Task 4: Scanner-only MV3 extension with command polling

**Files:**
- Create: extension/manifest.json
- Create: extension/background/router.js
- Create: extension/lib/api.js
- Create: extension/lib/protocol.js
- Create: extension/sidepanel/panel.html
- Create: extension/sidepanel/panel.js
- Create: extension/tests/router.test.mjs
- Create: extension/tests/api.test.mjs

**Interfaces:**
- command types in M2: STATUS and SCAN_AREA only.
- api.pair(code) persists token in chrome.storage.local.
- api.nextCommand() polls the Mesa.
- router executes SCAN_AREA by enumerating list pages through content-script messages and posts one final sanitized result.
- sidepanel shows Mesa connection, portal detection, Pair action only when needed, and Open Mesa.

- [ ] **Step 1: Write failing router test**

~~~javascript
const command = { id: 7, type: "SCAN_AREA", payload: {} };
const result = await executeCommand(command, {
  scanPortal: async () => ({
    source_scope: "sector_finalistic",
    marker: { label: "M", value: "6189" },
    rows: [{ process_key: "102390/2026", classification: "PRECISA_COMPLEMENTAR" }],
  }),
});
assert.equal(result.command_id, 7);
assert.equal(result.rows.length, 1);
~~~

- [ ] **Step 2: Verify RED**

Run: cd extension && node --test tests/router.test.mjs tests/api.test.mjs

Expected: missing modules.

- [ ] **Step 3: Implement minimal extension**

Manifest permissions: storage, sidePanel, alarms, webNavigation only if pagination requires it. Host permissions: novaarearestrita.tce.rn.gov.br and 127.0.0.1. Do not request e-Contas permissions in this extension.

Do not depend on the sidepanel staying open. While an authorized Área Restrita tab is loaded, a tiny content-script heartbeat sends POLL_COMMANDS to the service worker every 1500 ms; that browser event wakes the MV3 worker, which performs the authenticated loopback fetch. Use chrome.alarms only as a slow recovery fallback. When no Área Restrita tab is connected, the Mesa reports that state and leaves commands queued rather than pretending the scan started.

Persist client_id and bearer token in chrome.storage.local. No dataset import UI, no lot UI, no OCR controls.

- [ ] **Step 4: Verify extension tests**

Run: cd extension && npm test

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add extension
git commit -m "feat: add thin Área Restrita bridge extension"
~~~

### Task 5: Mesa-driven Analyze Área Restrita flow

**Files:**
- Modify: app/api/server.py
- Modify: app/web/index.html
- Modify: app/web/app.js
- Modify: tests/test_api_server.py
- Modify: tests/test_area_scan.py

**Interfaces:**
- POST /api/v1/area/analyze -> creates SCAN_AREA command and returns command_id
- GET /api/v1/extension/commands/ID -> status/result for Mesa polling
- successful SCAN_AREA result is persisted through Store.create_area_scan
- Mesa action label: Analisar Área Restrita.

- [ ] **Step 1: Write failing end-to-end command result test**

Create analyze command through HTTP, claim it as extension-test, post a sanitized scan result, then assert latest_area_scan and process states match.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_api_server tests.test_area_scan -v

Expected: analyze route missing.

- [ ] **Step 3: Implement route and UI**

Mesa button creates command, shows Analisando…, polls status, then refreshes counters. Display total, pending, completed and ambiguous counts. Never show token, command payload internals or technical queue ids in the normal view.

- [ ] **Step 4: Verify GREEN**

Run both Python and extension suites.

Expected: all PASS.

- [ ] **Step 5: Commit**

~~~text
git add app tests
git commit -m "feat: drive Área Restrita analysis from Mesa"
~~~

### Task 6: Read-only CDP compatibility fallback

**Files:**
- Create: app/area_restrita/__init__.py
- Create: app/area_restrita/cdp_fallback.py
- Create: scripts/scan-area-cdp.ps1
- Create: tests/test_cdp_fallback.py
- Modify: app/api/server.py
- Modify: app/web/app.js

**Interfaces:**
- build_cdp_scan_command(repo_root: Path) -> list[str]
- POST /api/v1/area/analyze-cdp -> runs read-only fallback and persists the same scan schema.
- PowerShell output is one JSON object on stdout.

- [ ] **Step 1: Write failing command/sanitization tests**

Assert the built command invokes scripts/scan-area-cdp.ps1 and contains no submit, click-final, credential, cookie or password argument. Feed a fake PowerShell JSON result and assert it goes through the same Store.create_area_scan path.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_cdp_fallback -v

Expected: module missing.

- [ ] **Step 3: Implement fallback**

Reuse the CDP connection patterns already proven in probe-existing-chrome.ps1. Load extension/lib/area-snapshot.js text into Runtime.evaluate and call the same scanner against the authenticated Área Restrita frame tree. The script may navigate pagination only; it must not open Complementar Ato, select an interested person, write fields or click submission controls.

- [ ] **Step 4: Verify automated and supervised read-only smoke**

Run Python tests first. Then, with an authenticated session, run scripts/scan-area-cdp.ps1 and compare process keys/counts with an extension scan of the same marker. Differences block M2 exit.

- [ ] **Step 5: Commit**

~~~text
git add app/area_restrita scripts/scan-area-cdp.ps1 tests app/web/app.js
git commit -m "feat: add read-only Área Restrita CDP fallback"
~~~

## M2 Exit Gate

- Clicking Analisar Área Restrita in the Mesa initiates the scan.
- Extension scan is the primary path.
- Scan result is persisted in SQLite and updates process states.
- Pairing normally happens once and survives service/browser restarts.
- CDP fallback produces the same sanitized schema and does not write to the portal.
- Legacy extension remains available as fallback; no fill behavior has migrated yet.



---

<!-- Source: docs/superpowers/plans/2026-09-18-m3-econtas-acquisition.md -->

# M3 — e-Contas Acquisition Controlled by Mesa Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Let the Mesa calculate missing processes, create bounded internal batches, invoke the proven e-Contas collector, and track acquisition jobs without exposing frozen queues, lot ids or PowerShell details to the operator.

**Architecture:** The new application owns job state and selection. During M3, the actual browser/download engine remains the proven legacy collector. A compatibility writer generates the exact frozen-queue contract that the existing PowerShell module already validates.

**Tech Stack:** Python standard library subprocess/SQLite/unittest, existing PowerShell collector and CDP driver, vanilla Mesa UI.

**Spec:** docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md

## Global Constraints

- The Mesa owns which process keys are eligible for acquisition.
- The legacy collector remains intact until equivalence is proven.
- Only process keys in the Mesa-generated frozen queue may be downloaded.
- Batches are internal implementation details; default batch size is 50.
- Failed processes do not invalidate successful processes.
- No process outside the selected Área Restrita pending set may be downloaded.
- No portal form filling occurs in M3.

## File map

Create app/econtas/collector.py, app/econtas/legacy_queue.py, app/core/jobs.py and tests/test_econtas_acquisition.py. Extend API, store and Mesa UI. Legacy work/tce-extractor/portable/Coletar-Processos-TCE.ps1 remains unchanged at first.

### Task 1: Acquisition job model

**Files:**
- Create: app/core/jobs.py
- Modify: app/core/store.py
- Modify: app/core/models.py
- Create: tests/test_econtas_acquisition.py

**Interfaces:**
- JobManager.create(job_type: str, item_ids: list[int]) -> int
- JobManager.start(job_id: int) -> None
- JobManager.mark_item(job_id: int, process_id: int, state: str, error: str | None = None) -> None
- JobManager.finish(job_id: int) -> None
- Store.list_missing_pending_processes() -> list[dict]
- process acquisition states: NOT_DOWNLOADED, QUEUED, DOWNLOADING, DOWNLOADED, FAILED.
- schema_version becomes 3.

- [ ] **Step 1: Write failing job-state test**

~~~python
rows = [
    make_process("102390/2026", status="PENDENTE"),
    make_process("102391/2026", status="PENDENTE"),
]
job_id = manager.create("acquisition", [row["id"] for row in rows])
manager.start(job_id)
manager.mark_item(job_id, rows[0]["id"], "DOWNLOADED")
manager.mark_item(job_id, rows[1]["id"], "FAILED", "auth required")
manager.finish(job_id)

job = store.get_job(job_id)
self.assertEqual(job["completed"], 1)
self.assertEqual(job["failed"], 1)
self.assertEqual(job["status"], "COMPLETED_WITH_ERRORS")
~~~

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_econtas_acquisition -v

Expected: missing JobManager/store job-item methods.

- [ ] **Step 3: Implement schema migration**

Add job_items with UNIQUE(job_id, process_id), state, error and timestamps. Add acquisition_state to processes. Implement this as schema migration 2 -> 3 and update metadata.schema_version only after the migration transaction commits. list_missing_pending_processes returns only needs_complement=1 with acquisition_state NOT_DOWNLOADED or FAILED and excludes ATO_COMPLEMENTADO.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_store tests.test_econtas_acquisition -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add app/core tests/test_econtas_acquisition.py
git commit -m "feat: add acquisition job tracking"
~~~

### Task 2: Exact legacy frozen-queue compatibility writer

**Files:**
- Create: app/econtas/__init__.py
- Create: app/econtas/legacy_queue.py
- Modify: tests/test_econtas_acquisition.py

**Interfaces:**
- write_frozen_queue(processes: list[dict], source_scope: str, marker: dict, path: Path, lot_size: int = 50) -> FrozenQueueInfo
- FrozenQueueInfo: path, analysis_id, dataset_sha256, queue_size, lot_count.
- Output must be accepted by both work/tce-extractor/portable/app/frozen_queue.py and work/tce-extractor/portable/TceFrozenQueue.psm1.

- [ ] **Step 1: Write failing compatibility test**

~~~python
info = write_frozen_queue(
    processes=[
        {"process_key": "102390/2026"},
        {"process_key": "102391/2026"},
    ],
    source_scope="sector_finalistic",
    marker={"label": "M", "value": "6189"},
    path=queue_path,
    lot_size=1,
)
loaded = legacy_load_frozen_queue(queue_path)
self.assertEqual([x["process_key"] for x in loaded["items"]], ["102390/2026", "102391/2026"])
self.assertEqual(info.lot_count, 2)
~~~

Load the legacy Python module by temporarily adding work/tce-extractor/portable/app to sys.path in the test.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_econtas_acquisition -v

Expected: legacy_queue module missing.

- [ ] **Step 3: Implement schema exactly**

Build:
- schema_version = 3
- observed_at = current UTC ISO string
- spec.source_scope
- spec.acquisition_source = econtas
- spec.marker
- queue = ordered process_key objects
- blocked = []
- lots = sequential lot-1, lot-2...
- canonical_json = compact sorted JSON of schema_version, observed_at, spec, queue, blocked
- dataset_sha256 = SHA-256 of canonical_json
- analysis_id = analysis- plus first 24 hex characters of dataset_sha256.

Then write JSON atomically.

- [ ] **Step 4: Verify against both validators**

Run:

~~~text
python -m unittest tests.test_econtas_acquisition -v
powershell -NoProfile -Command "Import-Module .\work\tce-extractor\portable\TceFrozenQueue.psm1; Read-TceFrozenQueue -Path .\tmp\test-frozen-queue.json | ConvertTo-Json -Depth 10"
~~~

Expected: Python and PowerShell accept the same queue.

- [ ] **Step 5: Commit**

~~~text
git add app/econtas tests/test_econtas_acquisition.py
git commit -m "feat: write legacy-compatible acquisition queues"
~~~

### Task 3: Legacy collector adapter

**Files:**
- Create: app/econtas/collector.py
- Modify: tests/test_econtas_acquisition.py

**Interfaces:**
- CollectorRequest: queue_path, lot_number, destination, source_scope, keep_browser_open=True
- build_collector_command(request: CollectorRequest, repo_root: Path) -> list[str]
- run_collector(request, on_line, repo_root) -> CollectorResult
- CollectorResult: exit_code, downloaded, reused, deduplicated, failed, auth_required.

- [ ] **Step 1: Write failing command test**

~~~python
command = build_collector_command(
    CollectorRequest(
        queue_path=Path("tmp/q.json"),
        lot_number=1,
        destination=Path("data/archive"),
        source_scope="sector_finalistic",
    ),
    repo_root,
)
joined = " ".join(command)
self.assertIn("Coletar-Processos-TCE.ps1", joined)
self.assertIn("-FilaCongelada", command)
self.assertIn("-NumeroLote", command)
self.assertIn("-EscopoPortal", command)
self.assertIn("sector_finalistic", command)
self.assertNotIn("-Selecao", command)
~~~

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_econtas_acquisition -v

Expected: collector module missing.

- [ ] **Step 3: Implement subprocess adapter**

Command must invoke powershell.exe -NoProfile -ExecutionPolicy Bypass -File work/tce-extractor/portable/Coletar-Processos-TCE.ps1 with:
- -Destino data/archive
- -FilaCongelada queue path
- -NumeroLote N
- -NaoInterativo
- -ManterNavegadorAberto
- -EscopoPortal selected scope
- -ModoPreparacao progressivo
- -MaxDownloads 2.

Do not pass ServiceChild from the new Mesa because the legacy service is no longer the parent lock owner.

Parse the existing final summary line:
Concluído (...). Baixados: N; reutilizados: N; deduplicados: N; processos com falha: N.

Classify known login/auth messages as auth_required without logging credentials or URLs.

- [ ] **Step 4: Verify with fake runner**

Inject subprocess_factory so unit tests never open a browser. Test successful summary, nonzero exit, and auth-required output.

- [ ] **Step 5: Commit**

~~~text
git add app/econtas/collector.py tests/test_econtas_acquisition.py
git commit -m "feat: adapt proven e-Contas collector"
~~~

### Task 4: Acquisition coordinator and automatic batches

**Files:**
- Create: app/econtas/service.py
- Modify: app/core/jobs.py
- Modify: app/core/store.py
- Modify: tests/test_econtas_acquisition.py

**Interfaces:**
- AcquisitionService.plan_pending() -> AcquisitionPlan
- AcquisitionPlan: process_ids, process_keys, total, lot_size=50, lot_count.
- AcquisitionService.start(plan) -> job_id
- worker processes lots serially; legacy collector may still download at MaxDownloads 2 inside one process.
- After each lot, service calls app.archive.legacy_import.canonicalize_process_tree(data_root, store), then rescans the archive and updates document/acquisition state. This moves newly downloaded bytes into the canonical SHA blob store and leaves the legacy-shaped process path as a verified hardlink whenever supported.

- [ ] **Step 1: Write failing plan test**

Given 92 pending missing processes and 10 already downloaded, plan_pending returns 82 keys, two lots, and preserves Área Restrita order.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_econtas_acquisition -v

Expected: service missing.

- [ ] **Step 3: Implement coordinator**

Use the latest area_scan order. Generate one frozen queue for the whole plan, then invoke lot 1..N. Mark each process QUEUED before start. After each lot, canonicalize the process tree before updating states by comparing archive contents to requested keys. A lot failure does not erase prior successes. auth_required pauses the job as WAITING_FOR_LOGIN and stops later lots.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_econtas_acquisition -v

Expected: PASS for 50/32 batching, partial failure and auth pause.

- [ ] **Step 5: Commit**

~~~text
git add app/econtas app/core tests/test_econtas_acquisition.py
git commit -m "feat: coordinate e-Contas acquisition from Mesa"
~~~

### Task 5: Mesa acquisition API and UI

**Files:**
- Modify: app/api/server.py
- Modify: app/web/index.html
- Modify: app/web/app.js
- Modify: tests/test_api_server.py

**Interfaces:**
- GET /api/v1/acquisition/plan
- POST /api/v1/acquisition/jobs
- GET /api/v1/jobs/ID
- Mesa shows Não baixados count and Baixar N processos.
- Normal UI shows progress as completed/total, not lot ids.

- [ ] **Step 1: Write failing API test**

Seed three pending missing processes. GET plan must report total=3. POST job must create acquisition job. GET job returns state and counters.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_api_server -v

Expected: routes missing.

- [ ] **Step 3: Implement API/UI**

Start worker in one background thread managed by the app process. Refuse a second active acquisition job. UI polls job every second, shows process-level failures and a Faça login no e-Contas state for WAITING_FOR_LOGIN.

- [ ] **Step 4: Verify GREEN**

Run all M1-M3 Python tests.

- [ ] **Step 5: Commit**

~~~text
git add app/api app/web tests/test_api_server.py
git commit -m "feat: add Mesa acquisition controls"
~~~

### Task 6: Supervised real e-Contas equivalence gate

**Files:**
- Modify code only if the smoke reveals a defect.
- Write private evidence only under ignored data/logs or tmp.

**Interfaces:**
- Use a bounded set of 1 to 5 pending processes first.
- Compare requested keys, resulting folders/documents and hashes with legacy expectations.

- [ ] **Step 1: Create a small real acquisition plan**

Use the Mesa to select the first 1 to 5 NOT_DOWNLOADED pending processes from a real Area scan.

- [ ] **Step 2: Start the job and authenticate manually if requested**

No credential automation. The collector may reuse an existing authenticated Chrome or open the proven work profile.

- [ ] **Step 3: Verify scope**

Assert every downloaded process key was requested and no unrequested process directory was created during the job.

- [ ] **Step 4: Verify documents**

For each successful process, compare local manifest count, PDF count and SHA-256 records. Any mismatch blocks M3 exit.

- [ ] **Step 5: Expand to one normal 50-process internal batch**

Only after the 1 to 5 process smoke is green. Record job summary in ignored logs. Do not disable the legacy collector fallback.

## M3 Exit Gate

- The Mesa decides which pending processes need download.
- Internal batches are automatic and hidden from the operator.
- The existing collector accepts the Mesa-generated frozen queue.
- A real bounded acquisition downloads only requested keys.
- Authentication failure pauses instead of continuing blindly.
- The legacy collector remains available and unchanged as the download engine.



---

<!-- Source: docs/superpowers/plans/2026-09-18-m4-analysis-evidence.md -->

# M4 — Analysis, Legal Rules and Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Make the Mesa automatically analyze each downloaded process, persist fields/evidence in SQLite, show document-level traceability, and move legal-decision logic out of the extension.

**Architecture:** The existing proven incremental analysis remains the first execution engine behind an adapter. Its results are normalized into SQLite. Legal-rule behavior currently implemented in extension JavaScript is ported to backend Python with parity tests before the extension copy is retired.

**Tech Stack:** Python standard library plus the dependencies already shipped by the portable runtime, existing analysis_pipeline/incremental_pipeline, unittest, existing Node tests as parity oracle, PDF.js assets already present in the project.

**Spec:** docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md

## Global Constraints

- Analysis starts automatically after successful acquisition.
- Native text is preferred; OCR remains fallback only.
- Every proposed field retains source/evidence when available.
- Missing mandatory fields produce REVISAR, not a partial automatic fill.
- genero remains optional; modalidade, fundamento_legal, data_publicacao_doe, cargo, matricula and data_nascimento remain mandatory.
- The extension must no longer be the authoritative owner of legal/business decisions after this milestone.
- Existing analysis outputs remain available as fallback until parity is proven.

## File map

Create app/analysis/legacy_adapter.py, normalize.py, legal.py, evidence.py and service.py; extend Store and API; extend Mesa process detail and PDF viewer; create tests/test_analysis_service.py and tests/test_legal_rules.py.

### Task 1: Normalize legacy incremental analysis into SQLite

**Files:**
- Create: app/analysis/__init__.py
- Create: app/analysis/normalize.py
- Create: app/analysis/legacy_adapter.py
- Create: tests/test_analysis_service.py

**Interfaces:**
- LegacyAnalysisAdapter.analyze(process_key: str) -> dict
- normalize_analysis(process_key: str, payload: dict) -> NormalizedAnalysis
- NormalizedAnalysis contains process_status, fields, documents, pending_fields, warnings.
- No legacy JSON path is exposed to the web UI.

- [ ] **Step 1: Write failing normalization test**

Use a sanitized payload shaped like the current incremental_pipeline result:

~~~python
payload = {
    "process": "102390/2026",
    "status": "complete",
    "blocks": [{
        "interested": "Pessoa Exemplo",
        "pending": [],
        "fields": {
            "cargo": {
                "value": "Professor",
                "status": "found",
                "confidence": "high",
                "process": "102390/2026",
                "event": "1",
                "document": "Ato.pdf",
                "page": 2,
                "evidence": {
                    "document_id": "doc-1",
                    "page": 2,
                    "quote": "Professor",
                    "rects": [[0.1, 0.2, 0.4, 0.25]],
                    "method": "text",
                    "status": "ready"
                }
            }
        }
    }]
}
analysis = normalize_analysis("102390/2026", payload)
self.assertEqual(analysis.fields[0].field_name, "cargo")
self.assertEqual(analysis.fields[0].page, 2)
self.assertEqual(analysis.process_status, "PRONTO")
~~~

Also test that missing data_nascimento produces REVISAR while missing genero alone does not.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_analysis_service -v

Expected: missing analysis package.

- [ ] **Step 3: Implement adapter and normalization**

LegacyAnalysisAdapter temporarily imports work/tce-extractor/portable/app/incremental_pipeline.py by adding that exact directory to sys.path inside the adapter only. Call analyze_process with archive_root=data/archive and resolved Tesseract paths.

normalize_analysis maps legacy field confidence high to 1.0, other known confidence values to deterministic numeric values, preserves raw evidence JSON, and computes mandatory-field readiness.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_analysis_service -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add app/analysis tests/test_analysis_service.py
git commit -m "feat: normalize legacy analysis for Mesa"
~~~

### Task 2: Analysis service and automatic job chaining

**Files:**
- Create: app/analysis/service.py
- Modify: app/core/jobs.py
- Modify: app/core/store.py
- Modify: app/econtas/service.py
- Modify: app/econtas/collector.py
- Modify: work/tce-extractor/portable/Coletar-Processos-TCE.ps1
- Modify: work/tce-extractor/tests/Test-TcePortable.ps1
- Modify: tests/test_analysis_service.py
- Modify: tests/test_econtas_acquisition.py

**Interfaces:**
- AnalysisService.enqueue(process_id: int) -> int
- AnalysisService.run(job_id: int) -> None
- AnalysisService.analyze_one(process_id: int) -> str
- acquisition success calls AnalysisService.enqueue for that process.
- process states transition DOWNLOADED -> ANALISANDO -> PRONTO or REVISAR; failures -> ERRO.

- [ ] **Step 1: Write failing chain test**

Use fake collector + fake analyzer. After one acquisition success, assert an analysis job is queued. After analysis completion, assert fields are stored and process status is PRONTO.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_econtas_acquisition tests.test_analysis_service -v

Expected: no analysis chaining.

- [ ] **Step 3: Add an acquisition-only compatibility mode before enabling chaining**

Extend the legacy collector parameter ValidateSet from progressivo|completo to progressivo|completo|nenhum. In nenhum mode, download/synchronization still runs but Invoke-TceIncrementalPreparation is never called. Add a PowerShell regression test proving nenhum performs no preparation call while preserving queue validation and download behavior.

After that test is green, change the new app/econtas/collector.py adapter to pass -ModoPreparacao nenhum.

- [ ] **Step 4: Implement minimal chaining**

Do not create a second process-wide executor. Reuse the app worker thread and a typed job queue. Analysis failures are item-local and preserve downloaded files. Persist workflow events download_finished, analysis_started, analysis_finished or analysis_failed.

- [ ] **Step 5: Verify GREEN**

Run the PowerShell collector tests plus all M1-M4 Python tests. Assert one successful acquisition causes exactly one AnalysisService execution.

- [ ] **Step 6: Commit**

~~~text
git add app work/tce-extractor/portable/Coletar-Processos-TCE.ps1 work/tce-extractor/tests/Test-TcePortable.ps1 tests/test_analysis_service.py tests/test_econtas_acquisition.py
git commit -m "feat: analyze processes after acquisition"
~~~

### Task 3: Port legal reference parsing and foundation rules to Python

**Files:**
- Create: app/analysis/legal.py
- Create: tests/test_legal_rules.py
- Create: tests/fixtures/legal-cases.json

**Interfaces:**
- parse_legal_references(text: str) -> list[LegalReference]
- resolve_legal_foundation(context: dict, options: list[dict]) -> dict
- RULES_VERSION = legal-foundation-v3
- Return shape preserves status, automatic, decision_state, method, rule_id, option_value, option_label, confidence, margin, reasons, warnings, citations and rules_version.

- [ ] **Step 1: Build parity fixtures from existing public tests**

Mirror the non-private scenarios from:
- work/tce-extractor/portable/extensao-complementar-ato/tests/legal-foundation.test.mjs
- legal-reference-parser-v2.test.mjs
- portal-legal-crosswalk.test.mjs
- retirement-legal-profile.test.mjs

Fixture example:

~~~json
{
  "name": "ec41_without_p5",
  "operative_text": "Art. 6º e art. 7º da Emenda Constitucional 41/2003",
  "cargo": "Professor",
  "options": [
    {"value": "A", "label": "Art. 6º e art. 7º da Emenda Constitucional 41/2003"}
  ],
  "expected": {
    "status": "selected",
    "automatic": true,
    "rule_id": "EC41_SEM_P5",
    "option_value": "A"
  }
}
~~~

- [ ] **Step 2: Write failing Python parity tests**

For each fixture, call resolve_legal_foundation and assert every expected field. Also test incomplete references, contradictory references and no references return pending/manual review.

- [ ] **Step 3: Verify RED**

Run: python -m unittest tests.test_legal_rules -v

Expected: legal.py missing.

- [ ] **Step 4: Port rules behaviorally**

Port normalization, article/diploma parsing, source-family classification, scoring, confidence/margin gates and contradiction checks from legal-foundation.js and its current helper files. Do not simplify a rule unless a parity fixture proves the change intentional.

- [ ] **Step 5: Verify both suites**

Run:

~~~text
python -m unittest tests.test_legal_rules -v
cd work\tce-extractor\portable\extensao-complementar-ato
node --test tests/legal-foundation.test.mjs tests/legal-reference-parser-v2.test.mjs tests/portal-legal-crosswalk.test.mjs tests/retirement-legal-profile.test.mjs
~~~

Expected: both old and new suites green.

- [ ] **Step 6: Commit**

~~~text
git add app/analysis/legal.py tests/test_legal_rules.py tests/fixtures/legal-cases.json
git commit -m "feat: move legal foundation rules to backend"
~~~

### Task 4: Evidence service and PDF range support

**Files:**
- Create: app/analysis/evidence.py
- Modify: app/api/server.py
- Modify: tests/test_api_server.py
- Modify: tests/test_analysis_service.py

**Interfaces:**
- GET /api/v1/processes/ID/evidence/FIELD
- GET /api/v1/documents/ID/pdf supports Range: bytes=start-end and returns 206.
- evidence response: document_id, page, quote, rects, method, status.
- Paths are always resolved from SQLite document ids.

- [ ] **Step 1: Write failing evidence and Range tests**

Seed one PDF and field evidence. Request evidence and Range bytes=0-9. Assert 206, Content-Range and exact bytes.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_api_server tests.test_analysis_service -v

Expected: evidence route missing and PDF route returns full response only.

- [ ] **Step 3: Implement evidence lookup and safe Range**

Accept only one byte range. Reject invalid/multiple ranges with 416. Never accept a path query parameter. Missing evidence returns 404 rather than invented coordinates.

- [ ] **Step 4: Verify GREEN**

Run Python tests.

- [ ] **Step 5: Commit**

~~~text
git add app/analysis/evidence.py app/api tests
git commit -m "feat: expose field evidence and PDF ranges"
~~~

### Task 5: Process review UI with integrated PDF viewer

**Files:**
- Copy/adapt: work/tce-extractor/portable/app/web/pdf-viewer.js -> app/web/pdf-viewer.js
- Modify: app/web/index.html
- Modify: app/web/app.js
- Modify: app/web/app.css
- Modify: tests/test_api_server.py

**Interfaces:**
- Process detail tabs: Dados, Documentos, Histórico.
- Clicking a field source opens its document at evidence.page and applies rect highlights when available.
- The viewer retains zoom 75% to 300%, quarter-turn rotation and reset behavior proven in the current viewer.

- [ ] **Step 1: Add failing static contract test**

Assert index includes pdf-viewer container and app.js includes evidence endpoint use. Add a small Node/browserless test only if the copied viewer already has a testable adapter; otherwise preserve the existing legacy viewer tests during the copy.

- [ ] **Step 2: Verify RED**

Run Python static tests.

- [ ] **Step 3: Adapt current viewer**

Preserve existing PDF.js vendor assets and the current zoom/rotation contract. Change document URLs to /api/v1/documents/ID/pdf. Add source links next to every field with evidence.

- [ ] **Step 4: Verify**

Run Python tests and the existing legacy web viewer tests. Open a real imported process and confirm field source -> correct document/page.

- [ ] **Step 5: Commit**

~~~text
git add app/web tests
git commit -m "feat: add evidence-driven process review"
~~~

### Task 6: Real analysis equivalence gate

**Files:** code only if defects are found; evidence stays ignored.

- [ ] **Step 1: Select 10 already-downloaded real processes covering complete, missing mandatory field, and multiple-interested cases.**

- [ ] **Step 2: Run legacy current result and new AnalysisService for the same process keys.**

- [ ] **Step 3: Compare field values, status, document source, page and evidence status.**

Any mismatch in a mandatory field blocks M4 exit until explained and covered by a regression test.

- [ ] **Step 4: Compare legal-foundation decisions for processes where a foundation proposal exists.**

Backend output must match the current JS rule outcome or have an explicitly approved fixture-backed correction.

- [ ] **Step 5: Enable automatic post-download analysis only after equivalence is green.**

Keep a configuration switch to disable the new analysis worker and use legacy preparation until M5 is complete.

## M4 Exit Gate

- Download completion automatically schedules analysis.
- Process state becomes PRONTO, REVISAR or ERRO from backend analysis.
- Mandatory-field rules are enforced centrally.
- Legal foundation decisions are backend-owned with parity tests.
- Mesa shows source/evidence and integrated PDFs.
- Existing legacy analysis remains available as rollback.



---

<!-- Source: docs/superpowers/plans/2026-09-18-m5-extension-filling.md -->

# M5 — Thin Extension and Mesa-Driven Form Filling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Move form-opening and filling orchestration to the Mesa, reduce the new extension to portal observation/execution, provide manual fallback, and make auto-submit impossible in the new protocol.

**Architecture:** A fill request is a backend workflow. The Mesa creates it, the extension receives only specific OPEN_ACT, READ_FORM and FILL_FORM commands, and the backend validates every intermediate result. There is no SUBMIT command type. The legacy extension remains installed as rollback until real equivalence is proven.

**Tech Stack:** Python SQLite/HTTP, Chrome MV3 JavaScript, node:test, existing portal DOM behavior as migration source.

**Spec:** docs/superpowers/specs/2026-09-18-mesa-local-refactor-design.md

## Global Constraints

- The new protocol has no submit/finalize command.
- The new extension never chooses a process or legal outcome.
- The backend is authoritative for mandatory fields and legal decisions.
- Identity must match process + interested person before any field write.
- Existing divergent portal values block writing; no partial write on preflight failure.
- genero is optional; six other configured fields are mandatory.
- Manual fallback and automatic navigation must use the same fill-form implementation.
- The legacy extension is not deleted in M5.

## File map

Create app/area_restrita/fill_service.py and tests/test_fill_service.py. Expand root extension with content/navigate.js, detect-form.js and fill-form.js. Reduce root sidepanel to connection/current-form fallback. Extend protocol/router and Mesa UI.

### Task 1: Backend fill-request state machine

**Files:**
- Create: app/area_restrita/fill_service.py
- Modify: app/core/store.py
- Create: tests/test_fill_service.py

**Interfaces:**
- FillService.request_fill(process_id: int) -> int
- FillService.handle_command_result(command_id: int, result: dict) -> None
- FillService.request_manual_fill(form_snapshot: dict) -> int
- fill request states: OPENING, READING, PREFLIGHT, FILLING, PREENCHIDO, BLOQUEADO, ERRO.
- Store methods create_fill_request, get_fill_request, update_fill_request.
- schema_version becomes 4 through an atomic migration 3 -> 4.
- all POST fill routes inherit the authenticated Mesa session and same-origin checks introduced in M2.
- extension command metadata contains fill_request_id.

- [ ] **Step 1: Write failing state-machine test**

~~~python
request_id = service.request_fill(process_id)
open_command = store.claim_extension_command("extension-test")
self.assertEqual(open_command["type"], "OPEN_ACT")

service.handle_command_result(open_command["id"], {
    "ok": True,
    "identity": {"processKey": "102390/2026", "interestedNormalized": "pessoa exemplo"},
})
read_command = store.claim_extension_command("extension-test")
self.assertEqual(read_command["type"], "READ_FORM")
~~~

Also test that a process not in PRONTO state is refused and that identity mismatch becomes BLOQUEADO.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_fill_service -v

Expected: fill service missing.

- [ ] **Step 3: Implement store migration and state machine**

Add portal_fill_requests with process_id, state, current_command_id, error, created_at, updated_at. Apply it as schema migration 3 -> 4 and update metadata.schema_version only after commit. request_fill validates PRONTO and creates OPEN_ACT. Result handling must transition only through the defined sequence and reject stale/foreign command ids.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_fill_service tests.test_area_scan -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add app/area_restrita app/core tests/test_fill_service.py
git commit -m "feat: add Mesa fill request state machine"
~~~

### Task 2: Form preflight and backend fill plan

**Files:**
- Create: app/area_restrita/preflight.py
- Modify: app/area_restrita/fill_service.py
- Modify: tests/test_fill_service.py
- Modify: tests/test_legal_rules.py

**Interfaces:**
- build_fill_plan(process: dict, form_snapshot: dict) -> FillPlan
- FillPlan: identity, generation, fields, preserved, legal_decision, warnings.
- Allowed fields: modalidade, fundamento_legal, data_publicacao_doe, cargo, matricula, data_nascimento, genero.
- Mandatory: all except genero.

- [ ] **Step 1: Write failing preflight tests**

Cases:
- exact identity + empty controls -> fill plan succeeds;
- missing data_nascimento -> block with FIELD_PROPOSAL_MISSING;
- existing portal value equal to proposal -> preserved;
- existing non-empty divergent value -> block with EXISTING_VALUE_DIVERGENCE;
- select proposal absent from current options -> block;
- fundamento_legal uses backend resolve_legal_foundation with current form options.

Example:

~~~python
plan = build_fill_plan(process, form_snapshot)
self.assertEqual(plan.fields["cargo"], "Professor")
self.assertEqual(plan.preserved, {})
self.assertEqual(plan.legal_decision["rules_version"], "legal-foundation-v3")
~~~

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_fill_service -v

Expected: preflight module missing.

- [ ] **Step 3: Implement fail-closed preflight**

The form snapshot must include identity, generation, fields with value/disabled/readOnly, and options for selects. Reject disabled/readOnly mandatory controls. Do not write any field if any mandatory field fails preflight.

- [ ] **Step 4: Verify GREEN**

Run: python -m unittest tests.test_fill_service tests.test_legal_rules -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~text
git add app/area_restrita/preflight.py app/area_restrita/fill_service.py tests
git commit -m "feat: centralize form preflight in backend"
~~~

### Task 3: Extract navigation and form reader into thin extension

**Files:**
- Create: extension/content/navigate.js
- Create: extension/content/detect-form.js
- Create: extension/tests/navigate.test.mjs
- Create: extension/tests/detect-form.test.mjs
- Modify: extension/manifest.json
- Modify: extension/lib/protocol.js
- Modify: extension/background/router.js

**Interfaces:**
- OPEN_ACT payload: processKey, interestedNormalized, portalActId.
- READ_FORM result: identity, generation, fields, options.
- navigate.js knows list pagination, Complementar Ato opening, interested selection and return behavior.
- detect-form.js is read-only.

- [ ] **Step 1: Port failing behavior tests from legacy**

Port the relevant non-submit scenarios from:
- work/tce-extractor/portable/extensao-complementar-ato/tests/portal-navigation.test.mjs
- form-detector.test.mjs

Required cases: legacy frames, list pagination, opening dynamic act frame, interested screen, selecting exact interested person, late form appearance, process/year identity, hidden form rejection, option catalog read.

- [ ] **Step 2: Verify RED**

Run: cd extension && node --test tests/navigate.test.mjs tests/detect-form.test.mjs

Expected: new modules missing.

- [ ] **Step 3: Extract proven selectors and behavior**

Do not redesign selectors. Move only the behavior required by OPEN_ACT and READ_FORM from current portal-navigation.js and form-detector.js. Keep side effects isolated to explicit navigation commands.

- [ ] **Step 4: Run new and legacy suites**

Run new extension tests and then legacy npm test. Both must remain green.

- [ ] **Step 5: Commit**

~~~text
git add extension/content extension/tests extension/manifest.json extension/lib/protocol.js extension/background/router.js
git commit -m "feat: add thin portal navigation and form reader"
~~~

### Task 4: Single fill implementation with no submit capability

**Files:**
- Create: extension/content/fill-form.js
- Create: extension/tests/fill-form.test.mjs
- Modify: extension/lib/protocol.js
- Modify: extension/background/router.js

**Interfaces:**
- FILL_FORM payload: identity, generation, fields.
- FILL_FORM result: identity, generation_after, field_results.
- field_results per field: before, proposed, after, status.
- There is no SUBMIT, COMPLEMENT, SEND or AUTO_SUBMIT protocol type.

- [ ] **Step 1: Write failing fill tests**

Port write/verify behavior from the current form-detector.js and relevant preflight tests.

Required cases:
- native value setter is used;
- input/change/blur events bubble;
- select value must exist;
- identity mismatch writes nothing;
- stale generation writes nothing;
- disabled/readOnly writes nothing;
- a failed field verification returns failure and the backend does not mark PREENCHIDO.

- [ ] **Step 2: Add a protocol-negative test**

~~~javascript
const types = Object.values(MESSAGE_TYPES);
for (const forbidden of ["SUBMIT", "SEND", "AUTO_SUBMIT", "COMPLEMENT_ACT"]) {
  assert.equal(types.includes(forbidden), false);
}
~~~

Also scan root extension source in the test and fail if exact submit button click logic is added.

- [ ] **Step 3: Verify RED**

Run: cd extension && node --test tests/fill-form.test.mjs tests/protocol.test.mjs

Expected: fill module missing.

- [ ] **Step 4: Implement fill-form**

Reuse FIELD_MAP:
- modalidade -> txtModalidade
- fundamento_legal -> txtFundamentoLegal
- data_publicacao_doe -> txtDataDOE
- cargo -> txtCargo
- matricula -> txtMatricula
- data_nascimento -> txtDataNascimento
- genero -> txtGenero

Perform one pre-write identity/generation check, write all planned fields, then reread every written/preserved field. Return result; never locate or click the final Complementar Ato button.

- [ ] **Step 5: Verify and commit**

Run root extension npm test and legacy npm test.

~~~text
git add extension
git commit -m "feat: add verified form filling without submission"
~~~

### Task 5: Complete backend orchestration OPEN -> READ -> PREFLIGHT -> FILL

**Files:**
- Modify: app/area_restrita/fill_service.py
- Modify: app/api/server.py
- Modify: app/web/index.html
- Modify: app/web/app.js
- Modify: tests/test_fill_service.py
- Modify: tests/test_api_server.py

**Interfaces:**
- POST /api/v1/processes/ID/fill -> fill_request_id
- GET /api/v1/fill-requests/ID -> state/result
- successful READ_FORM result runs build_fill_plan and queues FILL_FORM.
- successful verified FILL_FORM sets process status PREENCHIDO and workflow event form_filled.
- blocked preflight keeps process REVISAR or BLOQUEADO and writes no FILL_FORM command.

- [ ] **Step 1: Write failing full-chain test**

Mock extension command results:
1. OPEN_ACT success;
2. READ_FORM with exact identity/options;
3. FILL_FORM with after values equal proposals.

Assert final fill request is PREENCHIDO and process workflow has form_filled.

- [ ] **Step 2: Verify RED**

Run Python fill/API tests.

- [ ] **Step 3: Implement routes and Mesa action**

Show Preencher ato only for PRONTO. While running show Abrindo ato, Lendo formulário, Validando and Preenchendo. Technical command ids remain hidden.

- [ ] **Step 4: Verify GREEN**

Run all Python tests and root extension tests.

- [ ] **Step 5: Commit**

~~~text
git add app tests
git commit -m "feat: drive verified act filling from Mesa"
~~~

### Task 6: Manual current-form fallback using the same filler

**Files:**
- Modify: extension/sidepanel/panel.html
- Modify: extension/sidepanel/panel.js
- Modify: extension/background/router.js
- Modify: app/api/server.py
- Modify: app/area_restrita/fill_service.py
- Modify: extension/tests/router.test.mjs
- Modify: tests/test_fill_service.py

**Interfaces:**
- sidepanel action: Preencher formulário atual.
- extension first READ_FORMs the current tab.
- POST /api/v1/portal/manual-form with snapshot creates a fill request for the matching PRONTO process.
- backend queues the same FILL_FORM command used by automatic navigation.

- [ ] **Step 1: Write failing manual-flow tests**

Assert current form identity finds exactly one PRONTO process. Zero or multiple matches block. Assert the resulting FILL_FORM payload is identical to automatic mode for the same snapshot.

- [ ] **Step 2: Verify RED**

Run Python and root extension tests.

- [ ] **Step 3: Implement minimal sidepanel**

Sidepanel contains only:
- Mesa connected status;
- Área Restrita detected status;
- current process identity if form is open;
- Preencher formulário atual;
- Abrir Mesa;
- diagnostic text.

No dataset import, lot, acquisition, legal-rule or auto-submit controls.

- [ ] **Step 4: Verify GREEN**

Run all root extension tests and fill service tests.

- [ ] **Step 5: Commit**

~~~text
git add extension/sidepanel extension/background app tests
git commit -m "feat: add manual current-form fallback"
~~~

### Task 7: Supervised real filling equivalence gate

**Files:** code only when a defect is reproduced and tested.

- [ ] **Step 1: Use one real PRONTO process and automatic Open/Read only.**

Confirm identity and option catalogs without writing.

- [ ] **Step 2: Run backend preflight and inspect proposed values in the Mesa.**

Do not issue FILL_FORM if any value is unexpected.

- [ ] **Step 3: Authorize FILL_FORM for that process and verify DOM reread.**

No final click. Compare all six mandatory values and optional genero behavior.

- [ ] **Step 4: Repeat with manual current-form fallback.**

The same process/snapshot must generate the same fill plan.

- [ ] **Step 5: Expand to a supervised sample of at least five acts before making the new extension the default.**

Any portal-side mismatch blocks M5 exit. Final submission remains manual throughout.

## M5 Exit Gate

- Mesa owns fill workflow.
- New extension supports scan, navigation, form read and form fill only.
- New protocol cannot submit an act.
- Automatic and manual paths share one fill-form implementation.
- Backend preflight is authoritative.
- Real supervised fills reread exactly as proposed.
- Legacy extension remains available for rollback until packaging/cleanup M6.



---

<!-- Source: docs/superpowers/plans/2026-09-18-m6-packaging-storage-cleanup.md -->

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

### Task 2: Hybrid archive manager for HOT, ARCHIVED and MISSING documents

**Files:**
- Create: app/archive/manager.py
- Modify: app/core/store.py
- Modify: app/api/server.py
- Modify: app/web/app.js
- Modify: app/web/index.html
- Create: tests/test_archive_manager.py

**Interfaces:**
- ArchiveManager.archive_process(process_id: int, external_root: Path) -> ArchiveResult
- ArchiveManager.restore_process(process_id: int) -> ArchiveResult
- ArchiveManager.reconcile_locations() -> dict
- document storage_state values: HOT, ARCHIVED, MISSING.
- schema_version becomes 5 through atomic migration 4 -> 5.
- POST /api/v1/processes/ID/archive requires authenticated Mesa session and external_root configured in SQLite metadata.
- POST /api/v1/processes/ID/restore requires authenticated Mesa session.

- [ ] **Step 1: Write failing archive/restore tests**

Create one canonical PDF blob, one process-view hardlink, and SQLite document metadata. Archive to a second temporary root, verify the external SHA, remove the process-view link, mark ARCHIVED, then restore and verify HOT.

Also test reconcile_locations marks MISSING only when neither a verified local blob nor verified external blob exists.

- [ ] **Step 2: Verify RED**

Run: python -m unittest tests.test_archive_manager -v

Expected: archive manager missing.

- [ ] **Step 3: Add blob-location metadata**

Add archive_blobs with sha256 primary key, size_bytes, local_relative_path, external_path, local_present, external_present and verified_at. Migration 4 -> 5 populates rows from existing documents and canonical blob paths.

Documents continue referencing sha256; do not duplicate blob bytes per document.

- [ ] **Step 4: Implement archive safely**

For every distinct SHA referenced by the selected process:
1. copy the canonical blob to external_root/blobs/AA/SHA.pdf using a temporary file;
2. hash the external temporary file;
3. atomically publish it only if SHA matches;
4. remove the selected process-view hardlink;
5. remove the local canonical blob only when no remaining HOT document references that SHA;
6. mark selected documents ARCHIVED.

If any copy/hash fails, leave the local source and metadata HOT.

- [ ] **Step 5: Implement restore and reconciliation**

Restore copies a verified external blob back to the canonical local blob path if absent, recreates the process-view hardlink, verifies SHA, and marks documents HOT. reconcile_locations updates presence flags and marks a document MISSING only when no verified location remains.

- [ ] **Step 6: Add Mesa controls and tests**

Show Arquivar processo only for completed/non-active processes. Show Restaurar documentos for ARCHIVED. Display MISSING as an error state, never as successful archival.

Run: python -m unittest tests.test_archive_manager tests.test_api_server -v

Expected: PASS.

- [ ] **Step 7: Commit**

~~~text
git add app/archive/manager.py app/core/store.py app/api app/web tests/test_archive_manager.py
git commit -m "feat: add hybrid archive management"
~~~

### Task 3: Storage inventory and canonical-copy verifier

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

### Task 4: Explicit full backup and restore manifest

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

### Task 5: New archive-free portable builder

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

### Task 6: Clean extraction smoke and build retention

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

### Task 7: Receipt-driven cleanup tool

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

### Task 8: Make new app/extension/package the default and retire legacy surface

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

