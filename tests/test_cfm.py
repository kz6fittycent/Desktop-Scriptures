"""Standalone test script for src/scriptures/cfm.py's manual-page-parsing
logic. No test framework, no network, no Qt event loop required -
_parse_current_week is a plain function over raw HTML text (see
tests/test_ask.py's own docstring for why this project tests pure logic
this way rather than with a framework).

SAMPLE_HTML below is a trimmed real fragment of the Come Follow Me
manual page's list markup (verified against the live page on
2026-09-22) - just enough consecutive weeks to exercise picking the
right one, not the full ~400KB page.

Run directly:

    python3 tests/test_cfm.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.cfm import _parse_current_week  # noqa: E402


def _week_li(date_start: str, date_end: str, href: str, label: str, block: str) -> str:
    return (
        f'<li data-content-type="chapter" data-date-end="{date_end}" '
        f'data-date-start="{date_start}">'
        f'<a href="{href}" class="sc-omeqik-0 ewktus list-tile listTile-WHLxI">'
        f'<div class="sc-omeqik-1 hrmBvm"><div class="sc-omeqik-2 eHGbnh">'
        f'<div class="sc-omeqik-3 knLBrM"><div class="sc-omeqik-4 eJJULB">'
        f'<h6 class="sc-1r3sor6-0 gRhZLd sc-omeqik-5 fqGeGi">'
        f'<p class="primaryMeta">{label}</p></h6></div></div>'
        f'<div class="sc-omeqik-7 iwWCCo"><h4 class="sc-12mz36o-0 jSCFto sc-omeqik-9 dbmmCm">'
        f'<p class="title">{block}</p></h4></div></div></div></a></li>\n'
    )


SAMPLE_HTML = (
    _week_li(
        "2026-09-14",
        "2026-09-20",
        "/study/manual/come-follow-me-for-home-and-church-old-testament-2026/38?lang=eng",
        "September 14–20",
        "Isaiah 1–12",
    )
    + _week_li(
        "2026-09-21",
        "2026-09-27",
        "/study/manual/come-follow-me-for-home-and-church-old-testament-2026/39?lang=eng",
        "September 21–27",
        "Isaiah 13–14; 22; 24–30; 35",
    )
    + _week_li(
        "2026-09-28",
        "2026-10-04",
        "/study/manual/come-follow-me-for-home-and-church-old-testament-2026/40?lang=eng",
        "September 28–October 4",
        "Isaiah 40–45",
    )
)


def test_picks_the_week_containing_today() -> None:
    lesson = _parse_current_week(SAMPLE_HTML, date(2026, 9, 22))
    assert lesson is not None
    assert lesson.date_label == "September 21–27"
    assert lesson.scripture_block == "Isaiah 13–14; 22; 24–30; 35"
    assert lesson.link == (
        "https://www.churchofjesuschrist.org/study/manual/"
        "come-follow-me-for-home-and-church-old-testament-2026/39?lang=eng"
    )
    print("test_picks_the_week_containing_today: PASSED")


def test_boundary_dates_are_inclusive() -> None:
    start = _parse_current_week(SAMPLE_HTML, date(2026, 9, 21))
    end = _parse_current_week(SAMPLE_HTML, date(2026, 9, 27))
    assert start is not None and start.scripture_block == "Isaiah 13–14; 22; 24–30; 35"
    assert end is not None and end.scripture_block == "Isaiah 13–14; 22; 24–30; 35"
    print("test_boundary_dates_are_inclusive: PASSED")


def test_date_outside_every_listed_week_returns_none() -> None:
    assert _parse_current_week(SAMPLE_HTML, date(2027, 1, 1)) is None
    print("test_date_outside_every_listed_week_returns_none: PASSED")


def test_garbage_html_returns_none() -> None:
    assert _parse_current_week("<html>nothing useful here</html>", date(2026, 9, 22)) is None
    print("test_garbage_html_returns_none: PASSED")


if __name__ == "__main__":
    test_picks_the_week_containing_today()
    test_boundary_dates_are_inclusive()
    test_date_outside_every_listed_week_returns_none()
    test_garbage_html_returns_none()
    print("All cfm.py tests passed.")
