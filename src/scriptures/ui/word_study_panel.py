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

Typed in, these are the words the KJV translates that way in general.
Right-clicked in a Bible or JST verse, the exact word behind it in that
verse comes first ("In John 3:16, "loved" translates:") - from the
word-by-word Strong's tags (scripts/import_strongs_tags.py,
data_access.get_word_strongs) - and the general matches after it.

A Book of Mormon name (data_access.get_bom_name, built by
scripts/build_bom_names.py) gets a card above any matches: its meaning,
labeled by confidence, with the scholars' proposals and sources. A date
("the first month", clicked in the text or typed here) gets a Hebrew
calendar card instead: the month's names, holy days, and the Book of
Mormon's events in it (hebrew_calendar.py).
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

from scriptures import hebrew_calendar
from scriptures.data_access import BomName, LexiconEntry, get_bom_name, get_lexicon_entry, search_lexicon
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
    "suggestions, not certainties. Hebrew in Lehi's day was also written without vowels - "
    "the vowel marks came only with the Masoretes, about AD 600-1000 - so a name's "
    "consonants are a surer guide than its vowels."
)
JAREDITE_NOTE = (
    "This is a Jaredite name. The Jaredites' language is older than the Nephites' and "
    "unknown today (Ether 1:33-35), so any meaning proposed for it is speculative."
)


class _BomNameCard(QFrame):
    """A Book of Mormon name: its confidence label, meaning, proposals
    with their proponents (Strong's numbers link to the lexicon entry),
    and sources."""

    def __init__(self, name: BomName, on_link, parent: QWidget | None = None):
        """`on_link` gets a Strong's number ("H7806") or "name:Mulek"."""
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
        kind = "Jaredite name" if name.people == "jaredite" else "Book of Mormon name"
        header = QLabel(f"{kind} · {label}{where}")
        header.setObjectName("resultPrimary")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setWordWrap(True)
        layout.addWidget(header)

        parts = []
        if name.meaning:
            parts.append(f"<p><b>Meaning:</b> {html.escape(name.meaning)}</p>")
        if name.tier == "biblical":
            parts.append("<p>The same name appears in the Bible - its Hebrew or Greek entry is below.</p>")
        if name.notes:
            notes = "".join(f"<li>{linked(note)}</li>" for note in name.notes)
            parts.append(f"<p><b>Study notes</b></p><ul>{notes}</ul>")
        if name.proposals:
            items = []
            for proposal in name.proposals:
                origin = linked(proposal.get("origin", ""))
                who = proposal.get("proponent")
                items.append(
                    f"<li>{html.escape(proposal['meaning'])} - <i>{origin}</i>"
                    + (f" - proposed by {html.escape(who)}" if who else "")
                    + "</li>"
                )
            parts.append("<p><b>Proposals</b> (most likely first):</p><ul>" + "".join(items) + "</ul>")
        if not name.tier:
            parts.append(
                "<p>No meaning has been recorded here for this name yet - the Onomasticon "
                "link below gathers what scholars have proposed.</p>"
            )
        body = QLabel("".join(parts))
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.linkActivated.connect(on_link)
        layout.addWidget(body)

        if name.related:
            groups = []
            for element, gloss, others in name.related:
                links = ", ".join(
                    f'<a href="name:{html.escape(other)}">{html.escape(other)}</a>' for other in others
                )
                groups.append(f"<li><i>{html.escape(element)}</i> ({linked(gloss)}): {links}</li>")
            related = QLabel(
                "<p><b>Related names</b> - sharing consonants or an element, which may mean a "
                f"shared root:</p><ul>{''.join(groups)}</ul>"
            )
            related.setWordWrap(True)
            related.setTextFormat(Qt.TextFormat.RichText)
            related.linkActivated.connect(on_link)
            layout.addWidget(related)

        if name.tier in ("hebrew_root", "proposed", "unknown"):
            note = QLabel(JAREDITE_NOTE if name.people == "jaredite" else LANGUAGE_NOTE)
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


