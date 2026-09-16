"""Popup listing the General Conference talks that cite a verse (pilot
feature - only verses in the Scripture of the Day pool have data; see
scripts/harvest_citations.py and scriptures/citations.py).

Only ever shows metadata (talk title, speaker, date) pulled from the
local JSON - never talk text. Clicking a talk opens its
churchofjesuschrist.org page in the user's default browser rather than
showing anything from the talk inside the app, same as the About
dialog's external links.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from scriptures.citations import Citation


class _CitationRow(QFrame):
    """One citing talk: title + "speaker · date", clickable through to
    its churchofjesuschrist.org page. Reuses the search view's resultRow/
    resultPrimary/resultSecondary styling rather than inventing new QSS."""

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


class CitationsDialog(QDialog):
    def __init__(
        self, reference: str, citations: list[Citation], parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Citations — {reference}")
        self.setMinimumSize(420, 480)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        count = len(citations)
        header = QLabel(
            f"{reference} is cited in {count} General Conference "
            f"talk{'s' if count != 1 else ''}:"
        )
        header.setWordWrap(True)
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(6)
        for citation in citations:
            content_layout.addWidget(_CitationRow(citation))
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
