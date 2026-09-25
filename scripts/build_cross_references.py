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

Four relationship kinds (see also schema.sql's own comment):
- "quotation": wording matches (allowing for translation-era spelling).
- "paraphrase": same content/point, but wording diverges meaningfully, or
  only part of the passage is quoted amid original commentary.
- "translation": a JST/Moses-style revision of the very same underlying
  narrative, not an independent quotation of it.
- "typology": a symbol or event scripture itself explicitly identifies as
  pointing to Christ or His mission - the brazen serpent, the Passover
  lamb, Jonah's three days, and so on. Held to the same accuracy bar as
  every other relationship here: the connection must be one scripture
  itself states plainly (Christ's own "as Moses lifted up the serpent...
  even so must the Son of man be lifted up," Paul's "Christ our passover
  is sacrificed for us," Alma explicitly calling the brazen serpent "a
  type"), never a connection only later tradition or this app's own
  inference draws. A rich, well-known typological thread (like the
  brazen serpent) is deliberately captured as several pair-wise entries
  - one per pairing scripture itself makes - rather than one entry
  trying to name every anchor at once.
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
    # --- Typology: symbols and events scripture itself explicitly ties to
    # Christ, not a quotation of one passage by another. The brazen
    # serpent gets three separate entries - one per pairing scripture
    # itself makes - rather than trying to name every anchor in one row.
    (
        "John", "Holy Bible", 3, 14, 15,
        "Numbers", "Holy Bible", 21, 8, 9,
        "typology", "jesus-christ",
        "Christ Himself draws this connection: \"as Moses lifted up the "
        "serpent in the wilderness, even so must the Son of man be "
        "lifted up.\" Looking to the brazen serpent in faith healed the "
        "Israelites' snakebite; looking to Christ in faith saves from "
        "sin.",
    ),
    (
        "Alma", "The Book of Mormon", 33, 19, 22,
        "Numbers", "Holy Bible", 21, 8, 9,
        "typology", "faith",
        "Alma uses the word \"type\" outright: \"a type was raised up in "
        "the wilderness, that whosoever would look upon it might live\" "
        "- faith as simple as looking, whether at the serpent or at "
        "Christ, is still enough to save.",
    ),
    (
        "Helaman", "The Book of Mormon", 8, 14, 15,
        "Numbers", "Holy Bible", 21, 8, 9,
        "typology", "jesus-christ",
        "Nephi (son of Helaman) makes the identical application "
        "generations before Christ's own ministry: \"as he lifted up the "
        "brazen serpent... even so shall he be lifted up who should "
        "come.\"",
    ),
    (
        "Matthew", "Holy Bible", 12, 39, 40,
        "Jonah", "Holy Bible", 1, 17, 17,
        "typology", "resurrection",
        "\"As Jonas was three days and three nights in the whale's "
        "belly; so shall the Son of man be three days and three nights "
        "in the heart of the earth\" - Christ's own explicit sign of His "
        "coming resurrection.",
    ),
    (
        "1 Corinthians", "Holy Bible", 5, 7, 7,
        "Exodus", "Holy Bible", 12, 3, 7,
        "typology", "atonement",
        "\"Christ our passover is sacrificed for us\" - Paul explicitly "
        "identifies the Passover lamb, whose blood protected Israel from "
        "the destroyer, with Christ's own atoning sacrifice.",
    ),
    (
        "Hebrews", "Holy Bible", 7, 1, 17,
        "Genesis", "Holy Bible", 14, 18, 20,
        "typology", "priesthood",
        "Melchizedek's priesthood, explicitly named as a type of "
        "Christ's own eternal priesthood: \"a priest for ever after the "
        "order of Melchisedec.\"",
    ),
    (
        "Alma", "The Book of Mormon", 13, 14, 19,
        "Genesis", "Holy Bible", 14, 18, 20,
        "typology", "priesthood",
        "Alma teaches this same Melchizedek priesthood doctrine "
        "centuries before Hebrews was written, calling him \"a high "
        "priest after this same order\" - see Hebrews 7 above for Paul's "
        "own version of the same teaching.",
    ),
    (
        "John", "Holy Bible", 6, 31, 35,
        "Exodus", "Holy Bible", 16, 14, 15,
        "typology", "jesus-christ",
        "\"Our fathers did eat manna... I am the bread of life\" - Christ "
        "explicitly applies the wilderness manna to Himself as the true "
        "bread that sustains eternal life.",
    ),
    (
        "1 Corinthians", "Holy Bible", 10, 1, 4,
        "Exodus", "Holy Bible", 17, 5, 6,
        "typology", "jesus-christ",
        "\"They drank of that spiritual Rock that followed them: and "
        "that Rock was Christ\" - Paul's own explicit identification of "
        "the rock struck for water in the wilderness.",
    ),
    # --- D&C's own explicit ties back to the Bible ---
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 70, 98,
        "1 Corinthians", "Holy Bible", 15, 40, 42,
        "paraphrase", "exaltation",
        "\"Celestial\" and \"terrestrial\" bodies of differing glory - "
        "Paul's own terms, which this vision borrows and greatly expands "
        "into the doctrine of three degrees of glory, adding a third, "
        "\"telestial,\" glory Paul doesn't name.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 45, 16, 59,
        "Matthew", "Holy Bible", 24, None, None,
        "paraphrase", "second-coming",
        "The Lord's own retelling of the Olivet Discourse's signs of the "
        "times, given directly to Joseph Smith - independently worded "
        "from both the King James text and Joseph Smith's own separate "
        "revision in Joseph Smith-Matthew above, but the same doctrine "
        "of watching for the signs preceding the Second Coming.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 133, 48, 50,
        "Isaiah", "Holy Bible", 63, 1, 3,
        "quotation", "second-coming",
        "\"His apparel... like him that treadeth in the wine-vat\" - "
        "Christ's own return in glory and judgment, described in nearly "
        "Isaiah's own words.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 132, 34, 38,
        "Genesis", "Holy Bible", 16, 1, 4,
        "paraphrase", "covenants",
        "Retells Abraham and Sarah giving Hagar to Abraham as wife, "
        "\"because this was the law\" of the time - used to teach that a "
        "commandment from God can override an otherwise-binding law, "
        "part of this section's broader teaching on covenants.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 107, 2, 4,
        "Genesis", "Holy Bible", 14, 18, 20,
        "paraphrase", "priesthood",
        "\"The first priesthood is called the Melchizedek Priesthood, "
        "because Melchizedek was such a great high priest\" - the same "
        "Melchizedek Hebrews 7 and Alma 13 both draw on above, explaining "
        "why the priesthood itself carries his name.",
    ),
    # --- More typology, scripture's own explicit connections ---
    (
        "Hebrews", "Holy Bible", 10, 19, 20,
        "Matthew", "Holy Bible", 27, 51, 51,
        "typology", "atonement",
        "The temple veil torn in two at Christ's death, which Hebrews "
        "explains as opening \"a new and living way\" into God's presence "
        "\"through the veil, that is to say, his flesh\" - Christ's own "
        "body as the veil, torn open by His atoning death.",
    ),
    (
        "1 Peter", "Holy Bible", 3, 20, 21,
        "Genesis", "Holy Bible", 7, 1, 7,
        "typology", "baptism",
        "Peter explicitly reads Noah's family being saved through water "
        "in the ark as \"the like figure whereunto even baptism doth "
        "also now save us\" - the Flood as a type of baptism's own "
        "saving power.",
    ),
    (
        "Hebrews", "Holy Bible", 11, 17, 19,
        "Genesis", "Holy Bible", 22, 9, 13,
        "typology", "faith",
        "Abraham offering Isaac, \"accounting that God was able to raise "
        "him up, even from the dead\" - Paul explicitly calls this \"a "
        "figure\" of resurrection, Abraham's faith foreshadowing God's "
        "own willingness to give His Son.",
    ),
    (
        "Hebrews", "Holy Bible", 9, 11, 12,
        "Leviticus", "Holy Bible", 16, 14, 15,
        "typology", "atonement",
        "The high priest entering the Holy of Holies once a year with "
        "sacrificial blood on the Day of Atonement - Paul explains "
        "Christ fulfilled this by entering heaven itself \"by his own "
        "blood,\" once, for all.",
    ),
    (
        "Galatians", "Holy Bible", 3, 13, 13,
        "Deuteronomy", "Holy Bible", 21, 22, 23,
        "quotation", "atonement",
        "\"Cursed is every one that hangeth on a tree\" - Paul quotes "
        "this directly, teaching that Christ bore the law's own curse on "
        "the cross so that others could be redeemed from it.",
    ),
    # --- D&C 77: an explicit, verse-by-verse interpretation of Revelation
    # 4-11, each answer naming its own source chapter/verse outright -
    # about as clean a "how these relate" case as scripture offers.
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 77, 1, 4,
        "Revelation", "Holy Bible", 4, 6, 6,
        "paraphrase", "second-coming",
        "Explains John's vision plainly: the \"sea of glass\" is the "
        "earth itself in its future sanctified, immortal, and eternal "
        "state - the four beasts figures of the classes of created "
        "beings in that same glorified condition.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 77, 5, 5,
        "Revelation", "Holy Bible", 4, 4, 4,
        "paraphrase", "resurrection",
        "The twenty-four elders are identified as real, specific people "
        "- ministers from John's own era who had already died and were "
        "then in paradise - not symbolic figures.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 77, 6, 7,
        "Revelation", "Holy Bible", 5, 1, 1,
        "paraphrase", "revelation",
        "The sealed book contains \"the revealed will, mysteries, and "
        "works of God\" for the earth's full seven-thousand-year "
        "temporal existence, one seal's worth of history unsealed at a "
        "time.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 77, 8, 9,
        "Revelation", "Holy Bible", 7, 1, 2,
        "paraphrase", "second-coming",
        "The four angels holding back the four winds are literal angels "
        "given power to restrain until the gathering and sealing work "
        "described in the following verses is complete.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 77, 11, 11,
        "Revelation", "Holy Bible", 7, 4, 8,
        "paraphrase", "priesthood",
        "The 144,000 sealed are explicitly identified as \"high priests, "
        "ordained unto the holy order of God,\" sent to gather Israel "
        "from every nation - not a symbolic number alone, but a "
        "description of priesthood service.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 77, 14, 14,
        "Revelation", "Holy Bible", 10, 1, 2,
        "paraphrase", "prophets",
        "The little book John ate was \"a mission, and an ordinance\" - "
        "identified here as Elias, the one who \"must come and restore "
        "all things\" before the gathering of Israel.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 77, 15, 15,
        "Revelation", "Holy Bible", 11, 3, 4,
        "paraphrase", "prophets",
        "The two witnesses are named plainly as two literal prophets, "
        "raised up to prophesy to the Jews in Jerusalem in the last "
        "days.",
    ),
    # --- More explicit New Testament quotations of the Old Testament ---
    (
        "Matthew", "Holy Bible", 12, 18, 21,
        "Isaiah", "Holy Bible", 42, 1, 4,
        "quotation", "jesus-christ",
        "\"Behold my servant... he shall bring forth judgment\" - "
        "explicitly introduced by Matthew as fulfilled prophecy of "
        "Christ's own gentle, non-contentious ministry.",
    ),
    (
        "Matthew", "Holy Bible", 21, 16, 16,
        "Psalms", "Holy Bible", 8, 2, 2,
        "quotation", "jesus-christ",
        "\"Out of the mouth of babes and sucklings hast thou ordained "
        "strength\" - Christ quotes this directly to the chief priests "
        "when children praised Him in the temple.",
    ),
    (
        "Matthew", "Holy Bible", 13, 14, 15,
        "Isaiah", "Holy Bible", 6, 9, 10,
        "quotation", "revelation",
        "\"Hearing ye shall hear, and shall not understand\" - Christ "
        "explains that He teaches in parables because this very "
        "prophecy of spiritual dullness is fulfilled in His own "
        "generation.",
    ),
    (
        "Matthew", "Holy Bible", 13, 35, 35,
        "Psalms", "Holy Bible", 78, 2, 2,
        "quotation", "revelation",
        "\"I will utter dark sayings of old\" - Matthew explicitly ties "
        "Christ's use of parables to this psalm's own prophecy of "
        "teaching in hidden sayings.",
    ),
    (
        "Matthew", "Holy Bible", 26, 31, 31,
        "Zechariah", "Holy Bible", 13, 7, 7,
        "quotation", "jesus-christ",
        "\"Smite the shepherd, and the sheep shall be scattered\" - "
        "Christ quotes this directly the night of His betrayal, "
        "foretelling the disciples' own scattering.",
    ),
    (
        "John", "Holy Bible", 13, 18, 18,
        "Psalms", "Holy Bible", 41, 9, 9,
        "quotation", "atonement",
        "\"He that eateth bread with me hath lifted up his heel against "
        "me\" - Christ quotes this at the Last Supper, identifying His "
        "own betrayal by Judas as fulfilling David's words.",
    ),
    (
        "John", "Holy Bible", 15, 25, 25,
        "Psalms", "Holy Bible", 69, 4, 4,
        "quotation", "atonement",
        "\"They hated me without a cause\" - Christ applies this psalm "
        "of suffering directly to the world's hatred of Him.",
    ),
    (
        "John", "Holy Bible", 19, 36, 36,
        "Exodus", "Holy Bible", 12, 46, 46,
        "typology", "atonement",
        "The Passover lamb's bones were never to be broken - John "
        "explicitly notes this was fulfilled when Christ's legs were "
        "not broken on the cross, unlike the two thieves crucified with "
        "Him.",
    ),
    (
        "John", "Holy Bible", 19, 37, 37,
        "Zechariah", "Holy Bible", 12, 10, 10,
        "quotation", "atonement",
        "\"They shall look on him whom they pierced\" - John explicitly "
        "quotes this as fulfilled by the spear thrust into Christ's "
        "side at the crucifixion.",
    ),
    (
        "Acts", "Holy Bible", 3, 22, 22,
        "Deuteronomy", "Holy Bible", 18, 15, 15,
        "quotation", "prophets",
        "\"A Prophet shall the Lord... raise up unto you... like unto "
        "me\" - Peter quotes Moses' own prophecy directly, applying it "
        "to Christ before the people at the temple.",
    ),
    (
        "Acts", "Holy Bible", 2, 27, 27,
        "Psalms", "Holy Bible", 16, 10, 10,
        "quotation", "resurrection",
        "\"Thou wilt not leave my soul in hell, neither wilt thou "
        "suffer thine Holy One to see corruption\" - Peter quotes this "
        "word for word at Pentecost as prophecy of Christ's own "
        "resurrection before His body could decay.",
    ),
    (
        "Romans", "Holy Bible", 9, 33, 33,
        "Isaiah", "Holy Bible", 28, 16, 16,
        "quotation", "jesus-christ",
        "\"A stone of stumbling and rock of offence\" - Paul applies "
        "Isaiah's cornerstone prophecy to Christ, whom many stumbled "
        "over rather than believed on.",
    ),
    (
        "Philippians", "Holy Bible", 2, 10, 11,
        "Isaiah", "Holy Bible", 45, 23, 23,
        "quotation", "jesus-christ",
        "\"Every knee shall bow, every tongue... confess\" - Paul "
        "quotes this directly, applying to Christ what Isaiah's own "
        "words say only God Himself may claim.",
    ),
    (
        "1 Corinthians", "Holy Bible", 15, 54, 55,
        "Isaiah", "Holy Bible", 25, 8, 8,
        "quotation", "resurrection",
        "\"He will swallow up death in victory\" - Paul quotes this "
        "directly as fulfilled through Christ's resurrection, the "
        "promise that death itself will finally be undone.",
    ),
    (
        "1 Corinthians", "Holy Bible", 15, 54, 55,
        "Hosea", "Holy Bible", 13, 14, 14,
        "quotation", "resurrection",
        "\"O death, I will be thy plagues; O grave, I will be thy "
        "destruction\" - Paul quotes this alongside Isaiah 25:8 above in "
        "the same triumphant declaration over death through Christ's "
        "resurrection.",
    ),
    (
        "Galatians", "Holy Bible", 3, 8, 8,
        "Genesis", "Holy Bible", 12, 3, 3,
        "quotation", "covenants",
        "\"In thee shall all nations be blessed\" - Paul explicitly "
        "calls this verse itself \"the gospel\" preached beforehand to "
        "Abraham, tying the Abrahamic covenant directly to salvation "
        "through faith in Christ.",
    ),
    (
        "Hebrews", "Holy Bible", 10, 30, 30,
        "Deuteronomy", "Holy Bible", 32, 35, 35,
        "quotation", "judgment",
        "\"Vengeance belongeth unto me... the Lord shall judge his "
        "people\" - quoted directly to warn against turning away from "
        "Christ after receiving the truth.",
    ),
    (
        "Hebrews", "Holy Bible", 12, 5, 6,
        "Proverbs", "Holy Bible", 3, 11, 12,
        "quotation", "trials-and-adversity",
        "\"Whom the Lord loveth he correcteth\" - quoted directly to "
        "teach that trials are evidence of God's fatherly love, not His "
        "abandonment.",
    ),
    # --- Book of Mormon prophecy/fulfillment and shared distinctive
    # language with the Bible - not verbatim quotation, but wording
    # and imagery close enough to be more than coincidence.
    (
        "Romans", "Holy Bible", 11, 17, 24,
        "Jacob", "The Book of Mormon", 5, None, None,
        "paraphrase", "house-of-israel",
        "Paul uses the same olive-tree grafting imagery - wild branches "
        "grafted in among the natural, some broken off for unbelief - "
        "that Zenos' allegory (quoted in full by Jacob) develops at far "
        "greater length: God's care for scattered Israel and grafted-in "
        "Gentiles alike.",
    ),
    (
        "Luke", "Holy Bible", 22, 44, 44,
        "Mosiah", "The Book of Mormon", 3, 7, 7,
        "paraphrase", "atonement",
        "\"Blood cometh from every pore\" - Benjamin prophesies the "
        "Atonement's suffering in strikingly specific, physical terms "
        "nearly a century before Luke records Christ's own sweat "
        "becoming \"as it were great drops of blood\" in Gethsemane.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 19, 18, 18,
        "Mosiah", "The Book of Mormon", 3, 7, 7,
        "paraphrase", "atonement",
        "Christ's own later description of His suffering - \"to bleed "
        "at every pore\" - matches Benjamin's prophecy almost word for "
        "word, given independently by revelation centuries apart.",
    ),
    (
        "Hebrews", "Holy Bible", 2, 17, 18,
        "Alma", "The Book of Mormon", 7, 11, 13,
        "paraphrase", "atonement",
        "Both texts use the same striking word: Alma says Christ "
        "suffers \"that he may know... how to succor his people,\" "
        "Hebrews that He is \"able to succour them that are tempted\" - "
        "Christ's own suffering as the very thing that qualifies Him to "
        "help others through theirs.",
    ),
    (
        "Hebrews", "Holy Bible", 4, 15, 15,
        "Alma", "The Book of Mormon", 7, 11, 13,
        "paraphrase", "atonement",
        "\"Touched with the feeling of our infirmities... tempted like "
        "as we are\" - the same doctrine Alma teaches above: Christ's "
        "own experience of mortal suffering lets Him fully understand "
        "and help His people.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 1, 15, 21,
        "Helaman", "The Book of Mormon", 14, 2, 6,
        "paraphrase", "prophets",
        "Samuel the Lamanite prophesies a night and a day and a night "
        "without darkness as the sign of Christ's birth - fulfilled "
        "precisely as foretold, five years later.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 8, 5, 23,
        "Helaman", "The Book of Mormon", 14, 20, 27,
        "paraphrase", "atonement",
        "Samuel foretells three days of darkness, storms, and great "
        "destruction marking Christ's death on the other side of the "
        "world - fulfilled exactly as prophesied at the moment of the "
        "crucifixion.",
    ),
    # --- D&C 113: another explicit, verse-by-verse interpretation, this
    # time of Isaiah 11 and 52 - same vein as D&C 77's Revelation
    # exposition above.
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 113, 1, 4,
        "Isaiah", "Holy Bible", 11, 1, 1,
        "paraphrase", "jesus-christ",
        "Identifies the \"Stem of Jesse\" as Christ Himself, and the "
        "\"rod\" that comes of that stem as a latter-day servant holding "
        "priesthood power - not competing figures, but Christ and His "
        "authorized servant together.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 113, 5, 6,
        "Isaiah", "Holy Bible", 11, 10, 10,
        "paraphrase", "house-of-israel",
        "The \"root of Jesse\" is identified as a latter-day descendant "
        "of Jesse and Joseph holding \"the priesthood, and the keys of "
        "the kingdom,\" raised as an ensign for gathering scattered "
        "Israel.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 113, 7, 8,
        "Isaiah", "Holy Bible", 52, 1, 1,
        "paraphrase", "priesthood",
        "\"Put on thy strength, O Zion\" is explained as the last-day "
        "call to those who \"hold the power of priesthood to bring "
        "again Zion.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 113, 9, 10,
        "Isaiah", "Holy Bible", 52, 2, 2,
        "paraphrase", "house-of-israel",
        "Zion \"loosing herself from the bands of her neck\" is "
        "explained as scattered Israel's own call to return to the "
        "Lord.",
    ),
    # --- More typology and direct Psalm/Hebrews Christological quotations ---
    (
        "John", "Holy Bible", 1, 51, 51,
        "Genesis", "Holy Bible", 28, 10, 12,
        "typology", "jesus-christ",
        "Christ explicitly applies Jacob's ladder to Himself: \"ye "
        "shall see heaven open, and the angels of God ascending and "
        "descending upon the Son of man\" - He is the very connection "
        "between heaven and earth Jacob's dream showed.",
    ),
    (
        "Romans", "Holy Bible", 16, 20, 20,
        "Genesis", "Holy Bible", 3, 14, 15,
        "typology", "jesus-christ",
        "\"The God of peace shall bruise Satan under your feet shortly\" "
        "- Paul's own echo of the Lord's first curse on the serpent, "
        "\"it shall bruise thy head,\" the earliest Messianic promise in "
        "scripture.",
    ),
    (
        "Hebrews", "Holy Bible", 1, 5, 5,
        "Psalms", "Holy Bible", 2, 7, 7,
        "quotation", "jesus-christ",
        "\"Thou art my Son, this day have I begotten thee\" - quoted "
        "directly as testimony of Christ's divine Sonship, a title "
        "never given to any angel.",
    ),
    (
        "Acts", "Holy Bible", 13, 33, 33,
        "Psalms", "Holy Bible", 2, 7, 7,
        "quotation", "jesus-christ",
        "Paul quotes the same psalm as Hebrews 1:5 above, applying "
        "\"this day have I begotten thee\" directly to Christ's own "
        "resurrection.",
    ),
    (
        "Hebrews", "Holy Bible", 1, 8, 9,
        "Psalms", "Holy Bible", 45, 6, 7,
        "quotation", "jesus-christ",
        "\"Thy throne, O God, is for ever and ever\" - quoted directly, "
        "applying language addressed to God alone to Christ's own "
        "eternal kingdom.",
    ),
    (
        "Hebrews", "Holy Bible", 1, 10, 12,
        "Psalms", "Holy Bible", 102, 25, 27,
        "quotation", "jesus-christ",
        "\"Thou, Lord, in the beginning hast laid the foundation of the "
        "earth\" - quoted directly, identifying Christ as the "
        "unchanging Creator this psalm addresses.",
    ),
    (
        "Luke", "Holy Bible", 2, 32, 32,
        "Isaiah", "Holy Bible", 49, 6, 6,
        "quotation", "jesus-christ",
        "\"A light to lighten the Gentiles\" - Simeon's own words over "
        "the infant Christ, echoing Isaiah's prophecy of a servant who "
        "would be a light not only to Israel but to all nations.",
    ),
    (
        "Acts", "Holy Bible", 13, 47, 47,
        "Isaiah", "Holy Bible", 49, 6, 6,
        "quotation", "missionary-work",
        "Paul and Barnabas quote the same prophecy as Luke 2:32 above "
        "directly, to justify preaching the gospel to the Gentiles, not "
        "the Jews alone.",
    ),
    (
        "Colossians", "Holy Bible", 2, 11, 12,
        "Genesis", "Holy Bible", 17, 10, 11,
        "typology", "baptism",
        "Paul explicitly calls baptism \"the circumcision of Christ\" - "
        "the new covenant token replacing the old, both marking entry "
        "into God's covenant people.",
    ),
    (
        "Hebrews", "Holy Bible", 4, 9, 10,
        "Genesis", "Holy Bible", 2, 2, 3,
        "typology", "sabbath-day",
        "\"There remaineth therefore a rest to the people of God\" - "
        "the Sabbath's own pattern of God's rest after His work becomes "
        "a type of the greater spiritual rest offered through Christ.",
    ),
    (
        "Revelation", "Holy Bible", 22, 2, 2,
        "Genesis", "Holy Bible", 2, 9, 9,
        "typology", "plan-of-salvation",
        "The tree of life, first seen in Eden and lost through the "
        "Fall, reappears in the final restored paradise - access to it "
        "regained through Christ rather than barred by the flaming "
        "sword of Genesis 3:24.",
    ),
    (
        "Revelation", "Holy Bible", 22, 14, 14,
        "Genesis", "Holy Bible", 3, 22, 24,
        "typology", "plan-of-salvation",
        "\"That they may have right to the tree of life\" reverses "
        "Eden's own curse - mankind was driven out and barred from the "
        "tree in Genesis; the redeemed are welcomed back to it here.",
    ),
    (
        "Matthew", "Holy Bible", 26, 67, 67,
        "Isaiah", "Holy Bible", 50, 6, 6,
        "paraphrase", "atonement",
        "\"I gave my back to the smiters, and my cheeks to them that "
        "plucked off the hair\" - one of Isaiah's suffering-servant "
        "songs, fulfilled when the council spat on Christ and struck "
        "Him during His trial.",
    ),
    (
        "1 Corinthians", "Holy Bible", 5, 8, 8,
        "Exodus", "Holy Bible", 12, 15, 15,
        "typology", "atonement",
        "Removing leaven from the house before Passover becomes, for "
        "Paul, a call to keep the feast \"with the unleavened bread of "
        "sincerity and truth\" rather than \"the leaven of malice and "
        "wickedness\" - the same Passover-as-Christ imagery as 1 "
        "Corinthians 5:7 above, applied to daily discipleship.",
    ),
    (
        "1 Corinthians", "Holy Bible", 10, 4, 4,
        "Helaman", "The Book of Mormon", 5, 12, 12,
        "typology", "jesus-christ",
        "Both name \"the Rock\" as a title for Christ Himself outright "
        "- Paul of the rock struck in the wilderness, Helaman of the "
        "foundation his sons must build their lives upon.",
    ),
    (
        "Acts", "Holy Bible", 15, 16, 17,
        "Amos", "Holy Bible", 9, 11, 12,
        "quotation", "church-of-jesus-christ",
        "\"I will build again the tabernacle of David\" - James quotes "
        "this directly at the Jerusalem council to show that Gentiles "
        "being gathered into the Church, without first requiring "
        "circumcision, was foretold by the prophets all along.",
    ),
    (
        "Mark", "Holy Bible", 1, 2, 2,
        "Malachi", "Holy Bible", 3, 1, 1,
        "quotation", "prophets",
        "\"I send my messenger before thy face, which shall prepare thy "
        "way before thee\" - Mark opens his gospel by quoting this "
        "directly, identifying John the Baptist as the promised "
        "forerunner.",
    ),
    (
        "Hebrews", "Holy Bible", 10, 1, 4,
        "Alma", "The Book of Mormon", 34, 10, 14,
        "paraphrase", "atonement",
        "Both explicitly teach that animal sacrifice could never itself "
        "take away sin - Amulek that \"it shall not be a human "
        "sacrifice... but it must be an infinite and eternal "
        "sacrifice,\" Hebrews that \"it is not possible that the blood "
        "of bulls and goats should take away sins\" - each explaining "
        "why a greater atonement was required.",
    ),
    (
        "Revelation", "Holy Bible", 22, 17, 17,
        "Isaiah", "Holy Bible", 55, 1, 1,
        "quotation", "salvation",
        "\"Come... buy wine and milk without money and without "
        "price\"/\"take the water of life freely\" - both invite all "
        "who thirst to partake of salvation's blessings without cost, "
        "the same invitation centuries apart.",
    ),
    (
        "John", "Holy Bible", 10, 7, 9,
        "2 Nephi", "The Book of Mormon", 9, 41, 41,
        "typology", "jesus-christ",
        "Both name Christ directly as the gate to salvation - John "
        "records Christ's own words, \"I am the door of the sheep\"; "
        "Nephi calls Him \"the keeper of the gate\" who \"employeth no "
        "servant there.\"",
    ),
    (
        "3 Nephi", "The Book of Mormon", 27, 27, 27,
        "Matthew", "Holy Bible", 5, 48, 48,
        "paraphrase", "discipleship",
        "\"What manner of men ought ye to be? Verily... even as I am\" "
        "- the risen Christ's own standard for discipleship matches His "
        "earlier teaching in the Sermon on the Mount, \"be ye therefore "
        "perfect, even as your Father... is perfect.\"",
    ),
    # --- "Other sheep I have": Christ quotes His own words from John twice
    # more, identifying who they meant - a three-text network anchored on
    # the same original verse, same pattern as the brazen serpent above.
    (
        "3 Nephi", "The Book of Mormon", 15, 21, 24,
        "John", "Holy Bible", 10, 16, 16,
        "quotation", "house-of-israel",
        "Christ explicitly quotes His own words to the Nephites, \"ye "
        "are they of whom I said: Other sheep I have which are not of "
        "this fold\" - explaining that the promise of \"other sheep\" "
        "beyond Jerusalem's fold meant the very people now hearing Him "
        "in the Americas.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 16, 1, 3,
        "John", "Holy Bible", 10, 16, 16,
        "quotation", "house-of-israel",
        "Christ clarifies that \"other sheep\" means still more than "
        "even the Nephites - other scattered branches of Israel \"not "
        "of this land, neither of the land of Jerusalem\" that He must "
        "also visit.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 10, 59, 60,
        "John", "Holy Bible", 10, 16, 16,
        "quotation", "house-of-israel",
        "Christ quotes His own words a third time, now to Joseph "
        "Smith, identifying the Book of Mormon itself as proof that the "
        "\"other sheep\" promise was literally fulfilled among the "
        "Nephites.",
    ),
    # --- Found by mining which verses General Conference/Ensign/Liahona
    # talks actually cite TOGETHER in the same talk (see data/verse_
    # citations.json and data/liahona_citations.json) - a strong signal
    # of a connection speakers themselves have already drawn repeatedly,
    # each still verified against the real text before being added here.
    (
        "Matthew", "Holy Bible", 17, 5, 5,
        "Joseph Smith--History", "Pearl of Great Price", 1, 17, 17,
        "quotation", "jesus-christ,restoration",
        "The Father's declaration is nearly word for word the same: "
        "\"This is my beloved Son... hear ye him\" at the Mount of "
        "Transfiguration becomes \"This is My Beloved Son. Hear Him!\" "
        "at the First Vision - the same divine testimony given "
        "seventeen centuries apart.",
    ),
    (
        "Matthew", "Holy Bible", 17, 5, 5,
        "3 Nephi", "The Book of Mormon", 11, 6, 7,
        "quotation", "jesus-christ",
        "\"Hear ye him\"/\"hear ye him\" - the Father's own words to the "
        "apostles at the Transfiguration are echoed almost exactly when "
        "He introduces the resurrected Christ to the Nephites.",
    ),
    (
        "Joseph Smith--History", "Pearl of Great Price", 1, 17, 17,
        "3 Nephi", "The Book of Mormon", 11, 6, 7,
        "quotation", "jesus-christ,restoration",
        "Both records preserve the Father's voice using nearly "
        "identical language to introduce the Son and command that He "
        "be heard - the same divine pattern repeating across "
        "dispensations.",
    ),
    (
        "Joseph Smith--History", "Pearl of Great Price", 1, 11, 13,
        "James", "Holy Bible", 1, 5, 5,
        "quotation", "revelation",
        "Joseph Smith explicitly names his source: \"reading the "
        "Epistle of James, first chapter and fifth verse\" - it was "
        "pondering this very verse that drove him to pray and receive "
        "the First Vision.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 20, 77, 77,
        "Moroni", "The Book of Mormon", 4, 3, 3,
        "quotation", "ordinances",
        "The sacrament prayer on the bread is given in the Doctrine "
        "and Covenants in nearly the same words the Nephites already "
        "used centuries earlier, recorded by Moroni - the same "
        "ordinance, restored with the same words.",
    ),
    (
        "John", "Holy Bible", 3, 16, 16,
        "Moses", "Pearl of Great Price", 1, 39, 39,
        "paraphrase", "plan-of-salvation",
        "Two of scripture's most quoted single verses state the same "
        "doctrine from opposite directions: \"God so loved the world, "
        "that he gave his only begotten Son\" is the motive; \"this is "
        "my work and my glory - to bring to pass the immortality and "
        "eternal life of man\" is the purpose that love accomplishes.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 14, 7, 7,
        "Moses", "Pearl of Great Price", 1, 39, 39,
        "paraphrase", "exaltation",
        "\"Eternal life, which gift is the greatest of all the gifts of "
        "God\" names exactly what Moses 1:39 calls God's own \"work and "
        "glory\" - the same goal, described from the receiving end and "
        "the giving end.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 2, 25, 25,
        "Moses", "Pearl of Great Price", 1, 39, 39,
        "paraphrase", "plan-of-salvation",
        "\"Men are, that they might have joy\" and \"the immortality "
        "and eternal life of man\" answer the same question - why "
        "mortal life exists at all - each in its own single, oft-quoted "
        "sentence.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 20, 77, 77,
        "Mosiah", "The Book of Mormon", 18, 8, 10,
        "paraphrase", "covenants",
        "The sacrament prayer's promise to \"always remember him and "
        "keep his commandments\" renews, week by week, the very "
        "covenant Alma's converts first made at the waters of Mormon - "
        "to \"bear one another's burdens,\" \"mourn with those that "
        "mourn,\" and \"stand as witnesses of God at all times.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 1, 38, 38,
        "Amos", "Holy Bible", 3, 7, 7,
        "paraphrase", "prophets",
        "\"The Lord God will do nothing, but he revealeth his secret "
        "unto his servants the prophets\" and \"whether by mine own "
        "voice or by the voice of my servants, it is the same\" both "
        "teach that a living prophet's word carries the Lord's own "
        "authority.",
    ),
    (
        "Matthew", "Holy Bible", 5, 48, 48,
        "Moroni", "The Book of Mormon", 10, 32, 32,
        "paraphrase", "grace",
        "\"Be ye therefore perfect\" is the command; \"be perfected in "
        "him... then is his grace sufficient for you\" explains how - "
        "perfection is reached through Christ's grace, not unaided "
        "human effort.",
    ),
    (
        "John", "Holy Bible", 17, 3, 3,
        "Joseph Smith--History", "Pearl of Great Price", 1, 17, 17,
        "paraphrase", "testimony",
        "\"This is life eternal, that they might know thee the only "
        "true God, and Jesus Christ\" defines eternal life as knowing "
        "God personally - exactly what Joseph Smith received when the "
        "Father and the Son appeared to him directly.",
    ),
    (
        "John", "Holy Bible", 13, 34, 34,
        "Moroni", "The Book of Mormon", 7, 47, 47,
        "paraphrase", "charity",
        "Christ's \"new commandment... that ye love one another\" and "
        "Mormon's definition of charity as \"the pure love of Christ\" "
        "describe the same defining Christian virtue from two "
        "different vantage points, command and definition.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 93, 40, 40,
        "Proverbs", "Holy Bible", 22, 6, 6,
        "paraphrase", "children",
        "\"I have commanded you to bring up your children in light and "
        "truth\" and \"train up a child in the way he should go\" teach "
        "the same parental duty, one as commandment, one as proverb.",
    ),
    (
        "Luke", "Holy Bible", 22, 42, 42,
        "Mosiah", "The Book of Mormon", 3, 19, 19,
        "paraphrase", "obedience",
        "Christ's own submission in Gethsemane - \"not my will, but "
        "thine, be done\" - is the perfect pattern of the \"submissive, "
        "meek, humble\" disposition Mosiah 3:19 teaches every disciple "
        "must adopt, becoming \"as a child.\"",
    ),
    (
        "Matthew", "Holy Bible", 28, 19, 19,
        "Doctrine and Covenants", "Doctrine and Covenants", 18, 10, 10,
        "paraphrase", "missionary-work",
        "\"The worth of souls is great in the sight of God\" is the "
        "reason behind the command to \"go ye therefore, and teach all "
        "nations\" - the value of each soul is what makes the "
        "missionary charge urgent.",
    ),
    (
        "Articles of Faith", "Pearl of Great Price", 1, 13, 13,
        "1 Corinthians", "Holy Bible", 13, 7, 7,
        "quotation", "charity",
        "\"We believe all things, we hope all things\" - the Articles "
        "of Faith explicitly credit this to \"the admonition of Paul,\" "
        "quoting his own definition of charity almost word for word.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 59, 23, 23,
        "John", "Holy Bible", 14, 27, 27,
        "paraphrase", "peace",
        "\"Peace in this world, and eternal life in the world to come\" "
        "and \"Peace I leave with you, my peace I give unto you\" both "
        "name peace as Christ's own gift to the righteous, not "
        "something the world can offer.",
    ),
    # --- A second, wider pass of the same citation-mining technique
    # (cross-book this time, not only cross-volume, which is what
    # surfaced these Old Testament <-> New Testament pairs).
    (
        "John", "Holy Bible", 14, 27, 27,
        "Philippians", "Holy Bible", 4, 7, 7,
        "paraphrase", "peace",
        "\"My peace I give unto you\" and \"the peace of God, which "
        "passeth all understanding\" both describe a peace only Christ, "
        "not the world, can give.",
    ),
    (
        "John", "Holy Bible", 14, 27, 27,
        "Matthew", "Holy Bible", 5, 9, 9,
        "paraphrase", "peace",
        "Christ's gift of peace and His blessing on \"the peacemakers... "
        "they shall be called the children of God\" tie receiving "
        "Christ's peace to becoming a peacemaker oneself.",
    ),
    (
        "John", "Holy Bible", 14, 27, 27,
        "Matthew", "Holy Bible", 11, 28, 28,
        "paraphrase", "peace",
        "\"Come unto me... I will give you rest\" is the same gift of "
        "peace Christ promises in John 14:27, offered to \"all ye that "
        "labour and are heavy laden.\"",
    ),
    (
        "Ephesians", "Holy Bible", 1, 10, 10,
        "Acts", "Holy Bible", 3, 19, 21,
        "paraphrase", "restoration",
        "\"The times of restitution of all things\" and \"the "
        "dispensation of the fulness of times\" name the same latter-day "
        "restoration - both Peter and Paul point to a future gathering "
        "together of all things in Christ.",
    ),
    (
        "Alma", "The Book of Mormon", 41, 10, 10,
        "2 Nephi", "The Book of Mormon", 2, 27, 27,
        "paraphrase", "agency",
        "\"Free to choose liberty and eternal life... or to choose "
        "captivity and death\" and \"wickedness never was happiness\" "
        "both teach that agency's consequences are built into the "
        "choice itself, not arbitrarily assigned afterward.",
    ),
    (
        "Abraham", "Pearl of Great Price", 3, 25, 25,
        "2 Nephi", "The Book of Mormon", 2, 27, 27,
        "paraphrase", "agency",
        "Agency's purpose - being \"free to choose\" - is what makes "
        "Abraham 3:25's premortal test possible at all: \"we will prove "
        "them herewith, to see if they will do all things whatsoever "
        "the Lord... shall command.\"",
    ),
    (
        "Articles of Faith", "Pearl of Great Price", 1, 1, 1,
        "Joseph Smith--History", "Pearl of Great Price", 1, 17, 17,
        "paraphrase", "godhead",
        "\"We believe in God, the Eternal Father, and in His Son, Jesus "
        "Christ\" as two separate beings is exactly what Joseph Smith "
        "saw firsthand in the First Vision - the article of faith "
        "states as doctrine what he witnessed directly.",
    ),
    (
        "Matthew", "Holy Bible", 25, 40, 40,
        "James", "Holy Bible", 1, 27, 27,
        "paraphrase", "service",
        "\"Pure religion... is this, To visit the fatherless and "
        "widows in their affliction\" and \"inasmuch as ye have done it "
        "unto one of the least of these... ye have done it unto me\" "
        "both define true religion by service to the vulnerable.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 119, 4, 4,
        "Malachi", "Holy Bible", 3, 10, 10,
        "quotation", "tithing",
        "\"Bring ye all the tithes into the storehouse... prove me now "
        "herewith\" is the same law and the same promised blessing the "
        "Lord restores as \"a standing law unto them forever\" in this "
        "modern revelation.",
    ),
    (
        "James", "Holy Bible", 1, 5, 5,
        "Moroni", "The Book of Mormon", 10, 4, 5,
        "paraphrase", "testimony",
        "\"If any of you lack wisdom, let him ask of God\" and "
        "Moroni's promise to \"ask God, the Eternal Father, in the name "
        "of Christ, if these things are not true\" teach the same "
        "pattern of receiving personal revelation - Joseph Smith's own "
        "use of James 1:5 (see Joseph Smith-History above) makes the "
        "connection more than coincidence.",
    ),
    (
        "Isaiah", "Holy Bible", 9, 6, 6,
        "John", "Holy Bible", 14, 27, 27,
        "paraphrase", "jesus-christ",
        "Isaiah names Him \"The Prince of Peace\" centuries in advance; "
        "Christ Himself then gives what that title promises: \"my peace "
        "I give unto you.\"",
    ),
    (
        "Alma", "The Book of Mormon", 7, 11, 13,
        "Matthew", "Holy Bible", 11, 28, 28,
        "paraphrase", "atonement",
        "\"That his bowels may be filled with mercy... that he may "
        "know... how to succor his people\" is the same gift of rest "
        "and relief Christ offers directly in \"come unto me, all ye "
        "that labour and are heavy laden, and I will give you rest.\"",
    ),
    (
        "Joseph Smith--History", "Pearl of Great Price", 1, 17, 17,
        "Moses", "Pearl of Great Price", 1, 39, 39,
        "paraphrase", "restoration",
        "The First Vision, opening the \"dispensation of the fulness of "
        "times,\" is the beginning of God bringing to pass in the "
        "latter days the very work and glory Moses 1:39 describes.",
    ),
    # --- A third mining pass, further down the ranked list, filtered to
    # pairs not already touching a chapter already in this table.
    (
        "John", "Holy Bible", 16, 33, 33,
        "Matthew", "Holy Bible", 11, 28, 28,
        "paraphrase", "peace",
        "\"That in me ye might have peace... be of good cheer; I have "
        "overcome the world\" is the same peace-in-Christ theme as "
        "\"come unto me... I will give you rest\" above.",
    ),
    (
        "John", "Holy Bible", 16, 33, 33,
        "Philippians", "Holy Bible", 4, 7, 7,
        "paraphrase", "peace",
        "Christ's promise that His followers may \"have peace\" even "
        "amid the world's tribulation matches Paul's \"peace of God, "
        "which passeth all understanding\" above.",
    ),
    (
        "Alma", "The Book of Mormon", 5, 14, 14,
        "Mosiah", "The Book of Mormon", 5, 2, 2,
        "paraphrase", "repentance",
        "Both use the same distinctive phrase for true conversion: Alma "
        "asks \"have ye experienced this mighty change in your "
        "hearts?\"; King Benjamin's people already had, having \"no more "
        "disposition to do evil, but to do good continually.\"",
    ),
    (
        "John", "Holy Bible", 8, 12, 12,
        "Matthew", "Holy Bible", 5, 16, 16,
        "paraphrase", "jesus-christ",
        "\"I am the light of the world\" is Christ's own declaration; "
        "\"let your light so shine before men\" is what He then asks of "
        "everyone who follows Him - reflecting the very light He is.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 110, 14, 16,
        "Malachi", "Holy Bible", 4, 5, 6,
        "quotation", "temple",
        "\"The time has fully come, which was spoken of by the mouth of "
        "Malachi\" - Elijah's own appearance in the Kirtland Temple, "
        "explicitly identified as the literal fulfillment of Malachi's "
        "prophecy, restoring the sealing power for temple work (see "
        "D&C 128:17 above for how that power is then applied).",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 24, 24,
        "Acts", "Holy Bible", 17, 28, 29,
        "paraphrase", "godhead",
        "\"We are also his offspring\" and \"begotten sons and "
        "daughters unto God\" both teach the same doctrine of literal "
        "divine parentage - not a figure of speech, but a real "
        "relationship.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 59, 9, 9,
        "Exodus", "Holy Bible", 20, 8, 8,
        "paraphrase", "sabbath-day",
        "\"Remember the sabbath day, to keep it holy\" is restated in "
        "modern revelation as going \"to the house of prayer\" and "
        "offering \"thy sacraments upon my holy day\" - the same "
        "commandment, adapted to Christ's own restored Church.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 38, 27, 27,
        "John", "Holy Bible", 17, 21, 21,
        "paraphrase", "church-of-jesus-christ",
        "\"Be one; and if ye are not one ye are not mine\" matches "
        "Christ's own intercessory prayer \"that they all may be "
        "one... that the world may believe that thou hast sent me\" - "
        "unity among believers as evidence of true discipleship.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 122, 8, 8,
        "Alma", "The Book of Mormon", 7, 11, 13,
        "paraphrase", "atonement",
        "\"The Son of Man hath descended below them all. Art thou "
        "greater than he?\" is the same doctrine as Alma 7's teaching "
        "above - Christ's suffering exceeds and therefore qualifies Him "
        "to succor every other person's own trials.",
    ),
    (
        "Ether", "The Book of Mormon", 12, 27, 27,
        "Mosiah", "The Book of Mormon", 4, 27, 27,
        "paraphrase", "grace",
        "\"My grace is sufficient for all men that humble themselves\" "
        "and \"it is not requisite that a man should run faster than he "
        "has strength\" both teach that the Lord's expectations are "
        "matched to what His grace actually enables, not to unaided "
        "human effort alone.",
    ),
    # --- A fourth mining pass, filtered specifically to Bible <-> LDS-
    # scripture pairs (the highest-value case, since a Bible-internal
    # pair is already well covered by public-domain resources like the
    # Treasury of Scripture Knowledge - see this file's own docstring).
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 65, 2, 2,
        "Daniel", "Holy Bible", 2, 44, 44,
        "quotation", "restoration",
        "\"The stone which is cut out of the mountain without hands\" - "
        "D&C 65 explicitly quotes Daniel's own image, applying it to "
        "the kingdom of God rolling forth to fill the whole earth in "
        "the latter days.",
    ),
    (
        "Ephesians", "Holy Bible", 1, 10, 10,
        "Daniel", "Holy Bible", 2, 44, 44,
        "paraphrase", "restoration",
        "Both describe a final kingdom that will \"never be destroyed\" "
        "and gather \"all things\" together - Daniel's stone that fills "
        "the whole earth, Paul's dispensation of the fulness of times.",
    ),
    (
        "Joseph Smith--History", "Pearl of Great Price", 1, 17, 17,
        "Revelation", "Holy Bible", 14, 6, 6,
        "paraphrase", "restoration",
        "\"Another angel fly in the midst of heaven, having the "
        "everlasting gospel\" is read as prophecy of the angelic "
        "ministrations - Moroni among them - that restored the gospel "
        "beginning with the First Vision.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 130, 20, 21,
        "Malachi", "Holy Bible", 3, 10, 10,
        "paraphrase", "covenants",
        "\"All blessings are predicated\" on obedience to God's law is "
        "the very principle Malachi's tithing promise demonstrates: "
        "bring the tithe, and the windows of heaven open in return.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 58, 42, 42,
        "Isaiah", "Holy Bible", 1, 18, 18,
        "paraphrase", "repentance",
        "\"He who has repented of his sins... I, the Lord, remember "
        "them no more\" and \"though your sins be as scarlet, they "
        "shall be as white as snow\" both teach that true repentance "
        "makes forgiveness complete, not partial.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 2, 1, 3,
        "Malachi", "Holy Bible", 4, 5, 6,
        "quotation", "temple",
        "Moroni's first recorded words to Joseph Smith, in 1823, "
        "already quote Malachi's Elijah prophecy directly - years "
        "before Elijah's actual appearance in the Kirtland Temple "
        "fulfilled it (see D&C 110 above).",
    ),
    (
        "1 Corinthians", "Holy Bible", 6, 19, 19,
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 15, 15,
        "paraphrase", "resurrection",
        "\"Your body is the temple of the Holy Ghost\" and \"the spirit "
        "and the body are the soul of man\" both teach that the body is "
        "sacred, not incidental, to a person's spiritual life.",
    ),
    (
        "Matthew", "Holy Bible", 28, 20, 20,
        "Doctrine and Covenants", "Doctrine and Covenants", 84, 88, 88,
        "paraphrase", "missionary-work",
        "\"I will go before your face... mine angels round about you, "
        "to bear you up\" is Christ's own promise of constant support "
        "for those sent to teach, matching His \"lo, I am with you "
        "alway\" at the very end of Matthew.",
    ),
    (
        "Acts", "Holy Bible", 10, 38, 38,
        "Luke", "Holy Bible", 2, 52, 52,
        "paraphrase", "jesus-christ",
        "\"Jesus increased in wisdom and stature\" and \"went about "
        "doing good\" together sketch Christ's mortal life, from "
        "growing boy to anointed, healing minister.",
    ),
    (
        "Luke", "Holy Bible", 22, 42, 42,
        "1 Nephi", "The Book of Mormon", 3, 7, 7,
        "paraphrase", "obedience",
        "Nephi's resolve, \"I will go and do the things which the Lord "
        "hath commanded,\" is the same willing submission Christ "
        "Himself models in Gethsemane: \"not my will, but thine, be "
        "done.\"",
    ),
    # --- Filling in books untouched so far - checked which books had zero
    # entries, then looked for well-known content there rather than only
    # following citation-mining leads from already-popular verses.
    (
        "John", "Holy Bible", 10, 11, 11,
        "Ezekiel", "Holy Bible", 34, 23, 24,
        "paraphrase", "jesus-christ",
        "Ezekiel prophesies one shepherd, \"my servant David,\" who "
        "will feed and care for God's scattered flock - the same role "
        "Christ claims centuries later: \"I am the good shepherd: the "
        "good shepherd giveth his life for the sheep.\"",
    ),
    (
        "Hebrews", "Holy Bible", 8, 8, 12,
        "Jeremiah", "Holy Bible", 31, 31, 34,
        "quotation", "covenants",
        "The \"new covenant\" promised to the house of Israel - \"I "
        "will put my laws into their mind, and write them in their "
        "hearts\" - is quoted by Hebrews at unusual length, one of the "
        "longest continuous Old Testament quotations anywhere in the "
        "New Testament, to show Christ's covenant fulfilling and "
        "replacing the old.",
    ),
    (
        "Mark", "Holy Bible", 2, 5, 5,
        "Enos", "The Book of Mormon", 1, 5, 8,
        "paraphrase", "repentance",
        "Enos hears almost the same words Christ later speaks to the "
        "man sick of the palsy - \"thy sins are forgiven thee\" - the "
        "same divine assurance of complete forgiveness, given directly, "
        "centuries apart, and in Enos' case explicitly \"because of thy "
        "faith in Christ\" though Christ's own ministry was still "
        "generations away.",
    ),
    (
        "Acts", "Holy Bible", 4, 32, 32,
        "4 Nephi", "The Book of Mormon", 1, 15, 17,
        "paraphrase", "zion",
        "\"Of one heart and of one soul... had all things common\" and "
        "\"there was no contention in the land, because of the love of "
        "God\" both describe a unified, consecrated community "
        "immediately after encountering the resurrected Christ - a Zion "
        "society on two different continents.",
    ),
    (
        "Ether", "The Book of Mormon", 12, 27, 27,
        "2 Corinthians", "Holy Bible", 12, 9, 9,
        "quotation", "grace",
        "\"My grace is sufficient for thee\" - Moroni echoes Paul's own "
        "words almost verbatim: \"my grace is sufficient for all men "
        "that humble themselves before me.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 96, 98,
        "1 Thessalonians", "Holy Bible", 4, 16, 17,
        "paraphrase", "second-coming",
        "Both describe the same moment: the dead in Christ rising "
        "first, then the living \"caught up\" to meet Him - Paul's own "
        "account of the Second Coming and this modern revelation's "
        "description of the same event.",
    ),
    (
        "Moroni", "The Book of Mormon", 7, 6, 8,
        "James", "Holy Bible", 2, 17, 18,
        "paraphrase", "faith",
        "\"Faith, if it hath not works, is dead\" and \"except he shall "
        "do it with real intent it profiteth him nothing\" both teach "
        "that sincere action, not empty profession, is what makes faith "
        "real.",
    ),
    (
        "Luke", "Holy Bible", 22, 42, 42,
        "1 Samuel", "Holy Bible", 15, 22, 22,
        "paraphrase", "obedience",
        "\"To obey is better than sacrifice\" and Christ's own \"not my "
        "will, but thine, be done\" both teach that willing obedience "
        "matters more than the outward form of devotion.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 93, 40, 40,
        "3 John", "Holy Bible", 1, 4, 4,
        "paraphrase", "children",
        "\"I have no greater joy than to hear that my children walk in "
        "truth\" is the same parental joy behind the commandment \"to "
        "bring up your children in light and truth\" above.",
    ),
    # --- More book-coverage gap-filling ---
    (
        "1 Corinthians", "Holy Bible", 15, 20, 20,
        "Job", "Holy Bible", 19, 25, 26,
        "paraphrase", "resurrection",
        "\"I know that my redeemer liveth... in my flesh shall I see "
        "God\" is Job's own resurrection hope, realized when \"Christ "
        "is risen from the dead, and become the firstfruits of them "
        "that slept.\"",
    ),
    (
        "Alma", "The Book of Mormon", 40, 11, 11,
        "Ecclesiastes", "Holy Bible", 12, 7, 7,
        "paraphrase", "plan-of-salvation",
        "\"The spirit shall return unto God who gave it\" and \"the "
        "spirits of all men, as soon as they are departed from this "
        "mortal body... are taken home to that God who gave them "
        "life\" describe the same immediate destination of the spirit "
        "at death.",
    ),
    (
        "Alma", "The Book of Mormon", 18, 32, 32,
        "1 Samuel", "Holy Bible", 16, 7, 7,
        "paraphrase", "judgment",
        "\"The Lord seeth not as man seeth; for man looketh on the "
        "outward appearance, but the Lord looketh on the heart\" and "
        "\"he knows all the thoughts and intents of the heart\" both "
        "teach that God judges by what's within, not outward "
        "appearance.",
    ),
    (
        "Luke", "Holy Bible", 4, 27, 27,
        "2 Kings", "Holy Bible", 5, 10, 14,
        "quotation", "faith",
        "Naaman's healing after washing in the Jordan seven times, at "
        "first refused in pride - Christ Himself cites this very story "
        "by name to the people of Nazareth, teaching that faith, not "
        "birthright, determines who receives God's power.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 18, 13, 13,
        "Zephaniah", "Holy Bible", 3, 17, 17,
        "paraphrase", "missionary-work",
        "\"How great is his joy in the soul that repenteth\" and \"he "
        "will rejoice over thee with joy... he will joy over thee with "
        "singing\" both describe God's own joy - not just relief - over "
        "a single soul returning to Him.",
    ),
    (
        "Hebrews", "Holy Bible", 12, 26, 26,
        "Haggai", "Holy Bible", 2, 6, 7,
        "quotation", "second-coming",
        "\"Yet once more I shake not the earth only, but also heaven\" "
        "- Hebrews quotes Haggai's own prophecy of a final, decisive "
        "shaking of all things at the Lord's coming.",
    ),
    (
        "Jacob", "The Book of Mormon", 2, 18, 19,
        "1 Timothy", "Holy Bible", 6, 10, 10,
        "paraphrase", "consecration",
        "\"The love of money is the root of all evil\" and \"before ye "
        "seek for riches, seek ye for the kingdom of God\" both warn "
        "that the danger isn't riches themselves but placing them "
        "ahead of God.",
    ),
    (
        "Moroni", "The Book of Mormon", 7, 47, 47,
        "1 John", "Holy Bible", 4, 8, 8,
        "paraphrase", "charity",
        "\"God is love\" and \"charity is the pure love of Christ\" "
        "both root the definition of true love in God's own nature, "
        "not human sentiment.",
    ),
    (
        "Jude", "Holy Bible", 1, 3, 3,
        "2 Thessalonians", "Holy Bible", 2, 3, 3,
        "paraphrase", "restoration",
        "\"Earnestly contend for the faith which was once delivered\" "
        "assumes that faith could be - and was - lost; Paul explicitly "
        "warns that \"a falling away\" must come first, before Christ's "
        "return - the apostasy these two verses anticipate is what the "
        "Restoration would later address.",
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
