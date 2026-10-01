"""Client for the user's own, self-configured AI endpoint (see the AI
Integration menu in main_window.py and AiSettingsDialog in
ui/ai_settings_dialog.py).

Talks to any OpenAI-compatible chat-completions API - this covers OpenAI
itself, several other hosted providers that offer an OpenAI-compatible
endpoint, and a locally-run server such as Ollama's or a local-inference
snap's - never a fixed, built-in provider. The feature is entirely opt-in
and points wherever the user configures it; nothing here ever runs unless
the user has supplied their own base URL. An API key is optional, not
required - a locally-run server commonly doesn't check for one at all,
only a hosted provider does.

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
    api_key: str  # "" is valid - see module docstring
    model: str


def embeddings_config(
    chat: AiConfig, embeddings_base_url: str, embeddings_api_key: str, embedding_model: str
) -> AiConfig:
    """Where embedding requests for the study index go (see
    study_index.py). A blank embeddings URL means "same endpoint as chat."
    A different URL uses only its own key (possibly none, e.g. a local
    Ollama) - never the chat endpoint's, so a hosted provider's API key
    can't leak to some other server just because it was left blank."""
    if not embeddings_base_url.strip():
        return AiConfig(chat.base_url, chat.api_key, embedding_model)
    return AiConfig(embeddings_base_url.strip(), embeddings_api_key.strip(), embedding_model)


# Qt's own classification of "the server specifically rejected this for an
# auth reason" (401/403-shaped errors), as opposed to a network-level
# problem like a wrong port or a dead server - the two need very different
# advice: "add/fix your API key" vs. "check the address". Exposed (no
# leading underscore) since ask.py's own QuestionAsker checks against it
# too, for the same distinction on the /chat/completions call.
AUTH_ERRORS = (
    QNetworkReply.NetworkError.AuthenticationRequiredError,
    QNetworkReply.NetworkError.ContentAccessDenied,
)


def build_request(config: AiConfig, path: str) -> QNetworkRequest:
    request = QNetworkRequest(QUrl(config.base_url.rstrip("/") + path))
    request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
    if config.api_key:
        request.setRawHeader(b"Authorization", f"Bearer {config.api_key}".encode())
    return request


class ConnectionTester(QObject):
    """Fires a single GET .../models - the standard OpenAI-compatible
    "list models" endpoint every provider this targets implements, cheap
    (no completion tokens spent) and a good stand-in for "is this base
    URL (+ API key, if it needs one) actually valid".

    `finished(ok, message, needs_api_key)` fires exactly once -
    `needs_api_key` is true when the failure specifically looks like a
    missing/wrong API key, so the caller can prompt for one rather than
    just show a generic network error. Keep a reference to this object
    until it fires (PySide6 can garbage-collect it early otherwise, same
    as any other QObject not rooted in a widget hierarchy)."""

    finished = Signal(bool, str, bool)

    def __init__(self, config: AiConfig, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply = self._manager.get(build_request(config, "/models"))
        self._reply.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        reply = self._reply
        error = reply.error()
        if error != QNetworkReply.NetworkError.NoError:
            self.finished.emit(False, reply.errorString(), error in AUTH_ERRORS)
        else:
            self.finished.emit(True, "Connected successfully.", False)
        reply.deleteLater()
