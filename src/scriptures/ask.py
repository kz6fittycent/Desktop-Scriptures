"""Retrieval-validated, AI-assisted scripture search (Stage 2 - see
ai_client.py's module docstring for the overall opt-in, bring-your-own-
endpoint design, and main_window.py's search bar for how this surfaces).

A natural-language question (e.g. "how did Christ organize the Nephite
church") is sent to the user's configured AI endpoint, asking it for
candidate scripture references - nothing more. The model's job stops
there: every candidate reference it returns is parsed and looked up
against THIS app's own local database, and only references that actually
resolve to real content are ever shown to the user, always with that
verse's real, indexed text - never anything the model itself wrote. A
made-up or misremembered reference is silently dropped rather than
surfaced as a "maybe".

Each resolved reference is also enriched with any General Conference
talks already known to cite it (citations.py's same local,
pre-harvested data the Citations tab and Topical Guide already read) -
this is a plain local lookup, not something the model is ever asked
for, so it carries none of the hallucination risk a "suggest a talk"
prompt would. Coverage is necessarily partial: only verses that some
Topical Guide topic's search already surfaced (or that were in the
original Scripture of the Day pool) have any citations harvested at
all - see build_topical_guide.py.

This deliberately only covers the standard, citation-style volumes (Holy
Bible, Book of Mormon, Doctrine and Covenants, Pearl of Great Price,
Joseph Smith Translation) - Journal of Discourses and Lectures on Faith
address content by speaker/title or lecture number, not a chapter:verse
citation a model would ever guess at, so a question that's really about
one of those just won't resolve to anything here, the same as any other
unresolvable guess.

Book names are also normalized against standard LDS citation
abbreviations (_BOOK_ALIASES) before resolution - "D&C" in particular
isn't a rare style choice, it's how Doctrine and Covenants is almost
always actually cited, far more often than spelling it out, so without
this every D&C (and much of the Book of Mormon/Pearl of Great Price)
reference a model naturally reaches for would silently fail to resolve
while Bible references - rarely abbreviated in general writing - kept
working fine. That asymmetry ("the Bible always shows up, everything
else is missing") is exactly the bug this fixes.

On the initial question of a conversation (not a follow-up refinement -
see AiConversationSection), coverage is also supplemented by a plain
local keyword search: the question's own significant words (stopwords
stripped - see _extract_keywords) are run through the same FTS5 index
the ordinary keyword search already uses, across every volume, and any
real matches not already suggested by the model are appended. This
exists because a model's own citation recall is necessarily uneven -
"Acts 11:26" (first called Christians) is near-universally known
Christian trivia, while "Alma 46:16" (the Book of Mormon's own, much
earlier use of the same word) is a far more obscure, LDS-specific
cross-reference a general-purpose or smaller local model may simply
never have learned to recall, no matter how the request is phrased.
The local search doesn't depend on the model knowing anything - it
only depends on the question sharing real words with the actual verse
text, so it catches exactly this kind of gap.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply

from scriptures.ai_client import AUTH_ERRORS, AiConfig, build_request
from scriptures.citations import Citation, get_citations
from scriptures.data_access import get_chapter_by_loose_reference, get_verse_by_loose_reference

# Cap on how many citing talks are attached per resolved reference - a
# heavily-cited verse (e.g. John 3:16) could otherwise pad out a single
# search result with dozens of talks.
MAX_CITATIONS_PER_REFERENCE = 5

# Cap on how many candidate references the model is asked for (and, as a
# backstop, how many this will ever act on even if it returns more) - a
# short, focused list is more useful than an exhaustive one.
MAX_REFERENCES = 6

# How many *additional* results the local keyword search (see module
# docstring) is always guaranteed room for, on top of whatever the model
# itself already suggested - reserved capacity, not a shared pool. If it
# instead had to compete for space within MAX_REFERENCES, a model that
# fills every slot with its own picks (plausible for a question with
# several well-known answers, e.g. several different Bible verses all
# using the same word) would leave the local search zero room to
# contribute even one more real, independent match - exactly the bug
# this constant exists to prevent.
LOCAL_SUPPLEMENT_LIMIT = 3

SYSTEM_PROMPT = (
    "You help locate passages in the LDS standard works (the Holy Bible, "
    "the Book of Mormon, the Doctrine and Covenants, the Pearl of Great "
    "Price, and the Joseph Smith Translation) that are relevant to a "
    "reader's question. Reply with ONLY a JSON array of up to "
    f"{MAX_REFERENCES} scripture reference strings, most relevant first - "
    'no prose, no markdown, just e.g. ["3 Nephi 11:18-22", "3 Nephi 18:1-11"]. '
    "Each reference must be a real book name, chapter number, and "
    "optionally a verse or verse range (e.g. \"Alma 32:21\", \"Doctrine and "
    'Covenants 76", "1 Nephi 3:7"). If nothing in these books is clearly '
    "relevant, reply with an empty array []. The conversation may include "
    "your own earlier replies (each still just a bare JSON array) and a "
    "follow-up refining what's wanted (e.g. \"just the ones about "
    'baptism") - narrow or adjust your previous answer accordingly, still '
    "following the same rules."
)


@dataclass(frozen=True)
class AskedReference:
    """One AI-suggested reference, already resolved against the local
    database - `text` and `reference` always come from there, never from
    the model's own output. `citations` (possibly empty) are real,
    already-harvested General Conference talks known to cite this
    reference - see this module's own docstring."""

    chapter_id: int
    verse_id: int | None
    reference: str
    text: str
    citations: list[Citation] = field(default_factory=list)


