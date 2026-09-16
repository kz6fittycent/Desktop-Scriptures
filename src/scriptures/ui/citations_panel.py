"""Citations tab: which verses in the current chapter are cited in
General Conference talks (pilot-scoped to the Scripture of the Day pool -
see scripts/harvest_citations.py and scriptures/citations.py; most
chapters have no data at all, which is the normal case, not an error).

Each cited verse is a header row ("Verse 15 - cited 3 times") that
expands/collapses inline (accordion-style) to show its citing talks,
rather than opening a popup - lets more than one be open and compared at
once, and keeps the whole feature inside its own tab instead of adding UI
to the verse rows themselves.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from scriptures.citations import Citation, get_citations
from scriptures.data_access import Verse


class _TalkRow(QFrame):
    """One citing talk inside an expanded verse entry: title + "speaker ·
    date", clickable through to its churchofjesuschrist.org page. Reuses
    the search view's resultRow/resultPrimary/resultSecondary styling."""

    def __init__(self, citation: Citation, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("resultRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open this talk at churchofjesuschrist.org")
        self._url = citation.url

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        title = QLabel(citation.talk_title)
        title.setObjectName("resultPrimary")
        title.setWordWrap(True)
        layout.addWidget(title)

        subtitle = QLabel(f"{citation.speaker} · {citation.date}")
        subtitle.setObjectName("resultSecondary")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mousePressEvent(event)


class _VerseCitationEntry(QFrame):
    """One cited verse: a clickable header that expands/collapses its talk
    list inline. Collapsed by default - a heavily-cited verse's full list
    would otherwise push everything else in the tab out of view."""

    def __init__(self, verse: Verse, citations: list[Citation], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sidePanelBox")
        self._expanded = False
        self._verse_number = verse.verse_number
        self._count = len(citations)

        layout = QVBoxLayout(self)

        self._header = QPushButton()
        self._header.setObjectName("citationAccordionHeader")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.clicked.connect(self._toggle)
        layout.addWidget(self._header)

        self._talks_container = QWidget()
        talks_layout = QVBoxLayout(self._talks_container)
        talks_layout.setContentsMargins(0, 8, 0, 0)
        talks_layout.setSpacing(6)
        for citation in citations:
            talks_layout.addWidget(_TalkRow(citation))
        self._talks_container.setVisible(False)
        layout.addWidget(self._talks_container)

        self._update_header_text()

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._talks_container.setVisible(self._expanded)
        self._update_header_text()

    def _update_header_text(self) -> None:
        arrow = "▾" if self._expanded else "▸"
        plural = "s" if self._count != 1 else ""
        self._header.setText(f"{arrow} Verse {self._verse_number} — cited {self._count} time{plural}")


class CitationsPanel(QWidget):
    """Scrollable list of the current chapter's cited verses, or an
    empty-state message if none - most chapters, since the pool is only
    100 verses out of the full ~41,995."""

    def __init__(self, verses: list[Verse], parent: QWidget | None = None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(12)

        cited_count = 0
        for verse in verses:
            citations = get_citations(verse.reference)
            if citations:
                cited_count += 1
                content_layout.addWidget(_VerseCitationEntry(verse, citations))
        self.cited_verse_count = cited_count

        if cited_count == 0:
            empty = QLabel("No verses in this chapter are cited in Conference talks.")
            empty.setObjectName("resultSecondary")
            empty.setWordWrap(True)
            content_layout.addWidget(empty)

        content_layout.addStretch(1)
        scroll.setWidget(content)
