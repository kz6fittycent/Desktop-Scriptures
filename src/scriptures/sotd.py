"""Scripture of the Day: a random pick from a curated pool of the most
frequently cited verses (see data/scripture_of_the_day_pool.json for the
pool's provenance and caveats), with live text pulled from the actual
imported database rather than baked into the pool file.

Not deterministic per-day yet - just a fresh random pick each time this is
called (typically once, when the landing page is built).
"""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from scriptures.data_access import get_verse_by_reference

POOL_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "scripture_of_the_day_pool.json"

# Per the pool file's _format_note: book names match this project's
# volumes.json / import_scriptures.py naming exactly, except "D&C" - the
# same alias the importer itself applies when reading the source text.
BOOK_NAME_ALIASES = {"D&C": "Doctrine and Covenants"}

_pool_cache: list[dict] | None = None


@dataclass(frozen=True)
class ScriptureOfTheDay:
    reference: str
    text: str


def _load_pool() -> list[dict]:
    global _pool_cache
    if _pool_cache is None:
        data = json.loads(POOL_PATH.read_text(encoding="utf-8"))
        _pool_cache = data["verses"]
    return _pool_cache


def get_scripture_of_the_day(conn: sqlite3.Connection) -> ScriptureOfTheDay | None:
    """Pick a random verse from the curated pool and pull its live text
    from the database - only ever the single "verse" field (the range's
    start), even for pool entries whose "end_verse" marks them as
    originally a multi-verse passage; this always shows exactly one verse.

    An entry whose book/chapter/verse doesn't actually resolve against the
    database (shouldn't happen, but the pool is hand-curated data) is
    skipped in favor of another pick rather than crashing. None only if no
    entry in the whole pool resolves.
    """
    candidates = list(_load_pool())
    random.shuffle(candidates)
    for entry in candidates:
        book_name = BOOK_NAME_ALIASES.get(entry["book"], entry["book"])
        verse = get_verse_by_reference(conn, book_name, entry["chapter"], entry["verse"])
        if verse is not None:
            return ScriptureOfTheDay(reference=verse.reference, text=verse.text)
    return None
