"""Israel's calendar, for the Book of Mormon's dates ("the fourth day of the
first month" - 3 Nephi 8:5): each month's names, season, and the holy days
of the law of Moses, which the Nephites kept (2 Nephi 5:10).

The Book of Mormon numbers its months, as pre-exilic Israel did ("the
first month" - Exodus 12:2), or used the old Canaanite names (Abib, Ziv,
Ethanim, Bul). The Babylonian names (Nisan, Tishri...) came into use after
the exile - after Lehi left Jerusalem in the first year of Zedekiah
(1 Nephi 1:4). Days and events that came later than Lehi (the fall of
Jerusalem, Purim, Hanukkah) are marked so, since the Nephites wouldn't
have known them.

Whether the Nephite months lined up with Israel's isn't known: the
Nephites counted years from Lehi's departure, the reign of the judges, and
the sign of Christ's birth (3 Nephi 2:8), so their first month may have
begun at another season. The cards say so.

Used by the reading view (date phrases as links - see reading_view.py) and
the Word Study tab's calendar card (word_study_panel.py). Strong's numbers
in the text link to the lexicon there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HolyDay:
    days: str  # "14", "15-21", "" for one counted rather than dated
    name: str
    about: str
    after_lehi: bool = False  # came after Lehi left Jerusalem


@dataclass(frozen=True)
class Month:
    number: int
    early_name: str  # the pre-exilic name the Bible records, if any
    later_name: str  # the post-exilic (Babylonian) name
    season: str
    days: list[HolyDay] = field(default_factory=list)


@dataclass(frozen=True)
class BomDate:
    month: int
    day: int | None
    reference: str
    event: str


ORDINALS = (
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
    "eleventh", "twelfth",
)

MONTHS: list[Month] = [
    Month(1, "Abib (H24) - \"fresh ears\" of grain (Exodus 13:4; Deuteronomy 16:1)",
          "Nisan (H5212) - Nehemiah 2:1; Esther 3:7", "March-April, the barley harvest", [
        HolyDay("1", "The beginning of months",
                "\"This month shall be unto you the beginning of months\" (Exodus 12:2) - the first month of "
                "Israel's sacred year."),
        HolyDay("10", "The Passover lamb chosen", "Each household chose its lamb (Exodus 12:3)."),
        HolyDay("14", "Passover (H6453)", "The lamb was slain at evening (Exodus 12:6; Leviticus 23:5). Jesus was "
                "crucified at Passover (John 19:14)."),
        HolyDay("15-21", "The Feast of Unleavened Bread (H4682)", "Seven days without leaven (Leviticus 23:6-8)."),
        HolyDay("", "Firstfruits", "The first sheaf of the barley harvest was waved before the Lord \"on the morrow "
                "after the sabbath\" during the feast (Leviticus 23:10-11)."),
    ]),
    Month(2, "Ziv (H2099), spelled Zif in the King James Version - \"brightness\" (1 Kings 6:1, 37)",
          "Iyyar (not in the Bible)", "April-May", [
        HolyDay("14", "The second Passover", "For those unclean or on a journey at the first (Numbers 9:10-11)."),
        HolyDay("", "Solomon's temple begun", "Solomon began building the temple in this month (1 Kings 6:1)."),
    ]),
    Month(3, "", "Sivan (H5510) - Esther 8:9", "May-June, the wheat harvest", [
        HolyDay("", "The Feast of Weeks (H7620), or Pentecost", "Counted fifty days from the wave sheaf of "
                "firstfruits (Leviticus 23:15-21; Deuteronomy 16:9-10), so it usually falls in this month."),
        HolyDay("1", "Israel at Sinai", "Israel came to the wilderness of Sinai in the third month (Exodus 19:1)."),
    ]),
    Month(4, "", "Tammuz (not a month name in the Bible)", "June-July", [
        HolyDay("9", "Jerusalem's wall broken through", "Babylon breached the city (Jeremiah 39:2; 52:6-7); later "
                "mourned as \"the fast of the fourth month\" (Zechariah 8:19).", after_lehi=True),
    ]),
    Month(5, "", "Av (not in the Bible)", "July-August", [
        HolyDay("1", "Aaron died", "Aaron died on Mount Hor (Numbers 33:38)."),
        HolyDay("7-10", "The temple burned", "Babylon burned the temple and Jerusalem (2 Kings 25:8-9; Jeremiah "
                "52:12-13); later \"the fast of the fifth month\" (Zechariah 7:3), today Tisha B'Av.",
                after_lehi=True),
    ]),
    Month(6, "", "Elul (H435) - Nehemiah 6:15", "August-September", [
        HolyDay("25", "Jerusalem's wall finished", "Nehemiah finished rebuilding the wall (Nehemiah 6:15).",
                after_lehi=True),
    ]),
    Month(7, "Ethanim (H388) - 1 Kings 8:2", "Tishri (not in the Bible)", "September-October, the fruit harvest", [
        HolyDay("1", "The memorial of blowing of trumpets (H8643)", "\"In the first day of the seventh month\" "
                "(Leviticus 23:24; Numbers 29:1) - later called Rosh Hashanah, \"head of the year,\" the civil new "
                "year."),
        HolyDay("10", "The Day of Atonement (H3725)", "The one day the high priest entered the holy of holies "
                "(Leviticus 16:29-34; 23:27); the jubilee was proclaimed on it (Leviticus 25:9)."),
        HolyDay("15-21", "The Feast of Tabernacles (H5521)", "Seven days living in booths, with a solemn assembly "
                "on the eighth day (Leviticus 23:34-36, 39-43). Solomon dedicated the temple at this feast "
                "(1 Kings 8:2), and every seventh year the law was read to all Israel then (Deuteronomy 31:10-11)."),
    ]),
    Month(8, "Bul (H945) - 1 Kings 6:38", "Marcheshvan, or Heshvan (not in the Bible)", "October-November", [
        HolyDay("", "Solomon's temple finished", "The temple was finished in this month (1 Kings 6:38)."),
        HolyDay("15", "Jeroboam's rival feast", "Jeroboam set up a feast \"which he had devised of his own heart\" "
                "to rival Tabernacles (1 Kings 12:32-33)."),
    ]),
    Month(9, "", "Kislev (H3691), spelled Chisleu in the King James Version - Nehemiah 1:1; Zechariah 7:1",
          "November-December", [
        HolyDay("25", "Hanukkah, the Feast of Dedication", "The temple rededicated in 164 BC (1 Maccabees 4:52-59; "
                "John 10:22).", after_lehi=True),
    ]),
    Month(10, "", "Tebeth (H2887) - Esther 2:16", "December-January", [
        HolyDay("10", "The siege of Jerusalem begun", "Nebuchadnezzar besieged Jerusalem (2 Kings 25:1; Jeremiah "
                "52:4); later \"the fast of the tenth month\" (Zechariah 8:19).", after_lehi=True),
    ]),
    Month(11, "", "Shebat (H7627), spelled Sebat in the King James Version - Zechariah 1:7", "January-February", [
        HolyDay("1", "Moses expounds the law", "Moses began declaring the law to Israel in the plains of Moab "
                "(Deuteronomy 1:3) - the book of Deuteronomy."),
    ]),
    Month(12, "", "Adar (H143) - Ezra 6:15; Esther 3:7", "February-March", [
        HolyDay("3", "The second temple finished", "(Ezra 6:15)", after_lehi=True),
        HolyDay("14-15", "Purim", "The deliverance in Esther's day (Esther 9:17-21).", after_lehi=True),
    ]),
]

# Every dated event in the Book of Mormon.
BOM_DATES: list[BomDate] = [
    BomDate(1, 1, "Alma 52:1", "The Lamanites find Amalickiah dead in his tent \"on the first morning of the "
            "first month\" - New Year's Day; Teancum had slain him the night before (Alma 51:34)."),
    BomDate(1, 2, "Alma 56:1", "Moroni receives Helaman's epistle about the two thousand stripling warriors."),
    BomDate(1, 4, "3 Nephi 8:5", "The great storm and destruction at Christ's death - in Israel's calendar, "
            "this is the month of Passover, when He was crucified at Jerusalem."),
    BomDate(2, 5, "Alma 16:1", "A cry of war: the Lamanites destroy Ammonihah (Alma 16:2-3)."),
    BomDate(2, None, "Alma 56:27", "Provisions and two thousand more men reach Helaman's army."),
    BomDate(6, None, "3 Nephi 4:7, 11", "The great battle against Giddianhi's Gadianton robbers."),
    BomDate(7, 3, "Alma 56:42", "Helaman's army, pursued for two days, finds the Lamanites have halted."),
    BomDate(7, 4, "Alma 10:6", "Amulek says he rebelled against God \"until the fourth day of this seventh month\" "
            "- he is speaking in the seventh month, the month of Trumpets, the Day of Atonement, and Tabernacles."),
    BomDate(10, 12, "Alma 14:23", "The chief judge comes to the imprisoned Alma and Amulek; that day the prison "
            "falls (Alma 14:27-28)."),
    BomDate(11, 10, "Alma 49:1", "The Lamanites march on the rebuilt city of Ammonihah."),
]

CALENDAR_NOTE = (
    "The Book of Mormon numbers its months, as Israel did before the exile; the Babylonian month names came "
    "after Lehi left Jerusalem. Whether the Nephite months lined up with Israel's isn't known - the Nephites "
    "counted their years from Lehi's departure, the reign of the judges, and the sign of Christ's birth "
    "(3 Nephi 2:8). The holy days are those of the law of Moses, which the Nephites kept (2 Nephi 5:10). "
    "Each month began with the new moon (Numbers 28:11) - Hebrew ḥōdeš means both \"month\" and \"new moon\" "
    "(H2320)."
)

_ORDINAL = "|".join(ORDINALS)
# "the fourth day of this seventh month", "the first morning of the first
# month", "the twelfth day, in the tenth month", "the first month, on the
# fourth day of the month", "the eleventh month of the nineteenth year, on
# the tenth day of the month", or just "the sixth month".
_DATE_RE = re.compile(
    rf"\b(?:(?P<day>{_ORDINAL})\s+(?:day|morning),?\s+(?:of|in)\s+(?:the|this)\s+)?(?P<month>{_ORDINAL})\s+month"
    rf"(?:(?:\s+of\s+the\s+[\w ]+?\s+year)?,\s+on\s+the\s+(?P<day_after>{_ORDINAL})\s+day\s+of\s+the\s+month)?\b",
    re.IGNORECASE,
)


def month(number: int) -> Month:
    return MONTHS[number - 1]


def find_dates(text: str) -> list[tuple[int, int, int, int | None]]:
    """(start, end, month, day) for each date phrase in a verse."""
    found = []
    for match in _DATE_RE.finditer(text):
        day_word = match.group("day") or match.group("day_after")
        day = ORDINALS.index(day_word.lower()) + 1 if day_word else None
        found.append((match.start(), match.end(), ORDINALS.index(match.group("month").lower()) + 1, day))
    return found


def _short(name: str) -> str:
    """"Abib (H24) - ..." -> "Abib"; "Iyyar (not in the Bible)" -> "Iyyar"."""
    return re.split(r" \(| - ", name)[0]


def _in_sentence(name: str) -> str:
    """A holy day's name mid-sentence: "the Feast of Tabernacles"."""
    short = _short(name)
    return "the " + short[4:] if short.startswith("The ") else short


