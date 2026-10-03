"""AI Integration → "AI Setup Wizard..." - a guided alternative to filling
in AI Settings by hand (see ai_settings_dialog.py, which still holds the
same values afterward for fine-tuning).

Four pages:

1. Welcome - what the two kinds of AI model are for (chat answers
   questions; an embedding model builds the study index), privacy, and a
   link to the wiki's "Choosing an AI Setup" guide.
2. Chat - pick a server found running on this computer (see
   ai_setup.LocalServerScan), OpenAI, or any other address; pick a model
   from that server's own list; test it.
3. Study index - same for embeddings (or "same as chat", or skip), with
   the exact `ollama pull` command to run if Ollama has no embedding
   model yet.
4. Finish - a summary, and an option to start building the study index
   right away.

Choices are styled checkable buttons ("choice cards") rather than radio
buttons, for the same reason toggle_row.py exists: a native radio
indicator can be nearly invisible on some desktop themes.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from scriptures import ai_setup
from scriptures.ai_client import AiConfig, ConnectionTester
from scriptures.ai_setup import FoundServer, LocalServerScan, ModelLister
from scriptures.embeddings import EmbeddingRequest
from scriptures.ui.toggle_row import ToggleRow

# Choice keys besides a found server's base URL.
_OPENAI = "openai"
_OTHER = "other"
_SAME_AS_CHAT = "same"
_SKIP = "skip"


def _label(text: str, *, secondary: bool = False, rich: bool = False) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    if secondary:
        label.setObjectName("resultSecondary")
    if rich:
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
    return label


def guide_link_html(text: str = "Choosing an AI Setup (wiki)") -> str:
    return f'<a href="{ai_setup.AI_SETUP_GUIDE_URL}">{text}</a>'


class _ChoiceCards(QWidget):
    """A vertical, exclusive set of checkable cards, each with a key."""

    changed = Signal()
    # Only for a card the user clicked, not one selected programmatically.
    picked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._keys: dict[QPushButton, str] = {}
        # buttonToggled fires for the card turning off as well as the one
        # turning on - only the latter is a change of choice.
        self._group.buttonToggled.connect(
            lambda _button, checked: self.changed.emit() if checked else None
        )
        self._group.buttonClicked.connect(lambda _button: self.picked.emit())

    def clear(self) -> None:
        for button in list(self._keys):
            self._group.removeButton(button)
            # Out of the layout now - deleteLater() alone leaves it there
            # until the event loop runs, stacking old cards with new ones.
            self._layout.removeWidget(button)
            button.hide()
            button.deleteLater()
        self._keys.clear()

    def add(self, key: str, title: str, detail: str) -> None:
        button = QPushButton(f"{title}\n{detail}" if detail else title)
        button.setObjectName("choiceCard")
        button.setCheckable(True)
        button.setAutoDefault(False)
        # Never squashed below its two lines of text - the page scrolls
        # instead (see _ServerPage).
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._group.addButton(button)
        self._layout.addWidget(button)
        self._keys[button] = key

    def select(self, key: str) -> None:
        for button, button_key in self._keys.items():
            if button_key == key:
                button.setChecked(True)
                return

    def selected(self) -> str | None:
        button = self._group.checkedButton()
        return self._keys.get(button) if button else None

    def keys(self) -> list[str]:
        return list(self._keys.values())


class _WelcomePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Set up AI features")
        layout = QVBoxLayout(self)
        layout.addWidget(_label(
            "Desktop Scriptures' AI features use an AI service <b>you</b> choose - "
            "OpenAI, or a model running on this computer (Ollama, an Ubuntu inference "
            "snap, LM Studio, and so on). Nothing is sent anywhere until you finish "
            "this wizard.", rich=True,
        ))
        layout.addWidget(_label(
            "<b>Two kinds of model are involved:</b><ul>"
            "<li><b>A chat model</b> answers questions in AI-assisted search (and, "
            "later, the talk-prep helper).</li>"
            "<li><b>An embedding model</b> (optional) builds the <i>study index</i>, "
            "which lets AI features find passages by meaning. Chat models usually "
            "can't do this, so it may come from a different place.</li></ul>",
            rich=True,
        ))
        layout.addWidget(_label(
            "Every answer still points to real passages in this app's own text - a "
            "model's own words are never shown as scripture.", secondary=True,
        ))
        layout.addWidget(_label(
            f"Not sure what to choose? See {guide_link_html()} for setups that work "
            "well, including on computers without a powerful graphics card.",
            rich=True,
        ))
        layout.addStretch(1)


class _ServerPage(QWizardPage):
    """Shared shape of the Chat and Study index pages: choice cards for
    where to connect, then address/key/model fields and a Test button."""

    embeddings = False

    def __init__(self, wizard: "AiSetupWizard"):
        super().__init__()
        self._wizard = wizard
        self._lister: ModelLister | None = None
        self._test = None

        # Up to six cards plus the form can be taller than the wizard on
        # a small screen - scroll rather than squash.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        self._intro = _label("", rich=True)
        layout.addWidget(self._intro)

        self._cards = _ChoiceCards()
        self._cards.changed.connect(self._on_choice_changed)
        # Until the user clicks a card, the selection is just this page's
        # suggestion and is re-suggested when a scan finishes.
        self._user_chose = False
        self._cards.picked.connect(lambda: setattr(self, "_user_chose", True))
        layout.addWidget(self._cards)

        rescan_row = QHBoxLayout()
        self._scan_status = _label("", secondary=True)
        rescan_row.addWidget(self._scan_status, 1)
        rescan = QPushButton("Look Again")
        rescan.setToolTip("Check this computer for running AI servers again")
        rescan.setAutoDefault(False)
        rescan.clicked.connect(self._wizard.rescan)
        rescan_row.addWidget(rescan)
        layout.addLayout(rescan_row)

        self._form_container = QWidget()
        form = QFormLayout(self._form_container)
        form.setContentsMargins(0, 4, 0, 0)
        self._url = QLineEdit()
        self._url.setPlaceholderText("e.g. http://localhost:11434/v1")
        self._url.textChanged.connect(self.completeChanged)
        form.addRow("Address:", self._url)
        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("Only if the service needs one (hosted providers do)")
        form.addRow("API key:", self._key)
        model_row = QHBoxLayout()
        self._model = QComboBox()
        self._model.setEditable(True)
        self._model.setMinimumWidth(240)
        self._model.currentTextChanged.connect(self.completeChanged)
        model_row.addWidget(self._model, 1)
        refresh = QPushButton("Refresh")
        refresh.setToolTip("Ask this address for its list of models again")
        refresh.setAutoDefault(False)
        refresh.clicked.connect(self._list_models)
        model_row.addWidget(refresh)
        form.addRow("Model:", model_row)
        self._dimensions = QLineEdit()
        self._dimensions.setPlaceholderText("Optional - e.g. 512 with OpenAI (smaller index)")
        if self.embeddings:
            form.addRow("Dimensions:", self._dimensions)
        layout.addWidget(self._form_container)

        self._hint = _label("", rich=True)
        self._hint.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        layout.addWidget(self._hint)

        test_row = QHBoxLayout()
        test_button = QPushButton("Test")
        test_button.setAutoDefault(False)
        test_button.clicked.connect(self._run_test)
        test_row.addWidget(test_button)
        self._test_status = _label("", secondary=True)
        test_row.addWidget(self._test_status, 1)
        self._test_row = QWidget()
        self._test_row.setLayout(test_row)
        layout.addWidget(self._test_row)
        layout.addStretch(1)

    # --- choices -------------------------------------------------------

    def populate(self, found: list[FoundServer], scanning: bool) -> None:
        previous = self._cards.selected()
        # Re-selecting the same card below re-fills the fields from it -
        # keep whatever the user had typed or picked there instead.
        kept = (self._url.text(), self._key.text(), self._model.currentText(), self._dimensions.text())
        self._cards.clear()
        self._add_leading_choices()
        for server in found:
            models = server.embedding_models if self.embeddings else server.chat_models
            if models:
                shown = ", ".join(models[:3]) + (f" and {len(models) - 3} more" if len(models) > 3 else "")
                detail = f"{server.base_url} - {shown}"
            elif self.embeddings and server.is_ollama:
                detail = f"{server.base_url} - no embedding model yet (the next step shows how to add one)"
            else:
                detail = f"{server.base_url} - running, but no {'embedding' if self.embeddings else 'chat'} models listed"
            self._cards.add(server.base_url, f"{server.name} on this computer", detail)
        self._cards.add(_OPENAI, "OpenAI", "Hosted - needs an API key from platform.openai.com; usage is billed by OpenAI")
        self._cards.add(_OTHER, "Somewhere else", "Any other OpenAI-compatible address")
        self._add_trailing_choices()
        if scanning:
            self._scan_status.setText("Looking for AI servers on this computer...")
        elif found:
            self._scan_status.setText(f"Found {len(found)} running on this computer.")
        else:
            self._scan_status.setText(
                "Nothing found running on this computer - start your local server and "
                "click Look Again, or pick OpenAI or Somewhere else."
            )
        keep_previous = self._user_chose and previous in self._cards.keys()
        choice = previous if keep_previous else self.default_choice(found)
        self._cards.select(choice)
        if keep_previous:
            self._url.setText(kept[0])
            self._key.setText(kept[1])
            self._model.setCurrentText(kept[2])
            self._dimensions.setText(kept[3])

    def _add_leading_choices(self) -> None:
        pass

    def _add_trailing_choices(self) -> None:
        pass

    def default_choice(self, found: list[FoundServer]) -> str:
        raise NotImplementedError

    def _server_for(self, key: str | None) -> FoundServer | None:
        return next((s for s in self._wizard.found if s.base_url == key), None)

    def _on_choice_changed(self, *_args) -> None:
        key = self._cards.selected()
        if key is None:
            return
        self._test_status.setText("")
        self._hint.setText("")
        self._form_container.setVisible(key not in (_SAME_AS_CHAT, _SKIP))
        self._test_row.setVisible(key != _SKIP)
        server = self._server_for(key)
        self._url.setReadOnly(key not in (_OTHER, _OPENAI))
        self._key.setEnabled(key in (_OTHER, _OPENAI))
        if server is not None:
            self._url.setText(server.base_url)
            self._key.clear()
            self._set_models(server.embedding_models if self.embeddings else server.chat_models)
            self._after_server_selected(server)
        elif key == _OPENAI:
            self._url.setText(ai_setup.OPENAI_BASE_URL)
            self._key.setText(self._wizard.initial.get("api_key", ""))
            recommended = (
                ai_setup.RECOMMENDED_OPENAI_EMBEDDING_MODEL if self.embeddings
                else ai_setup.RECOMMENDED_OPENAI_CHAT_MODEL
            )
            self._set_models([recommended])
            self._dimensions.setText(ai_setup.RECOMMENDED_OPENAI_EMBEDDING_DIMENSIONS)
        elif key == _OTHER:
            self._url.clear()
            self._set_models([])
            self._url.setFocus()
        self.completeChanged.emit()

    def _after_server_selected(self, server: FoundServer) -> None:
        self._dimensions.clear()

    def _set_models(self, models: list[str]) -> None:
        current = self._model.currentText()
        self._model.clear()
        self._model.addItems(models)
        if current in models:
            self._model.setCurrentText(current)

    def _list_models(self) -> None:
        url = self._url.text().strip()
        if not url:
            return
        self._test_status.setText("Asking for the list of models...")
        self._lister = ModelLister(AiConfig(url, self._key.text().strip(), ""), parent=self)
        self._lister.finished.connect(self._on_models_listed)

    def _on_models_listed(self, ok: bool, models: list, message: str) -> None:
        self._lister = None
        if not ok:
            self._test_status.setText(f"⚠️ {message}")
            return
        chat, embedding = ai_setup.split_models(models)
        wanted = embedding if self.embeddings else chat
        # A server that only lists one kind might be named unusually -
        # offer everything rather than nothing.
        self._set_models(wanted or models)
        self._test_status.setText(f"Found {len(models)} model(s).")

    # --- results -------------------------------------------------------

    def choice(self) -> str | None:
        return self._cards.selected()

    def url(self) -> str:
        return self._url.text().strip()

    def api_key(self) -> str:
        return self._key.text().strip()

    def model(self) -> str:
        return self._model.currentText().strip()

    def dimensions(self) -> str:
        return self._dimensions.text().strip()

    def isComplete(self) -> bool:  # noqa: N802 (Qt override)
        return bool(self._cards.selected() and self.url() and self.model())

    def _run_test(self) -> None:
        raise NotImplementedError


class _ChatPage(_ServerPage):
    embeddings = False

    def __init__(self, wizard: "AiSetupWizard"):
        super().__init__(wizard)
        self.setTitle("Chat model")
        self._intro.setText(
            "Where should questions go? A chat model reads your question and suggests "
            "where in the scriptures to look."
        )

    def default_choice(self, found: list[FoundServer]) -> str:
        initial_url = self._wizard.initial.get("base_url", "")
        if any(s.base_url == initial_url for s in found):
            return initial_url
        if initial_url == ai_setup.OPENAI_BASE_URL:
            return _OPENAI
        if initial_url:
            return _OTHER
        suggested = ai_setup.suggested_chat_server(found)
        return suggested.base_url if suggested else _OPENAI

    def _on_choice_changed(self, *args) -> None:
        super()._on_choice_changed(*args)
        initial = self._wizard.initial
        if self.choice() == _OTHER and initial.get("base_url"):
            self._url.setText(initial["base_url"])
            self._key.setText(initial.get("api_key", ""))
        if initial.get("model") and self.url() == initial.get("base_url"):
            self._model.setCurrentText(initial["model"])

    def _run_test(self) -> None:
        if not self.url():
            self._test_status.setText("Enter an address first.")
            return
        self._test_status.setText("Testing...")
        self._test = ConnectionTester(AiConfig(self.url(), self.api_key(), self.model()), parent=self)
        self._test.finished.connect(self._on_tested)

    def _on_tested(self, ok: bool, message: str, needs_key: bool) -> None:
        self._test = None
        if ok:
            self._test_status.setText("✅ Connected.")
        elif needs_key:
            self._test_status.setText("⚠️ This service needs an API key (or the key was rejected).")
        else:
            self._test_status.setText(f"⚠️ {message}")


class _EmbeddingsPage(_ServerPage):
    embeddings = True

    def __init__(self, wizard: "AiSetupWizard"):
        super().__init__(wizard)
        self.setTitle("Study index (optional)")
        self._intro.setText(
            "The study index needs an <b>embedding model</b>. Building it sends the "
            "scriptures and related text, <b>including your notes</b> (never your "
            "Journal), to the service you pick here. You can skip this and set it up later."
        )

    def _add_leading_choices(self) -> None:
        self._cards.add(_SAME_AS_CHAT, "Same as chat", "Use the chat service's address - only if it offers embedding models")

    def _add_trailing_choices(self) -> None:
        self._cards.add(_SKIP, "Skip for now", "No study index - AI-assisted search still works without it")

    def initializePage(self) -> None:  # noqa: N802 (Qt override)
        # The chat choice may have changed since this page was built.
        self.populate(self._wizard.found, self._wizard.scanning)

    def default_choice(self, found: list[FoundServer]) -> str:
        initial_url = self._wizard.initial.get("embeddings_base_url", "")
        if initial_url and any(s.base_url == initial_url for s in found):
            return initial_url
        chat = self._wizard.chat_page
        if chat.choice() == _OPENAI:
            return _SAME_AS_CHAT
        chat_server = self._server_for(chat.choice())
        if chat_server is not None and chat_server.embedding_models:
            return _SAME_AS_CHAT
        with_embedding = [s for s in found if s.embedding_models]
        if with_embedding:
            return with_embedding[0].base_url
        ollama = [s for s in found if s.is_ollama]
        return ollama[0].base_url if ollama else _SKIP

    def _on_choice_changed(self, *args) -> None:
        super()._on_choice_changed(*args)
        key = self.choice()
        chat = self._wizard.chat_page
        if key == _SAME_AS_CHAT:
            self._form_container.setVisible(True)
            self._url.setText(chat.url())
            self._url.setReadOnly(True)
            self._key.setEnabled(False)
            self._key.clear()
            chat_server = self._server_for(chat.choice())
            if chat.choice() == _OPENAI:
                self._set_models([ai_setup.RECOMMENDED_OPENAI_EMBEDDING_MODEL])
                self._dimensions.setText(ai_setup.RECOMMENDED_OPENAI_EMBEDDING_DIMENSIONS)
            else:
                self._set_models(chat_server.embedding_models if chat_server else [])
            self.completeChanged.emit()

    def _after_server_selected(self, server: FoundServer) -> None:
        super()._after_server_selected(server)
        if server.is_ollama and not server.embedding_models:
            command = ai_setup.ollama_pull_command(ai_setup.RECOMMENDED_OLLAMA_EMBEDDING_MODEL)
            self._hint.setText(
                "Ollama doesn't have an embedding model yet. Run this in a terminal, "
                f"then click <b>Refresh</b>:<br><code>{command}</code><br>"
                "(about 600 MB - Google's EmbeddingGemma, built for exactly this)"
            )
            self._model.setCurrentText(ai_setup.RECOMMENDED_OLLAMA_EMBEDDING_MODEL)

    def isComplete(self) -> bool:  # noqa: N802 (Qt override)
        key = self.choice()
        if key == _SKIP:
            return True
        return bool(key and self.url() and self.model())

    def _run_test(self) -> None:
        if not self.url() or not self.model():
            self._test_status.setText("Pick an address and a model first.")
            return
        dims = self.dimensions()
        self._test_status.setText("Testing...")
        self._test = EmbeddingRequest(
            AiConfig(self.url(), self.effective_api_key(), self.model()),
            self.model(),
            ["Faith is the substance of things hoped for."],
            int(dims) if dims.isdigit() else None,
            self,
        )
        self._test.succeeded.connect(
            lambda vectors: self._set_test_status(f"✅ Works - {len(vectors[0]):,} numbers per piece.")
        )
        self._test.failed.connect(lambda message, _k, _a: self._set_test_status(f"⚠️ {message}"))

    def _set_test_status(self, text: str) -> None:
        self._test = None
        self._test_status.setText(text)

    def effective_api_key(self) -> str:
        return self._wizard.chat_page.api_key() if self.choice() == _SAME_AS_CHAT else self.api_key()


class _FinishPage(QWizardPage):
    def __init__(self, wizard: "AiSetupWizard"):
        super().__init__()
        self._wizard = wizard
        self.setTitle("All set")
        layout = QVBoxLayout(self)
        self._summary = _label("", rich=True)
        layout.addWidget(self._summary)
        self.build_now = ToggleRow("Start building the study index when I click Finish")
        layout.addWidget(self.build_now)
        self._build_note = _label(
            "Building runs in the background and can be stopped and resumed any time - "
            "usually minutes with a hosted service or a graphics card, longer without one.",
            secondary=True,
        )
        layout.addWidget(self._build_note)
        layout.addWidget(_label(
            "You can change any of this later under Menu → AI Integration → AI Settings..., "
            f"or run this wizard again. Help: {guide_link_html()}", rich=True,
        ))
        layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802 (Qt override)
        w = self._wizard
        lines = [f"<b>Chat:</b> {w.chat_page.model()} at {w.chat_page.url()}"]
        if w.embeddings_page.choice() == _SKIP:
            lines.append("<b>Study index:</b> skipped for now")
        else:
            url = w.chat_page.url() if w.embeddings_page.choice() == _SAME_AS_CHAT else w.embeddings_page.url()
            lines.append(f"<b>Study index:</b> {w.embeddings_page.model()} at {url}")
        lines.append("AI-assisted search will be turned on.")
        self._summary.setText("<br>".join(lines))
        has_index = w.embeddings_page.choice() != _SKIP
        self.build_now.setVisible(has_index)
        self._build_note.setVisible(has_index)
        self.build_now.setChecked(has_index)


class AiSetupWizard(QWizard):
    """`initial` holds the current settings (same keys as the result
    properties below) so re-running the wizard starts from them. After
    exec() returns Accepted, read the results from the properties."""

    def __init__(
        self, initial: dict[str, str], link_color: str | None = None, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("AI Setup Wizard")
        if link_color:
            # Rich-text links use the palette's Link role - the default
            # dark blue is nearly unreadable on the dark theme.
            palette = self.palette()
            palette.setColor(QPalette.ColorRole.Link, QColor(link_color))
            self.setPalette(palette)
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.setMinimumSize(600, 600)
        self.initial = initial
        self.found: list[FoundServer] = []
        self.scanning = True
        self._scan: LocalServerScan | None = None

        self.addPage(_WelcomePage())
        self.chat_page = _ChatPage(self)
        self.addPage(self.chat_page)
        self.embeddings_page = _EmbeddingsPage(self)
        self.addPage(self.embeddings_page)
        self.finish_page = _FinishPage(self)
        self.addPage(self.finish_page)

        self.chat_page.populate([], scanning=True)
        self.rescan()

    def rescan(self) -> None:
        self.scanning = True
        self._scan = LocalServerScan(parent=self)
        self._scan.finished.connect(self._on_scanned)

    def _on_scanned(self, found: list) -> None:
        self._scan = None
        self.scanning = False
        self.found = found
        self.chat_page.populate(found, scanning=False)
        self.embeddings_page.populate(found, scanning=False)

    # --- results, as AI Settings stores them ----------------------------

    @property
    def base_url(self) -> str:
        return self.chat_page.url()

    @property
    def api_key(self) -> str:
        return self.chat_page.api_key()

    @property
    def model(self) -> str:
        return self.chat_page.model()

    @property
    def embeddings_base_url(self) -> str:
        """Blank = same as chat (see ai_client.embeddings_config)."""
        page = self.embeddings_page
        if page.choice() in (_SAME_AS_CHAT, _SKIP) or page.url() == self.base_url:
            return ""
        return page.url()

    @property
    def embeddings_api_key(self) -> str:
        return self.embeddings_page.api_key() if self.embeddings_base_url else ""

    @property
    def embedding_model(self) -> str:
        return "" if self.embeddings_page.choice() == _SKIP else self.embeddings_page.model()

    @property
    def embedding_dimensions(self) -> str:
        return "" if self.embeddings_page.choice() == _SKIP else self.embeddings_page.dimensions()

    @property
    def build_now(self) -> bool:
        return bool(self.embedding_model) and self.finish_page.build_now.isChecked()
