"""Optional, opt-in Family History reminder (see main_window.py's "Family
History Reminder" menu item and startup check for the overall design).

Unlike General Conference or Temple Recommend, this isn't tied to any
particular date - it's just a nudge to spend a few minutes on family
history now and then. A fixed interval gets tuned out fast, so instead
of firing every N days on the dot, each reminder schedules the *next*
one at a random interval - irregular enough to stay noticeable, but
never less than MIN_INTERVAL_DAYS apart so it can't turn into a nag.
Entirely offline: no network access, no server involved.
"""

from __future__ import annotations

import random as random_module
from datetime import date, timedelta

MIN_INTERVAL_DAYS = 4
MAX_INTERVAL_DAYS = 14

FAMILYSEARCH_URL = "https://www.familysearch.org"


def pick_next_reminder_date(today: date, rng: random_module.Random | None = None) -> date:
    """The next date a reminder should fire, picked uniformly at random
    from [MIN_INTERVAL_DAYS, MAX_INTERVAL_DAYS] days out. `rng` is
    injectable for deterministic tests - real callers just let it default
    to a fresh Random()."""
    rng = rng or random_module.Random()
    return today + timedelta(days=rng.randint(MIN_INTERVAL_DAYS, MAX_INTERVAL_DAYS))


def should_show_reminder(next_due: date, today: date) -> bool:
    return today >= next_due
