"""Repository layer over the scripture database.

The UI talks to these functions, never to raw SQL directly - keeps the
query logic in one place and makes the UI layer easy to test/reason about
independent of the schema.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Volume:
    id: int
    name: str
    slug: str


@dataclass(frozen=True)
class Testament:
    id: int
    volume_id: int
    name: str


@dataclass(frozen=True)
class Book:
    id: int
    name: str


@dataclass(frozen=True)
class Chapter:
    id: int
    chapter_number: int
    title: str | None = None
    speaker: str | None = None
    discourse_date: str | None = None


@dataclass(frozen=True)
class Verse:
    id: int
    verse_number: int
    text: str
    reference: str
    chapter_id: int


@dataclass(frozen=True)
class Note:
    id: int
    text: str
    verse_id: int | None
    chapter_id: int | None
    updated_at: str


@dataclass(frozen=True)
class Tag:
    id: int
    name: str


@dataclass(frozen=True)
class Highlight:
    """A highlighted substring of a verse: verse.text[start_offset:end_offset]
    (a Python-slice-style [start, end) range), in one of three colors."""

    id: int
    verse_id: int
    color: str
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class Topic:
    id: int
    name: str
    slug: str
    description: str


@dataclass(frozen=True)
class TopicTalk:
    """Same metadata-only shape as citations.py's Citation - talk title,
    speaker, date, and its churchofjesuschrist.org URL, never talk text."""

    talk_title: str
    speaker: str
    date: str
    url: str


@dataclass(frozen=True)
class NoteResult:
    """A note-search hit: `reference` is the verse's reference, or a
    "Book chapter_number" label for a chapter-level note."""

    id: int
    text: str
    chapter_id: int
    reference: str


@dataclass(frozen=True)
class TaggedItem:
    """One verse or chapter a tag is attached to."""

    chapter_id: int
    reference: str


@dataclass(frozen=True)
class ChapterMatch:
    chapter_id: int
    label: str


def get_volumes(conn: sqlite3.Connection) -> list[Volume]:
    rows = conn.execute(
        "SELECT id, name, slug FROM volumes ORDER BY sort_order"
    ).fetchall()
    return [Volume(r["id"], r["name"], r["slug"]) for r in rows]


def get_volume(conn: sqlite3.Connection, volume_id: int) -> Volume:
    r = conn.execute(
        "SELECT id, name, slug FROM volumes WHERE id = ?", (volume_id,)
    ).fetchone()
    return Volume(r["id"], r["name"], r["slug"])


def get_testaments(conn: sqlite3.Connection, volume_id: int) -> list[Testament]:
    """Returns an empty list for volumes with no testament tier
    (everything except the Bible)."""
    rows = conn.execute(
        "SELECT id, volume_id, name FROM testaments "
        "WHERE volume_id = ? ORDER BY sort_order",
        (volume_id,),
    ).fetchall()
    return [Testament(r["id"], r["volume_id"], r["name"]) for r in rows]


def get_testament(conn: sqlite3.Connection, testament_id: int) -> Testament:
    r = conn.execute(
        "SELECT id, volume_id, name FROM testaments WHERE id = ?", (testament_id,)
    ).fetchone()
    return Testament(r["id"], r["volume_id"], r["name"])


def get_books(
    conn: sqlite3.Connection, volume_id: int, testament_id: int | None = None
) -> list[Book]:
    if testament_id is not None:
        rows = conn.execute(
            "SELECT id, name FROM books "
            "WHERE volume_id = ? AND testament_id = ? ORDER BY sort_order",
            (volume_id, testament_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name FROM books "
            "WHERE volume_id = ? AND testament_id IS NULL ORDER BY sort_order",
            (volume_id,),
        ).fetchall()
    return [Book(r["id"], r["name"]) for r in rows]


def get_book(conn: sqlite3.Connection, book_id: int) -> Book:
    r = conn.execute("SELECT id, name FROM books WHERE id = ?", (book_id,)).fetchone()
    return Book(r["id"], r["name"])


def get_chapters(conn: sqlite3.Connection, book_id: int) -> list[Chapter]:
    rows = conn.execute(
        "SELECT id, chapter_number, title, speaker, discourse_date FROM chapters "
        "WHERE book_id = ? ORDER BY chapter_number",
        (book_id,),
    ).fetchall()
    return [
        Chapter(r["id"], r["chapter_number"], r["title"], r["speaker"], r["discourse_date"])
        for r in rows
    ]


def get_chapter(conn: sqlite3.Connection, chapter_id: int) -> Chapter:
    r = conn.execute(
        "SELECT id, chapter_number, title, speaker, discourse_date FROM chapters WHERE id = ?",
        (chapter_id,),
    ).fetchone()
    return Chapter(r["id"], r["chapter_number"], r["title"], r["speaker"], r["discourse_date"])


def get_verses(conn: sqlite3.Connection, chapter_id: int) -> list[Verse]:
    rows = conn.execute(
        "SELECT id, verse_number, text, reference, chapter_id FROM verses "
        "WHERE chapter_id = ? ORDER BY verse_number",
        (chapter_id,),
    ).fetchall()
    return [
        Verse(r["id"], r["verse_number"], r["text"], r["reference"], r["chapter_id"])
        for r in rows
    ]


def get_verse_by_reference(
    conn: sqlite3.Connection, book_name: str, chapter_number: int, verse_number: int
) -> Verse | None:
    """Look up a verse by book name + chapter + verse number (e.g. for the
    Scripture of the Day pool, which references verses this way rather
    than by id). None if it doesn't resolve to an actual verse."""
    r = conn.execute(
        "SELECT v.id, v.verse_number, v.text, v.reference, v.chapter_id "
        "FROM verses v "
        "JOIN chapters c ON c.id = v.chapter_id "
        "JOIN books b ON b.id = c.book_id "
        "WHERE b.name = ? AND c.chapter_number = ? AND v.verse_number = ?",
        (book_name, chapter_number, verse_number),
    ).fetchone()
    if not r:
        return None
    return Verse(r["id"], r["verse_number"], r["text"], r["reference"], r["chapter_id"])


