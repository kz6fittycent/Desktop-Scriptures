"""Study index: a semantic ("search by meaning") index over everything the
app knows about, built on the user's own machine through their own AI
endpoint's embeddings API - groundwork for the talk-prep helper, and for
AI-assisted search to retrieve passages by meaning rather than relying on
a model's own recall (see ask.py's module docstring for that gap).

Nothing here exists until the user opts in: there is no bundled index or
bundled model. Once AI Integration is set up with an embedding model, the
"Build Study Index..." dialog (ui/study_index_dialog.py) sends the text
below to that endpoint in batches (embeddings.py) and stores the returned
vectors here.

What gets indexed ("pieces"):

- scripture: every volume's verses (headed by the reference alone - an
  earlier "(volume name)" suffix made "Lectures on Faith" match any
  question about faith) in small overlapping windows (up to
  WINDOW verses, and up to WINDOW_MAX_CHARS - Lectures on Faith's long
  paragraphs make for fewer verses per window), each overlapping the next
  by one verse, so each piece carries a little surrounding context rather
  than one short, context-free verse.
- discourse: the Journal of Discourses - each discourse is stored as a
  single (often 20KB+) "verse", so it's split on paragraph breaks into
  pieces of roughly DISCOURSE_TARGET_CHARS.
- topic: each Topical Guide topic - name, description, and its verses.
- cross_reference / user_cross_reference: curated and the reader's own,
  with their explanatory notes.
- talk / article: one summary card per General Conference talk and
  Ensign/Liahona article - title, speaker, date, and every verse it
  cites. Metadata only, never talk/article text (see citations.py).
- note: the reader's own notes. Journal entries are deliberately NOT
  included.

Storage lives in its own SQLite file next to the main database
(index_path_for), never inside it: in a source checkout the main database
IS the git-tracked data/scriptures.db, and 100MB+ of vectors there would
end up committed. Vectors are keyed by a hash of the exact text embedded,
not by piece, so identical text (much of the JST matches the KJV word for
word) is only ever embedded once, and a rebuild after new content arrives
only embeds what's actually new or changed. Each vector is stored
L2-normalized as float16, half the size of float32 with no meaningful
loss for cosine similarity.

The index records which embedding model (and dimensions) produced its
vectors - questions must be embedded with that same model to be
comparable, so changing the model clears the vectors (configure_model).

Search (StudyIndex.search) fuses the semantic ranking with a plain FTS5
keyword ranking over the same pieces by reciprocal rank fusion, so an
exact phrase still wins even when its meaning is ambiguous, and still
works (keyword-only) before any vectors exist.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from scriptures.ask import extract_keywords
from scriptures.citations import iter_citing_works

INDEX_FILENAME = "study_index.db"

WINDOW = 3
WINDOW_MAX_CHARS = 2000
DISCOURSE_TARGET_CHARS = 1200
DISCOURSE_MAX_CHARS = 2000
# A long talk card's verse list is capped - beyond this many, more
# references add little to what the card means and just cost tokens.
MAX_CARD_REFERENCES = 60
MAX_TOPIC_REFERENCES = 80
# Journal of Discourses titles are often a long run-on synopsis of
# topics joined by em dashes (up to ~900 characters) - repeated on every
# part of a discourse, it swamped each part's own meaning and matched
# almost any question. Only the first topic goes in the heading (cut to
# this length); the full title stays in the piece's meta.
MAX_HEADING_TITLE_CHARS = 100

# Reciprocal rank fusion's damping constant - the conventional value.
RRF_K = 60

# Per-kind caps for a mixed result list (see StudyIndex.search) - scripture
# is uncapped; everything else can't crowd it out. Found necessary in
# testing: "celestial marriage" filled 9 of 10 slots with Journal of
# Discourses sermons, whose 19th-century speakers used the phrase far more
# often (and often to mean plural marriage).
MIXED_KIND_LIMITS = {
    "discourse": 2,
    "talk": 3,
    "article": 2,
    "topic": 2,
    "cross_reference": 2,
    "user_cross_reference": 2,
    "note": 2,
}

KINDS = (
    "scripture",
    "discourse",
    "topic",
    "cross_reference",
    "user_cross_reference",
    "talk",
    "article",
    "note",
)

_RELATIONSHIP_VERB = {
    "quotation": "quotes",
    "paraphrase": "parallels",
    "translation": "is a translation-revision of",
    "typology": "connects to",
    "tradition": "is traditionally linked to",
}

# Bumped whenever the schema or what gets embedded changes shape -
# connect_index() discards an index from any other version (it's derived
# data; rebuilding it is always possible) rather than migrating it.
SCHEMA_VERSION = 2

# Each vector is one 1-3KB row (512-1536 float16 numbers plus its hash).
# At SQLite's default 4KB page only one or two fit per page, wasting
# ~20% of the vectors table (measured: 163MB for 122MB of vectors at 768
# dimensions); 16KB pages pack them with little waste.
PAGE_SIZE = 16384

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pieces (
    id            INTEGER PRIMARY KEY,
    key           TEXT NOT NULL UNIQUE,
    kind          TEXT NOT NULL,
    volume_slug   TEXT,
    chapter_id    INTEGER,
    heading       TEXT NOT NULL,
    body          TEXT NOT NULL,
    meta          TEXT NOT NULL DEFAULT '{}',
    content_hash  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pieces_hash ON pieces(content_hash);

-- heading and body are separate columns so keyword relevance can weight
-- them differently (see StudyIndex._keyword_ranking) - otherwise a word
-- in a heading every piece of a book shares, like "Faith" in "Lectures
-- on Faith", would make the whole book match.
CREATE VIRTUAL TABLE IF NOT EXISTS pieces_fts USING fts5(
    heading, body, content='pieces', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS pieces_ai AFTER INSERT ON pieces BEGIN
    INSERT INTO pieces_fts(rowid, heading, body) VALUES (new.id, new.heading, new.body);
END;
CREATE TRIGGER IF NOT EXISTS pieces_ad AFTER DELETE ON pieces BEGIN
    INSERT INTO pieces_fts(pieces_fts, rowid, heading, body)
        VALUES ('delete', old.id, old.heading, old.body);
END;
CREATE TRIGGER IF NOT EXISTS pieces_au AFTER UPDATE ON pieces BEGIN
    INSERT INTO pieces_fts(pieces_fts, rowid, heading, body)
        VALUES ('delete', old.id, old.heading, old.body);
    INSERT INTO pieces_fts(rowid, heading, body) VALUES (new.id, new.heading, new.body);
END;

-- float16, L2-normalized - see the module docstring.
CREATE TABLE IF NOT EXISTS vectors (
    content_hash  TEXT PRIMARY KEY,
    vector        BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS index_meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Piece:
    """`heading` says what the piece is (a reference, a title and
    speaker); `body` is its content. Kept apart so a model's document
    format (see EmbeddingFormat) and keyword weighting can treat them
    differently; `text` joins them for display or for a prompt."""

    key: str
    kind: str
    heading: str
    body: str
    volume_slug: str | None = None
    chapter_id: int | None = None
    meta: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return f"{self.heading}\n{self.body}" if self.body else self.heading

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.heading}\x00{self.body}".encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SearchHit:
    piece_id: int
    key: str
    kind: str
    text: str
    volume_slug: str | None
    chapter_id: int | None
    meta: dict
    score: float
    semantic_rank: int | None
    keyword_rank: int | None


@dataclass(frozen=True)
class IndexStatus:
    pieces: int
    unique_texts: int
    embedded: int
    pending_chars: int
    model: str | None
    dimensions: int | None

    @property
    def complete(self) -> bool:
        return self.unique_texts > 0 and self.embedded >= self.unique_texts


def index_path_for(scripture_conn: sqlite3.Connection) -> Path:
    """study_index.db, next to whichever file the main database was
    opened from ($SNAP_USER_COMMON in the snap, data/ in a source
    checkout - where .gitignore keeps it out of git)."""
    main_path = next(
        row[2] for row in scripture_conn.execute("PRAGMA database_list") if row[1] == "main"
    )
    return Path(main_path).with_name(INDEX_FILENAME)


def connect_index(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) a study index. One from a different
    SCHEMA_VERSION is emptied first - see SCHEMA_VERSION."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    has_tables = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'pieces'"
    ).fetchone()
    if has_tables and version != SCHEMA_VERSION:
        for name in ("pieces_fts", "pieces", "vectors", "index_meta"):
            conn.execute(f"DROP TABLE IF EXISTS {name}")
        conn.commit()
    if not has_tables or version != SCHEMA_VERSION:
        # Only takes effect on an empty file, or with the VACUUM after it.
        conn.execute(f"PRAGMA page_size = {PAGE_SIZE}")
        conn.execute("VACUUM")
    conn.executescript(_SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return conn


# ---------------------------------------------------------------------
# Collecting pieces from every source
# ---------------------------------------------------------------------


def collect_pieces(conn: sqlite3.Connection) -> list[Piece]:
    """Every piece the index should contain right now, built fresh from
    the main database and the citation data files."""
    pieces: list[Piece] = []
    pieces.extend(_scripture_pieces(conn))
    pieces.extend(_discourse_pieces(conn))
    pieces.extend(_topic_pieces(conn))
    pieces.extend(_cross_reference_pieces(conn))
    pieces.extend(_user_cross_reference_pieces(conn))
    pieces.extend(_citing_work_pieces())
    pieces.extend(_note_pieces(conn))
    return pieces


def _windows(lengths: list[int]) -> list[tuple[int, int]]:
    """[start, end) index ranges over a chapter's verses (given their text
    lengths): each window takes up to WINDOW verses without going over
    WINDOW_MAX_CHARS (a single verse longer than that still gets a window
    of its own), and the next window starts on the previous one's last
    verse, so neighbors overlap by one."""
    ranges: list[tuple[int, int]] = []
    start = 0
    count = len(lengths)
    while start < count:
        end = start + 1
        total = lengths[start]
        while end < count and end - start < WINDOW and total + lengths[end] <= WINDOW_MAX_CHARS:
            total += lengths[end]
            end += 1
        ranges.append((start, end))
        if end >= count:
            break
        start = end - 1 if end - start > 1 else end
    return ranges


def _scripture_pieces(conn: sqlite3.Connection) -> list[Piece]:
    rows = conn.execute(
        "SELECT vol.slug AS volume_slug, b.name AS book_name, "
        "c.id AS chapter_id, c.chapter_number, v.verse_number, v.text "
        "FROM verses v JOIN chapters c ON c.id = v.chapter_id "
        "JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id "
        "WHERE vol.slug != 'journal-of-discourses' "
        "ORDER BY vol.sort_order, b.sort_order, c.chapter_number, v.verse_number"
    ).fetchall()
    pieces = []
    chapter_rows: list[sqlite3.Row] = []

    def flush() -> None:
        if not chapter_rows:
            return
        first = chapter_rows[0]
        for lo, hi in _windows([len(r["text"]) for r in chapter_rows]):
            window = chapter_rows[lo:hi]
            start, end = window[0]["verse_number"], window[-1]["verse_number"]
            verses = f"{start}" if start == end else f"{start}-{end}"
            reference = f"{first['book_name']} {first['chapter_number']}:{verses}"
            body = " ".join(r["text"] for r in window)
            pieces.append(
                Piece(
                    key=f"scripture:{first['volume_slug']}:{first['book_name']}:"
                    f"{first['chapter_number']}:{verses}",
                    kind="scripture",
                    heading=reference,
                    body=body,
                    volume_slug=first["volume_slug"],
                    chapter_id=first["chapter_id"],
                    meta={
                        "reference": reference,
                        "book": first["book_name"],
                        "chapter": first["chapter_number"],
                        "verse_start": start,
                        "verse_end": end,
                    },
                )
            )

    for row in rows:
        if chapter_rows and row["chapter_id"] != chapter_rows[0]["chapter_id"]:
            flush()
            chapter_rows = []
        chapter_rows.append(row)
    flush()
    return pieces


def split_discourse(text: str) -> list[str]:
    """Paragraph-packed parts of roughly DISCOURSE_TARGET_CHARS, never
    over DISCOURSE_MAX_CHARS - a paragraph longer than that on its own is
    split further at sentence boundaries (or, failing that, hard-split)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= DISCOURSE_MAX_CHARS:
            units.append(paragraph)
            continue
        current = ""
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            while len(sentence) > DISCOURSE_MAX_CHARS:
                if current:
                    units.append(current)
                    current = ""
                units.append(sentence[:DISCOURSE_MAX_CHARS])
                sentence = sentence[DISCOURSE_MAX_CHARS:]
            if current and len(current) + 1 + len(sentence) > DISCOURSE_TARGET_CHARS:
                units.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            units.append(current)

    parts: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + 2 + len(unit) > DISCOURSE_MAX_CHARS:
            parts.append(current)
            current = unit
        else:
            current = f"{current}\n\n{unit}" if current else unit
        if len(current) >= DISCOURSE_TARGET_CHARS:
            parts.append(current)
            current = ""
    if current:
        parts.append(current)
    return parts


