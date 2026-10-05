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
        for word in ("Israel", "Aaron"):
            start = damaged.index(word)
            conn.execute(
                "INSERT INTO highlights (verse_id, color, start_offset, end_offset) VALUES (?, 'yellow', ?, ?)",
                (verse_id, start, start + len(word)),
            )
        conn.commit()

        sync_bundled_content(conn, tmp / "bundled.db")

        assert conn.execute("SELECT text FROM verses WHERE id = ?", (verse_id,)).fetchone()[0] == corrected
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


if __name__ == "__main__":
    test_remap_offset()
    test_corrected_text_reaches_an_existing_install()
    print("All bundled text update tests passed.")
