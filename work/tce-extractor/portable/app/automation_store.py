"""Durable, fail-closed event store for local automation runs.

The store deliberately has no browser or service dependencies.  Every public
operation opens a fresh SQLite connection, acquires an immediate transaction,
and returns a defensive projection of the durable state.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import uuid
from typing import Any, Callable


SCHEMA_VERSION = 1
DATABASE_RELATIVE_PATH = Path("automacao") / "execucoes.sqlite3"
ACTIVE_RUN_STATES = frozenset({"discovering", "running", "paused"})
RUN_STATES = frozenset(
    {"discovering", "running", "paused", "stopped", "completed"}
)
ITEM_STATES = frozenset(
    {
        "queued",
        "prepared",
        "filled",
        "send_intent",
        "confirmed",
        "pending",
        "failed",
        "unconfirmed",
    }
)
EVENT_TYPES = frozenset(
    {
        "queue_frozen",
        "item_prepared",
        "fields_verified",
        "send_intent",
        "send_confirmed",
        "item_pending",
        "item_failed",
        "send_unconfirmed",
        "run_paused",
        "run_resumed",
        "run_stopped",
        "run_completed",
    }
)
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class AutomationStoreError(RuntimeError):
    """Base error for unsafe or invalid automation-store operations."""


class RunNotFound(AutomationStoreError):
    """The requested run does not exist."""


class ActiveRunError(AutomationStoreError):
    """A root already has an active run."""


class EventConflict(AutomationStoreError):
    """An event ID was reused with a different payload or run."""


class LegacyEventReplayError(AutomationStoreError):
    """A legacy event has no durable result snapshot for safe replay."""


class InvalidTransition(AutomationStoreError):
    """An event cannot be applied to the current projection."""


class RevisionConflict(AutomationStoreError):
    """The caller attempted to write from a stale run revision."""

    def __init__(self, expected_revision: int, actual_revision: int) -> None:
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        super().__init__(
            f"revisão de automação conflitante: esperada {expected_revision}, "
            f"atual {actual_revision}"
        )


class EventValidationError(AutomationStoreError):
    """An event or run specification does not satisfy the contract."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EventValidationError("payload não é JSON serializável") from exc


