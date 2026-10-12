"""Talk Prep: a guided interview that finds scriptures, talks, and
articles for a talk or lesson (ui/talk_prep_dialog.py is the dialog).

It never writes the talk, and the AI never writes anything at all: the
same rule as study_ask.py, which does the real searching. Each step only
narrows what to search for:

1. Topic, meeting, and length (the length sets how many results), and for
   a lesson, what it's based on - this week's Come Follow Me reading, a
   scripture block, or a manual lesson's title.
2. An assigned talk or article, if there is one: picked from the 15,000
   the app knows (citations.py - title, speaker, date, and cited verses
   only; the app has no talk text), with an optional passage the user
   pastes from it.
3. A direction: DirectionFinder searches broadly and the chat model picks
   a few distinct themes from what it found (talk and article titles,
   Topical Guide topics) - picked, not written. Plus the user's own
   impressions, and which sources to include.
4. Results, from study_ask.StudyQuestionAsker with this interview's
   options: capped by talk length, in the user's standing order (Standard
   Works, Conference talks, Ensign/Liahona, the rest), with the verses an
   assigned talk cites or a lesson's reading always among the candidates.
   KeyVerseFinder then picks each passage's key verse by meaning (the
   verse whose embedding is closest to the question's), and the
   strongest few lead the results.

The context ("a 10-minute sacrament meeting talk") goes to the chat model
only, never into retrieval - see study_ask.selection_messages.

Sessions are kept in the talk_prep_sessions table so a preparation can be
reopened during the week, and sync between devices only when the user
turns that on (TALK_PREP_SYNC_SETTING - see sync.py).
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import date

from PySide6.QtCore import QObject, Signal

from scriptures import study_index
from scriptures.ai_client import AiConfig, ChatRequest, numbers_schema
from scriptures.citations import Citation, CitingWork, iter_citing_works
from scriptures.data_access import get_journal_entry, get_setting, save_journal_entry
from scriptures.embeddings import EmbeddingRequest, QueryEmbedder
from scriptures.study_ask import (
    STANDARD_WORKS,
    StudyQuestionAsker,
    StudyResult,
    StudySearch,
    _VectorLoader,
    snippet_keywords,
)
from scriptures.sync import TALK_PREP_SYNC_SETTING

BANNER = (
    "This helper finds scriptures, talks, and articles - it won't write your talk. "
    "Rely on the Holy Ghost, and prayerfully ask the Lord for help as you prepare."
)

MEETINGS = (
    "Sacrament meeting",
    "Stake conference",
    "Youth",
    "Primary",
    "Lesson (Relief Society, elders quorum, Sunday School)",
)
LESSON_MEETING = MEETINGS[-1]

# Talk length in minutes -> at most this many results. A lesson or "not
# sure" gets DEFAULT_RESULTS.
RESULTS_BY_LENGTH = {5: 5, 10: 8, 15: 12, 20: 15}
DEFAULT_RESULTS = 8
KEY_VERSES_SHOWN = 3

LESSON_SOURCES = ("cfm", "block", "manual", "none")

# The "Preferred sources" checkboxes -> what study_ask searches.
SOURCE_OPTIONS = (
    ("book-of-mormon", "Book of Mormon"),
    ("bible", "Bible (and the JST)"),
    ("dc-pgp", "Doctrine and Covenants, Pearl of Great Price"),
    ("talks", "General Conference talks"),
    ("articles", "Ensign/Liahona articles"),
    ("other", "Other: Topical Guide, Journal of Discourses, your notes"),
)
_SOURCE_VOLUMES = {
    "book-of-mormon": {"book-of-mormon"},
    "bible": {"holy-bible", "inspired-version"},
    "dc-pgp": {"doctrine-and-covenants", "pearl-of-great-price"},
}
_OTHER_GROUPS = frozenset(
    {"lectures_on_faith", "apocrypha", "other_ancient_texts", "other", "lexicon"}
)

# How many verses an assigned talk cites that are offered as candidates.
MAX_PINNED_CITED = 8
# How many of a lesson's reading's best passages are offered.
MAX_PINNED_READING = 5
MAX_READING_PER_CHAPTER = 2

# Citation consensus (consensus_hits): how many matching talks and articles
# to read, how many must cite a verse, how many passages to offer.
# 25, with the closest-matching counting more: with 40 counted equally,
# Easter talks (close to "Second Coming of Christ" by meaning) brought in
# the empty tomb; with 20, a direction's own drift took over.
CONSENSUS_WORKS = 25
CONSENSUS_MIN_WORKS = 2
CONSENSUS_PASSAGES = 10
# A work citing up to this many verses counts fully for each; one citing
# more counts for less per verse (by the square root).
CONSENSUS_FULL_WEIGHT_REFERENCES = 15
CONSENSUS_MAX_PASSAGE = 6  # verses - longer runs split into separate passages


# Directions: how many themes are offered, chosen from how many found.
DIRECTIONS_SHOWN = 4
# How many found themes the chat model picks from - enough to choose
# distinct ones, few enough for a small model to read.
MAX_THEME_CANDIDATES = 16
DIRECTION_PROMPT = (
    "Someone is preparing a talk or lesson. You'll get their topic and a "
    "numbered list of themes found in the Church's talks, articles, and "
    f"Topical Guide. Choose up to {DIRECTIONS_SHOWN} that fit the topic and "
    "are clearly different from each other - distinct directions the talk "
    "could take. Reply with ONLY JSON listing their numbers, best first, "
    'e.g. {"numbers": [3, 7, 1]}. Use only numbers from the list.'
)


@dataclass
class Interview:
    topic: str = ""
    meeting: str = MEETINGS[0]
    length: int | None = None  # minutes; None = not sure
    lesson_source: str = "none"  # one of LESSON_SOURCES
    lesson_text: str = ""  # the reading block, or the manual lesson's title
    talk_url: str = ""
    talk_title: str = ""
    talk_passage: str = ""
    directions: list[str] = field(default_factory=list)
    impressions: str = ""
    sources: list[str] = field(default_factory=lambda: [key for key, _ in SOURCE_OPTIONS])

    @property
    def is_lesson(self) -> bool:
        return self.meeting == LESSON_MEETING

    @property
    def result_limit(self) -> int:
        if self.is_lesson or self.length is None:
            return DEFAULT_RESULTS
        return RESULTS_BY_LENGTH.get(self.length, DEFAULT_RESULTS)

    def context(self) -> str:
        """For the chat model only - see the module docstring."""
        if self.is_lesson:
            what = "a lesson (Relief Society, elders quorum, or Sunday School)"
            if self.lesson_source in ("cfm", "block") and self.lesson_text:
                what += f" on {self.lesson_text}"
            elif self.lesson_source == "manual" and self.lesson_text:
                what += f' from the manual lesson "{self.lesson_text}"'
        else:
            minutes = f"{self.length}-minute " if self.length else ""
            audience = {
                "Youth": "talk for the youth",
                "Primary": "talk for Primary children",
                "Stake conference": "stake conference talk",
            }.get(self.meeting, "sacrament meeting talk")
            what = f"a {minutes}{audience}"
        line = f"They are preparing {what}."
        if self.talk_title:
            line += f' They were asked to speak about the talk "{self.talk_title}".'
        return line

    def questions(self) -> list[str]:
        """What to search for: the topic first, then each refinement -
        study_ask.retrieval_query drops any with nothing to search for."""
        first = self.topic.strip()
        if self.is_lesson and self.lesson_source == "manual" and self.lesson_text.strip():
            first = f"{first} {self.lesson_text.strip()}".strip()
        result = [first or self.talk_title or self.lesson_text]
        if self.talk_title and self.talk_title not in result[0]:
            result.append(self.talk_title)
        if self.talk_passage.strip():
            result.append(self.talk_passage.strip()[:500])
        result.extend(d for d in self.directions if d)
        if self.impressions.strip():
            result.append(self.impressions.strip()[:500])
        return [q for q in result if q]

    def volumes(self) -> set[str] | None:
        """The Standard Works volumes to search, or None for all of them."""
        chosen: set[str] = set()
        for key, slugs in _SOURCE_VOLUMES.items():
            if key in self.sources:
                chosen |= slugs
        return None if chosen >= STANDARD_WORKS else chosen

    def skip_groups(self) -> frozenset[str]:
        skip = set()
        if "talks" not in self.sources:
            skip.add("talks")
        if "articles" not in self.sources:
            skip.add("articles")
        if "other" not in self.sources:
            skip |= _OTHER_GROUPS
        if not any(key in self.sources for key in _SOURCE_VOLUMES):
            skip |= {"standard_works", "cross_references"}
        return frozenset(skip)

    def title(self) -> str:
        return self.topic.strip() or self.talk_title or self.lesson_text or "Talk preparation"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Interview:
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


# ---------------------------------------------------------------------
# Talks and articles - the assigned-talk picker
# ---------------------------------------------------------------------

_works_cache: list[CitingWork] | None = None
_citing_counts: dict[str, int] | None = None


def all_works() -> list[CitingWork]:
    global _works_cache
    if _works_cache is None:
        _works_cache = sorted(iter_citing_works(), key=lambda w: w.date, reverse=True)
    return _works_cache


def _is_reprint(work: CitingWork, conference: set[tuple[str, str]]) -> bool:
    return work.source_label != "General Conference" and (
        work.talk_title.strip().lower(), work.speaker.strip().lower()
    ) in conference


def find_works(query: str, limit: int = 50) -> list[CitingWork]:
    """Talks and articles whose title or speaker contains every word typed -
    leaving out Ensign/Liahona reprints of Conference talks, so each talk
    is listed once."""
    words = [w for w in re.findall(r"[\w']+", query.lower()) if w]
    if not words:
        return []
    conference = {
        (w.talk_title.strip().lower(), w.speaker.strip().lower())
        for w in all_works()
        if w.source_label == "General Conference"
    }
    found = []
    for work in all_works():
        if _is_reprint(work, conference):
            continue
        haystack = f"{work.talk_title} {work.speaker}".lower()
        if all(word in haystack for word in words):
            found.append(work)
            if len(found) >= limit:
                break
    return found


def citing_counts() -> dict[str, int]:
    """How many of all the talks and articles cite each verse."""
    global _citing_counts
    if _citing_counts is None:
        counts: dict[str, int] = {}
        for work in all_works():
            for reference in set(work.references):
                counts[reference] = counts.get(reference, 0) + 1
        _citing_counts = counts
    return _citing_counts


def work_by_url(url: str) -> CitingWork | None:
    return next((w for w in all_works() if w.url == url), None)


def volume_slug(conn: sqlite3.Connection, result: StudyResult) -> str | None:
    if result.chapter_id is None:
        return None
    row = conn.execute(
        "SELECT vol.slug FROM chapters c JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id "
        "WHERE c.id = ?",
        (result.chapter_id,),
    ).fetchone()
    return row[0] if row else None


def is_standard_works(conn: sqlite3.Connection, result: StudyResult) -> bool:
    """A passage from the Standard Works - not Lectures on Faith, the
    Apocrypha, or Other Ancient Texts, which are listed under "Also"."""
    return result.kind == "scripture" and volume_slug(conn, result) in STANDARD_WORKS


JST = "inspired-version"


def label_jst(conn: sqlite3.Connection, results: list[StudyResult]) -> list[StudyResult]:
    """A Joseph Smith Translation passage shares the Bible's book names but
    not always its numbering - JST Matthew 3:6 is the King James Matthew
    2:6 - so unlabeled it looks like the wrong verse."""
    return [
        dataclasses.replace(r, title=f"JST {r.title}")
        if r.kind == "scripture" and not r.title.startswith("JST") and volume_slug(conn, r) == JST
        else r
        for r in results
    ]


def drop_unrelated_words(results: list[StudyResult], topic: str) -> list[StudyResult]:
    """An original-language word only when it's about the topic - its
    meaning or renderings mention one of the topic's words. (gemma3-4b
    offered the Hebrew word for "drink" for a lesson on faith.)"""
    words = set(snippet_keywords(topic))
    if not words:
        return results
    kept = []
    for result in results:
        if result.kind == "lexicon":
            found = set(re.findall(r"[a-z']+", f"{result.title} {result.detail}".lower()))
            stems = {w[:6] for w in found}
            if not any(w in found or w[:6] in stems for w in words):
                continue
        kept.append(result)
    return kept


def prefer_conference_talks(results: list[StudyResult]) -> list[StudyResult]:
    """An Ensign/Liahona article that reprints a General Conference talk
    (the May and November issues carry each Conference) becomes that talk -
    a talk is what someone preparing one wants to cite - and isn't listed
    twice if the talk is already there."""
    conference = {
        (w.talk_title.strip().lower(), w.speaker.strip().lower()): w
        for w in all_works()
        if w.source_label == "General Conference"
    }
    by_url = {w.url: w for w in all_works()}
    updated: list[StudyResult] = []
    urls: set[str] = set()
    for result in results:
        work = by_url.get(result.url or "")
        if result.kind == "article" and work is not None:
            talk = conference.get((work.talk_title.strip().lower(), work.speaker.strip().lower()))
            if talk is not None:
                byline = ", ".join(part for part in (talk.speaker, talk.date) if part)
                result = dataclasses.replace(
                    result,
                    kind="talk",
                    title=f'{talk.source_label}: "{talk.talk_title}"' + (f" - {byline}" if byline else ""),
                    url=talk.url,
                )
        if result.url and result.url in urls:
            continue
        if result.url:
            urls.add(result.url)
        updated.append(result)
    order = {"scripture": 0, "talk": 1, "article": 2}
    return sorted(updated, key=lambda r: order.get(r.kind, 3) if r.kind != "scripture" or r.verse_start else 3)


# ---------------------------------------------------------------------
# Candidates that always reach the chat model
# ---------------------------------------------------------------------


def _passage_hit(
    conn: sqlite3.Connection, chapter_id: int, start: int, end: int, label: str, key: str
) -> study_index.SearchHit | None:
    row = conn.execute(
        "SELECT b.name, c.chapter_number, vol.slug FROM chapters c JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id WHERE c.id = ?",
        (chapter_id,),
    ).fetchone()
    if row is None:
        return None
    book, chapter, slug = row[0], row[1], row[2]
    texts = [
        r[0]
        for r in conn.execute(
            "SELECT text FROM verses WHERE chapter_id = ? AND verse_number BETWEEN ? AND ? ORDER BY verse_number",
            (chapter_id, start, end),
        )
    ]
    if not texts:
        return None
    verses = f"{start}" if start == end else f"{start}-{end}"
    reference = f"{book} {chapter}:{verses}"
    return study_index.SearchHit(
        piece_id=0,
        key=key,
        kind="scripture",
        text=f"{reference}\n{' '.join(texts)}",
        volume_slug=slug,
        chapter_id=chapter_id,
        meta={
            "reference": reference, "book": book, "chapter": chapter,
            "verse_start": start, "verse_end": end, "pinned_label": label,
        },
        score=0.0,
        semantic_rank=None,
        keyword_rank=None,
    )


def cited_verse_hits(conn: sqlite3.Connection, work: CitingWork) -> list[study_index.SearchHit]:
    """The verses an assigned talk cites, as candidates - consecutive
    verses of one chapter joined into one passage. Only the Standard Works
    (the citation index covers nothing else)."""
    located: list[tuple[int, int]] = []
    for reference in work.references:
        row = conn.execute(
            "SELECT v.chapter_id, v.verse_number FROM verses v JOIN chapters c ON c.id = v.chapter_id "
            "JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id "
            "WHERE v.reference = ? ORDER BY vol.sort_order LIMIT 1",
            (reference,),
        ).fetchone()
        if row is not None:
            located.append((row[0], row[1]))
    passages: list[list[int]] = []  # [chapter_id, start, end]
    for chapter_id, verse in sorted(set(located)):
        if passages and passages[-1][0] == chapter_id and verse == passages[-1][2] + 1:
            passages[-1][2] = verse
        else:
            passages.append([chapter_id, verse, verse])
    hits = []
    for chapter_id, start, end in passages[:MAX_PINNED_CITED]:
        hit = _passage_hit(
            conn, chapter_id, start, end, "cited in the assigned talk", f"cited:{chapter_id}:{start}-{end}"
        )
        if hit is not None:
            hits.append(hit)
    return hits


_BLOCK_PART_RE = re.compile(r"^\s*(?P<book>(?:\d\s+)?[A-Za-z][A-Za-z .&']*?)?\s*(?P<range>\d+(?:\s*[-–]\s*\d+)?)\s*$")


def parse_reading_block(conn: sqlite3.Connection, block: str) -> list[int]:
    """Chapter ids for a reading like "Isaiah 13-14; 22; 24-30; 35" or
    "Alma 32-35" - a book name carries over to the parts after it. Parts
    that don't resolve are skipped."""
    chapter_ids: list[int] = []
    book: str | None = None
    for part in re.split(r"[;,]", block):
        match = _BLOCK_PART_RE.match(part)
        if not match:
            continue
        if match["book"]:
            book = _resolve_book(conn, match["book"].strip())
        if book is None:
            continue
        first, _, last = match["range"].replace("–", "-").partition("-")
        start, end = int(first), int(last or first)
        for row in conn.execute(
            "SELECT c.id FROM chapters c JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id "
            "WHERE b.name = ? AND c.chapter_number BETWEEN ? AND ? AND vol.slug != 'inspired-version' "
            "ORDER BY c.chapter_number",
            (book, start, min(end, start + 60)),
        ):
            if row[0] not in chapter_ids:
                chapter_ids.append(row[0])
    return chapter_ids


