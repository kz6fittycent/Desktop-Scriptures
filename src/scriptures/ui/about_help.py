"""The About menu's License dialog and the Help menu's wiki dialog.

Both show their links inside the dialog (clickable QLabel text) rather
than opening a browser directly - QDesktopServices.openUrl() has reported
success without anything visibly opening in this app (see the Family
History reminder's history in main_window.py).

The License dialog shows the full MIT License text from LICENSE.md, which
ships with the app (snapcraft.yaml copies it in), so it works offline;
if the file is ever missing it falls back to a link.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from scriptures.ai_setup import WIKI_URL

REPO_URL = "https://github.com/kz6fittycent/Desktop-Scriptures"
LICENSE_URL = f"{REPO_URL}/blob/main/LICENSE.md"
ISSUES_URL = f"{REPO_URL}/issues"
LICENSE_PATH = Path(__file__).resolve().parents[3] / "LICENSE.md"

# Wiki pages, in the wiki sidebar's order.
WIKI_PAGES = (
    ("Home", "Home - what the app does, and a note on privacy"),
    ("Installation", "Installation"),
    ("Word-Study", "Word Study - original words, Book of Mormon names, and the Hebrew calendar"),
    ("AI-Integration", "AI Integration"),
    ("Choosing-an-AI-Setup", "Choosing an AI Setup"),
    ("Sync", "Sync"),
    ("Landing-Page-Extras", "Landing Page Extras"),
    ("Journal", "Journal"),
    ("Listen", "Listen (text-to-speech)"),
    ("General-Conference-Reminder", "General Conference Reminder"),
    ("Temple-Recommend-Reminder", "Temple Recommend Reminder"),
    ("Family-History-Reminder", "Family History Reminder"),
)


def _link_label(html: str) -> QLabel:
    label = QLabel(html)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    label.setWordWrap(True)
    return label


class LicenseDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("License")
        self.resize(560, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(_link_label(
            "Desktop Scriptures is released under the MIT License. The lexicon data carries "
            "its own licenses - see the About menu."
        ))
        try:
            text = LICENSE_PATH.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if text:
            view = QPlainTextEdit(text)
            view.setReadOnly(True)
            layout.addWidget(view, 1)
        else:
            layout.addWidget(_link_label(f'Read it at <a href="{LICENSE_URL}">{LICENSE_URL}</a>.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class HelpDialog(QDialog):
    """The wiki's pages, each a link, plus where to report a problem."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Desktop Scriptures Help")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        pages = "".join(f'<li><a href="{WIKI_URL}/{page}">{title}</a></li>' for page, title in WIKI_PAGES)
        layout.addWidget(_link_label(
            f'<p>The <a href="{WIKI_URL}">Desktop Scriptures wiki</a> walks through every '
            f"feature:</p><ul>{pages}</ul>"
            f'<p>Found a problem, or have an idea? <a href="{ISSUES_URL}">Report an issue</a>.</p>'
        ))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
