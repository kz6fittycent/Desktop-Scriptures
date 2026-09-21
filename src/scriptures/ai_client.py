"""Client for the user's own, self-configured AI endpoint (see the Ask
menu in main_window.py and AiSettingsDialog in ui/ai_settings_dialog.py).

Talks to any OpenAI-compatible chat-completions API - this covers OpenAI
itself, several other hosted providers that offer an OpenAI-compatible
endpoint, and a locally-run server such as Ollama's - never a fixed,
built-in provider. The feature is entirely opt-in and points wherever the
user configures it; nothing here ever runs unless the user has supplied
their own base URL and API key.

Nothing in this module is ever treated as a source of truth for scripture
content - see ask.py, which is the only thing that actually asks a
question, and is the one place a model's answer gets validated against
the real local database before anything reaches the user.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


@dataclass(frozen=True)
class AiConfig:
    base_url: str
    api_key: str
    model: str


def _request(config: AiConfig, path: str) -> QNetworkRequest:
    request = QNetworkRequest(QUrl(config.base_url.rstrip("/") + path))
    request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
    request.setRawHeader(b"Authorization", f"Bearer {config.api_key}".encode())
    return request


class ConnectionTester(QObject):
    """Fires a single GET .../models - the standard OpenAI-compatible
    "list models" endpoint every provider this targets implements, cheap
    (no completion tokens spent) and a good stand-in for "is this base
    URL + API key actually valid". `finished(ok, message)` fires exactly
    once; keep a reference to this object until it does (PySide6 can
    garbage-collect it early otherwise, same as any other QObject not
    rooted in a widget hierarchy)."""

    finished = Signal(bool, str)

    def __init__(self, config: AiConfig, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply = self._manager.get(_request(config, "/models"))
        self._reply.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        reply = self._reply
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.finished.emit(False, reply.errorString())
        else:
            self.finished.emit(True, "Connected successfully.")
        reply.deleteLater()
