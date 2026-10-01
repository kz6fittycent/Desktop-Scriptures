"""Cross-references tab: passages elsewhere in the corpus that quote,
paraphrase, or (for the Joseph Smith Translation/Moses) are a translation-
revision of something in the current chapter, plus a smaller set of
widely-recognized traditional/thematic associations scripture itself
doesn't explicitly state (labeled "Traditionally linked to" rather than
one of the other four verbs, so a reader can tell the tiers apart at a
glance) - see scripts/build_cross_references.py for how this list is
curated and why.

Unlike the Citations tab, each entry here points to exactly one other
passage, so there's no accordion - every entry is a single clickable row
(reference + relationship + a short note on how the two differ or
agree), jumping straight to that chapter in the reading view the same way
a search result or Topical Guide entry does. Each entry is also tagged
with the doctrine it's actually about (e.g. Atonement, Faith) as small
clickable chips reusing the same Topical Guide topics shown elsewhere in
the app - clicking one jumps to that topic's own detail view instead of
the related chapter.

The reader can also add their own cross-references (see
add_cross_reference_dialog.py), listed after the curated ones - labeled
"See also" and marked "Your cross-reference" so they're never mistaken for
a curated entry, each with its own Remove button.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from scriptures.data_access import (
    CrossReference,
    CrossReferenceTopic,
    delete_user_cross_reference,
    get_cross_references,
)
from scriptures.ui.add_cross_reference_dialog import AddCrossReferenceDialog

_RELATIONSHIP_VERB = {
    "quotation": "Quotes",
    "paraphrase": "Parallels",
    "translation": "Compare with",
    "typology": "Connects to",
    # Deliberately a longer, more hedged phrase than the other four - this
    # is the one relationship kind scripture itself doesn't explicitly
    # state (see build_cross_references.py's own note on the distinction),
    # and the wording here is the main way a reader can tell the two
    # tiers apart at a glance.
    "tradition": "Traditionally linked to",
    # The reader's own entry (see the module docstring) - deliberately
    # the most neutral verb, since the app can't vouch for what kind of
    # link it is.
    "user": "See also",
}


def _local_range_label(cross_reference: CrossReference) -> str:
    if cross_reference.verse_start is None:
        return "This chapter"
    if cross_reference.verse_end is None or cross_reference.verse_end == cross_reference.verse_start:
        return f"Verse {cross_reference.verse_start}"
    return f"Verses {cross_reference.verse_start}-{cross_reference.verse_end}"


class _TopicChip(QPushButton):
    """A small clickable pill naming one doctrine this passage pair is
    about (e.g. "Atonement"), jumping to that topic's own Topical Guide
    detail view - a flat QPushButton rather than a QLabel specifically so
    it intercepts its own click instead of bubbling up to the row's
    chapter-jump behavior."""

    def __init__(self, topic: CrossReferenceTopic, parent: QWidget | None = None):
        super().__init__(topic.name, parent)
        self.setObjectName("crossReferenceTopicChip")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Open the \"{topic.name}\" topic")
        self.setFlat(True)


class _CrossReferenceRow(QFrame):
    """One parallel passage: a clickable header naming both sides, an
    optional row of topic chips naming the doctrine involved, and a short
    always-visible note on how it plays out across both passages. Reuses
    the search view's resultRow/resultPrimary/resultSecondary styling."""

    clicked = Signal(int)
    topic_clicked = Signal(int)
    remove_clicked = Signal(int)

    def __init__(self, cross_reference: CrossReference, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("resultRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open this passage in the reading view")
        self._chapter_id = cross_reference.related_chapter_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        verb = _RELATIONSHIP_VERB.get(cross_reference.relationship, "See")
        title = QLabel(
            f"{_local_range_label(cross_reference)} — {verb} {cross_reference.related_reference}"
        )
        title.setObjectName("resultPrimary")
        title.setWordWrap(True)
        layout.addWidget(title)

        if cross_reference.user_id is not None:
            # Same reasoning as _TopicChip for a QPushButton: it intercepts
            # its own click instead of also triggering the row's jump.
            owner_row = QHBoxLayout()
            owner_row.setContentsMargins(0, 0, 0, 0)
            owner_label = QLabel("Your cross-reference")
            owner_label.setObjectName("resultSecondary")
            owner_row.addWidget(owner_label)
            owner_row.addStretch(1)
            remove_button = QPushButton("Remove")
            remove_button.setToolTip("Remove this cross-reference")
            remove_button.clicked.connect(
                lambda checked=False, i=cross_reference.user_id: self.remove_clicked.emit(i)
            )
            owner_row.addWidget(remove_button)
            layout.addLayout(owner_row)

        if cross_reference.topics:
            chips_row = QHBoxLayout()
            chips_row.setContentsMargins(0, 0, 0, 0)
            chips_row.setSpacing(6)
            for topic in cross_reference.topics:
                chip = _TopicChip(topic)
                chip.clicked.connect(lambda checked=False, t=topic: self.topic_clicked.emit(t.id))
                chips_row.addWidget(chip)
            chips_row.addStretch(1)
            layout.addLayout(chips_row)

        if cross_reference.note:
            note = QLabel(cross_reference.note)
            note.setObjectName("resultSecondary")
            note.setWordWrap(True)
            layout.addWidget(note)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._chapter_id)
        super().mousePressEvent(event)


