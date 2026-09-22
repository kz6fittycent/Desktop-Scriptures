"""The landing page's Inspirational Message box (see main_window.py's
show_volumes) - off by default, matching Church News' and Come Follow
Me's own opt-in precedent: shows a "click to enable" prompt until the
user turns it on (via the box itself, or View -> Show Inspirational
Message), then fetches and shows the message currently featured on
churchofjesuschrist.org's own homepage.

Built the same way as the other landing-page boxes - a single rich-text
QLabel styled by the shared "sotdBanner, newsBox, cfmBox, inspirationBox"
rule in theme.py - so all four are pixel-for-pixel the same size and use
the same (not muted/gray) text color.
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QWidget

from scriptures.inspiration import InspirationalMessage, InspirationFetcher
from scriptures.ui.result_row import truncate_text

# Keeps the box roughly the same height as its siblings (a scripture verse,
# a CFM scripture block) - these featured quotes run noticeably longer.
_QUOTE_TRUNCATE_LIMIT = 160


class InspirationBox(QLabel):
    """`enable_requested` fires when a disabled box is clicked, so
    MainWindow can flip the setting on and rebuild the landing page -
    this widget never touches settings itself, it just renders whichever
    state (enabled or not) it's constructed with and reports the click."""

    enable_requested = Signal()

    def __init__(self, enabled: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("inspirationBox")
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._enabled = enabled
        self._url: str | None = None

        # Kept alive for the fetch's duration by this attribute, same
        # reasoning as ai_conversation.py's own _asker reference.
        self._fetcher: InspirationFetcher | None = None
        if enabled:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setText("<b>Inspirational Message:</b><br>Loading...")
            self._fetcher = InspirationFetcher(parent=self)
            self._fetcher.succeeded.connect(self._on_succeeded)
            self._fetcher.failed.connect(self._on_failed)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip("Click to turn on the Inspirational Message")
            self.setText(
                "<b>Inspirational Message:</b><br>Off - click to show a featured message here."
            )

    def _on_succeeded(self, message: InspirationalMessage) -> None:
        self._url = message.link
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open this message at churchofjesuschrist.org")
        quote = truncate_text(message.quote, limit=_QUOTE_TRUNCATE_LIMIT)
        self.setText(
            "<b>Inspirational Message:</b><br>"
            f"“{escape(quote)}” - {escape(message.author)}"
        )

    def _on_failed(self, message: str) -> None:  # noqa: ARG002 (kept for parity/debuggability)
        self.setText("<b>Inspirational Message:</b><br>Couldn't load a featured message.")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            if self._url:
                QDesktopServices.openUrl(QUrl(self._url))
            elif not self._enabled:
                self.enable_requested.emit()
        super().mousePressEvent(event)
