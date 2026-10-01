"""Chapter reading view.

Displays verse number + text for every verse in a chapter, scrollable.
Reading color scheme, font family, and zoom are all applied here - the
app-theme (light/dark chrome) lives in theme.py's app-wide stylesheet
instead, since it applies to every screen, not just this one.

Each verse has a small pencil button; clicking it reveals (creating if
needed) that verse's note/tags entry in the "Study" tab of the tabbed
panel docked to the right, and focuses it there - that tab (ChapterPanel)
is the single editing surface for every note and tag in this chapter,
verse-level and chapter-level alike. "Citations" shows which of this
chapter's verses are cited in General Conference talks or Ensign/Liahona
articles (see scriptures/citations.py). "Cross-references" shows known
parallel passages elsewhere in the corpus - quotations, paraphrases, or
JST/Moses-style translation-revisions (see
scripts/build_cross_references.py) - each clickable straight through to
that other chapter. Selecting which tab is current is tracked by
MainWindow and threaded back in via selected_side_tab, so it survives
Previous/Next chapter navigation even though each navigation rebuilds
this whole view from scratch. The reading pane and this side panel sit
in a QSplitter rather than a fixed division, so the user can drag the
divider to give the side panel more (or less) room than its default
width - that width is tracked and threaded back in the same way, via
panel_width/panel_width_changed.

Highlighting is armed from the Highlighter menu (see main_window.py) rather
than anything on this screen. Each verse's body is a read-only QTextEdit
rather than a QLabel specifically so the user can drag-select an exact
word or phrase (via QTextCursor character offsets) instead of only ever
being able to mark a whole verse; releasing the drag while a color is
armed applies (or, in "clear" mode, removes) that color over just the
selected span, matching the "highlighter pen" metaphor - pick a color
once, then mark up several verses without re-opening the menu each time.
The drag itself isn't confined to one verse either - dragging past a
verse's own top or bottom continues the same selection into its
neighbors, applied (or cleared) across all of them together on release;
see _VerseTextEdit's own docstring for how a selection is made to span
sibling widgets Qt wouldn't otherwise let it cross. Right-clicking
directly on a highlighted word or phrase offers a quick "Remove
Highlight" instead, without needing to arm "Clear Highlight" and
re-drag over it.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QEvent, Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPixmap, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scriptures import tts
from scriptures.data_access import (
    Highlight,
    Verse,
    add_highlight,
    clear_highlight_range,
    get_annotated_verse_ids,
    get_chapter_location,
    get_highlights,
    get_note,
    get_tags,
)
from scriptures.ui.chapter_panel import PANEL_MIN_WIDTH, PANEL_WIDTH, ChapterPanel
from scriptures.ui.citations_panel import CitationsPanel
from scriptures.ui.cross_references_panel import CrossReferencesPanel
from scriptures.ui.word_study_panel import WordStudyPanel
from scriptures.ui.theme import HIGHLIGHT_COLORS, PANEL_RADIUS, ReadingPalette
from scriptures.ui.tts_playback import ReadableVerse, TtsController

VERSE_NUMBER_WIDTH = 32

_COLOR_ICON_CACHE: dict[str, QIcon] = {}


def _solid_color_icon(hex_color: str) -> QIcon:
    """A small solid-color square for a highlight color's own context-menu
    entry - the same swatch-not-just-a-name idea as the Highlighter menu's
    _HighlightColorRow, cached per color since every verse's context menu
    wants the identical three icons."""
    icon = _COLOR_ICON_CACHE.get(hex_color)
    if icon is None:
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(hex_color))
        icon = QIcon(pixmap)
        _COLOR_ICON_CACHE[hex_color] = icon
    return icon


class _VerseTextEdit(QTextEdit):
    """Read-only, frameless, auto-height display for one verse's body text.

    A QTextEdit rather than a QLabel so the text is natively drag-selectable
    down to the character - offsets reported here always match Python
    string indices straight into `verse.text`, since the document holds
    nothing but that plain text (no markup, no verse-number prefix).

    Qt's own text selection is confined to whichever single widget the
    drag started in - it doesn't extend into a sibling widget just
    because the cursor moves over one, and the moment the cursor leaves
    this widget's own bounds Qt stops delivering it mouseMoveEvent at
    all (there's no implicit "keep sending me events" the way, say, a
    slider's handle gets - only an explicit OS-level grabMouse() gives
    that, and it's deliberately NOT used here: if release ever failed to
    fire for any reason, a stuck grab can freeze mouse input for the
    whole application, not just this widget, which is a far worse
    failure than a highlight drag simply not spanning verses).

    So letting a highlight drag span several verses in one continuous
    gesture works the other way around: this widget only announces that
    a drag has begun (`drag_started`, from mousePressEvent) and otherwise
    stays out of it entirely - no mouseMoveEvent/mouseReleaseEvent
    overrides here at all. ReadingView, the only thing that ever needs
    to know about a drag crossing a verse boundary, installs its own
    temporary QApplication-wide event filter for the duration (see its
    own eventFilter and _on_verse_drag_started/_extended/_finished) -
    purely observational, never consuming or blocking an event, so a bug
    in it can misjudge a drag but can never lock up input the way a
    stuck grab could.
    """

    drag_started = Signal()
    highlight_remove_requested = Signal(int, int)
    highlight_color_requested = Signal(str)
    cross_reference_requested = Signal()
    word_lookup_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("verseBody")
        self.setReadOnly(True)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.document().setDocumentMargin(0)
        self.viewport().setAutoFillBackground(False)
        self._current_highlights: list[Highlight] = []

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        super().resizeEvent(event)
        self._adjust_height()

    def _adjust_height(self) -> None:
        # QTextEdit wraps to its width automatically but never shrinks or
        # grows its own height to match - without this it either clips
        # wrapped lines or leaves a scrollbar-worthy gap. contentsMargins()
        # (the style's default frame width, reserved around the viewport
        # even with NoFrame set) has to be added on top of the document's
        # own height, or the last wrapped line clips into the row below.
        self.document().setTextWidth(self.viewport().width())
        margins = self.contentsMargins()
        height = round(self.document().size().height()) + margins.top() + margins.bottom()
        height = max(1, height)
        if height != self.height():
            self.setFixedHeight(height)

    def render_text(
        self, text: str, font: QFont, normal_color: str, highlights: list[Highlight]
    ) -> None:
        """Fully (re)render from the given source of truth - always a
        complete overwrite, never an incremental patch, so this can't drift
        from what's actually in the database."""
        self.setFont(font)
        if self.toPlainText() != text:
            self.setPlainText(text)

        # setCharFormat() replaces the *whole* char format, not just the
        # properties given - any left unset (font family/size here) fall
        # back through Qt's own resolution order rather than reliably
        # inheriting the setFont() call above, and the whole-document
        # pass below and each highlighted span's own pass can resolve
        # that fallback differently, visibly changing the rendered font
        # size between highlighted and plain text. Setting the font
        # explicitly on every format applied here avoids depending on
        # that fallback at all.
        normal_format = QTextCharFormat()
        normal_format.setFont(font)
        normal_format.setForeground(QColor(normal_color))
        normal_format.clearBackground()
        whole_doc = QTextCursor(self.document())
        whole_doc.select(QTextCursor.SelectionType.Document)
        whole_doc.setCharFormat(normal_format)

        for hl in highlights:
            colors = HIGHLIGHT_COLORS[hl.color]
            fmt = QTextCharFormat()
            fmt.setFont(font)
            fmt.setForeground(QColor(colors.text))
            fmt.setBackground(QColor(colors.background))
            span = QTextCursor(self.document())
            span.setPosition(hl.start_offset)
            span.setPosition(hl.end_offset, QTextCursor.MoveMode.KeepAnchor)
            span.setCharFormat(fmt)

        self._current_highlights = highlights
        self._adjust_height()

    def clear_selection(self) -> None:
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)

    def set_now_reading(self, active: bool) -> None:
        """Toggles the "currently being read aloud" border - a dynamic
        property + QSS rule (see theme.py's #verseBody[nowReading="true"]),
        same re-polish pattern as ReadingView._refresh_verse_indicator's
        annotate button. Deliberately separate from the user's own
        highlight colors (applied as char-format spans in render_text,
        not a widget-level style) so the two never conflict."""
        self.setProperty("nowReading", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_started.emit()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        # Left deliberately unhandled while dragging: ReadingView's
        # QApplication-wide event filter is the sole owner of selection
        # updates during a drag (it's the only thing that can see the
        # cursor once it crosses into a sibling verse). Letting Qt's own
        # default handling run here too would fight it for control of
        # this same widget's selection on every single move event -
        # each one setting a slightly different range - which is exactly
        # what produced the jitter and the occasional "selection ends up
        # empty at release" failure. Only forward hover-only moves (no
        # button held) so things like the I-beam cursor still update.
        if event.buttons() & Qt.MouseButton.LeftButton:
            return
        super().mouseMoveEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        offset = self.cursorForPosition(event.pos()).position()
        hit = next(
            (h for h in self._current_highlights if h.start_offset <= offset < h.end_offset), None
        )
        has_selection = self.textCursor().hasSelection()

        menu = self.createStandardContextMenu()
        standard_actions = menu.actions()
        first_standard = standard_actions[0] if standard_actions else None

        # Built in the order they should appear, then inserted as one
        # block ahead of Copy/Select All - "act on what's already
        # highlighted here" before "highlight what I just selected."
        new_actions: list[QAction] = []
        if hit is not None:
            remove_action = QAction("Remove Highlight", self)
            remove_action.triggered.connect(
                lambda checked=False, s=hit.start_offset, e=hit.end_offset: (
                    self.highlight_remove_requested.emit(s, e)
                )
            )
            new_actions.append(remove_action)
        if has_selection:
            for color in ("yellow", "pink", "orange"):
                color_action = QAction(f"Highlight {color.capitalize()}", self)
                color_action.setIcon(_solid_color_icon(HIGHLIGHT_COLORS[color].background))
                color_action.triggered.connect(
                    lambda checked=False, c=color: self.highlight_color_requested.emit(c)
                )
                new_actions.append(color_action)
        cross_reference_action = QAction("Add Cross-reference…", self)
        cross_reference_action.triggered.connect(self.cross_reference_requested)
        new_actions.append(cross_reference_action)
        # The selection if there is one (a word or short phrase), otherwise
        # the word that was right-clicked.
        if has_selection:
            word = self.textCursor().selectedText().strip()
        else:
            word_cursor = self.cursorForPosition(event.pos())
            word_cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            word = word_cursor.selectedText().strip()
        word = word.strip(".,;:!?()[]'\"")
        if word and len(word.split()) <= 3:
            lookup_action = QAction(f"Look Up Original Word: {word}", self)
            lookup_action.triggered.connect(lambda checked=False, w=word: self.word_lookup_requested.emit(w))
            new_actions.append(lookup_action)

        if new_actions:
            if first_standard is not None:
                for action in new_actions:
                    menu.insertAction(first_standard, action)
                menu.insertSeparator(first_standard)
            else:
                menu.addActions(new_actions)

        menu.exec(event.globalPos())


def _original_language(conn: sqlite3.Connection, chapter_id: int) -> str | None:
    """Which original language's words Word Study lists first for this
    chapter: Greek in the New Testament, Hebrew in the Old (the JST shares
    the Bible's testaments). Other volumes get no preference - the Book of
    Mormon quotes both Isaiah and the Sermon on the Mount."""
    location = get_chapter_location(conn, chapter_id)
    testament = location[1] if location else None
    if testament is None:
        return None
    return "greek" if testament.name == "New Testament" else "hebrew"


class ReadingView(QWidget):
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    prev_requested = Signal()
    next_requested = Signal()
    side_tab_changed = Signal(int)
    chapter_link_activated = Signal(int)
    topic_link_activated = Signal(int)
    panel_width_changed = Signal(int)

    def __init__(
        self,
        conn: sqlite3.Connection,
        chapter_id: int,
        title: str,
        verses: list[Verse],
        palette: ReadingPalette,
        font_family: str,
        font_size: int,
        *,
        panel_width: int | None = None,
        has_previous: bool = False,
        has_next: bool = False,
        armed_highlight: str | None = None,
        selected_side_tab: int = 0,
        subtitle: str | None = None,
        tts_voice: str = tts.DEFAULT_VOICE_KEY,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.conn = conn
        self.chapter_id = chapter_id
        self._title = title
        self._verses = verses
        self._verse_highlights = get_highlights(conn, chapter_id)
        self._armed_highlight = armed_highlight
        self._tts_voice = tts_voice
        self._tts: TtsController | None = None  # created lazily - see _ensure_tts()
        self._now_reading_verse_id: int | None = None

        outer = QHBoxLayout(self)

        reading_column = QVBoxLayout()

        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(title_label, stretch=1)

        self._listen_btn = QPushButton("▶ Listen")
        self._listen_btn.setObjectName("listenButton")
        self._listen_btn.setToolTip("Read this chapter aloud")
        self._listen_btn.clicked.connect(self._on_listen_clicked)
        header.addWidget(self._listen_btn)

        self._stop_listen_btn = QPushButton("⏹")
        self._stop_listen_btn.setObjectName("stopListenButton")
        self._stop_listen_btn.setToolTip("Stop reading aloud")
        self._stop_listen_btn.setVisible(False)
        self._stop_listen_btn.clicked.connect(self._on_stop_listen_clicked)
        header.addWidget(self._stop_listen_btn)

        zoom_out_btn = QPushButton("A-")
        zoom_out_btn.setObjectName("zoomButton")
        zoom_out_btn.setToolTip("Smaller text (Ctrl+-)")
        zoom_out_btn.clicked.connect(self.zoom_out_requested)
        header.addWidget(zoom_out_btn)

        zoom_in_btn = QPushButton("A+")
        zoom_in_btn.setObjectName("zoomButton")
        zoom_in_btn.setToolTip("Larger text (Ctrl+=)")
        zoom_in_btn.clicked.connect(self.zoom_in_requested)
        header.addWidget(zoom_in_btn)

        reading_column.addLayout(header)

        # Only Journal of Discourses chapters pass a subtitle - who gave
        # it and when matters for a sermon in a way it doesn't for
        # scripture, where the title (e.g. "Genesis 1") is self-contained.
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("readingSubtitle")
            subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            subtitle_label.setWordWrap(True)
            reading_column.addWidget(subtitle_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.viewport().setObjectName("readingViewport")
        self._content = QWidget()
        self._content.setObjectName("readingCard")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 18, 20, 18)
        self._content_layout.setSpacing(10)

        annotated_ids = get_annotated_verse_ids(conn, chapter_id)
        # A chapter with exactly one verse - every Journal of Discourses
        # discourse, imported as one continuous page of prose rather than
        # numbered statements - has nothing for a verse number to
        # disambiguate, so it's left off entirely instead of showing a
        # lone, meaningless "1" next to a whole page of text.
        show_numbers = len(verses) > 1
        self._number_labels: dict[int, QLabel] = {}
        self._body_widgets: dict[int, _VerseTextEdit] = {}
        self._annotate_buttons: dict[int, QPushButton] = {}
        self._verse_index: dict[int, int] = {v.id: i for i, v in enumerate(verses)}
        # Set only while a highlight drag is in progress - see
        # _on_verse_drag_started/eventFilter below.
        self._drag_anchor_verse: Verse | None = None
        self._drag_anchor_offset: int = 0
        for verse in verses:
            row = QHBoxLayout()
            row.setSpacing(10)

            annotate_btn = QPushButton("✎")
            annotate_btn.setObjectName("annotateButton")
            annotate_btn.setFixedSize(28, 28)
            annotate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            annotate_btn.setToolTip("Open this verse's note/tags in the side panel")
            annotate_btn.setProperty("annotated", verse.id in annotated_ids)
            annotate_btn.clicked.connect(lambda checked=False, v=verse: self._open_verse_note(v))
            row.addWidget(annotate_btn, 0, Qt.AlignmentFlag.AlignTop)
            self._annotate_buttons[verse.id] = annotate_btn

            if show_numbers:
                number_label = QLabel(str(verse.verse_number))
                number_label.setFixedWidth(VERSE_NUMBER_WIDTH)
                number_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
                row.addWidget(number_label, 0)
                self._number_labels[verse.id] = number_label

            body = _VerseTextEdit()
            body.drag_started.connect(lambda v=verse: self._on_verse_drag_started(v))
            body.highlight_remove_requested.connect(
                lambda start, end, v=verse: self._on_highlight_remove_requested(v, start, end)
            )
            body.highlight_color_requested.connect(self._on_verse_highlight_color_requested)
            body.cross_reference_requested.connect(
                lambda v=verse: self._on_cross_reference_requested(v)
            )
            body.word_lookup_requested.connect(self._on_word_lookup_requested)
            row.addWidget(body, 1)
            self._body_widgets[verse.id] = body

            self._content_layout.addLayout(row)

        self._content_layout.addStretch()
        self._scroll.setWidget(self._content)
        reading_column.addWidget(self._scroll)

        nav_row = QHBoxLayout()
        self._prev_btn = QPushButton("← Previous")
        self._prev_btn.setObjectName("navButton")
        self._prev_btn.setEnabled(has_previous)
        self._prev_btn.clicked.connect(self.prev_requested)
        nav_row.addWidget(self._prev_btn)

        nav_row.addStretch(1)

        self._next_btn = QPushButton("Next →")
        self._next_btn.setObjectName("navButton")
        self._next_btn.setEnabled(has_next)
        self._next_btn.clicked.connect(self.next_requested)
        nav_row.addWidget(self._next_btn)

        reading_column.addLayout(nav_row)

        reading_container = QWidget()
        reading_container.setLayout(reading_column)
        reading_container.setMinimumWidth(400)

        self._panel = ChapterPanel(conn, chapter_id, verses, annotated_ids)
        self._panel.verse_annotation_changed.connect(self._refresh_verse_indicator)

        self._side_tabs = QTabWidget()
        self._side_tabs.setMinimumWidth(PANEL_MIN_WIDTH)
        self._side_tabs.addTab(self._panel, "Study")

        citations_panel = CitationsPanel(verses)
        self._side_tabs.addTab(citations_panel, self._citations_tab_label(citations_panel))

        self._cross_references_panel = CrossReferencesPanel(conn, chapter_id, title)
        self._cross_references_panel.chapter_selected.connect(self.chapter_link_activated)
        self._cross_references_panel.topic_selected.connect(self.topic_link_activated)
        self._cross_references_panel.references_changed.connect(
            self._refresh_cross_references_tab_label
        )
        self._side_tabs.addTab(
            self._cross_references_panel,
            self._cross_references_tab_label(self._cross_references_panel),
        )

        self._word_study_panel = WordStudyPanel(conn, _original_language(conn, chapter_id))
        self._side_tabs.addTab(self._word_study_panel, "Word Study")
        self._side_tabs.setTabToolTip(
            self._side_tabs.indexOf(self._cross_references_panel),
            "Cross-references: passages elsewhere that quote, parallel, or connect to this chapter",
        )
        self._side_tabs.setTabToolTip(
            self._side_tabs.indexOf(self._word_study_panel),
            "Word Study: the Hebrew or Aramaic words behind the English",
        )

        self._side_tabs.setCurrentIndex(selected_side_tab)
        self._side_tabs.currentChanged.connect(self.side_tab_changed)

        # A QSplitter rather than a plain stretch-factor split so the user
        # can drag the divider themselves - Study/Citations/Cross-references
        # habitually want more room than the reading pane's own default
        # share leaves them. Neither side is collapsible: dragging past
        # each one's minimum width just stops there instead of hiding it
        # entirely, which would strand the user with no way to get it back
        # short of reopening the chapter.
        self._panel_width = panel_width if panel_width is not None else PANEL_WIDTH
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(reading_container)
        self._splitter.addWidget(self._side_tabs)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        outer.addWidget(self._splitter)

        self.apply_theme(palette, font_family, font_size)

        # At construction time this view isn't parented into the window yet,
        # so the verse text edits compute their wrapped height against a
        # provisional width - clipping the last wrapped line until something
        # (e.g. zooming) forces a relayout. Re-validating once on the next
        # event loop turn, after the real width is known, fixes it up front.
        #
        # For the verse text edits specifically, one activate() isn't
        # enough on its own: each has a fixed height (see
        # _VerseTextEdit._adjust_height), so correcting row N's height
        # shifts row N+1's position, which Qt only resolves reactively
        # through that row's own next resizeEvent - a cascade that can take
        # several event-loop turns to fully settle in a long chapter,
        # visibly "jumping" during it. Recomputing every row's height in
        # one explicit pass, all against the now-final width, avoids the
        # cascade instead of waiting it out.
        QTimer.singleShot(0, self._finalize_verse_layout)

        # Same reasoning as above: this view has no real width yet at
        # construction time, so setSizes() here would split against a
        # provisional one. Fixing it up next turn instead gives the side
        # panel its actual requested width and hands the reading pane
        # whatever's left, rather than an even 50/50 split.
        QTimer.singleShot(0, self._finalize_splitter_sizes)

    def _finalize_splitter_sizes(self) -> None:
        total_width = self._splitter.width()
        self._splitter.setSizes([max(total_width - self._panel_width, 0), self._panel_width])

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        self._panel_width = self._splitter.sizes()[1]
        self.panel_width_changed.emit(self._panel_width)

    def _finalize_verse_layout(self) -> None:
        self._content_layout.activate()
        for body in self._body_widgets.values():
            body._adjust_height()
        # setFixedHeight() above invalidates the layout but only *schedules*
        # repositioning sibling rows for the next event-loop pass - without
        # forcing it here too, every row after the first would still
        # visibly jump into place a frame later instead of appearing right.
        self._content_layout.activate()

    def apply_theme(self, palette: ReadingPalette, font_family: str, font_size: int) -> None:
        self._palette = palette
        self._font = QFont(font_family, font_size)
        for verse in self._verses:
            self._render_verse(verse)

        self._content.setStyleSheet(
            f"QWidget#readingCard {{ "
            f"background-color: {palette.background}; "
            f"border: 1px solid {palette.title_border}; "
            f"border-radius: {PANEL_RADIUS}px; "
            f"}}"
        )

    def _render_verse(self, verse: Verse) -> None:
        number_label = self._number_labels.get(verse.id)
        if number_label is not None:
            number_label.setFont(self._font)
            number_label.setStyleSheet(
                f"color: {self._palette.verse_number}; font-weight: bold; background: transparent;"
            )

        body = self._body_widgets[verse.id]
        body.render_text(
            verse.text, self._font, self._palette.text, self._verse_highlights.get(verse.id, [])
        )

    def _open_verse_note(self, verse: Verse) -> None:
        self._panel.focus_verse(verse)

    @staticmethod
    def _citations_tab_label(citations_panel: CitationsPanel) -> str:
        count = citations_panel.cited_verse_count
        return f"Citations ({count})" if count else "Citations"

    @staticmethod
    def _cross_references_tab_label(cross_references_panel: CrossReferencesPanel) -> str:
        # "Cross-refs" rather than "Cross-references" - with Word Study
        # added, four full labels didn't fit the panel's default width
        # (the tab's tooltip spells it out).
        count = cross_references_panel.reference_count
        return f"Cross-refs ({count})" if count else "Cross-refs"

    def _refresh_cross_references_tab_label(self) -> None:
        index = self._side_tabs.indexOf(self._cross_references_panel)
        self._side_tabs.setTabText(
            index, self._cross_references_tab_label(self._cross_references_panel)
        )

    def _on_word_lookup_requested(self, word: str) -> None:
        self._side_tabs.setCurrentWidget(self._word_study_panel)
        self._word_study_panel.look_up(word)

    def _on_cross_reference_requested(self, verse: Verse) -> None:
        """A verse's own right-click "Add Cross-reference..." - pre-fills
        the dialog with whichever verses currently have a selection (a
        multi-verse drag can leave several), or just the verse that was
        right-clicked if none do."""
        selected = [
            v.verse_number for v in self._verses if self._body_widgets[v.id].textCursor().hasSelection()
        ]
        if not selected:
            selected = [verse.verse_number]
        self._side_tabs.setCurrentWidget(self._cross_references_panel)
        self._cross_references_panel.open_add_dialog(min(selected), max(selected))

    def _on_verse_drag_started(self, verse: Verse) -> None:
        """A verse widget's own mousePressEvent, left button - the one
        and only thing it tells ReadingView about a drag; everything
        past this point (does it cross into another verse? has the
        button been released yet?) is watched for centrally instead, via
        a temporary application-wide event filter - see eventFilter and
        its own docstring for why nothing here uses grabMouse().

        Only installs that filter if one isn't already active: if a
        previous drag's release was ever somehow missed (leaving
        _drag_anchor_verse still set), this just points the existing
        filter at the new anchor instead of installing a second one -
        self-healing the moment any new drag starts, rather than
        accumulating duplicate filters."""
        if self._drag_anchor_verse is None:
            QApplication.instance().installEventFilter(self)
        self._drag_anchor_verse = verse
        self._drag_anchor_offset = self._body_widgets[verse.id].textCursor().position()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt naming convention)
        if self._drag_anchor_verse is None:
            return super().eventFilter(obj, event)
        event_type = event.type()
        if event_type == QEvent.Type.MouseMove:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self._on_verse_drag_extended(event.globalPosition().toPoint())
        elif event_type == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self._on_verse_drag_finished()
                QApplication.instance().removeEventFilter(self)
                self._drag_anchor_verse = None
        # Never consumes anything (always defers to the base
        # implementation's own answer, normally False) - this is a purely
        # observational tap on the event stream, not an interception, so
        # every other widget in the app keeps receiving these events
        # completely normally throughout the drag.
        return super().eventFilter(obj, event)

    def _on_verse_drag_extended(self, global_pos: QPoint) -> None:
        """Fires on every mouse-move anywhere in the app for as long as a
        drag begun in _drag_anchor_verse's own widget is in progress,
        however far the cursor has since wandered from it. With no
        highlighter armed this is a no-op - dragging is just ordinary
        text selection (e.g. to copy it) confined to whichever single
        verse Qt's own selection already handles.

        With a color (or "clear") armed, extends a fake selection across
        every verse between the drag's start and wherever the cursor is
        now, using the exact same setTextCursor mechanism a plain
        same-widget drag already uses natively - the verses outside that
        range get their own selection cleared, so narrowing the drag back
        un-highlights-preview verses it had covered a moment ago."""
        if self._armed_highlight is None:
            return
        anchor_verse = self._drag_anchor_verse
        anchor_offset = self._drag_anchor_offset

        target_verse, target_offset = self._verse_and_offset_at_global(global_pos)
        if target_verse is None:
            return
        anchor_index = self._verse_index[anchor_verse.id]
        target_index = self._verse_index[target_verse.id]
        lo_index, hi_index = sorted((anchor_index, target_index))
        forward = anchor_index <= target_index

        for index, verse in enumerate(self._verses):
            widget = self._body_widgets[verse.id]
            if index < lo_index or index > hi_index:
                widget.clear_selection()
                continue
            text_len = len(verse.text)
            if forward:
                start = anchor_offset if index == anchor_index else 0
                end = target_offset if index == target_index else text_len
            else:
                start = target_offset if index == target_index else 0
                end = anchor_offset if index == anchor_index else text_len
            cursor = widget.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            widget.setTextCursor(cursor)

    def _verse_and_offset_at_global(self, global_pos: QPoint) -> tuple[Verse | None, int]:
        """Which verse (and character offset into its text) a global mouse
        position falls over, hit-testing by each row's own vertical span
        in self._content's coordinate space rather than requiring the
        point to land exactly inside that verse's own _VerseTextEdit -
        the point may be a little to the side of it (over the verse
        number, say) while still vertically within that row. A point
        above the first verse or below the last one clamps to that verse's
        own start/end, so dragging past either end of the list still
        extends the selection instead of doing nothing."""
        if not self._verses:
            return None, 0
        content_pos = self._content.mapFromGlobal(global_pos)
        first_widget = self._body_widgets[self._verses[0].id]
        if content_pos.y() < first_widget.mapTo(self._content, QPoint(0, 0)).y():
            return self._verses[0], 0
        for verse in self._verses:
            widget = self._body_widgets[verse.id]
            top = widget.mapTo(self._content, QPoint(0, 0)).y()
            if top <= content_pos.y() <= top + widget.height():
                local = widget.mapFromGlobal(global_pos)
                offset = widget.cursorForPosition(local).position()
                return verse, max(0, min(offset, len(verse.text)))
        last_verse = self._verses[-1]
        return last_verse, len(last_verse.text)

    def _on_verse_drag_finished(self) -> None:
        # With no highlighter armed, a plain drag is just ordinary text
        # selection (e.g. to copy it) - deliberately left in place rather
        # than applied or cleared, which also means it's left in place
        # for the user to right-click within a moment later and choose a
        # color from there instead (see _on_verse_highlight_color_requested).
        if self._armed_highlight is None:
            return
        self._apply_to_current_selection(self._armed_highlight)

    def _on_verse_highlight_color_requested(self, color: str) -> None:
        """The right-click context menu's own color choice - independent
        of whatever's armed in the Highlighter menu, applied to whatever
        verse(s) are currently selected (however that selection was made:
        a drag with nothing armed, left in place for exactly this)."""
        self._apply_to_current_selection(color)

    def _apply_to_current_selection(self, mode: str) -> None:
        """mode is a highlight color, or "clear" - applied across every
        verse that currently has a selection (a multi-verse drag can leave
        more than one), then clears each of their selections and
        re-renders. Shared by the drag-release handler above (using
        whatever's armed in the Highlighter menu) and the context menu's
        own direct color/remove choices."""
        changed_verses = []
        for verse in self._verses:
            widget = self._body_widgets[verse.id]
            cursor = widget.textCursor()
            if not cursor.hasSelection():
                continue
            start, end = cursor.selectionStart(), cursor.selectionEnd()
            if mode == "clear":
                clear_highlight_range(self.conn, verse.id, start, end)
            else:
                add_highlight(self.conn, verse.id, mode, start, end)
            changed_verses.append(verse)
            widget.clear_selection()
        if not changed_verses:
            return
        self._verse_highlights = get_highlights(self.conn, self.chapter_id)
        for verse in changed_verses:
            self._render_verse(verse)

    def _on_highlight_remove_requested(self, verse: Verse, start: int, end: int) -> None:
        """A verse's own right-click "Remove Highlight" - independent of
        whatever's currently armed in the Highlighter menu, since removing
        one specific highlight the user just clicked on shouldn't require
        arming "Clear Highlight" and re-dragging over it first."""
        clear_highlight_range(self.conn, verse.id, start, end)
        self._verse_highlights = get_highlights(self.conn, self.chapter_id)
        self._render_verse(verse)

    def set_armed_highlight(self, color: str | None) -> None:
        """Called by MainWindow when the Highlighter menu selection
        changes, so an already-open chapter picks up the new tool without
        needing to be reopened."""
        self._armed_highlight = color

    def set_tts_voice(self, key: str) -> None:
        """Called by MainWindow when the View -> Voice selection changes,
        same reasoning as set_armed_highlight - only affects the *next*
        time Listen is clicked, not anything already playing."""
        self._tts_voice = key

    def _refresh_verse_indicator(self, verse_id: int) -> None:
        btn = self._annotate_buttons.get(verse_id)
        if btn is None:
            return
        annotated = get_note(self.conn, verse_id=verse_id) is not None or bool(
            get_tags(self.conn, verse_id=verse_id)
        )
        btn.setProperty("annotated", annotated)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def flush_pending_save(self) -> None:
        """Forwarded to the chapter panel - see ChapterPanel.flush_pending_save."""
        self._panel.flush_pending_save()

    # ------------------------------------------------------------------
    # Listen (text-to-speech) - see tts.py and ui/tts_playback.py for the
    # synthesis/playback machinery this drives.
    # ------------------------------------------------------------------

    def _ensure_tts(self) -> TtsController:
        if self._tts is None:
            self._tts = TtsController(self)
            self._tts.verse_started.connect(self._on_tts_verse_started)
            self._tts.playback_stopped.connect(self._on_tts_playback_stopped)
            self._tts.synthesis_failed.connect(self._on_tts_synthesis_failed)
        return self._tts

    def _on_listen_clicked(self) -> None:
        if self._tts is not None and self._tts.is_active():
            if self._tts.is_paused():
                self._tts.resume()
                self._listen_btn.setText("⏸ Pause")
            else:
                self._tts.pause()
                self._listen_btn.setText("▶ Resume")
            return

        if not tts.is_voice_installed(self._tts_voice):
            QMessageBox.warning(
                self,
                "Listen",
                "This voice isn't installed. Pick a different one under "
                "View → Voice, or reinstall the app.",
            )
            return

        controller = self._ensure_tts()
        readable = [ReadableVerse(v.id, v.text) for v in self._verses]
        controller.start(self._tts_voice, readable)
        self._listen_btn.setText("⏸ Pause")
        self._stop_listen_btn.setVisible(True)

    def _on_stop_listen_clicked(self) -> None:
        if self._tts is not None:
            self._tts.stop()
        self._reset_listen_controls()

    def _on_tts_verse_started(self, verse_id: int) -> None:
        if self._now_reading_verse_id is not None:
            old = self._body_widgets.get(self._now_reading_verse_id)
            if old is not None:
                old.set_now_reading(False)
        self._now_reading_verse_id = verse_id
        body = self._body_widgets.get(verse_id)
        if body is not None:
            body.set_now_reading(True)
            self._scroll.ensureWidgetVisible(body)

    def _on_tts_playback_stopped(self) -> None:
        self._reset_listen_controls()

    def _on_tts_synthesis_failed(self, message: str) -> None:  # noqa: ARG002
        # Quiet failure with a reset back to idle, same policy as every
        # other opt-in fetch/feature in this app - message kept for
        # debugging via a future log, not surfaced as an error dialog for
        # what's most likely a one-off synthesis hiccup.
        self._reset_listen_controls()

    def _reset_listen_controls(self) -> None:
        self._listen_btn.setText("▶ Listen")
        self._stop_listen_btn.setVisible(False)
        if self._now_reading_verse_id is not None:
            old = self._body_widgets.get(self._now_reading_verse_id)
            if old is not None:
                old.set_now_reading(False)
            self._now_reading_verse_id = None

    def shutdown_tts(self) -> None:
        """Called by MainWindow right before this view is discarded (see
        its flush_pending_save() call site) - stops playback and shuts
        down the background synthesis thread for good, not just the
        current playback (see TtsController.shutdown)."""
        if self._tts is not None:
            self._tts.shutdown()
