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

from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from scriptures.data_access import (
    Book,
    Testament,
    Volume,
    get_book,
    get_books,
    get_chapter,
    get_chapters,
    get_testament,
    get_testaments,
    get_verses,
    get_volume,
    get_volumes,
    record_reading,
)
from scriptures.ui.breadcrumb import BreadcrumbBar
from scriptures.ui.card_grid import CardGridWidget
from scriptures.ui.reading_view import ReadingView


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self._path: list[dict] = []  # breadcrumb segments below the root

        self.setWindowTitle("Scriptures")
        self.resize(1000, 700)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.breadcrumb = BreadcrumbBar()
        self.breadcrumb.segment_clicked.connect(self._on_breadcrumb_clicked)
        layout.addWidget(self.breadcrumb)

        self._content_container = QWidget()
        self._content_layout = QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._content_container)

        self.show_volumes()

    # ------------------------------------------------------------------
    # Content swapping / breadcrumb
    # ------------------------------------------------------------------

    def _set_content(self, widget: QWidget) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._content_layout.addWidget(widget)

    def _update_breadcrumb(self) -> None:
        labels = ["Scriptures"] + [seg["label"] for seg in self._path]
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
        grid = CardGridWidget("Scriptures", [(v.id, v.name) for v in volumes], columns=4)
        grid.card_clicked.connect(self._on_volume_clicked)
        self._set_content(grid)

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
            grid = CardGridWidget(
                volume.name, [(t.id, t.name) for t in testaments], columns=2
            )
            grid.card_clicked.connect(lambda tid: self._on_testament_clicked(volume, tid))
        else:
            books = get_books(self.conn, volume_id)
            grid = CardGridWidget(volume.name, [(b.id, b.name) for b in books], columns=4)
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
        grid = CardGridWidget(testament.name, [(b.id, b.name) for b in books], columns=4)
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
        grid = CardGridWidget(book.name, items, columns=6)
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
        view = ReadingView(title, verses)
        self._set_content(view)

        # Reading streak: opening a chapter counts as "read" for today,
        # regardless of how much is actually read (per product decision).
        record_reading(self.conn, chapter_id, date.today().isoformat())
