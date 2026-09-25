"""SQLite source of truth for the Mesa.

The store owns persistence and durable workflow state. It never touches a
browser, a PDF or a filesystem path outside the database it was opened on;
adapters translate external observations into the records defined here.

Every migration runs in its own transaction and ``metadata.schema_version`` is
bumped inside that same transaction, so a half-applied schema is never visible.
"""

from __future__ import annotations

import hmac
import json
import secrets
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import (
    AREA_CLASSIFICATION_EVENT,
    AREA_CLASSIFICATION_TARGET,
    DocumentRecord,
    FieldRecord,
    ProcessRecord,
    status_rank,
)

SCHEMA_VERSION = 7

#: How long one claimed command may stay unanswered before another poller may
#: take it over. The MV3 worker can be suspended mid-command, so a claim is a
#: lease, never ownership until the end of time.
COMMAND_LEASE_SECONDS = 120.0

#: How many times a command may be re-claimed after an expired lease before it
#: is given up as FAILED. A command that keeps dying is a defect, not a queue.
COMMAND_MAX_ATTEMPTS = 3


class StoreError(RuntimeError):
    """Raised when the database cannot satisfy a Mesa invariant."""


def utc_now() -> str:
    """Return the current UTC time as a stable, sortable ISO-8601 string."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_after(seconds: float) -> str:
    """Return the current UTC time shifted forward, in the same sortable format."""

    shifted = datetime.now(timezone.utc) + timedelta(seconds=float(seconds))
    return shifted.replace(microsecond=0).isoformat().replace("+00:00", "Z")


SCHEMA_V1: tuple[str, ...] = (
    """
    CREATE TABLE processes (
      id INTEGER PRIMARY KEY,
      process_key TEXT NOT NULL,
      interested TEXT NOT NULL,
      interested_normalized TEXT NOT NULL,
      source_scope TEXT,
      marker TEXT,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(process_key, interested_normalized)
    )
    """,
    """
    CREATE TABLE documents (
      id INTEGER PRIMARY KEY,
      process_id INTEGER NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
      source_id TEXT NOT NULL,
      event TEXT,
      title TEXT NOT NULL,
      relative_path TEXT NOT NULL,
      sha256 TEXT NOT NULL,
      page_count INTEGER NOT NULL,
      classification TEXT,
      storage_state TEXT NOT NULL,
      UNIQUE(process_id, source_id)
    )
    """,
    """
    CREATE TABLE fields (
      id INTEGER PRIMARY KEY,
      process_id INTEGER NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
      field_name TEXT NOT NULL,
      value TEXT,
      status TEXT NOT NULL,
      confidence REAL,
      document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
      page INTEGER,
      evidence TEXT
    )
    """,
    """
    CREATE TABLE workflow_events (
      id INTEGER PRIMARY KEY,
      process_id INTEGER NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
      event_type TEXT NOT NULL,
      payload TEXT NOT NULL,
      created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE jobs (
      id INTEGER PRIMARY KEY,
      job_type TEXT NOT NULL,
      status TEXT NOT NULL,
      total INTEGER NOT NULL DEFAULT 0,
      completed INTEGER NOT NULL DEFAULT 0,
      failed INTEGER NOT NULL DEFAULT 0,
      started_at TEXT,
      finished_at TEXT
    )
    """,
    "CREATE INDEX idx_processes_status ON processes(status)",
    "CREATE INDEX idx_documents_process ON documents(process_id)",
    "CREATE INDEX idx_documents_sha256 ON documents(sha256)",
    "CREATE INDEX idx_fields_process ON fields(process_id, field_name)",
    "CREATE INDEX idx_workflow_events_process ON workflow_events(process_id)",
)

SCHEMA_V2: tuple[str, ...] = (
    """
    CREATE TABLE area_scans (
      id INTEGER PRIMARY KEY,
      source_scope TEXT NOT NULL,
      marker_label TEXT,
      marker_value TEXT,
      observed_at TEXT NOT NULL,
      origin TEXT NOT NULL,
      raw_sha256 TEXT,
      total INTEGER NOT NULL DEFAULT 0,
      pending INTEGER NOT NULL DEFAULT 0,
      completed INTEGER NOT NULL DEFAULT 0,
      ambiguous INTEGER NOT NULL DEFAULT 0,
      blocked INTEGER NOT NULL DEFAULT 0,
      not_found INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE area_scan_items (
      id INTEGER PRIMARY KEY,
      scan_id INTEGER NOT NULL REFERENCES area_scans(id) ON DELETE CASCADE,
      process_id INTEGER REFERENCES processes(id) ON DELETE SET NULL,
      process_key TEXT NOT NULL,
      interested TEXT NOT NULL,
      interested_normalized TEXT NOT NULL,
      portal_act_id TEXT,
      classification TEXT NOT NULL,
      needs_complement INTEGER NOT NULL DEFAULT 0,
      action_observed TEXT,
      UNIQUE(scan_id, process_key, interested_normalized)
    )
    """,
    """
    CREATE TABLE bridge_clients (
      id INTEGER PRIMARY KEY,
      client_id TEXT NOT NULL UNIQUE,
      token_hash TEXT NOT NULL,
      origin TEXT,
      extension_id TEXT,
      created_at TEXT NOT NULL,
      last_seen_at TEXT
    )
    """,
    """
    CREATE TABLE extension_commands (
      id INTEGER PRIMARY KEY,
      command_type TEXT NOT NULL,
      payload TEXT NOT NULL,
      state TEXT NOT NULL,
      client_id TEXT,
      result TEXT,
      error TEXT,
      created_at TEXT NOT NULL,
      claimed_at TEXT,
      finished_at TEXT
    )
    """,
    "ALTER TABLE processes ADD COLUMN portal_act_id TEXT",
    "ALTER TABLE processes ADD COLUMN area_classification TEXT",
    "ALTER TABLE processes ADD COLUMN needs_complement INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE processes ADD COLUMN last_area_scan_id INTEGER",
    "CREATE INDEX idx_area_scans_observed ON area_scans(observed_at)",
    "CREATE INDEX idx_area_scan_items_scan ON area_scan_items(scan_id)",
    "CREATE INDEX idx_extension_commands_state ON extension_commands(state, id)",
)

SCHEMA_V3: tuple[str, ...] = (
    """
    CREATE TABLE job_items (
      id INTEGER PRIMARY KEY,
      job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
      process_id INTEGER NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
      state TEXT NOT NULL,
      error TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(job_id, process_id)
    )
    """,
    "ALTER TABLE jobs ADD COLUMN error TEXT",
    "ALTER TABLE processes ADD COLUMN acquisition_state TEXT NOT NULL DEFAULT 'NOT_DOWNLOADED'",
    "CREATE INDEX idx_job_items_job ON job_items(job_id, state)",
    "CREATE INDEX idx_processes_acquisition ON processes(acquisition_state)",
    # A process whose documents are already in the acervo is not missing bytes:
    # the migration states that fact instead of leaving it to a later rescan.
    "UPDATE processes SET acquisition_state = 'DOWNLOADED' "
    "WHERE EXISTS (SELECT 1 FROM documents WHERE documents.process_id = processes.id)",
)

SCHEMA_V4: tuple[str, ...] = (
    """
    CREATE TABLE portal_fill_requests (
      id INTEGER PRIMARY KEY,
      process_id INTEGER NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
      state TEXT NOT NULL,
      mode TEXT NOT NULL,
      current_command_id INTEGER,
      form_snapshot TEXT,
      error TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """,
    "ALTER TABLE extension_commands ADD COLUMN fill_request_id INTEGER",
    "CREATE INDEX idx_fill_requests_process ON portal_fill_requests(process_id, state)",
    "CREATE INDEX idx_commands_fill_request ON extension_commands(fill_request_id)",
)

SCHEMA_V5: tuple[str, ...] = (
    """
    CREATE TABLE archive_blobs (
      sha256 TEXT PRIMARY KEY,
      size_bytes INTEGER NOT NULL DEFAULT 0,
      local_relative_path TEXT,
      external_path TEXT,
      local_present INTEGER NOT NULL DEFAULT 0,
      external_present INTEGER NOT NULL DEFAULT 0,
      verified_at TEXT
    )
    """,
    # Presence is not assumed from the documents table: the reconciler verifies
    # the canonical path and only then flips the flag.
    "INSERT INTO archive_blobs (sha256, local_relative_path) "
    "SELECT DISTINCT sha256, 'archive/blobs/' || substr(sha256, 1, 2) || '/' || sha256 || '.pdf' "
    "FROM documents WHERE sha256 NOT IN (SELECT sha256 FROM archive_blobs)",
    "CREATE INDEX idx_archive_blobs_presence ON archive_blobs(local_present, external_present)",
)

SCHEMA_V6: tuple[str, ...] = (
    # A claim is a lease: without a deadline a command whose worker died stays
    # CLAIMED forever and the Mesa waits on a result that will never come.
    "ALTER TABLE extension_commands ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE extension_commands ADD COLUMN claim_token TEXT",
    "ALTER TABLE extension_commands ADD COLUMN lease_expires_at TEXT",
    "CREATE INDEX idx_extension_commands_lease ON extension_commands(state, lease_expires_at)",
)

SCHEMA_V7: tuple[str, ...] = (
    # One command produces at most one scan: the unique index is what turns a
    # retry into the same observation instead of a second one.
    "ALTER TABLE area_scans ADD COLUMN source_command_id INTEGER",
    "CREATE UNIQUE INDEX idx_area_scans_command ON area_scans(source_command_id) "
    "WHERE source_command_id IS NOT NULL",
)

#: Sentinel that distinguishes "leave this column alone" from "set it to NULL".
_UNSET: Any = object()


class Store:
    """Owns one SQLite database and every workflow decision persisted in it."""

    def __init__(self, connection: sqlite3.Connection, path: Path) -> None:
        self._connection = connection
        self._lock = threading.RLock()
        self.path = path

    # ------------------------------------------------------------------ setup

    @classmethod
    def open(cls, path: str | Path) -> "Store":
        """Open (creating if needed) the Mesa database at ``path``."""

        database = Path(path)
        database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 15000")
        store = cls(connection, database)
        store._migrate()
        return store

    @classmethod
    def open_read_only(cls, path: str | Path) -> "Store":
        """Open an existing database without ever migrating it.

        Inspection tools must not change what they inspect: a schema this build
        does not understand is reported, never upgraded in place.
        """

        database = Path(path)
        if not database.is_file():
            raise StoreError(f"database not found: {database}")
        connection = sqlite3.connect(
            f"file:{database.as_posix()}?mode=ro", uri=True, check_same_thread=False
        )
        connection.row_factory = sqlite3.Row
        store = cls(connection, database)
        version = store._read_schema_version()
        if version != SCHEMA_VERSION:
            connection.close()
            raise StoreError(
                f"database schema_version {version} is not the expected {SCHEMA_VERSION}; "
                "refusing to inspect it instead of migrating it"
            )
        return store

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a write unit atomically; never nest two of these."""

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")

    # -------------------------------------------------------------- migration

    def _migrate(self) -> None:
        with self._lock:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            version = self._read_schema_version()
            if version > SCHEMA_VERSION:
                raise StoreError(
                    f"database schema_version {version} is newer than this application supports "
                    f"({SCHEMA_VERSION}); refusing to open it"
                )
            while version < SCHEMA_VERSION:
                target = version + 1
                with self._transaction() as connection:
                    self._apply_migration(connection, target)
                    connection.execute(
                        "INSERT INTO metadata (key, value) VALUES ('schema_version', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (str(target),),
                    )
                version = target

    @staticmethod
    def _apply_migration(connection: sqlite3.Connection, target: int) -> None:
        if target == 1:
            for statement in SCHEMA_V1:
                connection.execute(statement)
            return
        if target == 2:
            for statement in SCHEMA_V2:
                connection.execute(statement)
            return
        if target == 3:
            for statement in SCHEMA_V3:
                connection.execute(statement)
            return
        if target == 4:
            for statement in SCHEMA_V4:
                connection.execute(statement)
            return
        if target == 5:
            for statement in SCHEMA_V5:
                connection.execute(statement)
            return
        if target == 6:
            for statement in SCHEMA_V6:
                connection.execute(statement)
            return
        if target == 7:
            for statement in SCHEMA_V7:
                connection.execute(statement)
            return
        raise StoreError(f"no migration is defined for schema_version {target}")

    def _read_schema_version(self) -> int:
        row = self._connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row is not None else 0

    @property
    def schema_version(self) -> int:
        with self._lock:
            return self._read_schema_version()

    # --------------------------------------------------------------- processes

    def upsert_process(self, record: ProcessRecord) -> int:
        """Insert or update one process, returning its stable row id.

        The natural key is ``(process_key, interested_normalized)``. A blank
        scope or marker never erases a value the portal told us earlier.
        """

        with self._transaction() as connection:
            return self._upsert_process_row(connection, record)

    @staticmethod
    def _upsert_process_row(connection: sqlite3.Connection, record: ProcessRecord) -> int:
        """Upsert one process inside an open transaction."""

        now = utc_now()
        connection.execute(
            """
            INSERT INTO processes (
                process_key, interested, interested_normalized,
                source_scope, marker, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(process_key, interested_normalized) DO UPDATE SET
                interested = excluded.interested,
                source_scope = COALESCE(excluded.source_scope, processes.source_scope),
                marker = COALESCE(excluded.marker, processes.marker),
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                record.process_key,
                record.interested,
                record.interested_normalized,
                record.source_scope,
                record.marker,
                record.status,
                now,
                now,
            ),
        )
        row = connection.execute(
            "SELECT id FROM processes WHERE process_key = ? AND interested_normalized = ?",
            (record.process_key, record.interested_normalized),
        ).fetchone()
        return int(row["id"])

    # ------------------------------------------------------------- area scans

    def create_area_scan(
        self,
        source_scope: str,
        marker_label: str | None,
        marker_value: str | None,
        rows: Sequence[Mapping[str, Any]],
        origin: str = "extension",
        raw_sha256: str | None = None,
        source_command_id: int | None = None,
    ) -> int:
        """Persist one Área Restrita observation and update process states.

        The mapping is fail-closed: the portal decides which processes need
        complementation, but only a *more advanced* stored state survives the
        update, so a finished process is never pushed back to the start.

        When the scan came from an extension command, the command id makes the
        write idempotent: the same command can never produce a second
        observation, so a retry after a failure is safe.
        """

        observed_at = utc_now()
        counters = {"total": 0, "pending": 0, "completed": 0, "ambiguous": 0, "blocked": 0, "not_found": 0}
        with self._transaction() as connection:
            if source_command_id is not None:
                existing = connection.execute(
                    "SELECT id FROM area_scans WHERE source_command_id = ?",
                    (int(source_command_id),),
                ).fetchone()
                if existing is not None:
                    return int(existing["id"])
            cursor = connection.execute(
                "INSERT INTO area_scans (source_scope, marker_label, marker_value, observed_at, origin, "
                "raw_sha256, source_command_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    source_scope,
                    marker_label,
                    marker_value,
                    observed_at,
                    origin,
                    raw_sha256,
                    int(source_command_id) if source_command_id is not None else None,
                ),
            )
            scan_id = int(cursor.lastrowid)
            for raw_row in rows:
                counters["total"] += 1
                self._apply_scan_row(connection, scan_id, raw_row, observed_at, source_scope, marker_label, counters)
            connection.execute(
                "UPDATE area_scans SET total = ?, pending = ?, completed = ?, ambiguous = ?, "
                "blocked = ?, not_found = ? WHERE id = ?",
                (
                    counters["total"],
                    counters["pending"],
                    counters["completed"],
                    counters["ambiguous"],
                    counters["blocked"],
                    counters["not_found"],
                    scan_id,
                ),
            )
        return scan_id

    def _apply_scan_row(
        self,
        connection: sqlite3.Connection,
        scan_id: int,
        raw_row: Mapping[str, Any],
        observed_at: str,
        source_scope: str,
        marker_label: str | None,
        counters: dict[str, int],
    ) -> None:
        process_key = str(raw_row.get("process_key") or "").strip()
        interested = str(raw_row.get("interested") or "").strip()
        interested_normalized = str(raw_row.get("interested_normalized") or "").strip()
        if not process_key or not interested or not interested_normalized:
            return

        # An unrecognised or missing classification is treated as AMBIGUO, and
        # only an explicit PRECISA_COMPLEMENTAR ever queues a download.
        classification = str(raw_row.get("classification") or "AMBIGUO").strip().upper()
        if classification not in AREA_CLASSIFICATION_TARGET:
            classification = "AMBIGUO"
        counter_key = {
            "PRECISA_COMPLEMENTAR": "pending",
            "ATO_COMPLEMENTADO": "completed",
            "AMBIGUO": "ambiguous",
            "BLOQUEADO": "blocked",
            "NAO_ENCONTRADO_AREA_RESTRITA": "not_found",
        }[classification]
        counters[counter_key] += 1
        needs_complement = 1 if classification == "PRECISA_COMPLEMENTAR" else 0

        previous = connection.execute(
            "SELECT id, status FROM processes WHERE process_key = ? AND interested_normalized = ?",
            (process_key, interested_normalized),
        ).fetchone()
        target = AREA_CLASSIFICATION_TARGET[classification]
        previous_status = str(previous["status"]) if previous is not None else None
        if previous_status is not None and status_rank(previous_status) > status_rank(target):
            target = previous_status

        process_id = self._upsert_process_row(
            connection,
            ProcessRecord(
                process_key=process_key,
                interested=interested,
                interested_normalized=interested_normalized,
                source_scope=source_scope,
                marker=marker_label,
                status=target,
            ),
        )
        connection.execute(
            "UPDATE processes SET portal_act_id = ?, area_classification = ?, needs_complement = ?, "
            "last_area_scan_id = ? WHERE id = ?",
            (
                str(raw_row.get("portal_act_id") or "") or None,
                classification,
                needs_complement,
                scan_id,
                process_id,
            ),
        )
        connection.execute(
            "INSERT INTO area_scan_items (scan_id, process_id, process_key, interested, "
            "interested_normalized, portal_act_id, classification, needs_complement, action_observed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(scan_id, process_key, interested_normalized) "
            "DO UPDATE SET classification = excluded.classification, "
            "needs_complement = excluded.needs_complement, action_observed = excluded.action_observed",
            (
                scan_id,
                process_id,
                process_key,
                interested,
                interested_normalized,
                str(raw_row.get("portal_act_id") or "") or None,
                classification,
                needs_complement,
                str(raw_row.get("action_observed") or "") or None,
            ),
        )
        if previous_status is not None and previous_status != target:
            connection.execute(
                "INSERT INTO workflow_events (process_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                (
                    process_id,
                    AREA_CLASSIFICATION_EVENT[classification],
                    json.dumps(
                        {
                            "scan_id": scan_id,
                            "from": previous_status,
                            "to": target,
                            "classification": classification,
                            "action_observed": str(raw_row.get("action_observed") or "") or None,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    observed_at,
                ),
            )

    def get_area_scan(self, scan_id: int) -> dict[str, Any] | None:
        """Return one scan with its items."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM area_scans WHERE id = ?", (scan_id,)
            ).fetchone()
            if row is None:
                return None
            scan = dict(row)
            scan["items"] = [
                dict(item)
                for item in self._connection.execute(
                    "SELECT * FROM area_scan_items WHERE scan_id = ? ORDER BY id", (scan_id,)
                )
            ]
            return scan

    def latest_area_scan(self) -> dict[str, Any] | None:
        """Return the most recent scan with its items, or ``None``."""

        with self._lock:
            row = self._connection.execute(
                "SELECT id FROM area_scans ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return self.get_area_scan(int(row["id"]))

    # ------------------------------------------------------ extension commands

    def create_extension_command(self, command_type: str, payload: dict[str, Any] | None = None) -> int:
        """Queue one command for a registered extension client."""

        with self._transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO extension_commands (command_type, payload, state, created_at) "
                "VALUES (?, ?, 'QUEUED', ?)",
                (
                    command_type,
                    json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def queue_fill_command(
        self, command_type: str, payload: dict[str, Any] | None, fill_request_id: int
    ) -> int:
        """Queue a command that belongs to one fill request (M5)."""

        with self._transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO extension_commands (command_type, payload, state, created_at, fill_request_id) "
                "VALUES (?, ?, 'QUEUED', ?, ?)",
                (
                    command_type,
                    json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                    int(fill_request_id),
                ),
            )
            return int(cursor.lastrowid)

    # ----------------------------------------------------------- fill requests

    def create_fill_request(
        self,
        process_id: int,
        *,
        state: str = "OPENING",
        mode: str = "automatic",
        form_snapshot: dict[str, Any] | None = None,
    ) -> int:
        now = utc_now()
        with self._transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM processes WHERE id = ?", (process_id,)
            ).fetchone() is None:
                raise ValueError(f"unknown process: {process_id}")
            cursor = connection.execute(
                "INSERT INTO portal_fill_requests "
                "(process_id, state, mode, form_snapshot, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    process_id,
                    state,
                    mode,
                    json.dumps(form_snapshot, ensure_ascii=False, sort_keys=True)
                    if form_snapshot is not None
                    else None,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def update_fill_request(
        self,
        request_id: int,
        *,
        state: str | None = None,
        current_command_id: Any = _UNSET,
        error: Any = _UNSET,
        form_snapshot: Any = _UNSET,
    ) -> None:
        assignments = ["updated_at = ?"]
        parameters: list[Any] = [utc_now()]
        if state is not None:
            assignments.append("state = ?")
            parameters.append(state)
        if current_command_id is not _UNSET:
            assignments.append("current_command_id = ?")
            parameters.append(None if current_command_id is None else int(current_command_id))
        if error is not _UNSET:
            assignments.append("error = ?")
            parameters.append(error)
        if form_snapshot is not _UNSET:
            assignments.append("form_snapshot = ?")
            parameters.append(
                json.dumps(form_snapshot, ensure_ascii=False, sort_keys=True)
                if form_snapshot is not None
                else None
            )
        parameters.append(request_id)
        with self._transaction() as connection:
            updated = connection.execute(
                f"UPDATE portal_fill_requests SET {', '.join(assignments)} WHERE id = ?",
                tuple(parameters),
            ).rowcount
            if not updated:
                raise ValueError(f"unknown fill request: {request_id}")

    def get_fill_request(self, request_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM portal_fill_requests WHERE id = ?", (request_id,)
            ).fetchone()
        return self._decode_fill_request(row) if row is not None else None

    def latest_fill_request(self, process_id: int) -> dict[str, Any] | None:
        """Return the newest fill request for one process, if any."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM portal_fill_requests WHERE process_id = ? ORDER BY id DESC LIMIT 1",
                (int(process_id),),
            ).fetchone()
        return self._decode_fill_request(row) if row is not None else None

    def list_fill_requests(
        self, *, process_id: int | None = None, state: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM portal_fill_requests"
        clauses: list[str] = []
        parameters: list[Any] = []
        if process_id is not None:
            clauses.append("process_id = ?")
            parameters.append(process_id)
        if state is not None:
            clauses.append("state = ?")
            parameters.append(state)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id"
        with self._lock:
            return [
                self._decode_fill_request(row)
                for row in self._connection.execute(query, tuple(parameters))
            ]

    @staticmethod
    def _decode_fill_request(row: sqlite3.Row) -> dict[str, Any]:
        request = dict(row)
        raw = request.get("form_snapshot")
        request["form_snapshot"] = json.loads(raw) if raw else None
        return request

    def claim_extension_command(self, client_id: str) -> dict[str, Any] | None:
        """Atomically claim the oldest queued command for ``client_id``.

        ``BEGIN IMMEDIATE`` plus the primary key guarantees two pollers can
        never receive the same command. A claim carries a token and a lease: the
        result is only accepted from the client holding the token, and an
        expired lease returns the command to the queue (or fails it once the
        attempt budget is exhausted).
        """

        now = utc_now()
        with self._transaction() as connection:
            self._release_expired_leases(connection, now)
            row = connection.execute(
                "SELECT * FROM extension_commands WHERE state = 'QUEUED' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            attempts = int(row["attempt_count"]) + 1
            token = secrets.token_urlsafe(24)
            lease_expires_at = utc_after(COMMAND_LEASE_SECONDS)
            connection.execute(
                "UPDATE extension_commands SET state = 'CLAIMED', client_id = ?, claimed_at = ?, "
                "attempt_count = ?, claim_token = ?, lease_expires_at = ? WHERE id = ?",
                (client_id, now, attempts, token, lease_expires_at, int(row["id"])),
            )
            claimed = dict(row)
            claimed.update(
                {
                    "state": "CLAIMED",
                    "client_id": client_id,
                    "claimed_at": now,
                    "attempt_count": attempts,
                    "claim_token": token,
                    "lease_expires_at": lease_expires_at,
                }
            )
        return self._decode_command(claimed)

    def renew_extension_command_lease(
        self, command_id: int, *, client_id: str, claim_token: str
    ) -> bool:
        """Extend a live claim without allowing stale workers to regain ownership."""

        if not claim_token:
            return False
        now = utc_now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT state, client_id, claim_token, lease_expires_at "
                "FROM extension_commands WHERE id = ?",
                (int(command_id),),
            ).fetchone()
            if row is None or row["state"] != "CLAIMED":
                return False
            if str(row["client_id"] or "") != str(client_id):
                return False
            current_token = str(row["claim_token"] or "")
            if not current_token or not hmac.compare_digest(current_token, str(claim_token)):
                return False
            if not row["lease_expires_at"] or row["lease_expires_at"] <= now:
                return False
            cursor = connection.execute(
                "UPDATE extension_commands SET lease_expires_at = ? "
                "WHERE id = ? AND state = 'CLAIMED' AND client_id = ? "
                "AND claim_token = ? AND lease_expires_at > ?",
                (utc_after(COMMAND_LEASE_SECONDS), int(command_id), client_id, claim_token, now),
            )
            return cursor.rowcount == 1

    @staticmethod
    def _release_expired_leases(connection: sqlite3.Connection, now: str) -> None:
        """Requeue, or give up on, every claim whose lease already expired."""

        Store._release_claims(connection, now, expired_only=True)

    @staticmethod
    def _release_claims(
        connection: sqlite3.Connection, now: str, *, expired_only: bool
    ) -> tuple[int, int]:
        """Return claims to the queue and report (requeued, failed).

        An expired lease is one whose worker went away. At startup nothing of
        this process is running yet, so every claim is released the same way.
        """

        query = "SELECT id, attempt_count FROM extension_commands WHERE state = 'CLAIMED'"
        parameters: list[Any] = []
        if expired_only:
            query += " AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?"
            parameters.append(now)
        query += " ORDER BY id"
        rows = connection.execute(query, tuple(parameters)).fetchall()
        requeued = 0
        failed = 0
        for row in rows:
            attempts = int(row["attempt_count"]) + 1
            if attempts >= COMMAND_MAX_ATTEMPTS:
                connection.execute(
                    "UPDATE extension_commands SET state = 'FAILED', error = ?, finished_at = ?, "
                    "client_id = NULL, claim_token = NULL, lease_expires_at = NULL WHERE id = ?",
                    (
                        "a extensão não devolveu o resultado do comando dentro do prazo",
                        now,
                        int(row["id"]),
                    ),
                )
                failed += 1
                continue
            connection.execute(
                "UPDATE extension_commands SET state = 'QUEUED', client_id = NULL, claimed_at = NULL, "
                "claim_token = NULL, lease_expires_at = NULL WHERE id = ?",
                (int(row["id"]),),
            )
            requeued += 1
        return requeued, failed

    def recover_interrupted_runtime_state(self) -> dict[str, int]:
        """Return runtime state left behind by a previous process to a safe state.

        Every worker lives in memory, so after a restart nothing is running and
        any state that means "in progress" would wait forever. Nothing is ever
        marked as succeeded here: an interrupted analysis becomes an explicit
        error, and a downloaded item stays downloaded.
        """

        now = utc_now()
        reason = "a Mesa foi encerrada durante este trabalho"
        summary = {
            "commands_requeued": 0,
            "commands_failed": 0,
            "jobs_interrupted": 0,
            "items_requeued": 0,
            "analysis_interrupted": 0,
        }
        with self._transaction() as connection:
            requeued, failed = self._release_claims(connection, now, expired_only=False)
            summary["commands_requeued"] = requeued
            summary["commands_failed"] = failed

            jobs = connection.execute(
                "SELECT id, job_type FROM jobs WHERE status IN ('PENDING', 'RUNNING')"
            ).fetchall()
            for row in jobs:
                job_id = int(row["id"])
                connection.execute(
                    "UPDATE jobs SET status = 'INTERRUPTED', error = ? WHERE id = ?",
                    (reason, job_id),
                )
                summary["items_requeued"] += int(
                    connection.execute(
                        "UPDATE job_items SET state = 'QUEUED', error = ?, updated_at = ? "
                        "WHERE job_id = ? AND state IN ('QUEUED', 'DOWNLOADING', 'ANALISANDO')",
                        (reason, now, job_id),
                    ).rowcount
                )
                if str(row["job_type"]) == "acquisition":
                    connection.execute(
                        "UPDATE processes SET acquisition_state = 'QUEUED', updated_at = ? "
                        "WHERE id IN (SELECT process_id FROM job_items "
                        "WHERE job_id = ? AND state = 'QUEUED')",
                        (now, job_id),
                    )
            summary["jobs_interrupted"] = len(jobs)

            interrupted = connection.execute(
                "SELECT id FROM processes WHERE status = 'ANALISANDO'"
            ).fetchall()
            for row in interrupted:
                process_id = int(row["id"])
                connection.execute(
                    "UPDATE processes SET status = 'ERRO', updated_at = ? WHERE id = ?",
                    (now, process_id),
                )
                connection.execute(
                    "INSERT INTO workflow_events (process_id, event_type, payload, created_at) "
                    "VALUES (?, 'analysis_interrupted', ?, ?)",
                    (
                        process_id,
                        json.dumps({"reason": reason}, ensure_ascii=False, sort_keys=True),
                        now,
                    ),
                )
            summary["analysis_interrupted"] = len(interrupted)
        return summary

    def complete_extension_command(
        self,
        command_id: int,
        *,
        client_id: str,
        claim_token: str | None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> str:
        """Record the outcome of a claimed command and report what happened.

        The transition is conditional on the claim: another client may not
        finish someone else's command, and a claim whose token does not match is
        stale. Returns "ok", "replay" (already finished, so the caller must not
        repeat its side effects), "stale", "forbidden" or "unknown".
        """

        now = utc_now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT state, client_id, claim_token FROM extension_commands WHERE id = ?",
                (command_id,),
            ).fetchone()
            if row is None:
                return "unknown"
            state = str(row["state"])
            if state in {"SUCCEEDED", "FAILED"}:
                return "replay"
            if state != "CLAIMED":
                return "stale"
            if str(row["client_id"] or "") != str(client_id):
                return "forbidden"
            expected = str(row["claim_token"] or "")
            presented = str(claim_token or "")
            if not expected or not hmac.compare_digest(
                expected.encode("utf-8"), presented.encode("utf-8")
            ):
                return "stale"
            connection.execute(
                "UPDATE extension_commands SET state = ?, result = ?, error = ?, finished_at = ?, "
                "lease_expires_at = NULL WHERE id = ?",
                (
                    "FAILED" if error else "SUCCEEDED",
                    json.dumps(result, ensure_ascii=False, sort_keys=True) if result is not None else None,
                    error,
                    now,
                    command_id,
                ),
            )
        return "ok"

    def get_extension_command(self, command_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM extension_commands WHERE id = ?", (command_id,)
            ).fetchone()
        return self._decode_command(dict(row)) if row is not None else None

    def check_command_claim(
        self, command_id: int, *, client_id: str, claim_token: str | None
    ) -> str:
        """Report whether this client may still finish the command, without writing.

        Returns the same vocabulary as complete_extension_command, so the
        caller can decide *before* applying the effect of the command.
        """

        with self._lock:
            row = self._connection.execute(
                "SELECT state, client_id, claim_token FROM extension_commands WHERE id = ?",
                (command_id,),
            ).fetchone()
        if row is None:
            return "unknown"
        state = str(row["state"])
        if state in {"SUCCEEDED", "FAILED"}:
            return "replay"
        if state != "CLAIMED":
            return "stale"
        if str(row["client_id"] or "") != str(client_id):
            return "forbidden"
        expected = str(row["claim_token"] or "")
        presented = str(claim_token or "")
        if not expected or not hmac.compare_digest(
            expected.encode("utf-8"), presented.encode("utf-8")
        ):
            return "stale"
        return "ok"

    def find_area_scan_by_command(self, command_id: int) -> int | None:
        """The scan one command already produced, if it produced one."""

        with self._lock:
            row = self._connection.execute(
                "SELECT id FROM area_scans WHERE source_command_id = ?", (int(command_id),)
            ).fetchone()
        return int(row["id"]) if row is not None else None

    @staticmethod
    def _decode_command(raw: dict[str, Any]) -> dict[str, Any]:
        command = dict(raw)
        command["type"] = command.pop("command_type")
        payload = command.get("payload")
        command["payload"] = json.loads(payload) if payload else {}
        result = command.get("result")
        command["result"] = json.loads(result) if result else None
        return command

    # ----------------------------------------------------------- bridge clients

    def register_bridge_client(
        self,
        client_id: str,
        token_hash: str,
        origin: str | None = None,
        extension_id: str | None = None,
    ) -> None:
        """Persist the hash of a freshly registered extension token."""

        now = utc_now()
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO bridge_clients (client_id, token_hash, origin, extension_id, created_at, last_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(client_id) DO UPDATE SET "
                "token_hash = excluded.token_hash, origin = excluded.origin, "
                "extension_id = excluded.extension_id, last_seen_at = excluded.last_seen_at",
                (client_id, token_hash, origin, extension_id, now, now),
            )

    def verify_bridge_token(self, client_id: str, token_hash: str) -> bool:
        """Constant-time check of a registered client's token hash."""

        with self._lock:
            row = self._connection.execute(
                "SELECT token_hash FROM bridge_clients WHERE client_id = ?", (client_id,)
            ).fetchone()
        if row is None:
            return False
        return hmac.compare_digest(str(row["token_hash"]), str(token_hash))

    def authenticate_bridge_client(
        self,
        client_id: str,
        token_hash: str,
        origin: str | None,
        extension_id: str | None,
    ) -> bool:
        """Check the token *and* the origin that owns it.

        A registered token is only valid from the extension origin it was registered
        with: a token that leaks to another page cannot be replayed from there,
        and an extension id that does not match the Origin is refused.
        """

        with self._lock:
            row = self._connection.execute(
                "SELECT token_hash, origin, extension_id FROM bridge_clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
        if row is None:
            return False
        if not hmac.compare_digest(str(row["token_hash"]), str(token_hash)):
            return False
        registered_origin = str(row["origin"] or "").strip().casefold()
        presented_origin = str(origin or "").strip().casefold()
        if not registered_origin or not presented_origin or registered_origin != presented_origin:
            return False
        registered_id = str(row["extension_id"] or "").strip().casefold()
        if registered_id and registered_id != str(extension_id or "").strip().casefold():
            return False
        return True

    def list_bridge_clients(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM bridge_clients ORDER BY id"
                )
            ]

    def touch_bridge_client(self, client_id: str) -> None:
        """Record that a registered client just authenticated successfully."""

        with self._transaction() as connection:
            connection.execute(
                "UPDATE bridge_clients SET last_seen_at = ? WHERE client_id = ?",
                (utc_now(), client_id),
            )

    # --------------------------------------------------------------------- jobs

    def create_job(self, job_type: str, total: int = 0) -> int:
        with self._transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO jobs (job_type, status, total) VALUES (?, 'PENDING', ?)",
                (job_type, int(total)),
            )
            return int(cursor.lastrowid)

    def add_job_item(self, job_id: int, process_id: int, state: str = "QUEUED") -> None:
        now = utc_now()
        with self._transaction() as connection:
            job = connection.execute(
                "SELECT job_type FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if job is None:
                raise ValueError(f"unknown job {job_id}")
            connection.execute(
                "INSERT INTO job_items (job_id, process_id, state, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(job_id, process_id) DO UPDATE SET "
                "state = excluded.state, error = NULL, updated_at = excluded.updated_at",
                (job_id, process_id, state, now, now),
            )
            if str(job["job_type"]) == "acquisition":
                connection.execute(
                    "UPDATE processes SET acquisition_state = ?, updated_at = ? WHERE id = ?",
                    (state, now, process_id),
                )

    def mark_job_item(
        self,
        job_id: int,
        process_id: int,
        state: str,
        error: str | None = None,
        *,
        done_state: str = "DOWNLOADED",
    ) -> None:
        """Move one item and refresh the job counters from the item table."""

        now = utc_now()
        with self._transaction() as connection:
            job = connection.execute(
                "SELECT job_type FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if job is None:
                raise ValueError(f"unknown job {job_id}")
            if connection.execute(
                "SELECT 1 FROM processes WHERE id = ?", (process_id,)
            ).fetchone() is None:
                raise ValueError(f"unknown process: {process_id}")
            updated = connection.execute(
                "UPDATE job_items SET state = ?, error = ?, updated_at = ? "
                "WHERE job_id = ? AND process_id = ?",
                (state, error, now, job_id, process_id),
            ).rowcount
            if not updated:
                raise ValueError(f"job {job_id} has no item for process {process_id}")
            if str(job["job_type"]) == "acquisition":
                connection.execute(
                    "UPDATE processes SET acquisition_state = ?, updated_at = ? WHERE id = ?",
                    (state, now, process_id),
                )
            self._refresh_job_counters(connection, job_id, done_state)

    @staticmethod
    def _refresh_job_counters(
        connection: sqlite3.Connection, job_id: int, done_state: str = "DOWNLOADED"
    ) -> None:
        connection.execute(
            "UPDATE jobs SET "
            "completed = (SELECT COUNT(*) FROM job_items WHERE job_id = ? AND state = ?), "
            "failed = (SELECT COUNT(*) FROM job_items WHERE job_id = ? AND state = 'FAILED') "
            "WHERE id = ?",
            (job_id, done_state, job_id, job_id),
        )

    def set_job_status(
        self,
        job_id: int,
        status: str,
        *,
        started: bool = False,
        finished: bool = False,
        error: str | None = None,
        clear_error: bool = False,
        done_state: str = "DOWNLOADED",
    ) -> None:
        with self._transaction() as connection:
            if connection.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone() is None:
                raise ValueError(f"unknown job: {job_id}")
            assignments = ["status = ?"]
            parameters: list[Any] = [status]
            if started:
                assignments.append("started_at = COALESCE(started_at, ?)")
                parameters.append(utc_now())
            if finished:
                assignments.append("finished_at = ?")
                parameters.append(utc_now())
            if clear_error:
                assignments.append("error = NULL")
            if error is not None:
                assignments.append("error = ?")
                parameters.append(error)
            parameters.append(job_id)
            connection.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?", tuple(parameters)
            )
            self._refresh_job_counters(connection, job_id, done_state)

    def set_process_status(
        self,
        process_id: int,
        status: str,
        *,
        event_type: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Move one process state and, optionally, record why."""

        now = utc_now()
        with self._transaction() as connection:
            updated = connection.execute(
                "UPDATE processes SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, process_id),
            ).rowcount
            if not updated:
                raise ValueError(f"unknown process: {process_id}")
            if event_type:
                connection.execute(
                    "INSERT INTO workflow_events (process_id, event_type, payload, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        process_id,
                        event_type,
                        json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                        now,
                    ),
                )

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row is not None else None

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (int(limit),)
                )
            ]

    def list_job_items(self, job_id: int) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM job_items WHERE job_id = ? ORDER BY id", (job_id,)
                )
            ]

    def count_active_jobs(self, job_type: str | None = None) -> int:
        """Count jobs that have not finished, so a second one can be refused."""

        query = "SELECT COUNT(*) AS n FROM jobs WHERE status IN ('PENDING', 'RUNNING', 'WAITING_FOR_LOGIN')"
        parameters: tuple[Any, ...] = ()
        if job_type is not None:
            query += " AND job_type = ?"
            parameters = (job_type,)
        with self._lock:
            return int(self._connection.execute(query, parameters).fetchone()["n"])

    # -------------------------------------------------------------- acquisition

    def set_process_acquisition_state(self, process_id: int, state: str) -> None:
        with self._transaction() as connection:
            updated = connection.execute(
                "UPDATE processes SET acquisition_state = ?, updated_at = ? WHERE id = ?",
                (state, utc_now(), process_id),
            ).rowcount
            if not updated:
                raise ValueError(f"unknown process: {process_id}")

    def list_missing_pending_processes(self) -> list[dict[str, Any]]:
        """Pending processes whose bytes are not local yet, in portal order."""

        with self._lock:
            return [
                dict(row)
                for row in self._connection.execute(
                    """
                    SELECT p.* FROM processes p
                    LEFT JOIN area_scan_items i
                      ON i.process_id = p.id AND i.scan_id = p.last_area_scan_id
                    WHERE p.needs_complement = 1
                      AND p.acquisition_state IN ('NOT_DOWNLOADED', 'FAILED')
                      AND p.area_classification = 'PRECISA_COMPLEMENTAR'
                    ORDER BY (i.id IS NULL) ASC, i.id ASC, p.id ASC
                    """
                )
            ]

    def get_process(self, process_id: int) -> dict[str, Any] | None:
        """Return one process with its documents, fields and workflow history."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM processes WHERE id = ?", (process_id,)
            ).fetchone()
            if row is None:
                return None
            process = dict(row)
            process["documents"] = [
                dict(document)
                for document in self._connection.execute(
                    "SELECT * FROM documents WHERE process_id = ? ORDER BY id", (process_id,)
                )
            ]
            process["fields"] = [
                self._decode_field(field_row)
                for field_row in self._connection.execute(
                    "SELECT * FROM fields WHERE process_id = ? ORDER BY id", (process_id,)
                )
            ]
            process["events"] = [
                self._decode_event(event_row)
                for event_row in self._connection.execute(
                    "SELECT * FROM workflow_events WHERE process_id = ? ORDER BY id", (process_id,)
                )
            ]
            return process

    def list_processes(self, status: str | None = None) -> list[dict[str, Any]]:
        """List processes, optionally filtered by workflow status."""

        query = "SELECT * FROM processes"
        parameters: tuple[Any, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            parameters = (status,)
        query += " ORDER BY process_key ASC, id ASC"
        with self._lock:
            return [dict(row) for row in self._connection.execute(query, parameters)]

    def find_process(self, process_key: str, interested_normalized: str) -> dict[str, Any] | None:
        """Look a process up by its natural key without creating it."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM processes WHERE process_key = ? AND interested_normalized = ?",
                (process_key, interested_normalized),
            ).fetchone()
            return dict(row) if row is not None else None

    # --------------------------------------------------------------- documents

    def replace_documents(self, process_id: int, documents: Sequence[DocumentRecord]) -> None:
        """Reconcile the document set of one process, keeping stable ids.

        Deleting and reinserting would hand every document a new id, and a
        field that points at one (fields.document_id) would silently lose its
        evidence. Documents are matched by (process_id, source_id): existing
        rows are updated in place, new ones inserted, and only the ones that
        really disappeared are removed - with the loss recorded.
        """

        wanted = {document.source_id: document for document in documents}
        with self._transaction() as connection:
            existing = {
                str(row["source_id"]): int(row["id"])
                for row in connection.execute(
                    "SELECT id, source_id FROM documents WHERE process_id = ?", (process_id,)
                )
            }
            connection.executemany(
                """
                INSERT INTO documents (
                    process_id, source_id, event, title, relative_path,
                    sha256, page_count, classification, storage_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(process_id, source_id) DO UPDATE SET
                    event = excluded.event,
                    title = excluded.title,
                    relative_path = excluded.relative_path,
                    sha256 = excluded.sha256,
                    page_count = excluded.page_count,
                    classification = excluded.classification,
                    storage_state = excluded.storage_state
                """,
                [
                    (
                        process_id,
                        document.source_id,
                        document.event,
                        document.title,
                        document.relative_path,
                        document.sha256,
                        document.page_count,
                        document.classification,
                        document.storage_state,
                    )
                    for document in documents
                ],
            )
            removed = sorted(source_id for source_id in existing if source_id not in wanted)
            if not removed:
                return
            placeholders = ", ".join("?" for _ in removed)
            lost_evidence = int(
                connection.execute(
                    "SELECT COUNT(*) AS n FROM fields WHERE process_id = ? AND document_id IN "
                    f"(SELECT id FROM documents WHERE process_id = ? AND source_id IN ({placeholders}))",
                    (process_id, process_id, *removed),
                ).fetchone()["n"]
            )
            connection.executemany(
                "DELETE FROM documents WHERE process_id = ? AND source_id = ?",
                [(process_id, source_id) for source_id in removed],
            )
            if lost_evidence:
                # A field pointed at a document that is gone: say so and put
                # the process back in front of the operator.
                now = utc_now()
                connection.execute(
                    "UPDATE processes SET status = 'REVISAR', updated_at = ? WHERE id = ?",
                    (now, process_id),
                )
                connection.execute(
                    "INSERT INTO workflow_events (process_id, event_type, payload, created_at) "
                    "VALUES (?, 'documents_removed', ?, ?)",
                    (
                        process_id,
                        json.dumps(
                            {"removed": removed, "lost_evidence": lost_evidence},
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        now,
                    ),
                )

    def list_documents(self, process_id: int) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM documents WHERE process_id = ? ORDER BY id", (process_id,)
                )
            ]

    def list_all_documents(self) -> list[dict[str, Any]]:
        """List every document row; used by the archive reconcilers."""

        with self._lock:
            return [
                dict(row)
                for row in self._connection.execute("SELECT * FROM documents ORDER BY id")
            ]

    def document_counts(self) -> dict[int, int]:
        """Return ``{process_id: document_count}`` for the process list."""

        with self._lock:
            return {
                int(row["process_id"]): int(row["n"])
                for row in self._connection.execute(
                    "SELECT process_id, COUNT(*) AS n FROM documents GROUP BY process_id"
                )
            }

    def get_document(self, document_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    # ------------------------------------------------------------------ fields

    def replace_fields(self, process_id: int, fields: Sequence[FieldRecord]) -> None:
        """Replace the full field set of one process."""

        with self._transaction() as connection:
            connection.execute("DELETE FROM fields WHERE process_id = ?", (process_id,))
            connection.executemany(
                """
                INSERT INTO fields (
                    process_id, field_name, value, status, confidence,
                    document_id, page, evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        process_id,
                        field.field_name,
                        field.value,
                        field.status,
                        field.confidence,
                        field.document_id,
                        field.page,
                        json.dumps(field.evidence, ensure_ascii=False, sort_keys=True)
                        if field.evidence is not None
                        else None,
                    )
                    for field in fields
                ],
            )

    def list_fields(self, process_id: int) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._decode_field(row)
                for row in self._connection.execute(
                    "SELECT * FROM fields WHERE process_id = ? ORDER BY id", (process_id,)
                )
            ]

    # ---------------------------------------------------------- workflow events

    def add_workflow_event(
        self, process_id: int, event_type: str, payload: dict[str, Any] | None = None
    ) -> int:
        """Append one immutable workflow event and return its id."""

        with self._transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO workflow_events (process_id, event_type, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    process_id,
                    event_type,
                    json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def list_workflow_events(self, process_id: int) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._decode_event(row)
                for row in self._connection.execute(
                    "SELECT * FROM workflow_events WHERE process_id = ? ORDER BY id", (process_id,)
                )
            ]

    # ----------------------------------------------------------------- summary

    # --------------------------------------------------------------- metadata

    def get_metadata(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM metadata WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row is not None else default

    def set_metadata(self, key: str, value: str | None) -> None:
        with self._transaction() as connection:
            if value is None:
                connection.execute("DELETE FROM metadata WHERE key = ?", (key,))
                return
            connection.execute(
                "INSERT INTO metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )

    # ----------------------------------------------------------- archive blobs

    def upsert_archive_blob(
        self,
        sha256: str,
        *,
        size_bytes: int | None = None,
        local_relative_path: str | None = None,
        external_path: str | None = None,
        local_present: bool | None = None,
        external_present: bool | None = None,
        verified_at: str | None = None,
    ) -> None:
        """Record where one canonical byte sequence lives right now."""

        now = utc_now()
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO archive_blobs (sha256, size_bytes, local_relative_path, external_path, "
                "local_present, external_present, verified_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(sha256) DO UPDATE SET "
                "size_bytes = CASE WHEN excluded.size_bytes > 0 THEN excluded.size_bytes ELSE archive_blobs.size_bytes END, "
                "local_relative_path = COALESCE(excluded.local_relative_path, archive_blobs.local_relative_path), "
                "external_path = COALESCE(excluded.external_path, archive_blobs.external_path), "
                "local_present = COALESCE(excluded.local_present, archive_blobs.local_present), "
                "external_present = COALESCE(excluded.external_present, archive_blobs.external_present), "
                "verified_at = COALESCE(excluded.verified_at, archive_blobs.verified_at)",
                (
                    sha256,
                    int(size_bytes or 0),
                    local_relative_path,
                    external_path,
                    0 if local_present is None else int(bool(local_present)),
                    0 if external_present is None else int(bool(external_present)),
                    verified_at or now,
                ),
            )

    def get_archive_blob(self, sha256: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM archive_blobs WHERE sha256 = ?", (sha256,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_archive_blobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self._connection.execute("SELECT * FROM archive_blobs ORDER BY sha256")
            ]

    def set_blob_presence(
        self,
        sha256: str,
        *,
        local_present: bool | None = None,
        external_present: bool | None = None,
        external_path: str | None = None,
        size_bytes: int | None = None,
        verified_at: str | None = None,
    ) -> None:
        self.upsert_archive_blob(
            sha256,
            size_bytes=size_bytes,
            external_path=external_path,
            local_present=local_present,
            external_present=external_present,
            verified_at=verified_at,
        )

    def mark_document_storage_state(self, document_id: int, state: str) -> None:
        with self._transaction() as connection:
            updated = connection.execute(
                "UPDATE documents SET storage_state = ? WHERE id = ?", (state, document_id)
            ).rowcount
            if not updated:
                raise ValueError(f"unknown document: {document_id}")

    def documents_for_sha(self, sha256: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM documents WHERE sha256 = ? ORDER BY id", (sha256,)
                )
            ]

    def count_hot_documents(self, sha256: str) -> int:
        """How many HOT documents still need these bytes on this machine."""

        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS n FROM documents WHERE sha256 = ? AND storage_state = 'HOT'",
                (sha256,),
            ).fetchone()
        return int(row["n"])

    def list_document_shas(self) -> list[str]:
        """Every SHA the documents reference, registered or not."""

        with self._lock:
            return [
                str(row["sha256"])
                for row in self._connection.execute(
                    "SELECT DISTINCT sha256 FROM documents ORDER BY sha256"
                )
            ]

    def storage_summary(self) -> dict[str, Any]:
        """Database-side totals for the Mesa storage panel."""

        with self._lock:
            return {
                "schema_version": self._read_schema_version(),
                "processes": {
                    "total": self._count("processes"),
                    "by_status": self._group_count("processes", "status"),
                },
                "documents": {
                    "total": self._count("documents"),
                    "unique_sha256": self._unique_sha_count(),
                    "by_storage_state": self._group_count("documents", "storage_state"),
                },
                "fields": {
                    "total": self._count("fields"),
                    "by_status": self._group_count("fields", "status"),
                },
                "jobs": {"total": self._count("jobs")},
                "events": {"total": self._count("workflow_events")},
            }

    def _count(self, table: str) -> int:
        row = self._connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"])

    def _group_count(self, table: str, column: str) -> dict[str, int]:
        rows = self._connection.execute(
            f"SELECT {column} AS k, COUNT(*) AS n FROM {table} GROUP BY {column} ORDER BY {column}"
        )
        return {str(row["k"]): int(row["n"]) for row in rows if row["k"] is not None}

    def _unique_sha_count(self) -> int:
        row = self._connection.execute(
            "SELECT COUNT(DISTINCT sha256) AS n FROM documents"
        ).fetchone()
        return int(row["n"])

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _decode_field(row: sqlite3.Row) -> dict[str, Any]:
        field_row = dict(row)
        raw = field_row.get("evidence")
        field_row["evidence"] = json.loads(raw) if raw else None
        return field_row

    @staticmethod
    def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
        event_row = dict(row)
        raw = event_row.get("payload")
        event_row["payload"] = json.loads(raw) if raw else {}
        return event_row
