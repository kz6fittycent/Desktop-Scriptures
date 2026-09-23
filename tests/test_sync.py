"""Standalone test script for src/scriptures/sync.py.

No test framework required - run directly:

    python3 tests/test_sync.py

Simulates two separate installations ("devices"), each with its own
temp-file database, making different offline edits and then syncing
through a shared temp folder that stands in for the cloud-synced folder a
real Nextcloud/OneDrive/Google Drive client would keep in sync. Confirms
the merge combines both devices' edits, and that a deletion made on one
device removes the corresponding thing on the other after syncing.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scriptures import data_access as da  # noqa: E402
from scriptures.db import connect  # noqa: E402
from scriptures.sync import export_device_state, import_and_merge  # noqa: E402


def _seed_minimal_scriptures(conn: sqlite3.Connection) -> dict[str, int]:
    """The same tiny slice of scripture content on every "device" DB in
    this test, standing in for the real bundled data every actual
    installation ships with. Returns the verse ids by verse_number for
    convenience."""
    conn.execute(
        "INSERT INTO volumes (id, name, slug, sort_order) VALUES (1, 'Holy Bible', 'holy-bible', 1)"
    )
    conn.execute(
        "INSERT INTO books (id, volume_id, name, sort_order) VALUES (1, 1, 'Genesis', 1)"
    )
    conn.execute(
        "INSERT INTO chapters (id, book_id, chapter_number) VALUES (1, 1, 1)"
    )
    verses = {
        1: "In the beginning God created the heaven and the earth.",
        2: "And the earth was without form, and void.",
        3: "And God said, Let there be light: and there was light.",
    }
    verse_ids = {}
    for num, text in verses.items():
        cur = conn.execute(
            "INSERT INTO verses (chapter_id, verse_number, text, reference) VALUES (1, ?, ?, ?)",
            (num, text, f"Genesis 1:{num}"),
        )
        verse_ids[num] = cur.lastrowid
    conn.commit()
    return verse_ids


def _set_updated_at(conn: sqlite3.Connection, table: str, row_id: int, timestamp: str) -> None:
    """Overrides a row's real datetime('now') timestamp with a controlled
    one, so ordering between devices in this test is deterministic instead
    of racing against the wall clock's 1-second resolution."""
    conn.execute(f"UPDATE {table} SET updated_at = ? WHERE id = ?", (timestamp, row_id))
    conn.commit()


def _make_device(tmp_root: Path, name: str) -> tuple[sqlite3.Connection, dict[str, int]]:
    db_path = tmp_root / f"{name}.db"
    conn = connect(db_path)
    verse_ids = _seed_minimal_scriptures(conn)
    return conn, verse_ids


