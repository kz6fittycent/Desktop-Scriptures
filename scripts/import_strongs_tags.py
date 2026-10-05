#!/usr/bin/env python3
"""Tag the King James Bible word by word with Strong's numbers, so Word
Study can show the exact Hebrew, Aramaic or Greek word behind a word in a
particular verse - not just every word the KJV translates that way.

Usage:
    python3 scripts/import_strongs_tags.py [path-to-db]

path-to-db defaults to data/scriptures.db. Downloads its source each run;
safe to re-run - the tags are replaced.

SOURCE: eBible.org's "King James Version + Apocrypha" (eng-kjv), USFM -
the same download scripts/import_apocrypha.py uses:
    https://ebible.org/Scriptures/eng-kjv_usfm.zip
Every translated word is marked with its Strong's number(s), e.g.
\\w beginning|strong="H7225"\\w*. The text and its tagging are courtesy of
the CrossWire Bible Society and eBible.org, public domain (outside the UK,
where the Crown's letters patent apply only to printing there). The
lexicon the numbers point into is scripts/import_lexicon.py's.

ALIGNMENT: the app's own KJV text (beandog/lds-scriptures) is the same
1769 text but not character for character the same - spelling, italics,
punctuation. So the tags aren't copied by position: each verse's words
are aligned with the source's (difflib, by lowercase word), and a tag
goes on the app's word wherever the words match. A word the two texts
spell differently is left untagged rather than guessed at.

The Joseph Smith Translation keeps most of the KJV's wording, so its
verses aren't stored: data_access.get_word_strongs aligns a JST verse with
the KJV verse of the same reference when asked, and its matching words
get the same tags. Words the JST added or changed get none - they have no
Hebrew or Greek behind them.

STORAGE: word_tags, one row per KJV verse - (volume slug, reference,
tags), where tags is "3:H7225 4:H430 9:H853,H5414 ..." - the position of
a word among the verse's words (data_access.WORD_RE, from 0) and its
Strong's numbers, without the source's leading zeros, as lexicon_entries
stores them. Word positions rather than character offsets keep it about
half the size.
"""

from __future__ import annotations

import difflib
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
# eBible.org refuses Python's default user agent.
USER_AGENT = "Desktop-Scriptures/2.3 (+https://github.com/kz6fittycent/Desktop-Scriptures; Strong's tags import)"

# USFM book codes for the 66 books, in the app's book names.
BOOK_CODES = {
    "GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers", "DEU": "Deuteronomy",
    "JOS": "Joshua", "JDG": "Judges", "RUT": "Ruth", "1SA": "1 Samuel", "2SA": "2 Samuel",
    "1KI": "1 Kings", "2KI": "2 Kings", "1CH": "1 Chronicles", "2CH": "2 Chronicles", "EZR": "Ezra",
    "NEH": "Nehemiah", "EST": "Esther", "JOB": "Job", "PSA": "Psalms", "PRO": "Proverbs",
    "ECC": "Ecclesiastes", "SNG": "Song of Solomon", "ISA": "Isaiah", "JER": "Jeremiah",
    "LAM": "Lamentations", "EZK": "Ezekiel", "DAN": "Daniel", "HOS": "Hosea", "JOL": "Joel",
    "AMO": "Amos", "OBA": "Obadiah", "JON": "Jonah", "MIC": "Micah", "NAM": "Nahum",
    "HAB": "Habakkuk", "ZEP": "Zephaniah", "HAG": "Haggai", "ZEC": "Zechariah", "MAL": "Malachi",
    "MAT": "Matthew", "MRK": "Mark", "LUK": "Luke", "JHN": "John", "ACT": "Acts", "ROM": "Romans",
    "1CO": "1 Corinthians", "2CO": "2 Corinthians", "GAL": "Galatians", "EPH": "Ephesians",
    "PHP": "Philippians", "COL": "Colossians", "1TH": "1 Thessalonians", "2TH": "2 Thessalonians",
    "1TI": "1 Timothy", "2TI": "2 Timothy", "TIT": "Titus", "PHM": "Philemon", "HEB": "Hebrews",
    "JAS": "James", "1PE": "1 Peter", "2PE": "2 Peter", "1JN": "1 John", "2JN": "2 John",
    "3JN": "3 John", "JUD": "Jude", "REV": "Revelation",
}

from scriptures.data_access import WORD_RE as _WORD_RE  # noqa: E402
_TAGGED_RE = re.compile(r'\\\+?w ([^|\\]+)\|strong="([^"]+)"\\\+?w\*')