class _MonthCard(QFrame):
    """A month of Israel's calendar (hebrew_calendar.py): its names,
    season, holy days, and the Book of Mormon's events in it - with the
    clicked day placed among the holy days. Links: Strong's numbers, and
    "month:N:0" to step to the neighboring months."""

    def __init__(self, number: int, day: int | None, on_link, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("nameCard")
        month = hebrew_calendar.month(number)
        ordinal = hebrew_calendar.ORDINALS[number - 1]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel(f"The {ordinal.capitalize()} Month")
        title.setObjectName("lexiconHebrew")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)
        header = QLabel(f"Hebrew calendar · {month.season}")
        header.setObjectName("resultPrimary")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setWordWrap(True)
        layout.addWidget(header)

        parts = []
        if day is not None:
            context = hebrew_calendar.day_context(number, day)
            parts.append(
                f"<p><b>The {hebrew_calendar.ORDINALS[day - 1]} day of the month.</b> {html.escape(context)}</p>"
            )
        if month.early_name:
            parts.append(f"<p><b>Name before the exile:</b> {linked(month.early_name)}</p>")
        parts.append(f"<p><b>Name after the exile:</b> {linked(month.later_name)}</p>")

        def holy_items(after_lehi: bool) -> str:
            items = []
            for holy in month.days:
                if holy.after_lehi != after_lehi:
                    continue
                when = f"<b>{html.escape(holy.days)}</b> - " if holy.days else ""
                items.append(f"<li>{when}<b>{linked(holy.name)}</b>: {linked(holy.about)}</li>")
            return "".join(items)

        known = holy_items(False)
        parts.append(
            f"<p><b>In the law of Moses</b> (known to Lehi):</p><ul>{known}</ul>" if known
            else "<p><b>In the law of Moses:</b> no holy day falls in this month.</p>"
        )
        later = holy_items(True)
        if later:
            parts.append(f"<p><b>Later</b> - after Lehi left Jerusalem:</p><ul>{later}</ul>")
        events = [d for d in hebrew_calendar.BOM_DATES if d.month == number]
        if events:
            items = "".join(
                f"<li><b>{html.escape(e.reference)}</b>"
                f"{f' (day {e.day})' if e.day else ''}: {html.escape(e.event)}</li>"
                for e in events
            )
            parts.append(f"<p><b>In the Book of Mormon:</b></p><ul>{items}</ul>")
        previous = 12 if number == 1 else number - 1
        following = 1 if number == 12 else number + 1
        parts.append(
            f'<p><a href="month:{previous}:0">← The {hebrew_calendar.ORDINALS[previous - 1]} month</a>'
            f' · <a href="month:{following}:0">The {hebrew_calendar.ORDINALS[following - 1]} month →</a></p>'
        )
        body = QLabel("".join(parts))
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.linkActivated.connect(on_link)
        layout.addWidget(body)

        note = QLabel(hebrew_calendar.CALENDAR_NOTE)
        note.setObjectName("resultSecondary")
        note.setWordWrap(True)
        layout.addWidget(note)


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
        # The Strong's number(s) behind a right-clicked word in its verse.
        self._exact: list[str] = []
        self._exact_reference: str | None = None

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
        self._name_card: _BomNameCard | _MonthCard | None = None

        self._matches = QVBoxLayout()
        self._matches.setSpacing(6)
        layout.addLayout(self._matches)

        self._entry = LexiconEntryView(conn)
        self._entry.hide()
        layout.addWidget(self._entry)
        layout.addStretch(1)

    def look_up(self, word: str, exact: list[str] | None = None, reference: str | None = None) -> None:
        """Look up a word; `exact` - the Strong's number(s) behind it in the
        verse `reference` it was right-clicked in - come first."""
        self._exact = [s for s in (exact or []) if get_lexicon_entry(self._conn, s) is not None]
        self._exact_reference = reference
        word = " ".join(word.split())
        dates = hebrew_calendar.find_dates(word)
        if dates and dates[0][0] <= 4 and dates[0][1] == len(word):  # the whole entry is a date
            self.show_month(dates[0][2], dates[0][3], text=word)
            return
        self._clear(word)
        if not word:
            self._status.setText(INTRO)
            return
        self._look_up_word(word)

    def show_month(self, number: int, day: int | None = None, *, text: str | None = None) -> None:
        """The calendar card for a month (and day) of Israel's calendar."""
        ordinal = hebrew_calendar.ORDINALS
        self._clear(text or (f"{ordinal[day - 1]} day of the {ordinal[number - 1]} month" if day
                             else f"{ordinal[number - 1]} month"))
        self._status.hide()
        self._name_card = _MonthCard(number, day, self._follow_card_link)
        self._name_slot.addWidget(self._name_card)

    def _clear(self, text: str) -> None:
        self._input.setText(text)
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

    def _look_up_word(self, word: str) -> None:
        name = get_bom_name(self._conn, word)
        if name is not None:
            self._name_card = _BomNameCard(name, self._follow_card_link)
            self._name_slot.addWidget(self._name_card)
        exact = self._exact
        entries = search_lexicon(self._conn, word, preferred_language=self._preferred)
        if exact:
            # The verse's own word(s) first, then the general matches.
            entries = [get_lexicon_entry(self._conn, s) for s in exact] + [
                e for e in entries if e.strongs not in exact
            ]
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
        if exact:
            self._status.setText(
                f'In {self._exact_reference}, "{word}" translates the first word below'
                + (" (and the next)" if len(exact) == 2 else "")
                + (". Other words the King James Version translates that way follow." if len(entries) > len(exact) else ".")
            )
        else:
            self._status.setText(
                f'Words the King James Version translates as "{word}":'
                if len(entries) > 1 else f'The original word for "{word}":'
            )
        for index, entry in enumerate(entries):
            button = _MatchButton(entry)
            if index < len(exact):
                button.setText(f"In this verse · {button.text()}")
            button.clicked.connect(lambda _checked=False, s=entry.strongs: self._select(s))
            self._matches.addWidget(button)
            self._buttons.append(button)
        self._select(entries[0].strongs)

    def _follow_card_link(self, target: str) -> None:
        """A name card link: a related name opens its own card; a Strong's
        number shows that entry below."""
        if target.startswith("name:"):
            self.look_up(target.removeprefix("name:"))
        elif target.startswith("month:"):
            month, _, day = target.removeprefix("month:").partition(":")
            self.show_month(int(month), int(day) or None)
        else:
            self._show_strongs(target)

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