def _decode_json(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AutomationStoreError("JSON persistido inválido") from exc


def _validate_run_id(value: object) -> str:
    if not isinstance(value, str) or not _RUN_ID_RE.fullmatch(value):
        raise EventValidationError("run_id inválido")
    return value


def _validate_event_id(value: object) -> str:
    if not isinstance(value, str) or not _EVENT_ID_RE.fullmatch(value):
        raise EventValidationError("event_id inválido")
    return value


def _validate_revision(value: object, name: str = "expected_revision") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EventValidationError(f"{name} deve ser inteiro não negativo")
    return value


def _identity_key(identity: dict[str, Any]) -> str:
    return _canonical_json(identity)


def _identity_reference(identity: dict[str, Any]) -> set[str]:
    values = {_identity_key(identity)}
    for key in ("item_id", "process_key", "id", "key", "act_id"):
        value = identity.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            values.add(str(value))
    return values


def _validate_identities(identities: object) -> list[dict[str, Any]]:
    if not isinstance(identities, list):
        raise EventValidationError("identities deve ser uma lista")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for identity in identities:
        if not isinstance(identity, dict) or not identity:
            raise EventValidationError("cada identidade deve ser um objeto não vazio")
        copied = deepcopy(identity)
        key = _identity_key(copied)
        if key in seen:
            raise EventValidationError("identidades duplicadas na fila")
        seen.add(key)
        result.append(copied)
    return result


def _event_type(event: dict[str, Any]) -> str:
    value = event.get("type", event.get("event_type"))
    if not isinstance(value, str) or value not in EVENT_TYPES:
        raise EventValidationError("tipo de evento não aceito")
    return value


def _event_parts(event: object) -> tuple[str, str, dict[str, Any], int]:
    if not isinstance(event, dict):
        raise EventValidationError("event deve ser um objeto")
    event_id = _validate_event_id(event.get("event_id"))
    event_type = _event_type(event)
    expected_revision = event.get("expected_revision")
    if expected_revision is None:
        raise EventValidationError("expected_revision é obrigatório")
    expected_revision = _validate_revision(expected_revision)

    raw_payload = event.get("payload", {})
    if not isinstance(raw_payload, dict):
        raise EventValidationError("payload do evento deve ser um objeto")
    payload = deepcopy(raw_payload)
    control_keys = {"event_id", "type", "event_type", "payload", "expected_revision"}
    payload.update(
        {
            key: deepcopy(value)
            for key, value in event.items()
            if key not in control_keys
        }
    )
    _canonical_json(payload)
    return event_id, event_type, payload, expected_revision


class AutomationStore:
    """Own the SQLite journal and projection for one workflow root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise AutomationStoreError(f"raiz de workflow inválida: {self.root}")
        self.database_path = self.root / DATABASE_RELATIVE_PATH
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._closed = False
        try:
            self._initialize_database()
            self._recover_open_runs()
        except Exception:
            self._closed = True
            raise

    def _connect(self) -> sqlite3.Connection:
        if self._closed:
            raise AutomationStoreError("AutomationStore já foi fechado")
        connection = sqlite3.connect(
            self.database_path,
            timeout=5.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize_database(self) -> None:
        connection = sqlite3.connect(
            self.database_path,
            timeout=5.0,
            isolation_level=None,
        )
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    root_key TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN (
                        'discovering', 'running', 'paused', 'stopped', 'completed'
                    )),
                    revision INTEGER NOT NULL CHECK (revision >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    paused_at TEXT,
                    paused_from_state TEXT,
                    stopped_at TEXT,
                    completed_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_run_per_root
                    ON runs(root_key)
                    WHERE state IN ('discovering', 'running', 'paused');
                CREATE TABLE IF NOT EXISTS items (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    identity_key TEXT NOT NULL,
                    identity_json TEXT NOT NULL,
                    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
                    state TEXT NOT NULL CHECK (state IN (
                        'queued', 'prepared', 'filled', 'send_intent',
                        'confirmed', 'pending', 'failed', 'unconfirmed'
                    )),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, identity_key),
                    UNIQUE (run_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL CHECK (seq >= 1),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (run_id, seq)
                );
                CREATE TABLE IF NOT EXISTS commands (
                    command_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    command_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    consumed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS confirmed_acts (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    identity_key TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE REFERENCES events(event_id),
                    payload_json TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, identity_key)
                );
                """
            )
            event_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(events)").fetchall()
            }
            if "result_json" not in event_columns:
                connection.execute("ALTER TABLE events ADD COLUMN result_json TEXT")
            run_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "paused_from_state" not in run_columns:
                connection.execute(
                    "ALTER TABLE runs ADD COLUMN paused_from_state TEXT"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _run_transaction(
        self, callback: Callable[[sqlite3.Connection], Any]
    ) -> Any:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                result = callback(connection)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            return result
        finally:
            connection.close()

    def _recover_open_runs(self) -> None:
        def recover(connection: sqlite3.Connection) -> None:
            rows = connection.execute(
                "SELECT run_id, state, revision FROM runs WHERE root_key = ? "
                "AND state IN ('discovering', 'running', 'paused') ORDER BY created_at",
                (str(self.root),),
            ).fetchall()
            for row in rows:
                run_id = str(row["run_id"])
                current_revision = int(row["revision"])
                if str(row["state"]) in {"discovering", "running"}:
                    self._append_event_transaction(
                        connection,
                        run_id,
                        f"recovery:{run_id}:{current_revision + 1}:paused",
                        "run_paused",
                        {"reason": "reopen_recovery"},
                        None,
                    )
                    current_revision += 1
                pending_items = connection.execute(
                    "SELECT identity_key, identity_json FROM items "
                    "WHERE run_id = ? AND state = 'send_intent' ORDER BY ordinal",
                    (run_id,),
                ).fetchall()
                for offset, item in enumerate(pending_items, start=1):
                    identity = _decode_json(str(item["identity_json"]))
                    self._append_event_transaction(
                        connection,
                        run_id,
                        f"recovery:{run_id}:{current_revision + offset}:unconfirmed",
                        "send_unconfirmed",
                        {"identity": identity, "reason": "reopen_recovery"},
                        None,
                        recovery=True,
                    )

        self._run_transaction(recover)

    def _get_run(self, connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM runs WHERE run_id = ? AND root_key = ?",
            (run_id, str(self.root)),
        ).fetchone()
        if row is None:
            raise RunNotFound(f"execução não encontrada: {run_id}")
        return row

    def _item_reference(self, payload: dict[str, Any]) -> object:
        for key in ("identity", "item", "item_id", "item_key", "identity_key", "process_key", "act_id"):
            if key in payload:
                return payload[key]
        return None

    def _find_item(
        self, connection: sqlite3.Connection, run_id: str, payload: dict[str, Any]
    ) -> sqlite3.Row:
        reference = self._item_reference(payload)
        if reference is None:
            raise InvalidTransition("evento de item sem identidade")
        rows = connection.execute(
            "SELECT * FROM items WHERE run_id = ? ORDER BY ordinal", (run_id,)
        ).fetchall()
        for row in rows:
            identity = _decode_json(str(row["identity_json"]))
            references = _identity_reference(identity)
            if isinstance(reference, dict):
                if _identity_key(reference) == str(row["identity_key"]):
                    return row
            elif isinstance(reference, (str, int)) and not isinstance(reference, bool):
                if str(reference) in references:
                    return row
        raise InvalidTransition("identidade não está na fila congelada")

    def _event_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = _decode_json(str(row["payload_json"]))
        return {
            "event_id": str(row["event_id"]),
            "run_id": str(row["run_id"]),
            "seq": int(row["seq"]),
            "type": str(row["event_type"]),
            "payload": payload,
            "created_at": str(row["created_at"]),
        }

    def _snapshot_transaction(
        self, connection: sqlite3.Connection, run_id: str
    ) -> dict[str, Any]:
        run = self._get_run(connection, run_id)
        item_rows = connection.execute(
            "SELECT * FROM items WHERE run_id = ? ORDER BY ordinal", (run_id,)
        ).fetchall()
        items = [
            {
                "identity": _decode_json(str(row["identity_json"])),
                "identity_key": str(row["identity_key"]),
                "ordinal": int(row["ordinal"]),
                "state": str(row["state"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
            for row in item_rows
        ]
        confirmed = connection.execute(
            "SELECT identity_key, payload_json, confirmed_at FROM confirmed_acts "
            "WHERE run_id = ? ORDER BY confirmed_at, identity_key",
            (run_id,),
        ).fetchall()
        last_confirmed = None
        if confirmed:
            last = confirmed[-1]
            last_confirmed = {
                "identity_key": str(last["identity_key"]),
                "payload": _decode_json(str(last["payload_json"])),
                "confirmed_at": str(last["confirmed_at"]),
            }
        interrupted = next(
            (
                item
                for item in items
                if item["state"] in {"unconfirmed", "send_intent", "pending"}
            ),
            None,
        )
        spec = _decode_json(str(run["spec_json"]))
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": str(run["run_id"]),
            "state": str(run["state"]),
            "revision": int(run["revision"]),
            "spec": spec,
            "created_at": str(run["created_at"]),
            "updated_at": str(run["updated_at"]),
            "started_at": run["started_at"],
            "paused_at": run["paused_at"],
            "stopped_at": run["stopped_at"],
            "completed_at": run["completed_at"],
            "items": items,
            "last_confirmed": last_confirmed,
            "interrupted_item": interrupted,
        }

    def _existing_event_result(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        existing_payload_json = str(row["payload_json"])
        if (
            str(row["event_type"]) != event_type
            or existing_payload_json != _canonical_json(payload)
        ):
            raise EventConflict(f"event_id já usado com payload diferente: {event_id}")
        if str(row["run_id"]) != run_id:
            raise EventConflict(f"event_id pertence a outra execução: {event_id}")
        result_json = row["result_json"]
        if result_json is not None:
            return _decode_json(str(result_json))
        raise LegacyEventReplayError(
            f"evento legado sem resultado persistido: {event_id}"
        )

    def _append_event_transaction(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
        expected_revision: int | None,
        recovery: bool = False,
    ) -> dict[str, Any]:
        existing = self._existing_event_result(
            connection, run_id, event_id, event_type, payload
        )
        if existing is not None:
            return existing
        run = self._get_run(connection, run_id)
        actual_revision = int(run["revision"])
        if expected_revision is not None and expected_revision != actual_revision:
            raise RevisionConflict(expected_revision, actual_revision)
        current_state = str(run["state"])
        if event_type == "queue_frozen":
            if current_state != "discovering":
                raise InvalidTransition(
                    f"queue_frozen inválido no estado {current_state}"
                )
            identities = _validate_identities(payload.get("identities"))
            existing_count = connection.execute(
                "SELECT COUNT(*) FROM items WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            if existing_count:
                raise InvalidTransition("fila já foi congelada")
        elif event_type in {"run_paused", "run_resumed", "run_stopped", "run_completed"}:
            allowed = {
                "run_paused": {"discovering", "running"},
                "run_resumed": {"paused"},
                "run_stopped": {"discovering", "running", "paused"},
                "run_completed": {"running"},
            }[event_type]
            if current_state not in allowed:
                raise InvalidTransition(
                    f"{event_type} inválido no estado {current_state}"
                )
            if event_type == "run_completed":
                active_items = connection.execute(
                    "SELECT COUNT(*) FROM items WHERE run_id = ? AND state IN "
                    "('queued', 'prepared', 'filled', 'send_intent')",
                    (run_id,),
                ).fetchone()[0]
                if active_items:
                    raise InvalidTransition("não é possível concluir itens não terminais")
        else:
            if current_state != "running" and not (
                recovery
                and current_state == "paused"
                and event_type == "send_unconfirmed"
            ):
                raise InvalidTransition(
                    f"evento de item inválido no estado da execução {current_state}"
                )
            item = self._find_item(connection, run_id, payload)
            item_state = str(item["state"])
            allowed_item_states = {
                "item_prepared": {"queued"},
                "fields_verified": {"prepared"},
                "send_intent": {"filled"},
                "send_confirmed": {"send_intent"},
                "item_pending": {"queued", "prepared", "filled", "send_intent", "unconfirmed"},
                "item_failed": {"queued", "prepared", "filled", "send_intent", "pending", "unconfirmed"},
                "send_unconfirmed": {"send_intent"},
            }[event_type]
            if item_state not in allowed_item_states:
                raise InvalidTransition(
                    f"{event_type} inválido para item no estado {item_state}"
                )

        seq = actual_revision + 1
        timestamp = _now()
        connection.execute(
            "INSERT INTO events(event_id, run_id, seq, event_type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, run_id, seq, event_type, _canonical_json(payload), timestamp),
        )

        if event_type == "queue_frozen":
            for ordinal, identity in enumerate(identities, start=1):
                connection.execute(
                    "INSERT INTO items(run_id, identity_key, identity_json, ordinal, state, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', ?, ?)",
                    (
                        run_id,
                        _identity_key(identity),
                        _canonical_json(identity),
                        ordinal,
                        timestamp,
                        timestamp,
                    ),
                )
            next_state = "running"
        elif event_type in {"run_paused", "run_resumed", "run_stopped", "run_completed"}:
            if event_type == "run_resumed":
                paused_from_state = run["paused_from_state"]
                next_state = (
                    str(paused_from_state)
                    if paused_from_state in {"discovering", "running"}
                    else "running"
                )
            else:
                next_state = {
                    "run_paused": "paused",
                    "run_stopped": "stopped",
                    "run_completed": "completed",
                }[event_type]
        else:
            item = self._find_item(connection, run_id, payload)
            next_item_state = {
                "item_prepared": "prepared",
                "fields_verified": "filled",
                "send_intent": "send_intent",
                "send_confirmed": "confirmed",
                "item_pending": "pending",
                "item_failed": "failed",
                "send_unconfirmed": "unconfirmed",
            }[event_type]
            connection.execute(
                "UPDATE items SET state = ?, updated_at = ? WHERE run_id = ? AND identity_key = ?",
                (next_item_state, timestamp, run_id, str(item["identity_key"])),
            )
            next_state = str(run["state"])
            if event_type == "send_confirmed":
                connection.execute(
                    "INSERT INTO confirmed_acts(run_id, identity_key, event_id, payload_json, confirmed_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        run_id,
                        str(item["identity_key"]),
                        event_id,
                        _canonical_json(payload),
                        timestamp,
                    ),
                )

        time_column = {
            "paused": "paused_at",
            "stopped": "stopped_at",
            "completed": "completed_at",
        }.get(next_state)
        update_columns = ["state = ?", "revision = ?", "updated_at = ?"]
        update_values: list[Any] = [next_state, seq, timestamp]
        if next_state == "running" and current_state == "discovering":
            update_columns.append("started_at = ?")
            update_values.append(timestamp)
        if event_type == "run_paused":
            update_columns.append("paused_from_state = ?")
            update_values.append(current_state)
        elif event_type in {"run_resumed", "run_stopped", "run_completed"}:
            update_columns.append("paused_from_state = NULL")
        if time_column:
            update_columns.append(f"{time_column} = ?")
            update_values.append(timestamp)
        update_values.extend([run_id, str(self.root)])
        connection.execute(
            f"UPDATE runs SET {', '.join(update_columns)} WHERE run_id = ? AND root_key = ?",
            tuple(update_values),
        )
        result = self._snapshot_transaction(connection, run_id)
        connection.execute(
            "UPDATE events SET result_json = ? WHERE event_id = ?",
            (_canonical_json(result), event_id),
        )
        return result

    def create_run(self, spec: dict) -> dict:
        if not isinstance(spec, dict):
            raise EventValidationError("spec deve ser um objeto")
        spec_copy = deepcopy(spec)
        raw_run_id = spec_copy.get("run_id")
        run_id = (
            _validate_run_id(raw_run_id)
            if raw_run_id is not None
            else _validate_run_id(f"run-{uuid.uuid4().hex}")
        )
        spec_json = _canonical_json(spec_copy)

        def create(connection: sqlite3.Connection) -> dict[str, Any]:
            active = connection.execute(
                "SELECT run_id FROM runs WHERE root_key = ? AND state IN "
                "('discovering', 'running', 'paused') LIMIT 1",
                (str(self.root),),
            ).fetchone()
            if active is not None:
                raise ActiveRunError(
                    f"já existe execução ativa: {active['run_id']}"
                )
            timestamp = _now()
            try:
                connection.execute(
                    "INSERT INTO runs(run_id, root_key, spec_json, state, revision, "
                    "created_at, updated_at) VALUES (?, ?, ?, 'discovering', 0, ?, ?)",
                    (run_id, str(self.root), spec_json, timestamp, timestamp),
                )
            except sqlite3.IntegrityError as exc:
                if "one_active_run" in str(exc) or "runs.root_key" in str(exc):
                    raise ActiveRunError("já existe execução ativa") from exc
                raise EventConflict(f"run_id já existe: {run_id}") from exc
            return self._snapshot_transaction(connection, run_id)

        return self._run_transaction(create)

    def freeze_queue(
        self,
        run_id: str,
        identities: list[dict],
        event_id: str,
        expected_revision: int,
    ) -> dict:
        run_id = _validate_run_id(run_id)
        event_id = _validate_event_id(event_id)
        expected_revision = _validate_revision(expected_revision)
        normalized_identities = _validate_identities(identities)
        return self._run_transaction(
            lambda connection: self._append_event_transaction(
                connection,
                run_id,
                event_id,
                "queue_frozen",
                {"identities": normalized_identities},
                expected_revision,
            )
        )

    def append_event(self, run_id: str, event: dict) -> dict:
        run_id = _validate_run_id(run_id)
        event_id, event_type, payload, expected_revision = _event_parts(event)
        return self._run_transaction(
            lambda connection: self._append_event_transaction(
                connection,
                run_id,
                event_id,
                event_type,
                payload,
                expected_revision,
            )
        )

    def snapshot(self, run_id: str) -> dict:
        run_id = _validate_run_id(run_id)
        return self._run_transaction(
            lambda connection: self._snapshot_transaction(connection, run_id)
        )

    def get_events(
        self, run_id: str, after: int = 0, through: int | None = None
    ) -> list[dict]:
        run_id = _validate_run_id(run_id)
        after = _validate_revision(after, "after")
        if through is not None:
            through = _validate_revision(through, "through")

        def read(connection: sqlite3.Connection) -> list[dict]:
            self._get_run(connection, run_id)
            if through is None:
                rows = connection.execute(
                    "SELECT * FROM events WHERE run_id = ? AND seq > ? ORDER BY seq",
                    (run_id, after),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM events WHERE run_id = ? AND seq > ? "
                    "AND seq <= ? ORDER BY seq",
                    (run_id, after, through),
                ).fetchall()
            return [self._event_from_row(row) for row in rows]

        return self._run_transaction(read)

    def close(self) -> None:
        self._closed = True

    def __enter__(self) -> "AutomationStore":
        if self._closed:
            raise AutomationStoreError("AutomationStore já foi fechado")
        return self

    def __exit__(self, _exc_type: object, _exc_value: object, _traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
