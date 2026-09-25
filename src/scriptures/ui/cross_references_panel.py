"""Cross-references tab: passages elsewhere in the corpus that quote,
paraphrase, or (for the Joseph Smith Translation/Moses) are a translation-
revision of something in the current chapter - see
scripts/build_cross_references.py for how this list is curated and why.

Unlike the Citations tab, each entry here points to exactly one other
passage, so there's no accordion - every entry is a single clickable row
(reference + relationship + a short note on how the two differ or
agree), jumping straight to that chapter in the reading view the same way
a search result or Topical Guide entry does.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from scriptures.data_access import CrossReference

_RELATIONSHIP_VERB = {
    "quotation": "Quotes",
    "paraphrase": "Parallels",
    "translation": "Compare with",
}


def _local_range_label(cross_reference: CrossReference) -> str:
    if cross_reference.verse_start is None:
        return "This chapter"
    if cross_reference.verse_end is None or cross_reference.verse_end == cross_reference.verse_start:
        return f"Verse {cross_reference.verse_start}"
    return f"Verses {cross_reference.verse_start}-{cross_reference.verse_end}"


class _CrossReferenceRow(QFrame):
    """One parallel passage: a clickable header naming both sides, and a
    short always-visible note on the relationship. Reuses the search
    view's resultRow/resultPrimary/resultSecondary styling."""

    clicked = Signal(int)

    def __init__(self, cross_reference: CrossReference, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("resultRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open this passage in the reading view")
        self._chapter_id = cross_reference.related_chapter_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        verb = _RELATIONSHIP_VERB.get(cross_reference.relationship, "See")
        title = QLabel(
            f"{_local_range_label(cross_reference)} — {verb} {cross_reference.related_reference}"
        )
        title.setObjectName("resultPrimary")
        title.setWordWrap(True)
        layout.addWidget(title)

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
    module docstring)."""

    chapter_selected = Signal(int)

    def __init__(self, cross_references: list[CrossReference], parent: QWidget | None = None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(12)

        self.reference_count = len(cross_references)

        if not cross_references:
            empty = QLabel(
                "No known parallel passages for this chapter - true of most "
                "chapters, since this list favors accuracy over completeness."
            )
            empty.setObjectName("resultSecondary")
            empty.setWordWrap(True)
            content_layout.addWidget(empty)
        else:
            for cross_reference in cross_references:
                row = _CrossReferenceRow(cross_reference)
                row.clicked.connect(self.chapter_selected)
                content_layout.addWidget(row)

        content_layout.addStretch(1)
        scroll.setWidget(content)
