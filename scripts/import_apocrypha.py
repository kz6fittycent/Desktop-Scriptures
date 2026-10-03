#!/usr/bin/env python3
"""Import the Apocrypha of the King James Version into the scriptures
database, as its own volume ("Apocrypha", slug "apocrypha"), after the
Joseph Smith Translation.

Usage:
    python3 scripts/import_apocrypha.py [path-to-db]

path-to-db defaults to data/scriptures.db. Downloads its source each run;
safe to re-run - the volume is replaced.

SOURCE: eBible.org's "King James Version + Apocrypha" (eng-kjv), USFM:
    https://ebible.org/Scriptures/eng-kjv_usfm.zip
the standardized 1769 KJV text, courtesy of the CrossWire Bible Society
and eBible.org - public domain (outside the UK, where the Crown's letters
patent apply only to printing there). The same text as the app's KJV
Bible, so the Apocrypha reads like the rest of it.

BOOKS: the 14 books of the KJV Apocrypha, in the KJV's own order and with
its usual English names, chosen so no reference collides with a Bible
book's ("Rest of Esther", not "Esther"; "Ecclesiasticus", not
"Ecclesiastes"):

    1 Esdras, 2 Esdras, Tobit, Judith, Rest of Esther, Wisdom of Solomon,
    Ecclesiasticus, Baruch, Song of the Three Children, Susanna, Bel and
    the Dragon, Prayer of Manasses, 1 Maccabees, 2 Maccabees

Baruch 6 is the Epistle of Jeremy, as in the KJV. Rest of Esther keeps the
KJV's numbering, chapters 10-16 (continuing Esther, from 10:4).

TEXT: the KJV's italic "supplied" words (USFM \\add) become plain text,
like the rest of the app's KJV; curly quotes become straight ones, to
match it (and so keyword search finds "Israel's" either way).
Ecclesiasticus' two-part prologue becomes chapter 0, shown as "Prologue" -
the same way the Lectures on Faith store their preface - one paragraph per
verse, with its two headings as the chapter's title. Rest of Esther's
notes on where each passage stands in the Greek ("Placed in the Greek
after chap. 3.13 of the Hebrew") are kept as its chapters' titles, shown
under the chapter heading (main_window._chapter_subtitle).

Why include it: Doctrine and Covenants 91 - "There are many things
contained therein that are true... and whoso is enlightened by the Spirit
shall obtain benefit therefrom." The volume's page quotes it.
"""

from __future__ import annotations

import io
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import compact, connect  # noqa: E402

SOURCE_URL = "https://ebible.org/Scriptures/eng-kjv_usfm.zip"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "scriptures.db"
VOLUME_NAME = "Apocrypha"
VOLUME_SLUG = "apocrypha"
# eBible.org refuses Python's default user agent.
USER_AGENT = "Desktop-Scriptures/2.3 (+https://github.com/kz6fittycent/Desktop-Scriptures; KJV Apocrypha import)"

# (USFM book code, this app's book name, chapter count, verse count) in KJV order.
BOOKS = [
    ("1ES", "1 Esdras", 9, 448),
    ("2ES", "2 Esdras", 16, 874),
    ("TOB", "Tobit", 14, 244),
    ("JDT", "Judith", 16, 339),
    ("ESG", "Rest of Esther", 7, 105),
    ("WIS", "Wisdom of Solomon", 19, 436),
    ("SIR", "Ecclesiasticus", 52, 1395),  # with its prologue as chapter 0 (2 paragraphs)
    ("BAR", "Baruch", 6, 213),
    ("S3Y", "Song of the Three Children", 1, 68),
    ("SUS", "Susanna", 1, 64),
    ("BEL", "Bel and the Dragon", 1, 42),
    ("MAN", "Prayer of Manasses", 1, 15),
    ("1MA", "1 Maccabees", 16, 924),
    ("2MA", "2 Maccabees", 15, 555),
]

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def clean(text: str) -> str:
    text = re.sub(r"\\add\*?\s?", "", text)  # supplied words: keep the words, drop the markers
    text = re.sub(r"\\[a-z0-9]+\*?\s?", "", text)  # any other inline marker
    text = text.translate(_QUOTES)
    return re.sub(r"\s+", " ", text).strip()


def heading(text: str) -> str:
    """"[PLACED IN THE GREEK AFTER CHAP. 3.13 OF THE HEBREW]" ->
    "Placed in the Greek after chap. 3.13 of the Hebrew"."""
    text = clean(text).strip("[] ")
    if text.isupper():
        text = text.capitalize()
        for word in ("Greek", "Hebrew", "Chaldee"):
            text = re.sub(rf"\b{word.lower()}\b", word, text)
    return text


