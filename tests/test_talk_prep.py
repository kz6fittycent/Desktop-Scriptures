"""Standalone test script for src/scriptures/talk_prep.py (Talk Prep) and
the talk-prep parts of study_ask.py and sync.py. No test framework, no Qt
event loop (see tests/test_ask.py's docstring) - the parts that talk to
an AI service were tested live against gemma3-4b; these cover the logic
around them.

Run directly:

    python3 tests/test_talk_prep.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures import study_ask, talk_prep  # noqa: E402
from scriptures import study_index as si  # noqa: E402
from scriptures.data_access import get_journal_entry, set_setting  # noqa: E402
from scriptures.db import connect  # noqa: E402
from scriptures.study_ask import StudyResult  # noqa: E402
from scriptures.sync import TALK_PREP_SYNC_SETTING, export_device_state, import_and_merge  # noqa: E402


def _make_db(tmp_root: Path, name: str = "test") -> sqlite3.Connection:
    """A tiny slice of scripture: Alma 32-34 (Book of Mormon), Hebrews 11
    (Bible), and Lectures on Faith 1."""
    conn = connect(tmp_root / f"{name}.db")
    conn.executescript(
        """
        INSERT INTO volumes (id, name, slug, sort_order) VALUES
            (1, 'Book of Mormon', 'book-of-mormon', 2), (2, 'Holy Bible', 'holy-bible', 1),
            (3, 'Lectures on Faith', 'lectures-on-faith', 9);
        INSERT INTO books (id, volume_id, name, sort_order) VALUES
            (1, 1, 'Alma', 1), (2, 2, 'Hebrews', 1), (3, 3, 'Lectures on Faith', 1);
        INSERT INTO chapters (id, book_id, chapter_number) VALUES
            (32, 1, 32), (33, 1, 33), (34, 1, 34), (11, 2, 11), (1, 3, 1);
        """
    )
    texts = {
        (32, 21): "faith is not to have a perfect knowledge of things",
        (32, 22): "And now I would that ye should remember that God is merciful",
        (32, 23): "angels do impart his word unto men",
        (34, 31): "if ye will repent ye shall have redemption",
        (11, 1): "Now faith is the substance of things hoped for",
        (1, 1): "Faith being the first principle in revealed religion",
    }
    names = {32: "Alma 32", 33: "Alma 33", 34: "Alma 34", 11: "Hebrews 11", 1: "Lectures on Faith 1"}
    for (chapter, verse), text in texts.items():
        conn.execute(
            "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (?, ?, ?, ?)",
            (chapter, verse, text, f"{names[chapter]}:{verse}"),
        )
    conn.commit()
    return conn


def _hit(kind: str, reference: str = "", chapter_id: int | None = None, start: int = 1, end: int = 1,
         volume: str | None = "book-of-mormon", **meta) -> si.SearchHit:
    if kind == "scripture":
        meta.update(reference=reference, verse_start=start, verse_end=end)
    return si.SearchHit(0, f"{kind}:{reference}:{start}", kind, f"{reference}\ntext", volume, chapter_id,
                        meta, 1.0, 1, 1)


def test_interview_limits_and_context() -> None:
    interview = talk_prep.Interview(topic="repentance", length=10)
    assert interview.result_limit == 8
    assert talk_prep.Interview(topic="x", length=5).result_limit == 5
    assert talk_prep.Interview(topic="x", length=20).result_limit == 15
    assert talk_prep.Interview(topic="x").result_limit == talk_prep.DEFAULT_RESULTS
    assert "10-minute sacrament meeting talk" in interview.context()
    # The meeting never reaches retrieval - "sacrament meeting" would
    # match passages about the sacrament.
    assert interview.questions() == ["repentance"]

    lesson = talk_prep.Interview(
        topic="faith", meeting=talk_prep.LESSON_MEETING, length=5, lesson_source="manual", lesson_text="Lesson 12"
    )
    assert lesson.result_limit == talk_prep.DEFAULT_RESULTS  # a lesson has no talk length
    assert lesson.questions()[0] == "faith Lesson 12"
    assert "manual lesson" in lesson.context()
    print("test_interview_limits_and_context: PASSED")


def test_interview_sources() -> None:
    everything = talk_prep.Interview()
    assert everything.volumes() is None and everything.skip_groups() == frozenset()
    bom_only = talk_prep.Interview(sources=["book-of-mormon", "talks"])
    assert bom_only.volumes() == {"book-of-mormon"}
    assert {"articles", "other", "lexicon"} <= bom_only.skip_groups()
    assert "talks" not in bom_only.skip_groups()
    talks_only = talk_prep.Interview(sources=["talks"])
    assert {"standard_works", "cross_references"} <= talks_only.skip_groups()
    print("test_interview_sources: PASSED")


def test_parse_reading_block() -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="scriptures-talk-prep-test-"))
    try:
        conn = _make_db(tmp_root)
        assert talk_prep.parse_reading_block(conn, "Alma 32-34") == [32, 33, 34]
        # A book carries over to later parts; nonsense is skipped.
        assert talk_prep.parse_reading_block(conn, "Alma 32; 34, Nowhere 3") == [32, 34]
        assert talk_prep.parse_reading_block(conn, "Hebrews 11") == [11]
        print("test_parse_reading_block: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_themes_are_distinct_directions() -> None:
    hits = [
        _hit("talk", title="Repentance"),
        _hit("talk", title="Repentance: A Joyful Choice"),
        _hit("article", title="Repentance—a Joyful Choice"),
        _hit("talk", title="A Broken Heart and a Contrite Spirit"),
        _hit("topic", reference="Topical Guide: Forgiveness"),
    ]
    hits[-1] = si.SearchHit(0, "t", "topic", "Topical Guide: Forgiveness\n...", None, None, {}, 1.0, 1, 1)
    themes = talk_prep.themes_from_hits(hits, "repentance")
    assert themes == ["Repentance: A Joyful Choice", "A Broken Heart and a Contrite Spirit", "Forgiveness"], themes
    print("test_themes_are_distinct_directions: PASSED")


def test_balance_for_talk_prep() -> None:
    a = _hit("scripture", "Alma 32:17-23", 32, 17, 23)
    a_inner = _hit("scripture", "Alma 32:21", 32, 21, 21)
    loose = _hit("scripture", "Hebrews 11:1", 11, 1, 1, volume="holy-bible")  # a search result, unpicked
    key = _hit("scripture", "Alma 34:31", 34, 31, 31, key_topic="Repentance")  # a Topical Guide key passage
    reading = _hit("scripture", "Alma 33:3", 33, 3, 3)
    talk = _hit("talk", url="u1")
    talk.meta.update(title="Faith", speaker="A")
    reprint = _hit("article", url="u2")
    reprint.meta.update(title="Faith", speaker="A")
    jod = _hit("discourse", "JoD", volume=None)
    chosen = [a, a_inner, jod, reprint, talk]
    result = study_ask.balance_for_talk_prep(chosen, [loose, key, reading], 5, "faith", favored=[reading])
    assert a_inner not in result  # overlaps Alma 32:17-23
    assert reading in result and result.index(reading) == 0  # the lesson's reading leads
    assert key in result  # topped up from a trusted passage...
    assert loose not in result  # ...never from a search result the model passed over
    assert reprint not in result  # the Ensign reprint of a talk already listed
    assert talk in result
    if jod in result:  # trimmed "Also" items go before the talk
        assert result.index(talk) < result.index(jod)
    assert len(result) <= 5
    print("test_balance_for_talk_prep: PASSED")


def test_lexicon_kept_only_when_on_topic() -> None:
    on_topic = StudyResult(kind="lexicon", title="Greek word metanoia", detail="repentance - a change of mind")
    off_topic = StudyResult(kind="lexicon", title="Hebrew word shathah", detail="to drink - drunk, banquet")
    verse = StudyResult(kind="scripture", title="Alma 34:31")
    kept = talk_prep.drop_unrelated_words([on_topic, off_topic, verse], "repentance")
    assert kept == [on_topic, verse]
    print("test_lexicon_kept_only_when_on_topic: PASSED")


def test_reprints_become_conference_talks() -> None:
    picker = talk_prep.find_works("joyful choice")
    assert [w.source_label for w in picker] == ["General Conference"], picker  # the reprint isn't listed
    reprint = next(
        w for w in talk_prep.all_works()
        if w.talk_title == "Repentance: A Joyful Choice" and w.source_label != "General Conference"
    )
    article = StudyResult(kind="article", title="Ensign: ...", url=reprint.url)
    [result] = talk_prep.prefer_conference_talks([article])
    assert result.kind == "talk" and "general-conference" in result.url
    print("test_reprints_become_conference_talks: PASSED")


def test_sessions_journal_and_text() -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="scriptures-talk-prep-test-"))
    try:
        conn = _make_db(tmp_root)
        session = talk_prep.new_session(talk_prep.Interview(topic="faith", length=10))
        session.results = [
            StudyResult(kind="scripture", title="Alma 32:21-23", chapter_id=32, verse_start=21, verse_end=23,
                        key_verse=21),
            StudyResult(kind="scripture", title="Lectures on Faith 1:1", chapter_id=1, verse_start=1, verse_end=1,
                        key_verse=1),
            StudyResult(kind="talk", title='General Conference: "Faith"', url="https://example.org/faith"),
        ]
        talk_prep.save_session(conn, session)
        [loaded] = talk_prep.list_sessions(conn)
        assert loaded.title == "faith" and loaded.results[0].key_verse == 21

        text = talk_prep.as_text(conn, loaded)
        assert 'Alma 32:21: "faith is not to have a perfect knowledge of things"' in text
        # Lectures on Faith isn't part of the Standard Works: "Also", and no key verse.
        assert text.index("Lectures on Faith 1:1") > text.index("Also")
        assert "Lectures on Faith 1:1:" not in text

        talk_prep.append_to_journal(conn, "My own thoughts.", date(2026, 10, 12))
        talk_prep.append_to_journal(conn, text, date(2026, 10, 12))
        entry = get_journal_entry(conn, "2026-10-12")
        assert entry.text.startswith("My own thoughts.\n\nTalk Prep: faith")

        talk_prep.delete_session(conn, session.uid)
        assert talk_prep.list_sessions(conn) == []
        print("test_sessions_journal_and_text: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_sessions_sync_only_when_enabled() -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="scriptures-talk-prep-test-"))
    try:
        folder = tmp_root / "sync"
        folder.mkdir()
        laptop, desktop = _make_db(tmp_root, "laptop"), _make_db(tmp_root, "desktop")
        talk_prep.save_session(laptop, talk_prep.new_session(talk_prep.Interview(topic="faith")))

        export_device_state(laptop, folder)  # syncing off on the laptop: not written
        import_and_merge(desktop, folder)
        assert talk_prep.list_sessions(desktop) == []

        set_setting(laptop, TALK_PREP_SYNC_SETTING, "true")
        export_device_state(laptop, folder)
        import_and_merge(desktop, folder)  # off on the desktop: not taken
        assert talk_prep.list_sessions(desktop) == []

        set_setting(desktop, TALK_PREP_SYNC_SETTING, "true")
        import_and_merge(desktop, folder)
        assert [s.title for s in talk_prep.list_sessions(desktop)] == ["faith"]
        print("test_sessions_sync_only_when_enabled: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    test_interview_limits_and_context()
    test_interview_sources()
    test_parse_reading_block()
    test_themes_are_distinct_directions()
    test_balance_for_talk_prep()
    test_lexicon_kept_only_when_on_topic()
    test_reprints_become_conference_talks()
    test_sessions_journal_and_text()
    test_sessions_sync_only_when_enabled()
    print("All talk prep tests passed.")
