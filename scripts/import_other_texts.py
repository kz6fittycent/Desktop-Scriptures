#!/usr/bin/env python3
"""Import "Other Ancient Texts" - writings that are NOT part of the Standard Works, but that
Bible readers (early Latter-day Saints among them) have long found
interesting - as their own volume, after the Apocrypha.

Usage:
    python3 scripts/import_other_texts.py [path-to-db]

path-to-db defaults to data/scriptures.db. Downloads its sources each run
(about 300 small requests to Wikisource, one a second - a few minutes);
safe to re-run - the volume is replaced.

BOOKS

- 1 Enoch: R. H. Charles' translation from the Ethiopic (London: SPCK,
  1917) - the standard English edition, whose chapter and verse numbers
  are the ones scholars cite (Jude 1:14-15 quotes 1 Enoch 1:9). Public
  domain (published 1917; Charles died 1931). Source: Project Gutenberg
  #77935, proofread by Distributed Proofreaders.

- Jasher: "Sefer Ha-yashar, or the Book of Jasher" (New York: M. M. Noah
  and A. S. Gould, 1840) - the English translation of a Hebrew retelling
  of Genesis through Judges printed in Venice in 1625, generally dated to
  the Middle Ages. It is NOT the lost "book of Jasher" named in Joshua
  10:13 and 2 Samuel 1:18, though it retells those events; and not Jacob
  Ilive's 1751 forgery of the same name. Early Latter-day Saints read it
  (J. H. Parry & Co. reprinted it in Salt Lake City in 1887); the Church
  doesn't treat it as scripture. Public domain. Source: Wikisource's
  proofread transcription of the 1840 edition's scans.

HOW IT'S SHOWN: the volume's page says plainly that these aren't
scripture (main_window._other_texts_banner). AI search gives them their
own small share of candidates, in its last tier; they're kept out of the
Topical Guide.

TEXT
- Enoch: Charles prints verse numbers inline, poetry indented, some
  passages out of order or twice (as parallel versions, and the Greek
  text after the Ethiopic - kept, marked "[Greek text:]"). The parser keys
  every verse by chapter and verse wherever it's printed and checks that
  each chapter's verses run 1, 2, 3... without a gap. His critical marks
  (〚 〛 ⌜ ⌝ † ‹ ›) are dropped and the words they mark kept; his square
  and round brackets stay. His section headings become chapter headings.
- Jasher: Wikisource's markup removed; verses as numbered in 1840.
- Both: curly quotes become straight, as in the app's KJV.
"""

from __future__ import annotations

import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import compact, connect  # noqa: E402

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "scriptures.db"
VOLUME_NAME = "Other Ancient Texts"
VOLUME_SLUG = "other-ancient-texts"
USER_AGENT = "Desktop-Scriptures/2.3 (+https://github.com/kz6fittycent/Desktop-Scriptures; text import)"

ENOCH_URL = "https://www.gutenberg.org/cache/epub/77935/pg77935.txt"
JASHER_RAW = "https://en.wikisource.org/w/index.php?title={title}&action=raw"
JASHER_CHAPTER = "Sefer_Ha-yashar,_or,_the_Book_of_Jasher_(1840)/Chapter_{n}"

# (book name, chapters, verses) - checked on every import.
EXPECTED = {"1 Enoch": (108, 1062), "Jasher": (91, 3910)}

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8")


def tidy(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTES)).strip()


# --------------------------------------------------------------------------
# 1 Enoch (Charles, 1917)
# --------------------------------------------------------------------------

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman(numeral: str) -> int:
    total = 0
    for i, ch in enumerate(numeral):
        nxt = _ROMAN[numeral[i + 1]] if i + 1 < len(numeral) else 0
        total += -_ROMAN[ch] if nxt > _ROMAN[ch] else _ROMAN[ch]
    return total


