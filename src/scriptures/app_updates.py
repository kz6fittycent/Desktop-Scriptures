"""Tells Windows and macOS users when a newer release is out.

Those builds (PyInstaller, see packaging/) don't update themselves the way
the snap does, and their users may not use Winget or Homebrew. About once
a day (MainWindow, a little while after startup) the app asks GitHub for
this project's latest release - GitHub's /releases/latest skips test
pre-releases - and, when it's newer than the running app, shows an
"Update available" button on the menu bar. That opens one dialog with the
release notes and the download link. Nothing is downloaded or installed:
the builds aren't code-signed, so the user installs the new one themselves.

Only frozen builds check (paths.is_frozen()); the snap and a source
checkout never do. On by default; Menu → View → Check for App Updates
turns it off. Only GitHub is contacted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from scriptures import __version__

LATEST_RELEASE_API = "https://api.github.com/repos/kz6fittycent/Desktop-Scriptures/releases/latest"
RELEASES_PAGE = "https://github.com/kz6fittycent/Desktop-Scriptures/releases/latest"
CHECK_INTERVAL_HOURS = 20
REQUEST_TIMEOUT_MS = 30_000


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    notes: str

    def to_json(self) -> str:
        return json.dumps({"version": self.version, "url": self.url, "notes": self.notes})

    @staticmethod
    def from_json(text: str) -> "Release | None":
        try:
            data = json.loads(text)
            return Release(str(data["version"]), str(data["url"]), str(data.get("notes", "")))
        except (ValueError, KeyError, TypeError):
            return None


def version_key(version: str) -> tuple[int, ...]:
    """(2, 3, 4) for "2.3.4" or "v2.3.4". Unpushed work counts a fourth
    number (2.3.3.2), which sorts before the 2.3.4 release it leads to."""
    parts = []
    for piece in version.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def is_newer(candidate: str, current: str = __version__) -> bool:
    new, old = version_key(candidate), version_key(current)
    return bool(new) and new > old


def parse_latest_release(body: bytes) -> Release | None:
    """The release in a GitHub /releases/latest response, or None for
    anything unexpected (a draft, a pre-release, a tag that isn't vX.Y.Z)."""
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name") or "")
    if not tag.startswith("v") or len(version_key(tag)) < 3:
        return None
    url = str(data.get("html_url") or RELEASES_PAGE)
    if not url.startswith("https://github.com/"):
        url = RELEASES_PAGE
    return Release(tag[1:], url, str(data.get("body") or "").strip())


class ReleaseChecker(QObject):
    """One request for the latest release. `finished(ok, release)` fires
    once: `release` is a Release, or None if there isn't a usable one."""

    finished = Signal(bool, object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        request = QNetworkRequest(QUrl(LATEST_RELEASE_API))
        request.setTransferTimeout(REQUEST_TIMEOUT_MS)
        # GitHub's API turns away requests without one.
        request.setRawHeader(b"User-Agent", f"Desktop-Scriptures/{__version__}".encode())
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        self._reply = self._manager.get(request)
        self._reply.finished.connect(self._done)

    def _done(self) -> None:
        reply = self._reply
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if reply.error() == QNetworkReply.NetworkError.NoError:
            self.finished.emit(True, parse_latest_release(bytes(reply.readAll())))
        elif status == 404:  # no release published yet - a valid answer
            self.finished.emit(True, None)
        else:
            self.finished.emit(False, None)
        reply.deleteLater()