def _resolve_book(conn: sqlite3.Connection, name: str) -> str | None:
    aliases = {"d&c": "Doctrine and Covenants", "dc": "Doctrine and Covenants", "jsh": "Joseph Smith—History"}
    name = aliases.get(name.lower(), name)
    row = conn.execute("SELECT name FROM books WHERE lower(name) = lower(?) LIMIT 1", (name,)).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT name FROM books WHERE lower(name) LIKE lower(?) ORDER BY length(name) LIMIT 1", (f"{name}%",)
        ).fetchone()
    return row[0] if row else None


def reading_hits(
    conn: sqlite3.Connection,
    index: study_index.StudyIndex,
    chapter_ids: list[int],
    query: str,
    vector: list[float] | None,
) -> list[study_index.SearchHit]:
    """The lesson reading's passages that best match the topic - searched
    within the reading itself (a search of all scripture, filtered to the
    reading afterwards, missed Isaiah 61:1-3 for "Messiah" in Isaiah
    58-66), at most MAX_READING_PER_CHAPTER from any one chapter."""
    pieces = index.pieces_in_chapters(set(chapter_ids))
    if not pieces:
        return []
    hits = index.search(query, vector, kinds={"scripture"}, limit=MAX_PINNED_READING * 3, piece_ids=pieces)
    chosen: list[study_index.SearchHit] = []
    per_chapter: dict[int, int] = {}
    for hit in hits:
        if per_chapter.get(hit.chapter_id, 0) >= MAX_READING_PER_CHAPTER:
            continue
        per_chapter[hit.chapter_id] = per_chapter.get(hit.chapter_id, 0) + 1
        hit.meta["pinned_label"] = "from the lesson's reading"
        # Only the best match is favored outright (so the reading is
        # always represented); the rest are offered to the chat model.
        # Favoring them all put Isaiah 66:19-24 first for "Messiah".
        if chosen:
            hit.meta["offer_only"] = True
        chosen.append(hit)
        if len(chosen) >= MAX_PINNED_READING:
            break
    return chosen


