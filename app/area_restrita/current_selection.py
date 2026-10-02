"""The transient "current portal form" the Mesa follows (Portal Atual).

The extension observes the form the operator opened and publishes it; the Mesa
reads a minimal public state and may ask for the best-effort fill of that exact
form. Everything here lives in the server process's memory only: the form
snapshot is never written to SQLite, never emitted as a reliability event, never
logged, never returned by the public state, and it dies with the TTL.
"""

from __future__ import annotations

import copy
import contextlib
import re
import secrets
import threading
import time
from collections.abc import Callable, Iterator, Mapping
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
FILL_RESERVED = "FILL_RESERVED"

#: A screen is a short structural token, never a route: nothing here may hold
#: a URL, a query string or the portal's own text.
_SCREEN = re.compile(r"[a-z][a-z0-9_]{0,31}")
_OBSERVATION_ID = re.compile(r"[A-Za-z0-9_-]{43}")
_PUBLISHER_ID = re.compile(r"[a-f0-9]{32}")
_MAX_PUBLISHER_SEQUENCE = 2**53 - 1

#: Refusal codes the fill entry point may raise. Both are AR-1 attempt failure
#: codes, so a stale click stays a recorded failure instead of a server error.
_FILL_REFUSAL_BY_STATE: dict[str, str] = {
    AMBIGUOUS: "FORM_AMBIGUOUS",
    FILL_RESERVED: "STALE_SELECTION",
}
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
        self._interested_normalized: str | None = None
        self._portal_act_id: str | None = None
        self._generation: int | None = None
        self._screen: str | None = None
        self._observed_at: str | None = None
        self._expires_at: float | None = None
        self._snapshot: dict[str, Any] | None = None
        self._observation_id: str | None = None
        self._publisher_id: str | None = None
        self._publisher_sequence: int | None = None
        # Survives expiry: an expired MATCHED was still offered to the operator.
        self._offered = False

    # ------------------------------------------------------------ entry points

    def observe(
        self,
        form_snapshot: Mapping[str, Any],
        *,
        publisher_id: str,
        sequence: int,
    ) -> dict[str, Any]:
        """Resolve one observed form exactly and publish the public state.

        Zero matches is NOT_FOUND and several matches is AMBIGUOUS; neither
        stores a fillable snapshot, so neither can ever be filled. The process
        itself is only read: an observation never changes a status.
        """

        publisher_id, sequence = self._validate_publisher(publisher_id, sequence)
        observation = self._validate(form_snapshot)
        with self._lock:
            self._accept_publisher_locked(publisher_id, sequence)
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
                    interested_normalized=observation["interested"],
                    portal_act_id=observation["portal_act_id"],
                    generation=observation["generation"],
                    screen=observation["screen"],
                    publisher_id=publisher_id,
                    sequence=sequence,
                )
            if process is None:
                return self._publish_locked(
                    NOT_FOUND,
                    code="PROCESS_NOT_FOUND",
                    process_key=observation["process_key"],
                    interested_normalized=observation["interested"],
                    portal_act_id=observation["portal_act_id"],
                    generation=observation["generation"],
                    screen=observation["screen"],
                    publisher_id=publisher_id,
                    sequence=sequence,
                )
            return self._publish_locked(
                MATCHED,
                process_id=int(process["id"]),
                process_key=observation["process_key"],
                interested_normalized=observation["interested"],
                portal_act_id=observation["portal_act_id"],
                generation=observation["generation"],
                screen=observation["screen"],
                # The private copy exists only to serve the fill of this exact
                # form, and only while the observation is still fresh.
                snapshot=copy.deepcopy(dict(form_snapshot)),
                publisher_id=publisher_id,
                sequence=sequence,
            )

    def clear(
        self,
        code: str = "FORM_NOT_AVAILABLE",
        *,
        publisher_id: str,
        sequence: int,
    ) -> dict[str, Any]:
        """Publish that no single fillable form is observed any more."""

        publisher_id, sequence = self._validate_publisher(publisher_id, sequence)
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
            self._accept_publisher_locked(publisher_id, sequence)
            return self._publish_locked(
                state,
                code=normalized,
                publisher_id=publisher_id,
                sequence=sequence,
            )

    def public_state(self) -> dict[str, Any]:
        """The minimum the Mesa may read: never the snapshot, never a name."""

        with self._lock:
            self._sweep_locked()
            return self._public_state_locked()

    def require_fill_snapshot(self, expected_observation_id: str | None) -> dict[str, Any]:
        """The exact snapshot to fill, or a fail-closed refusal.

        The returned copy is the caller's own, so it can never reach back into
        the stored observation, and an expired or non-MATCHED selection refuses
        before any write is even attempted.
        """

        with self.fill_window(expected_observation_id) as snapshot:
            return snapshot

    @contextlib.contextmanager
    def fill_window(self, expected_observation_id: str | None) -> Iterator[dict[str, Any]]:
        """Atomically compare and consume one exact observation for a fill.

        The opaque id binds the rendered button to the process, identity,
        generation, observation time and private snapshot in memory. The lock
        remains held through request creation; a successful reservation consumes
        the id so a replay cannot create another fill.
        """

        with self._lock:
            self._sweep_locked()
            if self._state != MATCHED or self._snapshot is None:
                raise PortalSelectionError(
                    _FILL_REFUSAL_BY_STATE.get(self._state, _FILL_REFUSAL_DEFAULT),
                    "nenhuma seleção atual pode ser preenchida",
                    offered=self._offered,
                )
            if (
                not isinstance(expected_observation_id, str)
                or not _OBSERVATION_ID.fullmatch(expected_observation_id)
            ):
                raise PortalSelectionError(
                    "INVALID_OBSERVATION_ID",
                    "identificador da observação ausente ou inválido",
                    offered=self._offered,
                )
            if expected_observation_id != self._observation_id:
                raise PortalSelectionError(
                    "STALE_SELECTION",
                    "a observação exibida não é mais a observação atual",
                    offered=self._offered,
                )
            try:
                observation = self._validate(self._snapshot)
                process = self._store.resolve_process_identity(
                    observation["process_key"],
                    observation["interested"],
                    observation["portal_act_id"],
                )
            except (PortalSelectionError, StoreError):
                observation = None
                process = None
            if (
                process is None
                or observation is None
                or int(process["id"]) != self._process_id
                or observation["process_key"] != self._process_key
                or observation["interested"] != self._interested_normalized
                or observation["portal_act_id"] != self._portal_act_id
                or observation["generation"] != self._generation
                or observation["screen"] != self._screen
            ):
                raise PortalSelectionError(
                    "STALE_SELECTION",
                    "identidade ou generation da observação mudou",
                    offered=self._offered,
                )
            snapshot = copy.deepcopy(self._snapshot)
            yield snapshot
            self._state = FILL_RESERVED
            self._code = "FILL_ALREADY_REQUESTED"
            self._process_id = None
            self._process_key = None
            self._interested_normalized = None
            self._portal_act_id = None
            self._generation = None
            self._screen = None
            self._snapshot = None
            self._observation_id = None
            self._expires_at = None
            # The exact observation was consumed under this lock; release its
            # publisher lease with the snapshot so the next observation can
            # establish a fresh owner.
            self._publisher_id = None
            self._publisher_sequence = None
            self._observed_at = self._utcnow().isoformat()

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
        interested_normalized: str | None = None,
        portal_act_id: str | None = None,
        generation: int | None = None,
        screen: str | None = None,
        snapshot: dict[str, Any] | None = None,
        publisher_id: str,
        sequence: int,
    ) -> dict[str, Any]:
        self._state = state
        self._code = code
        self._offered = state == MATCHED
        self._process_id = process_id
        self._process_key = process_key
        self._interested_normalized = interested_normalized
        self._portal_act_id = portal_act_id
        self._generation = generation
        self._screen = screen
        self._snapshot = snapshot
        self._publisher_id = publisher_id
        self._publisher_sequence = sequence
        self._observed_at = self._utcnow().isoformat()
        self._expires_at = self._clock() + self._ttl
        self._observation_id = secrets.token_urlsafe(32) if state == MATCHED else None
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
                "observation_id": self._observation_id,
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
        self._interested_normalized = None
        self._portal_act_id = None
        self._generation = None
        self._screen = None
        self._observed_at = None
        self._expires_at = None
        self._snapshot = None
        self._observation_id = None
        self._publisher_id = None
        self._publisher_sequence = None

    @staticmethod
    def _validate_publisher(publisher_id: Any, sequence: Any) -> tuple[str, int]:
        if not isinstance(publisher_id, str) or not _PUBLISHER_ID.fullmatch(publisher_id):
            raise PortalSelectionError("INVALID_PUBLISHER", "publisher_id ausente ou inválido")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 1
            or sequence > _MAX_PUBLISHER_SEQUENCE
        ):
            raise PortalSelectionError("INVALID_SEQUENCE", "sequence ausente ou inválida")
        return publisher_id, sequence

    def _accept_publisher_locked(self, publisher_id: str, sequence: int) -> None:
        self._sweep_locked()
        if self._publisher_id is None:
            self._publisher_id = publisher_id
            self._publisher_sequence = sequence
            return
        if publisher_id != self._publisher_id:
            raise PortalSelectionError(
                "PUBLISHER_OWNED",
                "a seleção atual ainda pertence a outro publisher ativo",
                offered=self._offered,
            )
        if self._publisher_sequence is not None and sequence <= self._publisher_sequence:
            raise PortalSelectionError(
                "STALE_PUBLISHER",
                "sequence do publisher não avançou",
                offered=self._offered,
            )
        self._publisher_sequence = sequence

