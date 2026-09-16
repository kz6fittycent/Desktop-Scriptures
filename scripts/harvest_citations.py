#!/usr/bin/env python3
"""One-time harvest of General Conference citation metadata for the
Scripture of the Day pool (data/scripture_of_the_day_pool.json), from
scriptures.byu.edu's public "Scripture Citation Index".

Usage:
    python3 scripts/harvest_citations.py [output_path]

    output_path defaults to data/verse_citations.json.

COPYRIGHT: General Conference talks are copyrighted by Intellectual
Reserve, Inc. This script only ever extracts and stores METADATA - talk
title, speaker, date, and the talk's URL on churchofjesuschrist.org.
Talk text is never requested, parsed, or written anywhere. The app links
out to the official page; it never renders Church content itself.

SCOPE: pilot only, the 100 verses in the Scripture of the Day pool - not
the full ~41,995-verse database. Like import_scriptures.py, this is a
developer-run, one-time (or occasionally re-run) tool; the shipped app
never calls scriptures.byu.edu itself, only reads the local JSON this
script produces.

Rate limiting: one request per individual verse, 1.5s apart, sequential -
never parallel. Pool entries that cover a passage (e.g. "end_verse": 20)
are expanded to their individual verses rather than queried as one range,
since BYU's index only matches citations to that *exact* span otherwise
(see the comment in harvest() for why) - about 144 requests total for the
100-entry pool, run once. robots.txt at scriptures.byu.edu does not exist
(404, i.e. no crawl restrictions declared).
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from html import unescape
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

POOL_PATH = PROJECT_ROOT / "data" / "scripture_of_the_day_pool.json"
VOLUMES_PATH = PROJECT_ROOT / "data" / "volumes.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "verse_citations.json"

# Same alias the importer and sotd.py apply - the pool file uses "D&C" but
# the database (and this script's book-id map) use the canonical name.
BOOK_NAME_ALIASES = {"D&C": "Doctrine and Covenants"}

GENERAL_CONFERENCE_CORPUS = "G"  # site's own corpus code (see decodeFilter in its base.js)
BASE_URL = (
    "https://scriptures.byu.edu/citation_index/citation_ajax/"
    "Any/1830/{year}/" + GENERAL_CONFERENCE_CORPUS + "/s/f/{book}/{chapter}?verses={verses}"
)
REQUEST_DELAY_SECONDS = 1.5
USER_AGENT = (
    "Desktop-Scriptures/1.0 (+https://github.com/kz6fittycent/Desktop-Scriptures; "
    "one-time pilot harvest of citation metadata, ~144 requests total)"
)

# scriptures.byu.edu's own numeric book ids, discovered by requesting a
# volume/testament id (e.g. book=1) and reading the resulting book list -
# see the PR/session notes for the raw discovery. Old Testament, New
# Testament, and Book of Mormon are contiguous ranges in canonical book
# order, matching data/volumes.json exactly; D&C and Pearl of Great Price
# are irregular (Facsimiles has no id gap kept, Official Declarations
# share a book id with D&C sections under different "chapters"), so those
# are listed explicitly rather than derived.
_OT_FIRST_ID = 101
_NT_FIRST_ID = 140
_BOM_FIRST_ID = 205
_IRREGULAR_BOOK_IDS = {
    "Doctrine and Covenants": 302,
    "Official Declaration 1": (303, 1),  # (book id, fixed chapter)
    "Official Declaration 2": (303, 2),
    "Moses": 401,
    "Abraham": 402,
    "Joseph Smith--Matthew": 404,
    "Joseph Smith--History": 405,
    "Articles of Faith": 406,
}

MONTH_NAMES = {4: "April", 10: "October"}

REFERENCES_BLOCK_RE = re.compile(
    r'<ul class="referencesblock">(?P<body>.*?)</ul>', re.DOTALL
)
# Applied per-<li> (see parse_citations) rather than as one regex scanning
# the whole references block - three chained ".*?" groups over a block
# with hundreds of repeated near-identical entries triggers catastrophic
# backtracking in Python's re engine on a verse with many citations (e.g.
# Moses 1:39 has 380+); splitting on "<li>" first keeps each match against
# a single short fragment instead.
META_RE = re.compile(r'<div class="reference[^"]*">(?P<meta>.*?)</div>', re.DOTALL)
TITLE_RE = re.compile(r'<div class="talktitle[^"]*">(?P<title>.*?)</div>', re.DOTALL)
# Older talks link to lds.org (pre-2020 rebrand) rather than
# churchofjesuschrist.org - both are official Church domains and
# lds.org redirects to churchofjesuschrist.org, but the raw link is
# normalized to the current domain in parse_citations either way.
_TALK_LINK_RE = r"Talk\('[^']*',\s*'(?P<url>https?://www\.(?:churchofjesuschrist|lds)\.org/[^']*)'\)"
WATCH_URL_RE = re.compile("watch" + _TALK_LINK_RE)
LISTEN_URL_RE = re.compile("listen" + _TALK_LINK_RE)
TAG_RE = re.compile(r"<[^>]+>")


def _clean(html_fragment: str) -> str:
    return unescape(TAG_RE.sub("", html_fragment)).strip()


def _normalize_talk_url(raw_url: str) -> str:
    # Some older entries double-escape "&" (e.g. "&amp;amp;media=video"); a
    # second unescape() pass is a no-op once it's actually clean, so it's
    # safe to always apply. Trailing "&..." / "#..." are BYU's own
    # watch/listen UI params, not part of the talk's canonical URL.
    url = unescape(unescape(raw_url)).split("#", 1)[0].split("&", 1)[0]
    # Older entries link to http:// and/or lds.org (pre-2020 rebrand, and
    # pre-HTTPS); both still redirect to the current URL, but rewriting
    # once here up front means every stored link is already final -
    # verified against live redirect chains during harvesting.
    url = re.sub(r"^https?://www\.lds\.org/", "https://www.churchofjesuschrist.org/", url)
    url = re.sub(
        r"^http://www\.churchofjesuschrist\.org/", "https://www.churchofjesuschrist.org/", url
    )
    if url.startswith("https://www.churchofjesuschrist.org/") and "/study/" not in url:
        url = url.replace(
            "https://www.churchofjesuschrist.org/",
            "https://www.churchofjesuschrist.org/study/",
            1,
        )
    return url


def build_book_id_map() -> dict[str, int]:
    """Book name (matching data/volumes.json / the DB) -> BYU's numeric
    book id. Skips Facsimiles (no canonical equivalent) and both Official
    Declarations (id, fixed-chapter pairs, not usable as a plain book id)
    - callers needing those look them up via _IRREGULAR_BOOK_IDS directly.
    """
    volumes = json.loads(VOLUMES_PATH.read_text(encoding="utf-8"))["volumes"]

    def books_of(volume_name: str, testament_name: str | None = None) -> list[str]:
        vol = next(v for v in volumes if v["name"] == volume_name)
        if testament_name is None:
            return vol["books"]
        return next(t for t in vol["testaments"] if t["name"] == testament_name)["books"]

    book_ids: dict[str, int] = {}
    for i, name in enumerate(books_of("Holy Bible", "Old Testament")):
        book_ids[name] = _OT_FIRST_ID + i
    for i, name in enumerate(books_of("Holy Bible", "New Testament")):
        book_ids[name] = _NT_FIRST_ID + i
    for i, name in enumerate(books_of("The Book of Mormon")):
        book_ids[name] = _BOM_FIRST_ID + i
    for name, value in _IRREGULAR_BOOK_IDS.items():
        if isinstance(value, int):
            book_ids[name] = value
    return book_ids


def fetch_citation_html(book_id: int, chapter: int, verses: str) -> str:
    url = BASE_URL.format(year=date.today().year, book=book_id, chapter=chapter, verses=verses)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_citations(html: str) -> list[dict]:
    """Extract only title/speaker/date/url per citing talk - never talk
    text, which this HTML doesn't even contain (it's an index, not the
    talks themselves)."""
    block_match = REFERENCES_BLOCK_RE.search(html)
    if not block_match:
        return []

    citations = []
    for li in block_match.group("body").split("<li>")[1:]:
        meta_match = META_RE.search(li)
        title_match = TITLE_RE.search(li)
        url_match = WATCH_URL_RE.search(li) or LISTEN_URL_RE.search(li)
        if not (meta_match and title_match and url_match):
            continue  # no watch/listen link (e.g. an undigitized older talk) - skip, don't guess a URL

        meta = _clean(meta_match.group("meta"))  # e.g. "2025-O:113, Dale G. Renlund"
        title = _clean(title_match.group("title"))
        url = _normalize_talk_url(url_match.group("url"))

        _, _, speaker = meta.partition(",")
        speaker = speaker.strip()

        date_match = re.search(r"/general-conference/(\d{4})/(\d{2})/", url)
        if date_match:
            year, month = int(date_match.group(1)), int(date_match.group(2))
            display_date = f"{MONTH_NAMES.get(month, month)} {year}"
        else:
            display_date = ""

        if not title or not speaker:
            continue

        citations.append(
            {"talk_title": title, "speaker": speaker, "date": display_date, "url": url}
        )
    return citations


def harvest() -> tuple[dict[str, list[dict]], dict]:
    pool = json.loads(POOL_PATH.read_text(encoding="utf-8"))["verses"]
    book_ids = build_book_id_map()

    result: dict[str, list[dict]] = {}
    summary = {
        "requested": 0,
        "succeeded": 0,
        "zero_citations": 0,
        "failed": 0,
        "failures": [],
        "total_citations": 0,
    }

    # Expand each pool entry to its individual verses rather than querying
    # a range as one span: BYU's index only returns citations for talks
    # that cite that *exact* span, which badly undercounts a range like
    # Joseph Smith--History 1:15-20 (3 citations) against its most-cited
    # verse within it, 1:17 alone (109) - querying per-verse instead
    # matches how the reading view shows a citation indicator per verse.
    work_items = [
        (entry, verse)
        for entry in pool
        for verse in range(entry["verse"], entry.get("end_verse", entry["verse"]) + 1)
    ]

    for entry, verse in work_items:
        book_name = BOOK_NAME_ALIASES.get(entry["book"], entry["book"])
        chapter = entry["chapter"]
        reference_label = f"{entry['book']} {chapter}:{verse}"

        book_id = book_ids.get(book_name)
        if book_id is None:
            summary["failed"] += 1
            summary["failures"].append(f"{reference_label}: no known book id for {book_name!r}")
            continue

        summary["requested"] += 1

        try:
            html = fetch_citation_html(book_id, chapter, str(verse))
            citations = parse_citations(html)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            summary["failed"] += 1
            summary["failures"].append(f"{reference_label}: request failed ({exc})")
            time.sleep(REQUEST_DELAY_SECONDS)
            continue
        except Exception as exc:  # site structure differed from expected - skip, don't crash
            summary["failed"] += 1
            summary["failures"].append(f"{reference_label}: parse failed ({exc})")
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        if citations:
            summary["succeeded"] += 1
            summary["total_citations"] += len(citations)
            result[f"{book_name} {chapter}:{verse}"] = citations
        else:
            summary["zero_citations"] += 1

        print(f"  {reference_label}: {len(citations)} citation(s)")
        time.sleep(REQUEST_DELAY_SECONDS)

    return result, summary


def main() -> None:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_PATH

    print(f"Harvesting citations for the {POOL_PATH.name} pool from scriptures.byu.edu ...")
    citations, summary = harvest()

    output = {
        "_source": "scriptures.byu.edu Citation Index (General Conference talks)",
        "_harvested": date.today().isoformat(),
        "_note": (
            "Metadata only (talk title, speaker, date, churchofjesuschrist.org URL) - "
            "never talk text, per copyright. See scripts/harvest_citations.py. Keyed by "
            "the exact verse reference string used in the imported database "
            "(e.g. 'Genesis 1:1')."
        ),
        "citations": citations,
    }
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("Harvest summary:")
    print(f"  Verses requested:     {summary['requested']}")
    print(f"  Succeeded (>0 cites): {summary['succeeded']}")
    print(f"  Zero citations:       {summary['zero_citations']}")
    print(f"  Failed:               {summary['failed']}")
    print(f"  Total citations:      {summary['total_citations']}")
    if summary["failures"]:
        print("  Failures:")
        for f in summary["failures"]:
            print(f"    - {f}")
    print()
    print(f"Written to: {output_path}")


if __name__ == "__main__":
    main()