# Chapter (and verse) references, then an italic or =bold= title:
# "XX. _...", "VI-XI. _...", "LXXXIX. 10-27. _...", "LV. 3-LVI. 4. _...".
_REF = r"[IVXLC]+(?:[-–][IVXLC]+)?"
_HEADING_START = re.compile(rf"^\s*(?:{_REF}[.,]\s+)+(?:\d[\dIVXLC,\-–.\s]*?\.\s+)?[_=]")
# A centred italic heading - not a lettered sub-line like "_b._ And by you...".
_ITALIC_LINE = re.compile(r"^\s*_(?![a-z]\._)[^_]{4,}")
_TOKEN = re.compile(
    r"§(?P<hch>\d+):(?P<hv>\d+)§"
    r"|(?:(?<=[\s\[(])|^)(?P<lv>\d{1,3})\.L\s"
    r"|(?:(?<=[\s\[(])|^)(?:(?P<ch>[IVXLC]{1,7})\.\s+)?(?P<v>\d{1,3})\.\s"
    r"|(?:(?<=\s)|^)(?P<chonly>[IVXLC]{1,7})\.\s+(?=[A-Z(⌜〚‘“†\[])"
)


def _enoch_lines(text: str) -> tuple[list[str], dict[int, set], dict[int, str]]:
    """The text's lines with headings replaced by §chapter:verse§ markers,
    the verse ranges headings vouch for, and each chapter's heading."""
    lines = text.splitlines()
    kept: list[str] = []
    allowed: dict[int, set] = {}
    titles: dict[int, str] = {}
    i = 0
    while i < len(lines):
        line, stripped = lines[i], lines[i].strip()
        if _HEADING_START.match(line) or _ITALIC_LINE.match(line):
            heading = [stripped]
            delim = "_" if "_" in stripped else "="
            j = i
            while " ".join(heading).count(delim) % 2 == 1 and j + 1 < len(lines):
                j += 1
                heading.append(lines[j].strip())
            heading_text = " ".join(heading)
            # An italic-only line is a heading only if nothing but
            # punctuation follows its closing "_" ("_hollow places_: ..." is text).
            if not _HEADING_START.match(line) and re.sub(r"[\s.:,;]", "", heading_text.rsplit(delim, 1)[-1]):
                kept.append(line)
                i += 1
                continue
            i = j + 1
            # Verse ranges it lists ("XCII. XCI. 1-10, 18-19.") are trusted
            # even across a jump (91: 10, then 18).
            for numeral, ranges in re.findall(
                r"([IVXLC]+)\.\s+((?:\d+(?:[-–]\d+)?,\s*)*\d+(?:[-–]\d+)?)\.", heading_text.split(delim)[0]
            ):
                for part in ranges.split(","):
                    a, _, b = part.strip().replace("–", "-").partition("-")
                    allowed.setdefault(roman(numeral), set()).update(range(int(a), int(b or a) + 1))
            # The heading's own chapter (and starting verse): some chapters'
            # text starts at "1." with the number only in the heading.
            refs = re.match(rf"\s*((?:{_REF}[.,]\s+)+)(\d+)?", heading_text)
            if refs:
                # Its chapter: the last reference before a verse range, else
                # the first - and a chapter range ("VI-XI.") starts at its first.
                tokens = re.findall(_REF, refs.group(1))
                chapter = roman(re.split(r"[-–]", tokens[-1] if refs.group(2) else tokens[0])[0])
                start_verse = int(refs.group(2)) if refs.group(2) else 1
                kept.append(f" §{chapter}:{start_verse}§ ")
                title = re.search(rf"{re.escape(delim)}(.+?){re.escape(delim)}", heading_text)
                if title and start_verse == 1:
                    titles.setdefault(chapter, tidy(title.group(1)).rstrip("."))
            continue
        letters = re.sub(r"^(?:[IVXLC]+\.\s+)+", "", stripped)
        if letters and not re.search(r"[a-z]", letters) and re.search(r"[A-Z]{3,}", letters):
            i += 1  # an all-capitals banner ("THE BOOK OF ENOCH", "AN APPENDIX ...")
            continue
        if re.fullmatch(r"[IVXLC]+[-–][IVXLC]+\.?", stripped):
            i += 1
            continue
        kept.append(line)
        i += 1
    return kept, allowed, titles


