"""Citation metadata for the Scripture of the Day pool's 100 verses -
General Conference talks (see scripts/harvest_citations.py) and, since
v2.2.x, Ensign/Liahona magazine articles, English issues 1971-present
(see scripts/harvest_liahona_citations.py) - merged into one list per
verse, each entry tagged with which magazine it came from. See each
script's own module docstring for the copyright reasoning behind what's
stored.

Pilot-scoped: only verses in that pool have any data here. Not backed by
the SQLite database - this is plain local JSON (two separate files, one
per source), loaded the same way sotd.py loads the pool file itself,
since neither concern is really "repository over the scripture database"
the way data_access.py is.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
GENERAL_CONFERENCE_CITATIONS_PATH = _DATA_DIR / "verse_citations.json"
LIAHONA_CITATIONS_PATH = _DATA_DIR / "liahona_citations.json"

GENERAL_CONFERENCE_LABEL = "General Conference"
ENSIGN_LABEL = "Ensign"
LIAHONA_LABEL = "Liahona"

# The Ensign became the Liahona for English-language adult content in
# January 2021 (see harvest_liahona_citations.py's own LIAHONA_START) -
# which magazine name a citation displays under is derived from its date
# rather than stored per entry, since the date already fully determines it.
_LIAHONA_START = (2021, 1)

_MONTH_NUMBER = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}

_gc_cache: dict[str, list[dict]] | None = None
_liahona_cache: dict[str, list[dict]] | None = None


@dataclass(frozen=True)
class Citation:
    talk_title: str
    speaker: str
    date: str
    url: str
    source_label: str


def _load(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))["citations"]


def _load_gc() -> dict[str, list[dict]]:
    global _gc_cache
    if _gc_cache is None:
        _gc_cache = _load(GENERAL_CONFERENCE_CITATIONS_PATH)
    return _gc_cache


def _load_liahona() -> dict[str, list[dict]]:
    """liahona_citations.json is stored one entry per article (see
    harvest_liahona_citations.py's save() for why), so it's inverted
    here into the same per-verse shape as verse_citations.json."""
    global _liahona_cache
    if _liahona_cache is None:
        _liahona_cache = {}
        if LIAHONA_CITATIONS_PATH.exists():
            data = json.loads(LIAHONA_CITATIONS_PATH.read_text(encoding="utf-8"))
            for article in data["articles"]:
                citation = {k: article[k] for k in ("talk_title", "speaker", "date", "url")}
                for reference in article["references"]:
                    _liahona_cache.setdefault(reference, []).append(citation)
    return _liahona_cache


def _date_sort_key(display_date: str) -> tuple[int, int]:
    """"Month Year" -> (year, month), both harvesters' shared display
    format - unrecognized/empty dates sort first (oldest), not last,
    so a parsing gap can't make something look newer than it is."""
    parts = display_date.split()
    if len(parts) == 2 and parts[0] in _MONTH_NUMBER:
        return (int(parts[1]), _MONTH_NUMBER[parts[0]])
    return (0, 0)


def _magazine_label(display_date: str) -> str:
    year, month = _date_sort_key(display_date)
    return LIAHONA_LABEL if (year, month) >= _LIAHONA_START else ENSIGN_LABEL


@dataclass(frozen=True)
class CitingWork:
    """One talk or article with every verse it cites - the per-work view
    of the same data get_citations() serves per verse, for the study
    index's talk/article summary cards (see study_index.py)."""

    talk_title: str
    speaker: str
    date: str
    url: str
    source_label: str
    references: list[str]


def iter_citing_works() -> list[CitingWork]:
    """Every known General Conference talk and Ensign/Liahona article,
    each once, with the verses it cites in sorted order."""
    works: dict[str, CitingWork] = {}
    for loader, label_for in (
        (_load_gc, lambda _date: GENERAL_CONFERENCE_LABEL),
        (_load_liahona, _magazine_label),
    ):
        for reference, entries in loader().items():
            for c in entries:
                work = works.get(c["url"])
                if work is None:
                    work = CitingWork(
                        c["talk_title"], c["speaker"], c["date"], c["url"], label_for(c["date"]), []
                    )
                    works[c["url"]] = work
                work.references.append(reference)
    for work in works.values():
        # verse_citations.json sometimes lists the same talk more than
        # once under one verse.
        work.references[:] = sorted(set(work.references))
    return sorted(works.values(), key=lambda w: w.url)


def get_citations(reference: str) -> list[Citation]:
    """Every citing work for a verse - General Conference talks and
    Ensign/Liahona articles alike - keyed by its exact Verse.reference
    string (e.g. "Genesis 1:1"), empty if this verse isn't in the pilot
    pool or has no known citations from either source. Newest first
    across both sources combined."""
    entries = [
        Citation(**c, source_label=GENERAL_CONFERENCE_LABEL) for c in _load_gc().get(reference, [])
    ] + [
        Citation(**c, source_label=_magazine_label(c["date"]))
        for c in _load_liahona().get(reference, [])
    ]
    entries.sort(key=lambda c: _date_sort_key(c.date), reverse=True)
    return entries
