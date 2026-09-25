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

This is an intentionally ongoing, incremental list, not a finished one -
the goal is eventually covering notable parallels across the whole
standard works (the New Testament's own many quotations of the Old
Testament very much included), added a well-verified batch at a time
rather than all at once. A public-domain dataset exists for the
Bible-internal side (the Treasury of Scripture Knowledge, ~500,000
cross-references) but is deliberately NOT bulk-imported here - it isn't
doctrine-tagged, and at that scale would bury a chapter in loosely-related
verses rather than surfacing the handful that actually matter, the
opposite of this feature's own accuracy-first design.

DOCTRINE: each entry names the doctrine it's actually about via
TOPIC_SLUGS - a comma-separated string of slugs from the Topical Guide's
own topic list (see build_topical_guide.py's TOPICS), reused rather than
inventing a second taxonomy. Left empty only when no existing topic is a
close enough fit; the note still names the doctrine in prose either way.
Every note leads with what doctrine the passage is teaching and how both
sides agree on it, then (where relevant) how the wording or scope
differs - "how the doctrine aligns," not just "what changed."

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

# (book, volume, chapter, verse_start, verse_end,
#  related_book, related_volume, related_chapter, related_verse_start, related_verse_end,
#  relationship, topic_slugs, note)
#
# verse_start/verse_end are None together for a whole-chapter entry (see
# schema.sql). topic_slugs is a comma-separated string, "" if nothing
# existing fits well.
ENTRIES = [
    # --- 2 Nephi 12-24 <-> Isaiah 2-14: quoted nearly word for word, but
    # each chapter is its own doctrine, not one undifferentiated block.
    (
        "2 Nephi", "The Book of Mormon", 12, None, None,
        "Isaiah", "Holy Bible", 2, None, None,
        "quotation", "zion",
        "Both describe the latter-day gathering to \"the mountain of the "
        "Lord's house\" - Zion established before the Second Coming. "
        "Nephi expands Isaiah 2:5's brief admonition into \"yea, come, "
        "for ye have all gone astray, every one to his wicked ways,\" an "
        "invitation Isaiah's own text only implies.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 13, None, None,
        "Isaiah", "Holy Bible", 3, None, None,
        "quotation", "judgment,humility",
        "Both pronounce judgment on Judah for pride and oppression of "
        "the poor, particularly \"the daughters of Zion\" - worldly "
        "pride, in both texts, is what invites divine judgment.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 14, None, None,
        "Isaiah", "Holy Bible", 4, None, None,
        "quotation", "zion",
        "Both promise that a purified remnant of Zion will be protected "
        "- a cloud by day, a flaming fire by night - once its \"filth\" "
        "is washed away, the same covenant-protection doctrine of Zion "
        "as the previous chapter.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 15, None, None,
        "Isaiah", "Holy Bible", 5, None, None,
        "quotation", "house-of-israel",
        "The Song of the Vineyard: Israel as a vineyard the Lord planted "
        "and tended, yet which brought forth wild grapes - God's "
        "covenant care for Israel, and Israel's own responsibility to "
        "bear fruit.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 16, None, None,
        "Isaiah", "Holy Bible", 6, None, None,
        "quotation", "prophets",
        "Isaiah's temple vision and call to prophetic ministry - \"Here "
        "am I; send me\" - the doctrine that prophets are cleansed and "
        "called by God before being sent.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 17, None, None,
        "Isaiah", "Holy Bible", 7, None, None,
        "quotation", "jesus-christ",
        "The sign of Immanuel - \"a virgin shall conceive, and bear a "
        "son\" - read in both texts as a Messianic prophecy of Christ's "
        "birth.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 18, None, None,
        "Isaiah", "Holy Bible", 8, None, None,
        "quotation", "testimony",
        "\"Bind up the testimony, seal the law among my disciples\" - "
        "preserving true testimony intact for a future generation, "
        "alongside a second reference to Immanuel.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 19, None, None,
        "Isaiah", "Holy Bible", 9, None, None,
        "quotation", "jesus-christ",
        "\"For unto us a child is born... Wonderful, Counsellor, The "
        "mighty God\" - Christ's divine titles and eternal government, a "
        "core Messianic prophecy in both texts.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 20, None, None,
        "Isaiah", "Holy Bible", 10, None, None,
        "quotation", "judgment",
        "Assyria as \"the rod of mine anger\" - God using a wicked "
        "nation as an instrument of judgment on Israel, then judging "
        "that nation in turn for its own pride.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 21, None, None,
        "Isaiah", "Holy Bible", 11, None, None,
        "quotation", "second-coming,plan-of-salvation",
        "\"A rod out of the stem of Jesse\" ushering in the peaceable, "
        "Millennial kingdom - Christ's Second Coming and the plan of "
        "salvation's culminating rest from conflict, agreed on by both "
        "texts down to the imagery.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 22, None, None,
        "Isaiah", "Holy Bible", 12, None, None,
        "quotation", "gratitude,salvation",
        "A psalm of thanksgiving for deliverance - \"with joy shall ye "
        "draw water out of the wells of salvation\" - gratitude as the "
        "natural response to God's saving power.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 23, None, None,
        "Isaiah", "Holy Bible", 13, None, None,
        "quotation", "judgment",
        "The \"burden of Babylon\" - judgment on a proud, idolatrous "
        "nation, continuing the same judgment doctrine as chapter 10's "
        "Assyria.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 24, None, None,
        "Isaiah", "Holy Bible", 14, None, None,
        "quotation", "premortal-life",
        "\"How art thou fallen from heaven, O Lucifer\" - read "
        "doctrinally as Satan's fall following his rebellion in the "
        "premortal council, alongside continued judgment on Babylon.",
    ),
    # --- 3 Nephi's Sermon at the Temple <-> the Sermon on the Mount ---
    (
        "3 Nephi", "The Book of Mormon", 12, None, None,
        "Matthew", "Holy Bible", 5, None, None,
        "quotation", "discipleship",
        "The Beatitudes and \"ye are the salt of the earth\" - the "
        "character and higher law expected of Christ's true disciples, "
        "surpassing the law of Moses in both accounts alike.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 13, None, None,
        "Matthew", "Holy Bible", 6, None, None,
        "quotation", "prayer",
        "The Lord's Prayer, given here as the pattern for personal "
        "prayer, alongside teaching on fasting in secret and seeking "
        "\"first the kingdom of God.\"",
    ),
    (
        "3 Nephi", "The Book of Mormon", 14, None, None,
        "Matthew", "Holy Bible", 7, None, None,
        "paraphrase", "obedience",
        "\"Judge not, that ye be not judged,\" then the wise man who "
        "built upon the rock - true discipleship is doing, not merely "
        "hearing, what the Lord commands. 3 Nephi omits the Lord's "
        "Prayer already taught in the previous chapter, so its 27 verses "
        "don't line up one-to-one with Matthew's 29.",
    ),
    # --- 3 Nephi's Malachi block ---
    (
        "3 Nephi", "The Book of Mormon", 24, None, None,
        "Malachi", "Holy Bible", 3, None, None,
        "quotation", "tithing",
        "\"Will a man rob God?... bring ye all the tithes into the "
        "storehouse\" - the doctrine and promised blessing of tithing, "
        "quoted to the Nephites almost word for word.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 25, None, None,
        "Malachi", "Holy Bible", 4, None, None,
        "quotation", "second-coming",
        "The day that \"shall burn as an oven\" at Christ's coming, and "
        "Elijah's promise to \"turn the heart of the fathers to the "
        "children\" - the Second Coming and the sealing power that binds "
        "families (see D&C 128:17 below for how that promise was later "
        "applied to temple work).",
    ),
    # --- Isaiah quoted elsewhere in the Book of Mormon ---
    (
        "Mosiah", "The Book of Mormon", 12, 21, 24,
        "Isaiah", "Holy Bible", 52, 7, 10,
        "quotation", "missionary-work",
        "\"How beautiful upon the mountains are the feet of him that "
        "bringeth good tidings\" - those who publish the gospel's peace "
        "are honored before God. Abinadi quotes it word for word while "
        "testifying before King Noah's priests.",
    ),
    (
        "Mosiah", "The Book of Mormon", 14, None, None,
        "Isaiah", "Holy Bible", 53, None, None,
        "quotation", "atonement",
        "The \"suffering servant\" chapter - \"he was wounded for our "
        "transgressions, he was bruised for our iniquities\" - the "
        "clearest Old Testament prophecy of Christ's atoning sacrifice, "
        "which Abinadi quotes in full and applies directly to Christ.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 16, 18, 20,
        "Isaiah", "Holy Bible", 52, 8, 10,
        "quotation", "house-of-israel",
        "\"The Lord hath made bare his holy arm in the eyes of all the "
        "nations\" - God's latter-day work of gathering scattered "
        "Israel, quoted by the risen Christ while explaining the "
        "Gentiles' role in that gathering.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 20, 32, 45,
        "Isaiah", "Holy Bible", 52, 1, 15,
        "paraphrase", "zion",
        "\"Awake, awake... put on thy strength, O Zion\" - Zion's "
        "latter-day redemption, woven together here with the watchmen "
        "passage above and the opening of Isaiah 53, rather than quoted "
        "as one single continuous passage.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 22, None, None,
        "Isaiah", "Holy Bible", 54, None, None,
        "quotation", "covenants",
        "\"My covenant of peace shall not be removed\" - God's "
        "everlasting covenant with a gathered, afflicted-but-redeemed "
        "Zion, quoted here in its entirety.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 27, None, None,
        "Isaiah", "Holy Bible", 29, None, None,
        "paraphrase", "restoration",
        "The \"sealed book\" prophecy - \"a marvelous work and a "
        "wonder\" - understood as foretelling the Book of Mormon's own "
        "coming forth, a foundational Restoration prophecy. Nephi "
        "paraphrases and greatly expands it (29 verses become 35) rather "
        "than quoting it verbatim.",
    ),
    # --- Joseph Smith Translation / Moses: revisions, not quotations ---
    (
        "Joseph Smith--Matthew", "Pearl of Great Price", 1, None, None,
        "Matthew", "Holy Bible", 24, None, None,
        "translation", "second-coming",
        "The Olivet Discourse - signs of the times preceding the Second "
        "Coming, the same doctrine in both. Joseph Smith's inspired "
        "revision of the same conversation, offset by one verse "
        "throughout and expanded further toward the end.",
    ),
    (
        "Moses", "Pearl of Great Price", 2, None, None,
        "Genesis", "Holy Bible", 1, None, None,
        "translation", "creation",
        "The creation of the heavens and the earth, in Joseph Smith's "
        "revision of Genesis' opening account.",
    ),
    (
        "Moses", "Pearl of Great Price", 3, None, None,
        "Genesis", "Holy Bible", 2, None, None,
        "translation", "marriage",
        "\"Therefore shall a man leave his father and mother, and shall "
        "cleave unto his wife\" - marriage instituted in Eden. Moses "
        "3:1 restates Genesis 2:1 almost verbatim (\"Thus the heaven and "
        "the earth were finished...\").",
    ),
    (
        "Moses", "Pearl of Great Price", 4, None, None,
        "Genesis", "Holy Bible", 3, None, None,
        "translation", "agency",
        "The Fall, prefaced in Moses by Satan's own account of seeking "
        "\"to destroy the agency of man\" - agency as the very thing his "
        "rebellion opposed, before rejoining Genesis' account of the "
        "forbidden fruit.",
    ),
    (
        "Moses", "Pearl of Great Price", 5, None, None,
        "Genesis", "Holy Bible", 4, None, None,
        "translation", "sacrifice",
        "Cain and Abel's offerings - Moses adds that sacrifice was "
        "commanded \"in similitude of the only Begotten,\" giving the "
        "doctrine behind an ordinance Genesis simply narrates.",
    ),
    (
        "Moses", "Pearl of Great Price", 6, None, None,
        "Genesis", "Holy Bible", 5, None, None,
        "translation", "baptism",
        "Adam's genealogy, expanded with the gospel being taught to "
        "Adam - \"by the water... ye keep the commandment... by the "
        "Spirit ye are justified\" - one of scripture's clearest "
        "statements of baptism's doctrine, absent from Genesis' brief "
        "record.",
    ),
    (
        "Moses", "Pearl of Great Price", 8, None, None,
        "Genesis", "Holy Bible", 6, None, None,
        "translation", "repentance",
        "God's call to repent before the Flood - \"I am angry with this "
        "people, and my fierce anger is kindled against them\" - "
        "repentance as the offer that precedes judgment. Moses 7's "
        "entire account of Enoch's vision has no Genesis counterpart at "
        "all and sits between these two chapters.",
    ),
    # --- D&C / Bible ---
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 128, 17, 17,
        "Malachi", "Holy Bible", 4, 5, 6,
        "quotation", "temple",
        "Elijah's promise, applied here to baptism for the dead - the "
        "sealing power that makes temple ordinance work for deceased "
        "ancestors possible. Joseph Smith quotes it directly (\"for "
        "Malachi says, last chapter, verses 5th and 6th\") before "
        "explaining its meaning.",
    ),
    # --- Book of Mormon / New Testament paraphrases ---
    (
        "Ether", "The Book of Mormon", 12, 6, 22,
        "Hebrews", "Holy Bible", 11, None, None,
        "paraphrase", "faith",
        "Faith defined as \"things which are hoped for and not seen\" - "
        "Moroni explicitly draws on \"Paul\" (Ether 12:6 echoes Hebrews "
        "11:1) for his own \"faith chapter,\" then illustrates it with "
        "Book of Mormon examples rather than Paul's Old Testament ones.",
    ),
    (
        "Moroni", "The Book of Mormon", 7, 45, 48,
        "1 Corinthians", "Holy Bible", 13, 4, 8,
        "paraphrase", "charity",
        "\"Charity never faileth\" - charity as the pure love of Christ, "
        "described here in places word for word the same as Paul's "
        "\"love\" chapter.",
    ),
    (
        "Moroni", "The Book of Mormon", 10, 9, 16,
        "1 Corinthians", "Holy Bible", 12, 8, 11,
        "paraphrase", "holy-ghost",
        "Spiritual gifts given \"by the Spirit\" for the edification of "
        "the Church - Moroni's list parallels Paul's, though it "
        "continues further, adding gifts like beholding angels that "
        "Paul doesn't list.",
    ),
    # --- New Testament quotes Old Testament: the clearest, most explicit
    # cases first - passages the New Testament itself flags as fulfilled
    # prophecy ("that it might be fulfilled," "as it is written," a
    # direct quotation from Christ or an apostle) rather than a looser
    # thematic echo. Both sides live in the same "Holy Bible" volume here.
    (
        "Matthew", "Holy Bible", 1, 22, 23,
        "Isaiah", "Holy Bible", 7, 14, 14,
        "quotation", "jesus-christ",
        "The sign of Immanuel - \"a virgin shall conceive, and bear a "
        "son\" - Matthew explicitly quotes Isaiah as fulfilled prophecy "
        "of Christ's birth (\"that it might be fulfilled which was "
        "spoken of the Lord by the prophet\").",
    ),
    (
        "Matthew", "Holy Bible", 2, 5, 6,
        "Micah", "Holy Bible", 5, 2, 2,
        "quotation", "jesus-christ",
        "Bethlehem named centuries in advance as the Messiah's "
        "birthplace - the chief priests and scribes quote this very "
        "verse to Herod when asked where Christ should be born.",
    ),
    (
        "Matthew", "Holy Bible", 2, 14, 15,
        "Hosea", "Holy Bible", 11, 1, 1,
        "quotation", "jesus-christ",
        "\"Out of Egypt have I called my son\" - originally about "
        "Israel's own exodus, applied by Matthew to the child Jesus "
        "fleeing to and returning from Egypt, explicitly marked as "
        "fulfillment.",
    ),
    (
        "Matthew", "Holy Bible", 3, 3, 3,
        "Isaiah", "Holy Bible", 40, 3, 3,
        "quotation", "prophets",
        "\"The voice of him that crieth in the wilderness, prepare ye "
        "the way of the Lord\" - Matthew identifies this prophecy with "
        "John the Baptist's own ministry preparing the way for Christ.",
    ),
    (
        "Matthew", "Holy Bible", 4, 4, 4,
        "Deuteronomy", "Holy Bible", 8, 3, 3,
        "quotation", "temptation",
        "\"Man shall not live by bread alone, but by every word that "
        "proceedeth out of the mouth of God\" - Christ quotes Moses' own "
        "teaching on Israel's wilderness wandering while resisting "
        "Satan's first temptation.",
    ),
    (
        "Luke", "Holy Bible", 4, 18, 19,
        "Isaiah", "Holy Bible", 61, 1, 2,
        "quotation", "jesus-christ",
        "\"The Spirit of the Lord is upon me... to preach the gospel to "
        "the poor\" - Christ reads this passage aloud in the Nazareth "
        "synagogue and declares, \"this day is this scripture fulfilled "
        "in your ears,\" one of His clearest public claims to be the "
        "promised Messiah.",
    ),
    (
        "Matthew", "Holy Bible", 21, 42, 42,
        "Psalms", "Holy Bible", 118, 22, 22,
        "quotation", "jesus-christ",
        "\"The stone which the builders rejected, the same is become "
        "the head of the corner\" - Christ applies this directly to "
        "Himself, asking the chief priests and elders, \"Did ye never "
        "read in the scriptures...\"",
    ),
    (
        "Matthew", "Holy Bible", 21, 4, 5,
        "Zechariah", "Holy Bible", 9, 9, 9,
        "quotation", "jesus-christ",
        "\"Thy King cometh unto thee... riding upon an ass\" - Christ's "
        "triumphal entry into Jerusalem, explicitly identified by "
        "Matthew as fulfilling this prophecy.",
    ),
    (
        "Matthew", "Holy Bible", 27, 46, 46,
        "Psalms", "Holy Bible", 22, 1, 1,
        "quotation", "atonement",
        "\"My God, my God, why hast thou forsaken me?\" - Christ quotes "
        "this psalm of suffering word for word from the cross, at the "
        "depth of His atoning suffering.",
    ),
    (
        "John", "Holy Bible", 19, 24, 24,
        "Psalms", "Holy Bible", 22, 18, 18,
        "quotation", "atonement",
        "\"They part my garments among them, and cast lots upon my "
        "vesture\" - John notes explicitly that this was fulfilled when "
        "the soldiers cast lots for Christ's clothing at the "
        "crucifixion - the same psalm quoted in Matthew 27:46 above.",
    ),
    (
        "Matthew", "Holy Bible", 8, 17, 17,
        "Isaiah", "Holy Bible", 53, 4, 4,
        "quotation", "atonement",
        "\"Himself took our infirmities, and bare our sicknesses\" - "
        "Matthew explicitly quotes the suffering servant prophecy to "
        "explain Christ's healing miracles, the same chapter Mosiah 14 "
        "quotes in full over the Atonement itself (see above).",
    ),
    (
        "Acts", "Holy Bible", 2, 16, 21,
        "Joel", "Holy Bible", 2, 28, 32,
        "quotation", "holy-ghost",
        "\"I will pour out my spirit upon all flesh\" - Peter explicitly "
        "quotes Joel's prophecy to explain the miraculous outpouring of "
        "the Holy Ghost at Pentecost.",
    ),
    (
        "Romans", "Holy Bible", 4, 3, 3,
        "Genesis", "Holy Bible", 15, 6, 6,
        "quotation", "faith",
        "\"Abraham believed God, and it was counted unto him for "
        "righteousness\" - Paul quotes this directly to teach that "
        "righteousness comes through faith, not merely obedience to "
        "the law.",
    ),
    (
        "Romans", "Holy Bible", 1, 17, 17,
        "Habakkuk", "Holy Bible", 2, 4, 4,
        "quotation", "faith",
        "\"The just shall live by faith\" - quoted by Paul as the "
        "foundation of his entire argument that the gospel's "
        "righteousness is received through faith.",
    ),
    (
        "Matthew", "Holy Bible", 19, 5, 5,
        "Genesis", "Holy Bible", 2, 24, 24,
        "quotation", "marriage",
        "\"A man shall leave his father and mother, and shall cleave "
        "unto his wife\" - Christ quotes marriage's original institution "
        "in Eden while teaching on its permanence, the same doctrine "
        "Moses 3 restates in its own revision of this chapter (see "
        "above).",
    ),
    (
        "Matthew", "Holy Bible", 22, 37, 37,
        "Deuteronomy", "Holy Bible", 6, 5, 5,
        "quotation", "love",
        "\"Thou shalt love the Lord thy God with all thine heart\" - "
        "quoted by Christ as the first and great commandment.",
    ),
    (
        "Matthew", "Holy Bible", 22, 39, 39,
        "Leviticus", "Holy Bible", 19, 18, 18,
        "quotation", "love",
        "\"Thou shalt love thy neighbour as thyself\" - quoted by Christ "
        "as the second great commandment, \"like unto\" the first (see "
        "Deuteronomy 6:5 above).",
    ),
    (
        "Matthew", "Holy Bible", 22, 44, 44,
        "Psalms", "Holy Bible", 110, 1, 1,
        "quotation", "jesus-christ",
        "\"The LORD said unto my Lord, sit thou on my right hand\" - "
        "Christ quotes this psalm to testify of His own divine Sonship, "
        "asking the Pharisees how David's own \"Lord\" could also be "
        "David's descendant.",
    ),
    (
        "Matthew", "Holy Bible", 11, 4, 5,
        "Isaiah", "Holy Bible", 35, 5, 6,
        "quotation", "jesus-christ",
        "\"The eyes of the blind shall be opened... the lame man shall "
        "leap as an hart\" - Christ points to His own healing miracles "
        "as proof, to John the Baptist's disciples, that He is the "
        "promised Messiah these signs describe.",
    ),
]


