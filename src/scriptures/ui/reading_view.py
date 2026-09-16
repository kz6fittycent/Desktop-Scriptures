"""Chapter reading view.

Displays verse number + text for every verse in a chapter, scrollable.
Reading color scheme, font family, and zoom are all applied here - the
app-theme (light/dark chrome) lives in theme.py's app-wide stylesheet
instead, since it applies to every screen, not just this one.

Each verse has a small pencil button; clicking it reveals (creating if
needed) that verse's note/tags entry in the persistent ChapterPanel docked
to the right, and focuses it there - the panel is the single editing
surface for every note and tag in this chapter, verse-level and
chapter-level alike.

Highlighting is armed from the Highlighter menu (see main_window.py) rather
than anything on this screen. Each verse's body is a read-only QTextEdit
rather than a QLabel specifically so the user can drag-select an exact
word or phrase (via QTextCursor character offsets) instead of only ever
being able to mark a whole verse; releasing the drag while a color is
armed applies (or, in "clear" mode, removes) that color over just the
selected span, matching the "highlighter pen" metaphor - pick a color
once, then mark up several verses without re-opening the menu each time.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scriptures.citations import Citation, get_citations
from scriptures.data_access import (
    Highlight,
    Verse,
    add_highlight,
    clear_highlight_range,
    get_annotated_verse_ids,
    get_highlights,
    get_note,
    get_tags,
)
from scriptures.ui.chapter_panel import ChapterPanel
from scriptures.ui.citations_dialog import CitationsDialog
from scriptures.ui.theme import HIGHLIGHT_COLORS, PANEL_RADIUS, ReadingPalette

VERSE_NUMBER_WIDTH = 32
CITATION_BADGE_WIDTH = 32


class _VerseTextEdit(QTextEdit):
    """Read-only, frameless, auto-height display for one verse's body text.

    A QTextEdit rather than a QLabel so the text is natively drag-selectable
    down to the character - `range_selected` reports the selection's
    [start, end) offsets straight into `verse.text`, since the document
    here holds nothing but that plain text (no markup, no verse-number
    prefix) - offsets always match Python string indices exactly.
    """

    range_selected = Signal(int, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("verseBody")
        self.setReadOnly(True)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.document().setDocumentMargin(0)
        self.viewport().setAutoFillBackground(False)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        super().resizeEvent(event)
        self._adjust_height()

    def _adjust_height(self) -> None:
        # QTextEdit wraps to its width automatically but never shrinks or
        # grows its own height to match - without this it either clips
        # wrapped lines or leaves a scrollbar-worthy gap. contentsMargins()
        # (the style's default frame width, reserved around the viewport
        # even with NoFrame set) has to be added on top of the document's
        # own height, or the last wrapped line clips into the row below.
        self.document().setTextWidth(self.viewport().width())
        margins = self.contentsMargins()
        height = round(self.document().size().height()) + margins.top() + margins.bottom()
        height = max(1, height)
        if height != self.height():
            self.setFixedHeight(height)

    def render_text(
        self, text: str, font: QFont, normal_color: str, highlights: list[Highlight]
    ) -> None:
        """Fully (re)render from the given source of truth - always a
        complete overwrite, never an incremental patch, so this can't drift
        from what's actually in the database."""
        self.setFont(font)
        if self.toPlainText() != text:
            self.setPlainText(text)

        normal_format = QTextCharFormat()
        normal_format.setForeground(QColor(normal_color))
        normal_format.clearBackground()
        whole_doc = QTextCursor(self.document())
        whole_doc.select(QTextCursor.SelectionType.Document)
        whole_doc.setCharFormat(normal_format)

        for hl in highlights:
            colors = HIGHLIGHT_COLORS[hl.color]
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colors.text))
            fmt.setBackground(QColor(colors.background))
            span = QTextCursor(self.document())
            span.setPosition(hl.start_offset)
            span.setPosition(hl.end_offset, QTextCursor.MoveMode.KeepAnchor)
            span.setCharFormat(fmt)

        self._adjust_height()

    def clear_selection(self) -> None:
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        cursor = self.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        if start == end:
            return
        self.range_selected.emit(start, end)


