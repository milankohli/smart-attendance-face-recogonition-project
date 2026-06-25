"""
utils/db_manager.py
───────────────────────────────────────────────────────────────────────────────
Smart Attendance System — Centralised SQLite Database Manager

WHY THIS FILE EXISTS
────────────────────
The original attendance_manager.py embedded its own _get_connection() helper
and _CREATE_TABLE_SQL directly.  attendance_system.py had an inline
_AttendanceManager class that wrote ONLY to CSV (no SQLite at all).

This module consolidates every database concern in one place:
  • Schema creation + migrations
  • Thread-safe connection factory
  • Low-level insert / query helpers
  • Reused by both attendance_system.py (live writes) and
    attendance_manager.py (queries + reports)

SCHEMA
──────
Table: attendance
  id          INTEGER PK AUTOINCREMENT
  name        TEXT    NOT NULL          — recognised person
  date        TEXT    NOT NULL          — ISO date YYYY-MM-DD
  time        TEXT    NOT NULL          — HH:MM:SS
  similarity  REAL    NOT NULL          — cosine similarity score [0,1]
  status      TEXT    DEFAULT 'Present' — extensible status field
  created_at  TEXT    DEFAULT datetime('now','localtime')

  UNIQUE(name, date, time)              — idempotent writes

Indexes: idx_attendance_date, idx_attendance_name, idx_attendance_name_date

Table: registered_persons
  id            INTEGER PK AUTOINCREMENT
  name          TEXT    UNIQUE NOT NULL
  embedding_count INTEGER DEFAULT 0
  registered_at TEXT    NOT NULL
  updated_at    TEXT    NOT NULL

  (Mirrors embedding store metadata for SQL-queryable registration history.)
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from utils.config import Config
from utils.logger import get_logger

log = get_logger(__name__)


# ── Schema ────────────────────────────────────────────────────────────────────
_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;

CREATE TABLE IF NOT EXISTS attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    time        TEXT    NOT NULL,
    similarity  REAL    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'Present',
    created_at  TEXT    DEFAULT (datetime('now','localtime')),
    UNIQUE(name, date, time)
);

CREATE INDEX IF NOT EXISTS idx_attendance_date
    ON attendance(date);

CREATE INDEX IF NOT EXISTS idx_attendance_name
    ON attendance(name);

CREATE INDEX IF NOT EXISTS idx_attendance_name_date
    ON attendance(name, date);

CREATE TABLE IF NOT EXISTS registered_persons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    UNIQUE NOT NULL,
    embedding_count INTEGER NOT NULL DEFAULT 0,
    registered_at   TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
"""

# ── Connection pool (one connection per thread) ───────────────────────────────
_local = threading.local()


