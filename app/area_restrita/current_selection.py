"""The transient "current portal form" the Mesa follows (Portal Atual).

The extension observes the form the operator opened and publishes it; the Mesa
reads a minimal public state and may ask for the best-effort fill of that exact
form. Everything here lives in the server process's memory only: the form
snapshot is never written to SQLite, never emitted as a reliability event, never
logged, never returned by the public state, and it dies with the TTL.
"""

from __future__ import annotations

import copy
import re
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from ..core.identity import normalize_interested
from ..core.store import Store, StoreError

#: How long an observation stays usable without a valid renewal.
PORTAL_SELECTION_TTL_SECONDS = 10.0

#: The public states. Only MATCHED ever carries a ``process_id``.
MATCHED = "MATCHED"
NOT_FOUND = "NOT_FOUND"
AMBIGUOUS = "AMBIGUOUS"
INVALID = "INVALID"
NO_ACTIVE_FORM = "NO_ACTIVE_FORM"

#: A screen is a short structural token, never a route: nothing here may hold
#: a URL, a query string or the portal's own text.
_SCREEN = re.compile(r"[a-z][a-z0-9_]{0,31}")

#: Refusal codes the fill entry point may raise. Both are AR-1 attempt failure
#: codes, so a stale click stays a recorded failure instead of a server error.
_FILL_REFUSAL_BY_STATE: dict[str, str] = {AMBIGUOUS: "FORM_AMBIGUOUS"}
_FILL_REFUSAL_DEFAULT = "FORM_NOT_AVAILABLE"

#: Short codes a cleared observation may carry as its diagnostic.
_CLEAR_CODES: frozenset[str] = frozenset(
    {
        "FORM_NOT_AVAILABLE",
        "FORM_AMBIGUOUS",
        "PORTAL_TAB_NOT_ACTIVE",
        "INVALID",
    }
)


