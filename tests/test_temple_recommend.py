"""Standalone test script for src/scriptures/temple_recommend.py's date
math. No test framework, no network, no Qt event loop required (see
tests/test_ask.py's own docstring for why this project tests pure logic
this way rather than with a framework).

Run directly:

    python3 tests/test_temple_recommend.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.temple_recommend import (  # noqa: E402
    REMINDER_WINDOW_DAYS,
    format_reminder_message,
    should_show_reminder,
)


def test_should_show_reminder_within_window() -> None:
    today = date(2026, 9, 24)
    assert should_show_reminder(today + timedelta(days=REMINDER_WINDOW_DAYS + 1), today) is False
    assert should_show_reminder(today + timedelta(days=REMINDER_WINDOW_DAYS), today) is True
    assert should_show_reminder(today, today) is True
    print("test_should_show_reminder_within_window: PASSED")


def test_should_show_reminder_keeps_firing_once_overdue() -> None:
    today = date(2026, 9, 24)
    assert should_show_reminder(today - timedelta(days=1), today) is True
    assert should_show_reminder(today - timedelta(days=365), today) is True
    print("test_should_show_reminder_keeps_firing_once_overdue: PASSED")


def test_format_reminder_message_future() -> None:
    today = date(2026, 9, 24)
    message = format_reminder_message(today + timedelta(days=30), today)
    assert message == "Your temple recommend expires in 30 days (October 24, 2026)."
    print("test_format_reminder_message_future: PASSED")


def test_format_reminder_message_singular_day() -> None:
    today = date(2026, 9, 24)
    message = format_reminder_message(today + timedelta(days=1), today)
    assert message == "Your temple recommend expires in 1 day (September 25, 2026)."
    print("test_format_reminder_message_singular_day: PASSED")


def test_format_reminder_message_today() -> None:
    today = date(2026, 9, 24)
    message = format_reminder_message(today, today)
    assert message == "Your temple recommend expires today (September 24, 2026)."
    print("test_format_reminder_message_today: PASSED")


def test_format_reminder_message_overdue() -> None:
    today = date(2026, 9, 24)
    message = format_reminder_message(today - timedelta(days=3), today)
    assert message == "Your temple recommend expired 3 days ago (September 21, 2026)."
    print("test_format_reminder_message_overdue: PASSED")


if __name__ == "__main__":
    test_should_show_reminder_within_window()
    test_should_show_reminder_keeps_firing_once_overdue()
    test_format_reminder_message_future()
    test_format_reminder_message_singular_day()
    test_format_reminder_message_today()
    test_format_reminder_message_overdue()
    print("All temple_recommend.py tests passed.")
