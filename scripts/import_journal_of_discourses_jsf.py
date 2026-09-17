#!/usr/bin/env python3
"""Replace the Journal of Discourses dataset in the Scriptures SQLite DB
with content scraped from josephsmithfoundation.org's "Journal of
Discourses Online" project, superseding the archive.org OCR pipeline
(import_journal_of_discourses.py) - that pipeline hit a hard quality
ceiling (OCR noise, and some pages structurally interleave two columns
of text in a way that can't be safely auto-corrected without risking
fabricated content). This source's per-discourse web pages are clean,
accurately-typeset HTML with no OCR artifacts.

Usage:
    python3 scripts/import_journal_of_discourses_jsf.py <discourses.jsonl> <path-to-db>

discourses.jsonl: one JSON object per line, fields url/title/speaker/
volume/date/paragraphs, produced by scraping every discourse page linked
from https://www.josephsmithfoundation.org/journalofdiscourses/topics/
volumes/volume-<N>/ (N=1..26, paginated), fetched sequentially at 1.5s
between requests. Site's robots.txt is fully open; no copyright/
reproduction-restriction notice was found on the site despite real
search effort (unlike fairlatterdaysaints.org and scriptures.byu.edu,
both explicitly avoided in the OCR pipeline's docstring for exactly that
reason). This is still a judgment call, not a certainty - the user was
told the residual ambiguity explicitly (a compilation/presentation-level
claim over this specific edition can't be fully ruled out even without a
found notice) and confirmed, specifically and with awareness of scale,
that bulk-scraping and permanently storing this content was intended.

TEXT MODEL: unchanged from the OCR pipeline - one discourse is one
`verses` row (verse_number=1), paragraph breaks kept as "\n\n" within
that single text, reference format "Journal of Discourses 1:<chapter_
number>". Chapter numbers are assigned sequentially in date order within
each volume (this source doesn't expose the original discourse-number
column the way FAIR's index did, so numbering here is this script's own,
not necessarily matching the original book's numbering).

REPLACES, not merges: every existing Journal of Discourses book/chapter/
verse (and their notes/tags/highlights) is deleted before this source's
data is inserted. Every other volume (scripture) and every other table
is untouched.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import connect  # noqa: E402

VOLUME_NAME = "Journal of Discourses"
VOLUME_SLUG = "journal-of-discourses"

DATE_RE = re.compile(r"([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})")


def parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    m = DATE_RE.search(date_str)
    if not m:
        return None
    month_name, day, year = m.groups()
    try:
        return datetime.strptime(f"{month_name} {day} {year}", "%B %d %Y").date().isoformat()
    except ValueError:
        return None


def load_discourses(jsonl_path: Path) -> dict[int, list[dict]]:
    by_volume: dict[int, list[dict]] = {}
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if "error" in record or not record.get("paragraphs"):
                continue
            vol = record.get("volume")
            if not vol or not (1 <= vol <= 26):
                continue
            by_volume.setdefault(vol, []).append(record)
    return by_volume


def _delete_existing_jod(conn) -> None:
    row = conn.execute("SELECT id FROM volumes WHERE slug = ?", (VOLUME_SLUG,)).fetchone()
    if row is None:
        return
    volume_id = row["id"]
    chapter_ids = [
        r["id"]
        for r in conn.execute(
            "SELECT c.id FROM chapters c JOIN books b ON b.id = c.book_id WHERE b.volume_id = ?",
            (volume_id,),
        )
    ]
    for chapter_id in chapter_ids:
        verse_ids = [
            r["id"] for r in conn.execute("SELECT id FROM verses WHERE chapter_id = ?", (chapter_id,))
        ]
        for verse_id in verse_ids:
            conn.execute("DELETE FROM highlights WHERE verse_id = ?", (verse_id,))
            conn.execute("DELETE FROM notes WHERE verse_id = ?", (verse_id,))
            conn.execute("DELETE FROM tag_assignments WHERE verse_id = ?", (verse_id,))
        conn.execute("DELETE FROM notes WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM tag_assignments WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM reading_log WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM verses WHERE chapter_id = ?", (chapter_id,))
    conn.execute(
        "DELETE FROM chapters WHERE book_id IN (SELECT id FROM books WHERE volume_id = ?)",
        (volume_id,),
    )
    conn.execute("DELETE FROM books WHERE volume_id = ?", (volume_id,))
    conn.execute("DELETE FROM volumes WHERE id = ?", (volume_id,))


def import_all(conn, by_volume: dict[int, list[dict]]) -> dict:
    _delete_existing_jod(conn)

    cur = conn.execute(
        "INSERT INTO volumes (name, slug, sort_order) VALUES (?, ?, ?)",
        (VOLUME_NAME, VOLUME_SLUG, 5),
    )
    volume_id = cur.lastrowid

    summary = {"volumes": 0, "discourses": 0, "no_date": 0}

    for vol_num in sorted(by_volume):
        discourses = by_volume[vol_num]
        # Sequential chapter numbers in date order (undated ones sort last,
        # stable by scrape order) - this source doesn't carry the original
        # book's own discourse numbering, unlike the FAIR-index-driven OCR
        # pipeline, so this numbering is this script's own.
        def sort_key(d):
            iso = parse_date(d.get("date"))
            return (iso is None, iso or "")

        discourses.sort(key=sort_key)

        cur = conn.execute(
            "INSERT INTO books (volume_id, testament_id, name, sort_order) VALUES (?, NULL, ?, ?)",
            (volume_id, f"Volume {vol_num}", vol_num),
        )
        book_id = cur.lastrowid

        for i, d in enumerate(discourses, start=1):
            iso_date = parse_date(d.get("date"))
            if iso_date is None:
                summary["no_date"] += 1
            title = d.get("title") or "Untitled"
            speaker = d.get("speaker") or "Unknown"
            text = "\n\n".join(p.strip() for p in d["paragraphs"] if p.strip())
            if not text:
                continue

            cur = conn.execute(
                "INSERT INTO chapters (book_id, chapter_number, title, speaker, discourse_date) "
                "VALUES (?, ?, ?, ?, ?)",
                (book_id, i, title, speaker, iso_date),
            )
            chapter_id = cur.lastrowid
            reference = f"{VOLUME_NAME} 1:{i}"
            conn.execute(
                "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (?, 1, ?, ?)",
                (chapter_id, text, reference),
            )
            summary["discourses"] += 1
        summary["volumes"] += 1

    conn.commit()
    return summary


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    jsonl_path = Path(sys.argv[1])
    db_path = Path(sys.argv[2])

    by_volume = load_discourses(jsonl_path)
    print(f"Loaded {sum(len(v) for v in by_volume.values())} discourses across {len(by_volume)} volumes")

    conn = connect(db_path)
    summary = import_all(conn, by_volume)
    conn.close()

    print()
    print("Import summary:")
    print(f"  Volumes:    {summary['volumes']}")
    print(f"  Discourses: {summary['discourses']}")
    print(f"  No parseable date: {summary['no_date']}")


if __name__ == "__main__":
    main()
