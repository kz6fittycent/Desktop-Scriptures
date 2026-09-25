#!/usr/bin/env python3
"""Build (or refresh) Cross-references: developer-curated pairs of passages
that quote, paraphrase, or (for the Joseph Smith Translation/Moses) are a
revision of another passage elsewhere in the corpus.

Usage:
    python3 scripts/build_cross_references.py [path-to-db]

    path-to-db defaults to data/scriptures.db.

Re-run this any time an entry below changes - it fully replaces the
cross_references table each run (DELETE + re-INSERT), same as
build_topical_guide.py does for topics. End users get its output the same
way they get everything else here, through db.py's sync_bundled_content
on their next snap refresh.

CURATION: every entry below was checked directly against this app's own
imported text (not assumed from memory) before being added - see the
"Isaiah in 2 Nephi" section of the project history for why that check
matters: the Joseph Smith Translation reuses the King James Bible's own
chapter/verse numbers, so two completely unrelated verses can share the
exact same reference string. Entries are hand-picked, well-documented
parallels (the kind already named in the scriptures' own chapter
summaries, e.g. 2 Nephi 12's "Compare Isaiah 2"), not machine-detected
text similarity - accuracy matters more than exhaustiveness here, so a
plausible-but-unverified parallel is left out rather than guessed at.

Three relationship kinds (see also schema.sql's own comment):
- "quotation": wording matches (allowing for translation-era spelling).
- "paraphrase": same content/point, but wording diverges meaningfully, or
  only part of the passage is quoted amid original commentary.
- "translation": a JST/Moses-style revision of the very same underlying
  narrative, not an independent quotation of it.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.db import connect  # noqa: E402

# Consecutive whole chapters, quoted 1:1 - every chapter in the range has
# the exact same verse count as its counterpart (verified directly against
# the database before being added here). Expanded below into one
# chapter-level ENTRIES row per chapter pair.
CHAPTER_BLOCKS = [
    # (book, volume, chapter_start, chapter_end,
    #  related_book, related_volume, related_chapter_start,
    #  relationship, note)
    (
        "2 Nephi", "The Book of Mormon", 12, 24,
        "Isaiah", "Holy Bible", 2,
        "quotation",
        "Nephi quotes Isaiah 2-14 nearly word for word, though not without "
        "change - for example expanding Isaiah 2:5's brief admonition into "
        "\"yea, come, for ye have all gone astray, every one to his wicked "
        "ways\" in 2 Nephi 12:5.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 12, 13,
        "Matthew", "Holy Bible", 5,
        "quotation",
        "The risen Christ's \"Sermon at the Temple\" to the Nephites, "
        "closely following the Sermon on the Mount - see 3 Nephi 14 for "
        "where it begins to diverge.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 24, 25,
        "Malachi", "Holy Bible", 3,
        "quotation",
        "Christ quotes Malachi 3-4 to the Nephites almost word for word, "
        "identifying it by name in 3 Nephi 24:1.",
    ),
]

# Everything else: a single chapter, or a specific verse range on one or
# both sides. verse_start/verse_end are None together for a whole-chapter
# entry (see schema.sql).
ENTRIES = [
    # (book, volume, chapter, verse_start, verse_end,
    #  related_book, related_volume, related_chapter, related_verse_start, related_verse_end,
    #  relationship, note)
    (
        "Mosiah", "The Book of Mormon", 12, 21, 24,
        "Isaiah", "Holy Bible", 52, 7, 10,
        "quotation",
        "Abinadi quotes Isaiah directly while testifying before King "
        "Noah's priests.",
    ),
    (
        "Mosiah", "The Book of Mormon", 14, None, None,
        "Isaiah", "Holy Bible", 53, None, None,
        "quotation",
        "Abinadi quotes the entire \"suffering servant\" chapter, applying "
        "it to Christ.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 16, 18, 20,
        "Isaiah", "Holy Bible", 52, 8, 10,
        "quotation",
        "The risen Christ quotes Isaiah to the Nephites while foretelling "
        "the Gentiles' role in the latter days.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 20, 32, 45,
        "Isaiah", "Holy Bible", 52, 1, 15,
        "paraphrase",
        "Christ weaves together verses from Isaiah 52 (and, from verse 43 "
        "on, the opening of Isaiah 53) rather than quoting a single "
        "continuous passage.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 22, None, None,
        "Isaiah", "Holy Bible", 54, None, None,
        "quotation",
        "Christ quotes the entirety of Isaiah 54 - \"O thou afflicted, "
        "tossed with tempest\" - to the Nephites.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 27, None, None,
        "Isaiah", "Holy Bible", 29, None, None,
        "paraphrase",
        "Nephi paraphrases and greatly expands Isaiah's \"sealed book\" "
        "prophecy (29 verses become 35), interweaving his own commentary "
        "rather than quoting it verbatim.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 14, None, None,
        "Matthew", "Holy Bible", 7, None, None,
        "paraphrase",
        "Continues the Sermon at the Temple, but omits the Lord's Prayer "
        "(already taught in 3 Nephi 13) and edits other material, so its "
        "27 verses don't line up one-to-one with Matthew's 29.",
    ),
    (
        "Joseph Smith--Matthew", "Pearl of Great Price", 1, None, None,
        "Matthew", "Holy Bible", 24, None, None,
        "translation",
        "Joseph Smith's inspired revision of the Olivet Discourse - the "
        "same conversation as Matthew 24, offset by one verse throughout "
        "(JS-Matthew adds an opening verse Matthew doesn't have) and "
        "expanded further toward the end.",
    ),
    (
        "Moses", "Pearl of Great Price", 2, None, None,
        "Genesis", "Holy Bible", 1, None, None,
        "translation",
        "Joseph Smith's revision of the creation account.",
    ),
    (
        "Moses", "Pearl of Great Price", 3, None, None,
        "Genesis", "Holy Bible", 2, None, None,
        "translation",
        "Continues the creation account and the Garden of Eden - Moses "
        "3:1 restates Genesis 2:1 almost verbatim (\"Thus the heaven and "
        "the earth were finished...\").",
    ),
    (
        "Moses", "Pearl of Great Price", 4, None, None,
        "Genesis", "Holy Bible", 3, None, None,
        "translation",
        "The Fall - Moses adds several verses on Satan's motive before "
        "rejoining Genesis' account of the serpent and the forbidden "
        "fruit.",
    ),
    (
        "Moses", "Pearl of Great Price", 5, None, None,
        "Genesis", "Holy Bible", 4, None, None,
        "translation",
        "Cain and Abel, and Adam's posterity - Moses adds substantial "
        "teaching about sacrifice and the gospel being preached to "
        "Adam's family.",
    ),
    (
        "Moses", "Pearl of Great Price", 6, None, None,
        "Genesis", "Holy Bible", 5, None, None,
        "translation",
        "Adam's genealogy, expanded with an account of a \"book of "
        "remembrance\" and Enoch's ministry beginning.",
    ),
    (
        "Moses", "Pearl of Great Price", 8, None, None,
        "Genesis", "Holy Bible", 6, None, None,
        "translation",
        "Corruption before the Flood and God's call to Noah - Moses 7's "
        "entire account of Enoch's vision has no Genesis counterpart at "
        "all and sits between these two chapters.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 128, 17, 17,
        "Malachi", "Holy Bible", 4, 5, 6,
        "quotation",
        "Joseph Smith quotes Malachi's Elijah prophecy directly within "
        "this verse (\"for Malachi says, last chapter, verses 5th and "
        "6th\"), applying it to temple work for the dead.",
    ),
    (
        "Ether", "The Book of Mormon", 12, 6, 22,
        "Hebrews", "Holy Bible", 11, None, None,
        "paraphrase",
        "Moroni explicitly draws on \"Paul\" (Ether 12:6 echoes Hebrews "
        "11:1's own definition of faith) for his own \"faith chapter,\" "
        "then continues with Book of Mormon examples rather than the Old "
        "Testament ones Paul lists.",
    ),
    (
        "Moroni", "The Book of Mormon", 7, 45, 48,
        "1 Corinthians", "Holy Bible", 13, 4, 8,
        "paraphrase",
        "Mormon's discourse on faith, hope, and charity closely parallels "
        "- in places word for word - Paul's \"love\" chapter.",
    ),
    (
        "Moroni", "The Book of Mormon", 10, 9, 16,
        "1 Corinthians", "Holy Bible", 12, 8, 11,
        "paraphrase",
        "Moroni's list of spiritual gifts parallels Paul's list to the "
        "Corinthians, though Moroni's is longer - it continues with gifts, "
        "like beholding angels, that Paul doesn't list.",
    ),
]


def expand_chapter_blocks(blocks: list[tuple]) -> list[tuple]:
    """One whole-chapter ENTRIES-shaped tuple per chapter in each block,
    the related side's chapter number advancing in lockstep."""
    expanded = []
    for (
        book, volume, chapter_start, chapter_end,
        related_book, related_volume, related_chapter_start,
        relationship, note,
    ) in blocks:
        span = chapter_end - chapter_start
        for offset in range(span + 1):
            expanded.append(
                (
                    book, volume, chapter_start + offset, None, None,
                    related_book, related_volume, related_chapter_start + offset, None, None,
                    relationship, note,
                )
            )
    return expanded


