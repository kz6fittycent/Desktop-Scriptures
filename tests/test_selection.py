"""Standalone test script for selecting and copying text in the reading
view (ui/reading_view.py): a plain drag, with no highlighter armed,
selects - within a verse or across several - and Copy takes all of it.
No test framework (see tests/test_ask.py's docstring); offscreen Qt, a
copy of the shipped data/scriptures.db.

Run directly:

    python3 tests/test_selection.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QKeySequence, QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scriptures import data_access as da  # noqa: E402
from scriptures.db import connect  # noqa: E402
from scriptures.ui import theme  # noqa: E402
from scriptures.ui.reading_view import ReadingView  # noqa: E402


def _mouse(widget, kind, offset: int, buttons) -> None:
    """A mouse event over character `offset` of a verse widget, sent the
    way a real one arrives (so ReadingView's event filter sees it too)."""
    cursor = widget.textCursor()
    cursor.setPosition(offset)
    local = QPointF(widget.cursorRect(cursor).center())
    viewport = widget.viewport()
    event = QMouseEvent(
        kind, local, QPointF(viewport.mapToGlobal(local.toPoint())),
        Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton,
        buttons, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(viewport, event)


def test_drag_selects_and_copy_takes_it_all() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-selection-"))
    try:
        shutil.copy(PROJECT_ROOT / "data" / "scriptures.db", tmp / "s.db")
        conn = connect(tmp / "s.db")
        chapter_id = conn.execute(
            "SELECT c.id FROM chapters c JOIN books b ON b.id = c.book_id "
            "WHERE b.name = 'John' AND c.chapter_number = 3"
        ).fetchone()[0]
        verses = da.get_verses(conn, chapter_id)
        view = ReadingView(conn, chapter_id, "John 3", verses, theme.get_reading_palette("day"), "Serif", 14)
        view.resize(1200, 800)
        view.show()
        QApplication.processEvents()
        v16, v17 = verses[15], verses[16]
        body16, body17 = view._body_widgets[v16.id], view._body_widgets[v17.id]
        held = Qt.MouseButton.LeftButton

        # Within one verse: "For God so loved the world".
        _mouse(body16, QEvent.Type.MouseButtonPress, 0, held)
        _mouse(body16, QEvent.Type.MouseMove, 26, held)
        _mouse(body16, QEvent.Type.MouseButtonRelease, 26, Qt.MouseButton.NoButton)
        assert body16.textCursor().selectedText().startswith("For God so loved the world"), body16.textCursor().selectedText()
        QTest.keySequence(body16, QKeySequence.StandardKey.Copy)
        assert QGuiApplication.clipboard().text().startswith("For God so loved the world")
        assert not da.get_highlights(conn, chapter_id)  # nothing armed, nothing highlighted

        # Across two verses: each verse's part, numbered.
        _mouse(body16, QEvent.Type.MouseButtonPress, 0, held)
        _mouse(body17, QEvent.Type.MouseMove, len(v17.text), held)
        _mouse(body17, QEvent.Type.MouseButtonRelease, len(v17.text), Qt.MouseButton.NoButton)
        assert body16.textCursor().hasSelection() and body17.textCursor().hasSelection()
        view._copy_selection()
        copied = QGuiApplication.clipboard().text()
        assert copied == f"16 {v16.text.strip()}\n17 {v17.text.strip()}", repr(copied)

        # A new click elsewhere drops the old multi-verse selection.
        _mouse(body17, QEvent.Type.MouseButtonPress, 3, held)
        _mouse(body17, QEvent.Type.MouseButtonRelease, 3, Qt.MouseButton.NoButton)
        assert not body16.textCursor().hasSelection()

        # With a highlighter armed, the same drag highlights instead.
        view.set_armed_highlight("yellow")
        _mouse(body16, QEvent.Type.MouseButtonPress, 0, held)
        _mouse(body16, QEvent.Type.MouseMove, 26, held)
        _mouse(body16, QEvent.Type.MouseButtonRelease, 26, Qt.MouseButton.NoButton)
        assert da.get_highlights(conn, chapter_id)
        print("test_drag_selects_and_copy_takes_it_all: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_drag_selects_and_copy_takes_it_all()
    print("All selection tests passed.")
