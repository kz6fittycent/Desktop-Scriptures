"""Word Study tab: the original-language words behind the English you're
reading - the v3.0 linguistics roadmap's first layers (see the README):
Hebrew and Aramaic for the Old Testament, Greek for the New.

Look up a word by typing it at the top, or by right-clicking it in the
reading view ("Look Up Original Word" - see reading_view.py). The matches
are the words whose King James renderings or meanings include it
(data_access.search_lexicon): "anointed" finds Hebrew mashiach and Greek
chriō. Reading the New Testament, Greek matches are listed first; the Old
Testament, Hebrew/Aramaic. Picking one shows the full entry below
(lexicon_dialog's LexiconEntryView).

These are the words the KJV translates that way in general, not
necessarily the exact word behind one particular verse - pinning that
down needs a word-by-word tagged text, planned separately.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from scriptures.data_access import LexiconEntry, search_lexicon
from scriptures.ui.lexicon_dialog import LexiconEntryView, language_name

INTRO = (
    "Look up the Hebrew, Aramaic, or Greek words behind an English word - type it "
    "above, or right-click a word in the text and choose Look Up Original Word."
)


class _MatchButton(QPushButton):
    """One matching word - a choice card (see theme.py's choiceCard),
    transliteration first so the line lays out left to right."""

    def __init__(self, entry: LexiconEntry, parent: QWidget | None = None):
        super().__init__(f"{entry.transliteration} · {entry.lemma}\n{entry.gloss}", parent)
        self.setObjectName("choiceCard")
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{language_name(entry)} · Strong's {entry.strongs}")
        self.strongs = entry.strongs


class WordStudyPanel(QWidget):
    def __init__(
        self,
        conn: sqlite3.Connection,
        preferred_language: str | None = None,
        parent: QWidget | None = None,
    ):
        """`preferred_language` ("hebrew" or "greek") lists that language's
        matches first - the chapter being read decides it."""
        super().__init__(parent)
        self._conn = conn
        self._preferred = preferred_language
        self._buttons: list[_MatchButton] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        search_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Look up a word, e.g. anointed")
        self._input.returnPressed.connect(lambda: self.look_up(self._input.text()))
        search_row.addWidget(self._input, 1)
        go = QPushButton("Look Up")
        go.setAutoDefault(False)
        go.clicked.connect(lambda: self.look_up(self._input.text()))
        search_row.addWidget(go)
        outer.addLayout(search_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 8, 4, 0)
        layout.setSpacing(8)

        self._status = QLabel(INTRO)
        self._status.setObjectName("resultSecondary")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._matches = QVBoxLayout()
        self._matches.setSpacing(6)
        layout.addLayout(self._matches)

        self._entry = LexiconEntryView(conn)
        self._entry.hide()
        layout.addWidget(self._entry)
        layout.addStretch(1)

    def look_up(self, word: str) -> None:
        word = " ".join(word.split())
        self._input.setText(word)
        for button in self._buttons:
            self._matches.removeWidget(button)
            button.hide()
            button.deleteLater()
        self._buttons.clear()
        self._entry.hide()
        if not word:
            self._status.setText(INTRO)
            return
        entries = search_lexicon(self._conn, word, preferred_language=self._preferred)
        if not entries:
            self._status.setText(
                f'No Hebrew, Aramaic, or Greek word found for "{word}". Try a single word, its '
                'root form ("anoint" rather than "anointing"), or a Strong\'s number like H4899.'
            )
            return
        self._status.setText(
            f'Words the King James Version translates as "{word}":'
            if len(entries) > 1 else f'The original word for "{word}":'
        )
        for entry in entries:
            button = _MatchButton(entry)
            button.clicked.connect(lambda _checked=False, s=entry.strongs: self._select(s))
            self._matches.addWidget(button)
            self._buttons.append(button)
        self._select(entries[0].strongs)

    def _select(self, strongs: str) -> None:
        for button in self._buttons:
            button.setChecked(button.strongs == strongs)
        self._entry.show_entry(strongs)
        self._entry.show()
