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
    _migrate_whole_verse_highlights(conn)
    _migrate_add_chapter_metadata_columns(conn)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    _backfill_migrated_highlights(conn)
    conn.commit()


def _migrate_whole_verse_highlights(conn: sqlite3.Connection) -> None:
    """An earlier highlights table (one row per verse, no start/end
    offsets - the whole verse was "the" highlight) predates letting the
    user drag-select just a word or phrase. `CREATE TABLE IF NOT EXISTS`
    below won't add the new columns to an existing table, so a database
    still on that shape needs its highlights table moved aside before the
    real schema is (re)applied; `_backfill_migrated_highlights` then
    copies its rows forward as full-verse ranges.
    """
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'highlights'"
    ).fetchone()
    if not table_exists:
        return
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(highlights)")}
    if "start_offset" in columns:
        return
    conn.execute("ALTER TABLE highlights RENAME TO highlights_pre_ranges")


def _backfill_migrated_highlights(conn: sqlite3.Connection) -> None:
    old_table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'highlights_pre_ranges'"
    ).fetchone()
    if not old_table_exists:
        return
    conn.execute(
        "INSERT INTO highlights (verse_id, color, start_offset, end_offset, created_at) "
        "SELECT old.verse_id, old.color, 0, LENGTH(v.text), old.created_at "
        "FROM highlights_pre_ranges old JOIN verses v ON v.id = old.verse_id"
    )
    conn.execute("DROP TABLE highlights_pre_ranges")


def _migrate_add_chapter_metadata_columns(conn: sqlite3.Connection) -> None:
    """`CREATE TABLE IF NOT EXISTS` below won't add columns to a chapters
    table that already exists from before the Journal of Discourses
    import needed title/speaker/discourse_date - add them here if
    missing. Safe on a fresh database too: PRAGMA table_info on a
    not-yet-created table just returns no rows, so the "already there"
    check below is skipped rather than erroring, and schema.sql then
    creates the table with these columns already included.
    """
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chapters'"
    ).fetchone()
    if not table_exists:
        return
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(chapters)")}
    if "title" in columns:
        return
    conn.execute("ALTER TABLE chapters ADD COLUMN title TEXT")
    conn.execute("ALTER TABLE chapters ADD COLUMN speaker TEXT")
    conn.execute("ALTER TABLE chapters ADD COLUMN discourse_date TEXT")


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
