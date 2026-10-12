"""Client for the user's own, self-configured AI endpoint (see the AI
Integration menu in main_window.py and AiSettingsDialog in
ui/ai_settings_dialog.py).

Talks to two kinds of API, never a fixed, built-in provider:

- Any OpenAI-compatible chat-completions API - OpenAI itself, the many
  hosted providers with a compatible endpoint (Google Gemini, OpenRouter,
  Groq, Mistral, ...), and locally-run servers such as Ollama's or a
  local-inference snap's - through Qt's own networking.
- Anthropic's Claude, when the base URL is Anthropic's (is_anthropic),
  through Anthropic's official Python SDK on a background thread.
  Anthropic offers no embeddings, so the study index then needs an
  embeddings endpoint of its own.

ChatRequest is the one way the rest of the app asks a chat model
anything; it hides which of the two is in use. Given a JSON schema it
asks for structured output - the reply is constrained to that schema
(e.g. only numbers from the list on offer) by the provider itself, so a
small model can't answer in prose or invent a number. A server that
doesn't support structured output is asked again without it, and
remembered. The feature is entirely opt-in
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

import json
import re
import threading
from dataclasses import dataclass
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

ANTHROPIC_BASE_URL = "https://api.anthropic.com"
# The model offered first for Claude - Anthropic's current default.
RECOMMENDED_ANTHROPIC_MODEL = "claude-opus-5-5"
REQUEST_TIMEOUT_MS = 120_000


@dataclass(frozen=True)
class AiConfig:
    base_url: str
    api_key: str  # "" is valid - see module docstring
    model: str


def is_anthropic(config: AiConfig) -> bool:
    host = urlparse(config.base_url.strip()).hostname or ""
    return host == "anthropic.com" or host.endswith(".anthropic.com")


def embeddings_config(
    chat: AiConfig, embeddings_base_url: str, embeddings_api_key: str, embedding_model: str
) -> AiConfig:
    """Where embedding requests for the study index go (see
    study_index.py). A blank embeddings URL means "same endpoint as chat."
    A different URL uses only its own key (possibly none, e.g. a local
    Ollama) - never the chat endpoint's, so a hosted provider's API key
    can't leak to some other server just because it was left blank."""
    if not embeddings_base_url.strip():
        if is_anthropic(chat):  # Anthropic has no embeddings endpoint
            return AiConfig("", "", embedding_model)
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
        if is_anthropic(config):
            # The same check through Anthropic's own models list.
            self._listing = AnthropicModelListing(config, self)
            self._listing.finished.connect(
                lambda ok, _models, message, needs_key: self.finished.emit(
                    ok, "Connected successfully." if ok else message, needs_key
                )
            )
            return
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


# ---------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------


def numbers_schema(count: int) -> dict:
    """A reply of {"numbers": [...]}, each one of 1..count - for every
    "choose from this numbered list" question. (Structured output needs
    an object at the top level; parse_selection and friends find the
    array inside it the same way they find a bare one.)"""
    return {
        "type": "object",
        "properties": {
            "numbers": {"type": "array", "items": {"type": "integer", "enum": list(range(1, count + 1))}}
        },
        "required": ["numbers"],
        "additionalProperties": False,
    }


def strings_schema(key: str) -> dict:
    return {
        "type": "object",
        "properties": {key: {"type": "array", "items": {"type": "string"}}},
        "required": [key],
        "additionalProperties": False,
    }


# Servers that rejected structured output once - asked without it from
# then on, for the rest of the session.
_NO_SCHEMA_SERVERS: set[str] = set()


def openai_chat_payload(
    config: AiConfig, messages: list[dict], temperature: float, schema: dict | None
) -> dict:
    payload: dict = {"model": config.model or "gpt-4o-mini", "temperature": temperature, "messages": messages}
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "answer", "strict": True, "schema": schema},
        }
    return payload


# ---------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------

# Models that take `fallbacks: "default"` - a request their safety
# classifiers decline is re-run on Anthropic's recommended fallback model
# instead of failing (beta server-side-fallback-2026-07-01).
_ANTHROPIC_FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"})
# Models that take output_config.effort ("low" here: these are quick
# choose-from-a-list questions). Older ones reject it.
_ANTHROPIC_EFFORT_RE = re.compile(r"^claude-(opus-(4-[5-9]|5)|sonnet-(4-6|5)|haiku-5|fable-5|mythos-5)")
ANTHROPIC_MAX_TOKENS = 8000


def anthropic_chat_params(config: AiConfig, messages: list[dict], schema: dict | None) -> dict:
    """The Messages API request for an OpenAI-style message list: system
    messages become the top-level `system`. No temperature - current
    Claude models reject one."""
    model = config.model or RECOMMENDED_ANTHROPIC_MODEL
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    params: dict = {
        "model": model,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"],
    }
    if system:
        params["system"] = system
    output_config: dict = {}
    if _ANTHROPIC_EFFORT_RE.match(model):
        output_config["effort"] = "low"
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    if output_config:
        params["output_config"] = output_config
    if model in _ANTHROPIC_FALLBACK_MODELS:
        params["betas"] = ["server-side-fallback-2026-07-01"]
        params["fallbacks"] = "default"
    return params


_anthropic_clients: dict[tuple[str, str], object] = {}
_anthropic_lock = threading.Lock()