def strongs_numbers(value: str) -> list[str]:
    """'H0853 H5414' -> ['H853', 'H5414'] (the lexicon's own form)."""
    numbers = []
    for part in value.replace(",", " ").split():
        m = re.fullmatch(r"([HG])0*(\d+)[a-z]?", part.strip())
        if m:
            numbers.append(f"{m.group(1)}{m.group(2)}")
    return numbers


def parse_usfm(usfm: str) -> dict[tuple[int, int], list[tuple[str, list[str]]]]:
    """(chapter, verse) -> the verse's words in order, each with the
    Strong's numbers on it ([] for an untranslated or supplied word)."""
    verses: dict[tuple[int, int], list[tuple[str, list[str]]]] = {}
    chapter = 0
    key = None
    for line in usfm.splitlines():
        line = line.strip()
        m = re.match(r"\\c (\d+)", line)
        if m:
            chapter = int(m.group(1))
            continue
        m = re.match(r"\\v (\d+)\s?(.*)", line)
        if m:
            key = (chapter, int(m.group(1)))
            verses[key] = []
            line = m.group(2)
        elif key is None or not line or line.startswith(("\\s", "\\ms", "\\mt", "\\h", "\\toc", "\\id")):
            continue
        # Footnotes and cross-references aren't part of the verse.
        line = re.sub(r"\\f .*?\\f\*", "", line)
        line = re.sub(r"\\x .*?\\x\*", "", line)
        pos = 0
        for tag in _TAGGED_RE.finditer(line):
            for word in _WORD_RE.findall(_strip_markers(line[pos:tag.start()])):
                verses[key].append((word, []))
            numbers = strongs_numbers(tag.group(2))
            for word in _WORD_RE.findall(tag.group(1)):
                verses[key].append((word, numbers))
            pos = tag.end()
        for word in _WORD_RE.findall(_strip_markers(line[pos:])):
            verses[key].append((word, []))
    return verses


def _strip_markers(text: str) -> str:
    return re.sub(r"\\[a-z0-9+]+\*?", " ", text)


def tag_text(text: str, source: list[tuple[str, list[str]]]) -> dict[int, list[str]]:
    """Word position in `text` (the app's verse) -> the source's Strong's
    numbers, wherever the aligned words match."""
    ours = [w.lower() for w in _WORD_RE.findall(text)]
    theirs = [w.lower() for w, _n in source]
    tags = {}
    for op, i1, i2, j1, _j2 in difflib.SequenceMatcher(None, ours, theirs, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                if source[j1 + k][1]:
                    tags[i1 + k] = source[j1 + k][1]
    return tags


def encode(tags: dict[int, list[str]]) -> str:
    return " ".join(f"{i}:{','.join(n)}" for i, n in sorted(tags.items()))


def download() -> dict[str, str]:
    print(f"Downloading {SOURCE_URL} ...")
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    texts = {}
    for name in archive.namelist():
        m = re.match(r"\d+-([0-9A-Z]{3})eng-kjv\.usfm$", Path(name).name)
        if m and m.group(1) in BOOK_CODES:
            texts[m.group(1)] = archive.read(name).decode("utf-8")
    return texts


def import_tags(conn, texts: dict[str, str]) -> None:
    conn.execute("DELETE FROM word_tags")
    app_verses: dict[str, dict[tuple[int, int], str]] = {}
    for book, chapter, verse, text in conn.execute(
        "SELECT b.name, c.chapter_number, v.verse_number, v.text FROM verses v "
        "JOIN chapters c ON c.id = v.chapter_id JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id WHERE vol.slug = 'holy-bible'"
    ):
        app_verses.setdefault(book, {})[(chapter, verse)] = text
    verses = words = tagged = source_tagged = 0
    rows = []
    for code, usfm in texts.items():
        book = BOOK_CODES[code]
        source = parse_usfm(usfm)
        for (chapter, verse), text in app_verses.get(book, {}).items():
            source_words = source.get((chapter, verse))
            if not source_words:
                continue
            tags = tag_text(text, source_words)
            verses += 1
            words += len(_WORD_RE.findall(text))
            tagged += len(tags)
            source_tagged += sum(1 for _w, n in source_words if n)
            if tags:
                rows.append(("holy-bible", f"{book} {chapter}:{verse}", encode(tags)))
    conn.executemany("INSERT INTO word_tags (volume_slug, reference, tags) VALUES (?, ?, ?)", rows)
    conn.commit()
    print(
        f"  {verses} verses: {tagged} of {words} words tagged ({tagged / max(words, 1):.0%}) - "
        f"{tagged / max(source_tagged, 1):.1%} of the words the source tags"
    )


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB_PATH
    conn = connect(db_path)
    import_tags(conn, download())
    compact(conn)
    conn.close()


if __name__ == "__main__":
    main()
