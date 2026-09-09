"""Ephemeral pairing and bearer-token authentication for the local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets
import threading
from urllib.parse import urlsplit


class BridgeAuthError(RuntimeError):
    """A pairing or token operation was rejected."""


def _is_extension_origin(origin: str) -> bool:
    if not isinstance(origin, str) or not origin or origin == "null":
        return False
    parsed = urlsplit(origin)
    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "chrome-extension"
        and bool(hostname)
        and parsed.netloc == hostname
        and port is None
        and parsed.username is None
        and parsed.password is None
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


@dataclass
class _PendingPairing:
    code: str
    expires_at: datetime
    attempts: int = 0


class BridgeAuth:
    """Keep pairing codes and tokens in memory; restart invalidates both."""

    def __init__(self, *, clock=None, ttl: timedelta = timedelta(seconds=120), max_attempts: int = 5):
        if ttl.total_seconds() <= 0:
            raise ValueError("ttl deve ser positivo")
        if max_attempts <= 0:
            raise ValueError("max_attempts deve ser positivo")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._ttl = ttl
        self._max_attempts = max_attempts
        self._lock = threading.RLock()
        self._pending: _PendingPairing | None = None
        self._tokens: dict[str, str] = {}

    def issue_pairing_code(self) -> str:
        with self._lock:
            code = f"{secrets.randbelow(100_000_000):08d}"
            self._pending = _PendingPairing(code, self._clock() + self._ttl)
            return code

    def redeem(self, code: str, origin: str) -> str:
        with self._lock:
            pending = self._pending
            if pending is None:
                raise BridgeAuthError("código de pareamento ausente")
            if self._clock() >= pending.expires_at:
                self._pending = None
                raise BridgeAuthError("código de pareamento expirado")

            if pending.attempts >= self._max_attempts:
                self._pending = None
                raise BridgeAuthError("limite de tentativas de pareamento excedido")
            pending.attempts += 1
            if pending.code != code:
                if pending.attempts >= self._max_attempts:
                    self._pending = None
                raise BridgeAuthError("código de pareamento inválido")
            if not _is_extension_origin(origin):
                if pending.attempts >= self._max_attempts:
                    self._pending = None
                raise BridgeAuthError("origem de extensão inválida")

            token = secrets.token_urlsafe(32)
            self._tokens[token] = origin
            self._pending = None
            return token

    def validate(self, token: str, origin: str | None = None, *, allow_missing_origin: bool = False) -> bool:
        with self._lock:
            expected_origin = self._tokens.get(token)
            if expected_origin is None:
                return False
            if origin is None:
                return allow_missing_origin
            return origin == expected_origin

    @staticmethod
    def is_extension_origin(origin: str | None) -> bool:
        return _is_extension_origin(origin or "")