def _discourse_pieces(conn: sqlite3.Connection) -> list[Piece]:
    rows = conn.execute(
        "SELECT c.id AS chapter_id, b.name AS book_name, c.chapter_number, c.title, "
        "c.speaker, c.discourse_date, "
        "GROUP_CONCAT(v.text, char(10) || char(10)) AS text "
        "FROM chapters c JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id "
        "JOIN verses v ON v.chapter_id = c.id "
        "WHERE vol.slug = 'journal-of-discourses' "
        "GROUP BY c.id ORDER BY b.sort_order, c.chapter_number"
    ).fetchall()
    pieces = []
    for row in rows:
        title = (row["title"] or "").split("—")[0].strip()
        if len(title) > MAX_HEADING_TITLE_CHARS:
            title = title[:MAX_HEADING_TITLE_CHARS].rsplit(" ", 1)[0] + "..."
        # 325 of the 1,003 discourses have no recorded date.
        byline = ", ".join(part for part in (row["speaker"], row["discourse_date"]) if part)
        heading = f"Journal of Discourses, {row['book_name']}: \"{title}\" - {byline}"
        for part_number, part in enumerate(split_discourse(row["text"]), start=1):
            pieces.append(
                Piece(
                    key=f"discourse:{row['book_name']}:{row['chapter_number']}:{part_number}",
                    kind="discourse",
                    heading=heading,
                    body=part,
                    volume_slug="journal-of-discourses",
                    chapter_id=row["chapter_id"],
                    meta={
                        "title": row["title"],
                        "speaker": row["speaker"],
                        "date": row["discourse_date"],
                        "book": row["book_name"],
                        "part": part_number,
                    },
                )
            )
    return pieces


