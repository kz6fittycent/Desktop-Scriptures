"""Standalone test script for src/scriptures/family_history.py's
scheduling logic. No test framework, no network, no Qt event loop
required (see tests/test_ask.py's own docstring for why this project
tests pure logic this way rather than with a framework).

Run directly:

    python3 tests/test_family_history.py
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.family_history import (  # noqa: E402
    MAX_INTERVAL_DAYS,
    MIN_INTERVAL_DAYS,
    pick_next_reminder_date,
    should_show_reminder,
)


def test_pick_next_reminder_date_stays_within_bounds() -> None:
    rng = random.Random(1234)
    today = date(2026, 1, 1)
    seen_deltas = set()
    for _ in range(500):
        chosen = pick_next_reminder_date(today, rng=rng)
        delta = (chosen - today).days
        assert MIN_INTERVAL_DAYS <= delta <= MAX_INTERVAL_DAYS, delta
        seen_deltas.add(delta)
    # Genuinely irregular, not just always picking the same offset.
    assert len(seen_deltas) > 1
    print("test_pick_next_reminder_date_stays_within_bounds: PASSED")


def test_pick_next_reminder_date_never_below_minimum() -> None:
    today = date(2026, 1, 1)
    # A rigged RNG that always returns its lower bound - still must
    # respect MIN_INTERVAL_DAYS, never sooner.
    class _MinRng:
        def randint(self, a, b):
            return a

    chosen = pick_next_reminder_date(today, rng=_MinRng())
    assert (chosen - today).days == MIN_INTERVAL_DAYS
    print("test_pick_next_reminder_date_never_below_minimum: PASSED")


def test_should_show_reminder_only_once_due() -> None:
    today = date(2026, 6, 15)
    assert should_show_reminder(today + timedelta(days=1), today) is False
    assert should_show_reminder(today, today) is True
    assert should_show_reminder(today - timedelta(days=1), today) is True
    print("test_should_show_reminder_only_once_due: PASSED")


if __name__ == "__main__":
    test_pick_next_reminder_date_stays_within_bounds()
    test_pick_next_reminder_date_never_below_minimum()
    test_should_show_reminder_only_once_due()
    print("All family_history.py tests passed.")
