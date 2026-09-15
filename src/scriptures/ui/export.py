"""Export notes and search results to a plain-text file under
~/Documents, with a confirmation message in the GUI once it's saved.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QWidget

from scriptures.data_access import get_all_notes, search_verse_references, search_verses


def _documents_dir() -> Path:
    documents = Path.home() / "Documents"
    documents.mkdir(parents=True, exist_ok=True)
    return documents


def _write_export(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_notes(conn: sqlite3.Connection, parent: QWidget | None) -> None:
    notes = get_all_notes(conn)
    if not notes:
        QMessageBox.information(parent, "Export Notes", "You don't have any notes yet.")
        return

    timestamp = datetime.now()
    lines = [
        "Desktop Scriptures — Notes Export",
        f"Exported {timestamp:%Y-%m-%d %H:%M:%S}",
        "",
    ]
    for note in notes:
        lines.append(note.reference)
        lines.append(note.text)
        lines.append("")

    path = _documents_dir() / f"desktop-scriptures-notes-{timestamp:%Y%m%d-%H%M%S}.txt"
    _write_export(path, lines)

    QMessageBox.information(
        parent, "Export Notes", f"Saved {len(notes)} note(s) to:\n{path}"
    )


def export_search_results(conn: sqlite3.Connection, query: str, parent: QWidget | None) -> None:
    query = query.strip()
    if not query:
        QMessageBox.information(
            parent, "Export Search", "Type something in the search bar first."
        )
        return

    seen_ids: set[int] = set()
    verses = []
    for v in [*search_verse_references(conn, query), *search_verses(conn, query)]:
        if v.id in seen_ids:
            continue
        seen_ids.add(v.id)
        verses.append(v)

    if not verses:
        QMessageBox.information(
            parent, "Export Search", f'No scripture results for "{query}" to export.'
        )
        return

    timestamp = datetime.now()
    lines = [
        "Desktop Scriptures — Search Export",
        f'Query: "{query}"',
        f"Exported {timestamp:%Y-%m-%d %H:%M:%S}",
        "",
    ]
    for verse in verses:
        lines.append(verse.reference)
        lines.append(verse.text)
        lines.append("")

    safe_query = "".join(c if c.isalnum() else "-" for c in query).strip("-")[:40] or "search"
    path = _documents_dir() / f"desktop-scriptures-search-{safe_query}-{timestamp:%Y%m%d-%H%M%S}.txt"
    _write_export(path, lines)

    QMessageBox.information(
        parent, "Export Search", f"Saved {len(verses)} verse(s) to:\n{path}"
    )
