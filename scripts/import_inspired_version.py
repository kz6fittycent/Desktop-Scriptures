#!/usr/bin/env python3
"""Import a book of the Inspired Version (Joseph Smith Translation) into the
Scriptures SQLite DB, as its own volume alongside the existing scripture
volumes. PILOT: built and hand-verified against the whole of Genesis (its
first 8 chapters cross-checked against the Book of Moses text already in
the DB, since Moses 1-8 is drawn from the same underlying JST manuscript;
the rest checked structurally - all 50 chapters present, matching the
book's own chapter count, no verse-count outliers, no misattributed
content - plus spot-checks of exact wording against KJV Genesis for
chapters where the JST tracks it closely, e.g. chapter 49's 33 verses
matching KJV Genesis 49 verse-for-verse). See git history for that pilot.
Not yet run against the rest of the Bible; each new book should get the
same hand-verification before being trusted, since the OCR/layout quirks
below were each found empirically and a new book may have others.

Usage:
    python3 scripts/import_inspired_version.py <book-name> <path-to-djvu.xml> <path-to-db>

Source text: the DjVu XML (word-level OCR, PARAGRAPH-per-print-paragraph
structure - see below for why that matters here) for archive.org item
holyscripturestr00smituoft ("The Holy Scriptures, tr. and cor. by the
spirit of revelation", Plano: Church of Jesus Christ of Latter Day Saints,
1867):
    https://archive.org/download/holyscripturestr00smituoft/holyscripturestr00smituoft_djvu.xml
This is Trinity College Toronto's 500 PPI scan of the RLDS (now Community
of Christ) 1867 FIRST edition - unambiguously public domain (no copyright
renewal is possible for an 1867 work; the item's own metadata records "no
visible notice of copyright"). Community of Christ's copyright claims cover
only later reprints/editions, not this one.

Do NOT substitute the transcription at centerplace.org: it's clean HTML
text and would be far less work than OCR, but the site carries a blanket
"(c) Centerplace.org" notice with no public-domain disclaimer, the same
category of risk the Journal of Discourses importer's docstring rejected
other transcription sites for. Used only as an external QA cross-check
during the pilot, never as the source of record.

TEXT MODEL: unlike Journal of Discourses, this source is genuinely
verse-structured - each print paragraph in this 1867 edition IS one verse
(verse 1 of a chapter is simply unnumbered, matching standard KJV-era
typesetting), so it maps directly onto this schema's normal chapter/verse
shape instead of JoD's one-verse-per-discourse workaround. Each chapter
also has a short italic "argument" (topic summary) in the source, which
gets stored in chapters.title - the same column JoD already repurposes for
its own per-chapter metadata (see schema.sql's comment on that column).

BOUNDARY DETECTION: a chapter's argument line (an em dash joining its topic
phrases, e.g. "Satan tempts man - Cain and Abel...") is the primary
signal, not the "CHAPTER <roman-numeral>" heading text, because the
heading is unreliable in two ways: it's ALSO printed as a running header
at the top of every page within that chapter (appearing again and again,
immediately followed by a bare page number, or - if a page number wasn't
OCR'd separately - by an explicitly-numbered verse; a real chapter start
is never followed directly by verse 2+), and it occasionally gets
column/page-order-shuffled into the middle of an unrelated verse (spotted
once, mid-verse-13 - recognizable because the interrupted verse's
continuation resumes in lowercase, never how a real argument or verse 1
opens). Roman-numeral OCR is also just unreliable on its own (e.g. chapter
III's real heading OCR'd as "err AFTER in."). Single-topic arguments have
no dash (e.g. chapter 1's "History of the creation.", chapter 43's
"Joseph maketh his brethren a feast.") and rely on the heading itself
(once confirmed real by the checks above) to open the chapter instead;
the argument text then simply fills in behind it. An explicit verse
number always wins over a dash-triggered boundary even in the rare verse
that contains a genuine em dash itself (seen once: "...blessed of
thousands - of millions...", Genesis 24:65) - arguments never start with
a number, so checking VERSE_RE first only ever affects real verses.

Occasionally an argument (or a heading+argument pair) gets fragmented
across 3+ separate PARAGRAPH elements instead of the usual 1-2 (seen in
chapters II and XLV/"Joseph is known of his brethren"); title_open()
keeps feeding every following paragraph into the same chapter's title
until it completes. That accumulation stops the moment a paragraph looks
like verse 1 starting (this print always opens verse 1 with a decorative
drop-cap word in small caps, AND/THUS/NOW/etc.) even if the argument's own
tail never completed with real sentence punctuation - otherwise, when an
argument's tail is itself lost to OCR (seen once, chapter L, cut off
mid-hyphen as "...He prophe-"), real verse 1 text would get absorbed into
the chapter title instead of becoming a verse.

A few OCR artifacts get light, targeted cleanup (same "not a full OCR
correction pass" philosophy as the JoD importer): line-wrap dehyphenation,
noise fragments that are pure digits/whitespace/asterisks (page numbers,
sometimes with a stray OCR'd space or asterisk in them), and a
whitelist-based fix for the decorative drop-cap letter sometimes getting
OCR'd as a separate stray letter (e.g. "A ND Abram" -> "AND Abram"). Other
known-uncorrected artifacts: occasional "1" for "I" (digit/letter
confusable in mid-sentence), and the argument lines themselves (set in
italics, so their OCR is noticeably worse than the body text, and in two
chapters - XXXII and L - their last topic phrase never recovered and the
stored title just ends mid-phrase) - both left as-is since neither
affects verse text accuracy.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import connect  # noqa: E402

VOLUME_NAME = "Inspired Version"
VOLUME_SLUG = "inspired-version"
VOLUME_SORT_ORDER = 7

PAGE_NUMBER_RE = re.compile(r"^[\d\s*.]{1,8}$")
HEADING_RE = re.compile(r"^[A-Z]{4,12}\s+[IVXLCDM]+\.?$")
CHAPTER_RANGE_RE = re.compile(r"^CHAPTER\s+[IVXLCDM]+\.?\s*[—–]\s*[IVXLCDM]+\.?$", re.IGNORECASE)
BOOK_TITLE_RE = re.compile(r"^[A-Z]{3,20}\.?$")
SENTENCE_END_RE = re.compile(r"""[.!?:"'”’]$""")
VERSE_RE = re.compile(r"^(\d{1,3})\s+(.*)$")
DASH_RE = re.compile(r"[—–]")
ARGUMENT_LEAD_RE = re.compile(r"^CHAPTER\s+[IVXLCDM]+\.?\s*", re.IGNORECASE)
ARGUMENT_SPLIT_RE = re.compile(r"\.\s+([A-Z]{2,}\b.*)$")
DEHYPHENATE_RE = re.compile(r"(\w)-\s+([a-z]\w*)")
DROPCAP_WORDS = {"AND", "NOW", "THE", "BUT", "FOR", "WHEN", "THUS", "SO", "THEN", "THEREFORE", "YEA"}
DROPCAP_RE = re.compile(r"^([A-Z])\s+([A-Z]{2,})\b(.*)$")


