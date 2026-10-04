"""AI-assisted search grounded in the study index (see study_index.py) -
used instead of ask.py's QuestionAsker whenever a study index has been
built.

ask.py asks the chat model to *recall* scripture references and then
checks them, which only works as well as the model's memory: in testing,
a 4B local model asked about "the Land of Bountiful" proposed D&C 138 (the
spirit world), Mosiah 28, Alma 31, and Ether 9 - all real, none relevant.
Here the order is reversed:

1. The study index retrieves candidates for the question by meaning and
   by words - scripture, Journal of Discourses passages, talks and
   articles (by title and the verses they cite), Topical Guide topics,
   cross-references, and the user's notes - with per-kind caps so no one
   kind crowds out the rest.
2. The chat model is shown those numbered candidates and asked only which
   numbers genuinely help, most relevant first - it can't introduce
   anything that isn't already in the list, so it can't invent a source.
3. If the chat model fails, or replies with something unusable, the
   index's own ranking is shown instead, with a note saying so - a chat
   hiccup never means no results.

Every result's text is read back from this app's own data (verse text
from the main database, not the index's copy), never from the model.

Follow-up refinements re-run retrieval on the original question plus the
refinement, and describe both to the model in one message rather than
replaying a chat history - simpler for a small local model to follow.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply

from scriptures import study_index
from scriptures.ai_client import AUTH_ERRORS, AiConfig, build_request
from scriptures.ask import citations_for, extract_keywords
from scriptures.citations import Citation
from scriptures.data_access import get_topic_key_passages
from scriptures.embeddings import QueryEmbedder

MAX_SELECTED = 10
SNIPPET_CHARS = 220

STANDARD_WORKS = frozenset(
    {"holy-bible", "book-of-mormon", "doctrine-and-covenants", "pearl-of-great-price",
     # JST excerpts are part of the published Bible's footnotes/appendix.
     "inspired-version"}
)

# Candidates for the chat model, gathered per group so every group is
# always represented. One mixed search wasn't enough: a talk or article is
# indexed as just its title plus the verses it cites, which scores below a
# passage of real text, so for "eternal marriage" none of the many
# conference talks on it made the top 24 at all. (name, kinds, volumes,
# how many). Sized against scripts/eval_study_index.py --select: with 12
# Standard Works slots (Lectures on Faith sharing them) scripture hit@10
# fell from 81% to 69% - too few good verses reached the model at all.
CANDIDATE_GROUPS = (
    ("standard_works", {"scripture"}, STANDARD_WORKS, 16),
    ("talks", {"talk"}, None, 4),
    ("articles", {"article"}, None, 3),
    # Curated cross-references point straight at the scripture a question
    # is after (and often bring in the right verse when the passage search
    # alone missed it) - their own slots, not shared with the rest below.
    ("cross_references", {"cross_reference", "user_cross_reference"}, None, 3),
    ("lectures_on_faith", {"scripture"}, {"lectures-on-faith"}, 1),
    # The Apocrypha (KJV) - its own small share, so a question it speaks to
    # can find it without crowding out the Standard Works.
    ("apocrypha", {"scripture"}, {"apocrypha"}, 2),
    # 1 Enoch and Jasher - not scripture; one slot, in the last tier.
    ("other_ancient_texts", {"scripture"}, {"other-ancient-texts"}, 1),
    ("other", {"discourse", "topic", "note"}, None, 3),
    # A question about what a word means ("What does Christ mean?") is
    # answered by a lexicon entry ("anointed... the Messiah") the
    # question's own words never mention.
    ("lexicon", {"lexicon"}, None, 3),
)
CANDIDATES = sum(group[3] for group in CANDIDATE_GROUPS)
# Topical Guide key passages (see scripts/build_topic_key_verses.py) added
# to the candidates: from the best-matching topics, the most central few
# of each. They catch the landmark verse a question is really after when
# its wording doesn't match the question's at all - Moroni 10:4 never says
# "Book of Mormon", so "how can I know the Book of Mormon is true" missed
# it entirely by meaning and by words.
KEY_TOPICS = 3
KEY_PASSAGES_PER_TOPIC = 3
# Where key passages go in the candidate list. A small model mostly takes
# the first ten or so items in order - gemma3-4b offered Moroni 10:4-5 at
# #15 for "how to know if the Book of Mormon is true" picked #1-#10 - so
# position decides. Each chosen topic's single most central passage leads
# the list; the rest follow this many of the index's own Standard Works
# candidates. (Putting every key passage first hurt when topics were
# matched by the index - Judgment's "judge not" got picked for that same
# question - but the chat model's own topic choice is far more reliable.)
KEY_PASSAGES_AFTER = 8

# Which topics a question is about is asked of the chat model - picking
# from 61 names is easy even for a small model, unlike recalling verses -
# since matching by meaning chose Judgment and Restoration over Testimony
# for "how can I know the Book of Mormon is true". The index's own topic
# ranking is the fallback when the model's reply isn't usable.
TOPIC_PROMPT = (
    "You match a question to Topical Guide topics. Reply with ONLY a JSON "
    "array of the numbers of the 1 or 2 topics that best fit the question, "
    "most relevant first - e.g. [12] or [12, 40]. If none clearly fit, reply []."
)

# Shown, per tier, when the chat model's selection isn't usable.
FALLBACK_PER_TIER = (4, 2, 1, 1)
# Always shown, per tier, even when the chat model picked none from it:
# General Conference talks and Ensign/Liahona articles are central to
# preparing a talk, and in testing a 4B model sometimes chose none at all
# for "eternal marriage" - a topic covered in dozens of each - despite
# four strong talks among its options.
MIN_PER_TIER = {1: 2, 2: 1}

_KIND_LABELS = {
    "scripture": "Scripture",
    "discourse": "Journal of Discourses",
    "talk": "General Conference talk",
    "article": "Ensign/Liahona article",
    "topic": "Topical Guide",
    "cross_reference": "Cross-reference",
    "user_cross_reference": "Your cross-reference",
    "note": "Your note",
    "lexicon": "Original-language word",
}

SELECTION_PROMPT = (
    "You help someone preparing a talk or lesson find helpful sources in "
    "the scriptures and the Church's own publications. You'll get their "
    "question and a numbered list of passages and sources from this app's "
    "library. Choose the ones that genuinely help with the question, most "
    f"helpful first, at most {MAX_SELECTED}. Reply with ONLY a JSON array "
    "of their numbers - no prose, no markdown, e.g. [4, 1, 9]. Use only "
    "numbers from the list. If none of them fit, reply []."
)


@dataclass(frozen=True)
class StudyResult:
    """One result, ready to show. `chapter_id` (reading view) or
    `topic_id` (Topical Guide) or `url` (a talk/article on
    churchofjesuschrist.org) says where clicking it goes."""

    kind: str
    title: str
    detail: str = ""
    chapter_id: int | None = None
    topic_id: int | None = None
    url: str | None = None
    # A lexicon entry's Strong's number ("H4899") - opens that entry.
    strongs: str | None = None
    citations: list[Citation] = field(default_factory=list)

    @property
    def kind_label(self) -> str:
        return _KIND_LABELS.get(self.kind, self.kind)


# Follow-up phrases that narrow results to certain volumes or kinds of
# source - applied as real search filters (see detect_filters), not left
# to the chat model, which in testing ignored "just the Book of Mormon"
# and kept D&C, Psalms, and Ensign results. Order matters: the JST before
# the Bible, so "Joseph Smith Translation" isn't read as the whole Bible.
_VOLUME_PHRASES = (
    (r"\bbook of mormon\b", {"book-of-mormon"}),
    (r"\bdoctrine and covenants\b|\bd\s*&\s*c\b", {"doctrine-and-covenants"}),
    (r"\bpearl of great price\b", {"pearl-of-great-price"}),
    (r"\bjoseph smith translation\b|\bjst\b", {"inspired-version"}),
    # The index doesn't record testaments, so either one means the Bible.
    (r"\bbible\b|\bold testament\b|\bnew testament\b", {"holy-bible", "inspired-version"}),
    (r"\bjournal of discourses\b", {"journal-of-discourses"}),
    (r"\blectures on faith\b", {"lectures-on-faith"}),
    (r"\bapocrypha\b|\bapocryphal\b", {"apocrypha"}),
    (r"\bbook of enoch\b|\b1 enoch\b|\bjasher\b|\bother ancient texts\b", {"other-ancient-texts"}),
)
_KIND_PHRASES = (
    (r"\bgeneral conference\b|\bconference talks?\b|\btalks\b", {"talk"}),
    (r"\bensign\b|\bliahona\b|\barticles?\b|\bmagazines?\b", {"article"}),
    (r"\btopical guide\b", {"topic"}),
)


# Words that only frame a narrowing request ("just the ... please") -
# not things to search for.
_NARROWING_WORDS = frozenset(
    {"just", "only", "please", "any", "ones", "those", "show", "give", "instead",
     "stick", "limit", "keep", "focus", "filter", "now", "actually", "also"}
)


def _match_filters(text: str) -> tuple[set[str], set[str], str]:
    """(kinds, volume slugs, text with those phrases removed)."""
    lowered = text.lower()
    kinds: set[str] = set()
    volumes: set[str] = set()
    for pattern, slugs in _VOLUME_PHRASES:
        if re.search(pattern, lowered):
            volumes |= slugs
            lowered = re.sub(pattern, " ", lowered)
    for pattern, kind_set in _KIND_PHRASES:
        if re.search(pattern, lowered):
            kinds |= kind_set
            lowered = re.sub(pattern, " ", lowered)
    return kinds, volumes, lowered


def detect_filters(questions: list[str]) -> tuple[set[str] | None, set[str] | None]:
    """(kinds, volume slugs) to restrict the search to, from the most
    recent follow-up that names any - never from the first question, which
    may be *about* a book ("how was the Book of Mormon translated") rather
    than asking to search only within it. A kind wins over a volume when a
    follow-up names both (talks and articles have no volume)."""
    for question in reversed(questions[1:]):
        kinds, volumes, _rest = _match_filters(question)
        if kinds:
            return kinds, None
        if volumes:
            return {"scripture"}, volumes
    return None, None


def tier(hit: study_index.SearchHit) -> int:
    """Display order, by source (the user's chosen ranking): the Standard
    Works, then General Conference talks, then Ensign/Liahona articles,
    then everything else - Journal of Discourses, Lectures on Faith, the
    Apocrypha (D&C 91: "many things contained therein that are true"),
    Other Ancient Texts (1 Enoch, Jasher - not scripture),
    Topical Guide, cross-references, notes. Within a tier, the chat
    model's (or the index's) order is kept."""
    if hit.kind == "scripture" and hit.volume_slug in STANDARD_WORKS:
        return 0
    if hit.kind == "talk":
        return 1
    if hit.kind == "article":
        return 2
    return 3


def by_tier(hits: list[study_index.SearchHit]) -> list[study_index.SearchHit]:
    return sorted(hits, key=tier)  # stable


def topic_messages(questions: list[str], topics: list[tuple[int, str]]) -> list[dict]:
    listing = "\n".join(f"{number}. {name}" for number, (_id, name) in enumerate(topics, start=1))
    return [
        {"role": "system", "content": TOPIC_PROMPT},
        {"role": "user", "content": f"Question: {' '.join(questions)}\n\nTopics:\n{listing}"},
    ]


def parse_topic_choice(content: str, topics: list[tuple[int, str]]) -> list[int] | None:
    """Topic ids the model chose (at most KEY_TOPICS - it sometimes lists
    more than asked), [] for an explicit "none fit", None if unusable."""
    chosen = parse_selection(content, len(topics))
    if chosen is None:
        return None
    return [topics[i][0] for i in chosen[:KEY_TOPICS]]


def all_topics(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    return [(r[0], r[1]) for r in conn.execute("SELECT id, name FROM topics ORDER BY name")]


def _key_passage_hits(
    conn: sqlite3.Connection,
    index: study_index.StudyIndex,
    query: str,
    vector: list[float] | None,
    already: list[study_index.SearchHit],
    topic_ids: list[int] | None = None,
) -> list[study_index.SearchHit]:
    """Key passages of the given topics (or, without any, of the index's
    best-matching ones) as scripture candidates, skipping any that
    overlap a scripture candidate already found."""
    def overlaps(hit: study_index.SearchHit, book: str, chapter: int, start: int, end: int) -> bool:
        m = hit.meta
        return (
            hit.kind == "scripture" and m.get("book") == book and m.get("chapter") == chapter
            and m.get("verse_start", 0) <= end and m.get("verse_end", 0) >= start
        )

    if topic_ids is None:
        topic_ids = [
            h.meta["topic_id"]
            for h in index.search(query, vector, kinds={"topic"}, limit=KEY_TOPICS)
            if h.meta.get("topic_id") is not None
        ]
    found: list[study_index.SearchHit] = []
    for topic_id in topic_ids:
        row = conn.execute("SELECT name, slug FROM topics WHERE id = ?", (topic_id,)).fetchone()
        if row is None:
            continue
        topic_name, topic_slug = row[0], row[1]
        for passage in get_topic_key_passages(conn, topic_id)[:KEY_PASSAGES_PER_TOPIC]:
            book, _, rest = passage.reference.rpartition(" ")
            chapter = int(rest.split(":")[0])
            if any(overlaps(h, book, chapter, passage.verse_start, passage.verse_end) for h in already + found):
                continue
            found.append(
                study_index.SearchHit(
                    piece_id=0,
                    key=f"key:{topic_slug}:{passage.reference}",
                    kind="scripture",
                    text=f"{passage.reference}\n{passage.text}",
                    volume_slug=passage.volume_slug,
                    chapter_id=passage.chapter_id,
                    meta={
                        "reference": passage.reference, "book": book, "chapter": chapter,
                        "verse_start": passage.verse_start, "verse_end": passage.verse_end,
                        "key_topic": topic_name,
                    },
                    score=0.0,
                    semantic_rank=None,
                    keyword_rank=None,
                )
            )
    return found


def gather_candidates(
    index: study_index.StudyIndex,
    questions: list[str],
    query: str,
    vector: list[float] | None,
    conn: sqlite3.Connection | None = None,
    topic_ids: list[int] | None = None,
) -> list[study_index.SearchHit]:
    """The candidates the chat model chooses from: one search per
    CANDIDATE_GROUPS group plus - given the main database `conn` - the
    best-matching Topical Guide topics' key passages, listed first; or,
    when a follow-up asked for one volume or kind of source
    (detect_filters), a single search restricted to it."""
    kinds, volumes = detect_filters(questions)
    if kinds:
        return index.search(query, vector, kinds=kinds, volume_slugs=volumes, limit=CANDIDATES)
    hits: list[study_index.SearchHit] = []
    for _name, group_kinds, group_volumes, count in CANDIDATE_GROUPS:
        hits.extend(
            index.search(
                query, vector, kinds=group_kinds, volume_slugs=group_volumes,
                kind_limits=study_index.MIXED_KIND_LIMITS, limit=count,
            )
        )
    if conn is not None:
        keys = _key_passage_hits(conn, index, query, vector, hits, topic_ids)
        leads, rest, seen_topics = [], [], set()
        for hit in keys:  # keys come in topic order, most central first
            topic = hit.meta.get("key_topic")
            (rest if topic in seen_topics else leads).append(hit)
            seen_topics.add(topic)
        hits = leads + hits[:KEY_PASSAGES_AFTER] + rest + hits[KEY_PASSAGES_AFTER:]
    return hits


def fallback_hits(hits: list[study_index.SearchHit]) -> list[study_index.SearchHit]:
    """A few of the index's best from each tier, for when the chat
    model's selection isn't usable."""
    chosen: list[study_index.SearchHit] = []
    for level, count in enumerate(FALLBACK_PER_TIER):
        chosen.extend([h for h in hits if tier(h) == level][:count])
    return chosen


def _shares_a_word(hit: study_index.SearchHit, question: str) -> bool:
    """Whether a talk or article's title is plausibly about the question:
    it shares at least two of the question's significant words, or its
    only one. One shared word was too loose - "sisters" alone brought in
    "A Plea to My Sisters" for "Where are Nephi's sisters mentioned?". A
    heuristic, not a judgment: two common words can still match an
    unrelated title ("relationship" and "Christ" for "What was Mark's
    relationship to Christ?")."""
    title = {re.sub(r"'s$", "", w) for w in re.findall(r"[a-z']+", hit.text.partition("\n")[0].lower())}
    keywords = list(dict.fromkeys(snippet_keywords(question)))
    shared = sum(1 for word in keywords if word in title)
    return shared >= min(2, len(keywords)) and shared > 0


def with_minimums(
    chosen: list[study_index.SearchHit],
    candidates: list[study_index.SearchHit],
    question: str = "",
) -> list[study_index.SearchHit]:
    """`chosen` plus, for each MIN_PER_TIER tier it has fewer of than the
    minimum, the index's best remaining candidates from that tier - only
    ones whose title shares a word with the question, since in testing
    unrelated talks were otherwise forced in (for "Who is Teancum", a
    talk titled "Where Your Treasure Is")."""
    result = list(chosen)
    for level, minimum in MIN_PER_TIER.items():
        have = sum(1 for h in result if tier(h) == level)
        for hit in candidates:
            if have >= minimum:
                break
            if tier(hit) == level and hit not in result and _shares_a_word(hit, question):
                result.append(hit)
                have += 1
    return result


def retrieval_query(questions: list[str]) -> str:
    """A follow-up ("just the ones about the Atonement") means little on
    its own - retrieve on the whole line of questioning. A follow-up
    that's only a filter ("just the Book of Mormon") adds nothing to
    search *for* once detect_filters has turned it into a filter, so it's
    left out rather than matching every passage that mentions the book."""
    parts = [questions[0]] if questions else []
    for question in questions[1:]:
        _kinds, _volumes, rest = _match_filters(question)
        if [k for k in extract_keywords(rest) if k not in _NARROWING_WORDS]:
            parts.append(question)
    return " ".join(parts)


# How much of a snippet comes before the first word it's centered on.
SNIPPET_LEAD_CHARS = 80


def snippet_keywords(question: str) -> list[str]:
    """The question's significant words, as matched against passage text
    ("Nephi's" -> "nephi")."""
    return [re.sub(r"'s$", "", w) for w in extract_keywords(question, limit=12)]


def _snippet(text: str, limit: int = SNIPPET_CHARS, keywords: list[str] = ()) -> str:
    """`limit` characters of `text` - starting a little before the first
    of `keywords` it contains, when it contains any, rather than always at
    the start. A passage's opening can be about something else entirely:
    2 Nephi 5:5-7 is the one passage that mentions Nephi's sisters, but
    "my sisters" is past the first 220 characters, so the chat model -
    shown only those - skipped it for a less relevant passage."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    start = 0
    lowered = text.lower()
    visible = lowered[:limit]
    # Words of the question the opening doesn't show but the rest does -
    # center on the earliest of those. ("Nephi" is already in 2 Nephi
    # 5:5-7's opening; "sisters" isn't, so that's what to show.)
    hidden = [
        m.start() for k in keywords if k and not re.search(rf"\b{re.escape(k)}", visible)
        for m in [re.search(rf"\b{re.escape(k)}", lowered)] if m
    ]
    if hidden:
        start = max(0, min(hidden) - SNIPPET_LEAD_CHARS)
        start = text.find(" ", start) + 1 if start else 0
    piece = text[start:start + limit]
    if start + limit < len(text):
        piece = piece.rsplit(" ", 1)[0] + "..."
    return ("..." if start else "") + piece


def selection_messages(questions: list[str], hits: list[study_index.SearchHit]) -> list[dict]:
    if len(questions) == 1:
        ask = f"Question: {questions[0]}"
    else:
        ask = f"Original question: {questions[0]}\n" + "\n".join(
            f"Refinement: {q}" for q in questions[1:]
        )
    keywords = snippet_keywords(" ".join(questions))
    lines = []
    for number, hit in enumerate(hits, start=1):
        heading, _, body = hit.text.partition("\n")
        label = _KIND_LABELS.get(hit.kind, hit.kind)
        if hit.kind == "scripture":
            heading = hit.meta.get("reference", heading)
            if hit.meta.get("key_topic"):
                label = f"Scripture - a key passage on {hit.meta['key_topic']}"
        line = f"[{number}] ({label}) {heading}"
        if body:
            line += f" - {_snippet(body, keywords=keywords)}"
        lines.append(line)
    return [
        {"role": "system", "content": SELECTION_PROMPT},
        {"role": "user", "content": f"{ask}\n\nSources:\n" + "\n".join(lines)},
    ]


def parse_selection(content: str, count: int) -> list[int] | None:
    """0-based indexes the model chose, in its order, deduplicated and
    limited to the list's real range. None if the reply isn't a JSON array
    of numbers at all (prose, a refusal, ...) - [] means it explicitly
    chose nothing."""
    match = re.search(r"\[[^\[\]]*\]", content)
    if not match:
        return None
    try:
        values = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(values, list):
        return None
    chosen: list[int] = []
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= count and number - 1 not in chosen:
            chosen.append(number - 1)
    if values and not chosen:
        return None  # numbers, but none from the list - not a real answer
    return chosen[:MAX_SELECTED]


def _chapter_for(conn: sqlite3.Connection, volume_slug: str | None, reference: str) -> int | None:
    match = re.match(r"^(?P<book>.+?)\s+(?P<chapter>\d+)", reference)
    if not match:
        return None
    sql = (
        "SELECT c.id FROM chapters c JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id WHERE b.name = ? AND c.chapter_number = ?"
    )
    params: list = [match["book"], int(match["chapter"])]
    if volume_slug:
        sql += " AND vol.slug = ?"
        params.append(volume_slug)
    row = conn.execute(sql + " ORDER BY vol.sort_order LIMIT 1", params).fetchone()
    return row[0] if row else None


def to_result(
    conn: sqlite3.Connection, hit: study_index.SearchHit, question: str = ""
) -> StudyResult | None:
    """A search hit as something to show - text re-read from the main
    database where there is one, its snippet centered on the question's
    words where it contains them (see _snippet). None if it no longer
    resolves (e.g. a chapter this database doesn't have)."""
    keywords = snippet_keywords(question) if question else []
    heading, _, body = hit.text.partition("\n")
    meta = hit.meta
    if hit.kind == "scripture":
        rows = conn.execute(
            "SELECT verse_number, text, reference FROM verses WHERE chapter_id = ? "
            "AND verse_number BETWEEN ? AND ? ORDER BY verse_number",
            (hit.chapter_id, meta["verse_start"], meta["verse_end"]),
        ).fetchall()
        if not rows:
            return None
        return StudyResult(
            kind="scripture",
            title=meta["reference"],
            detail=_snippet(" ".join(r[1] for r in rows), 400, keywords),
            chapter_id=hit.chapter_id,
            citations=citations_for([r[2] for r in rows]),
        )
    if hit.kind == "lexicon":
        gloss = meta.get("gloss", "")
        return StudyResult(
            kind="lexicon",
            title=heading,
            detail=f"{gloss} - {_snippet(body, keywords=keywords)}" if gloss else _snippet(body, keywords=keywords),
            strongs=meta.get("strongs"),
        )
    if hit.kind in ("talk", "article"):
        return StudyResult(kind=hit.kind, title=heading, url=meta.get("url"))
    if hit.kind == "topic":
        return StudyResult(
            kind="topic", title=heading, detail=_snippet(body, keywords=keywords), topic_id=meta.get("topic_id")
        )
    if hit.kind in ("cross_reference", "user_cross_reference"):
        chapter_id = _chapter_for(conn, hit.volume_slug, meta.get("reference", ""))
        if chapter_id is None:
            return None
        return StudyResult(
            kind=hit.kind, title=heading, detail=_snippet(body, keywords=keywords), chapter_id=chapter_id
        )
    if hit.chapter_id is None:
        return None
    # discourse, note
    return StudyResult(
        kind=hit.kind, title=heading, detail=_snippet(body, keywords=keywords), chapter_id=hit.chapter_id
    )


@dataclass
class StudySearch:
    """What AI search needs to use a built study index - created once by
    MainWindow (so the vectors stay loaded between searches) and passed
    down through SearchView to AiConversationSection."""

    index: study_index.StudyIndex
    index_path: Path
    embedding_config: AiConfig
    embedding_dimensions: int | None


class _VectorLoader(QObject):
    """Loads a StudyIndex's vectors on a background thread (its own sqlite
    connection - they can't cross threads), so the first search doesn't
    stall the window. `done()` arrives on the main thread."""

    done = Signal(object)

    def start(self, index_path: Path) -> None:
        threading.Thread(target=self._run, args=(index_path,), daemon=True).start()

    def _run(self, index_path: Path) -> None:
        try:
            self.done.emit(study_index.StudyIndex.load_arrays(index_path))
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            self.done.emit(exc)


class StudyQuestionAsker(QObject):
    """One question (or follow-up) answered from the study index.

    `succeeded(results, note)` - `note` is "" normally, or explains a
    fallback to the index's own ranking. `failed(message, needs_api_key)`
    only when nothing at all could be retrieved. Exactly one fires; keep a
    reference to this object until it does."""

    succeeded = Signal(list, str)
    failed = Signal(str, bool)

    def __init__(
        self,
        conn: sqlite3.Connection,
        index: study_index.StudyIndex,
        index_path: Path,
        chat_config: AiConfig,
        embedding_config: AiConfig,
        embedding_dimensions: int | None,
        questions: list[str],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self._index = index
        self._chat_config = chat_config
        self._questions = list(questions)
        self._query = retrieval_query(self._questions)
        self._vector: list[float] | None = None
        self._embedded = False
        self._loaded = index.is_loaded()
        self._hits: list[study_index.SearchHit] = []
        self._manager: QNetworkAccessManager | None = None

        self._embedder = QueryEmbedder(
            embedding_config, embedding_config.model, self._query, embedding_dimensions, self
        )
        self._embedder.ready.connect(self._on_embedded)
        # A failed embedding still leaves keyword search - carry on.
        self._embedder.failed.connect(lambda _message: self._on_embedded(None))
        if not self._loaded:
            self._loader = _VectorLoader(self)
            self._loader.done.connect(self._on_loaded)
            self._loader.start(index_path)

    def _on_loaded(self, arrays) -> None:
        if not isinstance(arrays, Exception):
            self._index.adopt_arrays(arrays)
        self._loaded = True
        self._maybe_search()

    def _on_embedded(self, vector) -> None:
        self._vector = vector
        self._embedded = True
        self._maybe_search()

    def _maybe_search(self) -> None:
        if not (self._embedded and self._loaded):
            return
        if detect_filters(self._questions)[0] is not None:
            self._gather(None)  # a filtered follow-up uses no topics
            return
        self._topics = all_topics(self.conn)
        self._manager = QNetworkAccessManager(self)
        payload = json.dumps(
            {
                "model": self._chat_config.model or "gpt-4o-mini",
                "temperature": 0,
                "messages": topic_messages(self._questions, self._topics),
            }
        ).encode("utf-8")
        self._topic_reply = self._manager.post(
            build_request(self._chat_config, "/chat/completions"), payload
        )
        self._topic_reply.finished.connect(self._on_topics)

    def _on_topics(self) -> None:
        reply = self._topic_reply
        topic_ids = None
        if reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                content = json.loads(bytes(reply.readAll()))["choices"][0]["message"]["content"]
                topic_ids = parse_topic_choice(content, self._topics)
            except (ValueError, KeyError, IndexError, TypeError):
                topic_ids = None
        elif reply.error() in AUTH_ERRORS:
            reply.deleteLater()
            self.failed.emit(reply.errorString(), True)
            return
        reply.deleteLater()
        self._gather(topic_ids)

    def _gather(self, topic_ids: list[int] | None) -> None:
        self._hits = gather_candidates(
            self._index,
            self._questions,
            self._query,
            self._vector if self._index.is_loaded() else None,
            self.conn,
            topic_ids,
        )
        if not self._hits:
            self.succeeded.emit([], "")
            return
        if self._manager is None:
            self._manager = QNetworkAccessManager(self)
        payload = json.dumps(
            {
                "model": self._chat_config.model or "gpt-4o-mini",
                "temperature": 0.1,
                "messages": selection_messages(self._questions, self._hits),
            }
        ).encode("utf-8")
        self._reply = self._manager.post(build_request(self._chat_config, "/chat/completions"), payload)
        self._reply.finished.connect(self._on_selected)

    def _results(self, hits: list[study_index.SearchHit]) -> list[StudyResult]:
        question = " ".join(self._questions)
        return [r for r in (to_result(self.conn, h, question) for h in hits) if r is not None]

    def _fallback(self, why: str) -> None:
        self.succeeded.emit(
            self._results(fallback_hits(self._hits)),
            f"Showing the study index's best matches - {why}",
        )

    def _on_selected(self) -> None:
        reply = self._reply
        error = reply.error()
        raw = bytes(reply.readAll()).decode("utf-8", errors="replace")
        reply.deleteLater()
        if error != QNetworkReply.NetworkError.NoError:
            if error in AUTH_ERRORS:
                self.failed.emit(reply.errorString(), True)
                return
            self._fallback(f"the AI didn't answer ({reply.errorString()}).")
            return
        try:
            content = json.loads(raw)["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            self._fallback("the AI's reply wasn't in the expected format.")
            return
        chosen = parse_selection(content, len(self._hits))
        if chosen is None:
            self._fallback("the AI's reply didn't pick from the list.")
            return
        if not chosen:
            self._fallback("the AI didn't think any of them fit, so these may be loose matches.")
            return
        chosen_hits = [self._hits[i] for i in chosen]
        # A follow-up that asked for one volume or kind gets only that.
        if detect_filters(self._questions)[0] is None:
            chosen_hits = with_minimums(chosen_hits, self._hits, self._query)
        self.succeeded.emit(self._results(by_tier(chosen_hits)), "")
