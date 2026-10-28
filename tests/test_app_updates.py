"""Standalone test script for src/scriptures/app_updates.py and the main
window's "Update Available" button. No test framework (see
tests/test_ask.py's docstring); offscreen Qt, a local stand-in for
GitHub's API, and a copy of the shipped data/scriptures.db.

Run directly:

    python3 tests/test_app_updates.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scriptures import __version__, app_updates  # noqa: E402
from scriptures.app_updates import Release, is_newer, parse_latest_release, version_key  # noqa: E402
from scriptures.data_access import set_setting  # noqa: E402
from scriptures.db import connect  # noqa: E402


def _release_json(**overrides) -> bytes:
    data = {
        "tag_name": "v9.9.9",
        "html_url": "https://github.com/kz6fittycent/Desktop-Scriptures/releases/tag/v9.9.9",
        "body": "Windows 11: download the -setup.exe.",
        "draft": False,
        "prerelease": False,
    }
    data.update(overrides)
    return json.dumps(data).encode()


def test_versions() -> None:
    assert version_key("v2.3.4") == (2, 3, 4)
    assert version_key("2.3.3.2") == (2, 3, 3, 2)
    assert is_newer("2.3.4", "2.3.3.2")  # unpushed work sorts before its release
    assert is_newer("2.4.0", "2.3.9")
    assert is_newer("2.3.10", "2.3.9")
    assert not is_newer("2.3.4", "2.3.4")
    assert not is_newer("2.3.4", "2.3.4.1")
    assert not is_newer("2.3.3", "2.3.4")
    assert not is_newer("", "2.3.4")
    print("test_versions: PASSED")


def test_parse_latest_release() -> None:
    release = parse_latest_release(_release_json())
    assert release == Release(
        "9.9.9",
        "https://github.com/kz6fittycent/Desktop-Scriptures/releases/tag/v9.9.9",
        "Windows 11: download the -setup.exe.",
    )
    assert Release.from_json(release.to_json()) == release
    assert parse_latest_release(_release_json(draft=True)) is None
    assert parse_latest_release(_release_json(prerelease=True)) is None
    assert parse_latest_release(_release_json(tag_name="citations-data")) is None
    assert parse_latest_release(_release_json(tag_name="test-v2.3.4-build10")) is None
    assert parse_latest_release(b"not json") is None
    assert parse_latest_release(b"[]") is None
    # Only ever send the user to GitHub.
    odd = parse_latest_release(_release_json(html_url="https://example.com/evil"))
    assert odd.url == app_updates.RELEASES_PAGE
    assert Release.from_json("") is None and Release.from_json("{}") is None
    print("test_parse_latest_release: PASSED")


def _api_server(status: int, body: bytes) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):  # noqa: N802
            assert self.headers.get("User-Agent", "").startswith("Desktop-Scriptures/")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _check(status: int, body: bytes):
    server = _api_server(status, body)
    original = app_updates.LATEST_RELEASE_API
    app_updates.LATEST_RELEASE_API = f"http://127.0.0.1:{server.server_address[1]}/releases/latest"
    try:
        result = {}
        loop = QEventLoop()
        checker = app_updates.ReleaseChecker()
        checker.finished.connect(lambda ok, release: (result.update(ok=ok, release=release), loop.quit()))
        QTimer.singleShot(10_000, loop.quit)
        loop.exec()
        return result
    finally:
        app_updates.LATEST_RELEASE_API = original
        server.shutdown()


def test_release_checker() -> None:
    found = _check(200, _release_json())
    assert found["ok"] and found["release"].version == "9.9.9", found
    none_yet = _check(404, b'{"message": "Not Found"}')
    assert none_yet == {"ok": True, "release": None}, none_yet
    broken = _check(500, b"")
    assert broken == {"ok": False, "release": None}, broken
    print("test_release_checker: PASSED")


def test_update_button() -> None:
    """Frozen builds show the button for a newer stored release - and only
    then; the snap and source checkouts never do."""
    from scriptures.ui import main_window as mw

    tmp = Path(tempfile.mkdtemp(prefix="scriptures-app-updates-"))
    original_frozen = mw.is_frozen
    try:
        shutil.copy(PROJECT_ROOT / "data" / "scriptures.db", tmp / "s.db")
        conn = connect(tmp / "s.db")
        newer = Release("9.9.9", app_updates.RELEASES_PAGE, "Notes")
        set_setting(conn, mw.APP_UPDATE_LATEST_SETTING, newer.to_json())

        window = mw.MainWindow(conn)
        assert window.update_button.isHidden(), "a source checkout shows no update notice"
        assert not window._app_updates_action.isVisible()
        window.close()

        mw.is_frozen = lambda: True
        window = mw.MainWindow(conn)
        assert not window.update_button.isHidden()
        assert "9.9.9" in window.update_button.toolTip()
        window._set_app_updates(False)
        assert window.update_button.isHidden(), "switched off in View"
        window.close()

        set_setting(conn, mw.APP_UPDATES_SETTING, "true")
        set_setting(conn, mw.APP_UPDATE_LATEST_SETTING, Release(__version__, app_updates.RELEASES_PAGE, "").to_json())
        window = mw.MainWindow(conn)
        assert window.update_button.isHidden(), "same version: nothing to say"
        window.close()
        conn.close()
        print("test_update_button: PASSED")
    finally:
        mw.is_frozen = original_frozen
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_versions()
    test_parse_latest_release()
    test_release_checker()
    test_update_button()
    print("All app update tests passed.")