def load_paragraphs(djvu_xml_path: Path) -> list[str]:
    """Reading-order paragraphs, page by page - see module docstring for
    why a paragraph here corresponds to a verse, unlike JoD's prose text."""
    tree = ET.parse(djvu_xml_path)
    paragraphs = []
    for obj in tree.getroot().iter("OBJECT"):
        for para in obj.iter("PARAGRAPH"):
            words = [w.text for w in para.iter("WORD") if w.text]
            if words:
                paragraphs.append(" ".join(words))
    return paragraphs


def header_re_for(book_name: str) -> re.Pattern:
    return re.compile(rf"^\d*\s*{re.escape(book_name.upper())}\.?\s*\d*$")


def clean_text(text: str) -> str:
    text = DEHYPHENATE_RE.sub(r"\1\2", text)
    text = " ".join(text.split())
    m = DROPCAP_RE.match(text)
    if m and (m.group(1) + m.group(2)) in DROPCAP_WORDS:
        text = m.group(1) + m.group(2) + m.group(3)
    return text.strip()


def split_argument(paragraph: str) -> tuple[str, str | None]:
    """An argument paragraph sometimes has a leading 'CHAPTER N.' fragment
    (strip it - cosmetic) and, once seen in the pilot (chapter II), the
    OCR merged the argument and verse 1 into a single PARAGRAPH element -
    split there (see module docstring's BOUNDARY DETECTION note)."""
    text = ARGUMENT_LEAD_RE.sub("", paragraph).strip()
    m = ARGUMENT_SPLIT_RE.search(text)
    if m:
        return text[: m.start() + 1].strip(), m.group(1).strip()
    return text, None


