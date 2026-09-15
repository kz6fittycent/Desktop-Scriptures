"""Chapter side panel: the single editing surface for this chapter's tags
and notes - both the chapter-level note and every per-verse note.

There used to be a separate modal dialog for per-verse notes/tags, opened
from each verse's pencil icon. It's retired: the pencil icon now just
reveals (creating if needed) that verse's entry here and focuses it, so
everything lives in one place instead of being scattered across popups.

Tags apply/remove immediately. Every note text box (chapter or verse)
autosaves shortly after the user stops typing, or immediately on focus
loss / panel teardown - there's no explicit save button anywhere here.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QEvent, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scriptures.data_access import (
    Verse,
    add_tag,
    delete_note,
    get_note,
    get_tags,
    remove_tag,
    save_note,
)
from scriptures.ui.card_grid import FlowLayout
from scriptures.ui.tag_chip import TagChip

PANEL_WIDTH = 300
AUTOSAVE_DELAY_MS = 900
NOTE_FONT_FAMILY = "Ubuntu Mono"


class _AutosaveNote(QVBoxLayout):
    """Shared bit of plumbing behind both the chapter note and each verse
    note: a QTextEdit that saves itself ~1s after typing stops or on focus
    loss, with the empty-body-means-delete convention the old dialog used."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        placeholder: str,
        *,
        verse_id: int | None = None,
        chapter_id: int | None = None,
        min_height: int = 90,
    ):
        super().__init__()
        self.conn = conn
        self.verse_id = verse_id
        self.chapter_id = chapter_id

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(placeholder)
        # StyleHint.Monospace is the fallback if Ubuntu Mono isn't actually
        # installed (e.g. a bare-bones Snap base) - fontconfig then
        # substitutes whatever monospace font it has, same fallback
        # approach theme.py uses for reading fonts. Built here rather than
        # at module import time since QFont needs a QApplication to exist.
        note_font = QFont(NOTE_FONT_FAMILY)
        note_font.setStyleHint(QFont.StyleHint.Monospace)
        self.text_edit.setFont(note_font)
        # Fixed, not minimum: QTextEdit defaults to an Expanding vertical
        # size policy, so inside this panel's unbounded scrollable column a
        # merely-minimum height lets it balloon to fill whatever leftover
        # space exists, pushing every entry below it further down than it
        # needs to be. Long text just scrolls within the box instead.
        self.text_edit.setFixedHeight(min_height)
        existing = get_note(conn, verse_id=verse_id, chapter_id=chapter_id)
        if existing:
            self.text_edit.setPlainText(existing.text)
        self.addWidget(self.text_edit)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(AUTOSAVE_DELAY_MS)
        self._timer.timeout.connect(self.save_now)
        self.text_edit.textChanged.connect(self._timer.start)

    def save_now(self) -> None:
        text = self.text_edit.toPlainText().strip()
        if text:
            save_note(self.conn, text, verse_id=self.verse_id, chapter_id=self.chapter_id)
        else:
            existing = get_note(self.conn, verse_id=self.verse_id, chapter_id=self.chapter_id)
            if existing:
                delete_note(self.conn, existing.id)

    def flush_pending_save(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.save_now()

    def has_text(self) -> bool:
        return bool(self.text_edit.toPlainText().strip())


class VerseNoteEntry(QFrame):
    """One verse's note + tags, shown in the panel's verse-notes section.
    Only shown for verses that currently have a note and/or tags, or that
    the user just opened via the pencil icon this session.
    """

    changed = Signal(int)  # verse_id - note or tags for this verse changed
    should_remove = Signal(int)  # verse_id - now has neither note nor tags

    def __init__(self, conn: sqlite3.Connection, verse: Verse, parent: QWidget | None = None):
        super().__init__(parent)
        self.conn = conn
        self.verse = verse
        self.setObjectName("sidePanelBox")

        layout = QVBoxLayout(self)

        title = QLabel(verse.reference)
        title.setObjectName("panelSectionTitle")
        layout.addWidget(title)

        self.tags_container = QWidget()
        self.tags_flow = FlowLayout(self.tags_container, margin=0, spacing=6)
        layout.addWidget(self.tags_container)

        input_row = QHBoxLayout()
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Add a tag...")
        self.tag_input.returnPressed.connect(self._add_tag)
        input_row.addWidget(self.tag_input)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_tag)
        input_row.addWidget(add_btn)
        layout.addLayout(input_row)

        self._note = _AutosaveNote(
            conn, "Write a note for this verse...", verse_id=verse.id, min_height=70
        )
        self._note.text_edit.installEventFilter(self)
        layout.addLayout(self._note)

        self._reload_tags()

    def focus_note(self) -> None:
        self._note.text_edit.setFocus()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt override)
        if obj is self._note.text_edit and event.type() == QEvent.Type.FocusOut:
            self._note.flush_pending_save()
            self.changed.emit(self.verse.id)
            self._maybe_remove()
        return super().eventFilter(obj, event)

    def flush_pending_save(self) -> None:
        self._note.flush_pending_save()

    def _reload_tags(self) -> None:
        while self.tags_flow.count():
            item = self.tags_flow.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for tag in get_tags(self.conn, verse_id=self.verse.id):
            chip = TagChip(tag.id, tag.name)
            chip.removed.connect(self._remove_tag)
            self.tags_flow.addWidget(chip)

    def _add_tag(self) -> None:
        name = self.tag_input.text().strip()
        if not name:
            return
        add_tag(self.conn, name, verse_id=self.verse.id)
        self.tag_input.clear()
        self._reload_tags()
        self.changed.emit(self.verse.id)

    def _remove_tag(self, tag_id: int) -> None:
        remove_tag(self.conn, tag_id, verse_id=self.verse.id)
        self._reload_tags()
        self.changed.emit(self.verse.id)
        self._maybe_remove()

    def _maybe_remove(self) -> None:
        if not self._note.has_text() and not get_tags(self.conn, verse_id=self.verse.id):
            self.should_remove.emit(self.verse.id)


