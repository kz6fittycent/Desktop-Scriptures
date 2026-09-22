"""The landing page's Church News box (see main_window.py's
show_volumes) - off by default, matching AI Integration's own opt-in
precedent: shows a "click to enable" prompt until the user turns it on
(via the box itself, or View -> Show Church News Headline), then fetches
and shows the single latest headline from church_news.py's RSS feed.

Rebuilt fresh every time the landing page is (re)built, so revisiting it
mid-session re-fetches rather than caching a result - simple, and the
feed itself only turns over a handful of times a day anyway.
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from scriptures.church_news import ChurchNewsFetcher, NewsHeadline


class ChurchNewsBox(QFrame):
    """`enable_requested` fires when a disabled box is clicked, so
    MainWindow can flip the setting on and rebuild the landing page -
    this widget never touches settings itself, it just renders whichever
    state (enabled or not) it's constructed with and reports the click."""

    enable_requested = Signal()

    def __init__(self, enabled: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("resultRow")
        self._enabled = enabled
        self._url: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        header = QLabel("Church News")
        header.setObjectName("panelSectionTitle")
        layout.addWidget(header)

        self._body = QLabel()
        self._body.setObjectName("resultSecondary")
        self._body.setWordWrap(True)
        layout.addWidget(self._body)

        # Kept alive for the fetch's duration by this attribute, same
        # reasoning as ai_conversation.py's own _asker reference.
        self._fetcher: ChurchNewsFetcher | None = None
        if enabled:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._body.setText("Loading the latest headline...")
            self._fetcher = ChurchNewsFetcher(parent=self)
            self._fetcher.succeeded.connect(self._on_succeeded)
            self._fetcher.failed.connect(self._on_failed)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip("Click to turn on the Church News headline")
            self._body.setText("Off - click to show the latest headline here.")

    def _on_succeeded(self, headline: NewsHeadline) -> None:
        self._url = headline.link
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open this story at thechurchnews.com")
        text = escape(headline.title)
        if headline.byline:
            text += f'<br><span style="font-size: 11px;">{escape(headline.byline)}</span>'
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setText(text)

    def _on_failed(self, message: str) -> None:  # noqa: ARG002 (kept for parity/debuggability)
        self._body.setText("Couldn't load the latest headline.")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            if self._url:
                QDesktopServices.openUrl(QUrl(self._url))
            elif not self._enabled:
                self.enable_requested.emit()
        super().mousePressEvent(event)
