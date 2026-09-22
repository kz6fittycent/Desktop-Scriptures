"""The landing page's Come Follow Me box (see main_window.py's
show_volumes) - off by default, matching Church News' and AI
Integration's own opt-in precedent: shows a "click to enable" prompt
until the user turns it on (via the box itself, or View -> Show Come
Follow Me Helper), then fetches and shows this week's lesson from
cfm.py's manual page.

Built the same way as the other two landing-page boxes beside it - a
single rich-text QLabel styled by the shared "sotdBanner, newsBox,
cfmBox" rule in theme.py - so all three are pixel-for-pixel the same
size and use the same (not muted/gray) text color.
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QWidget

from scriptures.cfm import CfmFetcher, CfmLesson


class CfmBox(QLabel):
    """`enable_requested` fires when a disabled box is clicked, so
    MainWindow can flip the setting on and rebuild the landing page -
    this widget never touches settings itself, it just renders whichever
    state (enabled or not) it's constructed with and reports the click."""

    enable_requested = Signal()

    def __init__(self, enabled: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("cfmBox")
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._enabled = enabled
        self._url: str | None = None

        # Kept alive for the fetch's duration by this attribute, same
        # reasoning as ai_conversation.py's own _asker reference.
        self._fetcher: CfmFetcher | None = None
        if enabled:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setText("<b>Come Follow Me:</b><br>Loading this week's lesson...")
            self._fetcher = CfmFetcher(parent=self)
            self._fetcher.succeeded.connect(self._on_succeeded)
            self._fetcher.failed.connect(self._on_failed)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip("Click to turn on the Come Follow Me helper")
            self.setText("<b>Come Follow Me:</b><br>Off - click to show this week's lesson here.")

    def _on_succeeded(self, lesson: CfmLesson) -> None:
        self._url = lesson.link
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open this week's lesson at churchofjesuschrist.org")
        self.setText(
            f"<b>Come Follow Me: {escape(lesson.date_label)}</b><br>"
            f"{escape(lesson.scripture_block)}"
        )

    def _on_failed(self, message: str) -> None:  # noqa: ARG002 (kept for parity/debuggability)
        self.setText("<b>Come Follow Me:</b><br>Couldn't load this week's lesson.")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            if self._url:
                QDesktopServices.openUrl(QUrl(self._url))
            elif not self._enabled:
                self.enable_requested.emit()
        super().mousePressEvent(event)
