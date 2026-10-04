"""Standalone test script for the Apocrypha volume (scripts/import_apocrypha.py)
and everything the Standard Works get that it should get too: reading,
search, the study index and AI search, Word Study, cross-references. No
test framework (see tests/test_ask.py's docstring); offscreen Qt, a copy of
the shipped data/scriptures.db.

Run directly:

    python3 tests/test_apocrypha.py
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

from PySide6.QtWidgets import QApplication  # noqa: E402

from scriptures import data_access as da  # noqa: E402
from scriptures.db import connect  # noqa: E402

BOOKS = [
    "1 Esdras", "2 Esdras", "Tobit", "Judith", "Rest of Esther", "Wisdom of Solomon",
    "Ecclesiasticus", "Baruch", "Song of the Three Children", "Susanna", "Bel and the Dragon",
    "Prayer of Manasses", "1 Maccabees", "2 Maccabees",
]


def _conn(tmp: Path):
    shutil.copy(PROJECT_ROOT / "data" / "scriptures.db", tmp / "s.db")
    return connect(tmp / "s.db")


def _chapter(conn, book: str, number: int) -> int:
    return conn.execute(
        "SELECT c.id FROM chapters c JOIN books b ON b.id = c.book_id JOIN volumes v ON v.id = b.volume_id "
        "WHERE v.slug = 'apocrypha' AND b.name = ? AND c.chapter_number = ?", (book, number)
    ).fetchone()[0]


def test_the_volume_and_its_text() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-apocrypha-"))
    try:
        conn = _conn(tmp)
        volume = next(v for v in da.get_volumes(conn) if v.slug == "apocrypha")
        assert volume.name == "Apocrypha" and not da.get_testaments(conn, volume.id)
        assert [b.name for b in da.get_books(conn, volume.id)] == BOOKS
        count = conn.execute(
            "SELECT count(*) FROM verses v JOIN chapters c ON c.id = v.chapter_id JOIN books b ON b.id = c.book_id "
            "WHERE b.volume_id = ?", (volume.id,)
        ).fetchone()[0]
        assert count == 5722, count
        # No reference collides with a Bible book's.
        clash = conn.execute(
            "SELECT count(*) FROM verses a JOIN chapters ca ON ca.id = a.chapter_id JOIN books ba ON ba.id = ca.book_id "
            "JOIN verses b ON b.reference = a.reference AND b.id != a.id WHERE ba.volume_id = ?", (volume.id,)
        ).fetchone()[0]
        assert clash == 0
        text = da.get_verses(conn, _chapter(conn, "Ecclesiasticus", 28))[1].text
        assert text.startswith("Forgive thy neighbour") and "\\" not in text
        # Keyword search finds it.
        hits = da.search_verses(conn, "Maccabeus") if hasattr(da, "search_verses") else None
        fts = conn.execute("SELECT count(*) FROM verses_fts WHERE verses_fts MATCH 'Maccabeus'").fetchone()[0]
        assert fts > 0 and (hits is None or hits)
        print("test_the_volume_and_its_text: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_reading_view_headings_prologue_and_cross_references() -> None:
    from scriptures.ui.main_window import MainWindow

    tmp = Path(tempfile.mkdtemp(prefix="scriptures-apocrypha-"))
    try:
        conn = _conn(tmp)
        window = MainWindow(conn)
        volume = next(v for v in da.get_volumes(conn) if v.slug == "apocrypha")
        window._on_volume_clicked(volume.id)  # the volume page, with D&C 91's counsel
        # Ecclesiasticus' prologue is chapter 0, "Ecclesiasticus - Prologue".
        prologue = _chapter(conn, "Ecclesiasticus", 0)
        _vol, _testament, book, chapter = da.get_chapter_location(conn, prologue)
        assert MainWindow._chapter_label(volume, da.get_chapter(conn, prologue)) == "Prologue"
        window._on_chapter_clicked(volume, None, book, prologue)
        view = window._current_reading_view
        assert view._title == "Ecclesiasticus - Prologue"
        # Rest of Esther 13's headings show under its title.
        rest = _chapter(conn, "Rest of Esther", 13)
        _vol, _t, book, chapter = da.get_chapter_location(conn, rest)
        assert "after chap. 3.13 of the Hebrew" in MainWindow._chapter_subtitle(da.get_chapter(conn, rest), volume)
        # Word Study prefers Greek here.
        from scriptures.ui.reading_view import _original_language

        assert _original_language(conn, rest) == "greek"
        # 1 Maccabees 4 shows its cross-reference to John 10:22.
        dedication = _chapter(conn, "1 Maccabees", 4)
        _vol, _t, book, chapter = da.get_chapter_location(conn, dedication)
        window._on_chapter_clicked(volume, None, book, dedication)
        assert window._current_reading_view._cross_references_panel.reference_count >= 1
        print("test_reading_view_headings_prologue_and_cross_references: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ai_search_and_the_study_index() -> None:
    from scriptures import study_ask, study_index
    from scriptures.ask import parse_reference

    tmp = Path(tempfile.mkdtemp(prefix="scriptures-apocrypha-"))
    try:
        conn = _conn(tmp)
        # Its verses are indexed like any other scripture.
        pieces = [p for p in study_index._scripture_pieces(conn) if p.key.startswith("scripture:apocrypha")]
        assert len(pieces) > 1000, len(pieces)
        # AI search: its own candidate slots, the fourth (everything-else) tier,
        # a filter phrase, and the abbreviations a model might use.
        assert any(group[2] == {"apocrypha"} for group in study_ask.CANDIDATE_GROUPS)
        assert study_ask.detect_filters(["verses about wisdom", "just the Apocrypha"])[1] == {"apocrypha"}
        assert parse_reference("Sir 28:2")[0] == "Ecclesiasticus"
        assert parse_reference("1 Macc 4:59")[0] == "1 Maccabees"
        assert parse_reference("Ecclesiastes 3:1")[0] == "Ecclesiastes"
        print("test_ai_search_and_the_study_index: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_other_ancient_texts() -> None:
    """1 Enoch and Jasher (scripts/import_other_texts.py): their own volume,
    labeled not scripture, with the same reading and search features."""
    from scriptures import study_ask
    from scriptures.ask import parse_reference
    from scriptures.ui.main_window import MainWindow

    tmp = Path(tempfile.mkdtemp(prefix="scriptures-other-texts-"))
    try:
        conn = _conn(tmp)
        volume = next(v for v in da.get_volumes(conn) if v.slug == "other-ancient-texts")
        assert [b.name for b in da.get_books(conn, volume.id)] == ["1 Enoch", "Jasher"]
        counts = dict(conn.execute(
            "SELECT b.name, count(*) FROM verses v JOIN chapters c ON c.id = v.chapter_id "
            "JOIN books b ON b.id = c.book_id WHERE b.volume_id = ? GROUP BY b.name", (volume.id,)
        ).fetchall())
        assert counts == {"1 Enoch": 1062, "Jasher": 3910}, counts
        enoch_1_9 = conn.execute("SELECT text FROM verses WHERE reference = '1 Enoch 1:9'").fetchone()[0]
        assert enoch_1_9.startswith("And behold! He cometh with ten thousands of His holy ones")
        assert not conn.execute(
            "SELECT 1 FROM verses v JOIN chapters c ON c.id = v.chapter_id JOIN books b ON b.id = c.book_id "
            "WHERE b.volume_id = ? AND (v.text GLOB '*[〚⌜†{}|]*' OR v.text = '')", (volume.id,)
        ).fetchone()
        # The volume page says they aren't scripture; Charles' headings show.
        window = MainWindow(conn)
        window._on_volume_clicked(volume.id)
        assert "not scripture" in window._other_texts_banner().text()
        chapter = da.get_chapter(conn, conn.execute(
            "SELECT c.id FROM chapters c JOIN books b ON b.id = c.book_id WHERE b.name = '1 Enoch' "
            "AND c.chapter_number = 72").fetchone()[0])
        assert MainWindow._chapter_subtitle(chapter, volume) == "The Sun"
        # Search, AI search, and the Jude quotation.
        assert conn.execute("SELECT count(*) FROM verses_fts WHERE verses_fts MATCH 'Methuselah'").fetchone()[0] > 0
        assert any(group[2] == {"other-ancient-texts"} for group in study_ask.CANDIDATE_GROUPS)
        assert study_ask.detect_filters(["the flood", "just the Book of Enoch"])[1] == {"other-ancient-texts"}
        assert parse_reference("Book of Jasher 88:64")[0] == "Jasher"
        assert conn.execute(
            "SELECT relationship FROM cross_references WHERE book_name = 'Jude' AND related_book_name = '1 Enoch'"
        ).fetchone()[0] == "quotation"
        print("test_other_ancient_texts: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    test_the_volume_and_its_text()
    test_reading_view_headings_prologue_and_cross_references()
    test_ai_search_and_the_study_index()
    test_other_ancient_texts()
    print("All Apocrypha tests passed.")
