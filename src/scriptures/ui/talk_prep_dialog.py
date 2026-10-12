"""The Talk Prep dialog - the guided interview and its results (see
talk_prep.py for what each step does and why the AI never writes).

Non-modal, so the reader can open a scripture from the results and keep
the list beside it. The banner reminding the user to rely on the Holy
Ghost stays at the top through every step.

Choices are checkable QPushButtons and ToggleRows rather than radio
buttons and QCheckBoxes - the snap's GTK-integrated style draws those
indicators too small to notice (see gc_reminder_dialog.py's _CheckboxRow).
"""

from __future__ import annotations

import html
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scriptures import talk_prep
from scriptures.ai_client import AiConfig
from scriptures.cfm import CfmFetcher
from scriptures.study_ask import StudyResult, StudySearch, _VectorLoader
from scriptures.ui.toggle_row import ToggleRow

_WIDTH = 720
_HEIGHT = 720
_NOT_SURE = 0  # the length button group's id for "Not sure"

_LESSON_CHOICES = (
    ("cfm", "This week's Come Follow Me reading"),
    ("block", "A scripture reading I'll type"),
    ("manual", "A lesson from a manual"),
    ("none", "None of these"),
)
_LESSON_PLACEHOLDERS = {
    "cfm": "This week's reading appears here",
    "block": "e.g. Alma 32-35",
    "manual": "The lesson's title",
}


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("talkPrepHeading")
    label.setWordWrap(True)
    return label


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("talkPrepHint")
    label.setWordWrap(True)
    return label


