-- Scriptures app database schema
-- Designed for local-only storage under $SNAP_USER_COMMON at runtime.
-- All user data (notes/tags/highlights/streak) lives in the SAME database
-- file as the scripture text, so the whole app is a single portable file.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- Scripture hierarchy: volume -> (testament) -> book -> chapter -> verse
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS volumes (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,      -- e.g. "Holy Bible"
    slug        TEXT NOT NULL UNIQUE,      -- e.g. "holy-bible"
    sort_order  INTEGER NOT NULL
);

-- Only the Bible currently has testaments. Other volumes have no rows here;
-- their books reference volume_id directly and testament_id is NULL.
CREATE TABLE IF NOT EXISTS testaments (
    id          INTEGER PRIMARY KEY,
    volume_id   INTEGER NOT NULL REFERENCES volumes(id),
    name        TEXT NOT NULL,             -- e.g. "Old Testament"
    slug        TEXT NOT NULL,
    sort_order  INTEGER NOT NULL,
    UNIQUE (volume_id, name)
);

CREATE TABLE IF NOT EXISTS books (
    id            INTEGER PRIMARY KEY,
    volume_id     INTEGER NOT NULL REFERENCES volumes(id),
    testament_id  INTEGER REFERENCES testaments(id),   -- NULL if volume has no testaments
    name          TEXT NOT NULL,           -- e.g. "Genesis", "Alma"
    sort_order    INTEGER NOT NULL,
    UNIQUE (volume_id, name)
);

-- For D&C, a "chapter" row represents a Section (or an Official Declaration).
-- For Journal of Discourses, it represents one discourse (sermon) - title/
-- speaker/discourse_date identify it instead of chapter_number alone, which
-- is just its sequential position within the volume there. The UI layer
-- decides how to label a chapter based on the parent book/volume; the
-- schema doesn't need to know. All three columns stay NULL for ordinary
-- scripture chapters.
CREATE TABLE IF NOT EXISTS chapters (
    id              INTEGER PRIMARY KEY,
    book_id         INTEGER NOT NULL REFERENCES books(id),
    chapter_number  INTEGER NOT NULL,
    title           TEXT,             -- JoD discourse title, e.g. "Salvation"
    speaker         TEXT,             -- JoD discourse speaker, e.g. "Brigham Young"
    discourse_date  TEXT,             -- JoD discourse date, ISO (full or "YYYY-MM")
    UNIQUE (book_id, chapter_number)
);

CREATE TABLE IF NOT EXISTS verses (
    id            INTEGER PRIMARY KEY,
    chapter_id    INTEGER NOT NULL REFERENCES chapters(id),
    verse_number  INTEGER NOT NULL,
    text          TEXT NOT NULL,
    reference     TEXT NOT NULL,           -- denormalized display string, e.g. "Genesis 1:1"
    UNIQUE (chapter_id, verse_number)
);

CREATE INDEX IF NOT EXISTS idx_verses_chapter ON verses(chapter_id);
CREATE INDEX IF NOT EXISTS idx_chapters_book ON chapters(book_id);
CREATE INDEX IF NOT EXISTS idx_books_volume ON books(volume_id);
CREATE INDEX IF NOT EXISTS idx_verses_reference ON verses(reference);

