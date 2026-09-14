"""Note and tag editor dialog.

One dialog handles both verse-level and chapter-level notes/tags - which
target it edits is decided by which of verse_id/chapter_id is passed in,
mirroring the data layer's own `notes`/`tag_assignments` design (a row
attaches to exactly one of the two).
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scriptures.data_access import add_tag, delete_note, get_note, get_tags, remove_tag, save_note
from scriptures.ui.card_grid import FlowLayout


class TagChip(QWidget):
    """A small rounded pill showing a tag name with a remove button."""

    removed = Signal(int)

    def __init__(self, tag_id: int, name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.tag_id = tag_id
        self.setObjectName("tagChip")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 6, 4)
        layout.setSpacing(6)

        label = QLabel(name)
        layout.addWidget(label)

        close_btn = QPushButton("×")
        close_btn.setObjectName("tagChipClose")
        close_btn.setFixedSize(16, 16)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(lambda: self.removed.emit(self.tag_id))
        layout.addWidget(close_btn)


class NoteEditorDialog(QDialog):
    """Edit the note and tags attached to a single verse or chapter.

    `changed` is set to True if anything was actually written to the
    database, so the caller knows whether to refresh its own display
    (e.g. a verse's "has annotation" indicator) after the dialog closes.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        title: str,
        *,
        verse_id: int | None = None,
        chapter_id: int | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self.verse_id = verse_id
        self.chapter_id = chapter_id
        self.changed = False

        self.setWindowTitle(f"Note — {title}")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(heading)

        layout.addWidget(QLabel("Note"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Write a note...")
        self.text_edit.setMinimumHeight(120)
        existing_note = get_note(conn, verse_id=verse_id, chapter_id=chapter_id)
        self._note_id = existing_note.id if existing_note else None
        if existing_note:
            self.text_edit.setPlainText(existing_note.text)
        layout.addWidget(self.text_edit)

        layout.addWidget(QLabel("Tags"))
        self.tags_container = QWidget()
        self.tags_flow = FlowLayout(self.tags_container, margin=0, spacing=8)
        layout.addWidget(self.tags_container)

        tag_input_row = QHBoxLayout()
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Add a tag and press Enter")
        self.tag_input.returnPressed.connect(self._add_tag)
        tag_input_row.addWidget(self.tag_input)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_tag)
        tag_input_row.addWidget(add_btn)
        layout.addLayout(tag_input_row)

        buttons = QDialogButtonBox()
        self.delete_btn = buttons.addButton(
            "Delete Note", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        self.delete_btn.setEnabled(self._note_id is not None)
        self.delete_btn.clicked.connect(self._delete_note)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        save_btn = buttons.addButton(QDialogButtonBox.StandardButton.Save)
        save_btn.setDefault(True)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._reload_tags()

    def _reload_tags(self) -> None:
        while self.tags_flow.count():
            item = self.tags_flow.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        for tag in get_tags(self.conn, verse_id=self.verse_id, chapter_id=self.chapter_id):
            chip = TagChip(tag.id, tag.name)
            chip.removed.connect(self._remove_tag)
            self.tags_flow.addWidget(chip)

    def _add_tag(self) -> None:
        name = self.tag_input.text().strip()
        if not name:
            return
        add_tag(self.conn, name, verse_id=self.verse_id, chapter_id=self.chapter_id)
        self.tag_input.clear()
        self.changed = True
        self._reload_tags()

    def _remove_tag(self, tag_id: int) -> None:
        remove_tag(self.conn, tag_id, verse_id=self.verse_id, chapter_id=self.chapter_id)
        self.changed = True
        self._reload_tags()

    def _save(self) -> None:
        text = self.text_edit.toPlainText().strip()
        if text:
            save_note(self.conn, text, verse_id=self.verse_id, chapter_id=self.chapter_id)
            self.changed = True
        elif self._note_id is not None:
            # Saved with an empty body: treat as clearing the note.
            delete_note(self.conn, self._note_id)
            self.changed = True
        self.accept()

    def _delete_note(self) -> None:
        if self._note_id is not None:
            delete_note(self.conn, self._note_id)
            self.changed = True
        self.accept()