def consensus_hits(
    conn: sqlite3.Connection,
    index: study_index.StudyIndex,
    query: str,
    vector: list[float] | None,
    volumes: set[str] | None = None,
    chapter_ids: set[int] | None = None,
) -> list[study_index.SearchHit]:
    """The verses Church leaders reach for on this topic: the talks and
    articles that best match it, and the verses they cite - weighed, as
    a search engine weighs words (TF-IDF), by how much more often talks on
    this topic cite a verse than all talks do. Consecutive verses are
    joined into one passage, best first.

    The weighing matters: counting citations alone, the First Vision, D&C
    76:22-24, 2 Nephi 25:26, and 3 Nephi 11 - cited in talks on nearly
    everything - topped "Second Coming", ahead of Matthew 24-25 and D&C 45.

    This, not the chat model's judgment, is what keeps results to what a
    reader would expect. Tested on four topics, it found D&C 121:7-8 and
    122:7-8 for adversity, D&C 19:16-18 and Alma 7:11-12 for the
    Atonement, Isaiah 9:6 for the Messiah; gemma3-4b, asked to filter
    results itself, dropped D&C 19:16 and kept Matthew 3:2 for "Messiah".

    A verse needs CONSENSUS_MIN_WORKS works citing it. A work that cites
    many verses counts for less per verse - a study guide citing a whole
    book shouldn't outvote three talks. A Conference talk and its
    Ensign/Liahona reprint count once. `chapter_ids` keeps only verses in
    those chapters (a lesson's reading)."""
    # By meaning alone when there's an embedding: matching titles by word
    # brought in articles about the book of Revelation for "personal
    # revelation", and with them Revelation 7.
    works = index.search("" if vector is not None else query, vector, kinds={"talk", "article"}, limit=CONSENSUS_WORKS)
    weights: dict[str, float] = {}
    counts: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for rank, hit in enumerate(works):
        work = work_by_url(hit.meta.get("url", ""))
        if work is None or not work.references:
            continue
        identity = (work.talk_title.strip().lower(), work.speaker.strip().lower())
        if identity in seen:
            continue
        seen.add(identity)
        weight = 1.0 / max(1.0, (len(work.references) / CONSENSUS_FULL_WEIGHT_REFERENCES) ** 0.5)
        weight /= math.sqrt(rank + 1)  # the closest-matching talks count most
        for reference in set(work.references):
            weights[reference] = weights.get(reference, 0.0) + weight
            counts[reference] = counts.get(reference, 0) + 1

    located: dict[tuple[int, int], tuple[float, int]] = {}  # (chapter_id, verse) -> (weight, works)
    for reference, works_citing in counts.items():
        if works_citing < CONSENSUS_MIN_WORKS:
            continue
        row = conn.execute(
            "SELECT v.chapter_id, v.verse_number, vol.slug FROM verses v JOIN chapters c ON c.id = v.chapter_id "
            "JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id "
            "WHERE v.reference = ? AND vol.slug != 'inspired-version' ORDER BY vol.sort_order LIMIT 1",
            (reference,),
        ).fetchone()
        if row is None or row[2] not in STANDARD_WORKS:
            continue
        if volumes is not None and row[2] not in volumes:
            continue
        if chapter_ids is not None and row[0] not in chapter_ids:
            continue
        everywhere = citing_counts().get(reference, works_citing)
        rarity = math.log(len(all_works()) / max(everywhere, 1))
        located[(row[0], row[1])] = (weights[reference] * rarity, works_citing)

    passages: list[list] = []  # [chapter_id, start, end, weight, works]
    for (chapter_id, verse), (weight, works_citing) in sorted(located.items()):
        last = passages[-1] if passages else None
        if last and last[0] == chapter_id and verse == last[2] + 1 and verse - last[1] < CONSENSUS_MAX_PASSAGE:
            last[2] = verse
            last[3] = max(last[3], weight)
            last[4] = max(last[4], works_citing)
        else:
            passages.append([chapter_id, verse, verse, weight, works_citing])
    passages.sort(key=lambda p: p[3], reverse=True)

    hits = []
    for chapter_id, start, end, _weight, works_citing in passages[:CONSENSUS_PASSAGES]:
        hit = _passage_hit(
            conn, chapter_id, start, end, f"cited in {works_citing} talks and articles on this topic",
            f"consensus:{chapter_id}:{start}-{end}",
        )
        if hit is not None:
            hit.meta["consensus"] = works_citing
            hits.append(hit)
    return hits


