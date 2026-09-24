"""Standalone test script for scripts/harvest_liahona_citations.py's pure
parsing logic - month_range() and parse_article() - against a fixture
built from real page structure (verified live against
churchofjesuschrist.org while building this harvester, see the module's
own docstring). No test framework, no network, no Qt event loop (see
tests/test_ask.py's own docstring for why this project tests pure logic
this way rather than with a framework); resolve_book_name() itself is
excluded since it always makes a real network request - the two real
book-name quirks it has to handle (a non-breaking space between a
numbered book's digit and name, and the Church's own em dash in
"Joseph Smith--History") are exercised here instead via parse_article()
receiving pre-resolved book names directly, matching what
resolve_book_name() would have already normalized by the time
parse_article() uses it.

Run directly:

    python3 tests/test_liahona_citations.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from harvest_liahona_citations import (  # noqa: E402
    _normalize_book_name,
    issue_url_prefix,
    month_range,
    parse_article,
)

# Trimmed but structurally real fragment: og:title meta tag, the
# JSON-LD-ish author blob, and a handful of /study/scriptures/ links -
# including a verse range (id=p22-p24) and a same-chapter repeat, both
# seen in real articles.
SAMPLE_HTML = """
<meta data-react-helmet="true" property="og:title" content="Jesus Christ Is Our Savior"/>
<script>window.__DATA__ = {"author":{"@type":"Person","name":"Russell M. Nelson","url":"/x"}};</script>
<a href="/study/scriptures/nt/matt/28?lang=eng&amp;id=p18#p18">Matthew 28:18</a>
<a href="/study/scriptures/bofm/mosiah/16?lang=eng&amp;id=p10#p10">Mosiah 16:10</a>
<a href="/study/scriptures/dc-testament/dc/76?lang=eng&amp;id=p22-p24#p22">D&amp;C 76:22-24</a>
<a href="/study/scriptures/nt/matt/28?lang=eng&amp;id=p18#p18">duplicate, same verse</a>
"""


def test_month_range_spans_year_boundary() -> None:
    result = list(month_range(2021, 11, 2022, 2))
    assert result == [(2021, 11), (2021, 12), (2022, 1), (2022, 2)], result
    print("test_month_range_spans_year_boundary: PASSED")


def test_month_range_single_month() -> None:
    assert list(month_range(2024, 6, 2024, 6)) == [(2024, 6)]
    print("test_month_range_single_month: PASSED")


def test_normalize_book_name_plain_case() -> None:
    assert _normalize_book_name("Matthew 28") == "Matthew"
    print("test_normalize_book_name_plain_case: PASSED")


def test_normalize_book_name_strips_nonbreaking_space() -> None:
    # The literal non-breaking space the Church's own <title> uses
    # between a numbered book's digit and name.
    assert _normalize_book_name("2\xa0Nephi 9") == "2 Nephi"
    print("test_normalize_book_name_strips_nonbreaking_space: PASSED")


def test_normalize_book_name_converts_em_dash() -> None:
    assert _normalize_book_name("Joseph Smith—History 1") == "Joseph Smith--History"
    print("test_normalize_book_name_converts_em_dash: PASSED")


def test_normalize_book_name_applies_psalm_alias() -> None:
    assert _normalize_book_name("Psalm 146") == "Psalms"
    print("test_normalize_book_name_applies_psalm_alias: PASSED")


def test_issue_url_prefix_switches_exactly_at_january_2021() -> None:
    assert issue_url_prefix(2020, 12) == "ensign"
    assert issue_url_prefix(2021, 1) == "liahona"
    assert issue_url_prefix(1971, 1) == "ensign"
    assert issue_url_prefix(2026, 6) == "liahona"
    print("test_issue_url_prefix_switches_exactly_at_january_2021: PASSED")


def _fake_resolve_book_name(volume_slug, book_slug, chapter):
    return {
        ("nt", "matt"): "Matthew",
        ("bofm", "mosiah"): "Mosiah",
        ("dc-testament", "dc"): "Doctrine and Covenants",
    }[(volume_slug, book_slug)]


def test_parse_article_extracts_metadata_and_expands_verse_ranges() -> None:
    with patch("harvest_liahona_citations.resolve_book_name", side_effect=_fake_resolve_book_name):
        result = parse_article(SAMPLE_HTML, "https://example.com/article", 2023, 4)
    assert result is not None
    citation, references = result
    assert citation["talk_title"] == "Jesus Christ Is Our Savior"
    assert citation["speaker"] == "Russell M. Nelson"
    assert citation["date"] == "April 2023"  # from the known issue month, not article metadata
    assert citation["url"] == "https://example.com/article"
    assert references == {
        "Matthew 28:18",
        "Mosiah 16:10",
        "Doctrine and Covenants 76:22",
        "Doctrine and Covenants 76:23",
        "Doctrine and Covenants 76:24",
    }
    print("test_parse_article_extracts_metadata_and_expands_verse_ranges: PASSED")


def test_parse_article_returns_none_without_a_title() -> None:
    assert parse_article("<html>no title here</html>", "url", 2023, 4) is None
    print("test_parse_article_returns_none_without_a_title: PASSED")


def test_parse_article_handles_missing_author() -> None:
    html = '<meta property="og:title" content="Anonymous Article"/>'
    result = parse_article(html, "url", 2023, 4)
    assert result is not None
    citation, references = result
    assert citation["speaker"] == ""
    assert references == set()
    print("test_parse_article_handles_missing_author: PASSED")


if __name__ == "__main__":
    test_month_range_spans_year_boundary()
    test_month_range_single_month()
    test_normalize_book_name_plain_case()
    test_normalize_book_name_strips_nonbreaking_space()
    test_normalize_book_name_converts_em_dash()
    test_normalize_book_name_applies_psalm_alias()
    test_issue_url_prefix_switches_exactly_at_january_2021()
    test_parse_article_extracts_metadata_and_expands_verse_ranges()
    test_parse_article_returns_none_without_a_title()
    test_parse_article_handles_missing_author()
    print("All harvest_liahona_citations.py tests passed.")