def _anthropic_client(config: AiConfig):
    """One SDK client per key and address, reused - each holds a
    connection pool (see embeddings.py on the snap's open-files limit)."""
    import anthropic  # only needed when Claude is configured

    base = config.base_url.strip().rstrip("/")
    base = base[: -len("/v1")] if base.endswith("/v1") else base  # the SDK adds /v1 itself
    key = (base, config.api_key)
    with _anthropic_lock:
        client = _anthropic_clients.get(key)
        if client is None:
            client = anthropic.Anthropic(api_key=config.api_key or None, base_url=base or None, timeout=120.0)
            _anthropic_clients[key] = client
        return client


def _anthropic_error(exc: Exception) -> tuple[str, bool]:
    """(message, needs_api_key) for an SDK error."""
    import anthropic

    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return "Anthropic rejected the API key.", True
    if isinstance(exc, anthropic.NotFoundError):
        return "Anthropic doesn't know that model name.", False
    if isinstance(exc, anthropic.RateLimitError):
        return "Anthropic's rate limit was reached - try again in a minute.", False
    if isinstance(exc, anthropic.APIStatusError):
        return f"Anthropic returned an error ({exc.status_code}): {exc.message}", False
    if isinstance(exc, anthropic.APIConnectionError):
        return "Couldn't reach Anthropic - check the internet connection.", False
    return str(exc), False


def anthropic_reply_text(response) -> tuple[str | None, str]:
    """(text, problem) from a Messages API response."""
    if response.stop_reason == "refusal":
        return None, "Claude declined this request."
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        return None, "Claude returned no answer."
    return text, ""


class AnthropicModelListing(QObject):
    """Anthropic's model list, fetched on a background thread.
    `finished(ok, models, message, needs_api_key)` fires once."""

    finished = Signal(bool, list, str, bool)

    def __init__(self, config: AiConfig, parent: QObject | None = None):
        super().__init__(parent)
        # Started on the next event-loop turn, not here: a thread that
        # finishes at once (no library, an instant error) would otherwise
        # fire `finished` before the caller has connected to it.
        QTimer.singleShot(0, lambda: threading.Thread(target=self._run, args=(config,), daemon=True).start())

    def _run(self, config: AiConfig) -> None:
        try:
            client = _anthropic_client(config)
            models = [m.id for m in client.models.list()]
        except ImportError:
            self.finished.emit(False, [], "The Anthropic library isn't installed.", False)
            return
        except Exception as exc:  # noqa: BLE001 - reported to the user
            message, needs_key = _anthropic_error(exc)
            self.finished.emit(False, [], message, needs_key)
            return
        self.finished.emit(True, models, "", False)


# ---------------------------------------------------------------------
# The one chat request
# ---------------------------------------------------------------------


class ChatRequest(QObject):
    """One chat completion from whichever provider `config` names.

    `finished(content, message, needs_api_key)` fires exactly once:
    `content` is the reply text, or None on failure - then `message` says
    why and `needs_api_key` whether it looks like a missing or rejected
    key. Keep a reference to this object until it fires."""

    finished = Signal(object, str, bool)

    def __init__(
        self,
        config: AiConfig,
        messages: list[dict],
        *,
        temperature: float = 0.0,
        schema: dict | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._config = config
        self._messages = messages
        self._temperature = temperature
        self._schema = schema
        if is_anthropic(config):
            # Next event-loop turn - see AnthropicModelListing.
            QTimer.singleShot(
                0, lambda: threading.Thread(target=self._run_anthropic, args=(schema,), daemon=True).start()
            )
        else:
            self._manager = QNetworkAccessManager(self)
            self._send_openai(schema if config.base_url not in _NO_SCHEMA_SERVERS else None)

    # --- OpenAI-compatible -------------------------------------------

    def _send_openai(self, schema: dict | None) -> None:
        self._sent_schema = schema
        payload = openai_chat_payload(self._config, self._messages, self._temperature, schema)
        request = build_request(self._config, "/chat/completions")
        request.setTransferTimeout(REQUEST_TIMEOUT_MS)
        self._reply = self._manager.post(request, json.dumps(payload).encode("utf-8"))
        self._reply.finished.connect(self._on_openai_reply)

    def _on_openai_reply(self) -> None:
        reply = self._reply
        error = reply.error()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        body = bytes(reply.readAll())
        reply.deleteLater()
        if error != QNetworkReply.NetworkError.NoError:
            if self._sent_schema is not None and status in (400, 422, 500, 501):
                # Most likely structured output isn't supported here - ask
                # once more without it, and don't try it again this session.
                _NO_SCHEMA_SERVERS.add(self._config.base_url)
                self._send_openai(None)
                return
            self.finished.emit(None, reply.errorString(), error in AUTH_ERRORS)
            return
        try:
            content = json.loads(body)["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            self.finished.emit(None, "The AI endpoint's response wasn't in the expected format.", False)
            return
        if not isinstance(content, str):
            self.finished.emit(None, "The AI endpoint's response wasn't in the expected format.", False)
            return
        self.finished.emit(content, "", False)

    # --- Anthropic (background thread) ---------------------------------

    def _run_anthropic(self, schema: dict | None) -> None:
        try:
            client = _anthropic_client(self._config)
            params = anthropic_chat_params(self._config, self._messages, schema)
            if "betas" in params:
                response = client.beta.messages.create(**params)
            else:
                response = client.messages.create(**params)
        except ImportError:
            self.finished.emit(None, "The Anthropic library isn't installed.", False)
            return
        except Exception as exc:  # noqa: BLE001 - reported to the user
            import anthropic

            if schema is not None and isinstance(exc, anthropic.BadRequestError):
                self._run_anthropic(None)  # an older model without structured output
                return
            message, needs_key = _anthropic_error(exc)
            self.finished.emit(None, message, needs_key)
            return
        text, problem = anthropic_reply_text(response)
        self.finished.emit(text, problem, False)
