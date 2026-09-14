"""Search results view: keywords, references, tags, and notes.

The search box itself lives in MainWindow's persistent header (always
visible, not tucked behind a menu) - this widget only renders results for
whatever query MainWindow hands it via `set_query()`.

Four independent lookups run on every query and are shown as labeled
sections, each only appearing when it has results. Tags and notes are
your own annotations, so they're shown first, ahead of the scripture
matches themselves:
- Tags: tag-name matches, with every verse/chapter that tag is attached
  to listed directly underneath - no separate drill-down click needed
- Notes: a keyword (FTS5) match over note text
- Chapters: book/chapter name matches (e.g. "Genesis 1", "Alma")
- Verses: a direct reference match (e.g. "John 3:16") first, then a
  keyword (FTS5) match over scripture text, deduplicated by verse

Clicking any result emits `result_selected(chapter_id)`; MainWindow
resolves that chapter's full volume/testament/book path and navigates
exactly as if the chapter had been reached by clicking through the
normal card-grid levels.
"""

from __future__ import annotations

import sqlite3

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

from scriptures.data_access import (
    get_tag_targets,
    search_chapters,
    search_notes,
    search_tags_by_name,
    search_verse_references,
    search_verses,
)
from scriptures.ui.export import export_search_results


def _truncate(text: str, limit: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class ResultRow(QFrame):
    """A single clickable search result: a bold primary line (usually a
    reference) and an optional secondary line (a snippet)."""

    clicked = Signal(int)

    def __init__(
        self, chapter_id: int, primary_text: str, secondary_text: str = "", parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.chapter_id = chapter_id
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

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.chapter_id)
        super().mousePressEvent(event)


class SearchView(QWidget):
    result_selected = Signal(int)

    def __init__(self, conn: sqlite3.Connection, parent: QWidget | None = None):
        super().__init__(parent)
        self.conn = conn
        self._query = ""

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

        matched_tags = search_tags_by_name(self.conn, query)
        note_rows = [
            ResultRow(n.chapter_id, n.reference, _truncate(n.text))
            for n in search_notes(self.conn, query)
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
        self._add_section("Chapters", chapter_rows)
        self._add_section("Verses", verse_rows)

        if not (chapter_rows or verse_rows or note_rows or matched_tags):
            self._show_message(f'No results for "{query}".')
            return

        self._results_layout.addStretch(1)
