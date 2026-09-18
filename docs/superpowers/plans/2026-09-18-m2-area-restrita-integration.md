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
