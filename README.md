# Desktop-Scriptures

A desktop reader for the LDS standard works (Bible, Book of Mormon,
Doctrine and Covenants, Pearl of Great Price) with personal notes, tags,
highlights, keyword search, and a reading streak. Fully offline. Built
with Python 3 and PySide6, packaged as a Snap (`base: core24`).

This is an **unofficial** application, not produced by or affiliated
with The Church of Jesus Christ of Latter-day Saints.

## Status

Data layer: built, tested against the real 41,995-verse file, verified correct.

UI navigation shell: landing page -> testament/book -> chapter -> reading
view, with breadcrumbs. Visually verified on a real display (see "What to
check when you run it" below).

Theming: built and visually verified on a real display (light/dark app
chrome, day/night/sepia reading colors, font family choice, zoom-based
text sizing 10-28pt via Ctrl+=/Ctrl+-/Ctrl+0 or the A-/A+ buttons, all
persisted to the `settings` table). See "Theming checklist" below.

Visual style: Material Design-inspired (rounded surfaces, indigo accent,
elevation shadows on cards, a thin rounded scrollbar) instead of the
original flat/dated look. Landing-page and navigation cards are
fixed-size squares (128x128) that wrap onto new rows as the window
resizes and stay centered both horizontally and vertically in the
available space, rather than rectangles that stretch with the window
(`FlowLayout` in card_grid.py - centers each row, and CardGridWidget
sandwiches the grid between two stretches for vertical centering).

Bugs found and fixed while visually verifying theming, both the same root
cause in different widgets: `deleteLater()` alone doesn't force a repaint
of the region a removed widget occupied, so a new, differently-sized
widget placed in the same spot could leave stale pixels from the old one
behind. `hide()` before `deleteLater()` fixes it. Hit in
`BreadcrumbBar.set_path()` and `MainWindow._set_content()` - worth
remembering for any future code that swaps widgets in a layout.

Also hit and fixed: an unscoped `widget.setStyleSheet("border: ...; ...")`
(no selector) cascades to *every* descendant widget in Qt, not just the
widget it's called on - it briefly gave every verse `QLabel` its own
bordered box instead of just the reading view's content card. Fixed by
scoping with an object name (`QWidget#readingCard { ... }`).

Notes/tags UI: built and visually verified. Each verse in the reading view
has a small pencil-icon button (filled indigo when that verse already has
a note and/or tag, muted outline otherwise) that opens a dialog
(`note_editor.py`) to write a note and add/remove tags - one note per
verse, editing in place, matching how most reading apps handle this even
though the schema technically allows more than one row per verse. The
reading view's header has an equivalent "Note" button for a chapter-level
note/tags, styled the same way. Tag chips wrap using the same `FlowLayout`
built for the card grid.

Bug found and fixed while verifying notes/tags: word-wrapped `RichText`
`QLabel`s (the verse text) ignore the stylesheet cascade for their own
background fill - they painted an opaque box using a resolved color
unrelated to their actual parent, visible as a stray rectangle behind
every verse once the reading card's background differed from the window
background. Only reproduced with multi-line wrapped text, not short
single-line labels, which is what made it easy to miss. Fixed by setting
`background: transparent` directly on the label's own stylesheet, not on
an ancestor - explicitly worth noting since the *fix* for this one looks
identical to the *cause* of the two bugs above (an unscoped
`setStyleSheet()` cascading to children); this is the one case where
setting an unscoped property directly on the affected widget itself,
rather than routing it through a scoped ancestor rule, was correct.

Bug found and fixed (reported by the user, not caught during earlier
verification): verse text was visibly clipped on the last wrapped line of
many verses at the *default* zoom level only - zooming in or out fixed it
immediately. Cause: `ReadingView` computes its word-wrapped `QLabel`
heights during `__init__`, before the view has been inserted into the
window and given its real width, so the first layout pass reserves too
little height; any later relayout (like zooming, which touches every
label's font) recomputes against the now-correct width and fixes itself.
Fixed with a one-shot `QTimer.singleShot(0, self._content_layout.activate)`
at the end of `__init__`, which re-validates the layout on the next event
loop turn - by then the view has its final width, so it's correct from
the very first paint instead of needing user interaction to self-correct.

Search UI: built and visually verified. The search box itself lives in
`MainWindow`'s header, next to the breadcrumb - always visible and usable
from any screen, not a page you navigate to first; Ctrl+F just focuses it
(`search_bar` in main_window.py). Typing runs four independent lookups
250ms after you stop (or immediately on Enter), each shown in
`search_view.py` as its own labeled section only when it has results, in
this order: **Tags** and **Notes** first (your own annotations, name
matches / FTS5 keyword match over note text - every verse/chapter a
matched tag is attached to is listed directly underneath it, no extra
click to drill in), then **Chapters** (book/chapter name, e.g. "Alma" or
"Genesis 1", exact/prefix matches sorted first) and **Verses** (a direct
reference like "John 3:16" first, then an FTS5 keyword match over
scripture text, deduplicated). Clicking any result resolves its full
volume/testament/book path (`get_chapter_location` in data_access.py) and
navigates exactly as if you'd clicked through the card grid, so the
breadcrumb is always correct - the search bar stays populated afterward
since it's part of the header, not the page you navigated away from.

Window title, the landing page's centered title card, and the breadcrumb's
root segment all read "Desktop Scriptures" (not just "Scriptures"). The
breadcrumb is empty on the landing page itself, rather than showing a
redundant, non-clickable "Desktop Scriptures" there too - it only appears
once you've navigated at least one level deep, where it's an actual link
back to the landing page.

About dialog: built and visually verified (`about_dialog.py`, under the
new "Help" menu). Shows the version (1.0), the unofficial-app disclaimer
also stated at the top of this README, a "Special thanks to Beandog" line
with "Beandog" linking to https://github.com/beandog/lds-scriptures, and
a link to churchofjesuschrist.org.

Menu bar order is (left to right): **Menu**, **View**, **Help**. "Menu"
(new) holds:
- **Export Notes** - every note in the database (verse- and
  chapter-level), in canonical scripture order, written to a timestamped
  `.txt` file under `~/Documents/` (created if it doesn't exist yet), with
  a message box confirming the exact path once it's saved
  (`export_notes` in `export.py`, backed by `get_all_notes` in
  data_access.py)
- **Share the Book of Mormon** - a message box with a clickable link to
  https://go.churchofjesuschrist.org/x/n1Ic embedded in the text; Qt
  auto-enables external-link opening on a `QMessageBox` once its text
  format is set to RichText, so this didn't need a custom dialog class
  the way the About dialog did

Exporting search results lives with the search results themselves rather
than in the Menu: an "Export Results" button sits top-right, nested
between the "Search results for ..." banner and the first results
section (`search_view.py`) - only visible once there's an active query.
It exports the scripture verses currently matching that query - the same
reference + keyword combination the Verses section uses - to
`~/Documents/` with the same confirming-message-box pattern as Export
Notes (`export_search_results` in `export.py`, shared by both).

Both export actions handle the empty-result case gracefully (no notes
yet / nothing typed in the search bar / a search with no verse matches)
with an explanatory message box instead of writing an empty file.

Resume Reading + reading streak: built and visually verified. Both live in
the menu bar's top-right corner, right after "Help": a filled, pill-shaped
"Resume Reading" button (`resumeButton` in theme.py - solid primary color,
so it reads as an obvious button rather than another plain menu label),
then the streak badge ("\U0001f525 N days streak"), in a small container
widget set via `QMenuBar.setCornerWidget()`. The button only appears when
there's any reading history at all (`get_last_read_chapter_id` in
data_access.py); clicking it resolves that chapter's full path and
navigates straight there, the same as any other navigation. The streak
count itself (`get_reading_streak`) counts backward from today, or from
yesterday if today hasn't been read yet so it doesn't drop to zero before
you've had a chance to read; hidden entirely at a 0-day streak rather than
showing "0 days."

An earlier version put "Resume Reading" as a 5th, accent-colored card on
the landing page - moved after visual feedback that it looked out of
place there. The 4 volume cards themselves keep the size bump from that
version: 128px to `round(128 * 1.618)` = 207px (`LANDING_CARD_SIZE` in
card_grid.py) - sized up by the golden ratio so they visibly fill the
landing page's otherwise mostly-empty space, since it only ever holds 4
cards unlike the book/chapter grids.

Real bug hit while wiring this up: `QMenuBar` doesn't actually support
`QWidgetAction` the way `QToolBar` does - a `QPushButton` added that way
gets a computed geometry but is left unparented and never painted, so it
silently doesn't appear at all. `setCornerWidget()` is the mechanism that
actually works. A second, separate bug from the same change: the
container `QWidget` holding both the button and the badge has to be
stored on `self` (`self._menu_corner`), not a local variable in
`_build_menu()` - PySide/shiboken can garbage-collect a widget (cascading
to delete its children's underlying C++ objects too) once its last Python
reference goes out of scope, even though Qt's own C++ parent-child
ownership nominally covers it once `setCornerWidget()` is called.

Not yet built: verse highlighting. The data layer already supports it;
only the UI is missing.

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
        theme.py           # light/dark + day/night/sepia palettes, Material-style QSS
        card_grid.py       # reusable clickable card + FlowLayout wrapping card-grid widget
        breadcrumb.py       # clickable breadcrumb bar
        reading_view.py     # chapter reading view: verse list, annotate buttons, zoom
        note_editor.py      # note/tag editor dialog, used for both a verse and a chapter
        search_view.py       # keyword/reference/tag/note search, one box, four sections
        about_dialog.py       # version, unofficial-app disclaimer, beandog + church credits
        export.py              # notes/search-results export to ~/Documents as .txt
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
  segment jumps back to it correctly; it's empty on the landing page
  itself (nothing to navigate back to there) and starts with "Desktop
  Scriptures" as soon as you're one level deep
- Window title bar always says "Desktop Scriptures"
- Help menu -> About Desktop Scriptures opens a dialog with the version,
  the unofficial-app disclaimer, a "Special thanks to Beandog" credit
  (linking to its GitHub repo), and a churchofjesuschrist.org link - both
  links should open in your default browser

### Theming checklist

All of this lives under the **View** menu.

- App Theme (Light/Dark) restyles the window chrome, menus, cards, and
  breadcrumb; switching it does NOT change the reading view's colors -
  that's the independent axis below
- Reading Colors (Day/Night/Sepia) restyles only the open chapter's
  background/text/verse-number colors - try every combination with both
  App Themes (e.g. Dark chrome + Sepia reading) to confirm they're truly
  independent
- Font submenu lists fonts actually installed on this machine (always
  includes "Sans Serif" as a safe fallback); picking one restyles the
  currently-open chapter's text immediately
- Zoom In/Out (Ctrl+=/Ctrl+-), Reset Zoom (Ctrl+0), and the A-/A+ buttons
  in the reading view's top-right all resize verse text together, clamped
  10-28pt
- Close the app and reopen it - the last-chosen theme, reading colors,
  font, and zoom level should all still be in effect (persisted to the
  `settings` table)
- Navigate through several levels (volume -> book -> chapter -> back via
  breadcrumb) and watch the breadcrumb bar closely for stray leftover
  pixels from the previous label - this is what the `hide()`-before-
  `deleteLater()` fix above addresses; worth re-checking after any future
  breadcrumb change

### Notes/tags checklist

- Click a verse's pencil icon - a dialog opens titled with that verse's
  reference (e.g. "1 Nephi 1:1")
- Type a note, add a couple of tags (Enter or the Add button), Save - the
  dialog closes and that verse's pencil icon turns filled/indigo
- Reopen the same verse's dialog - the note text and tags you added are
  still there; remove a tag with its `x` - it's gone immediately, no
  separate save step needed for tags
- Clear the note text entirely and Save (or use "Delete Note") - the
  pencil icon reverts to its plain outline UNLESS tags remain on that
  verse (the icon reflects "has a note OR tags", not just the note)
- Click the chapter-level "Note" button in the reading view's header -
  same dialog, but scoped to the whole chapter instead of one verse; its
  own indicator (text/border turn indigo) follows the same rule
- Close and reopen the app on the same chapter - notes and tags are still
  there (they're in the `notes`/`tags`/`tag_assignments` tables, not the
  `settings` key/value store)
- Watch for the reading-view box bug described above (a wrong-colored
  rectangle behind verse text) if you ever change reading-view styling -
  it's specific to word-wrapped `RichText` `QLabel`s and easy to
  reintroduce by accident

### Search checklist

- The search box is visible in the header on every screen - landing page,
  book/chapter grids, and the reading view - without clicking anything
  first; confirm it's still there after navigating around
- Press Ctrl+F from anywhere - focus jumps to the search box (and selects
  any text already in it) instead of opening a separate page
- Type a common word (e.g. "charity") *while on some other screen, like a
  chapter reading view* - about a quarter second after you stop typing,
  the app should navigate itself to the search results and the breadcrumb
  should read "Scriptures > Search"; the box keeps your typed text since
  it's part of the header, not the page that just got replaced
- With results showing, add a note and a tag to some verse first (see the
  notes/tags checklist above) with a word/name you then search for -
  confirm **Tags** and **Notes** sections appear *before* **Chapters**
  and **Verses** in the results, in that order
- Type a reference like "John 3:16" - it appears at the top of "Verses"
  ahead of any keyword matches, and "1 John 3:16" also shows up (a
  reference search is substring-based on purpose)
- Type a book name or "Book Chapter" (e.g. "Alma", "Genesis 1") - a
  "Chapters" section appears; the exact chapter you typed sorts before
  incidental matches like "Genesis 10"
- Search something that matches nothing - a centered "No results for..."
  message appears instead of empty blank space
- Click any result - it navigates straight to that chapter's reading view
  with the *full* correct breadcrumb (volume -> testament if any -> book
  -> chapter), the same as clicking through the card grid by hand, and
  the search box in the header still has your query in it

### Export & Share checklist

- Menu bar reads, left to right, exactly "Menu", "View", "Help"
- With at least one note saved, Menu -> Export Notes - a message box
  reports how many notes were saved and the exact path; that file should
  exist under `~/Documents/`, one entry per note, in scripture order
- With no notes, Menu -> Export Notes instead says there's nothing to
  export yet, and no file is written
- With the search bar empty (or right after opening Search with nothing
  typed yet), there's no "Export Results" button - it only appears once
  you've typed something, top-right, right below the "Search results
  for ..." banner and above the first results section
- Type something with verse matches, then click "Export Results" - a
  message box reports how many verses were saved and the path; the file
  should list every verse currently shown in the Verses section
  (reference + full text), including any exact reference match first
- Search something with no verse matches (tags/notes/chapters only, or
  nothing at all) and click "Export Results" anyway - it says so instead
  of writing an empty file
- Menu -> Share the Book of Mormon - a dialog appears with a clickable
  link; clicking it opens https://go.churchofjesuschrist.org/x/n1Ic in
  your default browser

### Resume Reading & streak checklist

- On a fresh database (no reading history), the menu bar's top-right
  corner is empty - no "Resume Reading" button, no streak badge - right
  after "Help"
- Open any chapter - both appear immediately in that same corner: a
  solid, filled "Resume Reading" button first, then "\U0001f525 1 day
  streak" - clearly buttons/badges, not plain menu text
- Click "Resume Reading" - it navigates straight to the chapter you were
  just reading, with the correct breadcrumb, same as clicking through the
  card grid by hand
- The landing page itself only ever shows the 4 volume cards now - no 5th
  card - but they should look noticeably larger than the book/chapter
  grids one level deeper; that's intentional (`LANDING_CARD_SIZE` vs
  `CARD_SIZE` in card_grid.py)

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

Also verified: a full import run against the real 41,995-verse
`lds-scriptures.txt`, with no unmatched book names.

## Next steps

The data layer already supports both of these; only the UI is missing:

1. Verse highlighting - yellow/pink/orange, one per verse.
2. Reading-streak display.