def test_two_device_sync_merges_and_propagates_deletion() -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="scriptures-sync-test-"))
    sync_folder = tmp_root / "sync"
    sync_folder.mkdir()

    try:
        conn_a, verses_a = _make_device(tmp_root, "device_a")
        conn_b, verses_b = _make_device(tmp_root, "device_b")

        # --- Offline edits, before either device has synced ---

        # Device A: a note on verse 1, a "Favorites" tag on verse 2.
        da.save_note(conn_a, "A's note on verse 1", verse_id=verses_a[1])
        note_a = da.get_note(conn_a, verse_id=verses_a[1])
        _set_updated_at(conn_a, "notes", note_a.id, "2026-01-01 00:00:00")

        da.add_tag(conn_a, "Favorites", verse_id=verses_a[2])
        tag_row_a = conn_a.execute(
            "SELECT id FROM tag_assignments WHERE verse_id = ?", (verses_a[2],)
        ).fetchone()
        _set_updated_at(conn_a, "tag_assignments", tag_row_a["id"], "2026-01-01 00:00:00")

        # Device B: a different note on verse 3, a different tag on the
        # SAME verse 2 (should coexist with A's "Favorites"), a highlight.
        da.save_note(conn_b, "B's note on verse 3", verse_id=verses_b[3])
        note_b = da.get_note(conn_b, verse_id=verses_b[3])
        _set_updated_at(conn_b, "notes", note_b.id, "2026-01-01 00:00:00")

        da.add_tag(conn_b, "ToStudy", verse_id=verses_b[2])
        tag_row_b = conn_b.execute(
            "SELECT id FROM tag_assignments WHERE verse_id = ?", (verses_b[2],)
        ).fetchone()
        _set_updated_at(conn_b, "tag_assignments", tag_row_b["id"], "2026-01-01 00:00:00")

        da.add_highlight(conn_b, verses_b[3], "pink", 0, 4)
        hl_row_b = conn_b.execute(
            "SELECT id FROM highlights WHERE verse_id = ?", (verses_b[3],)
        ).fetchone()
        _set_updated_at(conn_b, "highlights", hl_row_b["id"], "2026-01-01 00:00:00")

        # --- First sync: both devices export, then both merge ---

        export_device_state(conn_a, sync_folder)
        export_device_state(conn_b, sync_folder)
        assert len(list(sync_folder.glob("device-*.json"))) == 2

        import_and_merge(conn_a, sync_folder)
        import_and_merge(conn_b, sync_folder)

        # Device A should now also see B's note, B's tag, B's highlight.
        assert da.get_note(conn_a, verse_id=verses_a[3]).text == "B's note on verse 3"
        tags_v2_a = {t.name for t in da.get_tags(conn_a, verse_id=verses_a[2])}
        assert tags_v2_a == {"Favorites", "ToStudy"}
        assert da.get_highlights(conn_a, chapter_id=1).get(verses_a[3])

        # Device B should symmetrically see A's note and A's tag.
        assert da.get_note(conn_b, verse_id=verses_b[1]).text == "A's note on verse 1"
        tags_v2_b = {t.name for t in da.get_tags(conn_b, verse_id=verses_b[2])}
        assert tags_v2_b == {"Favorites", "ToStudy"}

        # --- Second sync: A removes its "Favorites" tag; confirm the
        # deletion reaches B ---

        da.remove_tag(conn_a, da.get_tags(conn_a, verse_id=verses_a[2])[0].id, verse_id=verses_a[2])
        removed_row = conn_a.execute(
            "SELECT id FROM tag_assignments WHERE verse_id = ? AND deleted_at IS NOT NULL",
            (verses_a[2],),
        ).fetchone()
        _set_updated_at(conn_a, "tag_assignments", removed_row["id"], "2026-01-02 00:00:00")

        export_device_state(conn_a, sync_folder)
        import_and_merge(conn_b, sync_folder)

        tags_v2_b_after = {t.name for t in da.get_tags(conn_b, verse_id=verses_b[2])}
        assert tags_v2_b_after == {"ToStudy"}, (
            f"expected A's tag removal to propagate to B, got {tags_v2_b_after}"
        )

        # A's own database still reflects the removal too, of course.
        tags_v2_a_after = {t.name for t in da.get_tags(conn_a, verse_id=verses_a[2])}
        assert tags_v2_a_after == {"ToStudy"}

        print("test_two_device_sync_merges_and_propagates_deletion: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_journal_entry_sync_merges_edits_and_deletion() -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="scriptures-sync-test-"))
    sync_folder = tmp_root / "sync"
    sync_folder.mkdir()

    try:
        conn_a, verses_a = _make_device(tmp_root, "device_a")
        conn_b, verses_b = _make_device(tmp_root, "device_b")

        # Device A writes today's entry, with an optional reference to
        # verse 1 - device B has its own, independent verse_id for that
        # same verse, so this also confirms the reference resolves by
        # natural key rather than by raw id.
        da.save_journal_entry(
            conn_a, "2026-09-20", "A's entry", verse_id=verses_a[1]
        )
        entry_a = da.get_journal_entry(conn_a, "2026-09-20")
        _set_updated_at(conn_a, "journal_entries", entry_a.id, "2026-01-01 00:00:00")

        export_device_state(conn_a, sync_folder)
        import_and_merge(conn_b, sync_folder)

        entry_on_b = da.get_journal_entry(conn_b, "2026-09-20")
        assert entry_on_b is not None
        assert entry_on_b.text == "A's entry"
        assert entry_on_b.verse_id == verses_b[1], (
            "reference should resolve to B's own local verse_id for the same verse"
        )

        # Device B edits that same day's entry, later - should win on next sync.
        da.save_journal_entry(conn_b, "2026-09-20", "B's edit")
        edited_on_b = da.get_journal_entry(conn_b, "2026-09-20")
        _set_updated_at(conn_b, "journal_entries", edited_on_b.id, "2026-01-02 00:00:00")

        export_device_state(conn_b, sync_folder)
        import_and_merge(conn_a, sync_folder)
        assert da.get_journal_entry(conn_a, "2026-09-20").text == "B's edit"

        # Device B deletes it - should propagate to A too.
        da.delete_journal_entry(conn_b, "2026-09-20")
        deleted_row = conn_b.execute(
            "SELECT id FROM journal_entries WHERE entry_date = ? AND deleted_at IS NOT NULL",
            ("2026-09-20",),
        ).fetchone()
        _set_updated_at(conn_b, "journal_entries", deleted_row["id"], "2026-01-03 00:00:00")

        export_device_state(conn_b, sync_folder)
        import_and_merge(conn_a, sync_folder)
        assert da.get_journal_entry(conn_a, "2026-09-20") is None

        print("test_journal_entry_sync_merges_edits_and_deletion: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_export_file_contents() -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="scriptures-sync-test-"))
    sync_folder = tmp_root / "sync"
    sync_folder.mkdir()

    try:
        conn, verses = _make_device(tmp_root, "solo")
        da.save_note(conn, "hello", verse_id=verses[1])
        da.add_tag(conn, "Tag1", verse_id=verses[1])
        da.add_highlight(conn, verses[1], "yellow", 0, 3)
        da.record_reading(conn, 1, "2026-01-01")

        path = export_device_state(conn, sync_folder)
        assert path.exists()
        assert path.name == f"device-{da.get_device_id(conn)}.json"

        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["device_id"] == da.get_device_id(conn)
        assert len(payload["notes"]) == 1
        assert payload["notes"][0]["target"] == {
            "kind": "verse",
            "volume_slug": "holy-bible",
            "reference": "Genesis 1:1",
        }
        assert len(payload["tag_assignments"]) == 1
        assert payload["tag_assignments"][0]["tag_name"] == "Tag1"
        assert len(payload["highlights"]) == 1
        assert len(payload["reading_log"]) == 1
        assert payload["reading_log"][0]["read_date"] == "2026-01-01"

        print("test_export_file_contents: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_missing_sync_folder_raises() -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="scriptures-sync-test-"))
    try:
        conn, verses = _make_device(tmp_root, "solo")
        missing = tmp_root / "does-not-exist"
        try:
            export_device_state(conn, missing)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("expected FileNotFoundError for a missing sync folder")

        try:
            import_and_merge(conn, missing)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("expected FileNotFoundError for a missing sync folder")

        print("test_missing_sync_folder_raises: PASSED")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    test_export_file_contents()
    test_two_device_sync_merges_and_propagates_deletion()
    test_journal_entry_sync_merges_edits_and_deletion()
    test_missing_sync_folder_raises()
    print("All sync tests passed.")
