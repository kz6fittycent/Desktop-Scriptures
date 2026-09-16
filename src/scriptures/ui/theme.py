"""Theming: app chrome light/dark, reading color scheme, font, and zoom.

Two independent axes, matching the product decision that you can read in
sepia while the app chrome is dark (or any other combination):

- App theme (light/dark): window chrome, cards, breadcrumb, menus - applied
  as a QApplication-wide stylesheet, Material Design-inspired (rounded
  surfaces, a primary accent color, elevation shadows on cards).
- Reading color scheme (day/night/sepia): the verse text background and
  foreground in ReadingView only.

Font family and zoom (text size) also apply to the reading view.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QFontDatabase

APP_THEMES = ("light", "dark")
READING_SCHEMES = ("day", "night", "sepia")

MIN_FONT_SIZE = 10
MAX_FONT_SIZE = 28
DEFAULT_FONT_SIZE = 16
ZOOM_STEP = 2

CARD_RADIUS = 16
PANEL_RADIUS = 12
MENU_RADIUS = 10
BUTTON_RADIUS = 8

# "Serif"/"Sans Serif" are Qt generic family names resolved by fontconfig on
# any Linux system (including a minimal Snap base) without depending on a
# specific font package being installed - safe defaults. The rest are
# filtered against what's actually installed at runtime.
DEFAULT_FONT_FAMILY = "Sans Serif"

CANDIDATE_FONTS = [
    "Sans Serif",
    "Serif",
    "Noto Serif",
    "Noto Sans",
    "Liberation Serif",
    "Liberation Sans",
    "DejaVu Serif",
    "DejaVu Sans",
    "Ubuntu",
]


def available_fonts() -> list[str]:
    """Curated reading fonts, filtered to what's actually installed.

    "Serif" and "Sans Serif" are always available (Qt/fontconfig generic
    families), so this list is never empty even on a bare-bones system.
    """
    installed = set(QFontDatabase.families())
    fonts = [f for f in CANDIDATE_FONTS if f == DEFAULT_FONT_FAMILY or f in installed]
    if DEFAULT_FONT_FAMILY not in fonts:
        fonts.insert(0, DEFAULT_FONT_FAMILY)
    return fonts


def clamp_font_size(size: int) -> int:
    return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))


@dataclass(frozen=True)
class ReadingPalette:
    background: str
    text: str
    verse_number: str
    title_border: str


READING_PALETTES: dict[str, ReadingPalette] = {
    "day": ReadingPalette(
        background="#FFFFFF", text="#1A1A1A", verse_number="#3A5C8A", title_border="#CCCCCC"
    ),
    # Matches the dark App Theme's surface/text/primary/border exactly
    # (APP_PALETTES["dark"]) rather than its own separate near-black, so
    # the reading card doesn't look darker than the chrome around it.
    "night": ReadingPalette(
        background="#343436", text="#E8E8E8", verse_number="#8C9EFF", title_border="#48484A"
    ),
    "sepia": ReadingPalette(
        background="#F4ECD8", text="#3B2F1E", verse_number="#8B5E34", title_border="#D8C9A3"
    ),
}


@dataclass(frozen=True)
class HighlightColor:
    background: str
    text: str


# Highlighter marks always use a dark, fixed text color rather than the
# active reading palette's - the backgrounds are light pastels by design
# (like a real highlighter pen), so they'd be unreadable against night
# scheme's light-on-dark verse text.
HIGHLIGHT_COLORS: dict[str, HighlightColor] = {
    "yellow": HighlightColor(background="#FFF176", text="#1A1A1A"),
    "pink": HighlightColor(background="#F8BBD0", text="#1A1A1A"),
    "orange": HighlightColor(background="#FFCC80", text="#1A1A1A"),
}


@dataclass(frozen=True)
class AppPalette:
    window_bg: str
    text: str
    surface: str
    border: str
    hover_bg: str
    muted: str
    primary: str
    primary_hover: str
    card_bg: str
    card_hover_bg: str
    card_text: str


# Material Design-inspired: an indigo primary accent, soft indigo-tinted
# card surfaces (rather than a single saturated fill color), and elevation
# communicated with a drop shadow (applied in code - QSS has no box-shadow)
# instead of hard 1px borders everywhere.
APP_PALETTES: dict[str, AppPalette] = {
    "light": AppPalette(
        window_bg="#F3F4F8",
        text="#1A1A1A",
        surface="#FFFFFF",
        border="#E1E3E8",
        hover_bg="#EDEFF5",
        muted="#6B7280",
        primary="#3F51B5",
        primary_hover="#303F9F",
        card_bg="#E8EAF6",
        card_hover_bg="#C5CAE9",
        card_text="#283593",
    ),
    "dark": AppPalette(
        # A neutral dark gray rather than near-black - easier on the eyes
        # for extended reading than the higher-contrast Material default.
        window_bg="#2A2A2C",
        text="#E8E8E8",
        surface="#343436",
        border="#48484A",
        hover_bg="#3C3C3E",
        muted="#A3A3A8",
        primary="#8C9EFF",
        primary_hover="#536DFE",
        card_bg="#33375A",
        card_hover_bg="#3F4570",
        card_text="#C7CCEE",
    ),
}


def app_stylesheet(theme: str) -> str:
    p = APP_PALETTES[theme]
    return f"""
        QMainWindow, QWidget {{
            background-color: {p.window_bg};
            color: {p.text};
        }}
        QScrollArea {{ border: none; }}
        /* Scoped by object name, not widget.setStyleSheet() - an unscoped
        instance stylesheet here would cascade "background: transparent"
        to every descendant, wiping out e.g. the annotate button's
        [annotated="true"] fill. Needed because a bare QLabel (only
        "color" set) doesn't stay transparent without it and paints the
        viewport's own default fill instead of the reading card's color. */
        QWidget#readingViewport {{ background: transparent; }}
        QScrollBar:vertical {{
            background: transparent;
            width: 14px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {p.border};
            min-height: 32px;
            margin: 0px 4px 0px 4px;
            border-radius: 3px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {p.primary}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
            border: none;
            background: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 14px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {p.border};
            min-width: 32px;
            margin: 4px 0px 4px 0px;
            border-radius: 3px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {p.primary}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
            border: none;
            background: none;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}
        QMenuBar {{
            background-color: {p.surface};
            color: {p.text};
            border-bottom: 1px solid {p.border};
            padding: 2px;
        }}
        QMenuBar::item {{
            padding: 6px 12px;
            border-radius: {BUTTON_RADIUS}px;
            margin: 2px 4px;
        }}
        QMenuBar::item:selected {{ background-color: {p.card_bg}; }}
        QMenu {{
            background-color: {p.surface};
            color: {p.text};
            border: 1px solid {p.border};
            border-radius: {MENU_RADIUS}px;
            padding: 6px;
        }}
        QMenu::item {{
            padding: 6px 24px;
            border-radius: {BUTTON_RADIUS}px;
            margin: 1px 4px;
        }}
        QMenu::item:selected {{
            background-color: {p.card_bg};
            color: {p.card_text};
        }}
        QMenu::separator {{
            height: 1px;
            background: {p.border};
            margin: 6px 8px;
        }}
        QLabel#sectionTitle {{
            font-size: 19px;
            font-weight: bold;
            padding: 14px;
            margin: 8px;
            background-color: {p.surface};
            border: 1px solid {p.border};
            border-radius: {PANEL_RADIUS}px;
        }}
        QLabel#sotdBanner {{
            font-size: 14px;
            padding: 12px 16px;
            margin: 0px 8px 8px 8px;
            background-color: {p.surface};
            border: 1px solid {p.border};
            border-radius: {PANEL_RADIUS}px;
            color: {p.text};
        }}
        QLabel#breadcrumbSep {{ color: {p.muted}; }}
        QLabel#breadcrumbCurrent {{ font-weight: bold; }}
        QLabel#breadcrumbLink {{
            color: {p.primary};
            text-decoration: underline;
        }}
        QFrame#sidePanelBox {{
            background-color: {p.surface};
            border: 1px solid {p.border};
            border-radius: {PANEL_RADIUS}px;
            padding: 10px;
        }}
        QLabel#panelSectionTitle {{
            font-weight: bold;
            font-size: 13px;
            color: {p.muted};
            background: transparent;
        }}
        QLabel#searchSectionHeader {{
            color: {p.muted};
            font-weight: bold;
            font-size: 12px;
            padding: 4px 4px 0px 4px;
        }}
        QFrame#resultRow {{
            background-color: {p.surface};
            border: 1px solid {p.border};
            border-radius: {BUTTON_RADIUS}px;
        }}
        QFrame#resultRow:hover {{
            background-color: {p.card_bg};
            border: 1px solid {p.primary};
        }}
        QLabel#resultPrimary {{
            font-weight: bold;
            background: transparent;
        }}
        QLabel#resultSecondary {{
            color: {p.muted};
            font-size: 12px;
            background: transparent;
        }}
        QPushButton#zoomButton {{
            background-color: {p.surface};
            border: 1px solid {p.border};
            border-radius: {BUTTON_RADIUS}px;
            padding: 3px 10px;
            font-weight: bold;
        }}
        QPushButton#zoomButton:hover {{
            background-color: {p.card_bg};
            color: {p.card_text};
        }}
        QPushButton#zoomButton[annotated="true"] {{
            border: 1px solid {p.primary};
            color: {p.primary};
        }}
        QPushButton#navButton {{
            background-color: {p.surface};
            border: 1px solid {p.border};
            border-radius: {BUTTON_RADIUS}px;
            padding: 8px 18px;
            margin: 8px;
            font-weight: bold;
        }}
        QPushButton#navButton:hover {{
            background-color: {p.card_bg};
            color: {p.card_text};
        }}
        QPushButton#navButton:disabled {{
            color: {p.muted};
            border: 1px solid {p.border};
            background-color: {p.window_bg};
        }}
        QPushButton#annotateButton {{
            background-color: transparent;
            border: 1px solid {p.border};
            border-radius: 14px;
            color: {p.muted};
            font-size: 13px;
        }}
        QPushButton#annotateButton:hover {{
            background-color: {p.card_bg};
            color: {p.card_text};
            border: 1px solid {p.card_hover_bg};
        }}
        QPushButton#annotateButton[annotated="true"] {{
            background-color: {p.card_bg};
            color: {p.primary};
            border: 1px solid {p.primary};
        }}
        /* Base rule (and :disabled) is fully invisible - reading_view.py
        always creates one per verse, at a fixed width, so the verse text
        column stays aligned whether or not a given verse has citation
        data; [hasCitations="true"] is the only variant that actually
        looks like anything. */
        QPushButton#citationBadge, QPushButton#citationBadge:disabled {{
            background-color: transparent;
            border: none;
            color: transparent;
            font-size: 11px;
            font-weight: bold;
        }}
        QPushButton#citationBadge[hasCitations="true"] {{
            background-color: {p.card_bg};
            border: 1px solid {p.primary};
            border-radius: 14px;
            color: {p.primary};
        }}
        QPushButton#citationBadge[hasCitations="true"]:hover {{
            background-color: {p.primary};
            color: #FFFFFF;
            border: 1px solid {p.primary};
        }}
        QWidget#tagChip {{
            background-color: {p.card_bg};
            border-radius: 12px;
        }}
        QWidget#tagChip QLabel {{
            color: {p.card_text};
            font-size: 12px;
            font-weight: bold;
            background: transparent;
        }}
        QPushButton#tagChipClose {{
            background: transparent;
            border: none;
            color: {p.card_text};
            font-weight: bold;
            padding: 0px;
        }}
        QPushButton#tagChipClose:hover {{ color: {p.primary}; }}
        QLineEdit, QTextEdit {{
            background-color: {p.surface};
            color: {p.text};
            border: 1px solid {p.border};
            border-radius: {BUTTON_RADIUS}px;
            padding: 6px;
            selection-background-color: {p.primary};
        }}
        QLineEdit#headerSearchBar {{
            border-radius: 16px;
            padding: 6px 14px;
        }}
        QLineEdit#headerSearchBar:focus {{
            border: 1px solid {p.primary};
        }}
        /* Overrides the generic QTextEdit padding/border above - without
        this, the 6px padding pushes each verse's body text down inside
        its row while the verse-number QLabel (not a QLineEdit/QTextEdit,
        so untouched by that rule) stays flush at the top, misaligning
        the two vertically. Colors are still applied per-character in
        reading_view.py via QTextCharFormat, not here. */
        QTextEdit#verseBody {{
            background: transparent;
            border: none;
            padding: 0px;
        }}
        QDialog QPushButton {{
            background-color: {p.surface};
            border: 1px solid {p.border};
            border-radius: {BUTTON_RADIUS}px;
            padding: 6px 16px;
        }}
        QDialog QPushButton:hover {{
            background-color: {p.card_bg};
            color: {p.card_text};
        }}
        QDialog QPushButton:default {{
            background-color: {p.primary};
            color: #FFFFFF;
            border: 1px solid {p.primary};
        }}
        QDialog QPushButton:default:hover {{
            background-color: {p.primary_hover};
            border: 1px solid {p.primary_hover};
        }}
        QFrame#card {{
            background-color: {p.card_bg};
            border-radius: {CARD_RADIUS}px;
        }}
        QFrame#card:hover {{
            background-color: {p.card_hover_bg};
        }}
        QFrame#card QLabel {{
            color: {p.card_text};
            font-size: 14px;
            font-weight: bold;
            background: transparent;
        }}
        QLabel#streakBadge {{
            background-color: {p.card_bg};
            color: {p.card_text};
            font-weight: bold;
            font-size: 12px;
            border-radius: 12px;
            padding: 5px 14px;
            margin: 4px 10px 4px 0px;
        }}
        QPushButton#resumeButton {{
            background-color: {p.primary};
            color: #FFFFFF;
            font-weight: bold;
            border: none;
            border-radius: {BUTTON_RADIUS}px;
            padding: 4px 14px;
            margin: 2px 4px;
        }}
        QPushButton#resumeButton:hover {{
            background-color: {p.primary_hover};
        }}
    """


def apply_app_theme(app, theme: str) -> None:
    app.setStyleSheet(app_stylesheet(theme))
