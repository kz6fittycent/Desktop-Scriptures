"""The citation data files' shape and safety checks - shared by the app
(content_updates.py, before using a downloaded file) and the weekly
GitHub workflows (scripts/publish_citations.py, before publishing one).
No Qt here, so the workflows can import it with plain Python.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

FILES = ("verse_citations.json", "liahona_citations.json")
# A downloaded file may not have fewer entries than this share of the
# data in use - a harvest that lost data must never replace good data.
MIN_KEEP_RATIO = 0.9

_HARVESTED_RE = re.compile(r'"_harvested":\s*"(\d{4}-\d{2}-\d{2})"')


def harvested_date(path: Path) -> str:
    """The file's "_harvested" date (YYYY-MM-DD), read from its header."""
    try:
        with open(path, encoding="utf-8") as f:
            match = _HARVESTED_RE.search(f.read(4096))
    except OSError:
        return ""
    return match.group(1) if match else ""


def entry_count(name: str, data: dict) -> int:
    """Verses (General Conference) or articles (Liahona) - raises
    ValueError if the data isn't shaped like that file."""
    if name == "verse_citations.json":
        citations = data.get("citations")
        if not isinstance(citations, dict):
            raise ValueError("no citations table")
        return len(citations)
    articles = data.get("articles")
    if not isinstance(articles, list) or not all(
        isinstance(a, dict) and {"url", "talk_title", "references"} <= set(a) for a in articles[:50]
    ):
        raise ValueError("no articles list")
    return len(articles)


def check_replacement(name: str, new_data: dict, current_path: Path) -> str | None:
    """Why `new_data` must not replace the file in use, or None if it may."""
    try:
        new_count = entry_count(name, new_data)
    except ValueError as exc:
        return f"unexpected contents ({exc})"
    try:
        current_count = entry_count(name, json.loads(current_path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None  # nothing usable in place - anything well-formed is better
    if new_count < current_count * MIN_KEEP_RATIO:
        return f"only {new_count} entries where {current_count} are in use"
    return None
