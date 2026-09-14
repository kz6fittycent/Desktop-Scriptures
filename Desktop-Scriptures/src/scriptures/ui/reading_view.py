"""Chapter reading view.

Minimal for this build session: displays verse number + text for every
verse in a chapter, scrollable. Font/size/color-scheme controls, tagging,
highlighting, and notes attach to this screen in a later pass - the data
layer already supports all of them, this just isn't wired up yet.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from scriptures.data_access import Verse


class ReadingView(QWidget):
    def __init__(
        self, title: str, verses: list[Verse], parent: QWidget | None = None
    ):
        super().__init__(parent)

        outer = QVBoxLayout(self)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; padding: 12px;"
            "border: 1px solid #333; margin: 8px;"
        )
        outer.addWidget(title_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)

        for verse in verses:
            line = QLabel(f"<b>{verse.verse_number}</b>&nbsp;&nbsp;{verse.text}")
            line.setWordWrap(True)
            line.setTextFormat(Qt.TextFormat.RichText)
            content_layout.addWidget(line)

        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
