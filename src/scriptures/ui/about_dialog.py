"""About dialog: version, the "unofficial app" disclaimer required by the
project's own stated policy (see README), and credit to the beandog
project whose lds-scriptures dataset this app's scripture text comes from.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

APP_VERSION = "1.0"
BEANDOG_REPO_URL = "https://github.com/beandog/lds-scriptures"
CHURCH_SCRIPTURES_URL = "https://www.churchofjesuschrist.org/study/scriptures"


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("About Desktop Scriptures")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(f"Desktop Scriptures — version {APP_VERSION}")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        disclaimer = QLabel(
            "This is an unofficial application, not produced by or "
            "affiliated with The Church of Jesus Christ of Latter-day "
            "Saints."
        )
        disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)

        credit = QLabel(
            f'Special thanks to <a href="{BEANDOG_REPO_URL}">Beandog</a> '
            "for the scripture text this app is built on."
        )
        credit.setTextFormat(Qt.TextFormat.RichText)
        credit.setOpenExternalLinks(True)
        credit.setWordWrap(True)
        layout.addWidget(credit)

        church_link = QLabel(
            "Read the scriptures officially at "
            f'<a href="{CHURCH_SCRIPTURES_URL}">churchofjesuschrist.org</a>.'
        )
        church_link.setTextFormat(Qt.TextFormat.RichText)
        church_link.setOpenExternalLinks(True)
        church_link.setWordWrap(True)
        layout.addWidget(church_link)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