def _topic_pieces(conn: sqlite3.Connection) -> list[Piece]:
    pieces = []
    for topic in conn.execute("SELECT id, name, slug, description FROM topics ORDER BY sort_order"):
        references = [
            r["reference"]
            for r in conn.execute(
                "SELECT reference FROM topic_verses WHERE topic_id = ? ORDER BY sort_order LIMIT ?",
                (topic["id"], MAX_TOPIC_REFERENCES),
            )
        ]
        body = topic["description"]
        if references:
            body += "\nScriptures: " + "; ".join(references)
        pieces.append(
            Piece(
                key=f"topic:{topic['slug']}",
                kind="topic",
                heading=f"Topical Guide: {topic['name']}",
                body=body,
                meta={"topic_id": topic["id"], "name": topic["name"], "slug": topic["slug"]},
            )
        )
    return pieces


def _range_label(book: str, chapter: int, start: int | None, end: int | None) -> str:
    if start is None:
        return f"{book} {chapter}"
    if end is None or end == start:
        return f"{book} {chapter}:{start}"
    return f"{book} {chapter}:{start}-{end}"


def _cross_reference_text(row: sqlite3.Row, verb: str) -> tuple[str, str, str, str]:
    """(heading, body, this side's reference, the other side's)."""
    a = _range_label(row["book_name"], row["chapter_number"], row["verse_start"], row["verse_end"])
    b = _range_label(
        row["related_book_name"],
        row["related_chapter_number"],
        row["related_verse_start"],
        row["related_verse_end"],
    )
    return f"Cross-reference: {a} {verb} {b}", row["note"] or "", a, b


