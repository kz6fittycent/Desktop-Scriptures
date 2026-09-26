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

Five relationship kinds (see also schema.sql's own comment):
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
- "tradition": a deliberately looser fifth tier, added once the first
  four kinds' well-documented, explicitly-stated candidates were largely
  exhausted (confirmed by several independent passes converging on the
  same set rather than finding new ones). Covers widely-recognized
  thematic or traditional associations - e.g. Ruth's Boaz as a type of
  Christ the kinsman-redeemer, or Song of Solomon read allegorically -
  that scripture itself does not explicitly state the way the other four
  kinds require. The UI labels these "Traditionally linked to" (not
  "Quotes"/"Parallels"/"Connects to") specifically so a reader can tell
  the two tiers apart at a glance; every "tradition" entry's own note
  should likewise be candid that it's an interpretive reading, not a
  textually-stated one.
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
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 85, 6, 6,
        "1 Kings", "Holy Bible", 19, 11, 12,
        "paraphrase", "revelation",
        "Elijah learns God speaks \"not in the wind... not in the "
        "earthquake... not in the fire\" but in \"a still small voice\" "
        "- the same \"still small voice, which whispereth through and "
        "pierceth all things\" this modern revelation describes.",
    ),
    (
        "Titus", "Holy Bible", 3, 5, 5,
        "2 Nephi", "The Book of Mormon", 25, 23, 23,
        "paraphrase", "grace",
        "\"Not by works of righteousness which we have done, but "
        "according to his mercy he saved us\" and \"it is by grace that "
        "we are saved, after all we can do\" both teach that salvation "
        "comes through Christ's mercy, not human effort alone - two of "
        "scripture's clearest single-verse statements of the doctrine "
        "of grace.",
    ),
    (
        "Mormon", "The Book of Mormon", 9, 9, 9,
        "James", "Holy Bible", 1, 17, 17,
        "quotation", "godhead",
        "\"God is the same yesterday, today, and forever, and in him "
        "there is no variableness neither shadow of changing\" nearly "
        "repeats James' own words, \"with whom is no variableness, "
        "neither shadow of turning\" - the same doctrine of God's "
        "unchanging nature.",
    ),
    (
        "2 Timothy", "Holy Bible", 4, 7, 7,
        "Moroni", "The Book of Mormon", 10, 34, 34,
        "paraphrase", "testimony",
        "Paul's final words - \"I have fought a good fight, I have "
        "finished my course, I have kept the faith\" - and Moroni's own "
        "farewell - \"I soon go to rest in the paradise of God... to "
        "meet you before the pleasing bar of the great Jehovah\" - are "
        "both a final witness given at the very end of a lifetime of "
        "testimony, just before facing God.",
    ),
    (
        "2 Peter", "Holy Bible", 3, 9, 9,
        "Doctrine and Covenants", "Doctrine and Covenants", 18, 11, 11,
        "paraphrase", "atonement",
        "\"The Lord is not slack... not willing that any should "
        "perish, but that all should come to repentance\" and \"he "
        "suffered the pain of all men, that all men might repent and "
        "come unto him\" both root patience toward sinners in the "
        "Atonement's own reach - Christ has already paid for repentance "
        "to be possible.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 68, 6, 6,
        "Joshua", "Holy Bible", 1, 9, 9,
        "paraphrase", "faith",
        "\"Be strong and of a good courage... for the Lord thy God is "
        "with thee\" and \"be of good cheer, and do not fear, for I the "
        "Lord am with you, and will stand by you\" both promise the "
        "same divine companionship to those the Lord sends out.",
    ),
    (
        "1 Corinthians", "Holy Bible", 15, 22, 23,
        "Leviticus", "Holy Bible", 23, 10, 11,
        "typology", "resurrection",
        "The wave-sheaf of firstfruits, waved before the Lord the day "
        "after the Sabbath during the Passover week, gives Paul his own "
        "term for Christ's resurrection: \"Christ the firstfruits; "
        "afterward they that are Christ's at his coming.\"",
    ),
    # --- Fork: OT historical/wisdom books (Genesis-Deuteronomy narrative,
    # Joshua-Esther, Job-Song of Solomon) ---
    (
        "Hebrews", "Holy Bible", 11, 5, 5,
        "Genesis", "Holy Bible", 5, 24, 24,
        "paraphrase", "faith",
        "Enoch \"walked with God: and he was not; for God took him\" - "
        "Paul explains this as being \"translated that he should not "
        "see death... because he pleased God,\" faith itself the "
        "cause.",
    ),
    (
        "John", "Holy Bible", 8, 58, 58,
        "Exodus", "Holy Bible", 3, 14, 14,
        "quotation", "jesus-christ",
        "\"I AM THAT I AM\" is the very name Christ claims for Himself: "
        "\"before Abraham was, I am\" - the same divine self-existence, "
        "the same name.",
    ),
    (
        "2 Corinthians", "Holy Bible", 3, 7, 13,
        "Exodus", "Holy Bible", 34, 29, 35,
        "paraphrase", "revelation",
        "Moses' face shone so brightly after speaking with God that he "
        "wore a veil - Paul explains this glory as \"done away,\" a "
        "lesser glory compared to the greater one Christ's gospel now "
        "reveals without a veil.",
    ),
    (
        "Revelation", "Holy Bible", 22, 16, 16,
        "Numbers", "Holy Bible", 24, 17, 17,
        "paraphrase", "jesus-christ",
        "\"There shall come a Star out of Jacob\" is Balaam's own "
        "Messianic prophecy; Christ later claims the title directly: "
        "\"I am... the bright and morning star.\"",
    ),
    (
        "Joshua", "Holy Bible", 24, 15, 15,
        "Deuteronomy", "Holy Bible", 30, 19, 19,
        "paraphrase", "agency",
        "\"Choose you this day whom ye will serve\" and \"I have set "
        "before you life and death... therefore choose life\" both make "
        "agency, not fate, the deciding factor in a person's standing "
        "before God.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 1, 19, 20,
        "Judges", "Holy Bible", 7, 2, 2,
        "paraphrase", "humility",
        "Gideon's army is deliberately shrunk \"lest Israel vaunt "
        "themselves... mine own hand hath saved me\" - the same reason "
        "\"the weak things of the world\" are chosen in this modern "
        "revelation, so no one can claim the credit that belongs to "
        "God.",
    ),
    (
        "Matthew", "Holy Bible", 1, 5, 5,
        "Ruth", "Holy Bible", 4, 13, 17,
        "quotation", "house-of-israel",
        "Ruth, a Moabite woman, is named outright in Christ's own "
        "genealogy - \"Booz begat Obed of Ruth\" - the same marriage "
        "and birth Ruth's own book records in full.",
    ),
    (
        "Luke", "Holy Bible", 1, 32, 33,
        "2 Samuel", "Holy Bible", 7, 12, 16,
        "quotation", "jesus-christ",
        "\"The Lord God shall give unto him the throne of his father "
        "David... he shall reign... for ever\" - Gabriel's own "
        "announcement to Mary quotes the Davidic covenant almost "
        "verbatim, applying it directly to Christ.",
    ),
    (
        "Luke", "Holy Bible", 4, 25, 26,
        "1 Kings", "Holy Bible", 17, 8, 16,
        "quotation", "faith",
        "Christ Himself cites this exact story by name to the people "
        "of Nazareth - Elijah sent to the widow of Zarephath rather "
        "than any widow in Israel - to teach that God's power isn't "
        "limited by birthright or expectation.",
    ),
    (
        "Mosiah", "The Book of Mormon", 2, 34, 34,
        "1 Chronicles", "Holy Bible", 29, 11, 14,
        "paraphrase", "gratitude",
        "\"All that is in the heaven and in the earth is thine\" and "
        "\"ye are eternally indebted to your heavenly Father\" both "
        "teach that everything a person has, and gives back, "
        "ultimately belongs to God first.",
    ),
    (
        "Mosiah", "The Book of Mormon", 24, 15, 15,
        "Job", "Holy Bible", 1, 21, 21,
        "paraphrase", "trials-and-adversity",
        "Job's submission - \"the Lord gave, and the Lord hath taken "
        "away; blessed be the name of the Lord\" - is the same patient "
        "acceptance Alma's people show when the Lord \"did strengthen "
        "them that they could bear up their burdens with ease.\"",
    ),
    (
        "John", "Holy Bible", 10, 11, 11,
        "Psalms", "Holy Bible", 23, 1, 1,
        "paraphrase", "jesus-christ",
        "\"The Lord is my shepherd; I shall not want\" is realized "
        "directly in Christ's own words: \"I am the good shepherd: the "
        "good shepherd giveth his life for the sheep.\"",
    ),
    (
        "John", "Holy Bible", 19, 36, 36,
        "Psalms", "Holy Bible", 34, 20, 20,
        "quotation", "atonement",
        "\"He keepeth all his bones: not one of them is broken\" is "
        "fulfilled, alongside the Passover lamb's own unbroken bones, "
        "when Christ's legs are left unbroken on the cross.",
    ),
    (
        "Luke", "Holy Bible", 23, 46, 46,
        "Psalms", "Holy Bible", 31, 5, 5,
        "quotation", "atonement",
        "\"Into thine hand I commit my spirit\" - Christ quotes this "
        "psalm directly as His very last words on the cross.",
    ),
    (
        "Hebrews", "Holy Bible", 10, 5, 7,
        "Psalms", "Holy Bible", 40, 6, 8,
        "quotation", "jesus-christ",
        "\"Sacrifice and offering thou wouldest not, but a body hast "
        "thou prepared me\" - Hebrews quotes this psalm as Christ's own "
        "words spoken \"when he cometh into the world,\" accepting a "
        "mortal body to do God's will.",
    ),
    (
        "Ephesians", "Holy Bible", 4, 8, 8,
        "Psalms", "Holy Bible", 68, 18, 18,
        "quotation", "atonement",
        "\"When he ascended up on high, he led captivity captive, and "
        "gave gifts unto men\" - Paul quotes this psalm directly of "
        "Christ's ascension, freeing the captive dead and bestowing "
        "spiritual gifts.",
    ),
    (
        "Matthew", "Holy Bible", 4, 6, 6,
        "Psalms", "Holy Bible", 91, 11, 12,
        "quotation", "temptation",
        "\"He shall give his angels charge over thee\" is the very "
        "psalm Satan quotes - accurately, but out of context - while "
        "tempting Christ to test God by casting Himself down.",
    ),
    (
        "Matthew", "Holy Bible", 21, 9, 9,
        "Psalms", "Holy Bible", 118, 26, 26,
        "quotation", "jesus-christ",
        "\"Blessed is he that cometh in the name of the Lord\" - the "
        "crowd's own shout at Christ's triumphal entry quotes this "
        "psalm directly.",
    ),
    (
        "Hebrews", "Holy Bible", 2, 6, 8,
        "Psalms", "Holy Bible", 8, 4, 6,
        "quotation", "jesus-christ",
        "\"Thou madest him a little lower than the angels... and "
        "didst set him over the works of thy hands\" - Hebrews quotes "
        "this psalm to teach Christ's own condescension and "
        "exaltation.",
    ),
    (
        "Alma", "The Book of Mormon", 37, 37, 37,
        "Proverbs", "Holy Bible", 3, 5, 6,
        "paraphrase", "prayer",
        "\"Trust in the Lord with all thine heart... and he shall "
        "direct thy paths\" and \"counsel with the Lord in all thy "
        "doings, and he will direct thee for good\" teach the identical "
        "pattern of seeking God's guidance in daily life.",
    ),
    (
        "Moses", "Pearl of Great Price", 6, 63, 63,
        "Psalms", "Holy Bible", 19, 1, 1,
        "paraphrase", "creation",
        "\"The heavens declare the glory of God\" and \"all things... "
        "are created and made to bear record of me\" both teach that "
        "creation itself testifies of God, not just scripture or "
        "prophets.",
    ),
    (
        "Matthew", "Holy Bible", 5, 5, 5,
        "Psalms", "Holy Bible", 37, 11, 11,
        "quotation", "humility",
        "\"The meek shall inherit the earth\" - one of the Beatitudes, "
        "quoted directly from this psalm.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 68, 25, 28,
        "Psalms", "Holy Bible", 127, 3, 3,
        "paraphrase", "children",
        "\"Children are an heritage of the Lord\" is the same premise "
        "behind the commandment that parents \"teach them to "
        "understand the doctrine\" - children are a trust from God, "
        "not merely a family matter.",
    ),
    (
        "Micah", "Holy Bible", 7, 19, 19,
        "Psalms", "Holy Bible", 103, 12, 12,
        "paraphrase", "forgiveness",
        "\"As far as the east is from the west, so far hath he removed "
        "our transgressions\" and \"cast all their sins into the depths "
        "of the sea\" both picture complete, irretrievable forgiveness.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 9, 15, 15,
        "Genesis", "Holy Bible", 1, 1, 1,
        "quotation", "jesus-christ",
        "\"I created the heavens and the earth, and all things that in "
        "them are\" - the resurrected Christ explicitly claims to be "
        "the Creator of Genesis' opening account.",
    ),
    (
        "Moses", "Pearl of Great Price", 6, 60, 60,
        "Leviticus", "Holy Bible", 17, 11, 11,
        "paraphrase", "atonement",
        "\"It is the blood that maketh an atonement for your souls\" "
        "and \"by the blood ye are sanctified\" both root atonement and "
        "sanctification in blood - anticipating Christ's own atoning "
        "blood.",
    ),
    (
        "1 Peter", "Holy Bible", 1, 16, 16,
        "Leviticus", "Holy Bible", 19, 2, 2,
        "quotation", "reverence",
        "\"Be ye holy; for I am holy\" - Peter quotes this commandment "
        "directly, unchanged across covenants old and new.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 122, 7, 7,
        "Job", "Holy Bible", 13, 15, 15,
        "paraphrase", "trials-and-adversity",
        "\"Though he slay me, yet will I trust in him\" is the same "
        "resolve behind the promise that the deepest afflictions, even "
        "to \"the gates of hell,\" \"shall be but a small moment\" if "
        "endured well.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 2, 24, 24,
        "Genesis", "Holy Bible", 50, 20, 20,
        "paraphrase", "plan-of-salvation",
        "\"Ye thought evil against me; but God meant it unto good\" and "
        "\"all things have been done in the wisdom of him who knoweth "
        "all things\" both teach that God can turn even others' evil "
        "intentions toward His own good purposes.",
    ),
    (
        "Revelation", "Holy Bible", 22, 18, 19,
        "Deuteronomy", "Holy Bible", 4, 2, 2,
        "paraphrase", "word-of-god",
        "\"Ye shall not add unto the word... neither shall ye "
        "diminish ought from it\" and Revelation's own closing warning "
        "against adding to or taking from \"this book\" bookend the "
        "entire Bible with the same command.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 32, 3, 3,
        "Joshua", "Holy Bible", 1, 8, 8,
        "paraphrase", "word-of-god",
        "\"Thou shalt meditate therein day and night\" and \"feast "
        "upon the words of Christ\" both call for constant, not "
        "occasional, engagement with scripture.",
    ),
    (
        "Helaman", "The Book of Mormon", 5, 12, 12,
        "1 Samuel", "Holy Bible", 2, 2, 2,
        "paraphrase", "jesus-christ",
        "\"There is none holy as the Lord... neither is there any rock "
        "like our God\" and \"the rock of our Redeemer, who is Christ\" "
        "both use the same title - the Rock - for God.",
    ),
    (
        "Alma", "The Book of Mormon", 44, 4, 4,
        "2 Chronicles", "Holy Bible", 20, 15, 15,
        "paraphrase", "faith",
        "\"Be not afraid nor dismayed... for the battle is not yours, "
        "but God's\" and \"God will support, and keep, and preserve "
        "us, so long as we are faithful\" both teach that victory in a "
        "righteous cause depends on God, not numbers or strength.",
    ),
    (
        "Mosiah", "The Book of Mormon", 17, 9, 10,
        "Esther", "Holy Bible", 4, 16, 16,
        "paraphrase", "testimony",
        "\"If I perish, I perish\" and Abinadi's own willingness that "
        "\"it matters not... if it so be I am saved\" both show a "
        "readiness to risk life itself rather than abandon a righteous "
        "cause.",
    ),
    (
        "1 Nephi", "The Book of Mormon", 15, 25, 25,
        "Ecclesiastes", "Holy Bible", 12, 13, 13,
        "paraphrase", "word-of-god",
        "\"Fear God, and keep his commandments: for this is the whole "
        "duty of man\" and Nephi's own exhortation to \"give heed unto "
        "the word of the Lord\" both call obedience to God's word the "
        "defining duty of life.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 84, 99, 100,
        "Exodus", "Holy Bible", 15, 1, 2,
        "paraphrase", "salvation",
        "Both are songs of triumphant redemption - Moses and Israel "
        "singing after the Red Sea, this modern revelation's own song "
        "of Zion redeemed \"according to the election of grace.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 97, 15, 16,
        "Exodus", "Holy Bible", 25, 8, 8,
        "paraphrase", "temple",
        "\"Let them make me a sanctuary; that I may dwell among them\" "
        "and \"my glory shall rest upon\" a temple built unto the Lord "
        "both state the same purpose for a temple - God's own presence "
        "among His people.",
    ),
    (
        "Mosiah", "The Book of Mormon", 4, 15, 16,
        "Genesis", "Holy Bible", 4, 9, 9,
        "paraphrase", "service",
        "\"Am I my brother's keeper?\" is the question Cain refuses to "
        "answer rightly; Benjamin teaches the correct answer - to "
        "\"succor those that stand in need of your succor\" and "
        "\"administer to their relief.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 42, 18, 19,
        "Genesis", "Holy Bible", 9, 6, 6,
        "paraphrase", "judgment",
        "\"Whoso sheddeth man's blood, by man shall his blood be "
        "shed\" and \"he that kills shall not have forgiveness in this "
        "world, nor in the world to come\" both treat murder as the "
        "gravest of sins.",
    ),
    (
        "Luke", "Holy Bible", 1, 37, 37,
        "Genesis", "Holy Bible", 18, 14, 14,
        "paraphrase", "faith",
        "\"Is any thing too hard for the Lord?\" asked of Sarah's own "
        "impossible pregnancy, is echoed by the angel Gabriel about "
        "Mary's: \"with God nothing shall be impossible.\"",
    ),
    (
        "Moses", "Pearl of Great Price", 7, 18, 18,
        "Psalms", "Holy Bible", 133, 1, 1,
        "paraphrase", "zion",
        "\"How good and how pleasant it is for brethren to dwell "
        "together in unity\" and Enoch's Zion, \"of one heart and one "
        "mind,\" both describe the same ideal of a unified, righteous "
        "community.",
    ),
    (
        "Mosiah", "The Book of Mormon", 24, 14, 14,
        "Psalms", "Holy Bible", 55, 22, 22,
        "paraphrase", "trials-and-adversity",
        "\"Cast thy burden upon the Lord, and he shall sustain thee\" "
        "and the Lord's own promise to \"ease the burdens which are "
        "put upon your shoulders, that even you cannot feel them\" both "
        "describe divine relief carrying what a person cannot bear "
        "alone.",
    ),
    (
        "Abraham", "Pearl of Great Price", 2, 3, 3,
        "Genesis", "Holy Bible", 12, 1, 1,
        "translation", "faith",
        "Abraham's own record repeats the Lord's call to him nearly "
        "word for word - \"get thee out of thy country, and from thy "
        "kindred, and from thy father's house\" - the same call Genesis "
        "records, retold in Abraham's own voice.",
    ),
    (
        "1 Peter", "Holy Bible", 2, 9, 9,
        "Exodus", "Holy Bible", 19, 5, 6,
        "quotation", "church-of-jesus-christ",
        "\"A kingdom of priests, and an holy nation\" is echoed almost "
        "word for word: \"a royal priesthood, an holy nation, a "
        "peculiar people\" - the same covenant identity given to "
        "Israel at Sinai, and to the Church through Peter.",
    ),
    # --- Fork: Book of Mormon ---
    (
        "1 Nephi", "The Book of Mormon", 10, 7, 10,
        "Matthew", "Holy Bible", 3, 11, 11,
        "quotation", "jesus-christ",
        "Lehi prophesies of \"a prophet who should come before the "
        "Messiah, to prepare the way of the Lord\" who \"should baptize "
        "in Bethabara, beyond Jordan\" - the same prophet Matthew "
        "records as John the Baptist, who says of Christ, \"he that "
        "cometh after me is mightier than I.\"",
    ),
    (
        "1 Nephi", "The Book of Mormon", 11, 18, 21,
        "Luke", "Holy Bible", 1, 30, 35,
        "paraphrase", "jesus-christ",
        "Nephi's vision shows him \"the virgin\" who is \"the mother of "
        "the Son of God, after the manner of the flesh\" - the same "
        "annunciation Luke records, when the angel tells Mary she will "
        "\"bring forth a son\" and \"call his name Jesus.\"",
    ),
    (
        "1 Nephi", "The Book of Mormon", 14, 14, 14,
        "Ephesians", "Holy Bible", 1, 10, 10,
        "paraphrase", "restoration",
        "Nephi's vision of the saints \"armed with righteousness and "
        "with the power of God in great glory\" in the last days "
        "matches Paul's own \"dispensation of the fulness of times,\" "
        "when God gathers His covenant people together in Christ.",
    ),
    (
        "1 Nephi", "The Book of Mormon", 17, 41, 41,
        "Numbers", "Holy Bible", 21, 8, 9,
        "typology", "jesus-christ",
        "Nephi recounts the same brazen-serpent story as Numbers - "
        "\"the labor which they had to perform was to look\" - a "
        "fourth witness (alongside John 3:14-15, Alma 33:19-22, and "
        "Helaman 8:14-15 above) that simple faith, not effort, was "
        "what healed them.",
    ),
    (
        "1 Nephi", "The Book of Mormon", 22, 20, 21,
        "Deuteronomy", "Holy Bible", 18, 15, 19,
        "quotation", "prophets",
        "Nephi quotes the same prophecy of Moses that Peter later "
        "quotes in Acts 3:22 - \"A prophet shall the Lord your God "
        "raise up unto you, like unto me\" - applying it to Christ "
        "centuries before Peter does.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 2, 27, 27,
        "Joshua", "Holy Bible", 24, 15, 15,
        "paraphrase", "agency",
        "\"Free to choose liberty and eternal life... or to choose "
        "captivity and death\" and Joshua's own charge, \"choose you "
        "this day whom ye will serve,\" both frame agency as a real, "
        "consequential choice between serving God or not.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 4, 17, 19,
        "Romans", "Holy Bible", 7, 24, 24,
        "quotation", "repentance",
        "\"O wretched man that I am!\" - Nephi's own psalm of "
        "self-reproach uses nearly the same cry as Paul's, both "
        "immediately followed by turning back to God rather than "
        "despair.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 7, None, None,
        "Isaiah", "Holy Bible", 50, None, None,
        "quotation", "jesus-christ",
        "Nephi quotes Isaiah 50 in its entirety, word for word - the "
        "Lord's servant giving \"my back to the smiters,\" confident "
        "that \"he is near that justifieth me.\"",
    ),
    (
        "2 Nephi", "The Book of Mormon", 8, None, None,
        "Isaiah", "Holy Bible", 51, None, None,
        "quotation", "zion",
        "\"Look unto the rock from whence ye are hewn... look unto "
        "Abraham your father\" - Nephi quotes Isaiah's own comfort to "
        "Zion, promising joy and gladness to a people presently "
        "afflicted.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 11, 4, 4,
        "Colossians", "Holy Bible", 2, 17, 17,
        "paraphrase", "jesus-christ",
        "\"All things which have been given of God from the beginning "
        "of the world, unto man, are the typifying of him\" is Nephi's "
        "own statement of the very principle behind this whole "
        "feature - matching Paul's own \"which are a shadow of things "
        "to come; but the body is of Christ.\"",
    ),
    (
        "2 Nephi", "The Book of Mormon", 26, 24, 24,
        "John", "Holy Bible", 3, 16, 17,
        "paraphrase", "jesus-christ",
        "\"He loveth the world, even that he layeth down his own life "
        "that he may draw all men unto him\" restates John's own "
        "\"God so loved the world, that he gave his only begotten "
        "Son.\"",
    ),
    (
        "2 Nephi", "The Book of Mormon", 31, 5, 9,
        "Matthew", "Holy Bible", 3, 13, 15,
        "paraphrase", "baptism",
        "\"If the Lamb of God, he being holy, should have need to be "
        "baptized by water, to fulfil all righteousness\" - Nephi "
        "reasons from the very account Matthew records, where Christ "
        "tells John, \"thus it becometh us to fulfil all "
        "righteousness.\"",
    ),
    (
        "2 Nephi", "The Book of Mormon", 31, 20, 20,
        "Doctrine and Covenants", "Doctrine and Covenants", 14, 7, 7,
        "paraphrase", "exaltation",
        "\"If ye shall press forward... and endure to the end... ye "
        "shall have eternal life\" matches the same promise named "
        "\"the greatest of all the gifts of God\" in this modern "
        "revelation.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 31, 20, 20,
        "Hebrews", "Holy Bible", 11, 1, 1,
        "paraphrase", "hope",
        "\"A perfect brightness of hope\" is Nephi's own phrase for the "
        "same confidence Paul defines as faith: \"the substance of "
        "things hoped for, the evidence of things not seen.\"",
    ),
    (
        "Jacob", "The Book of Mormon", 4, 4, 5,
        "Hebrews", "Holy Bible", 11, 13, 13,
        "paraphrase", "faith",
        "\"We knew of Christ, and we had a hope of his glory many "
        "hundred years before his coming\" is the same faith Hebrews "
        "describes in the patriarchs, who \"having seen them afar off\" "
        "still \"were persuaded of them, and embraced them.\"",
    ),
    (
        "Jarom", "The Book of Mormon", 1, 11, 11,
        "Acts", "Holy Bible", 10, 43, 43,
        "paraphrase", "prophets",
        "Jarom's prophets, priests, and teachers spent their lives "
        "\"persuading them to look forward unto the Messiah, and "
        "believe in him to come as though he already was\" - the same "
        "witness Peter later describes running the other direction: "
        "\"to him give all the prophets witness.\"",
    ),
    (
        "Omni", "The Book of Mormon", 1, 26, 26,
        "Doctrine and Covenants", "Doctrine and Covenants", 14, 7, 7,
        "paraphrase", "exaltation",
        "\"Come unto Christ... and endure to the end; and as the Lord "
        "liveth ye will be saved\" is Amaleki's own version of the same "
        "eternal-life promise named explicitly in D&C 14:7 above.",
    ),
    (
        "Words of Mormon", "The Book of Mormon", 1, 7, 8,
        "Isaiah", "Holy Bible", 55, 8, 9,
        "paraphrase", "truth",
        "Mormon trusts a purpose he cannot fully see - \"I do not know "
        "all things; but the Lord knoweth all things which are to "
        "come\" - the same humility Isaiah teaches: \"my thoughts are "
        "not your thoughts, neither are your ways my ways.\"",
    ),
    (
        "Mosiah", "The Book of Mormon", 2, 17, 17,
        "Matthew", "Holy Bible", 25, 40, 40,
        "paraphrase", "service",
        "\"When ye are in the service of your fellow beings ye are "
        "only in the service of your God\" is King Benjamin's own "
        "version of Christ's \"inasmuch as ye have done it unto one of "
        "the least of these my brethren, ye have done it unto me.\"",
    ),
    (
        "Mosiah", "The Book of Mormon", 13, 12, 24,
        "Exodus", "Holy Bible", 20, 3, 17,
        "quotation", "obedience",
        "Abinadi recites the Ten Commandments to King Noah's priests "
        "word for word from the law of Moses, before teaching that "
        "salvation does not come by this law alone.",
    ),
    (
        "Mosiah", "The Book of Mormon", 15, 1, 3,
        "John", "Holy Bible", 1, 1, 14,
        "paraphrase", "godhead",
        "\"God himself shall come down among the children of men, and "
        "shall redeem his people\" is Abinadi's own statement of the "
        "same mystery John opens his gospel with: \"the Word was God... "
        "and the Word was made flesh, and dwelt among us.\"",
    ),
    (
        "Mosiah", "The Book of Mormon", 16, 6, 8,
        "1 Corinthians", "Holy Bible", 15, 54, 55,
        "paraphrase", "resurrection",
        "Abinadi's \"O death, where is thy sting? O grave, where is thy "
        "victory?\" is quoted so closely from Paul's own words that the "
        "two passages read almost as one, though centuries and an "
        "ocean apart.",
    ),
    (
        "Mosiah", "The Book of Mormon", 27, 8, 24,
        "Acts", "Holy Bible", 9, 1, 9,
        "paraphrase", "repentance",
        "Alma the younger, actively working \"to destroy the church of "
        "God,\" is struck down and left unable to speak by an angel's "
        "appearance - the same pattern as Saul's own conversion on the "
        "road to Damascus, struck blind by a light and voice from "
        "heaven.",
    ),
    (
        "Alma", "The Book of Mormon", 5, 38, 38,
        "John", "Holy Bible", 10, 11, 11,
        "paraphrase", "jesus-christ",
        "\"The good shepherd doth call you... in his own name, which "
        "is the name of Christ\" - Alma uses the very title Christ "
        "later claims for Himself: \"I am the good shepherd: the good "
        "shepherd giveth his life for the sheep.\"",
    ),
    (
        "Alma", "The Book of Mormon", 26, 12, 12,
        "Genesis", "Holy Bible", 18, 27, 27,
        "paraphrase", "humility",
        "\"I know that I am nothing; as to my strength I am weak... I "
        "will boast of my God\" is Ammon's own version of Abraham's "
        "humility before the Lord, taking no credit for what only God "
        "could accomplish.",
    ),
    (
        "Alma", "The Book of Mormon", 30, 44, 44,
        "Romans", "Holy Bible", 1, 20, 20,
        "paraphrase", "truth",
        "Alma's argument to Korihor - \"all things denote there is a "
        "God; yea, even the earth, and all things that are upon the "
        "face of it\" - matches Paul's own claim that God's \"eternal "
        "power and Godhead\" are \"clearly seen, being understood by "
        "the things that are made.\"",
    ),
    (
        "Alma", "The Book of Mormon", 32, 21, 21,
        "Hebrews", "Holy Bible", 11, 1, 1,
        "paraphrase", "faith",
        "\"Faith is not to have a perfect knowledge of things; "
        "therefore if ye have faith ye hope for things which are not "
        "seen\" is nearly Paul's own definition: \"faith is the "
        "substance of things hoped for, the evidence of things not "
        "seen.\"",
    ),
    (
        "Alma", "The Book of Mormon", 34, 32, 34,
        "2 Corinthians", "Holy Bible", 6, 2, 2,
        "paraphrase", "repentance",
        "\"This life is the time for men to prepare to meet God\" is "
        "Amulek's own version of Paul's \"now is the accepted time; "
        "behold, now is the day of salvation\" - urgency about "
        "repenting without delay.",
    ),
    (
        "Alma", "The Book of Mormon", 36, 6, 10,
        "Acts", "Holy Bible", 9, 1, 9,
        "paraphrase", "repentance",
        "Alma's own account to his son of being confronted by an angel "
        "\"as it were with a voice of thunder\" while \"seeking to "
        "destroy the church of God\" is his first-person retelling of "
        "the same conversion pattern Paul experienced on the road to "
        "Damascus.",
    ),
    (
        "Alma", "The Book of Mormon", 42, 8, 8,
        "Doctrine and Covenants", "Doctrine and Covenants", 14, 7, 7,
        "paraphrase", "plan-of-salvation",
        "Alma teaches that reclaiming man from temporal death without "
        "a plan \"would destroy the great plan of happiness\" - the "
        "same plan whose reward, eternal life, D&C 14:7 calls "
        "\"the greatest of all the gifts of God.\"",
    ),
    (
        "Alma", "The Book of Mormon", 42, 15, 15,
        "Romans", "Holy Bible", 3, 26, 26,
        "paraphrase", "atonement",
        "\"God himself atoneth for the sins of the world, to bring "
        "about the plan of mercy, to appease the demands of justice\" "
        "matches Paul's own teaching that God is both \"just, and the "
        "justifier of him which believeth in Jesus.\"",
    ),
    (
        "Helaman", "The Book of Mormon", 3, 29, 29,
        "Hebrews", "Holy Bible", 4, 12, 12,
        "paraphrase", "word-of-god",
        "\"The word of God... is quick and powerful, which shall "
        "divide asunder all the cunning and the snares and the wiles "
        "of the devil\" nearly repeats Hebrews' own description: "
        "\"the word of God is quick, and powerful, and sharper than "
        "any twoedged sword.\"",
    ),
    (
        "Helaman", "The Book of Mormon", 12, 7, 8,
        "Isaiah", "Holy Bible", 40, 15, 17,
        "paraphrase", "humility",
        "\"How great is the nothingness of the children of men\" and "
        "Isaiah's own \"the nations are as a drop of a bucket... "
        "counted as the small dust of the balance\" both teach the "
        "same lesson of humility before God's greatness.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 9, 18, 18,
        "John", "Holy Bible", 8, 12, 12,
        "paraphrase", "jesus-christ",
        "\"I am the light and the life of the world\" - Christ repeats "
        "to the Nephites, in the darkness following His crucifixion, "
        "the same title He claimed in Jerusalem: \"I am the light of "
        "the world.\"",
    ),
    (
        "3 Nephi", "The Book of Mormon", 17, 21, 24,
        "Mark", "Holy Bible", 10, 13, 16,
        "paraphrase", "children",
        "Christ blesses the Nephite children \"one by one\" with angels "
        "encircling them in fire - the same tenderness as when He "
        "\"took them up in his arms, put his hands upon them, and "
        "blessed them\" in Judea.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 18, 1, 7,
        "Luke", "Holy Bible", 22, 19, 20,
        "paraphrase", "ordinances",
        "Christ institutes the sacrament of bread and wine among the "
        "Nephites in almost the same words as the Last Supper - "
        "\"this do in remembrance of me\" - the same ordinance given "
        "on two continents.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 19, 23, 23,
        "John", "Holy Bible", 17, 21, 23,
        "paraphrase", "church-of-jesus-christ",
        "Christ prays for the Nephites \"that they may believe in me, "
        "that I may be in them as thou, Father, art in me\" - nearly "
        "the same words as His own intercessory prayer in Gethsemane's "
        "own upper room, \"that they all may be one.\"",
    ),
    (
        "3 Nephi", "The Book of Mormon", 27, 27, 27,
        "Matthew", "Holy Bible", 16, 24, 24,
        "paraphrase", "discipleship",
        "\"What manner of men ought ye to be?... even as I am\" and "
        "Christ's own charge to \"deny himself, and take up his cross, "
        "and follow me\" both describe the same total, transforming "
        "discipleship.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 28, 6, 9,
        "John", "Holy Bible", 21, 22, 23,
        "quotation", "testimony",
        "Christ explicitly names \"John, my beloved, who was with me "
        "in my ministry\" as the very disciple this desire was granted "
        "to, confirming the same tarrying John's own gospel only hints "
        "at: \"if I will that he tarry till I come, what is that to "
        "thee?\"",
    ),
    (
        "Mormon", "The Book of Mormon", 7, 5, 7,
        "Acts", "Holy Bible", 4, 12, 12,
        "paraphrase", "salvation",
        "Mormon's dying charge to \"believe in Jesus Christ, that he is "
        "the Son of God\" rests on the same exclusive claim Peter "
        "makes: \"none other name under heaven given among men, "
        "whereby we must be saved.\"",
    ),
    (
        "Ether", "The Book of Mormon", 3, 6, 16,
        "1 Timothy", "Holy Bible", 6, 16, 16,
        "paraphrase", "faith",
        "The brother of Jared sees the Lord's finger, then His whole "
        "spirit body, told \"never has man come before me with such "
        "exceeding faith\" - remarkable precisely because, as Paul "
        "says, God ordinarily dwells \"in the light which no man can "
        "approach unto.\"",
    ),
    (
        "Ether", "The Book of Mormon", 6, 2, 12,
        "Genesis", "Holy Bible", 7, 17, 18,
        "paraphrase", "faith",
        "The Jaredite barges, buried in the sea yet brought safely "
        "across by the Lord, echo Noah's own ark - both accounts of a "
        "vessel and a people preserved through water by following "
        "exact divine instruction.",
    ),
    (
        "Moroni", "The Book of Mormon", 6, 4, 4,
        "Acts", "Holy Bible", 2, 42, 42,
        "paraphrase", "church-of-jesus-christ",
        "The newly baptized Nephites were \"numbered among the people "
        "of the church of Christ\" and nourished \"by the good word of "
        "God\" - the same pattern of fellowship Acts describes: "
        "\"they continued steadfastly in the apostles' doctrine and "
        "fellowship.\"",
    ),
    (
        "Moroni", "The Book of Mormon", 8, 8, 12,
        "Mark", "Holy Bible", 10, 14, 14,
        "paraphrase", "baptism",
        "\"Little children are alive in Christ\" and need no baptism, "
        "Mormon teaches - the same truth behind Christ's own words, "
        "\"suffer the little children to come unto me, and forbid them "
        "not: for of such is the kingdom of God.\"",
    ),
    # --- Fork: New Testament ---
    (
        "Mark", "Holy Bible", 10, 14, 15,
        "3 Nephi", "The Book of Mormon", 11, 37, 38,
        "paraphrase", "baptism",
        "\"Suffer the little children to come unto me... for of such is "
        "the kingdom of God\" and \"ye must repent, and become as a "
        "little child, and be baptized\" both make childlike humility "
        "the condition of entering God's kingdom.",
    ),
    (
        "Luke", "Holy Bible", 15, 4, 7,
        "Doctrine and Covenants", "Doctrine and Covenants", 18, 15, 15,
        "paraphrase", "missionary-work",
        "The shepherd who leaves ninety and nine to seek the one lost "
        "sheep is the same joy this modern revelation promises: \"if it "
        "so be... ye bring, save it be one soul unto me, how great shall "
        "be your joy.\"",
    ),
    (
        "Luke", "Holy Bible", 24, 32, 32,
        "Doctrine and Covenants", "Doctrine and Covenants", 9, 8, 9,
        "paraphrase", "revelation",
        "\"Did not our heart burn within us, while he talked with us by "
        "the way\" describes in narrative the very confirmation this "
        "revelation later teaches as a pattern: \"I will cause that your "
        "bosom shall burn within you.\"",
    ),
    (
        "Luke", "Holy Bible", 24, 36, 39,
        "Doctrine and Covenants", "Doctrine and Covenants", 130, 22, 22,
        "quotation", "godhead",
        "The risen Christ invites the apostles to \"handle me, and see; "
        "for a spirit hath not flesh and bones, as ye see me have\" - "
        "the same doctrine this modern revelation states plainly: \"The "
        "Father has a body of flesh and bones as tangible as man's; the "
        "Son also.\"",
    ),
    (
        "John", "Holy Bible", 5, 39, 39,
        "Jacob", "The Book of Mormon", 7, 11, 11,
        "paraphrase", "testimony",
        "\"Search the scriptures... they are they which testify of me\" "
        "and \"none of the prophets have written, nor prophesied, save "
        "they have spoken concerning this Christ\" both teach that "
        "scripture's whole purpose is to testify of Him.",
    ),
    (
        "John", "Holy Bible", 20, 29, 29,
        "Alma", "The Book of Mormon", 32, 21, 21,
        "paraphrase", "faith",
        "\"Blessed are they that have not seen, and yet have believed\" "
        "and \"faith is not to have a perfect knowledge of things... ye "
        "hope for things which are not seen, which are true\" both "
        "describe faith as trust that outruns physical proof.",
    ),
    (
        "Acts", "Holy Bible", 9, 3, 6,
        "Alma", "The Book of Mormon", 36, 6, 11,
        "paraphrase", "testimony",
        "Saul struck down by light on the road to Damascus and Alma "
        "struck down by an angel's voice \"as it were of thunder\" are "
        "each a sudden, overwhelming conversion that redirects a "
        "persecutor into a witness of Christ.",
    ),
    (
        "Romans", "Holy Bible", 8, 38, 39,
        "2 Nephi", "The Book of Mormon", 1, 15, 15,
        "paraphrase", "love",
        "\"Nothing... shall be able to separate us from the love of "
        "God\" and \"I am encircled about eternally in the arms of his "
        "love\" both describe God's love as something nothing in "
        "mortality can take away.",
    ),
    (
        "1 Corinthians", "Holy Bible", 11, 23, 25,
        "3 Nephi", "The Book of Mormon", 18, 7, 7,
        "quotation", "ordinances",
        "\"This do in remembrance of me\" - Paul's account of the "
        "sacrament's institution at the Last Supper and Christ's own "
        "words instituting it again among the Nephites use nearly "
        "identical language for the same ordinance.",
    ),
    (
        "2 Corinthians", "Holy Bible", 5, 17, 17,
        "Mosiah", "The Book of Mormon", 27, 25, 26,
        "paraphrase", "repentance",
        "\"If any man be in Christ, he is a new creature: old things are "
        "passed away\" and \"all mankind... must be born again... "
        "changed from their carnal and fallen state\" both describe "
        "conversion as a genuine change of nature, not a fresh start in "
        "name only.",
    ),
    (
        "Ephesians", "Holy Bible", 4, 11, 14,
        "Articles of Faith", "Pearl of Great Price", 1, 6, 6,
        "paraphrase", "church-of-jesus-christ",
        "\"He gave some, apostles; and some, prophets... pastors and "
        "teachers\" is the same church organization the Articles of "
        "Faith name as restored: \"the same organization that existed "
        "in the Primitive Church.\"",
    ),
    (
        "Philippians", "Holy Bible", 4, 13, 13,
        "Alma", "The Book of Mormon", 26, 12, 12,
        "quotation", "faith",
        "\"I can do all things through Christ which strengtheneth me\" "
        "and Ammon's own \"in his strength I can do all things\" name "
        "the identical source of power - not personal ability, but "
        "Christ's own strength lent to the believer.",
    ),
    (
        "Colossians", "Holy Bible", 1, 15, 17,
        "Doctrine and Covenants", "Doctrine and Covenants", 93, 21, 21,
        "paraphrase", "jesus-christ",
        "\"The image of the invisible God, the firstborn of every "
        "creature... by him were all things created\" and \"I was in "
        "the beginning with the Father, and am the Firstborn\" both "
        "name Christ's premortal role as Creator and Firstborn.",
    ),
    (
        "1 Timothy", "Holy Bible", 2, 5, 5,
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 40, 42,
        "paraphrase", "atonement",
        "\"One mediator between God and men, the man Christ Jesus\" and "
        "\"he came into the world... to be crucified for the world, and "
        "to bear the sins of the world\" both describe Christ's unique "
        "mediating role between God and mankind.",
    ),
    (
        "Hebrews", "Holy Bible", 13, 8, 8,
        "Mormon", "The Book of Mormon", 9, 9, 9,
        "quotation", "godhead",
        "\"Jesus Christ the same yesterday, and to day, and for ever\" "
        "is echoed even more closely by Mormon's own three-part "
        "phrasing, \"God is the same yesterday, today, and forever, and "
        "in him there is no variableness\" - the same doctrine of God's "
        "changeless nature (see also James 1:17 above).",
    ),
    (
        "James", "Holy Bible", 5, 14, 15,
        "Doctrine and Covenants", "Doctrine and Covenants", 42, 43, 44,
        "paraphrase", "ordinances",
        "\"Let him call for the elders of the church; and let them pray "
        "over him, anointing him with oil\" is the same ordinance of "
        "administering to the sick this modern revelation directs the "
        "elders to perform.",
    ),
    (
        "1 Peter", "Holy Bible", 1, 18, 19,
        "Exodus", "Holy Bible", 12, 5, 5,
        "typology", "atonement",
        "\"Redeemed... with the precious blood of Christ, as of a lamb "
        "without blemish\" - Peter explicitly applies the Passover "
        "lamb's own qualification, unblemished and without spot, to "
        "Christ's atoning sacrifice.",
    ),
    (
        "2 Peter", "Holy Bible", 1, 4, 4,
        "Doctrine and Covenants", "Doctrine and Covenants", 132, 20, 20,
        "paraphrase", "exaltation",
        "\"Partakers of the divine nature\" and \"then shall they be "
        "gods, because they have no end\" both teach that the faithful "
        "can become like God in nature, not merely admitted to His "
        "presence.",
    ),
    (
        "1 John", "Holy Bible", 3, 2, 2,
        "Doctrine and Covenants", "Doctrine and Covenants", 130, 1, 1,
        "quotation", "second-coming",
        "\"We shall be like him; for we shall see him as he is\" is "
        "quoted almost word for word in this revelation's own promise: "
        "\"when the Savior shall appear we shall see him as he is.\"",
    ),
    (
        "1 John", "Holy Bible", 1, 9, 9,
        "Mosiah", "The Book of Mormon", 26, 29, 30,
        "paraphrase", "repentance",
        "\"If we confess our sins, he is faithful and just to forgive us "
        "our sins\" and \"as often as my people repent will I forgive "
        "them their trespasses\" both promise that sincere confession "
        "and repentance bring real, repeated forgiveness.",
    ),
    (
        "Revelation", "Holy Bible", 1, 8, 8,
        "Doctrine and Covenants", "Doctrine and Covenants", 19, 1, 1,
        "quotation", "jesus-christ",
        "\"I am Alpha and Omega... which is, and which was, and which is "
        "to come\" is quoted almost exactly in Christ's own "
        "self-introduction to this modern revelation: \"I am Alpha and "
        "Omega, Christ the Lord... the beginning and the end.\"",
    ),
    (
        "Revelation", "Holy Bible", 1, 18, 18,
        "Doctrine and Covenants", "Doctrine and Covenants", 110, 4, 4,
        "quotation", "jesus-christ",
        "\"I am he that liveth, and was dead; and, behold, I am alive "
        "for evermore\" is echoed in Christ's own words to Joseph Smith "
        "and Oliver Cowdery in the Kirtland Temple: \"I am he who "
        "liveth, I am he who was slain.\"",
    ),
    (
        "Revelation", "Holy Bible", 12, 7, 9,
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 25, 27,
        "paraphrase", "premortal-life",
        "\"There was war in heaven: Michael and his angels fought "
        "against the dragon\" and this revelation's own account of an "
        "angel \"who rebelled against the Only Begotten Son\" both "
        "describe Lucifer's premortal rebellion.",
    ),
    (
        "Revelation", "Holy Bible", 20, 12, 13,
        "Doctrine and Covenants", "Doctrine and Covenants", 128, 6, 7,
        "quotation", "judgment",
        "Joseph Smith explicitly cites this very verse by chapter and "
        "number - \"as you will find recorded in Revelation 20:12\" - "
        "while teaching about the books of record kept for the final "
        "judgment.",
    ),
    (
        "Galatians", "Holy Bible", 4, 4, 5,
        "Doctrine and Covenants", "Doctrine and Covenants", 20, 26, 26,
        "paraphrase", "jesus-christ",
        "\"When the fulness of the time was come, God sent forth his "
        "Son\" and this revelation's own \"meridian of time, in the "
        "flesh\" both mark Christ's mortal birth as the appointed "
        "center-point of history.",
    ),
    (
        "Matthew", "Holy Bible", 16, 18, 18,
        "Doctrine and Covenants", "Doctrine and Covenants", 10, 69, 69,
        "quotation", "church-of-jesus-christ",
        "\"Upon this rock I will build my church; and the gates of hell "
        "shall not prevail against it\" is echoed almost word for word "
        "in this revelation's own promise to those who endure in "
        "Christ's church to the end.",
    ),
    (
        "Matthew", "Holy Bible", 16, 19, 19,
        "Doctrine and Covenants", "Doctrine and Covenants", 128, 8, 9,
        "paraphrase", "priesthood",
        "\"Whatsoever thou shalt bind on earth shall be bound in "
        "heaven\" is the same sealing power this revelation explains at "
        "length as an ordinance \"granted\" through priesthood "
        "authority, not Peter's alone to hold.",
    ),
    (
        "Matthew", "Holy Bible", 24, 36, 36,
        "Doctrine and Covenants", "Doctrine and Covenants", 49, 7, 7,
        "paraphrase", "second-coming",
        "\"Of that day and hour knoweth no man... but my Father only\" "
        "and \"the hour and the day no man knoweth, neither the angels "
        "in heaven\" both withhold the exact timing of the Second "
        "Coming from everyone but God.",
    ),
    (
        "John", "Holy Bible", 3, 3, 5,
        "Moses", "Pearl of Great Price", 6, 59, 60,
        "quotation", "baptism",
        "\"Except a man be born of water and of the Spirit, he cannot "
        "enter into the kingdom of God\" is taught to Adam himself in "
        "nearly the same words: \"born into the world by water, and "
        "blood, and the spirit... even so ye must be born again.\"",
    ),
    (
        "John", "Holy Bible", 6, 38, 38,
        "Moses", "Pearl of Great Price", 4, 1, 2,
        "paraphrase", "premortal-life",
        "\"I came down from heaven, not to do mine own will, but the "
        "will of him that sent me\" is the mortal fulfillment of "
        "Christ's own premortal answer to the Father's plan: \"Father, "
        "thy will be done, and the glory be thine forever.\"",
    ),
    (
        "Revelation", "Holy Bible", 3, 5, 5,
        "Alma", "The Book of Mormon", 5, 57, 58,
        "paraphrase", "judgment",
        "\"I will not blot out his name out of the book of life\" and "
        "Alma's warning that the wicked's \"names shall be blotted "
        "out\" both use the same image of a heavenly record kept - or "
        "erased - according to faithfulness.",
    ),
    (
        "Revelation", "Holy Bible", 22, 18, 19,
        "1 Nephi", "The Book of Mormon", 13, 26, 29,
        "paraphrase", "restoration",
        "John's warning against adding to or taking away from scripture "
        "and Nephi's vision of \"many plain and precious things\" being "
        "taken away from the Bible by \"that great and abominable "
        "church\" both anticipate scripture itself being corrupted.",
    ),
    (
        "Luke", "Holy Bible", 1, 37, 37,
        "1 Nephi", "The Book of Mormon", 7, 12, 12,
        "paraphrase", "faith",
        "\"For with God nothing shall be impossible\" and \"the Lord is "
        "able to do all things according to his will, for the children "
        "of men, if it so be that they exercise faith in him\" both "
        "root faith in God's own limitless power.",
    ),
    (
        "Acts", "Holy Bible", 4, 12, 12,
        "Mosiah", "The Book of Mormon", 3, 17, 17,
        "quotation", "salvation",
        "\"Neither is there salvation in any other: for there is none "
        "other name under heaven given among men, whereby we must be "
        "saved\" is repeated almost word for word: \"there shall be no "
        "other name given... whereby salvation can come... only in and "
        "through the name of Christ.\"",
    ),
    (
        "John", "Holy Bible", 11, 25, 26,
        "Mosiah", "The Book of Mormon", 16, 8, 9,
        "paraphrase", "resurrection",
        "\"I am the resurrection, and the life: he that believeth in "
        "me, though he were dead, yet shall he live\" and \"there is a "
        "resurrection, therefore the grave hath no victory, and the "
        "sting of death is swallowed up in Christ\" both anchor victory "
        "over death in Christ personally, not merely in an abstract "
        "future event.",
    ),
    (
        "Romans", "Holy Bible", 12, 1, 1,
        "Omni", "The Book of Mormon", 1, 26, 26,
        "paraphrase", "consecration",
        "\"Present your bodies a living sacrifice, holy, acceptable "
        "unto God\" and \"come unto him, and offer your whole souls as "
        "an offering unto him\" both call for a complete, personal "
        "consecration, not merely outward observance.",
    ),
    (
        "1 Corinthians", "Holy Bible", 2, 9, 9,
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 10, 10,
        "quotation", "revelation",
        "\"Eye hath not seen, nor ear heard... the things which God hath "
        "prepared for them that love him\" is quoted directly in this "
        "revelation's own account of the vision of the degrees of "
        "glory, describing \"those things which eye has not seen, nor "
        "ear heard.\"",
    ),
    (
        "Luke", "Holy Bible", 17, 10, 10,
        "Mosiah", "The Book of Mormon", 2, 21, 21,
        "quotation", "humility",
        "\"When ye shall have done all those things which are commanded "
        "you, say, We are unprofitable servants\" and King Benjamin's "
        "own \"if ye should serve him with all your whole souls yet ye "
        "would be unprofitable servants\" both teach that even perfect "
        "obedience earns no claim on God.",
    ),
    (
        "Matthew", "Holy Bible", 7, 7, 7,
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 63, 63,
        "quotation", "prayer",
        "\"Ask, and it shall be given you; seek, and ye shall find; "
        "knock, and it shall be opened unto you\" is quoted almost word "
        "for word in this modern revelation's own invitation to draw "
        "near to God.",
    ),
    (
        "Ephesians", "Holy Bible", 6, 11, 17,
        "Doctrine and Covenants", "Doctrine and Covenants", 27, 15, 18,
        "quotation", "temptation",
        "\"Put on the whole armour of God, that ye may be able to stand "
        "against the wiles of the devil\" is quoted at length in this "
        "modern revelation's own charge to \"take upon you my whole "
        "armor, that ye may be able to withstand the evil day.\"",
    ),
    (
        "1 Corinthians", "Holy Bible", 3, 16, 17,
        "Doctrine and Covenants", "Doctrine and Covenants", 93, 35, 35,
        "paraphrase", "temple",
        "\"Ye are the temple of God... if any man defile the temple of "
        "God, him shall God destroy\" is restated in this modern "
        "revelation as \"man is the tabernacle of God, even temples; "
        "and whatsoever temple is defiled, God shall destroy that "
        "temple.\"",
    ),
    (
        "Acts", "Holy Bible", 2, 38, 38,
        "Articles of Faith", "Pearl of Great Price", 1, 4, 4,
        "paraphrase", "ordinances",
        "\"Repent, and be baptized every one of you... for the "
        "remission of sins, and ye shall receive the gift of the Holy "
        "Ghost\" gives, in narrative order, the very sequence of first "
        "principles and ordinances the Articles of Faith later name "
        "formally: faith, repentance, baptism, and the gift of the Holy "
        "Ghost.",
    ),
    # --- Fork: D&C and Pearl of Great Price ---
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 4, 4, 4,
        "John", "Holy Bible", 4, 35, 35,
        "quotation", "missionary-work",
        "\"The field is white already to harvest\" - Christ's own "
        "words to His disciples in Samaria, quoted directly as this "
        "revelation's charge to labor in the latter-day harvest.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 8, 2, 3,
        "Exodus", "Holy Bible", 14, 21, 22,
        "paraphrase", "revelation",
        "\"This is the spirit of revelation; behold, this is the "
        "spirit by which Moses brought the children of Israel through "
        "the Red Sea on dry ground\" - the Lord explicitly names the "
        "exodus as the very pattern of the gift Oliver Cowdery is "
        "promised.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 9, 7, 9,
        "Luke", "Holy Bible", 24, 32, 32,
        "paraphrase", "revelation",
        "\"You must study it out in your mind\" before receiving "
        "confirmation matches the same pattern the disciples on the "
        "road to Emmaus describe after Christ opened the scriptures to "
        "them: \"did not our heart burn within us... while he opened to "
        "us the scriptures?\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 27, 11, 11,
        "Revelation", "Holy Bible", 12, 7, 7,
        "paraphrase", "premortal-life",
        "\"Michael, or Adam, the father of all, the prince of all\" is "
        "named here as the same Michael who, per Revelation, \"fought "
        "against the dragon\" in the war in heaven.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 64, 9, 10,
        "Matthew", "Holy Bible", 6, 14, 15,
        "paraphrase", "forgiveness",
        "\"He that forgiveth not his brother his trespasses standeth "
        "condemned\" is the same conditional forgiveness Christ teaches "
        "directly: \"if ye forgive not men their trespasses, neither "
        "will your Father forgive your trespasses.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 6, 13,
        "John", "Holy Bible", 1, 9, 9,
        "paraphrase", "jesus-christ",
        "\"This is the light of Christ\" is named directly here as the "
        "same light John calls \"the true Light, which lighteth every "
        "man that cometh into the world.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 89, 10, 17,
        "Daniel", "Holy Bible", 1, 8, 16,
        "paraphrase", "word-of-wisdom",
        "Daniel's refusal to \"defile himself with the portion of the "
        "king's meat, nor with the wine,\" choosing simple food instead "
        "- and being found healthier for it - is the same principle "
        "the Word of Wisdom teaches about wholesome food and abstaining "
        "from what harms the body.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 121, 34, 36,
        "Matthew", "Holy Bible", 22, 14, 14,
        "quotation", "humility",
        "\"There are many called, but few are chosen\" repeats Christ's "
        "own words almost exactly, explained here as failing \"because "
        "their hearts are set so much upon the things of this world.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 35, 17, 18,
        "Matthew", "Holy Bible", 16, 19, 19,
        "paraphrase", "priesthood",
        "\"The keys of the mystery of those things which have been "
        "sealed\" given to Joseph Smith parallel the keys of the "
        "kingdom Christ gives Peter, with authority to bind and loose.",
    ),
    (
        "Moses", "Pearl of Great Price", 1, 12, 15,
        "Matthew", "Holy Bible", 4, 3, 10,
        "paraphrase", "temptation",
        "Satan tempts Moses directly, \"worship me,\" and is answered "
        "and cast out - the same pattern of temptation and rejection "
        "Christ Himself later models in the wilderness against the "
        "same adversary.",
    ),
    (
        "Moses", "Pearl of Great Price", 7, 68, 69,
        "Hebrews", "Holy Bible", 11, 5, 5,
        "quotation", "faith",
        "\"Zion was not, for God received it up\" - Enoch's city taken "
        "up without tasting death is the same event Hebrews names "
        "directly: \"by faith Enoch was translated that he should not "
        "see death... for before his translation he had this "
        "testimony, that he pleased God.\"",
    ),
    (
        "Abraham", "Pearl of Great Price", 4, 1, 3,
        "Genesis", "Holy Bible", 1, 1, 3,
        "translation", "creation",
        "Abraham's own account of the creation - \"the Gods organized "
        "and formed the heavens and the earth\" - a third telling of "
        "Genesis 1's opening, alongside Moses 2 above, each independent "
        "but describing the same work.",
    ),
    (
        "Abraham", "Pearl of Great Price", 1, 2, 4,
        "Hebrews", "Holy Bible", 11, 8, 10,
        "paraphrase", "faith",
        "Abraham seeking \"the blessings of the fathers\" and \"a "
        "greater knowledge\" is the same faith Hebrews describes: "
        "\"by faith Abraham... obeyed... and he went out, not knowing "
        "whither he went.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 137, 7, 10,
        "1 Peter", "Holy Bible", 4, 6, 6,
        "paraphrase", "salvation",
        "\"All who have died without a knowledge of this gospel... "
        "shall be heirs of the celestial kingdom\" is the same "
        "doctrine Peter states directly: \"the gospel preached also to "
        "them that are dead, that they might be judged according to "
        "men in the flesh, but live according to God in the spirit.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 138, 29, 37,
        "1 Peter", "Holy Bible", 3, 18, 20,
        "paraphrase", "salvation",
        "This vision explains in detail what Peter states briefly - "
        "that Christ, between His death and resurrection, \"went and "
        "preached unto the spirits in prison\" - by describing exactly "
        "who was taught, and by whom, among the dead.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 86, 1, 7,
        "Matthew", "Holy Bible", 13, 24, 30,
        "quotation", "judgment",
        "An explicit, verse-by-verse interpretation of Christ's own "
        "parable: \"the field was the world, and the apostles were the "
        "sowers of the seed,\" naming who the wheat, the tares, and the "
        "harvest represent.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 42, 18, 19,
        "Exodus", "Holy Bible", 20, 13, 15,
        "quotation", "obedience",
        "\"Thou shalt not kill\" is restated to the Church almost word "
        "for word from the Ten Commandments, with an added penalty "
        "clause for the current dispensation.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 64, 33, 34,
        "Galatians", "Holy Bible", 6, 9, 9,
        "quotation", "endure-to-the-end",
        "\"Be not weary in well-doing\" repeats Paul's own words "
        "almost exactly, both promising a harvest to those who don't "
        "give up.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 6, 34, 34,
        "Luke", "Holy Bible", 12, 32, 32,
        "quotation", "faith",
        "\"Fear not, little flock\" repeats Christ's own words to His "
        "disciples nearly verbatim, reassuring Oliver Cowdery the same "
        "way Christ reassured the Twelve.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 98, 16, 16,
        "Isaiah", "Holy Bible", 2, 4, 4,
        "paraphrase", "peace",
        "\"Renounce war and proclaim peace\" echoes Isaiah's own vision "
        "of a day when nations \"shall beat their swords into "
        "plowshares... neither shall they learn war any more.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 5, 10,
        "1 Corinthians", "Holy Bible", 2, 9, 9,
        "quotation", "plan-of-salvation",
        "\"Great shall be their reward and eternal shall be their "
        "glory\" is introduced here in language matching Paul's own "
        "quotation: \"eye hath not seen, nor ear heard, neither have "
        "entered into the heart of man, the things which God hath "
        "prepared for them that love him.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 133, 36, 37,
        "Revelation", "Holy Bible", 14, 6, 6,
        "quotation", "restoration",
        "\"I have sent forth mine angel flying through the midst of "
        "heaven, having the everlasting gospel\" repeats John's own "
        "vision almost word for word, identifying it as already "
        "fulfilled.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 29, 36, 38,
        "Isaiah", "Holy Bible", 14, 12, 15,
        "paraphrase", "premortal-life",
        "\"The devil was before Adam, for he rebelled against me... "
        "and sought to destroy the agency of man\" gives the premortal "
        "backstory to the same fall Isaiah describes: \"how art thou "
        "fallen from heaven, O Lucifer, son of the morning!\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 136, 1, 4,
        "Exodus", "Holy Bible", 18, 21, 21,
        "paraphrase", "church-of-jesus-christ",
        "Organizing the westward-journeying Saints into \"companies, "
        "with a president and his two counselors at the head thereof\" "
        "follows the same pattern Jethro counsels Moses to adopt: "
        "\"rulers of thousands, rulers of hundreds, rulers of fifties, "
        "and rulers of tens.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 84, 19, 22,
        "2 Timothy", "Holy Bible", 3, 5, 5,
        "paraphrase", "priesthood",
        "\"Without the ordinances thereof... the power of godliness is "
        "not manifest\" is the positive counterpart to Paul's warning "
        "of those \"having a form of godliness, but denying the power "
        "thereof.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 46, 10, 26,
        "1 Corinthians", "Holy Bible", 12, 4, 11,
        "paraphrase", "holy-ghost",
        "This revelation's own list of spiritual gifts - given \"to "
        "every man... that all may be profited\" - parallels Paul's "
        "own list of gifts \"by the same Spirit,\" a third version of "
        "this same doctrine alongside Moroni 10 above.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 22, 24,
        "1 Corinthians", "Holy Bible", 15, 3, 8,
        "paraphrase", "testimony",
        "\"This is the testimony... that he lives! For we saw him\" is "
        "the same kind of eyewitness resurrection testimony Paul lists "
        "at length: \"he was seen of Cephas, then of the twelve... he "
        "was seen of me also.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 25, 3, 3,
        "2 John", "Holy Bible", 1, 1, 1,
        "quotation", "",
        "\"Thou art an elect lady, whom I have called\" uses the exact "
        "title John addresses to an otherwise-unnamed woman: \"the "
        "elder unto the elect lady and her children.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 128, 8, 9,
        "Matthew", "Holy Bible", 18, 18, 18,
        "quotation", "priesthood",
        "\"Whatsoever you bind on earth shall be bound in heaven\" "
        "repeats Christ's own words to explain the binding power of "
        "priesthood ordinances performed for the dead.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 84, 33, 40,
        "Hebrews", "Holy Bible", 7, 20, 21,
        "paraphrase", "priesthood",
        "The \"oath and covenant\" of the priesthood described here "
        "matches the pattern Hebrews describes for Christ's own "
        "priesthood: \"not without an oath he was made priest... The "
        "Lord sware and will not repent, Thou art a priest for ever "
        "after the order of Melchisedec.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 50, 23, 23,
        "1 Corinthians", "Holy Bible", 14, 33, 33,
        "paraphrase", "truth",
        "\"That which doth not edify is not of God, and is darkness\" "
        "teaches the same principle Paul states to the Corinthians: "
        "\"God is not the author of confusion, but of peace.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 78, 5, 6,
        "Acts", "Holy Bible", 4, 32, 32,
        "paraphrase", "consecration",
        "\"That you may be equal in the bonds of heavenly things... "
        "and earthly things also\" is the same economic unity the early "
        "Church practiced: \"of one heart and of one soul... they had "
        "all things common.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 20, 37, 37,
        "Mosiah", "The Book of Mormon", 18, 8, 10,
        "paraphrase", "baptism",
        "\"Come forth with broken hearts and contrite spirits\" as the "
        "requirement for baptism matches Alma's own baptismal covenant "
        "at the waters of Mormon - the same ordinance, described in "
        "nearly the same terms centuries apart.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 13, 1, 1,
        "Malachi", "Holy Bible", 3, 3, 3,
        "paraphrase", "priesthood",
        "The restored \"Priesthood of Aaron\" is conferred in words "
        "recalling Malachi's own prophecy that the Lord \"shall purify "
        "the sons of Levi... that they may offer unto the Lord an "
        "offering in righteousness.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 56, 57,
        "Revelation", "Holy Bible", 1, 6, 6,
        "paraphrase", "priesthood",
        "\"They are they who are priests and kings\" matches John's own "
        "description of the redeemed: Christ \"hath made us kings and "
        "priests unto God and his Father.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 84, 99, 102,
        "Isaiah", "Holy Bible", 45, 5, 6,
        "paraphrase", "godhead",
        "This song's declaration - \"the Lord hath redeemed his "
        "people\" and reigns without rival - echoes Isaiah's own "
        "words spoken by the Lord: \"I am the Lord, and there is none "
        "else, there is no God beside me.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 90, 24, 24,
        "Romans", "Holy Bible", 8, 28, 28,
        "quotation", "faith",
        "\"All things shall work together for your good, if ye walk "
        "uprightly\" repeats Paul's own words almost exactly: \"we know "
        "that all things work together for good to them that love "
        "God.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 93, 1, 1,
        "Matthew", "Holy Bible", 5, 8, 8,
        "paraphrase", "repentance",
        "\"Every soul who forsaketh his sins... shall see my face\" "
        "teaches the same promise as the Beatitude: \"blessed are the "
        "pure in heart: for they shall see God.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 41, 41,
        "Hebrews", "Holy Bible", 4, 13, 13,
        "paraphrase", "godhead",
        "\"He comprehendeth all things, and all things are before "
        "him\" states the same doctrine of God's complete knowledge "
        "that Hebrews teaches: \"all things are naked and opened unto "
        "the eyes of him with whom we have to do.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 3, 1, 2,
        "Isaiah", "Holy Bible", 14, 27, 27,
        "paraphrase", "truth",
        "\"The works, and the designs, and the purposes of God cannot "
        "be frustrated\" restates Isaiah's own question: \"the Lord of "
        "hosts hath purposed, and who shall disannul it?\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 19, 16, 17,
        "Isaiah", "Holy Bible", 53, None, None,
        "paraphrase", "atonement",
        "\"I, God, have suffered these things for all, that they "
        "might not suffer if they would repent\" is Christ's own first-"
        "person statement of the very suffering Isaiah's servant "
        "chapter foretells, already quoted directly in Mosiah 14 and "
        "Matthew 8:17 above.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 45, 51, 52,
        "Zechariah", "Holy Bible", 12, 10, 10,
        "quotation", "second-coming",
        "\"What are these wounds in thine hands and in thy feet?\" is "
        "this revelation's own retelling of Zechariah's prophecy - "
        "\"they shall look upon me whom they have pierced\" - already "
        "fulfilled once at the crucifixion (see John 19:37 above) and "
        "foretold here to be recognized again at the Second Coming.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 25, 29,
        "Revelation", "Holy Bible", 12, 9, 9,
        "paraphrase", "premortal-life",
        "\"An angel of God who was in authority in the presence of "
        "God... was thrust down\" matches John's own vision of the "
        "same rebellion: \"that old serpent, called the Devil, and "
        "Satan... was cast out into the earth.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 107, 18, 19,
        "Hebrews", "Holy Bible", 12, 22, 24,
        "paraphrase", "priesthood",
        "\"To commune with the general assembly and church of the "
        "Firstborn, and to enjoy the communion and presence of God the "
        "Father, and Jesus the mediator\" echoes Hebrews' own phrase "
        "almost exactly: \"the general assembly and church of the "
        "firstborn... Jesus the mediator of the new covenant.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 121, 7, 9,
        "2 Corinthians", "Holy Bible", 4, 17, 17,
        "paraphrase", "trials-and-adversity",
        "\"Thine adversity and thine afflictions shall be but a small "
        "moment\" teaches the same doctrine Paul states: \"our light "
        "affliction, which is but for a moment, worketh for us a far "
        "more exceeding and eternal weight of glory.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 122, 7, 7,
        "Romans", "Holy Bible", 5, 3, 4,
        "paraphrase", "trials-and-adversity",
        "A long list of possible afflictions ending \"know thou, my "
        "son, that all these things shall give thee experience\" "
        "matches Paul's own progression: \"tribulation worketh "
        "patience; and patience, experience; and experience, hope.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 68, 4, 4,
        "2 Peter", "Holy Bible", 1, 21, 21,
        "paraphrase", "revelation",
        "\"Whatsoever they shall speak when moved upon by the Holy "
        "Ghost shall be scripture\" restates Peter's own teaching: "
        "\"holy men of God spake as they were moved by the Holy "
        "Ghost.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 82, 3, 3,
        "Luke", "Holy Bible", 12, 48, 48,
        "quotation", "judgment",
        "\"Of him unto whom much is given much is required\" repeats "
        "Christ's own words almost verbatim: \"for unto whomsoever much "
        "is given, of him shall be much required.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 42, 61, 61,
        "Matthew", "Holy Bible", 7, 7, 7,
        "paraphrase", "prayer",
        "\"If thou shalt ask, thou shalt receive revelation upon "
        "revelation\" is the same promise Christ makes: \"ask, and it "
        "shall be given you; seek, and ye shall find.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 63, 63,
        "James", "Holy Bible", 4, 8, 8,
        "quotation", "prayer",
        "\"Draw near unto me and I will draw near unto you\" repeats "
        "James' own words nearly exactly: \"draw nigh to God, and he "
        "will draw nigh to you.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 67, 67,
        "Matthew", "Holy Bible", 6, 22, 22,
        "quotation", "discipleship",
        "\"If your eye be single to my glory, your whole bodies shall "
        "be filled with light\" repeats Christ's own teaching nearly "
        "word for word: \"if therefore thine eye be single, thy whole "
        "body shall be full of light.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 130, 22, 23,
        "Luke", "Holy Bible", 24, 39, 39,
        "paraphrase", "godhead",
        "\"The Father has a body of flesh and bones as tangible as "
        "man's; the Son also\" is illustrated directly by the risen "
        "Christ's own invitation: \"behold my hands and my feet, that "
        "it is I myself: handle me, and see; for a spirit hath not "
        "flesh and bones, as ye see me have.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 133, 52, 52,
        "Joel", "Holy Bible", 3, 16, 16,
        "paraphrase", "zion",
        "The Lord's redeemed people gathering to hear His voice matches "
        "Joel's own prophecy: \"the Lord also shall roar out of Zion, "
        "and utter his voice from Jerusalem.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 45, 71, 75,
        "Revelation", "Holy Bible", 21, 2, 2,
        "paraphrase", "zion",
        "\"The righteous shall be gathered out from among all nations, "
        "and shall come to Zion\" describes the same gathering John "
        "sees as \"the holy city, new Jerusalem, coming down from God "
        "out of heaven.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 1, 36, 36,
        "Isaiah", "Holy Bible", 34, 5, 5,
        "paraphrase", "judgment",
        "\"Shall come down in judgment upon Idumea, or the world\" "
        "names the very land - Idumea - Isaiah's own prophecy of "
        "judgment names: \"my sword shall be bathed in heaven... it "
        "shall come down upon Idumea.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 29, 1, 2,
        "Matthew", "Holy Bible", 23, 37, 37,
        "quotation", "jesus-christ",
        "\"Who will gather his people even as a hen gathereth her "
        "chickens under her wings\" repeats Christ's own lament over "
        "Jerusalem almost word for word.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 43, 24, 25,
        "Matthew", "Holy Bible", 23, 37, 37,
        "quotation", "jesus-christ",
        "A second instance of the same image within the Doctrine and "
        "Covenants: \"how often would I have gathered you together as "
        "a hen gathereth her chickens under her wings, but ye would "
        "not!\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 118, 119,
        "Proverbs", "Holy Bible", 4, 7, 7,
        "paraphrase", "wisdom",
        "\"Seek learning, even by study and also by faith\" teaches "
        "the same priority Proverbs states: \"wisdom is the principal "
        "thing; therefore get wisdom.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 131, 1, 4,
        "1 Corinthians", "Holy Bible", 11, 11, 11,
        "paraphrase", "marriage",
        "Marriage as a requirement for the highest degree of celestial "
        "glory matches Paul's own teaching that \"neither is the man "
        "without the woman, neither the woman without the man, in the "
        "Lord.\"",
    ),
    (
        "Abraham", "Pearl of Great Price", 3, 22, 23,
        "Jeremiah", "Holy Bible", 1, 5, 5,
        "paraphrase", "premortal-life",
        "\"God saw these souls that they were good, and he stood in "
        "the midst of them\" among the \"noble and great ones\" chosen "
        "before mortality matches Jeremiah's own account of being "
        "foreordained: \"before I formed thee in the belly I knew "
        "thee... I ordained thee a prophet.\"",
    ),
    (
        "Abraham", "Pearl of Great Price", 5, 7, 7,
        "Genesis", "Holy Bible", 2, 7, 7,
        "translation", "creation",
        "\"The Gods formed man from the dust of the ground... and man "
        "became a living soul\" restates Genesis' own account of "
        "Adam's creation almost word for word, a third telling "
        "alongside Moses 3 above.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 132, 19, 20,
        "Psalms", "Holy Bible", 82, 6, 6,
        "paraphrase", "exaltation",
        "The promise that the exalted \"shall be gods\" echoes the "
        "Psalm's own declaration, \"I have said, Ye are gods,\" which "
        "Christ Himself later quotes directly (see John 10:34 below).",
    ),
    (
        "John", "Holy Bible", 10, 34, 34,
        "Psalms", "Holy Bible", 82, 6, 6,
        "quotation", "exaltation",
        "Christ quotes this Psalm directly - \"is it not written in "
        "your law, I said, Ye are gods?\" - defending His own claim to "
        "divine sonship by appealing to what the Psalm already calls "
        "others.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 58, 26, 27,
        "Joshua", "Holy Bible", 24, 15, 15,
        "paraphrase", "agency",
        "\"It is not meet that I should command in all things\" - "
        "agency requiring a person's own willingness to act - is the "
        "same principle behind Joshua's own charge: \"choose you this "
        "day whom ye will serve.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 101, 78, 78,
        "Galatians", "Holy Bible", 5, 1, 1,
        "paraphrase", "agency",
        "\"The moral agency which I have given unto him\" as the basis "
        "for accountability matches Paul's own teaching on agency as "
        "liberty: \"stand fast therefore in the liberty wherewith "
        "Christ hath made us free.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 58, 42, 43,
        "Isaiah", "Holy Bible", 43, 25, 25,
        "paraphrase", "repentance",
        "\"He who has repented of his sins... I, the Lord, remember "
        "them no more\" restates Isaiah's own words spoken by the "
        "Lord: \"I, even I, am he that blotteth out thy transgressions "
        "for mine own sake, and will not remember thy sins\" - the "
        "same doctrine as D&C 58:42/Isaiah 1:18 above, from a "
        "different Isaiah chapter.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 121, 1, 3,
        "Psalms", "Holy Bible", 22, 1, 1,
        "paraphrase", "trials-and-adversity",
        "\"O God, where art thou?... How long shall thy hand be "
        "stayed\" is Joseph Smith's own cry from Liberty Jail, the same "
        "kind of anguished question David asks: \"my God, my God, why "
        "hast thou forsaken me?\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 45, 47,
        "Psalms", "Holy Bible", 19, 1, 1,
        "paraphrase", "creation",
        "The sun, moon, and stars described as bearing record of God's "
        "glory match the Psalm's own declaration: \"the heavens "
        "declare the glory of God; and the firmament sheweth his "
        "handywork.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 19, 21,
        "Acts", "Holy Bible", 7, 55, 56,
        "paraphrase", "jesus-christ",
        "\"We beheld the glory of the Son, on the right hand of the "
        "Father\" is the same vision Stephen describes at his own "
        "martyrdom: \"he saw the glory of God, and Jesus standing on "
        "the right hand of God.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 20, 17, 19,
        "John", "Holy Bible", 1, 3, 3,
        "paraphrase", "jesus-christ",
        "\"By him... all things were made\" restates John's own "
        "opening testimony of Christ almost word for word: \"all "
        "things were made by him; and without him was not any thing "
        "made that was made.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 45, 3, 5,
        "1 John", "Holy Bible", 2, 1, 1,
        "quotation", "atonement",
        "\"Listen to him who is the advocate with the Father, who is "
        "pleading your cause before him\" repeats John's own word for "
        "Christ almost exactly: \"if any man sin, we have an advocate "
        "with the Father, Jesus Christ the righteous.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 84, 54, 58,
        "Deuteronomy", "Holy Bible", 8, 11, 14,
        "paraphrase", "obedience",
        "A warning that unbelief and treating sacred things lightly "
        "brings the Church \"under condemnation\" matches Moses' own "
        "warning against forgetting God after being blessed: \"beware "
        "that thou forget not the Lord thy God... lest... thine heart "
        "be lifted up.\"",
    ),
    # --- Fork: OT prophetic books (Isaiah, Jeremiah, Lamentations,
    # Ezekiel, Daniel, Hosea through Malachi) ---
    (
        'Acts', 'Holy Bible', 8, 32, 35,
        'Isaiah', 'Holy Bible', 53, 7, 7,
        'quotation', 'jesus-christ',
        "\"He was led as a sheep to the slaughter\" - Philip explicitly reads "
        "this passage with the Ethiopian eunuch and \"began at the same "
        "scripture, and preached unto him Jesus,\" one of the clearest moments "
        "in the New Testament of Isaiah 53 being read as prophecy of Christ.",
    ),
    (
        '1 Peter', 'Holy Bible', 2, 24, 24,
        'Isaiah', 'Holy Bible', 53, 5, 5,
        'quotation', 'atonement',
        "\"He was wounded for our transgressions... with his stripes we are "
        "healed\" is quoted almost verbatim: \"who his own self bare our sins "
        "in his own body on the tree... by whose stripes ye were healed.\"",
    ),
    (
        'Luke', 'Holy Bible', 22, 37, 37,
        'Isaiah', 'Holy Bible', 53, 12, 12,
        'quotation', 'atonement',
        "\"He was numbered with the transgressors\" - Christ explicitly quotes "
        "this the night of His arrest: \"this that is written must yet be "
        "accomplished in me... he was reckoned among the transgressors.\"",
    ),
    (
        'Matthew', 'Holy Bible', 27, 57, 60,
        'Isaiah', 'Holy Bible', 53, 9, 9,
        'paraphrase', 'atonement',
        "\"He made his grave with the wicked, and with the rich in his death\" "
        "- fulfilled when a rich man, Joseph of Arimathaea, laid Christ's "
        "body in his own tomb.",
    ),
    (
        'Matthew', 'Holy Bible', 15, 8, 9,
        'Isaiah', 'Holy Bible', 29, 13, 13,
        'quotation', 'truth',
        "\"This people draweth nigh unto me with their mouth... but their "
        "heart is far from me\" - Christ quotes Isaiah directly to condemn "
        "worship that is outwardly correct but inwardly empty.",
    ),
    (
        'Revelation', 'Holy Bible', 1, 17, 17,
        'Isaiah', 'Holy Bible', 44, 6, 6,
        'paraphrase', 'jesus-christ',
        "\"I am the first, and I am the last; and beside me there is no God\" "
        "is the very title Christ takes for Himself in John's vision: \"Fear "
        "not; I am the first and the last.\"",
    ),
    (
        'Revelation', 'Holy Bible', 21, 1, 1,
        'Isaiah', 'Holy Bible', 65, 17, 17,
        'paraphrase', 'second-coming',
        "\"I create new heavens and a new earth\" and \"I saw a new heaven and a "
        "new earth: for the first heaven and the first earth were passed "
        "away\" describe the same final renewal, Isaiah's promise and John's "
        "vision of its fulfillment.",
    ),
    (
        'Revelation', 'Holy Bible', 21, 23, 23,
        'Isaiah', 'Holy Bible', 60, 19, 20,
        'paraphrase', 'second-coming',
        "\"The Lord shall be unto thee an everlasting light\" and \"the city had "
        "no need of the sun... for the glory of God did lighten it, and the "
        "Lamb is the light thereof\" describe the same Millennial city, lit by "
        "God's own presence rather than the sun.",
    ),
    (
        'Revelation', 'Holy Bible', 3, 7, 7,
        'Isaiah', 'Holy Bible', 22, 22, 22,
        'quotation', 'jesus-christ',
        "\"The key of the house of David... he shall open, and none shall "
        "shut\" is quoted directly by the risen Christ: \"he that hath the key "
        "of David, he that openeth, and no man shutteth.\"",
    ),
    (
        'Matthew', 'Holy Bible', 2, 17, 18,
        'Jeremiah', 'Holy Bible', 31, 15, 15,
        'quotation', 'jesus-christ',
        "\"Rahel weeping for her children\" is quoted directly as fulfilled at "
        "the slaughter of the innocents in Bethlehem: \"in Rama was there a "
        "voice heard, lamentation, and weeping... Rachel weeping for her "
        "children.\"",
    ),
    (
        '2 Nephi', 'The Book of Mormon', 3, 12, 12,
        'Ezekiel', 'Holy Bible', 37, 15, 19,
        'paraphrase', 'house-of-israel',
        "Ezekiel's two sticks - one for Judah, one for Joseph - joined into "
        "one in the Lord's hand is the same promise Lehi gives Joseph: \"the "
        "fruit of thy loins shall write; and the fruit of the loins of Judah "
        "shall write... and they shall grow together.\"",
    ),
    (
        'Articles of Faith', 'Pearl of Great Price', 1, 2, 2,
        'Ezekiel', 'Holy Bible', 18, 20, 20,
        'paraphrase', 'judgment',
        "\"The soul that sinneth, it shall die. The son shall not bear the "
        "iniquity of the father\" is the same doctrine of individual "
        "accountability the Articles of Faith state plainly: \"men will be "
        "punished for their own sins, and not for Adam's transgression.\"",
    ),
    (
        'Jacob', 'The Book of Mormon', 1, 19, 19,
        'Ezekiel', 'Holy Bible', 3, 17, 19,
        'paraphrase', 'prophets',
        "Ezekiel is made \"a watchman unto the house of Israel,\" warned that a "
        "sinner's blood is required at his hand if he fails to warn them - "
        "the same responsibility Jacob describes: \"answering the sins of the "
        "people upon our own heads if we did not teach them the word of God.\"",
    ),
    (
        'Matthew', 'Holy Bible', 26, 64, 64,
        'Daniel', 'Holy Bible', 7, 13, 14,
        'quotation', 'jesus-christ',
        "\"One like the Son of man came with the clouds of heaven\" is the very "
        "title and image Christ applies to Himself before the high priest: "
        "\"hereafter shall ye see the Son of man... coming in the clouds of "
        "heaven.\"",
    ),
    (
        'John', 'Holy Bible', 5, 28, 29,
        'Daniel', 'Holy Bible', 12, 2, 2,
        'paraphrase', 'resurrection',
        "\"Many of them that sleep in the dust of the earth shall awake, some "
        "to everlasting life, and some to shame\" is echoed almost exactly by "
        "Christ Himself: \"they that have done good, unto the resurrection of "
        "life; and they that have done evil, unto the resurrection of "
        "damnation.\"",
    ),
    (
        '1 Corinthians', 'Holy Bible', 15, 4, 4,
        'Hosea', 'Holy Bible', 6, 2, 2,
        'paraphrase', 'resurrection',
        "\"In the third day he will raise us up\" is widely read as one of the "
        "prophetic scriptures Paul has in mind when he writes that Christ "
        "\"rose again the third day according to the scriptures.\"",
    ),
    (
        '1 Nephi', 'The Book of Mormon', 13, 29, 29,
        'Amos', 'Holy Bible', 8, 11, 11,
        'paraphrase', 'restoration',
        "\"A famine... of hearing the words of the Lord\" is the same loss "
        "Nephi's vision describes - \"many plain and precious things taken "
        "away\" from the Gentiles' record of the gospel - both naming a real "
        "spiritual famine, not merely a literal one.",
    ),
    (
        'Isaiah', 'Holy Bible', 2, 2, 3,
        'Micah', 'Holy Bible', 4, 1, 2,
        'quotation', 'zion',
        "Micah records the very same prophecy, in nearly the same words, as "
        "Isaiah: \"the mountain of the house of the Lord shall be established "
        "in the top of the mountains... and all nations shall flow unto it\" - "
        "two prophets bearing identical witness.",
    ),
    (
        'Jude', 'Holy Bible', 1, 9, 9,
        'Zechariah', 'Holy Bible', 3, 1, 2,
        'quotation', 'agency',
        "\"The Lord rebuke thee, O Satan\" is quoted directly by Jude, "
        "describing Michael's own dispute with the devil - the same rebuke "
        "first recorded in Zechariah's vision of Joshua the high priest.",
    ),
    (
        'Acts', 'Holy Bible', 1, 11, 12,
        'Zechariah', 'Holy Bible', 14, 4, 4,
        'paraphrase', 'second-coming',
        "\"His feet shall stand in that day upon the mount of Olives\" - the "
        "same mountain Christ ascended from at His departure, where angels "
        "promise \"this same Jesus... shall so come in like manner as ye have "
        "seen him go into heaven.\"",
    ),
    (
        'Mormon', 'The Book of Mormon', 9, 9, 9,
        'Malachi', 'Holy Bible', 3, 6, 6,
        'paraphrase', 'godhead',
        "\"I am the Lord, I change not\" is the same doctrine Mormon later "
        "teaches: \"God is the same yesterday, today, and forever, and in him "
        "there is no variableness neither shadow of changing.\"",
    ),
    (
        'Mosiah', 'The Book of Mormon', 4, 6, 6,
        'Lamentations', 'Holy Bible', 3, 22, 23,
        'paraphrase', 'gratitude',
        "\"It is of the Lord's mercies that we are not consumed... they are "
        "new every morning\" and \"if ye have come to a knowledge of the "
        "goodness of God, and his matchless power, and his wisdom, and his "
        "patience\" both anchor gratitude in God's own unfailing, daily mercy.",
    ),
    (
        'Mosiah', 'The Book of Mormon', 3, 5, 5,
        'Isaiah', 'Holy Bible', 9, 6, 6,
        'paraphrase', 'jesus-christ',
        "\"Unto us a child is born... his name shall be called... The mighty "
        "God\" is echoed in King Benjamin's own prophecy: \"the Lord Omnipotent "
        "who reigneth, who was, and is from all eternity to all eternity, "
        "shall come down.\"",
    ),
    (
        '3 Nephi', 'The Book of Mormon', 11, 10, 10,
        'Isaiah', 'Holy Bible', 9, 6, 6,
        'paraphrase', 'jesus-christ',
        "Isaiah's child \"whose name shall be called Wonderful\" identifies "
        "Himself directly to the Nephites: \"Behold, I am Jesus Christ, whom "
        "the prophets testified shall come into the world.\"",
    ),
    (
        '1 Nephi', 'The Book of Mormon', 14, 14, 14,
        'Isaiah', 'Holy Bible', 29, 14, 14,
        'paraphrase', 'restoration',
        "\"A marvellous work and a wonder\" - the very phrase Nephi's own "
        "vision uses for the latter-day work: \"the power of the Lamb of "
        "God... descended upon the saints of the church of the Lamb.\"",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 110, 3, 4,
        'Isaiah', 'Holy Bible', 40, 5, 5,
        'paraphrase', 'second-coming',
        "\"The glory of the Lord shall be revealed, and all flesh shall see it "
        "together\" - a foretaste of that glory appears already in the "
        "Kirtland Temple: \"his eyes were as a flame of fire... his voice as "
        "the sound of the rushing of great waters.\"",
    ),
    (
        'Matthew', 'Holy Bible', 18, 2, 4,
        'Isaiah', 'Holy Bible', 11, 6, 9,
        'paraphrase', 'humility',
        "The peaceable kingdom where \"a little child shall lead them\" matches "
        "Christ's own teaching that only those who \"become as little "
        "children\" can enter His kingdom - childlike humility as the "
        "condition of peace in both texts.",
    ),
    (
        'Mosiah', 'The Book of Mormon', 4, 26, 26,
        'Isaiah', 'Holy Bible', 58, 6, 7,
        'paraphrase', 'service',
        "\"Is not this the fast that I have chosen... to let the oppressed go "
        "free\" and \"impart of your substance to the poor... administer to "
        "their relief\" both teach that true worship is measured by concrete "
        "care for the needy, not ritual alone.",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 93, 40, 40,
        'Isaiah', 'Holy Bible', 54, 13, 13,
        'paraphrase', 'children',
        "\"All thy children shall be taught of the Lord\" is the same promise "
        "behind the commandment \"to bring up your children in light and "
        "truth\" above.",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 90, 24, 24,
        'Isaiah', 'Holy Bible', 55, 9, 9,
        'paraphrase', 'truth',
        "\"As the heavens are higher than the earth, so are my ways higher "
        "than your ways\" is the same trust behind the promise \"all things "
        "shall work together for your good, if ye walk uprightly.\"",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 138, 55, 56,
        'Jeremiah', 'Holy Bible', 1, 5, 5,
        'paraphrase', 'premortal-life',
        "Jeremiah's own foreordination as a prophet \"before thou camest forth "
        "out of the womb\" is the same doctrine this vision describes more "
        "broadly: spirits \"chosen... to be rulers in the Church of God\" even "
        "\"before they were born.\"",
    ),
    (
        'Alma', 'The Book of Mormon', 13, 3, 3,
        'Jeremiah', 'Holy Bible', 1, 5, 5,
        'paraphrase', 'premortal-life',
        "Alma teaches the identical doctrine Jeremiah's own call illustrates "
        "- priests \"called and prepared from the foundation of the world "
        "according to the foreknowledge of God.\"",
    ),
    (
        'Alma', 'The Book of Mormon', 7, 11, 12,
        'Isaiah', 'Holy Bible', 53, 4, 4,
        'paraphrase', 'atonement',
        "\"Surely he hath borne our griefs, and carried our sorrows\" is the "
        "same prophecy Alma quotes directly in teaching the Atonement: \"this "
        "that the word might be fulfilled which saith he will take upon "
        "him... the pains and the sicknesses of his people.\"",
    ),
    (
        'Malachi', 'Holy Bible', 3, 10, 10,
        'Genesis', 'Holy Bible', 14, 20, 20,
        'paraphrase', 'tithing',
        "Abram's tithe to Melchizedek - \"he gave him tithes of all\" - is "
        "scripture's first recorded example of the very law Malachi later "
        "commands and promises to bless.",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 1, 30, 30,
        'Daniel', 'Holy Bible', 2, 44, 45,
        'paraphrase', 'restoration',
        "Daniel's kingdom \"which shall never be destroyed\" is identified in "
        "modern revelation as \"the only true and living church upon the face "
        "of the whole earth,\" brought forth \"out of obscurity and out of "
        "darkness.\"",
    ),
    (
        '2 Nephi', 'The Book of Mormon', 9, 14, 14,
        'Isaiah', 'Holy Bible', 61, 10, 10,
        'paraphrase', 'salvation',
        "\"He hath clothed me with the garments of salvation, he hath covered "
        "me with the robe of righteousness\" is the same image Jacob uses for "
        "the righteous at the judgment: a \"perfect knowledge of their "
        "enjoyment\" and \"purity.\"",
    ),
    (
        'Jeremiah', 'Holy Bible', 18, 6, 6,
        'Isaiah', 'Holy Bible', 64, 8, 8,
        'paraphrase', 'humility',
        "\"We are the clay, and thou our potter\" and \"as the clay is in the "
        "potter's hand, so are ye in mine hand\" both use the same image, from "
        "two different prophets, to teach submission to God's shaping hand.",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 1, 12, 13,
        'Zephaniah', 'Holy Bible', 1, 14, 15,
        'paraphrase', 'second-coming',
        "\"The great day of the Lord is near, it is near, and hasteth greatly\" "
        "is echoed in modern revelation's own warning: \"prepare ye, prepare "
        "ye for that which is to come, for the Lord is nigh.\"",
    ),
    (
        'Revelation', 'Holy Bible', 11, 15, 15,
        'Obadiah', 'Holy Bible', 1, 21, 21,
        'paraphrase', 'second-coming',
        "\"The kingdom shall be the Lord's\" is the same final sovereignty "
        "John's vision announces: \"the kingdoms of this world are become the "
        "kingdoms of our Lord, and of his Christ.\"",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 84, 98, 98,
        'Habakkuk', 'Holy Bible', 2, 14, 14,
        'quotation', 'missionary-work',
        "\"The earth shall be filled with the knowledge of the glory of the "
        "Lord, as the waters cover the sea\" is quoted almost word for word in "
        "this modern revelation's own promise that all shall \"be filled with "
        "the knowledge of the Lord.\"",
    ),
    (
        '1 Peter', 'Holy Bible', 2, 25, 25,
        'Isaiah', 'Holy Bible', 53, 6, 6,
        'paraphrase', 'atonement',
        "\"All we like sheep have gone astray... the Lord hath laid on him the "
        "iniquity of us all\" is echoed directly: \"ye were as sheep going "
        "astray; but are now returned unto the Shepherd and Bishop of your "
        "souls.\"",
    ),
    (
        'Alma', 'The Book of Mormon', 5, 37, 39,
        'Ezekiel', 'Holy Bible', 34, 2, 4,
        'paraphrase', 'jesus-christ',
        "Ezekiel condemns shepherds who fail to feed the flock and let it be "
        "scattered; Alma asks his own people the identical question - whether "
        "they are \"a shepherd\" who watches over the flock \"or a hireling\" who "
        "lets it be led away.",
    ),
    (
        'Abraham', 'Pearl of Great Price', 3, 27, 27,
        'Isaiah', 'Holy Bible', 6, 8, 8,
        'quotation', 'premortal-life',
        "\"Whom shall I send, and who will go for us?... Here am I; send me\" - "
        "the very words Isaiah records in his own call vision are given "
        "again, in the same form, in the premortal council Abraham is shown.",
    ),
    (
        'Articles of Faith', 'Pearl of Great Price', 1, 9, 9,
        'Amos', 'Holy Bible', 3, 7, 7,
        'paraphrase', 'revelation',
        "\"Surely the Lord God will do nothing, but he revealeth his secret "
        "unto his servants the prophets\" is the same principle of continuing "
        "revelation the Articles of Faith affirm: God \"will yet reveal many "
        "great and important things.\"",
    ),
    (
        'Luke', 'Holy Bible', 2, 32, 32,
        'Isaiah', 'Holy Bible', 42, 6, 6,
        'paraphrase', 'jesus-christ',
        "\"A covenant of the people, for a light of the Gentiles\" is the same "
        "title Simeon gives the infant Christ: \"a light to lighten the "
        "Gentiles, and the glory of thy people Israel.\"",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 59, 8, 8,
        'Micah', 'Holy Bible', 6, 6, 8,
        'paraphrase', 'sacrifice',
        "\"What doth the Lord require of thee, but to do justly, and to love "
        "mercy\" - not burnt offerings - is the same shift in modern "
        "revelation's own sacrifice: \"a broken heart and a contrite spirit,\" "
        "not an animal offering.",
    ),
    (
        'Romans', 'Holy Bible', 10, 13, 13,
        'Joel', 'Holy Bible', 2, 32, 32,
        'quotation', 'salvation',
        "\"Whosoever shall call on the name of the Lord shall be delivered\" is "
        "quoted directly by Paul: \"whosoever shall call upon the name of the "
        "Lord shall be saved.\"",
    ),
    (
        'James', 'Holy Bible', 1, 27, 27,
        'Isaiah', 'Holy Bible', 1, 17, 17,
        'paraphrase', 'service',
        "\"Relieve the oppressed, judge the fatherless, plead for the widow\" "
        "and \"pure religion... is this, To visit the fatherless and widows in "
        "their affliction\" both define true devotion to God by care for the "
        "vulnerable.",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 1, 19, 19,
        'Zechariah', 'Holy Bible', 4, 6, 6,
        'paraphrase', 'humility',
        "\"Not by might, nor by power, but by my spirit\" is the same principle "
        "behind modern revelation's own promise that \"the weak things of the "
        "world shall come forth and break down the mighty and strong ones.\"",
    ),
    (
        'Mosiah', 'The Book of Mormon', 26, 30, 30,
        'Isaiah', 'Holy Bible', 43, 25, 25,
        'paraphrase', 'forgiveness',
        "\"I, even I, am he that blotteth out thy transgressions... and will "
        "not remember thy sins\" is the same promise the Lord gives Alma: \"as "
        "often as my people repent will I forgive them their trespasses.\"",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 49, 24, 25,
        'Isaiah', 'Holy Bible', 35, 1, 1,
        'paraphrase', 'restoration',
        "\"The desert shall rejoice, and blossom as the rose\" is quoted in "
        "nearly the same words in modern revelation's own promise of the "
        "latter-day gathering: \"the Lamanites shall blossom as the rose.\"",
    ),
    (
        'Acts', 'Holy Bible', 7, 49, 49,
        'Isaiah', 'Holy Bible', 66, 1, 1,
        'quotation', 'reverence',
        "\"Heaven is my throne, and the earth is my footstool: where is the "
        "house that ye build unto me?\" is quoted directly by Stephen to teach "
        "that God cannot be confined to any temple built by human hands.",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 88, 63, 63,
        'Jeremiah', 'Holy Bible', 29, 13, 13,
        'paraphrase', 'prayer',
        "\"Ye shall seek me, and find me, when ye shall search for me with all "
        "your heart\" is echoed almost exactly: \"draw near unto me and I will "
        "draw near unto you; seek me diligently and ye shall find me.\"",
    ),
    (
        'Mosiah', 'The Book of Mormon', 17, 9, 10,
        'Daniel', 'Holy Bible', 3, 17, 18,
        'paraphrase', 'faith',
        "Shadrach, Meshach, and Abednego's faith regardless of outcome - \"if "
        "not... we will not serve thy gods\" - is the same steadfastness "
        "Abinadi shows facing death: \"I will not recall the words which I "
        "have spoken... for they are true.\"",
    ),
    (
        'Moroni', 'The Book of Mormon', 7, 14, 17,
        'Isaiah', 'Holy Bible', 5, 20, 20,
        'paraphrase', 'truth',
        "\"Woe unto them that call evil good, and good evil\" is the same "
        "warning Moroni gives about discerning good from evil: \"take heed... "
        "that ye do not judge that which is evil to be of God, or that which "
        "is good and of God to be of the devil.\"",
    ),
    (
        'Revelation', 'Holy Bible', 2, 17, 17,
        'Isaiah', 'Holy Bible', 62, 2, 2,
        'paraphrase', 'covenants',
        "\"Thou shalt be called by a new name, which the mouth of the Lord "
        "shall name\" is echoed in John's own vision of Christ's promise: \"to "
        "him that overcometh will I give... a new name written, which no man "
        "knoweth.\"",
    ),
    (
        'Alma', 'The Book of Mormon', 40, 3, 4,
        'Isaiah', 'Holy Bible', 26, 19, 19,
        'paraphrase', 'resurrection',
        "\"Thy dead men shall live, together with my dead body shall they "
        "arise\" anticipates the same resurrection Alma teaches his son - "
        "though, as Alma cautions, \"the resurrection is not yet\" in full for "
        "all.",
    ),
    (
        'Mosiah', 'The Book of Mormon', 5, 2, 2,
        'Ezekiel', 'Holy Bible', 36, 26, 26,
        'paraphrase', 'repentance',
        "\"A new heart also will I give you... I will take away the stony "
        "heart\" is the same change King Benjamin's people describe "
        "experiencing: \"we have no more disposition to do evil, but to do "
        "good continually.\"",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 89, 20, 20,
        'Isaiah', 'Holy Bible', 40, 31, 31,
        'quotation', 'word-of-wisdom',
        "\"They shall run, and not be weary; and they shall walk, and not "
        "faint\" is repeated almost word for word as the Word of Wisdom's own "
        "promise: \"shall run and not be weary, and shall walk and not faint.\"",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 68, 6, 6,
        'Isaiah', 'Holy Bible', 41, 10, 10,
        'paraphrase', 'faith',
        "\"Fear thou not; for I am with thee... I will strengthen thee\" is the "
        "same promise of divine companionship given to those the Lord sends: "
        "\"be of good cheer, and do not fear, for I the Lord am with you, and "
        "will stand by you.\"",
    ),
    (
        '1 Peter', 'Holy Bible', 5, 2, 4,
        'Isaiah', 'Holy Bible', 40, 11, 11,
        'paraphrase', 'service',
        "\"He shall feed his flock like a shepherd... and gently lead those "
        "that are with young\" is the same pastoral care Peter asks of every "
        "under-shepherd: \"feed the flock of God which is among you, taking "
        "the oversight thereof... willingly.\"",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 113, 5, 6,
        'Ezekiel', 'Holy Bible', 37, 11, 14,
        'paraphrase', 'house-of-israel',
        "Ezekiel's dry bones - \"these bones are the whole house of Israel\" - "
        "restored and brought \"into the land of Israel,\" is the same latter- "
        "day gathering this revelation identifies as the work of a descendant "
        "of Jesse and Joseph holding \"the keys of the kingdom.\"",
    ),
    (
        '1 Peter', 'Holy Bible', 1, 7, 7,
        'Isaiah', 'Holy Bible', 48, 10, 10,
        'paraphrase', 'trials-and-adversity',
        "\"I have refined thee... in the furnace of affliction\" is the same "
        "purpose behind trials Peter describes: \"the trial of your faith, "
        "being much more precious than of gold that perisheth, though it be "
        "tried with fire.\"",
    ),
    (
        'Matthew', 'Holy Bible', 4, 16, 16,
        'Isaiah', 'Holy Bible', 9, 2, 2,
        'quotation', 'jesus-christ',
        "\"The people that walked in darkness have seen a great light\" is "
        "quoted directly of Christ beginning His Galilean ministry: \"the "
        "people which sat in darkness saw great light.\"",
    ),
    (
        'Mosiah', 'The Book of Mormon', 15, 10, 10,
        'Isaiah', 'Holy Bible', 53, 10, 10,
        'quotation', 'atonement',
        "\"When thou shalt make his soul an offering for sin, he shall see his "
        "seed\" is quoted directly by Abinadi in his own exposition of "
        "Isaiah's suffering-servant prophecy: \"when his soul has been made an "
        "offering for sin he shall see his seed.\"",
    ),
    (
        'Enos', 'The Book of Mormon', 1, 6, 6,
        'Micah', 'Holy Bible', 7, 18, 19,
        'paraphrase', 'forgiveness',
        "\"He retaineth not his anger for ever... he will cast all their sins "
        "into the depths of the sea\" is the same complete forgiveness Enos "
        "experiences directly: \"I, Enos, knew that God could not lie; "
        "wherefore, my guilt was swept away.\"",
    ),
    (
        '1 Thessalonians', 'Holy Bible', 1, 9, 9,
        'Jeremiah', 'Holy Bible', 10, 10, 10,
        'paraphrase', 'godhead',
        "\"The Lord is the true God, he is the living God\" is echoed in the "
        "same distinctive phrase Paul uses to describe conversion: turning "
        "\"from idols to serve the living and true God.\"",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 97, 15, 16,
        'Habakkuk', 'Holy Bible', 2, 20, 20,
        'paraphrase', 'temple',
        "\"The Lord is in his holy temple: let all the earth keep silence "
        "before him\" is the same reverence modern revelation asks of a temple "
        "built to the Lord, that His \"glory shall rest upon it\" and \"presence "
        "shall be there.\"",
    ),
    (
        'Doctrine and Covenants', 'Doctrine and Covenants', 19, 16, 19,
        'Zechariah', 'Holy Bible', 13, 1, 1,
        'paraphrase', 'atonement',
        "\"A fountain opened to the house of David... for sin and for "
        "uncleanness\" is the same cleansing Christ Himself explains He "
        "purchased through suffering: \"I, God, have suffered these things for "
        "all, that they might not suffer if they would repent.\"",
    ),
    # --- Fork: exhaustive citation mining + knowledge-based sweep ---
    (
        "John", "Holy Bible", 2, 17, 17,
        "Psalms", "Holy Bible", 69, 9, 9,
        "quotation", "jesus-christ",
        "\"The zeal of thine house hath eaten me up\" - John explicitly notes the disciples remembered this psalm as Christ drove the money-changers from the temple.",
    ),
    (
        "Acts", "Holy Bible", 1, 20, 20,
        "Psalms", "Holy Bible", 109, 8, 8,
        "quotation", "prophets",
        "Peter quotes this psalm directly - \"let another take his office\" - as scriptural warrant for replacing Judas among the Twelve.",
    ),
    (
        "Mosiah", "The Book of Mormon", 27, 24, 29,
        "John", "Holy Bible", 3, 3, 5,
        "paraphrase", "repentance",
        "Alma the younger's own testimony - \"I am born of the Spirit\" - is the same doctrine Christ teaches Nicodemus: \"except a man be born again, he cannot see the kingdom of God.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 42, 22, 22,
        "Ephesians", "Holy Bible", 5, 25, 25,
        "paraphrase", "marriage",
        "\"Thou shalt love thy wife with all thy heart\" and \"husbands, love your wives, even as Christ also loved the church\" both make a husband's love the measure of the marriage covenant.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 11, 14, 15,
        "Zechariah", "Holy Bible", 13, 6, 6,
        "typology", "atonement",
        "\"What are these wounds in thine hands?\" is answered centuries later when the risen Christ has the Nephites \"feel the prints of the nails\" in His own hands and feet.",
    ),
    (
        "Enos", "The Book of Mormon", 1, 1, 2,
        "Genesis", "Holy Bible", 32, 24, 30,
        "paraphrase", "prayer",
        "Enos uses the same distinctive word as Jacob's own night at Peniel: \"I will tell you of the wrestle which I had before God, before I received a remission of my sins\" - prayer as an actual wrestle, not a quick request.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 132, 7, 7,
        "Matthew", "Holy Bible", 16, 19, 19,
        "paraphrase", "priesthood",
        "\"All covenants... that are not made... by him who is anointed\" echoes Christ's own promise of binding and loosing keys - \"whatsoever thou shalt bind on earth shall be bound in heaven.\"",
    ),
    (
        "Alma", "The Book of Mormon", 32, 28, 30,
        "Luke", "Holy Bible", 17, 6, 6,
        "paraphrase", "faith",
        "Alma's seed of faith, planted and nourished until it grows, and Christ's \"faith as a grain of mustard seed\" both use the same small-seed image for how little faith is needed to begin.",
    ),
    (
        "Mosiah", "The Book of Mormon", 5, 2, 2,
        "Psalms", "Holy Bible", 51, 10, 10,
        "paraphrase", "repentance",
        "\"Create in me a clean heart, O God\" is David's own request for the same \"mighty change\" King Benjamin's people had already received.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 4, 34, 34,
        "Proverbs", "Holy Bible", 3, 5, 6,
        "paraphrase", "faith",
        "\"Trust in the Lord with all thine heart; and lean not unto thine own understanding\" and Nephi's own \"I will not put my trust in the arm of flesh\" both set trusting God against relying on oneself.",
    ),
    (
        "John", "Holy Bible", 1, 29, 29,
        "Genesis", "Holy Bible", 22, 8, 8,
        "typology", "atonement",
        "\"God will provide himself a lamb\" - Abraham's own words before offering Isaac - are fulfilled when John the Baptist declares of Christ, \"Behold the Lamb of God, which taketh away the sin of the world.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 105, 14, 14,
        "1 Samuel", "Holy Bible", 17, 47, 47,
        "paraphrase", "faith",
        "\"The battle is the Lord's\" - David's own confidence facing Goliath - matches this revelation's promise: \"I do not require at their hands to fight the battles of Zion... I will fight your battles.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 97, 21, 21,
        "Psalms", "Holy Bible", 24, 3, 4,
        "paraphrase", "zion",
        "\"Who shall stand in his holy place? He that hath clean hands, and a pure heart\" is the same standard this revelation names outright: \"Zion - the pure in heart.\"",
    ),
    (
        "Ether", "The Book of Mormon", 2, 15, 15,
        "Genesis", "Holy Bible", 6, 3, 3,
        "quotation", "repentance",
        "\"My Spirit will not always strive with man\" - the Lord's warning before the Flood - is repeated nearly word for word to the brother of Jared as a warning of the same danger.",
    ),
    (
        "Matthew", "Holy Bible", 9, 13, 13,
        "Hosea", "Holy Bible", 6, 6, 6,
        "quotation", "repentance",
        "\"I will have mercy, and not sacrifice\" - Christ quotes Hosea directly to explain why He eats with sinners rather than the outwardly righteous.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 22, 24,
        "Job", "Holy Bible", 42, 5, 5,
        "paraphrase", "testimony",
        "\"I have heard of thee by the hearing of the ear: but now mine eye seeth thee\" is Job's own move from secondhand belief to firsthand knowledge - the same shift this vision's own testimony describes: \"that he lives! For we saw him.\"",
    ),
    (
        "Moses", "Pearl of Great Price", 1, 3, 3,
        "Psalms", "Holy Bible", 90, 2, 2,
        "paraphrase", "godhead",
        "\"From everlasting to everlasting, thou art God\" and \"I am without beginning of days or end of years\" both testify of God's own eternal, unbeginning existence.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 101, 26, 26,
        "Isaiah", "Holy Bible", 11, 6, 9,
        "paraphrase", "peace",
        "\"The wolf also shall dwell with the lamb\" is Isaiah's own image for the Millennium's peace; this revelation states the same promise plainly: \"the enmity of man, and the enmity of beasts... shall cease.\"",
    ),
    (
        "Revelation", "Holy Bible", 10, 9, 10,
        "Ezekiel", "Holy Bible", 3, 1, 3,
        "typology", "revelation",
        "Both prophets are commanded to eat a book or roll before delivering its message - Ezekiel finds it \"in my mouth as honey for sweetness\"; John finds his \"sweet as honey,\" but \"bitter\" once received.",
    ),
    (
        "Ether", "The Book of Mormon", 3, 12, 12,
        "Numbers", "Holy Bible", 23, 19, 19,
        "paraphrase", "truth",
        "\"God is not a man, that he should lie\" and the brother of Jared's own testimony - \"thou art a God of truth, and canst not lie\" - both ground faith in God's own incapacity to deceive.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 4, 35, 35,
        "2 Samuel", "Holy Bible", 22, 2, 3,
        "paraphrase", "faith",
        "David's \"the Lord is my rock, and my fortress\" and Nephi's own psalm - \"I will cry unto thee, my God, the rock of my righteousness\" - both use the same image of God as an unshakeable refuge.",
    ),
    (
        "Moses", "Pearl of Great Price", 1, 10, 10,
        "Psalms", "Holy Bible", 8, 3, 4,
        "paraphrase", "humility",
        "\"What is man, that thou art mindful of him?\" and Moses' own reaction after beholding God's creations - \"now, for this cause I know that man is nothing\" - both teach humility before the vastness of God's works.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 132, 30, 30,
        "Genesis", "Holy Bible", 17, 5, 5,
        "paraphrase", "covenants",
        "\"Thy name shall be... Abraham; for a father of many nations have I made thee\" is the same covenant this revelation recalls, still being fulfilled through Abraham's seed.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 1, 38, 38,
        "Isaiah", "Holy Bible", 55, 11, 11,
        "quotation", "word-of-god",
        "\"My word... shall not return unto me void, but it shall accomplish that which I please\" is the same assurance this revelation gives of the Lord's own spoken word.",
    ),
    (
        "Moses", "Pearl of Great Price", 6, 31, 32,
        "Exodus", "Holy Bible", 4, 10, 12,
        "paraphrase", "prophets",
        "Enoch's own self-doubt at his calling - \"I am but a lad, and all the people hate me\" - echoes Moses' \"I am not eloquent... I am slow of speech\" - the same reluctance the Lord answers in both.",
    ),
    # --- Fork: second manual pass ---
    (
        "1 Corinthians", "Holy Bible", 2, 8, 8,
        "Psalms", "Holy Bible", 24, 7, 10,
        "paraphrase", "jesus-christ",
        "\"The King of glory\" and \"the Lord of glory\" are the same "
        "divine title - one anticipating Christ's triumphal reception "
        "in heaven, the other naming Him crucified by rulers who "
        "\"knew not\" they were crucifying the very King of glory.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 9, 20, 20,
        "Psalms", "Holy Bible", 51, 17, 17,
        "quotation", "repentance",
        "\"A broken and a contrite heart\" - Christ's own words to the "
        "Nephites echo David's psalm of repentance almost verbatim, "
        "now naming that broken heart itself as the true sacrifice He "
        "requires.",
    ),
    (
        "Moses", "Pearl of Great Price", 1, 3, 4,
        "Psalms", "Holy Bible", 90, 1, 2,
        "paraphrase", "godhead",
        "\"From everlasting to everlasting, thou art God\" and \"I "
        "am... without beginning of days or end of years\" both "
        "testify of God's eternal, timeless nature.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 41, 41,
        "Psalms", "Holy Bible", 139, 7, 10,
        "paraphrase", "godhead",
        "\"Whither shall I go from thy spirit?\" and \"he comprehendeth "
        "all things... is in all things\" both teach the same doctrine "
        "of God's presence filling and reaching all creation.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 61, 36, 36,
        "Isaiah", "Holy Bible", 43, 1, 2,
        "paraphrase", "faith",
        "\"When thou passest through the waters, I will be with thee\" "
        "is the same divine companionship promised directly to the "
        "elders literally crossing a river: \"I am in your midst, and "
        "I have not forsaken you.\"",
    ),
    (
        "Hebrews", "Holy Bible", 11, 3, 3,
        "Psalms", "Holy Bible", 33, 6, 9,
        "quotation", "faith",
        "\"By the word of the Lord were the heavens made\" is the same "
        "truth Paul teaches by faith: \"the worlds were framed by the "
        "word of God, so that things which are seen were not made of "
        "things which do appear.\"",
    ),
    (
        "2 Nephi", "The Book of Mormon", 4, 34, 34,
        "Psalms", "Holy Bible", 146, 3, 4,
        "paraphrase", "faith",
        "\"Put not your trust in princes, nor in the son of man\" and "
        "\"I will not put my trust in the arm of flesh\" both warn "
        "against trusting mortal power in place of God.",
    ),
    (
        "Ephesians", "Holy Bible", 2, 8, 10,
        "2 Nephi", "The Book of Mormon", 25, 23, 23,
        "paraphrase", "grace",
        "\"By grace are ye saved through faith... not of works\" and "
        "\"it is by grace that we are saved, after all we can do\" are "
        "two of scripture's clearest single-passage statements that "
        "salvation is a gift, not something fully earned.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 17, 24, 24,
        "Helaman", "The Book of Mormon", 5, 43, 45,
        "paraphrase", "jesus-christ",
        "Both describe people \"encircled about as if by fire\" from "
        "heaven - Nephi and Lehi in a Lamanite prison, and the Nephite "
        "children surrounded by angels at Christ's own visit - the "
        "same divine manifestation, decades apart.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 76, 22, 24,
        "1 Corinthians", "Holy Bible", 15, 5, 8,
        "paraphrase", "testimony",
        "Both give a list of witnesses testifying that the resurrected "
        "Christ was seen and known directly - Paul's catalogue of "
        "those Christ appeared to, and \"the testimony, last of all\" "
        "given by Joseph Smith and Sidney Rigdon: \"we saw him.\"",
    ),
    (
        "Acts", "Holy Bible", 26, 22, 23,
        "Isaiah", "Holy Bible", 42, 6, 7,
        "paraphrase", "missionary-work",
        "Paul explicitly cites \"the prophets\" testifying that Christ "
        "\"should shew light unto the people, and to the Gentiles\" - "
        "the same role Isaiah gives the Lord's servant, \"a light of "
        "the Gentiles.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 64, 10, 10,
        "Micah", "Holy Bible", 7, 18, 19,
        "paraphrase", "forgiveness",
        "\"I, the Lord, will forgive whom I will forgive\" and \"who is "
        "a God like unto thee, that pardoneth iniquity... he retaineth "
        "not his anger for ever\" both testify of God's own "
        "willingness to forgive fully.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 6, 32, 32,
        "Matthew", "Holy Bible", 18, 20, 20,
        "quotation", "church-of-jesus-christ",
        "\"As I said unto my disciples\" - Christ explicitly quotes His "
        "own earlier promise, \"where two or three are gathered "
        "together in my name, there am I in the midst of them,\" now "
        "given directly to Joseph Smith and Oliver Cowdery.",
    ),
    (
        "Mark", "Holy Bible", 12, 29, 29,
        "Deuteronomy", "Holy Bible", 6, 4, 4,
        "quotation", "godhead",
        "\"Hear, O Israel: The Lord our God is one Lord\" - Christ "
        "quotes the Shema directly, naming it \"the first of all the "
        "commandments.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 101, 16, 16,
        "Psalms", "Holy Bible", 46, 10, 10,
        "quotation", "faith",
        "\"Be still, and know that I am God\" is quoted directly, "
        "comforting the Saints concerning Zion just as the psalm "
        "comforts against every earthly upheaval.",
    ),
    (
        "Moroni", "The Book of Mormon", 7, 16, 16,
        "John", "Holy Bible", 1, 4, 5,
        "paraphrase", "jesus-christ",
        "\"The life was the light of men\" and \"the Spirit of Christ "
        "is given to every man, that he may know good from evil\" both "
        "teach that Christ's own light reaches and enlightens everyone, "
        "not only believers.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 1, 11, 14,
        "Amos", "Holy Bible", 8, 11, 12,
        "paraphrase", "restoration",
        "Amos foretells \"a famine... of hearing the words of the "
        "Lord\"; this revelation answers it directly, the Lord's own "
        "voice going forth again \"unto the ends of the earth, that "
        "all that will hear may hear.\"",
    ),
    (
        "Ephesians", "Holy Bible", 4, 4, 6,
        "Malachi", "Holy Bible", 2, 10, 10,
        "paraphrase", "church-of-jesus-christ",
        "\"Have we not all one father? hath not one God created us?\" "
        "and \"one Lord, one faith, one baptism, One God and Father of "
        "all\" both root unity among believers in having one common "
        "God.",
    ),
    (
        "Mosiah", "The Book of Mormon", 24, 13, 14,
        "Isaiah", "Holy Bible", 40, 31, 31,
        "paraphrase", "trials-and-adversity",
        "\"They that wait upon the Lord shall renew their strength\" "
        "and the Lord's own voice to Alma's people in bondage - \"lift "
        "up your heads and be of good comfort\" - both promise renewed "
        "strength to the afflicted who trust in Him.",
    ),
    (
        "Alma", "The Book of Mormon", 41, 3, 5,
        "Galatians", "Holy Bible", 6, 7, 7,
        "paraphrase", "judgment",
        "\"Whatsoever a man soweth, that shall he also reap\" is the "
        "same law of restoration Alma teaches: men \"judged according "
        "to their works,\" good returning good and evil returning "
        "evil.",
    ),
    (
        "Luke", "Holy Bible", 16, 10, 10,
        "Alma", "The Book of Mormon", 37, 6, 7,
        "paraphrase", "obedience",
        "\"He that is faithful in that which is least is faithful also "
        "in much\" is the same principle Alma teaches: \"by small and "
        "simple things are great things brought to pass.\"",
    ),
    (
        "Revelation", "Holy Bible", 3, 7, 8,
        "Isaiah", "Holy Bible", 22, 22, 22,
        "quotation", "priesthood",
        "\"He that hath the key of David, he that openeth, and no man "
        "shutteth\" - John quotes Isaiah's own image of authority "
        "directly, applying it to Christ.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 28, 7, 8,
        "Isaiah", "Holy Bible", 5, 20, 20,
        "paraphrase", "truth",
        "\"Eat, drink, and be merry, for tomorrow we die... and it "
        "shall be well with us\" is the same moral confusion Isaiah "
        "warns against: \"woe unto them that call evil good, and good "
        "evil.\"",
    ),
    (
        "Moroni", "The Book of Mormon", 9, 6, 6,
        "Galatians", "Holy Bible", 6, 9, 9,
        "paraphrase", "endure-to-the-end",
        "\"Let us not be weary in well doing: for in due season we "
        "shall reap, if we faint not\" is the same encouragement Mormon "
        "gives his son amid discouragement: \"let us labor diligently; "
        "for if we should cease to labor, we should be brought under "
        "condemnation.\"",
    ),
    (
        "Helaman", "The Book of Mormon", 10, 7, 7,
        "Matthew", "Holy Bible", 16, 19, 19,
        "paraphrase", "priesthood",
        "\"Whatsoever ye shall seal on earth shall be sealed in "
        "heaven\" closely matches the sealing power Christ promises "
        "Peter: \"whatsoever thou shalt bind on earth shall be bound "
        "in heaven.\"",
    ),
    (
        "Revelation", "Holy Bible", 12, 7, 9,
        "Doctrine and Covenants", "Doctrine and Covenants", 29, 36, 38,
        "paraphrase", "premortal-life",
        "\"There was war in heaven: Michael and his angels fought "
        "against the dragon\" and this revelation's own account of "
        "Satan's rebellion - \"Give me thine honor, which is my "
        "power\" - both narrate the same premortal war.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 101, 26, 31,
        "Isaiah", "Holy Bible", 11, 6, 9,
        "paraphrase", "second-coming",
        "\"The wolf also shall dwell with the lamb\" is the same "
        "millennial peace this revelation describes at length - \"the "
        "enmity of man, and the enmity of beasts... shall cease from "
        "before my face.\"",
    ),
    (
        "2 Corinthians", "Holy Bible", 6, 2, 2,
        "Alma", "The Book of Mormon", 34, 32, 33,
        "paraphrase", "repentance",
        "\"Now is the accepted time... now is the day of salvation\" "
        "and \"this life is the time for men to prepare to meet God\" "
        "both teach that mortality itself is the appointed time to "
        "repent, not a time to presume upon later.",
    ),
    (
        "Revelation", "Holy Bible", 5, 5, 5,
        "Genesis", "Holy Bible", 49, 10, 10,
        "paraphrase", "jesus-christ",
        "\"The Lion of the tribe of Juda... hath prevailed\" fulfills "
        "the ancient blessing that \"the sceptre shall not depart from "
        "Judah... until Shiloh come.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 27, 5, 5,
        "Matthew", "Holy Bible", 26, 29, 29,
        "quotation", "second-coming",
        "\"I will drink of the fruit of the vine with you on the "
        "earth\" repeats Christ's own promise at the Last Supper "
        "almost word for word: \"I will not drink henceforth of this "
        "fruit of the vine, until that day when I drink it new with "
        "you in my Father's kingdom.\"",
    ),
    (
        "1 Corinthians", "Holy Bible", 15, 21, 22,
        "Mosiah", "The Book of Mormon", 16, 7, 9,
        "paraphrase", "resurrection",
        "\"As in Adam all die, even so in Christ shall all be made "
        "alive\" is the same doctrine Abinadi teaches: without "
        "Christ's own resurrection breaking \"the bands of death,\" "
        "\"there could have been no resurrection\" for anyone.",
    ),
    (
        "Mark", "Holy Bible", 10, 14, 14,
        "Doctrine and Covenants", "Doctrine and Covenants", 137, 10, 10,
        "paraphrase", "children",
        "\"Suffer the little children to come unto me... of such is "
        "the kingdom of God\" is the same doctrine this revelation "
        "states outright: \"all children who die before they arrive "
        "at the years of accountability are saved in the celestial "
        "kingdom of heaven.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 3, 1, 2,
        "Numbers", "Holy Bible", 23, 19, 19,
        "paraphrase", "truth",
        "\"God is not a man, that he should lie... shall he not make "
        "it good?\" is the same reliability this revelation teaches: "
        "\"the works, and the designs, and the purposes of God cannot "
        "be frustrated, neither can they come to naught.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 20, 17, 19,
        "Malachi", "Holy Bible", 3, 6, 6,
        "paraphrase", "godhead",
        "\"I am the Lord, I change not\" is the same unchanging nature "
        "this revelation confesses: \"from everlasting to everlasting "
        "the same unchangeable God.\"",
    ),
    (
        "1 Corinthians", "Holy Bible", 1, 19, 20,
        "2 Nephi", "The Book of Mormon", 9, 28, 29,
        "paraphrase", "wisdom",
        "\"I will destroy the wisdom of the wise\" and \"when they are "
        "learned they think they are wise, and they hearken not unto "
        "the counsel of God\" both warn that worldly learning can "
        "become a stumbling block rather than a strength.",
    ),
    (
        "Proverbs", "Holy Bible", 1, 7, 7,
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 118, 118,
        "paraphrase", "wisdom",
        "\"The fear of the Lord is the beginning of knowledge\" and "
        "\"seek learning, even by study and also by faith\" both join "
        "reverence for God to the pursuit of real knowledge, rather "
        "than treating the two as opposites.",
    ),
    (
        "Hebrews", "Holy Bible", 5, 4, 6,
        "Psalms", "Holy Bible", 110, 4, 4,
        "quotation", "priesthood",
        "\"Thou art a priest for ever after the order of Melchisedec\" "
        "is quoted directly, alongside the teaching that \"no man "
        "taketh this honour unto himself, but he that is called of "
        "God, as was Aaron\" - the same Melchizedek Priesthood chain "
        "as Genesis 14, Alma 13, and D&C 107 above.",
    ),
    (
        "2 Corinthians", "Holy Bible", 11, 3, 3,
        "Moses", "Pearl of Great Price", 4, 6, 6,
        "paraphrase", "temptation",
        "\"The serpent beguiled Eve through his subtilty\" restates "
        "almost word for word what Moses records directly: Satan "
        "\"sought also to beguile Eve.\"",
    ),
    (
        "Romans", "Holy Bible", 6, 23, 23,
        "Alma", "The Book of Mormon", 42, 15, 15,
        "paraphrase", "atonement",
        "\"The wages of sin is death; but the gift of God is eternal "
        "life through Jesus Christ\" is the same exchange Alma "
        "explains through the Atonement: \"God himself atoneth for the "
        "sins of the world, to bring about the plan of mercy.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 29, 39, 40,
        "2 Nephi", "The Book of Mormon", 2, 11, 11,
        "paraphrase", "agency",
        "\"It must needs be that the devil should tempt the children "
        "of men, or they could not be agents unto themselves\" is the "
        "same doctrine Lehi teaches: \"it must needs be, that there is "
        "an opposition in all things\" for agency to mean anything at "
        "all.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 42, 22, 26,
        "Matthew", "Holy Bible", 5, 27, 28,
        "quotation", "chastity",
        "\"He that looketh upon a woman to lust after her shall deny "
        "the faith\" restates Christ's own teaching almost word for "
        "word: \"whosoever looketh on a woman to lust after her hath "
        "committed adultery with her already in his heart.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 42, 30, 31,
        "Acts", "Holy Bible", 20, 35, 35,
        "paraphrase", "consecration",
        "The commandment to \"remember the poor, and consecrate of thy "
        "properties for their support\" is the same principle Paul "
        "quotes from the Lord Jesus: \"it is more blessed to give than "
        "to receive.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 59, 7, 8,
        "1 Thessalonians", "Holy Bible", 5, 18, 18,
        "paraphrase", "gratitude",
        "\"Thou shalt thank the Lord thy God in all things\" is the "
        "same commandment Paul gives: \"in every thing give thanks: "
        "for this is the will of God in Christ Jesus concerning you.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 25, 12, 12,
        "Ephesians", "Holy Bible", 5, 19, 19,
        "paraphrase", "prayer",
        "\"The song of the righteous is a prayer unto me\" matches "
        "Paul's own instruction to the saints: \"speaking to "
        "yourselves in psalms and hymns and spiritual songs... making "
        "melody in your heart to the Lord.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 50, 23, 24,
        "1 John", "Holy Bible", 4, 1, 1,
        "paraphrase", "revelation",
        "\"That which doth not edify is not of God, and is darkness\" "
        "gives the same test John commands: \"believe not every "
        "spirit, but try the spirits whether they are of God.\"",
    ),
    (
        "Matthew", "Holy Bible", 20, 25, 27,
        "Doctrine and Covenants", "Doctrine and Covenants", 121, 41, 42,
        "paraphrase", "priesthood",
        "\"Whosoever will be great among you, let him be your "
        "minister\" is the same principle this revelation teaches of "
        "priesthood power: it can only be maintained \"by persuasion, "
        "by long-suffering, by gentleness and meekness, and by love "
        "unfeigned,\" never by dominion.",
    ),
    (
        "1 Peter", "Holy Bible", 4, 8, 8,
        "Proverbs", "Holy Bible", 10, 12, 12,
        "quotation", "charity",
        "\"Charity shall cover the multitude of sins\" restates the "
        "proverb almost exactly: \"love covereth all sins.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 98, 23, 24,
        "Matthew", "Holy Bible", 5, 38, 39,
        "paraphrase", "peace",
        "Bearing an offense patiently \"and revile not against them, "
        "neither seek revenge\" is the same doctrine Christ teaches: "
        "\"ye have heard... an eye for an eye... but I say unto you, "
        "that ye resist not evil.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 98, 16, 16,
        "Matthew", "Holy Bible", 26, 52, 52,
        "paraphrase", "peace",
        "\"Renounce war and proclaim peace\" is the same warning Christ "
        "gives Peter in Gethsemane: \"all they that take the sword "
        "shall perish with the sword.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 25, 26,
        "Romans", "Holy Bible", 8, 19, 22,
        "paraphrase", "creation",
        "\"The earth abideth the law of a celestial kingdom, for it "
        "filleth the measure of its creation\" is the same hope Paul "
        "describes: \"the creature itself also shall be delivered from "
        "the bondage of corruption into the glorious liberty of the "
        "children of God.\"",
    ),
    # --- Closing the gap toward 600: more Psalms/crucifixion prophecy ---
    (
        "Matthew", "Holy Bible", 27, 39, 39,
        "Psalms", "Holy Bible", 22, 7, 8,
        "quotation", "atonement",
        "\"They shoot out the lip, they shake the head\" is fulfilled "
        "almost exactly as those passing the cross \"reviled him, "
        "wagging their heads\" - the same psalm of suffering already "
        "quoted for Matthew 27:46 and John 19:24 above, now for the "
        "mockery itself.",
    ),
    (
        "2 Peter", "Holy Bible", 3, 8, 8,
        "Psalms", "Holy Bible", 90, 4, 4,
        "paraphrase", "second-coming",
        "\"One day is with the Lord as a thousand years\" nearly "
        "repeats Moses' own psalm, \"a thousand years in thy sight are "
        "but as yesterday\" - God's patience measured on a scale "
        "mortals can't otherwise imagine.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 6, 36, 36,
        "Hebrews", "Holy Bible", 12, 2, 2,
        "paraphrase", "faith",
        "\"Look unto me in every thought\" and \"looking unto Jesus the "
        "author and finisher of our faith\" both make Christ Himself, "
        "not circumstance, the fixed point to watch.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 121, 34, 36,
        "1 Peter", "Holy Bible", 5, 2, 3,
        "paraphrase", "priesthood",
        "Both warn against priesthood authority exercised for status "
        "or gain - Peter that elders should serve \"not for filthy "
        "lucre... not as being lords,\" this revelation that many "
        "\"aspire to the honors of men\" and so are not chosen.",
    ),
    (
        "2 Peter", "Holy Bible", 3, 13, 13,
        "Isaiah", "Holy Bible", 65, 17, 17,
        "quotation", "second-coming",
        "\"New heavens and a new earth\" - Peter quotes Isaiah's own "
        "prophecy directly as what the righteous still look for.",
    ),
    (
        "Isaiah", "Holy Bible", 2, 4, 4,
        "Micah", "Holy Bible", 4, 3, 3,
        "quotation", "second-coming",
        "Two prophets, writing independently, record the Lord's "
        "millennial peace in nearly identical words: \"they shall beat "
        "their swords into plowshares... nation shall not lift up "
        "sword against nation.\"",
    ),
    (
        "Luke", "Holy Bible", 11, 9, 9,
        "3 Nephi", "The Book of Mormon", 14, 7, 7,
        "quotation", "prayer",
        "\"Ask, and it shall be given you; seek, and ye shall find\" - "
        "Luke's own independent record of the same teaching Matthew "
        "preserves in the Sermon on the Mount, given again word for "
        "word by the risen Christ to the Nephites.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 118, 118,
        "Proverbs", "Holy Bible", 4, 7, 7,
        "paraphrase", "wisdom",
        "\"Wisdom is the principal thing; therefore get wisdom\" and "
        "\"seek ye diligently... seek learning, even by study and also "
        "by faith\" both make the pursuit of wisdom a central "
        "commandment, not an optional pursuit.",
    ),
    (
        "Helaman", "The Book of Mormon", 12, 1, 6,
        "Proverbs", "Holy Bible", 16, 18, 18,
        "paraphrase", "humility",
        "\"Pride goeth before destruction, and an haughty spirit "
        "before a fall\" describes exactly the cycle Mormon laments "
        "here: prosperity leads to pride, pride to forgetting God, "
        "forgetting God to affliction.",
    ),
    (
        "Revelation", "Holy Bible", 11, 15, 15,
        "Psalms", "Holy Bible", 72, 8, 11,
        "paraphrase", "second-coming",
        "\"He shall have dominion also from sea to sea... all kings "
        "shall fall down before him\" is the same universal reign John "
        "later sees fulfilled: \"the kingdoms of this world are become "
        "the kingdoms of our Lord, and of his Christ.\"",
    ),
    (
        "2 Nephi", "The Book of Mormon", 9, 28, 29,
        "Proverbs", "Holy Bible", 1, 7, 7,
        "paraphrase", "wisdom",
        "\"The fear of the Lord is the beginning of knowledge: but "
        "fools despise wisdom\" and Jacob's own warning, \"when they "
        "are learned they think they are wise, and they hearken not "
        "unto the counsel of God,\" both teach that learning without "
        "humility before God leads to folly, not wisdom.",
    ),
    # --- "tradition" tier: widely-recognized thematic/traditional
    # associations, not something scripture itself explicitly states -
    # added once the first four kinds' well-documented candidates were
    # largely exhausted (see module docstring's own note on this). Every
    # note below is candid that it's an interpretive reading.
    (
        "Matthew", "Holy Bible", 26, 14, 16,
        "Genesis", "Holy Bible", 37, 23, 28,
        "tradition", "jesus-christ",
        "Joseph sold by his own brothers for silver is traditionally "
        "read as foreshadowing Christ betrayed for thirty pieces of "
        "silver by one of His own - a widely-recognized parallel, "
        "though scripture itself never states the connection outright.",
    ),
    (
        "Luke", "Holy Bible", 23, 41, 41,
        "Genesis", "Holy Bible", 39, 20, 23,
        "tradition", "jesus-christ",
        "Joseph imprisoned though entirely innocent is traditionally "
        "read as a type of Christ's own unjust condemnation - the same "
        "innocence the repentant thief on the cross recognizes: \"this "
        "man hath done nothing amiss.\"",
    ),
    (
        "Philippians", "Holy Bible", 2, 9, 11,
        "Genesis", "Holy Bible", 41, 39, 41,
        "tradition", "jesus-christ",
        "Joseph exalted to sit at Pharaoh's own right hand, given "
        "authority over all Egypt, is traditionally read as "
        "prefiguring Christ's own exaltation - \"God also hath highly "
        "exalted him, and given him a name which is above every name.\"",
    ),
    (
        "Luke", "Holy Bible", 23, 34, 34,
        "Genesis", "Holy Bible", 45, 4, 5,
        "tradition", "forgiveness",
        "Joseph's forgiveness of the very brothers who sold him is "
        "traditionally compared to Christ's own forgiveness from the "
        "cross of those who crucified Him - \"Father, forgive them; "
        "for they know not what they do.\"",
    ),
    (
        "John", "Holy Bible", 2, 5, 5,
        "Genesis", "Holy Bible", 41, 55, 55,
        "tradition", "jesus-christ",
        "\"Go unto Joseph; what he saith to you, do\" is traditionally "
        "read as an almost word-for-word foreshadowing of Mary's own "
        "counsel at Cana: \"whatsoever he saith unto you, do it.\"",
    ),
    (
        "John", "Holy Bible", 3, 17, 17,
        "Genesis", "Holy Bible", 45, 7, 7,
        "tradition", "jesus-christ",
        "Joseph's mission \"to preserve you a posterity... and to save "
        "your lives\" is traditionally read as a type of Christ's own "
        "saving mission, sent \"that the world through him might be "
        "saved.\"",
    ),
    (
        "Ephesians", "Holy Bible", 1, 7, 7,
        "Ruth", "Holy Bible", 4, 9, 10,
        "tradition", "atonement",
        "Boaz purchasing Ruth's redemption as her near kinsman is "
        "traditionally read as a type of Christ's own redemption of "
        "His people - \"in whom we have redemption through his "
        "blood.\"",
    ),
    (
        "Galatians", "Holy Bible", 4, 4, 5,
        "Ruth", "Holy Bible", 2, 20, 20,
        "tradition", "atonement",
        "Boaz named Ruth's \"near kinsman\" - the Hebrew go'el, "
        "kinsman-redeemer - is traditionally read as a type of Christ, "
        "\"sent forth... to redeem them that were under the law.\"",
    ),
    (
        "Luke", "Holy Bible", 7, 14, 15,
        "2 Kings", "Holy Bible", 4, 32, 35,
        "tradition", "resurrection",
        "Elisha raising the Shunammite woman's son is traditionally "
        "read alongside Christ's own raising of the widow of Nain's "
        "son as evidence of the same resurrection power at work "
        "through God's prophets and through Christ Himself.",
    ),
    (
        "1 Peter", "Holy Bible", 1, 18, 19,
        "Joshua", "Holy Bible", 2, 18, 21,
        "tradition", "atonement",
        "Rahab's household spared by the scarlet cord in her window is "
        "traditionally read as a type of salvation marked by blood, "
        "the same imagery Peter uses of being \"redeemed... with the "
        "precious blood of Christ.\"",
    ),
    (
        "Luke", "Holy Bible", 2, 21, 21,
        "Genesis", "Holy Bible", 17, 12, 12,
        "tradition", "covenants",
        "Christ was circumcised the eighth day exactly as the law of "
        "Abraham's covenant required - fulfilling the custom rather "
        "than a stated prophecy, but traditionally noted as His own "
        "submission to the very covenant He came to fulfill.",
    ),
    (
        "Matthew", "Holy Bible", 6, 11, 11,
        "Exodus", "Holy Bible", 16, 4, 4,
        "tradition", "prayer",
        "Manna gathered fresh each day, no more than a day's portion "
        "at a time, is traditionally read behind the Lord's Prayer's "
        "own request: \"give us this day our daily bread.\"",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 9, 8, 8,
        "Judges", "Holy Bible", 6, 36, 40,
        "tradition", "revelation",
        "Gideon's fleece is a widely-used example of seeking a "
        "confirming sign before acting in faith - the same pattern "
        "this revelation describes as studying a question out, then "
        "asking for confirmation.",
    ),
    (
        "Ephesians", "Holy Bible", 2, 12, 13,
        "Matthew", "Holy Bible", 1, 5, 5,
        "tradition", "house-of-israel",
        "Rahab and Ruth, both Gentile women, named openly in Christ's "
        "own genealogy, are traditionally read as an early sign of the "
        "same truth Paul later teaches - that those once \"far off\" "
        "are \"made nigh by the blood of Christ.\"",
    ),
    (
        "John", "Holy Bible", 19, 17, 17,
        "Genesis", "Holy Bible", 22, 6, 6,
        "tradition", "atonement",
        "Isaac carrying the wood for his own sacrifice up the mountain "
        "is traditionally read alongside Christ \"bearing his cross\" "
        "to Golgotha - a son carrying the very instrument of his own "
        "offering.",
    ),
    (
        "James", "Holy Bible", 1, 5, 5,
        "1 Kings", "Holy Bible", 3, 9, 9,
        "tradition", "wisdom",
        "Solomon's request for \"an understanding heart\" rather than "
        "riches is traditionally cited alongside James' own invitation "
        "to ask God for wisdom - both receiving it generously, without "
        "being upbraided for the asking.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 88, 119, 119,
        "1 Kings", "Holy Bible", 8, 27, 27,
        "tradition", "temple",
        "Solomon's own wonder that \"the heaven and heaven of heavens "
        "cannot contain\" God, even in the temple built for Him, is "
        "traditionally read alongside this revelation's own "
        "instruction to build \"a house of prayer, a house of God\" - "
        "the same tension between God's infinite greatness and a "
        "finite house built for His name.",
    ),
    (
        "Moroni", "The Book of Mormon", 4, 3, 3,
        "Genesis", "Holy Bible", 14, 18, 18,
        "tradition", "ordinances",
        "Melchizedek bringing forth bread and wine is traditionally "
        "read as an early foreshadowing of the sacrament, though "
        "scripture itself does not state the connection the way it "
        "names the Passover lamb or manna as types of Christ.",
    ),
    (
        "Matthew", "Holy Bible", 3, 16, 16,
        "Genesis", "Holy Bible", 8, 11, 11,
        "tradition", "holy-ghost",
        "The dove returning to Noah's ark with an olive leaf is "
        "traditionally paired with the Holy Ghost descending \"like a "
        "dove\" at Christ's own baptism - the same image of peace "
        "after judgment, used in both settings.",
    ),
    (
        "Matthew", "Holy Bible", 2, 2, 2,
        "Numbers", "Holy Bible", 24, 17, 17,
        "tradition", "jesus-christ",
        "Balaam's prophecy of \"a Star out of Jacob\" is traditionally "
        "read as pointing toward the very star the wise men later "
        "followed to Bethlehem, \"where is he that is born King of the "
        "Jews?\"",
    ),
    (
        "1 Corinthians", "Holy Bible", 15, 52, 52,
        "Leviticus", "Holy Bible", 23, 24, 24,
        "tradition", "second-coming",
        "The Feast of Trumpets is traditionally associated with the "
        "same \"last trump\" Paul describes at the resurrection of the "
        "dead, though Paul never names the feast directly.",
    ),
    (
        "Isaiah", "Holy Bible", 53, 6, 6,
        "Leviticus", "Holy Bible", 16, 21, 22,
        "tradition", "atonement",
        "The scapegoat, bearing Israel's confessed sins away into the "
        "wilderness, is traditionally read as a type of Christ bearing "
        "sin - \"the Lord hath laid on him the iniquity of us all\" - "
        "a companion to the sacrificed goat's blood already covered "
        "above.",
    ),
    (
        "Isaiah", "Holy Bible", 53, 2, 2,
        "1 Samuel", "Holy Bible", 16, 11, 13,
        "tradition", "jesus-christ",
        "David, the youngest and least expected of Jesse's sons, "
        "anointed king while tending sheep, is traditionally compared "
        "to the Messiah Isaiah describes as having \"no form nor "
        "comeliness\" - greatness hidden in an unlikely, overlooked "
        "beginning.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 105, 14, 14,
        "1 Samuel", "Holy Bible", 17, 45, 47,
        "tradition", "faith",
        "David's confidence that \"the battle is the Lord's,\" not "
        "decided by conventional weapons, is traditionally cited "
        "alongside this revelation's own promise that the Lord's own "
        "power, not human strength, secures Zion's victories.",
    ),
    (
        "Matthew", "Holy Bible", 6, 26, 26,
        "1 Kings", "Holy Bible", 17, 4, 6,
        "tradition", "faith",
        "Elijah fed by ravens in the wilderness is traditionally "
        "paired with Christ's own teaching to \"behold the fowls of "
        "the air... yet your heavenly Father feedeth them\" - both "
        "making the same point about God's providential care.",
    ),
    (
        "Mark", "Holy Bible", 12, 43, 44,
        "1 Kings", "Holy Bible", 17, 14, 16,
        "tradition", "faith",
        "The widow of Zarephath's meal and oil not failing after she "
        "gave what little she had is traditionally compared to the "
        "widow's mite - two poor widows whose small, complete "
        "offerings became sufficient through faith.",
    ),
    (
        "Ephesians", "Holy Bible", 5, 26, 26,
        "Exodus", "Holy Bible", 30, 18, 20,
        "tradition", "baptism",
        "The bronze laver, where priests washed before entering God's "
        "presence, is traditionally read as a type of baptism's own "
        "cleansing, \"the washing of water by the word,\" before "
        "approaching God.",
    ),
    (
        "Revelation", "Holy Bible", 22, 16, 16,
        "Song of Solomon", "Holy Bible", 2, 1, 1,
        "tradition", "jesus-christ",
        "\"I am the rose of Sharon, and the lily of the valleys\" is "
        "traditionally read as a poetic description of Christ Himself "
        "- an allegorical reading of the whole book, not a connection "
        "scripture itself states, though Christ's own \"I am the root "
        "and the offspring of David, and the bright and morning star\" "
        "affirms the same self-description in plainer language.",
    ),
    (
        "Doctrine and Covenants", "Doctrine and Covenants", 122, 9, 9,
        "Esther", "Holy Bible", 4, 14, 16,
        "tradition", "faith",
        "Esther's willingness to risk everything for her people - \"if "
        "I perish, I perish\" - after being reminded she may have "
        "\"come to the kingdom for such a time as this,\" is "
        "traditionally read alongside this revelation's own charge: "
        "\"hold on thy way... fear not what man can do.\"",
    ),
    (
        "Galatians", "Holy Bible", 4, 7, 7,
        "Philemon", "Holy Bible", 1, 15, 16,
        "tradition", "family",
        "Paul's plea that Onesimus be received \"not now as a "
        "servant, but... a brother beloved\" is traditionally read "
        "alongside his own teaching elsewhere that through Christ "
        "\"thou art no more a servant, but a son\" - forgiveness and "
        "adoption modeled in a single, personal letter.",
    ),
    (
        "2 Nephi", "The Book of Mormon", 4, 20, 20,
        "Nahum", "Holy Bible", 1, 7, 7,
        "tradition", "faith",
        "\"The Lord is good, a strong hold in the day of trouble; and "
        "he knoweth them that trust in him\" is the same confidence "
        "Nephi expresses in his own psalm of trust: \"my God hath been "
        "my support; he hath led me through mine afflictions.\"",
    ),
    (
        "Hebrews", "Holy Bible", 11, 30, 30,
        "Joshua", "Holy Bible", 6, 20, 20,
        "paraphrase", "faith",
        "\"By faith the walls of Jericho fell down\" - Hebrews retells "
        "this same event as one of its prime examples of faith "
        "accomplishing what force could not.",
    ),
    (
        "1 Corinthians", "Holy Bible", 10, 16, 16,
        "Exodus", "Holy Bible", 12, 7, 7,
        "tradition", "atonement",
        "Israel's doorposts marked with the Passover lamb's blood, "
        "protecting them from \"the destroyer,\" is traditionally "
        "extended to \"the cup of blessing which we bless, is it not "
        "the communion of the blood of Christ?\" - the same protecting "
        "blood, applied sacramentally rather than architecturally.",
    ),
    (
        "3 Nephi", "The Book of Mormon", 28, 19, 22,
        "Daniel", "Holy Bible", 6, 22, 22,
        "tradition", "faith",
        "Daniel's deliverance from the lions - \"my God hath sent his "
        "angel, and hath shut the lions' mouths\" - is traditionally "
        "compared to the Three Nephites' own protection from wild "
        "beasts and fire, both accounts of God shielding the faithful "
        "from otherwise-certain harm.",
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
