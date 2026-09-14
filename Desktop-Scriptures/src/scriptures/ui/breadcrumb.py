"""Breadcrumb navigation bar.

Shows the current drill-down path (e.g. "Holy Bible > Old Testament >
Genesis") as clickable segments, so the user can jump back to any
earlier level in one click instead of repeatedly going back.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class BreadcrumbBar(QWidget):
    """Emits `segment_clicked(index)` when a breadcrumb segment is clicked,
    where index is the position of that segment in the path (0 = root).
    """

    segment_clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 6, 12, 6)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.set_path([])

    def set_path(self, labels: list[str]) -> None:
        """Rebuild the breadcrumb from a list of segment labels, root first."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, label in enumerate(labels):
            if i > 0:
                sep = QLabel(">")
                sep.setStyleSheet("color: #888;")
                self._layout.addWidget(sep)

            is_last = i == len(labels) - 1
            if is_last:
                current = QLabel(label)
                current.setStyleSheet("font-weight: bold;")
                self._layout.addWidget(current)
            else:
                btn = QPushButton(label)
                btn.setFlat(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    "QPushButton { border: none; color: #2A5DB0; text-decoration: underline; }"
                )
                btn.clicked.connect(lambda checked=False, idx=i: self.segment_clicked.emit(idx))
                self._layout.addWidget(btn)