def _cross_reference_pieces(conn: sqlite3.Connection) -> list[Piece]:
    topic_names = {r["slug"]: r["name"] for r in conn.execute("SELECT slug, name FROM topics")}
    pieces = []
    for row in conn.execute("SELECT * FROM cross_references ORDER BY sort_order"):
        verb = _RELATIONSHIP_VERB.get(row["relationship"], "relates to")
        heading, body, a, b = _cross_reference_text(row, verb)
        topics = [
            topic_names[s.strip()]
            for s in row["topic_slugs"].split(",")
            if s.strip() in topic_names
        ]
        if topics:
            body += "\nTopics: " + ", ".join(topics)
        pieces.append(
            Piece(
                key=f"cross_reference:{row['volume_slug']}:{a}|{row['related_volume_slug']}:{b}",
                kind="cross_reference",
                heading=heading,
                body=body,
                volume_slug=row["volume_slug"],
                meta={
                    "reference": a,
                    "related_reference": b,
                    "related_volume_slug": row["related_volume_slug"],
                    "relationship": row["relationship"],
                },
            )
        )
    return pieces


def _user_cross_reference_pieces(conn: sqlite3.Connection) -> list[Piece]:
    pieces = []
    for row in conn.execute(
        "SELECT * FROM user_cross_references WHERE deleted_at IS NULL ORDER BY id"
    ):
        heading, body, a, b = _cross_reference_text(row, "(the reader's own link) see also")
        pieces.append(
            Piece(
                key=f"user_cross_reference:{row['id']}",
                kind="user_cross_reference",
                heading=heading,
                body=body,
                volume_slug=row["volume_slug"],
                meta={
                    "reference": a,
                    "related_reference": b,
                    "related_volume_slug": row["related_volume_slug"],
                },
            )
        )
    return pieces


def _citing_work_pieces() -> list[Piece]:
    pieces = []
    for work in iter_citing_works():
        kind = "talk" if work.source_label == "General Conference" else "article"
        byline = ", ".join(part for part in (work.speaker, work.date) if part)
        heading = f"{work.source_label}: \"{work.talk_title}\""
        if byline:
            heading += f" - {byline}"
        body = "Cites: " + "; ".join(work.references[:MAX_CARD_REFERENCES])
        pieces.append(
            Piece(
                key=f"{kind}:{work.url}",
                kind=kind,
                heading=heading,
                body=body,
                meta={
                    "title": work.talk_title,
                    "speaker": work.speaker,
                    "date": work.date,
                    "url": work.url,
                    "source": work.source_label,
                },
            )
        )
    return pieces


def _note_pieces(conn: sqlite3.Connection) -> list[Piece]:
    rows = conn.execute(
        "SELECT n.id, n.text, vol.slug AS volume_slug, "
        "COALESCE(v.chapter_id, n.chapter_id) AS chapter_id, "
        "COALESCE(v.reference, b.name || ' ' || c.chapter_number) AS reference "
        "FROM notes n LEFT JOIN verses v ON v.id = n.verse_id "
        "JOIN chapters c ON c.id = COALESCE(v.chapter_id, n.chapter_id) "
        "JOIN books b ON b.id = c.book_id JOIN volumes vol ON vol.id = b.volume_id "
        "WHERE n.deleted_at IS NULL AND TRIM(n.text) != ''"
    ).fetchall()
    return [
        Piece(
            key=f"note:{r['id']}",
            kind="note",
            heading=f"My note on {r['reference']}",
            body=r["text"],
            volume_slug=r["volume_slug"],
            chapter_id=r["chapter_id"],
            meta={"reference": r["reference"], "note_id": r["id"]},
        )
        for r in rows
    ]


