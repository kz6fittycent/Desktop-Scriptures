"""Standalone test script for scripts/import_lexicon.py (Hebrew and Greek), the
lexicon_entries table, data_access's get_lexicon_entry/search_lexicon,
db.py's syncing of the lexicon, and its study index pieces. No test
framework (see tests/test_ask.py's own docstring for why). No network:
sources are small inline samples in the real formats.

Run directly:

    python3 tests/test_lexicon.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import import_lexicon as ihl  # noqa: E402
from scriptures import study_index as si  # noqa: E402
from scriptures.data_access import get_lexicon_entry, search_lexicon  # noqa: E402
from scriptures.db import connect, sync_bundled_content  # noqa: E402

STRONGS_SAMPLE = "/* header */\nvar strongsHebrewDictionary = " + json.dumps({
    "H4899": {"lemma": "מָשִׁיחַ", "xlit": "mâshîyach", "pron": "maw-shee'-akh",
              "derivation": "from H4886 (מָשַׁח);",
              "strongs_def": "anointed; usually a consecrated person; specifically, the Messiah",
              "kjv_def": "anointed, Messiah."},
    "H4886": {"lemma": "מָשַׁח", "xlit": "mâshach", "pron": "maw-shakh'", "derivation": "a primitive root;",
              "strongs_def": "to rub with oil, i.e. to anoint", "kjv_def": "anoint, paint."},
    "H4887": {"lemma": "מְשַׁח", "xlit": "mᵉshach", "pron": "mesh-akh'",
              "derivation": "(Aramaic) from a root corresponding to H4886;",
              "strongs_def": "oil", "kjv_def": "oil."},
    "H3068": {"lemma": "יְהֹוָה", "xlit": "Yᵉhôvâh", "pron": "yeh-ho-vaw'", "derivation": "from H1961;",
              "strongs_def": "(the) self-Existent or Eternal; Jehovah, Jewish national name of God",
              "kjv_def": "Jehovah, the Lord."},
    "H3071": {"lemma": "יְהֹוָה נִסִּי", "xlit": "Yᵉhôvâh niççîy", "pron": "", "derivation": "from H3068 and H5251;",
              "strongs_def": "Jehovah (is) my banner", "kjv_def": "Jehovah-nissi."},
}, ensure_ascii=False) + ";"

TBESH_SAMPLE = "\n".join([
    "TBESH header line",
    "H4899\tH4899 =\tH4899\tמָשִׁיחַ\tma.shi.ach\tH:N-M\tanointed\t1) anointed",
    "H4886\tH4886 =\tH4886\tמָשַׁח\tma.shach\tH:V\tto anoint\t1) to smear",
    "H4887\tH4887 =\tH4887\tמְשַׁח\tme.shach\tA:N-M\toil\t1) oil",
    "H3068G\tH3068G =\tH3068G\tיְהֹוָה\tye.ho.vah\tN:N--T\tLORD\tJehovah",
    "H3071a\tH3071a =\tH3071\tיְהֹוָה נִסִּי\tx\tN:N--L\tYHWH/Jehovah-nissi\tx",
    "H3071b\tH3071b =\tH3071\tיְהֹוָה נִסִּי\tx\tN:N--L\tthe LORD is my banner\tx",
    "H9001\tH9001 =\tH9001\tו\tve\tHC\tand\tprefix - never in Strong's",
])


GREEK_STRONGS_SAMPLE = "var strongsGreekDictionary = " + json.dumps({
    "G5547": {"translit": "Christós", "lemma": "Χριστός", "kjv_def": "Christ",
              "strongs_def": " anointed, i.e. the Messiah, an epithet of Jesus", "derivation": "from G5548 (χρίω);"},
    "G2584": {"translit": "Kapernaoúm", "lemma": "Καπερναούμ", "kjv_def": "Capernaum",
              "strongs_def": " Capernaum (i.e. Caphanachum), a place in Palestine",
              "derivation": "of Hebrew origin (probably H03723 and H05151);"},
    "G5548": {"translit": "chríō", "lemma": "χρίω", "kjv_def": "anoint",
              "strongs_def": " to smear or rub with oil", "derivation": "probably akin to G5530;"},
}, ensure_ascii=False) + ";"

TBESG_SAMPLE = "\n".join([
    "TBESG header",
    "G5547\tG5547 = a Name of\tG2424G\tΧριστός\tChristos\tN:N--T\tChrist\tx",
    "G2584\tG2584 =\tG2584\tΚαπερναούμ\tKapernaoum\tN:N--L\tCapernaum\tx",
    "G5548\tG5548 =\tG5548\tχρίω\tchriō\tG:V\tto anoint\tx",
    "G6000\tG6000 =\tG6000\tx\tx\tG:V\tbeyond Strong's\tx",
])

HEBREW = ihl.LANGUAGES["hebrew"]
GREEK = ihl.LANGUAGES["greek"]


def _rows() -> list[tuple]:
    return ihl.build_rows(ihl.parse_strongs(STRONGS_SAMPLE), ihl.parse_glosses(TBESH_SAMPLE, HEBREW), HEBREW)


def _greek_rows() -> list[tuple]:
    return ihl.build_rows(
        ihl.parse_strongs(GREEK_STRONGS_SAMPLE), ihl.parse_glosses(TBESG_SAMPLE, GREEK), GREEK
    )


def test_parsing_and_rows() -> None:
    glosses = ihl.parse_glosses(TBESH_SAMPLE, HEBREW)
    assert glosses["H3068"] == ["LORD"]
    # Lowercase disambiguation letters ("H3071a") are read, and several
    # rows for one number combine.
    assert glosses["H3071"] == ["YHWH/Jehovah-nissi", "the LORD is my banner"]
    assert "H9001" not in glosses  # prefixes past Strong's own numbering
    rows = {r[0]: r for r in _rows()}
    assert rows["H4899"][1] == "hebrew" and rows["H4899"][8] == "anointed"
    assert rows["H4887"][1] == "aramaic"
    assert rows["H4899"][7] == "anointed, Messiah."
    assert list(rows) == ["H3068", "H3071", "H4886", "H4887", "H4899"]  # numeric order
    greek = {r[0]: r for r in _greek_rows()}
    assert greek["G5547"][1] == "greek" and greek["G5547"][8] == "Christ"
    assert greek["G5547"][4] == ""  # Strong's Greek has no pronunciations
    # Zero-padded Hebrew cross-references are normalized so they link.
    assert greek["G2584"][5] == "of Hebrew origin (probably H3723 and H5151);"
    assert "G6000" not in greek and ihl.parse_glosses(TBESG_SAMPLE, GREEK).get("G6000") is None
    print("test_parsing_and_rows: PASSED")


def test_verify_catches_a_source_that_changed_shape() -> None:
    problems = ihl.verify(_rows(), HEBREW)
    assert any("only 5 hebrew entries" in p for p in problems), problems
    assert any("H7676" in p for p in problems), problems  # a spot check missing
    print("test_verify_catches_a_source_that_changed_shape: PASSED")


def _db(path: Path):
    conn = connect(path)
    ihl.write(conn, _rows(), HEBREW)
    ihl.write(conn, _greek_rows(), GREEK)
    return conn


def test_lookup_and_search_ranking() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-lexicon-test-"))
    try:
        conn = _db(tmp / "s.db")
        entry = get_lexicon_entry(conn, "h4899")
        assert entry and entry.transliteration == "mâshîyach" and entry.gloss == "anointed"
        assert [e.strongs for e in search_lexicon(conn, "Messiah")] == ["H4899"]
        assert [e.strongs for e in search_lexicon(conn, "H4886")] == ["H4886"]
        # The word itself ranks before compounds containing it.
        assert [e.strongs for e in search_lexicon(conn, "Jehovah")][:2] == ["H3068", "H3071"]
        # Whole words only: "anoint" doesn't match mashiach's "anointed".
        assert "H4899" not in [e.strongs for e in search_lexicon(conn, "anoint")]
        assert search_lexicon(conn, "how do I cope with grief today") == []  # not a word lookup
        # Greek, and the reading context's language first.
        assert [e.strongs for e in search_lexicon(conn, "Christ")] == ["G5547"]
        assert [e.strongs for e in search_lexicon(conn, "anoint")][:2] == ["H4886", "G5548"]
        assert [e.strongs for e in search_lexicon(conn, "anoint", preferred_language="greek")][:2] == ["G5548", "H4886"]
        # An inflected KJV word finds its root's entries: Greek chrio's
        # renderings say only "anoint".
        assert "G5548" in [e.strongs for e in search_lexicon(conn, "anointed")]
        print("test_lookup_and_search_ranking: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sync_mirrors_the_bundled_lexicon_and_index_pieces() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scriptures-lexicon-sync-"))
    try:
        _db(tmp / "bundled.db").close()
        local = connect(tmp / "local.db")
        local.execute(
            "INSERT INTO lexicon_entries (strongs, language, lemma, definition) "
            "VALUES ('H1', 'hebrew', 'x', 'stale')"
        )
        local.commit()
        sync_bundled_content(local, tmp / "bundled.db")
        assert get_lexicon_entry(local, "H1") is None
        assert get_lexicon_entry(local, "H4899").gloss == "anointed"

        pieces = [p for p in si.collect_pieces(local) if p.kind == "lexicon"]
        mashiach = next(p for p in pieces if p.meta["strongs"] == "H4899")
        assert "Strong's H4899" in mashiach.heading and "Messiah" in mashiach.body
        aramaic = next(p for p in pieces if p.meta["strongs"] == "H4887")
        assert aramaic.heading.startswith("Aramaic word")
        print("test_sync_mirrors_the_bundled_lexicon_and_index_pieces: PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_shipped_lexicon_is_complete() -> None:
    import sqlite3

    conn = sqlite3.connect(f"file:{PROJECT_ROOT / 'data' / 'scriptures.db'}?mode=ro", uri=True)
    counts = dict(conn.execute(
        "SELECT CASE language WHEN 'aramaic' THEN 'hebrew' ELSE language END, COUNT(*) "
        "FROM lexicon_entries GROUP BY 1"
    ).fetchall())
    for name, language in ihl.LANGUAGES.items():
        assert counts.get(name, 0) >= language.expected_minimum, counts
    assert conn.execute("SELECT COUNT(*) FROM lexicon_entries WHERE gloss = ''").fetchone()[0] == 0
    print("test_shipped_lexicon_is_complete: PASSED")


if __name__ == "__main__":
    test_parsing_and_rows()
    test_verify_catches_a_source_that_changed_shape()
    test_lookup_and_search_ranking()
    test_sync_mirrors_the_bundled_lexicon_and_index_pieces()
    test_shipped_lexicon_is_complete()
    print("All Hebrew lexicon tests passed.")
