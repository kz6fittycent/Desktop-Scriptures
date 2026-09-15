"""Breadcrumb navigation bar.

Shows the current drill-down path (e.g. "Holy Bible > Old Testament >
Genesis") as clickable segments, so the user can jump back to any
earlier level in one click instead of repeatedly going back.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class _LinkLabel(QLabel):
    """A clickable QLabel styled as a link.

    QPushButton with setFlat(True) is deliberately avoided here: under
    Fusion/Breeze it double-paints its text (a "sunken" shadow duplicate)
    when combined with a stylesheet, producing a visible ghost glyph after
    the label - the same reason Card (card_grid.py) uses a plain frame with
    mousePressEvent instead of a button.
    """

    clicked = Signal()

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("breadcrumbLink")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


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
                # hide() immediately invalidates the region it occupied, so
                # Qt repaints over it - deleteLater() alone defers that and
                # can leave stale pixels behind when the new label at the
                # same spot is narrower than the one it replaced (e.g. bold
                # "current" text -> regular-weight "link" text).
                item.widget().hide()
                item.widget().deleteLater()

        for i, label in enumerate(labels):
            if i > 0:
                sep = QLabel(">")
                sep.setObjectName("breadcrumbSep")
                self._layout.addWidget(sep)

            is_last = i == len(labels) - 1
            if is_last:
                current = QLabel(label)
                current.setObjectName("breadcrumbCurrent")
                self._layout.addWidget(current)
            else:
                link = _LinkLabel(label)
                link.clicked.connect(lambda idx=i: self.segment_clicked.emit(idx))
                self._layout.addWidget(link)
