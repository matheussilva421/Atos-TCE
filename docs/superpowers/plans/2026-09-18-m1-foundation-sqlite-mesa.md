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
- infer canonical process keys from existing folder/index metadata and upsert records into SQLite.

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
