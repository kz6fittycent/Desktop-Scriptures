"""Non-UI helpers for the AI Setup Wizard (ui/ai_setup_wizard.py): finding
AI servers already running on this computer, listing their models, and
telling chat models from embedding models.

Detection only ever looks at localhost, on the default ports of the
common local servers below, with a short timeout - it never scans the
network or contacts anything remote. Every server here speaks the same
OpenAI-compatible API the rest of the app uses (see ai_client.py), so a
found server's address is exactly what goes in AI Settings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply

from scriptures.ai_client import AiConfig, build_request

WIKI_URL = "https://github.com/kz6fittycent/Desktop-Scriptures/wiki"
AI_SETUP_GUIDE_URL = f"{WIKI_URL}/Choosing-an-AI-Setup"

OPENAI_BASE_URL = "https://api.openai.com/v1"
RECOMMENDED_OPENAI_CHAT_MODEL = "gpt-4o-mini"
RECOMMENDED_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
RECOMMENDED_OPENAI_EMBEDDING_DIMENSIONS = "512"
# Suggested `ollama pull` for each role when nothing suitable is installed.
RECOMMENDED_OLLAMA_EMBEDDING_MODEL = "embeddinggemma"
RECOMMENDED_OLLAMA_CHAT_MODEL = "gemma3:4b"

PROBE_TIMEOUT_MS = 1500


@dataclass(frozen=True)
class KnownServer:
    name: str
    base_url: str
    is_ollama: bool = False


# Default ports only. An Ubuntu inference snap (e.g. `gemma3`) runs
# llama.cpp's server; 8328 is gemma3's default - other inference snaps
# may use other ports, which is what the wizard's "somewhere else"
# option is for.
KNOWN_LOCAL_SERVERS = (
    KnownServer("Ollama", "http://localhost:11434/v1", is_ollama=True),
    KnownServer("Inference snap (llama.cpp)", "http://127.0.0.1:8328/v1"),
    KnownServer("LM Studio", "http://localhost:1234/v1"),
    KnownServer("llama.cpp server", "http://localhost:8080/v1"),
    KnownServer("vLLM", "http://localhost:8000/v1"),
)

# Substrings that mark a model as an embedding model rather than a chat
# one - a name heuristic, since only some servers report capabilities.
_EMBEDDING_MARKERS = ("embed", "bge-", "bge:", "e5-", "gte-", "minilm", "nomic", "arctic-embed")


def is_embedding_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return any(marker in lowered for marker in _EMBEDDING_MARKERS)


def parse_models(body: bytes) -> list[str]:
    """Model ids from an OpenAI-style GET .../models response
    ({"data": [{"id": ...}, ...]}), in the server's order. [] for
    anything else."""
    try:
        data = json.loads(body).get("data", [])
        return [str(m["id"]) for m in data if isinstance(m, dict) and m.get("id")]
    except (ValueError, AttributeError, TypeError):
        return []


# Chat models specialized for something other than conversation - still
# listed, just never suggested first.
_SPECIALIST_MARKERS = ("code", "coder", "math", "vision", "-vl", "guard")


def _is_specialist(model_id: str) -> bool:
    lowered = model_id.lower()
    return any(marker in lowered for marker in _SPECIALIST_MARKERS)


def split_models(models: list[str]) -> tuple[list[str], list[str]]:
    """(chat models, embedding models). Chat models are ordered general-
    purpose first (e.g. a coding model like qwen3-coder after gemma3), so
    the first one is a sensible suggestion."""
    embedding = [m for m in models if is_embedding_model(m)]
    chat = [m for m in models if not is_embedding_model(m)]
    chat.sort(key=_is_specialist)  # stable: keeps the server's order otherwise
    return chat, embedding


def suggested_chat_server(found: list["FoundServer"]) -> "FoundServer | None":
    """The found server to suggest for chat: one offering a general-
    purpose chat model if any does, else any with a chat model at all."""
    general = [s for s in found if any(not _is_specialist(m) for m in s.chat_models)]
    with_chat = [s for s in found if s.chat_models]
    return (general or with_chat or [None])[0]


def ollama_pull_command(model: str) -> str:
    return f"ollama pull {model}"


@dataclass(frozen=True)
class FoundServer:
    name: str
    base_url: str
    models: list[str]
    is_ollama: bool = False

    @property
    def chat_models(self) -> list[str]:
        return split_models(self.models)[0]

    @property
    def embedding_models(self) -> list[str]:
        return split_models(self.models)[1]


class ModelLister(QObject):
    """GET {base_url}/models once - `finished(ok, models, message)`."""

    finished = Signal(bool, list, str)

    def __init__(self, config: AiConfig, timeout_ms: int = 10_000, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        request = build_request(config, "/models")
        request.setTransferTimeout(timeout_ms)
        self._reply = self._manager.get(request)
        self._reply.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        reply = self._reply
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.finished.emit(False, [], reply.errorString())
        else:
            self.finished.emit(True, parse_models(bytes(reply.readAll())), "")
        reply.deleteLater()


class LocalServerScan(QObject):
    """Checks every KNOWN_LOCAL_SERVERS address at once; `finished(found)`
    fires once all have answered or timed out, with a FoundServer for
    each that responded, in KNOWN_LOCAL_SERVERS order."""

    finished = Signal(list)

    def __init__(self, servers=None, parent: QObject | None = None):
        super().__init__(parent)
        self._servers = list(KNOWN_LOCAL_SERVERS if servers is None else servers)
        self._results: dict[int, FoundServer | None] = {}
        self._listers = []
        for i, server in enumerate(self._servers):
            lister = ModelLister(AiConfig(server.base_url, "", ""), PROBE_TIMEOUT_MS, self)
            lister.finished.connect(
                lambda ok, models, _msg, i=i, server=server: self._on_result(i, server, ok, models)
            )
            self._listers.append(lister)

    def _on_result(self, i: int, server: KnownServer, ok: bool, models: list) -> None:
        self._results[i] = (
            FoundServer(server.name, server.base_url, models, server.is_ollama) if ok else None
        )
        if len(self._results) == len(self._servers):
            found = [self._results[i] for i in range(len(self._servers)) if self._results[i]]
            self.finished.emit(found)
