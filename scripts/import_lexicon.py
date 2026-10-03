"""Import the original-language lexicons - Strong's dictionaries with
STEPBible's short glosses - into data/scriptures.db's lexicon_entries
table. Hebrew (with Biblical Aramaic) for the Old Testament, Greek for
the New.

    python3 scripts/import_lexicon.py [path-to-db] [--language hebrew|greek] [--cache DIR]

With no --language, imports every language in LANGUAGES. Downloads the
sources (pinned to the commits below, so a re-run is reproducible), or
reads them from --cache if already downloaded there.

SOURCES AND LICENSES - all require credit, given in the README, the
app's Help menu, and every lexicon entry the app shows:

- Strong's dictionaries: "A Concise Dictionary of the Words in the Hebrew
  Bible" and "...in the Greek Testament" by James Strong (1890/1894,
  public domain), in Open Scriptures' corrected JSON editions -
  github.com/openscriptures/strongs - which are CC BY-SA (Copyright
  2009/2010 Open Scriptures). The share-alike applies to this lexicon
  data and anything adapted from it, not to the app's own GPL-licensed
  code. Supplies each entry's original word, transliteration,
  pronunciation (Hebrew only), derivation, definition, and KJV renderings.
- STEPBible's "Translators Brief lexicon of Extended Strongs" - TBESH
  (Hebrew) and TBESG (Greek) - github.com/STEPBible/STEPBible-Data - CC BY
  4.0, credit "STEP Bible" linked to www.STEPBible.org. Only their Gloss
  column (short meanings like "anointed", by Tyndale House scholars) is
  used. TBESH's longer Hebrew definitions are deliberately NOT imported:
  they're based on Online Bible's abridged BDB, and TBESH itself says
  permission should be gained from Online Bible first. (TBESG's longer
  Greek definitions come from Abbott-Smith's 1922 lexicon instead, with
  no such condition - a possible later addition.)

Each Strong's number gets one row. TBESH/TBESG sometimes have several rows
for one number (distinct people sharing a name, distinct senses); their
distinct glosses are joined. Cross-references in the text are normalized
to Strong's own numbering ("H03723" -> "H3723"), so they link.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import compact, connect  # noqa: E402

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "scriptures.db"

OPEN_SCRIPTURES_COMMIT = "0acd2f251c2d35ff8db2dece4e0593979d3ac223"  # 2021-07-15
STEPBIBLE_COMMIT = "b99716b0cddb648ddb95cc786a197180f2f97d48"  # 2026-09-18
_OPEN_SCRIPTURES = f"https://raw.githubusercontent.com/openscriptures/strongs/{OPEN_SCRIPTURES_COMMIT}"
_STEPBIBLE = f"https://raw.githubusercontent.com/STEPBible/STEPBible-Data/{STEPBIBLE_COMMIT}/Lexicons"

MAX_GLOSSES = 4


@dataclass(frozen=True)
class Language:
    name: str
    prefix: str  # Strong's number prefix: "H" or "G"
    strongs_url: str
    strongs_file: str
    gloss_url: str
    gloss_file: str
    highest_number: int  # Strong's own numbering ends here; beyond it are STEPBible additions
    expected_minimum: int  # a full import is about this size; far fewer means a source changed shape
    # (number, original word, an English word its definition/gloss/KJV renderings must contain)
    spot_checks: tuple


LANGUAGES = {
    "hebrew": Language(
        name="hebrew",
        prefix="H",
        strongs_url=f"{_OPEN_SCRIPTURES}/hebrew/strongs-hebrew-dictionary.js",
        strongs_file="strongs-hebrew-dictionary.js",
        gloss_url=f"{_STEPBIBLE}/TBESH%20-%20Translators%20Brief%20lexicon%20of%20Extended%20Strongs%20"
        "for%20Hebrew%20-%20STEPBible.org%20CC%20BY.txt",
        gloss_file="tbesh.txt",
        highest_number=8674,
        expected_minimum=8600,
        spot_checks=(("H4899", "מָשִׁיחַ", "anointed"), ("H7676", "שַׁבָּת", "sabbath"),
                     ("H3478", "יִשְׂרָאֵל", "Israel")),
    ),
    "greek": Language(
        name="greek",
        prefix="G",
        strongs_url=f"{_OPEN_SCRIPTURES}/greek/strongs-greek-dictionary.js",
        strongs_file="strongs-greek-dictionary.js",
        gloss_url=f"{_STEPBIBLE}/TBESG%20-%20Translators%20Brief%20lexicon%20of%20Extended%20Strongs%20"
        "for%20Greek%20-%20STEPBible.org%20CC%20BY.txt",
        gloss_file="tbesg.txt",
        highest_number=5624,
        expected_minimum=5450,
        spot_checks=(("G5547", "Χριστός", "Messiah"), ("G26", "ἀγάπη", "love"),
                     ("G2584", "Καπερναούμ", "Capernaum")),
    ),
}


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


def parse_glosses(source: str, language: Language) -> dict[str, list[str]]:
    """Strong's number ("H4899") -> distinct STEPBible glosses, in file
    order. STEPBible numbers are zero-padded, may carry a disambiguating
    letter ("H0430G", or lowercase: "H0122a"), and run past Strong's own
    highest number for STEPBible's additions (prefixes, suffixes, variants),
    which have no Strong's entry to attach to."""
    glosses: dict[str, list[str]] = {}
    pattern = re.compile(rf"^{language.prefix}(\d{{4,5}})[A-Za-z]?$")
    for line in source.splitlines():
        columns = line.split("\t")
        match = pattern.match(columns[0].strip()) if columns else None
        if not match or len(columns) < 7:
            continue
        number = int(match.group(1))
        gloss = columns[6].strip()
        if not gloss or number == 0 or number > language.highest_number:
            continue
        key = f"{language.prefix}{number}"
        if gloss not in glosses.setdefault(key, []):
            glosses[key].append(gloss)
    return glosses


