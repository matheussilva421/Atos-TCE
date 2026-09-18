"""SQLite source of truth for the Mesa.

The store owns persistence and durable workflow state. It never touches a
browser, a PDF or a filesystem path outside the database it was opened on;
adapters translate external observations into the records defined here.

Every migration runs in its own transaction and ``metadata.schema_version`` is
bumped inside that same transaction, so a half-applied schema is never visible.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import DocumentRecord, FieldRecord, ProcessRecord

SCHEMA_VERSION = 1


class StoreError(RuntimeError):
    """Raised when the database cannot satisfy a Mesa invariant."""


def utc_now() -> str:
    """Return the current UTC time as a stable, sortable ISO-8601 string."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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

        now = utc_now()
        with self._transaction() as connection:
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
        """Replace the full document set of one process."""

        with self._transaction() as connection:
            connection.execute("DELETE FROM documents WHERE process_id = ?", (process_id,))
            connection.executemany(
                """
                INSERT INTO documents (
                    process_id, source_id, event, title, relative_path,
                    sha256, page_count, classification, storage_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