class AskError(Exception):
    """`needs_api_key` mirrors ai_client.ConnectionTester's own
    distinction between an auth-shaped failure and any other kind."""

    def __init__(self, message: str, needs_api_key: bool = False):
        super().__init__(message)
        self.needs_api_key = needs_api_key


# Matches "Book Name Chapter[:Verse[-Verse]]" - book name is everything up
# to the last run of digits (optionally followed by :verse[-verse]), so
# numbered books ("1 Nephi", "2 Corinthians") still parse correctly since
# the engine backtracks the non-greedy book group until the remainder
# matches a bare chapter number.
_REFERENCE_RE = re.compile(
    r"^(?P<book>.+?)\s+(?P<chapter>\d+)(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?$"
)


def _parse_reference(text: str) -> tuple[str, int, int | None, int | None] | None:
    match = _REFERENCE_RE.match(text.strip())
    if not match:
        return None
    book = _canonical_book_name(match.group("book").strip())
    chapter = int(match.group("chapter"))
    start = int(match.group("start")) if match.group("start") else None
    end = int(match.group("end")) if match.group("end") else None
    return book, chapter, start, end


# Standard LDS citation abbreviations, keyed by their _normalize_book_key
# form, mapped to this database's own exact book name. "D&C" in
# particular isn't an edge case - it's how Doctrine and Covenants is
# almost always actually cited, far more often than the spelled-out
# name, so a model reaching for it is the norm, not a rare miss; the
# same pattern (a common abbreviation the model reaches for, that the
# database's own full name doesn't match) shows up throughout the Book
# of Mormon and Pearl of Great Price too. Without this, every one of
# these would silently fail to resolve while any Bible book (rarely
# abbreviated in general writing, and never needing this table to work)
# resolves fine - which is exactly the "Bible always shows up, everything
# else is missing" bug this fixes.
_BOOK_ALIASES: dict[str, str] = {
    "d&c": "Doctrine and Covenants",
    "dc": "Doctrine and Covenants",
    "od 1": "Official Declaration 1",
    "od1": "Official Declaration 1",
    "od 2": "Official Declaration 2",
    "od2": "Official Declaration 2",
    "1 ne": "1 Nephi",
    "2 ne": "2 Nephi",
    "3 ne": "3 Nephi",
    "4 ne": "4 Nephi",
    "w of m": "Words of Mormon",
    "wom": "Words of Mormon",
    "hel": "Helaman",
    "morm": "Mormon",
    "moro": "Moroni",
    "js-h": "Joseph Smith--History",
    "jsh": "Joseph Smith--History",
    "joseph smith-history": "Joseph Smith--History",
    "js-m": "Joseph Smith--Matthew",
    "jsm": "Joseph Smith--Matthew",
    "joseph smith-matthew": "Joseph Smith--Matthew",
    "a of f": "Articles of Faith",
    "aof": "Articles of Faith",
    "abr": "Abraham",
    # Holy Bible / JST (same abbreviated book names, common enough in
    # general writing that these are worth covering too, even though the
    # bug report was specifically about the LDS-only volumes above).
    "gen": "Genesis", "ex": "Exodus", "exod": "Exodus", "lev": "Leviticus",
    "num": "Numbers", "deut": "Deuteronomy", "josh": "Joshua", "judg": "Judges",
    "1 sam": "1 Samuel", "2 sam": "2 Samuel", "1 kgs": "1 Kings", "2 kgs": "2 Kings",
    "1 chr": "1 Chronicles", "2 chr": "2 Chronicles", "neh": "Nehemiah",
    "esth": "Esther", "ps": "Psalms", "psalm": "Psalms", "prov": "Proverbs",
    "eccl": "Ecclesiastes", "song of sol": "Song of Solomon", "sos": "Song of Solomon",
    "isa": "Isaiah", "jer": "Jeremiah", "lam": "Lamentations", "ezek": "Ezekiel",
    "dan": "Daniel", "hos": "Hosea", "obad": "Obadiah", "jon": "Jonah",
    "mic": "Micah", "nah": "Nahum", "hab": "Habakkuk", "zeph": "Zephaniah",
    "hag": "Haggai", "zech": "Zechariah", "mal": "Malachi",
    "matt": "Matthew", "mt": "Matthew", "mk": "Mark", "lk": "Luke",
    "rom": "Romans", "1 cor": "1 Corinthians", "2 cor": "2 Corinthians",
    "gal": "Galatians", "eph": "Ephesians", "phil": "Philippians",
    "col": "Colossians", "1 thess": "1 Thessalonians", "2 thess": "2 Thessalonians",
    "1 tim": "1 Timothy", "2 tim": "2 Timothy", "philem": "Philemon",
    "heb": "Hebrews", "jas": "James", "1 pet": "1 Peter", "2 pet": "2 Peter",
    "1 jn": "1 John", "2 jn": "2 John", "3 jn": "3 John", "rev": "Revelation",
}


