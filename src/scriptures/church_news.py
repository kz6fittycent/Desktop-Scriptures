"""Optional, opt-in Church News headline (see main_window.py's landing
page and the "Show Church News Headline" toggle under the View menu).

Off by default - nothing here ever runs unless the user turns it on.
This is, deliberately, the only place in the app that makes a network
call automatically rather than in direct response to something the user
just asked for (a sync, an AI question) - which is exactly why it's
opt-in rather than on by default, unlike everything else here.

Fetches only the single latest headline from Church News' own public
RSS feed (thechurchnews.com/rss/latest.rss) - title, byline, and a link
to the full story. Never the story's own text: the app links out to the
real page, the same "metadata only, never the source's own copyrighted
content" pattern citations.py's General Conference talk data already
follows.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

FEED_URL = "https://www.thechurchnews.com/rss/latest.rss"

_DC_CREATOR = "{http://purl.org/dc/elements/1.1/}creator"


@dataclass(frozen=True)
class NewsHeadline:
    title: str
    link: str
    byline: str  # e.g. "Madison Gay · September 22, 2026" - already formatted, may be ""


def _format_byline(creator: str, pub_date_rfc822: str) -> str:
    parts = []
    if creator:
        parts.append(creator)
    if pub_date_rfc822:
        try:
            parts.append(parsedate_to_datetime(pub_date_rfc822).strftime("%B %-d, %Y"))
        except (TypeError, ValueError):
            pass  # an unparseable date just isn't shown - not worth failing the whole fetch over
    return " · ".join(parts)


def _parse_latest_headline(raw_xml: bytes) -> NewsHeadline | None:
    """The single newest <item> in the feed - it's already sorted
    newest-first, same as every RSS feed. None if the feed is empty or
    doesn't parse as XML at all (a transient CDN/maintenance page
    instead of the real feed, say) - a malformed feed should surface as
    "couldn't load", not a crash."""
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return None
    item = root.find("./channel/item")
    if item is None:
        return None
    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()
    if not title or not link:
        return None
    byline = _format_byline(
        (item.findtext(_DC_CREATOR) or "").strip(), (item.findtext("pubDate") or "").strip()
    )
    return NewsHeadline(title=title, link=link, byline=byline)


class ChurchNewsFetcher(QObject):
    """Fetches just the latest headline from Church News' own RSS feed.
    `succeeded(NewsHeadline)` or `failed(str)` fires exactly once - keep
    a reference to this object until it does (same reasoning as
    ai_client.py's ConnectionTester)."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply = self._manager.get(QNetworkRequest(QUrl(FEED_URL)))
        self._reply.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        reply = self._reply
        if reply.error() != QNetworkReply.NetworkError.NoError:
            message = reply.errorString()
            reply.deleteLater()
            self.failed.emit(message)
            return
        raw = bytes(reply.readAll())
        reply.deleteLater()
        headline = _parse_latest_headline(raw)
        if headline is None:
            self.failed.emit("Couldn't read the Church News feed.")
            return
        self.succeeded.emit(headline)
