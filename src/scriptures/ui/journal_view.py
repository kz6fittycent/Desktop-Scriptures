"""The Journal - one free-text entry per calendar day, optionally
reflecting on a specific verse or chapter (see schema.sql's
journal_entries table). Always opens to today; Previous Day/Next Day
page through other dates, Next Day disabled once already viewing today
(entries can't be written for the future). The entry text autosaves the
same way chapter/verse notes do (see chapter_panel.py's _AutosaveNote) -
there's no explicit save button, and switching dates or navigating away
flushes whatever's pending first.

The optional reference is a single free-text field, resolved through the
same reference parser AI-assisted search already uses (ask.py's
resolve_references) rather than a separate verse-picker UI - type
"Alma 32:21" and press Enter, the same as citing a passage anywhere else
in this app.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scriptures.ask import resolve_references
from scriptures.data_access import (
    delete_journal_entry,
    get_journal_entry,
    get_reference_label,
    save_journal_entry,
)

AUTOSAVE_DELAY_MS = 900
NOTE_FONT_FAMILY = "Ubuntu Mono"


class _ReferenceChip(QFrame):
    """The entry's optional linked passage, shown as a single clickable
    row - a separate small copy of the _TalkRow pattern used elsewhere
    (ai_conversation.py, citations_panel.py, topical_guide_view.py),
    matching those three's own precedent of a small copy rather than a
    shared import, since this one navigates within the app (emits a
    signal) rather than opening an external URL."""

    clicked = Signal()

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("resultRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open this passage")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        text = QLabel(f"→ {label}")
        text.setObjectName("resultPrimary")
        layout.addWidget(text)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class JournalView(QWidget):
    """`reference_selected(chapter_id)` mirrors SearchView's own signal -
    forwarded straight through so MainWindow doesn't need to know this
    widget exists."""

    reference_selected = Signal(int)

    def __init__(self, conn: sqlite3.Connection, parent: QWidget | None = None):
        super().__init__(parent)
        self.conn = conn
        self._current_date = date.today()
        self._reference_verse_id: int | None = None
        self._reference_chapter_id: int | None = None
        self._reference_target_chapter_id: int | None = None

        layout = QVBoxLayout(self)

        nav_row = QHBoxLayout()
        self._prev_btn = QPushButton("← Previous Day")
        self._prev_btn.setObjectName("navButton")
        self._prev_btn.clicked.connect(self._go_previous_day)
        nav_row.addWidget(self._prev_btn)

        self._date_label = QLabel()
        self._date_label.setObjectName("sectionTitle")
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_row.addWidget(self._date_label, 1)

        self._next_btn = QPushButton("Next Day →")
        self._next_btn.setObjectName("navButton")
        self._next_btn.clicked.connect(self._go_next_day)
        nav_row.addWidget(self._next_btn)
        layout.addLayout(nav_row)

        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("Write today's entry...")
        note_font = QFont(NOTE_FONT_FAMILY)
        note_font.setStyleHint(QFont.StyleHint.Monospace)
        self._text_edit.setFont(note_font)
        layout.addWidget(self._text_edit, 1)

        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("Reflecting on (optional):"))
        self._reference_edit = QLineEdit()
        self._reference_edit.setPlaceholderText("e.g. Alma 32:21")
        self._reference_edit.returnPressed.connect(self._resolve_reference)
        ref_row.addWidget(self._reference_edit, 1)
        self._clear_reference_btn = QPushButton("Clear")
        self._clear_reference_btn.clicked.connect(self._clear_reference)
        self._clear_reference_btn.setVisible(False)
        ref_row.addWidget(self._clear_reference_btn)
        layout.addLayout(ref_row)

        self._reference_not_found_label = QLabel("Couldn't find that reference.")
        self._reference_not_found_label.setObjectName("resultSecondary")
        self._reference_not_found_label.setVisible(False)
        layout.addWidget(self._reference_not_found_label)

        self._reference_chip: _ReferenceChip | None = None
        self._reference_chip_slot = QVBoxLayout()
        layout.addLayout(self._reference_chip_slot)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(AUTOSAVE_DELAY_MS)
        self._timer.timeout.connect(self.save_now)
        self._text_edit.textChanged.connect(self._timer.start)

        self.load_date(self._current_date)

    def load_date(self, target_date: date) -> None:
        """Public, not just internal Previous/Next Day plumbing - also
        called by MainWindow right after construction to jump straight
        to a specific date, e.g. from a Journal search result."""
        self.flush_pending_save()
        self._current_date = target_date
        self._date_label.setText(target_date.strftime("%A, %B %-d, %Y"))
        self._next_btn.setEnabled(target_date < date.today())

        entry = get_journal_entry(self.conn, target_date.isoformat())
        self._text_edit.blockSignals(True)
        self._text_edit.setPlainText(entry.text if entry else "")
        self._text_edit.blockSignals(False)

        self._reference_verse_id = entry.verse_id if entry else None
        self._reference_chapter_id = entry.chapter_id if entry else None
        self._reference_edit.clear()
        self._reference_not_found_label.setVisible(False)
        self._refresh_reference_chip()

    def _go_previous_day(self) -> None:
        self.load_date(self._current_date - timedelta(days=1))

    def _go_next_day(self) -> None:
        if self._current_date < date.today():
            self.load_date(self._current_date + timedelta(days=1))

    def _resolve_reference(self) -> None:
        text = self._reference_edit.text().strip()
        if not text:
            return
        refs = resolve_references(self.conn, [text])
        if not refs:
            self._reference_not_found_label.setVisible(True)
            return
        ref = refs[0]
        self._reference_not_found_label.setVisible(False)
        self._reference_edit.clear()
        # At most one of verse_id/chapter_id is ever stored (matching
        # notes' own convention - see schema.sql) - a specific verse
        # already implies its chapter via a join, so only chapter_id is
        # kept for a reference that resolved to a whole chapter instead.
        if ref.verse_id is not None:
            self._reference_verse_id = ref.verse_id
            self._reference_chapter_id = None
        else:
            self._reference_verse_id = None
            self._reference_chapter_id = ref.chapter_id
        self._refresh_reference_chip()
        self.save_now()

    def _clear_reference(self) -> None:
        self._reference_verse_id = None
        self._reference_chapter_id = None
        self._refresh_reference_chip()
        self.save_now()

    def _refresh_reference_chip(self) -> None:
        if self._reference_chip is not None:
            self._reference_chip.hide()
            self._reference_chip.deleteLater()
            self._reference_chip = None

        label = get_reference_label(
            self.conn, verse_id=self._reference_verse_id, chapter_id=self._reference_chapter_id
        )
        has_ref = label is not None
        self._clear_reference_btn.setVisible(has_ref)
        if not has_ref:
            return

        if self._reference_verse_id is not None:
            row = self.conn.execute(
                "SELECT chapter_id FROM verses WHERE id = ?", (self._reference_verse_id,)
            ).fetchone()
            self._reference_target_chapter_id = row["chapter_id"] if row else None
        else:
            self._reference_target_chapter_id = self._reference_chapter_id

        chip = _ReferenceChip(label)
        chip.clicked.connect(self._on_reference_clicked)
        self._reference_chip_slot.addWidget(chip)
        self._reference_chip = chip

    def _on_reference_clicked(self) -> None:
        if self._reference_target_chapter_id is not None:
            self.reference_selected.emit(self._reference_target_chapter_id)

    def save_now(self) -> None:
        text = self._text_edit.toPlainText().strip()
        entry_date = self._current_date.isoformat()
        if text:
            save_journal_entry(
                self.conn,
                entry_date,
                text,
                verse_id=self._reference_verse_id,
                chapter_id=self._reference_chapter_id,
            )
        else:
            existing = get_journal_entry(self.conn, entry_date)
            if existing:
                delete_journal_entry(self.conn, entry_date)

    def flush_pending_save(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self.save_now()
