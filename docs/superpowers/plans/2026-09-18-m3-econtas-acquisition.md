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
