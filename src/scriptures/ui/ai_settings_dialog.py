"""AI Settings dialog (see main_window.py's AI Integration menu and
ai_client.py's module docstring for the overall design: an opt-in,
bring-your-own-endpoint AI-assisted search, never a built-in provider).

Alpaca-style configuration: a base URL and API key for any OpenAI-
compatible chat-completions endpoint (OpenAI itself, another hosted
provider with a compatible endpoint, or a locally-run server such as
Ollama's), plus which model to ask for. A "Test Connection" button
confirms the base URL + key actually work before the user leaves the
dialog, without spending any completion tokens.

Also holds the optional embedding model (and dimensions) the study index
is built with - see study_index.py and the "Build Study Index..." dialog.
Blank means no study index; nothing else changes.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from scriptures.ai_client import AiConfig, ConnectionTester


class AiSettingsDialog(QDialog):
    """On accept, `enabled`/`base_url`/`api_key`/`model`/
    `embedding_model`/`embedding_dimensions` hold the final values to
    persist - see main_window.py's `_show_ai_settings`."""

    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        api_key: str,
        model: str,
        embedding_model: str = "",
        embedding_dimensions: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("AI Settings")
        self.setMinimumWidth(420)
        self._tester: ConnectionTester | None = None

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Ask a question in your own words (e.g. \"how did Christ organize "
            "the Nephite church\") and get pointed at real, matching scripture "
            "- never text the model itself wrote. This is entirely opt-in: "
            "nothing is sent anywhere unless you enable it and provide your "
            "own endpoint below."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._enabled_check = QCheckBox("Enable AI-assisted search")
        self._enabled_check.setChecked(enabled)
        layout.addWidget(self._enabled_check)

        form = QFormLayout()

        self._base_url_edit = QLineEdit(base_url)
        self._base_url_edit.setPlaceholderText("https://api.openai.com/v1")
        form.addRow("Base URL:", self._base_url_edit)

        key_row = QHBoxLayout()
        self._api_key_edit = QLineEdit(api_key)
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText(
            "sk-... (optional - leave blank for a local server that doesn't need one)"
        )
        show_button = QPushButton("Show")
        show_button.setCheckable(True)
        show_button.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._api_key_edit)
        key_row.addWidget(show_button)
        form.addRow("API Key:", key_row)

        self._model_edit = QLineEdit(model)
        self._model_edit.setPlaceholderText("gpt-4o-mini")
        form.addRow("Model:", self._model_edit)

        self._embedding_model_edit = QLineEdit(embedding_model)
        self._embedding_model_edit.setPlaceholderText(
            "e.g. text-embedding-3-small, or nomic-embed-text on Ollama"
        )
        self._embedding_model_edit.setToolTip(
            "Used to build the study index (AI Integration → Build Study Index...). "
            "Leave blank if your endpoint doesn't offer embeddings."
        )
        form.addRow("Embedding model:", self._embedding_model_edit)

        self._embedding_dimensions_edit = QLineEdit(embedding_dimensions)
        self._embedding_dimensions_edit.setPlaceholderText(
            "Optional - e.g. 512 for text-embedding-3-* (smaller index)"
        )
        self._embedding_dimensions_edit.setToolTip(
            "Only some providers support this (OpenAI's text-embedding-3 models do). "
            "Leave blank to use the model's own size."
        )
        form.addRow("Embedding dimensions:", self._embedding_dimensions_edit)

        layout.addLayout(form)

        test_row = QHBoxLayout()
        test_button = QPushButton("Test Connection")
        test_button.clicked.connect(self._test_connection)
        test_row.addWidget(test_button)
        self._test_status_label = QLabel()
        self._test_status_label.setObjectName("resultSecondary")
        self._test_status_label.setWordWrap(True)
        test_row.addWidget(self._test_status_label, 1)
        layout.addLayout(test_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        dimensions = self._embedding_dimensions_edit.text().strip()
        if dimensions and (not dimensions.isdigit() or int(dimensions) <= 0):
            QMessageBox.warning(
                self, "AI Settings", "Embedding dimensions should be a whole number, or blank."
            )
            return
        self.accept()

    def _toggle_key_visibility(self, show: bool) -> None:
        self._api_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        )

    def _test_connection(self) -> None:
        base_url = self._base_url_edit.text().strip()
        if not base_url:
            self._test_status_label.setText("Enter a base URL first.")
            return
        self._test_status_label.setText("Testing...")
        api_key = self._api_key_edit.text().strip()
        config = AiConfig(base_url=base_url, api_key=api_key, model=self._model_edit.text().strip())
        self._tester = ConnectionTester(config, parent=self)
        self._tester.finished.connect(
            lambda ok, message, needs_key: self._on_test_finished(ok, message, needs_key, bool(api_key))
        )

    def _on_test_finished(self, ok: bool, message: str, needs_api_key: bool, had_key: bool) -> None:
        prefix = "✅" if ok else "⚠️"
        self._test_status_label.setText(f"{prefix} {message}")
        self._tester = None
        if not needs_api_key:
            return
        if had_key:
            body = (
                "This endpoint rejected the API key you entered (authentication "
                "error). Double-check the key and try again."
            )
        else:
            body = (
                "This endpoint requires an API key to connect. If you're using "
                "a hosted provider like OpenAI, enter your API key above and "
                "try again - a locally-running server (like Ollama or a local "
                "LLM snap) usually doesn't need one."
            )
        QMessageBox.warning(self, "AI Settings", body)

    @property
    def enabled(self) -> bool:
        return self._enabled_check.isChecked()

    @property
    def base_url(self) -> str:
        return self._base_url_edit.text().strip()

    @property
    def api_key(self) -> str:
        return self._api_key_edit.text().strip()

    @property
    def model(self) -> str:
        return self._model_edit.text().strip()

    @property
    def embedding_model(self) -> str:
        return self._embedding_model_edit.text().strip()

    @property
    def embedding_dimensions(self) -> str:
        return self._embedding_dimensions_edit.text().strip()
