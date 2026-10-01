"""Build (or refresh) the Topical Guide's curated KEY VERSES - the
landmark passages for each topic - into data/scriptures.db's
topic_key_verses table.

    python3 scripts/build_topic_key_verses.py [path-to-db]

WHY: build_topical_guide.py picks each topic's verses by keyword relevance
(the top FTS5 matches for a few search terms), so a landmark verse that
never uses the topic's own words is missed: none of Moroni 10:4 (Testimony),
D&C 132:19 (Marriage), Moses 1:39 (Plan of Salvation), or Ether 12:27
(Grace) were in any topic. The study index inherited the same blind spot -
AI search couldn't find Moroni 10:4 for "how can I know the Book of Mormon
is true" - so these key verses also feed AI search directly (see
study_ask.gather_candidates).

HOW THEY WERE CHOSEN (accuracy-first, like build_cross_references.py):
for each topic, the verses most often cited by General Conference talks
and Ensign/Liahona articles whose TITLES are about that topic (from
data/verse_citations.json and data/liahona_citations.json) were listed as
candidates, then reviewed by hand against each verse's text - keeping the
ones genuinely about the topic, dropping verses that rank high everywhere
just because they're cited constantly (Mosiah 3:19, Moses 1:39, 2 Nephi
31:20... outside the topics they actually teach). Seven topics have too
few titled works for that to settle it; their picks are marked JUDGMENT
below, preferring verses the citation data shows are widely used.

Each entry is a reference or a verse range in one book and chapter; the
build refuses to write anything if any entry doesn't resolve to real
verses in the Standard Works (Holy Bible, Book of Mormon, Doctrine and
Covenants, Pearl of Great Price - never the JST, whose numbering copies
the KJV's), or names an unknown topic slug.

Like the rest of the Topical Guide, this is developer-run; users get the
result through db.py's sync_bundled_content on their next update.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import compact, connect  # noqa: E402

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "scriptures.db"
STANDARD_WORKS = ("holy-bible", "book-of-mormon", "doctrine-and-covenants", "pearl-of-great-price")

# topic slug -> key passages, most central first.
KEY_VERSES: dict[str, list[str]] = {
    "agency": ["2 Nephi 2:27", "2 Nephi 2:16", "2 Nephi 10:23", "Moses 4:3", "Doctrine and Covenants 101:78", "2 Nephi 2:11"],
    # JUDGMENT (few titled works)
    "angels": ["Moroni 7:29-31", "Doctrine and Covenants 84:88", "Doctrine and Covenants 13:1", "2 Nephi 32:3", "Hebrews 13:2"],
    "atonement": ["Doctrine and Covenants 19:16-19", "Alma 7:11-12", "2 Nephi 9:7", "2 Nephi 2:7-8", "Alma 34:16", "Luke 22:44"],
    "baptism": ["Mosiah 18:8-10", "2 Nephi 31:5-7", "2 Nephi 31:17-18", "Moroni 8:10-11", "Doctrine and Covenants 68:27", "Matthew 3:13-15"],
    "charity": ["Moroni 7:45-48", "1 Corinthians 13:4-8", "1 Corinthians 13:13", "Ether 12:34", "Doctrine and Covenants 88:125", "Moroni 10:21"],
    "chastity": ["Alma 39:5", "Exodus 20:14", "1 Corinthians 6:18", "Matthew 5:27-28", "Doctrine and Covenants 121:45", "Articles of Faith 1:13", "Alma 38:12"],
    "children": ["Doctrine and Covenants 68:25-28", "Doctrine and Covenants 93:40", "Proverbs 22:6", "3 Nephi 17:21-24", "Matthew 18:3-4", "Mark 10:14", "Psalms 127:3"],
    "church-of-jesus-christ": ["Doctrine and Covenants 115:4", "3 Nephi 27:7-8", "Ephesians 2:20", "Ephesians 4:13", "Daniel 2:44", "Moroni 6:4", "Doctrine and Covenants 20:1"],
    # JUDGMENT (few titled works)
    "consecration": ["Doctrine and Covenants 105:5", "Doctrine and Covenants 42:30", "Omni 1:26", "Acts 4:32", "4 Nephi 1:3", "Doctrine and Covenants 104:15-18"],
    "covenants": ["Mosiah 18:8-10", "Doctrine and Covenants 20:77", "Doctrine and Covenants 84:33-38", "Doctrine and Covenants 82:10", "Doctrine and Covenants 14:7", "Abraham 2:9-11"],
    "creation": ["Moses 1:33", "Genesis 1:26-28", "Moses 2:26-27", "Abraham 3:24-25", "Moses 2:31"],
    "discipleship": ["Luke 9:23", "John 13:35", "John 14:15", "Matthew 11:29", "Matthew 25:40", "3 Nephi 27:27"],
    "endure-to-the-end": ["2 Nephi 31:20", "2 Nephi 31:16", "Matthew 24:13", "Doctrine and Covenants 14:7", "3 Nephi 15:9", "Doctrine and Covenants 121:7-8", "2 Timothy 4:7"],
    "exaltation": ["Doctrine and Covenants 131:1-3", "John 17:3", "Doctrine and Covenants 14:7", "Moses 1:39", "John 14:6", "Matthew 5:48", "3 Nephi 12:48"],
    "faith": ["Hebrews 11:1", "Alma 32:21", "Alma 32:27-28", "Ether 12:6", "James 1:5", "John 7:17", "Articles of Faith 1:4", "1 Nephi 3:7"],
    "family": ["Malachi 4:5-6", "Doctrine and Covenants 110:14-15", "Doctrine and Covenants 68:25-28", "Mosiah 4:15", "Doctrine and Covenants 88:119", "Exodus 20:12", "3 Nephi 18:21"],
    "fasting": ["Doctrine and Covenants 59:13-14", "Isaiah 58:6-9", "Helaman 3:35"],
    "forgiveness": ["Doctrine and Covenants 64:8-11", "Matthew 6:14-15", "Luke 23:34", "Doctrine and Covenants 58:42-43", "Isaiah 1:18", "Matthew 5:44", "Colossians 3:13"],
    "godhead": ["Joseph Smith--History 1:17", "Articles of Faith 1:1", "Doctrine and Covenants 130:22", "John 17:3", "Matthew 3:17", "3 Nephi 11:7", "John 15:26"],
    "grace": ["Ether 12:27", "2 Nephi 25:23", "Moroni 10:32", "Ephesians 2:8-9", "Philippians 4:13", "2 Corinthians 12:9"],
    "gratitude": ["Doctrine and Covenants 59:7", "Doctrine and Covenants 59:21", "Doctrine and Covenants 78:19", "Luke 17:12-19", "Mosiah 2:20", "1 Thessalonians 5:18"],
    "holy-ghost": ["John 14:26", "Doctrine and Covenants 8:2-3", "Moroni 10:4-5", "Doctrine and Covenants 9:8-9", "John 14:16", "Doctrine and Covenants 121:46", "Doctrine and Covenants 11:12", "Galatians 5:22", "1 Kings 19:12"],
    "honesty": ["Articles of Faith 1:13", "Exodus 20:15-16", "Doctrine and Covenants 124:15", "Proverbs 6:16-17", "Acts 5:3-4"],
    "hope": ["Moroni 7:40-41", "Ether 12:4", "2 Nephi 31:20", "1 Corinthians 13:13", "Moroni 8:26", "Hebrews 11:1"],
    "house-of-israel": ["Abraham 2:9-11", "Genesis 22:17-18", "Isaiah 11:11-12", "1 Nephi 15:14", "Genesis 17:7", "Doctrine and Covenants 84:34"],
    # JUDGMENT (few titled works) - each also cited widely elsewhere
    "humility": ["Mosiah 3:19", "Luke 22:42", "Ether 12:27", "Matthew 18:4"],
    "jesus-christ": ["Matthew 11:28-29", "John 3:16", "John 14:6", "Alma 7:11-12", "Moroni 10:32", "Doctrine and Covenants 19:18"],
    "judgment": ["Matthew 7:1-3", "John 8:7", "John 8:11", "Mormon 3:20"],
    # JUDGMENT (no titled works) - each widely cited
    "kindness": ["Ephesians 4:32", "Colossians 3:12", "1 Corinthians 13:4", "Moroni 7:45"],
    "love": ["Matthew 22:36-40", "John 13:34-35", "John 3:16", "John 14:15", "John 15:13", "Moroni 7:47-48"],
    "marriage": ["Genesis 2:24", "Matthew 19:5-6", "Doctrine and Covenants 42:22", "Doctrine and Covenants 131:1-3", "Doctrine and Covenants 132:19", "Doctrine and Covenants 49:15-17", "1 Corinthians 11:11", "Genesis 2:18"],
    "missionary-work": ["Matthew 28:19-20", "Mark 16:15", "Doctrine and Covenants 18:10", "Doctrine and Covenants 18:15-16", "Doctrine and Covenants 4:3", "Alma 17:2-3", "Doctrine and Covenants 123:12", "Romans 1:16"],
    "obedience": ["1 Nephi 3:7", "John 14:15", "Doctrine and Covenants 130:21", "Doctrine and Covenants 82:10", "1 Samuel 15:22", "Mosiah 2:41"],
    "ordinances": ["Doctrine and Covenants 84:20-21", "Mosiah 18:10", "2 Nephi 31:17", "Doctrine and Covenants 128:15", "Doctrine and Covenants 20:77", "Moses 6:59"],
    "peace": ["John 14:27", "John 16:33", "Doctrine and Covenants 59:23", "Matthew 5:9", "Philippians 4:7", "Doctrine and Covenants 19:23", "Isaiah 9:6"],
    "plan-of-salvation": ["Alma 42:8", "Moses 1:39", "2 Nephi 2:25", "Alma 42:15", "Alma 34:32", "Abraham 3:26", "2 Nephi 9:13", "Moses 5:11"],
    "prayer": ["Matthew 6:9-13", "Alma 34:18-27", "3 Nephi 18:20-21", "Enos 1:4", "Doctrine and Covenants 9:8", "Matthew 26:39"],
    # JUDGMENT (few titled works) - both passages also widely cited
    "premortal-life": ["Abraham 3:24-26", "Moses 4:1-4"],
    "priesthood": ["Doctrine and Covenants 13:1", "Doctrine and Covenants 84:33-38", "Doctrine and Covenants 121:36-37", "Doctrine and Covenants 121:41-42", "Doctrine and Covenants 121:45-46", "Doctrine and Covenants 84:19-20"],
    "prophets": ["Amos 3:7", "Doctrine and Covenants 1:38", "Doctrine and Covenants 21:4-6", "Ephesians 2:20", "Ephesians 4:14", "Doctrine and Covenants 135:3", "Doctrine and Covenants 107:23"],
    "repentance": ["Doctrine and Covenants 58:42-43", "Doctrine and Covenants 19:16-17", "2 Corinthians 7:10", "Alma 34:16", "Isaiah 1:18", "Mosiah 4:3", "Doctrine and Covenants 18:10-11"],
    "restoration": ["Joseph Smith--History 1:11-19", "James 1:5", "Acts 3:21", "Ephesians 1:10", "Doctrine and Covenants 110:14-16"],
    "resurrection": ["1 Corinthians 15:22", "Luke 24:39", "Luke 24:5-6", "Matthew 28:6", "John 20:15-17", "John 11:25"],
    "revelation": ["Doctrine and Covenants 8:2-3", "Doctrine and Covenants 9:8-9", "Moroni 10:5", "Doctrine and Covenants 6:15", "Doctrine and Covenants 42:61", "Helaman 5:30", "Articles of Faith 1:9", "2 Nephi 28:30"],
    # JUDGMENT (few titled works)
    "reverence": ["Exodus 3:4-5", "Leviticus 19:30", "Doctrine and Covenants 63:64", "Habakkuk 2:20"],
    "sabbath-day": ["Exodus 20:8-11", "Doctrine and Covenants 59:9-13", "Isaiah 58:13-14", "Mark 2:27", "Genesis 2:3"],
    "sacrifice": ["3 Nephi 9:19-20", "Moses 5:5-7", "Alma 34:10-14", "Hebrews 9:14", "Jacob 4:5"],
    "salvation": ["Articles of Faith 1:3", "2 Nephi 25:23", "Ephesians 2:8", "2 Nephi 31:17-20", "Alma 42:8", "Moses 1:39"],
    "second-coming": ["Doctrine and Covenants 45:26", "Doctrine and Covenants 45:39-40", "Doctrine and Covenants 45:57-58", "Matthew 24:14", "Malachi 4:5-6", "Doctrine and Covenants 88:89-90"],
    "self-reliance": ["1 Timothy 5:8", "Genesis 3:19", "Doctrine and Covenants 104:15-18", "Doctrine and Covenants 42:42", "Doctrine and Covenants 78:14", "Mosiah 4:26"],
    "service": ["Mosiah 2:17", "Matthew 25:40", "Doctrine and Covenants 58:27", "Matthew 22:39", "Doctrine and Covenants 81:5", "Luke 10:37"],
    "temple": ["Doctrine and Covenants 110:7", "Doctrine and Covenants 88:119", "Malachi 4:6", "1 Corinthians 15:29", "Doctrine and Covenants 124:28", "Doctrine and Covenants 128:15", "Doctrine and Covenants 131:2"],
    # JUDGMENT (few titled works)
    "temptation": ["1 Corinthians 10:13", "Matthew 4:1-11", "Doctrine and Covenants 20:22"],
    "testimony": ["Moroni 10:4-5", "Doctrine and Covenants 76:22-24", "James 1:5", "John 7:17", "Matthew 16:15-17", "Alma 5:45-46", "Joseph Smith--History 1:17"],
    "tithing": ["Malachi 3:8-12", "Doctrine and Covenants 119:3-4", "Genesis 14:20", "Leviticus 27:30"],
    "trials-and-adversity": ["Doctrine and Covenants 122:7-8", "Doctrine and Covenants 121:7-8", "John 16:33", "Mosiah 24:13-15", "Alma 7:11-12", "Hebrews 5:8", "1 Corinthians 10:13"],
    "truth": ["John 8:32", "Doctrine and Covenants 93:24", "Moroni 10:4-5", "John 7:17", "Doctrine and Covenants 88:118", "John 18:37"],
    "wisdom": ["James 1:5", "Doctrine and Covenants 88:118", "Doctrine and Covenants 6:7", "2 Nephi 28:30", "Doctrine and Covenants 89:19"],
    "word-of-god": ["John 5:39", "2 Nephi 32:3", "2 Timothy 3:15-16", "1 Nephi 19:23", "2 Nephi 4:15", "Articles of Faith 1:8", "Doctrine and Covenants 68:4", "3 Nephi 23:1"],
    "word-of-wisdom": ["Doctrine and Covenants 89:18-21", "Doctrine and Covenants 89:10-12", "Doctrine and Covenants 89:8-9", "Doctrine and Covenants 89:2-3", "Doctrine and Covenants 59:18-20"],
    "zion": ["Moses 7:18-19", "Doctrine and Covenants 97:21", "4 Nephi 1:3", "4 Nephi 1:15", "Doctrine and Covenants 105:5", "Isaiah 2:3", "Doctrine and Covenants 6:6"],
}

_RANGE_RE = re.compile(r"^(?P<book>.+?)\s+(?P<chapter>\d+):(?P<start>\d+)(?:-(?P<end>\d+))?$")


def expand(entry: str) -> tuple[str, int, list[int]]:
    match = _RANGE_RE.match(entry)
    if not match:
        raise ValueError(f"not a reference or verse range: {entry!r}")
    start = int(match["start"])
    end = int(match["end"]) if match["end"] else start
    if end < start:
        raise ValueError(f"backwards range: {entry!r}")
    return match["book"], int(match["chapter"]), list(range(start, end + 1))


def resolve(conn: sqlite3.Connection, entry: str) -> tuple[str, list[str]]:
    """(volume slug, [verse references]) for an entry, or ValueError."""
    book, chapter, verses = expand(entry)
    placeholders = ",".join("?" * len(STANDARD_WORKS))
    found_volume = None
    references = []
    for verse in verses:
        row = conn.execute(
            "SELECT vol.slug, v.reference FROM verses v JOIN chapters c ON c.id = v.chapter_id "
            "JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id "
            f"WHERE b.name = ? AND c.chapter_number = ? AND v.verse_number = ? "
            f"AND vol.slug IN ({placeholders})",
            (book, chapter, verse, *STANDARD_WORKS),
        ).fetchone()
        if row is None:
            raise ValueError(f"{entry!r}: {book} {chapter}:{verse} isn't in the Standard Works")
        found_volume = row[0]
        references.append(row[1])
    return found_volume, references


def verify(conn: sqlite3.Connection) -> list[str]:
    """Every problem with KEY_VERSES, or [] if it's all sound."""
    problems = []
    slugs = {r[0] for r in conn.execute("SELECT slug FROM topics")}
    for slug, entries in KEY_VERSES.items():
        if slug not in slugs:
            problems.append(f"unknown topic slug {slug!r}")
            continue
        if len(set(entries)) != len(entries):
            problems.append(f"{slug}: duplicate entry")
        for entry in entries:
            try:
                resolve(conn, entry)
            except ValueError as exc:
                problems.append(f"{slug}: {exc}")
    for slug in sorted(slugs - set(KEY_VERSES)):
        problems.append(f"topic {slug!r} has no key verses")
    return problems


def build(conn: sqlite3.Connection) -> int:
    problems = verify(conn)
    if problems:
        raise SystemExit("Not written - fix these first:\n  " + "\n  ".join(problems))
    conn.execute("DELETE FROM topic_key_verses")
    count = 0
    for slug, entries in KEY_VERSES.items():
        topic_id = conn.execute("SELECT id FROM topics WHERE slug = ?", (slug,)).fetchone()[0]
        for sort_order, entry in enumerate(entries, start=1):
            volume_slug, _references = resolve(conn, entry)
            conn.execute(
                "INSERT INTO topic_key_verses (topic_id, volume_slug, reference, sort_order) "
                "VALUES (?, ?, ?, ?)",
                (topic_id, volume_slug, entry, sort_order),
            )
            count += 1
    conn.commit()
    return count


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB_PATH
    conn = connect(db_path)
    count = build(conn)
    compact(conn)
    conn.close()
    print(f"Wrote {count} key passages across {len(KEY_VERSES)} topics to {db_path}")


if __name__ == "__main__":
    main()
