"""Downloads Listen voices on request (see tts.py's VOICES and
ui/voices_dialog.py).

Each voice is two files from Piper's model repository on Hugging Face:
the ~60 MB .onnx model and its small .onnx.json config. Each streams to a
".part" file beside its destination, is hashed as it arrives, and only
replaces the real file once its size and SHA-256 match the values pinned
in tts.VOICES - so an interrupted or tampered download never leaves a
half-written voice behind.

One QNetworkAccessManager serves every download (each manager holds a
connection and a thread - see embeddings.py's note on the snap's
open-files limit), and each finished reply is deleteLater()'d.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from scriptures import tts

# Generous: a 60 MB file on a slow connection. Applies to a stalled
# transfer, not the whole download.
TRANSFER_TIMEOUT_MS = 60_000


class VoiceDownloader(QObject):
    """Downloads one voice at a time.

    `progress(key, received, total)` as bytes arrive (across both files);
    `finished(key, ok, message)` exactly once per download - ok=False with
    message="" means it was cancelled."""

    progress = Signal(str, int, int)
    finished = Signal(str, bool, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._voice: tts.Voice | None = None
        self._steps: list[tuple[str, str, int, Path]] = []
        self._done_bytes = 0
        self._part: Path | None = None
        self._file = None
        self._hash = None

    def is_busy(self) -> bool:
        return self._voice is not None

    def download(self, key: str) -> None:
        voice = tts.get_voice(key)
        if voice is None:
            raise ValueError(f"Unknown voice: {key}")
        if self.is_busy():
            raise RuntimeError("A voice is already downloading")
        target = tts.download_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._voice = voice
        self._done_bytes = 0
        # The config first (small), then the model.
        self._steps = [
            (voice.url(".onnx.json"), voice.config_sha256, voice.config_size, target.with_suffix(".onnx.json")),
            (voice.url(".onnx"), voice.model_sha256, voice.model_size, target),
        ]
        self._next_file()

    def cancel(self) -> None:
        if self._voice is None:
            return
        key = self._voice.key
        if self._reply is not None:
            self._reply.readyRead.disconnect(self._on_ready_read)
            self._reply.finished.disconnect(self._on_finished)
            self._reply.abort()
            self._reply.deleteLater()
            self._reply = None
        self._discard_part()
        self._end(key, False, "")

    def _total(self) -> int:
        return self._voice.config_size + self._voice.model_size

    def _next_file(self) -> None:
        if not self._steps:
            key = self._voice.key
            self._end(key, True, f"{self._voice.label} is ready.")
            return
        url, _sha, _size, dest = self._steps[0]
        self._part = dest.with_name(dest.name + ".part")
        self._file = open(self._part, "wb")  # noqa: SIM115 - closed in _close_part
        self._hash = hashlib.sha256()
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(TRANSFER_TIMEOUT_MS)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,  # Hugging Face redirects to its CDN
        )
        self._reply = self._manager.get(request)
        self._reply.readyRead.connect(self._on_ready_read)
        self._reply.finished.connect(self._on_finished)

    def _on_ready_read(self) -> None:
        data = bytes(self._reply.readAll())
        self._file.write(data)
        self._hash.update(data)
        self._done_bytes += len(data)
        self.progress.emit(self._voice.key, self._done_bytes, self._total())

    def _on_finished(self) -> None:
        reply, self._reply = self._reply, None
        self._on_ready_read_remaining(reply)
        error = reply.error()
        error_text = reply.errorString()
        reply.deleteLater()
        key = self._voice.key
        url, sha, size, dest = self._steps[0]
        self._close_part()
        if error != QNetworkReply.NetworkError.NoError:
            self._discard_part()
            self._end(key, False, f"Couldn't download {self._voice.label}: {error_text}")
            return
        written = self._part.stat().st_size
        if written != size or self._hash.hexdigest() != sha:
            self._discard_part()
            self._end(
                key, False,
                f"The download of {self._voice.label} didn't match the expected file "
                "(it may have been interrupted). Please try again.",
            )
            return
        self._part.replace(dest)
        self._part = None
        self._steps.pop(0)
        self._next_file()

    def _on_ready_read_remaining(self, reply: QNetworkReply) -> None:
        data = bytes(reply.readAll())
        if data:
            self._file.write(data)
            self._hash.update(data)
            self._done_bytes += len(data)

    def _close_part(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def _discard_part(self) -> None:
        self._close_part()
        if self._part is not None:
            self._part.unlink(missing_ok=True)
            self._part = None

    def _end(self, key: str, ok: bool, message: str) -> None:
        if not ok and not tts.is_voice_installed(key):
            # Don't leave half a voice: a config without its model.
            tts.remove_voice(key)
        self._voice = None
        self._steps = []
        self.finished.emit(key, ok, message)
