"""A Hebrew/Aramaic lexicon entry, in full (see lexicon_entries in
schema.sql and scripts/import_hebrew_lexicon.py): the word in Hebrew,
its transliteration and pronunciation, meaning, Strong's definition,
derivation, and how the King James Version translates it.

Other entries a derivation names ("from H4886") are links - clicking one
shows that entry in the same dialog, with Back to return. The sources'
required credit sits at the bottom, linked, like the Help menu's.
"""

from __future__ import annotations

import html
import re
import sqlite3

from PySide6.QtCore import Qt
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


class LexiconDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, strongs: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._conn = conn
        self._history: list[str] = []
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
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

        credit = QLabel(LEXICON_CREDIT)
        credit.setObjectName("resultSecondary")
        credit.setWordWrap(True)
        credit.setTextFormat(Qt.TextFormat.RichText)
        credit.setOpenExternalLinks(True)
        layout.addWidget(credit)

        buttons = QHBoxLayout()
        self._back = QPushButton("Back")
        self._back.setAutoDefault(False)
        self._back.clicked.connect(self._go_back)
        buttons.addWidget(self._back)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._show(strongs)

    def _show(self, strongs: str) -> None:
        entry = get_lexicon_entry(self._conn, strongs)
        if entry is None:
            self._heading.setText(f"{strongs} isn't in the lexicon.")
            self._body.clear()
            self._hebrew.clear()
        else:
            self._render(entry)
        self._current = strongs
        self._back.setVisible(bool(self._history))

    def _render(self, entry: LexiconEntry) -> None:
        language = "Aramaic" if entry.language == "aramaic" else "Hebrew"
        self.setWindowTitle(f"{language} word - Strong's {entry.strongs}")
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

    def _follow(self, strongs: str) -> None:
        self._history.append(self._current)
        self._show(strongs)

    def _go_back(self) -> None:
        if self._history:
            self._show(self._history.pop())
