#!/usr/bin/env python3
"""Import the Inspired Version (Joseph Smith Translation) into the
Scriptures SQLite DB, as its own volume alongside the existing scripture
volumes. Started as a hand-verified pilot against the whole of Genesis
(its first 8 chapters cross-checked against the Book of Moses text
already in the DB, since Moses 1-8 is drawn from the same underlying JST
manuscript; the rest checked structurally - all 50 chapters present,
matching the book's own chapter count, no verse-count outliers - plus
spot-checks of exact wording against KJV Genesis, e.g. chapter 49's 33
verses matching KJV Genesis 49 verse-for-verse). Generalized from there to
the whole Bible; every book's chapter count is checked automatically
against the KJV's own (see EXPECTED_CHAPTERS and --all's summary output),
and any mismatch is worth a manual look before trusting that book - a new
edge case not covered by the notes below may need its own fix. See git
history for the Genesis pilot commit and the later commit that ran --all
across the rest of the Bible.

KNOWN LIMITATIONS as of that --all run: 61 of the Bible's 66 books
imported (see NOT_TRANSLATED and NEEDS_MANUAL_REVIEW for the other 5).
16 of those 61 still have a chapter-count mismatch, each a low-frequency
OCR/layout quirk not covered by the fixes below (most off by only 1-2
chapters; Psalms is the largest gap, 138 of 150, spread across many
individually-plausible-looking chapters rather than one obvious failure).
A handful of chapter titles also still have a stray leaked verse fragment
in them (rare - search a fresh --all run's imported DB for chapters.title
containing a digit to find current instances) - cosmetic only in most
cases, but a few do cost the chapter its first verse or two. Re-run
--all after any future fix and diff its summary output against this
paragraph before updating it.

Usage:
    python3 scripts/import_inspired_version.py <book-name> <path-to-djvu.xml> <path-to-db>
    python3 scripts/import_inspired_version.py --all <path-to-djvu.xml> <path-to-db>

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
The Psalms use "PSALM <n>." instead of "CHAPTER <n>." for this, and most
psalms' argument is a single short phrase rather than an em-dash list, but
otherwise follow the exact same shape - nothing below is CHAPTER-specific,
it all keys off the heading word generically (HEADING_PREFIX_RE et al).

BOOK BOUNDARIES: each book's own name is used as a running header from
where it starts onward, the same way a chapter's own heading is (see
BOUNDARY DETECTION below) - so finding a book's start means finding the
first occurrence of its name that's followed by real content rather than
by noise (a bare page number, or the previous book's tail continuing in
lowercase - both mean this occurrence is an early running-header
duplicate on the same page the book actually starts on, not the start
itself). find_book_start does this once per book, called in canonical
order with each call's search starting just past the previous book's
start, so the five books whose "core" name collides with another book's
(1/2/3 John vs. the Gospel of John; 1/2 Peter, Samuel, Kings, Chronicles,
Corinthians, Thessalonians, Timothy) still resolve correctly - ordering
disambiguates them, not the numeral, which the print formats
inconsistently anyway ("I. CORINTHIANS.", "1 SAMUEL", or the numeral
dropped entirely on later running headers). A book's real *title* page
(as opposed to its later running headers) is more descriptive than its
bare name - e.g. "THE FIRST BOOK OF SAMUEL." - so the search matches
anything ending in the book's core name, not just the bare name alone.
Since each book's start is known, its end is simply the next book's
start (or end of file, for Revelation) - no separate "did the next book
just start" detection is needed inside the per-book parse at all, unlike
the pilot version of this script.

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
opens). Roman-numeral OCR is also just unreliable on its own (e.g. one
chapter's real heading OCR'd as "err AFTER in.", another's numeral "I."
as "L"). Single-topic arguments have no dash (e.g. "History of the
creation.", "Joseph maketh his brethren a feast.") and rely on the
heading itself (once confirmed real by the checks above) to open the
chapter instead; the argument text then simply fills in behind it. Many
New Testament chapters (and most Psalms) print the heading and argument
as one merged paragraph instead of two ("CHAPTER I. Giving the genealogy
from Abraham until...") - HEADING_PREFIX_RE captures this shape directly,
heading word/numeral/remainder in one match, so it's handled the same way
whether the remainder is empty (bare heading, same disambiguation as
above applies) or not (always a real chapter start; a coincidental
running-header duplicate is never followed by extra merged text). An
explicit verse number always wins over a dash-triggered boundary even in
the rare verse that contains a genuine em dash itself (seen once:
"...blessed of thousands - of millions...", Genesis 24:65) - arguments
never start with a number, so checking VERSE_RE first only ever affects
real verses. The Bible's five one-chapter books (Obadiah, Philemon, 2
John, 3 John, Jude) have no heading/chapter-number at all - their book
title is immediately followed by the argument or verse 1 directly, which
already falls out of the same logic without any special-casing.

Occasionally an argument (or a heading+argument pair) gets fragmented
across 3+ separate PARAGRAPH elements instead of the usual 1-2 (seen in
the pilot); title_open() keeps feeding every following paragraph into the
same chapter's title until it completes. That accumulation stops the
moment a paragraph looks like verse 1 starting (this print always opens
verse 1 with a decorative drop-cap word in small caps, AND/THUS/NOW/etc.)
even if the argument's own tail never completed with real sentence
punctuation - otherwise, when an argument's tail is itself lost to OCR
(seen once, cut off mid-hyphen as "...He prophe-"), real verse 1 text
would get absorbed into the chapter title instead of becoming a verse.

A few OCR artifacts get light, targeted cleanup (same "not a full OCR
correction pass" philosophy as the JoD importer): line-wrap dehyphenation,
noise fragments that are pure digits/whitespace/asterisks (page numbers,
sometimes with a stray OCR'd space or asterisk in them), and a
whitelist-based fix for the decorative drop-cap letter sometimes getting
OCR'd as a separate stray letter (e.g. "A ND Abram" -> "AND Abram"). Other
known-uncorrected artifacts: occasional "1" for "I" (digit/letter
confusable in mid-sentence), and the argument lines themselves (set in
italics, so their OCR is noticeably worse than the body text, and
occasionally their last topic phrase never recovered and the stored title
just ends mid-phrase) - both left as-is since neither affects verse text
accuracy.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import connect  # noqa: E402

VOLUME_NAME = "Joseph Smith Translation"  # display name; most LDS readers won't recognize "Inspired Version"
VOLUME_SLUG = "inspired-version"
VOLUME_SORT_ORDER = 7

# Canonical book list/order and expected chapter counts, pulled from this
# app's existing Holy Bible volume (beandog/lds-scriptures) so the new
# volume's book names, order, and testament grouping match it exactly.
# Expected chapter counts are the KJV's own - a mismatch after import is
# not necessarily wrong (the JST does restructure some chapters, as seen
# throughout Genesis), but it's the signal that a book needs a manual look
# before it's trusted, the same way Genesis's pilot needed one.
OLD_TESTAMENT = [
    ("Genesis", 50), ("Exodus", 40), ("Leviticus", 27), ("Numbers", 36),
    ("Deuteronomy", 34), ("Joshua", 24), ("Judges", 21), ("Ruth", 4),
    ("1 Samuel", 31), ("2 Samuel", 24), ("1 Kings", 22), ("2 Kings", 25),
    ("1 Chronicles", 29), ("2 Chronicles", 36), ("Ezra", 10), ("Nehemiah", 13),
    ("Esther", 10), ("Job", 42), ("Psalms", 150), ("Proverbs", 31),
    ("Ecclesiastes", 12), ("Song of Solomon", 8), ("Isaiah", 66),
    ("Jeremiah", 52), ("Lamentations", 5), ("Ezekiel", 48), ("Daniel", 12),
    ("Hosea", 14), ("Joel", 3), ("Amos", 9), ("Obadiah", 1), ("Jonah", 4),
    ("Micah", 7), ("Nahum", 3), ("Habakkuk", 3), ("Zephaniah", 3),
    ("Haggai", 2), ("Zechariah", 14), ("Malachi", 4),
]
NEW_TESTAMENT = [
    ("Matthew", 28), ("Mark", 16), ("Luke", 24), ("John", 21), ("Acts", 28),
    ("Romans", 16), ("1 Corinthians", 16), ("2 Corinthians", 13),
    ("Galatians", 6), ("Ephesians", 6), ("Philippians", 4), ("Colossians", 4),
    ("1 Thessalonians", 5), ("2 Thessalonians", 3), ("1 Timothy", 6),
    ("2 Timothy", 4), ("Titus", 3), ("Philemon", 1), ("Hebrews", 13),
    ("James", 5), ("1 Peter", 5), ("2 Peter", 3), ("1 John", 5),
    ("2 John", 1), ("3 John", 1), ("Jude", 1), ("Revelation", 22),
]
EXPECTED_CHAPTERS = dict(OLD_TESTAMENT) | dict(NEW_TESTAMENT)

# This 1867 edition omits Song of Solomon entirely (Ecclesiastes XII is
# followed directly by Isaiah's title page, no title page for it anywhere
# in between) - Joseph Smith and the RLDS editors held it wasn't inspired
# scripture, so the translation committee didn't render it. Not a gap in
# this importer; skipped deliberately, everywhere the book list is used.
NOT_TRANSLATED = {"Song of Solomon"}

# This specific scanned copy has a binding/scanning defect around the end
# of the New Testament: content from Revelation's opening chapters, and
# what looks like duplicated leaves of 2 John/3 John, are interleaved at
# paragraph granularity with 2 John, 3 John, and Jude's real text (e.g.
# "THE SECOND EPISTLE OF JOHN." and "REVELATION."/"CHAPTER II." each
# appear twice, out of order, a few dozen paragraphs apart) - not
# something a text-parsing heuristic can safely reorder, since doing so
# risks silently misattributing real verse text between books. Skipped
# here rather than importing corrupted/misattributed text; needs either a
# second scan of this specific section or manual reconstruction to fix.
NEEDS_MANUAL_REVIEW = {"2 John", "3 John", "Jude", "Revelation"}

def is_page_number(raw: str) -> bool:
    """A bare page number, possibly with a little OCR noise around/inside
    it (whitespace, asterisks, periods, or a stray misread digit-like
    symbol such as "$" for "8") - checked by shape (short, digit-majority,
    no letters) rather than an exact character class, since enumerating
    every digit confusable this OCR happens to produce isn't tractable."""
    raw = raw.strip()
    if not raw or len(raw) > 8 or any(c.isalpha() for c in raw):
        return False
    non_digits = sum(1 for c in raw if not c.isdigit())
    return non_digits <= 2 and non_digits < len(raw)
