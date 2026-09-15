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
-- The UI layer decides whether to label this "Chapter" or "Section" based on
-- the parent book/volume - the schema doesn't need to know.
CREATE TABLE IF NOT EXISTS chapters (
    id              INTEGER PRIMARY KEY,
    book_id         INTEGER NOT NULL REFERENCES books(id),
    chapter_number  INTEGER NOT NULL,
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
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY,
    verse_id    INTEGER REFERENCES verses(id),
    chapter_id  INTEGER REFERENCES chapters(id),
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
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

-- Tags are user-defined labels. A tag can be applied to a verse or a chapter,
-- acting as a lightweight, user-built cross-reference system.
CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS tag_assignments (
    id          INTEGER PRIMARY KEY,
    tag_id      INTEGER NOT NULL REFERENCES tags(id),
    verse_id    INTEGER REFERENCES verses(id),
    chapter_id  INTEGER REFERENCES chapters(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
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
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_highlights_verse ON highlights(verse_id);

-- Reading streak: one row per calendar day the user opened any chapter.
-- Opening counts regardless of how much was read (per product decision).
CREATE TABLE IF NOT EXISTS reading_log (
    id          INTEGER PRIMARY KEY,
    read_date   TEXT NOT NULL UNIQUE,   -- ISO date, e.g. "2026-09-14"
    chapter_id  INTEGER REFERENCES chapters(id)  -- last chapter opened that day (informational)
);

-- Simple key/value settings store: theme, font, color scheme, zoom level, etc.
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