def parse_book(paragraphs: list[str], book_name: str) -> list[dict]:
    header_re = header_re_for(book_name)

    start = None
    for i, p in enumerate(paragraphs):
        if HEADING_RE.match(p.strip().upper()):
            # Chapter 1 has no dash - its argument is whatever short,
            # non-verse paragraph comes right after this heading.
            start = i + 1
            break
    if start is None:
        raise ValueError(f"No chapter heading found for {book_name!r}")

    chapters: list[dict] = []
    current: dict | None = None

    def open_chapter(title: str) -> None:
        nonlocal current
        current = {"title": title, "verses": []}
        chapters.append(current)

    def add_verse_text(text: str) -> None:
        assert current is not None
        current["verses"].append(text)

    def append_to_last_verse(text: str) -> None:
        assert current is not None
        if current["verses"]:
            current["verses"][-1] = f"{current['verses'][-1]} {text}"
        else:
            add_verse_text(text)

    def title_open() -> bool:
        """True while the current chapter's argument is still being
        accumulated: a title has started, no verse has started yet, and
        the title doesn't yet end in sentence-final punctuation. Some
        pages fragment a chapter's heading/argument/verse-1 across 3+
        separate OCR PARAGRAPH elements instead of the usual 1-2 (seen
        once in the pilot, chapter XLV/"Joseph is known of his
        brethren") - this lets every following paragraph keep feeding
        the same argument until it actually completes."""
        return (
            current is not None
            and not current["verses"]
            and bool(current["title"])
            and not SENTENCE_END_RE.search(current["title"])
        )

    def looks_like_verse_start(raw: str) -> bool:
        """This print always opens a chapter's verse 1 with a decorative
        drop-cap word set in small caps (AND/THUS/NOW/...), sometimes
        OCR'd as a lone stray letter plus the rest ("A ND"). An argument
        line's first word is never in caps like this - used to end
        title_open() accumulation even when the argument's own tail was
        lost to OCR (e.g. cut off mid-hyphen), so real verse 1 text never
        gets absorbed into the title (seen once in the pilot, chapter L)."""
        words = raw.split()
        if not words:
            return False
        if len(words) >= 2 and len(words[0]) == 1 and words[0].isupper() and words[1][:1].isupper():
            return True
        first = words[0].rstrip(".,;:")
        return len(first) >= 2 and first.isupper()

    open_chapter("")  # chapter 1, title filled in below

    i = start
    n = len(paragraphs)
    while i < n:
        raw = paragraphs[i].strip()
        i += 1
        if not raw:
            continue
        upper = raw.upper()

        if (
            raw.isupper()
            and BOOK_TITLE_RE.match(upper)
            and not header_re.match(upper)
            and i < n
            and HEADING_RE.match(paragraphs[i].strip().upper())
        ):
            # A bare all-caps title immediately followed by "CHAPTER I." is
            # the next book's own front matter, not this book's content -
            # this book is done (see module docstring's Genesis/Exodus
            # boundary example).
            break

        if PAGE_NUMBER_RE.match(raw):
            continue
        if header_re.match(upper):
            continue
        if CHAPTER_RANGE_RE.match(upper):
            # A page spanning two chapters gets a running header naming
            # both ("CHAPTER XX.-- XXI.") - noise, not a real boundary.
            continue
        if HEADING_RE.match(upper):
            # Real heading vs. noise: a running-header duplicate is
            # immediately followed by a bare page number, or (when a page
            # number wasn't printed/OCR'd separately on that page) by an
            # explicitly-numbered verse - a real chapter start is never
            # followed directly by verse *2+*, only by an argument or
            # verse 1 (always unnumbered in this print). A running header
            # that got column/page-order-shuffled into the middle of a
            # verse (seen once, mid-verse-13 in the pilot) is immediately
            # followed by the interrupted verse's lowercase-starting
            # continuation. None of these three are a real chapter start.
            # A real heading opens a new chapter itself (title filled in
            # as "" for now) - needed for single-topic arguments with no
            # dash to trigger on (e.g. "Joseph maketh his brethren a
            # feast."); a dash-bearing argument right after just fills
            # that title in (see the DASH_RE branch's `else`), so this
            # never double-opens.
            nxt = paragraphs[i].strip() if i < n else ""
            if PAGE_NUMBER_RE.match(nxt):
                i += 1
                continue
            if VERSE_RE.match(nxt):
                continue
            if nxt and nxt[0].islower():
                continue
            open_chapter("")
            continue

        if title_open() and not looks_like_verse_start(raw):
            # Still accumulating the current chapter's argument (see
            # title_open's docstring) - this paragraph either continues
            # it, or completes it and leads into verse 1.
            tail, verse1_lead = split_argument(raw)
            current["title"] = clean_text(f"{current['title']} {tail}")
            if verse1_lead:
                add_verse_text(clean_text(verse1_lead))
            continue

        m = VERSE_RE.match(raw)
        if m:
            # An explicit verse number wins even over a dash - verse text
            # can genuinely contain an em dash itself (seen once in the
            # pilot: "...blessed of thousands - of millions...").  Argument
            # lines never start with a number, so checking this first only
            # ever affects real verses, not chapter boundaries.
            add_verse_text(clean_text(m.group(2)))
            continue

        if DASH_RE.search(raw):
            argument, verse1_lead = split_argument(raw)
            if current is not None and current["verses"]:
                open_chapter(clean_text(argument))
            else:
                current["title"] = clean_text(argument)
            if verse1_lead:
                add_verse_text(clean_text(verse1_lead))
            continue

        # Continuation: either chapter 1's title line (before its verse 1
        # starts), verse 1's un-numbered text, or a wrapped continuation
        # of the previous verse across a page/column break.
        if current is not None and current["title"] == "" and not current["verses"]:
            current["title"] = raw
            continue
        if current is not None and not current["verses"]:
            add_verse_text(clean_text(raw))
        else:
            append_to_last_verse(clean_text(raw))

    for c in chapters:
        c["title"] = (c["title"] or "").strip() or None
    return [c for c in chapters if c["verses"]]


