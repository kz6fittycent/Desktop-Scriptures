"""The app's own log - what Help → Report a Bug sends along (bug_report.py).

What goes in: one line per session describing the system (version,
platform, Python, Qt), every uncaught exception with its traceback
(including ones raised in Qt slots and background threads), Qt's own
warnings, and anything else logged through the standard `logging` module.
A hard crash (segfault in Qt or a native library) can't be logged from
Python, so `faulthandler` writes its traceback to a separate crash.log.

What never goes in: anything the user wrote - notes, journal entries,
search terms. Nothing here logs them, and nothing should.

The files live in log_dir() and stay small: app.log rotates at 512 KB with
two old copies kept. They're only ever read locally, by bug_report.py,
which scrubs home-folder paths before anything is sent.
"""

from __future__ import annotations

import faulthandler
import hashlib
import logging
import logging.handlers
import os
import platform
import re
import sys
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from scriptures import __version__, paths

LOG_NAME = "app.log"
CRASH_LOG_NAME = "crash.log"
MAX_LOG_BYTES = 512 * 1024
LOG_BACKUPS = 2
# An error older than this isn't assumed to be the one being reported.
RECENT_ERROR_DAYS = 7

log = logging.getLogger("scriptures")

# The marker line logged for each uncaught exception - latest_error()
# finds the most recent one by this pattern.
_UNCAUGHT_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR .*Uncaught (.+?) \[fp-([0-9a-f]{12})\]$",
    re.MULTILINE,
)

_crash_file = None  # kept open for faulthandler for the whole session


def log_dir() -> Path:
    """Beside the user's database in a snap or packaged app; running from
    source, in the per-user cache folder (not the repo)."""
    base = paths.user_data_dir()
    if base is not None:
        return base / "logs"
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache / "desktop-scriptures" / "logs"


def platform_summary() -> str:
    """A short one-line description, e.g. "Ubuntu 24.04.1 LTS (snap, revision 123)"."""
    if sys.platform.startswith("linux"):
        name = _os_release_name() or f"Linux {platform.release()}"
    elif sys.platform == "darwin":
        name = f"macOS {platform.mac_ver()[0]}"
    elif sys.platform == "win32":
        name = f"Windows {platform.release()} ({platform.version()})"
    else:
        name = platform.platform()
    if os.environ.get("SNAP"):
        how = f"snap, revision {os.environ.get('SNAP_REVISION', '?')}"
    elif paths.is_frozen():
        how = "packaged"
    else:
        how = "from source"
    return f"{name} ({how})"


def _os_release_name() -> str | None:
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^PRETTY_NAME="?([^"\n]*)"?$', text, re.MULTILINE)
    return match.group(1) if match else None


