"""Standalone test script for src/scriptures/general_conference.py's date
math and broadcasts-page-parsing logic. No test framework, no network, no
Qt event loop required (see tests/test_ask.py's own docstring for why
this project tests pure logic this way rather than with a framework).

SAMPLE_HTML below is a trimmed real fragment of
broadcasts.churchofjesuschrist.org's markup (verified against the live
page on 2026-09-22) - the Saturday and Sunday General Conference session
tiles, plus one unrelated broadcast tile (a devotional) that a correct
parser must NOT mistake for a Conference date.

Run directly:

    python3 tests/test_general_conference.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.general_conference import (  # noqa: E402
    ConferenceDates,
    _parse_conference_dates,
    estimate_next_conference_window,
    format_date_range,
    should_attempt_fetch,
    should_show_reminder,
)

SAMPLE_HTML = """
<div eventStartTime="Sun Sep 13 2026 14:00:00 GMT+0000 (Coordinated Universal Time)" eventEndTime="Sun Sep 13 2026 15:00:00 GMT+0000 (Coordinated Universal Time)" longDescription="Join us for this week's First Presidency message."></div>
<div eventStartTime="Sat Oct 03 2026 16:00:00 GMT+0000 (Coordinated Universal Time)" eventEndTime="Sat Oct 03 2026 22:00:00 GMT+0000 (Coordinated Universal Time)" longDescription="Join us for the Saturday sessions of the 196th Semiannual General Conference of The Church of Jesus Christ of Latter-day Saints."></div>
<div eventStartTime="Sun Oct 04 2026 16:00:00 GMT+0000 (Coordinated Universal Time)" eventEndTime="Sun Oct 04 2026 22:00:00 GMT+0000 (Coordinated Universal Time)" longDescription="Join us for the Sunday sessions of the 196th Semiannual General Conference of The Church of Jesus Christ of Latter-day Saints."></div>
"""


def test_parses_conference_dates_and_ignores_unrelated_broadcasts() -> None:
    dates = _parse_conference_dates(SAMPLE_HTML)
    assert dates is not None
    assert dates.start == date(2026, 10, 3)
    assert dates.end == date(2026, 10, 4)
    print("test_parses_conference_dates_and_ignores_unrelated_broadcasts: PASSED")


def test_parse_returns_none_without_a_conference_tile() -> None:
    html = '<div eventStartTime="Sun Sep 13 2026 14:00:00 GMT+0000 (Coordinated Universal Time)" eventEndTime="Sun Sep 13 2026 15:00:00 GMT+0000 (Coordinated Universal Time)" longDescription="Just a devotional."></div>'
    assert _parse_conference_dates(html) is None
    print("test_parse_returns_none_without_a_conference_tile: PASSED")


def test_format_date_range_same_month() -> None:
    assert format_date_range(ConferenceDates(date(2026, 10, 3), date(2026, 10, 4))) == (
        "October 3–4, 2026"
    )
    print("test_format_date_range_same_month: PASSED")


def test_estimate_finds_next_upcoming_weekend() -> None:
    # Well before October's Conference - should estimate October, not April.
    estimate = estimate_next_conference_window(date(2026, 9, 22))
    assert estimate.start == date(2026, 10, 3)
    assert estimate.end == date(2026, 10, 4)
    # Just after October's Conference - should roll to next April.
    estimate = estimate_next_conference_window(date(2026, 10, 5))
    assert estimate.start.month == 4
    assert estimate.start.year == 2027
    print("test_estimate_finds_next_upcoming_weekend: PASSED")


def test_should_attempt_fetch_gates_on_proximity() -> None:
    # 21+ days out - too early, don't bother fetching yet.
    assert should_attempt_fetch(date(2026, 9, 1)) is False
    # Within the gate buffer before the estimated start.
    assert should_attempt_fetch(date(2026, 9, 22)) is True
    # On the estimated start date itself.
    assert should_attempt_fetch(date(2026, 10, 3)) is True
    print("test_should_attempt_fetch_gates_on_proximity: PASSED")


def test_should_show_reminder_within_window_only() -> None:
    dates = ConferenceDates(date(2026, 10, 3), date(2026, 10, 4))
    assert should_show_reminder(dates, date(2026, 9, 19)) is True  # 14 days before
    assert should_show_reminder(dates, date(2026, 9, 18)) is False  # 15 days before
    assert should_show_reminder(dates, date(2026, 10, 3)) is True  # starts today
    assert should_show_reminder(dates, date(2026, 10, 4)) is False  # already started
    print("test_should_show_reminder_within_window_only: PASSED")


if __name__ == "__main__":
    test_parses_conference_dates_and_ignores_unrelated_broadcasts()
    test_parse_returns_none_without_a_conference_tile()
    test_format_date_range_same_month()
    test_estimate_finds_next_upcoming_weekend()
    test_should_attempt_fetch_gates_on_proximity()
    test_should_show_reminder_within_window_only()
    print("All general_conference.py tests passed.")
