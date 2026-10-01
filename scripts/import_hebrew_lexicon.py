"""Import the Hebrew lexicon - Strong's Hebrew dictionary with STEPBible's
short glosses - into data/scriptures.db's lexicon_entries table.

    python3 scripts/import_hebrew_lexicon.py [path-to-db] [--cache DIR]

Downloads both sources (pinned to the commits below, so a re-run is
reproducible), or reads them from --cache if already downloaded there.

SOURCES AND LICENSES - both require credit, given in the README and the
app's Help menu:

- Strong's Hebrew dictionary: "A Concise Dictionary of the Words in the
  Hebrew Bible" by James Strong (1894, public domain), in Open Scriptures'
  corrected JSON edition - github.com/openscriptures/strongs - which is
  CC BY-SA (Copyright 2010 Open Scriptures). The share-alike applies to
  this lexicon data and anything adapted from it, not to the app's own
  MIT-licensed code. Supplies each entry's Hebrew, transliteration,
  pronunciation, derivation, definition, and KJV renderings.
- STEPBible's TBESH ("Translators Brief lexicon of Extended Strongs for
  Hebrew") - github.com/STEPBible/STEPBible-Data - CC BY 4.0, credit
  "STEP Bible" linked to www.STEPBible.org. Only its Gloss column (short
  meanings like "anointed", created by Tyndale House scholars) is used.
  TBESH's longer definitions are deliberately NOT imported: they are
  based on Online Bible's abridged BDB, and TBESH itself says permission
  should be gained from Online Bible before applying them in a project.

Each Strong's number gets one row. TBESH sometimes has several rows for
one number (distinct people sharing a name, distinct senses); their
distinct glosses are joined.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import compact, connect  # noqa: E402

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "scriptures.db"

OPEN_SCRIPTURES_COMMIT = "0acd2f251c2d35ff8db2dece4e0593979d3ac223"  # 2021-07-15
STEPBIBLE_COMMIT = "b99716b0cddb648ddb95cc786a197180f2f97d48"  # 2026-09-18
STRONGS_URL = (
    f"https://raw.githubusercontent.com/openscriptures/strongs/{OPEN_SCRIPTURES_COMMIT}"
    "/hebrew/strongs-hebrew-dictionary.js"
)
TBESH_URL = (
    f"https://raw.githubusercontent.com/STEPBible/STEPBible-Data/{STEPBIBLE_COMMIT}/Lexicons/"
    "TBESH%20-%20Translators%20Brief%20lexicon%20of%20Extended%20Strongs%20for%20Hebrew%20-%20"
    "STEPBible.org%20CC%20BY.txt"
)
STRONGS_FILE = "strongs-hebrew-dictionary.js"
TBESH_FILE = "tbesh.txt"

# A full import is about this size; far fewer means a source changed shape.
EXPECTED_MINIMUM_ENTRIES = 8600
MAX_GLOSSES = 4


def fetch(url: str, cache: Path | None, name: str) -> str:
    if cache is not None and (cache / name).exists():
        return (cache / name).read_text(encoding="utf-8-sig")
    with urllib.request.urlopen(url, timeout=120) as response:
        text = response.read().decode("utf-8-sig")
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / name).write_text(text, encoding="utf-8")
    return text


def parse_strongs(source: str) -> dict[str, dict]:
    """Strong's number ("H4899") -> its Open Scriptures fields."""
    return json.loads(source[source.index("{"):source.rindex("}") + 1])


def parse_tbesh_glosses(source: str) -> dict[str, list[str]]:
    """Base Strong's number ("H4899") -> distinct TBESH glosses, in file
    order. TBESH numbers are zero-padded, may carry a disambiguating
    letter ("H0430G", or lowercase: "H0122a"), and run past 9000 for prefixes and suffixes, which
    Strong's never numbered."""
    glosses: dict[str, list[str]] = {}
    for line in source.splitlines():
        columns = line.split("\t")
        match = re.match(r"^H(\d{4})[A-Za-z]?$", columns[0].strip()) if columns else None
        if not match or len(columns) < 7:
            continue
        number = int(match.group(1))
        gloss = columns[6].strip()
        if not gloss or number == 0 or number > 8674:
            continue
        key = f"H{number}"
        if gloss not in glosses.setdefault(key, []):
            glosses[key].append(gloss)
    return glosses


def clean(text: str | None) -> str:
    """Open Scriptures marks some text with braces/brackets ("{father}",
    "[idiom]") - kept as the dictionary's own notation, whitespace
    normalized."""
    return " ".join((text or "").split())


def build_rows(strongs: dict[str, dict], glosses: dict[str, list[str]]) -> list[tuple]:
    rows = []
    for key in sorted(strongs, key=lambda k: int(k[1:])):
        entry = strongs[key]
        derivation = clean(entry.get("derivation"))
        language = "aramaic" if "(Aramaic)" in derivation or "Aramaic" in clean(entry.get("strongs_def"))[:12] else "hebrew"
        rows.append(
            (
                key,
                language,
                clean(entry.get("lemma")),
                clean(entry.get("xlit")),
                clean(entry.get("pron")),
                derivation,
                clean(entry.get("strongs_def")),
                clean(entry.get("kjv_def")),
                "; ".join(glosses.get(key, [])[:MAX_GLOSSES]),
            )
        )
    return rows


def verify(rows: list[tuple]) -> list[str]:
    problems = []
    if len(rows) < EXPECTED_MINIMUM_ENTRIES:
        problems.append(f"only {len(rows)} entries (expected at least {EXPECTED_MINIMUM_ENTRIES})")
    by_number = {r[0]: r for r in rows}

    def same_hebrew(a: str, b: str) -> bool:
        # Vowel points can be stored in different orders - compare in one
        # canonical form.
        return unicodedata.normalize("NFD", a) == unicodedata.normalize("NFD", b)

    # Spot checks against well-known entries.
    for number, lemma, word in (("H4899", "מָשִׁיחַ", "anointed"), ("H7676", "שַׁבָּת", "sabbath"),
                                ("H3478", "יִשְׂרָאֵל", "Israel")):
        row = by_number.get(number)
        if row is None or not same_hebrew(row[2], lemma) or word.lower() not in (row[6] + row[7] + row[8]).lower():
            problems.append(f"{number} doesn't look like {lemma} / {word}: {row}")
    missing_gloss = sum(1 for r in rows if not r[8])
    if missing_gloss > len(rows) * 0.02:
        problems.append(f"{missing_gloss} entries have no STEPBible gloss")
    return problems


def write(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.execute("DELETE FROM lexicon_entries WHERE language IN ('hebrew', 'aramaic')")
    conn.executemany(
        "INSERT INTO lexicon_entries (strongs, language, lemma, transliteration, pronunciation, "
        "derivation, definition, kjv_renderings, gloss) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("db", nargs="?", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--cache", type=Path, default=None, help="download/read sources here")
    args = parser.parse_args()

    strongs = parse_strongs(fetch(STRONGS_URL, args.cache, STRONGS_FILE))
    glosses = parse_tbesh_glosses(fetch(TBESH_URL, args.cache, TBESH_FILE))
    rows = build_rows(strongs, glosses)
    problems = verify(rows)
    if problems:
        raise SystemExit("Not written - the sources didn't look right:\n  " + "\n  ".join(problems))

    conn = connect(Path(args.db))
    write(conn, rows)
    compact(conn)
    conn.close()
    aramaic = sum(1 for r in rows if r[1] == "aramaic")
    print(f"Wrote {len(rows)} lexicon entries ({aramaic} Aramaic) to {args.db}")


if __name__ == "__main__":
    main()
