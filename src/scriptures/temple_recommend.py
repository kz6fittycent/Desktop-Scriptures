"""Optional, opt-in Temple Recommend renewal reminder (see main_window.py's
"Temple Recommend Reminder..." menu item and startup check for the overall
design).

Unlike the General Conference reminder, there's no external date to fetch -
the user enters their own recommend's expiration date once, and this module
just decides, from that single date, whether a reminder is due today.
Entirely offline: no network access, no server involved.
"""

from __future__ import annotations

from datetime import date

# The reminder starts firing this many days before expiration - four
# weeks, long enough to schedule a bishopric/stake presidency interview
# without rushing. There's no upper bound on the overdue side (see
# should_show_reminder): a lapsed recommend keeps being worth a reminder
# every day until the user renews and enters a new date.
REMINDER_WINDOW_DAYS = 28


def should_show_reminder(expiration: date, today: date) -> bool:
    """Whether today falls within the reminder window - including every
    day after expiration too, not just before it."""
    return (expiration - today).days <= REMINDER_WINDOW_DAYS


def format_reminder_message(expiration: date, today: date) -> str:
    formatted = f"{expiration:%B} {expiration.day}, {expiration.year}"
    days = (expiration - today).days
    if days > 0:
        plural = "day" if days == 1 else "days"
        return f"Your temple recommend expires in {days} {plural} ({formatted})."
    if days == 0:
        return f"Your temple recommend expires today ({formatted})."
    overdue = -days
    plural = "day" if overdue == 1 else "days"
    return f"Your temple recommend expired {overdue} {plural} ago ({formatted})."
