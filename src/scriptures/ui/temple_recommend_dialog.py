"""Temple Recommend renewal reminder - both its "Temple Recommend
Reminder..." setup dialog and the popup shown once it's due (see
main_window.py's menu wiring and startup check, and
temple_recommend.py's module docstring for the overall design).
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from scriptures.temple_recommend import format_reminder_message


class TempleRecommendOptionsDialog(QDialog):
    """On accept, `enabled` and `expiration` hold the user's choices -
    `expiration` is None only if the checkbox was left on but no date was
    ever set, which the date field's own default (two years out, a
    recommend's usual validity) makes unlikely in practice."""

    def __init__(
        self, enabled: bool, expiration: date | None, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Temple Recommend Reminder")
        self.setMinimumWidth(360)
        self.enabled = enabled
        self.expiration: date | None = expiration

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Get a heads-up starting about 4 weeks out from your temple "
            "recommend's expiration date. Entirely offline - this just "
            "checks the date below against today's date, nothing is sent "
            "anywhere."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._enabled_checkbox = QCheckBox("Remind me before it expires")
        self._enabled_checkbox.setChecked(enabled)
        layout.addWidget(self._enabled_checkbox)

        form = QFormLayout()
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("MMMM d, yyyy")
        if expiration is not None:
            self._date_edit.setDate(QDate(expiration.year, expiration.month, expiration.day))
        else:
            default = date.today() + timedelta(days=365 * 2)
            self._date_edit.setDate(QDate(default.year, default.month, default.day))
        form.addRow("Expiration date:", self._date_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        self.enabled = self._enabled_checkbox.isChecked()
        qd = self._date_edit.date()
        self.expiration = date(qd.year(), qd.month(), qd.day())
        self.accept()


class _CheckboxRow(QFrame):
    """A bordered, clickable row - clicking anywhere in it toggles the
    dismissal, not just a small indicator glyph. Same reasoning as
    gc_reminder_dialog.py's own copy of this: a checkable QPushButton
    sidesteps native/GTK-integrated Qt styles drawing a real QCheckBox's
    indicator through their own theme engine, too small to notice, that a
    QPushButton's plain QSS-styled rectangle never runs into."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("templeRecommendCheckboxRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        self._toggle = QPushButton()
        self._toggle.setObjectName("templeRecommendToggle")
        self._toggle.setCheckable(True)
        self._toggle.setFixedSize(18, 18)
        self._toggle.toggled.connect(lambda checked: self._toggle.setText("✓" if checked else ""))
        layout.addWidget(self._toggle)

        label = QLabel(text)
        label.setObjectName("templeRecommendCheckboxLabel")
        layout.addWidget(label)

    def isChecked(self) -> bool:
        return self._toggle.isChecked()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle.setChecked(not self._toggle.isChecked())
        super().mousePressEvent(event)


class TempleRecommendReminderDialog(QDialog):
    """On close, `dont_remind_again` says whether the checkbox was
    checked - see main_window.py's handling, which persists that as a
    dismissal keyed to this specific expiration date, so it naturally
    resets once the user renews and enters a new one."""

    def __init__(self, expiration: date, today: date, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Temple Recommend")
        self.setFixedWidth(340)
        self.dont_remind_again = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        message = QLabel(format_reminder_message(expiration, today))
        message.setObjectName("templeRecommendMessage")
        message.setWordWrap(True)
        layout.addWidget(message)

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