# ---------------------------------------------------------------------
# Keeping the index in step with its sources
# ---------------------------------------------------------------------


def sync_pieces(index_conn: sqlite3.Connection, pieces: list[Piece]) -> None:
    """Make the pieces table match `pieces` exactly - insert new keys,
    update changed ones, drop ones no longer produced (a deleted note, a
    removed cross-reference) - then drop any vector no piece uses anymore.
    Vectors for unchanged text are kept, so only new/changed text ever
    needs embedding again."""
    existing = {
        r["key"]: (r["id"], r["content_hash"], r["meta"])
        for r in index_conn.execute("SELECT id, key, content_hash, meta FROM pieces")
    }
    wanted_keys = set()
    for piece in pieces:
        wanted_keys.add(piece.key)
        meta = json.dumps(piece.meta, ensure_ascii=False, sort_keys=True)
        content_hash = piece.content_hash
        current = existing.get(piece.key)
        if current is None:
            index_conn.execute(
                "INSERT INTO pieces "
                "(key, kind, volume_slug, chapter_id, heading, body, meta, content_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (piece.key, piece.kind, piece.volume_slug, piece.chapter_id, piece.heading,
                 piece.body, meta, content_hash),
            )
        elif current[1] != content_hash or current[2] != meta:
            index_conn.execute(
                "UPDATE pieces SET kind = ?, volume_slug = ?, chapter_id = ?, heading = ?, body = ?, "
                "meta = ?, content_hash = ? WHERE id = ?",
                (piece.kind, piece.volume_slug, piece.chapter_id, piece.heading, piece.body, meta,
                 content_hash, current[0]),
            )
    stale_ids = [(piece_id,) for key, (piece_id, _h, _m) in existing.items() if key not in wanted_keys]
    index_conn.executemany("DELETE FROM pieces WHERE id = ?", stale_ids)
    index_conn.execute(
        "DELETE FROM vectors WHERE content_hash NOT IN (SELECT content_hash FROM pieces)"
    )
    index_conn.commit()


@dataclass(frozen=True)
class EmbeddingFormat:
    """How a given embedding model expects its input. Some models are
    trained with task prefixes and work noticeably better when given them
    - a question and a passage aren't embedded the same way. `version`
    goes into the index's model fingerprint, so changing a format here
    re-embeds everything with it next build."""

    name: str
    query: str = "{q}"
    document: str = "{heading}\n{body}"
    version: int = 1

    def format_query(self, question: str) -> str:
        return self.query.format(q=question)

    def format_document(self, heading: str, body: str) -> str:
        return self.document.format(heading=heading, body=body).strip()


# Matched by substring of the configured model name, first match wins.
# Prefixes are each model's own documented ones.
EMBEDDING_FORMATS = (
    EmbeddingFormat(
        "embeddinggemma",
        query="task: search result | query: {q}",
        document="title: {heading} | text: {body}",
    ),
    EmbeddingFormat(
        "nomic-embed",
        query="search_query: {q}",
        document="search_document: {heading}\n{body}",
    ),
)
_DEFAULT_FORMAT = EmbeddingFormat("default")


def embedding_format(model: str) -> EmbeddingFormat:
    lowered = model.lower()
    return next((f for f in EMBEDDING_FORMATS if f.name in lowered), _DEFAULT_FORMAT)


def format_query(model: str, question: str) -> str:
    return embedding_format(model).format_query(question)


def canonical_model(model: str) -> str:
    """The same model can be named more than one way - Ollama treats
    "embeddinggemma" and "embeddinggemma:latest" as one model (":latest"
    is its default tag), and its model list reports the latter. Compared
    in this form, so typing one and picking the other from a list (as the
    AI Setup Wizard does) isn't mistaken for a model change, which would
    discard every vector."""
    model = model.strip()
    return model[: -len(":latest")] if model.endswith(":latest") else model


def _fingerprint(model: str, dimensions: int | None) -> dict:
    fmt = embedding_format(model)
    return {
        "model": canonical_model(model),
        "dimensions": dimensions,
        "format": f"{fmt.name}:{fmt.version}",
    }


def configure_model(index_conn: sqlite3.Connection, model: str, dimensions: int | None) -> bool:
    """Record which embedding model (and requested dimensions) this
    index's vectors come from. Returns True if that changed from what was
    recorded - in which case every existing vector was just deleted, since
    vectors from two different models aren't comparable."""
    wanted = _fingerprint(model, dimensions)
    fingerprint = json.dumps(wanted, sort_keys=True)
    row = index_conn.execute("SELECT value FROM index_meta WHERE key = 'embedding'").fetchone()
    if row is not None:
        recorded = json.loads(row["value"])
        recorded["model"] = canonical_model(recorded.get("model", ""))
        if recorded == wanted:
            if row["value"] != fingerprint:  # store it in canonical form
                index_conn.execute(
                    "UPDATE index_meta SET value = ? WHERE key = 'embedding'", (fingerprint,)
                )
                index_conn.commit()
            return False
    index_conn.execute("DELETE FROM vectors")
    index_conn.execute("DELETE FROM index_meta WHERE key = 'vector_dimensions'")
    index_conn.execute(
        "INSERT OR REPLACE INTO index_meta (key, value) VALUES ('embedding', ?)", (fingerprint,)
    )
    index_conn.commit()
    return row is not None


