"""Standalone test script for corrected scripture text reaching existing
installs (db.sync_bundled_content / _update_verse_text) - e.g. the JST's
OCR cleanup (scripts/clean_inspired_version_text.py) - with highlights
moving to stay on the same words. No test framework (see
tests/test_ask.py's docstring); copies of the shipped data/scriptures.db.

Run directly:

    python3 tests/test_bundled_text_updates.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import connect, remap_offset, sync_bundled_content  # noqa: E402


def test_remap_offset() -> None:
    old = "unto the chil dren of Israel ; and they"
    new = "unto the children of Israel; and they"
    start = old.index("Israel")
    assert new[remap_offset(old, new, start):].startswith("Israel")
    end = start + len("Israel")
    assert new[remap_offset(old, new, start):remap_offset(old, new, end, is_end=True)] == "Israel"
    assert remap_offset(old, new, len(old), is_end=True) == len(new)
    print("test_remap_offset: PASSED")


def test_corrected_text_reaches_an_existing_install() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-text-updates-"))
    try:
        shutil.copy(PROJECT_ROOT / "data" / "scriptures.db", tmp / "bundled.db")
        shutil.copy(PROJECT_ROOT / "data" / "scriptures.db", tmp / "user.db")
        conn = connect(tmp / "user.db")
        verse_id, corrected = conn.execute(
            "SELECT v.id, v.text FROM verses v WHERE v.reference = 'Numbers 16:40' AND v.chapter_id IN "
            "(SELECT c.id FROM chapters c JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id "
            "WHERE vol.slug = 'inspired-version')"
        ).fetchone()
        assert "children of Israel" in corrected
        # This install still has the old, OCR-damaged text, with a highlight
        # on "Israel" and one on "Aaron".
        damaged = corrected.replace("children", "chil dren").replace("Lord;", "Lord ;")
        conn.execute("UPDATE verses SET text = ? WHERE id = ?", (damaged, verse_id))
        chapter_id, title = conn.execute(
            "SELECT c.id, c.title FROM chapters c JOIN verses v ON v.chapter_id = c.id WHERE v.id = ?", (verse_id,)
        ).fetchone()
        conn.execute("UPDATE chapters SET title = ? WHERE id = ?", ("T/ie " + (title or ""), chapter_id))
        for word in ("Israel", "Aaron"):
            start = damaged.index(word)
            conn.execute(
                "INSERT INTO highlights (verse_id, color, start_offset, end_offset) VALUES (?, 'yellow', ?, ?)",
                (verse_id, start, start + len(word)),
            )
        conn.commit()

        sync_bundled_content(conn, tmp / "bundled.db")

        assert conn.execute("SELECT text FROM verses WHERE id = ?", (verse_id,)).fetchone()[0] == corrected
        assert conn.execute("SELECT title FROM chapters WHERE id = ?", (chapter_id,)).fetchone()[0] == title
        covered = [
            corrected[s:e] for s, e in conn.execute(
                "SELECT start_offset, end_offset FROM highlights WHERE verse_id = ? AND deleted_at IS NULL "
                "ORDER BY start_offset", (verse_id,)
            )
        ]
        assert covered == ["Israel", "Aaron"], covered
        # Keyword search sees the corrected word.
        assert conn.execute(
            "SELECT count(*) FROM verses_fts WHERE verses_fts MATCH 'children' AND rowid = ?", (verse_id,)
        ).fetchone()[0] == 1
        print("test_corrected_text_reaches_an_existing_install: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_renumbered_verses_keep_the_readers_notes() -> None:
    """An install with the old JST numbering (each verse one number off,
    as in 1 Chronicles before the re-import, plus a verse past the end):
    after an update, a note and highlight follow the text they were made
    on, the stale extra verse goes, and a stale Topical Guide entry too."""
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-renumbered-"))
    try:
        shutil.copy(PROJECT_ROOT / "data" / "scriptures.db", tmp / "bundled.db")
        shutil.copy(PROJECT_ROOT / "data" / "scriptures.db", tmp / "user.db")
        conn = connect(tmp / "user.db")
        chapter_id = conn.execute(
            "SELECT c.id FROM chapters c JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id "
            "WHERE vol.slug = 'inspired-version' AND b.name = 'Ruth' AND c.chapter_number = 1"
        ).fetchone()[0]
        verses = conn.execute(
            "SELECT id, verse_number, text FROM verses WHERE chapter_id = ? ORDER BY verse_number", (chapter_id,)
        ).fetchall()
        texts = [v["text"] for v in verses]
        # Old numbering: verse n held verse n+1's text, and one extra verse.
        for v, text in zip(verses, texts[1:] + ["(an extra verse the old import made)"]):
            conn.execute("UPDATE verses SET text = ? WHERE id = ?", (text, v["id"]))
        conn.execute(
            "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (?, ?, ?, ?)",
            (chapter_id, len(verses) + 1, "stale", f"Ruth 1:{len(verses) + 1}"),
        )
        # The reader's note and highlight on old verse 3 (the text of verse 4).
        old3 = verses[2]["id"]
        word = texts[3].split()[2]
        start = texts[3].index(word)
        conn.execute("INSERT INTO notes (verse_id, text) VALUES (?, 'my note')", (old3,))
        conn.execute(
            "INSERT INTO highlights (verse_id, color, start_offset, end_offset) VALUES (?, 'pink', ?, ?)",
            (old3, start, start + len(word)),
        )
        topic_id = conn.execute("SELECT id FROM topics LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO topic_verses (topic_id, volume_slug, reference, sort_order) "
            "VALUES (?, 'inspired-version', 'Ruth 1:99', 999)", (topic_id,)
        )
        conn.commit()

        sync_bundled_content(conn, tmp / "bundled.db")

        note_verse = conn.execute("SELECT verse_id FROM notes WHERE text = 'my note'").fetchone()[0]
        assert note_verse == verses[3]["id"], "the note should follow its text to verse 4"
        h = conn.execute("SELECT verse_id, start_offset, end_offset FROM highlights").fetchone()
        assert h["verse_id"] == verses[3]["id"] and texts[3][h["start_offset"]:h["end_offset"]] == word
        assert [r[0] for r in conn.execute(
            "SELECT text FROM verses WHERE chapter_id = ? ORDER BY verse_number", (chapter_id,)
        )] == texts, "every verse back to its bundled text, the extra one gone"
        assert not conn.execute("SELECT 1 FROM topic_verses WHERE reference = 'Ruth 1:99'").fetchone()
        print("test_renumbered_verses_keep_the_readers_notes: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_remap_offset()
    test_corrected_text_reaches_an_existing_install()
    test_renumbered_verses_keep_the_readers_notes()
    print("All bundled text update tests passed.")
