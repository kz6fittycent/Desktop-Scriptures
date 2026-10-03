#!/usr/bin/env python3
"""Harvest of scripture citation metadata from every English Ensign
(1971-2020) and Liahona (2021-present) magazine article, for
data/liahona_citations.json.

Usage:
    python3 scripts/harvest_liahona_citations.py [output_path] [--months N | --full]

    output_path defaults to data/liahona_citations.json.

    By default only the last RECENT_MONTHS issues are scanned (--months N
    to change it) - new articles only appear in new issues, so a monthly
    refresh (.github/workflows/refresh-liahona-citations.yml) takes a few
    minutes. --full rescans every issue from 1971: many hours - see
    "Rate limiting" below - so start it by hand and leave it running.

    Why not always rescan everything and skip what's already harvested?
    Only articles WITH scripture citations are stored, and about half of
    all articles have none (news, stories, contents pages) - so a full
    rescan re-downloads ~12,000 of them every time (5+ hours), which is
    what made the monthly refresh time out.

WHY THIS EXISTS SEPARATELY FROM harvest_citations.py: scriptures.byu.edu's
Citation Index (which that script scrapes) has no corpus at all for the
Ensign or Liahona - only General Conference, the Improvement Era
(1897-1970), the Journal of Discourses, and Teachings of the Prophet
Joseph Smith. There is no existing, ready-made citation index for
Ensign/Liahona content to extend; this script builds one directly from
churchofjesuschrist.org itself instead.

MECHANISM: every scripture reference in an Ensign/Liahona article is
already a hyperlink straight to its /study/scriptures/... page on the
same site - detecting a citation is just finding that link, never
reading or understanding the surrounding prose. The Church's own
book/volume slugs in those links (e.g. "nt/matt", "bofm/2-ne") are
resolved to this app's canonical book names (e.g. "Matthew", "2 Nephi")
by fetching that chapter's own page once per distinct book and reading
its <title> (e.g. "2 Nephi 9") - cached, so at most ~90 such lookups
total, however many articles are harvested. Every resulting "Book
Chapter:Verse" reference is then checked against this app's own local
`verses` table before being kept - anything that doesn't resolve to a
real local verse is dropped, never guessed at. Which magazine name
("Ensign" or "Liahona") is shown for a given citation is derived later,
at display time in scriptures/citations.py, from its issue date (the
Ensign became the Liahona for English content in January 2021) - not
stored per entry here, since it's fully determined by the date already
being recorded.

COPYRIGHT: Ensign/Liahona articles are copyrighted by Intellectual
Reserve, Inc. This script only ever extracts METADATA - article title,
author, publication date, and its churchofjesuschrist.org URL - plus
which scripture verses it cites, detected via the hyperlink structure
above. Article text itself is fetched (there's no way to find the links
without it) but never stored, displayed, or analyzed beyond that;
robots.txt at churchofjesuschrist.org does not disallow /study/ensign/,
/study/liahona/, or /study/scriptures/.

SCOPE: every English issue from January 1971 (the Ensign's first) to
the current month - both the modern Liahona (/study/liahona/...) and
the older Ensign (/study/ensign/...), which use the same underlying
page structure (verified directly against a real 1971 issue while
building this). Skips each issue's region-specific "local pages" (local
news/inserts, not the magazine's actual editorial content).

Rate limiting: one request at a time, REQUEST_DELAY_SECONDS apart,
strictly sequential - every table of contents, every article, and every
one-time book-name lookup. The full ~55-year archive is on the order of
ten thousand articles - many hours, not minutes - so this is designed
to be safely interrupted and re-run: already-harvested article URLs are
skipped on a subsequent run (see `seen_urls`), and progress is saved
after every single issue, never batched up until the very end.
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

from scriptures.db import connect  # noqa: E402

DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "liahona_citations.json"
DB_PATH = PROJECT_ROOT / "data" / "scriptures.db"

BASE_URL = "https://www.churchofjesuschrist.org"
HARVEST_START_YEAR = 1971
HARVEST_START_MONTH = 1

# The Ensign became the Liahona for English-language adult content in
# January 2021 - the one date that decides both which URL path an
# issue's articles live under (see issue_url_prefix) and which magazine
# name a citation displays under (see scriptures/citations.py).
LIAHONA_START = (2021, 1)

REQUEST_DELAY_SECONDS = 1.5
# The default scan window: this month and the RECENT_MONTHS - 1 before it.
RECENT_MONTHS = 3
USER_AGENT = (
    "Desktop-Scriptures/1.0 (+https://github.com/kz6fittycent/Desktop-Scriptures; "
    "harvest of Ensign/Liahona citation metadata, English issues 1971-present)"
)

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}

# The Church's own site titles each individual psalm's chapter page
# "Psalm N" (singular) rather than "Psalms N" - this app's database (like
# the KJV itself) treats Psalms as one book, so this is the one place the
# two naming conventions genuinely differ rather than just needing an
# nbsp fixup (see resolve_book_name).
BOOK_NAME_ALIASES = {"Psalm": "Psalms"}

SCRIPTURE_LINK_RE = re.compile(
    r'href="/study/scriptures/([a-z-]+)/([a-z0-9-]+)/(\d+)\?lang=eng&(?:amp;)?'
    r'id=p(\d+)(?:-p(\d+))?'
)
TITLE_RE = re.compile(r'<meta[^>]*property="og:title"[^>]*content="([^"]*)"')
AUTHOR_RE = re.compile(r'"author":\{"@type":"Person","name":"([^"]*)"')


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def month_range(start_year: int, start_month: int, end_year: int, end_month: int):
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def issue_url_prefix(year: int, month: int) -> str:
    return "liahona" if (year, month) >= LIAHONA_START else "ensign"


def fetch_issue_article_urls(year: int, month: int) -> list[str]:
    prefix = issue_url_prefix(year, month)
    html = fetch(f"{BASE_URL}/study/{prefix}/{year}/{month:02d}?lang=eng")
    href_re = re.compile(rf'href="(/study/{prefix}/\d{{4}}/\d{{2}}/[^"?]*)')
    hrefs = set()
    for match in href_re.finditer(html):
        href = match.group(1)
        if "local-pages" in href:
            continue  # regional inserts, not the magazine's editorial content
        if href.rstrip("/").endswith("/contents"):
            continue  # the issue's table of contents, not an article
        hrefs.add(href)
    return sorted(hrefs)


_book_name_cache: dict[tuple[str, str], str | None] = {}


def _normalize_book_name(raw_title: str) -> str:
    """A scripture chapter page's own <title> (e.g. "2 Nephi 9") to just
    its book name (e.g. "2 Nephi"), matching this app's own
    `verses.reference` naming exactly. Two real, live-verified quirks
    handled here, not just the obvious "strip the trailing chapter
    number": the Church's own title uses a non-breaking space (&nbsp;,
    U+00A0) between a numbered book's leading digit and its name (e.g.
    "2\xa0Nephi 9") where this app's database uses a plain space, and an
    em dash (—, U+2014) in "Joseph Smith—History"/"Joseph Smith—Matthew"
    where this app's database uses a plain "--" - both silently dropped
    every citation for the affected books before being caught here."""
    title = unescape(raw_title).replace("\xa0", " ").replace("—", "--")
    book_name = title.rsplit(" ", 1)[0]
    return BOOK_NAME_ALIASES.get(book_name, book_name)


def resolve_book_name(volume_slug: str, book_slug: str, chapter: int) -> str | None:
    """The Church's own book name for this slug pair (e.g. "2 Nephi" for
    ("bofm", "2-ne")) - fetched once per distinct (volume_slug, book_slug)
    and cached, regardless of how many articles/chapters reference it."""
    key = (volume_slug, book_slug)
    if key in _book_name_cache:
        return _book_name_cache[key]
    url = f"{BASE_URL}/study/scriptures/{volume_slug}/{book_slug}/{chapter}?lang=eng"
    try:
        html = fetch(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        _book_name_cache[key] = None
        return None
    finally:
        time.sleep(REQUEST_DELAY_SECONDS)
    title_match = TITLE_RE.search(html)
    book_name = _normalize_book_name(title_match.group(1)) if title_match else None
    _book_name_cache[key] = book_name
    return book_name


def parse_article(html: str, url: str, issue_year: int, issue_month: int) -> tuple[dict, set[str]] | None:
    title_match = TITLE_RE.search(html)
    if not title_match:
        return None
    title = unescape(title_match.group(1))
    author_match = AUTHOR_RE.search(html)
    author = unescape(author_match.group(1)) if author_match else ""
    # Not the article's own "datePublished" metadata - that can reflect
    # some other internal timestamp (seen in testing: a talk reprinted in
    # the June 2024 issue whose datePublished was January 2024) rather
    # than the magazine issue it actually appeared in, which is what a
    # reader means by "when is this citing work from." The issue being
    # harvested is already known for certain at the call site below.
    display_date = f"{MONTH_NAMES[issue_month]} {issue_year}"

    references: set[str] = set()
    for volume_slug, book_slug, chapter_str, verse_start, verse_end in SCRIPTURE_LINK_RE.findall(
        html
    ):
        chapter = int(chapter_str)
        start = int(verse_start)
        end = int(verse_end) if verse_end else start
        book_name = resolve_book_name(volume_slug, book_slug, chapter)
        if book_name is None:
            continue
        for verse in range(start, end + 1):
            references.add(f"{book_name} {chapter}:{verse}")

    citation = {"talk_title": title, "speaker": author, "date": display_date, "url": url}
    return citation, references


def load(output_path: Path) -> dict[str, dict]:
    """Already-harvested articles, keyed by URL - see save() for the
    file's shape."""
    if not output_path.exists():
        return {}
    articles = json.loads(output_path.read_text(encoding="utf-8")).get("articles", [])
    return {article["url"]: article for article in articles}