class PortalSelectionError(RuntimeError):
    """A current-selection observation could not be used as asked."""

    def __init__(self, code: str, detail: str | None = None, *, offered: bool = False) -> None:
        self.code = str(code or "").strip().upper() or "INVALID"
        #: True when the Mesa could actually have rendered the fill action for
        #: the refused selection. A click on a button nobody saw is not a trial.
        self.offered = bool(offered)
        super().__init__(detail or self.code)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PortalSelectionTracker:
    """The last portal form observed, resolved exactly and held in memory."""

    def __init__(
        self,
        store: Store,
        *,
        ttl_seconds: float = PORTAL_SELECTION_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._store = store
        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._utcnow = utcnow
        # The Mesa and the extension reach this from different HTTP threads.
        self._lock = threading.RLock()
        self._state = NO_ACTIVE_FORM
        self._code: str | None = None
        self._process_id: int | None = None
        self._process_key: str | None = None
        self._generation: int | None = None
        self._screen: str | None = None
        self._observed_at: str | None = None
        self._expires_at: float | None = None
        self._snapshot: dict[str, Any] | None = None
        # Survives expiry: an expired MATCHED was still offered to the operator.
        self._offered = False

    # ------------------------------------------------------------ entry points

    def observe(self, form_snapshot: Mapping[str, Any]) -> dict[str, Any]:
        """Resolve one observed form exactly and publish the public state.

        Zero matches is NOT_FOUND and several matches is AMBIGUOUS; neither
        stores a fillable snapshot, so neither can ever be filled. The process
        itself is only read: an observation never changes a status.
        """

        observation = self._validate(form_snapshot)
        with self._lock:
            try:
                process = self._store.resolve_process_identity(
                    observation["process_key"],
                    observation["interested"],
                    observation["portal_act_id"],
                )
            except StoreError:
                return self._publish_locked(
                    AMBIGUOUS,
                    code="IDENTITY_AMBIGUOUS",
                    process_key=observation["process_key"],
                    generation=observation["generation"],
                    screen=observation["screen"],
                )
            if process is None:
                return self._publish_locked(
                    NOT_FOUND,
                    code="PROCESS_NOT_FOUND",
                    process_key=observation["process_key"],
                    generation=observation["generation"],
                    screen=observation["screen"],
                )
            return self._publish_locked(
                MATCHED,
                process_id=int(process["id"]),
                process_key=observation["process_key"],
                generation=observation["generation"],
                screen=observation["screen"],
                # The private copy exists only to serve the fill of this exact
                # form, and only while the observation is still fresh.
                snapshot=copy.deepcopy(dict(form_snapshot)),
            )

    def clear(self, code: str = "FORM_NOT_AVAILABLE") -> dict[str, Any]:
        """Publish that no single fillable form is observed any more."""

        normalized = str(code or "").strip().upper() or "FORM_NOT_AVAILABLE"
        if normalized not in _CLEAR_CODES:
            normalized = "FORM_NOT_AVAILABLE"
        if normalized == "INVALID":
            state = INVALID
        elif normalized == "FORM_AMBIGUOUS":
            state = AMBIGUOUS
        else:
            state = NO_ACTIVE_FORM
        with self._lock:
            return self._publish_locked(state, code=normalized)

    def public_state(self) -> dict[str, Any]:
        """The minimum the Mesa may read: never the snapshot, never a name."""

        with self._lock:
            self._sweep_locked()
            return self._public_state_locked()

    def require_fill_snapshot(self) -> dict[str, Any]:
        """The exact snapshot to fill, or a fail-closed refusal.

        The returned copy is the caller's own, so it can never reach back into
        the stored observation, and an expired or non-MATCHED selection refuses
        before any write is even attempted.
        """

        with self._lock:
            self._sweep_locked()
            if self._state != MATCHED or self._snapshot is None:
                raise PortalSelectionError(
                    _FILL_REFUSAL_BY_STATE.get(self._state, _FILL_REFUSAL_DEFAULT),
                    "nenhuma seleção atual pode ser preenchida",
                    offered=self._offered,
                )
            return copy.deepcopy(self._snapshot)

    # ----------------------------------------------------------------- internals

    @staticmethod
    def _validate(form_snapshot: Mapping[str, Any]) -> dict[str, Any]:
        """Structurally validate one observation, or refuse it as INVALID."""

        if not isinstance(form_snapshot, Mapping):
            raise PortalSelectionError("INVALID", "a observação não é um objeto")
        identity = form_snapshot.get("identity")
        if not isinstance(identity, Mapping):
            raise PortalSelectionError("INVALID", "a observação não trouxe identidade")
        process_key = str(
            identity.get("processKey") or identity.get("process_key") or ""
        ).strip()
        interested = normalize_interested(
            identity.get("interestedNormalized")
            or identity.get("interested_normalized")
            or ""
        )
        if not process_key or not interested:
            raise PortalSelectionError("INVALID", "identidade incompleta na observação")
        generation = form_snapshot.get("generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise PortalSelectionError("INVALID", "generation ausente ou inválida")
        raw_screen = form_snapshot.get("screen")
        screen = "form" if raw_screen is None else str(raw_screen).strip()
        if not _SCREEN.fullmatch(screen):
            raise PortalSelectionError("INVALID", "screen inválido na observação")
        return {
            "process_key": process_key,
            "interested": interested,
            "portal_act_id": identity.get("portalActId")
            or identity.get("portal_act_id"),
            "generation": generation,
            "screen": screen,
        }

    def _publish_locked(
        self,
        state: str,
        *,
        code: str | None = None,
        process_id: int | None = None,
        process_key: str | None = None,
        generation: int | None = None,
        screen: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._state = state
        self._code = code
        self._offered = state == MATCHED
        self._process_id = process_id
        self._process_key = process_key
        self._generation = generation
        self._screen = screen
        self._snapshot = snapshot
        self._observed_at = self._utcnow().isoformat()
        self._expires_at = self._clock() + self._ttl
        return self._public_state_locked()

    def _public_state_locked(self) -> dict[str, Any]:
        if self._state == MATCHED:
            return {
                "state": MATCHED,
                "process_id": self._process_id,
                "process_key": self._process_key,
                "generation": self._generation,
                "screen": self._screen,
                "observed_at": self._observed_at,
            }
        payload: dict[str, Any] = {"state": self._state}
        if self._code:
            payload["code"] = self._code
        if self._observed_at:
            payload["observed_at"] = self._observed_at
        return payload

    def _sweep_locked(self) -> None:
        if self._expires_at is not None and self._clock() >= self._expires_at:
            self._reset_locked()

    def _reset_locked(self) -> None:
        self._state = NO_ACTIVE_FORM
        self._code = None
        self._process_id = None
        self._process_key = None
        self._generation = None
        self._screen = None
        self._observed_at = None
        self._expires_at = None
        self._snapshot = None

