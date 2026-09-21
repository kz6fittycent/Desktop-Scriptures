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
    book = match.group("book").strip()
    chapter = int(match.group("chapter"))
    start = int(match.group("start")) if match.group("start") else None
    end = int(match.group("end")) if match.group("end") else None
    return book, chapter, start, end


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


class QuestionAsker(QObject):
    """Sends one question to the configured AI endpoint and resolves its
    answer against `conn`. `succeeded(list[AskedReference])` or
    `failed(str, needs_api_key: bool)` fires exactly once - keep a
    reference to this object until one does (see ai_client.py's
    ConnectionTester for why).

    `history` carries prior turns forward for a follow-up refinement
    ("just the ones about baptism") to have context - each entry is
    (question, reference strings previously shown for it). Critically,
    the "assistant" side of that history is never prose the model wrote:
    it's always the same bare JSON reference list already validated and
    shown to the user, re-fed back verbatim. The model never gets to
    accumulate its own commentary turn over turn - grounding holds across
    the whole conversation, not just the first message."""

    succeeded = Signal(list)
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

        candidates = _extract_json_array(content)
        self.succeeded.emit(resolve_references(self.conn, candidates))