def _normalize_book_key(book: str) -> str:
    """Collapses the punctuation/spacing variation a model might use
    around an abbreviation ("D&C", "D & C", "D.&C.") down to one
    consistent lookup key ("d&c") for _BOOK_ALIASES."""
    key = book.replace(".", "")
    key = key.replace("—", "-").replace("–", "-")  # em/en dash
    key = re.sub(r"\s*&\s*", "&", key)
    key = re.sub(r"-+", "-", key)
    key = re.sub(r"\s+", " ", key).strip().lower()
    return key


def _canonical_book_name(book: str) -> str:
    """Maps a recognized abbreviation to this database's own exact book
    name; anything else is returned unchanged; get_verse_by_loose_reference/
    get_chapter_by_loose_reference already match case-insensitively
    against the real name, so an already-correct full name (however
    cased) still resolves without needing an entry here."""
    return _BOOK_ALIASES.get(_normalize_book_key(book), book)


def _citations_for(references: list[str]) -> list[Citation]:
    """Real, already-harvested citing talks for any of these verse
    references, deduplicated by URL (the same talk often cites more than
    one verse in a range or chapter), capped at MAX_CITATIONS_PER_REFERENCE."""
    seen_urls: set[str] = set()
    result: list[Citation] = []
    for reference in references:
        for citation in get_citations(reference):
            if citation.url in seen_urls:
                continue
            seen_urls.add(citation.url)
            result.append(citation)
            if len(result) >= MAX_CITATIONS_PER_REFERENCE:
                return result
    return result


