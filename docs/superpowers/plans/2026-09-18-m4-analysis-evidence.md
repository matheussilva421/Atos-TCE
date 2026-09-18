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