def resolve_volume_slug(conn, volume_name: str) -> str:
    row = conn.execute("SELECT slug FROM volumes WHERE name = ?", (volume_name,)).fetchone()
    if row is None:
        raise ValueError(f"No such volume: {volume_name!r}")
    return row["slug"]


def verify_entry(conn, entry: tuple) -> None:
    """Sanity-check one entry against the actual imported text before it's
    written: both chapters must exist, any verse range given must fall
    within that chapter's real verse count, and every topic slug named
    must be a real Topical Guide topic - catches a typo'd chapter, verse
    number, or topic slug rather than silently writing a broken entry."""
    (
        book, volume, chapter, verse_start, verse_end,
        related_book, related_volume, related_chapter, related_verse_start, related_verse_end,
        _relationship, topic_slugs, _note,
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

    for slug in (s.strip() for s in topic_slugs.split(",") if s.strip()):
        exists = conn.execute("SELECT 1 FROM topics WHERE slug = ?", (slug,)).fetchone()
        if exists is None:
            raise ValueError(f"{book} {chapter}: no such topic slug {slug!r} - typo, or topics table not built yet?")


def rebuild(conn) -> None:
    conn.execute("DELETE FROM cross_references")

    print(f"Verifying {len(ENTRIES)} cross-reference entries against imported text...")
    for entry in ENTRIES:
        verify_entry(conn, entry)
    print("  All entries verified.")

    print("Writing cross_references...")
    for sort_order, entry in enumerate(ENTRIES, start=1):
        (
            book, volume, chapter, verse_start, verse_end,
            related_book, related_volume, related_chapter, related_verse_start, related_verse_end,
            relationship, topic_slugs, note,
        ) = entry
        conn.execute(
            "INSERT INTO cross_references "
            "(volume_slug, book_name, chapter_number, verse_start, verse_end, "
            "related_volume_slug, related_book_name, related_chapter_number, "
            "related_verse_start, related_verse_end, relationship, topic_slugs, note, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                resolve_volume_slug(conn, volume), book, chapter, verse_start, verse_end,
                resolve_volume_slug(conn, related_volume), related_book, related_chapter,
                related_verse_start, related_verse_end,
                relationship, topic_slugs, note, sort_order,
            ),
        )
    conn.commit()
    print(f"  {len(ENTRIES)} entries written.")


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "data" / "scriptures.db"
    conn = connect(db_path)
    rebuild(conn)
    conn.close()
    print()
    print(f"Database written to: {db_path}")


if __name__ == "__main__":
    main()
