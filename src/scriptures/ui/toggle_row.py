"""A clearly visible on/off row for settings dialogs, in place of a plain
QCheckBox.

A real QCheckBox's indicator is drawn by whatever native/GTK-integrated
Qt style is in effect, not by this app's stylesheet - on some desktop
themes that comes out as a tiny, low-contrast box that's easy to miss
entirely (the AI Settings "Enable AI-assisted search" box went unnoticed
this way). Same fix gc_reminder_dialog.py and temple_recommend_dialog.py
already use for their "don't remind me again" rows: a bordered row whose
indicator is a checkable QPushButton, styled entirely by QSS (see
theme.py's QFrame#toggleRow rules), and clickable anywhere along it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class ToggleRow(QFrame):
    """Drop-in for the QCheckBox calls these dialogs used: isChecked(),
    setChecked(), and a `toggled(bool)` signal."""

    toggled = Signal(bool)

    def __init__(self, text: str, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("toggleRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self._toggle = QPushButton()
        self._toggle.setObjectName("toggleRowToggle")
        self._toggle.setCheckable(True)
        self._toggle.setFixedSize(20, 20)
        self._toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self._toggle)

        label = QLabel(text)
        label.setObjectName("toggleRowLabel")
        layout.addWidget(label, 1)

        self.setChecked(checked)

    def _on_toggled(self, checked: bool) -> None:
        self._toggle.setText("✓" if checked else "")
        self.toggled.emit(checked)

    def isChecked(self) -> bool:  # noqa: N802 (matches QCheckBox)
        return self._toggle.isChecked()

    def setChecked(self, checked: bool) -> None:  # noqa: N802 (matches QCheckBox)
        self._toggle.setChecked(checked)
        self._toggle.setText("✓" if checked else "")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle.setChecked(not self._toggle.isChecked())
        super().mousePressEvent(event)
