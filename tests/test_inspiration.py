"""Standalone test script for src/scriptures/inspiration.py's homepage-
parsing logic. No test framework, no network, no Qt event loop required -
_parse_message is a plain function over raw HTML text (see
tests/test_ask.py's own docstring for why this project tests pure logic
this way rather than with a framework).

SAMPLE_HTML below is a trimmed real fragment of churchofjesuschrist.org's
homepage markup (verified against the live page on 2026-09-22).

Run directly:

    python3 tests/test_inspiration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures.inspiration import _parse_message  # noqa: E402

SAMPLE_HTML = """
<cta-poster>irrelevant surrounding markup</cta-poster><section class="blockquote">
  <h2 class="blockquoteHeading">Jesus Christ, Our Perfect Example</h2>
  <p class="blockquoteText">“We need to love and do good to all. We need to avoid contention and be peacemakers in all our communications.”</p>
  <a href="https://www.churchofjesuschrist.org/learn/people/dallin-h-oaks/life-leadership?lang=eng" target="_self" class="blockquoteAttribution">
  <img src="https://www.churchofjesuschrist.org/imgs/example" alt="President Oaks"/>
  <div>
    <div class="blockquoteAuthor">President Dallin H. Oaks</div>
    <div class="blockquoteByline">Prophet and president of The Church of Jesus Christ of Latter-day Saints</div>
  </div>
</a>
</section><section class="spotlightCollection">irrelevant trailing markup</section>
"""

INCOMPLETE_HTML = """
<section class="blockquote">
  <h2 class="blockquoteHeading">A Heading With No Quote</h2>
</section>
"""


def test_parses_quote_author_byline_and_link() -> None:
    message = _parse_message(SAMPLE_HTML)
    assert message is not None
    assert message.quote == (
        "We need to love and do good to all. We need to avoid contention "
        "and be peacemakers in all our communications."
    )
    assert message.author == "President Dallin H. Oaks"
    assert message.byline == "Prophet and president of The Church of Jesus Christ of Latter-day Saints"
    assert message.link == (
        "https://www.churchofjesuschrist.org/learn/people/dallin-h-oaks/life-leadership?lang=eng"
    )
    print("test_parses_quote_author_byline_and_link: PASSED")


def test_relative_link_is_made_absolute() -> None:
    html = SAMPLE_HTML.replace(
        'href="https://www.churchofjesuschrist.org/learn/people/dallin-h-oaks/life-leadership?lang=eng"',
        'href="/learn/people/dallin-h-oaks/life-leadership?lang=eng"',
    )
    message = _parse_message(html)
    assert message is not None
    assert message.link == (
        "https://www.churchofjesuschrist.org/learn/people/dallin-h-oaks/life-leadership?lang=eng"
    )
    print("test_relative_link_is_made_absolute: PASSED")


def test_missing_section_returns_none() -> None:
    assert _parse_message("<html>nothing useful here</html>") is None
    print("test_missing_section_returns_none: PASSED")


def test_incomplete_section_returns_none() -> None:
    assert _parse_message(INCOMPLETE_HTML) is None
    print("test_incomplete_section_returns_none: PASSED")


if __name__ == "__main__":
    test_parses_quote_author_byline_and_link()
    test_relative_link_is_made_absolute()
    test_missing_section_returns_none()
    test_incomplete_section_returns_none()
    print("All inspiration.py tests passed.")