def _get_or_create_volume(conn) -> int:
    row = conn.execute("SELECT id FROM volumes WHERE slug = ?", (VOLUME_SLUG,)).fetchone()
    if row is not None:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO volumes (name, slug, sort_order) VALUES (?, ?, ?)",
        (VOLUME_NAME, VOLUME_SLUG, VOLUME_SORT_ORDER),
    )
    return cur.lastrowid


def _delete_existing_book(conn, volume_id: int, book_name: str) -> None:
    row = conn.execute(
        "SELECT id FROM books WHERE volume_id = ? AND name = ?", (volume_id, book_name)
    ).fetchone()
    if row is None:
        return
    book_id = row["id"]
    chapter_ids = [r["id"] for r in conn.execute("SELECT id FROM chapters WHERE book_id = ?", (book_id,))]
    for chapter_id in chapter_ids:
        verse_ids = [r["id"] for r in conn.execute("SELECT id FROM verses WHERE chapter_id = ?", (chapter_id,))]
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


def import_book(conn, book_name: str, chapters: list[dict]) -> dict:
    volume_id = _get_or_create_volume(conn)
    _delete_existing_book(conn, volume_id, book_name)

    cur = conn.execute(
        "INSERT INTO books (volume_id, testament_id, name, sort_order) VALUES (?, NULL, ?, 1)",
        (volume_id, book_name),
    )
    book_id = cur.lastrowid

    summary = {"chapters": 0, "verses": 0}
    for chapter_number, chapter in enumerate(chapters, start=1):
        cur = conn.execute(
            "INSERT INTO chapters (book_id, chapter_number, title) VALUES (?, ?, ?)",
            (book_id, chapter_number, chapter["title"]),
        )
        chapter_id = cur.lastrowid
        for verse_number, text in enumerate(chapter["verses"], start=1):
            reference = f"{book_name} {chapter_number}:{verse_number}"
            conn.execute(
                "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (?, ?, ?, ?)",
                (chapter_id, verse_number, text, reference),
            )
        summary["chapters"] += 1
        summary["verses"] += len(chapter["verses"])

    conn.commit()
    return summary


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    book_name = sys.argv[1]
    djvu_xml_path = Path(sys.argv[2])
    db_path = Path(sys.argv[3])

    if not djvu_xml_path.exists():
        print(f"Source DjVu XML not found: {djvu_xml_path}")
        sys.exit(1)

    print(f"Parsing {djvu_xml_path} ...")
    paragraphs = load_paragraphs(djvu_xml_path)
    print(f"  {len(paragraphs)} paragraphs in reading order.")

    chapters = parse_book(paragraphs, book_name)

    conn = connect(db_path)
    print(f"Importing Inspired Version, {book_name} ...")
    summary = import_book(conn, book_name, chapters)
    conn.close()

    print()
    print("Import summary:")
    print(f"  Chapters imported: {summary['chapters']}")
    print(f"  Verses imported: {summary['verses']}")
    print()
    print(f"Database written to: {db_path}")


if __name__ == "__main__":
    main()