class ReadingView(QWidget):
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    prev_requested = Signal()
    next_requested = Signal()

    def __init__(
        self,
        conn: sqlite3.Connection,
        chapter_id: int,
        title: str,
        verses: list[Verse],
        palette: ReadingPalette,
        font_family: str,
        font_size: int,
        *,
        has_previous: bool = False,
        has_next: bool = False,
        armed_highlight: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self.chapter_id = chapter_id
        self._title = title
        self._verses = verses
        self._verse_highlights = get_highlights(conn, chapter_id)
        self._armed_highlight = armed_highlight

        outer = QHBoxLayout(self)

        reading_column = QVBoxLayout()

        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(title_label, stretch=1)

        zoom_out_btn = QPushButton("A-")
        zoom_out_btn.setObjectName("zoomButton")
        zoom_out_btn.setToolTip("Smaller text (Ctrl+-)")
        zoom_out_btn.clicked.connect(self.zoom_out_requested)
        header.addWidget(zoom_out_btn)

        zoom_in_btn = QPushButton("A+")
        zoom_in_btn.setObjectName("zoomButton")
        zoom_in_btn.setToolTip("Larger text (Ctrl+=)")
        zoom_in_btn.clicked.connect(self.zoom_in_requested)
        header.addWidget(zoom_in_btn)

        reading_column.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.viewport().setObjectName("readingViewport")
        self._content = QWidget()
        self._content.setObjectName("readingCard")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 18, 20, 18)
        self._content_layout.setSpacing(10)

        annotated_ids = get_annotated_verse_ids(conn, chapter_id)
        self._number_labels: dict[int, QLabel] = {}
        self._body_widgets: dict[int, _VerseTextEdit] = {}
        self._annotate_buttons: dict[int, QPushButton] = {}
        self._citation_buttons: dict[int, QPushButton] = {}
        self._citations: dict[int, list[Citation]] = {}
        for verse in verses:
            row = QHBoxLayout()
            row.setSpacing(10)

            annotate_btn = QPushButton("✎")
            annotate_btn.setObjectName("annotateButton")
            annotate_btn.setFixedSize(28, 28)
            annotate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            annotate_btn.setToolTip("Open this verse's note/tags in the side panel")
            annotate_btn.setProperty("annotated", verse.id in annotated_ids)
            annotate_btn.clicked.connect(lambda checked=False, v=verse: self._open_verse_note(v))
            row.addWidget(annotate_btn, 0, Qt.AlignmentFlag.AlignTop)
            self._annotate_buttons[verse.id] = annotate_btn

            number_label = QLabel(str(verse.verse_number))
            number_label.setFixedWidth(VERSE_NUMBER_WIDTH)
            number_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            row.addWidget(number_label, 0)
            self._number_labels[verse.id] = number_label

            # Always in the layout, at a fixed width, even for the (vast
            # majority of) verses outside the pilot's 100-verse pool that
            # have no citation data - so the body column's start x-position
            # stays identical across every verse in the chapter regardless
            # of which ones happen to show a badge, the same reasoning as
            # VERSE_NUMBER_WIDTH above. Left with no text/border/click, a
            # badge with no citations is invisible.
            citations = get_citations(verse.reference)
            self._citations[verse.id] = citations
            citation_btn = QPushButton(str(len(citations)) if citations else "")
            citation_btn.setObjectName("citationBadge")
            citation_btn.setFixedSize(CITATION_BADGE_WIDTH, 28)
            citation_btn.setProperty("hasCitations", bool(citations))
            if citations:
                citation_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                citation_btn.setToolTip(
                    f"Cited in {len(citations)} General Conference "
                    f"talk{'s' if len(citations) != 1 else ''} - click to view"
                )
                citation_btn.clicked.connect(
                    lambda checked=False, v=verse: self._open_citations(v)
                )
            else:
                citation_btn.setEnabled(False)
            row.addWidget(citation_btn, 0, Qt.AlignmentFlag.AlignTop)
            self._citation_buttons[verse.id] = citation_btn

            body = _VerseTextEdit()
            body.range_selected.connect(
                lambda start, end, v=verse: self._on_range_selected(v, start, end)
            )
            row.addWidget(body, 1)
            self._body_widgets[verse.id] = body

            self._content_layout.addLayout(row)

        self._content_layout.addStretch()
        self._scroll.setWidget(self._content)
        reading_column.addWidget(self._scroll)

        nav_row = QHBoxLayout()
        self._prev_btn = QPushButton("← Previous")
        self._prev_btn.setObjectName("navButton")
        self._prev_btn.setEnabled(has_previous)
        self._prev_btn.clicked.connect(self.prev_requested)
        nav_row.addWidget(self._prev_btn)

        nav_row.addStretch(1)

        self._next_btn = QPushButton("Next →")
        self._next_btn.setObjectName("navButton")
        self._next_btn.setEnabled(has_next)
        self._next_btn.clicked.connect(self.next_requested)
        nav_row.addWidget(self._next_btn)

        reading_column.addLayout(nav_row)

        outer.addLayout(reading_column, 1)

        self._panel = ChapterPanel(conn, chapter_id, verses, annotated_ids)
        self._panel.verse_annotation_changed.connect(self._refresh_verse_indicator)
        outer.addWidget(self._panel)

        self.apply_theme(palette, font_family, font_size)

        # At construction time this view isn't parented into the window yet,
        # so the verse text edits compute their wrapped height against a
        # provisional width - clipping the last wrapped line until something
        # (e.g. zooming) forces a relayout. Re-validating once on the next
        # event loop turn, after the real width is known, fixes it up front.
        #
        # For the verse text edits specifically, one activate() isn't
        # enough on its own: each has a fixed height (see
        # _VerseTextEdit._adjust_height), so correcting row N's height
        # shifts row N+1's position, which Qt only resolves reactively
        # through that row's own next resizeEvent - a cascade that can take
        # several event-loop turns to fully settle in a long chapter,
        # visibly "jumping" during it. Recomputing every row's height in
        # one explicit pass, all against the now-final width, avoids the
        # cascade instead of waiting it out.
        QTimer.singleShot(0, self._finalize_verse_layout)

    def _finalize_verse_layout(self) -> None:
        self._content_layout.activate()
        for body in self._body_widgets.values():
            body._adjust_height()
        # setFixedHeight() above invalidates the layout but only *schedules*
        # repositioning sibling rows for the next event-loop pass - without
        # forcing it here too, every row after the first would still
        # visibly jump into place a frame later instead of appearing right.
        self._content_layout.activate()

    def apply_theme(self, palette: ReadingPalette, font_family: str, font_size: int) -> None:
        self._palette = palette
        self._font = QFont(font_family, font_size)
        for verse in self._verses:
            self._render_verse(verse)

        self._content.setStyleSheet(
            f"QWidget#readingCard {{ "
            f"background-color: {palette.background}; "
            f"border: 1px solid {palette.title_border}; "
            f"border-radius: {PANEL_RADIUS}px; "
            f"}}"
        )

    def _render_verse(self, verse: Verse) -> None:
        number_label = self._number_labels[verse.id]
        number_label.setFont(self._font)
        number_label.setStyleSheet(
            f"color: {self._palette.verse_number}; font-weight: bold; background: transparent;"
        )

        body = self._body_widgets[verse.id]
        body.render_text(
            verse.text, self._font, self._palette.text, self._verse_highlights.get(verse.id, [])
        )

    def _open_verse_note(self, verse: Verse) -> None:
        self._panel.focus_verse(verse)

    def _open_citations(self, verse: Verse) -> None:
        citations = self._citations.get(verse.id, [])
        if not citations:
            return
        dialog = CitationsDialog(verse.reference, citations, parent=self)
        dialog.exec()

    def _on_range_selected(self, verse: Verse, start: int, end: int) -> None:
        # Selection is otherwise left alone here - with no highlighter
        # armed, dragging across verse text is just ordinary text
        # selection (e.g. to copy it), and clearing it out from under the
        # user right after they made it would defeat that.
        if self._armed_highlight is None:
            return
        if self._armed_highlight == "clear":
            clear_highlight_range(self.conn, verse.id, start, end)
        else:
            add_highlight(self.conn, verse.id, self._armed_highlight, start, end)
        self._verse_highlights = get_highlights(self.conn, self.chapter_id)
        self._render_verse(verse)
        self._body_widgets[verse.id].clear_selection()

    def set_armed_highlight(self, color: str | None) -> None:
        """Called by MainWindow when the Highlighter menu selection
        changes, so an already-open chapter picks up the new tool without
        needing to be reopened."""
        self._armed_highlight = color

    def _refresh_verse_indicator(self, verse_id: int) -> None:
        btn = self._annotate_buttons.get(verse_id)
        if btn is None:
            return
        annotated = get_note(self.conn, verse_id=verse_id) is not None or bool(
            get_tags(self.conn, verse_id=verse_id)
        )
        btn.setProperty("annotated", annotated)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def flush_pending_save(self) -> None:
        """Forwarded to the chapter panel - see ChapterPanel.flush_pending_save."""
        self._panel.flush_pending_save()