def resolve_volume_slug(conn, volume_name: str) -> str:
    row = conn.execute("SELECT slug FROM volumes WHERE name = ?", (volume_name,)).fetchone()
    if row is None:
        raise ValueError(f"No such volume: {volume_name!r}")
    return row["slug"]


def verify_entry(conn, entry: tuple) -> None:
    """Sanity-check one entry against the actual imported text before it's
    written: both chapters must exist, and any verse range given must fall
    within that chapter's real verse count - catches a typo'd chapter or
    verse number rather than silently writing a broken cross-reference."""
    (
        book, volume, chapter, verse_start, verse_end,
        related_book, related_volume, related_chapter, related_verse_start, related_verse_end,
        _relationship, _note,
    ) = entry
    for b, v, c, vs, ve in (
        (book, volume, chapter, verse_start, verse_end),
        (related_book, related_volume, related_chapter, related_verse_start, related_verse_end),
    ):
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM verses vv "
            "JOIN chapters ch ON ch.id = vv.chapter_id "
            "JOIN books bk ON bk.id = ch.book_id "
            "JOIN volumes vol ON vol.id = bk.volume_id "
            "WHERE bk.name = ? AND vol.name = ? AND ch.chapter_number = ?",
            (b, v, c),
        ).fetchone()
        verse_count = row["n"]
        if verse_count == 0:
            raise ValueError(f"{b} {c} ({v}) has no verses - does this chapter exist?")
        if vs is not None and vs > verse_count:
            raise ValueError(f"{b} {c}:{vs} ({v}) is out of range - chapter only has {verse_count} verses")
        if ve is not None and ve > verse_count:
            raise ValueError(f"{b} {c}:{ve} ({v}) is out of range - chapter only has {verse_count} verses")


