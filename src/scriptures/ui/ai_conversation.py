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
from scriptures.study_ask import StudyQuestionAsker, StudyResult, StudySearch
from scriptures.ui.lexicon_dialog import LexiconDialog
from scriptures.ui.result_row import ResultRow, truncate_text

DISCLAIMER = (
    "This only suggests real matches from Desktop Scriptures' own text - "
    "it can't discuss doctrine or explain further."
)
# With a study index (see study_ask.py), results come from the index and
# the model only chooses among them.
STUDY_DISCLAIMER = (
    "Every result comes from Desktop Scriptures' own library - scripture, "
    "talks, and more, found by meaning - and the AI only chooses among "
    "them. It can't discuss doctrine or explain further."
)
# Citing talks shown under each scripture result - the index's own talk
# and article results already cover the rest.
STUDY_CITATIONS_PER_RESULT = 2


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

        # citation.source_label spelled out, unlike the Citations tab's
        # own _TalkRow - there, section context alone already makes the
        # source obvious; here, a talk row sits directly beneath a verse
        # row with no section header between them, so it needs its own
        # cue (and since get_citations() merges General Conference talks
        # and Liahona articles together, a hardcoded "General Conference
        # talk" label here would be wrong for the latter).
        # Some harvested entries have no speaker (or date) - skip empty
        # parts rather than showing "Ensign ·  · January 2004".
        subtitle = QLabel(
            " · ".join(part for part in (citation.source_label, citation.speaker, citation.date) if part)
        )
        subtitle.setObjectName("resultSecondary")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mousePressEvent(event)


