"""General Conference citation metadata for the Scripture of the Day
pool's 100 verses (see scripts/harvest_citations.py for how
data/verse_citations.json is built, and its module docstring for the
copyright reasoning).

Pilot-scoped: only verses in that pool have any data here. Not backed by
the SQLite database - this is plain local JSON, loaded the same way
sotd.py loads the pool file itself, since neither concern is really
"repository over the scripture database" the way data_access.py is.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CITATIONS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "verse_citations.json"

_citations_cache: dict[str, list[dict]] | None = None


@dataclass(frozen=True)
class Citation:
    talk_title: str
    speaker: str
    date: str
    url: str


def _load_citations() -> dict[str, list[dict]]:
    global _citations_cache
    if _citations_cache is None:
        if CITATIONS_PATH.exists():
            data = json.loads(CITATIONS_PATH.read_text(encoding="utf-8"))
            _citations_cache = data["citations"]
        else:
            _citations_cache = {}
    return _citations_cache


def get_citations(reference: str) -> list[Citation]:
    """Citing General Conference talks for a verse, keyed by its exact
    Verse.reference string (e.g. "Genesis 1:1") - empty list if this verse
    isn't in the pilot pool or has no known citations. Already ordered
    newest-first, as harvested from the source index."""
    return [Citation(**c) for c in _load_citations().get(reference, [])]