-- ---------------------------------------------------------------------
-- Topical guide: developer-authored, like the scripture text itself, and
-- synced forward the same way (see db.py's sync_bundled_content) - never
-- user data. Built/refreshed by scripts/build_topical_guide.py, never
-- edited by hand or by the app itself.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS topics (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,      -- e.g. "Faith"
    slug         TEXT NOT NULL UNIQUE,
    description  TEXT NOT NULL,             -- a brief framing, not a definition
    sort_order   INTEGER NOT NULL
);

-- References a verse by its (volume slug, reference) pair, not verses.id
-- - a topic's supporting scriptures are chosen by matching text across
-- the whole bundled database, which can include a verse from a book a
-- given writable database hasn't synced in yet, and this keeps syncing
-- this table a plain natural-key operation (no cross-database id
-- remapping) the same way volumes/books/chapters already are. The
-- volume slug is needed alongside `reference` because reference strings
-- aren't unique on their own across volumes - the Joseph Smith
-- Translation reuses the King James Bible's own book/chapter/verse
-- numbering, so e.g. "Romans 3:3" exists once in Holy Bible and again,
-- with different wording, in Joseph Smith Translation. Resolved against
-- verses.reference (indexed above) joined through to volumes at query
-- time; a topic_verses row that doesn't (yet) match any verse is simply
-- skipped by that join rather than erroring.
CREATE TABLE IF NOT EXISTS topic_verses (
    id           INTEGER PRIMARY KEY,
    topic_id     INTEGER NOT NULL REFERENCES topics(id),
    volume_slug  TEXT NOT NULL,
    reference    TEXT NOT NULL,
    sort_order   INTEGER NOT NULL,
    UNIQUE (topic_id, volume_slug, reference)
);

CREATE INDEX IF NOT EXISTS idx_topic_verses_topic ON topic_verses(topic_id);

-- Same metadata-only shape as verse_citations.json (see citations.py) -
-- talk title/speaker/date/URL, never talk text - just persisted in the
-- database instead of a side JSON file, since these need to join and
-- sort alongside topic_verses rather than being looked up one verse at a
-- time.
CREATE TABLE IF NOT EXISTS topic_talks (
    id          INTEGER PRIMARY KEY,
    topic_id    INTEGER NOT NULL REFERENCES topics(id),
    talk_title  TEXT NOT NULL,
    speaker     TEXT NOT NULL,
    date        TEXT NOT NULL,
    url         TEXT NOT NULL,
    sort_order  INTEGER NOT NULL,
    UNIQUE (topic_id, url)
);

CREATE INDEX IF NOT EXISTS idx_topic_talks_topic ON topic_talks(topic_id);

-- Each topic's hand-curated landmark passages (e.g. Moroni 10:4-5 for
-- Testimony) - see scripts/build_topic_key_verses.py for how they were
-- chosen and why topic_verses' keyword-matched verses weren't enough.
-- `reference` is one verse or a range within one chapter ("Moroni
-- 10:4-5"); `volume_slug` disambiguates it the same way topic_verses'
-- does. Developer-authored, synced forward like the rest of the Topical
-- Guide (see db.py's _sync_bundled_topic_key_verses).
CREATE TABLE IF NOT EXISTS topic_key_verses (
    id           INTEGER PRIMARY KEY,
    topic_id     INTEGER NOT NULL REFERENCES topics(id),
    volume_slug  TEXT NOT NULL,
    reference    TEXT NOT NULL,
    sort_order   INTEGER NOT NULL,
    UNIQUE (topic_id, reference)
);

CREATE INDEX IF NOT EXISTS idx_topic_key_verses_topic ON topic_key_verses(topic_id);

-- Original-language word lexicon, one row per Strong's number ("H4899").
-- Developer-authored by scripts/import_lexicon.py (see its docstring for
-- sources and licenses - the definitions are Strong's Hebrew and Greek
-- dictionaries in Open Scriptures' CC BY-SA editions, the glosses
-- STEPBible's CC BY ones), synced forward like the Topical Guide (see
-- db.py's _sync_bundled_lexicon). `language` is 'hebrew', 'aramaic' (the
-- Aramaic portions of Daniel and Ezra), or 'greek' (Strong's "G" numbers).
CREATE TABLE IF NOT EXISTS lexicon_entries (
    id              INTEGER PRIMARY KEY,
    strongs         TEXT NOT NULL UNIQUE,
    language        TEXT NOT NULL,
    lemma           TEXT NOT NULL,
    transliteration TEXT NOT NULL DEFAULT '',
    pronunciation   TEXT NOT NULL DEFAULT '',
    derivation      TEXT NOT NULL DEFAULT '',
    definition      TEXT NOT NULL DEFAULT '',
    kjv_renderings  TEXT NOT NULL DEFAULT '',
    gloss           TEXT NOT NULL DEFAULT ''
);

-- Book of Mormon proper names and what's known of their meaning, labeled
-- by confidence (`tier`: defined / biblical / hebrew_root / proposed /
-- unknown; '' = not yet researched) - see scripts/build_bom_names.py,
-- which builds it (meanings in this project's own words, sources linked).
-- `strongs` lists related lexicon entries ("H7806"); `proposals` and
-- `sources` are JSON lists; `forms` are other spellings that mean this
-- name ("Nephites" -> Nephi). Synced like the lexicon.
CREATE TABLE IF NOT EXISTS bom_names (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    tier       TEXT NOT NULL DEFAULT '',
    meaning    TEXT NOT NULL DEFAULT '',
    reference  TEXT NOT NULL DEFAULT '',
    strongs    TEXT NOT NULL DEFAULT '',
    proposals  TEXT NOT NULL DEFAULT '[]',
    sources    TEXT NOT NULL DEFAULT '[]',
    forms      TEXT NOT NULL DEFAULT ''
);

-- Cross-references: passages that quote, closely paraphrase, or are a JST/
-- Moses-style translation-revision of another passage elsewhere in the
-- corpus - developer-curated like the Topical Guide above, and synced
-- forward the same way. Built/refreshed by scripts/build_cross_references.py,
-- never edited by hand or by the app itself.
--
-- Each row is one pair, named "primary"/"related" only for column-naming
-- purposes - a lookup matches either side (see get_cross_references), so
-- which passage a reader is currently viewing decides which side is
-- "this chapter" and which is "the other one" at query time.
--
-- Identified by (volume slug, book name, chapter number) rather than a
-- verse_id or even a single `reference` string, for the same reason as
-- topic_verses above: the Joseph Smith Translation reuses the King James
-- Bible's own chapter/verse numbering, so a bare reference like
-- "Isaiah 2:5" exists once in Holy Bible and again, with unrelated
-- wording, in Joseph Smith Translation. verse_start/verse_end are NULL
-- together for a whole-chapter match (e.g. 2 Nephi 12 <-> Isaiah 2);
-- verse_end NULL with verse_start set means a single verse.
CREATE TABLE IF NOT EXISTS cross_references (
    id                      INTEGER PRIMARY KEY,
    volume_slug             TEXT NOT NULL,
    book_name               TEXT NOT NULL,
    chapter_number          INTEGER NOT NULL,
    verse_start             INTEGER,
    verse_end               INTEGER,
    related_volume_slug     TEXT NOT NULL,
    related_book_name       TEXT NOT NULL,
    related_chapter_number  INTEGER NOT NULL,
    related_verse_start     INTEGER,
    related_verse_end       INTEGER,
    -- quotation = wording matches (allowing for translation-era spelling);
    -- paraphrase = same content/point, wording diverges meaningfully, or
    -- only part of the passage is quoted amid original commentary;
    -- translation = a JST-style revision of the very same underlying
    -- narrative, not an independent quotation of it; typology = a symbol
    -- or event scripture itself explicitly ties to Christ (the brazen
    -- serpent, the Passover lamb), not a quotation of one passage by
    -- another - see build_cross_references.py's own note on how strict
    -- "explicitly" is held to here; tradition = a widely-recognized
    -- thematic/traditional association (e.g. Ruth's Boaz as a type of
    -- Christ the kinsman-redeemer) that scripture itself does not
    -- explicitly state the way the other four kinds require - a
    -- deliberately looser tier, always labeled as such in the UI so a
    -- reader can tell it apart from the rest.
    relationship            TEXT NOT NULL CHECK (relationship IN ('quotation', 'paraphrase', 'translation', 'typology', 'tradition')),
    -- Comma-separated Topical Guide topic slugs (see topics.slug) naming
    -- the doctrine this pairing is actually about - e.g. "atonement", or
    -- "second-coming,plan-of-salvation" for a passage that touches both.
    -- Reuses the same topic taxonomy topics/topic_verses already curate
    -- rather than inventing a second one; a slug with no matching topic
    -- (e.g. an older writable database that hasn't synced in a newer
    -- topic yet) is simply left out when resolving this list, the same
    -- tolerance get_topic_verses already has. May be empty if no existing
    -- topic is a good fit.
    topic_slugs             TEXT NOT NULL DEFAULT '',
    note                    TEXT NOT NULL,
    sort_order              INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cross_references_primary
    ON cross_references(volume_slug, book_name, chapter_number);
CREATE INDEX IF NOT EXISTS idx_cross_references_related
    ON cross_references(related_volume_slug, related_book_name, related_chapter_number);

-- Full-text search over verse text. External-content table keeps the index
-- in sync with `verses` via triggers below, without duplicating storage.
CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts USING fts5(
    text,
    content='verses',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS verses_ai AFTER INSERT ON verses BEGIN
    INSERT INTO verses_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS verses_ad AFTER DELETE ON verses BEGIN
    INSERT INTO verses_fts(verses_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS verses_au AFTER UPDATE ON verses BEGIN
    INSERT INTO verses_fts(verses_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO verses_fts(rowid, text) VALUES (new.id, new.text);
END;

-- ---------------------------------------------------------------------
-- User data: notes, tags, highlights, reading streak, settings
-- ---------------------------------------------------------------------

-- A note attaches to either a verse or a whole chapter (exactly one of the two).
-- `deleted_at` (NULL = active) makes a "deletion" a tombstone rather than a
-- disappearing row, so a sync partner that hasn't merged yet still learns
-- about it - see sync.py. Every query that lists notes filters these out.
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY,
    verse_id    INTEGER REFERENCES verses(id),
    chapter_id  INTEGER REFERENCES chapters(id),
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at  TEXT,
    CHECK ((verse_id IS NOT NULL) + (chapter_id IS NOT NULL) = 1)
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    text,
    content='notes',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO notes_fts(rowid, text) VALUES (new.id, new.text);
END;

-- Journal: one free-text entry per calendar day (entry_date is UNIQUE),
-- optionally reflecting on a specific verse or chapter - unlike notes'
-- own target, both may be NULL here (most entries won't reference any
-- particular passage). save_journal_entry() always updates an existing
-- row for a given date in place (reusing even a soft-deleted one) rather
-- than inserting a second row for it, so the UNIQUE constraint is never
-- actually at odds with the tombstone convention - see its own
-- docstring. `deleted_at` is a tombstone for the same sync reason as
-- notes' own.
CREATE TABLE IF NOT EXISTS journal_entries (
    id          INTEGER PRIMARY KEY,
    entry_date  TEXT NOT NULL UNIQUE,  -- ISO date, e.g. "2026-09-23"
    text        TEXT NOT NULL,
    verse_id    INTEGER REFERENCES verses(id),
    chapter_id  INTEGER REFERENCES chapters(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at  TEXT,
    CHECK ((verse_id IS NOT NULL) + (chapter_id IS NOT NULL) <= 1)
);

CREATE VIRTUAL TABLE IF NOT EXISTS journal_entries_fts USING fts5(
    text,
    content='journal_entries',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS journal_entries_ai AFTER INSERT ON journal_entries BEGIN
    INSERT INTO journal_entries_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS journal_entries_ad AFTER DELETE ON journal_entries BEGIN
    INSERT INTO journal_entries_fts(journal_entries_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS journal_entries_au AFTER UPDATE ON journal_entries BEGIN
    INSERT INTO journal_entries_fts(journal_entries_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO journal_entries_fts(rowid, text) VALUES (new.id, new.text);
END;

-- User-added cross-references: the reader's own counterpart to the
-- developer-curated cross_references table above, shown alongside it in
-- the Cross-references tab (always labeled as the reader's own, so it's
-- never mistaken for a curated entry). Same column shape and the same
-- natural-key identification of each side (volume slug + book name +
-- chapter number, never a chapter_id - see cross_references' own comment
-- on why), which also makes these rows sync-ready as-is: sync.py matches
-- them across devices by those same columns, with no id remapping.
-- There's no relationship/topic_slugs here - a reader's own link is just
-- "see also," with an optional free-text note. add_user_cross_reference()
-- reuses an existing (even soft-deleted) row for the same pair rather
-- than inserting a duplicate; `deleted_at` is a tombstone for the same
-- sync reason as notes' own.
CREATE TABLE IF NOT EXISTS user_cross_references (
    id                      INTEGER PRIMARY KEY,
    volume_slug             TEXT NOT NULL,
    book_name               TEXT NOT NULL,
    chapter_number          INTEGER NOT NULL,
    verse_start             INTEGER,
    verse_end               INTEGER,
    related_volume_slug     TEXT NOT NULL,
    related_book_name       TEXT NOT NULL,
    related_chapter_number  INTEGER NOT NULL,
    related_verse_start     INTEGER,
    related_verse_end       INTEGER,
    note                    TEXT NOT NULL DEFAULT '',
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at              TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_cross_references_primary
    ON user_cross_references(volume_slug, book_name, chapter_number);
CREATE INDEX IF NOT EXISTS idx_user_cross_references_related
    ON user_cross_references(related_volume_slug, related_book_name, related_chapter_number);

-- Tags are user-defined labels. A tag can be applied to a verse or a chapter,
-- acting as a lightweight, user-built cross-reference system.
CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE COLLATE NOCASE
);

-- `updated_at`/`deleted_at` support sync's last-write-wins merge the same
-- way as notes above - removing a tag is setting `deleted_at`, not
-- deleting the row, so other devices learn about the removal too.
CREATE TABLE IF NOT EXISTS tag_assignments (
    id          INTEGER PRIMARY KEY,
    tag_id      INTEGER NOT NULL REFERENCES tags(id),
    verse_id    INTEGER REFERENCES verses(id),
    chapter_id  INTEGER REFERENCES chapters(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at  TEXT,
    CHECK ((verse_id IS NOT NULL) + (chapter_id IS NOT NULL) = 1)
);

CREATE INDEX IF NOT EXISTS idx_tag_assignments_tag ON tag_assignments(tag_id);

-- Highlights: an arbitrary substring of a verse's text (start_offset,
-- end_offset - a Python-slice-style [start, end) range into verses.text),
-- one of three colors. A verse can have several non-overlapping highlighted
-- ranges; db.py migrates forward any pre-range-based (whole-verse-only)
-- highlights rows from before this range model existed.
CREATE TABLE IF NOT EXISTS highlights (
    id            INTEGER PRIMARY KEY,
    verse_id      INTEGER NOT NULL REFERENCES verses(id),
    color         TEXT NOT NULL CHECK (color IN ('yellow', 'pink', 'orange')),
    start_offset  INTEGER NOT NULL,
    end_offset    INTEGER NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_highlights_verse ON highlights(verse_id);

-- Reading streak: one row per calendar day the user opened any chapter.
-- Opening counts regardless of how much was read (per product decision).
CREATE TABLE IF NOT EXISTS reading_log (
    id          INTEGER PRIMARY KEY,
    read_date   TEXT NOT NULL UNIQUE,   -- ISO date, e.g. "2026-09-14"
    chapter_id  INTEGER REFERENCES chapters(id),  -- last chapter opened that day (informational)
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Recent-reads history for the "Resume Reading" dropdown: one row per
-- qualifying chapter open (same dwell-time trigger as reading_log above),
-- not deduplicated here - re-reading a chapter should bump it back to the
-- top of the dropdown, which falls out naturally from
-- "MAX(read_at) per chapter_id, newest first" rather than needing an
-- upsert. Unlike reading_log, this is a per-visit log, not per-day.
CREATE TABLE IF NOT EXISTS reading_history (
    id          INTEGER PRIMARY KEY,
    chapter_id  INTEGER NOT NULL REFERENCES chapters(id),
    read_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reading_history_chapter ON reading_history(chapter_id);

-- Simple key/value settings store: theme, font, color scheme, zoom level,
-- etc. Also holds this installation's own `device_id` (a UUID, generated
-- once by db.py on first run and never changed) - this row is never itself
-- synced by sync.py, since it identifies one specific device, not shared
-- state.
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
