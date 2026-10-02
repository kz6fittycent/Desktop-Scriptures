"""Standalone test script for the Word Study tab (ui/word_study_panel.py)
and the lexicon entry view it shares with LexiconDialog
(ui/lexicon_dialog.py). No test framework (see tests/test_ask.py's own
docstring for why); offscreen Qt, the shipped data/scriptures.db's real
lexicon, read-only.

Run directly:

    python3 tests/test_word_study.py
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

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from scriptures import data_access as da  # noqa: E402
from scriptures.db import connect  # noqa: E402
from scriptures.ui import theme  # noqa: E402
from scriptures.ui.lexicon_dialog import LexiconDialog, LexiconEntryView  # noqa: E402
from scriptures.ui.word_study_panel import INTRO, WordStudyPanel  # noqa: E402


def _conn(tmp: Path):
    # A copy, since connect() writes schema/settings into what it opens.
    shutil.copy(PROJECT_ROOT / "data" / "scriptures.db", tmp / "s.db")
    return connect(tmp / "s.db")


def test_look_up_shows_matches_and_the_best_entry() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-word-study-"))
    try:
        panel = WordStudyPanel(_conn(tmp))
        panel.look_up("  anointed ")
        assert panel._input.text() == "anointed"
        assert panel._buttons[0].strongs == "H4899" and panel._buttons[0].isChecked()
        assert panel._entry.isVisibleTo(panel) and panel._entry._current == "H4899"
        # Picking another match shows it instead.
        other = panel._buttons[1]
        other.click()
        assert panel._entry._current == other.strongs and other.isChecked()
        assert not panel._buttons[0].isChecked()
        # A new lookup replaces the old matches.
        panel.look_up("Messiah")
        assert {b.strongs for b in panel._buttons} == {"H4899", "G3323"}  # Hebrew and Greek
        panel.look_up("qwertyuiop")
        assert not panel._buttons and "No Hebrew, Aramaic, or Greek word" in panel._status.text()
        panel.look_up("")
        assert panel._status.text() == INTRO
        # Reading the New Testament, Greek words are listed first.
        greek_panel = WordStudyPanel(panel._conn, "greek")
        greek_panel.look_up("love")
        assert greek_panel._buttons[0].strongs.startswith("G"), [b.strongs for b in greek_panel._buttons]
        print("test_look_up_shows_matches_and_the_best_entry: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_derivation_links_and_back() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-word-study-"))
    try:
        conn = _conn(tmp)
        view = LexiconEntryView(conn)
        view.show_entry("H4899")
        assert not view._back.isVisibleTo(view)
        assert 'href="H4886"' in view._body.text()
        view._follow("H4886")
        assert view._current == "H4886" and view._back.isVisibleTo(view)
        view.go_back()
        assert view._current == "H4899" and not view._back.isVisibleTo(view)
        # A fresh lookup starts a new history.
        view._follow("H4886")
        view.show_entry("H7676")
        assert not view._back.isVisibleTo(view)
        dialog = LexiconDialog(conn, "H6005")
        assert dialog.windowTitle() == "Hebrew word - Strong's H6005"
        # Greek: left to right, and its Hebrew-origin links work.
        view.show_entry("G2584")
        assert view._word.layoutDirection() == Qt.LayoutDirection.LeftToRight
        assert 'href="H3723"' in view._body.text() and 'href="H5151"' in view._body.text()
        view._follow("H5151")
        assert view._current == "H5151" and view._word.layoutDirection() == Qt.LayoutDirection.RightToLeft
        print("test_derivation_links_and_back: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_book_of_mormon_name_card() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-word-study-"))
    try:
        conn = _conn(tmp)
        # The data: each tier, group forms, and ordinary words aren't names.
        shazer = da.get_bom_name(conn, "shazer")
        assert shazer.tier == "hebrew_root" and shazer.strongs == ["H7806"] and len(shazer.proposals) == 3
        assert shazer.sources[0][1].startswith("https://onoma.lib.byu.edu/")
        assert da.get_bom_name(conn, "Irreantum").meaning == "many waters"
        assert da.get_bom_name(conn, "Deseret").tier == "defined"  # lowercase in Ether 2:3
        assert da.get_bom_name(conn, "Nephites").name == "Nephi"
        assert da.get_bom_name(conn, "Lehi").tier == "biblical"
        assert da.get_bom_name(conn, "Zarahemla").tier == "proposed"
        assert da.get_bom_name(conn, "faith") is None

        panel = WordStudyPanel(conn)
        panel.look_up("Shazer")
        card = panel._name_card
        assert card is not None and not panel._buttons  # no letter-alike lexicon matches
        text = " ".join(label.text() for label in card.findChildren(QLabel))
        assert "Hebrew root" in text and "Mormon 9:32-34" in text and 'href="H7806"' in text
        panel._show_strongs("H7806")
        assert panel._entry._current == "H7806" and panel._entry.isVisibleTo(panel)
        # Defined in the text itself: no "proposed" reminder.
        panel.look_up("Liahona")
        text = " ".join(label.text() for label in panel._name_card.findChildren(QLabel))
        assert "Defined in the Book of Mormon" in text and "Mormon 9:32-34" not in text
        # A Jaredite name gets the Ether note instead of Mormon 9's.
        panel.look_up("Coriantumr")
        text = " ".join(label.text() for label in panel._name_card.findChildren(QLabel))
        assert "Jaredite name" in text and "Ether 1:33-35" in text and "Mormon 9:32-34" not in text
        # Every name has been researched, and links its Onomasticon page.
        assert not conn.execute("SELECT 1 FROM bom_names WHERE tier = ''").fetchone()
        assert not conn.execute("SELECT 1 FROM bom_names WHERE sources NOT LIKE '%onoma.lib.byu.edu%'").fetchone()
        # A biblical name keeps its lexicon matches; an ordinary word gets no card.
        panel.look_up("Lehi")
        assert panel._name_card is not None and panel._buttons[0].strongs == "H3895"
        panel.look_up("anointed")
        assert panel._name_card is None and panel._buttons
        print("test_book_of_mormon_name_card: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_right_click_lookup_opens_the_tab() -> None:
    from scriptures.ui.reading_view import ReadingView

    tmp = Path(tempfile.mkdtemp(prefix="scriptures-word-study-"))
    try:
        conn = _conn(tmp)
        chapter_id = conn.execute(
            "SELECT c.id FROM chapters c JOIN books b ON b.id = c.book_id "
            "WHERE b.name = 'Psalms' AND c.chapter_number = 2 AND b.volume_id = 1"
        ).fetchone()[0]
        view = ReadingView(conn, chapter_id, "Psalms 2", da.get_verses(conn, chapter_id),
                           theme.get_reading_palette("day"), "Serif", 14)
        assert view._side_tabs.currentIndex() == 0
        assert view._side_tabs.tabText(3) == "Word Study"
        view._on_word_lookup_requested("anointed")
        assert view._side_tabs.currentWidget() is view._word_study_panel
        assert view._word_study_panel._entry._current == "H4899"
        print("test_right_click_lookup_opens_the_tab: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_look_up_shows_matches_and_the_best_entry()
    test_derivation_links_and_back()
    test_book_of_mormon_name_card()
    test_right_click_lookup_opens_the_tab()
    print("All Word Study tests passed.")
