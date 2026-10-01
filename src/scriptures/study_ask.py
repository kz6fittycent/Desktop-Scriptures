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
from scriptures.embeddings import QueryEmbedder

CANDIDATES = 24
MAX_SELECTED = 10
# Shown when the chat model's selection isn't usable.
FALLBACK_COUNT = 8
SNIPPET_CHARS = 220

_KIND_LABELS = {
    "scripture": "Scripture",
    "discourse": "Journal of Discourses",
    "talk": "General Conference talk",
    "article": "Ensign/Liahona article",
    "topic": "Topical Guide",
    "cross_reference": "Cross-reference",
    "user_cross_reference": "Your cross-reference",
    "note": "Your note",
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


def _snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."


def selection_messages(questions: list[str], hits: list[study_index.SearchHit]) -> list[dict]:
    if len(questions) == 1:
        ask = f"Question: {questions[0]}"
    else:
        ask = f"Original question: {questions[0]}\n" + "\n".join(
            f"Refinement: {q}" for q in questions[1:]
        )
    lines = []
    for number, hit in enumerate(hits, start=1):
        heading, _, body = hit.text.partition("\n")
        if hit.kind == "scripture":
            heading = hit.meta.get("reference", heading)
        line = f"[{number}] ({_KIND_LABELS.get(hit.kind, hit.kind)}) {heading}"
        if body:
            line += f" - {_snippet(body)}"
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


def to_result(conn: sqlite3.Connection, hit: study_index.SearchHit) -> StudyResult | None:
    """A search hit as something to show - text re-read from the main
    database where there is one. None if it no longer resolves (e.g. a
    chapter this database doesn't have)."""
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
            detail=_snippet(" ".join(r[1] for r in rows), 400),
            chapter_id=hit.chapter_id,
            citations=citations_for([r[2] for r in rows]),
        )
    if hit.kind in ("talk", "article"):
        return StudyResult(kind=hit.kind, title=heading, url=meta.get("url"))
    if hit.kind == "topic":
        return StudyResult(kind="topic", title=heading, detail=_snippet(body), topic_id=meta.get("topic_id"))
    if hit.kind in ("cross_reference", "user_cross_reference"):
        chapter_id = _chapter_for(conn, hit.volume_slug, meta.get("reference", ""))
        if chapter_id is None:
            return None
        return StudyResult(kind=hit.kind, title=heading, detail=_snippet(body), chapter_id=chapter_id)
    if hit.chapter_id is None:
        return None
    # discourse, note
    return StudyResult(kind=hit.kind, title=heading, detail=_snippet(body), chapter_id=hit.chapter_id)


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
        kinds, volumes = detect_filters(self._questions)
        self._hits = self._index.search(
            self._query,
            self._vector if self._index.is_loaded() else None,
            kinds=kinds,
            volume_slugs=volumes,
            # Per-kind caps only make sense for a mixed list.
            kind_limits=None if kinds else study_index.MIXED_KIND_LIMITS,
            limit=CANDIDATES,
        )
        if not self._hits:
            self.succeeded.emit([], "")
            return
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
        return [r for r in (to_result(self.conn, h) for h in hits) if r is not None]

    def _fallback(self, why: str) -> None:
        self.succeeded.emit(
            self._results(self._hits[:FALLBACK_COUNT]),
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
        self.succeeded.emit(self._results([self._hits[i] for i in chosen]), "")