def get_chapter_location(
    conn: sqlite3.Connection, chapter_id: int
) -> tuple[Volume, Testament | None, Book, Chapter] | None:
    """Walk chapter -> book -> volume/testament, for jumping straight to a
    chapter (e.g. from a search result) and still building a correct
    breadcrumb path."""
    r = conn.execute(
        "SELECT vol.id AS vol_id, vol.name AS vol_name, vol.slug AS vol_slug, "
        "t.id AS t_id, t.volume_id AS t_volume_id, t.name AS t_name, "
        "b.id AS b_id, b.name AS b_name, "
        "c.id AS c_id, c.chapter_number AS c_num "
        "FROM chapters c "
        "JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id "
        "LEFT JOIN testaments t ON t.id = b.testament_id "
        "WHERE c.id = ?",
        (chapter_id,),
    ).fetchone()
    if not r:
        return None
    volume = Volume(r["vol_id"], r["vol_name"], r["vol_slug"])
    testament = (
        Testament(r["t_id"], r["t_volume_id"], r["t_name"]) if r["t_id"] is not None else None
    )
    book = Book(r["b_id"], r["b_name"])
    chapter = Chapter(r["c_id"], r["c_num"])
    return volume, testament, book, chapter


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_device_id(conn: sqlite3.Connection) -> str:
    """This installation's permanent sync identity - see db.py's
    `_ensure_device_id`, which guarantees this is always present."""
    return get_setting(conn, "device_id")


def get_highlights(conn: sqlite3.Connection, chapter_id: int) -> dict[int, list[Highlight]]:
    """verse_id -> that verse's highlighted ranges (there can be more than
    one per verse), for drawing highlight backgrounds without an N+1
    query. Ordered by start_offset so callers can render them in text
    order without re-sorting."""
    rows = conn.execute(
        "SELECT h.id, h.verse_id, h.color, h.start_offset, h.end_offset "
        "FROM highlights h JOIN verses v ON v.id = h.verse_id "
        "WHERE v.chapter_id = ? AND h.deleted_at IS NULL ORDER BY h.start_offset",
        (chapter_id,),
    ).fetchall()
    by_verse: dict[int, list[Highlight]] = {}
    for r in rows:
        by_verse.setdefault(r["verse_id"], []).append(
            Highlight(r["id"], r["verse_id"], r["color"], r["start_offset"], r["end_offset"])
        )
    return by_verse


