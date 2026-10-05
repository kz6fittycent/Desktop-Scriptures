"""Standalone test script for downloadable Listen voices (tts.py,
voice_download.py, ui/voices_dialog.py). No test framework (see
tests/test_ask.py's docstring); a local HTTP server stands in for Hugging
Face, and SNAP_USER_COMMON points the voices folder at a temp dir.

Run directly:

    python3 tests/test_voices.py
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scriptures import paths, tts  # noqa: E402
from scriptures.voice_download import VoiceDownloader  # noqa: E402

MODEL = os.urandom(300_000)  # big enough to arrive in several chunks
CONFIG = b'{"audio": {"sample_rate": 22050}}'


class _Server:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = server.files.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}/voices"

    def close(self) -> None:
        self.httpd.shutdown()


class _Env:
    """A temp voices folder, a fake server, and one fake voice in the registry."""

    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="scriptures-voices-test-"))
        self.saved_env = os.environ.get("SNAP_USER_COMMON")
        os.environ["SNAP_USER_COMMON"] = str(self.tmp)
        self.server = _Server()
        self.saved = (tts.VOICES, tts.VOICE_BASE_URL)
        self.voice = replace(
            tts.VOICES[0], key="xx_XX-test-medium", source="xx/test",
            model_sha256=hashlib.sha256(MODEL).hexdigest(), model_size=len(MODEL),
            config_sha256=hashlib.sha256(CONFIG).hexdigest(), config_size=len(CONFIG),
        )
        tts.VOICES = [self.voice]
        tts.VOICE_BASE_URL = self.server.base
        self.serve(MODEL, CONFIG)

    def serve(self, model: bytes | None, config: bytes | None) -> None:
        self.server.files.clear()
        for suffix, body in ((".onnx", model), (".onnx.json", config)):
            if body is not None:
                self.server.files[f"/voices/xx/test/{self.voice.key}{suffix}"] = body

    def download(self, cancel_after_progress: bool = False) -> dict:
        downloader = VoiceDownloader()
        result: dict = {"progress": []}
        loop = QEventLoop()

        def on_progress(_key, received, total):
            result["progress"].append((received, total))
            if cancel_after_progress and len(result["progress"]) == 1:
                downloader.cancel()

        downloader.progress.connect(on_progress)
        downloader.finished.connect(lambda key, ok, msg: (result.update(ok=ok, message=msg), loop.quit()))
        QTimer.singleShot(15_000, loop.quit)
        downloader.download(self.voice.key)
        loop.exec()
        QApplication.processEvents()
        return result

    def leftovers(self) -> list[str]:
        folder = paths.voices_dir()
        return sorted(p.name for p in folder.iterdir()) if folder.exists() else []

    def close(self) -> None:
        tts.VOICES, tts.VOICE_BASE_URL = self.saved
        if self.saved_env is None:
            os.environ.pop("SNAP_USER_COMMON", None)
        else:
            os.environ["SNAP_USER_COMMON"] = self.saved_env
        self.server.close()
        shutil.rmtree(self.tmp, ignore_errors=True)


def test_download_verify_and_remove() -> None:
    env = _Env()
    try:
        key = env.voice.key
        assert paths.voices_dir() == env.tmp / "voices"
        assert not tts.is_voice_installed(key)
        result = env.download()
        assert result["ok"], result
        assert result["progress"][-1] == (len(MODEL) + len(CONFIG),) * 2
        assert tts.is_voice_installed(key) and tts.is_removable(key)
        assert tts.model_path(key).read_bytes() == MODEL
        assert env.leftovers() == [f"{key}.onnx", f"{key}.onnx.json"]  # no .part files
        tts.remove_voice(key)
        assert not tts.is_voice_installed(key) and env.leftovers() == []
        print("test_download_verify_and_remove: PASSED")
    finally:
        env.close()


def test_corrupt_missing_and_cancelled_downloads_leave_nothing() -> None:
    env = _Env()
    try:
        key = env.voice.key
        env.serve(MODEL[:-1] + b"x", CONFIG)  # wrong checksum
        result = env.download()
        assert not result["ok"] and "didn't match" in result["message"], result
        assert env.leftovers() == [], env.leftovers()

        env.serve(None, CONFIG)  # model missing (404)
        result = env.download()
        assert not result["ok"] and "Couldn't download" in result["message"], result
        assert env.leftovers() == [], env.leftovers()

        env.serve(MODEL, CONFIG)
        result = env.download(cancel_after_progress=True)
        assert result["ok"] is False and result["message"] == "", result
        assert env.leftovers() == [] and not tts.is_voice_installed(key)
        print("test_corrupt_missing_and_cancelled_downloads_leave_nothing: PASSED")
    finally:
        env.close()


def test_dialog_downloads_the_requested_voice() -> None:
    from scriptures.ui.voices_dialog import VoicesDialog

    env = _Env()
    try:
        key = env.voice.key
        dialog = VoicesDialog(start_key=key)
        changed = []
        dialog.voices_changed.connect(lambda: changed.append(True))
        status, button = dialog._rows[key]
        assert button.text() == "Cancel"
        loop = QEventLoop()
        dialog._downloader.finished.connect(lambda *_: QTimer.singleShot(0, loop.quit))
        QTimer.singleShot(15_000, loop.quit)
        loop.exec()
        assert changed and status.text() == "Downloaded" and button.text() == "Remove"
        button.click()
        assert status.text() == "Not downloaded" and not tts.is_voice_installed(key)
        print("test_dialog_downloads_the_requested_voice: PASSED")
    finally:
        env.close()


def test_listen_is_opt_in_and_the_welcome_window() -> None:
    from scriptures import data_access as da
    from scriptures.db import connect
    from scriptures.ui import main_window as mw
    from scriptures.ui.welcome_dialog import WelcomeDialog

    tmp = Path(tempfile.mkdtemp(prefix="scriptures-welcome-test-"))
    try:
        shutil.copy(PROJECT_ROOT / "data" / "scriptures.db", tmp / "s.db")
        conn = connect(tmp / "s.db")
        window = mw.MainWindow(conn)
        chapter_id = conn.execute(
            "SELECT c.id FROM chapters c JOIN books b ON b.id = c.book_id "
            "WHERE b.name = 'Helaman' AND c.chapter_number = 1"
        ).fetchone()[0]
        volume, testament, book, _ = da.get_chapter_location(conn, chapter_id)
        window._on_chapter_clicked(volume, testament, book, chapter_id)
        view = window._current_reading_view
        # Off until the user opts in.
        assert view._listen_btn.isHidden() and not window._listen_action.isChecked()
        window._listen_action.trigger()
        assert not view._listen_btn.isHidden()
        assert da.get_setting(conn, mw.LISTEN_ENABLED_SETTING) == "true"
        window._listen_action.trigger()
        assert view._listen_btn.isHidden()

        # The Welcome window shows at startup until "don't show again".
        shown = []
        window.show_welcome = lambda: shown.append(True)
        window.maybe_show_welcome()
        assert shown == [True]
        da.set_setting(conn, mw.WELCOME_DONT_SHOW_SETTING, "true")
        window.maybe_show_welcome()
        assert shown == [True]

        # Its steps: the Listen switch drives the same setting; reaching
        # the last step switches on "don't show again".
        listen, volumes = [], []
        dialog = WelcomeDialog(
            listen_enabled=False, set_listen_enabled=listen.append,
            open_ai_wizard=lambda: None, ai_configured=lambda: False,
            volume_shown=lambda slug: False, set_volume_shown=lambda slug, shown: volumes.append((slug, shown)),
            dont_show_again=False,
        )
        assert not dialog.dont_show_again() and not dialog._back.isEnabled()
        dialog._on_next()
        dialog._listen_toggle.setChecked(True)
        assert listen == [True]
        # The additional books start off; each switch drives its own setting.
        dialog._on_next()
        assert not any(t.isChecked() for t in dialog._volume_toggles.values())
        dialog._volume_toggles["apocrypha"].setChecked(True)
        assert volumes == [("apocrypha", True)]
        dialog._on_next()
        assert dialog._ai_status.text() == "Not set up yet"
        dialog._on_next()
        assert dialog._next.text() == "Finish" and dialog.dont_show_again()
        print("test_listen_is_opt_in_and_the_welcome_window: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_download_verify_and_remove()
    test_corrupt_missing_and_cancelled_downloads_leave_nothing()
    test_dialog_downloads_the_requested_voice()
    test_listen_is_opt_in_and_the_welcome_window()
    print("All voice tests passed.")
