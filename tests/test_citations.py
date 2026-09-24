"""Standalone test script for src/scriptures/citations.py's merging of
General Conference and Liahona citations into one newest-first list per
verse. No test framework, no network, no Qt event loop (see
tests/test_ask.py's own docstring for why this project tests pure logic
this way rather than with a framework) - monkeypatches the module's two
caches directly rather than touching real data files, matching
test_ask.py's own test_resolve_attaches_real_citations.

Run directly:

    python3 tests/test_citations.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import scriptures.citations as citations_module  # noqa: E402
from scriptures.citations import (  # noqa: E402
    ENSIGN_LABEL,
    GENERAL_CONFERENCE_LABEL,
    LIAHONA_LABEL,
    get_citations,
)


def _with_caches(gc: dict, liahona: dict):
    citations_module._gc_cache = gc
    citations_module._liahona_cache = liahona


def test_merges_both_sources_and_labels_each() -> None:
    _with_caches(
        gc={
            "Alma 32:21": [
                {
                    "talk_title": "A GC Talk",
                    "speaker": "Elder Someone",
                    "date": "October 2024",
                    "url": "https://example.com/gc",
                }
            ]
        },
        liahona={
            "Alma 32:21": [
                {
                    "talk_title": "A Liahona Article",
                    "speaker": "Jane Author",
                    "date": "June 2024",
                    "url": "https://example.com/liahona",
                }
            ]
        },
    )
    results = get_citations("Alma 32:21")
    assert len(results) == 2
    labels = {c.source_label for c in results}
    assert labels == {GENERAL_CONFERENCE_LABEL, LIAHONA_LABEL}
    print("test_merges_both_sources_and_labels_each: PASSED")


def test_sorted_newest_first_across_sources() -> None:
    _with_caches(
        gc={
            "John 3:16": [
                {"talk_title": "Older GC", "speaker": "A", "date": "April 2020", "url": "u1"},
                {"talk_title": "Newest overall", "speaker": "B", "date": "October 2025", "url": "u2"},
            ]
        },
        liahona={
            "John 3:16": [
                {"talk_title": "Middle Liahona", "speaker": "C", "date": "June 2023", "url": "u3"},
            ]
        },
    )
    results = get_citations("John 3:16")
    assert [c.talk_title for c in results] == ["Newest overall", "Middle Liahona", "Older GC"]
    print("test_sorted_newest_first_across_sources: PASSED")


def test_ensign_era_articles_labeled_ensign_not_liahona() -> None:
    # The magazine label is derived from each entry's own date, not a
    # single fixed constant - a pre-2021 (Ensign-era) article must be
    # labeled "Ensign", a 2021+ one "Liahona", even from the same file.
    _with_caches(
        gc={},
        liahona={
            "Moroni 10:4": [
                {"talk_title": "An Old Ensign Article", "speaker": "A", "date": "April 1985", "url": "u1"},
                {"talk_title": "A New Liahona Article", "speaker": "B", "date": "April 2022", "url": "u2"},
            ]
        },
    )
    results = {c.talk_title: c.source_label for c in get_citations("Moroni 10:4")}
    assert results["An Old Ensign Article"] == ENSIGN_LABEL
    assert results["A New Liahona Article"] == LIAHONA_LABEL
    print("test_ensign_era_articles_labeled_ensign_not_liahona: PASSED")


def test_unknown_verse_returns_empty_list() -> None:
    _with_caches(gc={}, liahona={})
    assert get_citations("Genesis 1:1") == []
    print("test_unknown_verse_returns_empty_list: PASSED")


def test_unparseable_date_sorts_first_not_last() -> None:
    _with_caches(
        gc={
            "Moroni 10:4": [
                {"talk_title": "Has a date", "speaker": "A", "date": "April 2024", "url": "u1"},
                {"talk_title": "No date at all", "speaker": "B", "date": "", "url": "u2"},
            ]
        },
        liahona={},
    )
    results = get_citations("Moroni 10:4")
    assert results[-1].talk_title == "No date at all"
    print("test_unparseable_date_sorts_first_not_last: PASSED")


if __name__ == "__main__":
    test_merges_both_sources_and_labels_each()
    test_sorted_newest_first_across_sources()
    test_ensign_era_articles_labeled_ensign_not_liahona()
    test_unknown_verse_returns_empty_list()
    test_unparseable_date_sorts_first_not_last()
    print("All citations.py tests passed.")