def _resolve_one(conn: sqlite3.Connection, candidate: str) -> AskedReference | None:
    parsed = _parse_reference(candidate)
    if parsed is None:
        return None
    book, chapter_number, verse_start, verse_end = parsed

    if verse_start is None:
        chapter = get_chapter_by_loose_reference(conn, book, chapter_number)
        if chapter is None:
            return None
        rows = conn.execute(
            "SELECT reference, text FROM verses WHERE chapter_id = ? ORDER BY verse_number",
            (chapter.id,),
        ).fetchall()
        if not rows:
            return None
        label = f"{book} {chapter_number}"
        snippet = " ".join(r["text"] for r in rows)
        citations = _citations_for([r["reference"] for r in rows])
        return AskedReference(chapter.id, None, label, snippet, citations)

    verse_end = verse_end or verse_start
    matched_verses = []
    for verse_number in range(verse_start, verse_end + 1):
        verse = get_verse_by_loose_reference(conn, book, chapter_number, verse_number)
        if verse is not None:
            matched_verses.append(verse)
    if not matched_verses:
        return None

    chapter_id = matched_verses[0].chapter_id
    if len(matched_verses) == 1:
        v = matched_verses[0]
        return AskedReference(chapter_id, v.id, v.reference, v.text, _citations_for([v.reference]))
    label = f"{book} {chapter_number}:{verse_start}-{verse_end}"
    snippet = " ".join(v.text for v in matched_verses)
    citations = _citations_for([v.reference for v in matched_verses])
    return AskedReference(chapter_id, matched_verses[0].id, label, snippet, citations)


def resolve_references(conn: sqlite3.Connection, candidates: list[str]) -> list[AskedReference]:
    """The pure, network-free half of this module: turns a list of
    free-form reference strings (as the model returned them) into
    validated AskedReferences, silently dropping anything that doesn't
    parse or doesn't resolve to real local content. Order is preserved
    (the model's own most-relevant-first ordering), duplicates by
    chapter+verse are dropped, and the result is capped at
    MAX_REFERENCES."""
    seen: set[tuple[int, int | None]] = set()
    resolved: list[AskedReference] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        ref = _resolve_one(conn, candidate)
        if ref is None:
            continue
        key = (ref.chapter_id, ref.verse_id)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(ref)
        if len(resolved) >= MAX_REFERENCES:
            break
    return resolved


def unresolved_candidates(conn: sqlite3.Connection, candidates: list[str]) -> list[str]:
    """Which of these candidate strings _resolve_one couldn't turn into
    real content - a diagnostic for the partial-miss case resolve_references
    itself can't surface: when the model suggests several references and
    only some resolve, the ones that silently got dropped are otherwise
    invisible (only a *complete* miss gets shown, via QuestionAsker's own
    raw_content). Recomputes resolution rather than diffing against
    resolve_references' own output, since a resolved AskedReference's
    `reference` can differ from the candidate string that produced it
    (e.g. "D&C 76:22" resolves to "Doctrine and Covenants 76:22") -
    cheap enough at the handful of candidates a single answer ever has."""
    return [c for c in candidates if isinstance(c, str) and _resolve_one(conn, c) is None]


# Common English words worth stripping before treating the rest of a
# natural-language question as search keywords for the local supplement
# below - deliberately short and unsurprising (not a linguistics-grade
# stopword list), just enough to turn a full sentence into its handful
# of actual content words - "when was the term christian first used"
# reduces to just ["christian"], the exact word that matters.
_STOPWORDS = frozenset(
    """
    a an the is was were are be been being when where who whom what
    which why how did does do first term used use to of in on at by
    for with about and or but that this these those it its i you he
    she we they his her their our your my me him them
    """.split()
)


