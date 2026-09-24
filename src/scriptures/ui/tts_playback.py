"""Background-thread TTS playback controller (see reading_view.py's
Listen controls and tts.py's module docstring for the overall design).

Synthesis (see tts.synthesize) is a blocking, CPU-bound onnxruntime call
- too slow to run on the UI thread without freezing it - so it happens
on a dedicated QThread, one verse at a time. Playback of the resulting
WAV bytes uses QMediaPlayer fed from an in-memory QBuffer (no temp
files): reading a chapter aloud is naturally sequential (synthesize one
verse, play it, then move to the next once it ends), so this doesn't
try to pipeline synthesis ahead of playback - simpler, and Piper is fast
enough per verse that the gap between verses is brief.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QThread, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from scriptures import tts


@dataclass(frozen=True)
class ReadableVerse:
    verse_id: int
    text: str


class _SynthesizeWorker(QObject):
    """Lives on its own QThread - see TtsController._thread. `generation`
    is echoed back unchanged so the controller can tell a stale, already-
    cancelled request's result apart from the current one (see
    TtsController's own docstring).

    `synthesize` is invoked only via the `requested` signal below, never
    called directly - a signal connected across a thread boundary is what
    actually gets Qt to queue the call onto this worker's own thread; a
    plain Python method call would just run synchronously on whichever
    thread happens to call it."""

    requested = Signal(int, str, str)  # generation, voice_key, text
    finished = Signal(int, bytes)
    failed = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.requested.connect(self._synthesize)

    def _synthesize(self, generation: int, voice_key: str, text: str) -> None:
        try:
            wav_bytes = tts.synthesize(voice_key, text)
        except Exception as e:  # noqa: BLE001 - reported to the UI either way
            self.failed.emit(generation, str(e))
            return
        self.finished.emit(generation, wav_bytes)


class TtsController(QObject):
    """One per ReadingView, created lazily on first use (see
    reading_view.py) - owns a background synthesis thread and a
    QMediaPlayer for the lifetime of the reading view that created it.

    `generation` increments on every start()/stop(), and any in-flight
    synthesis result tagged with an older generation is discarded when it
    arrives - the guard against e.g. clicking Stop (or navigating to a
    different chapter) while a verse is still being synthesized, and
    that verse's audio starting to play anyway once it finishes.
    """

    verse_started = Signal(int)  # verse_id
    playback_stopped = Signal()  # reached the end, or stop() was called
    synthesis_failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._verses: list[ReadableVerse] = []
        self._index = 0
        self._voice_key = tts.DEFAULT_VOICE_KEY
        self._generation = 0
        self._paused = False

        self._thread = QThread(self)
        self._worker = _SynthesizeWorker()
        self._worker.moveToThread(self._thread)
        self._worker.finished.connect(self._on_synthesized)
        self._worker.failed.connect(self._on_synthesis_failed)
        self._thread.start()

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

        # Every QBuffer created this session (see _on_synthesized), kept
        # alive for as long as this controller itself exists - see stop()
        # for why they're deliberately never freed any earlier than that.
        # QMediaPlayer.setSourceDevice() doesn't take ownership; letting
        # Python garbage-collect each previous verse's buffer as soon as
        # the next one replaced it (the first version of this) crashed
        # the whole process outright: Qt6's FFmpeg backend can still be
        # tearing down its read of the old device on its own internal
        # thread at that exact moment, and freeing the underlying C++
        # object out from under that is a use-after-free, not a
        # Python-catchable error.
        self._buffers: list[QBuffer] = []

    def is_active(self) -> bool:
        return self._index < len(self._verses) or self._paused

    def is_paused(self) -> bool:
        return self._paused

    def start(self, voice_key: str, verses: list[ReadableVerse], start_index: int = 0) -> None:
        self.stop()
        self._voice_key = voice_key
        self._verses = verses
        self._index = start_index
        self._generation += 1
        self._synthesize_current()

    def pause(self) -> None:
        if self._paused or not self.is_active():
            return
        self._paused = True
        self._player.pause()

    def resume(self) -> None:
        if not self._paused:
            return
        self._paused = False
        self._player.play()

    def stop(self) -> None:
        self._generation += 1  # invalidates any synthesis already in flight
        self._verses = []
        self._index = 0
        self._paused = False
        self._player.stop()
        # Deliberately NOT calling setSourceDevice(None) here (and NOT
        # clearing self._buffers either, for the same reason) - detaching
        # or freeing the source device the player still points to, right
        # after pausing it, deadlocks an internal Qt6Multimedia FFmpeg
        # thread (reproduced directly: pause, resume, pause again, then
        # stop - every time, on the *third* call into the player after a
        # pause). Calling player.stop() alone, and simply leaving the
        # last buffer referenced until this whole controller is later
        # destroyed, avoids it - the next verse's _on_synthesized() (or a
        # fresh start()) replaces the source device outright instead,
        # which is the one buffer-swapping path already proven safe
        # across a full 25-verse chapter.

    def shutdown(self) -> None:
        """Called once, when the owning ReadingView is torn down - stops
        the background thread for good, not just the current playback."""
        self.stop()
        self._thread.quit()
        self._thread.wait()

    def _synthesize_current(self) -> None:
        if self._index >= len(self._verses):
            self.playback_stopped.emit()
            return
        verse = self._verses[self._index]
        self._worker.requested.emit(self._generation, self._voice_key, verse.text)

    def _on_synthesized(self, generation: int, wav_bytes: bytes) -> None:
        if generation != self._generation:
            return  # stale - stop()/start() ran again before this arrived
        verse = self._verses[self._index]
        self.verse_started.emit(verse.verse_id)

        byte_array = QByteArray(wav_bytes)
        buffer = QBuffer(self)
        buffer.setData(byte_array)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._buffers.append(buffer)

        # Forces a clean handoff from whichever device (if any) the player
        # was still attached to before swapping in the new one, rather
        # than relying on setSourceDevice() to do that itself mid-stream.
        self._player.stop()
        self._player.setSourceDevice(buffer)
        self._player.play()

    def _on_synthesis_failed(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self.synthesis_failed.emit(message)
        self.stop()

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._paused:
            return
        self._index += 1
        self._synthesize_current()
