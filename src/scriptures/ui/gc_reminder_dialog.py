"""The General Conference reminder popup (see main_window.py's startup
check and general_conference.py's module docstring for the overall
design - an opt-in, once-a-day-at-most heads-up shown in the ~2 weeks
before Conference starts).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from scriptures.general_conference import ConferenceDates, format_date_range

# Small and unobtrusive on purpose - this is a heads-up, not something
# that needs to compete for attention like a real dialog (AI Settings,
# Sync Options). Wide enough that the checkbox's label fits on one line -
# QCheckBox, unlike QLabel, doesn't word-wrap its own text.
_DIALOG_WIDTH = 330
_MESSAGE_FONT_POINT_SIZE = 10
_CHECKBOX_FONT_POINT_SIZE = 10
_CHECKBOX_INDICATOR_SIZE = 20

# How far from the parent window's own bottom-left corner this opens -
# out of the way of the landing page's boxes, closer to where a toast
# notification would sit than a centered modal.
_POSITION_MARGIN_X = 40
_POSITION_MARGIN_Y = 60


class GeneralConferenceReminderDialog(QDialog):
    """On close, `dont_remind_again` says whether the checkbox was
    checked - see main_window.py's `_on_gc_dates_fetched`, which persists
    that as a dismissal keyed to this specific Conference's start date,
    so it naturally resets for the next one."""

    def __init__(self, dates: ConferenceDates, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("General Conference")
        self.setFixedWidth(_DIALOG_WIDTH)
        self.dont_remind_again = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        message = QLabel(f"General Conference is coming up: {format_date_range(dates)}.")
        message.setWordWrap(True)
        message_font = message.font()
        message_font.setPointSize(_MESSAGE_FONT_POINT_SIZE)
        message.setFont(message_font)
        layout.addWidget(message)

        self._checkbox = QCheckBox("Don't remind me for this Conference")
        checkbox_font = self._checkbox.font()
        checkbox_font.setPointSize(_CHECKBOX_FONT_POINT_SIZE)
        self._checkbox.setFont(checkbox_font)
        # A plain QCheckBox's indicator box is easy to miss at this
        # dialog's small size - sized up explicitly rather than relying
        # on whatever a given Qt style's default happens to be.
        self._checkbox.setStyleSheet(
            f"QCheckBox::indicator {{ width: {_CHECKBOX_INDICATOR_SIZE}px; "
            f"height: {_CHECKBOX_INDICATOR_SIZE}px; }}"
            "QCheckBox { spacing: 8px; }"
        )
        layout.addWidget(self._checkbox)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        ok_button = QPushButton("Okay")
        ok_button.setDefault(True)
        ok_button.clicked.connect(self.accept)
        button_row.addWidget(ok_button)
        layout.addLayout(button_row)

        if parent is not None:
            self._position_near_parent(parent)

    def _position_near_parent(self, parent: QWidget) -> None:
        self.adjustSize()
        parent_geo = parent.frameGeometry()
        x = parent_geo.x() + _POSITION_MARGIN_X
        y = parent_geo.y() + parent_geo.height() - self.height() - _POSITION_MARGIN_Y
        self.move(max(x, 0), max(y, 0))

    def accept(self) -> None:
        self.dont_remind_again = self._checkbox.isChecked()
        super().accept()