class DBManager:
    """
    Thread-safe SQLite manager for the attendance system.

    One DBManager instance is safe to share across the main loop and any
    background threads — each thread gets its own sqlite3.Connection via
    threading.local().

    Parameters
    ----------
    db_path : Path | None
        Override the database file path.  Uses Config.DB_FILE by default.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path or Config.DB_FILE
        Config.ensure_dirs()
        # Boot the schema on first use from the calling thread
        with self._conn() as conn:
            conn.executescript(_DDL)
            conn.commit()
        log.info(f"DBManager ready  |  db={self._db_path}")

    # ── Connection management ─────────────────────────────────────────────────
    def _conn(self) -> sqlite3.Connection:
        """
        Return a thread-local sqlite3.Connection, creating it if needed.

        WAL mode + row_factory are set once per connection.
        """
        if not getattr(_local, "conn", None):
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # WAL already set via DDL PRAGMA, but enforce on connection too
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous  = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            _local.conn = conn
            log.debug(f"Opened SQLite connection (thread={threading.get_ident()})")
        return _local.conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager: BEGIN … COMMIT, rolling back on exception."""
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            log.error(f"SQLite transaction rolled back: {exc}")
            raise

    # ── Attendance writes ─────────────────────────────────────────────────────
    def insert_attendance(
        self,
        name:       str,
        date_str:   str,
        time_str:   str,
        similarity: float,
        status:     str = "Present",
    ) -> bool:
        """
        Insert one attendance record.

        The UNIQUE(name, date, time) constraint means the same person cannot
        be inserted twice at the exact same second — INSERT OR IGNORE is used
        so duplicate calls are silently skipped (returns False).

        Returns
        -------
        bool – True if the row was inserted, False if it was a duplicate.
        """
        try:
            with self.transaction() as conn:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO attendance "
                    "(name, date, time, similarity, status) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (name, date_str, time_str, round(similarity, 6), status),
                )
                inserted = cursor.rowcount > 0
            if inserted:
                log.debug(f"DB insert: {name} {date_str} {time_str} sim={similarity:.4f}")
            return inserted
        except sqlite3.Error as exc:
            log.error(f"insert_attendance failed for {name}: {exc}")
            return False

    # ── Registration writes ───────────────────────────────────────────────────
    def upsert_person(self, name: str, embedding_count: int) -> None:
        """
        Insert or update the registered_persons record for `name`.

        Called from register_face.py after successful embedding generation.
        """
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with self.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO registered_persons (name, embedding_count, registered_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        embedding_count = excluded.embedding_count,
                        updated_at      = excluded.updated_at
                    """,
                    (name, embedding_count, now, now),
                )
        except sqlite3.Error as exc:
            log.error(f"upsert_person failed for {name}: {exc}")

    def delete_person(self, name: str) -> bool:
        """Remove a person from registered_persons. Returns True if found."""
        try:
            with self.transaction() as conn:
                cursor = conn.execute(
                    "DELETE FROM registered_persons WHERE name = ?", (name,)
                )
            return cursor.rowcount > 0
        except sqlite3.Error as exc:
            log.error(f"delete_person failed for {name}: {exc}")
            return False

    # ── Attendance queries ────────────────────────────────────────────────────
    def fetch_by_date(self, date_str: str) -> List[sqlite3.Row]:
        """All attendance rows for a specific date, ordered by time."""
        conn = self._conn()
        return conn.execute(
            "SELECT name, date, time, similarity, status "
            "FROM attendance WHERE date = ? ORDER BY time",
            (date_str,),
        ).fetchall()

    def fetch_by_name(self, name: str) -> List[sqlite3.Row]:
        """All attendance rows for a specific person, newest first."""
        conn = self._conn()
        return conn.execute(
            "SELECT name, date, time, similarity, status "
            "FROM attendance WHERE name = ? ORDER BY date DESC, time DESC",
            (name,),
        ).fetchall()

    def fetch_range(self, start: str, end: str) -> List[sqlite3.Row]:
        """Attendance rows between start and end date (inclusive)."""
        conn = self._conn()
        return conn.execute(
            "SELECT name, date, time, similarity, status "
            "FROM attendance WHERE date BETWEEN ? AND ? ORDER BY date, time",
            (start, end),
        ).fetchall()

    def fetch_all(self) -> List[sqlite3.Row]:
        """Every attendance row, ordered by date + time."""
        conn = self._conn()
        return conn.execute(
            "SELECT name, date, time, similarity, status "
            "FROM attendance ORDER BY date, time"
        ).fetchall()

    def fetch_summary(self) -> List[sqlite3.Row]:
        """Per-person aggregate: count of distinct days, first/last seen."""
        conn = self._conn()
        return conn.execute(
            """
            SELECT
                name,
                COUNT(DISTINCT date)   AS days_present,
                COUNT(*)               AS total_entries,
                MIN(date)              AS first_seen,
                MAX(date)              AS last_seen,
                ROUND(AVG(similarity), 4) AS avg_similarity
            FROM attendance
            GROUP BY name
            ORDER BY name
            """
        ).fetchall()

    def fetch_daily_counts(self) -> List[sqlite3.Row]:
        """Total present count per day."""
        conn = self._conn()
        return conn.execute(
            """
            SELECT date, COUNT(DISTINCT name) AS unique_persons, COUNT(*) AS total_entries
            FROM attendance
            GROUP BY date
            ORDER BY date
            """
        ).fetchall()

    def person_present_today(self, name: str, date_str: str) -> bool:
        """True if `name` has at least one record for `date_str`."""
        conn = self._conn()
        row = conn.execute(
            "SELECT 1 FROM attendance WHERE name = ? AND date = ? LIMIT 1",
            (name, date_str),
        ).fetchone()
        return row is not None

    # ── Registered persons queries ────────────────────────────────────────────
    def fetch_registered_persons(self) -> List[sqlite3.Row]:
        """All rows from registered_persons, ordered by name."""
        conn = self._conn()
        return conn.execute(
            "SELECT name, embedding_count, registered_at, updated_at "
            "FROM registered_persons ORDER BY name"
        ).fetchall()

    # ── Utility ───────────────────────────────────────────────────────────────
    def close(self) -> None:
        """Close the thread-local connection (call at end of main thread)."""
        conn = getattr(_local, "conn", None)
        if conn:
            conn.close()
            _local.conn = None
            log.debug("SQLite connection closed.")

    def __repr__(self) -> str:
        return f"<DBManager db={self._db_path}>"
