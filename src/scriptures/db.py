"""Database connection and schema management for the Scriptures app.

In production this file lives under $SNAP_USER_COMMON so it persists
across snap revision upgrades. For development it defaults to a local
path relative to the project.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection to the scripture database, creating the schema
    if this is a fresh database file.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    _migrate_whole_verse_highlights(conn)
    _migrate_add_chapter_metadata_columns(conn)
    _migrate_add_sync_columns(conn)
    _migrate_add_cross_reference_topic_slugs(conn)
    _migrate_cross_references_typology_relationship(conn)
    _migrate_cross_references_tradition_relationship(conn)
    _migrate_add_bom_name_people(conn)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    _backfill_migrated_highlights(conn)
    _backfill_migrated_cross_references_typology(conn)
    _backfill_migrated_cross_references_tradition(conn)
    _backfill_reading_history(conn)
    _backfill_journal_entries_fts(conn)
    _ensure_device_id(conn)
    conn.commit()


def _migrate_whole_verse_highlights(conn: sqlite3.Connection) -> None:
    """An earlier highlights table (one row per verse, no start/end
    offsets - the whole verse was "the" highlight) predates letting the
    user drag-select just a word or phrase. `CREATE TABLE IF NOT EXISTS`
    below won't add the new columns to an existing table, so a database
    still on that shape needs its highlights table moved aside before the
    real schema is (re)applied; `_backfill_migrated_highlights` then
    copies its rows forward as full-verse ranges.
    """
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'highlights'"
    ).fetchone()
    if not table_exists:
        return
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(highlights)")}
    if "start_offset" in columns:
        return
    conn.execute("ALTER TABLE highlights RENAME TO highlights_pre_ranges")


def _backfill_migrated_highlights(conn: sqlite3.Connection) -> None:
    old_table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'highlights_pre_ranges'"
    ).fetchone()
    if not old_table_exists:
        return
    conn.execute(
        "INSERT INTO highlights (verse_id, color, start_offset, end_offset, created_at) "
        "SELECT old.verse_id, old.color, 0, LENGTH(v.text), old.created_at "
        "FROM highlights_pre_ranges old JOIN verses v ON v.id = old.verse_id"
    )
    conn.execute("DROP TABLE highlights_pre_ranges")


def _backfill_reading_history(conn: sqlite3.Connection) -> None:
    """reading_history is new - on a database that already has reading_log
    entries (i.e. an existing install being upgraded, not a fresh one) but
    no reading_history yet, seed it from reading_log once, so the Resume
    Reading button doesn't disappear right after upgrading and only come
    back once something new gets read. reading_log only ever kept one,
    most-recent chapter per calendar day, so this is a coarser history
    than reading_history normally builds going forward, but it's the
    closest thing to prior history this database has.
    """
    if conn.execute("SELECT 1 FROM reading_history LIMIT 1").fetchone():
        return
    conn.execute(
        "INSERT INTO reading_history (chapter_id, read_at) "
        "SELECT chapter_id, read_date || 'T00:00:00' FROM reading_log "
        "WHERE chapter_id IS NOT NULL"
    )


def _backfill_journal_entries_fts(conn: sqlite3.Connection) -> None:
    """journal_entries_fts is new - any journal entries already written
    before this index existed (the journal feature itself shipped one
    version before search over it did) predate the triggers that keep it
    updated, so they'd otherwise never show up in search until next
    edited. Uses FTS5's own 'rebuild' command to re-derive the whole
    index from journal_entries' current content, rather than a `WHERE id
    NOT IN (SELECT rowid FROM journal_entries_fts)`-style check the way
    other one-off backfills in this file work: for an external-content
    FTS5 table (content='journal_entries'), a plain `SELECT rowid` like
    that doesn't reliably reflect what's actually term-indexed - it can
    still enumerate a rowid whose postings were already removed, making
    that check unable to tell "never indexed" apart from "indexed, then
    deleted." Gated by a settings flag so the rebuild only ever runs
    once, not on every launch."""
    already_done = conn.execute(
        "SELECT 1 FROM settings WHERE key = 'journal_entries_fts_backfilled'"
    ).fetchone()
    if already_done:
        return
    conn.execute("INSERT INTO journal_entries_fts(journal_entries_fts) VALUES ('rebuild')")
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('journal_entries_fts_backfilled', 'true')"
    )


def _migrate_add_chapter_metadata_columns(conn: sqlite3.Connection) -> None:
    """`CREATE TABLE IF NOT EXISTS` below won't add columns to a chapters
    table that already exists from before the Journal of Discourses
    import needed title/speaker/discourse_date - add them here if
    missing. Safe on a fresh database too: PRAGMA table_info on a
    not-yet-created table just returns no rows, so the "already there"
    check below is skipped rather than erroring, and schema.sql then
    creates the table with these columns already included.
    """
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chapters'"
    ).fetchone()
    if not table_exists:
        return
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(chapters)")}
    if "title" in columns:
        return
    conn.execute("ALTER TABLE chapters ADD COLUMN title TEXT")
    conn.execute("ALTER TABLE chapters ADD COLUMN speaker TEXT")
    conn.execute("ALTER TABLE chapters ADD COLUMN discourse_date TEXT")


def _migrate_add_bom_name_people(conn: sqlite3.Connection) -> None:
    """bom_names.people ("jaredite"), notes, and related came after the
    table did - add any missing, like the chapter metadata columns above."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(bom_names)")}
    if not columns:
        return
    for column, default in (("people", "''"), ("notes", "'[]'"), ("related", "'[]'")):
        if column not in columns:
            conn.execute(f"ALTER TABLE bom_names ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}")


def _migrate_add_sync_columns(conn: sqlite3.Connection) -> None:
    """`updated_at`/`deleted_at` (see sync.py) were added to tag_assignments/
    highlights/reading_log after those tables already existed for anyone
    upgrading - `ALTER TABLE ... ADD COLUMN` can't carry a non-constant
    default like `datetime('now')` the way a fresh `CREATE TABLE` in
    schema.sql can, so each column is added plain here and then backfilled:
    `updated_at` to the row's own `created_at` (the closest thing to a real
    "last changed" time a pre-existing row has - reading_log has no
    created_at, so its read_date stands in instead), and `deleted_at` is
    left NULL, which is already its correct "not deleted" value. notes
    already had `updated_at`; only `deleted_at` is new there.
    """
    _add_column_if_missing(conn, "notes", "deleted_at", "TEXT")

    if _add_column_if_missing(conn, "tag_assignments", "updated_at", "TEXT"):
        conn.execute(
            "UPDATE tag_assignments SET updated_at = created_at WHERE updated_at IS NULL"
        )
    _add_column_if_missing(conn, "tag_assignments", "deleted_at", "TEXT")

    if _add_column_if_missing(conn, "highlights", "updated_at", "TEXT"):
        conn.execute(
            "UPDATE highlights SET updated_at = created_at WHERE updated_at IS NULL"
        )
    _add_column_if_missing(conn, "highlights", "deleted_at", "TEXT")

    if _add_column_if_missing(conn, "reading_log", "updated_at", "TEXT"):
        conn.execute(
            "UPDATE reading_log SET updated_at = read_date || 'T00:00:00' "
            "WHERE updated_at IS NULL"
        )


def _migrate_add_cross_reference_topic_slugs(conn: sqlite3.Connection) -> None:
    """topic_slugs was added to cross_references after that table already
    existed for anyone who picked up an earlier v2.2.4 build - default to
    '' (no topics tagged yet), same as schema.sql's own DEFAULT for a
    fresh database."""
    _add_column_if_missing(conn, "cross_references", "topic_slugs", "TEXT NOT NULL DEFAULT ''")


def _migrate_cross_references_typology_relationship(conn: sqlite3.Connection) -> None:
    """cross_references.relationship's CHECK constraint originally allowed
    only ('quotation', 'paraphrase', 'translation') - 'typology' was added
    later, for symbols/events scripture itself explicitly ties to Christ
    (the brazen serpent, the Passover lamb, and so on) rather than a
    direct quotation of one passage by another. `CREATE TABLE IF NOT
    EXISTS` can't widen a CHECK constraint on a table that already exists,
    and SQLite has no ALTER TABLE for constraints at all - same shape of
    problem as _migrate_whole_verse_highlights above, same fix: rename the
    old table aside here so schema.sql's own CREATE TABLE (below) creates
    a fresh one with the new constraint, then
    _backfill_migrated_cross_references_typology copies its rows forward
    and drops it. A no-op on a fresh database, or one already migrated."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cross_references'"
    ).fetchone()
    if row is None or "'typology'" in row["sql"]:
        return
    conn.execute("ALTER TABLE cross_references RENAME TO cross_references_pre_typology")


def _backfill_migrated_cross_references_typology(conn: sqlite3.Connection) -> None:
    old_table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cross_references_pre_typology'"
    ).fetchone()
    if not old_table_exists:
        return
    conn.execute(
        "INSERT INTO cross_references "
        "(id, volume_slug, book_name, chapter_number, verse_start, verse_end, "
        "related_volume_slug, related_book_name, related_chapter_number, "
        "related_verse_start, related_verse_end, relationship, topic_slugs, note, sort_order) "
        "SELECT id, volume_slug, book_name, chapter_number, verse_start, verse_end, "
        "related_volume_slug, related_book_name, related_chapter_number, "
        "related_verse_start, related_verse_end, relationship, topic_slugs, note, sort_order "
        "FROM cross_references_pre_typology"
    )
    conn.execute("DROP TABLE cross_references_pre_typology")


def _migrate_cross_references_tradition_relationship(conn: sqlite3.Connection) -> None:
    """Same shape of problem as _migrate_cross_references_typology_
    relationship above, one relationship kind later: 'tradition' - a
    widely-recognized thematic/traditional association scripture itself
    doesn't explicitly state, a deliberately looser tier than the other
    four. Rename the old table aside here; _backfill_migrated_cross_
    references_tradition copies its rows forward and drops it."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cross_references'"
    ).fetchone()
    if row is None or "'tradition'" in row["sql"]:
        return
    conn.execute("ALTER TABLE cross_references RENAME TO cross_references_pre_tradition")


def _backfill_migrated_cross_references_tradition(conn: sqlite3.Connection) -> None:
    old_table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cross_references_pre_tradition'"
    ).fetchone()
    if not old_table_exists:
        return
    conn.execute(
        "INSERT INTO cross_references "
        "(id, volume_slug, book_name, chapter_number, verse_start, verse_end, "
        "related_volume_slug, related_book_name, related_chapter_number, "
        "related_verse_start, related_verse_end, relationship, topic_slugs, note, sort_order) "
        "SELECT id, volume_slug, book_name, chapter_number, verse_start, verse_end, "
        "related_volume_slug, related_book_name, related_chapter_number, "
        "related_verse_start, related_verse_end, relationship, topic_slugs, note, sort_order "
        "FROM cross_references_pre_tradition"
    )
    conn.execute("DROP TABLE cross_references_pre_tradition")


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, declaration: str
) -> bool:
    """Adds `column` to `table` if the table already exists and doesn't
    already have it. Returns True exactly when the column was just added,
    so callers know whether a backfill is needed - False either means
    there's nothing to backfill (column was already there) or the table
    doesn't exist yet (a fresh database, where schema.sql's own
    `CREATE TABLE` will include the column from the start)."""
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    if not table_exists:
        return False
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column in columns:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    return True


def _ensure_device_id(conn: sqlite3.Connection) -> None:
    """This installation's permanent identity for sync.py - a UUID
    generated once on first run and never changed afterward, so this
    device's exported filename (device-<id>.json) stays stable across
    restarts. Never itself synced - each device generates its own."""
    existing = conn.execute("SELECT 1 FROM settings WHERE key = 'device_id'").fetchone()
    if existing:
        return
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('device_id', ?)", (str(uuid.uuid4()),)
    )


def sync_bundled_content(conn: sqlite3.Connection, bundled_db_path: Path) -> None:
    """Copy any volumes/testaments/books/chapters/verses that exist in the
    bundled (packaged) database but not yet in `conn`, leaving whatever is
    already present - and all user data (notes/tags/highlights/reading
    streak/settings) - untouched.

    Without this, a snap refresh only replaces the read-only bundled copy
    inside the new revision's squashfs. The writable copy under
    $SNAP_USER_COMMON is seeded from that bundled copy exactly once, on
    an install's first-ever launch (see app.py's _default_db_path) - so
    an existing user would otherwise be stuck on whatever set of volumes
    happened to exist the day they first launched the app, no matter how
    many more get added upstream later. Matching is by natural key at
    each level (volume slug, book name, chapter number, verse number)
    rather than by id, since bundled and writable are separate SQLite
    files with independent, unrelated autoincrement ids.
    """
    if not bundled_db_path.exists():
        return

    conn.execute("ATTACH DATABASE ? AS bundled", (str(bundled_db_path),))
    try:
        for b_vol in conn.execute("SELECT * FROM bundled.volumes ORDER BY sort_order"):
            row = conn.execute(
                "SELECT id FROM volumes WHERE slug = ?", (b_vol["slug"],)
            ).fetchone()
            if row is None:
                cur = conn.execute(
                    "INSERT INTO volumes (name, slug, sort_order) VALUES (?, ?, ?)",
                    (b_vol["name"], b_vol["slug"], b_vol["sort_order"]),
                )
                volume_id = cur.lastrowid
            else:
                volume_id = row["id"]

            testament_map: dict[int, int] = {}
            for b_test in conn.execute(
                "SELECT * FROM bundled.testaments WHERE volume_id = ? ORDER BY sort_order",
                (b_vol["id"],),
            ):
                trow = conn.execute(
                    "SELECT id FROM testaments WHERE volume_id = ? AND name = ?",
                    (volume_id, b_test["name"]),
                ).fetchone()
                if trow is None:
                    cur = conn.execute(
                        "INSERT INTO testaments (volume_id, name, slug, sort_order) "
                        "VALUES (?, ?, ?, ?)",
                        (volume_id, b_test["name"], b_test["slug"], b_test["sort_order"]),
                    )
                    testament_map[b_test["id"]] = cur.lastrowid
                else:
                    testament_map[b_test["id"]] = trow["id"]

            for b_book in conn.execute(
                "SELECT * FROM bundled.books WHERE volume_id = ? ORDER BY sort_order",
                (b_vol["id"],),
            ):
                testament_id = (
                    testament_map.get(b_book["testament_id"])
                    if b_book["testament_id"] is not None
                    else None
                )
                brow = conn.execute(
                    "SELECT id FROM books WHERE volume_id = ? AND name = ?",
                    (volume_id, b_book["name"]),
                ).fetchone()
                if brow is None:
                    cur = conn.execute(
                        "INSERT INTO books (volume_id, testament_id, name, sort_order) "
                        "VALUES (?, ?, ?, ?)",
                        (volume_id, testament_id, b_book["name"], b_book["sort_order"]),
                    )
                    book_id = cur.lastrowid
                else:
                    book_id = brow["id"]

                for b_chap in conn.execute(
                    "SELECT * FROM bundled.chapters WHERE book_id = ? ORDER BY chapter_number",
                    (b_book["id"],),
                ):
                    crow = conn.execute(
                        "SELECT id FROM chapters WHERE book_id = ? AND chapter_number = ?",
                        (book_id, b_chap["chapter_number"]),
                    ).fetchone()
                    if crow is None:
                        cur = conn.execute(
                            "INSERT INTO chapters "
                            "(book_id, chapter_number, title, speaker, discourse_date) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (
                                book_id,
                                b_chap["chapter_number"],
                                b_chap["title"],
                                b_chap["speaker"],
                                b_chap["discourse_date"],
                            ),
                        )
                        chapter_id = cur.lastrowid
                    else:
                        chapter_id = crow["id"]

                    for b_verse in conn.execute(
                        "SELECT * FROM bundled.verses WHERE chapter_id = ? ORDER BY verse_number",
                        (b_chap["id"],),
                    ):
                        vrow = conn.execute(
                            "SELECT id FROM verses WHERE chapter_id = ? AND verse_number = ?",
                            (chapter_id, b_verse["verse_number"]),
                        ).fetchone()
                        if vrow is None:
                            conn.execute(
                                "INSERT INTO verses "
                                "(chapter_id, verse_number, text, reference) "
                                "VALUES (?, ?, ?, ?)",
                                (
                                    chapter_id,
                                    b_verse["verse_number"],
                                    b_verse["text"],
                                    b_verse["reference"],
                                ),
                            )
        _sync_bundled_topics(conn)
        _sync_bundled_topic_key_verses(conn)
        _sync_bundled_lexicon(conn)
        _sync_bundled_bom_names(conn)
        _sync_bundled_cross_references(conn)
        conn.commit()
    finally:
        conn.execute("DETACH DATABASE bundled")


def _sync_bundled_topics(conn: sqlite3.Connection) -> None:
    """Topics (and their scripture/talk references) are developer-authored
    like the scripture text above, not user data - synced the same way,
    by natural key (topic slug; a topic_verse by its verse reference
    string; a topic_talk by its URL) so a re-run of
    scripts/build_topical_guide.py just adds what's new."""
    for b_topic in conn.execute("SELECT * FROM bundled.topics ORDER BY sort_order"):
        row = conn.execute(
            "SELECT id FROM topics WHERE slug = ?", (b_topic["slug"],)
        ).fetchone()
        if row is None:
            cur = conn.execute(
                "INSERT INTO topics (name, slug, description, sort_order) VALUES (?, ?, ?, ?)",
                (b_topic["name"], b_topic["slug"], b_topic["description"], b_topic["sort_order"]),
            )
            topic_id = cur.lastrowid
        else:
            topic_id = row["id"]
            # Description/sort_order can change on a re-run without a slug
            # change - keep the writable copy in sync with the bundled one.
            conn.execute(
                "UPDATE topics SET name = ?, description = ?, sort_order = ? WHERE id = ?",
                (b_topic["name"], b_topic["description"], b_topic["sort_order"], topic_id),
            )

        for b_tv in conn.execute(
            "SELECT * FROM bundled.topic_verses WHERE topic_id = ? ORDER BY sort_order",
            (b_topic["id"],),
        ):
            exists = conn.execute(
                "SELECT 1 FROM topic_verses WHERE topic_id = ? AND volume_slug = ? AND reference = ?",
                (topic_id, b_tv["volume_slug"], b_tv["reference"]),
            ).fetchone()
            if exists is None:
                conn.execute(
                    "INSERT INTO topic_verses (topic_id, volume_slug, reference, sort_order) "
                    "VALUES (?, ?, ?, ?)",
                    (topic_id, b_tv["volume_slug"], b_tv["reference"], b_tv["sort_order"]),
                )

        for b_talk in conn.execute(
            "SELECT * FROM bundled.topic_talks WHERE topic_id = ? ORDER BY sort_order",
            (b_topic["id"],),
        ):
            exists = conn.execute(
                "SELECT 1 FROM topic_talks WHERE topic_id = ? AND url = ?",
                (topic_id, b_talk["url"]),
            ).fetchone()
            if exists is None:
                conn.execute(
                    "INSERT INTO topic_talks (topic_id, talk_title, speaker, date, url, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        topic_id,
                        b_talk["talk_title"],
                        b_talk["speaker"],
                        b_talk["date"],
                        b_talk["url"],
                        b_talk["sort_order"],
                    ),
                )


def _sync_bundled_topic_key_verses(conn: sqlite3.Connection) -> None:
    """Key verses are a small, whole curated list per topic - mirrored
    from the bundled copy exactly (replaced, not merged), so a passage
    removed or reordered upstream is removed or reordered here too.
    Matched to local topics by slug. A bundled database from before this
    table existed has none to copy, and leaves the local table as is."""
    has_table = conn.execute(
        "SELECT 1 FROM bundled.sqlite_master WHERE type = 'table' AND name = 'topic_key_verses'"
    ).fetchone()
    if not has_table:
        return
    conn.execute("DELETE FROM topic_key_verses")
    conn.execute(
        "INSERT INTO topic_key_verses (topic_id, volume_slug, reference, sort_order) "
        "SELECT t.id, bk.volume_slug, bk.reference, bk.sort_order "
        "FROM bundled.topic_key_verses bk "
        "JOIN bundled.topics bt ON bt.id = bk.topic_id "
        "JOIN topics t ON t.slug = bt.slug"
    )


def _sync_bundled_lexicon(conn: sqlite3.Connection) -> None:
    """The lexicon is developer-authored reference data - mirrored from
    the bundled copy exactly, like topic_key_verses (a corrected
    definition upstream replaces the old one here). A bundled database
    from before the lexicon existed leaves the local table as is."""
    has_table = conn.execute(
        "SELECT 1 FROM bundled.sqlite_master WHERE type = 'table' AND name = 'lexicon_entries'"
    ).fetchone()
    if not has_table:
        return
    conn.execute("DELETE FROM lexicon_entries")
    conn.execute(
        "INSERT INTO lexicon_entries (strongs, language, lemma, transliteration, pronunciation, "
        "derivation, definition, kjv_renderings, gloss) "
        "SELECT strongs, language, lemma, transliteration, pronunciation, derivation, definition, "
        "kjv_renderings, gloss FROM bundled.lexicon_entries"
    )


def _sync_bundled_bom_names(conn: sqlite3.Connection) -> None:
    """Mirrored from the bundled copy, like the lexicon."""
    has_table = conn.execute(
        "SELECT 1 FROM bundled.sqlite_master WHERE type = 'table' AND name = 'bom_names'"
    ).fetchone()
    if not has_table:
        return
    conn.execute("DELETE FROM bom_names")
    conn.execute(
        "INSERT INTO bom_names (name, tier, meaning, reference, strongs, proposals, sources, forms, people, notes, related) "
        "SELECT name, tier, meaning, reference, strongs, proposals, sources, forms, people, notes, related "
        "FROM bundled.bom_names"
    )


def _sync_bundled_cross_references(conn: sqlite3.Connection) -> None:
    """Cross-references are developer-authored, like topics above - synced
    the same way, matched by the full (volume/book/chapter/verse-range)
    pair on both sides rather than a single natural-key column, since no
    one column identifies a row. relationship/note/sort_order are kept in
    sync with the bundled copy on a re-run, same as a topic's own
    description/sort_order."""
    for b_cr in conn.execute("SELECT * FROM bundled.cross_references ORDER BY sort_order"):
        row = conn.execute(
            "SELECT id FROM cross_references WHERE "
            "volume_slug = ? AND book_name = ? AND chapter_number = ? "
            "AND verse_start IS ? AND verse_end IS ? "
            "AND related_volume_slug = ? AND related_book_name = ? AND related_chapter_number = ? "
            "AND related_verse_start IS ? AND related_verse_end IS ?",
            (
                b_cr["volume_slug"], b_cr["book_name"], b_cr["chapter_number"],
                b_cr["verse_start"], b_cr["verse_end"],
                b_cr["related_volume_slug"], b_cr["related_book_name"], b_cr["related_chapter_number"],
                b_cr["related_verse_start"], b_cr["related_verse_end"],
            ),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO cross_references "
                "(volume_slug, book_name, chapter_number, verse_start, verse_end, "
                "related_volume_slug, related_book_name, related_chapter_number, "
                "related_verse_start, related_verse_end, relationship, topic_slugs, note, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    b_cr["volume_slug"], b_cr["book_name"], b_cr["chapter_number"],
                    b_cr["verse_start"], b_cr["verse_end"],
                    b_cr["related_volume_slug"], b_cr["related_book_name"], b_cr["related_chapter_number"],
                    b_cr["related_verse_start"], b_cr["related_verse_end"],
                    b_cr["relationship"], b_cr["topic_slugs"], b_cr["note"], b_cr["sort_order"],
                ),
            )
        else:
            conn.execute(
                "UPDATE cross_references SET relationship = ?, topic_slugs = ?, note = ?, sort_order = ? "
                "WHERE id = ?",
                (b_cr["relationship"], b_cr["topic_slugs"], b_cr["note"], b_cr["sort_order"], row["id"]),
            )


# Settings connect() writes into whatever database it opens that must never
# ship in data/scriptures.db: a device_id there would give every fresh
# install the same sync identity (see _ensure_device_id), and the FTS
# backfill flag describes one particular copy's history, not the data.
_DEVICE_SPECIFIC_SETTINGS = ("device_id", "journal_entries_fts_backfilled")


def compact(conn: sqlite3.Connection) -> None:
    """Prepare data/scriptures.db for shipping: drop the device-specific
    settings connect() just added (see _DEVICE_SPECIFIC_SETTINGS), commit,
    then VACUUM away the free pages a bulk import/rebuild leaves behind.
    Every script under scripts/ that writes data/scriptures.db calls this
    last: that file is committed to git and shipped as-is, and left
    uncompacted it had grown to ~85MB with ~28MB of it empty pages - close
    enough to GitHub's 100MB per-file push limit to matter."""
    conn.execute(
        f"DELETE FROM settings WHERE key IN ({','.join('?' * len(_DEVICE_SPECIFIC_SETTINGS))})",
        _DEVICE_SPECIFIC_SETTINGS,
    )
    conn.commit()
    conn.execute("VACUUM")


def fts5_available(conn: sqlite3.Connection) -> bool:
    """Confirm the SQLite build this Python was linked against supports FTS5.
    Ubuntu's system SQLite has FTS5 enabled, but this is worth checking
    explicitly since it's a hard requirement for search to work at all.
    """
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_check USING fts5(x)")
        conn.execute("DROP TABLE _fts5_check")
        return True
    except sqlite3.OperationalError:
        return False
