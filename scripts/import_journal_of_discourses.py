#!/usr/bin/env python3
"""Import a Journal of Discourses volume into the Scriptures SQLite DB,
alongside the existing scripture volumes. Generalized across all 26
volumes - originally built and hand-verified against Volume 1 alone (see
git history for that pilot), then extended to the rest without
hand-verifying each one's boundary detection individually.

Usage:
    python3 scripts/import_journal_of_discourses.py <volume_number> <path-to-djvu.xml> <path-to-db>

Source text: download the DjVu XML (word-level OCR with per-word
confidence and column/paragraph structure - NOT the flat "djvu.txt",
which linearizes this book's two-column pages into corrupted,
column-interleaved lines) for the matching archive.org item, e.g. for
Volume 1: per_utah-and-the-mormons_journal-of-discourses-_brigham-young-_1854_1
    https://archive.org/download/<item>/<item>_djvu.xml
All 26 items follow that same "..._brigham-young-_<year>_<volume>" naming
and were found via archive.org's search API filtered to
title:(journal of discourses) AND creator:(brigham young) - confirmed
against each item's own `volume` metadata field. That 1850s-80s scan is
unambiguously public domain.

Do NOT substitute a transcription from fairlatterdaysaints.org (explicit
"no portion of this site may be reproduced" footer notice) or
scriptures.byu.edu (its /about panel carries its own "Copyright ... All
rights reserved" notice on the Scripture Citation Index, which includes
its own JoD transcription) - both considered and rejected for this
reason. contentdm.lib.byu.edu (BYU Library's own scan) was also
considered, but its robots.txt disallows /utils/, the path its file
downloads live under.

Discourse metadata (which discourse number has which speaker/date/title)
comes from data/journal_of_discourses_index.json, cross-referenced from
each volume's FAIR index page - factual metadata only (who/when/title),
never discourse prose, per the same reasoning as the General Conference
citation harvester.

COVERAGE: not every discourse in every volume gets a located boundary -
this script's detection (a "DELIVERED BY"-style header regex plus a
looser dateline heuristic, cross-checked against the volume's FAIR
speaker sequence via a two-pointer greedy match) typically locates most
but not all of a volume's discourses; the rest use non-standard 1850s-80s
headers it doesn't catch reliably enough to place with confidence, so
they're skipped rather than risked with a guessed boundary. Chapter
numbers preserve the original discourse numbering (with gaps) rather
than renumbering sequentially, so missing ones can slot in later.

TEXT MODEL: unlike scripture, a JoD "verse" isn't a meaningful unit - a
discourse is a continuous sermon, not a series of numbered statements -
so each imported discourse is a single `verses` row (verse_number=1)
holding the whole thing as one page of prose, paragraph breaks kept as
blank lines within it. This still gets FTS5 search, notes, tags, and
highlights for free through the same `verses` table scripture uses -
nothing schema-side is JoD-specific.

OCR QUALITY: uneven across the whole series, same as Volume 1 (see that
pilot's notes) - mostly coherent, some pages show visible column-
detection corruption. Cleanup here is deliberately light: dehyphenation
across line breaks, dropping running-header/page-number noise
paragraphs, re-merging paragraphs the OCR itself split mid-sentence, and
stripping stray "|" (2-column bleed-through), "^", and "/" characters
that are never legitimate in this book's prose - not a full OCR
correction pass.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import connect  # noqa: E402

INDEX_PATH = PROJECT_ROOT / "data" / "journal_of_discourses_index.json"

VOLUME_NAME = "Journal of Discourses"
VOLUME_SLUG = "journal-of-discourses"

# ---------------------------------------------------------------------
# Discourse boundary detection (generalized from the Volume 1 pilot)
# ---------------------------------------------------------------------

HEADER_RE = re.compile(r"DELIVERED BY", re.IGNORECASE)
YEAR_RE = re.compile(r"18[4-9][0-9]")
BYLINE_CONTEXT_WORDS = ("TABERNACLE", "CONFERENCE", "LAKE", "JURY", "TRIAL")
MERGE_WINDOW = 4  # merge candidate indices within this many paragraphs of each other

RUNNING_HEADER_RE = re.compile(
    r"^\d*\s*(JOURNAL OF DISCOURSES\.?,?|DISCOURSES\.?)\s*$", re.IGNORECASE
)
PAGE_NUMBER_RE = re.compile(r"^\d+$")
DEHYPHENATE_RE = re.compile(r"(\w)-\s+([a-z]\w*)")
NOISE_CHARS_RE = re.compile(r"[|^/]")
SENTENCE_END_RE = re.compile(r"""[.!?:"'”’]$""")
BYLINE_FRAGMENT_MAX_LEN = 60
MAX_BYLINE_FRAGMENTS_SKIPPED = 3