def recorded_model(index_conn: sqlite3.Connection) -> tuple[str | None, int | None]:
    row = index_conn.execute("SELECT value FROM index_meta WHERE key = 'embedding'").fetchone()
    if row is None:
        return None, None
    value = json.loads(row["value"])
    return value["model"], value["dimensions"]


def pending_hashes(index_conn: sqlite3.Connection) -> list[str]:
    """Every content_hash that still needs a vector, each once, in the
    order their pieces were added - computed once per build (see
    embeddings.IndexBuilder), not per batch: re-scanning ~80k pieces after
    every batch cost far more time than the batches themselves on a fast
    endpoint."""
    return [
        r["content_hash"]
        for r in index_conn.execute(
            "SELECT p.content_hash FROM pieces p "
            "LEFT JOIN vectors v ON v.content_hash = p.content_hash "
            "WHERE v.content_hash IS NULL "
            "GROUP BY p.content_hash ORDER BY MIN(p.id)"
        )
    ]


def texts_for(
    index_conn: sqlite3.Connection, hashes: list[str], model: str
) -> list[tuple[str, str]]:
    """(content_hash, text to embed) for each of `hashes`, in the same
    order - the text formatted the way `model` expects a document."""
    if not hashes:
        return []
    fmt = embedding_format(model)
    rows = index_conn.execute(
        f"SELECT content_hash, heading, body FROM pieces "
        f"WHERE content_hash IN ({','.join('?' * len(hashes))})",
        hashes,
    ).fetchall()
    by_hash = {r["content_hash"]: fmt.format_document(r["heading"], r["body"]) for r in rows}
    return [(h, by_hash[h]) for h in hashes if h in by_hash]


def store_vectors(index_conn: sqlite3.Connection, items: list[tuple[str, list[float]]]) -> None:
    """Persist a batch of (content_hash, raw embedding) pairs - normalized
    and stored as float16. Raises ValueError if a vector's length doesn't
    match the ones already stored (a misbehaving endpoint, or a model
    swapped behind the same name)."""
    if not items:
        return
    row = index_conn.execute(
        "SELECT value FROM index_meta WHERE key = 'vector_dimensions'"
    ).fetchone()
    expected = int(row["value"]) if row else None
    rows = []
    for content_hash, raw in items:
        vector = np.asarray(raw, dtype=np.float32)
        if expected is None:
            expected = len(vector)
            index_conn.execute(
                "INSERT INTO index_meta (key, value) VALUES ('vector_dimensions', ?)",
                (str(expected),),
            )
        if len(vector) != expected:
            raise ValueError(
                f"The embedding endpoint returned a {len(vector)}-number vector, but this "
                f"index's other vectors have {expected}."
            )
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector = vector / norm
        rows.append((content_hash, vector.astype(np.float16).tobytes()))
    index_conn.executemany(
        "INSERT OR REPLACE INTO vectors (content_hash, vector) VALUES (?, ?)", rows
    )
    index_conn.commit()


def index_status(index_conn: sqlite3.Connection) -> IndexStatus:
    pieces = index_conn.execute("SELECT COUNT(*) FROM pieces").fetchone()[0]
    unique_texts = index_conn.execute(
        "SELECT COUNT(DISTINCT content_hash) FROM pieces"
    ).fetchone()[0]
    embedded = index_conn.execute(
        "SELECT COUNT(*) FROM vectors WHERE content_hash IN (SELECT content_hash FROM pieces)"
    ).fetchone()[0]
    pending_chars = index_conn.execute(
        "SELECT COALESCE(SUM(chars), 0) FROM ("
        "  SELECT MIN(LENGTH(p.heading) + LENGTH(p.body)) AS chars FROM pieces p "
        "  LEFT JOIN vectors v ON v.content_hash = p.content_hash "
        "  WHERE v.content_hash IS NULL GROUP BY p.content_hash)"
    ).fetchone()[0]
    model, dimensions = recorded_model(index_conn)
    return IndexStatus(pieces, unique_texts, embedded, pending_chars, model, dimensions)


@dataclass(frozen=True)
class BuildEstimate:
    unique_texts: int
    embedded: int
    pending_chars: int
    total_chars: int

    @property
    def pending_tokens(self) -> int:
        # ~4 characters per token for English prose - the usual rule of
        # thumb, close enough for a cost/time estimate.
        return self.pending_chars // 4