def save(output_path: Path, articles: dict[str, dict]) -> None:
    """One entry per citing article - its metadata once, plus every
    verse reference it cites - rather than one entry per verse repeating
    the same article's metadata under each verse it cites: an article
    cites ~18 verses on average, so the per-verse shape repeated each
    title/author/URL that many times over, and grew past GitHub's 50MB
    large-file warning on its way toward the hard 100MB push limit.
    citations.py inverts this back to per-verse at load time.

    Written one article per line, sorted by URL, so a re-harvest's diff
    (see .github/workflows/refresh-liahona-citations.yml - a human
    reviews it before merging) is just one added line per new article."""
    output = {
        "_source": "churchofjesuschrist.org Ensign/Liahona magazine (English, 1971-present)",
        "_harvested": date.today().isoformat(),
        "_note": (
            "Metadata only (article title, author, date, churchofjesuschrist.org URL) - "
            "never article text, per copyright. Citations are detected via each article's "
            "own hyperlinks to /study/scriptures/..., never by reading article prose. See "
            "scripts/harvest_liahona_citations.py. One entry per article; each article's "
            "references are the exact verse reference strings used in the imported database "
            "(e.g. 'Genesis 1:1')."
        ),
    }
    header = json.dumps(output, indent=2, ensure_ascii=False)
    lines = [
        "  " + json.dumps(articles[url], ensure_ascii=False, separators=(", ", ": "))
        for url in sorted(articles)
    ]
    # header ends in "\n}" - reopen it to append the articles array.
    text = header[:-2] + ',\n  "articles": [\n' + ",\n".join(lines) + "\n  ]\n}\n"
    output_path.write_text(text, encoding="utf-8")


