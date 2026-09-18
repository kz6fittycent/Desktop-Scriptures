"""Topical Guide: browse major gospel topics with supporting scripture
and General Conference talk references.

This is Desktop Scriptures' own correlation, built by
scripts/build_topical_guide.py from data already in this app (a keyword
search over the local scripture text, and the same citation-index
harvest citations_panel.py uses) - never a transcription of the Church's
own copyrighted Topical Guide, and never talk text, only its metadata.

Two views, both reached from the landing page's synthetic "Topical
Guide" card (see main_window.py's TOPICAL_GUIDE_ID):
- A topic list, reusing CardGridWidget exactly like every other
  navigation level (wired up in main_window.py directly - there's no
  dedicated list widget here, unlike the detail view below).
- TopicDetailView: one topic's description, then its supporting
  scriptures (clickable through to the reading view, same interaction as
  a search result) and citing talks (clickable out to
  churchofjesuschrist.org, same interaction as the Citations tab).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from scriptures.data_access import Topic, TopicTalk, Verse


def _truncate(text: str, limit: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class _ScriptureRow(QFrame):
    """One supporting-scripture reference: reference + a short snippet,
    clickable through to its chapter in the reading view."""

    clicked = Signal(int)

    def __init__(self, verse: Verse, parent: QWidget | None = None):
        super().__init__(parent)
        self._chapter_id = verse.chapter_id
        self.setObjectName("resultRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        primary = QLabel(verse.reference)
        primary.setObjectName("resultPrimary")
        primary.setWordWrap(True)
        layout.addWidget(primary)

        secondary = QLabel(_truncate(verse.text))
        secondary.setObjectName("resultSecondary")
        secondary.setWordWrap(True)
        layout.addWidget(secondary)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._chapter_id)
        super().mousePressEvent(event)


class _TalkRow(QFrame):
    """One citing talk: title + "speaker · date", clickable out to
    churchofjesuschrist.org - same interaction as the Citations tab's
    talk rows (a separate small copy, not a shared import, since that
    widget takes a citations.Citation, a differently-sourced dataclass
    with the same shape)."""

    def __init__(self, talk: TopicTalk, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("resultRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open this talk at churchofjesuschrist.org")
        self._url = talk.url

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        title = QLabel(talk.talk_title)
        title.setObjectName("resultPrimary")
        title.setWordWrap(True)
        layout.addWidget(title)

        subtitle = QLabel(f"{talk.speaker} · {talk.date}")
        subtitle.setObjectName("resultSecondary")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mousePressEvent(event)


class TopicDetailView(QWidget):
    """A topic's description, its supporting scriptures, and its citing
    talks. `scripture_selected` mirrors SearchView.result_selected -
    MainWindow already knows how to resolve a chapter id into a full
    navigation path, so a scripture row's click reuses that handler."""

    scripture_selected = Signal(int)

    def __init__(
        self,
        topic: Topic,
        verses: list[Verse],
        talks: list[TopicTalk],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        outer = QVBoxLayout(self)

        title = QLabel(topic.name)
        title.setObjectName("sectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)

        description = QLabel(topic.description)
        description.setObjectName("resultSecondary")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(description)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 12, 4, 0)
        content_layout.setSpacing(12)

        if verses:
            header = QLabel("Scriptures")
            header.setObjectName("searchSectionHeader")
            content_layout.addWidget(header)
            for verse in verses:
                row = _ScriptureRow(verse)
                row.clicked.connect(self.scripture_selected)
                content_layout.addWidget(row)

        if talks:
            header = QLabel("Talks")
            header.setObjectName("searchSectionHeader")
            content_layout.addWidget(header)
            for talk in talks:
                content_layout.addWidget(_TalkRow(talk))

        if not verses and not talks:
            empty = QLabel("No references yet for this topic.")
            empty.setObjectName("resultSecondary")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            content_layout.addWidget(empty)

        content_layout.addStretch(1)
        scroll.setWidget(content)