def parse_book(usfm: str) -> list[dict]:
    """[{"number": n, "title": str | None, "verses": [(number, text), ...]}].
    Prose before a chapter's first verse (Ecclesiasticus' prologue) becomes
    chapter 0, one paragraph per verse; section headings, and a later
    chapter's unnumbered opening line, become that chapter's title (several
    are joined)."""
    chapters: list[dict] = []
    headings: list[str] = []
    prologue: list[str] = []
    verse: list | None = None
    for line in usfm.splitlines():
        line = line.strip()
        marker = re.match(r"\\(\w+)\s?(.*)", line)
        if not marker:
            if verse is not None and line:
                verse[1] += " " + line
            continue
        tag, rest = marker.groups()
        if tag == "c":
            chapters.append({"number": int(rest.split()[0]), "title": None, "verses": []})
            verse = None
        elif tag in ("s1", "ms1") and chapters:
            headings.append(heading(rest))
        elif tag == "p" and rest and chapters and not chapters[-1]["verses"]:
            # Before the book's first verse it's a prologue; before a later
            # chapter's, a heading ("A Prayer of Jesus the son of Sirach").
            (prologue if len(chapters) == 1 else headings).append(clean(rest))
        elif tag == "v":
            number, _, text = rest.partition(" ")
            if prologue:
                chapters.insert(len(chapters) - 1, {
                    "number": 0, "title": " · ".join(headings),
                    "verses": [(i, p) for i, p in enumerate(prologue, start=1)],
                })
                headings, prologue = [], []
            # The source sometimes repeats a verse's opening as a heading
            # (Baruch 6:1, under "The Epistle of Jeremy") - drop those.
            headings = [h for h in headings if h[:40].lower() != clean(text)[:40].lower()]
            if headings:
                current = chapters[-1]["title"]
                chapters[-1]["title"] = " · ".join(([current] if current else []) + headings)
                headings = []
            verse = [int(number), text]
            chapters[-1]["verses"].append(verse)
    for chapter in chapters:
        chapter["verses"] = [(n, clean(t)) for n, t in chapter["verses"]]
    return chapters


def download_books() -> dict[str, str]:
    print(f"Downloading {SOURCE_URL} ...")
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    texts = {}
    for name in archive.namelist():
        match = re.match(r"\d+-([0-9A-Z]{3})eng-kjv\.usfm$", Path(name).name)
        if match:
            texts[match.group(1)] = archive.read(name).decode("utf-8")
    return texts


def import_apocrypha(conn, texts: dict[str, str]) -> None:
    existing = conn.execute("SELECT id FROM volumes WHERE slug = ?", (VOLUME_SLUG,)).fetchone()
    if existing:
        volume_id = existing[0]
        conn.execute(
            "DELETE FROM verses WHERE chapter_id IN (SELECT c.id FROM chapters c JOIN books b "
            "ON b.id = c.book_id WHERE b.volume_id = ?)", (volume_id,)
        )
        conn.execute("DELETE FROM chapters WHERE book_id IN (SELECT id FROM books WHERE volume_id = ?)", (volume_id,))
        conn.execute("DELETE FROM books WHERE volume_id = ?", (volume_id,))
    else:
        sort_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM volumes").fetchone()[0]
        volume_id = conn.execute(
            "INSERT INTO volumes (name, slug, sort_order) VALUES (?, ?, ?)",
            (VOLUME_NAME, VOLUME_SLUG, sort_order),
        ).lastrowid

    total = 0
    for book_order, (code, name, expected_chapters, expected_verses) in enumerate(BOOKS, start=1):
        chapters = parse_book(texts[code])
        verse_count = sum(len(c["verses"]) for c in chapters)
        if len(chapters) != expected_chapters or verse_count != expected_verses:
            raise SystemExit(
                f"{name}: {len(chapters)} chapters / {verse_count} verses, expected "
                f"{expected_chapters} / {expected_verses} - the source changed; check before importing"
            )
        book_id = conn.execute(
            "INSERT INTO books (volume_id, testament_id, name, sort_order) VALUES (?, NULL, ?, ?)",
            (volume_id, name, book_order),
        ).lastrowid
        for chapter in chapters:
            chapter_id = conn.execute(
                "INSERT INTO chapters (book_id, chapter_number, title) VALUES (?, ?, ?)",
                (book_id, chapter["number"], chapter["title"]),
            ).lastrowid
            conn.executemany(
                "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (?, ?, ?, ?)",
                [(chapter_id, n, text, f"{name} {chapter['number']}:{n}") for n, text in chapter["verses"]],
            )
        total += verse_count
        print(f"  {name}: {len(chapters)} chapter(s), {verse_count} verses")
    conn.commit()
    print(f"Imported {len(BOOKS)} books, {total} verses.")


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB_PATH
    conn = connect(db_path)
    import_apocrypha(conn, download_books())
    compact(conn)
    conn.close()


if __name__ == "__main__":
    main()