def harvest(conn, output_path: Path, months: int | None = RECENT_MONTHS) -> None:
    """months=None scans every issue since 1971 (--full)."""
    articles = load(output_path)
    seen_urls = set(articles)

    today = date.today()
    start_year, start_month = HARVEST_START_YEAR, HARVEST_START_MONTH
    if months is not None:
        index = today.year * 12 + (today.month - 1) - (months - 1)
        start_year, start_month = max((index // 12, index % 12 + 1), (HARVEST_START_YEAR, HARVEST_START_MONTH))
    print(f"Scanning issues from {start_year}-{start_month:02d} to {today.year}-{today.month:02d}")
    stats = {
        "issues": 0,
        "articles": 0,
        "articles_with_citations": 0,
        "citation_links": 0,
        "unresolved_references": 0,
    }

    for year, month in month_range(start_year, start_month, today.year, today.month):
        try:
            article_hrefs = fetch_issue_article_urls(year, month)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"{year}-{month:02d}: table of contents failed ({exc})")
            time.sleep(REQUEST_DELAY_SECONDS)
            continue
        time.sleep(REQUEST_DELAY_SECONDS)
        stats["issues"] += 1
        print(f"{year}-{month:02d}: {len(article_hrefs)} article(s)")

        for href in article_hrefs:
            article_url = f"{BASE_URL}{href}?lang=eng"
            if article_url in seen_urls:
                continue  # already harvested in a previous run of this script

            try:
                html = fetch(article_url)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                print(f"    {href}: failed ({exc})")
                time.sleep(REQUEST_DELAY_SECONDS)
                continue
            time.sleep(REQUEST_DELAY_SECONDS)
            stats["articles"] += 1

            parsed = parse_article(html, article_url, year, month)
            if parsed is None:
                continue
            citation, references = parsed
            if not references:
                continue

            resolved = []
            for reference in references:
                exists = conn.execute(
                    "SELECT 1 FROM verses WHERE reference = ?", (reference,)
                ).fetchone()
                if not exists:
                    stats["unresolved_references"] += 1
                    continue
                resolved.append(reference)
                stats["citation_links"] += 1
            if resolved:
                articles[article_url] = {**citation, "references": sorted(resolved)}
                stats["articles_with_citations"] += 1
                seen_urls.add(article_url)
                print(f"    {href}: {len(references)} reference(s)")

        # Saved after every issue, not just at the end - a run interrupted
        # partway through (this can take well over an hour end-to-end)
        # keeps everything harvested so far, and re-running the script
        # picks up where it left off via seen_urls above.
        save(output_path, articles)

    print()
    print("Harvest summary:")
    print(f"  Issues processed:        {stats['issues']}")
    print(f"  Articles processed:      {stats['articles']}")
    print(f"  Articles with citations: {stats['articles_with_citations']}")
    print(f"  Total citation links:    {stats['citation_links']}")
    print(f"  Unresolved references:   {stats['unresolved_references']}")
    print()
    print(f"Written to: {output_path}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Harvest Ensign/Liahona citation metadata.")
    parser.add_argument("output_path", nargs="?", type=Path, default=DEFAULT_OUTPUT_PATH)
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--months", type=int, default=RECENT_MONTHS,
                        help=f"scan this many most recent issues (default {RECENT_MONTHS})")
    window.add_argument("--full", action="store_true", help="scan every issue since 1971 (many hours)")
    args = parser.parse_args()
    # Progress shows live even when output isn't a terminal (CI logs).
    sys.stdout.reconfigure(line_buffering=True)
    conn = connect(DB_PATH)
    harvest(conn, args.output_path, None if args.full else args.months)


if __name__ == "__main__":
    main()
