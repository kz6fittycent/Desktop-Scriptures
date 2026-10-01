"""A Hebrew/Aramaic lexicon entry, in full (see lexicon_entries in
schema.sql and scripts/import_hebrew_lexicon.py): the word in Hebrew,
its transliteration and pronunciation, meaning, Strong's definition,
derivation, and how the King James Version translates it.

LexiconEntryView is the reusable part - shown in the reading view's Word
Study tab (word_study_panel.py) and in LexiconDialog (opened from search
results). Other entries a derivation names ("from H4886") are links:
clicking one shows that entry in place, with Back to return. The
sources' required credit sits at the bottom, linked, like the Help
menu's.
"""

from __future__ import annotations

import html
import re
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from scriptures.data_access import LexiconEntry, get_lexicon_entry

OPEN_SCRIPTURES_URL = "https://github.com/openscriptures/strongs"
STEPBIBLE_URL = "https://www.STEPBible.org"
LEXICON_CREDIT = (
    f'Definitions: Strong\'s Hebrew dictionary (1894), <a href="{OPEN_SCRIPTURES_URL}">Open '
    f'Scriptures</a> edition, CC BY-SA. Short meanings: <a href="{STEPBIBLE_URL}">STEP Bible</a>, '
    "CC BY."
)

_STRONGS_RE = re.compile(r"\b(H\d{1,4})\b")


def _linked(text: str) -> str:
    """HTML-escaped text with every Strong's number turned into a link."""
    return _STRONGS_RE.sub(r'<a href="\1">\1</a>', html.escape(text))


def language_name(entry: LexiconEntry) -> str:
    return "Aramaic" if entry.language == "aramaic" else "Hebrew"


class LexiconEntryView(QWidget):
    """One entry, with derivation links and Back. `entry_shown(strongs,
    title)` fires whenever the shown entry changes (a dialog uses it for
    its window title)."""

    entry_shown = Signal(str, str)

    def __init__(self, conn: sqlite3.Connection, parent: QWidget | None = None):
        super().__init__(parent)
        self._conn = conn
        self._history: list[str] = []
        self._current: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._hebrew = QLabel()
        self._hebrew.setObjectName("lexiconHebrew")
        self._hebrew.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Hebrew reads right to left.
        self._hebrew.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout.addWidget(self._hebrew)

        self._heading = QLabel()
        self._heading.setObjectName("resultPrimary")
        self._heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._heading.setWordWrap(True)
        layout.addWidget(self._heading)

        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self._body.linkActivated.connect(self._follow)
        layout.addWidget(self._body)

        self._back = QPushButton("← Back")
        self._back.setAutoDefault(False)
        self._back.clicked.connect(self.go_back)
        self._back.hide()
        layout.addWidget(self._back, alignment=Qt.AlignmentFlag.AlignLeft)

        credit = QLabel(LEXICON_CREDIT)
        credit.setObjectName("resultSecondary")
        credit.setWordWrap(True)
        credit.setTextFormat(Qt.TextFormat.RichText)
        credit.setOpenExternalLinks(True)
        layout.addWidget(credit)

    def show_entry(self, strongs: str, *, keep_history: bool = False) -> None:
        """Show an entry. A fresh lookup (the default) clears Back's
        history; following a derivation link keeps it."""
        if not keep_history:
            self._history.clear()
        entry = get_lexicon_entry(self._conn, strongs)
        if entry is None:
            self._hebrew.clear()
            self._heading.setText(f"{strongs} isn't in the lexicon.")
            self._body.clear()
        else:
            self._render(entry)
        self._current = strongs
        self._back.setVisible(bool(self._history))

    def _render(self, entry: LexiconEntry) -> None:
        language = language_name(entry)
        self._hebrew.setText(entry.lemma)
        pronunciation = f" · pronounced {entry.pronunciation}" if entry.pronunciation else ""
        self._heading.setText(
            f"{entry.transliteration}{pronunciation}\n{language} · Strong's {entry.strongs}"
        )
        parts = []
        if entry.gloss:
            parts.append(f"<p><b>Meaning:</b> {html.escape(entry.gloss)}</p>")
        if entry.definition:
            parts.append(f"<p><b>Definition:</b> {_linked(entry.definition)}</p>")
        if entry.derivation:
            parts.append(f"<p><b>Derivation:</b> {_linked(entry.derivation)}</p>")
        if entry.kjv_renderings:
            parts.append(
                f"<p><b>The King James Version translates it:</b> {_linked(entry.kjv_renderings)}</p>"
            )
        self._body.setText("".join(parts))
        self.entry_shown.emit(entry.strongs, f"{language} word - Strong's {entry.strongs}")

    def _follow(self, strongs: str) -> None:
        if self._current:
            self._history.append(self._current)
        self.show_entry(strongs, keep_history=True)

    def go_back(self) -> None:
        if self._history:
            self.show_entry(self._history.pop(), keep_history=True)


class LexiconDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, strongs: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        self.view = LexiconEntryView(conn, self)
        self.view.entry_shown.connect(lambda _strongs, title: self.setWindowTitle(title))
        layout.addWidget(self.view)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.view.show_entry(strongs)