def parse_enoch(source: str) -> tuple[dict[int, dict[int, str]], dict[int, str]]:
    start = source.index("I. 1. The words of the blessing of Enoch")
    end = source.find("Transcriber’s Notes", start)
    end = source.rfind("\n", 0, end if end > 0 else source.index("*** END OF THE PROJECT GUTENBERG"))
    kept, allowed, titles = _enoch_lines(source[start:end])

    flat = " ".join(kept)
    # Lettered sub-verses in Charles' parallel arrangement ("6_a._",
    # "7 _c._", then back to "6_d._"): the number marks a verse.
    flat = re.sub(r"(?<![\w.])(\d{1,3})\s?_[a-z]\._", r"\1.L ", flat)
    flat = re.sub(r"_([a-z])\._\s*", "", flat)
    flat = re.sub(r"_([^_]+)_", r"\1", flat)
    # The Greek (Gizeh) text of a verse, after the Ethiopic: say so in words.
    flat = re.sub(r"G\^g\s+(?:\d{1,3}\.\s+)?", "[Greek text:] ", flat)
    flat = re.sub(r"=([^=]+)=", r"\1", flat)
    flat = re.sub(r"\s+", " ", flat)

    verses: dict[tuple[int, int], str] = {}
    chapter, last, current = None, 0, None
    marks: list[tuple[int, int, tuple[int, int] | None]] = []
    for m in _TOKEN.finditer(flat):
        if m.group("hch"):
            chapter, last = int(m.group("hch")), int(m.group("hv")) - 1
            marks.append((m.start(), m.end(), None))
            continue
        if m.group("chonly"):
            chapter, last = roman(m.group("chonly")), 1
            current = (chapter, 1)
            marks.append((m.start(), m.end(), current))
            continue
        if m.group("lv"):
            v = int(m.group("lv"))
            if 1 <= v <= last + 2:  # may step back to an earlier verse's next line
                last, current = max(last, v), (chapter, v)
                marks.append((m.start(), m.end(), current))
            continue
        v = int(m.group("v"))
        if m.group("ch"):
            chapter, last = roman(m.group("ch")), v
            current = (chapter, v)
            marks.append((m.start(), m.end(), current))
        elif (last - 5 <= v <= last + 3 or v in allowed.get(chapter, ())) and (chapter, v) != current:
            # A verse near the last: some are printed out of order (106: 17,
            # 15, 16, 18) or twice side by side (22:12-14) - a repeat joins
            # that verse. Not a number ending a sentence ("amount to 80.").
            last, current = max(last, v), (chapter, v)
            marks.append((m.start(), m.end(), current))
    receiving = None
    for n, (_s, e, key) in enumerate(marks):
        nxt = marks[n + 1][0] if n + 1 < len(marks) else len(flat)
        piece = flat[e:nxt].strip()
        if key is None:
            if piece and receiving:
                verses[receiving] += " " + piece
            continue
        receiving = key
        verses[key] = (verses.get(key, "") + " " + piece).strip()

    chapters: dict[int, dict[int, str]] = {}
    for (c, v), text in sorted(verses.items()):
        text = re.sub(r"\s*§\d+:\d+§\s*", " ", text)
        text = re.sub(rf"(?<=\s){v}\.\s", "", text)  # a parallel version repeating the verse's number
        text = re.sub(r"[〚〛⌜⌝†‹›]", "", text)
        text = re.sub(r"\s+[IVXLC]{2,}\.\s*$", "", text)  # the next chapter's stray numeral
        chapters.setdefault(c, {})[v] = tidy(text)
    return chapters, titles


# --------------------------------------------------------------------------
# Jasher (1840)
# --------------------------------------------------------------------------

def _wikisource(title: str) -> str:
    url = JASHER_RAW.format(title=urllib.parse.quote(title, safe="/(),_:"))
    text = fetch(url)
    time.sleep(1)  # politely
    return text


def _jasher_wikitext(n: int, pages: dict[str, str]) -> str:
    page = _wikisource(JASHER_CHAPTER.format(n=n))
    m = re.search(r'<pages index="([^"]+)" from=(\d+) to=(\d+)([^/]*)/>', page)
    if not m:
        return page  # typed directly on the chapter page
    index, first, last, rest = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    names = set(re.findall(r'(?:from|to)section="([^"]+)"', rest))
    parts = []
    for number in range(first, last + 1):
        title = f"Page:{index}/{number}"
        if title not in pages:
            pages[title] = _wikisource(title)
        text = re.sub(r"(?s)<noinclude>.*?</noinclude>", "", pages[title])
        if "<section" not in text or not names:
            parts.append(text)  # a page wholly within the chapter
            continue
        # Each page marks its own piece of each chapter: take this chapter's.
        for name in names:
            parts += re.findall(
                rf'<section begin="{re.escape(name)}"\s*/>(.*?)<section end="{re.escape(name)}"\s*/>', text, re.S
            )
    return "\n".join(parts)