TINY_FRAGMENT_RE = re.compile(r"^[A-Za-z][.,;:']?$")
HEADING_PREFIX_RE = re.compile(r"^([A-Z]{4,12})\s+([IVXLCDM]+)\.?(?:\s+(.+))?$")
CHAPTER_RANGE_RE = re.compile(r"^[A-Z]{4,12}\s+[IVXLCDM]+\.?\s*[—–]\s*[IVXLCDM]+\.?$")
TITLE_PAGE_RE = re.compile(r"^[A-Z][A-Z0-9 .,';]{2,100}$")
SENTENCE_END_RE = re.compile(r"""[.!?:"'”’]$""")
VERSE_RE = re.compile(r"^(\d{1,3})\s+(.*)$")
DASH_RE = re.compile(r"[—–]")
ARGUMENT_SPLIT_RE = re.compile(r"\.\s+([A-Z]{2,}\b.*)$")
GARBLED_HEADING_LEAD_RE = re.compile(r"^[A-Z]{4,12}\s+\S{1,6}\.?\s+(?=\S)")
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


def _book_core(book_name: str) -> str:
    """Drops a leading ordinal ("1 Samuel" -> "SAMUEL") - the print's own
    running headers vary in how (or whether) they render the ordinal, so
    matching on the core name alone is what's actually reliable. Safe
    because this is only ever applied to occurrences from find_book_start
    onward in canonical order (see module docstring's BOOK BOUNDARIES)."""
    return re.sub(r"^[123]\s+", "", book_name).upper()


