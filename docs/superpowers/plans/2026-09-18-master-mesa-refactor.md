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
