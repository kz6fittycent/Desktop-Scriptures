#!/usr/bin/env python3
"""Build (or refresh) the Topical Guide: for each topic, ranks the local
scripture text by full-text relevance to find its supporting verses,
harvests General Conference citation metadata for any of those verses
not already harvested, and writes topics/topic_verses/topic_talks into
the database.

Usage:
    python3 scripts/build_topical_guide.py [path-to-db]

    path-to-db defaults to data/scriptures.db.

Re-run this any time scripture content changes (a new book imported,
etc.) to pick up newly-relevant verses. It fully replaces the
topics/topic_verses/topic_talks tables each run (DELETE + re-INSERT) -
this is a developer-run tool, like every other scripts/import_*.py, not
something the app runs itself; end users get its output the same way
they get everything else here, through db.py's sync_bundled_content on
their next snap refresh.

TOPIC SELECTION: a topic's supporting scriptures are its
VERSES_PER_TOPIC highest-ranked local FTS5 matches (bm25, the same
relevance ranking the app's own Search already uses) against a small,
hand-picked set of search terms per topic - see TOPICS below. This is
Desktop Scriptures' own correlation of gospel topics against its own
local, already-legally-sourced text, not a transcription of the Church's
actual Topical Guide (which is a copyrighted, separately-curated work);
the one-line descriptions below are original framings, not definitions,
same distinction the user asked for. When the same reference exists in
more than one volume with different wording (Holy Bible vs. Joseph Smith
Translation, which reuses the KJV's numbering) only the higher-ranked
volume's wording is kept, so a topic never shows what looks like the
"same" verse twice.

TALK CITATIONS: reuses harvest_citations.py's scraper against
scriptures.byu.edu's public citation index (see that script's own
COPYRIGHT note - metadata only, talk title/speaker/date/URL, never talk
text), extended here to whatever verses this run's topics actually
picked, rather than just the Scripture of the Day pool that script was
originally scoped to. Results are merged into data/verse_citations.json
(the same file citations_panel.py already reads) instead of a separate
file, so a talk citation harvested for a topic also lights up that
verse's own Citations tab, and vice versa - a verse already in that file
is never re-fetched. Books outside the Bible/Book of Mormon/D&C/Pearl of
Great Price canon (Journal of Discourses, Lectures on Faith, Joseph
Smith Translation) have no entry in BYU's citation index at all and are
just skipped, same as harvest_citations.py already does for those.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from scriptures.db import connect  # noqa: E402

import harvest_citations as hc  # noqa: E402

CITATIONS_PATH = PROJECT_ROOT / "data" / "verse_citations.json"
VERSES_PER_TOPIC = 20
TALKS_PER_TOPIC = 15
_MONTH_NUMBER = {v: k for k, v in hc.MONTH_NAMES.items()}

# (name, slug, description, FTS5 query). Descriptions are one-line, deliberately
# not definitions (see module docstring). FTS5 queries are bare terms ORed
# together, phrases double-quoted - see fetch_topic_verses.
TOPICS = [
    (
        "Faith",
        "faith",
        "Faith is trust in Jesus Christ that leads to action - believing enough to obey "
        "before receiving a witness of the outcome.",
        "faith OR believe OR believeth OR believed OR belief",
    ),
    (
        "Repentance",
        "repentance",
        "Repentance is turning away from sin and back toward God, made possible through "
        "the Atonement of Jesus Christ.",
        "repent OR repentance OR repenteth OR repented OR repenting",
    ),
    (
        "Charity",
        "charity",
        "Charity is the pure love of Christ - patient and selfless, and expressed through "
        "service to others.",
        "charity OR charitable OR \"pure love\"",
    ),
    (
        "Salvation",
        "salvation",
        "Salvation is deliverance from sin and death through the Atonement of Jesus "
        "Christ, offered to all who come unto Him.",
        "salvation OR saved OR saveth OR redeem OR redeemer OR redemption",
    ),
    (
        "Exaltation",
        "exaltation",
        "Exaltation is the fulness of blessings God offers His children - eternal life in "
        "His presence, made possible through the covenants and ordinances of the gospel.",
        "exaltation OR exalt OR exalted OR \"eternal life\" OR \"eternal lives\"",
    ),
    (
        "Atonement",
        "atonement",
        "The Atonement is Jesus Christ's suffering, death, and resurrection, through which "
        "He paid the price for sin and made repentance and eternal life possible.",
        "atonement OR atone OR atoned OR atoneth OR atoning",
    ),
    (
        "Prayer",
        "prayer",
        "Prayer is personal communication with God - asking, listening, and expressing "
        "gratitude.",
        "prayer OR pray OR prayeth OR prayed OR supplication",
    ),
    (
        "Obedience",
        "obedience",
        "Obedience is keeping God's commandments out of love and trust rather than "
        "compulsion.",
        "obedience OR obey OR obeyed OR obedient OR commandments",
    ),
    (
        "Forgiveness",
        "forgiveness",
        "Forgiveness is letting go of resentment toward those who have wronged us, "
        "following the example and grace of Jesus Christ.",
        "forgive OR forgiveness OR forgiven OR forgiveth OR forgiving",
    ),
    (
        "Hope",
        "hope",
        "Hope is confident expectation in God's promises, anchored in faith in Jesus "
        "Christ and His Atonement.",
        "hope OR hopeth OR hoped",
    ),
    (
        "Humility",
        "humility",
        "Humility is a teachable, submissive heart before God - trusting Him rather than "
        "relying only on ourselves.",
        "humility OR humble OR humbleth OR humbled OR meek OR meekness",
    ),
    (
        "Priesthood",
        "priesthood",
        "The priesthood is the authority to act in God's name, given to bless, serve, and "
        "administer the ordinances of the gospel.",
        "priesthood",
    ),
    (
        "Revelation",
        "revelation",
        "Revelation is God's communication to His children, given personally or through "
        "prophets, to guide, teach, and testify of truth.",
        "revelation OR revelations OR reveal OR revealeth OR revealed",
    ),
    (
        "Sacrifice",
        "sacrifice",
        "Sacrifice is giving up something of value out of love and obedience to God, in "
        "the pattern of the Savior's own sacrifice.",
        "sacrifice OR sacrifices OR sacrificed OR sacrificeth",
    ),
    (
        "Covenants",
        "covenants",
        "Covenants are sacred two-way promises between God and His children, made through "
        "ordinances such as baptism and temple sealings.",
        "covenant OR covenants OR covenanted OR covenanting",
    ),
    (
        "Baptism",
        "baptism",
        "Baptism is the first ordinance of the gospel - a covenant to take Christ's name "
        "and follow Him, symbolizing death to sin and new spiritual life.",
        "baptism OR baptize OR baptized OR baptizeth OR baptizing",
    ),
    (
        "Holy Ghost",
        "holy-ghost",
        "The Holy Ghost is the third member of the Godhead, who testifies of truth, "
        "comforts, guides, and sanctifies those who receive Him.",
        "\"Holy Ghost\" OR \"Holy Spirit\" OR Comforter",
    ),
    (
        "Resurrection",
        "resurrection",
        "The Resurrection is the reuniting of body and spirit in immortality, made "
        "possible for all mankind through Jesus Christ's victory over death.",
        "resurrection OR resurrected OR resurrecteth OR risen",
    ),
    (
        "Agency",
        "agency",
        "Agency is the God-given ability to choose and act for ourselves, with "
        "accountability for the consequences of those choices.",
        "agency OR \"free to act\" OR \"act for themselves\" OR \"act for himself\" OR \"power to choose\"",
    ),
    (
        "Gratitude",
        "gratitude",
        "Gratitude is thankful recognition of God's hand in our lives, expressed through "
        "worship, obedience, and service.",
        "gratitude OR thankful OR thanksgiving OR grateful OR thanks",
    ),
    (
        "Temptation",
        "temptation",
        "Temptation is an enticement to sin, which can be overcome through faith in Jesus "
        "Christ, obedience, and reliance on the Spirit.",
        "temptation OR temptations OR tempt OR tempted OR tempteth",
    ),
    (
        "Service",
        "service",
        "Service is selfless work for the benefit of others, following the Savior's "
        "example of ministering to those in need.",
        "service OR serve OR serveth OR minister OR ministering OR ministered",
    ),
    (
        "Family",
        "family",
        "Family relationships are central to God's plan, providing the setting where "
        "love, covenants, and eternal relationships are built.",
        "marriage OR \"one flesh\" OR \"father and mother\" OR \"children of God\" OR household",
    ),
    (
        "Testimony",
        "testimony",
        "A testimony is a personal, spiritual conviction of gospel truths, gained and "
        "strengthened through the witness of the Holy Ghost.",
        "testimony OR testify OR testified OR testifieth OR witness",
    ),
    (
        "Word of God",
        "word-of-god",
        "The scriptures are the recorded word of God, given to teach, testify of Christ, "
        "and guide His children back to Him.",
        "scripture OR scriptures OR \"word of God\"",
    ),
]


MIN_RANK_RATIO = 0.35  # see fetch_topic_candidates


def fetch_topic_candidates(conn, query: str, limit: int) -> list[dict]:
    """Up to `limit` verses, deduplicated by reference (see module
    docstring's TOPIC SELECTION note on why), ranked by FTS5 bm25 -
    lower/more-negative is more relevant, hence ORDER BY rank ascending.

    Also drops anything weaker than MIN_RANK_RATIO of the top match's own
    rank for this query - a topic with few genuinely strong matches (seen
    with "Agency": 11 clearly on-topic verses, then a cliff straight into
    Journal of Discourses entries that only matched a rare shared word
    once in an entire discourse) would otherwise pad out to `limit` with
    weak, off-topic filler rather than just showing fewer, better verses.
    Topics with plenty of strong matches (every other topic checked while
    building this) are unaffected - their rank curve decays smoothly
    enough that this ratio never trims a genuinely relevant verse."""
    rows = conn.execute(
        "SELECT v.reference, v.text, vol.slug AS volume_slug, bm25(verses_fts) AS rank "
        "FROM verses_fts "
        "JOIN verses v ON v.id = verses_fts.rowid "
        "JOIN chapters c ON c.id = v.chapter_id "
        "JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id "
        "WHERE verses_fts MATCH ? "
        "ORDER BY rank "
        "LIMIT ?",
        (query, limit * 4),  # over-fetch; de-duping by reference below may drop some
    ).fetchall()

    seen_references: set[str] = set()
    candidates = []
    rank_threshold = None
    for row in rows:
        if rank_threshold is None:
            rank_threshold = row["rank"] * MIN_RANK_RATIO
        elif row["rank"] > rank_threshold:
            break  # everything from here on is only weaker (rows are rank-ordered)
        if row["reference"] in seen_references:
            continue
        seen_references.add(row["reference"])
        candidates.append(dict(row))
        if len(candidates) >= limit:
            break
    return candidates


def parse_reference(reference: str) -> tuple[str, int, int]:
    book, _, rest = reference.rpartition(" ")
    chapter_str, verse_str = rest.split(":")
    return book, int(chapter_str), int(verse_str)


def load_citations() -> dict:
    if CITATIONS_PATH.exists():
        return json.loads(CITATIONS_PATH.read_text(encoding="utf-8"))
    return {
        "_source": "scriptures.byu.edu Citation Index (General Conference talks)",
        "_harvested": "",
        "_note": (
            "Metadata only (talk title, speaker, date, churchofjesuschrist.org URL) - "
            "never talk text, per copyright. See scripts/harvest_citations.py and "
            "scripts/build_topical_guide.py. Keyed by the exact verse reference string "
            "used in the imported database (e.g. 'Genesis 1:1')."
        ),
        "citations": {},
    }


def save_citations(data: dict) -> None:
    data["_harvested"] = date.today().isoformat()
    CITATIONS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def harvest_missing_citations(references: set[str], citations_data: dict, book_ids: dict) -> None:
    to_fetch = sorted(references - citations_data["citations"].keys())
    if not to_fetch:
        print(f"  All {len(references)} referenced verse(s) already harvested.")
        return
    print(
        f"  Harvesting {len(to_fetch)} new verse(s) "
        f"({len(references) - len(to_fetch)} already cached)..."
    )
    for reference in to_fetch:
        book, chapter, verse = parse_reference(reference)
        book_id = book_ids.get(book)
        if book_id is None:
            continue  # not in BYU's index (JoD, Lectures on Faith, JST) - nothing to fetch
        try:
            html = hc.fetch_citation_html(book_id, chapter, str(verse))
            citations = hc.parse_citations(html)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"    {reference}: request failed ({exc})")
            time.sleep(hc.REQUEST_DELAY_SECONDS)
            continue
        except Exception as exc:  # site structure differed from expected - skip, don't crash
            print(f"    {reference}: parse failed ({exc})")
            time.sleep(hc.REQUEST_DELAY_SECONDS)
            continue
        citations_data["citations"][reference] = citations
        print(f"    {reference}: {len(citations)} citation(s)")
        time.sleep(hc.REQUEST_DELAY_SECONDS)


def _date_sort_key(talk: dict) -> tuple[int, int]:
    parts = talk.get("date", "").split()
    if len(parts) == 2 and parts[0] in _MONTH_NUMBER:
        return (int(parts[1]), _MONTH_NUMBER[parts[0]])
    return (0, 0)


def talks_for_references(references: list[str], citations_data: dict, limit: int) -> list[dict]:
    """Every citing talk for any of these references, deduplicated by
    URL (the same talk often cites more than one verse under a topic),
    newest first, capped at `limit`."""
    by_url: dict[str, dict] = {}
    for reference in references:
        for citation in citations_data["citations"].get(reference, []):
            by_url.setdefault(citation["url"], citation)
    talks = sorted(by_url.values(), key=_date_sort_key, reverse=True)
    return talks[:limit]


def rebuild(conn) -> None:
    conn.execute("DELETE FROM topic_talks")
    conn.execute("DELETE FROM topic_verses")
    conn.execute("DELETE FROM topics")

    print("Selecting supporting scriptures for each topic...")
    topic_candidates: dict[str, list[dict]] = {}
    all_references: set[str] = set()
    for name, slug, _description, query in TOPICS:
        candidates = fetch_topic_candidates(conn, query, VERSES_PER_TOPIC)
        topic_candidates[slug] = candidates
        all_references.update(c["reference"] for c in candidates)
        print(f"  {name}: {len(candidates)} verse(s)")

    print()
    print(f"Harvesting talk citations for {len(all_references)} referenced verse(s)...")
    citations_data = load_citations()
    book_ids = hc.build_book_id_map()
    harvest_missing_citations(all_references, citations_data, book_ids)
    save_citations(citations_data)

    print()
    print("Writing topics...")
    for sort_order, (name, slug, description, _query) in enumerate(TOPICS, start=1):
        cur = conn.execute(
            "INSERT INTO topics (name, slug, description, sort_order) VALUES (?, ?, ?, ?)",
            (name, slug, description, sort_order),
        )
        topic_id = cur.lastrowid

        candidates = topic_candidates[slug]
        for v_sort_order, candidate in enumerate(candidates, start=1):
            conn.execute(
                "INSERT INTO topic_verses (topic_id, volume_slug, reference, sort_order) "
                "VALUES (?, ?, ?, ?)",
                (topic_id, candidate["volume_slug"], candidate["reference"], v_sort_order),
            )

        talks = talks_for_references(
            [c["reference"] for c in candidates], citations_data, TALKS_PER_TOPIC
        )
        for t_sort_order, talk in enumerate(talks, start=1):
            conn.execute(
                "INSERT INTO topic_talks (topic_id, talk_title, speaker, date, url, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    topic_id,
                    talk["talk_title"],
                    talk["speaker"],
                    talk["date"],
                    talk["url"],
                    t_sort_order,
                ),
            )
        print(f"  {name}: {len(candidates)} scripture(s), {len(talks)} talk(s)")

    conn.commit()


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "data" / "scriptures.db"
    conn = connect(db_path)
    rebuild(conn)
    conn.close()
    print()
    print(f"Database written to: {db_path}")


if __name__ == "__main__":
    main()