def clean(text: str | None) -> str:
    """Whitespace normalized, and other entries' numbers in Strong's own
    form ("H03723" -> "H3723") so they link. Open Scriptures' own braces/
    brackets ("{father}", "[idiom]") are kept as the dictionary's notation."""
    text = " ".join((text or "").split())
    return re.sub(r"\b([HG])0+(\d)", r"\1\2", text)


def build_rows(strongs: dict[str, dict], glosses: dict[str, list[str]], language: Language) -> list[tuple]:
    rows = []
    for key in sorted(strongs, key=lambda k: int(k[1:])):
        entry = strongs[key]
        derivation = clean(entry.get("derivation"))
        definition = clean(entry.get("strongs_def"))
        name = language.name
        if name == "hebrew" and ("(Aramaic)" in derivation or "Aramaic" in definition[:12]):
            name = "aramaic"
        rows.append(
            (
                key,
                name,
                clean(entry.get("lemma")),
                clean(entry.get("xlit") or entry.get("translit")),
                clean(entry.get("pron")),
                derivation,
                definition,
                clean(entry.get("kjv_def")),
                "; ".join(glosses.get(key, [])[:MAX_GLOSSES]),
            )
        )
    return rows


def verify(rows: list[tuple], language: Language) -> list[str]:
    problems = []
    if len(rows) < language.expected_minimum:
        problems.append(f"only {len(rows)} {language.name} entries (expected at least {language.expected_minimum})")
    by_number = {r[0]: r for r in rows}

    def same_text(a: str, b: str) -> bool:
        # Accents/vowel points can be stored in different orders - compare
        # in one canonical form.
        return unicodedata.normalize("NFD", a) == unicodedata.normalize("NFD", b)

    for number, lemma, word in language.spot_checks:
        row = by_number.get(number)
        if row is None or not same_text(row[2], lemma) or word.lower() not in (row[6] + row[7] + row[8]).lower():
            problems.append(f"{number} doesn't look like {lemma} / {word}: {row}")
    missing_gloss = sum(1 for r in rows if not r[8])
    if missing_gloss > len(rows) * 0.02:
        problems.append(f"{missing_gloss} {language.name} entries have no STEPBible gloss")
    return problems


def write(conn: sqlite3.Connection, rows: list[tuple], language: Language) -> None:
    languages = ("hebrew", "aramaic") if language.name == "hebrew" else (language.name,)
    conn.execute(
        f"DELETE FROM lexicon_entries WHERE language IN ({','.join('?' * len(languages))})", languages
    )
    conn.executemany(
        "INSERT INTO lexicon_entries (strongs, language, lemma, transliteration, pronunciation, "
        "derivation, definition, kjv_renderings, gloss) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def load(language: Language, cache: Path | None) -> list[tuple]:
    strongs = parse_strongs(fetch(language.strongs_url, cache, language.strongs_file))
    glosses = parse_glosses(fetch(language.gloss_url, cache, language.gloss_file), language)
    return build_rows(strongs, glosses, language)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("db", nargs="?", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--language", choices=sorted(LANGUAGES), action="append")
    parser.add_argument("--cache", type=Path, default=None, help="download/read sources here")
    args = parser.parse_args()

    chosen = [LANGUAGES[name] for name in (args.language or LANGUAGES)]
    loaded = {}
    for language in chosen:
        rows = load(language, args.cache)
        problems = verify(rows, language)
        if problems:
            raise SystemExit("Not written - the sources didn't look right:\n  " + "\n  ".join(problems))
        loaded[language.name] = rows

    conn = connect(Path(args.db))
    for language in chosen:
        write(conn, loaded[language.name], language)
    compact(conn)
    conn.close()
    for name, rows in loaded.items():
        counts: dict[str, int] = {}
        for row in rows:
            counts[row[1]] = counts.get(row[1], 0) + 1
        print(f"Wrote {len(rows)} {name} lexicon entries {counts} to {args.db}")


if __name__ == "__main__":
    main()
