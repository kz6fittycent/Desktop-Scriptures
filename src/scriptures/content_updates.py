"""Keeps General Conference and Ensign/Liahona citations current without
an app update.

GitHub harvests both weekly (.github/workflows/refresh-*-citations.yml)
and publishes the results on this repository's "citations-data" release:
each file gzipped (FILE.gz) with its SHA-256 beside it (FILE.gz.sha256).
About once a day (MainWindow, a few seconds after startup) the app reads
those small .sha256 files. When one differs from what it last downloaded,
it fetches the .gz and keeps it only if the checksum matches, it
decompresses to the expected shape, and it isn't much smaller than the
data in use - a bad harvest never replaces good data. Downloaded files
live in the user's data folder (citation_updates/) and win over the
copies bundled with the app only when they're newer (their "_harvested"
date), so an app update that bundles newer data takes over again.

On by default; Menu → View → Download New Talks and Articles turns it
off. Only GitHub is contacted - never the Church's or BYU's sites.
Running from a source checkout (no user data folder) it does nothing:
there, data/ is the repository's own copy.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from scriptures.citation_files import FILES, check_replacement, harvested_date
from scriptures.paths import DATA_DIR, user_data_dir

RELEASE_URL = "https://github.com/kz6fittycent/Desktop-Scriptures/releases/download/citations-data"
CHECK_INTERVAL_HOURS = 20
REQUEST_TIMEOUT_MS = 60_000


def updates_dir() -> Path | None:
    base = user_data_dir()
    return None if base is None else base / "citation_updates"


def citation_path(name: str) -> Path:
    """The copy of a citation file to use: the downloaded one if it's at
    least as new as the bundled one, otherwise the bundled one."""
    bundled = DATA_DIR / name
    folder = updates_dir()
    if folder is not None:
        downloaded = folder / name
        if downloaded.exists() and harvested_date(downloaded) >= harvested_date(bundled):
            return downloaded
    return bundled


class CitationUpdater(QObject):
    """One check of every file in FILES, in turn. `finished(updated,
    problems)` fires once: the file names replaced, and any messages."""

    finished = Signal(list, list)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)  # one for every request
        self._queue: list[str] = []
        self._updated: list[str] = []
        self._problems: list[str] = []
        self._reply: QNetworkReply | None = None
        self._name = ""
        self._expected_sha = ""

    def check(self) -> None:
        folder = updates_dir()
        if folder is None:
            self.finished.emit([], [])
            return
        folder.mkdir(parents=True, exist_ok=True)
        self._queue = list(FILES)
        self._next()

    def _get(self, url: str, handler) -> None:
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(REQUEST_TIMEOUT_MS)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,  # GitHub redirects to its CDN
        )
        self._handler = handler
        self._reply = self._manager.get(request)
        self._reply.finished.connect(self._done)

    def _done(self) -> None:
        reply, self._reply = self._reply, None
        handler = self._handler
        ok = reply.error() == QNetworkReply.NetworkError.NoError
        body = bytes(reply.readAll()) if ok else b""
        error = reply.errorString()
        reply.deleteLater()
        if not ok:
            self._problems.append(f"{self._name}: {error}")
            self._next()
            return
        handler(body)

    def _next(self) -> None:
        if not self._queue:
            self.finished.emit(self._updated, self._problems)
            return
        self._name = self._queue.pop(0)
        self._get(f"{RELEASE_URL}/{self._name}.gz.sha256", self._on_checksum)

    def _on_checksum(self, body: bytes) -> None:
        sha = body.decode("ascii", "replace").split()[0].lower() if body.strip() else ""
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            self._problems.append(f"{self._name}: unreadable checksum")
            self._next()
            return
        known = updates_dir() / f"{self._name}.gz.sha256"
        if known.exists() and known.read_text().strip() == sha:
            self._next()  # unchanged since the last download
            return
        self._expected_sha = sha
        self._get(f"{RELEASE_URL}/{self._name}.gz", self._on_data)

    def _on_data(self, body: bytes) -> None:
        name, folder = self._name, updates_dir()
        try:
            if hashlib.sha256(body).hexdigest() != self._expected_sha:
                raise ValueError("checksum mismatch")
            data = json.loads(gzip.decompress(body))
            reason = check_replacement(name, data, citation_path(name))
            if reason:
                raise ValueError(reason)
        except (ValueError, OSError, EOFError) as exc:
            self._problems.append(f"{name}: not used ({exc})")
            self._next()
            return
        part = folder / f"{name}.part"
        part.write_bytes(gzip.decompress(body))
        part.replace(folder / name)
        (folder / f"{name}.gz.sha256").write_text(self._expected_sha)
        self._updated.append(name)
        self._next()
