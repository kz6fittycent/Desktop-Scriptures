# Desktop-Scriptures

A desktop reader for the LDS standard works (Bible, Book of Mormon,
Doctrine and Covenants, Pearl of Great Price) with personal notes, tags,
highlights, keyword search, and a reading streak. Fully offline. Built
with Python 3 and PySide6, packaged as a Snap (`base: core24`).

This is an **unofficial** application, not produced by or affiliated
with The Church of Jesus Christ of Latter-day Saints.

## Status

Data layer: built, tested against the real 41,995-verse file, verified correct.

UI: a working navigation shell exists (landing page -> testament/book ->
chapter -> reading view, with breadcrumbs) but has **not been visually
tested** - the sandbox this was built in has no display and no network
access to install PySide6. The query logic underneath it (data_access.py)
IS tested and confirmed correct. You're the first to actually run the GUI -
see "Running the app" below, and please report back anything that looks
or behaves wrong.

Not yet built: theming (light/dark, color schemes), font selection,
highlighting, notes/tags UI, search UI, settings screen, streak display.
The data layer already supports all of these; only the UI for them is
missing.

## Project layout

```
Desktop-Scriptures/
  data/
    volumes.json       # canonical volume/testament/book hierarchy (hand-maintained)
    scriptures.db       # <- your imported database (see below), not committed
    raw/
      sample.txt        # small hand-built test fixture (20 verses, all volumes)
      lds-scriptures.txt  # <- YOU ADD THIS (see below), not committed
  src/
    scriptures/
      __init__.py
      db.py              # connection + schema init helper
      schema.sql         # full database schema (hierarchy, FTS5, notes, tags, highlights, etc.)
      data_access.py      # query layer the UI calls - tested, no raw SQL in the UI
      ui/
        __init__.py
        app.py             # entry point - run this
        main_window.py     # navigation wiring: volume -> testament/book -> chapter -> reading
        card_grid.py       # reusable clickable card + wrapping card-grid widget
        breadcrumb.py       # clickable breadcrumb bar
        reading_view.py     # minimal chapter reading view (verse list)
  scripts/
    import_scriptures.py # parses the raw text file into the SQLite database
  tests/                 # (empty - next step)
  README.md
```

## Running the app

Needs PySide6:

```
pip install PySide6 --break-system-packages
```

(Later, in the actual snap build, this becomes a `python3-pyside6.*`
stage-package from the Ubuntu archive instead of pip, per the
apt-packages-first decision - pip is just for local dev convenience now.)

Then, with `data/scriptures.db` already built (see "Getting the real
scripture text" above):

```
cd src/scriptures/ui
python3 app.py
```

It defaults to looking for the database at `data/scriptures.db` relative
to the project root; pass a different path as an argument if yours lives
elsewhere: `python3 app.py /path/to/scriptures.db`

### What to check when you run it

- Landing page shows 4 volume cards
- Clicking "Holy Bible" shows Old Testament / New Testament (2 cards)
- Clicking a testament shows its books in a wrapping grid
- Clicking any other volume (Book of Mormon, D&C, Pearl of Great Price)
  skips straight to books - no testament screen, since only the Bible has one
- Clicking a book shows its chapters (labeled "Section" instead of
  "Chapter" for Doctrine and Covenants)
- Clicking a chapter shows the actual verse text
- Breadcrumb at the top updates at every level and clicking any earlier
  segment jumps back to it correctly
- Window title bar always says "Scriptures"

## Getting the real scripture text

The importer reads a **local** copy of the text file - the app never
fetches scripture text over the network, at import time or at runtime.

1. Download the file once:
   https://raw.githubusercontent.com/beandog/lds-scriptures/master/text/lds-scriptures.txt
2. Save it to `data/raw/lds-scriptures.txt`
3. Run the import:

   ```
   python3 scripts/import_scriptures.py data/raw/lds-scriptures.txt data/scriptures.db
   ```

The script prints a summary when it's done, including any book names it
couldn't match to the hierarchy in `volumes.json` (there shouldn't be
any, but the beandog file's exact naming for a few edge cases like
Official Declarations hasn't been verified against the full file yet -
only against a hand-built sample).

## Database schema, in brief

- `volumes` -> `testaments` (Bible only) -> `books` -> `chapters` -> `verses`
- `verses_fts` / `notes_fts` - FTS5 virtual tables kept in sync via triggers,
  so `INSERT`/`UPDATE`/`DELETE` on `verses` or `notes` just works without
  any extra application code to maintain the search index.
- `notes` - attaches to a verse OR a chapter (enforced by a CHECK constraint)
- `tags` / `tag_assignments` - user-defined tags on verses or chapters;
  this is the personal cross-reference mechanism
- `highlights` - one of yellow/pink/orange per verse (enforced by CHECK +
  UNIQUE constraints)
- `reading_log` - one row per calendar day any chapter was opened (streak)
- `settings` - key/value store for theme, font, color scheme, zoom level

All of this lives in a **single SQLite file**. In the packaged Snap this
file belongs under `$SNAP_USER_COMMON` so it persists across snap
revision upgrades without relying on snapd's per-revision copy mechanism.

## Verified so far

Tested against a 20-verse hand-built sample spanning every volume,
including the trickier cases:
- D&C sections (`D&C 1:1` -> aliased to `Doctrine and Covenants`)
- Official Declarations (`Official Declaration 1 1:1`)
- Double-dash book names (`Joseph Smith--Matthew`, `Joseph Smith--History`)
- Full volume/testament/book/chapter/verse join chain
- FTS5 search on both verse text and note text
- Constraint enforcement (one highlight per verse, notes can't attach to
  both a verse and a chapter at once)

Not yet tested: a full run against the real ~41,000-verse file. Book
names in the real file should match `volumes.json` exactly, but this
needs confirming once the full file is available - the current alias
table in `import_scriptures.py` is a best guess for the handful of
special cases (D&C, Official Declarations, Joseph Smith--*).

## Next steps

1. Run the importer against the full `lds-scriptures.txt` and fix any
   unmatched book names that show up in the summary.
2. Start the PySide6 UI shell: main window, card-grid navigation
   (landing page -> volume -> testament/book -> chapter -> reading view).
3. Wire the reading view to the data layer (display verses, notes, tags,
   highlights for the current chapter).
