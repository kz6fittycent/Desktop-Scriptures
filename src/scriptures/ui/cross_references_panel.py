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
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from scriptures.data_access import CrossReference, CrossReferenceTopic

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
    topic_selected = Signal(int)

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
                row.topic_clicked.connect(self.topic_selected)
                content_layout.addWidget(row)

        content_layout.addStretch(1)
        scroll.setWidget(content)
