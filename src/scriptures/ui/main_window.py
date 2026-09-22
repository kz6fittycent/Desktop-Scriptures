"""Main application window.

Navigation model: each level's handler queries its children, builds a
CardGridWidget (or ReadingView for the final level), and wires the next
click to the next handler down. The breadcrumb path is rebuilt at every
step from small closures so clicking any earlier segment re-renders that
exact level without re-deriving state from scratch.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from html import escape
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from scriptures import __version__
from scriptures.ai_client import AiConfig
from scriptures.data_access import (
    Book,
    Chapter,
    ReadingHistoryEntry,
    Testament,
    Volume,
    get_book,
    get_books,
    get_chapter,
    get_chapter_location,
    get_chapters,
    get_reading_history,
    get_reading_streak,
    get_setting,
    get_testament,
    get_testaments,
    get_topic,
    get_topics,
    get_topic_talks,
    get_topic_verses,
    get_verses,
    get_volume,
    get_volumes,
    record_reading,
    set_setting,
)
from scriptures.sotd import get_scripture_of_the_day
from scriptures.sync import sync_now
from scriptures.ui.ai_settings_dialog import AiSettingsDialog
from scriptures.ui.breadcrumb import BreadcrumbBar
from scriptures.ui.card_grid import LANDING_CARD_SIZE, CardGridWidget
from scriptures.ui.cfm_box import CfmBox
from scriptures.ui.church_news_box import ChurchNewsBox
from scriptures.ui.export import export_notes
from scriptures.ui.reading_view import ReadingView
from scriptures.ui.search_view import SearchView
from scriptures.ui.sync_dialog import SyncFolderDialog
from scriptures.ui.topical_guide_view import TopicDetailView
from scriptures.ui import theme as theming

# Sentinel item_id for the landing page's synthetic "Topical Guide" card,
# mixed in alongside the real (integer) volume ids from get_volumes() -
# it isn't a scripture volume (no testaments/books/chapters), so
# _on_volume_clicked branches to _show_topical_guide() instead of the
# normal get_volume() lookup whenever it sees this.
TOPICAL_GUIDE_ID = "topical-guide"

BOOK_OF_MORMON_SHARE_URL = "https://go.churchofjesuschrist.org/x/n1Ic"
BEANDOG_REPO_URL = "https://github.com/beandog/lds-scriptures"
BYU_CITATION_INDEX_URL = "https://scriptures.byu.edu"
CHURCH_SCRIPTURES_URL = "https://www.churchofjesuschrist.org/study/scriptures"

# Caps how wide the Help menu's word-wrapped labels (see _help_menu_label)
# can get, so the dropdown stays comfortably narrower than the window
# instead of growing to fit its longest line.
HELP_MENU_TEXT_WIDTH = 280

# How long a chapter has to stay open, uninterrupted, before it counts
# toward the reading streak - long enough that clicking through chapters
# (e.g. browsing to find a passage) doesn't rack up "reads" you didn't do.
READING_STREAK_DWELL_MS = 5000

# Settings keys backing the Sync menu - both device-specific (which folder
# THIS installation should read/write, when THIS installation last synced),
# so they live in the local settings table like the theme/font choices
# above, never inside anything sync.py itself reads or writes.
SYNC_FOLDER_SETTING = "sync_folder_path"
LAST_SYNC_SETTING = "last_sync_at"

# Settings keys backing the AI Integration menu's AI Settings - local-only like the
# Sync settings above (never touched by sync.py, never leaves this
# device), holding the user's own bring-your-own AI endpoint config.
AI_ENABLED_SETTING = "ai_enabled"
AI_BASE_URL_SETTING = "ai_api_base_url"
AI_API_KEY_SETTING = "ai_api_key"
AI_MODEL_SETTING = "ai_model"

# Local-only, same reasoning as the AI settings above: whether the
# landing page's Church News box is allowed to fetch anything from
# thechurchnews.com's RSS feed. Off by default - see church_news.py's
# module docstring for why this is the one place that ever calls out
# automatically rather than in direct response to a user action.
CHURCH_NEWS_ENABLED_SETTING = "church_news_enabled"

# Same reasoning and same off-by-default policy as CHURCH_NEWS_ENABLED_SETTING
# above, for the landing page's Come Follow Me box - see cfm.py.
CFM_ENABLED_SETTING = "cfm_enabled"


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self._path: list[dict] = []  # breadcrumb segments below the root
        self._current_reading_view: ReadingView | None = None
        # Highlighter tool state - which color (or "clear") is armed, if
        # any. Deliberately not persisted like the theme/font settings
        # below: it's a transient tool selection, not a standing
        # preference, so it always starts back at "Off" on launch.
        self._armed_highlight: str | None = None
        # Which tab (Study/Citations) of the reading view's side panel is
        # selected. Each chapter navigation rebuilds ReadingView (and its
        # QTabWidget) from scratch, so without this the tab would silently
        # reset to "Study" every time - tracked here and threaded back in
        # via selected_side_tab so it survives Previous/Next navigation.
        self._side_tab_index = 0

        # Reading streak dwell gate: a chapter only counts as "read" once
        # it's been open, uninterrupted, for READING_STREAK_DWELL_MS -
        # _set_content() cancels this whenever the user navigates away
        # first, chapter-to-chapter included.
        self._streak_timer = QTimer(self)
        self._streak_timer.setSingleShot(True)
        self._streak_timer.setInterval(READING_STREAK_DWELL_MS)
        self._streak_timer.timeout.connect(self._on_streak_dwell_elapsed)
        self._pending_streak_chapter_id: int | None = None

        self._app_theme = get_setting(conn, "app_theme", "light")
        if self._app_theme not in theming.APP_THEMES:
            self._app_theme = "light"
        self._app_accent = get_setting(conn, "app_accent", theming.DEFAULT_ACCENT)
        if self._app_accent not in theming.ACCENT_HUES:
            self._app_accent = theming.DEFAULT_ACCENT
        self._reading_scheme = get_setting(conn, "reading_scheme", "day")
        if self._reading_scheme not in theming.READING_SCHEMES:
            self._reading_scheme = "day"
        self._font_family = get_setting(conn, "font_family", theming.DEFAULT_FONT_FAMILY)
        try:
            self._font_size = theming.clamp_font_size(
                int(get_setting(conn, "font_size", str(theming.DEFAULT_FONT_SIZE)))
            )
        except ValueError:
            self._font_size = theming.DEFAULT_FONT_SIZE

        self.setWindowTitle("Desktop Scriptures")
        self.resize(1000, 700)

        self._build_menu()
        theming.apply_app_theme(QApplication.instance(), self._app_theme, self._app_accent)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 6, 12, 6)
        header_row.setSpacing(0)

        self.breadcrumb = BreadcrumbBar()
        self.breadcrumb.segment_clicked.connect(self._on_breadcrumb_clicked)
        header_row.addWidget(self.breadcrumb, 1)

        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("headerSearchBar")
        self.search_bar.setFixedWidth(280)
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(lambda: self._search_debounce.start())
        self.search_bar.returnPressed.connect(self._run_search)
        header_row.addWidget(self.search_bar, 0)
        self._update_search_placeholder()

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(self._run_search)

        layout.addLayout(header_row)

        self._content_container = QWidget()
        self._content_layout = QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._content_container)

        self.show_volumes()

    # ------------------------------------------------------------------
    # Theming: menu, persistence, live apply
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        # The search bar is always visible in the header, not a page you
        # navigate to - Ctrl+F just focuses it, matching the "quick find"
        # convention most apps use for an always-on search box.
        focus_search = QAction("Focus Search", self, shortcut=QKeySequence("Ctrl+F"))
        focus_search.triggered.connect(self._focus_search_bar)
        self.addAction(focus_search)

        # Menu order left-to-right: Menu, View, Highlighter, Help.
        file_menu = self.menuBar().addMenu("&Menu")

        export_notes_action = QAction("Export Notes", self)
        export_notes_action.triggered.connect(lambda: export_notes(self.conn, self))
        file_menu.addAction(export_notes_action)

        file_menu.addSeparator()

        share_bom_action = QAction("Share the Book of Mormon", self)
        share_bom_action.triggered.connect(self._share_book_of_mormon)
        file_menu.addAction(share_bom_action)

        menu = self.menuBar().addMenu("&View")

        theme_menu = menu.addMenu("App Theme")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for name in theming.APP_THEMES:
            action = QAction(name.capitalize(), self, checkable=True)
            action.setChecked(name == self._app_theme)
            action.triggered.connect(lambda checked=False, n=name: self._set_app_theme(n))
            theme_group.addAction(action)
            theme_menu.addAction(action)

        # Which hue cards/buttons/links use, independent of light/dark
        # above - see theme.py's ACCENT_HUES for naming/design rationale.
        # Each swatch icon uses that accent's light-mode primary color
        # regardless of the app's current theme, so the menu always shows
        # a clear, recognizable version of the hue rather than dark mode's
        # more muted variant.
        accent_menu = menu.addMenu("Accent Color")
        accent_group = QActionGroup(self)
        accent_group.setExclusive(True)
        for name in theming.ACCENT_HUES:
            swatch = theming.get_app_palette("light", name).primary
            action = QAction(name, self, checkable=True)
            action.setIcon(self._swatch_icon(swatch))
            action.setChecked(name == self._app_accent)
            action.triggered.connect(lambda checked=False, n=name: self._set_app_accent(n))
            accent_group.addAction(action)
            accent_menu.addAction(action)

        scheme_menu = menu.addMenu("Reading Colors")
        scheme_group = QActionGroup(self)
        scheme_group.setExclusive(True)
        for name in theming.READING_SCHEMES:
            action = QAction(name.capitalize(), self, checkable=True)
            action.setChecked(name == self._reading_scheme)
            action.triggered.connect(lambda checked=False, n=name: self._set_reading_scheme(n))
            scheme_group.addAction(action)
            scheme_menu.addAction(action)

        font_menu = menu.addMenu("Font")
        font_group = QActionGroup(self)
        font_group.setExclusive(True)
        for name in theming.available_fonts():
            action = QAction(name, self, checkable=True)
            action.setChecked(name == self._font_family)
            action.triggered.connect(lambda checked=False, n=name: self._set_font_family(n))
            font_group.addAction(action)
            font_menu.addAction(action)

        menu.addSeparator()
        zoom_in = QAction("Zoom In", self, shortcut=QKeySequence("Ctrl+="))
        zoom_in.triggered.connect(self._zoom_in)
        menu.addAction(zoom_in)

        zoom_out = QAction("Zoom Out", self, shortcut=QKeySequence("Ctrl+-"))
        zoom_out.triggered.connect(self._zoom_out)
        menu.addAction(zoom_out)

        zoom_reset = QAction("Reset Zoom", self, shortcut=QKeySequence("Ctrl+0"))
        zoom_reset.triggered.connect(self._zoom_reset)
        menu.addAction(zoom_reset)

        menu.addSeparator()
        self._church_news_action = QAction("Show Church News Headline", self, checkable=True)
        self._church_news_action.setChecked(
            get_setting(self.conn, CHURCH_NEWS_ENABLED_SETTING) == "true"
        )
        self._church_news_action.triggered.connect(self._toggle_church_news)
        menu.addAction(self._church_news_action)

        self._cfm_action = QAction("Show Come Follow Me Helper", self, checkable=True)
        self._cfm_action.setChecked(get_setting(self.conn, CFM_ENABLED_SETTING) == "true")
        self._cfm_action.triggered.connect(self._toggle_cfm)
        menu.addAction(self._cfm_action)

        # Its own top-level menu, not a View submenu: it's a tool the user
        # reaches for mid-read to quickly switch colors, not a one-time
        # preference like the View menu's theme/font settings - burying it
        # a level deep would cost an extra click every time.
        highlight_menu = self.menuBar().addMenu("Hi&ghlighter")
        highlight_group = QActionGroup(self)
        highlight_group.setExclusive(True)

        off_action = QAction("Off", self, checkable=True)
        off_action.setChecked(True)
        off_action.triggered.connect(lambda checked=False: self._set_highlight_mode(None))
        highlight_group.addAction(off_action)
        highlight_menu.addAction(off_action)

        for color in ("yellow", "pink", "orange"):
            action = QAction(color.capitalize(), self, checkable=True)
            action.setIcon(self._swatch_icon(theming.HIGHLIGHT_COLORS[color].background))
            action.triggered.connect(lambda checked=False, c=color: self._set_highlight_mode(c))
            highlight_group.addAction(action)
            highlight_menu.addAction(action)

        highlight_menu.addSeparator()
        clear_highlight_action = QAction("Clear Highlight", self, checkable=True)
        clear_highlight_action.triggered.connect(
            lambda checked=False: self._set_highlight_mode("clear")
        )
        highlight_group.addAction(clear_highlight_action)
        highlight_menu.addAction(clear_highlight_action)

        sync_menu = self.menuBar().addMenu("Sy&nc")

        # "Sync Options...", not "Choose Sync Folder...": what the user is
        # actually picking in the dialog this opens is a cloud syncing
        # solution (Nextcloud/OneDrive/etc.) - the folder underneath it is
        # just where that choice lands, not the point of the click. The
        # dialog itself carries the "point this at a cloud-synced folder"
        # explanation, so it doesn't need repeating here too.
        sync_options_action = QAction("Sync Options...", self)
        sync_options_action.triggered.connect(self._show_sync_options)
        sync_menu.addAction(sync_options_action)

        sync_menu.addSeparator()

        self._sync_now_action = QAction("Sync Now", self)
        self._sync_now_action.triggered.connect(self._sync_now)
        sync_menu.addAction(self._sync_now_action)

        sync_menu.addSeparator()

        # Two stacked labels in their own small widget (QWidgetAction, same
        # reasoning as the Help menu's own labels below: a plain QAction's
        # text never wraps, so a long folder path would otherwise just
        # grow the menu past the window) - a short headline (an emoji
        # glyph doubles as its status icon, no separate image asset
        # needed) plus a muted detail line underneath for the folder path
        # and last-sync time.
        sync_status_widget = QWidget()
        sync_status_layout = QVBoxLayout(sync_status_widget)
        sync_status_layout.setContentsMargins(12, 4, 12, 4)
        sync_status_layout.setSpacing(2)

        self._sync_status_line = QLabel()
        sync_status_layout.addWidget(self._sync_status_line)

        self._sync_status_detail = QLabel()
        self._sync_status_detail.setObjectName("resultSecondary")
        self._sync_status_detail.setWordWrap(True)
        self._sync_status_detail.setMaximumWidth(HELP_MENU_TEXT_WIDTH)
        sync_status_layout.addWidget(self._sync_status_detail)

        sync_status_action = QWidgetAction(self)
        sync_status_action.setDefaultWidget(sync_status_widget)
        sync_menu.addAction(sync_status_action)

        # Refreshed on open too, not just right after an action - the
        # folder could disappear (an unmounted drive, an uninstalled cloud
        # client) at any time while this menu sits closed.
        sync_menu.aboutToShow.connect(self._update_sync_status)
        self._update_sync_status()

        # Opt-in, bring-your-own-endpoint AI-assisted search - see
        # ai_client.py's module docstring for the full design. The
        # feature itself lives in the search bar (see search_view.py);
        # this menu only holds its configuration.
        ai_menu = self.menuBar().addMenu("&AI Integration")

        ai_settings_action = QAction("AI Settings...", self)
        ai_settings_action.triggered.connect(self._show_ai_settings)
        ai_menu.addAction(ai_settings_action)

        # No "About" dialog - the dropdown itself carries the same
        # verbiage a popup would have (version, the unofficial-app
        # disclaimer required by the project's own stated policy, and
        # credits). Plain QAction text doesn't word-wrap (menu width just
        # grows to fit the longest line, which overflowed past the
        # window edge here), so each line is a QWidgetAction hosting a
        # word-wrapped, width-capped QLabel instead - QMenu supports that
        # fine, unlike QMenuBar itself (see the comment below on the
        # corner-widget workaround for that).
        help_menu = self.menuBar().addMenu("&Help")

        help_menu.addAction(
            self._help_menu_label(f"Desktop Scriptures — version {__version__}")
        )
        help_menu.addSeparator()
        help_menu.addAction(
            self._help_menu_label(
                "This is an unofficial application, not produced by or "
                "affiliated with The Church of Jesus Christ of Latter-day Saints."
            )
        )
        help_menu.addSeparator()
        help_menu.addAction(
            self._help_menu_label(
                f'Special thanks to <a href="{BEANDOG_REPO_URL}">Beandog</a> for '
                "the scripture text this app is built on."
            )
        )
        help_menu.addAction(
            self._help_menu_label(
                f'Special thanks to <a href="{BYU_CITATION_INDEX_URL}">BYU\'s '
                "Scripture Citation Index</a> for General Conference citation data."
            )
        )
        help_menu.addAction(
            self._help_menu_label(
                "Read the scriptures officially at "
                f'<a href="{CHURCH_SCRIPTURES_URL}">churchofjesuschrist.org</a>.'
            )
        )

        # QMenuBar doesn't actually support QWidgetAction - a widget added
        # that way gets geometry but is left unparented and never painted.
        # QMenuBar's corner-widget slot is the mechanism that does work, so
        # both the "Resume Reading" button and the streak badge live there
        # together (only one widget per corner) in their own row, sitting
        # right after Help since it's the last real menu.
        # Stored on self, not a local - PySide/shiboken can garbage-collect
        # a widget (and cascade-delete its children) once its last Python
        # reference goes out of scope, even though Qt's C++ parent-child
        # ownership nominally covers it; setCornerWidget() alone isn't
        # enough to keep this alive past _build_menu() returning.
        self._menu_corner = QWidget()
        corner_layout = QHBoxLayout(self._menu_corner)
        corner_layout.setContentsMargins(0, 0, 8, 0)
        corner_layout.setSpacing(8)

        # A plain QPushButton with clicked -> exec()'d QMenu, not
        # setMenu() - setMenu()'s built-in drop-down arrow is drawn by
        # the active Qt style, which wouldn't necessarily match this
        # app's own QSS theming the way the "▾" text suffix and the
        # already-themed QMenu rule (see theme.py) both do.
        self.resume_button = QPushButton("Resume Reading ▾")
        self.resume_button.setObjectName("resumeButton")
        self.resume_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.resume_button.clicked.connect(self._show_resume_menu)
        corner_layout.addWidget(self.resume_button)

        self.streak_label = QLabel()
        self.streak_label.setObjectName("streakBadge")
        corner_layout.addWidget(self.streak_label)

        self.menuBar().setCornerWidget(self._menu_corner, Qt.Corner.TopRightCorner)
        self._update_resume_button()
        self._update_streak_display()

    def _update_streak_display(self) -> None:
        streak = get_reading_streak(self.conn)
        if streak <= 0:
            self.streak_label.setVisible(False)
            return
        day_word = "day" if streak == 1 else "days"
        self.streak_label.setText(f"\U0001f525 {streak} {day_word} streak")
        self.streak_label.setVisible(True)

    def _update_resume_button(self) -> None:
        self.resume_button.setVisible(bool(get_reading_history(self.conn, limit=1)))

    def _show_resume_menu(self) -> None:
        entries = get_reading_history(self.conn, limit=5)
        if not entries:
            return
        menu = QMenu(self)
        for entry in entries:
            action = menu.addAction(self._history_entry_label(entry))
            action.triggered.connect(
                lambda checked=False, chapter_id=entry.chapter_id: self._resume_reading(chapter_id)
            )
        # Anchored by its right edge, not QMenu's default top-left corner -
        # this button sits in the window's own top-right corner, so a menu
        # growing rightward from its bottom-left routinely overflowed past
        # the window's own right edge instead of staying inside it.
        bottom_right = self.resume_button.mapToGlobal(self.resume_button.rect().bottomRight())
        menu.exec(bottom_right - QPoint(menu.sizeHint().width(), 0))

    _HISTORY_LABEL_MAX_LEN = 50

    @classmethod
    def _history_entry_label(cls, entry: ReadingHistoryEntry) -> str:
        """Same special-casing as _chapter_label, but book-qualified
        (e.g. "Genesis 1", not just "Chapter 1") since this list can span
        more than one book - Journal of Discourses is left as-is, since
        "Speaker - Title" is already self-describing without its book
        name ("Volume N"). Capped at _HISTORY_LABEL_MAX_LEN and elided -
        a long Journal of Discourses title otherwise blows out the menu's
        width far past any reasonable dropdown size."""
        if entry.volume_slug == "journal-of-discourses" and entry.speaker:
            label = f"{entry.speaker} - {entry.title}"
        elif entry.volume_slug == "lectures-on-faith":
            suffix = "Preface" if entry.chapter_number == 0 else f"Lecture {entry.chapter_number}"
            label = f"{entry.book_name} - {suffix}"
        else:
            label = f"{entry.book_name} {entry.chapter_number}"
        if len(label) <= cls._HISTORY_LABEL_MAX_LEN:
            return label
        return label[: cls._HISTORY_LABEL_MAX_LEN - 1].rstrip() + "…"

    def _on_streak_dwell_elapsed(self) -> None:
        if self._pending_streak_chapter_id is None:
            return
        record_reading(self.conn, self._pending_streak_chapter_id, date.today().isoformat())
        self._pending_streak_chapter_id = None
        self._update_streak_display()
        self._update_resume_button()

    def _share_book_of_mormon(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Share the Book of Mormon")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            "Share this link to the Book of Mormon with others:<br>"
            f'<a href="{BOOK_OF_MORMON_SHARE_URL}">{BOOK_OF_MORMON_SHARE_URL}</a>'
        )
        box.exec()

    def _set_app_theme(self, name: str) -> None:
        self._app_theme = name
        set_setting(self.conn, "app_theme", name)
        theming.apply_app_theme(QApplication.instance(), name, self._app_accent)

    def _set_app_accent(self, name: str) -> None:
        self._app_accent = name
        set_setting(self.conn, "app_accent", name)
        theming.apply_app_theme(QApplication.instance(), self._app_theme, name)
        # Night reading colors' verse-number tint tracks the accent too
        # (see theme.py's get_reading_palette) - only visible effect if
        # that's the active reading scheme.
        self._apply_reading_theme()

    def _set_reading_scheme(self, name: str) -> None:
        self._reading_scheme = name
        set_setting(self.conn, "reading_scheme", name)
        self._apply_reading_theme()

    def _set_font_family(self, name: str) -> None:
        self._font_family = name
        set_setting(self.conn, "font_family", name)
        self._apply_reading_theme()

    def _zoom_in(self) -> None:
        self._set_font_size(self._font_size + theming.ZOOM_STEP)

    def _zoom_out(self) -> None:
        self._set_font_size(self._font_size - theming.ZOOM_STEP)

    def _zoom_reset(self) -> None:
        self._set_font_size(theming.DEFAULT_FONT_SIZE)

    def _toggle_church_news(self, checked: bool) -> None:
        set_setting(self.conn, CHURCH_NEWS_ENABLED_SETTING, "true" if checked else "false")
        if not self._path:  # only the landing page shows the box - rebuild it if that's current
            self.show_volumes()

    def _toggle_cfm(self, checked: bool) -> None:
        set_setting(self.conn, CFM_ENABLED_SETTING, "true" if checked else "false")
        if not self._path:  # only the landing page shows the box - rebuild it if that's current
            self.show_volumes()

    def _set_font_size(self, size: int) -> None:
        self._font_size = theming.clamp_font_size(size)
        set_setting(self.conn, "font_size", str(self._font_size))
        self._apply_reading_theme()

    def _apply_reading_theme(self) -> None:
        if self._current_reading_view is not None:
            palette = theming.get_reading_palette(self._reading_scheme, self._app_accent)
            self._current_reading_view.apply_theme(
                palette, self._font_family, self._font_size
            )

    # ------------------------------------------------------------------
    # Sync (see sync.py - this app never talks to any cloud provider's
    # API, it just reads/writes small JSON files in a folder some other,
    # already-running cloud client keeps synced)
    # ------------------------------------------------------------------

    def _show_sync_options(self) -> None:
        current = get_setting(self.conn, SYNC_FOLDER_SETTING)
        dialog = SyncFolderDialog(current, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.chosen_path is None:
            return
        set_setting(self.conn, SYNC_FOLDER_SETTING, str(dialog.chosen_path))
        # "...and once confirmed, the app creates the folder and syncing
        # begins" - _sync_now() re-reads the setting just written above.
        self._sync_now()

    def _sync_now(self) -> None:
        folder = get_setting(self.conn, SYNC_FOLDER_SETTING)
        if not folder:
            return
        try:
            sync_now(self.conn, Path(folder))
        except FileNotFoundError:
            QMessageBox.warning(
                self,
                "Sync",
                f"The sync folder no longer exists:\n{folder}\n\n"
                'Choose a new one under Sync → "Sync Options...".',
            )
            self._update_sync_status()
            return
        now = self.conn.execute("SELECT datetime('now')").fetchone()[0]
        set_setting(self.conn, LAST_SYNC_SETTING, now)
        self._update_sync_status()
        # Sync can only ever change notes/tags/highlights/the reading
        # streak - the only screen any of that shows live is the reading
        # view (its side panel and inline highlights) and the streak
        # badge; nothing else on screen needs rebuilding.
        self._refresh_current_view()
        self._update_streak_display()

    def _update_sync_status(self) -> None:
        folder = get_setting(self.conn, SYNC_FOLDER_SETTING)
        if not folder:
            self._sync_status_line.setText("No sync folder configured.")
            self._sync_status_detail.setVisible(False)
            self._sync_now_action.setEnabled(False)
            return
        if not Path(folder).is_dir():
            self._sync_status_line.setText("⚠️ Sync folder no longer exists")
            self._sync_status_detail.setText(folder)
            self._sync_status_detail.setVisible(True)
            self._sync_now_action.setEnabled(False)
            return
        self._sync_now_action.setEnabled(True)
        self._sync_status_line.setText("✅ Sync folder connected")
        last_sync_at = get_setting(self.conn, LAST_SYNC_SETTING)
        when = f"Last synced: {last_sync_at} UTC" if last_sync_at else "Never synced yet"
        self._sync_status_detail.setText(f"{folder}\n{when}")
        self._sync_status_detail.setVisible(True)

    def _refresh_current_view(self) -> None:
        """Re-renders the chapter currently on screen, if any, so a note/
        tag/highlight another device just contributed shows up right away
        instead of waiting for the next navigation."""
        if self._current_reading_view is None:
            return
        chapter_id = self._current_reading_view.chapter_id
        location = get_chapter_location(self.conn, chapter_id)
        if location is None:
            return
        volume, testament, book, _chapter = location
        self._on_chapter_clicked(volume, testament, book, chapter_id)

    # ------------------------------------------------------------------
    # AI Integration (opt-in, bring-your-own-endpoint AI-assisted search -
    # see ai_client.py's module docstring for the full design)
    # ------------------------------------------------------------------

    def _show_ai_settings(self) -> None:
        dialog = AiSettingsDialog(
            enabled=get_setting(self.conn, AI_ENABLED_SETTING) == "true",
            base_url=get_setting(self.conn, AI_BASE_URL_SETTING, ""),
            api_key=get_setting(self.conn, AI_API_KEY_SETTING, ""),
            model=get_setting(self.conn, AI_MODEL_SETTING, ""),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        set_setting(self.conn, AI_ENABLED_SETTING, "true" if dialog.enabled else "false")
        set_setting(self.conn, AI_BASE_URL_SETTING, dialog.base_url)
        set_setting(self.conn, AI_API_KEY_SETTING, dialog.api_key)
        set_setting(self.conn, AI_MODEL_SETTING, dialog.model)
        self._update_search_placeholder()

    def _update_search_placeholder(self) -> None:
        """The search bar's placeholder/tooltip are the only hint that
        AI-assisted search exists at all - without this, there's nothing
        in the UI suggesting a full natural-language question works there
        too, not just keywords/references. Refreshed here and right after
        AI Settings closes, so turning it on/off takes effect immediately
        rather than needing a restart to notice."""
        if self._current_ai_config() is not None:
            self.search_bar.setPlaceholderText("Ask a question, or search...")
            # A plain-text QToolTip doesn't wrap - Qt just renders it as
            # one unbroken line, which for a sentence this long extended
            # well past the window's own edge. Wrapping it in a width-
            # capped <div> makes Qt treat it as rich text, which does wrap.
            self.search_bar.setToolTip(
                '<div style="max-width: 320px;">'
                "Search verses, notes, and tags, or ask a full question in "
                "your own words - e.g. \"how did Christ organize the "
                "Nephite church\" - and AI-assisted search will suggest "
                "matching scripture."
                "</div>"
            )
        else:
            self.search_bar.setPlaceholderText("Search verses, notes, tags...")
            self.search_bar.setToolTip("")

    def _on_side_tab_changed(self, index: int) -> None:
        self._side_tab_index = index

    @staticmethod
    def _chapter_label(volume: Volume, chapter: Chapter) -> str:
        """Card/breadcrumb label for one chapter - "Section N" for D&C,
        "Speaker - Title" for a Journal of Discourses discourse (its
        chapter_number is just a sequential position, not something a
        reader would recognize the way a section number is), "Preface"/
        "Lecture N" for Lectures on Faith (chapter_number 0 is the
        preface, which precedes "Lecture First" in the original and
        isn't itself a lecture), "Chapter N" otherwise."""
        if volume.slug == "journal-of-discourses" and chapter.speaker:
            return f"{chapter.speaker} - {chapter.title}"
        if volume.slug == "lectures-on-faith":
            return "Preface" if chapter.chapter_number == 0 else f"Lecture {chapter.chapter_number}"
        unit = "Section" if volume.slug == "doctrine-and-covenants" else "Chapter"
        return f"{unit} {chapter.chapter_number}"

    @staticmethod
    def _chapter_subtitle(chapter: Chapter) -> str | None:
        """Speaker/title/date line for the reading view header - only
        Journal of Discourses chapters have this context to show."""
        if not chapter.speaker:
            return None
        date_label = MainWindow._format_discourse_date(chapter.discourse_date)
        by_line = f"{chapter.speaker}, {date_label}" if date_label else chapter.speaker
        return f"{chapter.title} — {by_line}"

    @staticmethod
    def _format_discourse_date(iso_date: str | None) -> str | None:
        if not iso_date:
            return None
        try:
            if len(iso_date) == 7:  # "YYYY-MM" - day unknown
                return date.fromisoformat(iso_date + "-01").strftime("%B %Y")
            return date.fromisoformat(iso_date).strftime("%B %-d, %Y")
        except ValueError:
            return iso_date

    @staticmethod
    def _swatch_icon(hex_color: str) -> QIcon:
        pixmap = QPixmap(QSize(14, 14))
        pixmap.fill(QColor(hex_color))
        return QIcon(pixmap)

    def _help_menu_label(self, html: str) -> QWidgetAction:
        """One line of the Help menu, as a word-wrapped QLabel hosted in a
        QWidgetAction rather than a plain QAction - see the comment where
        the Help menu is built for why. Any <a href> in `html` is left
        clickable (opens in the browser) via setOpenExternalLinks; a line
        with no link is just inert text, same as a disabled QAction."""
        label = QLabel(html)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        label.setWordWrap(True)
        label.setMaximumWidth(HELP_MENU_TEXT_WIDTH)
        label.setContentsMargins(12, 4, 12, 4)
        action = QWidgetAction(self)
        action.setDefaultWidget(label)
        return action

    def _set_highlight_mode(self, mode: str | None) -> None:
        self._armed_highlight = mode
        if self._current_reading_view is not None:
            self._current_reading_view.set_armed_highlight(mode)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if self._current_reading_view is not None:
            self._current_reading_view.flush_pending_save()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Content swapping / breadcrumb
    # ------------------------------------------------------------------

    def _set_content(self, widget: QWidget) -> None:
        # Whatever was showing before is being navigated away from - if it
        # was a chapter still mid-dwell (see READING_STREAK_DWELL_MS), that
        # visit didn't last long enough to count.
        self._streak_timer.stop()
        self._pending_streak_chapter_id = None

        if widget is not self._current_reading_view:
            self._current_reading_view = None
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                old = item.widget()
                # A ReadingView being replaced may have an unsaved,
                # debounced chapter note - flush it now rather than losing
                # whatever was typed in the last ~second before navigating.
                flush = getattr(old, "flush_pending_save", None)
                if flush is not None:
                    flush()
                # hide() first: see the matching comment in
                # BreadcrumbBar.set_path() - deleteLater() alone defers the
                # repaint that clears the old widget's region, which can
                # leave stale pixels behind (very visible now that section
                # titles are opaque rounded surfaces rather than a plain
                # background with a thin border).
                old.hide()
                old.deleteLater()
        self._content_layout.addWidget(widget)

    def _update_breadcrumb(self) -> None:
        # On the landing page itself there's nowhere for "Desktop
        # Scriptures" to navigate back to (and the centered title already
        # says it), so the breadcrumb stays empty there rather than
        # showing a redundant, non-clickable root segment.
        labels = ["Desktop Scriptures"] + [seg["label"] for seg in self._path] if self._path else []
        self.breadcrumb.set_path(labels)

    def _on_breadcrumb_clicked(self, index: int) -> None:
        if index == 0:
            self.show_volumes()
        else:
            self._path[index - 1]["action"]()

    # ------------------------------------------------------------------
    # Level: volumes (landing page)
    # ------------------------------------------------------------------

    def show_volumes(self) -> None:
        self._path = []
        self._update_breadcrumb()
        volumes = get_volumes(self.conn)

        sotd_label = None
        sotd = get_scripture_of_the_day(self.conn)
        if sotd is not None:
            sotd_label = QLabel(
                "<b>Scripture of the Day:</b><br>"
                f"{escape(sotd.text)} - {escape(sotd.reference)}"
            )
            sotd_label.setTextFormat(Qt.TextFormat.RichText)
            sotd_label.setObjectName("sotdBanner")
            sotd_label.setWordWrap(True)
            sotd_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        news_enabled = get_setting(self.conn, CHURCH_NEWS_ENABLED_SETTING) == "true"
        news_box = ChurchNewsBox(news_enabled)
        news_box.enable_requested.connect(self._enable_church_news)

        cfm_enabled = get_setting(self.conn, CFM_ENABLED_SETTING) == "true"
        cfm_box = CfmBox(cfm_enabled)
        cfm_box.enable_requested.connect(self._enable_cfm)

        # A single composite widget fills CardGridWidget's existing
        # optional `banner` slot - it only ever wanted one widget, and it
        # was already generic enough to not care what's inside it. A grid
        # (not two independent HBoxLayout rows) guarantees Come Follow
        # Me's column lines up exactly with Scripture of the Day's right
        # below it - a grid's columns are always the same width in every
        # row, where two separately-computed row layouts could drift out
        # of alignment depending on each row's own content.
        banner = QWidget()
        banner_grid = QGridLayout(banner)
        banner_grid.setContentsMargins(0, 0, 0, 0)
        banner_grid.setHorizontalSpacing(8)
        banner_grid.setVerticalSpacing(8)
        banner_grid.setColumnStretch(0, 3)
        banner_grid.setColumnStretch(1, 2)

        # Come Follow Me sits above Church News, in the top-right; the
        # top-left cell (above Scripture of the Day) is left empty for
        # now.
        banner_grid.addWidget(cfm_box, 0, 1)

        if sotd_label is not None:
            banner_grid.addWidget(sotd_label, 1, 0)
            banner_grid.addWidget(news_box, 1, 1)
        else:
            banner_grid.addWidget(news_box, 1, 0, 1, 2)

        grid = CardGridWidget(
            "Desktop Scriptures",
            [(v.id, v.name) for v in volumes] + [(TOPICAL_GUIDE_ID, "Topical Guide")],
            card_size=LANDING_CARD_SIZE,
            banner=banner,
            show_title=False,
        )
        grid.card_clicked.connect(self._on_volume_clicked)
        self._set_content(grid)

    def _enable_church_news(self) -> None:
        set_setting(self.conn, CHURCH_NEWS_ENABLED_SETTING, "true")
        self._church_news_action.setChecked(True)
        self.show_volumes()

    def _enable_cfm(self) -> None:
        set_setting(self.conn, CFM_ENABLED_SETTING, "true")
        self._cfm_action.setChecked(True)
        self.show_volumes()

    def _resume_reading(self, chapter_id: int) -> None:
        location = get_chapter_location(self.conn, chapter_id)
        if location is None:
            return
        volume, testament, book, _chapter = location
        self._on_chapter_clicked(volume, testament, book, chapter_id)

    # ------------------------------------------------------------------
    # Topical Guide
    # ------------------------------------------------------------------

    def _show_topical_guide(self) -> None:
        self._path = [{"label": "Topical Guide", "action": self._show_topical_guide}]
        self._update_breadcrumb()
        topics = get_topics(self.conn)
        grid = CardGridWidget("Topical Guide", [(t.id, t.name) for t in topics])
        grid.card_clicked.connect(self._show_topic_detail)
        self._set_content(grid)

    def _show_topic_detail(self, topic_id: int) -> None:
        topic = get_topic(self.conn, topic_id)
        self._path = [
            {"label": "Topical Guide", "action": self._show_topical_guide},
            {"label": topic.name, "action": lambda: self._show_topic_detail(topic_id)},
        ]
        self._update_breadcrumb()

        verses = get_topic_verses(self.conn, topic_id)
        talks = get_topic_talks(self.conn, topic_id)
        view = TopicDetailView(topic, verses, talks)
        # Same handler Search uses: resolve a chapter id into its full
        # volume/testament/book path and navigate there.
        view.scripture_selected.connect(self._on_search_result_selected)
        self._set_content(view)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _focus_search_bar(self) -> None:
        self.search_bar.setFocus()
        self.search_bar.selectAll()

    def _run_search(self) -> None:
        query = self.search_bar.text().strip()
        if not query:
            return
        self._path = [{"label": "Search", "action": self._run_search}]
        self._update_breadcrumb()
        view = SearchView(self.conn, ai_config=self._current_ai_config())
        view.result_selected.connect(self._on_search_result_selected)
        view.set_query(query)
        self._set_content(view)

    def _current_ai_config(self) -> AiConfig | None:
        """None means "don't even try" - AI-assisted search is off, or on
        but missing the one thing (a base URL) it can't run without. An
        API key is deliberately not required here either - see
        ai_client.py's module docstring."""
        if get_setting(self.conn, AI_ENABLED_SETTING) != "true":
            return None
        base_url = get_setting(self.conn, AI_BASE_URL_SETTING, "")
        if not base_url:
            return None
        return AiConfig(
            base_url=base_url,
            api_key=get_setting(self.conn, AI_API_KEY_SETTING, ""),
            model=get_setting(self.conn, AI_MODEL_SETTING, ""),
        )

    def _on_search_result_selected(self, chapter_id: int) -> None:
        location = get_chapter_location(self.conn, chapter_id)
        if location is None:
            return
        volume, testament, book, _chapter = location
        self._on_chapter_clicked(volume, testament, book, chapter_id)

    # ------------------------------------------------------------------
    # Level: testament (Bible only) or straight to books
    # ------------------------------------------------------------------

    def _on_volume_clicked(self, volume_id: int | str) -> None:
        if volume_id == TOPICAL_GUIDE_ID:
            self._show_topical_guide()
            return
        volume = get_volume(self.conn, volume_id)
        self._path = [
            {"label": volume.name, "action": lambda: self._on_volume_clicked(volume_id)}
        ]
        self._update_breadcrumb()

        testaments = get_testaments(self.conn, volume_id)
        if testaments:
            grid = CardGridWidget(volume.name, [(t.id, t.name) for t in testaments])
            grid.card_clicked.connect(lambda tid: self._on_testament_clicked(volume, tid))
        else:
            books = get_books(self.conn, volume_id)
            grid = CardGridWidget(volume.name, [(b.id, b.name) for b in books])
            grid.card_clicked.connect(lambda bid: self._on_book_clicked(volume, None, bid))
        self._set_content(grid)

    def _on_testament_clicked(self, volume: Volume, testament_id: int) -> None:
        testament = get_testament(self.conn, testament_id)
        self._path = [
            {"label": volume.name, "action": lambda: self._on_volume_clicked(volume.id)},
            {
                "label": testament.name,
                "action": lambda: self._on_testament_clicked(volume, testament_id),
            },
        ]
        self._update_breadcrumb()

        books = get_books(self.conn, volume.id, testament_id)
        grid = CardGridWidget(testament.name, [(b.id, b.name) for b in books])
        grid.card_clicked.connect(
            lambda bid: self._on_book_clicked(volume, testament, bid)
        )
        self._set_content(grid)

    # ------------------------------------------------------------------
    # Level: book -> chapters
    # ------------------------------------------------------------------

    def _on_book_clicked(
        self, volume: Volume, testament: Testament | None, book_id: int
    ) -> None:
        book = get_book(self.conn, book_id)

        path = [{"label": volume.name, "action": lambda: self._on_volume_clicked(volume.id)}]
        if testament:
            path.append(
                {
                    "label": testament.name,
                    "action": lambda: self._on_testament_clicked(volume, testament.id),
                }
            )
        path.append(
            {
                "label": book.name,
                "action": lambda: self._on_book_clicked(volume, testament, book_id),
            }
        )
        self._path = path
        self._update_breadcrumb()

        chapters = get_chapters(self.conn, book_id)
        items = [(c.id, self._chapter_label(volume, c)) for c in chapters]
        grid = CardGridWidget(book.name, items)
        grid.card_clicked.connect(
            lambda cid: self._on_chapter_clicked(volume, testament, book, cid)
        )
        self._set_content(grid)

    # ------------------------------------------------------------------
    # Level: chapter -> reading view
    # ------------------------------------------------------------------

    def _adjacent_chapter(
        self,
        volume: Volume,
        testament: Testament | None,
        book: Book,
        chapter: Chapter,
        direction: int,
    ) -> tuple[Testament | None, Book, Chapter] | None:
        """The chapter one step before/after this one (direction -1/+1),
        rolling into the next/previous book - and, within the Bible, across
        the Old/New Testament boundary too - but never out of the current
        volume. None at the very start/end of the volume.

        Book sort_order is only meaningful within a single testament (e.g.
        Matthew and Genesis are both sort_order 1, in different
        testaments), so book lists are always re-fetched scoped to a
        specific testament rather than compared by sort_order alone.
        """
        chapters = get_chapters(self.conn, book.id)
        idx = next(i for i, c in enumerate(chapters) if c.id == chapter.id)
        new_idx = idx + direction
        if 0 <= new_idx < len(chapters):
            return testament, book, chapters[new_idx]

        book_list = get_books(self.conn, volume.id, testament.id if testament else None)
        book_idx = next(i for i, b in enumerate(book_list) if b.id == book.id)
        new_book_idx = book_idx + direction
        if 0 <= new_book_idx < len(book_list):
            new_book = book_list[new_book_idx]
            new_chapters = get_chapters(self.conn, new_book.id)
            new_chapter = new_chapters[0] if direction > 0 else new_chapters[-1]
            return testament, new_book, new_chapter

        if testament is not None:
            testaments = get_testaments(self.conn, volume.id)
            t_idx = next(i for i, t in enumerate(testaments) if t.id == testament.id)
            new_t_idx = t_idx + direction
            if 0 <= new_t_idx < len(testaments):
                new_testament = testaments[new_t_idx]
                new_books = get_books(self.conn, volume.id, new_testament.id)
                new_book = new_books[0] if direction > 0 else new_books[-1]
                new_chapters = get_chapters(self.conn, new_book.id)
                new_chapter = new_chapters[0] if direction > 0 else new_chapters[-1]
                return new_testament, new_book, new_chapter

        return None

    def _on_chapter_clicked(
        self,
        volume: Volume,
        testament: Testament | None,
        book: Book,
        chapter_id: int,
    ) -> None:
        # Flush before reading anything below, not just before _set_content
        # tears the old view down (too late): the new ReadingView's own
        # constructor reads notes/tags/highlights from the database, and
        # would otherwise see stale data if this chapter (or a note
        # attached to it) still has an unflushed debounced edit pending -
        # most noticeably when re-navigating to the very chapter you're
        # already on.
        if self._current_reading_view is not None:
            self._current_reading_view.flush_pending_save()

        chapter = get_chapter(self.conn, chapter_id)

        path = [{"label": volume.name, "action": lambda: self._on_volume_clicked(volume.id)}]
        if testament:
            path.append(
                {
                    "label": testament.name,
                    "action": lambda: self._on_testament_clicked(volume, testament.id),
                }
            )
        path.append(
            {
                "label": book.name,
                "action": lambda: self._on_book_clicked(volume, testament, book.id),
            }
        )
        path.append(
            {
                "label": self._chapter_label(volume, chapter),
                "action": lambda: self._on_chapter_clicked(
                    volume, testament, book, chapter_id
                ),
            }
        )
        self._path = path
        self._update_breadcrumb()

        verses = get_verses(self.conn, chapter_id)
        title = verses[0].reference.rsplit(":", 1)[0] if verses else book.name
        palette = theming.get_reading_palette(self._reading_scheme, self._app_accent)
        prev_target = self._adjacent_chapter(volume, testament, book, chapter, -1)
        next_target = self._adjacent_chapter(volume, testament, book, chapter, 1)
        view = ReadingView(
            self.conn,
            chapter_id,
            title,
            verses,
            palette,
            self._font_family,
            self._font_size,
            has_previous=prev_target is not None,
            has_next=next_target is not None,
            armed_highlight=self._armed_highlight,
            selected_side_tab=self._side_tab_index,
            subtitle=self._chapter_subtitle(chapter),
        )
        view.zoom_in_requested.connect(self._zoom_in)
        view.zoom_out_requested.connect(self._zoom_out)
        view.side_tab_changed.connect(self._on_side_tab_changed)
        if prev_target is not None:
            pt, pb, pc = prev_target
            view.prev_requested.connect(lambda: self._on_chapter_clicked(volume, pt, pb, pc.id))
        if next_target is not None:
            nt, nb, nc = next_target
            view.next_requested.connect(lambda: self._on_chapter_clicked(volume, nt, nb, nc.id))
        self._current_reading_view = view
        self._set_content(view)

        # Reading streak: only counts once this chapter has stayed open,
        # uninterrupted, for READING_STREAK_DWELL_MS - see _set_content()
        # (cancels this on navigating away) and _on_streak_dwell_elapsed().
        self._pending_streak_chapter_id = chapter_id
        self._streak_timer.start()
