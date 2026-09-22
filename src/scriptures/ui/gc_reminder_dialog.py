"""The General Conference reminder popup (see main_window.py's startup
check and general_conference.py's module docstring for the overall
design - an opt-in, once-a-day-at-most heads-up shown in the ~2 weeks
before Conference starts).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from scriptures.general_conference import ConferenceDates, format_date_range

# Small and unobtrusive on purpose - this is a heads-up, not something
# that needs to compete for attention like a real dialog (AI Settings,
# Sync Options). Wide enough that the checkbox's label fits beside the
# Okay button on the same row without crowding.
_DIALOG_WIDTH = 340


class _CheckboxRow(QFrame):
    """A bordered, clickable row - clicking anywhere in it toggles the
    dismissal, not just a small indicator glyph. Built from a checkable
    QPushButton rather than a real QCheckBox: some native/GTK-integrated
    Qt styles (this app's Snap uses the gnome extension) draw a
    QCheckBox's indicator through their own theme engine and ignore this
    app's own size hint for it entirely, rendering it too small to
    notice. A QPushButton's whole box is styled as one ordinary
    rectangle, with none of that sub-control delegation, so plain QSS
    sizing always applies regardless of platform style."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("gcReminderCheckboxRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        self._toggle = QPushButton()
        self._toggle.setObjectName("gcReminderToggle")
        self._toggle.setCheckable(True)
        self._toggle.setFixedSize(18, 18)
        self._toggle.toggled.connect(lambda checked: self._toggle.setText("✓" if checked else ""))
        layout.addWidget(self._toggle)

        label = QLabel(text)
        label.setObjectName("gcReminderCheckboxLabel")
        layout.addWidget(label)

    def isChecked(self) -> bool:
        return self._toggle.isChecked()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle.setChecked(not self._toggle.isChecked())
        super().mousePressEvent(event)


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
        message.setObjectName("gcReminderMessage")
        message.setWordWrap(True)
        layout.addWidget(message)

        # One bottom row - the dismissal checkbox at its left edge, the
        # Okay button at its right, nothing else competing for space in
        # between.
        bottom_row = QHBoxLayout()
        self._checkbox_row = _CheckboxRow("Don't remind me again")
        bottom_row.addWidget(self._checkbox_row)
        bottom_row.addStretch(1)
        ok_button = QPushButton("Okay")
        ok_button.setDefault(True)
        ok_button.clicked.connect(self.accept)
        bottom_row.addWidget(ok_button)
        layout.addLayout(bottom_row)

    def accept(self) -> None:
        self.dont_remind_again = self._checkbox_row.isChecked()
        super().accept()
