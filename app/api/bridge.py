"""Trusted extension registration, bootstrap and session authority for the Mesa bridge.

Three separate credentials exist and never substitute for one another:

* a **trusted extension registration** tied to the shipped Manifest V3 public
  key and its stable Chrome extension origin;
* a **bearer token** for the extension, of which only the SHA-256 hash is
  persisted, so restarts do not need a new registration;
* a **Mesa session** created by a one-time bootstrap token and carried in an
  HttpOnly ``SameSite=Strict`` cookie.

Every state-changing Mesa route additionally requires a same-origin request,
checked through ``Origin``/``Referer`` and ``Sec-Fetch-Site``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..core.store import Store

TRUSTED_EXTENSION_ID = "nhpklhieopdbomkojifcengjaklabjng"
BOOTSTRAP_TTL_SECONDS = 300.0
SESSION_HANDOFF_TTL_SECONDS = 300.0
SESSION_TTL_SECONDS = 24 * 3600.0
TOKEN_BYTES = 32

SESSION_COOKIE = "mesa_session"


def hash_token(token: str) -> str:
    """Return the only form of a bearer token that is ever persisted."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def is_extension_origin(origin: str | None) -> bool:
    """True only for a Chrome/Edge extension origin."""

    return bool(origin) and origin.strip().casefold().startswith("chrome-extension://")


def extension_id_from_origin(origin: str | None) -> str | None:
    """The extension id an Origin names, or None when it is not an extension origin.

    The Origin header is the only part of an extension request the browser
    itself fills in, so the id is derived from it and never taken from the
    request body.
    """

    if not is_extension_origin(origin):
        return None
    parts = urlsplit(str(origin).strip())
    identifier = (parts.netloc or "").strip()
    return identifier.casefold() or None


def is_trusted_extension_origin(origin: str | None) -> bool:
    return extension_id_from_origin(origin) == TRUSTED_EXTENSION_ID


@dataclass
class _ExpiringSecret:
    value: str
    expires_at: float
    attempts: int = 0
    consumed: bool = False


@dataclass
class Bridge:
    """In-memory credential authority for one running Mesa server."""

    bootstrap_token: str | None = None
    clock: Callable[[], float] = time.monotonic
    bootstrap_ttl: float = BOOTSTRAP_TTL_SECONDS
    handoff_ttl: float = SESSION_HANDOFF_TTL_SECONDS
    session_ttl: float = SESSION_TTL_SECONDS
    _bootstrap: _ExpiringSecret | None = field(default=None, repr=False)
    _sessions: dict[str, float] = field(default_factory=dict, repr=False)
    _handoffs: dict[str, float] = field(default_factory=dict, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def __post_init__(self) -> None:
        now = self.clock()
        self._bootstrap = _ExpiringSecret(self.bootstrap_token or new_token(), now + self.bootstrap_ttl)

    def register(self, store: Store, client_id: str, origin: str) -> str | None:
        """Register the shipped extension and return one fresh bearer token."""

        client_id = str(client_id or "").strip()
        origin = str(origin or "").strip()
        if not client_id or not is_trusted_extension_origin(origin):
            return None
        token = new_token()
        store.register_bridge_client(
            client_id,
            hash_token(token),
            origin=origin,
            extension_id=extension_id_from_origin(origin),
        )
        return token

    # ----------------------------------------------------------------- bootstrap

    @property
    def bootstrap_value(self) -> str:
        assert self._bootstrap is not None
        return self._bootstrap.value

    def consume_bootstrap(self, candidate: str) -> bool:
        """Consume the one-time bootstrap token; a second use always fails."""

        with self._lock:
            assert self._bootstrap is not None
            state = self._bootstrap
            if state.consumed or self.clock() > state.expires_at:
                return False
            if not hmac.compare_digest(state.value, str(candidate or "")):
                return False
            state.consumed = True
            return True

    def issue_session_handoff(self, session_id: str | None) -> str | None:
        """Issue a short-lived one-time URL token from an authenticated session."""

        with self._lock:
            if not session_id:
                return None
            expires_at = self._sessions.get(session_id)
            if expires_at is None or self.clock() > expires_at:
                self._sessions.pop(session_id, None)
                return None
            now = self.clock()
            self._handoffs = {
                token: expiry for token, expiry in self._handoffs.items() if expiry >= now
            }
            token = new_token()
            self._handoffs[token] = now + self.handoff_ttl
            return token

    def consume_session_handoff(self, candidate: str) -> bool:
        """Consume a session transfer token exactly once."""

        with self._lock:
            token = str(candidate or "")
            expires_at = self._handoffs.pop(token, None)
            return expires_at is not None and self.clock() <= expires_at

    # ------------------------------------------------------------------ sessions

    def open_session(self) -> str:
        with self._lock:
            session_id = new_token()
            self._sessions[session_id] = self.clock() + self.session_ttl
            return session_id

    def valid_session(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        with self._lock:
            expires_at = self._sessions.get(session_id)
            if expires_at is None:
                return False
            if self.clock() > expires_at:
                self._sessions.pop(session_id, None)
                return False
            return True

    # ----------------------------------------------------------- origin checking

    @staticmethod
    def is_same_origin(headers: Mapping[str, str], expected: set[str]) -> bool:
        """Accept only requests that originate from one of the Mesa origins."""

        fetch_site = str(headers.get("Sec-Fetch-Site") or "").strip().casefold()
        if fetch_site and fetch_site not in {"same-origin", "none"}:
            return False
        allowed = {value.casefold() for value in expected if value}
        origin = str(headers.get("Origin") or "").strip().casefold()
        if origin:
            return origin in allowed
        referer = str(headers.get("Referer") or "").strip()
        if referer:
            parts = urlsplit(referer)
            if not parts.scheme or not parts.netloc:
                return False
            return f"{parts.scheme}://{parts.netloc}".casefold() in allowed
        return False
