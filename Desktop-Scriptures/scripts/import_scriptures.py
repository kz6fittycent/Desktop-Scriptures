#!/usr/bin/env python3
"""Import the beandog lds-scriptures.txt file into the Scriptures SQLite DB.

Usage:
    python3 import_scriptures.py <path-to-lds-scriptures.txt> <path-to-output.db>

Source text format (tab-separated), one verse per line:
    Genesis 1:1<TAB>In the beginning God created the heaven and the earth.
    1 Nephi 1:1<TAB>I, Nephi, having been born of goodly parents...
    D&C 1:1<TAB>Hearken, O ye people of my church...

This script is intentionally offline: it reads a LOCAL copy of the text
file rather than fetching it over the network at import time or at app
runtime, in keeping with the app's offline-first design. Download the
file once from:
    https://raw.githubusercontent.com/beandog/lds-scriptures/master/text/lds-scriptures.txt
and pass its path as the first argument.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import connect, fts5_available  # noqa: E402

VOLUMES_JSON = PROJECT_ROOT / "data" / "volumes.json"

# Matches "Book Name Chapter:Verse<WHITESPACE>Text", where Book Name may
# itself contain digits (e.g. "1 Nephi", "2 Corinthians"). The chapter:verse
# pair is unambiguous, so we anchor on that. The separator between the
# reference and the verse text varies by source file (tab in some releases,
# multiple spaces in others) - \s+ handles either.
LINE_RE = re.compile(r"^(?P<book>.+) (?P<chapter>\d+):(?P<verse>\d+)\s+(?P<text>\S.*)$")

# Some source files use short forms; map them to our canonical names from
# volumes.json. Extend this as real-world mismatches turn up during import.
BOOK_NAME_ALIASES = {
    "D&C": "Doctrine and Covenants",
    "JS-M": "Joseph Smith--Matthew",
    "JS-H": "Joseph Smith--History",
    "A of F": "Articles of Faith",
    "Joseph Smith-Matthew": "Joseph Smith--Matthew",
    "Joseph Smith-History": "Joseph Smith--History",
}


def load_hierarchy(conn: sqlite3.Connection) -> dict[str, dict]:
    """Insert volumes/testaments/books from volumes.json and return a lookup
    of canonical book name -> {"book_id": ..., "volume_slug": ...}.
    """
    data = json.loads(VOLUMES_JSON.read_text(encoding="utf-8"))
    book_lookup: dict[str, dict] = {}

    for vol in data["volumes"]:
        cur = conn.execute(
            "INSERT INTO volumes (name, slug, sort_order) VALUES (?, ?, ?)",
            (vol["name"], vol["slug"], vol["sort_order"]),
        )
        volume_id = cur.lastrowid

        if vol.get("testaments"):
            for test in vol["testaments"]:
                cur = conn.execute(
                    "INSERT INTO testaments (volume_id, name, slug, sort_order) "
                    "VALUES (?, ?, ?, ?)",
                    (volume_id, test["name"], test["slug"], test["sort_order"]),
                )
                testament_id = cur.lastrowid
                for i, book_name in enumerate(test["books"], start=1):
                    cur = conn.execute(
                        "INSERT INTO books (volume_id, testament_id, name, sort_order) "
                        "VALUES (?, ?, ?, ?)",
                        (volume_id, testament_id, book_name, i),
                    )
                    book_lookup[book_name] = {
                        "book_id": cur.lastrowid,
                        "volume_slug": vol["slug"],
                    }
        else:
            for i, book_name in enumerate(vol["books"], start=1):
                cur = conn.execute(
                    "INSERT INTO books (volume_id, testament_id, name, sort_order) "
                    "VALUES (?, NULL, ?, ?)",
                    (volume_id, book_name, i),
                )
                book_lookup[book_name] = {
                    "book_id": cur.lastrowid,
                    "volume_slug": vol["slug"],
                }

    conn.commit()
    return book_lookup


def import_verses(conn: sqlite3.Connection, text_path: Path, book_lookup: dict) -> dict:
    """Parse the raw text file and insert chapters/verses.
    Returns a summary dict of counts and any unmatched book names.
    """
    chapter_cache: dict[tuple[int, int], int] = {}  # (book_id, chapter_num) -> chapter_id
    verse_count = 0
    unmatched_books: dict[str, int] = {}
    unparsed_lines = 0
    unparsed_samples: list[str] = []

    with text_path.open("r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.rstrip("\r\n")
            if not line.strip():
                continue

            m = LINE_RE.match(line)
            if not m:
                unparsed_lines += 1
                if len(unparsed_samples) < 5:
                    unparsed_samples.append(repr(line[:80]))
                continue

            book_name = m.group("book").strip()
            book_name = BOOK_NAME_ALIASES.get(book_name, book_name)
            chapter_num = int(m.group("chapter"))
            verse_num = int(m.group("verse"))
            text = m.group("text").strip()

            entry = book_lookup.get(book_name)
            if entry is None:
                unmatched_books[book_name] = unmatched_books.get(book_name, 0) + 1
                continue

            book_id = entry["book_id"]
            key = (book_id, chapter_num)
            chapter_id = chapter_cache.get(key)
            if chapter_id is None:
                cur = conn.execute(
                    "INSERT INTO chapters (book_id, chapter_number) VALUES (?, ?)",
                    (book_id, chapter_num),
                )
                chapter_id = cur.lastrowid
                chapter_cache[key] = chapter_id

            reference = f"{book_name} {chapter_num}:{verse_num}"
            conn.execute(
                "INSERT INTO verses (chapter_id, verse_number, text, reference) "
                "VALUES (?, ?, ?, ?)",
                (chapter_id, verse_num, text, reference),
            )
            verse_count += 1

    conn.commit()
    return {
        "verse_count": verse_count,
        "chapter_count": len(chapter_cache),
        "unmatched_books": unmatched_books,
        "unparsed_lines": unparsed_lines,
        "unparsed_samples": unparsed_samples,
    }


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    text_path = Path(sys.argv[1])
    db_path = Path(sys.argv[2])

    if not text_path.exists():
        print(f"Source text file not found: {text_path}")
        sys.exit(1)

    if db_path.exists():
        db_path.unlink()  # fresh import each run

    conn = connect(db_path)

    if not fts5_available(conn):
        print("WARNING: this SQLite build does not support FTS5. "
              "Full-text search will not work.")

    print("Loading volume/testament/book hierarchy...")
    book_lookup = load_hierarchy(conn)
    print(f"  {len(book_lookup)} books registered.")

    print(f"Importing verses from {text_path} ...")
    summary = import_verses(conn, text_path, book_lookup)

    print()
    print("Import summary:")
    print(f"  Verses imported:   {summary['verse_count']}")
    print(f"  Chapters created:  {summary['chapter_count']}")
    print(f"  Unparsed lines:    {summary['unparsed_lines']}")
    if summary["unparsed_samples"]:
        print("  Sample unparsed lines (for debugging):")
        for s in summary["unparsed_samples"]:
            print(f"    {s}")
    if summary["unmatched_books"]:
        print(f"  Unmatched book names ({len(summary['unmatched_books'])}):")
        for name, count in sorted(summary["unmatched_books"].items()):
            print(f"    - {name!r}: {count} verses skipped")
    else:
        print("  Unmatched book names: none")

    conn.close()
    print()
    print(f"Database written to: {db_path}")


if __name__ == "__main__":
    main()
