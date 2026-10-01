""""Add Cross-reference" dialog: the reader links a verse range in the
chapter they're reading to any other passage in the corpus, typed in as an
ordinary reference ("Alma 32:21", "D&C 76:22-24", "Isaiah 53") - parsed
with ask.py's same parser, so the same standard abbreviations work here
too. Saved as one of the reader's own user_cross_references (see
schema.sql), shown alongside the curated entries in the Cross-references
tab and synced like notes.
"""

from __future__ import annotations

import re
import sqlite3

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from scriptures.ask import parse_reference
from scriptures.data_access import (
    add_user_cross_reference,
    find_chapter_for_reference,
    get_chapter_verse_count,
)

_VERSE_RANGE_RE = re.compile(r"^(?P<start>\d+)(?:\s*-\s*(?P<end>\d+))?$")


def parse_verse_range(text: str, verse_count: int) -> tuple[int | None, int | None]:
    """"" (the whole chapter), "16", or "16-18" -> (start, end), with end
    None for a single verse. Raises ValueError with a reader-facing
    message for anything else, or a range outside the chapter's own
    verses."""
    text = text.strip()
    if not text:
        return None, None
    match = _VERSE_RANGE_RE.match(text)
    if not match:
        raise ValueError("Verses should look like 16 or 16-18.")
    start = int(match.group("start"))
    end = int(match.group("end")) if match.group("end") else None
    if end is not None and end < start:
        raise ValueError("A verse range should go from lower to higher, like 16-18.")
    if start < 1 or (end or start) > verse_count:
        raise ValueError(f"That chapter has verses 1-{verse_count}.")
    return start, (None if end == start else end)


def resolve_related_passage(
    conn: sqlite3.Connection, text: str
) -> tuple[int, int | None, int | None]:
    """A typed reference -> (chapter_id, verse_start, verse_end), or
    ValueError with a reader-facing message if it doesn't parse or doesn't
    name a real passage in this database."""
    parsed = parse_reference(text)
    if parsed is None:
        raise ValueError("Enter a reference like Alma 32:21, D&C 76:22-24, or Isaiah 53.")
    book, chapter_number, verse_start, verse_end = parsed
    chapter_id = find_chapter_for_reference(conn, book, chapter_number)
    if chapter_id is None:
        raise ValueError(f"Couldn't find {book} {chapter_number}.")
    if verse_start is None:
        return chapter_id, None, None
    verse_text = str(verse_start) if verse_end is None else f"{verse_start}-{verse_end}"
    start, end = parse_verse_range(verse_text, get_chapter_verse_count(conn, chapter_id))
    return chapter_id, start, end


class AddCrossReferenceDialog(QDialog):
    """Saves on OK (staying open, after a warning, if either reference
    doesn't resolve) - the caller just checks exec()'s result and
    reloads."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        chapter_id: int,
        chapter_label: str,
        verse_start: int | None = None,
        verse_end: int | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add Cross-reference")
        self.setMinimumWidth(420)
        self._conn = conn
        self._chapter_id = chapter_id

        layout = QVBoxLayout(self)

        intro = QLabel(
            f"Link a passage in {chapter_label} to another one anywhere in "
            "the scriptures. It'll show up in the Cross-references tab on "
            "both chapters, marked as your own."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self._local_verses = QLineEdit()
        self._local_verses.setPlaceholderText("e.g. 16 or 16-18 - blank for the whole chapter")
        if verse_start is not None:
            self._local_verses.setText(
                str(verse_start)
                if verse_end is None or verse_end == verse_start
                else f"{verse_start}-{verse_end}"
            )
        form.addRow(f"Verses in {chapter_label}:", self._local_verses)

        self._related = QLineEdit()
        self._related.setPlaceholderText("e.g. Alma 32:21, D&C 76:22-24, or Isaiah 53")
        form.addRow("Related passage:", self._related)

        self._note = QPlainTextEdit()
        self._note.setPlaceholderText("Optional - how the two passages connect")
        self._note.setFixedHeight(80)
        form.addRow("Note:", self._note)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._related.setFocus()

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Add Cross-reference", message)

    def _on_accept(self) -> None:
        try:
            local_start, local_end = parse_verse_range(
                self._local_verses.text(), get_chapter_verse_count(self._conn, self._chapter_id)
            )
            related_chapter_id, related_start, related_end = resolve_related_passage(
                self._conn, self._related.text()
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return
        if (
            related_chapter_id == self._chapter_id
            and (related_start, related_end) == (local_start, local_end)
        ):
            self._show_error("That's the same passage - pick a different one to link to.")
            return
        add_user_cross_reference(
            self._conn,
            self._chapter_id,
            local_start,
            local_end,
            related_chapter_id,
            related_start,
            related_end,
            self._note.toPlainText().strip(),
        )
        self.accept()
