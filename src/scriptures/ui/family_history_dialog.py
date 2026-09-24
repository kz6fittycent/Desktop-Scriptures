"""The Family History reminder popup (see main_window.py's menu wiring
and startup check, and family_history.py's module docstring for the
overall design - an opt-in nudge shown at irregular intervals).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from scriptures.family_history import FAMILYSEARCH_URL


class FamilyHistoryReminderDialog(QDialog):
    """No "don't remind me again" checkbox here, unlike the GC/Temple
    Recommend reminders - there's no single instance of this reminder to
    dismiss, since it recurs indefinitely at random intervals for as long
    as the View menu toggle stays on. That toggle is the only opt-out."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Family History")
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        message = QLabel("Got a few minutes for family history today?")
        message.setObjectName("familyHistoryMessage")
        message.setWordWrap(True)
        layout.addWidget(message)

        # The link is embedded directly here, not behind a second
        # "Open FamilySearch" button that pops its own dialog -
        # QDesktopServices.openUrl() reports success without actually
        # opening anything for this one dialog, for reasons specific to
        # it that weren't worth chasing further once a plain clickable
        # link (same mechanism _share_book_of_mormon in main_window.py
        # already relies on) proved reliable.
        link = QLabel(f'<a href="{FAMILYSEARCH_URL}">{FAMILYSEARCH_URL}</a>')
        link.setTextFormat(Qt.TextFormat.RichText)
        link.setOpenExternalLinks(True)
        layout.addWidget(link)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        ok_button = QPushButton("Okay")
        ok_button.setDefault(True)
        ok_button.clicked.connect(self.accept)
        bottom_row.addWidget(ok_button)
        layout.addLayout(bottom_row)
