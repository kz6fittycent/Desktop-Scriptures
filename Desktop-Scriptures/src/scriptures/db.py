"""Database connection and schema management for the Scriptures app.

In production this file lives under $SNAP_USER_COMMON so it persists
across snap revision upgrades. For development it defaults to a local
path relative to the project.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection to the scripture database, creating the schema
    if this is a fresh database file.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()


def fts5_available(conn: sqlite3.Connection) -> bool:
    """Confirm the SQLite build this Python was linked against supports FTS5.
    Ubuntu's system SQLite has FTS5 enabled, but this is worth checking
    explicitly since it's a hard requirement for search to work at all.
    """
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_check USING fts5(x)")
        conn.execute("DROP TABLE _fts5_check")
        return True
    except sqlite3.OperationalError:
        return False
