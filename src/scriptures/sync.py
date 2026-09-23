"""Cloud-folder sync engine.

This app never talks to any cloud provider's API. Instead, the user points
it at a local folder that some already-running cloud client (Nextcloud,
OneDrive, Google Drive, etc.) keeps synced, and this module just reads and
writes small JSON files there - one per device, never touched by any other
device. That keeps the app completely agnostic to which cloud service (if
any) is in use.

Two independent operations:

- `export_device_state` writes this device's entire current state (every
  note/journal entry/tag assignment/highlight/reading-log row it has,
  including soft-deleted ones - see schema.sql's `deleted_at` columns) to
  <folder>/device-<this device's id>.json.
- `import_and_merge` reads every device-*.json file present in the folder
  (including this device's own last export), merges them by natural key
  (a verse/chapter's reference, not a raw integer id - device B's row 7
  means nothing to device A), and applies the merged result to the local
  database.

Records are matched across devices by natural key rather than by id
because two devices' databases are entirely separate SQLite files with
independent, unrelated autoincrement ids - the same pattern `db.py`'s
`sync_bundled_content` already uses for syncing in developer-authored
scripture content. A verse's `reference` string alone isn't quite enough,
since the Joseph Smith Translation reuses the King James Bible's own
book/chapter/verse numbering (see schema.sql's comment on `topic_verses`),
so every target here also carries the volume's slug.

Conflicts resolve by last-write-wins on `updated_at`: whichever device's
copy of a given record was updated more recently wins, including a
tombstoned (`deleted_at` set) record beating a non-deleted one if its
timestamp is newer - that's precisely what lets a deletion on one device
reach another. `updated_at` is always produced by SQLite's `datetime('now')`
(UTC, "YYYY-MM-DD HH:MM:SS"), which sorts correctly as a plain string, so
timestamps never need parsing.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from scriptures.data_access import get_device_id

DEVICE_FILE_GLOB = "device-*.json"


def _device_file_path(sync_folder: Path, device_id: str) -> Path:
    return sync_folder / f"device-{device_id}.json"


# ---------------------------------------------------------------------
# Natural-key targets: a verse or chapter, identified by volume slug plus
# either its reference string (verse) or book name + chapter number
# (chapter - chapters have no reference string of their own the way
# verses do).
# ---------------------------------------------------------------------


def _verse_target(conn: sqlite3.Connection, verse_id: int) -> dict[str, Any] | None:
    r = conn.execute(
        "SELECT v.reference, vol.slug AS volume_slug FROM verses v "
        "JOIN chapters c ON c.id = v.chapter_id "
        "JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id "
        "WHERE v.id = ?",
        (verse_id,),
    ).fetchone()
    if not r:
        return None
    return {"kind": "verse", "volume_slug": r["volume_slug"], "reference": r["reference"]}


def _chapter_target(conn: sqlite3.Connection, chapter_id: int) -> dict[str, Any] | None:
    r = conn.execute(
        "SELECT b.name AS book_name, c.chapter_number, vol.slug AS volume_slug "
        "FROM chapters c "
        "JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id "
        "WHERE c.id = ?",
        (chapter_id,),
    ).fetchone()
    if not r:
        return None
    return {
        "kind": "chapter",
        "volume_slug": r["volume_slug"],
        "book_name": r["book_name"],
        "chapter_number": r["chapter_number"],
    }


def _verse_or_chapter_target(
    conn: sqlite3.Connection, verse_id: int | None, chapter_id: int | None
) -> dict[str, Any] | None:
    if verse_id is not None:
        return _verse_target(conn, verse_id)
    return _chapter_target(conn, chapter_id)


def _resolve_target(conn: sqlite3.Connection, target: dict[str, Any]) -> tuple[int | None, int | None] | None:
    """The local (verse_id, chapter_id) a target resolves to on THIS
    device's database, or None if it doesn't resolve to anything here -
    e.g. a record from a book this device hasn't synced its scripture
    text in yet. Mirrors `topic_verses`' own resolution join, which is
    simply skipped by its caller when a row doesn't (yet) match - the
    same thing happens here."""
    if target["kind"] == "verse":
        r = conn.execute(
            "SELECT v.id FROM verses v "
            "JOIN chapters c ON c.id = v.chapter_id "
            "JOIN books b ON b.id = c.book_id "
            "JOIN volumes vol ON vol.id = b.volume_id AND vol.slug = ? "
            "WHERE v.reference = ?",
            (target["volume_slug"], target["reference"]),
        ).fetchone()
        return (r["id"], None) if r else None
    r = conn.execute(
        "SELECT c.id FROM chapters c "
        "JOIN books b ON b.id = c.book_id "
        "JOIN volumes vol ON vol.id = b.volume_id AND vol.slug = ? "
        "WHERE b.name = ? AND c.chapter_number = ?",
        (target["volume_slug"], target["book_name"], target["chapter_number"]),
    ).fetchone()
    return (None, r["id"]) if r else None


def _target_key(target: dict[str, Any]) -> tuple:
    """A hashable natural key for merging - see module docstring."""
    if target["kind"] == "verse":
        return ("verse", target["volume_slug"], target["reference"])
    return ("chapter", target["volume_slug"], target["book_name"], target["chapter_number"])


# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------


def _export_journal_entries(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM journal_entries"):
        # Unlike notes' own target below, a journal entry's reference is
        # optional - None here just means "no reference," not "skip this
        # record" (_verse_or_chapter_target(conn, None, None) itself
        # already returns None safely, since a NULL id matches no row).
        target = _verse_or_chapter_target(conn, r["verse_id"], r["chapter_id"])
        out.append(
            {
                "entry_date": r["entry_date"],
                "text": r["text"],
                "target": target,
                "updated_at": r["updated_at"],
                "deleted_at": r["deleted_at"],
            }
        )
    return out


def _export_notes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM notes"):
        target = _verse_or_chapter_target(conn, r["verse_id"], r["chapter_id"])
        if target is None:
            continue
        out.append(
            {
                "target": target,
                "text": r["text"],
                "updated_at": r["updated_at"],
                "deleted_at": r["deleted_at"],
            }
        )
    return out


def _export_tag_assignments(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    rows = conn.execute(
        "SELECT ta.*, t.name AS tag_name FROM tag_assignments ta JOIN tags t ON t.id = ta.tag_id"
    )
    for r in rows:
        target = _verse_or_chapter_target(conn, r["verse_id"], r["chapter_id"])
        if target is None:
            continue
        out.append(
            {
                "tag_name": r["tag_name"],
                "target": target,
                "updated_at": r["updated_at"],
                "deleted_at": r["deleted_at"],
            }
        )
    return out


def _export_highlights(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM highlights"):
        target = _verse_target(conn, r["verse_id"])
        if target is None:
            continue
        out.append(
            {
                "target": target,
                "start_offset": r["start_offset"],
                "end_offset": r["end_offset"],
                "color": r["color"],
                "updated_at": r["updated_at"],
                "deleted_at": r["deleted_at"],
            }
        )
    return out


def _export_reading_log(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM reading_log"):
        target = _chapter_target(conn, r["chapter_id"]) if r["chapter_id"] is not None else None
        out.append({"read_date": r["read_date"], "target": target, "updated_at": r["updated_at"]})
    return out


def export_device_state(conn: sqlite3.Connection, sync_folder: Path) -> Path:
    """Writes this device's entire current state to
    <sync_folder>/device-<device_id>.json, overwriting whatever this
    device wrote there last time. Every row is exported regardless of
    `deleted_at` - a soft-deleted row still needs to reach other devices
    as a tombstone, not just an active one. Raises FileNotFoundError if
    `sync_folder` doesn't exist (the caller - see Stage 3's UI - is
    expected to check for and handle that itself, e.g. by prompting the
    user to reconfigure).

    Written via a temp file + rename in the same folder rather than
    directly, so a cloud client watching this folder never has a chance
    to pick up and upload a half-written file to other devices.
    """
    sync_folder = Path(sync_folder)
    if not sync_folder.is_dir():
        raise FileNotFoundError(f"Sync folder does not exist: {sync_folder}")

    device_id = get_device_id(conn)
    payload = {
        "device_id": device_id,
        "notes": _export_notes(conn),
        "journal_entries": _export_journal_entries(conn),
        "tag_assignments": _export_tag_assignments(conn),
        "highlights": _export_highlights(conn),
        "reading_log": _export_reading_log(conn),
    }

    dest = _device_file_path(sync_folder, device_id)
    fd, tmp_name = tempfile.mkstemp(dir=sync_folder, prefix=".device-", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp_name, dest)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return dest


# ---------------------------------------------------------------------
# Import / merge
# ---------------------------------------------------------------------


def _keep_latest(bucket: dict[tuple, dict[str, Any]], key: tuple, record: dict[str, Any]) -> None:
    current = bucket.get(key)
    if current is None or record["updated_at"] >= current["updated_at"]:
        bucket[key] = record


def _read_device_files(sync_folder: Path) -> list[dict[str, Any]]:
    """Every device-*.json file's parsed contents, skipping (rather than
    erroring on) anything unreadable - a file can legitimately be mid-write
    by another device's cloud client when this device happens to read the
    folder."""
    payloads = []
    for path in sorted(Path(sync_folder).glob(DEVICE_FILE_GLOB)):
        try:
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return payloads


def _apply_journal_entry(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    """Matched by entry_date directly (a device-independent natural key
    on its own, unlike notes' verse/chapter target) - the optional
    reference is resolved separately and just left NULL if this device
    doesn't have that content synced yet, rather than dropping the whole
    entry the way an unresolvable note target does."""
    verse_id = chapter_id = None
    if record.get("target") is not None:
        resolved = _resolve_target(conn, record["target"])
        if resolved is not None:
            verse_id, chapter_id = resolved
    existing = conn.execute(
        "SELECT id, updated_at FROM journal_entries WHERE entry_date = ?",
        (record["entry_date"],),
    ).fetchone()
    if existing and existing["updated_at"] >= record["updated_at"]:
        return
    if existing:
        conn.execute(
            "UPDATE journal_entries SET text = ?, verse_id = ?, chapter_id = ?, "
            "updated_at = ?, deleted_at = ? WHERE id = ?",
            (
                record["text"],
                verse_id,
                chapter_id,
                record["updated_at"],
                record["deleted_at"],
                existing["id"],
            ),
        )
    else:
        conn.execute(
            "INSERT INTO journal_entries "
            "(entry_date, text, verse_id, chapter_id, updated_at, deleted_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                record["entry_date"],
                record["text"],
                verse_id,
                chapter_id,
                record["updated_at"],
                record["deleted_at"],
            ),
        )


def _apply_note(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    ids = _resolve_target(conn, record["target"])
    if ids is None:
        return
    verse_id, chapter_id = ids
    column = "verse_id" if verse_id is not None else "chapter_id"
    existing = conn.execute(
        f"SELECT id, updated_at FROM notes WHERE {column} = ? "
        "ORDER BY updated_at DESC, id DESC LIMIT 1",
        (verse_id if verse_id is not None else chapter_id,),
    ).fetchone()
    if existing and existing["updated_at"] >= record["updated_at"]:
        return
    if existing:
        conn.execute(
            "UPDATE notes SET text = ?, updated_at = ?, deleted_at = ? WHERE id = ?",
            (record["text"], record["updated_at"], record["deleted_at"], existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO notes (verse_id, chapter_id, text, updated_at, deleted_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (verse_id, chapter_id, record["text"], record["updated_at"], record["deleted_at"]),
        )


def _apply_tag_assignment(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    ids = _resolve_target(conn, record["target"])
    if ids is None:
        return
    verse_id, chapter_id = ids
    conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (record["tag_name"],))
    tag_id = conn.execute(
        "SELECT id FROM tags WHERE name = ?", (record["tag_name"],)
    ).fetchone()["id"]
    existing = conn.execute(
        "SELECT id, updated_at FROM tag_assignments "
        "WHERE tag_id = ? AND verse_id IS ? AND chapter_id IS ? "
        "ORDER BY updated_at DESC, id DESC LIMIT 1",
        (tag_id, verse_id, chapter_id),
    ).fetchone()
    if existing and existing["updated_at"] >= record["updated_at"]:
        return
    if existing:
        conn.execute(
            "UPDATE tag_assignments SET updated_at = ?, deleted_at = ? WHERE id = ?",
            (record["updated_at"], record["deleted_at"], existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO tag_assignments (tag_id, verse_id, chapter_id, updated_at, deleted_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (tag_id, verse_id, chapter_id, record["updated_at"], record["deleted_at"]),
        )


def _apply_highlight(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    ids = _resolve_target(conn, record["target"])
    if ids is None or ids[0] is None:
        return
    verse_id = ids[0]
    existing = conn.execute(
        "SELECT id, updated_at FROM highlights "
        "WHERE verse_id = ? AND start_offset = ? AND end_offset = ? "
        "ORDER BY updated_at DESC, id DESC LIMIT 1",
        (verse_id, record["start_offset"], record["end_offset"]),
    ).fetchone()
    if existing and existing["updated_at"] >= record["updated_at"]:
        return
    if existing:
        conn.execute(
            "UPDATE highlights SET color = ?, updated_at = ?, deleted_at = ? WHERE id = ?",
            (record["color"], record["updated_at"], record["deleted_at"], existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO highlights "
            "(verse_id, color, start_offset, end_offset, updated_at, deleted_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                verse_id,
                record["color"],
                record["start_offset"],
                record["end_offset"],
                record["updated_at"],
                record["deleted_at"],
            ),
        )


def _apply_reading_log(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    chapter_id = None
    if record["target"] is not None:
        ids = _resolve_target(conn, record["target"])
        if ids is not None:
            chapter_id = ids[1]
    existing = conn.execute(
        "SELECT updated_at FROM reading_log WHERE read_date = ?", (record["read_date"],)
    ).fetchone()
    if existing and existing["updated_at"] >= record["updated_at"]:
        return
    conn.execute(
        "INSERT INTO reading_log (read_date, chapter_id, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(read_date) DO UPDATE SET "
        "chapter_id = excluded.chapter_id, updated_at = excluded.updated_at",
        (record["read_date"], chapter_id, record["updated_at"]),
    )


def import_and_merge(conn: sqlite3.Connection, sync_folder: Path) -> None:
    """Reads every device-*.json file in `sync_folder` (including this
    device's own last export, if any), merges all records by natural key
    using last-write-wins on `updated_at`, and applies the merged result
    to `conn`. Safe to call even if this device hasn't exported yet, or
    hasn't exported its very latest local changes: each record is only
    ever applied if it's strictly newer than what's actually already in
    the local database (queried fresh, not assumed from a prior export),
    so this never regresses local state. Raises FileNotFoundError if
    `sync_folder` doesn't exist.
    """
    sync_folder = Path(sync_folder)
    if not sync_folder.is_dir():
        raise FileNotFoundError(f"Sync folder does not exist: {sync_folder}")

    notes: dict[tuple, dict[str, Any]] = {}
    journal_entries: dict[str, dict[str, Any]] = {}
    tags: dict[tuple, dict[str, Any]] = {}
    highlights: dict[tuple, dict[str, Any]] = {}
    reading_log: dict[tuple, dict[str, Any]] = {}

    for payload in _read_device_files(sync_folder):
        for rec in payload.get("notes", []):
            _keep_latest(notes, _target_key(rec["target"]), rec)
        for rec in payload.get("journal_entries", []):
            _keep_latest(journal_entries, rec["entry_date"], rec)
        for rec in payload.get("tag_assignments", []):
            _keep_latest(tags, (rec["tag_name"].lower(), _target_key(rec["target"])), rec)
        for rec in payload.get("highlights", []):
            key = (_target_key(rec["target"]), rec["start_offset"], rec["end_offset"])
            _keep_latest(highlights, key, rec)
        for rec in payload.get("reading_log", []):
            _keep_latest(reading_log, rec["read_date"], rec)

    for rec in notes.values():
        _apply_note(conn, rec)
    for rec in journal_entries.values():
        _apply_journal_entry(conn, rec)
    for rec in tags.values():
        _apply_tag_assignment(conn, rec)
    for rec in highlights.values():
        _apply_highlight(conn, rec)
    for rec in reading_log.values():
        _apply_reading_log(conn, rec)

    conn.commit()


def sync_now(conn: sqlite3.Connection, sync_folder: Path) -> None:
    """The full "Sync Now" action (see Stage 3): export this device's
    current state, then immediately merge in whatever every device's
    files - including the one just written - collectively contain."""
    export_device_state(conn, sync_folder)
    import_and_merge(conn, sync_folder)