class _LinkRow(QFrame):
    """A talk or article result from the study index - opens its page on
    churchofjesuschrist.org, like _TalkRow."""

    def __init__(self, title: str, subtitle: str, url: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("resultRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open at churchofjesuschrist.org")
        self._url = url
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        primary = QLabel(title)
        primary.setObjectName("resultPrimary")
        primary.setWordWrap(True)
        layout.addWidget(primary)
        secondary = QLabel(subtitle)
        secondary.setObjectName("resultSecondary")
        layout.addWidget(secondary)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mousePressEvent(event)


class AiConversationSection(QWidget):
    """Signal `result_selected(chapter_id)` mirrors SearchView's own -
    forwarded straight through so MainWindow doesn't need to know this
    widget exists."""

    result_selected = Signal(int)
    topic_selected = Signal(int)

    def __init__(
        self,
        conn: sqlite3.Connection,
        ai_config: AiConfig,
        question: str,
        study: StudySearch | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self.ai_config = ai_config
        self._study = study
        # With a study index: the whole line of questioning so far (see
        # study_ask.retrieval_query).
        self._questions: list[str] = []
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
        caption = QLabel(STUDY_DISCLAIMER if study is not None else DISCLAIMER)
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
        self._pending_placeholder.setWordWrap(True)
        self._thread_layout.addWidget(self._pending_placeholder)

        if self._study is not None:
            self._questions.append(question)
            study = self._study
            self._asker = StudyQuestionAsker(
                self.conn, study.index, study.index_path, self.ai_config, study.embedding_config,
                study.embedding_dimensions, self._questions, parent=self,
            )
            self._asker.succeeded.connect(self._on_study_succeeded)
            self._asker.failed.connect(self._on_failed)
            return
        self._asker = QuestionAsker(
            self.conn, self.ai_config, question, history=list(self._history), parent=self
        )
        self._asker.succeeded.connect(
            lambda refs, raw_content, misses: self._on_succeeded(question, refs, raw_content, misses)
        )
        self._asker.failed.connect(self._on_failed)

    def _release_asker(self) -> None:
        """Frees a finished question's asker and its network connections -
        it's parented to this conversation, so dropping the reference alone
        kept every follow-up's connection (and thread) alive."""
        if self._asker is not None:
            self._asker.deleteLater()
            self._asker = None

    def _clear_placeholder(self) -> None:
        if self._pending_placeholder is not None:
            self._pending_placeholder.hide()
            self._pending_placeholder.deleteLater()
            self._pending_placeholder = None

    def _on_succeeded(
        self,
        question: str,
        references: list[AskedReference],
        raw_content: str,
        unresolved: list[str],
    ) -> None:
        self._release_asker()
        self._clear_placeholder()
        self._set_busy(False)
        self._history.append((question, [ref.reference for ref in references]))
        if not references:
            note = QLabel("No matches for that.")
            note.setObjectName("resultSecondary")
            note.setWordWrap(True)
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
        if unresolved:
            # The partial-miss case: some references resolved (shown
            # above), but the model also proposed at least one more that
            # didn't - without this, that would be silently invisible
            # (only a *complete* miss shows the raw response). Diagnostic
            # only, same as that raw-response note - not a suggestion
            # that this reference is real, just what was tried.
            missed_label = QLabel(
                "The AI also mentioned, but a match wasn't found for: " + ", ".join(unresolved)
            )
            missed_label.setObjectName("resultSecondary")
            missed_label.setWordWrap(True)
            self._thread_layout.addWidget(missed_label)

    def _on_study_succeeded(self, results: list[StudyResult], note: str) -> None:
        self._release_asker()
        self._clear_placeholder()
        self._set_busy(False)
        if not results:
            empty = QLabel("No matches for that.")
            empty.setObjectName("resultSecondary")
            empty.setWordWrap(True)
            self._thread_layout.addWidget(empty)
        for result in results:
            self._add_study_result(result)
        if note:
            note_label = QLabel(note)
            note_label.setObjectName("resultSecondary")
            note_label.setWordWrap(True)
            self._thread_layout.addWidget(note_label)

    def _add_study_result(self, result: StudyResult) -> None:
        if result.strongs:
            # ResultRow's id is unused here - the row opens the lexicon entry.
            row = ResultRow(0, result.title, f"{result.kind_label} · {truncate_text(result.detail)}")
            row.clicked.connect(lambda _id, s=result.strongs: LexiconDialog(self.conn, s, self).exec())
            self._thread_layout.addWidget(row)
            return
        if result.url:
            self._thread_layout.addWidget(_LinkRow(result.title, result.kind_label, result.url))
            return
        if result.topic_id is not None:
            # ResultRow carries one id; here it's the topic's, routed to
            # topic_selected rather than result_selected.
            row = ResultRow(result.topic_id, result.title, truncate_text(result.detail))
            row.clicked.connect(self.topic_selected)
            self._thread_layout.addWidget(row)
            return
        if result.chapter_id is None:
            return
        detail = truncate_text(result.detail) if result.kind == "scripture" else (
            f"{result.kind_label} · {truncate_text(result.detail)}" if result.detail else result.kind_label
        )
        row = ResultRow(result.chapter_id, result.title, detail)
        row.clicked.connect(self.result_selected)
        self._thread_layout.addWidget(row)
        citations = result.citations[:STUDY_CITATIONS_PER_RESULT]
        if citations:
            # Indented under a label so a citing talk reads as belonging to
            # the verse above it, not as a result the AI chose - in a mixed
            # list (unlike plain AI search's all-scripture one) the two
            # were otherwise indistinguishable.
            cited = QWidget()
            cited_layout = QVBoxLayout(cited)
            cited_layout.setContentsMargins(28, 0, 0, 0)
            cited_layout.setSpacing(4)
            label = QLabel("Cited in")
            label.setObjectName("resultSecondary")
            cited_layout.addWidget(label)
            for citation in citations:
                cited_layout.addWidget(_TalkRow(citation))
            self._thread_layout.addWidget(cited)

    def _on_failed(self, message: str, needs_api_key: bool) -> None:
        self._release_asker()
        self._clear_placeholder()
        self._set_busy(False)
        if needs_api_key:
            QMessageBox.warning(
                self,
                "AI Search",
                "The configured AI endpoint rejected the request for an "
                "authentication reason - it likely requires an API key. "
                "Add one under Menu → AI Integration → AI Settings..., or leave it "
                "blank if you're using a local server that doesn't need "
                "one.",
            )
            return
        # An ordinary network hiccup shouldn't block the rest of the
        # conversation or the keyword results elsewhere on the page - a
        # quiet inline note, and the follow-up box stays usable to retry.
        note = QLabel(f"AI search failed: {message}")
        note.setObjectName("resultSecondary")
        note.setWordWrap(True)
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
