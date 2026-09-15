"""TagChip: a small rounded pill showing a tag name with a remove button.

Shared by the chapter-level and per-verse tag rows in chapter_panel.py.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class TagChip(QWidget):
    removed = Signal(int)

    def __init__(self, tag_id: int, name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.tag_id = tag_id
        self.setObjectName("tagChip")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 6, 4)
        layout.setSpacing(6)

        label = QLabel(name)
        layout.addWidget(label)

        close_btn = QPushButton("×")
        close_btn.setObjectName("tagChipClose")
        close_btn.setFixedSize(16, 16)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(lambda: self.removed.emit(self.tag_id))
        layout.addWidget(close_btn)
