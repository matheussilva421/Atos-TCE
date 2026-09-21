# Automatic Mesa–Extension Trust Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Replace the six-digit manual pairing flow with a zero-touch, self-healing Mesa ↔ ATOS TCE extension connection that requires no password, code, repair button, or user-visible token handling.

**Architecture:** The shipped extension receives a stable Chromium extension identity and the Mesa trusts only that exact chrome-extension origin. The MV3 service worker becomes the only Mesa network owner; chrome.storage.local is the single credential source of truth, automatic registration happens when credentials are missing or rejected, and authenticated requests retry at most once after recovery. The bearer token remains random and only its SHA-256 hash is persisted by the Mesa.

**Tech Stack:** Python stdlib HTTP server + SQLite Store, Chrome/Edge Manifest V3, JavaScript ES modules, chrome.storage.local, chrome.runtime messaging, Node built-in test runner, Python unittest, PowerShell project/package verification.

**Spec:** docs/superpowers/specs/2026-09-21-automatic-extension-trust-design.md

## Global Constraints

- No cloud account.
- No user login.
- No password.
- No manual pairing code.
- No native-messaging migration in this change.
- No redesign of command execution, portal scanning, acquisition, or fill workflows.
- No weakening of the localhost binding or extension-origin checks.
- The final click that complements/submits an act remains human.
- The extension stays Manifest V3 and supports Chrome 116+.
- Plaintext extension bearer tokens must never be persisted in SQLite or written to logs.
- chrome.storage.local is the only persistent credential source on the extension side.
- An authenticated request may perform at most one automatic recovery cycle after HTTP 401.
- Mesa-offline/network errors must not delete valid stored credentials.
- Temporary compatibility with the old pairing flow is allowed only while tasks are in progress; the final state must remove the old flow.

## File Structure / Ownership

- **extension/manifest.json** — stable extension identity and browser permissions.
- **app/api/bridge.py** — trusted extension identity, token generation/hash, Mesa session authority, automatic extension registration primitive.
- **app/api/server.py** — HTTP routes, CORS/origin enforcement, automatic registration endpoint, authenticated extension routes.
- **app/core/store.py** — persistence of client id, token hash, origin, extension id and last_seen_at; no plaintext token storage.
- **extension/lib/api.js** — storage-backed Mesa API client, automatic registration, bounded 401 recovery.
- **extension/lib/protocol.js** — runtime message vocabulary between sidepanel/content scripts and service worker.
- **extension/background/router.js** — sole Mesa network owner for the extension; command polling plus sidepanel bridge calls.
- **extension/sidepanel/panel.js** — presentation/controller only; no bearer-token ownership and no direct Mesa fetch.
- **extension/sidepanel/state.js** — three-state connection presentation.
- **extension/sidepanel/panel.html** — status-only connection UI; no pairing controls.
- **app/web/index.html / app/web/app.js** — remove pairing/repair UI while preserving session handoff to another browser profile.
- **tests/test_bridge.py** — backend registration/auth/security integration tests.
- **tests/test_extension_identity.py** — stable manifest-key ↔ trusted-extension-id parity contract.
- **extension/tests/api.test.mjs** — credential freshness, recovery, retry-bound and offline behavior.
- **extension/tests/router.test.mjs** — service-worker ownership of Mesa calls and sidepanel request routing.
- **extension/tests/sidepanel-state.test.mjs** — visible connection-state contract.
- **extension/tests/sidepanel-wiring.test.mjs** — absence of pairing UI/direct Mesa API ownership.
- **app/web/tests/ui-wiring.test.mjs** — Mesa web removal of pairing controls while preserving session handoff.
- **tests/test_packaging_contract.py** — portable package preserves the stable extension identity.
- **README.md** — operator instructions for automatic connection.

## Review Focus

1. **Two simultaneous callers after a stale token:** the service worker must coalesce registration and never create an unbounded registration storm; Task 3 tests this.
2. **Token changes between a 401 and recovery:** the caller must re-read chrome.storage.local and adopt the newer token before rotating again; Task 3 tests this.
3. **Mesa offline during recovery:** stored credentials must survive network failure and the UI must report Mesa unavailable rather than “auth failed”; Tasks 3 and 5 test this.
4. **Unexpected extension origin with a valid-looking client id:** automatic registration and authenticated routes must reject it; Tasks 1 and 2 test this.
5. **Portable ZIP changes the extension identity:** packaging must preserve manifest.key and the trusted id parity; Task 8 tests this.

---

## Execution Preflight

Before Task 1, use **superpowers:using-git-worktrees** and work from an isolated worktree based on branch **codex/mesa-local-refactor** at or after commit **c4aae27**.

Run the current baseline before changing code:

~~~powershell
git status --short
git rev-parse --short HEAD
python -m unittest tests.test_bridge tests.test_extension_parity -v
npm test --prefix extension
python -m unittest tests.test_web_suite -v
git diff --check
~~~

Expected: clean tracked tree and all listed tests green. Preserve unrelated untracked local files; do not delete or stage them.

---

### Task 1: Pin one stable trusted extension identity

