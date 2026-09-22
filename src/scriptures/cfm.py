"""Optional, opt-in Come Follow Me helper (see main_window.py's landing
page and the "Show Come Follow Me Helper" toggle under the View menu).

Off by default - nothing here ever runs unless the user turns it on,
same policy as church_news.py (see its own module docstring for why).

Parses the current year's Come Follow Me manual page on
churchofjesuschrist.org to find whichever week's lesson covers today's
date, and shows just that week's date range and scripture block - never
the lesson's own text, only a link out to read it there (the same
"metadata only, never the source's own copyrighted content" pattern
church_news.py and citations.py's General Conference data both follow).

MANUAL_URL is specific to one calendar year's manual - the Church cycles
through the four standard works yearly (Old Testament, New Testament,
Book of Mormon, Doctrine and Covenants, and back around), publishing a
new manual, at a new URL, each January. It goes stale every year and
needs updating by hand, the same as this app's other fixed external
links (see main_window.py's BOOK_OF_MORMON_SHARE_URL,
BYU_CITATION_INDEX_URL, etc.) - deliberately not something the app tries
to auto-discover.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

# Update every January when the Church publishes the next year's manual.
MANUAL_URL = (
    "https://www.churchofjesuschrist.org/study/manual/"
    "come-follow-me-for-home-and-church-old-testament-2026?lang=eng"
)

_SITE_ROOT = "https://www.churchofjesuschrist.org"

# Each week is a server-rendered <li data-content-type="chapter"
# data-date-end="YYYY-MM-DD" data-date-start="YYYY-MM-DD"> - attribute
# order confirmed against the real page (date-end before date-start).
_WEEK_RE = re.compile(
    r'<li data-content-type="chapter" data-date-end="(\d{4}-\d{2}-\d{2})" '
    r'data-date-start="(\d{4}-\d{2}-\d{2})">'
)
_HREF_RE = re.compile(r'<a href="([^"]+)"')
_DATE_LABEL_RE = re.compile(r'<p class="primaryMeta">([^<]+)</p>')
_SCRIPTURE_BLOCK_RE = re.compile(r'<p class="title">([^<]+)</p>')

# How far past each week's opening <li> tag to look for its href/date
# label/scripture block - comfortably past where they land in practice,
# without scanning so far it could cross into the next week's own <li>.
_SEARCH_WINDOW = 2000


@dataclass(frozen=True)
class CfmLesson:
    date_label: str  # e.g. "September 21-27", exactly as the manual displays it
    scripture_block: str  # e.g. "Isaiah 13-14; 22; 24-30; 35"
    link: str


def _parse_current_week(html: str, today: date) -> CfmLesson | None:
    """Scans every week's list entry in the manual page for the one
    whose date range contains `today` - None if the page doesn't parse
    as expected, or if today falls outside every week the page lists
    (e.g. MANUAL_URL hasn't been updated yet for a new year)."""
    for match in _WEEK_RE.finditer(html):
        date_end_str, date_start_str = match.groups()
        try:
            week_start = date.fromisoformat(date_start_str)
            week_end = date.fromisoformat(date_end_str)
        except ValueError:
            continue
        if not (week_start <= today <= week_end):
            continue
        window = html[match.end() : match.end() + _SEARCH_WINDOW]
        href_match = _HREF_RE.search(window)
        label_match = _DATE_LABEL_RE.search(window)
        block_match = _SCRIPTURE_BLOCK_RE.search(window)
        if not (href_match and label_match and block_match):
            return None
        link = href_match.group(1)
        if link.startswith("/"):
            link = _SITE_ROOT + link
        return CfmLesson(
            date_label=label_match.group(1),
            scripture_block=block_match.group(1),
            link=link,
        )
    return None


class CfmFetcher(QObject):
    """Fetches the manual page and picks out this week's lesson.
    `succeeded(CfmLesson)` or `failed(str)` fires exactly once - keep a
    reference to this object until it does (same reasoning as
    ai_client.py's ConnectionTester)."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply = self._manager.get(QNetworkRequest(QUrl(MANUAL_URL)))
        self._reply.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        reply = self._reply
        if reply.error() != QNetworkReply.NetworkError.NoError:
            message = reply.errorString()
            reply.deleteLater()
            self.failed.emit(message)
            return
        raw = bytes(reply.readAll()).decode("utf-8", errors="replace")
        reply.deleteLater()
        lesson = _parse_current_week(raw, date.today())
        if lesson is None:
            self.failed.emit("Couldn't find this week's lesson in the manual page.")
            return
        self.succeeded.emit(lesson)