def load_paragraphs(djvu_xml_path: Path) -> list[str]:
    """Reading-order paragraphs (page by page, column by column, as the
    scan's own OCR already ordered them) - this is the DjVu XML's actual
    value over the flat djvu.txt export, which loses that column
    structure and interleaves text from side-by-side columns."""
    tree = ET.parse(djvu_xml_path)
    paragraphs = []
    for obj in tree.getroot().iter("OBJECT"):
        for para in obj.iter("PARAGRAPH"):
            words = [w.text for w in para.iter("WORD") if w.text]
            if words:
                paragraphs.append(" ".join(words))
    return paragraphs


def find_candidate_boundaries(paragraphs: list[str]) -> list[int]:
    """Two signals, merged: an explicit "...DELIVERED BY..." byline
    (the reliable one), and a looser one for discourses phrased
    differently (mission reports, trial transcripts, etc.) - any short
    paragraph mentioning a plausible year and a typical dateline context
    word. Candidates within MERGE_WINDOW of each other collapse to one
    (both signals often fire near the same real boundary)."""
    delivered = {
        i for i, p in enumerate(paragraphs) if i > 60 and HEADER_RE.search(p)
    }
    byline = set()
    for i, p in enumerate(paragraphs):
        if i <= 60 or len(p) > 250:
            continue
        if YEAR_RE.search(p) and any(w in p.upper() for w in BYLINE_CONTEXT_WORDS):
            byline.add(i)

    merged: list[int] = []
    for i in sorted(delivered | byline):
        if merged and i - merged[-1] <= MERGE_WINDOW:
            continue
        merged.append(i)
    return merged


def speaker_markers(speaker: str) -> list[str]:
    """Substrings to look for in a byline window to confirm this speaker
    - first name/initial-set tried before the bare surname, since two
    different discourse authors sharing a surname (e.g. Orson Pratt and
    Parley P. Pratt) is common in this series. Used only as a fallback
    when title matching can't be attempted - see match_boundaries_to_index."""
    clean = re.sub(r"[.,]", "", speaker.upper())
    parts = [p for p in clean.split() if p not in ("JUN", "SEN", "JR", "SR")]
    if not parts:
        return []
    markers = []
    if len(parts) >= 2:
        markers.append(parts[0])  # first name/initial - more specific
    markers.append(parts[-1])  # surname - fallback
    return markers


# Title matching is the primary signal (see match_boundaries_to_index for
# why speaker alone fails badly on single-speaker-dominated volumes).
TITLE_LOOKAHEAD = 8
TITLE_MIN_SCORE = 2  # overlapping significant words required, floored to len(fair_words) if shorter
TITLE_STOPWORDS = {
    "THE", "AND", "OF", "A", "IN", "TO", "ETC", "ON", "BY", "FOR", "WITH",
    "HIS", "HER", "THEIR", "IS", "ARE", "AS", "AT", "OR", "AN", "BE", "IT",
    "ITS", "FROM", "THAT", "THIS", "WE", "OUR", "US", "ALL", "NOT", "BUT",
}
OCR_TITLE_FRAGMENT_MAX_LEN = 90
MAX_TITLE_FRAGMENTS = 3


def _normalize_title_words(text: str) -> set[str]:
    words = re.sub(r"[^A-Z0-9 ]", " ", text.upper()).split()
    return {w for w in words if len(w) >= 3 and w not in TITLE_STOPWORDS}


def _extract_ocr_title(paragraphs: list[str], boundary: int) -> str:
    """Walks backward from the paragraph just before a candidate's byline,
    collecting consecutive short/mostly-uppercase fragments (a printed
    title is often OCR'd as 2-3 separate PARAGRAPH elements, e.g.
    "LIBERTY AND PERSECUTION—" then "CONDUCT OF THE U.S. GOVERNMENT,
    ETC.") - stops at the first paragraph that looks like real body
    prose, i.e. the previous discourse's last paragraph."""
    fragments = []
    i = boundary - 1
    while i >= 0 and len(fragments) < MAX_TITLE_FRAGMENTS:
        p = paragraphs[i]
        if not _looks_like_title_leak(p):
            break
        fragments.insert(0, p)
        i -= 1
    return " ".join(fragments)


