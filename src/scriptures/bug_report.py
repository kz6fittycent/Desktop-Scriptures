"""Help → Report a Bug: sends the user's (optional) description with the
app's log (app_log.py) to the project's relay, which files it as a GitHub
issue - so the user needs no GitHub account. The relay's source and setup
are in relay/bug-report/.

The user only ever sees the description box: the log is gathered here
and attached without being shown. Before it leaves the machine, home-
folder paths (which contain the user's name) are replaced with "~".

Nothing is sent unless the user clicks Submit. If sending fails (offline,
the relay busy or down), the report is kept in log_dir()/pending and
retried on the next few launches - send_pending() - so the user never has
to do anything more. Reports older than PENDING_MAX_DAYS are dropped.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from scriptures import __version__, app_log

RELAY_URL = "https://desktop-scriptures-bug-report.jimmy-tigert.workers.dev/report"
REQUEST_TIMEOUT_MS = 30_000
# The relay trims to GitHub's issue size limit itself; this just keeps the
# upload reasonable. The newest lines are the ones kept.
MAX_LOG_CHARS = 45_000
MAX_DESCRIPTION_CHARS = 5000
PENDING_MAX_DAYS = 30
PENDING_MAX_FILES = 5

# /home/<name>, /Users/<name>, C:\Users\<name> - and a snap's
# /home/<name>/snap/... falls under the first.
_HOME_RE = re.compile(r"(/home/|/Users/|[A-Za-z]:\\Users\\)[^/\\\s\"']+")


def scrub(text: str) -> str:
    """Home-folder paths become "~", so the user's account name isn't sent."""
    return _HOME_RE.sub("~", text)


def build_report(description: str) -> dict:
    """The JSON the relay expects. `error` and `fingerprint` name the most
    recent uncaught exception, when there's one from the last few days -
    the relay files a repeat of a known fingerprint as a comment on its
    existing issue rather than a new one."""
    log_text = scrub(app_log.read_logs(MAX_LOG_CHARS))
    report = {
        "description": description.strip()[:MAX_DESCRIPTION_CHARS],
        "version": __version__,
        "platform": app_log.platform_summary(),
        "log": log_text,
    }
    error = app_log.latest_error(log_text)
    if error is not None:
        report["error"] = error.summary[:200]
        report["fingerprint"] = error.fingerprint
    return report


def pending_dir() -> Path:
    return app_log.log_dir() / "pending"


def save_pending(report: dict) -> Path | None:
    """Keeps a report that couldn't be sent, for send_pending() to retry.
    At most PENDING_MAX_FILES are kept (the oldest go first)."""
    folder = pending_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{time.time_ns():020d}-{uuid.uuid4().hex[:8]}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
    except OSError:
        return None
    for old in pending_reports()[:-PENDING_MAX_FILES]:
        old.unlink(missing_ok=True)
    return path


def pending_reports() -> list[Path]:
    """Saved reports, oldest first; expired ones are deleted along the way."""
    folder = pending_dir()
    if not folder.is_dir():
        return []
    cutoff = time.time() - PENDING_MAX_DAYS * 86400
    kept = []
    for path in sorted(folder.glob("*.json")):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                continue
        except OSError:
            continue
        kept.append(path)
    return kept


class BugReporter(QObject):
    """Sends one report. `finished(result)` fires once, with one of:
    "sent", "duplicate" (added to an existing report of the same problem),
    "rejected" (the relay refused the report itself - retrying won't help),
    or "failed" (offline, timed out, or the relay is busy - worth retrying)."""

    finished = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None

    def send(self, report: dict) -> None:
        request = QNetworkRequest(QUrl(RELAY_URL))
        request.setTransferTimeout(REQUEST_TIMEOUT_MS)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setRawHeader(b"User-Agent", f"DesktopScriptures/{__version__}".encode())
        self._reply = self._manager.post(request, QByteArray(json.dumps(report).encode("utf-8")))
        self._reply.finished.connect(self._done)

    def _done(self) -> None:
        reply, self._reply = self._reply, None
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
        body = bytes(reply.readAll())
        reply.deleteLater()
        self.finished.emit(classify_response(int(status), body))


def classify_response(status: int, body: bytes) -> str:
    if status in (200, 201):
        try:
            duplicate = bool(json.loads(body).get("duplicate"))
        except (ValueError, AttributeError):
            duplicate = False
        return "duplicate" if duplicate else "sent"
    if status == 400:
        return "rejected"
    return "failed"  # 0 (no connection / timeout), 429, 5xx


class PendingSender(QObject):
    """Retries saved reports one at a time (app.py calls this a little
    while after startup). Sent and rejected ones are deleted; the rest
    stay for next time. `finished` fires when done."""

    finished = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._reporter = BugReporter(self)
        self._reporter.finished.connect(self._on_result)
        self._queue: list[Path] = []
        self._current: Path | None = None

    def start(self) -> None:
        self._queue = pending_reports()
        self._next()

    def _next(self) -> None:
        while self._queue:
            self._current = self._queue.pop(0)
            try:
                report = json.loads(self._current.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._current.unlink(missing_ok=True)
                continue
            self._reporter.send(report)
            return
        self.finished.emit()

    def _on_result(self, result: str) -> None:
        if result == "failed":
            app_log.log.info("Saved bug report still couldn't be sent; will retry next launch")
            self.finished.emit()  # still offline - don't hammer the rest
            return
        self._current.unlink(missing_ok=True)
        self._next()
