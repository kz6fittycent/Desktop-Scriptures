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


class GeneralConferenceReminderDialog(QDialog):
    """On close, `dont_remind_again` says whether the checkbox was
    checked - see main_window.py's `_on_gc_dates_fetched`, which persists
    that as a dismissal keyed to this specific Conference's start date,
    so it naturally resets for the next one."""

    def __init__(self, dates: ConferenceDates, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("General Conference")
        self.setMinimumWidth(380)
        self.dont_remind_again = False

        layout = QVBoxLayout(self)

        message = QLabel(
            f"General Conference is coming up: {format_date_range(dates)}."
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        self._checkbox = QCheckBox("Don't remind me again for this Conference")
        layout.addWidget(self._checkbox)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

    def accept(self) -> None:
        self.dont_remind_again = self._checkbox.isChecked()
        super().accept()