def rebuild(conn) -> None:
    conn.execute("DELETE FROM cross_references")

    all_entries = expand_chapter_blocks(CHAPTER_BLOCKS) + ENTRIES
    print(f"Verifying {len(all_entries)} cross-reference entries against imported text...")
    for entry in all_entries:
        verify_entry(conn, entry)
    print("  All entries verified.")

    print("Writing cross_references...")
    for sort_order, entry in enumerate(all_entries, start=1):
        (
            book, volume, chapter, verse_start, verse_end,
            related_book, related_volume, related_chapter, related_verse_start, related_verse_end,
            relationship, note,
        ) = entry
        conn.execute(
            "INSERT INTO cross_references "
            "(volume_slug, book_name, chapter_number, verse_start, verse_end, "
            "related_volume_slug, related_book_name, related_chapter_number, "
            "related_verse_start, related_verse_end, relationship, note, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                resolve_volume_slug(conn, volume), book, chapter, verse_start, verse_end,
                resolve_volume_slug(conn, related_volume), related_book, related_chapter,
                related_verse_start, related_verse_end,
                relationship, note, sort_order,
            ),
        )
    conn.commit()
    print(f"  {len(all_entries)} entries written.")


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "data" / "scriptures.db"
    conn = connect(db_path)
    rebuild(conn)
    conn.close()
    print()
    print(f"Database written to: {db_path}")


if __name__ == "__main__":
    main()
