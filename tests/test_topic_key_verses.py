"""Standalone test script for scripts/build_topic_key_verses.py, the
topic_key_verses table, data_access.get_topic_key_passages, and db.py's
syncing of key verses from the bundled database. No test framework (see
tests/test_ask.py's own docstring for why).

Run directly:

    python3 tests/test_topic_key_verses.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_topic_key_verses as bkv  # noqa: E402
from scriptures.data_access import get_topic_key_passages  # noqa: E402
from scriptures.db import compact, connect, sync_bundled_content  # noqa: E402

REAL_DB = PROJECT_ROOT / "data" / "scriptures.db"


def test_every_curated_passage_resolves_against_the_real_text() -> None:
    """The safety check the build itself runs: every entry is a real verse
    or range in the Standard Works, every topic has key passages, and
    every slug is a real topic."""
    conn = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    assert bkv.verify(conn) == []
    # Spot-check the gaps that motivated this.
    assert bkv.resolve(conn, "Moroni 10:4-5") == (
        "book-of-mormon", ["Moroni 10:4", "Moroni 10:5"]
    )
    assert "Doctrine and Covenants 132:19" in bkv.KEY_VERSES["marriage"]
    assert "Moroni 10:4-5" in bkv.KEY_VERSES["testimony"]
    print("test_every_curated_passage_resolves_against_the_real_text: PASSED")


def test_verify_catches_bad_entries() -> None:
    conn = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    original = dict(bkv.KEY_VERSES)
    try:
        bkv.KEY_VERSES["faith"] = ["Hebrews 11:1", "Hebrews 99:1", "Alma 32:28-21", "nonsense"]
        bkv.KEY_VERSES["not-a-topic"] = ["Hebrews 11:1"]
        problems = bkv.verify(conn)
        assert any("Hebrews 99:1" in p for p in problems), problems
        assert any("backwards" in p for p in problems), problems
        assert any("nonsense" in p for p in problems), problems
        assert any("not-a-topic" in p for p in problems), problems
    finally:
        bkv.KEY_VERSES.clear()
        bkv.KEY_VERSES.update(original)
    print("test_verify_catches_bad_entries: PASSED")


def _seeded(path: Path) -> sqlite3.Connection:
    conn = connect(path)
    conn.execute("INSERT INTO volumes (id, name, slug, sort_order) VALUES (2, 'The Book of Mormon', 'book-of-mormon', 2)")
    conn.execute("INSERT INTO books (id, volume_id, name, sort_order) VALUES (1, 2, 'Moroni', 1)")
    conn.execute("INSERT INTO chapters (id, book_id, chapter_number) VALUES (1, 1, 10)")
    for n in (3, 4, 5, 6):
        conn.execute(
            "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (1, ?, ?, ?)",
            (n, f"verse {n} text", f"Moroni 10:{n}"),
        )
    conn.execute(
        "INSERT INTO topics (id, name, slug, description, sort_order) "
        "VALUES (1, 'Testimony', 'testimony', 'x', 1)"
    )
    conn.commit()
    return conn


def test_key_passages_resolve_and_sync_from_the_bundled_database() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-key-verses-test-"))
    try:
        bundled = _seeded(tmp / "bundled.db")
        bundled.executemany(
            "INSERT INTO topic_key_verses (topic_id, volume_slug, reference, sort_order) VALUES (1, ?, ?, ?)",
            [("book-of-mormon", "Moroni 10:4-5", 1), ("book-of-mormon", "Moroni 10:3", 2)],
        )
        bundled.commit()
        bundled.close()

        # A user's database with a stale, since-removed key passage.
        local = _seeded(tmp / "local.db")
        local.execute(
            "INSERT INTO topic_key_verses (topic_id, volume_slug, reference, sort_order) "
            "VALUES (1, 'book-of-mormon', 'Moroni 10:6', 1)"
        )
        local.commit()
        sync_bundled_content(local, tmp / "bundled.db")

        passages = get_topic_key_passages(local, 1)
        assert [p.reference for p in passages] == ["Moroni 10:4-5", "Moroni 10:3"], passages
        first = passages[0]
        assert (first.chapter_id, first.verse_start, first.verse_end) == (1, 4, 5)
        assert first.text == "verse 4 text verse 5 text"
        print("test_key_passages_resolve_and_sync_from_the_bundled_database: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_compact_never_ships_device_specific_settings() -> None:
    """Build scripts open data/scriptures.db through connect(), which
    gives it a device_id - compact(), every script's last step, must
    remove it again, or every fresh install would share one sync
    identity."""
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-compact-test-"))
    try:
        conn = connect(tmp / "shipped.db")
        conn.execute("INSERT INTO settings (key, value) VALUES ('font_family', 'Noto Sans')")
        conn.commit()
        assert conn.execute("SELECT 1 FROM settings WHERE key = 'device_id'").fetchone()
        compact(conn)
        keys = [r[0] for r in conn.execute("SELECT key FROM settings ORDER BY key")]
        assert keys == ["font_family"], keys
        print("test_compact_never_ships_device_specific_settings: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_every_curated_passage_resolves_against_the_real_text()
    test_verify_catches_bad_entries()
    test_key_passages_resolve_and_sync_from_the_bundled_database()
    test_compact_never_ships_device_specific_settings()
    print("All topic key verse tests passed.")
