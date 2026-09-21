# Automatic Mesa–Extension Trust Design

**Date:** 2026-09-21  
**Branch:** `codex/mesa-local-refactor`

## Intent

Replace the current manual six-digit pairing flow with an automatic, invisible connection between the local Mesa and the ATOS TCE browser extension.

The operator experience must be:

1. Start the Mesa.
2. Open Chrome/Edge with the extension installed.
3. The extension detects the Mesa and connects automatically.
4. If credentials become stale, recovery happens automatically.

There must be no password, pairing code, copy/paste step, manual repair button, or user-visible token management.

## Success Criteria

- No six-digit code is generated or shown.
- No `Parear` or `Reparear extensão` action is required.
- A fresh installation establishes trust automatically.
- Restarting the browser preserves or automatically restores connectivity.
- Restarting the Mesa preserves or automatically restores connectivity.
- Reloading/updating the extension does not require user intervention.
- Invalid, missing, or revoked extension credentials recover automatically.
- The side panel exposes only simple operational states:
  - `Mesa conectada`
  - `Conectando à Mesa…`
  - `Mesa não encontrada`
- Existing workflow commands and manual-fill behavior remain unchanged.
- The Mesa continues binding extension requests to the expected extension origin/id and bearer token; localhost must not become an unauthenticated command API.

## Architecture

### 1. Automatic registration

Replace the manual pairing endpoint with an automatic registration handshake.

Proposed endpoint:

`POST /api/v1/bridge/register`

The extension sends its local `client_id`. The Mesa derives the extension id from the browser-controlled `Origin` header and accepts registration only for the configured trusted extension id.

If the client is new or has no valid credential, the Mesa issues a fresh random bearer token, persists only its SHA-256 hash, and returns the plaintext token once.

The operator never sees this token.

### 2. Stable extension identity

The unpacked/development extension must have a stable extension id. The packaging/install flow must guarantee the same trusted id used by the Mesa.

The Mesa must not trust a caller-supplied `extension_id` as authority. The authoritative id remains the id derived from `Origin: chrome-extension://...`.

### 3. Single source of credential truth

`chrome.storage.local` becomes the only source of truth for:

- `clientId`
- `token`
- `baseUrl` if it remains configurable

Remove the long-lived in-memory credential cache currently implemented as `let state = null` in `extension/lib/api.js`.

Every authenticated request reads the current credentials from storage. This prevents sidepanel and MV3 service worker contexts from diverging after registration, recovery, extension reload, or another context updating credentials.

### 4. Automatic recovery

Authenticated operations use this state machine:

```text
request
  |
  +-- no credentials ----------------------+
  |                                        |
  +-- HTTP 401 ----------------------------+--> automatic register
                                                   |
                                                   v
                                           save new credential
                                                   |
                                                   v
                                             retry once
```

Rules:

- Missing credentials trigger automatic registration.
- A 401 triggers automatic re-registration and one retry.
- Never retry registration indefinitely.
- Network refusal / Mesa offline is not treated as an authentication failure.
- A successful registration written by another extension context must be adopted from storage rather than overwritten or cleared.
- Concurrent registration attempts for the same extension/client must converge safely on a valid credential.

### 5. Server-side trust

The Mesa keeps:

- `client_id`
- bearer token hash
- trusted origin
- extension id
- `created_at`
- `last_seen_at`

Authenticated command/status routes continue to require:

- valid bearer token
- `X-TCE-Client`
- expected extension origin/id

Automatic registration removes user ceremony, not request authentication.

### 6. UI simplification

Remove from the side panel:

- pairing code field
- `Parear` button
- pairing-expired/error copy
- `needsFreshPairing`
- explicit pairing repair instructions

Connection UI becomes status-only.

The panel should transition automatically between connecting, connected, and Mesa unavailable states.

### 7. Remove obsolete manual-pairing backend state

After automatic registration is proven:

- remove six-digit pairing-code generation
- remove pairing TTL
- remove maximum-attempt counter
- remove pairing-code renewal
- remove pairing-code consumption state
- remove endpoints whose sole purpose is manual pairing/repair
- remove obsolete pairing UI data from Mesa payloads

Do not remove bearer-token authentication.

## Known Bugs This Design Must Eliminate

### A. Cross-context credential cache divergence

`createApi()` currently caches storage credentials in memory. Sidepanel and service worker therefore can hold different tokens while sharing the same `chrome.storage.local`.

The new design must have tests proving a credential written by one API instance is used by another existing API instance on its next request.

### B. Stale cleanup can report failure after a newer token exists

The current conditional `clear(expected)` correctly refuses to delete newer credentials, but `panel.js` ignores the false result and still marks the profile as requiring fresh pairing.

The new state machine removes this manual cleanup path entirely.

### C. Registration/status race

A successful registration must not be followed by a request using the previous credential. The registration call must persist the new token before any follow-up status/command call is allowed to use credentials.

### D. Multiple sidepanel/service-worker instances

Concurrent extension contexts must not invalidate each other. Storage is authoritative; registration and retry behavior must be idempotent/convergent.

## Error Handling

### Mesa offline

Do not clear credentials. Show `Mesa não encontrada` and retry on the normal heartbeat/recovery cadence.

### 401 unauthorized

Attempt exactly one automatic recovery cycle:

1. read current storage again;
2. if credentials changed since the failed request, retry with the newer credentials;
3. otherwise register automatically;
4. persist returned credential;
5. retry original request once.

If the second authenticated attempt returns 401, surface a diagnostic error and stop the cycle. Do not loop.

### Registration rejected

Treat as a configuration/security fault, not a normal pairing prompt. Log a sanitized reason and show a non-interactive connection error. Never fall back to accepting arbitrary extension origins.

## Tests

Tests must cover at minimum:

1. first automatic connection with empty storage;
2. valid stored credential;
3. invalid stored credential -> auto-register -> retry succeeds;
4. storage changes between failed request and recovery;
5. two API instances share the newest storage credential;
6. sidepanel and service worker do not retain stale token caches;
7. Mesa unavailable does not delete credentials;
8. registration rejects an unexpected extension origin/id;
9. token hash is persisted, plaintext token is not;
10. registration followed immediately by status succeeds;
11. two concurrent registration attempts converge;
12. browser/extension reload preserves connectivity;
13. Mesa restart preserves or transparently restores connectivity;
14. current command polling and result posting remain compatible.

## Non-Goals

- No cloud account.
- No user login.
- No password.
- No manual pairing code.
- No native-messaging migration in this change.
- No redesign of command execution, portal scanning, acquisition, or fill workflows.
- No weakening of the localhost binding or extension-origin checks.

## Migration

During implementation, tests may temporarily support the old manual flow, but the final shipped state must remove it rather than maintain two authentication systems indefinitely.

Existing stale bridge-client rows may be migrated, revoked, or replaced on first automatic registration. The chosen implementation must avoid requiring the operator to delete SQLite rows or browser storage manually.

## Acceptance Test

On a clean local environment:

1. Start the Mesa with `START.cmd`.
2. Load/reload the ATOS TCE extension.
3. Do not enter any code or click any pairing control.
4. Within the normal heartbeat/recovery interval, the panel becomes `Mesa conectada`.
5. Restart Chrome and confirm it reconnects without action.
6. Restart the Mesa and confirm it reconnects without action.
7. Corrupt/remove the stored token and confirm the extension repairs itself automatically.
8. Confirm status/command endpoints still reject unauthenticated or unexpected extension callers.