def add_highlight(
    conn: sqlite3.Connection, verse_id: int, color: str, start_offset: int, end_offset: int
) -> None:
    """Highlight verse.text[start_offset:end_offset] in this color. Ranges
    never overlap, so any existing range(s) intersecting this one are
    removed first - the newest selection always wins over what it covers."""
    _delete_overlapping(conn, verse_id, start_offset, end_offset)
    conn.execute(
        "INSERT INTO highlights (verse_id, color, start_offset, end_offset, updated_at) "
        "VALUES (?, ?, ?, ?, datetime('now'))",
        (verse_id, color, start_offset, end_offset),
    )
    conn.commit()


def clear_highlight_range(
    conn: sqlite3.Connection, verse_id: int, start_offset: int, end_offset: int
) -> None:
    """Remove whatever highlight range(s) intersect
    verse.text[start_offset:end_offset]."""
    _delete_overlapping(conn, verse_id, start_offset, end_offset)
    conn.commit()


def _delete_overlapping(
    conn: sqlite3.Connection, verse_id: int, start_offset: int, end_offset: int
) -> None:
    # Two [start, end) ranges overlap iff each starts before the other ends.
    # A soft delete (tombstone), not a real DELETE, so a sync partner that
    # hasn't merged yet still learns this range was removed - see sync.py.
    conn.execute(
        "UPDATE highlights SET deleted_at = datetime('now'), updated_at = datetime('now') "
        "WHERE verse_id = ? AND start_offset < ? AND end_offset > ? AND deleted_at IS NULL",
        (verse_id, end_offset, start_offset),
    )


def get_annotated_verse_ids(conn: sqlite3.Connection, chapter_id: int) -> set[int]:
    """Verse ids in this chapter that have a note and/or tag, for drawing
    indicator badges without an N+1 query per verse."""
    rows = conn.execute(
        "SELECT v.id FROM verses v WHERE v.chapter_id = ? AND ("
        "EXISTS (SELECT 1 FROM notes n WHERE n.verse_id = v.id AND n.deleted_at IS NULL) OR "
        "EXISTS (SELECT 1 FROM tag_assignments ta WHERE ta.verse_id = v.id AND ta.deleted_at IS NULL))",
        (chapter_id,),
    ).fetchall()
    return {r["id"] for r in rows}


def get_note(
    conn: sqlite3.Connection, *, verse_id: int | None = None, chapter_id: int | None = None
) -> Note | None:
    """The note attached to a verse or a chapter (exactly one of the two).
    The schema permits more than one row per target, but this app's UI
    only ever creates one and edits it in place, so the most recent wins
    if extra rows exist some other way."""
    column = "verse_id" if verse_id is not None else "chapter_id"
    target = verse_id if verse_id is not None else chapter_id
    r = conn.execute(
        f"SELECT id, text, verse_id, chapter_id, updated_at FROM notes "
        f"WHERE {column} = ? AND deleted_at IS NULL ORDER BY id DESC LIMIT 1",
        (target,),
    ).fetchone()
    return Note(r["id"], r["text"], r["verse_id"], r["chapter_id"], r["updated_at"]) if r else None


def save_note(
    conn: sqlite3.Connection,
    text: str,
    *,
    verse_id: int | None = None,
    chapter_id: int | None = None,
) -> None:
    """Create or update the note attached to a verse or chapter."""
    existing = get_note(conn, verse_id=verse_id, chapter_id=chapter_id)
    if existing:
        conn.execute(
            "UPDATE notes SET text = ?, updated_at = datetime('now') WHERE id = ?",
            (text, existing.id),
        )
    else:
        conn.execute(
            "INSERT INTO notes (verse_id, chapter_id, text) VALUES (?, ?, ?)",
            (verse_id, chapter_id, text),
        )
    conn.commit()


def delete_note(conn: sqlite3.Connection, note_id: int) -> None:
    """Soft delete (tombstone), not a real DELETE, so a sync partner that
    hasn't merged yet still learns this note was removed - see sync.py."""
    conn.execute(
        "UPDATE notes SET deleted_at = datetime('now'), updated_at = datetime('now') "
        "WHERE id = ?",
        (note_id,),
    )
    conn.commit()


