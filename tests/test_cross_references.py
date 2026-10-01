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

from scriptures.data_access import (  # noqa: E402
    add_user_cross_reference,
    delete_user_cross_reference,
    find_chapter_for_reference,
    get_cross_references,
)
from scriptures.db import connect  # noqa: E402
from scriptures.ui.add_cross_reference_dialog import (  # noqa: E402
    parse_verse_range,
    resolve_related_passage,
)

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
    conn.execute(
        "INSERT INTO topics (id, name, slug, description, sort_order) "
        "VALUES (1, 'Zion', 'zion', 'test description', 1)"
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
            "related_verse_start, related_verse_end, relationship, topic_slugs, note, sort_order) "
            "VALUES ('book-of-mormon', '2 Nephi', 12, NULL, NULL, "
            "'holy-bible', 'Isaiah', 2, NULL, NULL, 'quotation', 'zion', 'test note', 1)"
        )
        conn.commit()

        forward = get_cross_references(conn, 2)  # 2 Nephi 12
        assert len(forward) == 1
        assert forward[0].related_reference == "Isaiah 2"
        assert forward[0].related_chapter_id == 1
        assert forward[0].verse_start is None
        assert [t.name for t in forward[0].topics] == ["Zion"]

        reverse = get_cross_references(conn, 1)  # Holy Bible Isaiah 2
        assert len(reverse) == 1
        assert reverse[0].related_reference == "2 Nephi 12"
        assert reverse[0].related_chapter_id == 2
        assert [t.name for t in reverse[0].topics] == ["Zion"]

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
            "related_verse_start, related_verse_end, relationship, topic_slugs, note, sort_order) "
            "VALUES ('book-of-mormon', '2 Nephi', 12, NULL, NULL, "
            "'holy-bible', 'Isaiah', 2, NULL, NULL, 'quotation', 'zion', 'test note', 1)"
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
            "quotation", "zion", "note",
        )
        try:
            bcr.verify_entry(conn, bad_chapter)
            raise AssertionError("expected verify_entry to reject a nonexistent chapter")
        except ValueError:
            pass

        bad_verse = (
            "2 Nephi", "The Book of Mormon", 12, 1, 999,
            "Isaiah", "Holy Bible", 2, None, None,
            "quotation", "zion", "note",
        )
        try:
            bcr.verify_entry(conn, bad_verse)
            raise AssertionError("expected verify_entry to reject an out-of-range verse")
        except ValueError:
            pass

        print("test_verify_entry_catches_bad_chapter: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_verify_entry_catches_unknown_topic_slug() -> None:
    conn, tmp_root = _make_db()
    try:
        _seed(conn)
        bad_topic = (
            "2 Nephi", "The Book of Mormon", 12, None, None,
            "Isaiah", "Holy Bible", 2, None, None,
            "quotation", "not-a-real-topic", "note",
        )
        try:
            bcr.verify_entry(conn, bad_topic)
            raise AssertionError("expected verify_entry to reject an unknown topic slug")
        except ValueError:
            pass

        # A real slug already seeded above must pass.
        bcr.verify_entry(
            conn,
            (
                "2 Nephi", "The Book of Mormon", 12, None, None,
                "Isaiah", "Holy Bible", 2, None, None,
                "quotation", "zion", "note",
            ),
        )

        print("test_verify_entry_catches_unknown_topic_slug: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_unresolvable_topic_slug_is_skipped_not_erroring() -> None:
    """A topic_slugs value naming a topic that isn't (yet) in this writable
    database's topics table - e.g. an older copy that hasn't synced in a
    newer topic - is simply left out of the resolved list, the same
    tolerance get_topic_verses already has for a stale reference, rather
    than raising or blocking the rest of the entry from showing."""
    conn, tmp_root = _make_db()
    try:
        _seed(conn)
        conn.execute(
            "INSERT INTO cross_references "
            "(volume_slug, book_name, chapter_number, verse_start, verse_end, "
            "related_volume_slug, related_book_name, related_chapter_number, "
            "related_verse_start, related_verse_end, relationship, topic_slugs, note, sort_order) "
            "VALUES ('book-of-mormon', '2 Nephi', 12, NULL, NULL, "
            "'holy-bible', 'Isaiah', 2, NULL, NULL, 'quotation', 'zion,not-synced-yet', 'test note', 1)"
        )
        conn.commit()

        results = get_cross_references(conn, 2)
        assert len(results) == 1
        assert [t.name for t in results[0].topics] == ["Zion"]

        print("test_unresolvable_topic_slug_is_skipped_not_erroring: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_user_cross_reference_shows_on_both_sides_after_curated() -> None:
    conn, tmp_root = _make_db()
    try:
        _seed(conn)
        conn.execute(
            "INSERT INTO cross_references "
            "(volume_slug, book_name, chapter_number, verse_start, verse_end, "
            "related_volume_slug, related_book_name, related_chapter_number, "
            "related_verse_start, related_verse_end, relationship, topic_slugs, note, sort_order) "
            "VALUES ('book-of-mormon', '2 Nephi', 12, NULL, NULL, "
            "'holy-bible', 'Isaiah', 2, NULL, NULL, 'quotation', '', 'curated', 1)"
        )
        conn.commit()
        # 2 Nephi 12:5 <-> Holy Bible Isaiah 2:1, a single verse each -
        # a 5-5 range is normalized to a single verse.
        add_user_cross_reference(conn, 2, 5, 5, 1, 1, None, "mine")

        nephi_side = get_cross_references(conn, 2)
        assert [cr.relationship for cr in nephi_side] == ["quotation", "user"]
        mine = nephi_side[1]
        assert (mine.verse_start, mine.verse_end) == (5, None)
        assert mine.related_reference == "Isaiah 2:1"
        assert mine.related_chapter_id == 1
        assert mine.user_id is not None
        assert nephi_side[0].user_id is None

        isaiah_side = get_cross_references(conn, 1)
        assert isaiah_side[1].related_reference == "2 Nephi 12:5"
        assert isaiah_side[1].verse_start == 1
        # The JST's same-named Isaiah 2 never picks it up.
        assert get_cross_references(conn, 3) == []

        # Re-adding the same pair updates it rather than duplicating it,
        # and also brings a removed one back.
        delete_user_cross_reference(conn, mine.user_id)
        assert [cr.relationship for cr in get_cross_references(conn, 2)] == ["quotation"]
        add_user_cross_reference(conn, 2, 5, None, 1, 1, None, "edited")
        assert conn.execute("SELECT COUNT(*) FROM user_cross_references").fetchone()[0] == 1
        assert get_cross_references(conn, 2)[1].note == "edited"

        print("test_user_cross_reference_shows_on_both_sides_after_curated: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_typed_reference_resolution() -> None:
    conn, tmp_root = _make_db()
    try:
        _seed(conn)
        # A book name shared with the JST resolves to the Holy Bible.
        assert find_chapter_for_reference(conn, "isaiah", 2) == 1
        assert resolve_related_passage(conn, "Isaiah 2:5") == (1, 5, None)
        assert resolve_related_passage(conn, "2 nephi 12:1-5") == (2, 1, 5)
        assert resolve_related_passage(conn, "2 Ne. 12") == (2, None, None)
        for bad in ("Isaiah 99", "Isaiah 2:6", "not a reference", "2 Nephi 12:5-1"):
            try:
                resolve_related_passage(conn, bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f"expected ValueError for {bad!r}")

        assert parse_verse_range("", 5) == (None, None)
        assert parse_verse_range(" 2 - 4 ", 5) == (2, 4)
        assert parse_verse_range("3-3", 5) == (3, None)
        for bad in ("0", "6", "abc", "4-2"):
            try:
                parse_verse_range(bad, 5)
            except ValueError:
                pass
            else:
                raise AssertionError(f"expected ValueError for {bad!r}")

        print("test_typed_reference_resolution: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    test_cross_reference_resolves_both_directions()
    test_reference_string_collision_does_not_leak_across_volumes()
    test_no_cross_references_is_empty_list()
    test_verify_entry_catches_bad_chapter()
    test_verify_entry_catches_unknown_topic_slug()
    test_unresolvable_topic_slug_is_skipped_not_erroring()
    test_user_cross_reference_shows_on_both_sides_after_curated()
    test_typed_reference_resolution()
    print("All cross-reference tests passed.")