**Files:**
- Modify: extension/manifest.json
- Modify: app/api/bridge.py (extension-origin helpers near is_extension_origin / extension_id_from_origin)
- Create: tests/test_extension_identity.py

**Interfaces:**
- Produces: TRUSTED_EXTENSION_ID: str
- Produces: is_trusted_extension_origin(origin: str | None) -> bool
- Contract: the Manifest V3 public key must deterministically derive the same extension id trusted by the Mesa.

- [ ] **Step 1: Add a failing parity/security test**

Create **tests/test_extension_identity.py** with tests equivalent to:

~~~python
import base64
import hashlib
import json
import unittest
from pathlib import Path

from app.api.bridge import TRUSTED_EXTENSION_ID, is_trusted_extension_origin

ROOT = Path(__file__).resolve().parents[1]
ALPHABET = "abcdefghijklmnop"

def chromium_extension_id(public_key_der: bytes) -> str:
    digest = hashlib.sha256(public_key_der).digest()[:16]
    return "".join(ALPHABET[b >> 4] + ALPHABET[b & 0x0F] for b in digest)

class ExtensionIdentityTests(unittest.TestCase):
    def test_manifest_key_derives_the_id_trusted_by_the_mesa(self):
        manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
        derived = chromium_extension_id(base64.b64decode(manifest["key"]))
        self.assertEqual(derived, TRUSTED_EXTENSION_ID)

    def test_only_the_shipped_extension_origin_is_trusted(self):
        self.assertTrue(
            is_trusted_extension_origin(f"chrome-extension://{TRUSTED_EXTENSION_ID}")
        )
        self.assertFalse(
            is_trusted_extension_origin("chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        )
        self.assertFalse(is_trusted_extension_origin("https://example.com"))
        self.assertFalse(is_trusted_extension_origin(None))

if __name__ == "__main__":
    unittest.main()
~~~

- [ ] **Step 2: Run the test and verify RED**

~~~powershell
python -m unittest tests.test_extension_identity -v
~~~

Expected: FAIL because manifest.key and/or TRUSTED_EXTENSION_ID do not exist.

- [ ] **Step 3: Pin the stable public key in the manifest**

Add this exact top-level Manifest V3 key to **extension/manifest.json**:

~~~json
"key": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxnww2cI97CqnnyOy6kUt5XlHO4QGdudo6Jxo0OSvwg/O8GnfN/IKi+TboVMS/2IzsdGVIXAkmDBiY3ASZjvIw70EWMqwzSPPm/hcoyGpgVG6raKdrCcbWJmfPKbXGo/w7kj1J3XGiw02tJLuDXIStLk/7IktnP8juapBnoSfInq9j6Hvc8Wib1EjRj2XiFWkdL0pGNkecfv7zKTaIKWkFM9fGVlfzOs5IwmlZ6tOBIvYI00wSluDZYlLRz8/9w8MejsEe2Q2inej+fTeuRITgDYSaDH+x7om5SraFiEGx6XTZaFjgsGxW8Oqwa/4mWIBZHQO3Os6g2hAI81pFwFhNQIDAQAB"
~~~

This public key deterministically yields extension id:

~~~text
nhpklhieopdbomkojifcengjaklabjng
~~~

Do not generate or commit a private key.

- [ ] **Step 4: Add the Mesa trust helper**

In **app/api/bridge.py**, keep extension_id_from_origin() and add:

~~~python
TRUSTED_EXTENSION_ID = "nhpklhieopdbomkojifcengjaklabjng"

def is_trusted_extension_origin(origin: str | None) -> bool:
    return extension_id_from_origin(origin) == TRUSTED_EXTENSION_ID
~~~

Do not weaken is_extension_origin(); authenticated routes still derive the id from Origin.

- [ ] **Step 5: Run identity tests GREEN**

~~~powershell
python -m unittest tests.test_extension_identity -v
~~~

Expected: PASS.

- [ ] **Step 6: Commit**

~~~powershell
git add extension/manifest.json app/api/bridge.py tests/test_extension_identity.py
git commit -m "feat: pin trusted extension identity"
~~~

---

### Task 2: Add automatic Mesa registration without removing old pairing yet

**Files:**
- Modify: app/api/bridge.py (Bridge extension credential methods)
- Modify: app/api/server.py (route tables, CORS and registration handler)
- Modify: tests/test_bridge.py (new automatic-registration cases only; keep old pairing tests temporarily)

**Interfaces:**
- Consumes: TRUSTED_EXTENSION_ID and is_trusted_extension_origin()
- Produces: Bridge.register(store: Store, client_id: str, origin: str) -> str | None
- Produces: POST /api/v1/bridge/register with body {"client_id": "..."}
- Returns: {"token": "...", "token_type": "Bearer", "client_id": "..."} on success

- [ ] **Step 1: Write backend RED tests**

Add focused tests to **tests/test_bridge.py**:

~~~python
def register(self, client_id="extension-test", origin=EXTENSION_ORIGIN):
    return self.call_json(
        "/api/v1/bridge/register",
        method="POST",
        headers={"Origin": origin},
        body={"client_id": client_id},
    )

def test_trusted_extension_registers_without_a_code(self):
    status, _headers, payload = self.register()
    self.assertEqual(status, 200, payload)
    self.assertTrue(payload["token"])
    self.assertEqual(payload["client_id"], "extension-test")

def test_registration_token_authenticates_immediately(self):
    _status, _headers, registered = self.register()
    status, _headers, payload = self.call_json(
        "/api/v1/bridge/status",
        headers=self.extension_headers(registered["token"]),
    )
    self.assertEqual(status, 200, payload)
    self.assertTrue(payload["paired"])

def test_registration_rejects_an_untrusted_extension_origin(self):
    status, _headers, payload = self.register(
        origin="chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    self.assertEqual(status, 403)
    self.assertEqual(payload["error"], "extension_not_trusted")
    self.assertEqual(self.store.list_bridge_clients(), [])

def test_registration_persists_only_the_token_hash(self):
    _status, _headers, payload = self.register()
    token = payload["token"]
    row = self.store.list_bridge_clients()[0]
    self.assertEqual(row["token_hash"], hash_token(token))
    self.assertNotIn(token.encode("utf-8"), (self.data_root / "atos-tce.db").read_bytes())

def test_re_registration_rotates_a_rejected_credential(self):
    _status, _headers, first = self.register()
    _status, _headers, second = self.register()
    self.assertNotEqual(first["token"], second["token"])

    status, _headers, _payload = self.call_json(
        "/api/v1/bridge/status",
        headers=self.extension_headers(first["token"]),
    )
    self.assertEqual(status, 401)

    status, _headers, payload = self.call_json(
        "/api/v1/bridge/status",
        headers=self.extension_headers(second["token"]),
    )
    self.assertEqual(status, 200, payload)
~~~

Use the real shipped trusted id from Task 1 for EXTENSION_ORIGIN:

~~~python
from app.api.bridge import TRUSTED_EXTENSION_ID
EXTENSION_ORIGIN = f"chrome-extension://{TRUSTED_EXTENSION_ID}"
~~~

- [ ] **Step 2: Verify RED**

~~~powershell
python -m unittest tests.test_bridge.ExtensionPairingTests -v
~~~

Expected: new /bridge/register tests fail with 404 or missing method.

- [ ] **Step 3: Implement Bridge.register()**

In **app/api/bridge.py** add a method that:
1. strips and validates client_id;
2. requires is_trusted_extension_origin(origin);
3. generates a fresh new_token();
4. writes only hash_token(token), origin and the derived extension id using Store.pair_bridge_client();
5. returns the plaintext token once to the handler.

Minimal shape:

~~~python
def register(self, store: Store, client_id: str, origin: str) -> str | None:
    client_id = str(client_id or "").strip()
    if not client_id or not is_trusted_extension_origin(origin):
        return None
    extension_id = extension_id_from_origin(origin)
    token = new_token()
    store.pair_bridge_client(
        client_id,
        hash_token(token),
        origin=str(origin).strip(),
        extension_id=extension_id,
    )
    return token
~~~

Do not remove pair() yet; removal is Task 7 after the new path is green.

- [ ] **Step 4: Add POST /api/v1/bridge/register**

In **app/api/server.py** add the public POST route and handler:

~~~python
Route(re.compile(r"/api/v1/bridge/register"), "post_bridge_register", "public"),
~~~

Handler behavior:

~~~python
def post_bridge_register(self) -> None:
    origin = str(self.headers.get("Origin") or "").strip()
    if not is_trusted_extension_origin(origin):
        self._send_json({"error": "extension_not_trusted"}, status=403)
        return
    self.cors_origin = origin
    payload = self._read_json_body()
    client_id = str(payload.get("client_id") or "").strip()
    token = self.mesa.bridge.register(self.mesa.store, client_id, origin)
    if token is None:
        self._send_json({"error": "registration_rejected"}, status=400)
        return
    self._send_json(
        {"token": token, "token_type": "Bearer", "client_id": client_id}
    )
~~~

Import is_trusted_extension_origin from app.api.bridge.

- [ ] **Step 5: Verify backend GREEN and security regression**

~~~powershell
python -m unittest tests.test_extension_identity tests.test_bridge -v
~~~

Expected: PASS, including existing token/origin/CORS/session tests.

- [ ] **Step 6: Commit**

~~~powershell
git add app/api/bridge.py app/api/server.py tests/test_bridge.py
git commit -m "feat: add automatic extension registration"
~~~

---

### Task 3: Make extension credentials storage-authoritative and self-healing

**Files:**
- Modify: extension/lib/api.js
- Modify: extension/tests/api.test.mjs
- Modify: extension/tests/helpers.mjs only if the test double needs delayed/concurrent route support

**Interfaces:**
- Produces: api.register() -> {ok, status, clientId?, error?}
- Produces: api.status(), nextCommand(), reportResult(), requestManualFill() with transparent missing-token/401 recovery
- Invariant: every authenticated attempt reads chrome.storage.local immediately before choosing credentials.
- Invariant: registration is single-flight inside the service-worker API instance.
- Invariant: after one recovery retry, a second 401 is returned to the caller; no loop.

- [ ] **Step 1: Replace pairing-centric tests with RED automatic-auth tests**

In **extension/tests/api.test.mjs**, remove the pair(code) expectations and add tests for:

~~~javascript
test("empty storage automatically registers before status", async () => {
  const { api, storage, fetchImpl } = build({
    routes: [
      {
        path: "/api/v1/bridge/register",
        method: "POST",
        body: { token: "fresh-token", client_id: CLIENT_ID },
      },
      {
        path: "/api/v1/bridge/status",
        body: { paired: true, client_id: CLIENT_ID },
      },
    ],
  });

  const outcome = await api.status();

  assert.equal(outcome.ok, true);
  assert.equal(outcome.paired, true);
  assert.equal(storage.data.get(STORAGE_KEYS.token), "fresh-token");
  assert.equal(fetchImpl.calls[0].url.endsWith("/api/v1/bridge/register"), true);
  assert.equal(fetchImpl.calls[1].headers.Authorization, "Bearer fresh-token");
});
~~~

Add a stale-token recovery test:

~~~javascript
test("401 automatically registers and retries exactly once", async () => {
  let statusCalls = 0;
  const { api, fetchImpl } = build({
    data: new Map([
      [STORAGE_KEYS.clientId, CLIENT_ID],
      [STORAGE_KEYS.token, "stale-token"],
    ]),
    routes: [
      {
        path: "/api/v1/bridge/status",
        body: () => {
          statusCalls += 1;
          return statusCalls === 1
            ? { __status: 401, error: "unauthorized" }
            : { paired: true, client_id: CLIENT_ID };
        },
      },
      {
        path: "/api/v1/bridge/register",
        method: "POST",
        body: { token: "fresh-token", client_id: CLIENT_ID },
      },
    ],
  });

  const outcome = await api.status();

  assert.equal(outcome.ok, true);
  assert.equal(statusCalls, 2);
  assert.equal(
    fetchImpl.calls.filter((call) => call.url.endsWith("/api/v1/bridge/register")).length,
    1
  );
});
~~~

If fakeFetch cannot vary status from a route function, extend the route double explicitly so a function may return {status, body}; do not encode test-only behavior in production code.

Add tests for:
- a second 401 after recovery stops and returns unauthorized;
- network failure leaves storage untouched;
- a token changed in storage after the first 401 is retried before register();
- two createApi() instances sharing one storage object always use the latest token;
- two simultaneous operations on one API instance share one registration promise;
- reportResult and nextCommand still send Authorization and X-TCE-Client.

- [ ] **Step 2: Verify RED**

~~~powershell
npm test --prefix extension -- --test-name-pattern="register|401|storage|credential|token"
~~~

Expected: FAIL because api.js still caches state and exposes manual pair().

- [ ] **Step 3: Remove the credential cache**

In **extension/lib/api.js** delete the long-lived:

~~~javascript
let state = null;
~~~

Make readStoredState() the authority for every call. saveCredentials() writes storage, then returns the written object; it must not establish an in-memory token cache.

Keep only an in-flight Promise for registration coordination:

~~~javascript
let registrationInFlight = null;
~~~

This Promise is coordination state, not credential state.

- [ ] **Step 4: Implement register()**

Registration must:
1. read storage fresh;
2. reuse existing clientId or create one;
3. POST /api/v1/bridge/register with only {client_id};
4. save client id + returned token + current baseUrl;
5. share one in-flight registration promise for concurrent callers;
6. clear registrationInFlight in finally.

Do not send extension_id in the request body; the Mesa derives it from Origin.

- [ ] **Step 5: Implement bounded authenticatedRequest()**

Use one helper for all authenticated endpoints. Its exact algorithm:

~~~text
read credentials
if missing -> register -> reread credentials
send request
if response != 401 -> return
reread storage
if credentials changed since failed attempt -> retry once with changed credentials
else -> register -> reread -> retry once
return second result even if it is 401
~~~

No recursive retry. No credential deletion on fetch/network errors.

Convert status(), nextCommand(), reportResult() and requestManualFill() to use this helper.

Remove pair() and clear() from the public API once no test depends on them.

- [ ] **Step 6: Verify focused API GREEN**

~~~powershell
npm test --prefix extension -- --test-name-pattern="register|401|storage|credential|token|nextCommand|reportResult|status"
~~~

Expected: PASS.

- [ ] **Step 7: Run the whole extension suite**

~~~powershell
npm test --prefix extension
~~~

Expected: PASS.

- [ ] **Step 8: Commit**

~~~powershell
git add extension/lib/api.js extension/tests/api.test.mjs extension/tests/helpers.mjs
git commit -m "feat: auto-recover extension credentials"
~~~

---

### Task 4: Make the MV3 service worker the sole Mesa network owner

**Files:**
- Modify: extension/lib/protocol.js
- Modify: extension/background/router.js
- Modify: extension/sidepanel/panel.js
- Modify: extension/tests/router.test.mjs

**Interfaces:**
- Produces runtime message: MESA_STATUS
- Produces runtime message: REQUEST_MANUAL_FILL
- Sidepanel consumes only chrome.runtime messaging for Mesa operations.
- Service worker owns one createApi() instance and therefore one registration single-flight.

- [ ] **Step 1: Add RED router-message tests**

Extend MESSAGE_TYPES expectations and add router tests equivalent to:

~~~javascript
test("the router answers MESA_STATUS through the Mesa API", async () => {
  const chromeApi = fakeChrome();
  installRouter({
    api: {
      status: async () => ({ ok: true, status: 200, paired: true }),
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
  });

  const response = await sendRuntime(chromeApi, { type: "MESA_STATUS" });

  assert.equal(response.ok, true);
  assert.equal(response.paired, true);
});
~~~

Add:

~~~javascript
test("the router sends manual fill through its Mesa API", async () => {
  const chromeApi = fakeChrome();
  let received = null;
  installRouter({
    api: {
      status: async () => ({ ok: true, paired: true }),
      requestManualFill: async (form) => {
        received = form;
        return { ok: true, status: 201, payload: { state: "READY" } };
      },
      nextCommand: async () => ({ ok: true, command: null }),
      reportResult: async () => {},
    },
    chromeApi,
  });

  const form = { identity: { processKey: "102390/2026" } };
  const response = await sendRuntime(chromeApi, {
    type: "REQUEST_MANUAL_FILL",
    payload: form,
  });

  assert.equal(response.ok, true);
  assert.deepEqual(received, form);
});
~~~

Implement a local sendRuntime helper in the test that invokes registered listeners and resolves sendResponse, matching the existing READ_CURRENT_FORM test style.

- [ ] **Step 2: Verify RED**

~~~powershell
npm test --prefix extension -- --test-name-pattern="MESA_STATUS|manual fill"
~~~

Expected: FAIL because those message types/listeners do not exist.

- [ ] **Step 3: Add protocol message types**

In **extension/lib/protocol.js** add:

~~~javascript
MESA_STATUS: "MESA_STATUS",
REQUEST_MANUAL_FILL: "REQUEST_MANUAL_FILL",
~~~

Do not alter command types.

- [ ] **Step 4: Route Mesa operations in background/router.js**

In the existing runtime.onMessage listener:
- READ_CURRENT_FORM keeps its current behavior;
- MESA_STATUS calls api.status();
- REQUEST_MANUAL_FILL calls api.requestManualFill(message.payload);
- POLL_COMMANDS keeps its current poll behavior;
- each async branch returns true and resolves sendResponse;
- errors are sanitized to {ok:false, status:0, error:String(...)}.

The sidepanel must no longer instantiate createApi().

- [ ] **Step 5: Change panel.js to call the worker**

Remove createApi import and all direct api.status()/api.requestManualFill() calls.

Use:

~~~javascript
await chrome.runtime.sendMessage({ type: MESSAGE_TYPES.MESA_STATUS })
~~~

and:

~~~javascript
await chrome.runtime.sendMessage({
  type: MESSAGE_TYPES.REQUEST_MANUAL_FILL,
  payload: form,
})
~~~

Keep READ_CURRENT_FORM routed through the worker as it is today.

- [ ] **Step 6: Verify router and full extension GREEN**

~~~powershell
npm test --prefix extension -- --test-name-pattern="router|MESA_STATUS|manual fill|READ_CURRENT_FORM"
npm test --prefix extension
~~~

Expected: PASS.

- [ ] **Step 7: Commit**

~~~powershell
git add extension/lib/protocol.js extension/background/router.js extension/sidepanel/panel.js extension/tests/router.test.mjs
git commit -m "refactor: centralize Mesa access in service worker"
~~~

---

### Task 5: Remove pairing UX from the extension and expose only simple connection states

**Files:**
- Modify: extension/sidepanel/panel.html
- Modify: extension/sidepanel/panel.js
- Modify: extension/sidepanel/state.js
- Delete: extension/sidepanel/operation-queue.js
- Delete: extension/tests/operation-queue.test.mjs
- Modify: extension/tests/sidepanel-state.test.mjs
- Create: extension/tests/sidepanel-wiring.test.mjs

**Interfaces:**
- describeMesaStatus(status) returns one of:
  - Mesa conectada
  - Conectando à Mesa…
  - Mesa não encontrada
- No DOM element or event named pair, pairing, repair or code remains in the sidepanel.

- [ ] **Step 1: Write RED state tests**

Replace the obsolete “fresh pairing” state test with:

~~~javascript
test("connected status is simple", () => {
  const state = describeMesaStatus({ ok: true, status: 200, paired: true });
  assert.equal(state.label, "Mesa conectada");
  assert.equal(state.tone, "ok");
});

test("startup/recovery status says connecting", () => {
  const state = describeMesaStatus({ ok: false, status: 401, recovering: true });
  assert.equal(state.label, "Conectando à Mesa…");
  assert.equal(state.tone, "warn");
});

test("network failure says Mesa not found", () => {
  const state = describeMesaStatus({ ok: false, status: 0, error: "fetch_failed" });
  assert.equal(state.label, "Mesa não encontrada");
  assert.equal(state.tone, "error");
});
~~~

Create **extension/tests/sidepanel-wiring.test.mjs** that reads panel.html and panel.js and asserts:
- no pair-code;
- no pair-action;
- no pair-section;
- no “Parear”;
- no “Reparear”;
- no createApi import;
- runtime messages MESA_STATUS and REQUEST_MANUAL_FILL are present.

- [ ] **Step 2: Verify RED**

~~~powershell
npm test --prefix extension -- --test-name-pattern="sidepanel|connection|pair"
~~~

Expected: FAIL against current pairing UI.

- [ ] **Step 3: Simplify panel.html**

Delete the entire pair-section, label, six-digit input and Parear button.

Initial Mesa text becomes:

~~~html
<span id="mesa-status">Conectando à Mesa…</span>
~~~

Keep Área Restrita state, current-form fallback and Abrir Mesa.

- [ ] **Step 4: Simplify panel.js**

Remove:
- createSerialQueue import;
- mesaOperations;
- needsFreshPairing;
- pair-action listener;
- all api.clear()/pair logic.

refreshMesa() asks the worker for MESA_STATUS and renders describeMesaStatus().

The five-second refresh may remain; it now performs status observation only and cannot mutate credentials itself.

- [ ] **Step 5: Simplify state.js**

Implement the three labels above. A post-recovery unauthorized/configuration fault may attach diagnostic text, but the main visible state must remain one of those three labels.

- [ ] **Step 6: Delete obsolete operation queue**

Delete:
- extension/sidepanel/operation-queue.js
- extension/tests/operation-queue.test.mjs

The queue was a mitigation for manual-pairing races and is no longer needed once the sidepanel owns no credentials.

- [ ] **Step 7: Verify full extension GREEN**

~~~powershell
npm test --prefix extension
~~~

Expected: PASS and no manual-pairing test remains.

- [ ] **Step 8: Commit**

~~~powershell
git add -A extension/sidepanel extension/tests
git commit -m "refactor: remove extension pairing UI"
~~~

---

### Task 6: Remove pairing/repair UI from the Mesa web app while preserving session handoff

**Files:**
- Modify: app/web/index.html (current pairing block around lines 44-55)
- Modify: app/web/app.js (current refreshPairing/renewPairing/resetPairing block around lines 306-363 and startup/listener wiring)
- Modify: app/web/app.css only to remove selectors that become unused
- Modify: app/web/tests/ui-wiring.test.mjs

**Interfaces:**
- Session handoff remains POST /api/v1/session/handoff.
- Mesa web no longer exposes bridge pairing state, code renewal or repair controls.

- [ ] **Step 1: Replace pairing UI tests with RED absence tests**

In **app/web/tests/ui-wiring.test.mjs**, delete:
- “the Mesa offers to re-pair…”
- “the pairing area explains…”

Add:

~~~javascript
test("the Mesa web UI has no manual extension pairing controls", () => {
  assert.doesNotMatch(page, /reset-pairing/u);
  assert.doesNotMatch(page, /renew-pairing/u);
  assert.doesNotMatch(page, /pairing-code/u);
  assert.doesNotMatch(page, /Reparear extensão/u);
  assert.doesNotMatch(source, /bridge\/pairing\/reset/u);
  assert.doesNotMatch(source, /bridge\/pairing\/renew/u);
});

test("session handoff remains independent from extension authentication", () => {
  assert.match(page, /id="handoff-session"/u);
  assert.match(page, /Copiar sessão para outro Chrome/u);
  assert.match(source, /\/api\/v1\/session\/handoff/u);
});
~~~

- [ ] **Step 2: Verify RED**

~~~powershell
node --test app/web/tests/ui-wiring.test.mjs
~~~

Expected: FAIL because the current pairing controls still exist.

- [ ] **Step 3: Move session handoff out of the pairing block**

In **app/web/index.html** remove:
- pairing-state;
- pairing-code;
- renew-pairing;
- reset-pairing.

Keep handoff-session and handoff-status in a small session-tools container associated with the existing Área Restrita/Mesa session controls.

- [ ] **Step 4: Delete manual pairing controller code**

In **app/web/app.js** remove:
- refreshPairing();
- renewPairing();
- resetPairing();
- listeners for renew-pairing/reset-pairing;
- periodic/startup calls whose only purpose is refreshPairing.

Keep handoffSession() and its listener.

- [ ] **Step 5: Remove only now-unused CSS selectors**

Search:

~~~powershell
Select-String -Path .appwebapp.css,.appweb*.html,.appweb*.js -Pattern "pairing"
~~~

If a pairing-specific CSS rule is no longer referenced by HTML/JS after Steps 3-4, delete that rule. Do not restyle unrelated Mesa components.

- [ ] **Step 6: Verify web tests GREEN**

~~~powershell
node --test app/web/tests/*.test.mjs
python -m unittest tests.test_web_suite -v
~~~

Expected: PASS.

- [ ] **Step 7: Commit**

~~~powershell
git add app/web/index.html app/web/app.js app/web/app.css app/web/tests/ui-wiring.test.mjs
git commit -m "refactor: remove Mesa pairing controls"
~~~

---

### Task 7: Delete the obsolete six-digit pairing backend

**Files:**
- Modify: app/api/bridge.py
- Modify: app/api/server.py
- Modify: tests/test_bridge.py
- Modify: README.md
- Review only: docs/notes/2026-09-21-extensao-token-recusado-handoff.md (historical note; do not rewrite history)

**Interfaces:**
- Automatic registration remains POST /api/v1/bridge/register.
- Extension authentication remains Bearer token + X-TCE-Client + trusted Origin.
- Manual pairing endpoints cease to exist.

- [ ] **Step 1: Write RED endpoint-removal tests**

In **tests/test_bridge.py**, add explicit checks that the retired routes are unavailable:

~~~python
def test_manual_pairing_endpoints_are_retired(self):
    for path, method in (
        ("/api/v1/bridge/pair", "POST"),
        ("/api/v1/bridge/pairing/renew", "POST"),
        ("/api/v1/bridge/pairing/reset", "POST"),
    ):
        status, _headers, _payload = self.call_json(
            path,
            method=method,
            headers={"Origin": EXTENSION_ORIGIN},
            body={},
        )
        self.assertEqual(status, 404, path)
~~~

For GET /api/v1/bridge/pairing, use the Mesa session opener and assert 404.

Before running, rewrite test helpers and command API tests to obtain tokens through /bridge/register rather than self.pair().

- [ ] **Step 2: Verify RED**

~~~powershell
python -m unittest tests.test_bridge -v
~~~

Expected: FAIL while old endpoints still exist.

- [ ] **Step 3: Remove pairing-code state from Bridge**

Delete from **app/api/bridge.py**:
- PAIRING_CODE_LENGTH;
- PAIRING_TTL_SECONDS;
- PAIRING_MAX_ATTEMPTS;
- new_pairing_code();
- pairing-code fields/state in Bridge;
- pairing_code;
- pairing_is_active();
- pairing_expires_in;
- renew_pairing_code();
- _accept_code();
- pair().

Keep:
- token hashing/generation;
- register();
- bootstrap/session/handoff;
- extension-origin helpers.

Do not alter Mesa browser session security.

- [ ] **Step 4: Remove obsolete routes and handlers**

Delete from **app/api/server.py**:
- GET /api/v1/bridge/pairing;
- POST /api/v1/bridge/pair;
- POST /api/v1/bridge/pairing/renew;
- POST /api/v1/bridge/pairing/reset;
- handle_bridge_pairing();
- post_bridge_pair();
- post_pairing_renew();
- post_pairing_reset();
- _pairing_payload().

Keep:
- /api/v1/bridge/register;
- /api/v1/bridge/status;
- extension command routes;
- session bootstrap/handoff.

- [ ] **Step 5: Rewrite bridge tests around automatic registration**

Rename ExtensionPairingTests to ExtensionRegistrationTests.

Delete tests whose only requirement was:
- code reuse;
- wrong-code attempt limit;
- code expiration;
- code renewal/reset.

Retain and adapt tests for:
- unregistered extension rejected from authenticated routes;
- token hash only;
- wrong origin rejected;
- missing origin rejected;
- last_seen_at advances;
- token survives Mesa restart because hash is in SQLite;
- command polling/results;
- Mesa session security.

- [ ] **Step 6: Update README operator flow**

Replace the current extension paragraph that says “O pareamento é feito com o código…” with:

~~~text
A extensão suportada é a da raiz, extension/ (Manifest V3 fina). Depois de carregada no Chrome/Edge, ela reconhece a Mesa local automaticamente; não há senha, código de pareamento ou etapa de reparo. Se a credencial local ficar ausente ou inválida, o service worker registra novamente a extensão confiável e refaz a chamada uma única vez.
~~~

Keep the separate Mesa-session/bootstrap instructions for the web UI; those are not extension pairing.

- [ ] **Step 7: Verify backend + docs contract GREEN**

~~~powershell
python -m unittest tests.test_extension_identity tests.test_bridge -v
Select-String -Path .appapiridge.py,.appapiserver.py,.extensionsidepanel*,.appwebindex.html,.appwebapp.js,.README.md -Pattern "pairing_code|pairing/renew|pairing/reset|Código exibido na Mesa|Reparear extensão"
~~~

Expected: tests PASS; search returns no active runtime/UI references. Historical docs are intentionally outside this search.

- [ ] **Step 8: Commit**

~~~powershell
git add app/api/bridge.py app/api/server.py tests/test_bridge.py README.md
git commit -m "refactor: retire manual bridge pairing"
~~~

---

### Task 8: Lock packaging identity and run complete regression gates

**Files:**
- Modify: tests/test_packaging_contract.py
- Modify: packaging/build-portable.ps1 only if the existing copy logic strips/rewrites manifest content; otherwise leave unchanged.
- Modify: packaging/verify-package.ps1 only if an explicit extension-identity assertion belongs there; prefer the Python contract test to avoid duplicate logic.
- Modify: docs/notes/2026-09-21-automatic-extension-trust-handoff.md (create final implementation/QA handoff)

**Interfaces:**
- Portable ZIP must contain extension/manifest.json with the exact stable key.
- Trusted id remains nhpklhieopdbomkojifcengjaklabjng.

- [ ] **Step 1: Add RED packaging identity test**

In **tests/test_packaging_contract.py**, add a contract that reads the source manifest and, when inspecting the built package fixture/path used by the existing suite, asserts:
1. extension/manifest.json is present;
2. its key equals the source manifest key;
3. that key derives extension id nhpklhieopdbomkojifcengjaklabjng.

Reuse the same SHA-256 nibble mapping from tests/test_extension_identity.py or move the pure helper into that test module and import it; do not duplicate production auth logic merely for packaging.

- [ ] **Step 2: Run packaging test RED/GREEN**

~~~powershell
python -m unittest tests.test_packaging_contract -v
~~~

If it already passes because packaging copies the extension byte-for-byte, keep production packaging scripts unchanged. A test that passes without production changes is acceptable here because the task locks an existing required property.

- [ ] **Step 3: Run all extension and web tests**

~~~powershell
npm test --prefix extension
node --test app/web/tests/*.test.mjs
~~~

Expected: PASS.

- [ ] **Step 4: Run the complete Python suite**

~~~powershell
python -m unittest discover -s tests -p 'test_*.py' -q
~~~

Expected: PASS.

- [ ] **Step 5: Run package contract and offline project gate**

~~~powershell
python -m unittest tests.test_packaging_contract -v
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .work	ce-extractorerify-project.ps1
git diff --check
~~~

Expected: zero failures; only previously documented environmental skips are acceptable.

- [ ] **Step 6: Build and verify the portable package**

~~~powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .packaginguild-portable.ps1
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .packagingerify-package.ps1 -ZipPath .distAtos-TCE-portable.zip
~~~

Expected: package verification PASS and no data/, browser profile, SQLite DB, token, PDF or private key included.

- [ ] **Step 7: Perform the manual acceptance matrix**

Use a clean Chrome/Edge profile with the unpacked root extension/ folder.

Run exactly:

1. Start Mesa with:
~~~powershell
.START.cmd --data-root data --port 18743
~~~
2. Reload the extension at chrome://extensions.
3. Do not enter a password/code and do not click any pairing control.
4. Confirm sidepanel changes from “Conectando à Mesa…” to “Mesa conectada”.
5. Confirm GET /api/v1/bridge/status updates the registered client last_seen_at.
6. Close and reopen Chrome; confirm automatic reconnection.
7. Stop and restart Mesa; confirm automatic reconnection.
8. In extension DevTools, remove only tce.bridge.token from chrome.storage.local; confirm automatic re-registration and recovery without UI intervention.
9. Set tce.bridge.token to a deliberately invalid value; confirm exactly one registration/retry cycle and recovery.
10. Confirm an untrusted extension origin/client request receives 403 on /bridge/register or 401 on authenticated routes.
11. Confirm command polling still claims a queued STATUS/SCAN_AREA command and reportResult still completes it.
12. Confirm the sidepanel manual “Preencher formulário atual” route still reaches /api/v1/portal/manual-form through the service worker.
13. Confirm there is no Pair, Parear, Reparear, pairing code, password, or repair action in either extension UI or Mesa UI.

Record pass/fail and any sanitized errors; never record bearer tokens.

- [ ] **Step 8: Create the implementation handoff**

Create **docs/notes/2026-09-21-automatic-extension-trust-handoff.md** containing:
- final commit SHA;
- final extension id;
- exact automated test counts/results;
- verify-project result;
- package verification result;
- manual acceptance results for the 13 cases above;
- any environmental skip;
- statement that no plaintext token/private key was committed.

- [ ] **Step 9: Final commit**

~~~powershell
git add tests/test_packaging_contract.py docs/notes/2026-09-21-automatic-extension-trust-handoff.md
git add packaging/build-portable.ps1 packaging/verify-package.ps1
git commit -m "test: verify automatic extension trust end to end"
~~~

If the packaging scripts were unchanged, omit them from git add.

---

## Final Self-Review Checklist

Before calling the work complete:

- [ ] The operator never types a pairing code or password.
- [ ] Neither UI contains Pair/Parear/Reparear/code controls.
- [ ] No active backend route generates or accepts six-digit pairing codes.
- [ ] Only the stable shipped extension id can auto-register.
- [ ] The extension id in manifest.key and Mesa TRUSTED_EXTENSION_ID are parity-tested.
- [ ] chrome.storage.local is the only persistent extension credential source.
- [ ] The sidepanel never directly owns a Mesa API client.
- [ ] Missing credentials self-register.
- [ ] 401 reads storage again before rotating a token.
- [ ] Recovery retries the original operation at most once.
- [ ] Mesa offline never clears credentials.
- [ ] Bearer tokens remain hashed-only in SQLite.
- [ ] Existing command polling, result reporting and manual fill still pass.
- [ ] Mesa browser session/bootstrap/handoff remains separate and secure.
- [ ] Portable packaging preserves the stable extension identity.
- [ ] npm test --prefix extension passes.
- [ ] app/web Node tests pass.
- [ ] Full Python unittest discovery passes.
- [ ] verify-project.ps1 passes.
- [ ] git diff --check passes.
- [ ] Manual clean-profile acceptance passes.

## Recommended Execution Method

Use **superpowers:subagent-driven-development**. The plan crosses Python auth, HTTP/CORS, MV3 storage, service-worker routing, two UIs and packaging; a fresh implementer/reviewer pair per task is worth the extra context because a subtle auth regression could either break every reconnect or accidentally weaken localhost trust.