def _extract_keywords(question: str, limit: int = 6) -> list[str]:
    """A rough, stopword-stripped set of the question's own significant
    words, order preserved and deduplicated - see the module docstring's
    note on why this (not asking the model for keywords) backs the local
    search supplement: it works the same regardless of which model is
    configured, or how well it follows instructions."""
    words = re.findall(r"[A-Za-z']+", question.lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for word in words:
        if word in _STOPWORDS or len(word) <= 2 or word in seen:
            continue
        seen.add(word)
        keywords.append(word)
        if len(keywords) >= limit:
            break
    return keywords


def _search_local_verses_by_keywords(
    conn: sqlite3.Connection, keywords: list[str], limit: int
) -> list[AskedReference]:
    """Real verses (any volume) matching any of these keywords, ranked by
    the same FTS5 bm25 relevance the app's own keyword search already
    uses - entirely independent of anything the AI itself suggested, so
    it surfaces real matches even when the configured model's own recall
    of a specific cross-reference comes up short (see module docstring).
    OR-combined (not AND, and not one quoted phrase the way the ordinary
    search box's exact-phrase matching works) since these are independent
    significant words, not a phrase to match verbatim. Each is also a
    prefix match ("christian"* also matches "Christians") - FTS5 does
    plain token matching with no stemming, and scripture text is
    overwhelmingly archaic/inflected (-eth, -ed, plurals), so a bare exact
    match on the word as typed would miss most of the very forms the
    question is actually asking about."""
    if not keywords:
        return []
    match_query = " OR ".join(f'"{kw}"*' for kw in keywords)
    rows = conn.execute(
        "SELECT v.id, v.verse_number, v.text, v.reference, v.chapter_id "
        "FROM verses_fts JOIN verses v ON v.id = verses_fts.rowid "
        "WHERE verses_fts MATCH ? ORDER BY rank LIMIT ?",
        (match_query, limit),
    ).fetchall()
    return [
        AskedReference(
            row["chapter_id"], row["id"], row["reference"], row["text"], _citations_for([row["reference"]])
        )
        for row in rows
    ]


def _merge_references(
    primary: list[AskedReference], supplementary: list[AskedReference], cap: int
) -> list[AskedReference]:
    """`primary` (whatever the AI itself suggested and validated) always
    leads; `supplementary` (the local keyword search) only fills in
    references not already present, up to `cap` total.

    Also dedupes by the *displayed* reference string, not just by
    (chapter_id, verse_id) - the Joseph Smith Translation reuses the
    King James Bible's own book/chapter/verse numbering (see schema.sql's
    comment on topic_verses), and JST's own translation changes can shift
    later verses in a chapter out of sync with the KJV's numbering, so
    e.g. "Acts 28:28" can be a real, different verse in each volume. Both
    are still genuine, resolvable content - but showing two rows both
    labeled "Acts 28:28" with no volume shown would read as a confusing
    exact duplicate rather than two distinct verses, so once a reference
    string is spoken for, a same-labeled verse from the other volume is
    treated as already covered rather than shown a second time."""
    seen_keys = {(r.chapter_id, r.verse_id) for r in primary}
    seen_references = {r.reference for r in primary}
    merged = list(primary)
    for ref in supplementary:
        if len(merged) >= cap:
            break
        key = (ref.chapter_id, ref.verse_id)
        if key in seen_keys or ref.reference in seen_references:
            continue
        seen_keys.add(key)
        seen_references.add(ref.reference)
        merged.append(ref)
    return merged


def _extract_json_array(content: str) -> list[str]:
    """The model was asked for bare JSON, but is asked nicely, not
    forced - this tolerates a markdown code fence or stray prose around
    the array by just grabbing the first [...] span, and gives up (empty
    list, not an exception - an odd response should surface as "no
    matches", not an error) if nothing array-shaped is found."""
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str)]


# A book name shaped like a proper noun - Capitalized word(s), optionally
# led by a book number (1-4) - followed immediately by a chapter number
# and optional verse/verse-range. Extends past one capitalized word only
# through a lowercase "and"/"of" joiner ("Doctrine and Covenants", "Song
# of Solomon"), never through another bare capitalized word directly -
# otherwise an ordinary capitalized word earlier in the same sentence
# ("See Doctrine and Covenants...") would get swallowed into the book
# name too. Deliberately NOT anchored to the whole string (unlike
# _REFERENCE_RE) - this scans for a reference occurring anywhere inside a
# larger block of prose.
_PROSE_REFERENCE_RE = re.compile(
    r"\b(?P<book>(?:[1-4]\s)?[A-Z][a-zA-Z]+(?:\s(?:and|of)\s[A-Z][a-zA-Z]+)*)"
    r"\s+(?P<chapter>\d{1,3})(?::(?P<start>\d{1,3})(?:-(?P<end>\d{1,3}))?)?\b"
)


def _extract_candidates(content: str) -> list[str]:
    """Every candidate reference string worth trying to resolve, from the
    model's raw reply. Tries the requested bare-JSON-array format first;
    if that finds nothing at all - a smaller or less compliant model
    ignoring the "just a JSON array" instruction and answering in prose
    instead is common enough, especially on a question phrased like
    general trivia rather than an obvious "find me a verse" ask - falls
    back to scanning the raw prose for reference-shaped substrings
    instead of giving up. This can't introduce new hallucination risk:
    whatever it finds, compliant or scanned, still goes through the exact
    same resolve_references validation before anything reaches the user,
    so a false-positive-looking scan match (e.g. "Chapter 3") that isn't
    a real book name simply fails to resolve and is dropped the same way
    a genuine hallucination already would be."""
    candidates = _extract_json_array(content)
    if candidates:
        return candidates
    return [m.group(0).strip() for m in _PROSE_REFERENCE_RE.finditer(content)]