def match_boundaries_to_index(
    paragraphs: list[str], candidates: list[int], index: list[dict]
) -> dict[int, int]:
    """For each candidate boundary, find which upcoming FAIR entry it is
    by TITLE word-overlap first, not speaker - speaker-only matching
    (the original approach) falls apart on volumes where one speaker
    gives 80+ of ~90 discourses (Brigham Young dominates many volumes),
    since "this byline mentions YOUNG" then carries almost no
    information about *which* of his discourses it is. Titles are
    unique per discourse even when speakers repeat.

    Matching isn't restricted to the very next unconsumed FAIR entry -
    order is still a real constraint (discourses appear in the book in
    the same order FAIR lists them), so a lookahead window of the next
    TITLE_LOOKAHEAD unconsumed entries is scored and the best one above
    threshold wins, then the pointer advances to just past it (entries
    skipped over stay unconsumed, i.e. not imported this pass - see the
    module docstring's COVERAGE note). Falls back to the old
    speaker-marker check, bounded to the same window, only when OCR
    title extraction found nothing usable for this candidate."""
    fair_ptr = 0
    boundaries: dict[int, int] = {}
    for h in candidates:
        window_entries = index[fair_ptr : fair_ptr + TITLE_LOOKAHEAD]
        if not window_entries:
            break

        ocr_title = _extract_ocr_title(paragraphs, h)
        ocr_words = _normalize_title_words(ocr_title)

        found_offset = None
        if ocr_words:
            best_offset, best_score = None, 0
            for offset, entry in enumerate(window_entries):
                fair_words = _normalize_title_words(entry["title"])
                if not fair_words:
                    continue
                score = len(ocr_words & fair_words)
                threshold = min(TITLE_MIN_SCORE, len(fair_words))
                if score >= threshold and score > best_score:
                    best_offset, best_score = offset, score
            found_offset = best_offset

        if found_offset is None:
            # Fallback: OCR title was empty/garbage for this candidate -
            # try the speaker marker instead, same bounded window.
            byline_window = " ".join(paragraphs[max(0, h - 2) : h + 3]).upper()
            for offset, entry in enumerate(window_entries):
                markers = speaker_markers(entry["speaker"])
                if markers and any(m in byline_window for m in markers):
                    found_offset = offset
                    break

        if found_offset is not None:
            matched = window_entries[found_offset]
            boundaries[matched["number"]] = h
            fair_ptr = fair_ptr + found_offset + 1
    return boundaries


# ---------------------------------------------------------------------
# Body text extraction / cleanup
# ---------------------------------------------------------------------


def _looks_like_title_leak(paragraph: str) -> bool:
    if len(paragraph) > 90:
        return False
    letters = [c for c in paragraph if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) > 0.7


def clean_paragraph(paragraph: str) -> str:
    text = DEHYPHENATE_RE.sub(r"\1\2", paragraph)
    text = NOISE_CHARS_RE.sub(" ", text)
    return " ".join(text.split())


def _skip_byline_tail(raw: list[str]) -> list[str]:
    skipped = 0
    while raw and skipped < MAX_BYLINE_FRAGMENTS_SKIPPED and len(raw[0]) < BYLINE_FRAGMENT_MAX_LEN:
        raw = raw[1:]
        skipped += 1
    return raw


def _merge_split_sentences(body: list[str]) -> list[str]:
    merged: list[str] = []
    for p in body:
        if merged and not SENTENCE_END_RE.search(merged[-1]) and p[:1].islower():
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return merged


def extract_body_paragraphs(paragraphs: list[str], start: int, end: int) -> list[str]:
    raw = _skip_byline_tail(paragraphs[start:end])
    if raw and _looks_like_title_leak(raw[-1]):
        raw = raw[:-1]

    body = []
    for p in raw:
        if RUNNING_HEADER_RE.match(p) or PAGE_NUMBER_RE.match(p):
            continue
        cleaned = clean_paragraph(p)
        if cleaned:
            body.append(cleaned)
    return _merge_split_sentences(body)