# ---------------------------------------------------------------------
# Directions
# ---------------------------------------------------------------------


def direction_messages(topic: str, themes: list[str]) -> list[dict]:
    listing = "\n".join(f"{n}. {theme}" for n, theme in enumerate(themes, start=1))
    return [
        {"role": "system", "content": DIRECTION_PROMPT},
        {"role": "user", "content": f"Topic: {topic}\n\nThemes:\n{listing}"},
    ]


def parse_directions(content: str, count: int) -> list[int] | None:
    match = re.search(r"\[[^\[\]]*\]", content)
    if not match:
        return None
    try:
        values = json.loads(match.group(0))
    except ValueError:
        return None
    chosen: list[int] = []
    for value in values if isinstance(values, list) else []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= count and number - 1 not in chosen:
            chosen.append(number - 1)
    return chosen[:DIRECTIONS_SHOWN] or None


_THEME_STOPWORDS = frozenset(
    "a an and the of to in on for our your my his her their is are be we you i it with "
    "by from as at that this how why what who when not no can will".split()
)


def _theme_words(text: str) -> set[str]:
    return {
        re.sub(r"(?:'s|s)$", "", w)
        for w in re.findall(r"[a-z']+", text.lower())
        if w not in _THEME_STOPWORDS
    }


def themes_from_hits(hits: list[study_index.SearchHit], topic: str = "") -> list[str]:
    """Candidate directions: talk and article titles and Topical Guide
    topic names - each once, and only ones that add something to the
    topic: "Repentance" alone, for a talk on repentance, isn't a
    direction, and neither is a second title made of the same words as one
    already listed (in testing, all four directions offered for
    "repentance" were "Repentance..." titles)."""
    topic_words = _theme_words(topic)
    themes: list[str] = []
    kept_words: list[set[str]] = []
    seen: set[str] = set()
    for hit in hits:
        if hit.kind in ("talk", "article"):
            theme = hit.meta.get("title", "")
        elif hit.kind == "topic":
            theme = hit.text.partition("\n")[0].removeprefix("Topical Guide: ")
        else:
            continue
        theme = theme.strip().strip('"“”').strip()
        if not theme or theme.lower() in seen:
            continue
        seen.add(theme.lower())
        words = _theme_words(theme) - topic_words
        if not words:
            continue
        if any(len(words & other) * 2 >= min(len(words), len(other)) for other in kept_words):
            continue
        kept_words.append(words)
        themes.append(theme)
    return themes


