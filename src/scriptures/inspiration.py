"""Optional, opt-in Inspirational Message helper (see main_window.py's
landing page and the "Show Inspirational Message" toggle under the View
menu).

Off by default - nothing here ever runs unless the user turns it on,
same policy as church_news.py and cfm.py (see their own module
docstrings for why).

Parses the small "featured message" section on churchofjesuschrist.org's
own homepage (a quote from a Church leader, e.g. "Jesus Christ, Our
Perfect Example" from President Oaks) - just the quote text, author, and
a link out to read more, never anything beyond what's already shown on
the homepage itself.

Unlike cfm.py's manual page, this isn't confirmed to rotate on any fixed
schedule - it's whatever the Church's own site currently features, the
same "show what's there right now" approach church_news.py already
takes with its RSS feed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

HOME_URL = "https://www.churchofjesuschrist.org/?lang=eng"
_SITE_ROOT = "https://www.churchofjesuschrist.org"

_SECTION_RE = re.compile(r'<section class="blockquote">(.*?)</section>', re.DOTALL)
_QUOTE_RE = re.compile(r'<p class="blockquoteText">(.*?)</p>', re.DOTALL)
_LINK_RE = re.compile(r'<a href="([^"]+)"[^>]*class="blockquoteAttribution"')
_AUTHOR_RE = re.compile(r'<div class="blockquoteAuthor">([^<]+)</div>')
_BYLINE_RE = re.compile(r'<div class="blockquoteByline">([^<]+)</div>')


@dataclass(frozen=True)
class InspirationalMessage:
    quote: str
    author: str
    byline: str  # e.g. "Prophet and president of The Church..." - may be ""
    link: str


def _parse_message(html: str) -> InspirationalMessage | None:
    section_match = _SECTION_RE.search(html)
    if section_match is None:
        return None
    block = section_match.group(1)
    quote_match = _QUOTE_RE.search(block)
    link_match = _LINK_RE.search(block)
    author_match = _AUTHOR_RE.search(block)
    if not (quote_match and link_match and author_match):
        return None
    byline_match = _BYLINE_RE.search(block)
    link = link_match.group(1)
    if link.startswith("/"):
        link = _SITE_ROOT + link
    return InspirationalMessage(
        quote=quote_match.group(1).strip().strip("“”"),
        author=author_match.group(1).strip(),
        byline=byline_match.group(1).strip() if byline_match else "",
        link=link,
    )


class InspirationFetcher(QObject):
    """Fetches the homepage and picks out its featured message.
    `succeeded(InspirationalMessage)` or `failed(str)` fires exactly
    once - keep a reference to this object until it does (same reasoning
    as ai_client.py's ConnectionTester)."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply = self._manager.get(QNetworkRequest(QUrl(HOME_URL)))
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
        parsed = _parse_message(raw)
        if parsed is None:
            self.failed.emit("Couldn't find a featured message on the homepage.")
            return
        self.succeeded.emit(parsed)
