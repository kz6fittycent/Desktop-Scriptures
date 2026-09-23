"""Search results view: keywords, references, tags, notes, and (when
configured - see ai_client.py's module docstring) AI-suggested matches.

The search box itself lives in MainWindow's persistent header (always
visible, not tucked behind a menu) - this widget only renders results for
whatever query MainWindow hands it via `set_query()`. There's no separate
"Ask a Question" flow: the same box that finds "John 3:16" also answers
"how did Christ organize the Nephite church", by product decision - one
place to search, not two.

Five independent LOCAL lookups run on every query and are shown as
labeled sections, each only appearing when it has results. Tags, notes,
and the journal are your own annotations, so they're shown first, ahead
of the scripture matches themselves:
- Tags: tag-name matches, with every verse/chapter that tag is attached
  to listed directly underneath - no separate drill-down click needed
- Notes: a keyword (FTS5) match over note text
- Journal: a keyword (FTS5) match over journal entry text - same "your
  own words, not what it's linked to" behavior as Notes: an entry linked
  to a verse doesn't surface just because the query matches that verse's
  own scripture text, only if the query also matches what was actually
  written. Clicking a result opens the Journal at that entry's date
  (journal_entry_selected, a plain ISO date - not result_selected below,
  since an entry doesn't necessarily have a chapter to navigate to).
- Chapters: book/chapter name matches (e.g. "Genesis 1", "Alma")
- Verses: a direct reference match (e.g. "John 3:16") first, then a
  keyword (FTS5) match over scripture text, deduplicated by verse

If an AiConfig is supplied, a sixth, asynchronous lookup also runs: the
query is sent to ask.py as a natural-language question, and an
AiConversationSection (see ui/ai_conversation.py) renders whatever comes
back - already validated against this same local database - as a
"Suggested by AI" section above all the others, once it arrives. That
section also lets the user send follow-up refinements ("no, just the
ones about baptism") without starting a new top-level search - these
queries are typically full sentences a keyword search wouldn't match
well at all, so this is additive, not a replacement for the sections
below it.

Clicking any result emits `result_selected(chapter_id)`; MainWindow
resolves that chapter's full volume/testament/book path and navigates
exactly as if the chapter had been reached by clicking through the
normal card-grid levels. A Journal result is the one exception - it
emits `journal_entry_selected(entry_date)` instead, opening the Journal
at that date rather than a chapter.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from scriptures.ai_client import AiConfig
from scriptures.data_access import (
    JournalEntryResult,
    get_tag_targets,
    search_chapters,
    search_journal_entries,
    search_notes,
    search_tags_by_name,
    search_verse_references,
    search_verses,
)
from scriptures.ui.ai_conversation import AiConversationSection
from scriptures.ui.export import export_search_results
from scriptures.ui.result_row import ResultRow, truncate_text as _truncate


def _format_journal_result_heading(entry: JournalEntryResult) -> str:
    label = date.fromisoformat(entry.entry_date).strftime("%B %-d, %Y")
    if entry.reference:
        return f"Journal — {label} ({entry.reference})"
    return f"Journal — {label}"


class _JournalResultRow(QFrame):
    """A journal-entry search hit - a separate small copy of ResultRow's
    own shape rather than reusing it directly, since clicking one needs
    to open the Journal at that entry's date (a plain ISO date string),
    not navigate to a chapter_id the way every other result row does;
    a journal entry doesn't necessarily have one at all."""

    clicked = Signal(str)

    def __init__(
        self, entry_date: str, primary_text: str, secondary_text: str = "", parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.entry_date = entry_date
        self.setObjectName("resultRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        primary = QLabel(primary_text)
        primary.setObjectName("resultPrimary")
        primary.setWordWrap(True)
        layout.addWidget(primary)

        if secondary_text:
            secondary = QLabel(secondary_text)
            secondary.setObjectName("resultSecondary")
            secondary.setWordWrap(True)
            layout.addWidget(secondary)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.entry_date)
        super().mousePressEvent(event)


class SearchView(QWidget):
    result_selected = Signal(int)
    journal_entry_selected = Signal(str)

    def __init__(
        self,
        conn: sqlite3.Connection,
        ai_config: AiConfig | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self.ai_config = ai_config
        self._query = ""
        self._ai_section: AiConversationSection | None = None

        outer = QVBoxLayout(self)

        self._title = QLabel("Search")
        self._title.setObjectName("sectionTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._title)

        # Nested between the title banner and the results themselves,
        # right-aligned - exports whatever verses the Verses section
        # currently shows, not the tags/notes/chapters sections.
        export_row = QHBoxLayout()
        export_row.addStretch(1)
        self._export_btn = QPushButton("Export Results")
        self._export_btn.setObjectName("zoomButton")
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setVisible(False)
        self._export_btn.clicked.connect(self._export_results)
        export_row.addWidget(self._export_btn)
        outer.addLayout(export_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._results_container = QWidget()
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setSpacing(16)
        scroll.setWidget(self._results_container)
        outer.addWidget(scroll)

        self._show_message("Start typing to search.")

    def _clear_results(self) -> None:
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _show_message(self, text: str) -> None:
        self._clear_results()
        message = QLabel(text)
        message.setObjectName("resultSecondary")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._results_layout.addWidget(message)
        self._results_layout.addStretch(1)

    def _add_section(self, heading: str, rows: list[ResultRow]) -> None:
        if not rows:
            return
        header = QLabel(heading)
        header.setObjectName("searchSectionHeader")
        self._results_layout.addWidget(header)
        for row in rows:
            row.clicked.connect(self.result_selected)
            self._results_layout.addWidget(row)

    def _add_journal_section(self, rows: list[_JournalResultRow]) -> None:
        if not rows:
            return
        header = QLabel("Journal")
        header.setObjectName("searchSectionHeader")
        self._results_layout.addWidget(header)
        for row in rows:
            row.clicked.connect(self.journal_entry_selected)
            self._results_layout.addWidget(row)

    def _export_results(self) -> None:
        export_search_results(self.conn, self._query, self)

    def set_query(self, query: str) -> None:
        query = query.strip()
        self._query = query
        self._title.setText(f'Search results for "{query}"' if query else "Search")
        self._export_btn.setVisible(bool(query))
        if not query:
            self._show_message("Start typing to search.")
            return
        self._clear_results()
        self._ai_section = None

        # Started first so it renders above the synchronous local sections
        # below - a query like a full question is exactly the shape those
        # rarely match well at all, so this is additive, never a
        # replacement for them. AiConversationSection owns its own
        # placeholder/results/follow-up input from here on.
        if self.ai_config is not None:
            self._ai_section = AiConversationSection(self.conn, self.ai_config, query, parent=self)
            self._ai_section.result_selected.connect(self.result_selected)
            self._results_layout.addWidget(self._ai_section)

        matched_tags = search_tags_by_name(self.conn, query)
        note_rows = [
            ResultRow(n.chapter_id, n.reference, _truncate(n.text))
            for n in search_notes(self.conn, query)
        ]
        journal_rows = [
            _JournalResultRow(
                e.entry_date,
                _format_journal_result_heading(e),
                _truncate(e.text),
            )
            for e in search_journal_entries(self.conn, query)
        ]
        chapter_rows = [
            ResultRow(m.chapter_id, m.label) for m in search_chapters(self.conn, query)
        ]
        seen_verse_ids: set[int] = set()
        verse_rows = []
        for v in [*search_verse_references(self.conn, query), *search_verses(self.conn, query)]:
            if v.id in seen_verse_ids:
                continue
            seen_verse_ids.add(v.id)
            verse_rows.append(ResultRow(v.chapter_id, v.reference, _truncate(v.text)))

        # Tags and notes are your own annotations, so they lead; chapters
        # and verses (matches within the scripture text itself) follow.
        for tag in matched_tags:
            header = QLabel(f"#{tag.name}")
            header.setObjectName("searchSectionHeader")
            self._results_layout.addWidget(header)
            for item in get_tag_targets(self.conn, tag.id):
                row = ResultRow(item.chapter_id, item.reference)
                row.clicked.connect(self.result_selected)
                self._results_layout.addWidget(row)
        self._add_section("Notes", note_rows)
        self._add_journal_section(journal_rows)
        self._add_section("Chapters", chapter_rows)
        self._add_section("Verses", verse_rows)

        # Not _show_message() - that clears the whole layout, which would
        # also wipe the AI placeholder/section above if one is pending or
        # already showing. A plain inline note alongside it instead.
        if not (chapter_rows or verse_rows or note_rows or journal_rows or matched_tags):
            no_keyword_results = QLabel(
                f'No keyword results for "{query}".'
                if self.ai_config is not None
                else f'No results for "{query}".'
            )
            no_keyword_results.setObjectName("resultSecondary")
            no_keyword_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._results_layout.addWidget(no_keyword_results)

        self._results_layout.addStretch(1)