# ---------------------------------------------------------------------
# DB import
# ---------------------------------------------------------------------


def _get_or_create_volume(conn) -> int:
    row = conn.execute("SELECT id FROM volumes WHERE slug = ?", (VOLUME_SLUG,)).fetchone()
    if row is not None:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO volumes (name, slug, sort_order) VALUES (?, ?, ?)",
        (VOLUME_NAME, VOLUME_SLUG, 5),
    )
    return cur.lastrowid


def _delete_existing_book(conn, volume_id: int, book_name: str) -> None:
    """Scoped to ONE book ("Volume N") - deletes/replaces only that
    volume's chapters/verses/related notes-tags-highlights, so
    re-running this for one volume never touches any other already-
    imported volume. (An earlier version of this script deleted the
    whole Journal of Discourses volume row on every run, which was fine
    for iterating on Volume 1 alone but would have destroyed every other
    already-imported volume the moment a second one was imported.)"""
    row = conn.execute(
        "SELECT id FROM books WHERE volume_id = ? AND name = ?", (volume_id, book_name)
    ).fetchone()
    if row is None:
        return
    book_id = row["id"]
    chapter_ids = [
        r["id"] for r in conn.execute("SELECT id FROM chapters WHERE book_id = ?", (book_id,))
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
    conn.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))
    conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()


def import_volume(conn, volume_number: int, paragraphs: list[str]) -> dict:
    all_volumes = json.loads(INDEX_PATH.read_text())["volumes"]
    index_list = all_volumes[str(volume_number)]
    index = {d["number"]: d for d in index_list}

    book_name = f"Volume {volume_number}"
    volume_id = _get_or_create_volume(conn)
    _delete_existing_book(conn, volume_id, book_name)

    cur = conn.execute(
        "INSERT INTO books (volume_id, testament_id, name, sort_order) VALUES (?, NULL, ?, ?)",
        (volume_id, book_name, volume_number),
    )
    book_id = cur.lastrowid

    candidates = find_candidate_boundaries(paragraphs)
    boundaries = match_boundaries_to_index(paragraphs, candidates, index_list)
    ordered_numbers = sorted(boundaries)

    summary = {
        "volume": volume_number,
        "total_discourses": len(index_list),
        "discourses": 0,
        "paragraphs": 0,
        "empty_body": [],
    }

    for i, number in enumerate(ordered_numbers):
        start = boundaries[number]
        end = (
            boundaries[ordered_numbers[i + 1]]
            if i + 1 < len(ordered_numbers)
            else len(paragraphs)
        )
        entry = index[number]
        body = extract_body_paragraphs(paragraphs, start + 1, end)
        if not body:
            summary["empty_body"].append(number)
            continue

        cur = conn.execute(
            "INSERT INTO chapters (book_id, chapter_number, title, speaker, discourse_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (book_id, number, entry["title"], entry["speaker"], entry["date"]),
        )
        chapter_id = cur.lastrowid

        full_text = "\n\n".join(body)
        reference = f"{VOLUME_NAME} 1:{number}"
        conn.execute(
            "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (?, 1, ?, ?)",
            (chapter_id, full_text, reference),
        )
        summary["discourses"] += 1
        summary["paragraphs"] += len(body)

    conn.commit()
    return summary


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    volume_number = int(sys.argv[1])
    djvu_xml_path = Path(sys.argv[2])
    db_path = Path(sys.argv[3])

    if not djvu_xml_path.exists():
        print(f"Source DjVu XML not found: {djvu_xml_path}")
        sys.exit(1)

    print(f"Parsing {djvu_xml_path} ...")
    paragraphs = load_paragraphs(djvu_xml_path)
    print(f"  {len(paragraphs)} paragraphs in reading order.")

    conn = connect(db_path)
    print(f"Importing Journal of Discourses, Volume {volume_number} ...")
    summary = import_volume(conn, volume_number, paragraphs)
    conn.close()

    print()
    print("Import summary:")
    print(f"  Discourses imported: {summary['discourses']} of {summary['total_discourses']}")
    print(f"  Paragraphs imported: {summary['paragraphs']}")
    if summary["empty_body"]:
        print(f"  Located but empty (skipped): {sorted(summary['empty_body'])}")
    print()
    print(f"Database written to: {db_path}")


if __name__ == "__main__":
    main()
