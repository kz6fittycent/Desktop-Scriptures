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

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from scriptures.data_access import (
    Book,
    Testament,
    Volume,
    get_book,
    get_books,
    get_chapter,
    get_chapter_location,
    get_chapters,
    get_last_read_chapter_id,
    get_reading_streak,
    get_setting,
    get_testament,
    get_testaments,
    get_verses,
    get_volume,
    get_volumes,
    record_reading,
    set_setting,
)
from scriptures.ui.about_dialog import AboutDialog
from scriptures.ui.breadcrumb import BreadcrumbBar
from scriptures.ui.card_grid import LANDING_CARD_SIZE, CardGridWidget
from scriptures.ui.export import export_notes
from scriptures.ui.reading_view import ReadingView
from scriptures.ui.search_view import SearchView
from scriptures.ui import theme as theming

BOOK_OF_MORMON_SHARE_URL = "https://go.churchofjesuschrist.org/x/n1Ic"


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self._path: list[dict] = []  # breadcrumb segments below the root
        self._current_reading_view: ReadingView | None = None

        self._app_theme = get_setting(conn, "app_theme", "light")
        if self._app_theme not in theming.APP_THEMES:
            self._app_theme = "light"
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
        theming.apply_app_theme(QApplication.instance(), self._app_theme)

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
        self.search_bar.setPlaceholderText("Search verses, notes, tags...")
        self.search_bar.setFixedWidth(280)
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(lambda: self._search_debounce.start())
        self.search_bar.returnPressed.connect(self._run_search)
        header_row.addWidget(self.search_bar, 0)

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

        # Menu order left-to-right: Menu, View, Help.
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

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction("&About Desktop Scriptures", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

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

        self.resume_button = QPushButton("Resume Reading")
        self.resume_button.setObjectName("resumeButton")
        self.resume_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.resume_button.clicked.connect(self._resume_reading)
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
        self.resume_button.setVisible(get_last_read_chapter_id(self.conn) is not None)

    def _show_about(self) -> None:
        AboutDialog(self).exec()

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
        theming.apply_app_theme(QApplication.instance(), name)

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

    def _set_font_size(self, size: int) -> None:
        self._font_size = theming.clamp_font_size(size)
        set_setting(self.conn, "font_size", str(self._font_size))
        self._apply_reading_theme()

    def _apply_reading_theme(self) -> None:
        if self._current_reading_view is not None:
            palette = theming.READING_PALETTES[self._reading_scheme]
            self._current_reading_view.apply_theme(
                palette, self._font_family, self._font_size
            )

    # ------------------------------------------------------------------
    # Content swapping / breadcrumb
    # ------------------------------------------------------------------

    def _set_content(self, widget: QWidget) -> None:
        if widget is not self._current_reading_view:
            self._current_reading_view = None
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                # hide() first: see the matching comment in
                # BreadcrumbBar.set_path() - deleteLater() alone defers the
                # repaint that clears the old widget's region, which can
                # leave stale pixels behind (very visible now that section
                # titles are opaque rounded surfaces rather than a plain
                # background with a thin border).
                item.widget().hide()
                item.widget().deleteLater()
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
        grid = CardGridWidget(
            "Desktop Scriptures",
            [(v.id, v.name) for v in volumes],
            card_size=LANDING_CARD_SIZE,
        )
        grid.card_clicked.connect(self._on_volume_clicked)
        self._set_content(grid)

    def _resume_reading(self) -> None:
        chapter_id = get_last_read_chapter_id(self.conn)
        if chapter_id is None:
            return
        location = get_chapter_location(self.conn, chapter_id)
        if location is None:
            return
        volume, testament, book, _chapter = location
        self._on_chapter_clicked(volume, testament, book, chapter_id)

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
        view = SearchView(self.conn)
        view.result_selected.connect(self._on_search_result_selected)
        view.set_query(query)
        self._set_content(view)

    def _on_search_result_selected(self, chapter_id: int) -> None:
        location = get_chapter_location(self.conn, chapter_id)
        if location is None:
            return
        volume, testament, book, _chapter = location
        self._on_chapter_clicked(volume, testament, book, chapter_id)

    # ------------------------------------------------------------------
    # Level: testament (Bible only) or straight to books
    # ------------------------------------------------------------------

    def _on_volume_clicked(self, volume_id: int) -> None:
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
        unit = "Section" if volume.slug == "doctrine-and-covenants" else "Chapter"
        items = [(c.id, f"{unit} {c.chapter_number}") for c in chapters]
        grid = CardGridWidget(book.name, items)
        grid.card_clicked.connect(
            lambda cid: self._on_chapter_clicked(volume, testament, book, cid)
        )
        self._set_content(grid)

    # ------------------------------------------------------------------
    # Level: chapter -> reading view
    # ------------------------------------------------------------------

    def _on_chapter_clicked(
        self,
        volume: Volume,
        testament: Testament | None,
        book: Book,
        chapter_id: int,
    ) -> None:
        chapter = get_chapter(self.conn, chapter_id)
        unit = "Section" if volume.slug == "doctrine-and-covenants" else "Chapter"

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
                "label": f"{unit} {chapter.chapter_number}",
                "action": lambda: self._on_chapter_clicked(
                    volume, testament, book, chapter_id
                ),
            }
        )
        self._path = path
        self._update_breadcrumb()

        verses = get_verses(self.conn, chapter_id)
        title = verses[0].reference.rsplit(":", 1)[0] if verses else book.name
        palette = theming.READING_PALETTES[self._reading_scheme]
        view = ReadingView(
            self.conn, chapter_id, title, verses, palette, self._font_family, self._font_size
        )
        view.zoom_in_requested.connect(self._zoom_in)
        view.zoom_out_requested.connect(self._zoom_out)
        self._current_reading_view = view
        self._set_content(view)

        # Reading streak: opening a chapter counts as "read" for today,
        # regardless of how much is actually read (per product decision).
        record_reading(self.conn, chapter_id, date.today().isoformat())
        self._update_streak_display()
        self._update_resume_button()
