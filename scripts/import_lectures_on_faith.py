#!/usr/bin/env python3
"""Import the 1835 "Lectures on Faith" into the Scriptures SQLite DB, as
its own volume alongside the existing scripture volumes and the Journal
of Discourses.

Usage:
    python3 scripts/import_lectures_on_faith.py <path-to-db>

Source text: the seven lectures plus the original preface, each saved as
its own data/Lectures_on_Faith_<Title>.txt file (public domain; first
published 1835, long before any copyright term still in force). Unlike
Journal of Discourses, these are short, clean, already-transcribed texts
with no OCR boundary-detection problem to solve - this script just needs
to split each into paragraphs and load them in lecture order.

TEXT MODEL: each lecture (and the preface) becomes one `chapters` row;
each paragraph within it becomes one `verses` row, numbered from 1 - the
1835 original itself numbers paragraphs this way (later editions render
them as "1.", "2." etc. inline), so this matches an actual historical
convention rather than inventing one, unlike Journal of Discourses where
a whole discourse is one verse. The preface is chapter_number 0 (it
precedes "Lecture First" in the original and isn't itself a lecture);
main_window._chapter_label special-cases 0 -> "Preface", others ->
"Lecture N".
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import connect  # noqa: E402

DATA_DIR = PROJECT_ROOT / "data"

VOLUME_NAME = "Lectures on Faith"
VOLUME_SLUG = "lectures-on-faith"
VOLUME_SORT_ORDER = 6  # after Journal of Discourses (5)

BOOK_NAME = VOLUME_NAME

# (chapter_number, filename, title) in reading order. Filenames come from
# the earlier scrape; titles are this app's own display labels, not
# carried through to the DB (only JoD chapters use the title/speaker/
# discourse_date columns - these stay NULL here, same as ordinary
# scripture chapters).
LECTURES = [
    (0, "Lectures_on_Faith_Preface.txt"),
    (1, "Lectures_on_Faith_Faith_Defined.txt"),
    (2, "Lectures_on_Faith_The_Object_of_Faith.txt"),
    (3, "Lectures_on_Faith_The_Character_of_God.txt"),
    (4, "Lectures_on_Faith_The_Attributes_of_God.txt"),
    (5, "Lectures_on_Faith_The_Godhead.txt"),
    (6, "Lectures_on_Faith_The_Law_of_Sacrifice.txt"),
    (7, "Lectures_on_Faith_The_Effects_of_Faith.txt"),
]


def load_paragraphs(path: Path) -> list[str]:
    """Blank-line-separated paragraphs. A handful of paragraphs also
    contain a single internal line break (e.g. a Q&A heading run
    straight into the first question, no blank line between) rather
    than a real paragraph break - collapsed here via split()/join()
    same as any other whitespace normalization, since a mid-paragraph
    line break carries no meaning in this source."""
    text = path.read_text(encoding="utf-8")
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    return [" ".join(p.split()) for p in paragraphs]


def _get_or_create_volume(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM volumes WHERE slug = ?", (VOLUME_SLUG,)).fetchone()
    if row is not None:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO volumes (name, slug, sort_order) VALUES (?, ?, ?)",
        (VOLUME_NAME, VOLUME_SLUG, VOLUME_SORT_ORDER),
    )
    return cur.lastrowid


def _delete_existing_book(conn: sqlite3.Connection, volume_id: int) -> None:
    """Safe to re-run: clears out any previously imported copy (and its
    notes/tags/highlights/reading-log rows) before reinserting, same
    approach as the Journal of Discourses importer."""
    row = conn.execute(
        "SELECT id FROM books WHERE volume_id = ? AND name = ?", (volume_id, BOOK_NAME)
    ).fetchone()
    if row is None:
        return
    book_id = row["id"]
    chapter_ids = [
        r["id"] for r in conn.execute("SELECT id FROM chapters WHERE book_id = ?", (book_id,))
    ]
    for chapter_id in chapter_ids:
        verse_ids = [
            r["id"]
            for r in conn.execute("SELECT id FROM verses WHERE chapter_id = ?", (chapter_id,))
        ]
        for verse_id in verse_ids:
            conn.execute("DELETE FROM highlights WHERE verse_id = ?", (verse_id,))
            conn.execute("DELETE FROM notes WHERE verse_id = ?", (verse_id,))
            conn.execute("DELETE FROM tag_assignments WHERE verse_id = ?", (verse_id,))
        conn.execute("DELETE FROM notes WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM tag_assignments WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM reading_log WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM verses WHERE chapter_id = ?", (chapter_id,))
    conn.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))
    conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()


def import_lectures(conn: sqlite3.Connection) -> dict:
    volume_id = _get_or_create_volume(conn)
    _delete_existing_book(conn, volume_id)

    cur = conn.execute(
        "INSERT INTO books (volume_id, testament_id, name, sort_order) VALUES (?, NULL, ?, 1)",
        (volume_id, BOOK_NAME),
    )
    book_id = cur.lastrowid

    summary = {"chapters": 0, "paragraphs": 0}

    for chapter_number, filename in LECTURES:
        path = DATA_DIR / filename
        paragraphs = load_paragraphs(path)
        if not paragraphs:
            print(f"  WARNING: no paragraphs found in {filename}, skipping")
            continue

        cur = conn.execute(
            "INSERT INTO chapters (book_id, chapter_number) VALUES (?, ?)",
            (book_id, chapter_number),
        )
        chapter_id = cur.lastrowid

        for verse_number, paragraph in enumerate(paragraphs, start=1):
            reference = f"{VOLUME_NAME} {chapter_number}:{verse_number}"
            conn.execute(
                "INSERT INTO verses (chapter_id, verse_number, text, reference) "
                "VALUES (?, ?, ?, ?)",
                (chapter_id, verse_number, paragraph, reference),
            )

        summary["chapters"] += 1
        summary["paragraphs"] += len(paragraphs)

    conn.commit()
    return summary


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    db_path = Path(sys.argv[1])

    conn = connect(db_path)
    print("Importing Lectures on Faith ...")
    summary = import_lectures(conn)
    conn.close()

    print()
    print("Import summary:")
    print(f"  Chapters imported: {summary['chapters']} of {len(LECTURES)}")
    print(f"  Paragraphs imported: {summary['paragraphs']}")
    print()
    print(f"Database written to: {db_path}")


if __name__ == "__main__":
    main()
