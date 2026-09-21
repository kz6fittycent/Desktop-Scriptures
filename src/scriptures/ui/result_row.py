"""A single clickable search result row - shared between SearchView's own
sections and AiConversationSection's, so both render matches identically."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


def truncate_text(text: str, limit: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class ResultRow(QFrame):
    """A single clickable search result: a bold primary line (usually a
    reference) and an optional secondary line (a snippet)."""

    clicked = Signal(int)

    def __init__(
        self, chapter_id: int, primary_text: str, secondary_text: str = "", parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.chapter_id = chapter_id
        self.setObjectName("resultRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        primary = QLabel(primary_text)
        primary.setObjectName("resultPrimary")
        primary.setWordWrap(True)
        layout.addWidget(primary)

        if secondary_text:
            secondary = QLabel(secondary_text)
            secondary.setObjectName("resultSecondary")
            secondary.setWordWrap(True)
            layout.addWidget(secondary)

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.chapter_id)
        super().mousePressEvent(event)
