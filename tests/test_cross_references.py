"""Standalone test script for src/scriptures/data_access.py's
get_cross_references, and scripts/build_cross_references.py's own
verify_entry safety check. No test framework, no Qt event loop (see
tests/test_ask.py's own docstring for why this project tests pure logic
this way rather than with a framework).

Run directly:

    python3 tests/test_cross_references.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from scriptures.data_access import get_cross_references  # noqa: E402
from scriptures.db import connect  # noqa: E402

import build_cross_references as bcr  # noqa: E402


def _make_db() -> tuple:
    tmp_root = Path(tempfile.mkdtemp(prefix="scriptures-cross-references-test-"))
    conn = connect(tmp_root / "test.db")
    return conn, tmp_root


def _seed(conn) -> None:
    """Two volumes with just enough books/chapters/verses to exercise a
    cross-chapter, cross-volume link - plus a second, same-named "Isaiah"
    book in a third volume, standing in for the real JST/KJV reference
    collision, to prove volume disambiguation actually matters here."""
    conn.execute("INSERT INTO volumes (id, name, slug, sort_order) VALUES (1, 'Holy Bible', 'holy-bible', 1)")
    conn.execute(
        "INSERT INTO volumes (id, name, slug, sort_order) VALUES (2, 'The Book of Mormon', 'book-of-mormon', 2)"
    )
    conn.execute(
        "INSERT INTO volumes (id, name, slug, sort_order) "
        "VALUES (3, 'Joseph Smith Translation', 'joseph-smith-translation', 3)"
    )

    conn.execute("INSERT INTO books (id, volume_id, name, sort_order) VALUES (1, 1, 'Isaiah', 1)")
    conn.execute("INSERT INTO books (id, volume_id, name, sort_order) VALUES (2, 2, '2 Nephi', 1)")
    conn.execute("INSERT INTO books (id, volume_id, name, sort_order) VALUES (3, 3, 'Isaiah', 1)")

    conn.execute("INSERT INTO chapters (id, book_id, chapter_number) VALUES (1, 1, 2)")  # Holy Bible Isaiah 2
    conn.execute("INSERT INTO chapters (id, book_id, chapter_number) VALUES (2, 2, 12)")  # 2 Nephi 12
    conn.execute("INSERT INTO chapters (id, book_id, chapter_number) VALUES (3, 3, 2)")  # JST Isaiah 2 (collides!)

    for chapter_id, verse_number in ((1, 1), (1, 5), (2, 1), (2, 5), (3, 5)):
        conn.execute(
            "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (?, ?, 'x', 'Isaiah 2:5')",
            (chapter_id, verse_number),
        )
    conn.commit()


def test_cross_reference_resolves_both_directions() -> None:
    conn, tmp_root = _make_db()
    try:
        _seed(conn)
        conn.execute(
            "INSERT INTO cross_references "
            "(volume_slug, book_name, chapter_number, verse_start, verse_end, "
            "related_volume_slug, related_book_name, related_chapter_number, "
            "related_verse_start, related_verse_end, relationship, note, sort_order) "
            "VALUES ('book-of-mormon', '2 Nephi', 12, NULL, NULL, "
            "'holy-bible', 'Isaiah', 2, NULL, NULL, 'quotation', 'test note', 1)"
        )
        conn.commit()

        forward = get_cross_references(conn, 2)  # 2 Nephi 12
        assert len(forward) == 1
        assert forward[0].related_reference == "Isaiah 2"
        assert forward[0].related_chapter_id == 1
        assert forward[0].verse_start is None

        reverse = get_cross_references(conn, 1)  # Holy Bible Isaiah 2
        assert len(reverse) == 1
        assert reverse[0].related_reference == "2 Nephi 12"
        assert reverse[0].related_chapter_id == 2

        print("test_cross_reference_resolves_both_directions: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_reference_string_collision_does_not_leak_across_volumes() -> None:
    """The JST's own "Isaiah" reuses the KJV's chapter/verse numbers, so a
    naive lookup by bare reference string ("Isaiah 2:5") would match both
    the Holy Bible chapter and the unrelated JST chapter. A cross-reference
    to the Holy Bible's Isaiah 2 must resolve to that chapter's id (1),
    never the JST one (3), even though both chapters contain a verse whose
    `reference` column reads "Isaiah 2:5"."""
    conn, tmp_root = _make_db()
    try:
        _seed(conn)
        conn.execute(
            "INSERT INTO cross_references "
            "(volume_slug, book_name, chapter_number, verse_start, verse_end, "
            "related_volume_slug, related_book_name, related_chapter_number, "
            "related_verse_start, related_verse_end, relationship, note, sort_order) "
            "VALUES ('book-of-mormon', '2 Nephi', 12, NULL, NULL, "
            "'holy-bible', 'Isaiah', 2, NULL, NULL, 'quotation', 'test note', 1)"
        )
        conn.commit()

        results = get_cross_references(conn, 2)
        assert len(results) == 1
        assert results[0].related_chapter_id == 1, "must resolve to the Holy Bible chapter, not the JST one"

        print("test_reference_string_collision_does_not_leak_across_volumes: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_no_cross_references_is_empty_list() -> None:
    conn, tmp_root = _make_db()
    try:
        _seed(conn)
        assert get_cross_references(conn, 1) == []
        print("test_no_cross_references_is_empty_list: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_verify_entry_catches_bad_chapter() -> None:
    conn, tmp_root = _make_db()
    try:
        _seed(conn)
        bad_chapter = (
            "2 Nephi", "The Book of Mormon", 999, None, None,
            "Isaiah", "Holy Bible", 2, None, None,
            "quotation", "note",
        )
        try:
            bcr.verify_entry(conn, bad_chapter)
            raise AssertionError("expected verify_entry to reject a nonexistent chapter")
        except ValueError:
            pass

        bad_verse = (
            "2 Nephi", "The Book of Mormon", 12, 1, 999,
            "Isaiah", "Holy Bible", 2, None, None,
            "quotation", "note",
        )
        try:
            bcr.verify_entry(conn, bad_verse)
            raise AssertionError("expected verify_entry to reject an out-of-range verse")
        except ValueError:
            pass

        print("test_verify_entry_catches_bad_chapter: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    test_cross_reference_resolves_both_directions()
    test_reference_string_collision_does_not_leak_across_volumes()
    test_no_cross_references_is_empty_list()
    test_verify_entry_catches_bad_chapter()
    print("All cross-reference tests passed.")