class CrossReferencesPanel(QWidget):
    """Scrollable list of this chapter's known parallel passages, or an
    empty-state message if none - most chapters, since curation is
    accuracy-first rather than exhaustive (see the build script's own
    module docstring) - plus the reader's own, and a button to add more.
    `references_changed` fires after an add/remove so the owning tab can
    refresh its count."""

    chapter_selected = Signal(int)
    topic_selected = Signal(int)
    references_changed = Signal()

    def __init__(
        self,
        conn: sqlite3.Connection,
        chapter_id: int,
        chapter_label: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._conn = conn
        self._chapter_id = chapter_id
        self._chapter_label = chapter_label
        self.reference_count = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        add_row = QHBoxLayout()
        add_button = QPushButton("Add Cross-reference…")
        add_button.setToolTip("Link a passage here to another one anywhere in the scriptures")
        add_button.clicked.connect(lambda: self.open_add_dialog())
        add_row.addWidget(add_button)
        add_row.addStretch(1)
        outer.addLayout(add_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self._scroll)

        self._reload()

    def _reload(self) -> None:
        cross_references = get_cross_references(self._conn, self._chapter_id)
        self.reference_count = len(cross_references)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(12)

        if not cross_references:
            empty = QLabel(
                "No known parallel passages for this chapter - true of most "
                "chapters, since this list favors accuracy over completeness. "
                "You can add your own with the button above."
            )
            empty.setObjectName("resultSecondary")
            empty.setWordWrap(True)
            content_layout.addWidget(empty)
        else:
            for cross_reference in cross_references:
                row = _CrossReferenceRow(cross_reference)
                row.clicked.connect(self.chapter_selected)
                row.topic_clicked.connect(self.topic_selected)
                row.remove_clicked.connect(self._remove)
                content_layout.addWidget(row)

        content_layout.addStretch(1)
        # setWidget() deletes whatever content widget it's replacing.
        self._scroll.setWidget(content)

    def open_add_dialog(self, verse_start: int | None = None, verse_end: int | None = None) -> None:
        dialog = AddCrossReferenceDialog(
            self._conn, self._chapter_id, self._chapter_label, verse_start, verse_end, self
        )
        if dialog.exec():
            self._reload()
            self.references_changed.emit()

    def _remove(self, user_cross_reference_id: int) -> None:
        answer = QMessageBox.question(
            self, "Remove Cross-reference", "Remove this cross-reference and its note?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        delete_user_cross_reference(self._conn, user_cross_reference_id)
        self._reload()
        self.references_changed.emit()
