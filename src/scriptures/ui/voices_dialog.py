"""Menu → Voice → Download Voices... - download or remove Listen voices.

Voices aren't part of the app (see tts.py): each row here shows a voice,
whether it's downloaded, its size, and the terms of the recordings it was
trained on, with Download/Remove. Downloads run one at a time through
voice_download.VoiceDownloader, with a progress bar and Cancel. Opening
the dialog with `start_key` begins that voice's download straight away -
used when Listen finds the chosen voice missing.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from scriptures import tts
from scriptures.paths import voices_dir
from scriptures.voice_download import VoiceDownloader


def _megabytes(n: int) -> str:
    return f"{n / 1_000_000:.0f} MB"


class VoicesDialog(QDialog):
    # A voice was downloaded or removed - the Voice menu refreshes its labels.
    voices_changed = Signal()

    def __init__(self, parent: QWidget | None = None, start_key: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Download Voices")
        self.setMinimumWidth(560)
        self._downloader = VoiceDownloader(self)
        self._downloader.progress.connect(self._on_progress)
        self._downloader.finished.connect(self._on_finished)
        self._rows: dict[str, tuple[QLabel, QPushButton]] = {}

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Listen reads chapters aloud with a voice you download once. After that it works "
            "offline. Voices come from Piper's voice collection on Hugging Face and are checked "
            f"before use. They're stored in:<br><code>{voices_dir()}</code>"
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(intro)

        grid_frame = QFrame()
        grid = QGridLayout(grid_frame)
        grid.setColumnStretch(0, 1)
        for row, voice in enumerate(tts.VOICES):
            name = QLabel(
                f"<b>{voice.label}</b> · {_megabytes(voice.model_size)}<br>"
                f"<span style='font-size: small'>Trained on {voice.dataset_license}</span>"
            )
            name.setTextFormat(Qt.TextFormat.RichText)
            name.setWordWrap(True)
            status = QLabel()
            status.setObjectName("resultSecondary")
            button = QPushButton()
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, k=voice.key: self._on_button(k))
            grid.addWidget(name, row, 0)
            grid.addWidget(status, row, 1)
            grid.addWidget(button, row, 2)
            self._rows[voice.key] = (status, button)
        layout.addWidget(grid_frame)

        self._progress = QProgressBar()
        self._progress.hide()
        layout.addWidget(self._progress)
        self._message = QLabel()
        self._message.setWordWrap(True)
        self._message.hide()
        layout.addWidget(self._message)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh()
        if start_key is not None and not tts.is_voice_installed(start_key):
            self._start(start_key)

    def _refresh(self) -> None:
        busy_key = self._busy_key()
        for voice in tts.VOICES:
            status, button = self._rows[voice.key]
            if voice.key == busy_key:
                status.setText("Downloading…")
                button.setText("Cancel")
                button.setEnabled(True)
            elif tts.is_voice_installed(voice.key):
                status.setText("Downloaded")
                button.setText("Remove")
                # A voice that came with the app (a source checkout or an
                # older build) isn't the user's to delete.
                button.setEnabled(tts.is_removable(voice.key) and busy_key is None)
            else:
                status.setText("Not downloaded")
                button.setText("Download")
                button.setEnabled(busy_key is None)

    def _busy_key(self) -> str | None:
        return getattr(self, "_downloading", None)

    def _on_button(self, key: str) -> None:
        if self._busy_key() == key:
            self._downloader.cancel()
        elif tts.is_voice_installed(key):
            tts.remove_voice(key)
            self._show_message(f"{tts.get_voice(key).label} was removed.")
            self.voices_changed.emit()
            self._refresh()
        else:
            self._start(key)

    def _start(self, key: str) -> None:
        self._downloading = key
        self._message.hide()
        self._progress.setRange(0, 0)  # busy until the first bytes arrive
        self._progress.show()
        self._refresh()
        self._downloader.download(key)

    def _on_progress(self, _key: str, received: int, total: int) -> None:
        self._progress.setRange(0, total)
        self._progress.setValue(received)
        self._progress.setFormat(f"{_megabytes(received)} of {_megabytes(total)}")

    def _on_finished(self, key: str, ok: bool, message: str) -> None:
        self._downloading = None
        self._progress.hide()
        if message:
            self._show_message(message)
        if ok:
            self.voices_changed.emit()
        self._refresh()

    def _show_message(self, text: str) -> None:
        self._message.setText(text)
        self._message.show()

    def done(self, result: int) -> None:  # noqa: D401 - Qt override
        self._downloader.cancel()  # closing mid-download stops it cleanly
        super().done(result)
