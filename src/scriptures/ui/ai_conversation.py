"""The "Suggested by AI" block within search results (see search_view.py)
- asks the original search query, then lets the user send follow-up
refinements ("no, just the ones about baptism") without starting a new
top-level search.

Reads like a chat: your question, its answer, your follow-up, its
refined answer. But the "assistant" side of that conversation is never
free text the model wrote - every answer is a set of real, clickable
scripture cards, resolved and validated the exact same way a single
one-shot question is (see ask.py's module docstring). The model is never
given room to explain, editorialize, or discuss doctrine; it only ever
proposes references, and only real ones ever reach the screen.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from scriptures.ai_client import AiConfig
from scriptures.ask import AskedReference, QuestionAsker
from scriptures.citations import Citation
from scriptures.ui.result_row import ResultRow, truncate_text

DISCLAIMER = (
    "This only suggests real matches from Desktop Scriptures' own text - "
    "it can't discuss doctrine or explain further."
)


class _TalkRow(QFrame):
    """One citing talk for a suggested verse: title + "speaker · date",
    clickable out to churchofjesuschrist.org - same interaction as the
    Citations tab's and Topical Guide's own talk rows (a separate small
    copy, not a shared import, matching those two's own precedent: each
    takes a differently-sourced dataclass with the same shape)."""

    def __init__(self, citation: Citation, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("resultRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open this talk at churchofjesuschrist.org")
        self._url = citation.url

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        title = QLabel(citation.talk_title)
        title.setObjectName("resultPrimary")
        title.setWordWrap(True)
        layout.addWidget(title)

        # "General Conference talk" spelled out, unlike the Citations tab's
        # own _TalkRow - there, section context alone already makes it
        # obvious; here, a talk row sits directly beneath a verse row with
        # no section header between them, so it needs its own cue.
        subtitle = QLabel(f"General Conference talk · {citation.speaker} · {citation.date}")
        subtitle.setObjectName("resultSecondary")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mousePressEvent(event)


class AiConversationSection(QWidget):
    """Signal `result_selected(chapter_id)` mirrors SearchView's own -
    forwarded straight through so MainWindow doesn't need to know this
    widget exists."""

    result_selected = Signal(int)

    def __init__(
        self,
        conn: sqlite3.Connection,
        ai_config: AiConfig,
        question: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self.ai_config = ai_config
        self._history: list[tuple[str, list[str]]] = []
        self._asker: QuestionAsker | None = None
        self._pending_placeholder: QLabel | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QLabel("Suggested by AI")
        header.setObjectName("searchSectionHeader")
        layout.addWidget(header)

        # Each round (a question and its answer - real result cards, or a
        # "You: ..." label for a follow-up plus its answer) is appended
        # here in order, so the whole thing reads top-to-bottom as a
        # conversation.
        self._thread_layout = QVBoxLayout()
        self._thread_layout.setSpacing(10)
        layout.addLayout(self._thread_layout)

        # Persistent, not a one-time dismissible banner - sits right where
        # the user is about to type, so it's re-seen every follow-up, not
        # just skimmed past once.
        caption = QLabel(DISCLAIMER)
        caption.setObjectName("resultSecondary")
        caption.setWordWrap(True)
        layout.addWidget(caption)

        input_row = QHBoxLayout()
        self._follow_up_edit = QLineEdit()
        self._follow_up_edit.setPlaceholderText('Ask a follow-up, e.g. "just the ones about baptism"')
        self._follow_up_edit.returnPressed.connect(self._send_follow_up)
        input_row.addWidget(self._follow_up_edit)
        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self._send_follow_up)
        input_row.addWidget(self._send_button)
        layout.addLayout(input_row)

        self._ask(question)

    def _set_busy(self, busy: bool) -> None:
        self._follow_up_edit.setEnabled(not busy)
        self._send_button.setEnabled(not busy)

    def _ask(self, question: str) -> None:
        self._set_busy(True)
        self._pending_placeholder = QLabel("Asking AI...")
        self._pending_placeholder.setObjectName("resultSecondary")
        self._thread_layout.addWidget(self._pending_placeholder)

        self._asker = QuestionAsker(
            self.conn, self.ai_config, question, history=list(self._history), parent=self
        )
        self._asker.succeeded.connect(
            lambda refs, raw_content: self._on_succeeded(question, refs, raw_content)
        )
        self._asker.failed.connect(self._on_failed)

    def _clear_placeholder(self) -> None:
        if self._pending_placeholder is not None:
            self._pending_placeholder.hide()
            self._pending_placeholder.deleteLater()
            self._pending_placeholder = None

    def _on_succeeded(
        self, question: str, references: list[AskedReference], raw_content: str
    ) -> None:
        self._asker = None
        self._clear_placeholder()
        self._set_busy(False)
        self._history.append((question, [ref.reference for ref in references]))
        if not references:
            note = QLabel("No matches for that.")
            note.setObjectName("resultSecondary")
            self._thread_layout.addWidget(note)
            # Diagnostic only, never presented as an answer - shows
            # exactly what the model actually replied with, so "why did
            # this find nothing" (the model didn't know a real one,
            # ignored the "just a JSON array" instruction, or something
            # else) is visible rather than a silent dead end.
            raw_label = QLabel(f"AI's raw response: {truncate_text(raw_content, limit=400)}")
            raw_label.setObjectName("resultSecondary")
            raw_label.setWordWrap(True)
            self._thread_layout.addWidget(raw_label)
            return
        for ref in references:
            row = ResultRow(ref.chapter_id, ref.reference, truncate_text(ref.text))
            row.clicked.connect(self.result_selected)
            self._thread_layout.addWidget(row)
            # Real, already-harvested citing talks for this reference (see
            # ask.py's module docstring) - only shown when this particular
            # verse happens to have any; most won't, since harvesting is
            # necessarily partial.
            for citation in ref.citations:
                self._thread_layout.addWidget(_TalkRow(citation))

    def _on_failed(self, message: str, needs_api_key: bool) -> None:
        self._asker = None
        self._clear_placeholder()
        self._set_busy(False)
        if needs_api_key:
            QMessageBox.warning(
                self,
                "AI Search",
                "The configured AI endpoint rejected the request for an "
                "authentication reason - it likely requires an API key. "
                "Add one under AI Integration → AI Settings..., or leave it "
                "blank if you're using a local server that doesn't need "
                "one.",
            )
            return
        # An ordinary network hiccup shouldn't block the rest of the
        # conversation or the keyword results elsewhere on the page - a
        # quiet inline note, and the follow-up box stays usable to retry.
        note = QLabel(f"AI search failed: {message}")
        note.setObjectName("resultSecondary")
        self._thread_layout.addWidget(note)

    def _send_follow_up(self) -> None:
        text = self._follow_up_edit.text().strip()
        if not text or self._asker is not None:
            return
        self._follow_up_edit.clear()
        you_label = QLabel(f"You: {text}")
        you_label.setObjectName("resultPrimary")
        you_label.setWordWrap(True)
        self._thread_layout.addWidget(you_label)
        self._ask(text)