def header_re_for(book_name: str) -> re.Pattern:
    # The Gospels' running headers add a "ST." prefix ("ST. MARK.").
    core = _book_core(book_name)
    return re.compile(rf"^(?:ST\.?\s+)?[\dIVXLCDM]*\.?\s*{re.escape(core)}\.?\s*\d*$")


def _levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def _title_matches_book(title: str, core: str) -> bool:
    """Fuzzy, not exact - a book's own name is just as OCR-fallible as any
    other word (seen once: Ruth's title page reading "...OF KUTH."). Most
    title pages end with the book's name ("THE BOOK OF JOSHUA."), but not
    all - Lamentations' is "THE LAMENTATIONS OF JEREMIAH.", so this checks
    for the name as any word in the title, not just its last one."""
    words = title.rstrip(".").replace(",", "").split()
    threshold = max(1, len(core) // 6)
    return any(_levenshtein(w, core) <= threshold for w in words)


def find_book_start(paragraphs: list[str], book_name: str, search_from: int = 0) -> int:
    """A book's real title page is a full descriptive phrase ("THE FIRST
    BOOK OF SAMUEL."), never just its bare running-header name - that
    distinction matters for the numbered books (1/2 Samuel, 1/2 Kings,
    1/2 Chronicles, 1/2 Corinthians, 1/2 Thessalonians, 1/2 Timothy, 1/2
    Peter, 2/3 John), where the bare header is the SAME word for both
    ("SAMUEL." alone, no ordinal) and would otherwise match on any of the
    first book's own internal chapter transitions, not just the second
    book's real start."""
    core = _book_core(book_name)
    min_words = 3 if re.match(r"^[123]\s", book_name) else 1
    n = len(paragraphs)
    for i in range(search_from, n - 1):
        p = paragraphs[i].strip()
        if not p or not p.isupper() or not TITLE_PAGE_RE.match(p):
            continue
        if p[-1].isdigit():
            # The New Testament's own front-matter table of contents lists
            # every book by name with a trailing page/writing-order number
            # ("TESTIMONY OF MATTHEW 89") - a real title always ends in
            # punctuation, never a bare number.
            continue
        if len(p.split()) < min_words:
            continue
        if not _title_matches_book(p, core):
            continue
        nxt = paragraphs[i + 1].strip()
        if not nxt or is_page_number(nxt) or VERSE_RE.match(nxt) or nxt[0].islower():
            continue  # an early running-header duplicate, not the real start
        return i
    raise ValueError(f"No title page found for {book_name!r} (search_from={search_from})")


def clean_text(text: str) -> str:
    text = DEHYPHENATE_RE.sub(r"\1\2", text)
    text = " ".join(text.split())
    m = DROPCAP_RE.match(text)
    if m and (m.group(1) + m.group(2)) in DROPCAP_WORDS:
        text = m.group(1) + m.group(2) + m.group(3)
    return text.strip()


def split_argument(text: str) -> tuple[str, str | None]:
    """Once seen in the pilot, the OCR merged an argument's tail and
    verse 1's start into a single PARAGRAPH element - split there (see
    module docstring's last-but-one paragraph). Only reached (via the
    DASH_RE branch) when HEADING_PREFIX_RE already failed to match, so a
    leading heading word is also stripped here with a looser pattern that
    doesn't require a valid-looking roman numeral - covers a heading
    whose numeral OCR'd badly enough that HEADING_PREFIX_RE couldn't
    recognize it as one, but which still has a real, dashed argument
    right behind it (e.g. "CHAPTER Ill. Aaron maketh a calf - ...")."""
    text = GARBLED_HEADING_LEAD_RE.sub("", text)
    m = ARGUMENT_SPLIT_RE.search(text)
    if m:
        return text[: m.start() + 1].strip(), m.group(1).strip()
    return text.strip(), None


def parse_book(paragraphs: list[str], book_name: str, start: int, end: int) -> list[dict]:
    header_re = header_re_for(book_name)

    chapters: list[dict] = []
    current: dict | None = None

    def open_chapter(title: str) -> None:
        nonlocal current
        current = {"title": title, "verses": []}
        chapters.append(current)

    def add_verse_text(text: str) -> None:
        nonlocal current
        if current is None:
            # A book can start with real content before any heading/
            # argument is recognized - seen once, Isaiah 1: the scan's own
            # page order is scrambled and verses 12-26 appear before the
            # chapter heading and verses 1-11 (a defect in the source scan
            # itself, not something reorderable here). Opening an untitled
            # chapter here avoids losing/crashing on that content instead.
            open_chapter("")
        current["verses"].append(text)

    def append_to_last_verse(text: str) -> None:
        if current is not None and current["verses"]:
            current["verses"][-1] = f"{current['verses'][-1]} {text}"
        else:
            add_verse_text(text)

    def title_open() -> bool:
        """True while the current chapter's argument is still being
        accumulated: a title has started, no verse has started yet, and
        the title doesn't yet end in sentence-final punctuation. Some
        pages fragment a chapter's heading/argument/verse-1 across 3+
        separate OCR PARAGRAPH elements instead of the usual 1-2 - this
        lets every following paragraph keep feeding the same argument
        until it actually completes."""
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
        gets absorbed into the title."""
        words = raw.split()
        if not words:
            return False
        if len(words) >= 2 and len(words[0]) == 1 and words[0].isupper() and words[1][:1].isupper():
            return True
        first = words[0].rstrip(".,;:")
        return len(first) >= 2 and first.isupper()

    i = start
    while i < end:
        raw = paragraphs[i].strip()
        i += 1
        if not raw:
            continue
        upper = raw.upper()

        if is_page_number(raw):
            continue
        if TINY_FRAGMENT_RE.match(raw):
            # A lone stray letter with nothing else - a decorative
            # drop-cap or margin mark that landed in its own PARAGRAPH
            # element instead of merging with the word it belongs to (the
            # same artifact DROPCAP_RE fixes when it's merged - see
            # clean_text). No real verse, title, or argument is ever this
            # short, so this is always noise.
            continue
        if header_re.match(upper):
            continue
        if CHAPTER_RANGE_RE.match(upper):
            # A page spanning two chapters gets a running header naming
            # both ("CHAPTER XX.-- XXI.") - noise, not a real boundary.
            continue

        heading = HEADING_PREFIX_RE.match(raw)
        if heading:
            remainder = heading.group(3)
            if remainder:
                # Heading and argument merged in one paragraph (common in
                # the New Testament and Psalms) - always a real chapter
                # start; a coincidental running-header duplicate is never
                # followed by extra merged text.
                argument, verse1_lead = split_argument(remainder)
                if current is None or current["verses"]:
                    open_chapter(clean_text(argument))
                else:
                    current["title"] = clean_text(argument)
                if verse1_lead:
                    add_verse_text(clean_text(verse1_lead))
                continue

            # Bare heading: real vs. noise. A running-header duplicate is
            # immediately followed by a bare page number, or (when a page
            # number wasn't printed/OCR'd separately on that page) by an
            # explicitly-numbered verse - a real chapter start is never
            # followed directly by verse *2+*, only by an argument or
            # verse 1 (always unnumbered in this print). A running header
            # that got column/page-order-shuffled into the middle of a
            # verse is immediately followed by the interrupted verse's
            # lowercase-starting continuation. None of these three are a
            # real chapter start. A real heading opens a new chapter
            # itself (title filled in as "" for now) - needed for
            # single-topic arguments with no dash to trigger on; a
            # dash-bearing argument right after just fills that title in,
            # so this never double-opens.
            nxt = paragraphs[i].strip() if i < end else ""
            if is_page_number(nxt):
                i += 1
                continue
            if VERSE_RE.match(nxt):
                continue
            if nxt and nxt[0].islower():
                continue
            open_chapter("")
            continue

        if title_open() and not looks_like_verse_start(raw) and not VERSE_RE.match(raw):
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
            remainder = m.group(2).strip()
            if len(remainder) <= 3 or header_re.match(remainder.upper()):
                # A page number merged with noise - either a printer's
                # signature mark (page-bottom letter/number combinations
                # used for collating a book's printed sections, e.g. "49
                # 2M") or the book's own running header ("13 ST. MARK").
                # No real verse is ever this short.
                continue
            # An explicit verse number wins even over a dash - verse text
            # can genuinely contain an em dash itself (seen once in the
            # pilot: "...blessed of thousands - of millions...").  Argument
            # lines never start with a number, so checking this first only
            # ever affects real verses, not chapter boundaries.
            add_verse_text(clean_text(remainder))
            continue

        if DASH_RE.search(raw):
            argument, verse1_lead = split_argument(raw)
            if current is None or current["verses"]:
                open_chapter(clean_text(argument))
            else:
                current["title"] = clean_text(argument)
            if verse1_lead:
                add_verse_text(clean_text(verse1_lead))
            continue

        # Continuation: either a still-untitled chapter's title line
        # (before its verse 1 starts), verse 1's un-numbered text, or a
        # wrapped continuation of the previous verse across a page/column
        # break. Also covers the Bible's five one-chapter books, whose
        # title is followed directly by the argument/verse 1 with no
        # heading/chapter-number at all.
        if current is None:
            open_chapter("")
        if current["title"] == "" and not current["verses"]:
            current["title"] = raw
            continue
        if not current["verses"]:
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


def _get_or_create_testament(conn, volume_id: int, name: str, sort_order: int) -> int:
    slug = name.lower().replace(" ", "-")
    row = conn.execute(
        "SELECT id FROM testaments WHERE volume_id = ? AND name = ?", (volume_id, name)
    ).fetchone()
    if row is not None:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO testaments (volume_id, name, slug, sort_order) VALUES (?, ?, ?, ?)",
        (volume_id, name, slug, sort_order),
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


def import_book(
    conn, book_name: str, chapters: list[dict], testament_id: int | None, sort_order: int
) -> dict:
    volume_id = _get_or_create_volume(conn)
    _delete_existing_book(conn, volume_id, book_name)

    cur = conn.execute(
        "INSERT INTO books (volume_id, testament_id, name, sort_order) VALUES (?, ?, ?, ?)",
        (volume_id, testament_id, book_name, sort_order),
    )
    book_id = cur.lastrowid

    summary = {"chapters": 0, "verses": 0, "empty_titles": 0}
    for chapter_number, chapter in enumerate(chapters, start=1):
        cur = conn.execute(
            "INSERT INTO chapters (book_id, chapter_number, title) VALUES (?, ?, ?)",
            (book_id, chapter_number, chapter["title"]),
        )
        chapter_id = cur.lastrowid
        if not chapter["title"]:
            summary["empty_titles"] += 1
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


def _report(book_name: str, summary: dict) -> None:
    expected = EXPECTED_CHAPTERS.get(book_name)
    flag = "" if summary["chapters"] == expected else "  <-- MISMATCH"
    print(
        f"  {book_name:<20} {summary['chapters']:>3} chapters "
        f"(expected {expected:>3}), {summary['verses']:>4} verses, "
        f"{summary['empty_titles']} untitled{flag}"
    )


def import_all(paragraphs: list[str], conn) -> None:
    volume_id = _get_or_create_volume(conn)
    ot_id = _get_or_create_testament(conn, volume_id, "Old Testament", 1)
    nt_id = _get_or_create_testament(conn, volume_id, "New Testament", 2)

    # One flat, in-order pass: each book's end is simply the next book's
    # start (or end of file, for Revelation) - see module docstring's
    # BOOK BOUNDARIES.
    ot_names = [name for name, _ in OLD_TESTAMENT if name not in NOT_TRANSLATED]
    nt_names = [name for name, _ in NEW_TESTAMENT if name not in NOT_TRANSLATED]
    all_books = [(name, ot_id, i + 1) for i, name in enumerate(ot_names)] + [
        (name, nt_id, i + 1) for i, name in enumerate(nt_names)
    ]

    search_from = 0
    testament_label = None
    for idx, (book_name, testament_id, sort_order) in enumerate(all_books):
        label = "Old Testament" if testament_id == ot_id else "New Testament"
        if label != testament_label:
            print(f"{label}:")
            testament_label = label
        # Boundaries are computed for every book, including ones skipped
        # below - a skipped book's neighbors still need its start to know
        # where their own content ends (see NEEDS_MANUAL_REVIEW's note).
        start = find_book_start(paragraphs, book_name, search_from)
        if idx + 1 < len(all_books):
            end = find_book_start(paragraphs, all_books[idx + 1][0], start + 1)
        else:
            end = len(paragraphs)
        search_from = start + 1

        if book_name in NEEDS_MANUAL_REVIEW:
            print(f"  {book_name:<20} skipped - needs manual review (see NEEDS_MANUAL_REVIEW)")
            continue

        chapters = parse_book(paragraphs, book_name, start, end)
        summary = import_book(conn, book_name, chapters, testament_id, sort_order)
        _report(book_name, summary)


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

    conn = connect(db_path)

    if book_name == "--all":
        import_all(paragraphs, conn)
        conn.close()
        print()
        print(f"Database written to: {db_path}")
        return

    if book_name in NOT_TRANSLATED:
        print(f"{book_name!r} isn't in this edition (see NOT_TRANSLATED in the module docstring).")
        sys.exit(1)
    if book_name in NEEDS_MANUAL_REVIEW:
        print(f"{book_name!r} needs manual review before importing (see NEEDS_MANUAL_REVIEW in the module docstring).")
        sys.exit(1)

    all_books = [b for b in OLD_TESTAMENT + NEW_TESTAMENT if b[0] not in NOT_TRANSLATED]
    names = [b for b, _ in all_books]
    if book_name not in names:
        print(f"Unknown book {book_name!r}. Use --all, or one of: {', '.join(names)}")
        sys.exit(1)
    idx = names.index(book_name)
    start = find_book_start(paragraphs, book_name)
    if idx + 1 < len(all_books):
        end = find_book_start(paragraphs, all_books[idx + 1][0], start + 1)
    else:
        end = len(paragraphs)
    ot_names = [b for b, _ in OLD_TESTAMENT if b not in NOT_TRANSLATED]
    is_ot = book_name in ot_names
    sort_order = ot_names.index(book_name) + 1 if is_ot else names.index(book_name) - len(ot_names) + 1
    volume_id = _get_or_create_volume(conn)
    testament_id = _get_or_create_testament(
        conn, volume_id, "Old Testament" if is_ot else "New Testament", 1 if is_ot else 2
    )

    chapters = parse_book(paragraphs, book_name, start, end)
    print(f"Importing Joseph Smith Translation, {book_name} ...")
    summary = import_book(conn, book_name, chapters, testament_id, sort_order)
    conn.close()

    print()
    print("Import summary:")
    print(f"  Chapters imported: {summary['chapters']} (expected {EXPECTED_CHAPTERS.get(book_name)})")
    print(f"  Verses imported: {summary['verses']}")
    if summary["empty_titles"]:
        print(f"  Chapters with no title captured: {summary['empty_titles']}")
    print()
    print(f"Database written to: {db_path}")


if __name__ == "__main__":
    main()