def _day_range(days: str) -> tuple[int, int] | None:
    if not days:
        return None
    first, _, last = days.partition("-")
    return int(first), int(last or first)


def day_context(month_number: int, day: int) -> str:
    """Where a day falls among its month's holy days of the law of Moses:
    "Passover falls 10 days later, on the 14th"."""
    lines = []
    for holy in month(month_number).days:
        span = _day_range(holy.days)
        if span is None or holy.after_lehi:
            continue
        first, last = span
        if first == day == last:
            lines.append(f"This is the day of {_in_sentence(holy.name)}.")
        elif first <= day <= last:
            lines.append(f"This is during {_in_sentence(holy.name)}.")
        elif day < first:
            gap = first - day
            lines.append(f"{_in_sentence(holy.name)[0].upper()}{_in_sentence(holy.name)[1:]} falls {gap} "
                         f"day{'s' if gap != 1 else ''} later, on the {_ordinal_number(first)}.")
    return " ".join(lines)


def tooltip(month_number: int, day: int | None) -> str:
    m = month(month_number)
    names = "; later ".join(_short(n) for n in (m.early_name, m.later_name) if n)
    holy = ", ".join(f"{_short(h.name)}{f' ({h.days})' if h.days else ''}" for h in m.days if not h.after_lehi)
    lines = [f"The {ORDINALS[month_number - 1]} month ({names}) - {m.season}"]
    if holy:
        lines.append(holy)
    if day is not None:
        context = day_context(month_number, day)
        if context:
            lines.append(context)
    lines.append("Click for the Hebrew calendar in Word Study")
    return "\n".join(lines)


def _ordinal_number(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
