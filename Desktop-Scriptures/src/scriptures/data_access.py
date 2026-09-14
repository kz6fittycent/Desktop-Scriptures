"""Repository layer over the scripture database.

The UI talks to these functions, never to raw SQL directly - keeps the
query logic in one place and makes the UI layer easy to test/reason about
independent of the schema.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Volume:
    id: int
    name: str
    slug: str


@dataclass(frozen=True)
class Testament:
    id: int
    volume_id: int
    name: str


@dataclass(frozen=True)
class Book:
    id: int
    name: str


@dataclass(frozen=True)
class Chapter:
    id: int
    chapter_number: int


@dataclass(frozen=True)
class Verse:
    id: int
    verse_number: int
    text: str
    reference: str


def get_volumes(conn: sqlite3.Connection) -> list[Volume]:
    rows = conn.execute(
        "SELECT id, name, slug FROM volumes ORDER BY sort_order"
    ).fetchall()
    return [Volume(r["id"], r["name"], r["slug"]) for r in rows]


def get_volume(conn: sqlite3.Connection, volume_id: int) -> Volume:
    r = conn.execute(
        "SELECT id, name, slug FROM volumes WHERE id = ?", (volume_id,)
    ).fetchone()
    return Volume(r["id"], r["name"], r["slug"])


def get_testaments(conn: sqlite3.Connection, volume_id: int) -> list[Testament]:
    """Returns an empty list for volumes with no testament tier
    (everything except the Bible)."""
    rows = conn.execute(
        "SELECT id, volume_id, name FROM testaments "
        "WHERE volume_id = ? ORDER BY sort_order",
        (volume_id,),
    ).fetchall()
    return [Testament(r["id"], r["volume_id"], r["name"]) for r in rows]


def get_testament(conn: sqlite3.Connection, testament_id: int) -> Testament:
    r = conn.execute(
        "SELECT id, volume_id, name FROM testaments WHERE id = ?", (testament_id,)
    ).fetchone()
    return Testament(r["id"], r["volume_id"], r["name"])


def get_books(
    conn: sqlite3.Connection, volume_id: int, testament_id: int | None = None
) -> list[Book]:
    if testament_id is not None:
        rows = conn.execute(
            "SELECT id, name FROM books "
            "WHERE volume_id = ? AND testament_id = ? ORDER BY sort_order",
            (volume_id, testament_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name FROM books "
            "WHERE volume_id = ? AND testament_id IS NULL ORDER BY sort_order",
            (volume_id,),
        ).fetchall()
    return [Book(r["id"], r["name"]) for r in rows]


def get_book(conn: sqlite3.Connection, book_id: int) -> Book:
    r = conn.execute("SELECT id, name FROM books WHERE id = ?", (book_id,)).fetchone()
    return Book(r["id"], r["name"])


def get_chapters(conn: sqlite3.Connection, book_id: int) -> list[Chapter]:
    rows = conn.execute(
        "SELECT id, chapter_number FROM chapters "
        "WHERE book_id = ? ORDER BY chapter_number",
        (book_id,),
    ).fetchall()
    return [Chapter(r["id"], r["chapter_number"]) for r in rows]


def get_chapter(conn: sqlite3.Connection, chapter_id: int) -> Chapter:
    r = conn.execute(
        "SELECT id, chapter_number FROM chapters WHERE id = ?", (chapter_id,)
    ).fetchone()
    return Chapter(r["id"], r["chapter_number"])


def get_verses(conn: sqlite3.Connection, chapter_id: int) -> list[Verse]:
    rows = conn.execute(
        "SELECT id, verse_number, text, reference FROM verses "
        "WHERE chapter_id = ? ORDER BY verse_number",
        (chapter_id,),
    ).fetchall()
    return [Verse(r["id"], r["verse_number"], r["text"], r["reference"]) for r in rows]


def record_reading(conn: sqlite3.Connection, chapter_id: int, read_date: str) -> None:
    """Log today's date as read, for the reading streak. Safe to call
    multiple times per day - read_date is UNIQUE, so we upsert."""
    conn.execute(
        "INSERT INTO reading_log (read_date, chapter_id) VALUES (?, ?) "
        "ON CONFLICT(read_date) DO UPDATE SET chapter_id = excluded.chapter_id",
        (read_date, chapter_id),
    )
    conn.commit()