def estimate_build(
    scripture_conn: sqlite3.Connection,
    index_conn: sqlite3.Connection,
    model: str,
    dimensions: int | None,
) -> BuildEstimate:
    """What a build with this model would have to embed, without
    touching the index (collecting pieces takes about a second; syncing
    them, which the build itself does, takes longer the first time). A
    model/dimensions change means everything is pending again."""
    texts = {p.content_hash: len(p.text) for p in collect_pieces(scripture_conn)}
    recorded, recorded_dimensions = recorded_model(index_conn)
    if (
        recorded is not None
        and canonical_model(recorded) == canonical_model(model)
        and recorded_dimensions == dimensions
    ):
        embedded_hashes = {
            r[0] for r in index_conn.execute("SELECT content_hash FROM vectors")
        }
    else:
        embedded_hashes = set()
    embedded = sum(1 for h in texts if h in embedded_hashes)
    pending_chars = sum(length for h, length in texts.items() if h not in embedded_hashes)
    return BuildEstimate(len(texts), embedded, pending_chars, sum(texts.values()))


# ---------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------


class StudyIndex:
    """Searches one study_index.db. Vectors are loaded into memory on
    first use (and again after `invalidate()`, e.g. once a build adds
    more) - kept as float16 to halve memory, with similarity computed in
    float32 blocks."""

    _BLOCK_ROWS = 8192

    def __init__(self, index_conn: sqlite3.Connection):
        self.conn = index_conn
        self._ids: np.ndarray | None = None
        self._matrix: np.ndarray | None = None
        self._kinds: np.ndarray | None = None
        self._volumes: np.ndarray | None = None

    def invalidate(self) -> None:
        self._ids = self._matrix = self._kinds = self._volumes = None

    def is_loaded(self) -> bool:
        return self._ids is not None

    @staticmethod
    def _arrays_from(conn: sqlite3.Connection) -> tuple:
        rows = conn.execute(
            "SELECT p.id, p.kind, p.volume_slug, v.vector FROM pieces p "
            "JOIN vectors v ON v.content_hash = p.content_hash ORDER BY p.id"
        ).fetchall()
        ids = np.array([r[0] for r in rows], dtype=np.int64)
        kinds = np.array([r[1] for r in rows], dtype=object)
        volumes = np.array([r[2] or "" for r in rows], dtype=object)
        if rows:
            matrix = np.vstack([np.frombuffer(r[3], dtype=np.float16) for r in rows])
        else:
            matrix = np.zeros((0, 0), dtype=np.float16)
        return ids, kinds, volumes, matrix

    @staticmethod
    def load_arrays(index_path: Path) -> tuple:
        """The in-memory search arrays, read through a connection of its
        own - safe to call from a background thread (see
        study_ask._VectorLoader), then hand the result to adopt_arrays()
        on the thread that owns this StudyIndex."""
        conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
        try:
            return StudyIndex._arrays_from(conn)
        finally:
            conn.close()

    def adopt_arrays(self, arrays: tuple) -> None:
        self._ids, self._kinds, self._volumes, self._matrix = arrays

    def _load(self) -> None:
        if self._ids is None:
            self.adopt_arrays(self._arrays_from(self.conn))

    def _mask(self, kinds: set[str] | None, volume_slugs: set[str] | None) -> np.ndarray:
        mask = np.ones(len(self._ids), dtype=bool)
        if kinds:
            mask &= np.isin(self._kinds, list(kinds))
        if volume_slugs:
            # Pieces with no volume (topics, talk cards) never match a
            # volume filter - that filter means "only scripture from X".
            mask &= np.isin(self._volumes, list(volume_slugs))
        return mask

    def _semantic_ranking(
        self, query_vector: list[float], kinds: set[str] | None, volume_slugs: set[str] | None,
        limit: int,
    ) -> list[int]:
        self._load()
        if len(self._ids) == 0:
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        if query.shape[0] != self._matrix.shape[1]:
            return []
        norm = float(np.linalg.norm(query))
        if norm > 0:
            query = query / norm
        scores = np.empty(len(self._ids), dtype=np.float32)
        for start in range(0, len(self._ids), self._BLOCK_ROWS):
            block = self._matrix[start:start + self._BLOCK_ROWS].astype(np.float32)
            scores[start:start + len(block)] = block @ query
        scores[~self._mask(kinds, volume_slugs)] = -np.inf
        candidates = min(limit, int(np.isfinite(scores).sum()))
        if candidates <= 0:
            return []
        top = np.argpartition(-scores, candidates - 1)[:candidates]
        top = top[np.argsort(-scores[top])]
        return [int(self._ids[i]) for i in top]

    def _keyword_ranking(
        self, query_text: str, kinds: set[str] | None, volume_slugs: set[str] | None, limit: int
    ) -> list[int]:
        keywords = extract_keywords(query_text, limit=12)
        if not keywords:
            return []
        match = " OR ".join('"' + k.replace('"', '""') + '"' for k in keywords)
        sql = (
            "SELECT p.id FROM pieces_fts JOIN pieces p ON p.id = pieces_fts.rowid "
            "WHERE pieces_fts MATCH ?"
        )
        params: list = [match]
        if kinds:
            sql += f" AND p.kind IN ({','.join('?' * len(kinds))})"
            params.extend(sorted(kinds))
        if volume_slugs:
            sql += f" AND p.volume_slug IN ({','.join('?' * len(volume_slugs))})"
            params.extend(sorted(volume_slugs))
        # A heading word counts a fifth as much as a body word.
        sql += " ORDER BY bm25(pieces_fts, 0.2, 1.0) LIMIT ?"
        params.append(limit)
        return [r["id"] for r in self.conn.execute(sql, params)]

    def search(
        self,
        query_text: str,
        query_vector: list[float] | None = None,
        *,
        kinds: set[str] | None = None,
        volume_slugs: set[str] | None = None,
        kind_limits: dict[str, int] | None = None,
        limit: int = 20,
    ) -> list[SearchHit]:
        """The best `limit` pieces for a question, fusing semantic
        similarity (when `query_vector` - the question embedded with the
        index's own model - is given) with keyword relevance. Optionally
        restricted to certain kinds and/or volumes, and/or capped per kind
        (`kind_limits`, e.g. MIXED_KIND_LIMITS) so no one kind of source
        can fill the list.

        Scripture results are consolidated: overlapping or adjacent
        windows of the same chapter merge into one wider result (e.g.
        Alma 32:27-29 and 32:29-31 become Alma 32:27-31) at the higher-
        ranked one's place, and the Bible and the JST - which share book/
        chapter/verse numbering and mostly the same wording - count as the
        same chapter for this."""
        candidates = limit * 5
        semantic = (
            self._semantic_ranking(query_vector, kinds, volume_slugs, candidates)
            if query_vector is not None
            else []
        )
        keyword = self._keyword_ranking(query_text, kinds, volume_slugs, candidates)

        fused: dict[int, float] = {}
        semantic_rank = {piece_id: rank for rank, piece_id in enumerate(semantic, start=1)}
        keyword_rank = {piece_id: rank for rank, piece_id in enumerate(keyword, start=1)}
        for ranking in (semantic_rank, keyword_rank):
            for piece_id, rank in ranking.items():
                fused[piece_id] = fused.get(piece_id, 0.0) + 1.0 / (RRF_K + rank)
        ranked = sorted(fused, key=lambda pid: fused[pid], reverse=True)
        if not ranked:
            return []

        rows = {
            r["id"]: r
            for r in self.conn.execute(
                f"SELECT * FROM pieces WHERE id IN ({','.join('?' * len(ranked))})", ranked
            )
        }
        hits: list[SearchHit] = []
        kind_counts: dict[str, int] = {}
        # (book, chapter) -> indexes into `hits` of that chapter's results
        by_chapter: dict[tuple, list[int]] = {}
        for pid in ranked:
            row = rows.get(pid)
            if row is None:
                continue
            meta = json.loads(row["meta"])
            if row["kind"] == "scripture" and self._merge_into(hits, by_chapter, meta):
                continue
            if kind_limits and kind_counts.get(row["kind"], 0) >= kind_limits.get(row["kind"], limit):
                continue
            kind_counts[row["kind"]] = kind_counts.get(row["kind"], 0) + 1
            if row["kind"] == "scripture":
                by_chapter.setdefault((meta.get("book"), meta.get("chapter")), []).append(len(hits))
            hits.append(
                SearchHit(
                    piece_id=pid,
                    key=row["key"],
                    kind=row["kind"],
                    text=f"{row['heading']}\n{row['body']}" if row["body"] else row["heading"],
                    volume_slug=row["volume_slug"],
                    chapter_id=row["chapter_id"],
                    meta=meta,
                    score=fused[pid],
                    semantic_rank=semantic_rank.get(pid),
                    keyword_rank=keyword_rank.get(pid),
                )
            )
            if len(hits) >= limit:
                break
        return hits

    @staticmethod
    def _merge_into(hits: list[SearchHit], by_chapter: dict[tuple, list[int]], meta: dict) -> bool:
        """If this scripture window overlaps or touches one already in
        `hits` from the same chapter, widen that one to cover both and
        return True (this window takes no slot of its own)."""
        start, end = meta.get("verse_start"), meta.get("verse_end")
        if start is None:
            return False
        for index in by_chapter.get((meta.get("book"), meta.get("chapter")), []):
            existing = hits[index]
            ex_start, ex_end = existing.meta["verse_start"], existing.meta["verse_end"]
            if start <= ex_end + 1 and end >= ex_start - 1:
                new_start, new_end = min(start, ex_start), max(end, ex_end)
                merged_meta = dict(existing.meta)
                merged_meta.update(
                    verse_start=new_start,
                    verse_end=new_end,
                    reference=f"{merged_meta['book']} {merged_meta['chapter']}:"
                    + (f"{new_start}" if new_start == new_end else f"{new_start}-{new_end}"),
                )
                hits[index] = replace(existing, meta=merged_meta)
                return True
        return False
