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

A Book of Mormon name (data_access.get_bom_name, built by
scripts/build_bom_names.py) gets a card above any matches: its meaning,
labeled by confidence, with the scholars' proposals and sources.
"""

from __future__ import annotations

import html
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

from scriptures.data_access import BomName, LexiconEntry, get_bom_name, search_lexicon
from scriptures.ui.lexicon_dialog import LexiconEntryView, language_name, linked

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


TIER_LABELS = {
    "defined": "Defined in the Book of Mormon",
    "biblical": "Biblical name",
    "hebrew_root": "Hebrew root",
    "proposed": "Proposed meaning",
    "unknown": "Meaning unknown",
}

# Shown with every meaning the text doesn't itself give or the Bible
# doesn't share - see scripts/build_bom_names.py.
LANGUAGE_NOTE = (
    'Moroni wrote that the Nephites altered their language "according to our manner of '
    'speech" (Mormon 9:32-34), so meanings proposed for Book of Mormon names are '
    "suggestions, not certainties."
)


class _BomNameCard(QFrame):
    """A Book of Mormon name: its confidence label, meaning, proposals
    with their proponents (Strong's numbers link to the lexicon entry),
    and sources."""

    def __init__(self, name: BomName, on_strongs, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("nameCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel(name.name)
        title.setObjectName("lexiconHebrew")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        label = TIER_LABELS.get(name.tier, "Not yet researched")
        where = f" · first mentioned in {name.reference}" if name.reference else ""
        header = QLabel(f"Book of Mormon name · {label}{where}")
        header.setObjectName("resultPrimary")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setWordWrap(True)
        layout.addWidget(header)

        parts = []
        if name.meaning:
            parts.append(f"<p><b>Meaning:</b> {html.escape(name.meaning)}</p>")
        if name.tier == "biblical":
            parts.append("<p>The same name appears in the Bible - its Hebrew or Greek entry is below.</p>")
        if name.proposals:
            items = []
            for proposal in name.proposals:
                origin = linked(proposal.get("origin", ""))
                who = proposal.get("proponent")
                items.append(
                    f"<li>\u201c{html.escape(proposal['meaning'])}\u201d - {origin}"
                    + (f" - proposed by {html.escape(who)}" if who else "")
                    + "</li>"
                )
            parts.append("<p><b>Proposals</b> (most likely first):</p><ul>" + "".join(items) + "</ul>")
        if not name.tier:
            parts.append("<p>No meaning has been recorded for this name yet.</p>")
        body = QLabel("".join(parts))
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.linkActivated.connect(on_strongs)
        layout.addWidget(body)

        if name.tier in ("hebrew_root", "proposed", "unknown"):
            note = QLabel(LANGUAGE_NOTE)
            note.setObjectName("resultSecondary")
            note.setWordWrap(True)
            layout.addWidget(note)
        if name.sources:
            links = " · ".join(
                f'<a href="{html.escape(url)}">{html.escape(title)}</a>' for title, url in name.sources
            )
            sources = QLabel(f"Sources: {links}")
            sources.setObjectName("resultSecondary")
            sources.setWordWrap(True)
            sources.setTextFormat(Qt.TextFormat.RichText)
            sources.setOpenExternalLinks(True)
            layout.addWidget(sources)


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

        self._name_slot = QVBoxLayout()
        layout.addLayout(self._name_slot)
        self._name_card: _BomNameCard | None = None

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
        self._status.show()
        if self._name_card is not None:
            self._name_slot.removeWidget(self._name_card)
            self._name_card.hide()
            self._name_card.deleteLater()
            self._name_card = None
        if not word:
            self._status.setText(INTRO)
            return
        name = get_bom_name(self._conn, word)
        if name is not None:
            self._name_card = _BomNameCard(name, self._show_strongs)
            self._name_slot.addWidget(self._name_card)
        entries = search_lexicon(self._conn, word, preferred_language=self._preferred)
        if name is not None and name.tier != "biblical":
            # A Book of Mormon-only name's lexicon "matches" would only be
            # words sharing letters - its own Strong's links are in the card.
            entries = [e for e in entries if e.strongs in name.strongs]
        if not entries and name is not None:
            self._status.hide()
            return
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

    def _show_strongs(self, strongs: str) -> None:
        """A Strong's link in a name card: show that entry below."""
        for button in self._buttons:
            button.setChecked(False)
        self._entry.show_entry(strongs)
        self._entry.show()

    def _select(self, strongs: str) -> None:
        for button in self._buttons:
            button.setChecked(button.strongs == strongs)
        self._entry.show_entry(strongs)
        self._entry.show()
