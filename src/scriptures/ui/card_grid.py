"""Reusable card and card-grid widgets.

Every navigation level (volumes, testaments, books, chapters) is the same
visual pattern - a wrapping grid of clickable cards - so it's implemented
once here and reused everywhere, per the UX sketches.

Cards are fixed-size squares that don't stretch with the window; FlowLayout
wraps them onto as many rows as the available width allows, like a
Material Design card gallery, instead of a fixed N-column grid that would
leave the squares stretched into rectangles.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# FlowLayout's own margin (below) inset the card grid an extra 12px past
# whatever CardGridWidget's outer layout already gives every other direct
# child (title, banner) - without matching that same inset, a banner
# widget's edges land 12px outside where the row of cards beneath it
# actually starts/ends.
GRID_MARGIN = 12

CARD_SIZE = 128

GOLDEN_RATIO = 1.618
# The landing page has room to spare with only 4-5 cards on it, unlike the
# book/chapter grids (which can hold dozens) - sized up from CARD_SIZE by
# the golden ratio so it visibly fills that space rather than floating
# alone in it.
LANDING_CARD_SIZE = round(CARD_SIZE * GOLDEN_RATIO)


class FlowLayout(QLayout):
    """Left-to-right, top-to-bottom wrapping layout (Qt's standard "flow
    layout" recipe) - lets a row hold as many fixed-size cards as fit the
    current width, re-wrapping live as the window resizes.
    """

    def __init__(self, parent: QWidget | None = None, margin: int = 0, spacing: int = 16):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items: list = []

    def addItem(self, item) -> None:  # noqa: N802 (Qt override)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 (Qt override)
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802 (Qt override)
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientations:  # noqa: N802 (Qt override)
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt override)
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 (Qt override)
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 (Qt override)
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """Two passes: first group items into rows (as many as fit the
        width), then - only when actually positioning, not measuring -
        place each row's items centered left-to-right within the width.
        Centering top-to-bottom is handled by the caller (CardGridWidget
        sandwiches the container this layout belongs to between two
        stretches), not here.
        """
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        spacing = self.spacing()

        rows: list[tuple[list, int, int]] = []  # (items, row_width, row_height)
        current_row: list = []
        row_width = 0
        row_height = 0

        for item in self._items:
            item_size = item.sizeHint()
            needed = item_size.width() if not current_row else row_width + spacing + item_size.width()
            if needed > effective.width() and current_row:
                rows.append((current_row, row_width, row_height))
                current_row = []
                row_width = 0
                row_height = 0
                needed = item_size.width()

            current_row.append(item)
            row_width = needed
            row_height = max(row_height, item_size.height())

        if current_row:
            rows.append((current_row, row_width, row_height))

        total_height = sum(h for _, _, h in rows) + spacing * max(0, len(rows) - 1)

        if not test_only:
            y = effective.y()
            for row_items, this_row_width, this_row_height in rows:
                x = effective.x() + (effective.width() - this_row_width) / 2
                for item in row_items:
                    item.setGeometry(QRect(QPoint(int(x), int(y)), item.sizeHint()))
                    x += item.sizeHint().width() + spacing
                y += this_row_height + spacing

        return total_height + top + bottom


def _wrap_lines(text: str, metrics: QFontMetrics, width: int) -> list[str]:
    """Greedy word-wrap simulation - same technique QLabel's own wrapping
    uses - so the resulting line count matches what word-wrap would
    actually produce at this width."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and metrics.horizontalAdvance(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _elide_label_text(text: str, metrics: QFontMetrics, width: int, max_lines: int) -> str:
    """`text`, word-wrapped to at most `max_lines` lines at `width` - if it
    would need more than that, the last visible line ends in an ellipsis
    instead of the overflow being clipped off by the card's fixed height."""
    lines = _wrap_lines(text, metrics, width)
    if len(lines) <= max_lines:
        return text
    visible = lines[:max_lines]
    visible[-1] = metrics.elidedText(visible[-1], Qt.TextElideMode.ElideRight, width)
    return "\n".join(visible)


class Card(QFrame):
    """A single clickable, fixed-size square card. Emits `clicked` with the
    item_id it represents. Colors/radius come from the app-wide stylesheet
    (object name "card"); only the elevation shadow is set up here, since
    QSS has no box-shadow equivalent.
    """

    clicked = Signal(object)

    def __init__(
        self,
        item_id: object,
        label: str,
        parent: QWidget | None = None,
        size: int = CARD_SIZE,
    ):
        super().__init__(parent)
        self.item_id = item_id
        self.setObjectName("card")
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        margin = 12
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        text = QLabel()
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text)

        # The QSS cascade (QFrame#card QLabel { font-size: 14px;
        # font-weight: bold; }) hasn't necessarily been applied yet at
        # construction time, so measuring against the label's plain
        # default font here would under-measure how much text actually
        # fits. Matching that font explicitly keeps the two in sync
        # regardless of when the stylesheet actually gets polished onto
        # the widget.
        card_font = text.font()
        card_font.setPixelSize(14)
        card_font.setBold(True)
        text.setFont(card_font)

        # Cards are a fixed size regardless of label length (uniform grid,
        # matching every other level's card - a Journal of Discourses
        # "Speaker - Title" label can be far longer than "Chapter 12").
        # A label too long to fit is elided to however many lines actually
        # fit, ellipsis on the last one, with the full text as a tooltip -
        # the standard fixed-size-tile-with-long-name pattern (file
        # manager icons, browser tabs), rather than shrinking the font
        # (illegible at the size some of these titles would need) or a
        # popup (a tooltip already *is* that, for free).
        content_width = size - 2 * margin
        metrics = QFontMetrics(card_font)
        max_lines = max(1, (size - 2 * margin) // metrics.lineSpacing())
        text.setText(_elide_label_text(label, metrics, content_width, max_lines))
        if metrics.horizontalAdvance(label) > content_width or "\n" in label:
            self.setToolTip(label)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(14)
        self._shadow.setOffset(0, 2)
        self._shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(self._shadow)

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item_id)
        super().mousePressEvent(event)

    def enterEvent(self, event):  # noqa: N802 (Qt naming convention)
        self._shadow.setBlurRadius(22)
        self._shadow.setOffset(0, 5)
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 (Qt naming convention)
        self._shadow.setBlurRadius(14)
        self._shadow.setOffset(0, 2)
        super().leaveEvent(event)


