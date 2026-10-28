"""Standalone test script for the per-verse note/tag entries in
src/scriptures/ui/chapter_panel.py. No test framework (see
tests/test_ask.py's docstring); offscreen Qt, a copy of the shipped
data/scriptures.db.

Run directly:

    python3 tests/test_chapter_panel.py
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

from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget  # noqa: E402

from scriptures import data_access as da  # noqa: E402
from scriptures.db import connect  # noqa: E402
from scriptures.ui.chapter_panel import ChapterPanel  # noqa: E402


def _settle() -> None:
    for _ in range(5):
        QApplication.processEvents()


def _window(conn):
    """The panel for 1 Nephi 3 next to a stand-in for the reading view, so
    focus has somewhere outside the panel to go."""
    verse = da.get_verse_by_reference(conn, "1 Nephi", 3, 7)
    window = QWidget()
    layout = QVBoxLayout(window)
    outside = QLineEdit()
    layout.addWidget(outside)
    panel = ChapterPanel(conn, verse.chapter_id, da.get_verses(conn, verse.chapter_id), set())
    layout.addWidget(panel)
    window.show()
    window.activateWindow()
    outside.setFocus()
    _settle()
    return window, outside, panel, verse


def test_tag_only_verse() -> None:
    """The pencil icon focuses the note box; clicking over to the tag box
    must not throw the (still empty) entry away before a tag is typed."""
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-chapter-panel-"))
    try:
        shutil.copy(PROJECT_ROOT / "data" / "scriptures.db", tmp / "s.db")
        conn = connect(tmp / "s.db")
        window, outside, panel, verse = _window(conn)

        panel.focus_verse(verse)
        _settle()
        entry = panel._verse_entries[verse.id]
        assert entry._note.text_edit.hasFocus()

        entry.tag_input.setFocus()
        _settle()
        assert verse.id in panel._verse_entries, "entry vanished when moving to the tag box"

        entry.tag_input.setText("faith")
        entry._add_tag()
        outside.setFocus()
        _settle()
        assert verse.id in panel._verse_entries
        assert [t.name for t in da.get_tags(conn, verse_id=verse.id)] == ["faith"]
        assert da.get_note(conn, verse_id=verse.id) is None
        window.close()
        conn.close()
        print("test_tag_only_verse: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_empty_entry_goes_once_left() -> None:
    """Opened with the pencil and left without a note or tag: the entry
    still disappears, but only when focus leaves the entry - including
    after its last tag is removed."""
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-chapter-panel-"))
    try:
        shutil.copy(PROJECT_ROOT / "data" / "scriptures.db", tmp / "s.db")
        conn = connect(tmp / "s.db")
        window, outside, panel, verse = _window(conn)

        panel.focus_verse(verse)
        _settle()
        outside.setFocus()
        _settle()
        assert verse.id not in panel._verse_entries

        panel.focus_verse(verse)
        _settle()
        entry = panel._verse_entries[verse.id]
        entry.tag_input.setFocus()
        entry.tag_input.setText("faith")
        entry._add_tag()
        tag = da.get_tags(conn, verse_id=verse.id)[0]
        entry._remove_tag(tag.id)
        _settle()
        assert verse.id in panel._verse_entries, "entry vanished while still being edited"

        outside.setFocus()
        _settle()
        assert verse.id not in panel._verse_entries
        window.close()
        conn.close()
        print("test_empty_entry_goes_once_left: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_tag_only_verse()
    test_empty_entry_goes_once_left()
    print("All chapter panel tests passed.")