def _clean_wikitext(text: str) -> str:
    text = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    # A word hyphenated across two scan pages: {{hws|Ash|Ashur}} {{hwe|ur|Ashur}}.
    text = re.sub(r"\{\{hws\|[^|}]*\|([^}]*)\}\}\s*\{\{hwe\|[^}]*\}\}", r"\1", text)
    text = re.sub(r"\{\{(?:nop|reflist|clear)[^}]*\}\}", "", text)
    text = re.sub(r"\{\{(?:sc|smaller|larger|x-larger|c|center|uc)\|([^{}]*)\}\}", r"\1", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    return tidy(text.replace("''", ""))


_JASHER_VERSE = re.compile(r"\{\{verse\|(?:chapter=\d+)?\|?(?:verse=)?(\d+)\}\}|^\s*(\d{1,3})\s+(?=\S)", re.M)


def parse_jasher_chapter(text: str) -> dict[int, str]:
    text = re.sub(r"\{\{c\|\{\{larger\|CHAPTER [IVXLC]+\.?\}\}\}\}", "", text)
    text = re.sub(r"(?m)^\s*CHAPTER [IVXLC]+\.?\s*$", "", text)
    marks, current = [], 0
    for m in _JASHER_VERSE.finditer(text):
        v = int(m.group(1) or m.group(2))
        if v == current + 1:
            marks.append((m.start(), m.end(), v))
            current = v
    return {
        v: _clean_wikitext(text[e:marks[i + 1][0] if i + 1 < len(marks) else len(text)])
        for i, (_s, e, v) in enumerate(marks)
    }


def parse_jasher() -> dict[int, dict[int, str]]:
    pages: dict[str, str] = {}
    chapters = {}
    for n in range(1, 92):
        chapters[n] = parse_jasher_chapter(_jasher_wikitext(n, pages))
        print(f"  Jasher {n}: {len(chapters[n])} verses", end="\r")
    print()
    return chapters


# --------------------------------------------------------------------------

def import_volume(conn, books: list[tuple[str, dict[int, dict[int, str]], dict[int, str]]]) -> None:
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
            "INSERT INTO volumes (name, slug, sort_order) VALUES (?, ?, ?)", (VOLUME_NAME, VOLUME_SLUG, sort_order)
        ).lastrowid
    for order, (name, chapters, titles) in enumerate(books, start=1):
        verse_count = sum(len(v) for v in chapters.values())
        expected = EXPECTED[name]
        gaps = [c for c, vs in chapters.items() if sorted(vs) != list(range(1, len(vs) + 1))]
        if (len(chapters), verse_count) != expected or gaps or sorted(chapters) != list(range(1, len(chapters) + 1)):
            raise SystemExit(
                f"{name}: {len(chapters)} chapters / {verse_count} verses (expected {expected[0]} / "
                f"{expected[1]}), verse gaps in {gaps[:5]} - the source changed; check before importing"
            )
        book_id = conn.execute(
            "INSERT INTO books (volume_id, testament_id, name, sort_order) VALUES (?, NULL, ?, ?)",
            (volume_id, name, order),
        ).lastrowid
        for number in sorted(chapters):
            chapter_id = conn.execute(
                "INSERT INTO chapters (book_id, chapter_number, title) VALUES (?, ?, ?)",
                (book_id, number, titles.get(number)),
            ).lastrowid
            conn.executemany(
                "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (?, ?, ?, ?)",
                [(chapter_id, v, text, f"{name} {number}:{v}") for v, text in sorted(chapters[number].items())],
            )
        print(f"  {name}: {len(chapters)} chapters, {verse_count} verses")
    conn.commit()


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB_PATH
    print(f"Downloading {ENOCH_URL} ...")
    enoch, enoch_titles = parse_enoch(fetch(ENOCH_URL))
    print("Downloading the Book of Jasher from Wikisource (a few minutes) ...")
    jasher = parse_jasher()
    conn = connect(db_path)
    import_volume(conn, [("1 Enoch", enoch, enoch_titles), ("Jasher", jasher, {})])
    compact(conn)
    conn.close()


if __name__ == "__main__":
    main()
