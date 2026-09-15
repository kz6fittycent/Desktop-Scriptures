"""Chapter reading view.

Displays verse number + text for every verse in a chapter, scrollable.
Reading color scheme, font family, and zoom are all applied here - the
app-theme (light/dark chrome) lives in theme.py's app-wide stylesheet
instead, since it applies to every screen, not just this one.

Each verse has a small annotate button that opens the note/tag editor for
that verse; the header has an equivalent button for a chapter-level note.
Highlighting attaches to this screen in a later pass - the data layer
already supports it, this just isn't wired up yet.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from scriptures.data_access import Verse, get_annotated_verse_ids, get_note, get_tags
from scriptures.ui.note_editor import NoteEditorDialog
from scriptures.ui.theme import PANEL_RADIUS, ReadingPalette


class ReadingView(QWidget):
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()

    def __init__(
        self,
        conn: sqlite3.Connection,
        chapter_id: int,
        title: str,
        verses: list[Verse],
        palette: ReadingPalette,
        font_family: str,
        font_size: int,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self.chapter_id = chapter_id
        self._title = title
        self._verses = verses

        outer = QVBoxLayout(self)

        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(title_label, stretch=1)

        self._chapter_note_btn = QPushButton("Note")
        self._chapter_note_btn.setObjectName("zoomButton")
        self._chapter_note_btn.setToolTip("Add or edit a note for this whole chapter")
        self._chapter_note_btn.clicked.connect(self._open_chapter_note)
        header.addWidget(self._chapter_note_btn)

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

        outer.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.viewport().setObjectName("readingViewport")
        self._content = QWidget()
        self._content.setObjectName("readingCard")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 18, 20, 18)
        self._content_layout.setSpacing(10)

        annotated_ids = get_annotated_verse_ids(conn, chapter_id)
        self._verse_labels: list[QLabel] = []
        self._annotate_buttons: dict[int, QPushButton] = {}
        for verse in verses:
            row = QHBoxLayout()
            row.setSpacing(10)

            annotate_btn = QPushButton("✎")
            annotate_btn.setObjectName("annotateButton")
            annotate_btn.setFixedSize(28, 28)
            annotate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            annotate_btn.setToolTip("Add or edit a note/tags for this verse")
            annotate_btn.setProperty("annotated", verse.id in annotated_ids)
            annotate_btn.clicked.connect(lambda checked=False, v=verse: self._open_verse_note(v))
            row.addWidget(annotate_btn, 0, Qt.AlignmentFlag.AlignTop)
            self._annotate_buttons[verse.id] = annotate_btn

            line = QLabel()
            line.setWordWrap(True)
            line.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(line, 1)
            self._verse_labels.append(line)

            self._content_layout.addLayout(row)

        self._content_layout.addStretch()
        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll)

        self._update_chapter_note_indicator()
        self.apply_theme(palette, font_family, font_size)

        # At construction time this view isn't parented into the window yet,
        # so word-wrapped labels compute their height against a provisional
        # width - clipping the last wrapped line until something (e.g.
        # zooming) forces a relayout. Re-validating once on the next event
        # loop turn, after the real width is known, fixes it up front.
        QTimer.singleShot(0, self._content_layout.activate)

    def apply_theme(self, palette: ReadingPalette, font_family: str, font_size: int) -> None:
        font = QFont(font_family, font_size)
        for label, verse in zip(self._verse_labels, self._verses):
            label.setFont(font)
            # Word-wrapped RichText QLabels ignore the stylesheet cascade
            # for their own background fill unless told explicitly here.
            label.setStyleSheet(f"color: {palette.text}; background: transparent;")
            label.setText(
                f'<span style="color:{palette.verse_number}"><b>{verse.verse_number}</b></span>'
                f"&nbsp;&nbsp;{verse.text}"
            )

        self._content.setStyleSheet(
            f"QWidget#readingCard {{ "
            f"background-color: {palette.background}; "
            f"border: 1px solid {palette.title_border}; "
            f"border-radius: {PANEL_RADIUS}px; "
            f"}}"
        )

    def _open_verse_note(self, verse: Verse) -> None:
        dlg = NoteEditorDialog(self.conn, verse.reference, verse_id=verse.id, parent=self)
        dlg.exec()
        if dlg.changed:
            self._refresh_verse_indicator(verse.id)

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

    def _open_chapter_note(self) -> None:
        dlg = NoteEditorDialog(self.conn, self._title, chapter_id=self.chapter_id, parent=self)
        dlg.exec()
        if dlg.changed:
            self._update_chapter_note_indicator()

    def _update_chapter_note_indicator(self) -> None:
        annotated = get_note(self.conn, chapter_id=self.chapter_id) is not None or bool(
            get_tags(self.conn, chapter_id=self.chapter_id)
        )
        self._chapter_note_btn.setProperty("annotated", annotated)
        self._chapter_note_btn.style().unpolish(self._chapter_note_btn)
        self._chapter_note_btn.style().polish(self._chapter_note_btn)
