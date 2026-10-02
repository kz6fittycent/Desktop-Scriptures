"""Build (or refresh) the Book of Mormon names table - each proper name in
the Book of Mormon with what's known of its meaning, labeled by how
confident that meaning is - into data/scriptures.db's bom_names table.

    python3 scripts/build_bom_names.py [path-to-db]

TIERS (shown to readers as labels - see ui/word_study_panel.py):

- defined     The Book of Mormon itself gives the meaning ("Irreantum,
              which, being interpreted, is many waters" - 1 Nephi 17:5).
- biblical    The same name appears in the Bible; its Strong's Hebrew/
              Greek entry (linked, when the lexicon spells it the same
              way) gives the derivation. Found automatically.
- hebrew_root A clear match to a Hebrew word in the lexicon, proposed by
              scholars (curated below, sources linked).
- proposed    A scholarly suggestion with lower confidence (curated).
- unknown     Checked; no credible proposal (curated).

A name with none of these has no entry yet - "not yet researched" - which
is not the same claim as "unknown".

Every non-defined, non-biblical entry carries the reminder of Mormon
9:32-34: the Nephites altered their language "according to our manner of
speech", so proposed meanings are suggestions, not certainties.

SOURCES: meanings are written here in this project's own short words,
with every source linked - never copied text (the same practice as for
General Conference talks). The principal source is BYU's Book of Mormon
Onomasticon (onoma.lib.byu.edu), which gathers the scholarly proposals;
every name, researched here or not, links to its Onomasticon page.

NAME EXTRACTION: capitalized words in the Book of Mormon that never
appear as ordinary lowercase words in the Book of Mormon or Bible (a
hyphenated compound like "Ramath-lehi" doesn't count as lowercase use,
and a hyphenated name keeps its lowercase parts - "Maher-shalal-hash-baz"),
with group forms ("Nephites", "Lamanitish") folded into their base name
and a few non-names excluded.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.data_access import search_lexicon  # noqa: E402
from scriptures.db import compact, connect  # noqa: E402

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "scriptures.db"
ONOMASTICON = "https://onoma.lib.byu.edu/index.php/"
# Names whose Onomasticon page has another title. Every other name's page
# is its name in capitals (all checked to exist, October 2026).
ONOMASTICON_PAGES = {"Amalekite": "AMALEKITES"}

# Capitalized words that aren't names of people or places.
NOT_NAMES = {
    "Bible", "Savior", "Wherewithal", "Christ", "Christs", "Christians", "Messiah", "Gentile",
    "Gentiles", "Hebrew", "Alpha", "Omega", "Lucifer", "Satan", "Raca", "Jehovah", "Jew", "Jews",
    "Anti-Christ", "Arabian", "Hosanna",
    # Verse-opening words never used in lowercase anywhere.
    "Associate", "Deniest", "Imagining",
}

# Group/adjective forms -> the name they come from.
FORMS = {
    "Nephites": "Nephi", "Nephite": "Nephi", "Lamanites": "Laman", "Lamanite": "Laman",
    "Lamanitish": "Laman", "Zoramites": "Zoram", "Zoramite": "Zoram", "Amlicites": "Amlici",
    "Ammonihahites": "Ammonihah", "Amalickiahites": "Amalickiah", "Amulonites": "Amulon",
    "Jaredites": "Jared", "Jacobites": "Jacob", "Josephites": "Joseph", "Lemuelites": "Lemuel",
    "Ishmaelites": "Ishmael", "Ishmaelitish": "Ishmael", "Nehors": "Nehor", "Lehies": "Lehi",
    "Amalekites": "Amalekite", "Ammonites": "Ammon", "Egyptians": "Egypt", "Egyptian": "Egypt",
    "Israelites": "Israel", "Syrians": "Syria", "Assyrian": "Assyria", "Chaldeans": "Chaldees",
    "Anti-Nephi-Lehies": "Anti-Nephi-Lehi",
}

# Hand-curated entries. "reference" is where the text defines it (defined)
# or a representative occurrence. Proposals: most likely first, in our own
# words; a Strong's number in "origin" links to that lexicon entry. A
# proponent is named only where the attribution is certain.
CURATED: dict[str, dict] = {
    "Irreantum": {"tier": "defined", "meaning": "many waters", "reference": "1 Nephi 17:5"},
    "Rabbanah": {"tier": "defined", "meaning": "powerful or great king", "reference": "Alma 18:13"},
    "Rameumptom": {"tier": "defined", "meaning": "the holy stand", "reference": "Alma 31:21"},
    "Liahona": {"tier": "defined", "meaning": "a compass (a ball, or director)", "reference": "Alma 37:38"},
    "Deseret": {"tier": "defined", "meaning": "honey bee", "reference": "Ether 2:3"},
    "Ripliancum": {"tier": "defined", "meaning": "large, or to exceed all", "reference": "Ether 15:8"},
    "Shazer": {
        "tier": "hebrew_root",
        "meaning": "twisting, intertwining - perhaps the twisted trees of an oasis campsite",
        "reference": "1 Nephi 16:13",
        "proposals": [
            {"meaning": "to twist, to intertwine", "origin": "Hebrew šāzar, H7806",
             "proponent": "Sidney B. Sperry"},
            {"meaning": "pass of the trees", "origin": "Arabic šajr (trees)", "proponent": "Hugh Nibley"},
            {"meaning": "young gazelle - fitting the hunting there", "origin": "pre-Islamic Hismaic šṣr",
             "proponent": "Matthew L. Bowen"},
        ],
    },
    "Zarahemla": {
        "tier": "proposed",
        "meaning": "seed of compassion",
        "reference": "Omni 1:12",
        "proposals": [
            {"meaning": "seed of compassion (or pity)", "origin": "Hebrew zeraʿ, seed (H2233) + ḥemlâ, compassion (H2551)"},
        ],
    },
    "Alma": {
        "tier": "hebrew_root",
        "meaning": "young man",
        "reference": "Mosiah 17:2",
        "proposals": [
            {"meaning": "young man, youth", "origin": "Hebrew ʿelem, H5958 - attested as a man's name "
             "(\"Alma son of Judah\") in a 2nd-century Judean desert document", "proponent": "Hugh Nibley"},
        ],
    },
    "Mosiah": {
        "tier": "hebrew_root",
        "meaning": "savior, deliverer",
        "reference": "Omni 1:12",
        "proposals": [
            {"meaning": "one who saves, a deliverer", "origin": "Hebrew môšîaʿ, from yāšaʿ (to save, H3467)"},
        ],
    },
    "Sariah": {
        "tier": "hebrew_root",
        "meaning": "Jehovah is prince",
        "reference": "1 Nephi 2:5",
        "proposals": [
            {"meaning": "Jehovah is prince (or has prevailed)", "origin": "Hebrew Śerāyāh - the Bible's "
             "Seraiah, H8304 - found as a woman's name in the Elephantine papyri", "proponent": "Jeffrey R. Chadwick"},
        ],
    },
    "Jershon": {
        "tier": "hebrew_root",
        "meaning": "place of inheritance",
        "reference": "Alma 27:22",
        "proposals": [
            {"meaning": "a place of inheritance - the text gives Jershon \"for an inheritance\" (Alma 27:22)",
             "origin": "Hebrew yāraš, to inherit or possess, H3423"},
        ],
    },
    "Pahoran": {
        "tier": "proposed",
        "meaning": "uncertain - perhaps \"the Syrian\" (Egyptian)",
        "reference": "Alma 50:40",
        "proposals": [
            {"meaning": "the Syrian (Hurrian)", "origin": "Egyptian p3-ḥry; compare the Bible's Horites, H2752",
             "proponent": "Hugh Nibley"},
            {"meaning": "the name of Egyptian officials in Canaan", "origin": "Canaanite paḥura, in the Amarna letters"},
            {"meaning": "governor", "origin": "Hebrew peḥâ, H6346"},
            {"meaning": "assembly, or potter", "origin": "Aramaic pḥr", "proponent": "Pedro Olavarria"},
        ],
    },
    "Paanchi": {
        "tier": "proposed",
        "meaning": "the living one (Egyptian)",
        "reference": "Helaman 1:3",
        "proposals": [
            {"meaning": "the living one", "origin": "Egyptian p3-ʿnḫ, a common Egyptian name for over a thousand years",
             "proponent": "John Gee"},
            {"meaning": "the same name as the Egyptian pharaoh Piankhi", "origin": "Egyptian", "proponent": "Hugh Nibley"},
            {"meaning": "the \"paaneah\" in Joseph's Egyptian name Zaphnath-paaneah (Genesis 41:45)",
             "origin": "Egyptian, as written in Hebrew, H6847", "proponent": "Robert F. Smith"},
        ],
    },
    "Pacumeni": {
        "tier": "proposed",
        "meaning": "uncertain - perhaps \"the Egyptian\"",
        "reference": "Helaman 1:3",
        "proposals": [
            {"meaning": "the Egyptian", "origin": "Egyptian p3-kmt, with the same \"the\" prefix (pa-) as Pahoran and Paanchi"},
            {"meaning": "like the names of Egypt's last priest-governors (Pa-menech, Pamenches)", "origin": "Egyptian",
             "proponent": "Hugh Nibley"},
            {"meaning": "blind man", "origin": "Egyptian p3-kmn", "proponent": "Hugh Nibley"},
            {"meaning": "-cumeni may be the Jaredite name element kumen (as in Kishkumen), which would make "
             "an Egyptian origin doubtful", "origin": "Jaredite"},
        ],
    },
    "Nephi": {
        "tier": "proposed",
        "meaning": "good, fair",
        "reference": "1 Nephi 1:1",
        "proposals": [
            {"meaning": "good, fair, fine - echoed in \"born of goodly parents\" (1 Nephi 1:1)",
             "origin": "Egyptian nfr"},
        ],
    },
}

STRONGS_RE = re.compile(r"\b[HG]\d{1,4}\b")
TIERS = ("defined", "biblical", "hebrew_root", "proposed", "unknown")


def _texts(conn: sqlite3.Connection, volume_slug: str) -> list[tuple[str, str]]:
    return conn.execute(
        "SELECT v.reference, v.text FROM verses v JOIN chapters c ON c.id = v.chapter_id "
        "JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id "
        "WHERE vol.slug = ? ORDER BY v.id",
        (volume_slug,),
    ).fetchall()


def extract_names(conn: sqlite3.Connection) -> dict[str, dict]:
    """Base name -> {"forms": [...], "first": reference, "count": n}."""
    bom = _texts(conn, "book-of-mormon")
    bible = _texts(conn, "holy-bible")
    lowercase = set()
    for _ref, text in bom + bible:
        # A lowercase word on its own - not the tail of a hyphenated
        # place name like "Ramath-lehi".
        lowercase.update(re.findall(r"(?<![A-Za-z-])[a-z][a-z]+\b", text))
    found: dict[str, dict] = {}
    for reference, text in bom:
        for match in re.finditer(r"\b[A-Z][a-z]+(?:-[A-Za-z][a-z]+)*\b", text):
            word = match.group(0)
            if word.lower() in lowercase or word in NOT_NAMES:
                continue
            # Sentence-initial capitals of ordinary words were filtered by
            # the lowercase check; names stay.
            base = FORMS.get(word, word)
            entry = found.setdefault(base, {"forms": set(), "first": reference, "count": 0})
            entry["forms"].add(word)
            entry["count"] += 1
    return found


def biblical_strongs(conn: sqlite3.Connection, name: str) -> list[str]:
    """Lexicon entries that are this very name: its gloss or the KJV's
    first rendering is the name (Hebrew before Greek)."""
    def first(text: str) -> str:
        return re.split(r"[,;:.]", text, maxsplit=1)[0].strip(" ()[]{}").lower()

    return [
        e.strongs for e in search_lexicon(conn, name)
        if first(e.gloss) == name.lower() or first(e.kjv_renderings) == name.lower()
    ][:3]


def in_bible(conn: sqlite3.Connection, name: str) -> bool:
    """The name occurs, capitalized, in the Bible's text - Isaiah's place
    names quoted in 2 Nephi (Calno, Aiath) whose Strong's spelling differs."""
    return conn.execute(
        "SELECT 1 FROM verses v JOIN chapters c ON c.id = v.chapter_id JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id WHERE vol.slug = 'holy-bible' AND v.text GLOB ? LIMIT 1",
        (f"*{name}*",),
    ).fetchone() is not None and any(
        re.search(rf"\b{re.escape(name)}\b", r[0])
        for r in conn.execute(
            "SELECT v.text FROM verses v JOIN chapters c ON c.id = v.chapter_id JOIN books b ON b.id = c.book_id "
            "JOIN volumes vol ON vol.id = b.volume_id WHERE vol.slug = 'holy-bible' AND v.text GLOB ?",
            (f"*{name}*",),
        )
    )


