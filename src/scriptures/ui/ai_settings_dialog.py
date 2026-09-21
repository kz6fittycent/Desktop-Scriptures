"""AI Settings dialog (see main_window.py's Ask menu and ai_client.py's
module docstring for the overall design: an opt-in, bring-your-own-
endpoint AI-assisted search, never a built-in provider).

Alpaca-style configuration: a base URL and API key for any OpenAI-
compatible chat-completions endpoint (OpenAI itself, another hosted
provider with a compatible endpoint, or a locally-run server such as
Ollama's), plus which model to ask for. A "Test Connection" button
confirms the base URL + key actually work before the user leaves the
dialog, without spending any completion tokens.
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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from scriptures.ai_client import AiConfig, ConnectionTester


class AiSettingsDialog(QDialog):
    """On accept, `enabled`/`base_url`/`api_key`/`model` hold the final
    values to persist - see main_window.py's `_show_ai_settings`."""

    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        api_key: str,
        model: str,
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
        self._api_key_edit.setPlaceholderText("sk-...")
        show_button = QPushButton("Show")
        show_button.setCheckable(True)
        show_button.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._api_key_edit)
        key_row.addWidget(show_button)
        form.addRow("API Key:", key_row)

        self._model_edit = QLineEdit(model)
        self._model_edit.setPlaceholderText("gpt-4o-mini")
        form.addRow("Model:", self._model_edit)

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
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_key_visibility(self, show: bool) -> None:
        self._api_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        )

    def _test_connection(self) -> None:
        base_url = self._base_url_edit.text().strip()
        api_key = self._api_key_edit.text().strip()
        if not base_url or not api_key:
            self._test_status_label.setText("Enter a base URL and API key first.")
            return
        self._test_status_label.setText("Testing...")
        config = AiConfig(base_url=base_url, api_key=api_key, model=self._model_edit.text().strip())
        self._tester = ConnectionTester(config, parent=self)
        self._tester.finished.connect(self._on_test_finished)

    def _on_test_finished(self, ok: bool, message: str) -> None:
        prefix = "✅" if ok else "⚠️"
        self._test_status_label.setText(f"{prefix} {message}")
        self._tester = None

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
