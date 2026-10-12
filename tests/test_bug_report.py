"""Standalone test script for src/scriptures/app_log.py and bug_report.py -
the log Help → Report a Bug sends, and the report built from it. No test
framework (see tests/test_ask.py's docstring); the one Qt check runs on
the offscreen platform.

Run directly:

    python3 tests/test_bug_report.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Logs go to $XDG_CACHE_HOME when running from source (app_log.log_dir) -
# point that at a scratch folder before anything is imported.
_TMP = Path(tempfile.mkdtemp(prefix="scriptures-bug-report-test-"))
os.environ["XDG_CACHE_HOME"] = str(_TMP)
os.environ.pop("SNAP_USER_COMMON", None)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from scriptures import app_log, bug_report  # noqa: E402


def _raise_in_scriptures_code():
    return {}["missing"]


def test_scrub_removes_home_folders() -> None:
    text = (
        'File "/home/alice/snap/desktop-scriptures/x1/app.py", line 3\n'
        "/Users/bob/Library/x and C:\\Users\\Carol\\AppData\\y"
    )
    scrubbed = bug_report.scrub(text)
    for name in ("alice", "bob", "Carol"):
        assert name not in scrubbed, scrubbed
    assert "~/snap/desktop-scriptures/x1/app.py" in scrubbed
    print("test_scrub_removes_home_folders: PASSED")


def test_fingerprint_ignores_line_numbers() -> None:
    try:
        _raise_in_scriptures_code()
    except KeyError:
        exc_type, _, tb = sys.exc_info()
    summary, fingerprint = app_log.describe_exception(exc_type, tb)
    assert summary == "KeyError in test_bug_report.py:_raise_in_scriptures_code", summary
    assert len(fingerprint) == 12
    # Same type, file and function -> same fingerprint, whatever the line.
    again, fingerprint_again = app_log.describe_exception(exc_type, tb)
    assert fingerprint == fingerprint_again
    _, other = app_log.describe_exception(ValueError, tb)
    assert other != fingerprint
    print("test_fingerprint_ignores_line_numbers: PASSED")


def test_latest_error_only_when_recent() -> None:
    now = datetime(2026, 10, 12, 12, 0, 0)
    log = (
        "2026-10-01 09:00:00 ERROR scriptures: Uncaught OldError in a.py:f [fp-aaaaaaaaaaaa]\n"
        "Traceback...\n"
        "2026-10-11 09:00:00 ERROR scriptures: Uncaught KeyError in b.py:g [fp-bbbbbbbbbbbb]\n"
        "Traceback...\n"
        "2026-10-11 09:05:00 INFO scriptures: something else\n"
    )
    error = app_log.latest_error(log, now)
    assert error is not None and error.fingerprint == "bbbbbbbbbbbb"
    assert error.summary == "KeyError in b.py:g"
    assert app_log.latest_error(log, now + timedelta(days=30)) is None
    assert app_log.latest_error("no errors here", now) is None
    print("test_latest_error_only_when_recent: PASSED")


def test_recent_crashes_skips_old_and_clean_sessions() -> None:
    now = datetime(2026, 10, 12, 12, 0, 0)
    text = (
        "\n=== 2026-09-01 10:00:00 session start, version 2.3.0\n"
        "Fatal Python error: Segmentation fault\nOLD CRASH\n"
        "\n=== 2026-10-11 10:00:00 session start, version 2.3.1\n"
        "\n=== 2026-10-12 10:00:00 session start, version 2.3.2\n"
        "Fatal Python error: Segmentation fault\nNEW CRASH\n"
    )
    kept = app_log.recent_crashes(text, now)
    assert "NEW CRASH" in kept and "OLD CRASH" not in kept
    assert "2.3.1" not in kept
    print("test_recent_crashes_skips_old_and_clean_sessions: PASSED")


def test_classify_response() -> None:
    assert bug_report.classify_response(201, b'{"issue":5,"duplicate":false}') == "sent"
    assert bug_report.classify_response(200, b'{"issue":5,"duplicate":true}') == "duplicate"
    assert bug_report.classify_response(400, b"{}") == "rejected"
    for status in (0, 429, 502, 503):
        assert bug_report.classify_response(status, b"") == "failed"
    print("test_classify_response: PASSED")


def test_uncaught_exception_is_logged_and_reported() -> None:
    """The real path: setup() installs the hooks, an exception goes
    uncaught, and the report built afterwards names it."""
    app_log.setup()
    try:
        _raise_in_scriptures_code()
    except KeyError:
        app_log.log_exception(*sys.exc_info())

    report = bug_report.build_report("  It broke when I clicked.  ")
    assert report["description"] == "It broke when I clicked."
    assert report["version"]
    assert report["platform"].endswith("(from source)"), report["platform"]
    assert report["error"] == "KeyError in test_bug_report.py:_raise_in_scriptures_code"
    assert len(report["fingerprint"]) == 12
    assert "Traceback" in report["log"] and "Desktop Scriptures" in report["log"]
    assert str(Path.home()) not in report["log"]

    empty = bug_report.build_report("")
    assert empty["description"] == ""
    print("test_uncaught_exception_is_logged_and_reported: PASSED")


def test_exception_in_qt_slot_reaches_the_log() -> None:
    from PySide6.QtCore import QCoreApplication, QTimer

    app = QCoreApplication.instance() or QCoreApplication([])
    app_log.install_qt_message_handler()

    def slot() -> None:
        raise RuntimeError("from a Qt slot")

    QTimer.singleShot(0, slot)
    QTimer.singleShot(50, app.quit)
    app.exec()
    log = (app_log.log_dir() / app_log.LOG_NAME).read_text(encoding="utf-8")
    assert "Uncaught RuntimeError in test_bug_report.py:slot" in log, log[-2000:]
    print("test_exception_in_qt_slot_reaches_the_log: PASSED")


def test_pending_reports_capped_and_expired() -> None:
    for n in range(bug_report.PENDING_MAX_FILES + 2):
        assert bug_report.save_pending({"description": str(n)}) is not None
    pending = bug_report.pending_reports()
    assert len(pending) == bug_report.PENDING_MAX_FILES, len(pending)
    newest = json.loads(pending[-1].read_text())
    assert newest["description"] == str(bug_report.PENDING_MAX_FILES + 1)

    old = pending[0]
    stale = time.time() - (bug_report.PENDING_MAX_DAYS + 1) * 86400
    os.utime(old, (stale, stale))
    assert old not in bug_report.pending_reports()
    assert not old.exists()
    print("test_pending_reports_capped_and_expired: PASSED")


if __name__ == "__main__":
    try:
        test_scrub_removes_home_folders()
        test_fingerprint_ignores_line_numbers()
        test_latest_error_only_when_recent()
        test_recent_crashes_skips_old_and_clean_sessions()
        test_classify_response()
        test_uncaught_exception_is_logged_and_reported()
        test_exception_in_qt_slot_reaches_the_log()
        test_pending_reports_capped_and_expired()
        print("All bug report tests passed.")
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