def build(conn: sqlite3.Connection) -> Counter:
    names = extract_names(conn)
    bom = _texts(conn, "book-of-mormon")
    for name in CURATED:
        if name in names:
            continue
        # Some defined words are lowercase in the text ("carry with them
        # deseret" - Ether 2:3), so never picked up as capitalized names.
        pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
        hits = [ref for ref, text in bom if pattern.search(text)]
        if not hits:
            raise SystemExit(f"Curated name {name!r} wasn't found in the Book of Mormon text")
        names[name] = {"forms": {name.lower()}, "first": hits[0], "count": len(hits)}
    rows = []
    for name in sorted(names):
        info = names[name]
        curated = CURATED.get(name)
        page = ONOMASTICON_PAGES.get(name, name.upper())
        onomasticon = [f"Book of Mormon Onomasticon: {page}", ONOMASTICON + page]
        strongs = biblical_strongs(conn, name)
        if curated:
            tier = curated["tier"]
            assert tier in TIERS, (name, tier)
            linked = [n for p in curated.get("proposals", []) for n in STRONGS_RE.findall(p.get("origin", ""))]
            linked = linked or strongs
            rows.append((
                name, tier, curated.get("meaning", ""), curated.get("reference", info["first"]),
                ",".join(linked), json.dumps(curated.get("proposals", []), ensure_ascii=False),
                json.dumps(curated.get("sources", []) + [onomasticon], ensure_ascii=False),
                ",".join(sorted(info["forms"] - {name})),
            ))
        elif strongs or in_bible(conn, name):
            rows.append((name, "biblical", "", info["first"], ",".join(strongs), "[]", json.dumps([onomasticon]),
                         ",".join(sorted(info["forms"] - {name}))))
        else:
            # Not yet researched: kept so its forms resolve, with no tier.
            rows.append((name, "", "", info["first"], "", "[]", json.dumps([onomasticon]),
                         ",".join(sorted(info["forms"] - {name}))))
    conn.execute("DELETE FROM bom_names")
    conn.executemany(
        "INSERT INTO bom_names (name, tier, meaning, reference, strongs, proposals, sources, forms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return Counter(r[1] or "not yet researched" for r in rows)


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB_PATH
    conn = connect(db_path)
    counts = build(conn)
    compact(conn)
    conn.close()
    print(f"Wrote {sum(counts.values())} Book of Mormon names to {db_path}: {dict(counts)}")


if __name__ == "__main__":
    main()
