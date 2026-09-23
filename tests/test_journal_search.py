"""Standalone test script for src/scriptures/data_access.py's
search_journal_entries and db.py's journal_entries_fts backfill
migration. No test framework, no Qt event loop required (see
tests/test_ask.py's own docstring for why this project tests pure logic
this way rather than with a framework).

Run directly:

    python3 tests/test_journal_search.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.data_access import save_journal_entry, search_journal_entries  # noqa: E402
from scriptures.db import connect  # noqa: E402


def _make_db() -> tuple:
    tmp_root = Path(tempfile.mkdtemp(prefix="scriptures-journal-search-test-"))
    conn = connect(tmp_root / "test.db")
    return conn, tmp_root


def test_search_matches_entry_text() -> None:
    conn, tmp_root = _make_db()
    try:
        save_journal_entry(conn, "2026-09-10", "A quiet morning of prayer and reflection.")
        save_journal_entry(conn, "2026-09-11", "Thinking about patience today.")

        results = search_journal_entries(conn, "prayer")
        assert len(results) == 1
        assert results[0].entry_date == "2026-09-10"

        assert search_journal_entries(conn, "patience")[0].entry_date == "2026-09-11"
        assert search_journal_entries(conn, "nonexistentword") == []

        print("test_search_matches_entry_text: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_search_ignores_linked_scripture_text() -> None:
    """A query matching only the linked verse's own scripture text - not
    anything the user actually wrote - must not surface the entry. Same
    "your own words, not what you linked to" behavior as notes."""
    conn, tmp_root = _make_db()
    try:
        conn.execute(
            "INSERT INTO volumes (id, name, slug, sort_order) VALUES (1, 'Holy Bible', 'holy-bible', 1)"
        )
        conn.execute("INSERT INTO books (id, volume_id, name, sort_order) VALUES (1, 1, 'Genesis', 1)")
        conn.execute("INSERT INTO chapters (id, book_id, chapter_number) VALUES (1, 1, 1)")
        conn.execute(
            "INSERT INTO verses (id, chapter_id, verse_number, text, reference) "
            "VALUES (1, 1, 1, 'In the beginning God created the heaven and the earth.', 'Genesis 1:1')"
        )
        conn.commit()

        save_journal_entry(conn, "2026-09-10", "Grateful today.", verse_id=1)

        assert search_journal_entries(conn, "beginning") == [], (
            "a query matching only the verse's own text must not surface the entry"
        )
        assert search_journal_entries(conn, "Grateful")[0].reference == "Genesis 1:1"

        print("test_search_ignores_linked_scripture_text: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_fts_backfill_covers_pre_existing_entries() -> None:
    """Simulates an upgrade: a journal entry written before
    journal_entries_fts existed (inserted with the AFTER INSERT trigger
    temporarily removed, so it never got indexed) becomes searchable
    again the next time connect() runs its one-time backfill."""
    conn, tmp_root = _make_db()
    try:
        conn.execute("DROP TRIGGER journal_entries_ai")
        conn.execute(
            "INSERT INTO journal_entries (entry_date, text) VALUES (?, ?)",
            ("2026-08-01", "An entry written before search existed."),
        )
        conn.execute("DELETE FROM settings WHERE key = 'journal_entries_fts_backfilled'")
        conn.commit()
        conn.execute(
            "CREATE TRIGGER journal_entries_ai AFTER INSERT ON journal_entries BEGIN "
            "INSERT INTO journal_entries_fts(rowid, text) VALUES (new.id, new.text); END"
        )
        conn.commit()

        assert search_journal_entries(conn, "existed") == []

        conn.close()
        conn2 = connect(tmp_root / "test.db")
        results = search_journal_entries(conn2, "existed")
        assert len(results) == 1
        assert results[0].entry_date == "2026-08-01"

        print("test_fts_backfill_covers_pre_existing_entries: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    test_search_matches_entry_text()
    test_search_ignores_linked_scripture_text()
    test_fts_backfill_covers_pre_existing_entries()
    print("All journal search tests passed.")
