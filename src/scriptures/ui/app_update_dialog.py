"""The "Update available" dialog behind the menu bar's button (see
app_updates.py): what's new, and where to download it. One dialog with
the link visible and clickable in it, like every external link in the
app - QDesktopServices.openUrl() alone has failed silently before.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextBrowser, QVBoxLayout, QWidget

from scriptures import __version__
from scriptures.app_updates import Release


class AppUpdateDialog(QDialog):
    def __init__(self, release: Release, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Update Available")
        self.resize(560, 440)
        layout = QVBoxLayout(self)

        url = html.escape(release.url, quote=True)
        intro = QLabel(
            f"<b>Desktop Scriptures {html.escape(release.version)}</b> is out "
            f"(you have {html.escape(__version__)}).<br><br>"
            f"Download it here:<br><a href=\"{url}\">{url}</a><br><br>"
            "Install it over this version - your notes, highlights, Journal, and study "
            "index stay. The first time it opens, your system asks once, the same as "
            "when you first installed it.<br><br>"
            "Installed it with Winget or Homebrew? Update the same way instead: "
            "<code>winget upgrade kz6fittycent.DesktopScriptures</code> or "
            "<code>brew upgrade --cask desktop-scriptures</code>."
        )
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setOpenExternalLinks(True)
        intro.setWordWrap(True)
        intro.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(intro)

        if release.notes:
            layout.addWidget(QLabel("<b>Release notes</b>"))
            notes = QTextBrowser()
            notes.setOpenExternalLinks(True)
            notes.setMarkdown(release.notes)
            layout.addWidget(notes, 1)
        else:
            layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