def setup() -> None:
    """Called once, first thing in app.py's main(). Never raises - an app
    that can't write its log still has to start."""
    global _crash_file
    try:
        folder = log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            folder / LOG_NAME, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        logging.captureWarnings(True)

        crash_path = folder / CRASH_LOG_NAME
        if crash_path.exists() and crash_path.stat().st_size > MAX_LOG_BYTES:
            crash_path.write_text(_read(crash_path)[-MAX_LOG_BYTES // 2 :], encoding="utf-8")
        _crash_file = open(crash_path, "a", encoding="utf-8")  # noqa: SIM115 - open all session
        _crash_file.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} session start, version {__version__}\n")
        _crash_file.flush()
        faulthandler.enable(file=_crash_file)
    except OSError:
        return

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    log.info(
        "Desktop Scriptures %s started on %s; Python %s",
        __version__,
        platform_summary(),
        platform.python_version(),
    )


def install_qt_message_handler() -> None:
    """Routes Qt's own warnings into the log. Called once the QApplication
    exists (app.py); also still prints them, as Qt would have."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler, qVersion

    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }
    qt_log = logging.getLogger("qt")

    def handler(mode, _context, message) -> None:
        qt_log.log(levels.get(mode, logging.WARNING), message)
        print(message, file=sys.stderr)

    qInstallMessageHandler(handler)
    log.info("Qt %s, platform plugin %s", qVersion(), os.environ.get("QT_QPA_PLATFORM") or "default")


def _excepthook(exc_type, exc, tb) -> None:
    log_exception(exc_type, exc, tb)
    sys.__excepthook__(exc_type, exc, tb)


def _thread_excepthook(args) -> None:
    if args.exc_type is SystemExit:
        return
    log_exception(args.exc_type, args.exc_value, args.exc_traceback, thread=args.thread)
    threading.__excepthook__(args)


def log_exception(exc_type, exc, tb, thread=None) -> None:
    summary, fingerprint = describe_exception(exc_type, tb)
    where = f"Thread: {thread.name}\n" if thread is not None else ""
    details = "".join(traceback.format_exception(exc_type, exc, tb))
    log.error("Uncaught %s [fp-%s]\n%s%s", summary, fingerprint, where, details.rstrip())


def describe_exception(exc_type, tb) -> tuple[str, str]:
    """("KeyError in reading_view.py:_on_click", "3f2a9c01b4de").

    The place is the innermost frame in the app's own code (a crash deep
    inside Qt or the standard library is still filed under the app code
    that called it). The fingerprint hashes the type and that file and
    function - not the line number, which shifts from version to version -
    so the same bug from different users and versions lands on one issue."""
    frames = traceback.extract_tb(tb) if tb is not None else []
    own = [f for f in frames if f"{os.sep}scriptures{os.sep}" in f.filename]
    frame = (own or frames or [None])[-1]
    name = exc_type.__name__ if exc_type is not None else "Error"
    if frame is None:
        place = "unknown"
    else:
        place = f"{Path(frame.filename).name}:{frame.name}"
    fingerprint = hashlib.sha1(f"{name}|{place}".encode()).hexdigest()[:12]
    return f"{name} in {place}", fingerprint


@dataclass(frozen=True)
class LoggedError:
    summary: str
    fingerprint: str
    when: datetime


def latest_error(text: str, now: datetime | None = None) -> LoggedError | None:
    """The most recent uncaught exception in this log text, if it's recent
    enough to be the likely subject of a report."""
    now = now or datetime.now()
    found = None
    for match in _UNCAUGHT_RE.finditer(text):
        found = match
    if found is None:
        return None
    when = datetime.strptime(found.group(1), "%Y-%m-%d %H:%M:%S")
    if now - when > timedelta(days=RECENT_ERROR_DAYS):
        return None
    return LoggedError(found.group(2), found.group(3), when)


def read_logs(max_chars: int) -> str:
    """The newest `max_chars` of the log, oldest rotated file first, then
    the tail of crash.log if a hard crash was recorded. Empty if there's
    no log yet."""
    folder = log_dir()
    parts = []
    for name in (f"{LOG_NAME}.{n}" for n in range(LOG_BACKUPS, 0, -1)):
        parts.append(_read(folder / name))
    parts.append(_read(folder / LOG_NAME))
    text = "".join(parts)[-max_chars:]

    crashes = recent_crashes(_read(folder / CRASH_LOG_NAME))
    if crashes:
        text += "\n--- crash.log ---\n" + crashes[-8000:]
    return text


_SESSION_RE = re.compile(r"^=== (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) session start", re.MULTILINE)


def recent_crashes(text: str, now: datetime | None = None) -> str:
    """The sessions in crash.log that ended in a hard crash within the last
    RECENT_ERROR_DAYS - so an old crash isn't sent with every report."""
    now = now or datetime.now()
    starts = list(_SESSION_RE.finditer(text))
    kept = []
    for i, match in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        block = text[match.start() : end]
        when = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        if "Fatal Python error" in block and now - when <= timedelta(days=RECENT_ERROR_DAYS):
            kept.append(block.strip())
    return "\n".join(kept)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