def get_tags(
    conn: sqlite3.Connection, *, verse_id: int | None = None, chapter_id: int | None = None
) -> list[Tag]:
    column = "verse_id" if verse_id is not None else "chapter_id"
    target = verse_id if verse_id is not None else chapter_id
    rows = conn.execute(
        f"SELECT t.id, t.name FROM tags t "
        f"JOIN tag_assignments ta ON ta.tag_id = t.id "
        f"WHERE ta.{column} = ? AND ta.deleted_at IS NULL ORDER BY t.name COLLATE NOCASE",
        (target,),
    ).fetchall()
    return [Tag(r["id"], r["name"]) for r in rows]


def add_tag(
    conn: sqlite3.Connection,
    name: str,
    *,
    verse_id: int | None = None,
    chapter_id: int | None = None,
) -> None:
    name = name.strip()
    if not name:
        return
    conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
    tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()["id"]
    existing = conn.execute(
        "SELECT id, deleted_at FROM tag_assignments "
        "WHERE tag_id = ? AND verse_id IS ? AND chapter_id IS ?",
        (tag_id, verse_id, chapter_id),
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO tag_assignments (tag_id, verse_id, chapter_id, updated_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (tag_id, verse_id, chapter_id),
        )
    elif existing["deleted_at"] is not None:
        # Previously removed, re-added now - revive the same row (by its
        # natural key) rather than insert a duplicate.
        conn.execute(
            "UPDATE tag_assignments SET deleted_at = NULL, updated_at = datetime('now') "
            "WHERE id = ?",
            (existing["id"],),
        )
    conn.commit()


def remove_tag(
    conn: sqlite3.Connection,
    tag_id: int,
    *,
    verse_id: int | None = None,
    chapter_id: int | None = None,
) -> None:
    """Soft delete (tombstone), not a real DELETE, so a sync partner that
    hasn't merged yet still learns this tag was removed - see sync.py."""
    conn.execute(
        "UPDATE tag_assignments SET deleted_at = datetime('now'), updated_at = datetime('now') "
        "WHERE tag_id = ? AND verse_id IS ? AND chapter_id IS ? AND deleted_at IS NULL",
        (tag_id, verse_id, chapter_id),
    )
    conn.commit()


def _fts_phrase(query: str) -> str:
    """Wrap free-form user input as a single FTS5 phrase, so punctuation or
    stray operator-like characters (-, ", *) in what someone types can
    never produce an invalid MATCH query."""
    return '"' + query.strip().replace('"', '""') + '"'


def search_verses(conn: sqlite3.Connection, query: str, limit: int = 40) -> list[Verse]:
    """Keyword search over scripture text (FTS5)."""
    query = query.strip()
    if not query:
        return []
    rows = conn.execute(
        "SELECT v.id, v.verse_number, v.text, v.reference, v.chapter_id "
        "FROM verses_fts JOIN verses v ON v.id = verses_fts.rowid "
        "WHERE verses_fts MATCH ? ORDER BY rank LIMIT ?",
        (_fts_phrase(query), limit),
    ).fetchall()
    return [
        Verse(r["id"], r["verse_number"], r["text"], r["reference"], r["chapter_id"])
        for r in rows
    ]


def search_verse_references(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[Verse]:
    """Direct reference lookup, e.g. "John 3:16" - only runs for
    verse-shaped queries (containing a ":"), since a bare word would
    otherwise match almost every reference's book name."""
    query = query.strip()
    if not query or ":" not in query:
        return []
    rows = conn.execute(
        "SELECT id, verse_number, text, reference, chapter_id FROM verses "
        "WHERE reference LIKE ? ORDER BY id LIMIT ?",
        (f"%{query}%", limit),
    ).fetchall()
    return [
        Verse(r["id"], r["verse_number"], r["text"], r["reference"], r["chapter_id"])
        for r in rows
    ]


def search_chapters(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[ChapterMatch]:
    """Book/chapter name lookup, e.g. "Genesis 1" or just "Alma". Exact and
    prefix matches sort first, so searching "Genesis 1" surfaces that
    chapter before incidental substring hits like "Genesis 10"."""
    query = query.strip()
    if len(query) < 2:
        return []
    label_expr = "b.name || ' ' || c.chapter_number"
    rows = conn.execute(
        f"SELECT c.id AS chapter_id, {label_expr} AS label FROM chapters c "
        f"JOIN books b ON b.id = c.book_id "
        f"WHERE {label_expr} LIKE ? "
        f"ORDER BY "
        f"CASE WHEN {label_expr} = ? THEN 0 "
        f"WHEN {label_expr} LIKE ? THEN 1 ELSE 2 END, "
        f"b.id, c.chapter_number LIMIT ?",
        (f"%{query}%", query, f"{query}%", limit),
    ).fetchall()
    return [ChapterMatch(r["chapter_id"], r["label"]) for r in rows]


def search_notes(conn: sqlite3.Connection, query: str, limit: int = 40) -> list[NoteResult]:
    """Keyword search over note text (FTS5)."""
    query = query.strip()
    if not query:
        return []
    rows = conn.execute(
        "SELECT n.id, n.text, "
        "COALESCE(v.chapter_id, n.chapter_id) AS chapter_id, "
        "COALESCE(v.reference, b.name || ' ' || c.chapter_number) AS reference "
        "FROM notes_fts "
        "JOIN notes n ON n.id = notes_fts.rowid "
        "LEFT JOIN verses v ON v.id = n.verse_id "
        "LEFT JOIN chapters c ON c.id = n.chapter_id "
        "LEFT JOIN books b ON b.id = c.book_id "
        "WHERE notes_fts MATCH ? AND n.deleted_at IS NULL ORDER BY rank LIMIT ?",
        (_fts_phrase(query), limit),
    ).fetchall()
    return [NoteResult(r["id"], r["text"], r["chapter_id"], r["reference"]) for r in rows]


def get_all_notes(conn: sqlite3.Connection) -> list[NoteResult]:
    """Every note in the database, in canonical scripture order (volume ->
    book -> chapter -> verse), for exporting the whole set at once."""
    rows = conn.execute(
        "SELECT n.id, n.text, "
        "COALESCE(v.chapter_id, n.chapter_id) AS chapter_id, "
        "COALESCE(v.reference, b.name || ' ' || c.chapter_number) AS reference "
        "FROM notes n "
        "LEFT JOIN verses v ON v.id = n.verse_id "
        "JOIN chapters c ON c.id = COALESCE(v.chapter_id, n.chapter_id) "
        "JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id "
        "WHERE n.deleted_at IS NULL "
        "ORDER BY vol.sort_order, b.sort_order, c.chapter_number, "
        "COALESCE(v.verse_number, 0)"
    ).fetchall()
    return [NoteResult(r["id"], r["text"], r["chapter_id"], r["reference"]) for r in rows]


def search_tags_by_name(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[Tag]:
    query = query.strip()
    if len(query) < 2:
        return []
    rows = conn.execute(
        "SELECT id, name FROM tags WHERE name LIKE ? ORDER BY name COLLATE NOCASE LIMIT ?",
        (f"%{query}%", limit),
    ).fetchall()
    return [Tag(r["id"], r["name"]) for r in rows]


def get_tag_targets(conn: sqlite3.Connection, tag_id: int, limit: int = 100) -> list[TaggedItem]:
    """Every verse/chapter a tag is attached to, for showing what a
    matched tag actually points at."""
    rows = conn.execute(
        "SELECT COALESCE(v.chapter_id, ta.chapter_id) AS chapter_id, "
        "COALESCE(v.reference, b.name || ' ' || c.chapter_number) AS reference "
        "FROM tag_assignments ta "
        "LEFT JOIN verses v ON v.id = ta.verse_id "
        "LEFT JOIN chapters c ON c.id = ta.chapter_id "
        "LEFT JOIN books b ON b.id = c.book_id "
        "WHERE ta.tag_id = ? AND ta.deleted_at IS NULL ORDER BY reference LIMIT ?",
        (tag_id, limit),
    ).fetchall()
    return [TaggedItem(r["chapter_id"], r["reference"]) for r in rows]


def record_reading(conn: sqlite3.Connection, chapter_id: int, read_date: str) -> None:
    """Log today's date as read, for the reading streak (safe to call
    multiple times per day - read_date is UNIQUE, so we upsert), and log
    this visit for the "Resume Reading" history (see reading_history's
    schema comment on why that one's a plain insert, not an upsert)."""
    conn.execute(
        "INSERT INTO reading_log (read_date, chapter_id, updated_at) "
        "VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(read_date) DO UPDATE SET "
        "chapter_id = excluded.chapter_id, updated_at = datetime('now')",
        (read_date, chapter_id),
    )
    conn.execute("INSERT INTO reading_history (chapter_id) VALUES (?)", (chapter_id,))
    conn.commit()


@dataclass(frozen=True)
class ReadingHistoryEntry:
    """One distinct chapter from the "Resume Reading" history - enough
    fields for the UI layer to build the same kind of label
    MainWindow._chapter_label already builds for cards/breadcrumbs
    (Section N for D&C, Speaker - Title for Journal of Discourses, etc.),
    plus the book name, since this list can span more than one book."""

    chapter_id: int
    volume_slug: str
    book_name: str
    chapter_number: int
    title: str | None
    speaker: str | None


def get_reading_history(conn: sqlite3.Connection, limit: int = 5) -> list[ReadingHistoryEntry]:
    """The `limit` most recently-read distinct chapters, most recent
    first - re-reading a chapter bumps it back to the top rather than
    adding a second entry for it."""
    rows = conn.execute(
        "SELECT c.id AS chapter_id, vol.slug AS volume_slug, b.name AS book_name, "
        "c.chapter_number, c.title, c.speaker, MAX(rh.read_at) AS last_read "
        "FROM reading_history rh "
        "JOIN chapters c ON c.id = rh.chapter_id "
        "JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id "
        "GROUP BY rh.chapter_id "
        "ORDER BY last_read DESC "
        "LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        ReadingHistoryEntry(
            r["chapter_id"], r["volume_slug"], r["book_name"], r["chapter_number"], r["title"], r["speaker"]
        )
        for r in rows
    ]


def get_reading_streak(conn: sqlite3.Connection) -> int:
    """Consecutive days read, ending today - or ending yesterday if
    today hasn't been read yet, so the streak doesn't drop to zero the
    moment midnight passes before that day's reading happens."""
    rows = conn.execute("SELECT read_date FROM reading_log").fetchall()
    read_dates = {date.fromisoformat(r["read_date"]) for r in rows}
    if not read_dates:
        return 0

    cursor = date.today()
    if cursor not in read_dates:
        cursor -= timedelta(days=1)
        if cursor not in read_dates:
            return 0

    streak = 0
    while cursor in read_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


# ---------------------------------------------------------------------
# Topical guide (see schema.sql's comment above the topics tables, and
# scripts/build_topical_guide.py, which is the only thing that writes to
# them)
# ---------------------------------------------------------------------


def get_topics(conn: sqlite3.Connection) -> list[Topic]:
    rows = conn.execute(
        "SELECT id, name, slug, description FROM topics ORDER BY sort_order"
    ).fetchall()
    return [Topic(r["id"], r["name"], r["slug"], r["description"]) for r in rows]


def get_topic(conn: sqlite3.Connection, topic_id: int) -> Topic:
    r = conn.execute(
        "SELECT id, name, slug, description FROM topics WHERE id = ?", (topic_id,)
    ).fetchone()
    return Topic(r["id"], r["name"], r["slug"], r["description"])


def get_topic_verses(conn: sqlite3.Connection, topic_id: int) -> list[Verse]:
    """Joined by (volume slug, reference), not id (see topic_verses'
    schema comment - reference alone is ambiguous between Holy Bible and
    Joseph Smith Translation) - a stale pair that no longer matches any
    verse (e.g. an older writable database that hasn't synced in a book
    yet) is simply left out by this join rather than erroring."""
    rows = conn.execute(
        "SELECT v.id, v.verse_number, v.text, v.reference, v.chapter_id "
        "FROM topic_verses tv "
        "JOIN verses v ON v.reference = tv.reference "
        "JOIN chapters c ON c.id = v.chapter_id "
        "JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id AND vol.slug = tv.volume_slug "
        "WHERE tv.topic_id = ? ORDER BY tv.sort_order",
        (topic_id,),
    ).fetchall()
    return [
        Verse(r["id"], r["verse_number"], r["text"], r["reference"], r["chapter_id"])
        for r in rows
    ]


def get_topic_talks(conn: sqlite3.Connection, topic_id: int) -> list[TopicTalk]:
    rows = conn.execute(
        "SELECT talk_title, speaker, date, url FROM topic_talks "
        "WHERE topic_id = ? ORDER BY sort_order",
        (topic_id,),
    ).fetchall()
    return [TopicTalk(r["talk_title"], r["speaker"], r["date"], r["url"]) for r in rows]
