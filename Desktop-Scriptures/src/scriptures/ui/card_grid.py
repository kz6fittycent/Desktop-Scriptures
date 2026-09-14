"""Reusable card and card-grid widgets.

Every navigation level (volumes, testaments, books, chapters) is the same
visual pattern - a wrapping grid of clickable cards - so it's implemented
once here and reused everywhere, per the UX sketches.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

CARD_MIN_WIDTH = 160
CARD_MIN_HEIGHT = 100


class Card(QFrame):
    """A single clickable card. Emits `clicked` with the item_id it represents."""

    clicked = Signal(object)

    def __init__(self, item_id: object, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.item_id = item_id
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(CARD_MIN_WIDTH, CARD_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        text = QLabel(label)
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text)

        # Basic styling now; a real theme/QSS system replaces this later.
        self.setStyleSheet(
            "#card {"
            "  background-color: #6E96C4;"
            "  border-radius: 6px;"
            "}"
            "#card:hover {"
            "  background-color: #5C82AE;"
            "}"
        )

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item_id)
        super().mousePressEvent(event)


class CardGridWidget(QWidget):
    """A titled, scrollable, wrapping grid of Cards.

    `items` is a list of (item_id, label) tuples. Emits `card_clicked(item_id)`
    when any card is clicked.
    """

    card_clicked = Signal(object)

    def __init__(
        self,
        title: str,
        items: list[tuple[object, str]],
        columns: int = 4,
        parent: QWidget | None = None,
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
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(12)

        for i, (item_id, label) in enumerate(items):
            row, col = divmod(i, columns)
            card = Card(item_id, label)
            card.clicked.connect(self.card_clicked)
            grid.addWidget(card, row, col)

        scroll.setWidget(grid_container)
        outer.addWidget(scroll)