class QuestionAsker(QObject):
    """Sends one question to the configured AI endpoint and resolves its
    answer against `conn`. `succeeded(list[AskedReference], raw_content)`
    or `failed(str, needs_api_key: bool)` fires exactly once - keep a
    reference to this object until one does (see ai_client.py's
    ConnectionTester for why).

    `raw_content` is the model's own unprocessed reply text, carried
    through purely as a diagnostic - never shown as if it were an answer.
    When no reference in it resolved (the model didn't know a real one,
    ignored the "just a JSON array" instruction and wrote prose instead,
    or something else entirely), the caller can show it so the user (and
    whoever's debugging a report like "it said no matches") can actually
    see why, instead of an unexplained empty result. `unresolved` is the
    partial-miss counterpart: any candidate the model proposed that
    didn't resolve, even when others did - without this, "the model also
    suggested something that got silently dropped" would be invisible
    whenever at least one other reference succeeded.

    `history` carries prior turns forward for a follow-up refinement
    ("just the ones about baptism") to have context - each entry is
    (question, reference strings previously shown for it). Critically,
    the "assistant" side of that history is never prose the model wrote:
    it's always the same bare JSON reference list already validated and
    shown to the user, re-fed back verbatim. The model never gets to
    accumulate its own commentary turn over turn - grounding holds across
    the whole conversation, not just the first message.

    An empty `history` also means this is the conversation's initial
    question (as opposed to a follow-up refinement of it), which is when
    the local keyword-search supplement (see module docstring) applies -
    a follow-up like "just the ones about baptism" is meant to narrow the
    existing results, not broaden them with an unrelated keyword sweep."""

    succeeded = Signal(list, str, list)
    failed = Signal(str, bool)

    def __init__(
        self,
        conn: sqlite3.Connection,
        config: AiConfig,
        question: str,
        history: list[tuple[str, list[str]]] = (),
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self.question = question
        self._is_initial_question = not history
        self._manager = QNetworkAccessManager(self)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for prior_question, prior_references in history:
            messages.append({"role": "user", "content": prior_question})
            messages.append({"role": "assistant", "content": json.dumps(prior_references)})
        messages.append({"role": "user", "content": question})
        payload = json.dumps(
            {"model": config.model or "gpt-4o-mini", "temperature": 0.2, "messages": messages}
        ).encode("utf-8")
        self._reply = self._manager.post(build_request(config, "/chat/completions"), payload)
        self._reply.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        reply = self._reply
        error = reply.error()
        if error != QNetworkReply.NetworkError.NoError:
            message = reply.errorString()
            needs_key = error in AUTH_ERRORS
            reply.deleteLater()
            self.failed.emit(message, needs_key)
            return

        raw = bytes(reply.readAll()).decode("utf-8", errors="replace")
        reply.deleteLater()
        try:
            content = json.loads(raw)["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            self.failed.emit("The AI endpoint's response wasn't in the expected format.", False)
            return

        candidates = _extract_candidates(content)
        resolved = resolve_references(self.conn, candidates)
        misses = unresolved_candidates(self.conn, candidates)

        if self._is_initial_question:
            keywords = _extract_keywords(self.question)
            # Over-fetched well past LOCAL_SUPPLEMENT_LIMIT - the top
            # bm25 matches for a common word can easily be entirely the
            # same verses the model already suggested (its own picks are
            # often the most obviously relevant ones too), which would
            # leave nothing left to fill the reserved slots with after
            # _merge_references dedupes them back out. Fetching this many
            # up front means a genuinely new match further down the
            # ranking still has room to be found.
            local_matches = _search_local_verses_by_keywords(
                self.conn, keywords, LOCAL_SUPPLEMENT_LIMIT + MAX_REFERENCES
            )
            # Reserved capacity, not shared with MAX_REFERENCES - see
            # LOCAL_SUPPLEMENT_LIMIT's own comment for why.
            resolved = _merge_references(
                resolved, local_matches, len(resolved) + LOCAL_SUPPLEMENT_LIMIT
            )

        self.succeeded.emit(resolved, content, misses)