class CardGridWidget(QWidget):
    """A titled, scrollable, wrapping gallery of fixed-size Cards.

    `items` is a list of (item_id, label) tuples. Emits `card_clicked(item_id)`
    when any card is clicked.
    """

    card_clicked = Signal(object)

    def __init__(
        self,
        title: str,
        items: list[tuple[object, str]],
        parent: QWidget | None = None,
        card_size: int = CARD_SIZE,
        banner: QWidget | None = None,
        show_title: bool = True,
    ):
        super().__init__(parent)

        outer = QVBoxLayout(self)

        # The landing page skips this - "Desktop Scriptures" is already
        # the window's own title bar text, so a second copy of it here
        # would just be repeated, space-wasting chrome. Every other level
        # (a volume, a book) still needs it - it's the only place that
        # name appears.
        if show_title:
            title_label = QLabel(title)
            title_label.setObjectName("sectionTitle")
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            outer.addWidget(title_label)

        # Optional extra widget between the title and the card grid - e.g.
        # the landing page's Scripture of the Day / Church News boxes.
        # Inset to match FlowLayout's own GRID_MARGIN below, so the
        # banner's left/right edges land exactly where the card row's do
        # rather than overhanging past them.
        if banner is not None:
            banner_wrap = QWidget()
            banner_layout = QHBoxLayout(banner_wrap)
            banner_layout.setContentsMargins(GRID_MARGIN, 0, GRID_MARGIN, 8)
            banner_layout.addWidget(banner)
            outer.addWidget(banner_wrap)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        grid_container = QWidget()
        flow = FlowLayout(grid_container, margin=GRID_MARGIN, spacing=16)

        for item_id, label in items:
            card = Card(item_id, label, size=card_size)
            card.clicked.connect(self.card_clicked)
            flow.addWidget(card)

        # Center the grid vertically too: sandwich it between two stretches
        # in a wrapper widget. QScrollArea (widgetResizable=True) grows the
        # wrapper to at least fill the viewport, so when the cards don't
        # fill the height the stretches split the leftover space evenly;
        # when there are enough cards to need scrolling, the stretches
        # collapse to zero and the wrapper's natural (taller) height wins.
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addStretch(1)
        wrapper_layout.addWidget(grid_container)
        wrapper_layout.addStretch(1)

        scroll.setWidget(wrapper)
        outer.addWidget(scroll)
