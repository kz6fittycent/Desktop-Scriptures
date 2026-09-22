"""Standalone test script for src/scriptures/church_news.py's RSS-parsing
logic. No test framework, no network, no Qt event loop required -
_parse_latest_headline and _format_byline are plain functions over raw
XML bytes (see tests/test_ask.py's own docstring for why this project
tests pure logic this way rather than with a framework).

Run directly:

    python3 tests/test_church_news.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.church_news import _format_byline, _parse_latest_headline  # noqa: E402

SAMPLE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel>
<title>Church News - Latest Articles</title>
<item>
<title><![CDATA[Newest headline of the day]]></title>
<link>https://www.thechurchnews.com/first-article</link>
<dc:creator><![CDATA[Jane Reporter]]></dc:creator>
<pubDate>Tue, 22 Sep 2026 10:00:00 +0000</pubDate>
</item>
<item>
<title><![CDATA[An older headline]]></title>
<link>https://www.thechurchnews.com/second-article</link>
<dc:creator><![CDATA[John Writer]]></dc:creator>
<pubDate>Mon, 21 Sep 2026 09:00:00 +0000</pubDate>
</item>
</channel>
</rss>
"""

EMPTY_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Church News</title></channel></rss>
"""


def test_parse_latest_headline_takes_the_first_item() -> None:
    headline = _parse_latest_headline(SAMPLE_FEED)
    assert headline is not None
    assert headline.title == "Newest headline of the day"
    assert headline.link == "https://www.thechurchnews.com/first-article"
    assert headline.byline == "Jane Reporter · September 22, 2026"
    print("test_parse_latest_headline_takes_the_first_item: PASSED")


def test_parse_latest_headline_handles_empty_feed() -> None:
    assert _parse_latest_headline(EMPTY_FEED) is None
    print("test_parse_latest_headline_handles_empty_feed: PASSED")


def test_parse_latest_headline_handles_garbage() -> None:
    assert _parse_latest_headline(b"not xml at all") is None
    print("test_parse_latest_headline_handles_garbage: PASSED")


def test_parse_latest_headline_requires_title_and_link() -> None:
    feed = b"""<rss><channel><item><title>Only a title</title></item></channel></rss>"""
    assert _parse_latest_headline(feed) is None
    print("test_parse_latest_headline_requires_title_and_link: PASSED")


def test_format_byline_omits_missing_parts() -> None:
    assert _format_byline("", "") == ""
    assert _format_byline("Jane Reporter", "") == "Jane Reporter"
    assert _format_byline("", "Tue, 22 Sep 2026 10:00:00 +0000") == "September 22, 2026"
    # An unparseable date shouldn't blow up the whole byline - it's just left out.
    assert _format_byline("Jane Reporter", "not a real date") == "Jane Reporter"
    print("test_format_byline_omits_missing_parts: PASSED")


if __name__ == "__main__":
    test_parse_latest_headline_takes_the_first_item()
    test_parse_latest_headline_handles_empty_feed()
    test_parse_latest_headline_handles_garbage()
    test_parse_latest_headline_requires_title_and_link()
    test_format_byline_omits_missing_parts()
    print("All church_news.py tests passed.")