class DirectionFinder(QObject):
    """Step 3's choices. `ready(themes, vector)` fires once - the themes to
    offer (possibly fewer than DIRECTIONS_SHOWN, or none), and the topic's
    embedding (None if that failed), kept for the reading search later."""

    ready = Signal(list, object)

    def __init__(
        self,
        study: StudySearch,
        chat_config: AiConfig,
        interview: Interview,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._study = study
        self._chat_config = chat_config
        self._interview = interview
        self._query = " ".join(interview.questions()[:2])
        self._vector: list[float] | None = None
        self._embedded = False
        self._loaded = study.index.is_loaded()
        self._themes: list[str] = []

        self._embedder = QueryEmbedder(
            study.embedding_config, study.embedding_config.model, self._query, study.embedding_dimensions, self
        )
        self._embedder.ready.connect(self._on_embedded)
        self._embedder.failed.connect(lambda _message: self._on_embedded(None))
        if not self._loaded:
            self._loader = _VectorLoader(self)
            self._loader.done.connect(self._on_loaded)
            self._loader.start(study.index_path)

    def _on_loaded(self, arrays) -> None:
        if not isinstance(arrays, Exception):
            self._study.index.adopt_arrays(arrays)
        self._loaded = True
        self._maybe_search()

    def _on_embedded(self, vector) -> None:
        self._vector = vector
        self._embedded = True
        self._maybe_search()

    def _maybe_search(self) -> None:
        if not (self._embedded and self._loaded):
            return
        index = self._study.index
        vector = self._vector if index.is_loaded() else None
        hits = []
        for kinds, limit in (({"talk"}, 16), ({"article"}, 10), ({"topic"}, 4)):
            hits.extend(index.search(self._query, vector, kinds=kinds, limit=limit))
        assigned = self._interview.talk_title.strip().lower()
        self._themes = [
            t for t in themes_from_hits(hits, self._interview.topic) if t.lower() != assigned
        ][:MAX_THEME_CANDIDATES]
        if len(self._themes) <= DIRECTIONS_SHOWN:
            self.ready.emit(self._themes, self._vector)
            return
        self._request = ChatRequest(
            self._chat_config,
            direction_messages(self._interview.topic or self._query, self._themes),
            schema=numbers_schema(len(self._themes)),
            parent=self,
        )
        self._request.finished.connect(self._on_reply)

    def _on_reply(self, content: str | None, _message: str, _needs_key: bool) -> None:
        chosen = parse_directions(content, len(self._themes)) if content is not None else None
        if chosen is None:  # the index's own order instead
            chosen = list(range(min(DIRECTIONS_SHOWN, len(self._themes))))
        self.ready.emit([self._themes[i] for i in chosen], self._vector)


# ---------------------------------------------------------------------
# The search itself
# ---------------------------------------------------------------------


def trusted_passages(
    conn: sqlite3.Connection,
    index: study_index.StudyIndex,
    interview: Interview,
    vector: list[float] | None,
) -> list[study_index.SearchHit]:
    """Passages the results favor, most trusted first (see
    study_ask.balance_for_talk_prep): an assigned talk's cited verses; a
    lesson's reading - what talks on the topic cite from it, then its best
    match; then what talks on the topic cite anywhere. The last always,
    even with talks left out of the results: what they cite is the best
    guide to the verses a reader would expect."""
    query = " ".join(interview.questions())
    volumes = interview.volumes()
    passages: list[study_index.SearchHit] = []
    if interview.talk_url:
        work = work_by_url(interview.talk_url)
        if work is not None:
            passages += cited_verse_hits(conn, work)
    if interview.is_lesson and interview.lesson_source in ("cfm", "block") and interview.lesson_text:
        chapters = parse_reading_block(conn, interview.lesson_text)
        passages += consensus_hits(conn, index, query, vector, volumes, set(chapters))
        passages += reading_hits(conn, index, chapters, query, vector)
    passages += consensus_hits(conn, index, query, vector, volumes)
    return passages


class TalkPrepSearch(QObject):
    """Step 4's search, start to finish, short of key verses - shared by
    the dialog and scripts/eval_talk_prep.py, so the benchmark measures
    exactly what users get. `succeeded(results, note, query_vector)` or
    `failed(message, needs_api_key)` fires once."""

    succeeded = Signal(list, str, object)
    failed = Signal(str, bool)

    def __init__(
        self,
        conn: sqlite3.Connection,
        study: StudySearch,
        chat_config: AiConfig,
        interview: Interview,
        fallback_vector: list[float] | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self._study = study
        self._chat_config = chat_config
        self._interview = interview
        self._asker = None
        # The whole query - topic, direction, impressions - embedded for the
        # citation search: the topic alone ("Second Coming") matched talks
        # about Christ in general, and with them the First Vision.
        self._embedder = QueryEmbedder(
            study.embedding_config,
            study.embedding_config.model,
            " ".join(interview.questions()),
            study.embedding_dimensions,
            self,
        )
        self._embedder.ready.connect(self._search_with)
        self._embedder.failed.connect(lambda _message: self._search_with(fallback_vector))

    def _search_with(self, vector) -> None:
        study, interview = self._study, self._interview
        self._asker = StudyQuestionAsker(
            self.conn,
            study.index,
            study.index_path,
            self._chat_config,
            study.embedding_config,
            study.embedding_dimensions,
            interview.questions(),
            self,
            max_selected=interview.result_limit,
            cap_total=True,
            context=interview.context(),
            volumes=interview.volumes(),
            skip_groups=interview.skip_groups(),
            pinned=trusted_passages(self.conn, study.index, interview, vector),
        )
        self._asker.succeeded.connect(self._on_results)
        self._asker.failed.connect(self.failed)

    def _on_results(self, results: list, note: str) -> None:
        tidy = label_jst(
            self.conn, drop_unrelated_words(prefer_conference_talks(results), self._interview.topic)
        )
        self.succeeded.emit(tidy, note, self._asker.query_vector)


# ---------------------------------------------------------------------
# Key verses
# ---------------------------------------------------------------------


def passage_verses(conn: sqlite3.Connection, result: StudyResult) -> list[tuple[int, str]]:
    if result.kind != "scripture" or result.chapter_id is None or result.verse_start is None:
        return []
    return [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT verse_number, text FROM verses WHERE chapter_id = ? AND verse_number BETWEEN ? AND ? "
            "ORDER BY verse_number",
            (result.chapter_id, result.verse_start, result.verse_end),
        )
    ]


def keyword_key_verse(verses: list[tuple[int, str]], question: str) -> int | None:
    """The fallback when embeddings aren't available: the verse sharing
    the most of the question's words (the first, on a tie)."""
    if not verses:
        return None
    words = set(snippet_keywords(question))
    best, best_score = verses[0][0], -1
    for number, text in verses:
        found = set(re.findall(r"[a-z']+", text.lower()))
        score = len(words & found)
        if score > best_score:
            best, best_score = number, score
    return best


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


class KeyVerseFinder(QObject):
    """Sets each scripture result's key_verse. `done(results)` fires once,
    with every result - by meaning when the embedding endpoint answers, by
    shared words otherwise."""

    done = Signal(list)

    def __init__(
        self,
        conn: sqlite3.Connection,
        study: StudySearch,
        results: list[StudyResult],
        question: str,
        query_vector: list[float] | None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._results = list(results)
        self._question = question
        self._vector = query_vector
        self._verses = {i: passage_verses(conn, r) for i, r in enumerate(self._results)}
        self._texts: list[tuple[int, int, str]] = [  # (result index, verse number, text)
            (i, number, text) for i, verses in self._verses.items() if len(verses) > 1 for number, text in verses
        ]
        self._study = study

    def start(self) -> None:
        if self._vector is None or not self._texts:
            self._finish(None)
            return
        fmt = study_index.embedding_format(self._study.embedding_config.model)
        documents = [fmt.format_document(self._results[i].title, text) for i, _n, text in self._texts]
        self._request = EmbeddingRequest(
            self._study.embedding_config,
            self._study.embedding_config.model,
            documents,
            self._study.embedding_dimensions,
            self,
        )
        self._request.succeeded.connect(self._finish)
        self._request.failed.connect(lambda *_args: self._finish(None))

    def _finish(self, vectors: list | None) -> None:
        best: dict[int, tuple[float, int]] = {}
        if vectors is not None and len(vectors) == len(self._texts):
            for (i, number, _text), vector in zip(self._texts, vectors):
                score = _cosine(self._vector, vector)
                if i not in best or score > best[i][0]:
                    best[i] = (score, number)
        updated = []
        for i, result in enumerate(self._results):
            verses = self._verses[i]
            if not verses:
                updated.append(result)
                continue
            key = best[i][1] if i in best else (verses[0][0] if len(verses) == 1 else keyword_key_verse(verses, self._question))
            updated.append(dataclasses.replace(result, key_verse=key))
        self.done.emit(updated)


def key_verses(conn: sqlite3.Connection, results: list[StudyResult], count: int = KEY_VERSES_SHOWN) -> list[tuple[str, str]]:
    """(reference, text) of the first `count` scripture results' key verses -
    the "Key verses" the results lead with."""
    found = []
    for result in results:
        if result.key_verse is None or not is_standard_works(conn, result):
            continue
        row = conn.execute(
            "SELECT reference, text FROM verses WHERE chapter_id = ? AND verse_number = ?",
            (result.chapter_id, result.key_verse),
        ).fetchone()
        if row is not None:
            reference = f"JST {row[0]}" if volume_slug(conn, result) == JST else row[0]
            found.append((reference, row[1]))
        if len(found) >= count:
            break
    return found


# ---------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------


@dataclass
class Session:
    uid: str
    interview: Interview
    results: list[StudyResult]
    note: str = ""
    updated_at: str = ""
    id: int | None = None

    @property
    def title(self) -> str:
        return self.interview.title()


def new_session(interview: Interview) -> Session:
    return Session(uuid.uuid4().hex, interview, [])


def _result_to_dict(result: StudyResult) -> dict:
    return dataclasses.asdict(result)


def _result_from_dict(data: dict) -> StudyResult:
    names = {f.name for f in dataclasses.fields(StudyResult)}
    values = {k: v for k, v in data.items() if k in names}
    values["citations"] = [Citation(**c) for c in values.get("citations", [])]
    return StudyResult(**values)


def save_session(conn: sqlite3.Connection, session: Session) -> None:
    data = json.dumps(
        {
            "interview": session.interview.to_dict(),
            "results": [_result_to_dict(r) for r in session.results],
            "note": session.note,
        }
    )
    existing = conn.execute("SELECT id FROM talk_prep_sessions WHERE uid = ?", (session.uid,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE talk_prep_sessions SET title = ?, data = ?, updated_at = datetime('now'), deleted_at = NULL "
            "WHERE id = ?",
            (session.title, data, existing[0]),
        )
        session.id = existing[0]
    else:
        cursor = conn.execute(
            "INSERT INTO talk_prep_sessions (uid, title, data) VALUES (?, ?, ?)", (session.uid, session.title, data)
        )
        session.id = cursor.lastrowid
    conn.commit()


def _session_from_row(row) -> Session:
    data = json.loads(row["data"])
    return Session(
        uid=row["uid"],
        interview=Interview.from_dict(data.get("interview", {})),
        results=[_result_from_dict(r) for r in data.get("results", [])],
        note=data.get("note", ""),
        updated_at=row["updated_at"],
        id=row["id"],
    )


def list_sessions(conn: sqlite3.Connection, limit: int = 20) -> list[Session]:
    rows = conn.execute(
        "SELECT * FROM talk_prep_sessions WHERE deleted_at IS NULL ORDER BY updated_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    sessions = []
    for row in rows:
        try:
            sessions.append(_session_from_row(row))
        except (ValueError, TypeError, KeyError):
            continue  # a damaged row isn't worth failing the whole list over
    return sessions


def delete_session(conn: sqlite3.Connection, uid: str) -> None:
    """Soft delete (tombstone) so a synced device learns of it - see sync.py."""
    conn.execute(
        "UPDATE talk_prep_sessions SET deleted_at = datetime('now'), updated_at = datetime('now') WHERE uid = ?",
        (uid,),
    )
    conn.commit()


def sync_enabled(conn: sqlite3.Connection) -> bool:
    return get_setting(conn, TALK_PREP_SYNC_SETTING) == "true"


# ---------------------------------------------------------------------
# Output: copy, export, Journal
# ---------------------------------------------------------------------

def sections(conn: sqlite3.Connection, results: list[StudyResult]) -> list[tuple[str, list[StudyResult]]]:
    """The results grouped for display, in the user's standing order."""
    groups: list[tuple[str, list[StudyResult]]] = [
        ("Scriptures", []), ("General Conference talks", []), ("Ensign/Liahona articles", []), ("Also", []),
    ]
    for result in results:
        if is_standard_works(conn, result):
            groups[0][1].append(result)
        elif result.kind == "talk":
            groups[1][1].append(result)
        elif result.kind == "article":
            groups[2][1].append(result)
        else:
            groups[3][1].append(result)
    return [(title, items) for title, items in groups if items]


def describe_meeting(interview: Interview) -> str:
    if interview.is_lesson:
        return "Lesson"
    minutes = f", {interview.length} minutes" if interview.length else ""
    return f"{interview.meeting}{minutes}"


def as_text(conn: sqlite3.Connection, session: Session) -> str:
    """The results as plain text - for Copy, Export, and Save to Journal."""
    interview = session.interview
    lines = [f"Talk Prep: {session.title}", describe_meeting(interview)]
    if interview.talk_title:
        lines.append(f'Assigned: "{interview.talk_title}"')
    if interview.directions:
        lines.append("Direction: " + "; ".join(interview.directions))
    keys = key_verses(conn, session.results)
    if keys:
        lines += ["", "Key verses"]
        lines += [f'- {reference}: "{text}"' for reference, text in keys]
    for heading, items in sections(conn, session.results):
        lines += ["", heading]
        lines += [f"- {_result_line(result)}" for result in items]
    return "\n".join(lines)


def labeled_title(result: StudyResult) -> str:
    """"Topical Guide: Faith" - without doubling a label the title already
    starts with ("Cross-reference: 1 John 1:9 parallels ...")."""
    if result.kind == "scripture" or result.title.startswith(result.kind_label):
        return result.title
    return f"{result.kind_label}: {result.title}"


def _result_line(result: StudyResult) -> str:
    if result.url:
        return f"{result.title} - {result.url}"
    if result.kind == "scripture" and result.key_verse is not None:
        return f"{result.title} (key verse {result.key_verse})"
    return labeled_title(result)


def append_to_journal(conn: sqlite3.Connection, text: str, today: date | None = None) -> None:
    """Adds `text` to today's Journal entry (after whatever's there)."""
    day = (today or date.today()).isoformat()
    entry = get_journal_entry(conn, day)
    if entry is None:
        save_journal_entry(conn, day, text)
        return
    combined = f"{entry.text.rstrip()}\n\n{text}" if entry.text.strip() else text
    save_journal_entry(conn, day, combined, verse_id=entry.verse_id, chapter_id=entry.chapter_id)
