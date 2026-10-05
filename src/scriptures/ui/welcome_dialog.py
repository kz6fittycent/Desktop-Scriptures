"""First-run welcome: a short, skippable walk through the optional extras.

Shown at startup (see app.py → MainWindow.maybe_show_welcome) until the
user switches on "Don't show this at startup again", and reachable any
time from Menu → Welcome.... Five steps:

1. Welcome - the app works offline; everything here is optional.
2. Listen - switch on the Listen controls (the same setting as Menu →
   Voice → Show Listen Controls) and download a voice (opens the same
   Download or Remove Voices dialog as the menu).
3. Additional books - switch on the Apocrypha and/or Other Ancient
   Texts (the same settings as Menu → Additional Books; see
   data_access.OPTIONAL_VOLUMES). Both start off.
4. AI - opens the existing AI Setup Wizard (still in Menu → AI
   Integration too).
5. Done - where to find all of it later.

Closing at any step is fine. Reaching the last step switches "Don't show
this at startup again" on (the user can switch it back off); otherwise
it stays as the user left it.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from scriptures import tts
from scriptures.data_access import OPTIONAL_VOLUMES
from scriptures.ui.toggle_row import ToggleRow
from scriptures.ui.voices_dialog import VoicesDialog


def _text(html: str) -> QLabel:
    label = QLabel(html)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    return label


class WelcomeDialog(QDialog):
    def __init__(
        self,
        *,
        listen_enabled: bool,
        set_listen_enabled: Callable[[bool], None],
        open_ai_wizard: Callable[[], None],
        ai_configured: Callable[[], bool],
        volume_shown: Callable[[str], bool],
        set_volume_shown: Callable[[str, bool], None],
        dont_show_again: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Desktop Scriptures")
        self.setMinimumWidth(560)
        self._set_listen_enabled = set_listen_enabled
        self._open_ai_wizard = open_ai_wizard
        self._ai_configured = ai_configured

        layout = QVBoxLayout(self)
        self._pages = QStackedWidget()
        layout.addWidget(self._pages, 1)

        # 1. Welcome
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(_text(
            "<h2>Welcome to Desktop Scriptures</h2>"
            "<p>Everything you need to read and study - the scriptures, notes, highlights, "
            "search, the Topical Guide, Word Study, and the Journal - is ready now and works "
            "offline.</p>"
            "<p>The next steps set up optional extras: having chapters read aloud, more books "
            "to read alongside the Standard Works, and AI-assisted search. Skip any of them, or "
            "close this window at any time; they're always in the <b>Menu</b>.</p>"
        ))
        v.addStretch(1)
        self._pages.addWidget(page)

        # 2. Listen
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(_text(
            "<h2>Listen</h2>"
            "<p>Have any chapter read aloud, verse by verse, with each verse highlighted as "
            "it's read. Switch it on to add a <b>▶ Listen</b> button to every chapter.</p>"
        ))
        self._listen_toggle = ToggleRow("Show the Listen controls", checked=listen_enabled)
        self._listen_toggle.toggled.connect(self._on_listen_toggled)
        v.addWidget(self._listen_toggle)
        v.addWidget(_text(
            "<p>Listen needs a voice, downloaded once - about 63 MB each - and then works "
            "offline. Choose the voice you want; you don't need them all.</p>"
        ))
        row = QHBoxLayout()
        voices_button = QPushButton("Download a Voice...")
        voices_button.setAutoDefault(False)
        voices_button.clicked.connect(self._open_voices)
        row.addWidget(voices_button)
        self._voices_status = QLabel()
        self._voices_status.setObjectName("resultSecondary")
        row.addWidget(self._voices_status, 1)
        v.addLayout(row)
        v.addStretch(1)
        self._pages.addWidget(page)

        # 3. Additional books
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(_text(
            "<h2>Additional books</h2>"
            "<p>Two more volumes are included, for reading alongside the Standard Works. They "
            "aren't considered part of the Standard Works, so they're hidden until you switch "
            "them on. Once on, they're in the library, search, and AI search like the rest.</p>"
            "<p><b>The Apocrypha</b> - the fourteen books printed between the Old and New "
            "Testaments in the 1611 King James Bible, of which the Lord said \"there are many "
            "things contained therein that are true\" (D&amp;C 91:1).<br>"
            "<b>Other Ancient Texts</b> - 1 Enoch, which Jude 1:14-15 quotes, and the Book "
            "of Jasher.</p>"
        ))
        self._volume_toggles: dict[str, ToggleRow] = {}
        for slug, (label, _key) in OPTIONAL_VOLUMES.items():
            toggle = ToggleRow(f"Show {label}", checked=volume_shown(slug))
            toggle.toggled.connect(lambda checked, s=slug: set_volume_shown(s, checked))
            v.addWidget(toggle)
            self._volume_toggles[slug] = toggle
        v.addStretch(1)
        self._pages.addWidget(page)

        # 4. AI
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(_text(
            "<h2>AI-assisted search</h2>"
            "<p>Ask a question in your own words - \"verses about forgiving others\" - and get "
            "pointed to real passages, talks, and articles. It uses an AI service you choose: "
            "one running on your own computer (such as Ollama), or a hosted one with your own "
            "key. Nothing is sent anywhere until you set it up.</p>"
            "<p>The AI Setup Wizard finds what's already running on this computer and walks "
            "you through the rest.</p>"
        ))
        row = QHBoxLayout()
        ai_button = QPushButton("Set Up AI...")
        ai_button.setAutoDefault(False)
        ai_button.clicked.connect(self._on_ai)
        row.addWidget(ai_button)
        self._ai_status = QLabel()
        self._ai_status.setObjectName("resultSecondary")
        row.addWidget(self._ai_status, 1)
        v.addLayout(row)
        v.addStretch(1)
        self._pages.addWidget(page)

        # 5. Done
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(_text(
            "<h2>You're all set</h2>"
            "<p>You can change any of this later:</p>"
            "<ul>"
            "<li><b>Menu → Voice</b> - Listen controls, your voice, and Download or Remove Voices...</li>"
            "<li><b>Menu → Additional Books</b> - the Apocrypha and Other Ancient Texts</li>"
            "<li><b>Menu → AI Integration</b> - the AI Setup Wizard and AI Settings</li>"
            "<li><b>Menu → Welcome...</b> - this window</li>"
            "<li><b>Menu → Help (Wiki)...</b> - a guide to every feature</li>"
            "</ul>"
        ))
        v.addStretch(1)
        self._pages.addWidget(page)

        # The bottom bar, on every step.
        bottom = QHBoxLayout()
        self._dont_show = ToggleRow("Don't show this at startup again", checked=dont_show_again)
        bottom.addWidget(self._dont_show, 1)
        self._back = QPushButton("Back")
        self._back.setAutoDefault(False)
        self._back.clicked.connect(lambda: self._go(self._pages.currentIndex() - 1))
        bottom.addWidget(self._back)
        self._next = QPushButton("Next")
        self._next.setDefault(True)
        self._next.clicked.connect(self._on_next)
        bottom.addWidget(self._next)
        close = QPushButton("Close")
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        layout.addLayout(bottom)

        self._go(0)

    def dont_show_again(self) -> bool:
        return self._dont_show.isChecked()

    def _go(self, index: int) -> None:
        last = self._pages.count() - 1
        index = max(0, min(index, last))
        self._pages.setCurrentIndex(index)
        self._back.setEnabled(index > 0)
        self._next.setText("Finish" if index == last else "Next")
        if index == last:
            self._dont_show.setChecked(True)
        self._refresh_status()

    def _on_next(self) -> None:
        if self._pages.currentIndex() == self._pages.count() - 1:
            self.accept()
        else:
            self._go(self._pages.currentIndex() + 1)

    def _on_listen_toggled(self, checked: bool) -> None:
        self._set_listen_enabled(checked)

    def _open_voices(self) -> None:
        dialog = VoicesDialog(self)
        dialog.exec()
        # Downloading a voice here means they want Listen.
        if any(tts.is_voice_installed(v.key) for v in tts.VOICES) and not self._listen_toggle.isChecked():
            self._listen_toggle.setChecked(True)
        self._refresh_status()

    def _on_ai(self) -> None:
        self._open_ai_wizard()
        self._refresh_status()

    def _refresh_status(self) -> None:
        installed = [v.label for v in tts.VOICES if tts.is_voice_installed(v.key)]
        self._voices_status.setText(
            "Downloaded: " + ", ".join(installed) if installed else "No voice downloaded yet"
        )
        self._ai_status.setText("AI is set up." if self._ai_configured() else "Not set up yet")
