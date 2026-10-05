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

KNOWN LIMITATIONS: all 61 imported books have the KJV's chapter count;
about 160 verse numbers are missing across the whole JST (shown as gaps,
never renumbered around) - 24 of them Judges 9:1-24, a leaf missing from
this copy of the scan, and most of the rest a verse the OCR merged into
its neighbour past recovering. 2 John, 3 John, Jude and Revelation are
still skipped (NEEDS_MANUAL_REVIEW). --all prints each book's missing
verse numbers and the scan defects it worked around.

VERSE NUMBERS (2.3.1 rewrite of parse_book): the printed chapter and verse
numbers are followed, not counted. Before, verses were numbered 1, 2, 3...
in the order found, so one misread number or chapter heading ("CHAPTER
H." for II) merged text and shifted every verse after it - 145 chapters
came out short (1 Chronicles 2 had a single verse). Now:

- A chapter heading's numeral is read through its usual OCR misreadings
  (H or U for II, T or l for I...). One that repeats the current chapter's
  number, or is followed by the current chapter's next verse, is a running
  header; a heading followed by running text rather than an argument is
  one too.
- A verse is taken at its printed number when that number comes next (or
  within a few, past ones the OCR lost). Misread numbers ("i:>", "U1")
  are recognized by shape and position; a number the OCR fused into the
  previous paragraph ("...need. 36 And Joses...") is split back out; a
  number misread inside the text ("...brethren. o And...") is found
  between a sentence's end and a usual verse opening (fill_gaps).
- Numbering that restarts at 2 means a chapter began whose heading was
  unreadable; its verse 1 (and argument) are recovered from the end of
  the chapter before. Numbering that jumps back and carries on is a
  chapter whose opening the scan lacks (Judges 9), or a hole the scan's
  out-of-order columns left (Mark 14: 47, 59-82, then 48-58).
- Scan defects handled explicitly: Isaiah 1:12-26 bound ahead of the
  book's first heading (merged into chapter 1), and Jude's verses
  interleaved into 1 John's last page (dropped).

The older notes below (BOUNDARY DETECTION onward) still describe the
argument/drop-cap handling, which carried over.

A re-import renumbers verses, so the Topical Guide's JST entries are
re-pointed at the verse now holding their text (repoint_topic_verses), and
existing installs are brought along by db.sync_bundled_content: changed
text is updated, a reader's notes and highlights follow the text they were
made on, and verses that no longer exist are removed.

OCR CLEANUP: scripts/clean_inspired_version_text.py is a second pass over
the imported text (split words, stray symbols, misread letters, the
chapter summaries' italic misreadings) - run it after any re-import.

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

import difflib
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import compact, connect  # noqa: E402

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


ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
# What OCR reads for roman-numeral letters in a chapter heading.
NUMERAL_FIXES = [("H", "II"), ("U", "II"), ("N", "II"), ("T", "I"), ("l", "I"), ("1", "I"), ("J", "I"),
                 ("!", "I"), ("|", "I"), ("i", "I"), ("Y", "V"), ("K", "X"), ("x", "X"), ("v", "V")]
HEADING_RE = re.compile(r"^(C[A-Z]{5,7}|[A-Z]HAPTER|PSALM)\s+([A-Za-z0-9!|]{1,9})[.,]?(?:\s+(.*))?$")
LEAD_NUM_RE = re.compile(r"^(\S{1,4})\s+(.+)$", re.S)
DIGIT_LIKE = str.maketrans({"l": "1", "I": "1", "i": "1", "O": "0", "o": "0", "S": "5", "B": "8", "Z": "2", "z": "2", "G": "6", "b": "6", "q": "9", "g": "9", "J": "1", "!": "1", "|": "1", "t": "1"})


def roman_value(token: str) -> int | None:
    token = token.strip(".,")
    for seen, meant in NUMERAL_FIXES:
        token = token.replace(seen, meant)
    if not token or any(c not in ROMAN for c in token):
        return None
    total = 0
    for a, b in zip(token, token[1:] + " "):
        v = ROMAN[a]
        total += -v if b != " " and ROMAN.get(b, 0) > v else v
    return total


def number_value(token: str) -> int | None:
    t = token.rstrip(".,")
    if t.isdigit():
        return int(t)
    mapped = t.translate(DIGIT_LIKE)
    return int(mapped) if mapped.isdigit() else None


def parse_book(
    paragraphs: list[str], book_name: str, start: int, end: int, expected_chapters: int
) -> tuple[list[dict], list[str]]:
    """One book's chapters - [{"title": str | None, "verses": {number: text}}]
    - and a log of the scan defects worked around. See the module
    docstring's VERSE NUMBERS for how chapters and verses are found."""
    header_re = header_re_for(book_name)
    chapters: list[dict] = []
    cur: dict | None = None
    log: list[str] = []

    def new_chapter(title: str = "") -> None:
        nonlocal cur
        cur = {"title": title, "verses": {}, "last": 0, "title_open": True}
        chapters.append(cur)

    def add(num: int, text: str) -> None:
        cur["verses"][num] = text
        cur["last"] = num
        cur["title_open"] = False
        split_fused()

    def append(text: str) -> None:
        if cur["last"]:
            cur["verses"][cur["last"]] += BREAK + text
            split_fused()
        else:
            add(1, text)

    def split_fused() -> None:
        """A next verse whose number the OCR ran into this paragraph
        ("...as he had need. 36 And Joses...")."""
        while True:
            text = cur["verses"][cur["last"]]
            m = None
            for found in re.finditer(r"[.;:?!,]\s+(\d{1,3})\s+(?=[A-Z(])", text):
                value = int(found.group(1))
                # The next number - or a jump past numbers the OCR lost,
                # when the one after it follows in the same text.
                if value in cur["verses"]:
                    continue
                if value == cur["last"] + 1 or (
                    cur["last"] + 1 < value <= cur["last"] + 15
                    and re.search(rf"[.;:?!,]\s+{value + 1}\s+[A-Z(]", text[found.end():])
                ):
                    m = found
                    break
            if not m:
                return
            nxt_no = int(m.group(1))
            cur["verses"][cur["last"]] = text[: m.start() + 1].strip()
            cur["verses"][nxt_no] = text[m.end():].strip()
            cur["last"] = nxt_no

    i = start + 1  # past the book's title page
    paras = paragraphs
    while i < end:
        raw = paras[i].strip()
        i += 1
        if not raw or _is_noise(raw) or TINY_FRAGMENT_RE.match(raw):
            continue
        upper = raw.upper()
        if header_re.match(upper) or CHAPTER_RANGE_RE.match(upper):
            continue

        heading = HEADING_RE.match(raw)
        if heading and heading.group(1) != "PSALM" and _levenshtein(heading.group(1), "CHAPTER") > 2:
            heading = None
        if heading:
            value = roman_value(heading.group(2))
            rest = heading.group(3)
            if rest and not re.match(r"[A-Z(]", rest):
                # Not an argument but the page's text running on - a page
                # number and a continuation after a running header
                # ("CHAPTER XXVI. 829 sea causeth his waves...").
                if cur is not None and cur["verses"]:
                    append(clean_text(re.sub(r"^\S*\d\S*\s+", "", rest)))
                continue
            # (Not counting verses bound in ahead of the book's first
            # heading - see the end of this function.)
            current_no = len(chapters) - (1 if chapters and 1 not in chapters[0]["verses"] else 0)
            nxt = _next_real(paras, i, end, header_re)
            # A running header: the current chapter's numbering carries on
            # right after it (maybe past one continuation line).
            following = _next_reals(paras, i, end, header_re, 2)
            continues = _continues(following[0], cur) or (
                len(following) > 1 and not _looks_like_verse_start(following[0])
                and not HEADING_RE.match(following[0]) and _continues(following[1], cur)
            )
            if continues and not rest:
                continue  # a running header: the current chapter goes on
            if value is not None and value == current_no and cur is not None and cur["verses"] and not rest:
                continue  # the running header repeats the current chapter's own number
            real = False
            if value is not None and value == current_no + 1:
                real = not (VERSE_RE.match(nxt) and number_value(nxt.split()[0]) not in (None, 1)
                            and cur is not None and number_value(nxt.split()[0]) == cur["last"] + 1) and not (nxt[:1].islower() and not rest)
            elif rest:
                real = True
            else:
                nv = VERSE_RE.match(nxt)
                real = not (is_page_number(nxt) or (nv and cur is not None and cur["last"]) or nxt[:1].islower())
            if not real:
                continue
            new_chapter()
            if rest:
                argument, verse1 = split_argument(rest)
                cur["title"] = clean_text(argument)
                if verse1:
                    add(1, clean_text(verse1))
            continue

        raw = re.sub(r"^[A-Za-z]\s+(?=\d{1,3}\s)", "", raw)  # a stray mark before a verse number
        if cur is None and LEAD_NUM_RE.match(raw) and raw.split()[0].isdigit():
            new_chapter()  # a book whose first pages are out of order (Isaiah)
        m = LEAD_NUM_RE.match(raw)
        if m and cur is not None:
            value = number_value(m.group(1))
            text = m.group(2).strip()
            if value is not None and len(text) > 3 and not header_re.match(text.upper()):
                # The next number not yet seen: after filling a hole the
                # scan's columns left (Mark 14: 47, 59-82, then 48-58),
                # numbering resumes past the highest.
                expected = cur["last"] + 1
                if expected in cur["verses"]:
                    expected = max(cur["verses"]) + 1
                plain_digits = m.group(1).rstrip(".,").isdigit()
                if value == expected or (plain_digits and expected < value <= expected + 3) or (
                    plain_digits and not cur["verses"] and 1 < value < 200 and not cur["title"]
                ):
                    add(value, clean_text(text))
                    continue
                if plain_digits and value < cur["last"] and value not in cur["verses"] and value - 1 in cur["verses"]:
                    log.append(f"filled a hole at {value}: {raw[:50]}")
                    add(value, clean_text(text))
                    continue
                if plain_digits and 3 < value < cur["last"] - 1 and _continues_from(
                    _next_reals(paras, i, end, header_re, 1)[0], value
                ):
                    # Numbering jumps back and carries on: the next chapter,
                    # whose opening the scan lacks (Judges 9:1-24 - a
                    # missing page).
                    log.append(f"restart mid-chapter: {raw[:60]}")
                    new_chapter()
                    add(value, clean_text(text))
                    continue
                if text[:1].islower() and not plain_digits or (plain_digits and value > 200):
                    # A page number fused onto a continuation ("80S king").
                    append(clean_text(text))
                    continue
                if plain_digits and value == 2 and cur["last"] >= 3 and cur["verses"]:
                    # Numbering restarted without a heading we could read:
                    # a new chapter, whose unnumbered verse 1 went onto the
                    # previous chapter's last verse.
                    log.append(f"chapter start found by numbering: {raw[:60]}")
                    prev = cur
                    tail = prev.get("last_para_start")
                    title = ""
                    if tail is None:
                        last_text = prev["verses"][prev["last"]]
                        pieces = last_text.split(BREAK)
                        start_at = next(
                            (k for k in range(len(pieces) - 1, 0, -1) if _looks_like_verse_start(pieces[k])), None
                        )
                        if start_at is not None:
                            # Before verse 1: maybe the lost heading's argument.
                            if start_at > 1 and DASH_RE.search(pieces[start_at - 1]):
                                title = clean_text(pieces[start_at - 1])
                                start_at -= 1
                                pieces[start_at] = ""
                            prev["verses"][prev["last"]] = BREAK.join(pieces[:start_at])
                            last_text = BREAK.join(pieces[:start_at]) + BREAK + BREAK.join(p for p in pieces[start_at:] if p)
                            prev["verses"][prev["last"]] = last_text
                            tail = len(BREAK.join(pieces[:start_at])) + 1
                        else:
                            # Argument and verse 1 in one paragraph, after the
                            # last verse: "...my father. for his father—
                            # Jacob is revived... nnHEN Joseph could not..."
                            argument, verse1_text = split_argument(pieces[-1], LOOSE_SPLIT_RE)
                            if len(pieces) > 1 and verse1_text and DASH_RE.search(argument):
                                title = clean_text(argument)
                                prev["verses"][prev["last"]] = BREAK.join(pieces[:-1])
                                last_text = prev["verses"][prev["last"]] + BREAK + verse1_text
                                prev["verses"][prev["last"]] = last_text
                                tail = len(last_text) - len(verse1_text)
                            else:
                                found = DROPCAP_INSIDE_RE.search(last_text)
                                tail = found.start() + 1 if found else None
                    verse1 = ""
                    if tail is not None:
                        last_text = prev["verses"][prev["last"]]
                        verse1 = last_text[tail:].strip()
                        prev["verses"][prev["last"]] = last_text[:tail].strip()
                    new_chapter()
                    cur["title"] = title
                    add(1, verse1 or "")
                    add(2, clean_text(text))
                    continue

        if cur is None:
            new_chapter()

        nxt = _next_real(paras, i, end, header_re)
        if DASH_RE.search(raw) and not cur["verses"] or (
            DASH_RE.search(raw) and cur["verses"] and _looks_like_argument(raw)
            and (split_argument(raw)[1] or _looks_like_verse_start(nxt))
            and not _continues(nxt, cur)
        ):
            argument, verse1 = split_argument(raw)
            if cur["verses"]:
                new_chapter()
            cur["title"] = clean_text(f"{cur['title']} {argument}".strip())
            if verse1:
                add(1, clean_text(verse1))
            continue

        if not cur["verses"]:
            # Before verse 1: the argument, or verse 1 itself (drop cap).
            if cur["title_open"] and not _looks_like_verse_start(raw) and not SENTENCE_END_RE.search(cur["title"] or " "):
                argument, verse1 = split_argument(raw)
                cur["title"] = clean_text(f"{cur['title']} {argument}".strip())
                if verse1:
                    add(1, clean_text(verse1))
                continue
            if cur["title_open"] and not cur["title"] and not _looks_like_verse_start(raw):
                cur["title"] = clean_text(raw)
                continue
            add(1, clean_text(raw))
            continue
        # A capitalized drop-cap paragraph could be the next chapter's
        # unnumbered verse 1 - remember where it starts.
        if _looks_like_verse_start(raw):
            cur["last_para_start"] = len(cur["verses"][cur["last"]]) + 1
        append(clean_text(raw))

    chapters = [c for c in chapters if c["verses"]]
    # The scan's own defects (see the module docstring):
    # - verses bound in ahead of a book's first heading (Isaiah 1:12-26)
    #   belong to chapter 1;
    if len(chapters) > expected_chapters and 1 not in chapters[0]["verses"]:
        stray = chapters.pop(0)
        for number, text in stray["verses"].items():
            chapters[0]["verses"].setdefault(number, text)
        log.append(f"merged {len(stray['verses'])} verses bound ahead of chapter 1")
    # - a run of another book's verses past the last chapter (Jude's,
    #   interleaved into 1 John's last pages).
    while len(chapters) > expected_chapters and 1 not in chapters[-1]["verses"]:
        dropped = chapters.pop()
        log.append(f"dropped {len(dropped['verses'])} trailing verses from another book")
    # A chapter whose verse 1 is still empty: it went onto the previous
    # chapter's last verse, after that chapter's own text - from the
    # last drop-cap opening there.
    for before, c in zip(chapters, chapters[1:]):
        if c["verses"].get(1, "x").strip():
            continue
        last = max(before["verses"])
        text = before["verses"][last]
        found = list(re.finditer(r"[.,;:]\s+([a-zA-Z~'\"\\_^]{0,3}[A-Z]{2,}\s+[A-Za-z])", text))
        if found and len(text) - found[-1].start(1) > 20:
            cut = found[-1].start(1)
            c["verses"][1] = text[cut:]
            before["verses"][last] = text[:cut].rstrip()
            log.append(f"verse 1 recovered from the previous chapter: {text[cut:cut + 40]!r}")
    for c in chapters:
        c["title"] = (c["title"] or "").strip() or None
        c.pop("last_para_start", None)
        fill_gaps(c["verses"], log)
        c["verses"] = {
            n: _strip_headers(" ".join(t.replace(BREAK, " ").split()), book_name)
            for n, t in sorted(c["verses"].items())
        }
    return chapters, log


def _looks_like_verse_start(raw: str) -> bool:
    words = raw.split()
    if not words:
        return False
    # A drop cap the OCR garbled: "nnHEN", "fTlHEN", "rT\"OW".
    if len(words) >= 2 and re.match(r"^[a-zA-Z~'\"\\_^]{1,3}[A-Z]{2,}[,.]?$", words[0]) and words[1][:1].islower():
        return True
    if len(words) >= 2 and len(words[0]) == 1 and words[0].isupper() and words[1][:1].isupper():
        return True
    first = words[0].rstrip(".,;:")
    return len(first) >= 2 and first.isupper() and first not in ("LORD", "GOD", "I")


def _looks_like_argument(raw: str) -> bool:
    # An argument: capitalized phrases joined by dashes, no verse-like opening.
    return raw[:1].isupper() and raw.count("—") + raw.count("–") >= 1 and len(raw) < 400


DROPCAP_WORD = r"(?:[A-Z]\s?[A-Z]{1,}|[a-zA-Z~'\"\\_]{0,3}[A-Z]{2,})"
ARGUMENT_SPLIT_RE = re.compile(r"[.,]\s+(" + DROPCAP_WORD + r"\s+[a-z].*)$")
# Looser, for a chapter start already known to be lost in the last verse.
LOOSE_SPLIT_RE = re.compile(r"[.,]\s+(" + DROPCAP_WORD + r"\s+[A-Za-z].*)$")
DROPCAP_INSIDE_RE = re.compile(r"[.;:?]\s+(?:[A-Z]\s?)?[A-Z]{2,}\s+[a-z]")


def split_argument(text: str, pattern=None) -> tuple[str, str | None]:
    """An argument and the start of verse 1 OCR'd into one paragraph:
    split where a drop-cap word (AND, A ND, npHEN...) follows a sentence."""
    text = GARBLED_HEADING_LEAD_RE.sub("", text)
    m = (pattern or ARGUMENT_SPLIT_RE).search(text)
    if m:
        return text[: m.start() + 1].strip(), m.group(1).strip()
    return text.strip(), None


def _next_real(paras, i, end, header_re) -> str:
    while i < end:
        p = paras[i].strip()
        i += 1
        if not p or _is_noise(p) or TINY_FRAGMENT_RE.match(p) or header_re.match(p.upper()):
            continue
        return p
    return ""


def _continues(nxt: str, cur) -> bool:
    """The next paragraph is the current chapter's next numbered verse -
    or opens with what can only be a misread verse number ("U1")."""
    m = LEAD_NUM_RE.match(nxt)
    if not (cur and cur["last"] and m):
        return False
    token = m.group(1)
    if number_value(token) in (cur["last"] + 1, cur["last"] + 2):
        return True
    return len(token) <= 3 and any(c.isdigit() for c in token) and not token.isdigit()


def _next_reals(paras, i, end, header_re, count: int) -> list[str]:
    found = []
    while i < end and len(found) < count:
        p = paras[i].strip()
        i += 1
        if not p or _is_noise(p) or TINY_FRAGMENT_RE.match(p) or header_re.match(p.upper()):
            continue
        found.append(p)
    return found or [""]


def _continues_from(nxt: str, value: int) -> bool:
    m = LEAD_NUM_RE.match(nxt)
    return bool(m and number_value(m.group(1)) in (value + 1, value + 2))


# A page number the OCR misread ("80S", "U1"): a short token with a digit in it.
PAGE_LIKE_RE = re.compile(r"^(?=\S*\d)[A-Za-z0-9$]{1,4}$")


def _is_noise(p: str) -> bool:
    return is_page_number(p) or bool(PAGE_LIKE_RE.match(p.strip()))


VERSE_OPENERS = (
    r"(?:And|But|For|Then|Now|Wherefore|Therefore|Behold|Yea|Thus|So|Neither|Nevertheless|"
    r"Verily|Ye|They|He|She|It|Let|Who|What|How|If|When|Because)"
)
BREAK = "\u2029"  # a paragraph break in the scan, kept until the end
GARBLED_NUMBER_RE = re.compile(r"^(\S{1,4})\s+(?=[A-Z(])")
RUNNING_HEADER_IN_TEXT_RE = re.compile(
    r"\s*\bC[A-Z]{5,7}\s+[IVXLCDMHT1l]{1,8}\.?(?:\s*[—–-]+\s*[IVXLCDMHT1l]{1,8}\.?)?(?=\s|$)"
)


def fill_gaps(verses: dict, log: list) -> None:
    """A verse number the OCR misread ("i:>" for 13) left that verse inside
    the one before: split it back out at the paragraph that opens with
    something that can't be a word."""
    for number in sorted(verses):
        missing = number + 1
        if missing in verses or missing + 1 not in verses:
            continue
        pieces = verses[number].split(BREAK)
        for k in range(1, len(pieces)):
            m = GARBLED_NUMBER_RE.match(pieces[k])
            if m and not m.group(1).isalpha() and not m.group(1).lower() in ("o", "a", "i"):
                verses[number] = BREAK.join(pieces[:k])
                verses[missing] = BREAK.join([pieces[k][m.end():]] + pieces[k + 1:])
                log.append(f"recovered verse {missing}: {m.group(1)!r}")
                break
        else:
            # Inside the text: a misread number ("o", "0", "1 5", "l6")
            # between a sentence's end and a usual verse opening.
            m = re.search(
                r"[.;:?!]\s+((?:\d\s)?[0-9oOlI|]{1,3})\s+(?=" + VERSE_OPENERS + r"\b)",
                verses[number],
            )
            if m and not re.fullmatch(r"[OI]", m.group(1)):
                text = verses[number]
                verses[number] = text[: m.start() + 1]
                verses[missing] = text[m.end():]
                log.append(f"recovered verse {missing} mid-text: {m.group(1)!r}")


def _strip_headers(text: str, book_name: str) -> str:
    """A running header the OCR placed mid-verse: a chapter's ("...at thy
    CHAPTER XL.— XL1 command") or the book's own, in capitals ("...to use
    THE ACTS. them despitefully")."""
    text = RUNNING_HEADER_IN_TEXT_RE.sub("", text)
    core = re.escape(_book_core(book_name))
    text = re.sub(rf"\s+(?:ST\.\s+|THE\s+|[IV1]+\.\s+)?{core}\.(?=\s|$)", "", text)
    return text.strip()


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
            conn.execute("UPDATE journal_entries SET verse_id = NULL WHERE verse_id = ?", (verse_id,))
        conn.execute("DELETE FROM notes WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM tag_assignments WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM reading_log WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM reading_history WHERE chapter_id = ?", (chapter_id,))
        conn.execute("UPDATE journal_entries SET chapter_id = NULL WHERE chapter_id = ?", (chapter_id,))
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
        for verse_number, text in chapter["verses"].items():
            reference = f"{book_name} {chapter_number}:{verse_number}"
            conn.execute(
                "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (?, ?, ?, ?)",
                (chapter_id, verse_number, text, reference),
            )
        summary["chapters"] += 1
        summary["verses"] += len(chapter["verses"])

    conn.commit()
    return summary


def _report(book_name: str, summary: dict, chapters: list[dict], notes: list[str]) -> None:
    expected = EXPECTED_CHAPTERS.get(book_name)
    flag = "" if summary["chapters"] == expected else "  <-- MISMATCH"
    missing = sum(
        1 for c in chapters for n in range(1, max(c["verses"]) + 1) if n not in c["verses"]
    )
    print(
        f"  {book_name:<20} {summary['chapters']:>3} chapters "
        f"(expected {expected:>3}), {summary['verses']:>4} verses, "
        f"{missing} verse numbers missing, {summary['empty_titles']} untitled{flag}"
    )
    for note in notes:
        if not note.startswith(("recovered", "filled", "chapter start")):
            print(f"      {note}")


def _jst_texts(conn) -> dict[str, tuple[str, str]]:
    return {
        r["reference"]: (r["name"], r["text"])
        for r in conn.execute(
            "SELECT b.name, v.reference, v.text FROM verses v JOIN chapters c ON c.id = v.chapter_id "
            "JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id WHERE vol.slug = ?",
            (VOLUME_SLUG,),
        )
    }


def repoint_topic_verses(conn, before: dict[str, tuple[str, str]]) -> None:
    """The Topical Guide lists some JST verses by reference
    (build_topical_guide.py); a re-import can renumber them. Each is
    re-pointed at the verse that now holds the text it was chosen for, or
    dropped if no verse does."""
    after: dict[str, list[tuple[str, str]]] = {}
    for reference, (book, text) in _jst_texts(conn).items():
        after.setdefault(book, []).append((reference, text))
    moved = dropped = 0
    for row in conn.execute(
        "SELECT id, reference FROM topic_verses WHERE volume_slug = ?", (VOLUME_SLUG,)
    ).fetchall():
        book, old_text = before.get(row["reference"], (None, None))
        if old_text is None:
            continue
        words = set(old_text.lower().split())
        candidates = sorted(after.get(book, []), key=lambda rt: -len(words & set(rt[1].lower().split())))[:10]
        best = max(
            candidates, key=lambda rt: difflib.SequenceMatcher(None, old_text, rt[1]).ratio(), default=None
        )
        if best is None or difflib.SequenceMatcher(None, old_text, best[1]).ratio() < 0.6:
            conn.execute("DELETE FROM topic_verses WHERE id = ?", (row["id"],))
            dropped += 1
        elif best[0] != row["reference"]:
            try:
                conn.execute("UPDATE topic_verses SET reference = ? WHERE id = ?", (best[0], row["id"]))
                moved += 1
            except sqlite3.IntegrityError:  # the topic already lists that verse
                conn.execute("DELETE FROM topic_verses WHERE id = ?", (row["id"],))
                dropped += 1
    conn.commit()
    print(f"Topical Guide: {moved} JST verse(s) re-pointed after renumbering, {dropped} dropped.")


def import_all(paragraphs: list[str], conn) -> None:
    before = _jst_texts(conn)
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

        chapters, notes = parse_book(paragraphs, book_name, start, end, EXPECTED_CHAPTERS[book_name])
        summary = import_book(conn, book_name, chapters, testament_id, sort_order)
        _report(book_name, summary, chapters, notes)

    repoint_topic_verses(conn, before)


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
        compact(conn)
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

    chapters, _notes = parse_book(paragraphs, book_name, start, end, EXPECTED_CHAPTERS[book_name])
    print(f"Importing Joseph Smith Translation, {book_name} ...")
    summary = import_book(conn, book_name, chapters, testament_id, sort_order)
    compact(conn)
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