class ChapterPanel(QWidget):
    """Scrollable panel: chapter tags, the chapter note, and the notes/tags
    for whichever verses currently have them (or were just opened)."""

    verse_annotation_changed = Signal(int)  # verse_id

    def __init__(
        self,
        conn: sqlite3.Connection,
        chapter_id: int,
        verses: list[Verse],
        annotated_verse_ids: set[int],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self.chapter_id = chapter_id
        self._verses_by_id = {v.id: v for v in verses}
        self._verse_entries: dict[int, VerseNoteEntry] = {}
        self.setFixedWidth(PANEL_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self._scroll)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 4, 0)
        self._content_layout.setSpacing(12)

        self._content_layout.addWidget(self._build_chapter_tags_box())
        self._content_layout.addWidget(self._build_chapter_note_box())

        self._verse_notes_container = QWidget()
        self._verse_notes_layout = QVBoxLayout(self._verse_notes_container)
        self._verse_notes_layout.setContentsMargins(0, 0, 0, 0)
        self._verse_notes_layout.setSpacing(12)
        self._content_layout.addWidget(self._verse_notes_container)

        self._content_layout.addStretch(1)
        self._scroll.setWidget(content)

        for verse_id in sorted(
            annotated_verse_ids, key=lambda vid: self._verses_by_id[vid].verse_number
        ):
            self._add_verse_entry(self._verses_by_id[verse_id])

    # ------------------------------------------------------------------
    # Chapter-level tags
    # ------------------------------------------------------------------

    def _build_chapter_tags_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("sidePanelBox")
        layout = QVBoxLayout(box)

        title = QLabel("Chapter Tags")
        title.setObjectName("panelSectionTitle")
        layout.addWidget(title)

        self.tags_container = QWidget()
        self.tags_flow = FlowLayout(self.tags_container, margin=0, spacing=6)
        layout.addWidget(self.tags_container)

        input_row = QHBoxLayout()
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Add a tag...")
        self.tag_input.returnPressed.connect(self._add_chapter_tag)
        input_row.addWidget(self.tag_input)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_chapter_tag)
        input_row.addWidget(add_btn)
        layout.addLayout(input_row)

        self._reload_chapter_tags()
        return box

    def _reload_chapter_tags(self) -> None:
        while self.tags_flow.count():
            item = self.tags_flow.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for tag in get_tags(self.conn, chapter_id=self.chapter_id):
            chip = TagChip(tag.id, tag.name)
            chip.removed.connect(self._remove_chapter_tag)
            self.tags_flow.addWidget(chip)

    def _add_chapter_tag(self) -> None:
        name = self.tag_input.text().strip()
        if not name:
            return
        add_tag(self.conn, name, chapter_id=self.chapter_id)
        self.tag_input.clear()
        self._reload_chapter_tags()

    def _remove_chapter_tag(self, tag_id: int) -> None:
        remove_tag(self.conn, tag_id, chapter_id=self.chapter_id)
        self._reload_chapter_tags()

    # ------------------------------------------------------------------
    # Chapter-level note
    # ------------------------------------------------------------------

    def _build_chapter_note_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("sidePanelBox")
        layout = QVBoxLayout(box)

        title = QLabel("Chapter Note")
        title.setObjectName("panelSectionTitle")
        layout.addWidget(title)

        self._chapter_note = _AutosaveNote(
            self.conn,
            "Capture your impressions...",
            chapter_id=self.chapter_id,
            min_height=120,
        )
        layout.addLayout(self._chapter_note)
        return box

    # ------------------------------------------------------------------
    # Per-verse notes/tags
    # ------------------------------------------------------------------

    def focus_verse(self, verse: Verse) -> None:
        """Reveal (creating if needed) this verse's entry and focus its
        note box - the pencil icon's whole job now."""
        entry = self._verse_entries.get(verse.id)
        if entry is None:
            entry = self._add_verse_entry(verse)
        # A just-inserted entry has no valid geometry yet - Qt only lays it
        # out on the next event loop turn - so ensureWidgetVisible() would
        # scroll based on stale (0,0) position. Deferring one tick, same
        # trick reading_view.py uses for its own post-construction relayout.
        QTimer.singleShot(0, lambda: self._reveal(entry))

    def _reveal(self, entry: "VerseNoteEntry") -> None:
        self._content_layout.activate()
        self._scroll.ensureWidgetVisible(entry, 0, 0)
        entry.focus_note()

    def _add_verse_entry(self, verse: Verse) -> VerseNoteEntry:
        entry = VerseNoteEntry(self.conn, verse)
        entry.changed.connect(self.verse_annotation_changed)
        entry.should_remove.connect(self._remove_verse_entry)
        self._verse_entries[verse.id] = entry

        # Keep entries in verse order rather than "most recently opened"
        # order, so the panel reads top-to-bottom the same way the chapter
        # does.
        insert_at = 0
        for i in range(self._verse_notes_layout.count()):
            item_widget = self._verse_notes_layout.itemAt(i).widget()
            if isinstance(item_widget, VerseNoteEntry) and item_widget.verse.verse_number < verse.verse_number:
                insert_at = i + 1
        self._verse_notes_layout.insertWidget(insert_at, entry)
        return entry

    def _remove_verse_entry(self, verse_id: int) -> None:
        entry = self._verse_entries.pop(verse_id, None)
        if entry is None:
            return
        self._verse_notes_layout.removeWidget(entry)
        entry.hide()
        entry.deleteLater()
        self.verse_annotation_changed.emit(verse_id)

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def flush_pending_save(self) -> None:
        """Save immediately anything mid-debounce - call before the panel
        goes away (chapter navigation, app close)."""
        self._chapter_note.flush_pending_save()
        for entry in self._verse_entries.values():
            entry.flush_pending_save()