def _choice(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("choiceCard")  # the AI wizard's checkable-choice style
    button.setCheckable(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    # Sized for the bold text it shows once checked (choiceCard:checked),
    # and never squeezed shorter than its text by a full page.
    bold = button.font()
    bold.setBold(True)
    width = QFontMetrics(bold).horizontalAdvance(text)
    button.setMinimumWidth(min(width + 40, 640))
    button.setMinimumHeight(button.sizeHint().height() + 6)
    return button


def _scrolling(page: QWidget) -> QScrollArea:
    """A page that may be taller than the dialog (the directions page,
    with its choices and source toggles) scrolls instead of squeezing."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(page)
    return area


class TalkPrepDialog(QDialog):
    def __init__(
        self,
        conn: sqlite3.Connection,
        chat_config: AiConfig,
        study: StudySearch | None,
        open_chapter: Callable[[int], None],
        open_topic: Callable[[int], None],
        build_index: Callable[[], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self._chat_config = chat_config
        self._study = study
        self._open_chapter = open_chapter
        self._open_topic = open_topic
        self._build_index = build_index
        self._interview = talk_prep.Interview()
        self._session: talk_prep.Session | None = None
        self._topic_vector: list[float] | None = None
        self._themes: list[str] = []
        self._finder = None
        self._search = None
        self._key_finder = None
        self._cfm_fetcher = None

        self.setWindowTitle("Talk Prep")
        self.setModal(False)
        self.resize(_WIDTH, _HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        banner = QLabel(talk_prep.BANNER)
        banner.setObjectName("talkPrepBanner")
        banner.setWordWrap(True)
        layout.addWidget(banner)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        self._start_page = self._build_start_page()
        self._needs_index_page = self._build_needs_index_page()
        self._topic_page = self._build_topic_page()
        self._talk_page = self._build_talk_page()
        self._direction_page = _scrolling(self._build_direction_page())
        self._results_page = self._build_results_page()
        for page in (
            self._start_page, self._needs_index_page, self._topic_page,
            self._talk_page, self._direction_page, self._results_page,
        ):
            self._stack.addWidget(page)

        nav = QHBoxLayout()
        self._back_button = QPushButton("Back")
        self._back_button.clicked.connect(self._back)
        nav.addWidget(self._back_button)
        nav.addStretch(1)
        self._next_button = QPushButton("Next")
        self._next_button.setDefault(True)
        self._next_button.clicked.connect(self._next)
        nav.addWidget(self._next_button)
        layout.addLayout(nav)

        # Loading the index's vectors takes a while the first time (300 MB
        # for a full index) - start now, while the user is still typing.
        self._loading_vectors = False
        self._directions_waiting = False
        if self._study is not None and not self._study.index.is_loaded():
            self._loading_vectors = True
            self._vector_loader = _VectorLoader(self)
            self._vector_loader.done.connect(self._on_vectors_loaded)
            self._vector_loader.start(self._study.index_path)

        if self._study is None:
            self._show(self._needs_index_page)
        elif talk_prep.list_sessions(self.conn):
            self._show(self._start_page)
        else:
            self._show(self._topic_page)

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    def _build_start_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_heading("Your recent preparations"))
        layout.addWidget(_hint("Open one to see its results again, or start a new one."))
        self._sessions_list = QListWidget()
        self._sessions_list.itemDoubleClicked.connect(lambda _item: self._open_selected_session())
        layout.addWidget(self._sessions_list, 1)
        row = QHBoxLayout()
        open_button = QPushButton("Open")
        open_button.clicked.connect(self._open_selected_session)
        row.addWidget(open_button)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._delete_selected_session)
        row.addWidget(delete_button)
        row.addStretch(1)
        new_button = QPushButton("Start a New Preparation")
        new_button.clicked.connect(self._start_new)
        row.addWidget(new_button)
        layout.addLayout(row)
        return page

    def _build_needs_index_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_heading("Talk Prep needs the study index"))
        layout.addWidget(
            _hint(
                "Talk Prep searches by meaning across the scriptures, Conference talks, and "
                "Ensign/Liahona articles using the study index, which is built once on this "
                "computer through your AI service's embedding model."
            )
        )
        button = QPushButton("Build Study Index...")
        button.clicked.connect(self._on_build_index)
        row = QHBoxLayout()
        row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _build_topic_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(_heading("What's your topic?"))
        self._topic_edit = QLineEdit()
        self._topic_edit.setPlaceholderText("e.g. repentance")
        self._topic_edit.returnPressed.connect(self._next)
        layout.addWidget(self._topic_edit)

        layout.addWidget(_heading("Where will you give it?"))
        self._meeting_combo = QComboBox()
        self._meeting_combo.addItems(talk_prep.MEETINGS)
        self._meeting_combo.currentTextChanged.connect(self._on_meeting_changed)
        layout.addWidget(self._meeting_combo)

        self._length_box = QWidget()
        length_layout = QVBoxLayout(self._length_box)
        length_layout.setContentsMargins(0, 0, 0, 0)
        length_layout.addWidget(_heading("How long is it?"))
        row = QHBoxLayout()
        self._length_group = QButtonGroup(self)
        for minutes in sorted(talk_prep.RESULTS_BY_LENGTH):
            button = _choice(f"{minutes} minutes")
            self._length_group.addButton(button, minutes)
            row.addWidget(button)
        not_sure = _choice("Not sure")
        self._length_group.addButton(not_sure, _NOT_SURE)
        row.addWidget(not_sure)
        row.addStretch(1)
        not_sure.setChecked(True)
        length_layout.addLayout(row)
        layout.addWidget(self._length_box)

        self._lesson_box = QWidget()
        lesson_layout = QVBoxLayout(self._lesson_box)
        lesson_layout.setContentsMargins(0, 0, 0, 0)
        lesson_layout.addWidget(_heading("What is the lesson based on?"))
        self._lesson_group = QButtonGroup(self)
        self._lesson_ids = {}
        for number, (key, text) in enumerate(_LESSON_CHOICES):
            button = _choice(text)
            self._lesson_group.addButton(button, number)
            self._lesson_ids[number] = key
            lesson_layout.addWidget(button)
        self._lesson_group.button(len(_LESSON_CHOICES) - 1).setChecked(True)
        self._lesson_group.idClicked.connect(self._on_lesson_source)
        self._lesson_edit = QLineEdit()
        self._lesson_edit.hide()
        lesson_layout.addWidget(self._lesson_edit)
        self._lesson_status = _hint("")
        self._lesson_status.hide()
        lesson_layout.addWidget(self._lesson_status)
        self._lesson_box.hide()
        layout.addWidget(self._lesson_box)

        layout.addStretch(1)
        return page

    def _build_talk_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(_heading("Were you given a specific talk or article to focus on?"))
        row = QHBoxLayout()
        self._talk_group = QButtonGroup(self)
        self._talk_yes = _choice("Yes")
        self._talk_no = _choice("No")
        self._talk_group.addButton(self._talk_yes)
        self._talk_group.addButton(self._talk_no)
        self._talk_no.setChecked(True)
        row.addWidget(self._talk_yes)
        row.addWidget(self._talk_no)
        row.addStretch(1)
        layout.addLayout(row)

        self._talk_box = QWidget()
        box = QVBoxLayout(self._talk_box)
        box.setContentsMargins(0, 0, 0, 0)
        self._talk_search = QLineEdit()
        self._talk_search.setPlaceholderText("Type part of its title or the speaker's name")
        self._talk_search.textChanged.connect(self._search_talks)
        box.addWidget(self._talk_search)
        self._talk_list = QListWidget()
        self._talk_list.currentItemChanged.connect(self._on_talk_chosen)
        box.addWidget(self._talk_list, 1)
        self._talk_chosen = _hint("")
        box.addWidget(self._talk_chosen)
        box.addWidget(
            _hint("Optional: paste a passage from it that stood out to you. It only steers the search.")
        )
        self._talk_passage = QTextEdit()
        self._talk_passage.setAcceptRichText(False)
        self._talk_passage.setFixedHeight(80)
        box.addWidget(self._talk_passage)
        self._talk_box.hide()
        layout.addWidget(self._talk_box, 1)
        self._talk_yes.toggled.connect(self._talk_box.setVisible)
        layout.addStretch(0)
        return page

    def _build_direction_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(_heading("Which direction would you like to go?"))
        self._direction_status = _hint("")
        layout.addWidget(self._direction_status)
        self._themes_box = QVBoxLayout()
        layout.addLayout(self._themes_box)
        self._theme_buttons: list[QPushButton] = []

        layout.addWidget(
            _hint(
                "Anything else on your mind - impressions you've felt, experiences, a question "
                "you want to answer? (optional - only used to steer the search)"
            )
        )
        self._impressions = QTextEdit()
        self._impressions.setAcceptRichText(False)
        self._impressions.setFixedHeight(70)
        layout.addWidget(self._impressions)

        layout.addWidget(_heading("Include"))
        self._source_rows: dict[str, ToggleRow] = {}
        for key, text in talk_prep.SOURCE_OPTIONS:
            row = ToggleRow(text, checked=True)
            self._source_rows[key] = row
            layout.addWidget(row)
        layout.addStretch(1)
        return page

    def _build_results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._results_title = _heading("")
        layout.addWidget(self._results_title)
        self._results_status = _hint("")
        layout.addWidget(self._results_status)

        self._results_scroll = QScrollArea()
        self._results_scroll.setWidgetResizable(True)
        self._results_scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self._results_scroll, 1)

        row = QHBoxLayout()
        self._refine_button = QPushButton("Refine...")
        self._refine_button.setToolTip("Try a different direction")
        self._refine_button.clicked.connect(self._refine)
        row.addWidget(self._refine_button)
        self._journal_button = QPushButton("Save to Journal")
        self._journal_button.clicked.connect(self._save_to_journal)
        row.addWidget(self._journal_button)
        self._copy_button = QPushButton("Copy")
        self._copy_button.clicked.connect(self._copy)
        row.addWidget(self._copy_button)
        self._export_button = QPushButton("Export...")
        self._export_button.clicked.connect(self._export)
        row.addWidget(self._export_button)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _show(self, page: QWidget) -> None:
        self._stack.setCurrentWidget(page)
        if page is self._start_page:
            self._fill_sessions()
        if page is self._topic_page:
            # Back to the saved preparations, when there are any.
            self._back_button.setVisible(bool(talk_prep.list_sessions(self.conn)))
        else:
            self._back_button.setVisible(page in (self._talk_page, self._direction_page, self._results_page))
        self._next_button.setVisible(page in (self._topic_page, self._talk_page, self._direction_page, self._results_page))
        self._next_button.setText(
            {
                self._direction_page: "Find Sources",
                self._results_page: "Start Over",
            }.get(page, "Next")
        )
        if page is self._topic_page:
            self._topic_edit.setFocus()

    def _back(self) -> None:
        page = self._stack.currentWidget()
        previous = {
            self._topic_page: self._start_page,
            self._talk_page: self._topic_page,
            self._direction_page: self._talk_page,
            self._results_page: self._direction_page,
        }.get(page)
        if previous is self._direction_page:
            self._refine()
        elif previous is not None:
            self._show(previous)

    def _next(self) -> None:
        page = self._stack.currentWidget()
        if page is self._topic_page:
            if not self._read_topic_page():
                return
            self._show(self._talk_page)
            self._talk_search.setFocus()
        elif page is self._talk_page:
            if not self._read_talk_page():
                return
            self._themes = []
            self._show(self._direction_page)
            self._find_directions()
        elif page is self._direction_page:
            self._read_direction_page()
            self._find_sources()
        elif page is self._results_page:
            self._start_new()

    # ------------------------------------------------------------------
    # Step 1: topic, meeting, length / lesson
    # ------------------------------------------------------------------

    def _on_meeting_changed(self, meeting: str) -> None:
        is_lesson = meeting == talk_prep.LESSON_MEETING
        self._lesson_box.setVisible(is_lesson)
        self._length_box.setVisible(not is_lesson)

    def _on_lesson_source(self, number: int) -> None:
        key = self._lesson_ids[number]
        self._lesson_edit.setVisible(key != "none")
        self._lesson_edit.setPlaceholderText(_LESSON_PLACEHOLDERS.get(key, ""))
        self._lesson_status.hide()
        if key == "cfm":
            self._lesson_status.setText("Looking up this week's reading...")
            self._lesson_status.show()
            self._cfm_fetcher = CfmFetcher(self)
            self._cfm_fetcher.succeeded.connect(self._on_cfm)
            self._cfm_fetcher.failed.connect(self._on_cfm_failed)
        elif key in ("block", "manual"):
            self._lesson_edit.clear()
            self._lesson_edit.setFocus()

    def _on_cfm(self, lesson) -> None:
        self._lesson_edit.setText(lesson.scripture_block)
        self._lesson_status.setText(f"Come Follow Me, {lesson.date_label}.")

    def _on_cfm_failed(self, message: str) -> None:
        self._lesson_status.setText(
            f"Couldn't look up this week's reading ({message}). You can type it instead, e.g. Alma 32-35."
        )

    def _read_topic_page(self) -> bool:
        interview = self._interview
        interview.topic = self._topic_edit.text().strip()
        interview.meeting = self._meeting_combo.currentText()
        length = self._length_group.checkedId()
        interview.length = None if length in (_NOT_SURE, -1) else length
        if interview.is_lesson:
            interview.lesson_source = self._lesson_ids.get(self._lesson_group.checkedId(), "none")
            interview.lesson_text = self._lesson_edit.text().strip() if interview.lesson_source != "none" else ""
        else:
            interview.lesson_source, interview.lesson_text = "none", ""
        if not interview.topic and not interview.lesson_text:
            self._topic_edit.setPlaceholderText("Type a topic to start - e.g. repentance")
            self._topic_edit.setFocus()
            return False
        return True

    # ------------------------------------------------------------------
    # Step 2: assigned talk
    # ------------------------------------------------------------------

    def _search_talks(self, text: str) -> None:
        self._talk_list.clear()
        for work in talk_prep.find_works(text):
            byline = ", ".join(part for part in (work.speaker, work.date) if part)
            item = QListWidgetItem(f"{work.talk_title} - {byline}" if byline else work.talk_title)
            item.setData(Qt.ItemDataRole.UserRole, work.url)
            self._talk_list.addItem(item)

    def _on_talk_chosen(self, item: QListWidgetItem | None, _previous=None) -> None:
        if item is None:
            return
        self._talk_chosen.setText(f"Chosen: {item.text()}")

    def _read_talk_page(self) -> bool:
        interview = self._interview
        if self._talk_yes.isChecked():
            item = self._talk_list.currentItem()
            if item is None:
                self._talk_chosen.setText("Choose the talk from the list - or answer No.")
                return False
            work = talk_prep.work_by_url(item.data(Qt.ItemDataRole.UserRole))
            interview.talk_url = work.url if work else ""
            interview.talk_title = work.talk_title if work else ""
            interview.talk_passage = self._talk_passage.toPlainText().strip()
        else:
            interview.talk_url = interview.talk_title = interview.talk_passage = ""
        return True

    # ------------------------------------------------------------------
    # Step 3: directions
    # ------------------------------------------------------------------

    def _on_vectors_loaded(self, arrays) -> None:
        if not isinstance(arrays, Exception) and not self._study.index.is_loaded():
            self._study.index.adopt_arrays(arrays)
        self._loading_vectors = False
        if self._directions_waiting:
            self._directions_waiting = False
            self._find_directions()

    def _find_directions(self) -> None:
        for button in self._theme_buttons:
            button.deleteLater()
        self._theme_buttons = []
        self._direction_status.setText("Finding directions you could take...")
        self._next_button.setEnabled(False)
        if self._loading_vectors:
            self._directions_waiting = True  # _on_vectors_loaded picks it up
            return
        self._finder = talk_prep.DirectionFinder(self._study, self._chat_config, self._interview, self)
        self._finder.ready.connect(self._on_directions)

    def _on_directions(self, themes: list, vector) -> None:
        self._themes = list(themes)
        self._topic_vector = vector
        self._next_button.setEnabled(True)
        self._show_themes()

    def _show_themes(self) -> None:
        for button in self._theme_buttons:
            button.deleteLater()
        self._theme_buttons = []
        if not self._themes:
            self._direction_status.setText("No particular directions stood out - Find Sources searches the topic itself.")
            return
        self._direction_status.setText("Choose any that fit (or none), then Find Sources.")
        for theme in self._themes:
            button = _choice(theme)
            button.setChecked(theme in self._interview.directions)
            self._themes_box.addWidget(button)
            self._theme_buttons.append(button)

    def _read_direction_page(self) -> None:
        interview = self._interview
        interview.directions = [b.text() for b in self._theme_buttons if b.isChecked()]
        interview.impressions = self._impressions.toPlainText().strip()
        interview.sources = [key for key, row in self._source_rows.items() if row.isChecked()]
        if not interview.sources:
            interview.sources = [key for key, _ in talk_prep.SOURCE_OPTIONS]

    def _refine(self) -> None:
        self._show(self._direction_page)
        if self._themes:
            self._show_themes()
        elif self._study is not None:
            self._find_directions()

    # ------------------------------------------------------------------
    # Step 4: results
    # ------------------------------------------------------------------

    def _find_sources(self) -> None:
        interview = self._interview
        if self._session is None or self._session.interview is not interview:
            self._session = talk_prep.new_session(interview)
        self._show(self._results_page)
        self._set_results_busy(True)
        self._results_title.setText(self._session.title)
        self._results_status.setText("Searching the scriptures, talks, and articles...")
        self._results_scroll.setWidget(QWidget())
        self._search = talk_prep.TalkPrepSearch(
            self.conn, self._study, self._chat_config, interview, self._topic_vector, self
        )
        self._search.succeeded.connect(self._on_results)
        self._search.failed.connect(self._on_results_failed)

    def _set_results_busy(self, busy: bool) -> None:
        for button in (self._refine_button, self._journal_button, self._copy_button, self._export_button, self._next_button):
            button.setEnabled(not busy)

    def _on_results(self, results: list, note: str, query_vector) -> None:
        self._results_note = note
        self._results_status.setText("Finding the key verses...")
        self._key_finder = talk_prep.KeyVerseFinder(
            self.conn, self._study, results, " ".join(self._interview.questions()), query_vector, self
        )
        self._key_finder.done.connect(self._on_key_verses)
        self._key_finder.start()

    def _on_key_verses(self, results: list) -> None:
        self._session.results = results
        self._session.note = self._results_note
        talk_prep.save_session(self.conn, self._session)
        self._render_results()

    def _on_results_failed(self, message: str, needs_api_key: bool) -> None:
        self._set_results_busy(False)
        hint = " Check the API key in Menu → AI Integration → AI Settings." if needs_api_key else ""
        self._results_status.setText(f"The search couldn't run: {message}.{hint}")

    def _render_results(self) -> None:
        session = self._session
        self._set_results_busy(False)
        self._results_title.setText(session.title)
        count = len(session.results)
        status = f"{count} source{'s' if count != 1 else ''} for {talk_prep.describe_meeting(session.interview).lower()}."
        if session.note:
            status += f" {session.note}"
        if not session.results:
            status = "Nothing matched. Try Refine with a different direction, or include more sources."
        self._results_status.setText(status)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(10)

        keys = talk_prep.key_verses(self.conn, session.results)
        if keys:
            layout.addWidget(_heading("Key verses"))
            box = QLabel(
                "<br><br>".join(f"<b>{html.escape(ref)}</b> - “{html.escape(text)}”" for ref, text in keys)
            )
            box.setObjectName("talkPrepKeyVerses")
            box.setWordWrap(True)
            box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(box)

        for title, items in talk_prep.sections(self.conn, session.results):
            layout.addWidget(_heading(title))
            for result in items:
                layout.addWidget(self._result_widget(result))
        layout.addStretch(1)
        self._results_scroll.setWidget(content)

    def _result_widget(self, result: StudyResult) -> QWidget:
        frame = QFrame()
        frame.setObjectName("talkPrepResult")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        if result.url:
            title = QLabel(self._link(result.url, html.escape(result.title)))
            title.setOpenExternalLinks(True)
            title.setWordWrap(True)
            layout.addWidget(title)
            work = talk_prep.work_by_url(result.url)
            if work is not None and work.references:
                cites = ", ".join(work.references[:8]) + ("..." if len(work.references) > 8 else "")
                layout.addWidget(_hint(f"Cites: {cites}"))
            return frame

        target = None
        if result.chapter_id is not None:
            target = f"chapter:{result.chapter_id}"
        elif result.topic_id is not None:
            target = f"topic:{result.topic_id}"
        heading = html.escape(talk_prep.labeled_title(result))
        if target:
            heading = self._link(target, heading)
        title = QLabel(heading)
        title.setWordWrap(True)
        title.linkActivated.connect(self._on_link)
        layout.addWidget(title)

        body = QLabel(self._passage_html(result))
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body)
        return frame

    def _link(self, href: str, text: str) -> str:
        """Rich-text links take Qt's default link color (dark blue) unless
        told otherwise - unreadable on the dark theme - so they use the
        accent color, like the rest of the app's links."""
        color = self.palette().color(QPalette.ColorRole.Highlight).name()
        return f'<a href="{html.escape(href)}" style="color:{color}; font-weight:bold;">{text}</a>'

    def _passage_html(self, result: StudyResult) -> str:
        verses = talk_prep.passage_verses(self.conn, result)
        if not verses:
            return html.escape(result.detail)
        palette = self.palette()
        background = palette.color(QPalette.ColorRole.Highlight).name()
        foreground = palette.color(QPalette.ColorRole.HighlightedText).name()
        parts = []
        for number, text in verses:
            verse = f"<sup>{number}</sup>&nbsp;{html.escape(text)}"
            if number == result.key_verse and len(verses) > 1:
                verse = f'<span style="background-color:{background}; color:{foreground};"><b>{verse}</b></span>'
            parts.append(verse)
        return " ".join(parts)

    def _on_link(self, link: str) -> None:
        kind, _, value = link.partition(":")
        if kind == "chapter":
            self._open_chapter(int(value))
        elif kind == "topic":
            self._open_topic(int(value))

    # ------------------------------------------------------------------
    # Results actions
    # ------------------------------------------------------------------

    def _results_text(self) -> str:
        return talk_prep.as_text(self.conn, self._session)

    def _save_to_journal(self) -> None:
        talk_prep.append_to_journal(self.conn, self._results_text())
        self._results_status.setText("Saved to today's Journal entry.")

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._results_text())
        self._results_status.setText("Copied - paste it wherever you're writing.")

    def _export(self) -> None:
        name = "".join(c if c.isalnum() or c in " -_" else "" for c in self._session.title).strip() or "Talk Prep"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Talk Prep", str(Path.home() / f"Talk Prep - {name}.txt"), "Text files (*.txt)"
        )
        if not path:
            return
        try:
            Path(path).write_text(self._results_text() + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Export Talk Prep", f"Couldn't save the file: {exc}")
            return
        self._results_status.setText(f"Saved to {path}.")

    # ------------------------------------------------------------------
    # Saved sessions
    # ------------------------------------------------------------------

    def _fill_sessions(self) -> None:
        self._sessions_list.clear()
        for session in talk_prep.list_sessions(self.conn):
            when = session.updated_at
            try:
                stamp = datetime.fromisoformat(session.updated_at)
                when = f"{stamp:%b} {stamp.day}"
            except ValueError:
                pass
            item = QListWidgetItem(f"{session.title} - {talk_prep.describe_meeting(session.interview)} - {when}")
            item.setData(Qt.ItemDataRole.UserRole, session.uid)
            self._sessions_list.addItem(item)
        if self._sessions_list.count():
            self._sessions_list.setCurrentRow(0)

    def _selected_session(self) -> talk_prep.Session | None:
        item = self._sessions_list.currentItem()
        if item is None:
            return None
        uid = item.data(Qt.ItemDataRole.UserRole)
        return next((s for s in talk_prep.list_sessions(self.conn) if s.uid == uid), None)

    def _open_selected_session(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        self._session = session
        self._interview = session.interview
        self._themes = []
        self._load_interview_into_pages()
        self._show(self._results_page)
        self._render_results()

    def _delete_selected_session(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        answer = QMessageBox.question(self, "Talk Prep", f'Delete "{session.title}"?')
        if answer == QMessageBox.StandardButton.Yes:
            talk_prep.delete_session(self.conn, session.uid)
            self._fill_sessions()
            if not self._sessions_list.count():
                self._start_new()

    def _start_new(self) -> None:
        self._interview = talk_prep.Interview()
        self._session = None
        self._themes = []
        self._load_interview_into_pages()
        self._show(self._topic_page)

    def _load_interview_into_pages(self) -> None:
        interview = self._interview
        self._topic_edit.setText(interview.topic)
        self._meeting_combo.setCurrentText(interview.meeting)
        self._on_meeting_changed(interview.meeting)
        button = self._length_group.button(interview.length or _NOT_SURE)
        if button is not None:
            button.setChecked(True)
        lesson_number = next(
            (n for n, key in self._lesson_ids.items() if key == interview.lesson_source), len(_LESSON_CHOICES) - 1
        )
        self._lesson_group.button(lesson_number).setChecked(True)
        self._lesson_edit.setText(interview.lesson_text)
        self._lesson_edit.setVisible(interview.lesson_source != "none")
        self._lesson_status.hide()
        (self._talk_yes if interview.talk_url else self._talk_no).setChecked(True)
        self._talk_search.setText(interview.talk_title)
        if interview.talk_url and self._talk_list.count():
            self._talk_list.setCurrentRow(0)
        self._talk_passage.setPlainText(interview.talk_passage)
        self._impressions.setPlainText(interview.impressions)
        for key, row in self._source_rows.items():
            row.setChecked(key in interview.sources)

    def _on_build_index(self) -> None:
        self._build_index()
        self.close()
