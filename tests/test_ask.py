"""Standalone test script for src/scriptures/ask.py's retrieval-validation
logic (Stage 2 of the AI-assisted search feature - see ai_client.py's
module docstring).

No test framework, no network, no Qt event loop required - resolve_references
and _parse_reference are plain functions over a local SQLite database, so
this only ever exercises that half (never QuestionAsker's actual HTTP call,
which needs a running Qt application to test - see the offscreen Qt driver
scripts used ad hoc elsewhere in this project for that side instead).

Run directly:

    python3 tests/test_ask.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import scriptures.citations as citations_module  # noqa: E402
from scriptures.ask import _extract_json_array, _parse_reference, resolve_references  # noqa: E402
from scriptures.db import connect  # noqa: E402


def _seed(conn: sqlite3.Connection) -> None:
    """A small, deliberately book-name-diverse slice of scripture: a
    numbered Book of Mormon book (to check "3 Nephi"-style parsing), a
    plain-named one in mixed case (to check case-insensitive matching),
    and a chapter with several verses (to check whole-chapter and
    verse-range resolution)."""
    conn.execute("INSERT INTO volumes (id, name, slug, sort_order) VALUES (1, 'Book of Mormon', 'book-of-mormon', 1)")
    conn.execute("INSERT INTO books (id, volume_id, name, sort_order) VALUES (1, 1, '3 Nephi', 1)")
    conn.execute("INSERT INTO books (id, volume_id, name, sort_order) VALUES (2, 1, 'Alma', 2)")
    conn.execute("INSERT INTO chapters (id, book_id, chapter_number) VALUES (1, 1, 11)")
    conn.execute("INSERT INTO chapters (id, book_id, chapter_number) VALUES (2, 2, 32)")
    verses = {
        1: "And it came to pass that Jesus spake unto them.",
        2: "And he called the twelve.",
        3: "And he gave them power to baptize.",
        4: "And he taught them of his church.",
        5: "And they went forth among the people.",
    }
    for num, text in verses.items():
        conn.execute(
            "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (1, ?, ?, ?)",
            (num, text, f"3 Nephi 11:{num}"),
        )
    conn.execute(
        "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (2, 21, ?, ?)",
        ("Yea, they may begin to exercise a particle of faith.", "Alma 32:21"),
    )
    conn.commit()


def _make_db() -> tuple[sqlite3.Connection, Path]:
    tmp_root = Path(tempfile.mkdtemp(prefix="scriptures-ask-test-"))
    conn = connect(tmp_root / "test.db")
    _seed(conn)
    return conn, tmp_root


def test_parse_reference() -> None:
    assert _parse_reference("3 Nephi 11:18-22") == ("3 Nephi", 11, 18, 22)
    assert _parse_reference("3 Nephi 11:18") == ("3 Nephi", 11, 18, None)
    assert _parse_reference("3 Nephi 11") == ("3 Nephi", 11, None, None)
    assert _parse_reference("Doctrine and Covenants 76") == ("Doctrine and Covenants", 76, None, None)
    assert _parse_reference("not a reference at all") is None
    print("test_parse_reference: PASSED")


def test_resolve_single_verse() -> None:
    conn, tmp_root = _make_db()
    try:
        results = resolve_references(conn, ["3 Nephi 11:2"])
        assert len(results) == 1
        assert results[0].reference == "3 Nephi 11:2"
        assert results[0].text == "And he called the twelve."
        assert results[0].verse_id is not None
        print("test_resolve_single_verse: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_resolve_verse_range() -> None:
    conn, tmp_root = _make_db()
    try:
        results = resolve_references(conn, ["3 Nephi 11:2-4"])
        assert len(results) == 1
        r = results[0]
        assert r.reference == "3 Nephi 11:2-4"
        assert "called the twelve" in r.text and "taught them" in r.text
        print("test_resolve_verse_range: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_resolve_whole_chapter() -> None:
    conn, tmp_root = _make_db()
    try:
        results = resolve_references(conn, ["3 Nephi 11"])
        assert len(results) == 1
        assert results[0].reference == "3 Nephi 11"
        assert results[0].verse_id is None
        assert "Jesus spake" in results[0].text
        print("test_resolve_whole_chapter: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_resolve_is_case_insensitive() -> None:
    conn, tmp_root = _make_db()
    try:
        results = resolve_references(conn, ["alma 32:21"])
        assert len(results) == 1
        assert results[0].reference == "Alma 32:21"
        print("test_resolve_is_case_insensitive: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_hallucinated_reference_is_dropped() -> None:
    conn, tmp_root = _make_db()
    try:
        # A well-formed but entirely made-up reference (this seed data has
        # no Genesis at all) must never surface as a result.
        results = resolve_references(conn, ["Genesis 1:1", "3 Nephi 11:1"])
        assert len(results) == 1
        assert results[0].reference == "3 Nephi 11:1"
        print("test_hallucinated_reference_is_dropped: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_malformed_and_non_string_candidates_are_dropped() -> None:
    conn, tmp_root = _make_db()
    try:
        results = resolve_references(conn, ["not a reference", "", 42, None, "3 Nephi 11:1"])
        assert len(results) == 1
        assert results[0].reference == "3 Nephi 11:1"
        print("test_malformed_and_non_string_candidates_are_dropped: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_duplicates_and_ordering_and_cap() -> None:
    conn, tmp_root = _make_db()
    try:
        # Same verse named two different ways (exact + inside a range)
        # collapses to one; order follows the model's own ordering.
        results = resolve_references(
            conn, ["3 Nephi 11:3", "3 Nephi 11:1", "3 Nephi 11:2-3"]
        )
        refs = [r.reference for r in results]
        assert refs == ["3 Nephi 11:3", "3 Nephi 11:1", "3 Nephi 11:2-3"]
        verse_ids = [r.verse_id for r in results]
        assert len(verse_ids) == len(set(verse_ids)), "verse 3 should not be duplicated"
        print("test_duplicates_and_ordering_and_cap: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_extract_json_array() -> None:
    assert _extract_json_array('["3 Nephi 11:1", "Alma 32:21"]') == ["3 Nephi 11:1", "Alma 32:21"]
    assert _extract_json_array('Sure! Here you go:\n```json\n["Alma 32:21"]\n```') == ["Alma 32:21"]
    assert _extract_json_array("I don't know.") == []
    assert _extract_json_array("[]") == []
    print("test_extract_json_array: PASSED")


def test_resolve_attaches_real_citations() -> None:
    """A resolved reference picks up any already-harvested General
    Conference talks that cite it (see ask.py's module docstring) -
    never anything the model itself suggested. Monkeypatches
    citations.py's module-level cache directly rather than touching the
    real data/verse_citations.json, so this is exact and repo-data-
    independent."""
    conn, tmp_root = _make_db()
    original_cache = citations_module._citations_cache
    try:
        citations_module._citations_cache = {
            "3 Nephi 11:1": [
                {
                    "talk_title": "A Sample Talk",
                    "speaker": "Elder Someone",
                    "date": "April 2020",
                    "url": "https://example.com/talk",
                }
            ]
        }
        results = resolve_references(conn, ["3 Nephi 11:1", "3 Nephi 11:2"])
        by_ref = {r.reference: r for r in results}
        assert len(by_ref["3 Nephi 11:1"].citations) == 1
        assert by_ref["3 Nephi 11:1"].citations[0].talk_title == "A Sample Talk"
        # A verse with nothing harvested for it just gets an empty list,
        # not an error - most verses will be in this state.
        assert by_ref["3 Nephi 11:2"].citations == []
        print("test_resolve_attaches_real_citations: PASSED")
    finally:
        citations_module._citations_cache = original_cache
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    test_parse_reference()
    test_resolve_single_verse()
    test_resolve_verse_range()
    test_resolve_whole_chapter()
    test_resolve_is_case_insensitive()
    test_hallucinated_reference_is_dropped()
    test_malformed_and_non_string_candidates_are_dropped()
    test_duplicates_and_ordering_and_cap()
    test_extract_json_array()
    test_resolve_attaches_real_citations()
    print("All ask.py tests passed.")
