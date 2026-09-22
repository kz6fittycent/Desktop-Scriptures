"""Optional, opt-in General Conference reminder (see main_window.py's
startup check and the "Show General Conference Reminder" toggle under
the View menu).

Off by default - nothing here ever runs unless the user turns it on,
same policy as church_news.py, cfm.py, and inspiration.py (see their own
module docstrings for why).

General Conference happens twice a year, always the first Saturday and
Sunday of April and October - reliable enough to compute locally with no
network access at all. That local estimate is used only as a cheap gate
(see `should_attempt_fetch`) so this opt-in feature doesn't fetch
anything most of the year; once the estimate says Conference is getting
close, the real announced dates are fetched from
broadcasts.churchofjesuschrist.org (which publishes each session's real
start/end time as plain HTML attributes) and used for the actual
reminder - more precise than the estimate alone, in the unlikely event a
particular Conference ever shifts off the usual pattern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

BROADCASTS_URL = "https://broadcasts.churchofjesuschrist.org/?lang=eng"

# The reminder only ever fires up to this many days before Conference
# starts (see should_show_reminder) - "maybe 2 weeks prior," per the
# design this was built to.
REMINDER_WINDOW_DAYS = 14

# How far before the locally-*estimated* start date should_attempt_fetch
# allows a fetch to happen at all - wider than REMINDER_WINDOW_DAYS so a
# few days' estimate drift can't push the real fetch past the point
# where the reminder should already be showing.
GATE_BUFFER_DAYS = 21

# "Sat Oct 03 2026 16:00:00 GMT+0000 (Coordinated Universal Time)" - the
# eventStartTime/eventEndTime attribute format broadcasts.churchofjesuschrist.org
# actually uses (confirmed against the live page 2026-09-22).
_EVENT_TIME_FORMAT = "%a %b %d %Y %H:%M:%S"

# Matches one whole opening <div ...> tag containing both time
# attributes, not just the attributes themselves - broadcasts.churchofjesuschrist.org
# lists other, unrelated broadcasts too (devotionals, First Presidency
# messages), tightly packed one after another, so confirming "General
# Conference" appears somewhere in the *same tag* (checked against the
# full match below) is what keeps a neighboring tile's own text from
# being mistaken for this one's - a fixed lookahead distance can't tell
# the difference once two tiles sit closer together than that distance.
_EVENT_TAG_RE = re.compile(
    r'<div\b[^>]*?eventStartTime="([^"]+)"[^>]*?eventEndTime="([^"]+)"[^>]*>', re.DOTALL
)


@dataclass(frozen=True)
class ConferenceDates:
    start: date
    end: date


def _first_saturday(year: int, month: int) -> date:
    first = date(year, month, 1)
    days_to_saturday = (5 - first.weekday()) % 7  # Monday=0 ... Saturday=5
    return first + timedelta(days=days_to_saturday)


def estimate_next_conference_window(today: date) -> ConferenceDates:
    """The next upcoming Conference weekend (Saturday-Sunday), assuming
    the reliable "first Saturday-Sunday of April or October" pattern -
    used only as should_attempt_fetch's cheap, no-network gate, never
    shown to the user directly."""
    candidates = []
    for year in (today.year, today.year + 1):
        for month in (4, 10):
            start = _first_saturday(year, month)
            end = start + timedelta(days=1)
            if end >= today:
                candidates.append(ConferenceDates(start=start, end=end))
    return min(candidates, key=lambda c: c.start)


def should_attempt_fetch(today: date) -> bool:
    """Whether it's worth fetching the real dates at all right now - the
    gate that keeps this opt-in feature from making a network request
    most of the year."""
    estimate = estimate_next_conference_window(today)
    return estimate.start - timedelta(days=GATE_BUFFER_DAYS) <= today <= estimate.start


def should_show_reminder(dates: ConferenceDates, today: date) -> bool:
    """Whether the reminder should actually pop up today, given the real
    (fetched) Conference dates - within REMINDER_WINDOW_DAYS before it
    starts, and not once it's already begun."""
    days_until = (dates.start - today).days
    return 0 <= days_until <= REMINDER_WINDOW_DAYS


def format_date_range(dates: ConferenceDates) -> str:
    start, end = dates.start, dates.end
    if start.month == end.month:
        return f"{start:%B} {start.day}–{end.day}, {end.year}"
    return f"{start:%B} {start.day} – {end:%B} {end.day}, {end.year}"


def _parse_event_time(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw.split(" GMT")[0], _EVENT_TIME_FORMAT)
    except ValueError:
        return None


def _parse_conference_dates(html: str) -> ConferenceDates | None:
    starts: list[datetime] = []
    ends: list[datetime] = []
    for match in _EVENT_TAG_RE.finditer(html):
        if "General Conference" not in match.group(0):
            continue
        start = _parse_event_time(match.group(1))
        end = _parse_event_time(match.group(2))
        if start is None or end is None:
            continue
        starts.append(start)
        ends.append(end)
    if not starts:
        return None
    return ConferenceDates(start=min(starts).date(), end=max(ends).date())


class GeneralConferenceFetcher(QObject):
    """Fetches the real, announced Conference dates.
    `succeeded(ConferenceDates)` or `failed(str)` fires exactly once -
    keep a reference to this object until it does (same reasoning as
    ai_client.py's ConnectionTester)."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply = self._manager.get(QNetworkRequest(QUrl(BROADCASTS_URL)))
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
        dates = _parse_conference_dates(raw)
        if dates is None:
            self.failed.emit("Couldn't find General Conference dates on the broadcasts page.")
            return
        self.succeeded.emit(dates)
